"""录入：后台手工加素材。

生产 bot 之外的第二个入口。三种来源——贴链接、贴文本、传文件——
都归一成一条 item，然后交给 app.intake 在后台跑分类和生成。

为什么不在请求里跑完：见 app/intake.py 开头。这里所有接口都是
"建好条目就立刻 303 回去"，进度到素材库按状态看。
"""
from __future__ import annotations

import io
import logging

from fastapi import APIRouter, File, Form, Request, UploadFile
from fastapi.responses import HTMLResponse

from app import db, intake
from app.ingest import document
from app.ingest import url as url_mod
from app.models import ItemStatus, Level, SourceType
from app.web.deps import page, redirect

log = logging.getLogger(__name__)
router = APIRouter()

# 一次提交的上限。不是性能问题，是手滑粘贴一整页链接时的刹车——
# 每条都要烧两次 LLM 调用。真要批量上百条，用 scripts/batch_ingest.py。
MAX_URLS = 30
MAX_FILES = 10


def _level_of(value: str) -> Level | None:
    """空值 = 交给分类器决定档位。"""
    if not value.strip():
        return None
    return Level.coerce(value, Level.P1)


@router.get("/ingest", response_class=HTMLResponse)
async def ingest_page(request: Request):
    # 最近录入的几条，按 id 倒序——刚提交完回到这一页能直接看见进度
    recent, _ = await db.browse_items(
        status=f"{ItemStatus.NEW},{ItemStatus.CLASSIFIED},"
               f"{ItemStatus.REVIEW},{ItemStatus.FAILED}",
        limit=8,
    )
    return page(
        request, "ingest.html",
        pending=intake.pending_count(),
        recent=recent,
        exts="、".join(sorted(document.SUPPORTED)),
        max_urls=MAX_URLS,
    )


@router.post("/ingest/url")
async def ingest_url(
    urls: str = Form(""),
    level: str = Form(""),
    make_pdf: str = Form(""),
):
    raw = [ln.strip() for ln in urls.replace(",", "\n").splitlines()]
    targets: list[str] = []
    for ln in raw:
        if not ln or ln.startswith("#"):
            continue
        if not ln.startswith(("http://", "https://")):
            return redirect("/ingest", err=f"这行不是 http(s) 链接：{ln[:60]}")
        if ln not in targets:
            targets.append(ln)

    if not targets:
        return redirect("/ingest", err="没填链接")
    if len(targets) > MAX_URLS:
        return redirect(
            "/ingest",
            err=f"一次最多 {MAX_URLS} 条，你贴了 {len(targets)} 条。"
                f"更大的批量请用 scripts/batch_ingest.py",
        )

    # 去重查询很便宜（一次索引命中），先查掉能当场给出回执，
    # 不然人要等后台跑完才发现全是收过的。
    fresh, dup = [], 0
    for t in targets:
        if await db.item_by_dedup_key(url_mod.normalize(t)) is not None:
            dup += 1
        else:
            fresh.append(t)

    lv = _level_of(level)
    for t in fresh:
        intake.submit_url(t, lv, make_pdf=bool(make_pdf))

    if not fresh:
        return redirect("/ingest", err=f"这 {dup} 条之前都收过了")
    tip = f"已提交 {len(fresh)} 条，正在后台抓取和生成"
    if dup:
        tip += f"（另有 {dup} 条之前收过，跳过）"
    return redirect("/ingest", msg=tip)


@router.post("/ingest/text")
async def ingest_text(
    text: str = Form(""),
    title: str = Form(""),
    source_url: str = Form(""),
    level: str = Form(""),
    make_pdf: str = Form(""),
):
    body = text.strip()
    if len(body) < 50:
        return redirect("/ingest", err="正文太短了（至少 50 字），这样生成不出东西")

    source_url = source_url.strip()
    if source_url and not source_url.startswith(("http://", "https://")):
        return redirect("/ingest", err="来源链接要以 http(s):// 开头")

    item_id = await db.create_item(
        source_type=str(SourceType.TEXT), raw_text=body,
        source_title=title.strip(), source_url=source_url,
    )
    if item_id is None:
        return redirect("/ingest", err="这条之前收过了")
    intake.submit_item(item_id, _level_of(level), make_pdf=bool(make_pdf))
    return redirect("/ingest", msg=f"已建 #{item_id}，正在后台生成文案")


@router.post("/ingest/file")
async def ingest_file(
    files: list[UploadFile] = File(default=[]),
    level: str = Form(""),
    make_pdf: str = Form(""),
):
    real = [f for f in files if f.filename]
    if not real:
        return redirect("/ingest", err="没选文件")
    if len(real) > MAX_FILES:
        return redirect("/ingest", err=f"一次最多 {MAX_FILES} 个文件")

    lv = _level_of(level)
    ok, errs = 0, []
    for f in real:
        name = f.filename or "untitled"
        if not document.is_supported(name):
            errs.append(f"「{name}」不支持这个格式")
            continue
        try:
            body = await document.parse(name, io.BytesIO(await f.read()))
        except ValueError as e:
            errs.append(f"「{name}」{e}")
            continue
        except Exception as e:
            log.exception("解析上传文件失败 %s", name)
            errs.append(f"「{name}」解析出错：{type(e).__name__}")
            continue

        item_id = await db.create_item(
            source_type=str(SourceType.DOCUMENT), raw_text=body,
            source_title=name,
        )
        if item_id is None:
            errs.append(f"「{name}」之前收过了")
            continue
        intake.submit_item(item_id, lv, make_pdf=bool(make_pdf))
        ok += 1

    if not ok:
        return redirect("/ingest", err="；".join(errs) or "没有可处理的文件")
    tip = f"已提交 {ok} 个文件，正在后台生成文案"
    if errs:
        tip += f"；跳过 {len(errs)} 个：{'；'.join(errs)}"
    return redirect("/ingest", msg=tip)
