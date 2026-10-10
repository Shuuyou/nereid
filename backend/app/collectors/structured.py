"""结构化源采集器：cvelistV5 / NVD / GHSA / OSV / KEV / ExploitDB / arXiv / HN"""
from __future__ import annotations

import asyncio
import csv
import io
import json
import os
import subprocess
import zipfile
from datetime import datetime, timedelta, timezone

import feedparser
from dateutil import parser as dtparser

from app.collectors.base import BaseCollector, RawItemData
from app.config import get_settings
from app.core.http import fetch
from app.core.logging import get_logger
from app.db.models import Source

log = get_logger("collectors.structured")


def _dt(s: str | None) -> datetime | None:
    if not s:
        return None
    try:
        d = dtparser.parse(s)
        return d if d.tzinfo else d.replace(tzinfo=timezone.utc)
    except Exception:  # noqa: BLE001
        return None


# ============ cvelistV5（git 准实时，~7min 官方增量）============

class CvelistCollector(BaseCollector):
    name = "cvelistv5"

    async def collect(self, source: Source) -> tuple[list[RawItemData], dict]:
        repo_dir = source.state.get("repo_dir") or "data/cvelistV5"
        repo_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))), repo_dir)
        os.makedirs(repo_dir, exist_ok=True)
        git_url = source.url

        def _git(*args: str) -> str:
            return subprocess.run(["git", "-C", repo_dir, *args], capture_output=True, text=True, timeout=300).stdout

        items: list[RawItemData] = []
        if not os.path.exists(os.path.join(repo_dir, ".git")):
            r = subprocess.run(["git", "clone", "--depth", "1", git_url, repo_dir],
                               capture_output=True, text=True, timeout=3600)
            if r.returncode != 0:
                raise RuntimeError(f"clone failed: {r.stderr[:300]}")
            # 首跑：只处理最近 2 天 delta 目录
            since_days = 2
        else:
            _git("fetch", "--depth", "2", "origin", "main") or _git("fetch", "origin", "main")
            diff = subprocess.run(["git", "-C", repo_dir, "diff", "--name-status", "HEAD", "origin/main"],
                                  capture_output=True, text=True, timeout=120).stdout
            changed = [l.split("\t")[-1] for l in diff.splitlines() if l.strip() and "cves/" in l and l.split("\t")[-1].endswith(".json")]
            subprocess.run(["git", "-C", repo_dir, "reset", "--hard", "origin/main"],
                           capture_output=True, text=True, timeout=300)
            for rel in changed[:3000]:
                fp = os.path.join(repo_dir, rel)
                if os.path.exists(fp):
                    it = self._parse_cve5(fp)
                    if it:
                        items.append(it)
            return items, {"last_sync": datetime.now(timezone.utc).isoformat()}

        # 首跑增量：扫 cves 下 delta 目录
        delta_root = os.path.join(repo_dir, "cves", "deltaCves")
        files = []
        if os.path.isdir(delta_root):
            for root, _, fs in os.walk(delta_root):
                for f in fs:
                    if f.endswith(".json"):
                        files.append(os.path.join(root, f))
        if not files:
            # fallback：按 mtime 找最近文件
            cves_root = os.path.join(repo_dir, "cves")
            newest = []
            for root, _, fs in os.walk(cves_root):
                for f in fs:
                    if f.startswith("CVE-") and f.endswith(".json"):
                        p = os.path.join(root, f)
                        newest.append((os.path.getmtime(p), p))
            newest.sort(reverse=True)
            cutoff = datetime.now().timestamp() - since_days * 86400
            files = [p for t, p in newest[:500] if t > cutoff]
        for fp in files[:2000]:
            it = self._parse_cve5(fp)
            if it:
                items.append(it)
        return items, {"last_sync": datetime.now(timezone.utc).isoformat()}

    def _parse_cve5(self, path: str) -> RawItemData | None:
        try:
            d = json.load(open(path, encoding="utf-8"))
            meta = d.get("cveMetadata", {})
            cve_id = meta.get("cveId") or os.path.basename(path).replace(".json", "")
            cna = d.get("containers", {}).get("cna", {})
            title = cna.get("title") or f"{cve_id}"
            desc = next((x["value"] for x in cna.get("descriptions", []) if x.get("lang") == "en"),
                        (cna.get("descriptions") or [{}])[0].get("value", ""))
            cwes = [p.get("cweId") for x in cna.get("problemTypes", [])
                    for p in x.get("descriptions", []) if p.get("cweId")]
            vendors, products = [], []
            versions_txt = []
            for a in cna.get("affected", []):
                if a.get("vendor") and a["vendor"] != "n/a":
                    vendors.append(a["vendor"])
                if a.get("product") and a["product"] != "n/a":
                    products.append(a["product"])
                for v in a.get("versions", []):
                    if v.get("version") and v["version"] != "n/a":
                        versions_txt.append(f"{a.get('product','')}:{v['version']}({v.get('status','')})")
            score31 = score40 = None
            vec31 = vec40 = None
            sev = None
            for m in cna.get("metrics", []):
                for key, attr in (("cvssV3_1", "v31"), ("cvssV4_0", "v40")):
                    if key in m:
                        mm = m[key]
                        if attr == "v31":
                            score31, vec31 = mm.get("baseScore"), mm.get("vectorString")
                            sev = sev or (mm.get("baseSeverity") or "").lower()
                        else:
                            score40, vec40 = mm.get("baseScore"), mm.get("vectorString")
                            sev = sev or (mm.get("baseSeverity") or "").lower()
            refs = [r.get("url") for r in cna.get("references", []) if r.get("url")]
            return RawItemData(
                title=title, url=refs[0] if refs else f"https://www.cve.org/CVERecord?id={cve_id}",
                native_id=cve_id, published_at=_dt(meta.get("datePublished")),
                content_text=desc, lang="en", raw={"cve5": {"refs": refs[:10], "adp_keys": list(d.get("containers", {}).get("adp", [{}])[0].keys()) if d.get("containers", {}).get("adp") else []}},
                item_type="vuln", cve_ids=[cve_id], cwe_ids=cwes,
                vendors=sorted(set(vendors)), products=sorted(set(products)),
                severity=sev, cvss_v31_score=score31, cvss_v31_vector=vec31,
                cvss_v40_score=score40, cvss_v40_vector=vec40,
            )
        except Exception as e:  # noqa: BLE001
            log.debug("cve5_parse_skip", path=path[-60:], error=str(e)[:120])
            return None


# ============ NVD（增量 lastMod）============

class NvdCollector(BaseCollector):
    name = "nvd"

    async def collect(self, source: Source) -> tuple[list[RawItemData], dict]:
        s = get_settings()
        now = datetime.now(timezone.utc)
        last = _dt(source.state.get("cursor")) or (now - timedelta(hours=26))
        end = now - timedelta(minutes=2)
        headers = {"apiKey": s.nvd_api_key} if s.nvd_api_key else {}
        items: list[RawItemData] = []
        start_idx = 0
        while True:
            resp = await fetch(source.url, headers=headers, params={
                "lastModStartDate": last.strftime("%Y-%m-%dT%H:%M:%S.000") + "+00:00",
                "lastModEndDate": end.strftime("%Y-%m-%dT%H:%M:%S.000") + "+00:00",
                "resultsPerPage": "2000", "startIndex": str(start_idx),
            })
            if resp.status_code != 200:
                raise RuntimeError(f"NVD {resp.status_code}: {resp.text[:200]}")
            data = resp.json()
            for v in data.get("vulnerabilities", []):
                it = self._parse(v.get("cve", {}))
                if it:
                    items.append(it)
            total = data.get("totalResults", 0)
            start_idx += data.get("resultsPerPage", 2000)
            if start_idx >= total:
                break
        return items, {"cursor": end.isoformat()}

    def _parse(self, c: dict) -> RawItemData | None:
        cid = c.get("id")
        if not cid:
            return None
        desc = next((x["value"] for x in c.get("descriptions", []) if x.get("lang") == "en"), "")
        cwes = [w["description"][0]["value"] for w in c.get("weaknesses", [])
                if w.get("description") and w["description"][0].get("value", "").startswith("CWE")]
        products, vendors, cpes = [], [], []
        for cfg in c.get("configurations", []):
            for node in cfg.get("nodes", []):
                for m in node.get("cpeMatch", []):
                    crit = m.get("criteria", "")
                    cpes.append(crit)
                    parts = crit.split(":")
                    if len(parts) >= 5:
                        vendors.append(parts[3])
                        products.append(parts[4])
        metrics = c.get("metrics", {})
        score31 = score40 = sev = vec31 = vec40 = None
        for key in ("cvssMetricV31", "cvssMetricV30"):
            if metrics.get(key):
                mm = metrics[key][0]["cvssData"]
                score31, vec31 = mm.get("baseScore"), mm.get("vectorString")
                sev = (metrics[key][0].get("baseSeverity") or mm.get("baseSeverity") or "").lower()
        if metrics.get("cvssMetricV40"):
            mm = metrics["cvssMetricV40"][0]["cvssData"]
            score40, vec40 = mm.get("baseScore"), mm.get("vectorString")
        return RawItemData(
            title=f"{cid}: {desc[:120]}", url=f"https://nvd.nist.gov/vuln/detail/{cid}",
            native_id=cid, published_at=_dt(c.get("published")), content_text=desc, lang="en",
            raw={"nvd": {"refs": [r.get("url") for r in c.get("references", [])][:10], "cpes": cpes[:20]}},
            item_type="vuln", cve_ids=[cid], cwe_ids=cwes,
            vendors=sorted(set(vendors))[:10], products=sorted(set(products))[:10],
            severity=sev, cvss_v31_score=score31, cvss_v31_vector=vec31,
            cvss_v40_score=score40, cvss_v40_vector=vec40,
        )


# ============ GHSA ============

class GhsaCollector(BaseCollector):
    name = "ghsa"

    async def collect(self, source: Source) -> tuple[list[RawItemData], dict]:
        s = get_settings()
        cursor = source.state.get("cursor") or (datetime.now(timezone.utc) - timedelta(hours=48)).isoformat()
        headers = {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"}
        if s.github_token:
            headers["Authorization"] = f"Bearer {s.github_token}"
        items: list[RawItemData] = []
        url = f"{source.url}?updated=>{cursor}&per_page=100"
        pages = 0
        while url and pages < 10:
            resp = await fetch(url, headers=headers)
            if resp.status_code != 200:
                raise RuntimeError(f"GHSA {resp.status_code}")
            for a in resp.json():
                it = self._parse(a)
                if it:
                    items.append(it)
            link = resp.headers.get("Link", "")
            url = None
            for part in link.split(","):
                if 'rel="next"' in part:
                    url = part.split("<")[1].split(">")[0]
            pages += 1
        return items, {"cursor": datetime.now(timezone.utc).isoformat()}

    def _parse(self, a: dict) -> RawItemData | None:
        ghsa = a.get("ghsa_id")
        if not ghsa:
            return None
        cwes = [f"CWE-{c['cwe_id']}" if str(c.get("cwe_id", "")).isdigit() else c.get("cwe_id")
                for c in a.get("cwes", [])]
        pkgs = []
        products = []
        for v in a.get("vulnerabilities", []):
            pkg = v.get("package", {})
            if pkg.get("name"):
                products.append(pkg["name"])
                pkgs.append(f"pkg:{pkg.get('ecosystem','').lower()}/{pkg['name']}")
        cvss = a.get("cvss") or {}
        cvss4 = a.get("cvss_severities", {}).get("cvss_v4", {})
        sev = (a.get("severity") or "").lower() or None
        return RawItemData(
            title=a.get("summary") or ghsa, url=a.get("html_url"), native_id=ghsa,
            published_at=_dt(a.get("published_at")), content_text=a.get("description") or "",
            lang="en", raw={"ghsa": {"epss": a.get("epss"), "references": a.get("references", [])[:10]}},
            item_type="advisory", cve_ids=[a["cve_id"]] if a.get("cve_id") else [],
            ghsa_ids=[ghsa], cwe_ids=[c for c in cwes if c],
            products=sorted(set(products)), packages=pkgs,
            severity=sev, cvss_v31_score=cvss.get("score"), cvss_v31_vector=cvss.get("vector_string"),
            cvss_v40_score=cvss4.get("score"), cvss_v40_vector=cvss4.get("vector_string"),
        )


# ============ OSV ============

AI_HINTS = ("ollama", "vllm", "langchain", "transformers", "mlflow", "jupyter", "pytorch",
            "tensorflow", "huggingface", "gradio", "ray", "mcp", "prompt", "llm", "sglang",
            "litellm", "langflow", "flowise", "dify", "milvus", "chromadb", "chromadb")


class OsvCollector(BaseCollector):
    name = "osv"
    ECOSYSTEMS = ["PyPI", "npm", "Go", "Maven", "crates.io"]

    async def collect(self, source: Source) -> tuple[list[RawItemData], dict]:
        cursor = _dt(source.state.get("cursor")) or (datetime.now(timezone.utc) - timedelta(days=7))
        items: list[RawItemData] = []
        for eco in self.ECOSYSTEMS:
            try:
                url = f"https://osv-vulnerabilities.storage.googleapis.com/{eco}/all.zip"
                resp = await fetch(url, rate_limit=True)
                if resp.status_code != 200:
                    log.warning("osv_zip_skip", eco=eco, code=resp.status_code)
                    continue
                zf = zipfile.ZipFile(io.BytesIO(resp.content))
                cnt = 0
                for name in zf.namelist():
                    if not name.endswith(".json"):
                        continue
                    try:
                        d = json.loads(zf.read(name))
                        mod = _dt(d.get("modified"))
                        if not mod or mod <= cursor:
                            continue
                        text = (d.get("summary") or "") + " " + (d.get("details") or "")
                        aliases = [a for a in d.get("aliases", [])]
                        hay = text.lower() + " " + " ".join(aliases).lower()
                        if not any(h in hay for h in AI_HINTS):
                            continue
                        it = self._parse(d, eco)
                        if it:
                            items.append(it)
                            cnt += 1
                    except Exception:  # noqa: BLE001
                        continue
                log.info("osv_eco_done", eco=eco, count=cnt)
            except Exception as e:  # noqa: BLE001
                log.error("osv_eco_failed", eco=eco, error=str(e)[:200])
        return items, {"cursor": datetime.now(timezone.utc).isoformat()}

    def _parse(self, d: dict, eco: str) -> RawItemData | None:
        vid = d.get("id")
        if not vid:
            return None
        aliases = d.get("aliases", [])
        cves = [a for a in aliases if a.upper().startswith("CVE-")]
        ghsas = [a for a in aliases if a.upper().startswith("GHSA-")]
        pkgs, products = [], []
        for a in d.get("affected", []):
            p = a.get("package", {})
            if p.get("name"):
                products.append(p["name"])
                pkgs.append(f"pkg:{p.get('ecosystem', eco).lower()}/{p['name']}")
        return RawItemData(
            title=d.get("summary") or vid,
            url=f"https://osv.dev/vulnerability/{vid}", native_id=vid,
            published_at=_dt(d.get("published")),
            content_text=(d.get("details") or d.get("summary") or "")[:8000], lang="en",
            raw={"osv": {"aliases": aliases, "severity": d.get("severity")}},
            item_type="advisory", cve_ids=cves, ghsa_ids=ghsas,
            products=sorted(set(products)), packages=pkgs,
            severity=None,
        )


# ============ CISA KEV（GitHub 镜像兜底 cisa.gov）============

KEV_URLS = [
    "https://www.cisa.gov/sites/default/files/feeds/known_exploited_vulnerabilities.json",
    "https://raw.githubusercontent.com/cisagov/kev-data/develop/known_exploited_vulnerabilities.json",
]


class KevCollector(BaseCollector):
    name = "cisa_kev"

    async def collect(self, source: Source) -> tuple[list[RawItemData], dict]:
        data = None
        for url in KEV_URLS:
            try:
                resp = await fetch(url)
                if resp.status_code == 200:
                    data = resp.json()
                    break
            except Exception as e:  # noqa: BLE001
                log.warning("kev_fetch_alt_failed", url=url[:60], error=str(e)[:120])
        if not data:
            raise RuntimeError("all KEV sources failed")
        known = set(source.state.get("known_cves", []))
        first_run = not known
        items: list[RawItemData] = []
        cutoff = datetime.now(timezone.utc) - timedelta(days=30)
        for v in data.get("vulnerabilities", []):
            cid = v.get("cveID")
            if not cid or cid in known:
                continue
            added = _dt(v.get("dateAdded"))
            if first_run and added and added < cutoff:
                continue  # 首跑只收近30天
            items.append(RawItemData(
                title=f"[KEV] {v.get('vulnerabilityName', cid)}",
                url=f"https://www.cve.org/CVERecord?id={cid}",
                native_id=cid, published_at=added,
                content_text=f"{v.get('vulnerabilityName','')}\n{v.get('shortDescription','')}\nRequired: {v.get('requiredAction','')}\nRansomware: {v.get('knownRansomwareCampaignUse','Unknown')}",
                lang="en", raw={"kev": v}, item_type="vuln", cve_ids=[cid],
                vendors=[v.get("vendorProject")] if v.get("vendorProject") else [],
                products=[v.get("product")] if v.get("product") else [],
            ))
            known.add(cid)
        return items, {"known_cves": sorted(known)[-5000:]}


# ============ ExploitDB ============

class ExploitDbCollector(BaseCollector):
    name = "exploitdb"

    async def collect(self, source: Source) -> tuple[list[RawItemData], dict]:
        import re
        resp = await fetch(source.url)
        if resp.status_code != 200:
            raise RuntimeError(f"EDB {resp.status_code}")
        known = set(source.state.get("known_ids", []))
        first_run = not known
        cutoff = datetime.now(timezone.utc) - timedelta(days=90)
        items: list[RawItemData] = []
        rdr = csv.DictReader(io.StringIO(resp.text))
        for row in rdr:
            eid = row.get("id", "").strip()
            if not eid or eid in known:
                continue
            d = _dt(row.get("date"))
            if first_run and d and d < cutoff:
                continue
            cves = re.findall(r"CVE-\d{4}-\d{4,7}", (row.get("codes") or "") + " " + (row.get("description") or ""), re.I)
            items.append(RawItemData(
                title=f"[EDB-{eid}] {row.get('description','')}",
                url=f"https://www.exploit-db.com/exploits/{eid}", native_id=eid,
                author=row.get("author"), published_at=d,
                content_text=f"{row.get('description','')} | type={row.get('type')} platform={row.get('platform')}",
                lang="en", raw={"edb": row}, item_type="exploit",
                cve_ids=sorted({c.upper() for c in cves}),
            ))
            known.add(eid)
        return items, {"known_ids": sorted(known)[-20000:]}


# ============ arXiv ============

class ArxivCollector(BaseCollector):
    name = "arxiv_cs_cr"

    async def collect(self, source: Source) -> tuple[list[RawItemData], dict]:
        from app.collectors.seeds import ARXIV_QUERIES
        cursor = _dt(source.state.get("cursor")) or (datetime.now(timezone.utc) - timedelta(days=7))
        items: list[RawItemData] = []
        for q in ARXIV_QUERIES:
            try:
                resp = await fetch(source.url, params={
                    "search_query": q, "sortBy": "submittedDate", "sortOrder": "descending",
                    "start": 0, "max_results": 50})
                if resp.status_code != 200:
                    continue
                feed = feedparser.parse(resp.text)
                for e in feed.entries:
                    pub = _dt(e.get("published"))
                    if pub and pub <= cursor:
                        continue
                    aid = (e.get("id") or "").split("/abs/")[-1]
                    items.append(RawItemData(
                        title=e.get("title", "").replace("\n", " ").strip(),
                        url=e.get("id"), native_id=aid,
                        author=", ".join(a.get("name", "") for a in e.get("authors", [])[:5]),
                        published_at=pub, content_text=e.get("summary", "").strip()[:6000],
                        lang="en", raw={"arxiv": {"id": aid, "categories": [t.get("term") for t in e.get("tags", [])]}},
                        item_type="paper",
                    ))
            except Exception as e:  # noqa: BLE001
                log.warning("arxiv_query_failed", q=q[:50], error=str(e)[:120])
            await asyncio.sleep(3)
        return items, {"cursor": datetime.now(timezone.utc).isoformat()}


# ============ HackerNews ============

class HnCollector(BaseCollector):
    name = "hackernews"

    async def collect(self, source: Source) -> tuple[list[RawItemData], dict]:
        from app.collectors.seeds import HN_QUERIES
        cursor = _dt(source.state.get("cursor")) or (datetime.now(timezone.utc) - timedelta(hours=48))
        items: list[RawItemData] = []
        for q in HN_QUERIES:
            try:
                resp = await fetch(source.url, params={"query": q, "tags": "story", "hitsPerPage": "30"})
                if resp.status_code != 200:
                    continue
                for h in resp.json().get("hits", []):
                    ts = h.get("created_at_i")
                    if ts and datetime.fromtimestamp(ts, timezone.utc) <= cursor:
                        continue
                    items.append(RawItemData(
                        title=f"[HN {h.get('points',0)}↑] {h.get('title','')}",
                        url=h.get("url") or f"https://news.ycombinator.com/item?id={h.get('objectID')}",
                        native_id=h.get("objectID"), author=h.get("author"),
                        published_at=datetime.fromtimestamp(ts, timezone.utc) if ts else None,
                        content_text=h.get("title", ""), lang="en",
                        raw={"hn": {"points": h.get("points"), "comments": h.get("num_comments")}},
                        item_type="article",
                    ))
            except Exception as e:  # noqa: BLE001
                log.warning("hn_query_failed", q=q, error=str(e)[:120])
        return items, {"cursor": datetime.now(timezone.utc).isoformat()}


# ============ AVID（AI 漏洞/事件专用库）============

class AvidCollector(BaseCollector):
    name = "avid"

    async def collect(self, source: Source) -> tuple[list[RawItemData], dict]:
        repo_dir = "data/avid-db"
        repo_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))), repo_dir)
        git_url = "https://github.com/avidml/avid-db.git"
        items: list[RawItemData] = []
        if not os.path.exists(os.path.join(repo_dir, ".git")):
            r = subprocess.run(["git", "clone", "--depth", "1", git_url, repo_dir],
                               capture_output=True, text=True, timeout=600)
            if r.returncode != 0:
                log.warning("avid_clone_failed", err=r.stderr[:200])
                return [], {}
            since = datetime.now(timezone.utc) - timedelta(days=180)
        else:
            subprocess.run(["git", "-C", repo_dir, "pull", "--ff-only"], capture_output=True, text=True, timeout=300)
            since = _dt(source.state.get("cursor")) or (datetime.now(timezone.utc) - timedelta(days=30))
        for root, _, fs in os.walk(repo_dir):
            for f in fs:
                if not f.endswith(".json"):
                    continue
                try:
                    d = json.load(open(os.path.join(root, f), encoding="utf-8"))
                    pub = _dt(d.get("published_date") or d.get("date_published"))
                    if pub and pub < since:
                        continue
                    desc = d.get("description") or d.get("summary") or ""
                    items.append(RawItemData(
                        title=f"[AVID] {d.get('title', f)}", url=f"https://avidml.org{'' if f.startswith('http') else '/'}",
                        native_id=f, published_at=pub, content_text=desc[:6000], lang="en",
                        raw={"avid": d}, item_type="incident",
                    ))
                except Exception:  # noqa: BLE001
                    continue
        return items, {"cursor": datetime.now(timezone.utc).isoformat()}
