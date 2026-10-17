"""个性化推荐 API（"为你推荐"）—— prefix=/api，风格对齐 api/routes.py

- PUT  /api/profile/{name}              建/更新画像（body = profile dict）
- GET  /api/profile/{name}              取画像
- GET  /api/feed/personalized?name=&days=  个性化情报流（含 matched_entities/why/score）
- POST /api/feed/{item_id}/feedback?name=&signal=  useful|read|mute 反馈
- GET  /api/feed/digest?name=           个性化晨报（LLM 摘要，无 key 降级）
"""
from __future__ import annotations

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.db.models import Item, UserProfile
from app.db.session import get_db
from app.services import personalization as svc

log = get_logger("api.personalization")
router = APIRouter(prefix="/api", tags=["personalization"])


def _card(it: Item, **extra) -> dict:
    """情报核心字段卡片（与 routes._item_card 同契约 + 个性化字段）"""
    return {
        "id": it.id, "item_type": it.item_type, "title": it.title,
        "title_zh": it.title_zh, "summary_zh": it.summary_zh or it.summary,
        "url": it.url,
        "published_at": it.published_at.isoformat() if it.published_at else None,
        "first_seen_at": it.first_seen_at.isoformat() if it.first_seen_at else None,
        "cve_ids": it.cve_ids, "ghsa_ids": it.ghsa_ids, "cwe_ids": it.cwe_ids,
        "products": it.products, "vendors": it.vendors, "packages": it.packages,
        "severity": it.severity, "cvss_v31_score": it.cvss_v31_score,
        "epss_score": it.epss_score, "is_kev": it.is_kev, "has_poc": it.has_poc,
        "exploit_maturity": it.exploit_maturity, "priority_score": it.priority_score,
        "ai_relevance_score": it.ai_relevance_score, "ai_layer": it.ai_layer,
        "owasp_llm": it.owasp_llm, "owasp_asi": it.owasp_asi,
        "atlas_techniques": it.atlas_techniques, "attack_techniques": it.attack_techniques,
        "source_names": it.source_names, "source_count": it.source_count,
        "review_status": it.review_status,
        **extra,
    }


async def _profile_or_404(db: AsyncSession, name: str) -> UserProfile:
    row = (await db.execute(
        select(UserProfile).where(UserProfile.name == name.strip()))).scalar_one_or_none()
    if not row:
        raise HTTPException(404, "profile not found")
    return row


@router.put("/profile/{name}")
async def upsert_profile(name: str,
                         profile: dict = Body(default_factory=dict),
                         db: AsyncSession = Depends(get_db)):
    """建/更新画像（body 即 profile dict：assets/interests/severity_floor/channels）"""
    name = name.strip()
    if not name or len(name) > 64:
        raise HTTPException(400, "invalid name")
    if profile is not None and not isinstance(profile, dict):
        raise HTTPException(400, "profile must be an object")
    row = (await db.execute(
        select(UserProfile).where(UserProfile.name == name))).scalar_one_or_none()
    if row is None:
        row = UserProfile(name=name, profile=profile or {})
        db.add(row)
    else:
        row.profile = profile or {}
    await db.commit()
    return {"name": row.name, "profile": row.profile,
            "updated_at": row.updated_at.isoformat() if row.updated_at else None}


@router.get("/profile/{name}")
async def get_profile(name: str, db: AsyncSession = Depends(get_db)):
    row = await _profile_or_404(db, name)
    return {"name": row.name, "profile": row.profile,
            "updated_at": row.updated_at.isoformat() if row.updated_at else None}


@router.get("/feed/personalized")
async def personalized_feed(name: str = Query(...),
                            days: int = Query(7, ge=1, le=90),
                            limit: int = Query(50, ge=1, le=100),
                            db: AsyncSession = Depends(get_db)):
    """规则 ∪ 向量 RRF 召回 → 画像打分排序 → 带 matched_entities/why/score 的卡片"""
    prof = await _profile_or_404(db, name)
    recs = await svc.match_items(prof, db, days=days, limit=limit)
    return {"count": len(recs), "items": [
        _card(r["item"], matched_entities=r["matched_entities"], why=r["why"],
              score=r["score"], via_vector=r["via_vector"]) for r in recs]}


@router.post("/feed/{item_id}/feedback")
async def feed_feedback(item_id: str,
                        name: str = Query(...),
                        signal: str = Query(...),
                        db: AsyncSession = Depends(get_db)):
    """反馈信号：mute→画像负权重并降权/剔除；useful→正权重；read→仅记录"""
    if signal not in svc.VALID_SIGNALS:
        raise HTTPException(400, f"signal must be one of {svc.VALID_SIGNALS}")
    prof = await _profile_or_404(db, name)
    item = await db.get(Item, item_id)
    if not item:
        raise HTTPException(404, "item not found")
    return await svc.feedback(prof, item, signal, db)


@router.get("/feed/digest")
async def feed_digest(name: str = Query(...),
                      days: int = Query(7, ge=1, le=90),
                      db: AsyncSession = Depends(get_db)):
    """个性化晨报：top10 命中 → LLM 200 字中文摘要（无 key 降级列表拼接）"""
    prof = await _profile_or_404(db, name)
    return await svc.digest(prof, db, days=days)
