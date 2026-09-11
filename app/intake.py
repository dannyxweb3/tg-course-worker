"""后台摄入队列：把「抓取 → 分类 → 生成文案」从 HTTP 请求里挪出来。

后台录入不能在请求里同步跑：一条素材要走分类和生成两次 LLM，二三十秒起步，
批量贴 20 个链接就是十来分钟，浏览器早断了。
所以录入接口只负责把条目建出来就立刻返回，真正的流水线扔到这里，
在同一个事件循环里慢慢跑，页面上按状态看进度（待分类 → 已分类 → 待审核）。

并发压到 2：DeepSeek 有限流，而且这个进程还要同时伺候 bot 轮询和定时发布。
"""
from __future__ import annotations

import asyncio
import logging

from app import db, pdfgen
from app.ingest import url as url_mod
from app.llm import pipeline
from app.models import AssetKind, ItemStatus, Level, SourceType
from app.utils import alerts
from config.settings import DATA_DIR

log = logging.getLogger(__name__)

_sem = asyncio.Semaphore(2)
# task 必须持有强引用，否则可能在跑完之前就被 GC 掉（asyncio 官方文档的坑）
_tasks: set[asyncio.Task] = set()
_pending: set[str] = set()


def pending_count() -> int:
    """还在排队或处理中的条数，给页面显示用。"""
    return len(_pending)


def _spawn(key: str, coro) -> None:
    if key in _pending:
        return
    _pending.add(key)

    async def wrapper() -> None:
        try:
            async with _sem:
                await coro
        except Exception as e:
            log.exception("后台摄入失败 %s", key)
            await alerts.report(f"后台录入 {key}", e)
        finally:
            _pending.discard(key)

    task = asyncio.create_task(wrapper())
    _tasks.add(task)
    task.add_done_callback(_tasks.discard)


def submit_item(item_id: int, level: Level | None = None,
                make_pdf: bool = False) -> None:
    """条目已经建好了，只跑后面的流水线。"""
    _spawn(f"item#{item_id}", _process(item_id, level, make_pdf))


def submit_url(target: str, level: Level | None = None,
               make_pdf: bool = False) -> None:
    """连抓取一起放到后台。抓一个页面一两秒，二十个就能把请求拖垮。"""
    _spawn(f"url:{target}", _fetch_then_process(target, level, make_pdf))


# ---------------------------------------------------------------- 内部

async def _fetch_then_process(target: str, level: Level | None,
                              make_pdf: bool) -> None:
    try:
        title, body = await url_mod.fetch(target)
    except Exception as e:
        log.warning("抓取失败 %s：%s", target, e)
        await alerts.notify(f"⚠️ 后台录入抓取失败\n{target}\n{type(e).__name__}: {e}")
        return

    item_id = await db.create_item(
        source_type=str(SourceType.URL), raw_text=body,
        source_title=title, source_url=target,
        dedup_key=url_mod.normalize(target),
    )
    if item_id is None:      # 提交那一刻还没有，跑到这里被别的入口抢先了
        return
    await _process(item_id, level, make_pdf)


async def _process(item_id: int, level: Level | None, make_pdf: bool) -> None:
    item = await db.get_item(item_id)
    if item is None:
        return

    try:
        # 即使表单里指定了档位也照样分类：内容方向决定用哪套风格 prompt，
        # 也是素材库和路由页的筛选维度。表单那个选项只覆盖档位，不跳过分类。
        routing = await pipeline.classify(item)
        await db.set_classification(
            item_id, vertical_id=routing.vertical_id,
            relevance=routing.relevance, tags=routing.tags,
            level=str(routing.level), reason=routing.reason,
            scores=routing.scores,
        )
        use = level if level is not None else routing.level
        if use is Level.P3:
            # 不自动丢弃：后台录入是人主动挑进来的，比 bot 随手转发更可能
            # 是有意为之。停在"已分类"，让人在详情页自己定档位重跑。
            return

        item = await db.get_item(item_id)
        draft = await pipeline.generate(item, use)
        draft.id = await db.add_draft(item_id, draft)
        await db.update_item(item_id, status=str(ItemStatus.REVIEW))
    except Exception:
        await db.update_item(item_id, status=str(ItemStatus.FAILED))
        raise

    if make_pdf:
        await _attach_pdf(item_id, draft)


async def _attach_pdf(item_id: int, draft) -> None:
    """PDF 挂不上不该让整条素材算失败——文案已经生成好了，人工补一次就行。"""
    item = await db.get_item(item_id)
    try:
        path = await asyncio.to_thread(pdfgen.render, draft, item)
    except Exception:
        log.exception("item#%s 生成 PDF 失败", item_id)
        return
    await db.create_asset(
        item_id, kind=str(AssetKind.VAULT), title=f"{draft.title}.pdf",
        # 用 posix 分隔符：可能在 Windows 上生成、在 Ubuntu 上读取
        url=path.relative_to(DATA_DIR).as_posix(),
        note="PDF", vault_msg_id=0, sort=-5,
    )
