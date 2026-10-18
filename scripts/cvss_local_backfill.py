#!/usr/bin/env python3
"""本地 cvelistV5 批量回填 CVSS/CWE（纯文件读取，无网络，确定性数据）。

与 refresh_epss_all 同模式：批量确定性更新器，非 per-item worker。
只写 cvss_v31_score/cvss_v31_vector/severity/cwe_ids + extra.cvss_source；
scorers worker 之后跑时字段已非空不会覆盖（merge 只填空）。

用法: backend/.venv/bin/python ../scripts/cvss_local_backfill.py [--limit N]
"""
import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from sqlalchemy import select

from app.db.models import Item
from app.db.session import get_session_factory
from app.enrichment.scorers import _cvelist_local


async def run(limit: int | None) -> None:
    q = (select(Item)
         .where(Item.cvss_v31_score.is_(None), Item.cve_ids != [])
         .order_by(Item.first_seen_at.desc()))
    if limit:
        q = q.limit(limit)
    async with get_session_factory()() as db:
        items = (await db.execute(q)).scalars().all()
    print(f"items missing cvss: {len(items)}")

    filled = 0
    batch = 0
    async with get_session_factory()() as db:
        for it in items:
            item = await db.get(Item, it.id)
            if not item or item.cvss_v31_score:
                continue
            cv = {}
            for c in (item.cve_ids or [])[:3]:
                cv = _cvelist_local(c)
                if cv:
                    break
            if not cv:
                continue
            src = cv.pop("cvss_source", "cna")
            for k in ("cvss_v31_score", "cvss_v31_vector", "cvss_v40_score",
                      "cvss_v40_vector", "severity", "cwe_ids"):
                v = cv.get(k)
                if v is None:
                    continue
                cur = getattr(item, k, None)
                if cur in (None, "", []):
                    setattr(item, k, v)
            item.extra = {**(item.extra or {}), "cvss_source": src}
            filled += 1
            batch += 1
            if batch >= 500:
                await db.commit()
                batch = 0
                print(f"  ... filled {filled}")
        await db.commit()
    print(f"done: filled {filled}/{len(items)}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=None)
    a = ap.parse_args()
    asyncio.run(run(a.limit))
