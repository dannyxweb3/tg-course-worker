"""频道发布。

发布身份必须是 **bot**：userbot 发的消息带不了 inline 按钮，
而"底部挂购买 bot"这个需求就是 inline 按钮。
把频道绑定的 publisher bot 设为该频道管理员即可。
"""
from __future__ import annotations

import logging
from datetime import datetime
from zoneinfo import ZoneInfo

from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app import botpool, db
from app.render import compose_post, split_html
from app.utils import alerts
from config.settings import settings

log = logging.getLogger(__name__)


async def _cta(channel_row, item_id: int) -> InlineKeyboardMarkup | None:
    """深链带参数：用户点进来时售卖 bot 会收到 /start item_<id>_c<channel>，
    归因和内容定位都靠它。payload 上限 64 字符。
    """
    sale_id = channel_row["sale_bot_id"]
    if not sale_id:
        return None
    sale = await db.get_bot(int(sale_id))
    if sale is None or not sale["username"]:
        return None

    kb = InlineKeyboardBuilder()
    kb.button(
        text="📚 获取完整资料",
        url=(
            f"https://t.me/{sale['username']}"
            f"?start=item_{item_id}_c{channel_row['id']}"
        ),
    )
    return kb.as_markup()


async def publish_item(channel_row, item_id: int, draft_id: int) -> int:
    """发一条到指定频道，返回首条消息 id。超长自动拆条，按钮挂在最后一条。"""
    draft = await db.get_draft(draft_id)
    if draft is None:
        raise ValueError(f"draft#{draft_id} 不存在")

    bot = await botpool.get_for_channel(channel_row)
    post = compose_post(
        title=draft.title, tldr=draft.tldr, body_html=draft.body_html,
        tags=draft.tags, attribution=draft.attribution,
    )
    chunks = split_html(post)
    cta = await _cta(channel_row, item_id)

    first_id = 0
    for idx, chunk in enumerate(chunks):
        is_last = idx == len(chunks) - 1
        prefix = "" if len(chunks) == 1 else f"({idx + 1}/{len(chunks)})\n\n"
        msg = await bot.send_message(
            int(channel_row["chat_id"]),
            prefix + chunk,
            parse_mode="HTML",
            disable_web_page_preview=True,
            reply_markup=cta if is_last else None,
        )
        first_id = first_id or msg.message_id

    await db.mark_published(item_id, int(channel_row["id"]), draft_id, first_id)
    log.info(
        "已发布 item#%s → 频道「%s」msg %s", item_id, channel_row["name"], first_id
    )
    return first_id


async def publish_next(channel_id: int) -> bool:
    """定时任务入口。返回是否真的发出去了。"""
    channel = await db.get_channel(channel_id)
    if channel is None or not channel["is_active"]:
        return False

    tz = ZoneInfo(channel["timezone"] or settings.timezone)
    today = datetime.now(tz).date().isoformat()
    row = await db.pop_next(channel_id, today)
    if row is None:
        await alerts.notify(
            f"📭 频道「{channel['name']}」今天没内容可发——队列是空的。"
        )
        return False

    item_id, draft_id = int(row["item_id"]), int(row["draft_id"])
    try:
        msg_id = await publish_item(channel, item_id, draft_id)
    except Exception as e:
        await alerts.report(f"publish item#{item_id} → 频道「{channel['name']}」", e)
        return False

    remaining = await db.queue_size(channel_id)
    await alerts.notify(
        f"📣 「{channel['name']}」已发布 #{item_id}（消息 {msg_id}），"
        f"队列还剩 {remaining} 条。"
    )
    return True
