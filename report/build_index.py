#!/usr/bin/env python
"""扫 report/*.json 重建 index.json。

**index.json 是派生文件，不要手写。** 加一个频道只需要放进
`<slug>.json` + `<slug>.md`，然后跑：

    conda run -n tg-course-worker python report/build_index.py

这么做是因为多个会话会并发往 report/ 里写分析。手工重排 channels 列表
曾经把别的会话刚写进来的记录挤掉过一次——扫目录生成就不会再有这个问题。

叙事性字段（headline / conclusions / disclaimer / content_warning /
schema_notes）由本脚本里的常量维护，改文案改这里；每个频道的数字一律从
`<slug>.json` 读，不在这里重复。

**报告只做分析，不产出「可借鉴 / 可迁移到本项目」这类结论。**
曾经有过 applicable_to_project / not_applicable 两个字段和每个频道的
takeaways，已全部移除，不要再加回来。
"""
from __future__ import annotations

import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
SCHEMA_VERSION = 3

# 展示顺序。没列到的 slug 按 slug 名排在后面，不会被丢掉。
ORDER = [
    # 正规机构（对照组）
    "cdtchinesefeed",
    # 机场 / VPN 生态（服务商本体 → 测评号 → 免费分享号）
    "xiaohuojianvpnvpn", "cheapairport_channel", "ffqchannel", "jcplnanmin", "go4sharing",
    "jichangdl",
    # 资源内容号（按 ERR 与内容质量降序）
    "wuwuwuEnglish", "lps999", "xiaoshuwu", "Czenb6", "bookusefor4",
    "pixiv_top50_r18", "Aichengrenyulan", "KaiPanshare", "FLAC_HR", "yingshi12345", "BYFXZ",
    "syrjfx_sl", "xph_fx", "bookMiao", "xuendj1", "vomfx",
    # 个人 / 无害小号（对照组）
    "hayami_kiraa", "qzxx_comment",
    # 搜索 / 广告平台
    "jisou771", "sousuohp", "sesecctv",
    # 直接犯罪服务（恶意软件 / 公民信息交易 / 招嫖 / 犯罪软件外包）
    "dajian910", "syfhhbd", "yuankong238", "mytdpaqj77777",
    "chengdu_normal_university", "CDdhyzck1", "szflwbd", "gansu8821", "guonrsgc",
    # AI 生成违禁内容（制作方，非搬运）
    "bcuhz",
]

HEADLINE = (
    "三十个样本，谱系两端都有：一端是 cdtchinesefeed（正规新闻媒体）与 qzxx_comment（无害个人号）做对照，"
    "另一端是 dajian910（犯罪软件外包）、syfhhbd（招嫖）等直接犯罪服务；中间是内容/机场/搜索三类灰产。"
    "内容号看 ERR，ERR 塌了就只剩灰产广告一条路；搜索平台不生产内容、只卖结果页广告位，毛利最好；"
    "机场生态是完整产业链；而犯罪服务类已非灰色地带，是刑事犯罪本身。"
    "一个反直觉的点：扩散力最强的是刚需内容——免费翻墙节点号 jichangdl 历史单帖转发上千（均值约 790/帖），"
    "招嫖『探店点评』号 guonrsgc（约 105 次/帖）、syfhhbd（约 95 次/帖）次之，都与内容合法性无关。"
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
    "syfhhbd 为线下性交易招嫖引流号，含从业者照片/化名/价位等人身识别信息，其原始 dump 已删除、报告只留聚合指标。"
    "dajian910 明列 CVV 钓鱼/远控等犯罪软件承接项目。"
    "Aichengrenyulan 为 AI 生成成人短剧并承接『私人定制换脸』（可能涉真人肖像、且有生成未成年形象的固有红线风险），"
    "已被 Telegram 官方按色情封禁 iOS 端，原始 dump 已删除、只留聚合指标。"
    "这些原始文案、人身信息与落地域名不适合在任何界面原样展示。"
    "UI 不要显示 data/recon/*.jsonl 的原始消息内容。"
    "注意 cdtchinesefeed 是正规新闻媒体、qzxx_comment 是无害个人号，二者为对照组，"
    "风险性质与上述灰产/犯罪样本根本不同，UI 上不应同框标红。"
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
