"""只读峰查：解析候选用户名，取订阅数 + 最后消息日期 + 类型，写 CSV。
用来在全量 dump 之前做门槛过滤（>8000 人、半年内有更新）。可断点续跑。"""
from __future__ import annotations
import asyncio, csv, sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from config.settings import DATA_DIR, settings
from telethon import TelegramClient
from telethon.tl.functions.channels import GetFullChannelRequest
from telethon.errors import FloodWaitError

ACCOUNT = "tony"
IN = Path(sys.argv[1])
OUT = Path(sys.argv[2])

def done_set() -> set[str]:
    if not OUT.exists():
        return set()
    s = set()
    for r in csv.reader(OUT.open(encoding="utf-8")):
        if r:
            s.add(r[0])
    return s

async def main() -> None:
    client = TelegramClient(str(DATA_DIR / f"recon-{ACCOUNT}.session"),
                            settings.tg_api_id, settings.tg_api_hash)
    await client.connect()
    if not await client.is_user_authorized():
        sys.exit("session 未授权")
    already = done_set()
    cands = [l.strip() for l in IN.read_text(encoding="utf-8").splitlines() if l.strip()]
    todo = [c for c in cands if c not in already]
    print(f"共 {len(cands)}，已完成 {len(already)}，本次 {len(todo)}", flush=True)
    write_header = not OUT.exists()
    f = OUT.open("a", encoding="utf-8", newline="")
    w = csv.writer(f)
    if write_header:
        w.writerow(["username","members","last_date","days_ago","kind","title","err"])
    now = datetime.now(timezone.utc)
    for i, u in enumerate(todo, 1):
        members=""; last=""; days=""; kind=""; title=""; err=""
        try:
            ent = await client.get_entity(u)
            kind = "group" if getattr(ent,"megagroup",False) else ("channel" if getattr(ent,"broadcast",False) else type(ent).__name__)
            title = (getattr(ent,"title","") or "").replace("\n"," ")
            try:
                full = await client(GetFullChannelRequest(ent))
                members = full.full_chat.participants_count or ""
            except Exception:
                members = ""
            msgs = await client.get_messages(ent, limit=1)
            if msgs:
                d = msgs[0].date.astimezone(timezone.utc)
                last = d.isoformat()
                days = (now - d).days
        except FloodWaitError as e:
            print(f"  FloodWait {e.seconds}s @ {u}", flush=True)
            await asyncio.sleep(e.seconds + 5)
            err = f"floodwait_retry"
            # retry once
            try:
                ent = await client.get_entity(u)
                kind = "group" if getattr(ent,"megagroup",False) else ("channel" if getattr(ent,"broadcast",False) else type(ent).__name__)
                title = (getattr(ent,"title","") or "").replace("\n"," ")
                full = await client(GetFullChannelRequest(ent))
                members = full.full_chat.participants_count or ""
                msgs = await client.get_messages(ent, limit=1)
                if msgs:
                    d = msgs[0].date.astimezone(timezone.utc)
                    last = d.isoformat(); days=(now-d).days
                err=""
            except Exception as e2:
                err = f"{type(e2).__name__}"
        except Exception as e:
            err = f"{type(e).__name__}"
        w.writerow([u,members,last,days,kind,title,err]); f.flush()
        print(f"[{i}/{len(todo)}] {u:<28} m={members} d={days} {kind} {err}", flush=True)
        await asyncio.sleep(2.0)
    await client.disconnect()
    f.close()
    print("done", flush=True)

asyncio.run(main())
