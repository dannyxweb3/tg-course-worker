"""内容侧路由：仪表盘、待发队列、素材列表与详情、改稿。"""
from __future__ import annotations

import json
import logging

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, PlainTextResponse, RedirectResponse

from app import db, publisher, scheduler, telegraph
from app.llm import pipeline
from app.models import AssetKind, Draft, ItemStatus, Level
from app.render import compose_post, sanitize, split_html
from app.web import auth
from app.web.deps import page, redirect

log = logging.getLogger(__name__)
router = APIRouter()


# ---------------------------------------------------------------- 登录

@router.get("/login", response_class=HTMLResponse)
async def login_form(request: Request):
    return page(request, "login.html")


@router.post("/login")
async def login(request: Request, password: str = Form("")):
    if not auth.password_ok(password):
        return redirect("/login", err="密码不对")
    resp = RedirectResponse("/", status_code=303)
    auth.issue(resp)
    return resp


@router.get("/logout")
async def logout():
    resp = RedirectResponse("/login", status_code=303)
    auth.clear(resp)
    return resp


@router.get("/healthz", response_class=PlainTextResponse)
async def healthz():
    return "ok"


# ---------------------------------------------------------------- 仪表盘

@router.get("/", response_class=HTMLResponse)
async def dashboard(request: Request):
    channels = await db.channels_overview()
    jobs = {j["id"]: j["next_run"] for j in scheduler.jobs_summary()}
    # sqlite3.Row 只读，转成 dict 才能挂上"下次发布时间"
    cards = []
    for ch in channels:
        d = dict(ch)
        d["next_run"] = jobs.get(f"{scheduler.PUBLISH_JOB_PREFIX}{ch['id']}", "")
        cards.append(d)

    return page(
        request, "dashboard.html",
        cards=cards,
        counts=await db.counts_by_status(),
        total_queue=await db.queue_size(),
        user_total=await db.user_count(),
        recent=await db.published_list(limit=8),
    )


# ---------------------------------------------------------------- 队列

@router.get("/queue", response_class=HTMLResponse)
async def queue_page(request: Request, channel: int = 0):
    rows = await db.queue_list(channel or None)
    grouped: dict[str, list] = {}
    for r in rows:
        grouped.setdefault(r["channel_name"], []).append(r)
    return page(
        request, "queue.html",
        grouped=grouped,
        channels=await db.list_channels(active_only=True),
        current=channel,
    )


@router.post("/queue/{item_id}/{channel_id}/move")
async def queue_move(item_id: int, channel_id: int, delta: int = Form(0)):
    entry = await db.queue_entry(item_id, channel_id)
    if entry is None:
        return redirect("/queue", err="队列里没有这条")
    await db.set_queue_fields(
        item_id, channel_id, priority=int(entry["priority"]) + int(delta)
    )
    return redirect("/queue", msg="顺序已调整")


@router.post("/queue/{item_id}/{channel_id}/pin")
async def queue_pin(item_id: int, channel_id: int, pin_date: str = Form("")):
    await db.set_queue_fields(item_id, channel_id, pin_date=pin_date.strip())
    return redirect("/queue", msg="发布日期已设置" if pin_date else "已取消指定日期")


@router.post("/queue/{item_id}/{channel_id}/remove")
async def queue_remove(item_id: int, channel_id: int):
    await db.dequeue(item_id, channel_id)
    if not await db.queue_entries_for_item(item_id):
        await db.update_item(item_id, status=str(ItemStatus.REVIEW))
    return redirect("/queue", msg="已移出队列")


@router.post("/queue/{item_id}/{channel_id}/publish")
async def queue_publish_now(item_id: int, channel_id: int):
    """立即发布，不等排期。"""
    channel = await db.get_channel(channel_id)
    entry = await db.queue_entry(item_id, channel_id)
    if channel is None or entry is None:
        return redirect("/queue", err="频道或队列条目不存在")
    try:
        msg_id = await publisher.publish_item(
            channel, item_id, int(entry["draft_id"])
        )
    except Exception as e:
        log.exception("后台立即发布失败")
        return redirect("/queue", err=f"发布失败：{e}")
    return redirect("/queue", msg=f"已发布，频道消息 {msg_id}")


# ---------------------------------------------------------------- 素材列表

@router.get("/items", response_class=HTMLResponse)
async def items_page(
    request: Request, status: str = "", vertical: int = 0, q: str = "", p: int = 1
):
    per = 20
    p = max(1, p)
    rows, total = await db.browse_items(
        status=status, vertical_id=vertical, q=q, limit=per, offset=(p - 1) * per
    )
    # 批量取资料数，别在模板里逐行查
    assets = await db.asset_counts([int(r["id"]) for r in rows])
    return page(
        request, "items.html",
        rows=rows, total=total, page_no=p, per=per, assets=assets,
        pages=max(1, (total + per - 1) // per),
        status=status, vertical=vertical, q=q,
        verticals=await db.list_verticals(),
    )


# ---------------------------------------------------------------- 素材详情

async def _detail_ctx(request: Request, item_id: int, draft_id: int = 0):
    item = await db.get_item(item_id)
    if item is None:
        return None
    drafts = await db.list_drafts(item_id)
    current = next((d for d in drafts if d.id == draft_id), None) or (
        drafts[-1] if drafts else None
    )
    vertical = None
    if item["vertical_id"]:
        vertical = await db.get_vertical(int(item["vertical_id"]))

    preview = ""
    chunk_count = 0
    if current is not None:
        preview = compose_post(
            title=current.title, tldr=current.tldr, body_html=current.body_html,
            tags=current.tags, attribution=current.attribution,
        )
        chunk_count = len(split_html(preview))

    return {
        "item": item,
        "drafts": drafts,
        "current": current,
        "vertical": vertical,
        "preview": preview,
        "chunk_count": chunk_count,
        "scores": json.loads(item["route_scores"] or "{}"),
        "tags": json.loads(item["topic_tags"] or "[]"),
        "queue_entries": await db.queue_entries_for_item(item_id),
        "published": await db.published_for_item(item_id),
        "channels": await db.list_channels(active_only=True),
        "verticals": await db.list_verticals(),
        "assets": await db.list_assets(item_id),
    }


@router.get("/items/{item_id}", response_class=HTMLResponse)
async def item_detail(request: Request, item_id: int, draft: int = 0):
    ctx = await _detail_ctx(request, item_id, draft)
    if ctx is None:
        return redirect("/items", err="素材不存在")
    return page(request, "item_detail.html", **ctx)


@router.post("/items/{item_id}/draft/{draft_id}/save")
async def draft_save(
    item_id: int,
    draft_id: int,
    title: str = Form(""),
    tldr: str = Form(""),
    body_html: str = Form(""),
    tags: str = Form(""),
    attribution: str = Form(""),
    mode: str = Form("inplace"),
):
    """保存改稿。

    inplace = 覆盖当前版本；fork = 另存为新版本（保留历史）。
    默认覆盖：手工编辑往往要连着改好几轮，每次都开新版本会把版本列表刷爆。
    """
    existing = await db.get_draft(draft_id)
    if existing is None:
        return redirect(f"/items/{item_id}", err="草稿不存在")

    tag_list = [t.strip() for t in tags.replace("，", ",").split(",") if t.strip()]
    clean_body = sanitize(body_html)

    if mode == "fork":
        new = Draft(
            title=title.strip(), tldr=tldr.strip(), body_html=clean_body,
            tags=tag_list, attribution=attribution.strip(),
            level=existing.level, channel_id=existing.channel_id,
            revise_note="后台手工编辑",
        )
        new_id = await db.add_draft(item_id, new, edited_by="human")
        return redirect(
            f"/items/{item_id}?draft={new_id}", msg="已另存为新版本"
        )

    await db.update_draft(
        draft_id,
        title=title.strip(), tldr=tldr.strip(), body_html=clean_body,
        tags=tag_list, attribution=attribution.strip(), edited_by="human",
    )
    return redirect(f"/items/{item_id}?draft={draft_id}", msg="已保存")


@router.post("/items/{item_id}/regenerate")
async def regenerate(item_id: int, level: str = Form("P1")):
    item = await db.get_item(item_id)
    if item is None:
        return redirect("/items", err="素材不存在")
    lvl = Level.coerce(level, Level.P1)
    try:
        draft = await pipeline.generate(item, lvl)
        new_id = await db.add_draft(item_id, draft)
    except Exception as e:
        log.exception("后台重新生成失败")
        return redirect(f"/items/{item_id}", err=f"生成失败：{e}")
    await db.update_item(item_id, status=str(ItemStatus.REVIEW))
    return redirect(f"/items/{item_id}?draft={new_id}", msg=f"已按{lvl.label}重新生成")


@router.post("/items/{item_id}/revise")
async def revise(item_id: int, draft_id: int = Form(0), note: str = Form("")):
    item = await db.get_item(item_id)
    previous = await db.get_draft(draft_id)
    if item is None or previous is None:
        return redirect(f"/items/{item_id}", err="草稿不存在")
    if not note.strip():
        return redirect(f"/items/{item_id}?draft={draft_id}", err="修改意见是空的")
    try:
        draft = await pipeline.revise(item, previous, note.strip())
        new_id = await db.add_draft(item_id, draft)
    except Exception as e:
        log.exception("后台修订失败")
        return redirect(f"/items/{item_id}?draft={draft_id}", err=f"重写失败：{e}")
    return redirect(f"/items/{item_id}?draft={new_id}", msg="已按意见重写")


@router.post("/items/{item_id}/reroute")
async def reroute(item_id: int, vertical_id: int = Form(0)):
    await db.update_item(item_id, vertical_id=vertical_id)
    return redirect(f"/items/{item_id}", msg="内容方向已改")


@router.post("/items/{item_id}/approve")
async def approve(item_id: int, draft_id: int = Form(0), channel_id: int = Form(0)):
    if not channel_id:
        return redirect(f"/items/{item_id}", err="没有选频道")
    channel = await db.get_channel(channel_id)
    if channel is None:
        return redirect(f"/items/{item_id}", err="频道不存在")
    await db.enqueue(item_id, channel_id, draft_id)
    return redirect(f"/items/{item_id}", msg=f"已进「{channel['name']}」队列")


@router.post("/items/{item_id}/discard")
async def discard(item_id: int):
    await db.update_item(item_id, status=str(ItemStatus.DISCARDED))
    await db.remove_from_all_queues(item_id)
    return redirect(f"/items/{item_id}", msg="已丢弃（原文仍保留）")


@router.post("/items/{item_id}/restore")
async def restore(item_id: int):
    await db.update_item(item_id, status=str(ItemStatus.REVIEW))
    return redirect(f"/items/{item_id}", msg="已恢复为待审核")


# ---------------------------------------------------------------- 配套资料

@router.post("/items/{item_id}/assets/new")
async def asset_new(
    item_id: int,
    kind: str = Form("link"),
    title: str = Form(""),
    url: str = Form(""),
    passcode: str = Form(""),
    note: str = Form(""),
):
    if not title.strip():
        return redirect(f"/items/{item_id}", err="资料名称必填")
    url = url.strip()
    if not url:
        return redirect(f"/items/{item_id}", err="链接必填")
    if not url.startswith(("http://", "https://", "tg://")):
        return redirect(f"/items/{item_id}", err="链接要以 http(s):// 开头")
    try:
        AssetKind(kind)
    except ValueError:
        return redirect(f"/items/{item_id}", err="资料类型不对")

    await db.create_asset(
        item_id, kind=kind, title=title.strip(), url=url,
        passcode=passcode.strip(), note=note.strip(),
    )
    return redirect(f"/items/{item_id}", msg="资料已添加，发布时会挂上按钮")


@router.post("/items/{item_id}/assets/{asset_id}/save")
async def asset_save(
    item_id: int,
    asset_id: int,
    kind: str = Form("link"),
    title: str = Form(""),
    url: str = Form(""),
    passcode: str = Form(""),
    note: str = Form(""),
    sort: int = Form(0),
):
    if kind == AssetKind.VAULT:
        # 仓库行的表单里没有 url / passcode / note 字段，
        # 一并写回去会把它们抹成空串
        await db.update_asset(asset_id, title=title.strip(), sort=sort)
    else:
        await db.update_asset(
            asset_id, kind=kind, title=title.strip(), url=url.strip(),
            passcode=passcode.strip(), note=note.strip(), sort=sort,
        )
    return redirect(f"/items/{item_id}", msg="资料已保存")


async def _byline(item_id: int):
    """全文页的署名：优先用这条素材实际投递的频道，否则拿第一个活跃频道。"""
    rows = await db.published_for_item(item_id) or await db.queue_entries_for_item(item_id)
    channel = None
    if rows:
        channel = await db.get_channel(int(rows[0]["channel_id"]))
    if channel is None:
        actives = await db.list_channels(active_only=True)
        channel = actives[0] if actives else None
    if channel is None:
        return "", ""
    url = f"https://t.me/{channel['username']}" if channel["username"] else ""
    return channel["name"], url


@router.post("/items/{item_id}/fulltext")
async def make_fulltext(item_id: int, source: str = Form("raw"), draft_id: int = Form(0)):
    """把完整内容推成 Telegraph 页，存成 fulltext 资料。

    已经有全文页就改那一页，不新建——链接可能已经发给读者了。
    """
    item = await db.get_item(item_id)
    if item is None:
        return redirect("/items", err="素材不存在")

    author_name, author_url = await _byline(item_id)
    src_url = item["source_url"] or item["source_link"]

    if source == "draft":
        draft = await db.get_draft(draft_id) or await db.latest_draft(item_id)
        if draft is None:
            return redirect(f"/items/{item_id}", err="还没有草稿可发")
        title = draft.title
        body = telegraph.html_to_nodes(draft.body_html)
    else:
        draft = await db.latest_draft(item_id)
        title = (draft.title if draft else "") or item["source_title"] or f"素材 #{item_id}"
        body = telegraph.text_to_nodes(item["raw_text"])

    if not body:
        return redirect(f"/items/{item_id}", err="内容是空的，没什么可发")

    # 页首交代出处。转载他人内容做全文页，这一条不能省。
    head: list = []
    if item["source_title"] or src_url:
        bits: list = ["原文："]
        if src_url:
            bits.append({"tag": "a", "attrs": {"href": src_url},
                         "children": [item["source_title"] or src_url]})
        else:
            bits.append(item["source_title"])
        head.append({"tag": "aside", "children": bits})

    existing = next(
        (a for a in await db.list_assets(item_id) if a["kind"] == AssetKind.FULLTEXT),
        None,
    )
    try:
        url, truncated = await telegraph.publish(
            title=title, nodes=head + body,
            author_name=author_name, author_url=author_url,
            source_url=src_url,
            edit_path=telegraph.path_of(existing["url"]) if existing else "",
        )
    except Exception as e:
        log.exception("Telegraph 发布失败")
        return redirect(f"/items/{item_id}", err=f"全文页生成失败：{e}")

    label = "全文（素材原文）" if source == "raw" else "全文（本频道版本）"
    if existing:
        await db.update_asset(int(existing["id"]), url=url, title=label)
        tip = "全文页已更新（链接不变）"
    else:
        await db.create_asset(
            item_id, kind=str(AssetKind.FULLTEXT), title=label, url=url,
            note="Instant View 全文", sort=-10,
        )
        tip = "全文页已生成，并挂成配套资料"
    if truncated:
        tip += "　⚠️ 内容超出 Telegraph 上限，页尾已标注为节选"
    return redirect(f"/items/{item_id}", msg=tip)


@router.post("/items/{item_id}/repin")
async def repin(item_id: int):
    """给已发布的帖子补挂「获取完整资料」按钮。"""
    ok, errs = await publisher.attach_button(item_id)
    if ok and not errs:
        return redirect(f"/items/{item_id}", msg=f"已给 {ok} 条帖子补挂按钮")
    if ok:
        return redirect(f"/items/{item_id}",
                        msg=f"{ok} 条成功；失败：{'；'.join(errs)}")
    return redirect(f"/items/{item_id}", err="；".join(errs) or "没有可补挂的帖子")


@router.post("/items/{item_id}/assets/{asset_id}/delete")
async def asset_delete(item_id: int, asset_id: int):
    await db.delete_asset(asset_id)
    left = await db.asset_count(item_id)
    tip = "资料已删除"
    if not left:
        tip += "——这条已经没有配套资料了，再发布不会挂按钮"
    return redirect(f"/items/{item_id}", msg=tip)


# ---------------------------------------------------------------- 预览接口

@router.post("/api/preview", response_class=HTMLResponse)
async def api_preview(
    title: str = Form(""),
    tldr: str = Form(""),
    body_html: str = Form(""),
    tags: str = Form(""),
    attribution: str = Form(""),
):
    """编辑器右侧的实时预览。走的是发布时同一套 compose + sanitize + split，
    所见即所发。
    """
    tag_list = [t.strip() for t in tags.replace("，", ",").split(",") if t.strip()]
    post = compose_post(
        title=title, tldr=tldr, body_html=body_html,
        tags=tag_list, attribution=attribution,
    )
    chunks = split_html(post)
    parts = [
        f'<div class="tg-bubble">{c}</div>' for c in chunks
    ]
    warn = ""
    if len(chunks) > 1:
        warn = f'<p class="warn">⚠️ 超过 4096 字符，发布时会拆成 {len(chunks)} 条</p>'
    return HTMLResponse(
        f'{warn}{"".join(parts)}'
        f'<p class="meta">正文 {len(post)} 字符</p>'
    )


# ---------------------------------------------------------------- 已发布

@router.get("/published", response_class=HTMLResponse)
async def published_page(request: Request, channel: int = 0):
    return page(
        request, "published.html",
        rows=await db.published_list(channel or None, limit=100),
        channels=await db.list_channels(),
        current=channel,
    )
