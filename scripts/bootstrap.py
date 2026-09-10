"""一次性引导：把 .env 里的单频道配置变成库里的第一套 bot / 方向 / 频道记录。

    conda run -n tg-course-worker python scripts/bootstrap.py

重复跑是安全的——已存在的记录会跳过，不会重复创建。
之后所有配置都在管理后台改，这个脚本就不用再碰了。
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import botpool, db  # noqa: E402
from config.settings import settings  # noqa: E402

# .env.example 里的示例值，别把它当成真频道建进库
PLACEHOLDER_CHANNEL = -1001234567890

DEFAULT_VERTICAL = {
    "name": "AI 自动化 / 工作流",
    "slug": "ai-automation",
    "description": (
        "n8n / Dify / Coze / Make 等工作流与自动化工具、Agent 搭建、"
        "API 编排、爬虫与脚本自动化、LLM 应用落地方向的教程和学习资料"
    ),
}


async def _ensure_bot(name: str, role: str, env_key: str) -> int | None:
    existing = await db.get_bot_by_name(name)
    if existing:
        print(f"  = bot「{name}」已存在，跳过")
        return int(existing["id"])
    if not botpool.has_token(env_key):
        print(f"  ! 环境变量 {env_key} 未设置，跳过 bot「{name}」")
        return None

    bot_id = await db.create_bot(name=name, role=role, token_env_key=env_key)
    try:
        bot = await botpool.get(bot_id)
        me = await bot.get_me()
        await db.update_bot(bot_id, username=me.username or "")
        print(f"  + bot「{name}」→ @{me.username}")
    except Exception as e:
        print(f"  ! bot「{name}」记录已建，但 token 校验失败：{e}")
    return bot_id


async def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    await db.connect()
    print(f"数据库：{settings.db_path}\n")

    print("Bot：")
    producer_id = await _ensure_bot("生产机", "producer", "PRODUCER_BOT_TOKEN")
    sale_id = await _ensure_bot("资料机", "sale", "SALE_BOT_TOKEN")
    # 发布身份单独一个更稳：售卖 bot 面向陌生读者，万一被限制，
    # 频道发布不该跟着一起哑火。没配就回落到售卖 bot 兼任。
    post_id = await _ensure_bot("发布机", "publisher", "POST_BOT_TOKEN")

    print("\n内容方向：")
    vertical = await db.get_vertical_by_slug(DEFAULT_VERTICAL["slug"])
    if vertical:
        vertical_id = int(vertical["id"])
        print(f"  = 方向「{vertical['name']}」已存在，跳过")
    else:
        vertical_id = await db.create_vertical(
            **DEFAULT_VERTICAL, relevance_threshold=settings.relevance_threshold
        )
        print(f"  + 方向「{DEFAULT_VERTICAL['name']}」")

    print("\n频道：")
    publisher_id = post_id or sale_id
    if not settings.channel_id or settings.channel_id == PLACEHOLDER_CHANNEL:
        print(
            "  ! CHANNEL_ID 还是占位值，跳过。\n"
            "    建好频道 → 把发布 bot 设为管理员并勾「发布消息」→\n"
            "    在频道发条消息转发给 @userinfobot 拿 -100 开头的 id →\n"
            "    填进 .env 重跑本脚本，或直接在后台「频道」页添加。"
        )
    elif await db.get_channel_by_chat_id(settings.channel_id):
        print(f"  = 频道 {settings.channel_id} 已存在，跳过")
    elif not publisher_id:
        print("  ! 没有可用的发布 bot，跳过频道创建")
    else:
        await db.create_channel(
            name=settings.channel_name,
            chat_id=settings.channel_id,
            vertical_id=vertical_id,
            publisher_bot_id=publisher_id,
            sale_bot_id=sale_id,
            publish_cron=settings.default_publish_cron,
            timezone_name=settings.timezone,
        )
        print(f"  + 频道「{settings.channel_name}」({settings.channel_id})")

    await botpool.close_all()
    await db.close()

    print(
        "\n完成。下一步：\n"
        f"  1. 确认 .env 里 WEB_PASSWORD / WEB_SECRET 已填\n"
        f"  2. python -m app.main\n"
        f"  3. 打开 http://127.0.0.1:{settings.web_port}"
    )
    if producer_id is None:
        print("\n⚠️ 没有生产 bot，主程序会拒绝启动。先把 PRODUCER_BOT_TOKEN 填上。")


if __name__ == "__main__":
    asyncio.run(main())
