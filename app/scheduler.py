"""定时任务：每个频道一个发布 job，外加队列低水位提醒和健康检查。

时区必须显式指定，不能吃系统默认——服务器很可能是 UTC，本地是 +08:00，
不写死就会在两边表现不一致。每个频道还能有自己的时区。

后台改了频道排期要能热重载，不能要求重启进程 —— 见 reload()。
"""
from __future__ import annotations

import logging
from zoneinfo import ZoneInfo

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from app import db, health, publisher
from app.utils import alerts
from config.settings import settings

log = logging.getLogger(__name__)

_sched: AsyncIOScheduler | None = None

PUBLISH_JOB_PREFIX = "publish_ch_"


async def _publish(channel_id: int) -> None:
    try:
        await publisher.publish_next(channel_id)
    except Exception as e:
        await alerts.report(f"daily_publish channel#{channel_id}", e)


async def _queue_watch() -> None:
    """低水位提醒。没有这一条，某天早上频道就悄无声息地断更了。"""
    try:
        low: list[str] = []
        for ch in await db.list_channels(active_only=True):
            size = await db.queue_size(int(ch["id"]))
            if size <= settings.queue_low_watermark:
                low.append(f"• 「{ch['name']}」只剩 {size} 条")
        if low:
            await alerts.notify("🔔 <b>待发队列告急</b>\n" + "\n".join(low))
    except Exception as e:
        await alerts.report("queue_watch", e)


async def _health_check() -> None:
    try:
        await health.check_all()
    except Exception as e:
        await alerts.report("health_check", e)


async def reload() -> None:
    """按库里的频道配置重建发布 job。

    后台改完排期直接调这个，不用重启进程。已停用或已删除的频道，
    对应的 job 会被移掉。
    """
    if _sched is None:
        return

    wanted: set[str] = set()
    for ch in await db.list_channels(active_only=True):
        cid = int(ch["id"])
        job_id = f"{PUBLISH_JOB_PREFIX}{cid}"
        cron = (ch["publish_cron"] or settings.default_publish_cron).strip()
        tzname = ch["timezone"] or settings.timezone
        try:
            trigger = CronTrigger.from_crontab(cron, timezone=ZoneInfo(tzname))
        except Exception as e:
            log.error("频道「%s」的 cron 无效（%s）：%s", ch["name"], cron, e)
            await alerts.notify(
                f"⚠️ 频道「{ch['name']}」的排期表达式无效：<code>{cron}</code>，"
                f"该频道不会自动发布。"
            )
            continue

        _sched.add_job(
            _publish, trigger, args=[cid], id=job_id,
            misfire_grace_time=3600,  # 进程刚重启也能把错过的那次补上
            coalesce=True, replace_existing=True,
        )
        wanted.add(job_id)
        log.info("频道「%s」排期 %s (%s)", ch["name"], cron, tzname)

    for job in _sched.get_jobs():
        if job.id.startswith(PUBLISH_JOB_PREFIX) and job.id not in wanted:
            job.remove()
            log.info("移除失效的发布 job：%s", job.id)


async def start() -> AsyncIOScheduler:
    global _sched
    _sched = AsyncIOScheduler(timezone=settings.tz)

    _sched.add_job(
        _queue_watch,
        CronTrigger(hour=20, minute=0, timezone=settings.tz),
        id="queue_watch", replace_existing=True,
    )
    _sched.add_job(
        _health_check,
        CronTrigger(hour=settings.health_check_hour, minute=0, timezone=settings.tz),
        id="health_check", replace_existing=True,
    )

    await reload()
    _sched.start()
    return _sched


def shutdown() -> None:
    if _sched is not None:
        _sched.shutdown(wait=False)


def next_run_for(channel_id: int):
    """某个频道下一次自动发布的时间，没排上返回 None。"""
    if _sched is None:
        return None
    job = _sched.get_job(f"{PUBLISH_JOB_PREFIX}{channel_id}")
    return getattr(job, "next_run_time", None) if job else None


def jobs_summary() -> list[dict]:
    """后台仪表盘用：下一次各频道什么时候发。"""
    if _sched is None:
        return []
    out = []
    for job in _sched.get_jobs():
        nxt = getattr(job, "next_run_time", None)
        out.append({
            "id": job.id,
            "next_run": nxt.isoformat() if nxt else "",
        })
    return out
