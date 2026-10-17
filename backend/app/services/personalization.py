"""个性化情报推荐服务（"为你推荐"）

管线：规则召回（实体 overlap ∪ 分类匹配 ∪ 关键词 ilike，severity_floor 过滤）
    ∪ 向量召回（画像文本 → embedder → qdrant hybrid_search top30）
    → RRF 合并候选 → score() 加权打分 → 中文 why → top-N

反馈：useful/read 记正信号、mute 写入画像 negative 负权重；
digest：top10 命中 → llm_text 生成中文晨报（无 key 降级为列表拼接）。
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.db.models import FeedFeedback, Item, UserProfile

log = get_logger("services.personalization")

VALID_SIGNALS = ("useful", "read", "mute")
SEVERITY_ORDER = {"none": 0, "low": 1, "medium": 2, "high": 3, "critical": 4}
# 画像资产类型 → Item 数组列名
_ASSET_FIELD = {
    "product": "products", "package": "packages", "cpe": "cpes",
    "vendor": "vendors", "cve": "cve_ids",
}
_LAYER_NAMES = {"L1": "L1基础设施", "L2": "L2模型数据", "L3": "L3应用智能体",
                "L4": "L4供应链", "L5": "L5政策治理", "L6": "L6滥用威胁"}


def _norm(v) -> str:
    return str(v or "").strip().lower()


def _sev_rank(s: str | None) -> int:
    """none/low/medium/high/critical → 0-4；NULL 视为 none(0)"""
    return SEVERITY_ORDER.get(_norm(s) or "none", 0)


def _variants(val: str) -> list[str]:
    """实体值大小写变体（PG && 为精确匹配，库内写法不一）"""
    return list({val, val.lower(), val.upper(), val.capitalize()})


# ---------- 规则召回 ----------

async def _rule_candidates(prof: dict, db: AsyncSession, days: int,
                           limit: int = 300) -> list[Item]:
    """按画像资产/兴趣做 SQL 级规则召回（任一命中即可，排序取上限）"""
    conds = [Item.first_seen_at >= datetime.now(timezone.utc) - timedelta(days=days)]
    ors = []
    for a in prof.get("assets") or []:
        field = _ASSET_FIELD.get(_norm(a.get("type")))
        val = str(a.get("value") or "").strip()
        if not field or not val:
            continue
        ors.append(getattr(Item, field).overlap(_variants(val)))
    for it_ in prof.get("interests") or []:
        t, v = _norm(it_.get("type")), str(it_.get("value") or "").strip()
        if not v:
            continue
        if t == "layer":
            ors.append(Item.ai_layer.in_(_variants(v)))
        elif t == "owasp":
            ors.append(or_(Item.owasp_llm.overlap(_variants(v)),
                           Item.owasp_asi.overlap(_variants(v))))
        elif t == "technique":
            ors.append(or_(Item.atlas_techniques.overlap(_variants(v)),
                           Item.attack_techniques.overlap(_variants(v))))
        elif t == "keyword":
            like = f"%{v}%"
            ors.append(or_(Item.title.ilike(like), Item.title_zh.ilike(like),
                           Item.summary.ilike(like), Item.summary_zh.ilike(like)))
    if not ors:
        return []
    conds.append(or_(*ors))
    floor = _sev_rank(prof.get("severity_floor"))
    if floor > 0:  # floor=none 不过滤；>0 时 severity 为空/低于下限的一律排除
        conds.append(Item.severity.in_([s for s, r in SEVERITY_ORDER.items() if r >= floor]))
    rows = (await db.execute(
        select(Item).where(*conds)
        .order_by(Item.is_kev.desc(), Item.priority_score.desc().nullslast(),
                  Item.first_seen_at.desc())
        .limit(limit))).scalars().all()
    return list(rows)


def _match_item(item: Item, prof: dict) -> dict:
    """Python 级精确命中明细 → matched_entities / why 的依据"""
    hits: dict[str, list] = {"assets": [], "interests": []}
    text = " ".join(filter(None, [item.title, item.title_zh, item.summary, item.summary_zh])).lower()
    for a in prof.get("assets") or []:
        field = _ASSET_FIELD.get(_norm(a.get("type")))
        val = _norm(a.get("value"))
        if not field or not val:
            continue
        stored = {_norm(x) for x in (getattr(item, field) or [])}
        if val in stored or val in text:  # 数组 overlap 为主，标题/摘要命中兜底
            hits["assets"].append({"type": a.get("type"), "value": a.get("value")})
    for i_ in prof.get("interests") or []:
        t, raw = _norm(i_.get("type")), str(i_.get("value") or "").strip()
        v = _norm(raw)
        if not v:
            continue
        hit = False
        if t == "layer":
            hit = _norm(item.ai_layer) == v
        elif t == "owasp":
            hit = v.upper() in ({x.upper() for x in (item.owasp_llm or [])}
                                | {x.upper() for x in (item.owasp_asi or [])})
        elif t == "technique":
            hit = v.upper() in ({x.upper() for x in (item.atlas_techniques or [])}
                                | {x.upper() for x in (item.attack_techniques or [])})
        elif t == "keyword":
            hit = v in text
        if hit:
            hits["interests"].append({"type": i_.get("type"), "value": raw})
    return hits


# ---------- 打分与理由 ----------

def score(item: Item, matched: dict) -> float:
    """0.45*实体命中强度 + 0.25*min(priority,5)/5 + 0.15*(kev|poc) + 0.10*epss + 0.05*recency"""
    n = len(matched.get("assets") or []) + len(matched.get("interests") or [])
    entity_strength = min(n / 3.0, 1.0)
    prio = min(max(item.priority_score or 0.0, 0.0), 5.0) / 5.0
    exploit = 1.0 if (item.is_kev or item.has_poc) else 0.0
    epss = min(max(item.epss_score or 0.0, 0.0), 1.0)
    ts = item.published_at or item.first_seen_at
    days_old = max((datetime.now(timezone.utc) - ts).days, 0) if ts else 30
    recency = 0.5 ** (days_old / 3.0)  # 半衰期 3 天
    s = (0.45 * entity_strength + 0.25 * prio + 0.15 * exploit
         + 0.10 * epss + 0.05 * recency)
    return round(max(min(s, 1.0), 0.0), 4)


def _why(item: Item, matched: dict, via_vector: bool) -> str:
    """中文一句推荐理由"""
    parts: list[str] = []
    if matched.get("assets"):
        parts.append("命中资产 " + "、".join(a["value"] for a in matched["assets"][:4]))
    if matched.get("interests"):
        labels = [_LAYER_NAMES.get(i["value"], i["value"]) for i in matched["interests"][:4]]
        parts.append("命中关注 " + "、".join(labels))
    if via_vector:
        parts.append("向量语义召回补强" if parts else "与画像语义相近（向量召回）")
    if item.is_kev:
        parts.append("CISA KEV 在野利用")
    if item.has_poc:
        parts.append("存在公开 PoC")
    if (item.epss_score or 0) >= 0.1:
        parts.append(f"EPSS {item.epss_score * 100:.1f}%")
    return "；".join(parts) or "画像弱相关"


# ---------- 向量召回 + RRF 合并 ----------

def _profile_text(prof: dict) -> str:
    assets = "、".join(str(a.get("value") or "") for a in prof.get("assets") or [] if a.get("value"))
    interests = "、".join(str(i.get("value") or "") for i in prof.get("interests") or [] if i.get("value"))
    if not assets and not interests:
        return ""
    return f"AI 安全威胁情报画像：关注资产 {assets}；关注方向 {interests}"


async def vector_recall(prof: dict, top_k: int = 30) -> list[dict]:
    """画像文本 → dense+sparse hybrid_search → top_k item 级命中；任何环节失败降级为空"""
    text = _profile_text(prof)
    if not text:
        return []
    try:
        from app.rag import embedder, qdrant
        dv = await embedder.embed_query(text)
        sv = (await embedder.sparse_texts([text]))[0]
        hits = await qdrant.hybrid_search(dv, sv, top_k=top_k)
        return hits or []
    except Exception as e:  # noqa: BLE001
        log.warning("vector_recall_failed", error=str(e)[:200])
        return []


async def match_items(profile: UserProfile, db: AsyncSession,
                      days: int = 7, limit: int = 50) -> list[dict]:
    """规则 ∪ 向量候选 RRF 合并 → score 排序 → [{item,matched_entities,why,score,...}]"""
    prof = profile.profile or {}
    neg = prof.get("negative") or {}
    neg_items = set(neg.get("items") or [])
    neg_entities = {_norm(e) for e in (neg.get("entities") or [])}
    pos_entities = {_norm(e) for e in ((prof.get("positive") or {}).get("entities") or [])}

    # RRF 合并两路候选（k=60）
    cand: dict[str, dict] = {}
    for rank, it in enumerate(await _rule_candidates(prof, db, days)):
        if it.id in neg_items:
            continue
        cand[it.id] = {"item": it, "rrf": 1.0 / (60 + rank + 1), "vector": False}
    for rank, h in enumerate(await vector_recall(prof, top_k=30)):
        iid = h.get("item_id")
        if not iid or iid in neg_items:
            continue
        rec = cand.setdefault(iid, {"item": None, "rrf": 0.0, "vector": True})
        rec["rrf"] += 1.0 / (60 + rank + 1)
        rec["vector"] = True

    # 仅向量命中的条目回库取全量
    missing = [iid for iid, r in cand.items() if r["item"] is None]
    if missing:
        rows = (await db.execute(select(Item).where(Item.id.in_(missing)))).scalars().all()
        by_id = {i.id: i for i in rows}
        for iid in missing:
            cand[iid]["item"] = by_id.get(iid)

    floor = _sev_rank(prof.get("severity_floor"))
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    out = []
    for r in cand.values():
        it = r["item"]
        if not it:
            continue
        if r["vector"] and not r["item"]:  # pragma: no cover
            continue
        if floor > 0 and _sev_rank(it.severity) < floor:
            continue
        # 向量召回的新条目也可能超出时间窗（payload 无 first_seen 约束），统一卡窗
        if it.first_seen_at and it.first_seen_at < cutoff:
            continue
        matched = _match_item(it, prof)
        sc = score(it, matched)
        # 负权重：命中 mute 实体降权；正权重：命中 useful 实体小幅加权
        item_entities = {_norm(x) for x in (it.products or []) + (it.vendors or [])}
        sc -= 0.15 * len(item_entities & neg_entities)
        sc += min(0.05 * len(item_entities & pos_entities), 0.15)
        out.append({
            "item": it,
            "matched_entities": matched["assets"] + matched["interests"],
            "why": _why(it, matched, r["vector"]),
            "score": round(max(sc, 0.0), 4),
            "rrf": round(r["rrf"], 5), "via_vector": r["vector"],
        })
    out.sort(key=lambda x: (x["score"], x["rrf"]), reverse=True)
    return out[:limit]


# ---------- 反馈 ----------

async def feedback(profile: UserProfile, item: Item | None,
                   signal: str, db: AsyncSession) -> dict:
    """落反馈流水 + 画像权重回写：mute→负权重；useful→正权重；read→仅流水"""
    if signal not in VALID_SIGNALS:
        raise ValueError(f"signal must be one of {VALID_SIGNALS}")
    db.add(FeedFeedback(profile_id=profile.id, item_id=item.id if item else "unknown",
                        signal=signal))
    if signal in ("mute", "useful"):
        prof = dict(profile.profile or {})
        key = "negative" if signal == "mute" else "positive"
        bucket = prof.setdefault(key, {"items": [], "entities": []} if key == "negative"
                                 else {"entities": []})
        if key == "negative" and item and item.id not in bucket["items"]:
            bucket["items"].append(item.id)
        if item:
            for v in (item.products or []) + (item.vendors or []):
                if v not in bucket["entities"]:
                    bucket["entities"].append(v)
        if key == "negative":
            bucket["items"] = bucket["items"][-500:]
        bucket["entities"] = bucket["entities"][-300:]
        profile.profile = prof  # JSONB 整体重赋值才触发 UPDATE
    await db.commit()
    return {"profile": profile.name, "item_id": item.id if item else None,
            "signal": signal, "recorded": True}


# ---------- 晨报 ----------

async def digest(profile: UserProfile, db: AsyncSession, days: int = 7,
                 limit: int = 10) -> dict:
    """top10 命中 → LLM 200 字中文晨报；无 key 降级为列表拼接"""
    recs = await match_items(profile, db, days=days, limit=limit)
    briefs = [{
        "title": r["item"].title_zh or r["item"].title,
        "severity": r["item"].severity, "cve": (r["item"].cve_ids or [None])[0],
        "is_kev": r["item"].is_kev, "has_poc": r["item"].has_poc,
        "why": r["why"], "score": r["score"],
    } for r in recs]
    if not briefs:
        return {"name": profile.name, "count": 0,
                "digest": "近 %d 天暂无命中画像的情报，可放宽严重度下限或补充关注资产。" % days,
                "items": []}
    text = None
    try:
        from app.enrichment.common import llm_text
        prompt = (
            "你是 AI 安全运营助手。下面是命中用户画像的今日情报（JSON 列表，含标题/严重度/CVE/推荐理由）。"
            "请写一段不超过 200 字的中文晨报摘要：先总览数量与最高风险，再点名最值得处置的 2-3 条"
            "（KEV 在野利用、有 PoC、命中资产者优先），语气专业克制，不要 Markdown 列表。\n"
            + json.dumps(briefs, ensure_ascii=False))
        text = await llm_text([{"role": "user", "content": prompt}],
                              max_tokens=400, temperature=0.3)
    except Exception as e:  # noqa: BLE001
        log.warning("digest_llm_failed", error=str(e)[:150])
    if not text:
        parts = [f"近{days}天为你筛选 {len(briefs)} 条相关情报"]
        for i, b in enumerate(briefs[:5], 1):
            tag = "【KEV】" if b["is_kev"] else ("【有PoC】" if b["has_poc"] else "")
            parts.append(f"{i}. {tag}{b['title']}（{b['severity'] or '未定级'}；{b['why']}）")
        if len(briefs) > 5:
            parts.append(f"另有 {len(briefs) - 5} 条见下方列表")
        text = "；".join(parts) + "。"
    return {"name": profile.name, "count": len(briefs), "digest": text, "items": briefs}
