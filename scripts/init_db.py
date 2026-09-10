"""初始化 / 迁移数据库。表结构用 CREATE TABLE IF NOT EXISTS，重复跑安全。

    conda run -n tg-course-worker python scripts/init_db.py
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import db  # noqa: E402
from config.settings import settings  # noqa: E402


async def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    await db.connect()
    conn = await db.connect()
    async with conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
    ) as cur:
        tables = [r["name"] for r in await cur.fetchall()]
    await db.close()
    print(f"数据库: {settings.db_path}")
    print("表: " + ", ".join(t for t in tables if not t.startswith("sqlite_")))


if __name__ == "__main__":
    asyncio.run(main())
