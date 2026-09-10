"""售卖 Bot：面向读者。

v1 只做两件事——接住频道按钮过来的深链、把用户落进自己的库（含来源频道）。
支付（建议起步用 Telegram Stars，纯 Bot API 闭环，不需要外部支付商）
放 v2，接口位置已经留好。

一个售卖 bot 可以被多个频道共用，靠深链 payload 里的 _c<channel_id> 区分来源。
"""
from __future__ import annotations

import html
import logging
import re

from aiogram import F, Router
from aiogram.filters import CommandObject, CommandStart
from aiogram.types import Message

from app import db

log = logging.getLogger(__name__)

router = Router(name="sale")

WELCOME = (
    "👋 这里是教程频道的资料机器人。\n\n"
    "频道里每条教程底部的按钮都会把你带到这里，对应的完整资料我会直接发给你。"
)

_PAYLOAD = re.compile(r"^item_(\d+)(?:_c(\d+))?$")


@router.message(CommandStart(deep_link=True))
async def on_deeplink(message: Message, command: CommandObject) -> None:
    payload = (command.args or "").strip()[:64]
    user = message.from_user

    m = _PAYLOAD.match(payload)
    item_id = int(m.group(1)) if m else 0
    channel_id = int(m.group(2)) if m and m.group(2) else 0

    await db.upsert_user(user.id, user.username or "", payload, channel_id)
    log.info("deeplink: user=%s item=%s channel=%s", user.id, item_id, channel_id)

    if item_id:
        await _deliver(message, item_id)
        return
    await message.answer(WELCOME, parse_mode="HTML")


@router.message(CommandStart(deep_link=False))
async def on_start(message: Message) -> None:
    user = message.from_user
    await db.upsert_user(user.id, user.username or "", "")
    await message.answer(WELCOME, parse_mode="HTML")


async def _deliver(message: Message, item_id: int) -> None:
    """发货。v1 只回标题和摘要；
    v2 在这里加付费判断和附件（用 file_id 复用，零存储成本）。
    """
    draft = await db.latest_draft(item_id)
    if draft is None:
        await message.answer("这份资料暂时找不到，稍后再试。")
        return
    await message.answer(
        f"📚 <b>{html.escape(draft.title)}</b>\n\n{html.escape(draft.tldr)}\n\n"
        f"完整内容整理中，稍后推送给你。",
        parse_mode="HTML",
    )


@router.message(F.text)
async def fallback(message: Message) -> None:
    await message.answer("直接从频道教程底部的按钮进来，我就知道你要哪份资料。")
