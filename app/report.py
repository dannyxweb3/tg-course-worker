"""竞品频道分析报告：读 report/ 目录，渲染成后台页面。

这块数据是**静态只读产出**，不进库：它随代码一起提交、一起部署，
改一次分析就是一次 git commit。目录约定见 report/README.md。

正文里引用了竞品频道的原始广告文案（联盟链接、推广码、诱导话术），
一律当不可信输入处理——Markdown 渲染完必须过 sanitize()。
"""
from __future__ import annotations

import html
import json
import logging
import re
from html.parser import HTMLParser
from pathlib import Path
from typing import Any

import markdown

from config.settings import REPORT_DIR

log = logging.getLogger(__name__)

INDEX_FILE = "index.json"
MD_EXTENSIONS = ["tables", "fenced_code", "sane_lists"]


# ---------------------------------------------------------------- HTML 清洗

# 保留的标签。和 app/render.py 的 Telegram 子集不是一回事：
# 那边是发给 Telegram 的，这边是给浏览器的，能留的多不少。
_KEEP = {
    "p", "br", "hr", "ul", "ol", "li", "blockquote",
    "strong", "em", "b", "i", "code", "pre", "del", "sup", "sub",
    "table", "thead", "tbody", "tr", "th", "td",
    "h2", "h3", "h4", "h5", "h6", "a",
}
# 连内容一起丢
_DROP_TREE = {"script", "style", "iframe", "object", "embed", "form", "input", "svg"}
# 正文里的 h1 会和页面自己的 h1 打架，整体降一级
_HEADING = {"h1": "h2", "h2": "h3", "h3": "h4", "h4": "h5", "h5": "h6", "h6": "h6"}
_VOID = {"br", "hr"}
_SAFE_HREF = re.compile(r"^https?://", re.I)


class _Sanitizer(HTMLParser):
    """白名单清洗。不在白名单里的标签丢掉但保留文字内容。"""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.out: list[str] = []
        self._open: list[str] = []
        self._skip = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.lower()
        if tag in _DROP_TREE:
            self._skip += 1
            return
        if self._skip:
            return

        tag = _HEADING.get(tag, tag)
        if tag not in _KEEP:
            return
        if tag in _VOID:
            self.out.append(f"<{tag}>")
            return

        if tag == "a":
            href = (next((v for k, v in attrs if k.lower() == "href"), "") or "").strip()
            # 报告正文里链到 data/recon/*.jsonl 的相对链接在服务器上是断的
            # （data/ 不进版本库），直接降级成纯文本，不留死链
            if not _SAFE_HREF.match(href):
                return
            self.out.append(
                f'<a href="{html.escape(href, quote=True)}" '
                f'target="_blank" rel="noopener nofollow">'
            )
            self._open.append("a")
            return

        # 其余标签一律丢掉全部属性，不给 on* / style 任何机会
        self.out.append(f"<{tag}>")
        self._open.append(tag)

    def handle_startendtag(self, tag: str, attrs) -> None:
        self.handle_starttag(tag, attrs)

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag in _DROP_TREE:
            self._skip = max(0, self._skip - 1)
            return
        if self._skip:
            return
        tag = _HEADING.get(tag, tag)
        if tag in self._open:
            while self._open:
                top = self._open.pop()
                self.out.append(f"</{top}>")
                if top == tag:
                    break

    def handle_data(self, data: str) -> None:
        if not self._skip:
            self.out.append(html.escape(data, quote=False))

    def close_all(self) -> str:
        while self._open:
            self.out.append(f"</{self._open.pop()}>")
        return "".join(self.out)


def sanitize(raw: str) -> str:
    p = _Sanitizer()
    p.feed(raw)
    p.close()
    return p.close_all()


def render_markdown(text: str) -> str:
    """Markdown → 安全 HTML。

    注意顺序：**先渲染再清洗**。反过来（先 html.escape 再渲染）会把
    正文里 `<slug>`、`<伙伴频道ID>` 这类行内代码二次转义成 `&lt;slug&gt;`，
    页面上就会显示成乱码。
    """
    return sanitize(markdown.markdown(text, extensions=MD_EXTENSIONS))


# ---------------------------------------------------------------- 读盘

# 文件是静态的，但开发时会改。按 mtime 做缓存，改完刷新页面就生效，不用重启。
_cache: dict[Path, tuple[float, Any]] = {}


def _read(path: Path, loader) -> Any:
    try:
        mtime = path.stat().st_mtime
    except OSError:
        _cache.pop(path, None)
        return None
    hit = _cache.get(path)
    if hit and hit[0] == mtime:
        return hit[1]
    try:
        value = loader(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        log.warning("读取 %s 失败：%s", path, e)
        return None
    _cache[path] = (mtime, value)
    return value


def index() -> dict[str, Any]:
    """清单。文件缺失或损坏时返回空壳，让页面显示"还没有报告"而不是 500。"""
    data = _read(REPORT_DIR / INDEX_FILE, json.loads)
    if not isinstance(data, dict):
        return {"channels": []}
    data.setdefault("channels", [])
    return data


def channel_entry(slug: str) -> dict[str, Any] | None:
    """按 slug 找清单里的那条。

    slug 来自 URL，**只认清单里已登记的**——不做路径拼接前的正则校验，
    而是直接白名单匹配，从根上堵掉 ../ 穿越。
    """
    for c in index()["channels"]:
        if c.get("slug") == slug:
            return c
    return None


def detail(slug: str) -> tuple[dict[str, Any], str] | None:
    """返回 (结构化指标, 正文 HTML)。slug 不在清单里就是 None。"""
    entry = channel_entry(slug)
    if entry is None:
        return None

    data = _read(REPORT_DIR / f"{slug}.json", json.loads)
    if not isinstance(data, dict):
        # JSON 没了还能看正文，反过来也一样，不要一起垮
        data = {}

    body = _read(REPORT_DIR / f"{slug}.md", render_markdown) or ""
    return {**entry, **data}, body
