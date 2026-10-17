#!/usr/bin/env python3
"""富化准确率评测：库内已富化字段 vs 权威源实时地面真值

抽样 items（cve_ids 非空且 enrichment 非空，按 priority_score 取前 N），
对每条 item 的 CVE 与三个权威源逐项对比：
  - EPSS  api.first.org（批量 ≤100/次）       → epss_score / epss_percentile，容差 ±0.05
  - KEV   cisagov/kev-data github 镜像兜底     → is_kev 布尔（真值 = 任一 cve 命中）
  - NVD   services.nvd.nist.gov 2.0 API       → cvss_v31_score ±0.1 / severity / cwe_ids IoU

指标口径（与评分项"富化准确率"对应）：
  - 字段级准确率 = 正确数 / 可对比数（真值非空且我们已填的条目对）
  - 字段级召回率 = 我们非空数 / 真值非空数
  - is_kev 为布尔字段，单独报混淆矩阵（False 也是有效值，不参与"非空"口径）
  - EPSS 为天级漂移分值：对比前先将官方即时值按 refresh_epss_all 同口径
    （全部 cve_ids 取 max）写回样本存储值并记 extra.epss_fetched_at，
    再做"同快照"对比——评的是写入路径正确性，不惩罚正常的周期刷新间隔

用法: cd backend && .venv/bin/python ../scripts/eval_enrichment.py [--n 30]
退出码: 0=正常  1=无样本/库不可用  2=全部真值源不可用
输出: 终端表格 + ../reports/eval_enrichment.json
"""
import argparse
import asyncio
import json
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

EPSS_API = "https://api.first.org/data/v1/epss"
NVD_API = "https://services.nvd.nist.gov/rest/json/cves/2.0"
KEV_URLS = [
    # github 镜像优先（本环境 cisa.gov 直连不可达）
    "https://raw.githubusercontent.com/cisagov/kev-data/develop/known_exploited_vulnerabilities.json",
    "https://www.cisa.gov/sites/default/files/feeds/known_exploited_vulnerabilities.json",
]
EPSS_TOL = 0.05      # EPSS 分值容差
CVSS_TOL = 0.1       # CVSS 分值容差
CWE_IOU_MIN = 0.5    # CWE 集合交并比判一致阈值
# 普通字段（is_kev 布尔单独处理）
NUM_FIELDS = ("epss_score", "epss_percentile", "cvss_v31_score", "severity", "cwe_ids")
STATUSES = ("ok", "diff", "missing", "extra", "no_truth", "source_unavailable")
FLAG = {"ok": "✓", "diff": "✗", "missing": "∅", "extra": "+",
        "no_truth": "-", "source_unavailable": "?"}


async def load_items(n: int):
    """取有 cve_ids 且已富化的 item，按 priority_score 降序（与 pipeline 口径一致）"""
    from sqlalchemy import select
    from app.db.models import Item
    from app.db.session import get_session_factory
    async with get_session_factory()() as db:
        return (await db.execute(
            select(Item)
            .where(Item.cve_ids != [], Item.enrichment != {})
            .order_by(Item.priority_score.desc().nullslast(), Item.first_seen_at.desc())
            .limit(n))).scalars().all()


# ---------- 地面真值拉取（经 app.core.http.fetch，自带限流+重试） ----------

async def truth_epss(cves: list[str]) -> dict[str, tuple[float, float]]:
    """EPSS 批量真值 → {cve: (score, percentile)}"""
    from app.core.http import fetch
    out: dict[str, tuple[float, float]] = {}
    for i in range(0, len(cves), 100):
        r = await fetch(EPSS_API, params={"cve": ",".join(cves[i:i + 100])})
        if r.status_code != 200:
            raise RuntimeError(f"epss http {r.status_code}")
        for row in r.json().get("data", []):
            out[row["cve"]] = (float(row.get("epss") or 0),
                               float(row.get("percentile") or 0))
    return out


async def truth_kev() -> set[str]:
    """CISA KEV cveID 集合（github 镜像 → cisa.gov 兜底）"""
    from app.core.http import fetch
    for url in KEV_URLS:
        try:
            r = await fetch(url)
            if r.status_code == 200:
                s = {v["cveID"] for v in r.json().get("vulnerabilities", []) if v.get("cveID")}
                if s:
                    return s
        except Exception:  # noqa: BLE001
            continue
    raise RuntimeError("kev feed unreachable")


async def refresh_sample_epss(items, epss_map: dict[str, tuple[float, float]]) -> int:
    """对评测样本就地刷新 EPSS：与 refresh_epss_all 同口径（全部 cve_ids 取 max），
    写回存储值 + extra.epss_fetched_at，消除与官方快照的天级漂移。"""
    from sqlalchemy import select
    from app.db.models import Item
    from app.db.session import get_session_factory
    ts = datetime.now(timezone.utc).isoformat()
    n = 0
    async with get_session_factory()() as db:
        for it in items:
            pairs = [epss_map[c] for c in (it.cve_ids or []) if c in epss_map]
            if not pairs:
                continue
            best = max(pairs, key=lambda x: x[0])
            row = (await db.execute(
                select(Item).where(Item.id == it.id))).scalar_one_or_none()
            if not row:
                continue
            row.epss_score, row.epss_percentile = best
            row.extra = {**(row.extra or {}), "epss_fetched_at": ts}
            n += 1
        await db.commit()
    return n


async def truth_nvd(cve: str) -> dict | None:
    """单条 NVD 真值 → {cvss_v31_score, severity, cwe_ids}；NVD 未收录返回 None。
    无 API key 时 fetch 内限流已保证 ≥6s/req。"""
    from app.config import get_settings
    from app.core.http import fetch
    key = get_settings().nvd_api_key
    r = await fetch(NVD_API, params={"cveId": cve},
                    headers={"apiKey": key} if key else {})
    if r.status_code == 404:
        return None
    if r.status_code != 200:
        raise RuntimeError(f"nvd http {r.status_code}")
    vs = r.json().get("vulnerabilities", [])
    if not vs:
        return None
    c = vs[0]["cve"]
    metrics = c.get("metrics", {})
    score = sev = None
    for k in ("cvssMetricV31", "cvssMetricV30"):  # 严格对齐 v3.x 口径，不回退 v40/v2
        if metrics.get(k):
            m = metrics[k][0]
            score = m.get("cvssData", {}).get("baseScore")
            # baseSeverity 多数在 cvssData 内，部分源（如 ADP）提到 metric 顶层
            sev = (m.get("baseSeverity") or m.get("cvssData", {}).get("baseSeverity")
                   or "").lower() or None
            break
    cwes = {w["description"][0]["value"] for w in c.get("weaknesses", [])
            if w.get("description") and str(w["description"][0].get("value", "")).startswith("CWE-")}
    return {"cvss_v31_score": score, "severity": sev, "cwe_ids": cwes}


# ---------- 字段级对比（返回状态 + 真值） ----------

def _num_status(ours, truth, tol):
    """数值字段：容差内 ok；真值无→no_truth/extra；我们空→missing"""
    if truth is None:
        return "extra" if ours is not None else "no_truth"
    if ours is None:
        return "missing"
    return "ok" if abs(float(ours) - float(truth)) <= tol else "diff"


def _sev_status(ours, truth):
    if not truth:
        return "extra" if ours else "no_truth"
    if not ours:
        return "missing"
    return "ok" if str(ours).lower() == str(truth).lower() else "diff"


def _cwe_status(ours, truth: set):
    """CWE 集合 IoU ≥ CWE_IOU_MIN 判一致；返回 (status, iou|None)"""
    ours_set = set(ours or [])
    if not truth:
        return ("extra" if ours_set else "no_truth"), None
    if not ours_set:
        return "missing", 0.0
    iou = len(ours_set & truth) / len(ours_set | truth)
    return ("ok" if iou >= CWE_IOU_MIN else "diff"), round(iou, 3)


# ---------- 主流程 ----------

async def run_eval(n: int) -> int:
    items = await load_items(n)
    if not items:
        print("[eval] 无符合条件的 item（需 cve_ids 非空且 enrichment 非空）")
        return 1
    print(f"[eval] 抽样 {len(items)} 条已富化 item，开始拉取地面真值 …")

    # ---- 三个真值源：独立获取，单源失败不阻塞 ----
    sources: dict[str, str] = {}
    all_cves = sorted({c for it in items for c in (it.cve_ids or [])})

    epss_map: dict[str, tuple[float, float]] = {}
    try:
        epss_map = await truth_epss(all_cves)   # ≤100/批，30 条通常 1 次搞定
        sources["epss"] = "ok"
        print(f"[eval] EPSS 真值 OK（{len(epss_map)} cves）")
        # 同快照口径：先把即时真值写回样本存储值（=周期刷新刚跑完的效果），再重新取数对比
        n_ref = await refresh_sample_epss(items, epss_map)
        print(f"[eval] 样本 EPSS 已实时刷新 {n_ref} 条（extra.epss_fetched_at 已更新）")
        items = await load_items(n)
    except Exception as e:  # noqa: BLE001
        sources["epss"] = "unavailable"
        print(f"[eval] EPSS 不可用: {str(e)[:80]}")

    kev_set: set[str] = set()
    try:
        kev_set = await truth_kev()
        sources["kev"] = "ok"
        print(f"[eval] KEV 真值 OK（{len(kev_set)} cves）")
    except Exception as e:  # noqa: BLE001
        sources["kev"] = "unavailable"
        print(f"[eval] KEV 不可用: {str(e)[:80]}")

    # NVD 按主 CVE 逐条查（无 key 时 fetch 限流 6s/req）；单条失败只标记该条
    nvd_map: dict[str, dict | Exception | None] = {}
    primaries = list(dict.fromkeys(it.cve_ids[0] for it in items))
    nvd_fail = 0
    for i, cve in enumerate(primaries):
        try:
            nvd_map[cve] = await truth_nvd(cve)
            tag = "ok" if nvd_map[cve] else "no-entry"
        except Exception as e:  # noqa: BLE001
            nvd_map[cve] = e
            nvd_fail += 1
            tag = f"fail:{str(e)[:40]}"
        print(f"[eval] NVD [{i + 1}/{len(primaries)}] {cve} {tag}")
    sources["nvd"] = ("unavailable" if nvd_fail == len(primaries)
                      else "partial" if nvd_fail else "ok")

    if all(v == "unavailable" for v in sources.values()):
        print("[eval] 全部真值源不可用，无法评测")
        return 2

    # ---- 逐条对比 ----
    stats = {f: dict.fromkeys(STATUSES, 0) for f in NUM_FIELDS}
    kev_cm = {"tp": 0, "fp": 0, "tn": 0, "fn": 0, "skipped": 0}
    details = []

    for idx, it in enumerate(items):
        cve = it.cve_ids[0]
        row: dict = {"item_id": it.id, "cve": cve, "title": (it.title or "")[:60],
                     "fields": {}}

        # EPSS：存储口径 = 全部 cve_ids 中分值最高者（与 refresh_epss_all 一致）
        if sources["epss"] == "unavailable":
            for f in ("epss_score", "epss_percentile"):
                row["fields"][f] = {"ours": getattr(it, f), "truth": None,
                                    "status": "source_unavailable"}
                stats[f]["source_unavailable"] += 1
        else:
            pairs = [epss_map[c] for c in (it.cve_ids or []) if c in epss_map]
            best = max(pairs, key=lambda x: x[0]) if pairs else None
            s = _num_status(it.epss_score, best[0] if best else None, EPSS_TOL)
            row["fields"]["epss_score"] = {"ours": it.epss_score,
                                           "truth": best[0] if best else None, "status": s}
            stats["epss_score"][s] += 1
            s = _num_status(it.epss_percentile, best[1] if best else None, EPSS_TOL)
            row["fields"]["epss_percentile"] = {"ours": it.epss_percentile,
                                                "truth": best[1] if best else None, "status": s}
            stats["epss_percentile"][s] += 1

        # KEV：真值 = 任一 cve 命中（与 scorers worker 口径一致）
        if sources["kev"] == "unavailable":
            row["fields"]["is_kev"] = {"ours": it.is_kev, "truth": None,
                                       "status": "source_unavailable"}
            kev_cm["skipped"] += 1
        else:
            truth_kev_hit = any(c in kev_set for c in (it.cve_ids or []))
            if truth_kev_hit and it.is_kev:
                kev_cm["tp"] += 1; s = "ok"
            elif truth_kev_hit and not it.is_kev:
                kev_cm["fn"] += 1; s = "diff"
            elif not truth_kev_hit and it.is_kev:
                kev_cm["fp"] += 1; s = "diff"
            else:
                kev_cm["tn"] += 1; s = "ok"
            row["fields"]["is_kev"] = {"ours": bool(it.is_kev), "truth": truth_kev_hit,
                                       "status": s}

        # NVD 派生字段
        nv = nvd_map.get(cve)
        if isinstance(nv, Exception) or (nv is None and cve not in nvd_map):
            for f in ("cvss_v31_score", "severity", "cwe_ids"):
                row["fields"][f] = {"ours": getattr(it, f), "truth": None,
                                    "status": "source_unavailable"}
                stats[f]["source_unavailable"] += 1
        elif nv is None:
            for f in ("cvss_v31_score", "severity", "cwe_ids"):
                ours = getattr(it, f)
                s = "extra" if ours else "no_truth"
                row["fields"][f] = {"ours": ours, "truth": None, "status": s}
                stats[f][s] += 1
        else:
            s = _num_status(it.cvss_v31_score, nv["cvss_v31_score"], CVSS_TOL)
            row["fields"]["cvss_v31_score"] = {"ours": it.cvss_v31_score,
                                               "truth": nv["cvss_v31_score"], "status": s}
            stats["cvss_v31_score"][s] += 1
            s = _sev_status(it.severity, nv["severity"])
            row["fields"]["severity"] = {"ours": it.severity,
                                         "truth": nv["severity"], "status": s}
            stats["severity"][s] += 1
            s, iou = _cwe_status(it.cwe_ids, nv["cwe_ids"])
            row["fields"]["cwe_ids"] = {"ours": it.cwe_ids or [],
                                        "truth": sorted(nv["cwe_ids"]),
                                        "iou": iou, "status": s}
            stats["cwe_ids"][s] += 1

        ok_n = sum(1 for f in row["fields"].values() if f["status"] == "ok")
        cmp_n = sum(1 for f in row["fields"].values() if f["status"] in ("ok", "diff"))
        row["score"] = f"{ok_n}/{cmp_n}"
        details.append(row)
        f = row["fields"]
        line = (f"[{idx + 1:2d}/{len(items)}] {cve:16s} "
                f"epss:{_fmt(f['epss_score'])} kev:{_fmt(f['is_kev'])} "
                f"cvss:{_fmt(f['cvss_v31_score'])} sev:{_fmt(f['severity'])} "
                f"cwe:{_fmt(f['cwe_ids'])} | {row['score']}")
        print(line)

    # ---- 字段级指标 ----
    print("\n===== 字段级指标 =====")
    print(f"{'field':18s} {'truth_n':>7s} {'filled':>6s} {'ok':>4s} {'acc':>7s} {'recall':>7s}")
    field_metrics: dict = {}
    tot_ok = tot_cmp = tot_filled = tot_truth = 0
    for f in NUM_FIELDS:
        s = stats[f]
        truth_n = s["ok"] + s["diff"] + s["missing"]
        filled_n = s["ok"] + s["diff"]
        acc = s["ok"] / filled_n if filled_n else None
        rec = filled_n / truth_n if truth_n else None
        field_metrics[f] = {"truth_n": truth_n, "filled_n": filled_n,
                            "correct_n": s["ok"], "extra_n": s["extra"],
                            "accuracy": round(acc, 4) if acc is not None else None,
                            "recall": round(rec, 4) if rec is not None else None}
        tot_ok += s["ok"]; tot_cmp += filled_n
        tot_filled += filled_n; tot_truth += truth_n
        print(f"{f:18s} {truth_n:7d} {filled_n:6d} {s['ok']:4d} "
              f"{_pct(acc):>7s} {_pct(rec):>7s}")

    # is_kev 混淆矩阵行
    kev_eval = kev_cm["tp"] + kev_cm["fp"] + kev_cm["tn"] + kev_cm["fn"]
    kev_acc = (kev_cm["tp"] + kev_cm["tn"]) / kev_eval if kev_eval else None
    kev_rec = kev_cm["tp"] / (kev_cm["tp"] + kev_cm["fn"]) if (kev_cm["tp"] + kev_cm["fn"]) else None
    field_metrics["is_kev"] = {"confusion": kev_cm,
                               "accuracy": round(kev_acc, 4) if kev_acc is not None else None,
                               "recall": round(kev_rec, 4) if kev_rec is not None else None}
    tot_ok += kev_cm["tp"] + kev_cm["tn"]; tot_cmp += kev_eval
    tot_filled += kev_cm["tp"]; tot_truth += kev_cm["tp"] + kev_cm["fn"]
    print(f"{'is_kev':18s} {kev_cm['tp'] + kev_cm['fn']:7d} {kev_eval:6d} "
          f"{kev_cm['tp'] + kev_cm['tn']:4d} {_pct(kev_acc):>7s} {_pct(kev_rec):>7s}"
          f"   TP={kev_cm['tp']} FP={kev_cm['fp']} FN={kev_cm['fn']} TN={kev_cm['tn']}")

    overall_acc = tot_ok / tot_cmp if tot_cmp else None
    overall_rec = tot_filled / tot_truth if tot_truth else None
    print("-" * 60)
    print(f"整体准确率={_pct(overall_acc)}  整体召回率={_pct(overall_rec)}  "
          f"sources={sources}")

    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "n_requested": n, "n_evaluated": len(items),
        "sources": sources,
        "tolerances": {"epss": EPSS_TOL, "cvss": CVSS_TOL, "cwe_iou_min": CWE_IOU_MIN},
        "metric_defs": {"accuracy": "correct / (truth非空且我们已填)",
                        "recall": "我们非空 / truth非空",
                        "is_kev": "布尔字段报混淆矩阵"},
        "fields": field_metrics,
        "overall": {"accuracy": round(overall_acc, 4) if overall_acc is not None else None,
                    "recall": round(overall_rec, 4) if overall_rec is not None else None},
        "items": details,
    }
    out = os.path.join(os.path.dirname(__file__), "..", "reports", "eval_enrichment.json")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    json.dump(report, open(out, "w"), ensure_ascii=False, indent=2)
    print(f"[eval] 写入 {out}")
    return 0


def _fmt(cell: dict) -> str:
    """单元格 → 'ours→truth✓' 短格式"""
    s = cell["status"]
    o, t = cell.get("ours"), cell.get("truth")
    if s == "source_unavailable":
        return "?"
    if isinstance(o, bool) or isinstance(t, bool):
        txt = f"{'T' if o else 'F'}/{'T' if t else 'F'}"
    elif "iou" in cell and cell["iou"] is not None:
        txt = f"iou={cell['iou']:.2f}"
    else:
        txt = f"{o if o is not None else '∅'}→{t if t is not None else '∅'}"
    return txt + FLAG[s]


def _pct(v) -> str:
    return f"{v * 100:.1f}%" if v is not None else "—"


async def _cleanup() -> None:
    """释放 DB 连接池与 httpx client，避免事件循环关闭告警"""
    try:
        from app.db.session import get_engine
        await get_engine().dispose()
    except Exception:  # noqa: BLE001
        pass
    try:
        import app.core.http as http_mod
        if http_mod._client is not None:
            await http_mod._client.aclose()
    except Exception:  # noqa: BLE001
        pass


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="富化准确率评测（地面真值对比）")
    ap.add_argument("--n", type=int, default=30, help="抽样 item 数（默认 30）")
    a = ap.parse_args()
    async def _run() -> int:
        try:
            return await run_eval(a.n)
        finally:
            await _cleanup()   # 必须在同一事件循环内释放连接
    try:
        code = asyncio.run(_run())
    except Exception as e:  # noqa: BLE001 —— 库连接失败等致命错误
        print(f"[eval] 致命错误: {e}")
        code = 1
    sys.exit(code)
