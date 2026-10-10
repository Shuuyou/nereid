"""mappings worker：CWE→CAPEC→ATT&CK / MITRE ATLAS 结构化映射（确定性）"""
from __future__ import annotations

import json
import os

from sqlalchemy import select

from app.core.logging import get_logger
from app.db.models import Item
from app.enrichment.common import ok, skipped

log = get_logger("enrich.mappings")

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
_cache: dict | None = None


def _load() -> dict:
    global _cache
    if _cache is None:
        out = {"cwe_capec": {}, "atlas_by_tech": {}, "atlas_names": {}}
        try:
            d = json.load(open(os.path.join(_ROOT, "data/cwe_capec.json"), encoding="utf-8"))
            out["cwe_capec"] = d.get("cwe_to_capec", {})
        except Exception as e:  # noqa: BLE001
            log.warning("cwe_capec_load", error=str(e)[:100])
        try:
            d = json.load(open(os.path.join(_ROOT, "data/attack_ai.json"), encoding="utf-8"))
            for t in d.get("techniques", []):
                out["atlas_names"][t["id"]] = t.get("name")
                for cwe in t.get("cwes", []):
                    out["atlas_by_tech"].setdefault(cwe, []).append(t["id"])
        except Exception as e:  # noqa: BLE001
            log.warning("atlas_load", error=str(e)[:100])
        _cache = out
    return _cache


async def run(item, ctx) -> dict:
    cwes = item.cwe_ids or []
    # 从描述/标题中再捞 CWE
    from app.core.ids import extract_ids
    text = " ".join(x or "" for x in (item.title, item.summary, (item.content_text or "")[:2000]))
    cwes = sorted(set(cwes) | set(extract_ids(text)["cwe"]))
    if not cwes:
        return skipped("no cwes")

    data = _load()
    capex = sorted({c for cwe in cwes for c in data["cwe_capec"].get(cwe, [])})
    atlas = sorted({t for cwe in cwes for t in data["atlas_by_tech"].get(cwe, [])})

    # ATLAS 技术名
    atlas_named = [{"id": t, "name": data["atlas_names"].get(t)} for t in atlas]

    cve = (item.cve_ids or [None])[0]
    rows = []  # → mapping_links
    for cwe in cwes:
        rows.append({"cve_id": cve, "cwe_id": cwe, "source": "extracted", "confidence": 0.9})
        for c in capex:
            rows.append({"cve_id": cve, "cwe_id": cwe, "capec_id": c,
                         "source": "cwe-capec-db", "confidence": 0.7})
        for t in atlas:
            rows.append({"cve_id": cve, "cwe_id": cwe, "atlas_technique": t,
                         "source": "atlas-db", "confidence": 0.7})

    fields = {"cwe_ids": cwes}
    if atlas:
        fields["atlas_techniques"] = atlas
    extra = {"capec_ids": capex, "atlas_named": atlas_named}
    return ok(f"cwe={len(cwes)} capec={len(capex)} atlas={len(atlas)}",
              confidence=0.85 if rows else 0.4,
              fields=fields, extra=extra, rows={"mappings": rows},
              data_keys=["mappings"])
