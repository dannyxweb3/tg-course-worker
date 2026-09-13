"""分批只读抓取 data/analyze_targets.tsv 里的频道/群历史消息。
FloodWait 感知 + 限速(每 3 个成功后歇 120s)+ 断点续跑。
复用 tg_recon 的行解析。只读,不发送/不加群。

    python scripts/tg_batch_dump.py data/analyze_targets.tsv -a tony
"""
from __future__ import annotations
import argparse, asyncio, json, sys, time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from config.settings import DATA_DIR, settings
import tg_recon as R
from telethon import TelegramClient
from telethon.tl.functions.channels import GetFullChannelRequest
from telethon.errors import FloodWaitError

OUT_DIR = DATA_DIR / "recon"
REST_EVERY = 3
REST_SECS = 120
PAGE_PAUSE = 1.0


async def dump_one(client, user, limit):
    entity = await client.get_entity(user)
    full = await client(GetFullChannelRequest(entity))
    fc = full.full_chat
    subs = getattr(fc, "participants_count", None)
    online = getattr(fc, "online_count", None)
    title = getattr(entity, "title", user)
    kind = ("group" if getattr(entity, "megagroup", False)
            else ("channel" if getattr(entity, "broadcast", False) else "?"))
    rows = []
    async for msg in client.iter_messages(entity, limit=limit):
        rows.append(R._row(msg))
        if len(rows) % 100 == 0:
            await asyncio.sleep(PAGE_PAUSE)
    rows.reverse()
    out = OUT_DIR / f"{user}.jsonl"
    meta = {"_meta": True, "channel": user, "title": title, "kind": kind,
            "subscribers": subs, "online": online,
            "fetched_at": datetime.now(timezone.utc).isoformat()}
    with open(out, "w", encoding="utf-8", newline="\n") as f:
        f.write(json.dumps(meta, ensure_ascii=False) + "\n")
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    return kind, subs, online, len(rows)


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("targets")
    ap.add_argument("-a", "--account", default="tony")
    ap.add_argument("--limit", type=int, default=300)
    args = ap.parse_args()
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    targets = []
    for i, line in enumerate(Path(args.targets).read_text(encoding="utf-8").splitlines()):
        if i == 0 or not line.strip():
            continue
        targets.append(line.split("\t")[0])
    todo = [u for u in targets if not (OUT_DIR / f"{u}.jsonl").exists()]
    print(f"targets={len(targets)} 已存在={len(targets)-len(todo)} 本次={len(todo)}", flush=True)

    client = TelegramClient(str(DATA_DIR / f"recon-{args.account}.session"),
                            settings.tg_api_id, settings.tg_api_hash)
    await client.connect()
    if not await client.is_user_authorized():
        sys.exit("session 未授权")

    ok = 0
    for i, user in enumerate(todo, 1):
        for attempt in (1, 2):
            try:
                kind, subs, online, n = await dump_one(client, user, args.limit)
                ok += 1
                print(f"[{i}/{len(todo)}] OK {user} {kind} subs={subs} online={online} n={n}", flush=True)
                break
            except FloodWaitError as e:
                w = e.seconds + 10
                print(f"[{i}/{len(todo)}] FLOODWAIT {e.seconds}s @ {user} (attempt {attempt}) sleeping…", flush=True)
                await asyncio.sleep(w)
            except Exception as e:
                print(f"[{i}/{len(todo)}] ERR {user} {type(e).__name__}: {e}", flush=True)
                break
        if ok and ok % REST_EVERY == 0 and i < len(todo):
            print(f"  rest {REST_SECS}s (完成 {ok})", flush=True)
            await asyncio.sleep(REST_SECS)
    await client.disconnect()
    print(f"ALLDONE ok={ok}/{len(todo)}", flush=True)


asyncio.run(main())
