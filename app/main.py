"""入口：一个进程跑四件事——生产 bot、所有售卖 bot、定时调度、管理后台。

用 long polling 而不是 webhook：省掉域名、证书、公网入口和反向代理。
这个量级完全够，也是"少维护"这个目标里最值钱的一个取舍。
"""
from __future__ import annotations

import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage

from app import botpool, db, scheduler
from app.bots import producer, sale
from app.llm.deepseek import close_provider
from app.models import BotRole
from app.utils import alerts, logging as applog
from app.web import server as web_server

log = logging.getLogger(__name__)


async def _polling(bot: Bot, dp: Dispatcher, label: str) -> None:
    """单个 bot 的 polling。一个 bot 挂了不能带着整个进程一起死。"""
    try:
        await dp.start_polling(bot, handle_signals=False)
    except asyncio.CancelledError:
        raise
    except Exception as e:
        log.exception("%s 的 polling 异常退出", label)
        await alerts.report(f"polling {label}", e)


async def _run() -> None:
    applog.setup()
    await db.connect()

    bots = await db.list_bots(active_only=True)
    producers = [b for b in bots if b["role"] == BotRole.PRODUCER]
    sales = [b for b in bots if b["role"] == BotRole.SALE]

    if not producers:
        raise SystemExit(
            "还没有配置生产 bot。先跑一次：python scripts/bootstrap.py"
        )

    # 生产 bot 同时承担告警出口，必须最先就绪
    producer_bot = await botpool.get(int(producers[0]["id"]))
    alerts.bind(producer_bot)

    await botpool.refresh_usernames()

    tasks: list[asyncio.Task] = []

    producer_dp = Dispatcher(storage=MemoryStorage())
    producer_dp.include_router(producer.router)
    tasks.append(
        asyncio.create_task(
            _polling(producer_bot, producer_dp, f"生产 bot「{producers[0]['name']}」")
        )
    )

    # 每个售卖 bot 一个 Dispatcher；它们共用同一份 handler 逻辑
    for row in sales:
        try:
            bot = await botpool.get(int(row["id"]))
        except botpool.BotUnavailable as e:
            log.warning("售卖 bot「%s」跳过：%s", row["name"], e)
            continue
        dp = Dispatcher(storage=MemoryStorage())
        dp.include_router(sale.router)
        tasks.append(
            asyncio.create_task(_polling(bot, dp, f"售卖 bot「{row['name']}」"))
        )

    await scheduler.start()
    tasks.append(asyncio.create_task(web_server.serve()))

    channels = await db.list_channels(active_only=True)
    await alerts.notify(
        f"🟢 已启动\n"
        f"生产 @{(await producer_bot.get_me()).username} · "
        f"售卖 {len(sales)} 个 · 频道 {len(channels)} 个\n"
        f"待发总数 {await db.queue_size()}"
    )
    log.info("全部就绪：%s 个 polling 任务", len(tasks) - 1)

    try:
        await asyncio.gather(*tasks)
    finally:
        for t in tasks:
            t.cancel()
        scheduler.shutdown()
        await close_provider()
        await botpool.close_all()
        await db.close()


def main() -> None:
    try:
        asyncio.run(_run())
    except (KeyboardInterrupt, SystemExit) as e:
        if isinstance(e, SystemExit) and e.code:
            print(e.code)
        log.info("已停止")


if __name__ == "__main__":
    main()
