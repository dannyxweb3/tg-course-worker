"""告警：任何未捕获异常都私聊推给 OWNER。

这是"无人值守"的底线——服务器上出了事没人看日志，只能靠 bot 自己喊。
"""
from __future__ import annotations

import html
import logging
import traceback
from typing import Any

from config.settings import settings

log = logging.getLogger(__name__)

_bot: Any = None  # 由 main.py 注入生产 bot 实例，避免循环 import


def bind(bot: Any) -> None:
    global _bot
    _bot = bot


async def notify(text: str) -> None:
    """给 OWNER 发一条普通提醒。发送失败只记日志，绝不再抛。"""
    if _bot is None:
        log.warning("alert (bot 未就绪): %s", text)
        return
    try:
        await _bot.send_message(settings.owner_id, text, parse_mode="HTML")
    except Exception:
        log.exception("告警发送失败")


async def report(where: str, exc: BaseException) -> None:
    """上报异常。堆栈截断到 1500 字符，避免超 Telegram 长度限制。"""
    tb = "".join(traceback.format_exception(exc))[-1500:]
    log.exception("[%s] 异常", where, exc_info=exc)
    await notify(
        f"⚠️ <b>{html.escape(where)}</b> 出错\n"
        f"<code>{html.escape(type(exc).__name__)}: {html.escape(str(exc)[:200])}</code>\n"
        f"<pre>{html.escape(tb)}</pre>"
    )
