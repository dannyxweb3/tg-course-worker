"""Telegraph 全文页。

频道帖只有 4096 字符，而素材原文常常有两三万。把完整版推到 Telegraph，
频道给摘要、bot 给全文——Instant View 的阅读体验比网盘链接好得多，
而且免费、无需注册、不占存储。

Telegraph 只认一小撮标签（比 Telegram 那套还窄：没有 h1/h2，标题得用 h3/h4），
所以出站前同样要过一遍转换。
"""
from __future__ import annotations

import copy
import json
import logging
import re
from html.parser import HTMLParser
from pathlib import Path
from typing import Any

import httpx

from config.settings import DATA_DIR

log = logging.getLogger(__name__)

API = "https://api.telegra.ph"
TOKEN_FILE = DATA_DIR / "telegraph.json"

# content 参数上限 64KB。中文按 UTF-8 三字节算，再给标签留出余量。
MAX_CONTENT_BYTES = 60_000

# Telegraph 支持的标签，其余一律降级成纯文本
_KEEP = {
    "a", "aside", "b", "blockquote", "br", "code", "em", "figcaption",
    "figure", "h3", "h4", "hr", "i", "img", "li", "ol", "p", "pre", "s",
    "strong", "u", "ul", "video",
}
_ALIAS = {"strong": "b", "em": "i", "tg-spoiler": "i"}

Node = str | dict[str, Any]


# ---------------------------------------------------------------- 账号

def _load_token() -> str:
    if TOKEN_FILE.exists():
        try:
            return json.loads(TOKEN_FILE.read_text(encoding="utf-8"))["access_token"]
        except Exception:
            log.warning("telegraph.json 读不出来，将重新建号")
    return ""


async def ensure_account(client: httpx.AsyncClient, short_name: str) -> str:
    """拿 access_token，没有就建一个匿名账号。token 落盘复用——
    换了 token 之后旧页面就编辑不了了。
    """
    token = _load_token()
    if token:
        return token

    resp = await client.post(
        f"{API}/createAccount",
        data={"short_name": short_name[:32] or "worker", "author_name": short_name[:128]},
    )
    resp.raise_for_status()
    data = resp.json()
    if not data.get("ok"):
        raise RuntimeError(f"Telegraph 建号失败：{data.get('error')}")
    token = data["result"]["access_token"]
    TOKEN_FILE.write_text(
        json.dumps({"access_token": token, "short_name": short_name},
                   ensure_ascii=False, indent=1),
        encoding="utf-8",
    )
    log.info("已创建 Telegraph 账号，token 存到 %s", TOKEN_FILE)
    return token


# ---------------------------------------------------------------- HTML → 节点

class _Inline(HTMLParser):
    """把一段行内 HTML 转成 Telegraph 的节点数组。"""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.root: list[Node] = []
        self.stack: list[dict] = []

    def _sink(self) -> list[Node]:
        return self.stack[-1]["children"] if self.stack else self.root

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = _ALIAS.get(tag.lower(), tag.lower())
        if tag == "br":
            self._sink().append({"tag": "br"})
            return
        if tag not in _KEEP:
            return
        node: dict[str, Any] = {"tag": tag, "children": []}
        if tag == "a":
            href = next((v for k, v in attrs if k.lower() == "href"), "")
            if not href or not re.match(r"^(https?://|tg://)", href):
                return  # 没有合法 href 的 a 标签直接丢，文字照留
            node["attrs"] = {"href": href}
        self._sink().append(node)
        self.stack.append(node)

    def handle_endtag(self, tag: str) -> None:
        tag = _ALIAS.get(tag.lower(), tag.lower())
        for i in range(len(self.stack) - 1, -1, -1):
            if self.stack[i]["tag"] == tag:
                del self.stack[i:]
                return

    def handle_data(self, data: str) -> None:
        if data:
            self._sink().append(data)

    def result(self) -> list[Node]:
        # children 为空的标签 Telegraph 会报错，清掉
        def prune(nodes: list[Node]) -> list[Node]:
            out: list[Node] = []
            for n in nodes:
                if isinstance(n, str):
                    if n.strip() or n == " ":
                        out.append(n)
                    continue
                kids = prune(n.get("children", []))
                if kids:
                    n["children"] = kids
                    out.append(n)
                elif n["tag"] in ("br", "hr", "img"):
                    n.pop("children", None)
                    out.append(n)
            return out

        return prune(self.root)


_PRE = re.compile(r"<pre>(.*?)</pre>", re.S)
_BULLET = re.compile(r"^[•·\-\*]\s+")
_HEAD = re.compile(r"^<b>(.{1,40})</b>$")


def html_to_nodes(html_text: str) -> list[Node]:
    """把 Telegram HTML 子集转成 Telegraph 节点。

    额外做两件 Telegraph 才有的事：连续的「• 」行合并成 <ul>，
    独占一行的 <b>短标题</b> 提升成 <h4>——Telegram 没有标题标签，
    Telegraph 有，用上阅读体验会好很多。
    """
    nodes: list[Node] = []
    bullets: list[Node] = []

    def flush_bullets() -> None:
        if bullets:
            nodes.append({"tag": "ul", "children": list(bullets)})
            bullets.clear()

    pos = 0
    blocks: list[tuple[str, str]] = []
    for m in _PRE.finditer(html_text):
        for b in html_text[pos:m.start()].split("\n\n"):
            if b.strip():
                blocks.append(("text", b))
        blocks.append(("pre", m.group(1)))
        pos = m.end()
    for b in html_text[pos:].split("\n\n"):
        if b.strip():
            blocks.append(("text", b))

    for kind, block in blocks:
        if kind == "pre":
            code = re.sub(r"</?code[^>]*>", "", block)
            p = _Inline()
            p.feed(code)
            flush_bullets()
            nodes.append({"tag": "pre", "children": p.result() or [" "]})
            continue

        for line in block.split("\n"):
            line = line.strip()
            if not line:
                continue
            if _BULLET.match(line):
                p = _Inline()
                p.feed(_BULLET.sub("", line))
                bullets.append({"tag": "li", "children": p.result() or [" "]})
                continue
            flush_bullets()
            head = _HEAD.match(line)
            if head:
                nodes.append({"tag": "h4", "children": [head.group(1)]})
                continue
            p = _Inline()
            p.feed(line)
            kids = p.result()
            if kids:
                nodes.append({"tag": "p", "children": kids})
    flush_bullets()
    return nodes


# trafilatura 开着 include_links 抽出来的正文里，链接是 markdown 形式的。
# 不还原的话页面上会出现一坨 [文字](http://…) 裸露的方括号。
_MD_LINK = re.compile(r"\[([^\]\n]{1,250})\]\((https?://[^\s)]+)\)")
_BARE_URL = re.compile(r"(?<![(\w])(https?://[^\s<>()\[\]，。；、]+)")
# 有些站点的「相关文章卡片」会被抽成一个跨行的 markdown 链接。
# _linkify 是按行跑的，跨行的匹配不上，所以先压成一行。
_MD_MULTILINE = re.compile(r"\[([^\]]{1,250}?)\]\((https?://[^\s)]+)\)", re.S)


def _flatten_md_links(text: str) -> str:
    return _MD_MULTILINE.sub(
        lambda m: f"[{' '.join(m.group(1).split())}]({m.group(2)})", text
    )


def _linkify(line: str) -> list[Node]:
    """把一行纯文本里的 markdown 链接和裸链接转成 a 节点。"""
    out: list[Node] = []
    pos = 0
    for m in _MD_LINK.finditer(line):
        if m.start() > pos:
            out.extend(_bare(line[pos:m.start()]))
        label = m.group(1).strip()
        if len(label) > 80:      # 卡片式导航块会抽出很长的链接文字
            label = label[:77] + "…"
        out.append({"tag": "a", "attrs": {"href": m.group(2)},
                    "children": [label]})
        pos = m.end()
    out.extend(_bare(line[pos:]))
    return out


def _bare(chunk: str) -> list[Node]:
    out: list[Node] = []
    pos = 0
    for m in _BARE_URL.finditer(chunk):
        if m.start() > pos:
            out.append(chunk[pos:m.start()])
        url = m.group(1)
        label = url if len(url) <= 60 else url[:57] + "…"
        out.append({"tag": "a", "attrs": {"href": url}, "children": [label]})
        pos = m.end()
    if pos < len(chunk):
        out.append(chunk[pos:])
    return [n for n in out if n != ""]


def text_to_nodes(text: str) -> list[Node]:
    """纯文本（trafilatura 抽出来的原文）转节点：空行分段，行内保留换行。

    顺带把 markdown 标题和列表也认出来——原文里本来就有结构，
    丢掉可惜。
    """
    nodes: list[Node] = []
    bullets: list[Node] = []
    text = _flatten_md_links(text)

    def flush() -> None:
        if bullets:
            nodes.append({"tag": "ul", "children": list(bullets)})
            bullets.clear()

    for para in re.split(r"\n\s*\n", text):
        if not para.strip():
            continue
        kids: list[Node] = []
        for line in para.split("\n"):
            stripped = line.strip()
            if not stripped:
                continue
            head = re.match(r"^#{1,6}\s+(.+)$", stripped)
            if head:
                flush()
                if kids:
                    nodes.append({"tag": "p", "children": kids})
                    kids = []
                nodes.append({"tag": "h4", "children": _linkify(head.group(1))})
                continue
            if _BULLET.match(stripped):
                if kids:
                    nodes.append({"tag": "p", "children": kids})
                    kids = []
                bullets.append(
                    {"tag": "li", "children": _linkify(_BULLET.sub("", stripped)) or [" "]}
                )
                continue
            flush()
            if kids:
                kids.append({"tag": "br"})
            kids.extend(_linkify(line))
        flush()
        if kids:
            nodes.append({"tag": "p", "children": kids})
    flush()
    return nodes


def _size(ns: list[Node]) -> int:
    return len(json.dumps(ns, ensure_ascii=False).encode("utf-8"))


def _cut_tail_text(node: dict) -> bool:
    """从节点尾部砍掉一点文字，砍到了返回 True。"""
    kids = node.get("children")
    if not kids:
        return False
    for i in range(len(kids) - 1, -1, -1):
        k = kids[i]
        if isinstance(k, str):
            if len(k) > 40:
                kids[i] = k[: int(len(k) * 0.8)]
            else:
                kids.pop(i)
            return True
        if _cut_tail_text(k):
            return True
        kids.pop(i)
        return True
    return False


def _shrink(node: Node, budget: int) -> Node | None:
    """把单个节点裁进 budget。整篇只有一个巨型段落时全靠它，
    否则按节点数二分会把正文整段丢掉。
    """
    if isinstance(node, str):
        return node[: max(0, budget // 3)] or None
    n = copy.deepcopy(node)
    while _size([n]) > budget:
        if not _cut_tail_text(n):
            return None
    return n


def _fit(nodes: list[Node], source_url: str) -> tuple[list[Node], bool]:
    """裁到 64KB 以内。截断时在末尾说明，并留一条回原文的路。"""
    size = _size
    if size(nodes) <= MAX_CONTENT_BYTES:
        return nodes, False

    budget = MAX_CONTENT_BYTES - 800  # 给尾注留位置
    lo, hi = 0, len(nodes)
    while lo < hi:
        mid = (lo + hi + 1) // 2
        if size(nodes[:mid]) <= budget:
            lo = mid
        else:
            hi = mid - 1
    kept = nodes[:lo]

    # 还有余量就把下一个节点裁一半塞进来，避免正文被整段丢弃
    left = budget - size(kept)
    if lo < len(nodes) and left > 200:
        piece = _shrink(nodes[lo], left)
        if piece is not None:
            kept.append(piece)
    tail: list[Node] = ["（原文过长，此处为节选。"]
    if source_url:
        tail += ["完整版见 ", {"tag": "a", "attrs": {"href": source_url},
                             "children": ["原文链接"]}, "。）"]
    else:
        tail.append("）")
    kept.append({"tag": "p", "children": [{"tag": "i", "children": tail}]})
    return kept, True


# ---------------------------------------------------------------- 发布

def path_of(url: str) -> str:
    """从页面 URL 取出 path，编辑时要用。"""
    return url.rstrip("/").rsplit("/", 1)[-1]


async def publish(
    *,
    title: str,
    nodes: list[Node],
    author_name: str = "",
    author_url: str = "",
    source_url: str = "",
    edit_path: str = "",
) -> tuple[str, bool]:
    """建页或改页，返回 (url, 是否被截断)。

    已经有页面就改它、不要新建——旧链接可能已经发给读者了。
    """
    nodes, truncated = _fit(nodes, source_url)
    if not nodes:
        raise ValueError("没有可发布的内容")

    async with httpx.AsyncClient(timeout=45.0) as client:
        token = await ensure_account(client, author_name or "tg-course-worker")
        payload = {
            "access_token": token,
            "title": (title or "无标题")[:256],
            "author_name": author_name[:128],
            "content": json.dumps(nodes, ensure_ascii=False),
            "return_content": "false",
        }
        if author_url:
            payload["author_url"] = author_url[:512]

        endpoint = f"{API}/editPage/{edit_path}" if edit_path else f"{API}/createPage"
        resp = await client.post(endpoint, data=payload)
        resp.raise_for_status()
        data = resp.json()

        if not data.get("ok") and edit_path:
            # 页面被删了或换过 token，退回新建
            log.warning("编辑 Telegraph 页失败（%s），改为新建", data.get("error"))
            resp = await client.post(f"{API}/createPage", data=payload)
            resp.raise_for_status()
            data = resp.json()

        if not data.get("ok"):
            raise RuntimeError(f"Telegraph 发布失败：{data.get('error')}")
        return data["result"]["url"], truncated
