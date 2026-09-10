"""文件素材：.md / .txt / .pdf。"""
from __future__ import annotations

import asyncio
import io
import logging

log = logging.getLogger(__name__)

TEXT_EXT = {".md", ".markdown", ".txt", ".text", ".rst"}
PDF_EXT = {".pdf"}
SUPPORTED = TEXT_EXT | PDF_EXT

# 单文件上限；Bot API 下载本身也有 20MB 限制
MAX_BYTES = 10 * 1024 * 1024


def is_supported(filename: str) -> bool:
    return any(filename.lower().endswith(e) for e in SUPPORTED)


def _decode(data: bytes) -> str:
    for enc in ("utf-8", "utf-8-sig", "gb18030", "big5", "latin-1"):
        try:
            return data.decode(enc)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="replace")


def _pdf_sync(data: bytes) -> str:
    import fitz  # pymupdf

    with fitz.open(stream=data, filetype="pdf") as doc:
        return "\n\n".join(page.get_text() for page in doc)


async def parse(filename: str, buf: io.BytesIO) -> str:
    """把下载好的文件解析成纯文本。"""
    data = buf.getvalue()
    if len(data) > MAX_BYTES:
        raise ValueError(f"文件超过 {MAX_BYTES // 1024 // 1024}MB 上限")

    low = filename.lower()
    if any(low.endswith(e) for e in PDF_EXT):
        text = await asyncio.to_thread(_pdf_sync, data)
    else:
        text = _decode(data)

    if not text.strip():
        raise ValueError("文件内容为空或无法提取文字（扫描版 PDF 需要 OCR）")
    return text
