"""频道健康检查。

多频道之后最常出事的是 bot 被踢出频道或被降权——而你要到第二天九点
发不出去才发现。所以每天主动验一遍：bot 还在不在、有没有发布权限、
token 有没有失效。结果写回 channels.health_*，后台卡片上那个圆点就是它。
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from app import botpool, db, vault
from app.models import BotRole
from app.utils import alerts

log = logging.getLogger(__name__)

OK = "ok"
ERROR = "error"
UNKNOWN = "unknown"


async def check_channel(channel_row) -> tuple[str, str]:
    """返回 (状态, 说明)。不抛异常，任何失败都转成 error 状态。"""
    name = channel_row["name"]
    if not channel_row["is_active"]:
        return UNKNOWN, "频道已停用"
    if not channel_row["publisher_bot_id"]:
        return ERROR, "没有绑定发布 bot"

    try:
        bot = await botpool.get_for_channel(channel_row)
    except botpool.BotUnavailable as e:
        return ERROR, str(e)

    chat_id = int(channel_row["chat_id"])
    try:
        me = await bot.get_me()
        member = await bot.get_chat_member(chat_id, me.id)
    except Exception as e:
        return ERROR, f"读取频道成员失败：{type(e).__name__}: {str(e)[:120]}"

    if member.status not in {"administrator", "creator"}:
        return ERROR, f"bot 在频道里的身份是 {member.status}，不是管理员"

    # creator 天然有全部权限，administrator 才需要看具体开关
    if member.status == "administrator" and not getattr(
        member, "can_post_messages", False
    ):
        return ERROR, "bot 是管理员但没有「发布消息」权限"

    log.debug("频道「%s」健康", name)
    return OK, f"@{me.username} 管理员，发布权限正常"


async def check_vault() -> list[tuple[str, str, str]]:
    """仓库频道要求生产 bot 和每个售卖 bot 都在里面且是管理员。
    少一个，对应方向的资料就发不出去，而且只有读者点了按钮才会暴露。
    """
    if not vault.configured():
        return [("资料仓库", UNKNOWN, "未配置 VAULT_CHANNEL_ID，文件类资料不可用")]

    out: list[tuple[str, str, str]] = []
    for row in await db.list_bots(active_only=True):
        if row["role"] not in (BotRole.PRODUCER, BotRole.SALE):
            continue
        label = f"{BotRole(row['role']).label} bot「{row['name']}」"
        try:
            bot = await botpool.get(int(row["id"]))
        except botpool.BotUnavailable as e:
            out.append(("资料仓库", ERROR, f"{label}：{e}"))
            continue
        ok, detail = await vault.check_access(bot, label)
        out.append(("资料仓库", OK if ok else ERROR, detail))
    return out


async def check_all(notify_on_error: bool = True) -> list[tuple[str, str, str]]:
    """检查全部频道，写回状态。返回 [(频道名, 状态, 说明)]。"""
    results: list[tuple[str, str, str]] = []
    broken: list[str] = []

    for ch in await db.list_channels():
        status, detail = await check_channel(ch)
        await db.update_channel(
            int(ch["id"]),
            health_status=status,
            health_detail=detail,
            health_checked_at=datetime.now(timezone.utc).isoformat(),
        )
        results.append((ch["name"], status, detail))
        if status == ERROR:
            broken.append(f"• 「{ch['name']}」{detail}")

    for name, status, detail in await check_vault():
        results.append((name, status, detail))
        if status == ERROR:
            broken.append(f"• {detail}")

    if broken and notify_on_error:
        await alerts.notify(
            "🔴 <b>频道健康检查发现问题</b>\n" + "\n".join(broken)
        )
    return results
