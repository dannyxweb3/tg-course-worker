"""日志：控制台 + 按天轮转文件。"""
from __future__ import annotations

import logging
from logging.handlers import TimedRotatingFileHandler

from config.settings import LOG_DIR

_FMT = "%(asctime)s %(levelname)-7s %(name)s | %(message)s"


def setup(level: int = logging.INFO) -> None:
    root = logging.getLogger()
    if root.handlers:
        return
    root.setLevel(level)

    console = logging.StreamHandler()
    console.setFormatter(logging.Formatter(_FMT))
    root.addHandler(console)

    fileh = TimedRotatingFileHandler(
        LOG_DIR / "worker.log", when="midnight", backupCount=14, encoding="utf-8"
    )
    fileh.setFormatter(logging.Formatter(_FMT))
    root.addHandler(fileh)

    # 这些库的 INFO 太吵
    for noisy in ("aiogram.event", "httpx", "apscheduler.executors"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
