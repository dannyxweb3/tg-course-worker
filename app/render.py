"""Telegram HTML 清洗与分片。

Telegram 的 HTML 解析模式只认一小撮标签，多一个 <p> 就会整条消息发送失败。
LLM 再怎么在 prompt 里叮嘱也会偶尔越界，所以发送前必须过一遍这里。
"""
from __future__ import annotations

import html
import re
from html.parser import HTMLParser

# Telegram 单条消息上限；带 media 的 caption 只有 1024
TEXT_LIMIT = 4096
CAPTION_LIMIT = 1024
# 留出标题、TL;DR、来源标注、标签的空间
BODY_SOFT_LIMIT = 3500

# 直接保留的标签
_KEEP = {"b", "i", "u", "s", "code", "pre", "blockquote", "tg-spoiler"}
# 同义标签归一
_ALIAS = {
    "strong": "b", "em": "i", "ins": "u", "strike": "s", "del": "s",
    "mark": "b", "h1": "b", "h2": "b", "h3": "b", "h4": "b", "h5": "b", "h6": "b",
}
# 丢标签但保留内容，并在前后补换行
_BLOCK = {"p", "div", "section", "article", "tr", "table", "tbody", "thead"}
# 完全丢弃（含内容）
_DROP_TREE = {"script", "style", "head", "meta", "link"}


class _Sanitizer(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.out: list[str] = []
        self._open: list[str] = []
        self._skip_depth = 0

    # -- helpers --
    def _emit(self, s: str) -> None:
        if self._skip_depth == 0:
            self.out.append(s)

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.lower()
        if tag in _DROP_TREE:
            self._skip_depth += 1
            return
        if self._skip_depth:
            return

        if tag == "br":
            self._emit("\n")
            return
        if tag == "li":
            self._emit("\n• ")
            return
        if tag in {"ul", "ol"}:
            self._emit("\n")
            return
        if tag in _BLOCK:
            self._emit("\n")
            return

        if tag == "a":
            href = next((v for k, v in attrs if k.lower() == "href"), None)
            if href and re.match(r"^(https?://|tg://)", href.strip()):
                self._emit(f'<a href="{html.escape(href.strip(), quote=True)}">')
                self._open.append("a")
            return

        if tag == "span":
            cls = next((v for k, v in attrs if k.lower() == "class"), "") or ""
            if "tg-spoiler" in cls:
                self._emit("<tg-spoiler>")
                self._open.append("tg-spoiler")
            return

        if tag == "code":
            # Telegram 支持 <pre><code class="language-xxx"> 做语法高亮，保留它
            cls = next((v for k, v in attrs if k.lower() == "class"), "") or ""
            m = re.search(r"language-([A-Za-z0-9_+-]{1,20})", cls)
            self._emit(f'<code class="language-{m.group(1)}">' if m else "<code>")
            self._open.append("code")
            return

        norm = _ALIAS.get(tag, tag)
        if norm in _KEEP:
            self._emit(f"<{norm}>")
            self._open.append(norm)

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag in _DROP_TREE:
            self._skip_depth = max(0, self._skip_depth - 1)
            return
        if self._skip_depth:
            return

        if tag in _BLOCK or tag in {"ul", "ol", "li"}:
            self._emit("\n")
            return

        norm = "tg-spoiler" if tag == "span" else _ALIAS.get(tag, tag)
        if norm in _KEEP or norm == "a":
            # 只闭合确实开过的标签，避免 LLM 吐出孤立的 </b>
            if norm in self._open:
                while self._open:
                    top = self._open.pop()
                    self._emit(f"</{top}>")
                    if top == norm:
                        break

    def handle_data(self, data: str) -> None:
        self._emit(html.escape(data, quote=False))

    def close_all(self) -> str:
        while self._open:
            self.out.append(f"</{self._open.pop()}>")
        return "".join(self.out)


# 认识的标签名。不在这个集合里的 "<xxx>" 一律当普通文本，不当标签。
_KNOWN_TAGS = (
    _KEEP | set(_ALIAS) | _BLOCK | _DROP_TREE
    | {"a", "span", "br", "ul", "ol", "li", "img", "td", "th", "font", "small",
       "sup", "sub", "hr", "html", "body", "figure", "figcaption", "blockquote"}
)
_MAYBE_TAG = re.compile(r"</?([a-zA-Z][a-zA-Z0-9-]*)(?:\s[^<>]*?)?/?>")


def _escape_stray_lt(raw: str) -> str:
    """把不构成合法标签的 "<" 转义掉。

    教程正文里 `if a<b:`、`List<String>`、`cmd < input` 这类写法很常见，
    HTMLParser 会把 `<b` 当成加粗标签，连着后面的内容一起吞掉。所以先扫一遍，
    只有"认识的标签名 + 闭合的尖括号"才放行，其余的 < 都还原成文本。
    """
    out: list[str] = []
    pos = 0
    for m in _MAYBE_TAG.finditer(raw):
        if m.group(1).lower() not in _KNOWN_TAGS:
            continue
        out.append(raw[pos:m.start()].replace("<", "&lt;"))
        out.append(m.group(0))
        pos = m.end()
    out.append(raw[pos:].replace("<", "&lt;"))
    return "".join(out)


def sanitize(raw: str) -> str:
    """把任意 HTML 收敛成 Telegram 能接受的子集。"""
    p = _Sanitizer()
    p.feed(_escape_stray_lt(raw or ""))
    p.close()
    text = p.close_all()
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


# ---------------------------------------------------------------- 分片

_PRE_BLOCK = re.compile(r"<pre>.*?</pre>", re.S)


def _atomic_blocks(text: str) -> list[str]:
    """把正文切成"不可再分"的块：<pre> 整块保留，其余按段落切。"""
    blocks: list[str] = []
    pos = 0
    for m in _PRE_BLOCK.finditer(text):
        head = text[pos:m.start()]
        blocks.extend(b for b in head.split("\n\n") if b.strip())
        blocks.append(m.group(0))
        pos = m.end()
    tail = text[pos:]
    blocks.extend(b for b in tail.split("\n\n") if b.strip())
    return blocks


def split_html(text: str, limit: int = TEXT_LIMIT) -> list[str]:
    """按段落边界分片，绝不切断 <pre> 代码块和内联标签。"""
    text = text.strip()
    if len(text) <= limit:
        return [text]

    chunks: list[str] = []
    cur = ""
    for block in _atomic_blocks(text):
        candidate = f"{cur}\n\n{block}" if cur else block
        if len(candidate) <= limit:
            cur = candidate
            continue
        if cur:
            chunks.append(cur)
            cur = ""
        if len(block) <= limit:
            cur = block
        else:
            # 单块就超长（通常是超大代码块），按行硬切
            line_buf = ""
            for line in block.split("\n"):
                cand = f"{line_buf}\n{line}" if line_buf else line
                if len(cand) <= limit:
                    line_buf = cand
                else:
                    if line_buf:
                        chunks.append(line_buf)
                    line_buf = line[:limit]
            cur = line_buf
    if cur:
        chunks.append(cur)
    return chunks


# ---------------------------------------------------------------- 组装

def compose_post(
    *, title: str, tldr: str, body_html: str, tags: list[str], attribution: str
) -> str:
    """把一版草稿组装成频道里最终的样子。审核预览用的也是这个函数，
    保证"所见即所发"。
    """
    parts = [f"<b>{html.escape(title)}</b>"]
    if tldr:
        parts.append(html.escape(tldr))
    parts.append(sanitize(body_html))
    if attribution:
        parts.append(f"<i>{html.escape(attribution)}</i>")
    if tags:
        parts.append(" ".join("#" + re.sub(r"\W+", "_", t) for t in tags))
    return "\n\n".join(p for p in parts if p.strip())
