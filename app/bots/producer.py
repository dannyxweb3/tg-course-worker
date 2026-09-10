"""生产 Bot：收素材 → 跑流水线 → 审核卡片 ⇄ 修订循环 → 进某个频道的队列。

只服务 OWNER_ID 一个人，所有 handler 都带 owner 过滤。
"""
from __future__ import annotations

import html
import logging

from aiogram import Bot, F, Router
from aiogram.filters import Command, CommandStart
from aiogram.filters.callback_data import CallbackData
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app import db, scheduler
from app.ingest.mediagroup import MediaGroupCollector
from app.ingest.router import IngestError, build_item
from app.llm import pipeline
from app.models import Draft, ItemStatus, Level
from app.render import compose_post, split_html
from app.utils import alerts
from config.settings import settings

log = logging.getLogger(__name__)

router = Router(name="producer")
router.message.filter(F.from_user.id == settings.owner_id)
router.callback_query.filter(F.from_user.id == settings.owner_id)

HELP = (
    "<b>内容生产机</b>\n\n"
    "直接把素材丢给我就行：\n"
    "• 文字 / 链接\n"
    "• .md / .txt / .pdf 文件\n"
    "• 从别的群或频道转发的消息\n\n"
    "我会判断它属于哪个内容方向、选处理档位、生成文案，再发审核卡片给你。\n\n"
    "命令：\n"
    "/queue 看各频道待发队列\n"
    "/channels 看频道和绑定关系\n"
    "/status 看各状态计数\n"
    "/cancel 退出当前输入状态"
)


class RV(CallbackData, prefix="rv"):
    """审核卡片回调。callback_data 上限 64 字节，只放 id，内容回库里取。"""

    action: str  # ok | pick | rev | lvl | del | ver
    item: int
    draft: int
    arg: str = ""


class Revising(StatesGroup):
    waiting_note = State()


# ---------------------------------------------------------------- 审核卡片

def _keyboard(item_id: int, draft: Draft, versions: list[int]) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    did = draft.id or 0
    kb.button(text="✅ 通过", callback_data=RV(action="ok", item=item_id, draft=did))
    kb.button(text="✏️ 提建议", callback_data=RV(action="rev", item=item_id, draft=did))
    kb.button(text="🗑️ 丢弃", callback_data=RV(action="del", item=item_id, draft=did))

    for lv in (Level.P0, Level.P1, Level.P2):
        mark = "▪️" if lv is draft.level else "🔁"
        kb.button(
            text=f"{mark} {lv.label}",
            callback_data=RV(action="lvl", item=item_id, draft=did, arg=str(lv)),
        )

    other = [v for v in versions if v != did][-4:]
    for idx, vid in enumerate(other, start=1):
        kb.button(
            text=f"v{idx}",
            callback_data=RV(action="ver", item=item_id, draft=did, arg=str(vid)),
        )

    kb.adjust(3, 3, 4)
    return kb.as_markup()


async def send_review(bot: Bot, item_id: int, draft: Draft) -> None:
    """先发"所见即所发"的预览，再发一条控制面板。"""
    post = compose_post(
        title=draft.title, tldr=draft.tldr, body_html=draft.body_html,
        tags=draft.tags, attribution=draft.attribution,
    )
    chunks = split_html(post)
    for chunk in chunks:
        await bot.send_message(
            settings.owner_id, chunk, parse_mode="HTML",
            disable_web_page_preview=True,
        )

    item = await db.get_item(item_id)
    vertical = None
    if item and item["vertical_id"]:
        vertical = await db.get_vertical(int(item["vertical_id"]))

    versions = await db.draft_ids(item_id)
    head = f"—— #{item_id} v{draft.version} · {draft.level.label} · {draft.char_count} 字符"
    if vertical is not None:
        head += f" · 方向「{vertical['name']}」"
    meta = [head]
    if len(chunks) > 1:
        meta.append(f"⚠️ 超长，发布时会拆成 {len(chunks)} 条")
    if draft.note:
        meta.append(f"📝 模型备注：{html.escape(draft.note)}")

    await bot.send_message(
        settings.owner_id,
        "\n".join(meta),
        parse_mode="HTML",
        reply_markup=_keyboard(item_id, draft, versions),
    )


def _no_draft_keyboard(item_id: int) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for lv in (Level.P0, Level.P1, Level.P2):
        kb.button(
            text=f"🔁 {lv.label}",
            callback_data=RV(action="lvl", item=item_id, draft=0, arg=str(lv)),
        )
    kb.button(text="🗑️ 丢弃", callback_data=RV(action="del", item=item_id, draft=0))
    kb.adjust(3, 1)
    return kb.as_markup()


# ---------------------------------------------------------------- 流水线

async def _run_pipeline(bot: Bot, item_id: int, force_level: Level | None = None) -> None:
    item = await db.get_item(item_id)
    if item is None:
        return

    tip = await bot.send_message(settings.owner_id, "⏳ 分析中…")
    try:
        if force_level is None:
            routing = await pipeline.classify(item)
            await db.set_classification(
                item_id,
                vertical_id=routing.vertical_id,
                relevance=routing.relevance,
                tags=routing.tags,
                level=str(routing.level),
                reason=routing.reason,
                scores=routing.scores,
            )
            score_line = " · ".join(f"{k} {v}" for k, v in routing.scores.items())
            await tip.edit_text(
                f"方向「{routing.vertical_name or '无匹配'}」"
                f" · 相关性 {routing.relevance}/10 · 建议 {routing.level.label}\n"
                f"<i>{html.escape(routing.reason)}</i>\n"
                f"<code>{html.escape(score_line)}</code>",
                parse_mode="HTML",
            )
            if routing.level is Level.P3:
                await bot.send_message(
                    settings.owner_id,
                    f"—— #{item_id} 哪个方向都不沾边。要强行处理就点下面的档位。",
                    reply_markup=_no_draft_keyboard(item_id),
                )
                return
            level = routing.level
        else:
            level = force_level
            await tip.edit_text(f"⏳ 按 {level.label} 重新生成…")

        item = await db.get_item(item_id)
        draft = await pipeline.generate(item, level)
        draft.id = await db.add_draft(item_id, draft)
        draft.version = len(await db.draft_ids(item_id))
        await db.update_item(item_id, status=str(ItemStatus.REVIEW))
        await tip.delete()
        await send_review(bot, item_id, draft)
    except Exception as e:
        await db.update_item(item_id, status=str(ItemStatus.FAILED))
        try:
            await tip.edit_text(f"❌ 处理失败：{html.escape(str(e)[:300])}",
                                parse_mode="HTML")
        except Exception:
            pass
        await alerts.report(f"pipeline item#{item_id}", e)


# ---------------------------------------------------------------- 摄入

async def _ingest(bot: Bot, messages: list[Message]) -> None:
    try:
        payload = await build_item(bot, messages)
    except IngestError as e:
        await bot.send_message(settings.owner_id, f"⚠️ {e}")
        return
    except Exception as e:
        await alerts.report("ingest", e)
        return

    item_id = await db.create_item(**payload)
    if item_id is None:
        await bot.send_message(settings.owner_id, "↩️ 这个链接之前收过了，跳过。")
        return
    await _run_pipeline(bot, item_id)


_collector: MediaGroupCollector | None = None


def _get_collector(bot: Bot) -> MediaGroupCollector:
    global _collector
    if _collector is None:
        async def on_ready(messages: list[Message]) -> None:
            await _ingest(bot, messages)

        _collector = MediaGroupCollector(on_ready)
    return _collector


# ---------------------------------------------------------------- 命令

@router.message(CommandStart())
async def cmd_start(message: Message) -> None:
    await message.answer(HELP, parse_mode="HTML")


@router.message(Command("cancel"))
async def cmd_cancel(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer("已退出输入状态。")


@router.message(Command("queue"))
async def cmd_queue(message: Message) -> None:
    rows = await db.queue_list()
    if not rows:
        await message.answer("所有频道的待发队列都是空的。")
        return
    lines: list[str] = []
    current = None
    for r in rows:
        if r["channel_name"] != current:
            current = r["channel_name"]
            lines.append(f"\n<b>{html.escape(current)}</b>")
        pin = f" 📌{r['pin_date']}" if r["pin_date"] else ""
        lines.append(
            f"  #{r['item_id']} [{r['level']}]{pin} {html.escape(r['title'])}"
        )
    await message.answer("<b>待发队列</b>\n" + "\n".join(lines), parse_mode="HTML")


@router.message(Command("channels"))
async def cmd_channels(message: Message) -> None:
    rows = await db.channels_overview()
    if not rows:
        await message.answer("还没有配置频道。去后台加一个。")
        return
    dot = {"ok": "🟢", "error": "🔴"}
    lines = ["<b>频道</b>"]
    for c in rows:
        mark = dot.get(c["health_status"], "⚪")
        state = "" if c["is_active"] else "（已停用）"
        lines.append(
            f"\n{mark} <b>{html.escape(c['name'])}</b>{state}\n"
            f"  方向 {html.escape(c['vertical_name'] or '未设置')}\n"
            f"  发布 @{c['publisher_username'] or '?'}"
            f" · 售卖 @{c['sale_username'] or '—'}\n"
            f"  排期 {html.escape(c['publish_cron'])} · 队列 {c['queue_size']} 条"
        )
        if c["health_status"] == "error":
            lines.append(f"  ⚠️ {html.escape(c['health_detail'])}")
    await message.answer("\n".join(lines), parse_mode="HTML")


@router.message(Command("status"))
async def cmd_status(message: Message) -> None:
    counts = await db.counts_by_status()
    lines = ["<b>各状态计数</b>"]
    lines += [f"{k}: {v}" for k, v in sorted(counts.items())]
    lines.append(f"\n队列总长：{await db.queue_size()}")
    await message.answer("\n".join(lines), parse_mode="HTML")


# ---------------------------------------------------------------- 修订输入

@router.message(Revising.waiting_note, F.text)
async def on_revise_note(message: Message, state: FSMContext, bot: Bot) -> None:
    data = await state.get_data()
    await state.clear()
    item_id, draft_id = data["item_id"], data["draft_id"]
    note = (message.text or "").strip()

    item = await db.get_item(item_id)
    previous = await db.get_draft(draft_id)
    if item is None or previous is None:
        await message.answer("找不到这份草稿了。")
        return

    tip = await message.answer("⏳ 按你的意见重写…")
    try:
        draft = await pipeline.revise(item, previous, note)
        draft.id = await db.add_draft(item_id, draft)
        draft.version = len(await db.draft_ids(item_id))
        await tip.delete()
        await send_review(bot, item_id, draft)
    except Exception as e:
        await tip.edit_text(f"❌ 重写失败：{html.escape(str(e)[:300])}",
                            parse_mode="HTML")
        await alerts.report(f"revise item#{item_id}", e)


# ---------------------------------------------------------------- 通过 / 选频道

async def _approve(query: CallbackQuery, item_id: int, draft_id: int) -> None:
    """通过审核。该方向只有一个频道就直接进队列，多个就让你挑。"""
    item = await db.get_item(item_id)
    if item is None:
        await query.answer("素材不存在", show_alert=True)
        return

    vid = int(item["vertical_id"] or 0)
    channels = await db.channels_for_vertical(vid) if vid else []
    if not channels:
        channels = await db.list_channels(active_only=True)
    if not channels:
        # 瞬时 toast 在桌面端一闪而过，容易被当成"点了没反应"。
        # 这种要动手才能解的问题，写进消息里留着。
        total = len(await db.list_channels())
        why = "还没有登记任何频道" if total == 0 else f"{total} 个频道全部处于停用状态"
        await query.message.answer(
            f"⚠️ 无法入队：{why}。\n\n"
            f"去后台 <code>{settings.web_url}/channels</code> 添加，然后回来重新点通过。\n"
            f"记得先把发布 bot 设为频道管理员并勾选「发布消息」。",
            parse_mode="HTML",
        )
        await query.answer("没有可用频道", show_alert=True)
        return

    if len(channels) == 1:
        await _enqueue_to(query, item_id, draft_id, int(channels[0]["id"]))
        return

    kb = InlineKeyboardBuilder()
    for c in channels:
        kb.button(
            text=f"📢 {c['name']}",
            callback_data=RV(action="pick", item=item_id, draft=draft_id,
                             arg=str(c["id"])),
        )
    kb.adjust(1)
    await query.message.edit_text(
        f"#{item_id} 发到哪个频道？（可以多次点，一稿多投）",
        reply_markup=kb.as_markup(),
    )
    await query.answer()


async def _enqueue_to(
    query: CallbackQuery, item_id: int, draft_id: int, channel_id: int
) -> None:
    channel = await db.get_channel(channel_id)
    if channel is None:
        await query.answer("频道不存在", show_alert=True)
        return
    await db.enqueue(item_id, channel_id, draft_id)
    size = await db.queue_size(channel_id)
    entries = await db.queue_entries_for_item(item_id)
    where = "、".join(e["channel_name"] for e in entries)

    # 「通过」只是入队，不是发布。把下一次实际推送的时间写清楚，
    # 否则很容易以为点完就该出现在频道里了。
    nxt = scheduler.next_run_for(channel_id)
    when = nxt.strftime("%m-%d %H:%M") if nxt else "未排期"
    await query.message.edit_text(
        f"✅ #{item_id} 已进「{where}」的待发队列（{channel['name']} 共 {size} 条）\n"
        f"下次自动发布：{when}　想立刻发就去后台队列页点「立即发布」"
    )
    await query.answer("已入队")


# ---------------------------------------------------------------- 回调

@router.callback_query(RV.filter())
async def on_review_action(
    query: CallbackQuery, callback_data: RV, state: FSMContext, bot: Bot
) -> None:
    action = callback_data.action
    item_id, draft_id = callback_data.item, callback_data.draft

    if action == "ok":
        await _approve(query, item_id, draft_id)

    elif action == "pick":
        await _enqueue_to(query, item_id, draft_id, int(callback_data.arg))

    elif action == "rev":
        await state.set_state(Revising.waiting_note)
        await state.update_data(item_id=item_id, draft_id=draft_id)
        await query.message.answer(
            "✏️ 直接发一段修改意见给我，比如「开头砍掉，加一个 n8n 的对比」。\n"
            "不想改了就 /cancel。"
        )
        await query.answer()

    elif action == "lvl":
        level = Level.coerce(callback_data.arg, Level.P1)
        await query.answer(f"按{level.label}重跑")
        await query.message.edit_reply_markup(reply_markup=None)
        await _run_pipeline(bot, item_id, force_level=level)

    elif action == "ver":
        target = await db.get_draft(int(callback_data.arg))
        if target is None:
            await query.answer("版本不存在", show_alert=True)
            return
        await query.answer(f"切到 v{target.version}")
        await query.message.edit_reply_markup(reply_markup=None)
        await send_review(bot, item_id, target)

    elif action == "del":
        await db.update_item(item_id, status=str(ItemStatus.DISCARDED))
        await db.remove_from_all_queues(item_id)
        await query.message.edit_text(f"🗑️ #{item_id} 已丢弃（原文仍保留在库里）")
        await query.answer("已丢弃")

    else:
        await query.answer("未知操作", show_alert=True)


# ---------------------------------------------------------------- 素材入口
# 放在最后：命令和 FSM 状态都没接住的消息才当素材处理

@router.message(F.media_group_id)
async def on_media_group(message: Message, bot: Bot) -> None:
    await _get_collector(bot).add(str(message.media_group_id), message)


@router.message(F.text | F.caption | F.document)
async def on_material(message: Message, bot: Bot) -> None:
    await _ingest(bot, [message])
