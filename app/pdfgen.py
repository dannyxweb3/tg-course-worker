"""把一版文案渲染成教程 PDF。

复用 telegraph.html_to_nodes 的解析结果——它已经把我们那套 Telegram HTML
子集变成了带层级的节点（h4 / ul / pre / p），序列化成标准 HTML 喂给
PyMuPDF 的 Story API 就能自动分页。

字体用 PyMuPDF 内置的 china-s，不依赖系统字体文件，Ubuntu 上一样能跑。
存盘前必须 subset_fonts()：整套 CJK 字体嵌进去是 3.6MB，子集化之后只剩 50KB。
"""
from __future__ import annotations

import html as _html
import logging
import re
from pathlib import Path

import fitz

from app import telegraph
from app.models import Draft
from config.settings import DATA_DIR

log = logging.getLogger(__name__)

PDF_DIR = DATA_DIR / "pdf"

CSS = """
* { font-family: china-s; }
body { font-size: 10.5px; line-height: 1.65; color: #1a1a1a; }
h1 { font-size: 19px; margin: 0 0 4px 0; }
h2 { font-size: 12px; margin: 16px 0 6px 0; color: #111; }
h3, h4 { font-size: 12px; margin: 16px 0 6px 0; color: #111; }
p { margin: 0 0 9px 0; }
ul { margin: 0 0 9px 0; }
li { margin: 0 0 4px 0; }
pre { font-size: 9.5px; background: #f2f3f5; padding: 7px; margin: 0 0 10px 0;
      line-height: 1.45; }
code { font-size: 9.5px; background: #f2f3f5; }
a { color: #1a5fb4; }
.lead { font-size: 11px; color: #333; margin: 0 0 14px 0; }
.meta { font-size: 9px; color: #777; margin: 0 0 16px 0; }
.foot { font-size: 8.5px; color: #999; margin-top: 20px; }
"""


def _esc(s: str) -> str:
    return _html.escape(s or "", quote=False)


def _nodes_to_html(nodes: list) -> str:
    """telegraph 的节点树 → 标准 HTML。Story 只认标准标签。"""
    out: list[str] = []
    for n in nodes:
        if isinstance(n, str):
            out.append(_esc(n))
            continue
        tag = n.get("tag", "")
        if tag == "br":
            out.append("<br/>")
            continue
        inner = _nodes_to_html(n.get("children", []))
        if tag == "a":
            href = n.get("attrs", {}).get("href", "")
            out.append(f'<a href="{_html.escape(href, quote=True)}">{inner}</a>')
        elif tag == "aside":
            out.append(f'<p class="meta">{inner}</p>')
        elif tag in ("h3", "h4"):
            out.append(f"<h3>{inner}</h3>")
        elif tag in ("p", "ul", "li", "pre", "b", "i", "u", "s", "code",
                     "blockquote"):
            out.append(f"<{tag}>{inner}</{tag}>")
        else:
            out.append(inner)
    return "".join(out)


def build_html(draft: Draft, item) -> str:
    """组装整份 PDF 的 HTML。首页固定带来源，转载内容这条不能省。"""
    nodes = telegraph.html_to_nodes(draft.body_html)
    body = _nodes_to_html(nodes)

    meta: list[str] = []
    src_title = item["source_title"] if item is not None else ""
    src = (item["source_url"] or item["source_link"]) if item is not None else ""
    if src_title:
        meta.append(f"来源：{_esc(src_title)}")
    if src:
        meta.append(f'原文：<a href="{_html.escape(src, quote=True)}">{_esc(src[:80])}</a>')

    # LLM 写的 attribution 常常把来源和链接又抄一遍，重复就别放了
    attr = (draft.attribution or "").strip()
    if attr and not (
        (src_title and src_title[:20] in attr) or (src and src[:30] in attr)
    ):
        meta.append(_esc(attr))

    parts = [f"<h1>{_esc(draft.title)}</h1>"]
    if meta:
        parts.append(f'<p class="meta">{" ｜ ".join(meta)}</p>')
    if draft.tldr:
        parts.append(f'<p class="lead">{_esc(draft.tldr)}</p>')
    parts.append(body)
    if draft.tags:
        parts.append(f'<p class="foot">标签：{_esc(" · ".join(draft.tags))}</p>')
    return "".join(parts)


def _sweep_raw() -> None:
    """清掉上次没删干净的临时文件。Windows 上文件句柄释放有延迟，
    当场删不掉，下次进来就能删了。"""
    if not PDF_DIR.exists():
        return
    for f in PDF_DIR.glob("*.raw.pdf"):
        try:
            f.unlink()
        except OSError:
            pass


def render(draft: Draft, item, out_path: Path | None = None) -> Path:
    """渲染成 PDF，返回文件路径。"""
    PDF_DIR.mkdir(parents=True, exist_ok=True)
    _sweep_raw()
    if out_path is None:
        slug = re.sub(r"[^\w一-鿿-]+", "_", draft.title)[:48] or "tutorial"
        out_path = PDF_DIR / f"{item['id'] if item else 0}-{slug}.pdf"

    # 先排版到临时文件，再子集化输出到最终路径。
    # 不要「写最终路径 → 打开 → 删掉 → 改名」：Windows 上文件句柄还没释放，
    # unlink 会直接 PermissionError。
    raw = out_path.with_suffix(".raw.pdf")
    story = fitz.Story(html=build_html(draft, item), user_css=CSS)
    writer = fitz.DocumentWriter(str(raw))
    more, pages = 1, 0
    while more and pages < 200:      # 200 页封顶，防跑飞
        dev = writer.begin_page(fitz.paper_rect("a4"))
        more, _ = story.place(fitz.Rect(48, 52, 547, 792))
        story.draw(dev)
        writer.end_page()
        pages += 1
    writer.close()

    # 不做子集化的话每份 3.6MB，全是整套嵌进去的 CJK 字体；子集化后 ~90KB
    doc = fitz.open(raw)
    try:
        doc.subset_fonts()
        doc.save(str(out_path), garbage=4, deflate=True, clean=True)
    finally:
        doc.close()
    try:
        raw.unlink(missing_ok=True)
    except OSError:
        log.debug("临时文件 %s 暂时删不掉，下次再说", raw.name)

    log.info("PDF 已生成 %s（%s 页，%.0f KB）",
             out_path.name, pages, out_path.stat().st_size / 1024)
    return out_path
