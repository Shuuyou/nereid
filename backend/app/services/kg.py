"""KG 查询服务：子图提取（前端力导图）与统计"""
from __future__ import annotations

from app.core.logging import get_logger
from app.rag.kg import driver, stats

log = get_logger("services.kg")


async def init_schema() -> None:
    """Neo4j 约束初始化（幂等）"""
    try:
        async with driver().session() as ses:
            for stmt in [
                "CREATE CONSTRAINT item_id IF NOT EXISTS FOR (i:Item) REQUIRE i.id IS UNIQUE",
                "CREATE CONSTRAINT cve_id IF NOT EXISTS FOR (c:CVE) REQUIRE c.id IS UNIQUE",
                "CREATE CONSTRAINT cwe_id IF NOT EXISTS FOR (c:CWE) REQUIRE c.id IS UNIQUE",
                "CREATE CONSTRAINT ghsa_id IF NOT EXISTS FOR (g:GHSA) REQUIRE g.id IS UNIQUE",
                "CREATE INDEX product_name IF NOT EXISTS FOR (p:Product) ON (p.name)",
            ]:
                await ses.run(stmt)
        log.info("kg_schema_ready")
    except Exception as e:  # noqa: BLE001
        log.warning("kg_schema_failed", error=str(e)[:150])


async def sync_pending(limit: int = 200) -> int:
    """同步最近更新的 item 到图谱"""
    from sqlalchemy import select
    from app.db.models import Item
    from app.db.session import get_session_factory
    from app.rag.kg import sync_item
    n = 0
    async with get_session_factory()() as db:
        items = (await db.execute(
            select(Item).order_by(Item.updated_at.desc()).limit(limit))).scalars().all()
    for it in items:
        try:
            await sync_item(it)
            n += 1
        except Exception:  # noqa: BLE001
            continue
    return n


async def graph_stats() -> dict:
    return await stats()


async def get_subgraph(entity: str, depth: int = 2) -> dict:
    """以实体为中心的子图（nodes + links，兼容 react-force-graph / echarts graph）"""
    nodes: dict[str, dict] = {}
    links: list[dict] = []
    try:
        async with driver().session() as ses:
            res = await ses.run("""
                MATCH (n) WHERE n.id = $e OR n.name = $e OR n.title CONTAINS $e
                MATCH p = (n)-[r*1..%d]-(m)
                UNWIND relationships(p) AS rel
                WITH DISTINCT startNode(rel) AS a, rel, endNode(rel) AS b
                RETURN a, type(rel) AS rt, b LIMIT 300
            """ % depth, e=entity)
            async for rec in res:
                a, b, rt = rec["a"], rec["b"], rec["rt"]
                for n in (a, b):
                    nid = n.get("id") or n.get("name") or n.get("title")
                    if nid and nid not in nodes:
                        nodes[nid] = {"id": nid, "label": n.get("title") or n.get("name") or nid,
                                      "kind": list(n.labels)[0] if n.labels else "Node",
                                      "severity": n.get("severity"), "score": n.get("score")}
                aid = a.get("id") or a.get("name") or a.get("title")
                bid = b.get("id") or b.get("name") or b.get("title")
                if aid and bid:
                    links.append({"source": aid, "target": bid, "type": rt})
    except Exception as e:  # noqa: BLE001
        log.warning("subgraph_failed", entity=entity, error=str(e)[:150])
    return {"entity": entity, "nodes": list(nodes.values()), "links": links}
