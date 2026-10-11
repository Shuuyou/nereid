"""采集器注册与统一执行：run_source / run_due_sources"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone

from sqlalchemy import select

from app.collectors.base import BaseCollector
from app.collectors.feeds import (
    MsrcCollector, NvidiaPsirtCollector, PolicyCollector, RedditCollector, RssCollector,
)
from app.collectors.structured import (
    ArxivCollector, AvidCollector, CvelistCollector, ExploitDbCollector,
    GhsaCollector, HnCollector, KevCollector, NvdCollector, OsvCollector,
)
from app.core.logging import get_logger
from app.core.metrics import collection_duration, items_collected, items_merged, items_new, source_errors, source_lag
from app.db.models import Source, TaskRun
from app.db.session import get_session_factory
from app.services.ingest import ingest_items

log = get_logger("collectors.registry")

# source.name → collector 实例
COLLECTORS: dict[str, BaseCollector] = {
    "cvelistv5": CvelistCollector(),
    "nvd": NvdCollector(),
    "ghsa": GhsaCollector(),
    "osv": OsvCollector(),
    "cisa_kev": KevCollector(),
    "exploitdb": ExploitDbCollector(),
    "nvidia_psirt": NvidiaPsirtCollector(),
    "msrc": MsrcCollector(),
    "avid": AvidCollector(),
    "arxiv_cs_cr": ArxivCollector(),
    "hackernews": HnCollector(),
    "cac_policy": PolicyCollector(),
    "tc260": PolicyCollector(),
}

_rss = RssCollector()
_reddit = RedditCollector()
RSS_NAMES = [
    "hf_blog", "simonwillison", "embracethered", "msft_security_blog", "trailofbits",
    "google_project_zero", "google_security_blog", "unit42", "talos", "thehackernews",
    "bleepingcomputer", "securityaffairs", "darkreading", "schneier", "zdi",
    "freebuf", "anquanke", "seebug_paper", "nsfocus", "4hou", "aqniu", "secpulse",
    "tencent_xlab", "knownsec", "secwiki", "oss_sec", "fulldisclosure",
]
for n in RSS_NAMES:
    COLLECTORS[n] = _rss
COLLECTORS["reddit_netsec"] = _reddit

_running: set[int] = set()


async def run_source(source_id: int) -> dict:
    """执行单源采集：collector → ingest → 状态/指标更新

    三阶段事务模型：读(短事务) → 网络采集(无会话) → 写(短事务)。
    网络期不持任何 DB 事务/锁，避免长耗时外部调用饿死并发写。
    """
    if source_id in _running:
        return {"status": "skipped_running"}
    _running.add(source_id)
    started = datetime.now(timezone.utc)
    try:
        # 阶段1：短事务读 source 后 detach
        async with get_session_factory()() as db:
            source = (await db.execute(select(Source).where(Source.id == source_id))).scalar_one_or_none()
            if not source or not source.enabled:
                return {"status": "disabled"}
            db.expunge(source)
        collector = COLLECTORS.get(source.name)
        if not collector:
            raise RuntimeError(f"no collector for {source.name}")

        # 阶段2：网络采集——完全无会话
        import time as _t
        t0 = _t.time()
        collect_err: str | None = None
        items: list = []
        new_state: dict = {}
        try:
            items, new_state = await collector.collect(source)
        except Exception as e:  # noqa: BLE001
            collect_err = str(e)[:400]
        elapsed = _t.time() - t0

        # 阶段3：短事务——重附着 source + ingest + 状态写回
        async with get_session_factory()() as db:
            source = await db.merge(source)
            try:
                if collect_err:
                    raise RuntimeError(collect_err)
                stats = await ingest_items(db, source, items)
                source.state = {**(source.state or {}), **(new_state or {})}
                source.last_run_at = started
                source.last_success_at = datetime.now(timezone.utc)
                source.last_error = None
                source.consecutive_failures = 0
                stats.update({"status": "ok", "elapsed_s": round(elapsed, 1), "received": len(items),
                              "item_ids": stats.get("new_item_ids", [])[:50]})
                items_collected.labels(source=source.name).inc(len(items))
                items_new.inc(stats.get("new_items", 0))
                items_merged.inc(stats.get("merged", 0))
                collection_duration.labels(source=source.name).observe(elapsed)
                db.add(TaskRun(task_name=f"collect:{source.name}", status="success", started_at=started,
                               finished_at=datetime.now(timezone.utc), detail=stats))
                await db.commit()
                log.info("source_done", source=source.name, **stats)
                return stats
            except Exception as e:  # noqa: BLE001
                err = str(e)[:400]
                source.last_run_at = started
                source.last_error = err
                source.consecutive_failures = (source.consecutive_failures or 0) + 1
                source_errors.labels(source=source.name).set(source.consecutive_failures)
                db.add(TaskRun(task_name=f"collect:{source.name}", status="error", started_at=started,
                               finished_at=datetime.now(timezone.utc), detail={"error": err}))
                await db.commit()
                log.error("source_failed", source=source.name, error=err)
                return {"status": "error", "error": err}
    finally:
        _running.discard(source_id)


async def run_due_sources(force: bool = False) -> dict:
    """采集所有到期源（并发限流，git 型源串行）"""
    async with get_session_factory()() as db:
        sources = (await db.execute(select(Source).where(Source.enabled.is_(True)))).scalars().all()
    now = datetime.now(timezone.utc)
    due = []
    for s in sources:
        if force or not s.last_run_at or (now - s.last_run_at).total_seconds() >= (s.poll_interval_sec or 3600):
            due.append(s)
        lag = (now - s.last_run_at).total_seconds() if s.last_run_at else -1
        source_lag.labels(source=s.name).set(lag)
    git_sources = [s for s in due if s.source_type in ("cve_db", "vendor_csaf", "ai_specific")]
    rest = [s for s in due if s not in git_sources]
    sem = asyncio.Semaphore(5)

    async def guarded(sid: int):
        async with sem:
            return await run_source(sid)

    results = await asyncio.gather(*[guarded(s.id) for s in rest], return_exceptions=True)
    for s in git_sources:  # git 型源串行，避免 IO 争抢
        try:
            await run_source(s.id)
        except Exception as e:  # noqa: BLE001
            log.error("git_source_failed", source=s.name, error=str(e)[:200])
    ok = sum(1 for r in results if isinstance(r, dict) and r.get("status") == "ok")
    return {"due": len(due), "ok": ok, "errors": len(due) - ok}
