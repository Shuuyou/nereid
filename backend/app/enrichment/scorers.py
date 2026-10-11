"""scorers worker：NVD 补分 + EPSS + KEV 刷新 + SSVC（确定性源，置信度 1.0）"""
from __future__ import annotations

from app.core.http import fetch
from app.core.logging import get_logger
from app.enrichment.common import ok, partial, skipped
from app.services.ssvc import fetch_vulnrichment

log = get_logger("enrich.scorers")

_ROOT = __import__("os").path.dirname(__import__("os").path.dirname(
    __import__("os").path.dirname(__import__("os").path.dirname(__import__("os").path.abspath(__file__)))))


def _cvelist_local(cve_id: str) -> dict:
    """从本地 cvelistV5 git 克隆读取 CVSS/CWE（免外部 API，离线可复现）"""
    import json as _j
    import os as _o
    try:
        _, y, n = cve_id.split("-")
        path = _o.path.join(_ROOT, "data/cvelistV5/cves", y, f"{n[:-3]}xxx", f"{cve_id}.json")
        if not _o.path.exists(path):
            return {}
        d = _j.load(open(path, encoding="utf-8"))
        out: dict = {}
        # CNA + ADP 容器都可能有 metrics
        for cont in ("cna",):
            m = (d.get("containers", {}).get(cont, {}).get("metrics") or [])
            for mm in m:
                for ver, fk, fv, fs in (("cvssV3_1", "cvss_v31_score", "cvss_v31_vector", "severity"),
                                        ("cvssV3_0", "cvss_v31_score", "cvss_v31_vector", "severity"),
                                        ("cvssV4_0", "cvss_v40_score", "cvss_v40_vector", None)):
                    v = mm.get(ver)
                    if v and not out.get(fk):
                        out[fk] = v.get("baseScore")
                        if fv:
                            out[fv] = v.get("vectorString")
                        if fs and v.get("baseSeverity"):
                            out[fs] = v["baseSeverity"].lower()
        cwes = sorted({d2.get("cweId") for pt in
                       (d.get("containers", {}).get("cna", {}).get("problemTypes") or [])
                       for d2 in (pt.get("descriptions") or [])
                       if str(d2.get("cweId") or "").startswith("CWE-")})
        if cwes:
            out["cwe_ids"] = sorted(set(cwes))
        return out
    except Exception:  # noqa: BLE001
        return {}

KEV_URLS = [
    # github 镜像优先（本环境 cisa.gov 不可达，直连会耗尽 fetch 3 次指数退避）
    "https://raw.githubusercontent.com/cisagov/kev-data/develop/known_exploited_vulnerabilities.json",
    "https://www.cisa.gov/sites/default/files/feeds/known_exploited_vulnerabilities.json",
]
_kev_cache: dict | None = None


async def _kev_set() -> dict:
    global _kev_cache
    if _kev_cache is None:
        for url in KEV_URLS:
            try:
                r = await fetch(url)
                if r.status_code == 200:
                    _kev_cache = {v["cveID"]: v for v in r.json().get("vulnerabilities", []) if v.get("cveID")}
                    break
            except Exception:  # noqa: BLE001
                continue
        _kev_cache = _kev_cache or {}
    return _kev_cache


def invalidate_kev_cache() -> None:
    global _kev_cache
    _kev_cache = None


async def run(item, ctx) -> dict:
    cves = item.cve_ids or []
    if not cves:
        return skipped("no cve_ids")
    fields: dict = {}
    extra: dict = {}
    notes = []

    # ---- EPSS（批量 ≤100/次）----
    try:
        r = await fetch("https://api.first.org/data/v1/epss", params={"cve": ",".join(cves[:50])})
        if r.status_code == 200:
            for row in r.json().get("data", []):
                fields["epss_score"] = float(row.get("epss") or 0)
                fields["epss_percentile"] = float(row.get("percentile") or 0)
                break
    except Exception as e:  # noqa: BLE001
        notes.append(f"epss:{str(e)[:60]}")

    # ---- KEV ----
    kev = await _kev_set()
    hit = next((kev[c] for c in cves if c in kev), None)
    if hit:
        fields["is_kev"] = True
        from app.enrichment.common import parse_dt
        fields["kev_date_added"] = parse_dt(hit.get("dateAdded"))
        extra["kev_required_action"] = hit.get("requiredAction")
        fields["exploit_maturity"] = "weaponized"

    # ---- cvelistV5 本地克隆优先（免 NVD 限流，离线可用）----
    if not item.cvss_v31_score and cves:
        cv = _cvelist_local(cves[0])
        if cv:
            fields.update({k: v for k, v in cv.items() if v is not None})
            notes.append("cvss:cvelistV5-local")

    # ---- NVD 补分（仅当缺 CVSS 且本地克隆未覆盖）----
    if not item.cvss_v31_score and not fields.get("cvss_v31_score") and cves:
        from app.config import get_settings
        headers = {"apiKey": get_settings().nvd_api_key} if get_settings().nvd_api_key else {}
        try:
            r = await fetch("https://services.nvd.nist.gov/rest/json/cves/2.0",
                            params={"cveId": cves[0]}, headers=headers)
            if r.status_code == 200:
                vs = r.json().get("vulnerabilities", [])
                if vs:
                    c = vs[0]["cve"]
                    metrics = c.get("metrics", {})
                    for key in ("cvssMetricV31", "cvssMetricV30"):
                        if metrics.get(key) and not fields.get("cvss_v31_score"):
                            mm = metrics[key][0]["cvssData"]
                            fields["cvss_v31_score"] = mm.get("baseScore")
                            fields["cvss_v31_vector"] = mm.get("vectorString")
                            fields["severity"] = ((metrics[key][0].get("baseSeverity")
                                                    or mm.get("baseSeverity") or "").lower() or None)
                    if metrics.get("cvssMetricV40"):
                        mm = metrics["cvssMetricV40"][0]["cvssData"]
                        fields["cvss_v40_score"] = mm.get("baseScore")
                        fields["cvss_v40_vector"] = mm.get("vectorString")
                    # CWE 补充
                    cwes = [w["description"][0]["value"] for w in c.get("weaknesses", [])
                            if w.get("description") and w["description"][0].get("value", "").startswith("CWE")]
                    if cwes:
                        fields["cwe_ids"] = sorted(set((item.cwe_ids or []) + cwes))
                    # references 留作 papers/analysis 反向关联
                    refs = [x.get("url") for x in c.get("references", []) if x.get("url")]
                    extra["references"] = refs[:15]
        except Exception as e:  # noqa: BLE001
            notes.append(f"nvd:{str(e)[:60]}")

    # ---- SSVC（CISA Vulnrichment）----
    ssvc = await fetch_vulnrichment(cves[0])
    if ssvc:
        extra["ssvc"] = ssvc
        if ssvc.get("exploitation") == "active" and not fields.get("is_kev"):
            fields["exploit_maturity"] = "weaponized"

    return ok("|".join(notes) if notes else "scorers done",
              confidence=1.0, fields=fields, extra=extra,
              data_keys=["epss", "kev", "nvd", "ssvc"])


async def _epss_batch(cves: list[str]) -> dict[str, tuple[float, float]]:
    """EPSS 批量查询（≤100/次）→ {cve: (score, percentile)}"""
    out: dict[str, tuple[float, float]] = {}
    for i in range(0, len(cves), 100):
        batch = cves[i:i + 100]
        try:
            r = await fetch("https://api.first.org/data/v1/epss",
                            params={"cve": ",".join(batch)})
            if r.status_code == 200:
                for row in r.json().get("data", []):
                    out[row["cve"]] = (float(row.get("epss") or 0),
                                       float(row.get("percentile") or 0))
        except Exception as e:  # noqa: BLE001
            log.warning("epss_batch_failed", batch=i // 100, error=str(e)[:120])
    return out


async def refresh_epss_all(limit: int = 5000) -> int:
    """周期刷新 EPSS+KEV（评分随时间漂移）：批量 API，非 per-item worker"""
    from sqlalchemy import select
    from app.db.models import Item
    from app.db.session import get_session_factory
    global _kev_cache
    _kev_cache = None
    kev = await _kev_set()
    n = 0
    async with get_session_factory()() as db:
        rows = (await db.execute(
            select(Item).where(Item.cve_ids != [])
            .order_by(Item.first_seen_at.desc()).limit(limit))).scalars().all()
        # 收集全部 CVE 一次批量查 EPSS
        all_cves = sorted({c for it in rows for c in (it.cve_ids or [])})
        epss_map = await _epss_batch(all_cves)
        for it in rows:
            best = max(((epss_map.get(c) for c in it.cve_ids or [])),
                       key=lambda x: x[0] if x else -1)
            changed = False
            if best:
                if it.epss_score != best[0]:
                    it.epss_score = best[0]
                    changed = True
                if it.epss_percentile != best[1]:
                    it.epss_percentile = best[1]
                    changed = True
            kev_hit = next((c for c in (it.cve_ids or []) if c in kev), None)
            if kev_hit and not it.is_kev:
                it.is_kev = True
                it.exploit_maturity = "weaponized"
                changed = True
            if changed:
                enr = dict(it.enrichment or {})
                enr["scorers"] = {**(enr.get("scorers") or {}),
                                  "status": "ok", "confidence": 1.0,
                                  "note": "epss/kev refresh"}
                it.enrichment = enr
                n += 1
        await db.commit()
    return n
