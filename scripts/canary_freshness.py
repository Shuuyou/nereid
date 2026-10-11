#!/usr/bin/env python3
"""金丝雀端到端时效测试（Google SRE tracer 模式）

注入一条带唯一标记的合成情报 → 走真实 ingest→enrich→index→检索 链路 →
分阶段计时，输出瀑布 + Prometheus gauge。

用法: cd backend && PYTHONPATH=. python3 ../scripts/canary_freshness.py [--skip-enrich]
"""
import asyncio
import sys
import json
import time
import uuid
from datetime import datetime, timezone


async def main(skip_enrich: bool = False) -> None:
    from sqlalchemy import select
    from app.collectors.base import RawItemData
    from app.db.models import Item, RawItem, Source
    from app.db.session import get_session_factory
    from app.services.ingest import ingest_items

    tag = f"CANARY-{uuid.uuid4().hex[:8].upper()}"
    t0 = time.time()
    marks: dict[str, float] = {"inject": 0.0}
    print(f"[canary] 注入标记情报 {tag} @ {datetime.now(timezone.utc).isoformat()}")

    data = RawItemData(
        native_id=tag,
        url=f"https://canary.secagent.local/{tag}",
        title=f"{tag}: Synthetic critical vulnerability in CanaryLLM inference server",
        content_text=(f"{tag} —— 金丝雀测试条目。CanaryLLM 推理服务 <9.9 存在未授权 RCE，"
                      "CVSS 9.8，攻击者可通过 /api/generate 反序列化执行命令。该条目用于验证"
                      "采集→去重→富化→索引→检索 端到端链路时效。"),
        published_at=datetime.now(timezone.utc),
        lang="zh", item_type="vuln",
        cve_ids=[], ghsa_ids=[], cwe_ids=["CWE-502"],
        products=["CanaryLLM"], vendors=["Canary"],
        raw={"canary": True},
    )

    async with get_session_factory()() as db:
        src = await db.scalar(select(Source).where(Source.name == "canary"))
        if not src:
            src = Source(name="canary", source_type="canary", url="https://canary.secagent.local",
                         tier=1, lang="zh", poll_interval_sec=0, enabled=False)
            db.add(src)
            await db.flush()
        stats = await ingest_items(db, src, [data])
        await db.commit()
    marks["ingested"] = time.time() - t0
    print(f"[canary] ingest 完成 +{marks['ingested']:.2f}s → {stats}")

    async with get_session_factory()() as db:
        item = await db.scalar(select(Item).where(Item.title.like(f"{tag}%")))
        if item:
            item.extra = {**(item.extra or {}), "canary": True}
            await db.commit()
    if not item:
        print("[canary] FAIL: item 未入库"); sys.exit(1)
    marks["item_visible"] = time.time() - t0
    print(f"[canary] 情报卡片可见 +{marks['item_visible']:.2f}s id={item.id[:8]}")

    if not skip_enrich:
        try:
            from app.enrichment.pipeline import enrich_item
            await enrich_item(item.id)
            marks["enriched"] = time.time() - t0
            print(f"[canary] 富化完成 +{marks['enriched']:.2f}s")
        except Exception as e:  # noqa: BLE001
            print(f"[canary] 富化降级: {e}")
            marks["enriched"] = -1

    try:
        from app.rag.indexer import index_item
        n = await index_item(item.id)
        marks["indexed"] = time.time() - t0
        print(f"[canary] 向量索引 +{marks['indexed']:.2f}s ({n} chunks)")
    except Exception as e:  # noqa: BLE001
        print(f"[canary] 索引降级: {e}")
        marks["indexed"] = -1

    try:
        from app.rag.kg import sync_item
        async with get_session_factory()() as db:
            fresh = await db.get(Item, item.id)
            await sync_item(fresh)
        marks["kg"] = time.time() - t0
        print(f"[canary] KG 同步 +{marks['kg']:.2f}s")
    except Exception as e:  # noqa: BLE001
        print(f"[canary] KG 降级: {e}")
        marks["kg"] = -1

    try:
        from app.rag import retriever
        hits = await retriever.retrieve(f"{tag} CanaryLLM 漏洞", top_k=3)
        marks["searchable"] = time.time() - t0
        ok = any(h.get("item_id") == item.id for h in hits)
        print(f"[canary] 检索命中={ok} +{marks['searchable']:.2f}s")
    except Exception as e:  # noqa: BLE001
        print(f"[canary] 检索降级: {e}")
        marks["searchable"] = -1

    # 回写 API 进程 → /metrics 暴露 secagent_canary_e2e_seconds{stage=...}
    try:
        import urllib.request
        req = urllib.request.Request(
            "http://localhost:8000/api/internal/canary",
            data=json.dumps({"stages": marks}).encode(),
            headers={"Content-Type": "application/json"}, method="POST")
        urllib.request.urlopen(req, timeout=5)
        print("[canary] 指标已回写 /metrics")
    except Exception as e:  # noqa: BLE001
        print(f"[canary] 指标回写失败（API未在跑？）: {e}")

    total = time.time() - t0
    print("\n===== 金丝雀瀑布 =====")
    for k, v in marks.items():
        bar = "█" * min(40, int(v)) if v >= 0 else "✗"
        print(f"  {k:14s} {v:7.2f}s {bar}")
    print(f"  {'TOTAL':14s} {total:7.2f}s")
    # 默认自动清理金丝雀条目，防污染情报库/统计（--keep 保留作演示证据）
    if "--keep" in sys.argv:
        print(f"[canary] item_id={item.id}（--keep：已保留）")
    else:
        try:
            async with get_session_factory()() as db:
                from sqlalchemy import delete
                for m in (Item,):
                    await db.execute(delete(m).where(m.id == item.id))
                raw = await db.scalar(select(RawItem).where(RawItem.url.like(f"%{tag}")))
                if raw:
                    await db.delete(raw)
                await db.commit()
            print(f"[canary] 条目已清理 item_id={item.id[:8]}（指标保留于 /metrics）")
        except Exception as e:  # noqa: BLE001
            print(f"[canary] 清理失败（可手动删除 {item.id}）: {e}")


if __name__ == "__main__":
    asyncio.run(main("--skip-enrich" in sys.argv))
