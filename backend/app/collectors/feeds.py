"""内容型源采集器：RSS/Atom 通用、Reddit、厂商 CSAF、中文政策源"""
from __future__ import annotations

import asyncio
import json
import os
import re
import subprocess
from datetime import datetime, timedelta, timezone

import feedparser
from dateutil import parser as dtparser

from app.collectors.base import BaseCollector, RawItemData
from app.core.http import fetch
from app.core.logging import get_logger
from app.db.models import Source
from app.services.ingest import extract_body

log = get_logger("collectors.feeds")


def _dt(s) -> datetime | None:
    if not s:
        return None
    try:
        d = dtparser.parse(str(s)) if isinstance(s, str) else None
        if d:
            return d if d.tzinfo else d.replace(tzinfo=timezone.utc)
    except Exception:  # noqa: BLE001
        return None
    return None


def _dt_from_entry(e) -> datetime | None:
    for k in ("published_parsed", "updated_parsed", "created_parsed"):
        t = getattr(e, k, None) or e.get(k)
        if t:
            try:
                return datetime(*t[:6], tzinfo=timezone.utc)
            except Exception:  # noqa: BLE001
                pass
    return _dt(e.get("published") or e.get("updated"))


# ============ 通用 RSS/Atom ============

class RssCollector(BaseCollector):
    name = "rss"

    async def collect(self, source: Source) -> tuple[list[RawItemData], dict]:
        state = source.state or {}
        resp = await fetch(source.url, etag=state.get("etag"), last_modified=state.get("last_modified"))
        new_state = {"etag": resp.headers.get("ETag"), "last_modified": resp.headers.get("Last-Modified")}
        if resp.status_code == 304 or resp.status_code >= 400:
            return [], {**new_state, "cursor": state.get("cursor")}
        feed = feedparser.parse(resp.content)
        items: list[RawItemData] = []
        sem = asyncio.Semaphore(4)
        cursor = _dt(state.get("cursor")) or (datetime.now(timezone.utc) - timedelta(days=30))

        async def enrich(e) -> RawItemData | None:
            title = (e.get("title") or "").strip()
            if not title:
                return None
            link = e.get("link")
            guid = e.get("id") or link or title
            pub = _dt_from_entry(e)
            if pub and pub < cursor:
                return None
            content = ""
            for c in (e.get("content") or []):
                if c.get("value"):
                    content = c["value"]
                    break
            if not content:
                content = e.get("summary") or e.get("description") or ""
            # 拉正文（限量）
            if link and len(content) < 1500:
                async with sem:
                    try:
                        r2 = await fetch(link)
                        if r2.status_code == 200:
                            full = extract_body(r2.text, link)
                            if full and len(full) > len(content):
                                content = full
                    except Exception:  # noqa: BLE001
                        pass
            return RawItemData(
                title=title, url=link, native_id=guid[:250], author=e.get("author"),
                published_at=pub, content_text=content[:20000],
                lang=source.lang, raw={"rss": {"feed": source.name}},
                item_type="policy" if source.source_type == "policy" else
                          "article" if source.source_type in ("blog_rss", "mailing_list", "social") else "article",
            )

        results = await asyncio.gather(*[enrich(e) for e in feed.entries[:80]], return_exceptions=True)
        items = [r for r in results if isinstance(r, RawItemData)]
        new_state["cursor"] = datetime.now(timezone.utc).isoformat()
        return items, new_state


# ============ Reddit ============

class RedditCollector(RssCollector):
    name = "reddit"

    async def collect(self, source: Source) -> tuple[list[RawItemData], dict]:
        # Reddit .rss 激进限流，低频跑
        return await super().collect(source)


# ============ 厂商公告 ============

class NvidiaPsirtCollector(BaseCollector):
    name = "nvidia_psirt"

    async def collect(self, source: Source) -> tuple[list[RawItemData], dict]:
        repo_dir = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))),
            source.state.get("repo_dir") or "data/nvidia-psirt")
        items: list[RawItemData] = []
        if not os.path.exists(os.path.join(repo_dir, ".git")):
            r = subprocess.run(["git", "clone", "--depth", "1", source.url, repo_dir],
                               capture_output=True, text=True, timeout=1200)
            if r.returncode != 0:
                log.warning("nvidia_clone_failed", err=r.stderr[:200])
                return [], {}
            since = datetime.now(timezone.utc) - timedelta(days=365)
        else:
            subprocess.run(["git", "-C", repo_dir, "pull", "--ff-only"], capture_output=True, text=True, timeout=300)
            since = dtparser.parse(source.state.get("cursor", "2000-01-01")).replace(tzinfo=timezone.utc) \
                if source.state.get("cursor") else datetime.now(timezone.utc) - timedelta(days=30)
        for root, _, fs in os.walk(repo_dir):
            for f in fs:
                if f.endswith(".json"):
                    try:
                        d = json.load(open(os.path.join(root, f), encoding="utf-8"))
                        it = self._parse_csaf(d, f)
                        if it and (not it.published_at or it.published_at >= since):
                            items.append(it)
                    except Exception:  # noqa: BLE001
                        continue
                elif f.endswith(".md"):
                    try:
                        txt = open(os.path.join(root, f), encoding="utf-8").read()
                        mtime = datetime.fromtimestamp(os.path.getmtime(os.path.join(root, f)), timezone.utc)
                        if mtime >= since and ("CVE-" in txt):
                            items.append(RawItemData(
                                title=f"[NVIDIA] {f.replace('.md','')}", native_id=f"nv-{f}",
                                published_at=mtime, content_text=txt[:15000], lang="en",
                                raw={"nvidia": {"file": f}}, item_type="advisory"))
                    except Exception:  # noqa: BLE001
                        continue
        return items, {"cursor": datetime.now(timezone.utc).isoformat()}

    def _parse_csaf(self, d: dict, fname: str) -> RawItemData | None:
        doc = d.get("document", {})
        tid = (doc.get("tracking", {}) or {}).get("id") or fname
        title = doc.get("title") or tid
        vulns = d.get("vulnerabilities", [])
        cves = [v.get("cve") for v in vulns if v.get("cve")]
        if not cves and "CVE-" not in title:
            return None
        notes = " ".join(n.get("text", "") for n in doc.get("notes", []) if n.get("text"))
        prods = []
        for p in (d.get("product_tree", {}) or {}).get("branches", [])[:30]:
            if p.get("name"):
                prods.append(p["name"])
        return RawItemData(
            title=f"[NVIDIA] {title}", native_id=tid, published_at=_dt(doc.get("tracking", {}).get("initial_release_date")),
            content_text=(notes or title)[:8000], lang="en",
            raw={"csaf": {"id": tid, "refs": [r.get("url") for r in doc.get("references", [])][:8]}},
            item_type="advisory", cve_ids=cves, products=prods[:10],
        )


class MsrcCollector(BaseCollector):
    name = "msrc"
    AI_HINTS = ("copilot", "azure openai", "machine learning", "deep learning", "semantic kernel", "ai-assisted", "generative ai")

    async def collect(self, source: Source) -> tuple[list[RawItemData], dict]:
        now = datetime.now(timezone.utc)
        ym = now.strftime("%Y-%b")
        state = source.state or {}
        if state.get("ym") == ym:
            return [], state
        resp = await fetch(f"{source.url}/cvrf/{ym}")
        if resp.status_code != 200:
            log.warning("msrc_fetch", code=resp.status_code, ym=ym)
            return [], state
        items: list[RawItemData] = []
        doc = resp.json()
        for v in doc.get("Vulnerability", []):
            cve = v.get("CVE")
            title = v.get("Title", {}).get("Value") or (v.get("Title") if isinstance(v.get("Title"), str) else cve)
            notes = " ".join(n.get("Value", "") for n in v.get("Notes", []) if isinstance(n, dict))
            hay = (title or "") + " " + notes
            ai_hit = any(re.search(r"\b" + re.escape(h) + r"\b", hay.lower()) for h in self.AI_HINTS)
            sev = None
            for t in v.get("Threats", []):
                if t.get("Type") == 3:
                    sev = str(t.get("Description", {}).get("Value", "")).lower()
            kb = ""
            for r in v.get("Remediations", []):
                if r.get("Description"):
                    kb = str(r["Description"])
            items.append(RawItemData(
                title=f"[MSRC] {title or cve}", url=f"https://msrc.microsoft.com/update-guide/vulnerability/{cve}",
                native_id=cve or f"msrc-{title}", published_at=_dt(v.get("RevisionHistory", [{}])[0].get("Date")) if v.get("RevisionHistory") else None,
                content_text=(notes or title or "")[:6000], lang="en",
                raw={"msrc": {"kb": kb, "ai_hint": ai_hit}}, item_type="advisory",
                cve_ids=[cve] if cve else [], severity=sev if sev in ("critical", "important", "moderate", "low") else None,
            ))
        return items, {"ym": ym, "count": len(items)}


# ============ 中文政策源 ============

class PolicyCollector(RssCollector):
    name = "policy"

    async def collect(self, source: Source) -> tuple[list[RawItemData], dict]:
        # 先试标准 RSS
        try:
            items, st = await super().collect(source)
            if items:
                return items, st
        except Exception as e:  # noqa: BLE001
            log.debug("policy_rss_fallback", src=source.name, error=str(e)[:100])
        # 兜底：抓站点首页提取政策链接（source.url 可能是 rss.xml，RSS 挂时抓它没意义）
        home = source.state.get("home_url") or source.url
        if re.search(r"(rss|feed|atom)(\.[a-z]+)?$|\.xml$", home):
            home = re.sub(r"/[^/]*$", "/", home)  # 退到站点根
        resp = await fetch(home)
        if resp.status_code != 200:
            return [], {}
        html = resp.text
        links = re.findall(r'<a[^>]+href="([^"]+)"[^>]*>([^<]{10,80})</a>', html)
        items: list[RawItemData] = []
        host = home.rstrip("/").split("/")[2]
        base = f"https://{host}" if host else home
        seen = set(source.state.get("seen", []))
        for href, text in links[:40]:
            text = re.sub(r"\s+", " ", text).strip()
            if not text or len(text) < 8:
                continue
            url = href if href.startswith("http") else base + href
            if url in seen:
                continue
            items.append(RawItemData(
                title=f"[政策] {text}", url=url, native_id=url[-120:],
                published_at=None, content_text=text, lang="zh",
                raw={"policy": {"page": source.url}}, item_type="policy"))
            seen.add(url)
        return items, {"seen": sorted(seen)[-2000:]}
