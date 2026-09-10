"""Bot 实例池。

库里只存 `token_env_key`，真实 token 从环境变量取——数据库要备份、要挂卷、
后台页面可能误显示，明文 token 泄露等于 bot 被接管。

同一个 bot 可能被多个频道共用，所以按 bot_id 缓存实例，不要每次发布都新建
（每个 Bot 都带一个 aiohttp session，重复创建会漏连接）。
"""
from __future__ import annotations

import logging
import os

from aiogram import Bot
from aiogram.client.default import DefaultBotProperties

from app import db

log = logging.getLogger(__name__)


class BotUnavailable(RuntimeError):
    """token 没配、bot 被停用、或记录不存在。"""


_cache: dict[int, Bot] = {}


def token_for(env_key: str) -> str:
    token = os.environ.get(env_key, "").strip()
    if not token:
        raise BotUnavailable(f"环境变量 {env_key} 没有配置")
    return token


def has_token(env_key: str) -> bool:
    return bool(os.environ.get(env_key, "").strip())


async def get(bot_id: int) -> Bot:
    if bot_id in _cache:
        return _cache[bot_id]

    row = await db.get_bot(bot_id)
    if row is None:
        raise BotUnavailable(f"bot#{bot_id} 不存在")
    if not row["is_active"]:
        raise BotUnavailable(f"bot「{row['name']}」已停用")

    bot = Bot(
        token=token_for(row["token_env_key"]),
        default=DefaultBotProperties(parse_mode=None),
    )
    _cache[bot_id] = bot
    return bot


async def get_for_channel(channel_row) -> Bot:
    """取频道的发布身份。

    发布必须用 bot：userbot 发的消息带不了 inline 按钮，
    而"底部挂购买 bot"这个需求就是 inline 按钮。
    """
    bot_id = channel_row["publisher_bot_id"]
    if not bot_id:
        raise BotUnavailable(f"频道「{channel_row['name']}」没有绑定发布 bot")
    return await get(int(bot_id))


def drop(bot_id: int) -> None:
    """配置改了（换 token / 停用）之后让缓存失效。"""
    _cache.pop(bot_id, None)


async def close_all() -> None:
    for bot_id, bot in list(_cache.items()):
        try:
            await bot.session.close()
        except Exception:
            log.warning("关闭 bot#%s 的 session 失败", bot_id, exc_info=True)
    _cache.clear()


async def refresh_usernames() -> None:
    """启动时把每个 bot 的真实 username 回填进库，后台展示和深链都要用。"""
    for row in await db.list_bots(active_only=True):
        if not has_token(row["token_env_key"]):
            log.warning("bot「%s」缺 token（%s）", row["name"], row["token_env_key"])
            continue
        try:
            bot = await get(int(row["id"]))
            me = await bot.get_me()
            if me.username != row["username"]:
                await db.update_bot(int(row["id"]), username=me.username or "")
                log.info("bot「%s」username → @%s", row["name"], me.username)
        except Exception as e:
            log.warning("bot「%s」校验失败：%s", row["name"], e)
