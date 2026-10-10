"""papers worker：关联论文/分析文章（S2 + OpenAlex + arXiv + references 反向关联）"""
from __future__ import annotations

from app.core.http import fetch
from app.core.logging import get_logger
from app.enrichment.common import ok, partial, skipped, token_overlap
from app.db.models import Item

log = get_logger("enrich.papers")

_s2_dead = False

AI_TERMS = ("language model", "llm", "prompt injection", "jailbreak", "adversarial",
            "ai secur", "model security", "agent", "rag", "machine learning security")


async def run(item, ctx) -> dict:
    rows: list[dict] = []
    seen: set[str] = set()

    def add(title, url, source, year=None, venue=None, doi=None, authors=None, citations=None):
        if not title or (url or title) in seen:
            return
        seen.add(url or title)
        rel = token_overlap(title, (item.title or "") + " " + (item.summary or ""))
        # AI 相关加成
        hay = title.lower()
        if any(t in hay for t in AI_TERMS):
            rel += 0.25
        rows.append({"title": title, "url": url, "source": source, "year": year,
                     "venue": venue, "doi": doi,
                     "authors": ", ".join(authors or [])[:400],
                     "citations": citations, "relevance_score": round(min(rel, 1.0), 3)})

    cve = (item.cve_ids or [None])[0]
    query_terms = " ".join((item.products or [])[:2] + [cve or ""])

    # ① 本库 articles/papers 中引用本 CVE 的条目（references 反向关联）
    try:
        from sqlalchemy import select
        from app.db.session import get_session_factory
        async with get_session_factory()() as db:
            if cve:
                like = f"%{cve}%"
                hits = (await db.execute(
                    select(Item).where(Item.id != item.id, Item.item_type.in_(["article", "paper"]),
                                       Item.content_text.like(like)).limit(8))).scalars().all()
                for h in hits:
                    add(h.title, h.url, "internal_ref", year=h.published_at.year if h.published_at else None)
    except Exception as e:  # noqa: BLE001
        log.debug("internal_ref_failed", error=str(e)[:100])

    # ② Semantic Scholar（限流熔断）
    global _s2_dead
    q = " ".join((item.products or [])[:2] + ["vulnerability security"])
    if not q.strip():
        q = (item.title or "")[:120]
    if _s2_dead:
        r = None
    else:
      try:
        r = await fetch("https://api.semanticscholar.org/graph/v1/paper/search",
                        params={"query": q[:200], "limit": 6,
                                "fields": "title,year,venue,url,externalIds,authors,citationCount"})
        if r.status_code == 200:
            for p in r.json().get("data", []):
                add(p.get("title"), p.get("url"), "s2", p.get("year"), p.get("venue"),
                    doi=(p.get("externalIds") or {}).get("DOI"),
                    authors=[a.get("name") for a in (p.get("authors") or [])[:5]],
                    citations=p.get("citationCount"))
        elif r.status_code == 429:
            _s2_dead = True
      except Exception as e:  # noqa: BLE001
        log.debug("s2_failed", error=str(e)[:100])

    # ③ arXiv
    try:
        import feedparser
        terms = query_terms or (item.title or "")[:80]
        r = await fetch("https://export.arxiv.org/api/query",
                        params={"search_query": f"all:{terms}", "start": 0, "max_results": 5,
                                "sortBy": "relevance"})
        if r.status_code == 200:
            feed = feedparser.parse(r.text)
            for e in feed.entries:
                add(e.get("title", "").strip(), e.get("id"), "arxiv",
                    year=int(e.get("published", "2000")[:4]),
                    authors=[a.get("name") for a in e.get("authors", [])[:5]])
    except Exception as e:  # noqa: BLE001
        log.debug("arxiv_failed", error=str(e)[:100])

    if not rows:
        return skipped("no related papers found")
    rows.sort(key=lambda r: (r["relevance_score"], r.get("citations") or 0), reverse=True)
    return ok(f"{len(rows)} related papers", confidence=0.7,
              rows={"papers": rows[:15]}, data_keys=["papers"])
