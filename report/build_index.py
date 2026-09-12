#!/usr/bin/env python
"""扫 report/*.json 重建 index.json。

**index.json 是派生文件，不要手写。** 加一个频道只需要放进
`<slug>.json` + `<slug>.md`，然后跑：

    conda run -n tg-course-worker python report/build_index.py

这么做是因为多个会话会并发往 report/ 里写分析。手工重排 channels 列表
曾经把别的会话刚写进来的记录挤掉过一次——扫目录生成就不会再有这个问题。

叙事性字段（headline / conclusions / applicable_to_project / not_applicable /
disclaimer / content_warning / schema_notes）由本脚本里的常量维护，
改文案改这里；每个频道的数字一律从 `<slug>.json` 读，不在这里重复。
"""
from __future__ import annotations

import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
SCHEMA_VERSION = 3

# 展示顺序。没列到的 slug 按 slug 名排在后面，不会被丢掉。
ORDER = [
    # 机场 / VPN 生态（服务商本体 → 测评号 → 免费分享号）
    "xiaohuojianvpnvpn", "cheapairport_channel", "ffqchannel", "jcplnanmin", "go4sharing",
    # 资源内容号
    "lps999", "xiaoshuwu", "syrjfx_sl", "BYFXZ", "xph_fx", "xuendj1",
    # 搜索 / 广告平台
    "jisou771", "sesecctv",
]

HEADLINE = (
    "十三个样本，三类生意：内容号看 ERR，ERR 塌了就只剩灰产广告一条路；"
    "搜索平台不生产内容、只卖结果页里的广告位，毛利结构最好；"
    "机场生态则是一条完整产业链——服务商本体担经营者责任，"
    "测评号靠隐藏返利关系赚导流费，免费分享号把带宽成本转嫁给被扒节点的所有者。"
)

SCHEMA_NOTES = {
    "v2": "新增 kind 字段（channel | group）。群没有 per-message 阅读量，"
          "median_views / err_pct 对群为 null，改看 online_pct 与 bot_share_pct。"
          "UI 渲染前先判 kind。",
    "v3": "新增顶层 growth 维度（增长策略），结构为 strategy / paid_acquisition / "
          "mechanisms[] / signals{} / assessment，部分记录带 derived_from。"
          "paid_acquisition 取值 none | subs | engagement | exchange | mixed | unknown，"
          "已提到 index.channels[] 与对比表，适合做筛选和配色。",
}

CONCLUSIONS = [
    "内容号里 ERR（中位阅读/订阅）是唯一重要的单一指标。用外部手段堆粉丝数"
    "（买粉、互推）的号，ERR 掉到 1% 以下，之后只能靠给灰产引流凑收入。",
    "LLM 成本在这类生意里可以忽略——日更 350 条一年不到 300 元。瓶颈永远在"
    "内容质量与投递链路。极搜甚至完全不用 LLM。",
    "验证成立的正向循环长这样：内容好到用户愿意转发（lps999 50 次/帖、"
    "xiaoshuwu 49.7 次/帖），流量自己长，于是能接单价高的常驻联盟或包月广告位。"
    "这两个号的 ERR 是 4.5% 和 9%，收入也是全样本最高的两个。",
    "极搜是另一条路：不生产内容、不存资源、不买粉，把「帮用户找东西」做成产品，"
    "广告注在搜索结果顶部。毛利结构最好，技术门槛在索引。",
    "互推在这个生态里是标准件：soso 有互推产品，极搜自建了 @hutui1bot。"
    "但 syrjfx_sl 的 0.5% ERR 说明互推换来的是死粉。",
]

APPLICABLE = [
    {"title": "inline 按钮矩阵", "from": "syrjfx_sl",
     "detail": "每帖固定四件套：主资源 + 搜索更多 + 进群 + 防走丢频道。本项目目前只有"
               "单个「获取完整资料」深链按钮。URL 按钮不吃 callback_data 的 64 字节上限。"},
    {"title": "发布异步化", "from": "syrjfx_sl",
     "detail": "先发消息占位，资源就绪后 edit 补按钮。app/intake.py 已是异步，"
               "app/publisher.py 可对齐。"},
    {"title": "prompt 输出改固定字段 schema", "from": "syrjfx_sl",
     "detail": "结构化字段好入库、好检索、好去重。可收紧 config/prompts/_output_format.md。"},
    {"title": "Telegram 当免费 CDN", "from": "lps999",
     "detail": "102.76 GB、单包最大 2.69 GB 零成本托管。仓库频道可放心扩到大文件。"},
    {"title": "常驻联盟优于零散卖位", "from": "lps999",
     "detail": "广告位挂两年，置顶累计 24 万曝光，边际成本为零。"},
    {"title": "备份频道", "from": "syrjfx_sl",
     "detail": "「防走丢频道」按钮，长期运营该建一个。"},
    {"title": "搜索即广告位", "from": "jisou771",
     "detail": "本项目有素材库和多方向分类，搜索结果页天然是自家资源的推荐位，"
               "不需要外部广告主也成立。"},
    {"title": "关键词位的数据结构", "from": "jisou771",
     "detail": "ad=kw###### 把广告位绑到搜索词上，本质是「用户意图 → 匹配内容」，"
               "是站内推荐可直接复用的模型。"},
    {"title": "给 tg_recon.py 补 sender_id", "from": "jisou771",
     "detail": "_row() 按频道设计，不抓发言人。分析群必须知道 bot 与人的比例，"
               "建议补 sender_id 与 sender_is_bot。"},
]

NOT_APPLICABLE = [
    {"title": "滚动删除历史",
     "reason": "价值全在降低被举报面。正规内容不需要，可检索的历史存量反而是资产。"},
    {"title": "互推 / 买粉涨粉",
     "reason": "堆出来的是死粉，ERR 塌掉之后只剩灰产广告一条变现路。"},
    {"title": "灰产变现（博彩、成人、社工库、诈骗工具）",
     "reason": "在中国大陆属刑事范畴，不在本项目的可选集内。"},
    {"title": "把群简介卖成广告位",
     "reason": "技术可行，但对正规项目是信任自杀。"},
]

DISCLAIMER = (
    "所有收益数字均为基于公开可观测信号（成员数、在线数、阅读量、转发数、"
    "广告 slot id、联盟链接与推广码）的外部估算，非实际财务数据。"
    "联盟分成率与广告位报价不可见，是估算区间宽的主要原因。"
    "jisou771 的数字仅为本群可归因部分，不代表极搜网络整体。"
    "sesecctv 的经常性成本按「整套搜索服务」（平台方承担）口径计，"
    "而其收入是「单个展位」（节点）口径，两者不同口径、不可相减；"
    "对比表里它的成本列因此高于收入列，属正常。"
)

CONTENT_WARNING = (
    "jisou771 与 sesecctv 承载的广告类目包含社工库开盒、线下性交易招揽、境外博彩与成人 AI 换脸，"
    "sesecctv 群内更出现疑似涉未成年人性剥削的用户消息（属应向执法机关举报的对象，未收录）。"
    "这些原始文案与落地域名不适合在任何界面原样展示。"
    "UI 不要显示 data/recon/*.jsonl 的原始群消息内容。"
)

COMPARISON_COLUMNS = [
    "频道 / 群", "类型", "成员/订阅", "中位阅读", "ERR",
    "转发/帖", "主变现", "涨粉方式", "付费获客", "经常性成本", "估计月收入", "风险",
]


# growth.paid_acquisition 的中文显示名。对比表里这一列是判断增长质量的第一眼指标：
# none 基本对应高 ERR，exchange / subs / mixed 基本对应 ERR 塌陷。
_PAID_LABEL = {
    "none": "无",
    "subs": "买粉",
    "engagement": "刷互动",
    "exchange": "互推换量",
    "mixed": "买粉+刷量",
    "unknown": "未知",
}


def _fmt_range(r, unit="¥", suffix="/月"):
    if not r:
        return "—"
    lo, hi = r
    return f"{unit}{lo:,}–{hi:,}{suffix}"


def _cost_cell(d: dict) -> str:
    """对比表的成本列。

    有些记录的 cost.recurring_cny_month 记的是上游平台的整体成本，和
    revenue.est_cny_month（本号自己的分成）不是同一个主体。这种记录会额外
    给出 cost.owner_recurring_cny_month，表里必须用自担口径，否则并排读
    出来就是「成本是收入的十倍」这种假结论。
    """
    c = d["cost"]
    owner = c.get("owner_recurring_cny_month")
    if owner:
        return _fmt_range(owner) + "*"
    return _fmt_range(c.get("recurring_cny_month"))


def _row(d: dict) -> list[str]:
    m, kind = d["metrics"], d.get("kind", "channel")
    n = m.get("members") if kind == "group" else m.get("subscribers")
    return [
        f"{d['slug']} {d['title']}",
        "群" if kind == "group" else "频道",
        f"{n:,}" if n else "—",
        f"{m['median_views']:,}" if m.get("median_views") else "—",
        f"{m['err_pct']}%" if m.get("err_pct") is not None else "—",
        f"{m['forwards_per_post']}" if m.get("forwards_per_post") is not None else "—",
        d["revenue"].get("model", "—"),
        d.get("growth_short") or (d["implementation"].get("growth", "—") or "—")[:18],
        _PAID_LABEL.get(d.get("growth", {}).get("paid_acquisition"), "—"),
        _cost_cell(d),
        _fmt_range(d["revenue"].get("est_cny_month")) +
        ("*" if d["revenue"].get("est_scope") else ""),
        d["risk"]["level"],
    ]


def main() -> None:
    files = {p.stem: p for p in HERE.glob("*.json") if p.stem != "index"}
    slugs = [s for s in ORDER if s in files] + sorted(set(files) - set(ORDER))

    channels, rows, stale = [], [], []
    for s in slugs:
        d = json.loads(files[s].read_text(encoding="utf-8"))
        if d.get("schema_version") != SCHEMA_VERSION:
            stale.append(f"{s}(v{d.get('schema_version')})")
        kind = d.get("kind", "channel")
        m = d["metrics"]
        channels.append({
            "slug": d["slug"], "kind": kind, "username": d.get("username"),
            "url": d["url"], "title": d["title"], "category": d.get("category"),
            "one_liner": d.get("one_liner"),
            "subscribers": m.get("subscribers"), "members": m.get("members"),
            "median_views": m.get("median_views"), "err_pct": m.get("err_pct"),
            "online_pct": m.get("online_pct"), "bot_share_pct": m.get("bot_share_pct"),
            "forwards_per_post": m.get("forwards_per_post"),
            "est_revenue_cny_month": d["revenue"].get("est_cny_month"),
            "recurring_cost_cny_month": d["cost"].get("recurring_cny_month"),
            "monetization": d["revenue"].get("model"),
            "paid_acquisition": d.get("growth", {}).get("paid_acquisition"),
            "growth_strategy": d.get("growth", {}).get("strategy"),
            "risk_level": d["risk"]["level"], "confidence": m.get("confidence"),
            "analyzed_at": d.get("analyzed_at"),
            "markdown": f"{s}.md", "json": f"{s}.json",
            "dump": d.get("source", {}).get("dump"),
        })
        rows.append(_row(d))

    idx = {
        "schema_version": SCHEMA_VERSION,
        "generated_by": "report/build_index.py",
        "generated_at": __import__("datetime").datetime.now(
            __import__("datetime").timezone.utc).replace(microsecond=0).isoformat(),
        "title": "TG 频道分析",
        "description": "竞品 Telegram 频道与群的只读调研。"
                       "每条记录对应 report/<slug>.json 与 <slug>.md。",
        "headline": HEADLINE,
        "schema_notes": SCHEMA_NOTES,
        "channels": channels,
        "comparison": {
            "note": "一行一个频道，可直接当表格渲染。群没有阅读量，相关列为 —。带 * 的单元格表示口径受限：成本列的 * 是「仅本号自担，上游平台成本另计」，收入列的 * 是「仅本号可归因部分，不代表所属网络整体」——详见该记录 json 的 cost.owner_scope_note 与 revenue.est_scope。",
            "columns": COMPARISON_COLUMNS,
            "rows": rows,
        },
        "conclusions": CONCLUSIONS,
        "applicable_to_project": APPLICABLE,
        "not_applicable": NOT_APPLICABLE,
        "disclaimer": DISCLAIMER,
        "content_warning": CONTENT_WARNING,
    }

    out = HERE / "index.json"
    with open(out, "w", encoding="utf-8", newline="\n") as f:
        json.dump(idx, f, ensure_ascii=False, indent=2)
        f.write("\n")

    print(f"{out.relative_to(HERE.parent)}: {len(channels)} 条")
    for c in channels:
        print(f"  {c['kind']:8} {c['slug']:12} {c['title']}")
    if stale:
        print(f"\n⚠️  schema 不是 v{SCHEMA_VERSION} 的文件：{' '.join(stale)}")


if __name__ == "__main__":
    main()
