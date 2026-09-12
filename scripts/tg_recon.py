"""只读抓取公开频道的历史消息，用来做竞品分析。

    python scripts/tg_recon.py login -a tony                # 交互式登录，每个账号跑一次
    python scripts/tg_recon.py accounts                     # 看有哪些 session、分别是谁
    python scripts/tg_recon.py dump xiaoshuwu --limit 600   # 拉历史到 jsonl
    python scripts/tg_recon.py stats xiaoshuwu              # 汇总：ERR / 节奏 / 外链 / 广告位

session 按账号分开存成 data/recon-<账号名>.session，互不影响。
账号名只是给你自己认的标签，随便取（tony / main / alt 都行）。
只有一个 session 时 dump 不用写 -a，会自动用那个；有多个就必须指明。

用的是你自己的 user 账号（Telethon），不是 bot。bot 读不了自己没被拉进去的
频道，也读不了开了内容保护的频道正文——竞品号基本都开着，所以必须走 user。

**只读**：这个脚本里没有任何发送 / 转发 / 加群 / 删除的调用，
唯一会写的是 data/recon.session 和你用 --out 指定的输出文件。

⚠️ 登录要输手机号、短信验证码、两步验证密码，只能你自己在终端敲。
   data/recon.session 等同于账号凭据，.gitignore 已经拦了 *.session，
   别提交、别外发、别挂进 docker 卷里带出去。
⚠️ 抓取每页之间有 sleep。短时间猛拉会吃 FloodWait，极端情况账号被限制，
   别把 --limit 开到上万。做趋势跟踪的话，每天增量拉一两百条就够。
"""
from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path
from statistics import median
from urllib.parse import urlparse

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config.settings import DATA_DIR, settings  # noqa: E402

try:
    from telethon import TelegramClient
    from telethon.tl.functions.channels import GetFullChannelRequest
except ImportError:  # pragma: no cover
    sys.exit(
        "缺 telethon。它只给这个调研脚本用，没进 requirements.txt：\n"
        "    conda run -n tg-course-worker pip install telethon"
    )

OUT_DIR = DATA_DIR / "recon"
SESSION_GLOB = "recon-*.session"

# 粗筛广告位用。不追求准，只要能把量级看出来
AD_HINTS = ("广告", "推广", "赞助", "合作", "商务", "招租", "投放", "开户", "代理加盟")


def _session_path(account: str) -> Path:
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,32}", account):
        sys.exit(f"账号名 {account!r} 不合法：只能用字母数字和 _ -，最长 32 位。")
    return DATA_DIR / f"recon-{account}.session"


def _existing() -> list[tuple[str, Path]]:
    """已有的 session，按账号名排序。"""
    return sorted(
        (p.stem.removeprefix("recon-"), p) for p in DATA_DIR.glob(SESSION_GLOB)
    )


def _resolve_account(explicit: str | None) -> str:
    """dump/stats 没写 -a 时，只有一个 session 就用它，有多个必须指明。"""
    if explicit:
        return explicit
    found = _existing()
    if not found:
        sys.exit(
            "还没有任何已登录的账号。先在**能交互的终端**里跑：\n"
            "    python scripts/tg_recon.py login -a tony\n"
            "别用 conda run——它不转发 stdin，验证码输不进去。"
        )
    if len(found) > 1:
        names = "  ".join(n for n, _ in found)
        sys.exit(f"有多个账号，用 -a 指明要用哪个：{names}")
    return found[0][0]


def _client(account: str) -> TelegramClient:
    if not settings.tg_api_id or not settings.tg_api_hash:
        sys.exit(
            "没配 TG_API_ID / TG_API_HASH。去 https://my.telegram.org → API development tools\n"
            "申请一对，填进 .env（照抄 .env.example 里那一节）。\n"
            "注意这是 user API 凭据，和发布用的 bot token 是两套东西。"
        )
    return TelegramClient(str(_session_path(account)), settings.tg_api_id, settings.tg_api_hash)


def _urls(msg) -> list[str]:
    """正文里的链接。超链接锚文本和裸 URL 是两种 entity，都得取。"""
    out: list[str] = []
    text = msg.message or ""
    for ent in msg.entities or []:
        url = getattr(ent, "url", None)
        if url:
            out.append(url)
        elif type(ent).__name__ == "MessageEntityUrl":
            out.append(text[ent.offset : ent.offset + ent.length])
    markup = getattr(msg, "reply_markup", None)
    for row in getattr(markup, "rows", None) or []:
        for btn in getattr(row, "buttons", None) or []:
            if getattr(btn, "url", None):
                out.append(btn.url)
    return out


def _reactions(msg) -> dict[str, int]:
    res = getattr(getattr(msg, "reactions", None), "results", None) or []
    out: dict[str, int] = {}
    for r in res:
        emoji = getattr(r.reaction, "emoticon", None) or str(
            getattr(r.reaction, "document_id", "?")
        )
        out[emoji] = r.count
    return out


def _fwd_from(msg) -> str:
    fwd = getattr(msg, "forward", None)
    if not fwd:
        return ""
    try:
        chat = fwd.chat
        if chat is not None:
            return getattr(chat, "title", "") or getattr(chat, "username", "") or ""
    except Exception:
        pass
    return getattr(getattr(msg, "fwd_from", None), "from_name", "") or ""


def _file(msg) -> dict:
    """附件的文件名和体积。资源号直接把安装包挂在消息上，
    这两个字段才看得出它到底在分发什么、吃掉多少带宽。"""
    doc = getattr(msg, "document", None)
    if not doc:
        return {}
    name = next(
        (a.file_name for a in doc.attributes if hasattr(a, "file_name")), ""
    )
    return {"file_name": name, "file_mb": round(doc.size / 1048576, 1),
            "mime": doc.mime_type}


def _row(msg) -> dict:
    return {
        **_file(msg),
        "id": msg.id,
        "date": msg.date.astimezone(timezone.utc).isoformat(),
        "text": msg.message or "",
        "views": msg.views,
        "forwards": msg.forwards,
        "replies": getattr(getattr(msg, "replies", None), "replies", None),
        "reactions": _reactions(msg),
        "fwd_from": _fwd_from(msg),
        "media": type(msg.media).__name__ if msg.media else "",
        "urls": _urls(msg),
    }


async def _connect_authed(client: TelegramClient) -> None:
    """连上并确认已登录。没登录就直接退出，不要掉进交互式登录流程——
    dump 经常在 conda run / cron 里跑，那里没有 stdin，
    Telethon 的 input() 会抛一个看不出所以然的 EOFError。
    """
    await client.connect()
    if not await client.is_user_authorized():
        await client.disconnect()
        sys.exit(
            "这个 session 还没登录。先在**能交互的终端**里跑一次：\n"
            "    python scripts/tg_recon.py login\n"
            "注意别用 conda run——它不转发 stdin，验证码根本输不进去。\n"
            "环境已经激活的话直接 python 就行。"
        )


async def cmd_login(args: argparse.Namespace) -> None:
    if not sys.stdin.isatty():
        sys.exit(
            "stdin 不是终端，登录要输手机号和验证码，这样跑不了。\n"
            "在交互式终端里直接跑 python scripts/tg_recon.py login -a <账号名>，\n"
            "别套 conda run / nohup / 管道。"
        )
    path = _session_path(args.account)
    if path.exists():
        print(f"注意：{path} 已存在，登录成功会覆盖成新账号。")
    async with _client(args.account) as client:
        me = await client.get_me()
        print(f"已登录 [{args.account}]：{me.first_name or ''} "
              f"(@{me.username or '-'}, id={me.id})")
        print(f"session 写在 {path}，下次 dump 加 -a {args.account} 即可。")


async def cmd_accounts(args: argparse.Namespace) -> None:
    found = _existing()
    if not found:
        print("还没有任何 session。跑 login -a <账号名> 建一个。")
        return
    for name, path in found:
        client = _client(name)
        try:
            await client.connect()
            if await client.is_user_authorized():
                me = await client.get_me()
                who = f"{me.first_name or ''} (@{me.username or '-'}, id={me.id})"
            else:
                who = "未授权（登录没走完，重新 login 一次）"
        except Exception as e:
            who = f"读不出来：{type(e).__name__}: {e}"
        finally:
            await client.disconnect()
        print(f"  {name:<12} {who}")
        print(f"  {'':<12} {path}")


async def cmd_dump(args: argparse.Namespace) -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out = args.out or OUT_DIR / f"{args.channel.lstrip('@')}.jsonl"

    account = _resolve_account(args.account)
    client = _client(account)
    await _connect_authed(client)
    print(f"用账号 [{account}] 抓取")
    try:
        entity = await client.get_entity(args.channel)
        full = await client(GetFullChannelRequest(entity))
        subs = full.full_chat.participants_count
        title = getattr(entity, "title", args.channel)
        print(f"{title}  订阅 {subs:,}  → {out}")

        rows: list[dict] = []
        async for msg in client.iter_messages(entity, limit=args.limit):
            rows.append(_row(msg))
            if len(rows) % 100 == 0:
                print(f"  ...{len(rows)}")
                await asyncio.sleep(args.pause)
    finally:
        await client.disconnect()

    rows.reverse()  # 存成时间正序，方便看趋势
    meta = {"_meta": True, "channel": args.channel, "title": title,
            "subscribers": subs, "fetched_at": datetime.now(timezone.utc).isoformat()}
    with open(out, "w", encoding="utf-8", newline="\n") as f:
        f.write(json.dumps(meta, ensure_ascii=False) + "\n")
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(f"{len(rows)} 条已写入。接着跑：python scripts/tg_recon.py stats {args.channel}")


def _load(channel: str, out: Path | None) -> tuple[dict, list[dict]]:
    path = out or OUT_DIR / f"{channel.lstrip('@')}.jsonl"
    if not path.exists():
        sys.exit(f"没有 {path}，先跑 dump。")
    meta: dict = {}
    rows: list[dict] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        obj = json.loads(line)
        (meta.update(obj) if obj.get("_meta") else rows.append(obj))
    return meta, rows


async def cmd_stats(args: argparse.Namespace) -> None:
    meta, rows = _load(args.channel, args.out)
    if not rows:
        sys.exit("一条都没有。")

    tz = settings.tz
    now = datetime.now(timezone.utc)
    subs = meta.get("subscribers") or 0
    for r in rows:
        r["dt"] = datetime.fromisoformat(r["date"])

    first, last = rows[0]["dt"], rows[-1]["dt"]
    span_days = max((last - first).total_seconds() / 86400, 1)

    print(f"\n== {meta.get('title', args.channel)} ==")
    print(f"订阅 {subs:,}   样本 {len(rows)} 条   "
          f"{first.astimezone(tz):%Y-%m-%d} → {last.astimezone(tz):%Y-%m-%d}"
          f"（{span_days:.0f} 天，{len(rows) / span_days:.1f} 条/天）")

    # 阅读数只统计"熟了"的帖子：TG 的 view 要 7-10 天才收敛，
    # 混进新帖会把均值压低，看上去像在衰减
    mature = [r for r in rows if r["views"] and (now - r["dt"]).days >= args.mature_days]
    if mature:
        v = sorted(r["views"] for r in mature)
        print(f"\n成熟帖（≥{args.mature_days} 天）{len(mature)} 条："
              f"中位 {median(v):,.0f}  均值 {sum(v) / len(v):,.0f}  "
              f"p10 {v[len(v) // 10]:,}  p90 {v[-max(len(v) // 10, 1)]:,}")
        if subs:
            print(f"ERR（中位阅读 / 订阅）= {median(v) / subs:.1%}")

    # 按月看趋势，比看单条有意义
    by_month: dict[str, list[int]] = {}
    for r in mature:
        by_month.setdefault(f"{r['dt'].astimezone(tz):%Y-%m}", []).append(r["views"])
    if len(by_month) > 1:
        print("\n月度中位阅读：")
        for m in sorted(by_month):
            vs = by_month[m]
            bar = "█" * max(int(median(vs) / max(median(v) for v in by_month.values()) * 30), 1)
            print(f"  {m}  {median(vs):>7,.0f}  {bar}  (n={len(vs)})")

    hours = Counter(r["dt"].astimezone(tz).hour for r in rows)
    peak = max(hours.values())
    print(f"\n发布时刻（{settings.timezone}）：")
    for h in sorted(hours):
        print(f"  {h:02d}:00  {'▇' * max(round(hours[h] / peak * 30), 1)} {hours[h]}")

    reacts = sum(sum(r["reactions"].values()) for r in rows)
    fwds = sum(r["forwards"] or 0 for r in rows)
    views = sum(r["views"] or 0 for r in rows)
    er = f"  ER {reacts / views:.2%}" if views else ""
    print(f"\n互动：反应 {reacts:,}  转发 {fwds:,}{er}")

    fwd = Counter(r["fwd_from"] for r in rows if r["fwd_from"])
    if fwd:
        print(f"\n转发来源 top10（搬运比例 {sum(fwd.values()) / len(rows):.0%}）：")
        for name, n in fwd.most_common(10):
            print(f"  {n:>4}  {name}")

    hosts = Counter()
    for r in rows:
        for u in r["urls"]:
            try:
                h = urlparse(u if "://" in u else "https://" + u).hostname
                if h:
                    hosts[h.lower().removeprefix("www.")] += 1
            except ValueError:
                pass
    print("\n外链域名 top20：")
    for h, n in hosts.most_common(20):
        print(f"  {n:>4}  {h}")

    ads = [r for r in rows if any(k in r["text"] for k in AD_HINTS)]
    print(f"\n疑似广告/招商 {len(ads)} 条（{len(ads) / len(rows):.0%}），最近 5 条：")
    for r in ads[-5:]:
        flat = re.sub(r"\s+", " ", r["text"])[:70]
        print(f"  {r['dt'].astimezone(tz):%m-%d} {flat}")


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    lg = sub.add_parser("login", help="交互式登录，生成 data/recon-<账号名>.session")
    lg.add_argument("-a", "--account", default="default",
                    help="给这个账号起的标签，如 tony / main / alt")

    sub.add_parser("accounts", help="列出已有 session 分别是哪个账号")

    d = sub.add_parser("dump", help="拉历史消息到 jsonl")
    d.add_argument("channel", help="频道用户名，如 xiaoshuwu 或 @xiaoshuwu")
    d.add_argument("-a", "--account", help="用哪个账号抓，只有一个时可省略")
    d.add_argument("--limit", type=int, default=300)
    d.add_argument("--pause", type=float, default=1.5, help="每 100 条之间歇几秒")
    d.add_argument("--out", type=Path)

    s = sub.add_parser("stats", help="汇总已 dump 的数据")
    s.add_argument("channel")
    s.add_argument("--mature-days", type=int, default=7,
                   help="阅读数收敛所需天数，低于此的帖子不计入均值")
    s.add_argument("--out", type=Path)

    args = ap.parse_args()
    asyncio.run({"login": cmd_login, "accounts": cmd_accounts,
                 "dump": cmd_dump, "stats": cmd_stats}[args.cmd](args))


if __name__ == "__main__":
    main()
