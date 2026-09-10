"""相册聚合。

转发相册/多文件时，Telegram 发过来的是**多条独立消息共享一个 media_group_id**，
不是一条。不聚合的话你转一组 5 张图会收到 5 张审核卡片。

做法：收到第一条时开一个定时窗口，窗口内到达的同组消息累积，
窗口到期一次性交给回调。
"""
from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from typing import Any

log = logging.getLogger(__name__)

Handler = Callable[[list[Any]], Awaitable[None]]


class MediaGroupCollector:
    def __init__(self, on_ready: Handler, delay: float = 1.5) -> None:
        self._on_ready = on_ready
        self._delay = delay
        self._buckets: dict[str, list[Any]] = {}
        self._timers: dict[str, asyncio.Task] = {}
        self._lock = asyncio.Lock()

    async def add(self, group_id: str, message: Any) -> None:
        async with self._lock:
            self._buckets.setdefault(group_id, []).append(message)
            timer = self._timers.get(group_id)
            if timer:
                timer.cancel()
            self._timers[group_id] = asyncio.create_task(self._flush_later(group_id))

    async def _flush_later(self, group_id: str) -> None:
        try:
            await asyncio.sleep(self._delay)
        except asyncio.CancelledError:
            return  # 又来了新消息，窗口顺延

        async with self._lock:
            messages = self._buckets.pop(group_id, [])
            self._timers.pop(group_id, None)

        if not messages:
            return
        # 保持用户转发时的原始顺序
        messages.sort(key=lambda m: m.message_id)
        try:
            await self._on_ready(messages)
        except Exception:
            log.exception("相册聚合回调失败 group_id=%s", group_id)
