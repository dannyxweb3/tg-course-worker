"""批量灌素材：URL 列表 → 抓取 → 分类路由 → 生成文案 → PDF → 待审核队列。

    python scripts/batch_ingest.py urls.txt --level P2 --concurrency 3

刻意**不走生产 bot**：100 条素材会往私聊里灌 100 张审核卡片，没法用。
这里直接写库，status=review，你去后台列表里分批过。

可重复运行：URL 归一化后作为 dedup_key，已收过的直接跳过。
中途断了再跑一次即可，不会重复建。
"""
from __future__ import annotations

import argparse
import asyncio
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import db, pdfgen  # noqa: E402
from app.ingest import url as U  # noqa: E402
from app.llm import pipeline  # noqa: E402
from app.llm.deepseek import close_provider  # noqa: E402
from app.models import AssetKind, ItemStatus, Level, SourceType  # noqa: E402
from config.settings import DATA_DIR  # noqa: E402


@dataclass
class Stats:
    total: int = 0
    ok: int = 0
    dup: int = 0
    fetch_fail: int = 0
    llm_fail: int = 0
    off_topic: int = 0
    pdf_fail: int = 0
    failures: list[str] = field(default_factory=list)


async def handle(url: str, level: Level | None, st: Stats, lock: asyncio.Lock,
                 make_pdf: bool) -> None:
    short = url[:64]

    # 1) 抓正文
    try:
        title, body = await U.fetch(url)
    except Exception as e:
        st.fetch_fail += 1
        st.failures.append(f"抓取失败 {short} — {type(e).__name__}: {str(e)[:80]}")
        print(f"  ✗ 抓取  {short}")
        return

    # 2) 入库（dedup_key 冲突说明收过了）
    async with lock:
        item_id = await db.create_item(
            source_type=str(SourceType.URL), raw_text=body,
            source_title=title, source_url=url, dedup_key=U.normalize(url),
        )
    if item_id is None:
        st.dup += 1
        print(f"  ↩ 重复  {short}")
        return

    item = await db.get_item(item_id)

    # 3) 分类：主要为了路由到内容方向和拿标签
    try:
        routing = await pipeline.classify(item)
        async with lock:
            await db.set_classification(
                item_id, vertical_id=routing.vertical_id,
                relevance=routing.relevance, tags=routing.tags,
                level=str(routing.level), reason=routing.reason,
                scores=routing.scores,
            )
    except Exception as e:
        st.llm_fail += 1
        await db.update_item(item_id, status=str(ItemStatus.FAILED))
        st.failures.append(f"分类失败 #{item_id} {short} — {str(e)[:80]}")
        print(f"  ✗ 分类  #{item_id}")
        return

    if routing.level is Level.P3 and level is None:
        st.off_topic += 1
        await db.update_item(item_id, status=str(ItemStatus.DISCARDED))
        print(f"  ⊘ 无关  #{item_id} {routing.reason[:30]}")
        return

    # 4) 生成文案。批量默认强制 P2 重写：
    #    P0/P1 基本是原文照搬，做成可下载 PDF 分发等于再发布别人的内容。
    use_level = level or routing.level
    item = await db.get_item(item_id)
    try:
        draft = await pipeline.generate(item, use_level)
        async with lock:
            draft.id = await db.add_draft(item_id, draft)
            await db.update_item(item_id, status=str(ItemStatus.REVIEW))
    except Exception as e:
        st.llm_fail += 1
        await db.update_item(item_id, status=str(ItemStatus.FAILED))
        st.failures.append(f"生成失败 #{item_id} {short} — {str(e)[:80]}")
        print(f"  ✗ 生成  #{item_id}")
        return

    # 5) PDF。vault 频道没配时先落盘，url 里存相对路径，
    #    vault_msg_id=0 表示"待上传"，配好频道后由后台一次性传上去。
    if make_pdf:
        try:
            path = await asyncio.to_thread(pdfgen.render, draft, item)
            async with lock:
                await db.create_asset(
                    item_id, kind=str(AssetKind.VAULT),
                    title=f"{draft.title}.pdf",
                    # 用 posix 分隔符：Windows 上生成、Ubuntu 上读取
                    url=path.relative_to(DATA_DIR).as_posix(),
                    note="PDF", vault_msg_id=0, sort=-5,
                )
        except Exception as e:
            st.pdf_fail += 1
            st.failures.append(f"PDF 失败 #{item_id} — {str(e)[:80]}")
            print(f"  ⚠ PDF   #{item_id} {str(e)[:50]}")

    st.ok += 1
    print(f"  ✓ #{item_id:<4} [{use_level}] {routing.vertical_name or '未分类'}"
          f" · {draft.char_count} 字符 · {draft.title[:34]}")


async def main() -> None:
    ap = argparse.ArgumentParser(description="批量灌素材到待审核队列")
    ap.add_argument("file", type=Path, help="URL 列表，一行一个，# 开头为注释")
    ap.add_argument("--level", choices=["P0", "P1", "P2"], default="P2",
                    help="强制处理档位，默认 P2 重写（版权上更稳）")
    ap.add_argument("--concurrency", type=int, default=3,
                    help="并发数。DeepSeek 有限流，3-4 比较稳")
    ap.add_argument("--limit", type=int, default=0, help="只处理前 N 条")
    ap.add_argument("--no-pdf", action="store_true", help="跳过 PDF 生成")
    args = ap.parse_args()

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    urls = [
        ln.strip() for ln in args.file.read_text(encoding="utf-8").splitlines()
        if ln.strip() and not ln.strip().startswith("#")
    ]
    if args.limit:
        urls = urls[: args.limit]

    st = Stats(total=len(urls))
    level = Level(args.level)
    print(f"共 {len(urls)} 条 · 档位 {level.label} · 并发 {args.concurrency}"
          f" · PDF {'否' if args.no_pdf else '是'}\n")

    await db.connect()
    lock = asyncio.Lock()          # SQLite 写串行化，别让 N 个协程同时写
    sem = asyncio.Semaphore(args.concurrency)
    t0 = time.time()

    async def worker(u: str) -> None:
        async with sem:
            try:
                await handle(u, level, st, lock, not args.no_pdf)
            except Exception as e:      # 单条炸了不能拖垮整批
                st.failures.append(f"未捕获 {u[:60]} — {type(e).__name__}: {e}")
                print(f"  ✗ 异常  {u[:60]} {type(e).__name__}")

    await asyncio.gather(*(worker(u) for u in urls))
    await close_provider()

    dt = time.time() - t0
    print(f"\n{'=' * 54}")
    print(f"用时 {dt/60:.1f} 分钟　共 {st.total} 条")
    print(f"  成功入队 {st.ok}　重复跳过 {st.dup}　判定无关 {st.off_topic}")
    print(f"  抓取失败 {st.fetch_fail}　LLM 失败 {st.llm_fail}　PDF 失败 {st.pdf_fail}")
    print(f"  待审核总数 {len(await db.list_items(str(ItemStatus.REVIEW), limit=9999))}")
    if st.failures:
        print(f"\n失败明细（{len(st.failures)} 条）：")
        for f in st.failures[:40]:
            print(f"  - {f}")
    await db.close()


if __name__ == "__main__":
    asyncio.run(main())
