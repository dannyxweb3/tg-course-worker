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

from app import db, vault
from app.models import AssetKind
from app.render import split_html

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


def _asset_line(row) -> str:
    kind = AssetKind(row["kind"])
    title = html.escape(row["title"])
    bits = [f"{kind.icon} "]
    bits.append(
        f'<a href="{html.escape(row["url"], quote=True)}">{title}</a>'
        if row["url"] else f"<b>{title}</b>"
    )
    if row["passcode"]:
        # 提取码必须跟链接贴在一起，分两条发用户会漏
        bits.append(f'　提取码 <code>{html.escape(row["passcode"])}</code>')
    if row["note"]:
        bits.append(f'\n　<i>{html.escape(row["note"])}</i>')
    return "".join(bits)


async def _deliver(message: Message, item_id: int) -> None:
    """发货：把这条素材挂着的配套资料发给用户。"""
    draft = await db.latest_draft(item_id)
    if draft is None:
        await message.answer("这份资料暂时找不到，稍后再试。")
        return

    assets = await db.list_assets(item_id)
    head = f"📚 <b>{html.escape(draft.title)}</b>"
    if draft.tldr:
        head += f"\n{html.escape(draft.tldr)}"

    if not assets:
        # 理论上不该走到这——没资料的帖子根本不会挂按钮。
        # 但用户可能存了旧链接，或者资料被删了。
        await message.answer(
            f"{head}\n\n这一篇暂时没有配套资料，教程正文里已经写全了。",
            parse_mode="HTML",
        )
        return

    lines = [head, ""]
    lines += [_asset_line(a) for a in assets if a["kind"] != AssetKind.VAULT]
    for chunk in split_html("\n".join(lines)):
        await message.answer(
            chunk, parse_mode="HTML", disable_web_page_preview=True
        )

    # 仓库文件走 copyMessage 转发，不能给链接：t.me/c/... 只有频道成员打得开
    failed = 0
    for a in assets:
        if a["kind"] == AssetKind.VAULT and a["vault_msg_id"]:
            ok = await vault.deliver(
                message.bot, message.chat.id, int(a["vault_msg_id"])
            )
            failed += 0 if ok else 1
    if failed:
        await message.answer(
            f"有 {failed} 份文件暂时发不出来，我已经记录，稍后补给你。"
        )


@router.message(F.text)
async def fallback(message: Message) -> None:
    await message.answer("直接从频道教程底部的按钮进来，我就知道你要哪份资料。")
