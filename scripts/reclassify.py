"""回补 / 重跑素材的路由分类，不动状态、不重新生成文案。

    python scripts/reclassify.py                 # 只补没有内容方向的
    python scripts/reclassify.py --all           # 全部重跑（prompt 调完之后用）
    python scripts/reclassify.py --ids 12,15,20
    python scripts/reclassify.py --dry-run       # 只看会改成什么，不写库

分类和生成是两件事：改了方向的描述、或者修了分类 prompt，只需要重跑分类，
已有的文案不用动（各方向没填 style_prompt 时，文案本来就和路由无关）。

状态一律保持原样——这些素材多半已经在待审核甚至队列里了，
把状态推回"已分类"等于把人工进度抹掉。
"""
from __future__ import annotations

import argparse
import asyncio
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import db  # noqa: E402
from app.llm import pipeline  # noqa: E402
from app.llm.deepseek import close_provider  # noqa: E402


async def handle(item_id: int, lock: asyncio.Lock, dry: bool,
                 stat: dict) -> None:
    item = await db.get_item(item_id)
    if item is None:
        return
    before = int(item["vertical_id"] or 0)
    try:
        routing = await pipeline.classify(item)
    except Exception as e:
        stat["fail"] += 1
        stat["errors"].append(f"#{item_id} {type(e).__name__}: {str(e)[:90]}")
        print(f"  ✗ #{item_id:<4} {str(e)[:70]}")
        return

    mark = "=" if before == routing.vertical_id else "→"
    print(f"  ✓ #{item_id:<4} {before} {mark} {routing.vertical_id}"
          f" 「{routing.vertical_name or '无匹配'}」"
          f" 相关性 {routing.relevance}　{routing.reason[:34]}")

    if not dry:
        async with lock:
            await db.set_classification(
                item_id, vertical_id=routing.vertical_id,
                relevance=routing.relevance, tags=routing.tags,
                level=str(routing.level), reason=routing.reason,
                scores=routing.scores,
                keep_status=True,
            )
    stat["ok"] += 1
    if routing.vertical_id:
        stat["routed"] += 1
    if before != routing.vertical_id:
        stat["changed"] += 1


async def pick_ids(args) -> list[int]:
    if args.ids:
        return [int(x) for x in args.ids.replace("，", ",").split(",") if x.strip()]
    # 已丢弃的不值得再花 token
    clause = "status <> 'discarded'"
    if not args.all:
        clause += " AND (vertical_id IS NULL OR vertical_id = 0)"
    rows = await db._fetchall(f"SELECT id FROM items WHERE {clause} ORDER BY id")
    return [int(r["id"]) for r in rows]


async def main() -> None:
    ap = argparse.ArgumentParser(description="回补素材的路由分类")
    ap.add_argument("--all", action="store_true", help="全部重跑，不只是没方向的")
    ap.add_argument("--ids", default="", help="只处理这些 id，逗号分隔")
    ap.add_argument("--concurrency", type=int, default=4)
    ap.add_argument("--dry-run", action="store_true", help="只打印，不写库")
    args = ap.parse_args()

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    await db.connect()
    ids = await pick_ids(args)
    if not ids:
        print("没有需要处理的素材。")
        await db.close()
        return

    print(f"共 {len(ids)} 条 · 并发 {args.concurrency}"
          f"{' · 空跑（不写库）' if args.dry_run else ''}\n")

    stat = {"ok": 0, "fail": 0, "routed": 0, "changed": 0, "errors": []}
    lock = asyncio.Lock()
    sem = asyncio.Semaphore(args.concurrency)
    t0 = time.time()

    async def worker(i: int) -> None:
        async with sem:
            await handle(i, lock, args.dry_run, stat)

    await asyncio.gather(*(worker(i) for i in ids))
    await close_provider()

    print(f"\n{'=' * 54}")
    print(f"用时 {(time.time() - t0) / 60:.1f} 分钟　共 {len(ids)} 条")
    print(f"  成功 {stat['ok']}（其中落到方向的 {stat['routed']}，"
          f"方向有变化的 {stat['changed']}）　失败 {stat['fail']}")
    for e in stat["errors"][:20]:
        print(f"  - {e}")
    await db.close()


if __name__ == "__main__":
    asyncio.run(main())
