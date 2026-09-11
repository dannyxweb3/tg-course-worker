"""生成频道 / 讨论组 / 三个 bot 的头像。

    conda run -n tg-course-worker python scripts/make_avatars.py

设计约束来自 Telegram 自己：头像会被裁成圆形，且在会话列表里只有 ~40px。
所以——所有元素收在内切圆的安全区内、只有一个主体轮廓、不放小字。

视觉体系：底部两层「栈」是全家族共用的标识，顶部符号区分角色。
"""
from __future__ import annotations

import sys
from pathlib import Path

import fitz

OUT = Path(__file__).resolve().parent.parent / "assets" / "avatars"
SIZE = 512


def _diamond(cx: float, cy: float, w: float, h: float) -> str:
    return f"M {cx-w} {cy} L {cx} {cy-h} L {cx+w} {cy} L {cx} {cy+h} Z"


# 顶部符号：每个角色一个，都控制在 y≈105-290、x≈170-340 之间
GLYPHS = {
    # 闪电 = 自动化 / 通电
    "channel": "M 302 100 L 193 214 L 248 214 L 216 292 L 327 174 L 268 174 Z",
    # 对话气泡 = 评论区
    "group": (
        "M 187 118 h 138 a 34 34 0 0 1 34 34 v 74 a 34 34 0 0 1 -34 34 h -52 "
        "l -60 44 v -44 h -26 a 34 34 0 0 1 -34 -34 v -74 a 34 34 0 0 1 34 -34 Z"
    ),
    # 向下箭头 = 取资料
    "sale": "M 232 100 h 48 v 104 h 40 L 256 292 L 192 204 h 40 Z",
    # 纸飞机 = 发布
    "post": "M 344 104 L 168 192 L 236 218 L 252 292 L 288 232 Z",
    # 漏斗 = 素材进料
    "desk": "M 172 112 L 340 112 L 284 196 L 284 268 L 228 294 L 228 196 Z",
}

SPECS = {
    "channel": {
        "file": "01-channel-工具栈.png",
        "bg": [("#4c1d95", 0), ("#1d4ed8", 55), ("#0ea5e9", 100)],
        "mark": "#fde047",   # 电光黄，在蓝紫底上跳出来
        "stack": "#1e1b4b",
    },
    "group": {
        "file": "02-group-讨论组.png",
        "bg": [("#7c2d12", 0), ("#ea580c", 60), ("#f59e0b", 100)],
        "mark": "#ffffff",
        "stack": "#431407",
    },
    "sale": {
        "file": "03-bot-资料机.png",
        "bg": [("#064e3b", 0), ("#059669", 60), ("#34d399", 100)],
        "mark": "#ffffff",
        "stack": "#022c22",
    },
    "post": {
        "file": "04-bot-发布机.png",
        "bg": [("#0c4a6e", 0), ("#0284c7", 60), ("#38bdf8", 100)],
        "mark": "#ffffff",
        "stack": "#082f49",
    },
    "desk": {
        "file": "05-bot-生产机.png",
        # 内部工具，刻意压低存在感，别跟对外的三个抢眼
        "bg": [("#111827", 0), ("#334155", 60), ("#64748b", 100)],
        "mark": "#e2e8f0",
        "stack": "#0f172a",
    },
}


def _hex(c: str) -> tuple[int, int, int]:
    c = c.lstrip("#")
    return int(c[0:2], 16), int(c[2:4], 16), int(c[4:6], 16)


def _ramp(stops: list[tuple[str, float]], t: float) -> str:
    """在多个色标之间线性插值，t 为 0-100。"""
    for i in range(len(stops) - 1):
        (c0, p0), (c1, p1) = stops[i], stops[i + 1]
        if p0 <= t <= p1:
            k = 0.0 if p1 == p0 else (t - p0) / (p1 - p0)
            a, b = _hex(c0), _hex(c1)
            r, g, bl = (round(a[j] + (b[j] - a[j]) * k) for j in range(3))
            return f"#{r:02x}{g:02x}{bl:02x}"
    return stops[-1][0]


def _gradient_bands(stops: list[tuple[str, float]], n: int = 128) -> str:
    """PyMuPDF 的 SVG 子集不支持 linearGradient，用纯色横条手工铺一层。
    128 条在 512px 上每条 4px，肉眼看不出断层。
    """
    h = SIZE / n
    return "".join(
        f'<rect x="0" y="{i*h:.2f}" width="{SIZE}" height="{h+0.6:.2f}" '
        f'fill="{_ramp(stops, i / (n - 1) * 100)}"/>'
        for i in range(n)
    )


def _glow(cx: float, cy: float, r: float, n: int = 26) -> str:
    """radialGradient 同样不支持，用同心圆叠低透明度白色模拟高光。"""
    return "".join(
        f'<circle cx="{cx}" cy="{cy}" r="{r * (1 - i / n):.1f}" '
        f'fill="#ffffff" opacity="0.016"/>'
        for i in range(n)
    )


def build_svg(key: str) -> str:
    s = SPECS[key]
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="{SIZE}" height="{SIZE}"
     viewBox="0 0 {SIZE} {SIZE}">
  {_gradient_bands(s["bg"])}
  {_glow(256, 176, 300)}

  <!-- 底部两层「栈」：全家族共用的标识 -->
  <path d="{_diamond(256, 382, 128, 37)}" fill="{s['stack']}" opacity="0.38"/>
  <path d="{_diamond(256, 316, 128, 37)}" fill="{s['stack']}" opacity="0.72"/>

  <!-- 顶部符号：区分角色 -->
  <path d="{GLYPHS[key]}" fill="{s['mark']}"/>
</svg>"""


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    OUT.mkdir(parents=True, exist_ok=True)

    for key, spec in SPECS.items():
        svg_bytes = build_svg(key).encode("utf-8")
        doc = fitz.open(stream=svg_bytes, filetype="svg")
        pix = doc[0].get_pixmap(alpha=False)
        path = OUT / spec["file"]
        pix.save(path)
        doc.close()
        print(f"  + {path.name}  {pix.width}x{pix.height}")

    print(f"\n共 {len(SPECS)} 张，输出在 {OUT}")


if __name__ == "__main__":
    main()
