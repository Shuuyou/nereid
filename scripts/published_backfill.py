"""published_at 回填：从 cvelistV5 本地克隆反取 cveMetadata.datePublished
用法: backend/.venv/bin/python scripts/published_backfill.py [--apply]
"""
from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from sqlalchemy import func, select  # noqa: E402

from app.db.models import Item  # noqa: E402
from app.db.session import get_session_factory  # noqa: E402

REPO = Path(__file__).resolve().parent.parent
CVES_DIR = REPO / "data" / "cvelistV5" / "cves"


def load_published_map() -> dict[str, str]:
    """CVE-XXXX-NNNNN -> datePublished"""
    out: dict[str, str] = {}
    for p in CVES_DIR.glob("*/*/CVE-*.json"):
        try:
            d = json.loads(p.read_text(errors="ignore"))
            md = d.get("cveMetadata") or {}
            cid, dp = md.get("cveId"), md.get("datePublished")
            if cid and dp and md.get("state") == "PUBLISHED":
                out[cid] = dp
        except Exception:  # noqa: BLE001
            continue
    return out


async def main(apply: bool) -> None:
    pmap = load_published_map()
    print(f"local cvelistV5 published dates: {len(pmap)}")
    async with get_session_factory()() as db:
        rows = (await db.execute(select(Item).where(
            Item.published_at.is_(None),
            func.cardinality(Item.cve_ids) > 0))).scalars().all()
        print(f"items with NULL published_at & cves: {len(rows)}")
        fixed = 0
        for it in rows:
            dts = [pmap[c] for c in (it.cve_ids or []) if c in pmap]
            if not dts:
                continue
            dt = min(dts).replace("Z", "+00:00")
            if apply:
                from datetime import datetime
                it.published_at = datetime.fromisoformat(dt)
                it.extra = {**(it.extra or {}), "published_source": "cvelistV5-backfill",
                            "indexed_hash": None}  # 清 hash 触发重索引（payload published_at 更新）
            fixed += 1
        if apply:
            await db.commit()
        print(f"{'applied' if apply else 'dry-run'}: {fixed} items backfilled")


if __name__ == "__main__":
    asyncio.run(main("--apply" in sys.argv))
