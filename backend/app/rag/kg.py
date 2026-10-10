"""Neo4j 安全知识图谱：Item 同步 + 多跳路径查询
节点: (:Item) (:CVE) (:CWE) (:CAPEC) (:Technique{kind:atlas|attack}) (:Product) (:Vendor)
边:   Item-[:HAS_CVE]->CVE-[:HAS_CWE]->CWE-[:MAPS_TO]->CAPEC|Technique
      Item-[:AFFECTS]->Product-[:MADE_BY]->Vendor
"""
from __future__ import annotations

from functools import lru_cache

from neo4j import AsyncGraphDatabase

from app.config import get_settings
from app.core.logging import get_logger
from app.db.models import Item

log = get_logger("rag.kg")


@lru_cache
def driver():
    s = get_settings()
    return AsyncGraphDatabase.driver(s.neo4j_uri, auth=(s.neo4j_user, s.neo4j_password))


async def sync_item(item: Item) -> None:
    """单 item 写入图谱（MERGE 幂等）"""
    try:
        async with driver().session() as ses:
            await ses.run("""
                MERGE (i:Item {id:$id}) SET i.title=$title, i.type=$type, i.severity=$sev,
                    i.url=$url, i.layer=$layer, i.score=$cvss
                FOREACH (c IN $cves | MERGE (v:CVE {id:c}) MERGE (i)-[:HAS_CVE]->(v)
                    FOREACH (w IN $cwes | MERGE (w1:CWE {id:w}) MERGE (v)-[:HAS_CWE]->(w1)))
                FOREACH (w IN $cwes | MERGE (w1:CWE {id:w}) MERGE (i)-[:HAS_CWE]->(w1))
                FOREACH (c IN $capecs | MERGE (ca:CAPEC {id:c}) MERGE (i)-[:MAPS_TO]->(ca))
                FOREACH (t IN $atlas | MERGE (at:Technique {id:t}) SET at.kind='atlas' MERGE (i)-[:MAPS_TO]->(at))
                FOREACH (t IN $attack | MERGE (at2:Technique {id:t}) SET at2.kind='attack' MERGE (i)-[:MAPS_TO]->(at2))
                FOREACH (p IN $products | MERGE (pr:Product {name:p}) MERGE (i)-[:AFFECTS]->(pr))
                FOREACH (v IN $vendors | MERGE (ve:Vendor {name:v}) MERGE (i)-[:MADE_BY]->(ve))
                FOREACH (g IN $ghsas | MERGE (gh:GHSA {id:g}) MERGE (i)-[:HAS_GHSA]->(gh))
            """, id=item.id, title=item.title, type=item.item_type, sev=item.severity,
                url=item.url, layer=item.ai_layer, cvss=item.cvss_v31_score,
                cves=item.cve_ids or [], cwes=item.cwe_ids or [],
                capecs=(item.extra or {}).get("capec_ids", []),
                atlas=item.atlas_techniques or [], attack=item.attack_techniques or [],
                products=item.products or [], vendors=item.vendors or [],
                ghsas=item.ghsa_ids or [])
    except Exception as e:  # noqa: BLE001
        log.warning("kg_sync_failed", item=item.id, error=str(e)[:150])


async def entity_expand(ids: list[str], hops: int = 2, limit: int = 60) -> list[dict]:
    """从实体（CVE/CWE/产品/技术）出发的有界扩展 → 图谱事实"""
    if not ids:
        return []
    facts: list[dict] = []
    try:
        async with driver().session() as ses:
            # 1) 直接关联情报
            res = await ses.run("""
                UNWIND $ids AS eid
                MATCH (n) WHERE n.id = eid OR n.name = eid
                MATCH (i:Item)-[r]-(n)
                RETURN DISTINCT i.id AS item_id, i.title AS title, type(r) AS rel,
                       n.id AS nid, labels(n)[0] AS nlabel
                LIMIT $limit
            """, ids=ids, limit=limit)
            facts += [dict(r) async for r in res]
            # 2) 多跳：CVE→CWE→其他Item（同弱点关联的情报）
            if hops >= 2:
                res = await ses.run("""
                    UNWIND $ids AS eid
                    MATCH (v:CVE {id:eid})-[:HAS_CWE]->(w:CWE)<-[:HAS_CWE]-(other:CVE)<-[:HAS_CVE]-(i2:Item)
                    WHERE NOT i2.id IN [f.item_id FOR f IN []]
                    RETURN DISTINCT i2.id AS item_id, i2.title AS title,
                           w.id AS via_cwe, 'same_cwe' AS rel
                    LIMIT $limit
                """, ids=ids, limit=limit)
                facts += [dict(r) async for r in res]
    except Exception as e:  # noqa: BLE001
        log.warning("kg_expand_failed", error=str(e)[:150])
    # 去重
    seen, out = set(), []
    for f in facts:
        k = (f.get("item_id"), f.get("rel"), f.get("nid") or f.get("via_cwe"))
        if k not in seen:
            seen.add(k)
            out.append(f)
    return out


async def path_between(a: str, b: str, max_len: int = 4) -> list[list[str]]:
    """两个实体间最短路径（多跳解释链）"""
    try:
        async with driver().session() as ses:
            res = await ses.run("""
                MATCH (x) WHERE x.id = $a OR x.name = $a
                MATCH (y) WHERE y.id = $b OR y.name = $b
                MATCH p = shortestPath((x)-[*..%d]-(y))
                RETURN [n IN nodes(p) | coalesce(n.id, n.name, n.title)] AS path
                LIMIT 5
            """ % max_len, a=a, b=b)
            return [r["path"] async for r in res]
    except Exception as e:  # noqa: BLE001
        log.warning("kg_path_failed", error=str(e)[:120])
        return []


async def stats() -> dict:
    try:
        async with driver().session() as ses:
            r = await (await ses.run("MATCH (n) RETURN count(n) AS nodes")).single()
            r2 = await (await ses.run("MATCH ()-[e]->() RETURN count(e) AS edges")).single()
            return {"nodes": r["nodes"], "edges": r2["edges"]}
    except Exception:  # noqa: BLE001
        return {"nodes": 0, "edges": 0}
