"""SecAgent FastAPI 主程序"""
from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from starlette.responses import Response

from app.api.routes import router
from app.core import metrics as _metrics  # noqa: F401 注册全部自定义指标
from app.core.logging import get_logger, setup_logging
from app.db.session import init_db

log = get_logger("main")


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging()
    log.info("secagent_starting")
    await init_db()
    # 源注册
    try:
        from app.collectors.seeds import SEED_SOURCES
        from app.db.models import Source
        from app.db.session import get_session_factory
        async with get_session_factory()() as db:
            from sqlalchemy import select
            existing = {r[0] for r in (await db.execute(select(Source.name))).all()}
            for s in SEED_SOURCES:
                if s["name"] not in existing:
                    db.add(Source(**s))
            await db.commit()
        log.info("sources_seeded", count=len(SEED_SOURCES))
    except Exception as e:  # noqa: BLE001
        log.error("seed_sources_failed", error=str(e))
    # Qdrant 集合
    try:
        from app.rag.qdrant import ensure_collection
        await ensure_collection()
    except Exception as e:  # noqa: BLE001
        log.warning("qdrant_init_skipped", error=str(e)[:200])
    # Neo4j schema
    try:
        from app.services.kg import init_schema
        await init_schema()
    except Exception as e:  # noqa: BLE001
        log.warning("neo4j_init_skipped", error=str(e)[:200])
    # Embedding 预热（后台线程，不阻塞启动）
    asyncio.get_event_loop().run_in_executor(None, _warmup)
    yield
    log.info("secagent_stopped")


def _warmup() -> None:
    try:
        from app.core.embeddings import warmup
        warmup()
    except Exception as e:  # noqa: BLE001
        log.warning("embedding_warmup_failed", error=str(e)[:200])


app = FastAPI(title="SecAgent", version="0.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], allow_credentials=False,
    allow_methods=["*"], allow_headers=["*"],
)
app.include_router(router)


@app.get("/metrics")
async def metrics():
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)


@app.get("/")
async def root():
    return {"name": "SecAgent", "docs": "/docs"}
