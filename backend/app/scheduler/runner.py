"""调度器：APScheduler 统一编排周期任务

- collect_due：每分钟检查到期数据源并采集
- enrich_pending：每 5 分钟处理未富化条目
- index_pending：每 5 分钟处理未索引条目
- kg_sync：每 10 分钟同步知识图谱
- daily_report：每天 08:00 生成日报
"""
from __future__ import annotations

import asyncio

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from app.core.logging import get_logger, setup_logging

log = get_logger("scheduler")


async def job_collect() -> None:
    from app.collectors.registry import run_due_sources
    await run_due_sources()


async def job_enrich() -> None:
    from app.enrichment.pipeline import enrich_pending
    try:
        await enrich_pending(limit=40)
    except Exception as e:  # noqa: BLE001
        log.error("enrich_pending_failed", error=str(e)[:300])


async def job_index() -> None:
    from app.rag.indexer import index_pending
    try:
        await index_pending(limit=100)
    except Exception as e:  # noqa: BLE001
        log.error("index_pending_failed", error=str(e)[:300])


async def job_kg_sync() -> None:
    from app.services.kg import sync_pending
    try:
        await sync_pending(limit=200)
    except Exception as e:  # noqa: BLE001
        log.error("kg_sync_failed", error=str(e)[:300])


async def job_daily_report() -> None:
    from app.agents.analyst import generate_daily_report
    try:
        await generate_daily_report()
    except Exception as e:  # noqa: BLE001
        log.error("daily_report_failed", error=str(e)[:300])


async def job_epss_refresh() -> None:
    from app.enrichment.scorers import refresh_epss_all
    try:
        await refresh_epss_all()
    except Exception as e:  # noqa: BLE001
        log.error("epss_refresh_failed", error=str(e)[:300])


def main() -> None:
    setup_logging()
    sched = AsyncIOScheduler(timezone="Asia/Shanghai")
    sched.add_job(job_collect, IntervalTrigger(minutes=1), id="collect", max_instances=1, coalesce=True)
    sched.add_job(job_enrich, IntervalTrigger(minutes=5), id="enrich", max_instances=1, coalesce=True)
    sched.add_job(job_index, IntervalTrigger(minutes=5), id="index", max_instances=1, coalesce=True)
    sched.add_job(job_kg_sync, IntervalTrigger(minutes=10), id="kg", max_instances=1, coalesce=True)
    sched.add_job(job_daily_report, CronTrigger(hour=8, minute=0), id="daily_report")
    sched.add_job(job_epss_refresh, CronTrigger(hour="*/6"), id="epss")
    sched.start()
    log.info("scheduler_started")
    try:
        asyncio.get_event_loop().run_forever()
    except (KeyboardInterrupt, SystemExit):
        sched.shutdown()


if __name__ == "__main__":
    main()
