"""配置侧路由：bot / 内容方向 / 频道，以及关系拓扑和健康检查。"""
from __future__ import annotations

import logging
import os

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse

from app import botpool, db, health, scheduler
from app.web.deps import page, redirect

log = logging.getLogger(__name__)
router = APIRouter()


# ---------------------------------------------------------------- 拓扑

@router.get("/topology", response_class=HTMLResponse)
async def topology(request: Request):
    """Bot → 频道 → 方向 的三列关系图。

    一眼看出哪个 bot 被几个频道共用、哪个方向没有频道承接、
    哪个频道缺发布身份。
    """
    bots = [dict(b) for b in await db.list_bots()]
    verticals = [dict(v) for v in await db.list_verticals()]
    channels = [dict(c) for c in await db.channels_overview()]

    bot_idx = {b["id"]: i for i, b in enumerate(bots)}
    ver_idx = {v["id"]: i for i, v in enumerate(verticals)}

    links = []
    for i, c in enumerate(channels):
        if c["publisher_bot_id"] in bot_idx:
            links.append(("pub", bot_idx[c["publisher_bot_id"]], i))
        if c["sale_bot_id"] in bot_idx:
            links.append(("sale", bot_idx[c["sale_bot_id"]], i))
        if c["vertical_id"] in ver_idx:
            links.append(("ver", i, ver_idx[c["vertical_id"]]))

    # 孤儿检查：这几种情况会让流水线在某一步静默断掉
    orphans = []
    used_bots = {c["publisher_bot_id"] for c in channels} | {
        c["sale_bot_id"] for c in channels
    }
    for b in bots:
        if b["role"] != "producer" and b["id"] not in used_bots:
            orphans.append(f"bot「{b['name']}」没有被任何频道使用")
        if not botpool.has_token(b["token_env_key"]):
            orphans.append(
                f"bot「{b['name']}」缺 token（环境变量 {b['token_env_key']} 未设置）"
            )
    used_verticals = {c["vertical_id"] for c in channels if c["is_active"]}
    for v in verticals:
        if v["is_active"] and v["id"] not in used_verticals:
            orphans.append(f"方向「{v['name']}」没有任何频道承接，素材会积压")
    for c in channels:
        if not c["publisher_bot_id"]:
            orphans.append(f"频道「{c['name']}」没有绑定发布 bot，无法发布")

    return page(
        request, "topology.html",
        bots=bots, verticals=verticals, channels=channels,
        links=links, orphans=orphans,
    )


@router.post("/topology/check")
async def run_health_check():
    results = await health.check_all(notify_on_error=False)
    bad = [f"{n}: {d}" for n, s, d in results if s == "error"]
    if bad:
        return redirect("/topology", err="；".join(bad))
    return redirect("/topology", msg=f"{len(results)} 个频道全部正常")


# ---------------------------------------------------------------- 频道

@router.get("/channels", response_class=HTMLResponse)
async def channels_page(request: Request):
    return page(
        request, "channels.html",
        channels=await db.channels_overview(),
        bots=await db.list_bots(),
        verticals=await db.list_verticals(),
    )


@router.post("/channels/new")
async def channel_new(
    name: str = Form(""),
    chat_id: str = Form(""),
    username: str = Form(""),
    vertical_id: int = Form(0),
    publisher_bot_id: int = Form(0),
    sale_bot_id: int = Form(0),
    linked_group_id: str = Form("0"),
    publish_cron: str = Form("0 9 * * *"),
    timezone_name: str = Form("Asia/Shanghai"),
):
    if not name.strip() or not chat_id.strip():
        return redirect("/channels", err="频道名和 chat_id 必填")
    try:
        cid = int(chat_id.strip())
    except ValueError:
        return redirect("/channels", err="chat_id 必须是数字，形如 -1001234567890")

    try:
        await db.create_channel(
            name=name.strip(), chat_id=cid, username=username.strip().lstrip("@"),
            vertical_id=vertical_id, publisher_bot_id=publisher_bot_id,
            sale_bot_id=sale_bot_id or None,
            linked_group_id=int(linked_group_id or 0),
            publish_cron=publish_cron.strip(), timezone_name=timezone_name.strip(),
        )
    except Exception as e:
        return redirect("/channels", err=f"创建失败：{e}")
    await scheduler.reload()
    return redirect("/channels", msg="频道已创建，排期已生效")


@router.post("/channels/{channel_id}/save")
async def channel_save(
    channel_id: int,
    name: str = Form(""),
    username: str = Form(""),
    vertical_id: int = Form(0),
    publisher_bot_id: int = Form(0),
    sale_bot_id: int = Form(0),
    linked_group_id: str = Form("0"),
    publish_cron: str = Form("0 9 * * *"),
    timezone_name: str = Form("Asia/Shanghai"),
    is_active: str = Form(""),
):
    await db.update_channel(
        channel_id,
        name=name.strip(), username=username.strip().lstrip("@"),
        vertical_id=vertical_id, publisher_bot_id=publisher_bot_id,
        sale_bot_id=sale_bot_id or None,
        linked_group_id=int(linked_group_id or 0),
        publish_cron=publish_cron.strip(), timezone=timezone_name.strip(),
        is_active=1 if is_active else 0,
    )
    # 排期或启用状态可能变了，热重载 job，不用重启进程
    await scheduler.reload()
    return redirect("/channels", msg="已保存，排期已重载")


@router.post("/channels/{channel_id}/delete")
async def channel_delete(channel_id: int):
    if await db.queue_size(channel_id):
        return redirect("/channels", err="队列里还有待发内容，先清空再删")
    await db.delete_channel(channel_id)
    await scheduler.reload()
    return redirect("/channels", msg="频道已删除")


# ---------------------------------------------------------------- 内容方向

@router.get("/verticals", response_class=HTMLResponse)
async def verticals_page(request: Request):
    rows = []
    for v in await db.list_verticals():
        d = dict(v)
        d["channels"] = await db.channels_for_vertical(int(v["id"]))
        rows.append(d)
    return page(request, "verticals.html", rows=rows)


@router.post("/verticals/new")
async def vertical_new(
    name: str = Form(""),
    slug: str = Form(""),
    description: str = Form(""),
    relevance_threshold: int = Form(5),
):
    if not name.strip() or not slug.strip():
        return redirect("/verticals", err="名称和 slug 必填")
    try:
        await db.create_vertical(
            name=name.strip(), slug=slug.strip(),
            description=description.strip(),
            relevance_threshold=relevance_threshold,
        )
    except Exception as e:
        return redirect("/verticals", err=f"创建失败（slug 可能重复）：{e}")
    return redirect("/verticals", msg="方向已创建")


@router.post("/verticals/{vertical_id}/save")
async def vertical_save(
    vertical_id: int,
    name: str = Form(""),
    description: str = Form(""),
    style_prompt: str = Form(""),
    relevance_threshold: int = Form(5),
    is_active: str = Form(""),
):
    await db.update_vertical(
        vertical_id,
        name=name.strip(), description=description.strip(),
        style_prompt=style_prompt, relevance_threshold=relevance_threshold,
        is_active=1 if is_active else 0,
    )
    return redirect("/verticals", msg="已保存")


@router.post("/verticals/{vertical_id}/delete")
async def vertical_delete(vertical_id: int):
    if await db.channels_for_vertical(vertical_id):
        return redirect("/verticals", err="还有频道绑在这个方向上，先解绑")
    await db.delete_vertical(vertical_id)
    return redirect("/verticals", msg="方向已删除")


# ---------------------------------------------------------------- Bot

@router.get("/bots", response_class=HTMLResponse)
async def bots_page(request: Request):
    rows = []
    for b in await db.list_bots():
        d = dict(b)
        d["has_token"] = botpool.has_token(b["token_env_key"])
        rows.append(d)
    # 顺手把 .env 里已经存在、但还没建记录的 token 变量列出来做提示
    known = {b["token_env_key"] for b in rows}
    candidates = [
        k for k in os.environ
        if ("BOT" in k.upper() and "TOKEN" in k.upper() or k.startswith("BOT_"))
        and k not in known and os.environ[k].strip()
    ]
    return page(request, "bots.html", rows=rows, candidates=sorted(candidates))


@router.post("/bots/new")
async def bot_new(
    name: str = Form(""), role: str = Form("publisher"),
    token_env_key: str = Form(""),
):
    if not name.strip() or not token_env_key.strip():
        return redirect("/bots", err="名称和 token 变量名必填")
    key = token_env_key.strip()
    if not botpool.has_token(key):
        return redirect(
            "/bots", err=f"环境变量 {key} 还没设置，先去 .env 里加一行再重启进程"
        )
    try:
        bot_id = await db.create_bot(
            name=name.strip(), role=role, token_env_key=key
        )
    except Exception as e:
        return redirect("/bots", err=f"创建失败（名称可能重复）：{e}")
    try:
        bot = await botpool.get(bot_id)
        me = await bot.get_me()
        await db.update_bot(bot_id, username=me.username or "")
    except Exception as e:
        return redirect("/bots", err=f"记录已建，但 token 校验失败：{e}")
    return redirect("/bots", msg=f"已添加 @{me.username}")


@router.post("/bots/{bot_id}/save")
async def bot_save(
    bot_id: int, name: str = Form(""), role: str = Form("publisher"),
    token_env_key: str = Form(""), is_active: str = Form(""),
):
    await db.update_bot(
        bot_id, name=name.strip(), role=role,
        token_env_key=token_env_key.strip(), is_active=1 if is_active else 0,
    )
    botpool.drop(bot_id)  # token 可能换了，让缓存失效
    return redirect("/bots", msg="已保存")


@router.post("/bots/{bot_id}/delete")
async def bot_delete(bot_id: int):
    for c in await db.list_channels():
        if bot_id in (c["publisher_bot_id"], c["sale_bot_id"]):
            return redirect("/bots", err=f"频道「{c['name']}」还在用这个 bot")
    botpool.drop(bot_id)
    await db.delete_bot(bot_id)
    return redirect("/bots", msg="已删除")
