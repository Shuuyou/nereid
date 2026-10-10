"""assets worker：受影响互联网资产测绘（Hunter → 模拟降级）"""
from __future__ import annotations

from app.core.logging import get_logger
from app.enrichment.common import ok, partial, skipped
from app.services import hunter

log = get_logger("enrich.assets")

HIGH_VALUE_PRODUCTS = {  # AI 生态产品才测绘
    "ollama", "vllm", "gradio", "jupyter", "mlflow", "langflow", "flowise",
    "dify", "ray", "milvus", "chromadb", "lollms", "xinference", "sglang",
}


async def run(item, ctx) -> dict:
    products = [p for p in (item.products or []) if p.lower() in HIGH_VALUE_PRODUCTS] or \
               [p for p in (item.products or [])][:2]
    if not products:
        return skipped("no products to map")
    rows: list[dict] = []  # → asset_stats
    total = 0
    any_simulated = False
    for prod in products[:3]:
        res = await hunter.search(prod, page_size=15)
        simulated = res is None
        if simulated:
            res = hunter.simulated_assets(prod)
            any_simulated = True
        total += int(res.get("total") or 0)
        rows.append({
            "platform": "hunter",
            "query": prod,
            "total_count": int(res.get("total") or 0),
            "is_simulated": simulated,
            "sample": [{
                "ip": a.get("ip") or a.get("ip_str"), "port": a.get("port"),
                "domain": a.get("domain"), "org": a.get("company") or a.get("org"),
                "country": a.get("country"), "city": a.get("city"),
                "title": a.get("web_title") or a.get("title"),
                "service": a.get("protocol") or a.get("service"),
                "simulated": simulated,
            } for a in res.get("assets", [])[:15]],
        })
    note = f"{len(rows)} product exposures, total≈{total}" + (" (simulated)" if any_simulated else "")
    return ok(note, confidence=0.3 if any_simulated else 0.9,
              extra={"asset_exposure_count": total},
              rows={"assets": rows}, data_keys=["assets"])
