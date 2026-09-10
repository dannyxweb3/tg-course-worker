"""素材摄入分发：把一条（或一组）Telegram 消息归一成一条待入库记录。"""
from __future__ import annotations

import io
import logging
from typing import Any

from aiogram import Bot
from aiogram.types import Message

from app.ingest import document, url as url_mod
from app.models import SourceType

log = logging.getLogger(__name__)


class IngestError(Exception):
    """摄入阶段的可预期失败，消息文案直接给用户看。"""


def _origin(message: Message) -> tuple[str, str]:
    """从转发来源提取 (来源名, 可回溯链接)。"""
    origin = getattr(message, "forward_origin", None)
    if origin is None:
        return "", ""

    kind = getattr(origin, "type", "")
    if kind == "channel":
        chat = origin.chat
        name = chat.title or ""
        msg_id = getattr(origin, "message_id", None)
        if chat.username and msg_id:
            return name, f"https://t.me/{chat.username}/{msg_id}"
        if msg_id:
            internal = str(chat.id).removeprefix("-100")
            return name, f"https://t.me/c/{internal}/{msg_id}"
        return name, ""
    if kind == "chat":
        return getattr(origin.sender_chat, "title", "") or "", ""
    if kind == "user":
        u = origin.sender_user
        return (u.full_name or u.username or ""), ""
    if kind == "hidden_user":
        return getattr(origin, "sender_user_name", "") or "", ""
    return "", ""


def _collect_text(messages: list[Message]) -> str:
    parts = [(m.text or m.caption or "").strip() for m in messages]
    return "\n\n".join(p for p in parts if p)


def _collect_media(messages: list[Message]) -> list[dict[str, str]]:
    """只存 file_id，不下载。同一个 bot 拿到的 file_id 可无限复用，零存储成本。"""
    media: list[dict[str, str]] = []
    for m in messages:
        if m.photo:
            media.append({"type": "photo", "file_id": m.photo[-1].file_id})
        elif m.video:
            media.append({"type": "video", "file_id": m.video.file_id})
        elif m.document and not document.is_supported(m.document.file_name or ""):
            media.append({"type": "document", "file_id": m.document.file_id})
    return media


async def _read_documents(bot: Bot, messages: list[Message]) -> tuple[str, str]:
    """下载并解析可读文档，返回 (文件名, 合并文本)。"""
    chunks: list[str] = []
    first_name = ""
    for m in messages:
        doc = m.document
        if not doc or not document.is_supported(doc.file_name or ""):
            continue
        name = doc.file_name or "untitled"
        first_name = first_name or name
        buf = io.BytesIO()
        await bot.download(doc.file_id, destination=buf)
        try:
            chunks.append(await document.parse(name, buf))
        except ValueError as e:
            raise IngestError(f"「{name}」解析失败：{e}") from e
    return first_name, "\n\n".join(chunks)


async def build_item(bot: Bot, messages: list[Message]) -> dict[str, Any]:
    """归一成 db.create_item() 的入参。

    判定优先级：可读文档 > 转发消息 > 纯链接 > 纯文本。
    """
    text = _collect_text(messages)
    media = _collect_media(messages)
    src_title, src_link = _origin(messages[0])

    # 1) 可读文档
    has_doc = any(
        m.document and document.is_supported(m.document.file_name or "")
        for m in messages
    )
    if has_doc:
        filename, body = await _read_documents(bot, messages)
        return {
            "source_type": str(SourceType.DOCUMENT),
            "raw_text": f"{text}\n\n{body}".strip() if text else body,
            "source_title": src_title or filename,
            "source_link": src_link,
            "media": media,
        }

    urls = url_mod.find_urls(text)

    # 2) 转发消息：原文即素材，链接只作为附注
    if src_title or src_link:
        if not text.strip():
            raise IngestError("这条转发没有可提取的文字内容")
        return {
            "source_type": str(SourceType.FORWARD),
            "raw_text": text,
            "source_title": src_title,
            "source_link": src_link,
            "source_url": urls[0] if urls else "",
            "media": media,
        }

    # 3) 纯链接（或链接 + 一句话批注）：抓正文
    stripped = text
    for u in urls:
        stripped = stripped.replace(u, "")
    if urls and len(stripped.strip()) < 200:
        target = urls[0]
        try:
            title, body = await url_mod.fetch(target)
        except Exception as e:
            raise IngestError(f"抓取失败：{e}") from e
        note = stripped.strip()
        return {
            "source_type": str(SourceType.URL),
            "raw_text": f"[我的批注] {note}\n\n{body}" if note else body,
            "source_title": title,
            "source_url": target,
            "dedup_key": url_mod.normalize(target),
            "media": media,
        }

    # 4) 纯文本
    if not text.strip():
        raise IngestError("没收到可处理的内容。支持：文字、链接、.md/.txt/.pdf、转发消息")
    return {
        "source_type": str(SourceType.TEXT),
        "raw_text": text,
        "source_url": urls[0] if urls else "",
        "media": media,
    }
