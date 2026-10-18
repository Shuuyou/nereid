#!/usr/bin/env python3
"""NVD 2.0 批量窗口枚举 → 回填缺 CVSS 的条目（老 CVE 主要靠 NVD 评分）。

cvelistV5 本地克隆只含 CNA/ADP metrics；2002-2023 老 CVE 的权威分在 NVD。
一次全量枚举（≤120天/窗 × 2000/页），结果落 data/nvd_cvss_cache.json 断点续跑，
再批量 UPDATE 库内 cvss_v31_score 为空的条目。

用法: backend/.venv/bin/python ../scripts/nvd_cvss_backfill.py [--fetch|--apply|--both]
"""
import argparse
import asyncio
import gzip
import json
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from sqlalchemy import select

from app.core.http import fetch
from app.core.logging import get_logger
from app.db.models import Item
from app.db.session import get_session_factory

log = get_logger("nvd_backfill")
ROOT = Path(__file__).resolve().parent.parent
CACHE = ROOT / "data" / "nvd_cvss_cache.json.gz"
NVD = "https://services.nvd.nist.gov/rest/json/cves/2.0"
SLEEP_NO_KEY = 6.2   # 无 API key 限流 5req/30s
SLEEP_KEY = 0.7      # 有 key 50req/30s


def _windows():
    """2002-01-01 → now，每窗 119 天（NVD 上限 120 天）。批量 API 备用路径。"""
    start = datetime(2002, 1, 1, tzinfo=timezone.utc)
    end = datetime.now(timezone.utc)
    while start < end:
        w_end = min(start + timedelta(days=119), end)
        yield start.strftime("%Y-%m-%dT00:00:00.000"), w_end.strftime("%Y-%m-%dT23:59:59.000")
        start = w_end + timedelta(seconds=1)


NVD_FEED = "https://nvd.nist.gov/feeds/json/cve/2.0/nvdcve-2.0-{year}.json.gz"


async def _fetch_year(year: int, items: dict) -> int:
    """NVD 官方年度 feed 文件（整年一把下载，远比批量 API 快）"""
    try:
        r = await fetch(NVD_FEED.format(year=year))
    except Exception as e:  # noqa: BLE001
        log.warning("nvd_feed_error", year=year, error=str(e)[:120])
        return 0
    if r.status_code != 200:
        log.warning("nvd_feed_http", year=year, status=r.status_code)
        return 0
    try:
        d = json.loads(gzip.decompress(r.content).decode("utf-8"))
    except Exception as e:  # noqa: BLE001
        log.warning("nvd_feed_parse", year=year, error=str(e)[:120])
        return 0
    n = 0
    for v in d.get("vulnerabilities", []):
        cve = v.get("cve") or {}
        cid = cve.get("id")
        if not cid:
            continue
        rec = _pick(cve.get("metrics") or {})
        cwes = [w["description"][0]["value"] for w in cve.get("weaknesses", [])
                if w.get("description") and str(w["description"][0].get("value", "")).startswith("CWE")]
        if cwes:
            rec["cwe_ids"] = sorted(set(cwes))
        if rec:
            items[cid] = rec
            n += 1
    return n


def _pick(metrics: dict):
    """Primary > Secondary；v3.1 > v3.0 > v4.0 > v2"""
    out: dict = {}
    for key in ("cvssMetricV31", "cvssMetricV30"):
        arr = metrics.get(key) or []
        if not arr:
            continue
        m = next((x for x in arr if (x.get("type") or "").lower() == "primary"), arr[0])
        d = m.get("cvssData") or {}
        if d.get("baseScore") is not None:
            out["cvss_v31_score"] = d["baseScore"]
            out["cvss_v31_vector"] = d.get("vectorString")
            sev = (m.get("baseSeverity") or d.get("baseSeverity") or "").lower()
            if sev:
                out["severity"] = sev
            break
    arr = metrics.get("cvssMetricV40") or []
    if arr:
        m = next((x for x in arr if (x.get("type") or "").lower() == "primary"), arr[0])
        d = m.get("cvssData") or {}
        if d.get("baseScore") is not None:
            out["cvss_v40_score"] = d["baseScore"]
            out["cvss_v40_vector"] = d.get("vectorString")
            if not out.get("severity") and d.get("baseSeverity"):
                out["severity"] = str(d["baseSeverity"]).lower()
    if not out:  # v2 兜底（很老的 CVE）
        arr = metrics.get("cvssMetricV2") or []
        if arr:
            d = (arr[0].get("cvssData") or {})
            if d.get("baseScore") is not None:
                out["cvss_v31_score"] = None  # 仍保持 v31 空——v2 分数写 cvss_v2 不入主字段
                out["cvss_v2_score"] = d["baseScore"]
                sev = (arr[0].get("baseSeverity") or "").lower()
                if sev:
                    out["severity"] = sev
    return out


async def fetch_all(sleep_s: float) -> None:
    """NVD 年度 feed 文件为主路径（整年一把下载）；批量窗口枚举为 fallback。"""
    meta = {"done_windows": [], "items": {}}
    if CACHE.exists():
        meta = json.loads(gzip.decompress(CACHE.read_bytes()).decode())
    done = set(meta.get("done_windows", []))
    items: dict = meta.get("items", {})

    now_y = datetime.now(timezone.utc).year
    years = [y for y in range(2002, now_y + 1) if f"Y{y}" not in done]
    print(f"years total=25 todo={len(years)} cached_cves={len(items)}")
    for y in years:
        n = await _fetch_year(y, items)
        done.add(f"Y{y}")
        CACHE.write_bytes(gzip.compress(json.dumps(
            {"done_windows": sorted(done), "items": items}).encode()))
        print(f"  [{y}] +{n} cves={len(items)}")
        await asyncio.sleep(1.0)  # feed 文件也保持礼貌间隔
    print(f"fetch done: cves={len(items)}")


async def apply() -> None:
    if not CACHE.exists():
        print("no cache; run --fetch first")
        return
    items_map = json.loads(gzip.decompress(CACHE.read_bytes()).decode())["items"]
    print("cached cves:", len(items_map))
    filled = 0
    async with get_session_factory()() as db:
        rows = (await db.execute(
            select(Item).where(Item.cvss_v31_score.is_(None), Item.cve_ids != []))).scalars().all()
        print("items missing cvss:", len(rows))
        n = 0
        for it in rows:
            # 全部 cve_ids 找首个有实质 metrics 的记录（v31/v40/v2 皆可）
            rec = None
            for c in (it.cve_ids or []):
                cand = items_map.get(c)
                if cand and any(cand.get(k) is not None for k in
                                ("cvss_v31_score", "cvss_v40_score", "cvss_v2_score", "severity")):
                    rec = cand
                    break
            if not rec:
                continue
            for k in ("cvss_v31_score", "cvss_v31_vector", "cvss_v40_score",
                      "cvss_v40_vector", "severity", "cwe_ids"):
                v = rec.get(k)
                if v is None:
                    continue
                if getattr(it, k, None) in (None, "", []):
                    setattr(it, k, v)
            extra_add = {"cvss_source": "nvd-bulk"}
            if rec.get("cvss_v2_score") is not None:
                extra_add["cvss_v2_score"] = rec["cvss_v2_score"]
            it.extra = {**(it.extra or {}), **extra_add}
            filled += 1
            n += 1
            if n >= 500:
                await db.commit()
                n = 0
                print("  ...", filled)
        await db.commit()
    print("applied:", filled)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--fetch", action="store_true")
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--both", action="store_true")
    a = ap.parse_args()
    if a.both or (not a.fetch and not a.apply):
        a.fetch = a.apply = True
    from app.config import get_settings
    sleep_s = SLEEP_KEY if get_settings().nvd_api_key else SLEEP_NO_KEY
    print("sleep:", sleep_s)
    if a.fetch:
        asyncio.run(fetch_all(sleep_s))
    if a.apply:
        asyncio.run(apply())
