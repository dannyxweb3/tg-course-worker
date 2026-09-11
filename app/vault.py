"""资料仓库频道。

为什么要这么绕：**Telegram 的 file_id 是绑定 bot 的**。生产 bot 收到文件拿到的
file_id，售卖 bot 用不了，直接报错。两个 bot 之间没有任何共享文件的办法。

解法是拿一个私有频道当中转站，两个 bot 都是它的管理员：

    你发文件给生产 bot
      → 生产 bot copyMessage 到仓库频道，记下 message_id
      → 存成 kind=vault 的资料
      → 售卖 bot copyMessage(from_chat_id=仓库频道, message_id=N) 发给读者

用 copyMessage 而不是 forwardMessage，读者那边不会显示"转发自 XX"。
副作用是仓库频道同时成了你的资料备份。
"""
from __future__ import annotations

import logging

from aiogram import Bot
from aiogram.types import Message

from config.settings import settings

log = logging.getLogger(__name__)


class VaultError(RuntimeError):
    pass


def configured() -> bool:
    return bool(settings.vault_channel_id)


def _require() -> int:
    if not settings.vault_channel_id:
        raise VaultError(
            "资料仓库频道没配置。建一个私有频道，把生产 bot 和售卖 bot 都设为管理员，"
            "然后把频道 id 填进 .env 的 VAULT_CHANNEL_ID 并重启。"
        )
    return settings.vault_channel_id


def describe(message: Message) -> tuple[str, str]:
    """从消息里认出这是个什么文件，返回 (标题, 类型说明)。"""
    if message.document:
        return (message.document.file_name or "文件"), "文件"
    if message.video:
        return (message.video.file_name or "视频"), "视频"
    if message.audio:
        return (message.audio.file_name or message.audio.title or "音频"), "音频"
    if message.photo:
        return "图片", "图片"
    if message.animation:
        return (message.animation.file_name or "动图"), "动图"
    if message.voice:
        return "语音", "语音"
    if message.video_note:
        return "视频消息", "视频消息"
    if message.sticker:
        return "贴纸", "贴纸"
    if message.text:
        return (message.text.strip().splitlines() or ["文本"])[0][:60], "文本"
    return "未知内容", "其他"


async def store(bot: Bot, message: Message) -> int:
    """把一条消息存进仓库频道，返回仓库里的 message_id。"""
    vault = _require()
    try:
        copied = await bot.copy_message(
            chat_id=vault,
            from_chat_id=message.chat.id,
            message_id=message.message_id,
        )
    except Exception as e:
        raise VaultError(
            f"存进仓库频道失败：{type(e).__name__}: {str(e)[:150]}　"
            f"（检查生产 bot 是不是该频道的管理员）"
        ) from e
    return int(copied.message_id)


async def deliver(bot: Bot, user_id: int, vault_msg_id: int) -> bool:
    """从仓库频道把一份资料发给读者。失败只记日志，不打断其他资料的投递。"""
    if not configured():
        log.warning("仓库频道未配置，跳过 vault 资料 %s", vault_msg_id)
        return False
    try:
        await bot.copy_message(
            chat_id=user_id,
            from_chat_id=settings.vault_channel_id,
            message_id=vault_msg_id,
        )
        return True
    except Exception:
        log.exception(
            "发送 vault 资料失败 msg=%s → user=%s（售卖 bot 可能不在仓库频道里）",
            vault_msg_id, user_id,
        )
        return False


async def check_access(bot: Bot, label: str) -> tuple[bool, str]:
    """健康检查：这个 bot 在仓库频道里有没有该有的权限。"""
    if not configured():
        return False, "未配置 VAULT_CHANNEL_ID"
    try:
        me = await bot.get_me()
        member = await bot.get_chat_member(settings.vault_channel_id, me.id)
    except Exception as e:
        return False, f"{label} 读不到仓库频道：{type(e).__name__}: {str(e)[:100]}"
    if member.status not in {"administrator", "creator"}:
        return False, f"{label} 在仓库频道里是 {member.status}，不是管理员"
    return True, f"{label} @{me.username} 正常"
