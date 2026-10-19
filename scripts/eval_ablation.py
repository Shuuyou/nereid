"""检索/编排消融评测（无 LLM，分钟级出真数）
口径：对 eval_qa.py 同题集，逐题取 top-10 证据文本（标题+摘要+实体字段），
统计 expect 关键词覆盖率。配置：
  hybrid      — dense+sparse RRF（完整检索）
  dense_only  — 仅稠密向量
  sparse_only — 仅 BM42 稀疏
  no_kg       — hybrid 证据（不含 KG 桥接追加项）
  with_kg     — hybrid + KG 一跳邻居证据（KG 扩展贡献=with_kg-no_kg）
端到端"固定工作流"基线另由 scripts/eval_qa.py --fast 测（单独跑）。
用法: cd backend && .venv/bin/python ../scripts/eval_ablation.py
"""
import asyncio
import json
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))
sys.path.insert(0, os.path.dirname(__file__))

from eval_qa import EVAL_QUESTIONS  # noqa: E402
from app.rag import embedder, qdrant  # noqa: E402
from app.rag.kg import entity_expand  # noqa: E402


def coverage(text: str, expects: list[str]) -> float:
    t = text.lower()
    return sum(1 for e in expects if e.lower() in t) / max(1, len(expects))


def doc_text(h: dict) -> str:
    parts = [h.get("title", ""), h.get("title_zh", "") or "", h.get("summary_zh", "") or "", h.get("text", "") or ""]
    for k in ("cve", "cwe", "product"):
        v = h.get(k)
        if v:
            parts.append(" ".join(v) if isinstance(v, list) else str(v))
    return " ".join(parts)


async def sparse_search(sv: dict, top_k: int = 10) -> list[dict]:
    from qdrant_client import models as qm
    c = qdrant.client()
    res = await c.query_points(
        qdrant.COLLECTION,
        query=qm.SparseVector(indices=sv["indices"], values=sv["values"]),
        using=qdrant.SPARSE, limit=top_k, with_payload=True)
    return [{"id": str(p.id), "score": p.score or 0.0, **(p.payload or {})} for p in res.points]


async def main() -> None:
    rows = {m: {"all": [], "multi": [], "lat": []} for m in
            ["hybrid", "dense_only", "sparse_only", "no_kg", "with_kg"]}
    for q in EVAL_QUESTIONS:
        dv = await embedder.embed_query(q["q"])
        sv = (await embedder.sparse_texts([q["q"]]))[0]

        for mode in rows:
            t0 = time.time()
            if mode == "dense_only":
                hits = await qdrant.search_dense(dv, top_k=10)
            elif mode == "sparse_only":
                hits = await sparse_search(sv, top_k=10)
            else:
                hits = await qdrant.hybrid_search(dv, sv, top_k=10)
                if mode == "with_kg":
                    try:
                        eids = []
                        for h in hits[:8]:
                            eids += (h.get("cve") or []) + (h.get("cwe") or []) + (h.get("product") or [])
                        extra = await entity_expand(list(dict.fromkeys(eids))[:20], hops=2, limit=8)
                        for e in extra:
                            hits.append({"title": e.get("title", ""), "summary": e.get("rel", ""),
                                         "cve": [e.get("nid") or e.get("via_cwe", "")], "cwe": [], "product": []})
                    except Exception:
                        pass
            lat = (time.time() - t0) * 1000
            text = " ".join(doc_text(h) for h in hits)
            c = coverage(text, q["expect"])
            rows[mode]["all"].append(c)
            if q["type"] == "multi":
                rows[mode]["multi"].append(c)
            rows[mode]["lat"].append(lat)

    out = {}
    for m, r in rows.items():
        lats = sorted(r["lat"])
        out[m] = {
            "keyword_cov": round(sum(r["all"]) / len(r["all"]), 4),
            "multi_cov": round(sum(r["multi"]) / len(r["multi"]), 4),
            "p95_ms": round(lats[int(len(lats) * 0.95) - 1], 1),
            "p50_ms": round(lats[len(lats) // 2], 1),
        }
    print(json.dumps(out, ensure_ascii=False, indent=2))
    with open(os.path.join(os.path.dirname(__file__), "..", "reports", "eval_ablation.json"), "w") as f:
        json.dump({"generated_at": time.strftime("%Y-%m-%dT%H:%M:%S+00:00", time.gmtime()),
                   "metric": "top10 证据文本内 expect 关键词覆盖率（检索层口径，非答案口径）",
                   "n": len(EVAL_QUESTIONS), "modes": out}, f, ensure_ascii=False, indent=2)
    print("saved -> reports/eval_ablation.json")


if __name__ == "__main__":
    asyncio.run(main())
