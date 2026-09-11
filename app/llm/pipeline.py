"""内容流水线：路由分类 → 生成 → 修订。

prompt 全部从 config/prompts/ 读，改文案风格不用改代码。
每个内容方向可以在后台覆盖自己的 style_prompt，为空则回落到 system_style.md。
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from functools import lru_cache

from app import db
from app.llm.base import LLMError
from app.llm.deepseek import get_provider
from app.models import Draft, Level
from app.render import BODY_SOFT_LIMIT, sanitize
from config.settings import PROMPT_DIR, settings

log = logging.getLogger(__name__)

# 素材过长时截断后再喂给模型，控制 token 成本
MAX_RAW_CHARS = 24000


@lru_cache(maxsize=32)
def _prompt(name: str) -> str:
    return (PROMPT_DIR / f"{name}.md").read_text(encoding="utf-8")


def _base_style() -> str:
    return _prompt("system_style")


def _style_for(vertical_row) -> str:
    """方向自定义调性优先，没填就用全局的。"""
    if vertical_row is not None and (vertical_row["style_prompt"] or "").strip():
        return vertical_row["style_prompt"]
    return _base_style()


def _task(name: str) -> str:
    """生成类任务：任务模板 + 统一的输出格式说明。

    只给产出文案的任务用（P0/P1/P2/修订）。分类任务自带 JSON schema，
    再追加这一段就是两段互相矛盾的"严格输出 JSON"，模型会照着后一段答——
    分类调用返回的是一篇文案，路由结果整个丢掉。
    """
    return f"{_prompt(name)}\n\n{_prompt('_output_format')}"


def _clip(text: str) -> str:
    if len(text) <= MAX_RAW_CHARS:
        return text
    half = MAX_RAW_CHARS // 2
    return f"{text[:half]}\n\n...(中间省略)...\n\n{text[-half:]}"


def _source_block(item) -> str:
    """把素材出处也交代给模型，它才知道该怎么写归属声明。"""
    bits = []
    if item["source_title"]:
        bits.append(f"来源：{item['source_title']}")
    if item["source_url"]:
        bits.append(f"原文链接：{item['source_url']}")
    if item["source_link"]:
        bits.append(f"原消息：{item['source_link']}")
    return "\n".join(bits)


# ---------------------------------------------------------------- 分类 / 路由

@dataclass(slots=True)
class Routing:
    vertical_id: int = 0
    vertical_name: str = ""
    relevance: int = 0
    tags: list[str] = field(default_factory=list)
    level: Level = Level.P1
    reason: str = ""
    scores: dict[str, int] = field(default_factory=dict)


async def classify(item) -> Routing:
    """一次调用同时给所有方向打分并选出归属。

    多方向之后成本几乎没变——还是一次调用，只是让它多输出几个分数。
    """
    verticals = await db.list_verticals(active_only=True)
    if not verticals:
        raise LLMError("还没有配置任何内容方向，先去后台建一个")

    listing = "\n".join(
        f"- `{v['slug']}` **{v['name']}**：{v['description'] or '（未填说明）'}"
        for v in verticals
    )
    user = (
        # 用 _prompt 不用 _task：task_classify.md 自带输出 schema
        f"{_prompt('task_classify').replace('{VERTICALS}', listing)}\n\n"
        f"--- 素材出处 ---\n{_source_block(item)}\n\n"
        f"--- 素材正文 ---\n{_clip(item['raw_text'])}"
    )
    data = await get_provider().complete_json(
        system=_base_style(), user=user, model=settings.model_classify
    )

    # 分类结果必须带 scores 或 vertical。两个都没有说明模型根本没在做分类
    # （历史上就踩过：prompt 拼错，它照着生成任务的 schema 回了一篇文案），
    # 这时候宁可报错重试，也不要静默当成"哪个方向都不沾边"——
    # 那会让整批素材悄悄地没有内容方向，事后很难发现。
    if "scores" not in data and "vertical" not in data:
        raise LLMError(
            f"分类返回里没有 scores/vertical，拿到的键是 {sorted(data)[:6]}"
        )

    raw_scores = data.get("scores") or {}
    scores = {
        str(k): int(v) for k, v in raw_scores.items()
        if isinstance(v, (int, float, str)) and str(v).lstrip("-").isdigit()
    }
    by_slug = {v["slug"]: v for v in verticals}

    slug = str(data.get("vertical", "")).strip()
    if slug not in by_slug:
        # 模型没选或选了不存在的，用分数自己挑
        valid = {s: n for s, n in scores.items() if s in by_slug}
        slug = max(valid, key=valid.get) if valid else ""

    result = Routing(
        tags=[str(t) for t in (data.get("topic_tags") or [])][:4],
        level=Level.coerce(data.get("suggested_level", "P1"), Level.P1),
        reason=str(data.get("reason", ""))[:200],
        scores=scores,
    )
    if not slug:
        result.level = Level.P3
        return result

    vertical = by_slug[slug]
    result.vertical_id = int(vertical["id"])
    result.vertical_name = vertical["name"]
    result.relevance = int(data.get("relevance", scores.get(slug, 0)))

    threshold = int(vertical["relevance_threshold"] or settings.relevance_threshold)
    if result.relevance < threshold:
        result.level = Level.P3
    return result


# ---------------------------------------------------------------- 生成

_TASK_BY_LEVEL = {
    Level.P0: "task_p0_clean",
    Level.P1: "task_p1_format",
    Level.P2: "task_p2_rewrite",
}

_MODEL_BY_LEVEL = {
    Level.P0: lambda: settings.model_generate,
    Level.P1: lambda: settings.model_generate,
    Level.P2: lambda: settings.model_rewrite,  # 重写质量敏感，上更强的模型
}


def _to_draft(
    data: dict, level: Level, *, channel_id: int = 0, revise_note: str = ""
) -> Draft:
    body = sanitize(str(data.get("body_html", "")))
    if len(body) > BODY_SOFT_LIMIT * 1.3:
        log.warning("生成正文 %s 字符，超出软上限，发布时会自动分片", len(body))
    return Draft(
        title=str(data.get("title", "")).strip() or "(无标题)",
        tldr=str(data.get("tldr", "")).strip(),
        body_html=body,
        tags=[str(t) for t in (data.get("tags") or [])][:5],
        attribution=str(data.get("attribution", "")).strip(),
        note=str(data.get("note", "")).strip(),
        level=level,
        channel_id=channel_id,
        revise_note=revise_note,
    )


async def _vertical_of(item):
    vid = int(item["vertical_id"] or 0)
    return await db.get_vertical(vid) if vid else None


async def generate(item, level: Level, channel_id: int = 0) -> Draft:
    if level is Level.P3:
        raise LLMError("P3 是丢弃档位，不该走到生成")
    vertical = await _vertical_of(item)
    user = (
        f"{_task(_TASK_BY_LEVEL[level])}\n\n"
        f"--- 素材出处 ---\n{_source_block(item)}\n\n"
        f"--- 素材正文 ---\n{_clip(item['raw_text'])}"
    )
    data = await get_provider().complete_json(
        system=_style_for(vertical), user=user, model=_MODEL_BY_LEVEL[level]()
    )
    return _to_draft(data, level, channel_id=channel_id)


# ---------------------------------------------------------------- 修订

async def revise(item, previous: Draft, note: str) -> Draft:
    """带着「原素材 + 上一版 + 修改意见」重跑，产出新版本。"""
    vertical = await _vertical_of(item)
    user = (
        f"{_task('task_revise')}\n\n"
        f"--- 原始素材 ---\n{_clip(item['raw_text'])}\n\n"
        f"--- 上一版文案 ---\n"
        f"标题：{previous.title}\n"
        f"TLDR：{previous.tldr}\n"
        f"正文：\n{previous.body_html}\n\n"
        f"--- 编辑的修改意见 ---\n{note}"
    )
    data = await get_provider().complete_json(
        system=_style_for(vertical), user=user, model=settings.model_rewrite
    )
    return _to_draft(
        data, previous.level, channel_id=previous.channel_id, revise_note=note
    )
