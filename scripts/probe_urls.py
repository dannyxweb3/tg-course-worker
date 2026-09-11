"""批量探测 URL 能不能抽出正文。只做只读探测，不写库。

    python scripts/probe_urls.py cand.txt --out good.txt --min-chars 1200

抓不到正文的（纯 JS 渲染、付费墙、反爬）在这一步就筛掉，
免得灌进去一堆空壳，浪费 LLM 调用。
"""
from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.ingest import url as U  # noqa: E402


async def probe(u: str, sem: asyncio.Semaphore, min_chars: int) -> tuple[str, int, str]:
    async with sem:
        try:
            title, body = await U.fetch(u)
        except Exception as e:
            return u, 0, f"{type(e).__name__}: {str(e)[:60]}"
        n = len(body or "")
        return u, n, "" if n >= min_chars else "正文太短"


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("file", type=Path)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--min-chars", type=int, default=1200)
    ap.add_argument("--concurrency", type=int, default=8)
    args = ap.parse_args()

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    urls = [
        ln.strip() for ln in args.file.read_text(encoding="utf-8").splitlines()
        if ln.strip() and not ln.strip().startswith("#")
    ]
    sem = asyncio.Semaphore(args.concurrency)
    results = await asyncio.gather(*(probe(u, sem, args.min_chars) for u in urls))

    good = [(u, n) for u, n, err in results if not err]
    bad = [(u, n, err) for u, n, err in results if err]
    good.sort(key=lambda t: -t[1])

    args.out.write_text("\n".join(u for u, _ in good) + "\n", encoding="utf-8")
    print(f"可用 {len(good)} / {len(urls)}　→ {args.out}")
    for u, n, err in bad:
        print(f"  ✗ {n:>6}  {err[:40]:<42} {u[:70]}")


if __name__ == "__main__":
    asyncio.run(main())
