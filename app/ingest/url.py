"""URL 素材：抓正文。

trafilatura 是专做正文抽取的（比 readability 准），对静态页够用。
纯 JS 渲染的页面抓不到，v2 再挂 Playwright 兜底。
"""
from __future__ import annotations

import asyncio
import logging
import re
from urllib.parse import urlparse, urlunparse

import httpx

log = logging.getLogger(__name__)

URL_RE = re.compile(r"https?://[^\s<>()\[\]、，。；]+")

_UA = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)
# 归一化时要丢掉的跟踪参数
_TRACKING = re.compile(r"^(utm_|fbclid|gclid|spm|from|share_)", re.I)


def find_urls(text: str) -> list[str]:
    return URL_RE.findall(text or "")


def normalize(url: str) -> str:
    """归一化成 dedup_key：去掉 fragment 和跟踪参数，统一小写 host。"""
    try:
        p = urlparse(url)
    except ValueError:
        return url
    query = "&".join(
        kv for kv in p.query.split("&")
        if kv and not _TRACKING.match(kv.split("=", 1)[0])
    )
    return urlunparse(
        (p.scheme.lower(), p.netloc.lower(), p.path.rstrip("/"), "", query, "")
    )


def _extract_sync(html_text: str, url: str) -> tuple[str, str]:
    import trafilatura

    body = trafilatura.extract(
        html_text,
        url=url,
        include_comments=False,
        include_tables=True,
        include_links=True,
        favor_precision=True,
    ) or ""
    title = ""
    meta = trafilatura.extract_metadata(html_text)
    if meta and meta.title:
        title = meta.title
    return title, body


# README 的常见文件名。仓库不一定用 .md：torvalds/linux 就是无扩展名的 README
_README_NAMES = ("README.md", "README.rst", "README", "readme.md", "docs/README.md")


def _github_repo(url: str) -> tuple[str, str] | None:
    m = re.match(r"https?://github\.com/([^/]+)/([^/#?]+)/?$", url)
    return (m.group(1), m.group(2)) if m else None


async def _fetch_github_readme(
    client: httpx.AsyncClient, owner: str, repo: str
) -> str | None:
    """挨个试常见 README 文件名，全 404 就返回 None，让调用方回落到抓网页。"""
    for name in _README_NAMES:
        raw = f"https://raw.githubusercontent.com/{owner}/{repo}/HEAD/{name}"
        try:
            resp = await client.get(raw)
        except httpx.TransportError:
            continue
        if resp.status_code == 200 and resp.text.strip():
            return resp.text
    return None


async def fetch(url: str) -> tuple[str, str]:
    """返回 (标题, 正文)。抓不到正文时抛 ValueError。"""
    async with httpx.AsyncClient(
        headers={"User-Agent": _UA}, follow_redirects=True, timeout=30.0
    ) as client:
        repo = _github_repo(url)
        if repo:
            # GitHub 仓库页直接抓 raw README，比抽取渲染后的页面干净得多
            readme = await _fetch_github_readme(client, *repo)
            if readme is not None:
                return repo[1], readme
            # 没有可识别的 README，回落到按普通网页抽取

        resp = await client.get(url)
        resp.raise_for_status()
        content = resp.text

    if url.rstrip("/").endswith((".md", ".rst", ".txt")):
        return url.rstrip("/").split("/")[-1], content

    title, body = await asyncio.to_thread(_extract_sync, content, url)
    if not body.strip():
        raise ValueError("正文抽取为空，可能是纯 JS 渲染页面或需要登录")
    return title, body
