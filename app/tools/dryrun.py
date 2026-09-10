"""不连 Telegram，本地跑一遍流水线。

    # 只验证 HTML 清洗和分片，不需要网络和 API key
    conda run -n tg-course-worker python -m app.tools.dryrun --render-only

    # 跑真实流水线（需要 DEEPSEEK_API_KEY），把结果打到终端
    conda run -n tg-course-worker python -m app.tools.dryrun sample.md --level P1
"""
from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

from app.llm import pipeline
from app.llm.deepseek import close_provider
from app.models import Level
from app.render import compose_post, sanitize, split_html

DIRTY = """
<h2>安装 n8n</h2>
<p>先装 <strong>Docker</strong>，然后跑：</p>
<pre><code class="language-bash">docker run -it --rm --name n8n -p 5678:5678 n8nio/n8n</code></pre>
<ul><li>端口冲突就换 <code>-p 5679:5678</code></li>
<li>数据默认在 <code>~/.n8n</code>，记得挂卷</li></ul>
<p>参数里的 a &lt; b &amp;&amp; c &gt; d 要转义。</p>
<script>alert('xss')</script>
<p>更多见 <a href="https://docs.n8n.io">官方文档</a>，还有个 <a href="javascript:void(0)">坏链接</a>。</p>
</b></i>
"""


class _FakeItem(dict):
    """db 返回的是 sqlite3.Row，这里用 dict 模拟同样的下标访问。"""


def _render_only() -> None:
    clean = sanitize(DIRTY)
    print("=" * 60)
    print("sanitize 输出：")
    print("=" * 60)
    print(clean)

    post = compose_post(
        title="用 Docker 跑起 n8n",
        tldr="三行命令把 n8n 跑起来，附常见端口和挂卷坑。",
        body_html=DIRTY,
        tags=["n8n", "Docker"],
        attribution="改编自 n8n 官方文档",
    )
    chunks = split_html(post, limit=200)  # 故意调小，验证分片
    print("\n" + "=" * 60)
    print(f"compose + split(limit=200) → {len(chunks)} 片")
    print("=" * 60)
    for i, c in enumerate(chunks, 1):
        print(f"\n--- 第 {i} 片 ({len(c)} 字符) ---\n{c}")


async def _full(path: Path, level: Level | None) -> None:
    item = _FakeItem(
        raw_text=path.read_text(encoding="utf-8"),
        source_title=path.name,
        source_url="",
        source_link="",
    )

    if level is None:
        relevance, tags, level, reason = await pipeline.classify(item)
        print(f"相关性 {relevance}/10 · 标签 {tags} · 建议 {level.label}")
        print(f"理由：{reason}\n")
        if level is Level.P3:
            print("判定为无关，停止。用 --level 强制指定档位可继续。")
            return

    draft = await pipeline.generate(item, level)
    post = compose_post(
        title=draft.title, tldr=draft.tldr, body_html=draft.body_html,
        tags=draft.tags, attribution=draft.attribution,
    )
    chunks = split_html(post)
    print("=" * 60)
    print(f"{draft.title} · {draft.char_count} 字符 · {len(chunks)} 片")
    print("=" * 60)
    print(post)
    if draft.note:
        print(f"\n📝 模型备注：{draft.note}")


def main() -> None:
    # Windows 控制台默认 GBK，打不出 • 之类的字符
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    ap = argparse.ArgumentParser(description="本地跑流水线，不连 Telegram")
    ap.add_argument("file", nargs="?", type=Path, help="素材文件 (.md/.txt)")
    ap.add_argument("--level", choices=[l.value for l in Level], help="强制指定档位")
    ap.add_argument("--render-only", action="store_true",
                    help="只验证 HTML 清洗和分片，不调用 LLM")
    args = ap.parse_args()

    if args.render_only or args.file is None:
        _render_only()
        return

    level = Level(args.level) if args.level else None
    try:
        asyncio.run(_main(args.file, level))
    except KeyboardInterrupt:
        pass


async def _main(path: Path, level: Level | None) -> None:
    try:
        await _full(path, level)
    finally:
        await close_provider()


if __name__ == "__main__":
    main()
