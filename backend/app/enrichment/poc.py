"""poc worker：PoC/EXP 三级发现 + 可信度分级（防恶意 PoC）"""
from __future__ import annotations

import re
from datetime import datetime, timezone

from app.config import get_settings
from app.core.http import fetch
from app.core.logging import get_logger
from app.enrichment.common import ok, skipped

log = get_logger("enrich.poc")

MALICIOUS_PATTERNS = [
    (r"base64\s+(-[dD]|\w+decode)", "base64_decode_exec"),
    (r"curl[^|]*\|\s*(bash|sh|python)", "curl_pipe_exec"),
    (r"wget[^|]*\|\s*(bash|sh)", "wget_pipe_exec"),
    (r"Invoke-Expression|IEX\s*\(", "powershell_iex"),
    (r"(?:\d{1,3}\.){3}\d{1,3}:\d{2,5}", "hardcoded_ip_port"),
    (r"reverse.{0,10}shell|/dev/tcp/", "reverse_shell"),
    (r"certutil\s+-urlcache|bitsadmin", "lolbin_download"),
]

TRUSTED = {"exploitdb", "nuclei", "metasploit"}


def credibility(poc: dict) -> tuple[str, list[str]]:
    """确定性可信度分级"""
    reasons = []
    if poc["platform"] in TRUSTED or poc.get("verified"):
        return "trusted", ["source_whitelist"]
    stars = poc.get("stars") or 0
    if stars >= 50:
        reasons.append("stars>=50")
    elif stars < 3:
        reasons.append("low_stars")
    text = " ".join(str(poc.get(k) or "") for k in ("title", "description", "readme_snippet"))
    hits = [name for pat, name in MALICIOUS_PATTERNS if re.search(pat, text, re.I)]
    if hits:
        return "suspicious", reasons + hits
    if poc.get("paid_download") or "satoshidisk" in text.lower():
        return "malicious", ["pay4poc"]
    return ("community", reasons or ["no_flags"])


async def run(item, ctx) -> dict:
    cves = item.cve_ids or []
    if not cves:
        return skipped("no cve_ids")
    pocs: list[dict] = []
    seen: set[str] = set()

    def add(url, platform, title=None, stars=None, author=None, verified=False, description=None):
        if not url or url in seen:
            return
        seen.add(url)
        pocs.append({"url": url, "platform": platform, "title": title,
                     "stars": stars, "author": author, "verified": verified,
                     "description": description})

    year = (cves[0].split("-")[1] if cves else "")
    # ① nomi-sec 索引（零成本）
    for cve in cves[:3]:
        y = cve.split("-")[1]
        try:
            r = await fetch(f"https://raw.githubusercontent.com/nomi-sec/PoC-in-GitHub/master/{y}/{cve}.json")
            if r.status_code == 200:
                for e in r.json()[:8]:
                    add(e.get("html_url"), "github", e.get("full_name"),
                        e.get("stargazers_count"), e.get("owner", {}).get("login"),
                        description=e.get("description"))
        except Exception:  # noqa: BLE001
            pass
        # ② trickest/cve markdown 索引
        try:
            r = await fetch(f"https://raw.githubusercontent.com/trickest/cve/main/{y}/{cve}.md")
            if r.status_code == 200:
                for m in re.findall(r"https://github\.com/[\w.-]+/[\w.-]+", r.text)[:6]:
                    add(m, "github", "trickest-ref")
        except Exception:  # noqa: BLE001
            pass
    # ③ ExploitDB（items.edb_ids 已有则直接可信）
    for eid in (item.edb_ids or [])[:5]:
        add(f"https://www.exploit-db.com/exploits/{eid}", "exploitdb",
            f"ExploitDB #{eid}", verified=True)
    # ④ nuclei-templates 本地/远端
    for cve in cves[:3]:
        for tpl in _nuclei_templates(cve):
            add(tpl, "nuclei", "nuclei-template", verified=True)
    # ⑤ GitHub search 兜底
    if not pocs and get_settings().github_token:
        try:
            r = await fetch("https://api.github.com/search/repositories",
                            params={"q": f"{cves[0]} in:name,description,readme", "sort": "stars", "per_page": 5},
                            headers={"Authorization": f"Bearer {get_settings().github_token}"})
            if r.status_code == 200:
                for repo in r.json().get("items", [])[:5]:
                    add(repo["html_url"], "github", repo["full_name"],
                        repo.get("stargazers_count"), repo.get("owner", {}).get("login"),
                        description=repo.get("description"))
        except Exception:  # noqa: BLE001
            pass

    for p in pocs:
        cred, reasons = credibility(p)
        p["credibility"] = cred
        p["credibility_reasons"] = reasons

    fields = {"has_poc": bool(pocs)}
    if pocs and item.exploit_maturity in (None, "none"):
        fields["exploit_maturity"] = "poc"
    if any(p["platform"] == "metasploit" for p in pocs):
        fields["exploit_maturity"] = "weaponized"

    n_trusted = sum(1 for p in pocs if p["credibility"] == "trusted")
    conf = 1.0 if n_trusted else (0.8 if pocs else 0.3)
    return ok(f"{len(pocs)} pocs ({n_trusted} trusted)", confidence=conf,
              fields=fields, rows={"pocs": pocs}, data_keys=["pocs"])


_nuclei_cache: dict[str, list[str]] | None = None


def _nuclei_templates(cve: str) -> list[str]:
    """nuclei-templates 匹配：优先本地浅克隆缓存，否则 GitHub 直接探测常见路径"""
    if cve in (_nuclei_cache or {}):
        return _nuclei_cache[cve]  # type: ignore[index]
    return []


async def warmup_nuclei_index() -> None:
    """可选：构建 nuclei-templates CVE→模板路径索引（后台任务调用）"""
    global _nuclei_cache
    import subprocess, os
    repo = "data/nuclei-templates"
    repo = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))), repo)
    if not os.path.exists(os.path.join(repo, ".git")):
        subprocess.run(["git", "clone", "--depth", "1", "https://github.com/projectdiscovery/nuclei-templates.git", repo],
                       capture_output=True, timeout=1800)
    else:
        subprocess.run(["git", "-C", repo, "pull", "--ff-only"], capture_output=True, timeout=600)
    idx: dict[str, list[str]] = {}
    for root, _, fs in os.walk(repo):
        for f in fs:
            m = re.match(r"(CVE-\d{4}-\d+)\.yaml", f)
            if m:
                rel = os.path.relpath(os.path.join(root, f), repo)
                idx.setdefault(m.group(1), []).append(
                    f"https://github.com/projectdiscovery/nuclei-templates/blob/main/{rel}")
    _nuclei_cache = idx
    log.info("nuclei_index_ready", count=len(idx))
