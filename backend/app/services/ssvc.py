"""CISA Vulnrichment (SSVC) 适配器

数据源：CVE Services API（cveawg.mitre.org/api/cve/{cve}）中 CISA-ADP 的
adp 容器 metrics[].other.type == "ssvc"。产出决策点：
- exploitation: none|poc|active   （真实利用信号）
- automatable: yes|no
- technical_impact: partial|total
官方源 → 置信度 1.0；取不到返回 None（优雅降级）。
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from app.core.http import fetch
from app.core.logging import get_logger

log = get_logger("ssvc")
CVE_API = "https://cveawg.mitre.org/api/cve/{cve}"


def _parse_dt(s: Any) -> datetime | None:
    try:
        return datetime.fromisoformat(str(s).replace("Z", "+00:00"))
    except Exception:  # noqa: BLE001
        return None


def _dig_ssvc(containers: list[dict]) -> dict[str, Any] | None:
    """在 adp 容器列表中找 CISA-ADP 的 ssvc 决策点"""
    for adp in containers or []:
        provider = ((adp.get("providerMetadata") or {}).get("shortName") or "").lower()
        if "cisa" not in provider:
            continue
        for m in adp.get("metrics") or []:
            other = m.get("other") or {}
            if (other.get("type") or "").lower() != "ssvc":
                continue
            content = other.get("content") or {}
            out: dict[str, Any] = {"source": "cisa-vulnrichment",
                                   "version": content.get("version"),
                                   "timestamp": content.get("timestamp")}
            for opt in content.get("options") or []:
                for k, v in opt.items():
                    key = str(k).lower().replace(" ", "_")
                    out[key] = str(v).lower() if isinstance(v, str) else v
            # 归一化常用键（SSVC 2.0: Exploitation/Automatable/Technical Impact）
            out["exploitation"] = out.get("exploitation") or out.get("exploit")
            out["technical_impact"] = out.get("technical_impact") or out.get("technical impact")
            return out
    return None


async def fetch_vulnrichment(cve: str) -> dict[str, Any] | None:
    """抓取单个 CVE 的 CISA-ADP SSVC 决策点；失败/无数据返回 None"""
    try:
        resp = await fetch(CVE_API.format(cve=cve))
        if resp.status_code != 200:
            return None
        data = resp.json()
    except Exception as e:  # noqa: BLE001
        log.warning("vulnrichment_fetch_failed", cve=cve, error=str(e)[:150])
        return None
    adp = ((data.get("containers") or {}).get("adp")) or []
    ssvc = _dig_ssvc(adp)
    if ssvc:
        dt = _parse_dt(ssvc.get("timestamp"))
        ssvc["ts_parsed"] = dt.isoformat() if dt else None
    return ssvc
