"""安全情报标识符提取与规范化（跨源实体对齐的基础）"""
from __future__ import annotations

import hashlib
import re
import unicodedata
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

CVE_RE = re.compile(r"\bCVE-\d{4}-\d{4,7}\b", re.I)
GHSA_RE = re.compile(r"\bGHSA-[0-9a-z]{4}-[0-9a-z]{4}-[0-9a-z]{4}\b", re.I)
CNVD_RE = re.compile(r"\bCNVD-\d{4}-\d{4,6}\b", re.I)
CNNVD_RE = re.compile(r"\bCNNVD-\d{6}-\d{3}\b", re.I)
EDB_RE = re.compile(r"\bEDB-ID[:\s]*(\d{4,6})\b|\bexploit-db\.com/exploits/(\d{4,6})\b", re.I)
CWE_RE = re.compile(r"\bCWE-\d{1,4}\b", re.I)
CAPEC_RE = re.compile(r"\bCAPEC-\d{1,4}\b", re.I)
ATTACK_RE = re.compile(r"\bT\d{4}(?:\.\d{3})?\b")
ATLAS_RE = re.compile(r"\bAML\.T\d{4}(?:\.\d{3})?\b", re.I)
CPE_RE = re.compile(r"cpe:2\.3:[aoh]:[^\s,;]+", re.I)
ARXIV_RE = re.compile(r"\b(?:arXiv:)?(\d{4}\.\d{4,5})(?:v\d+)?\b")

TRACKING_PARAMS = {
    "utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content",
    "fbclid", "gclid", "spm", "ref", "ref_src", "mc_cid", "mc_eid", "_hsenc", "_hsmi",
}


def extract_ids(text: str) -> dict[str, list[str]]:
    """从任意文本提取安全标识符集合"""
    if not text:
        return {k: [] for k in ("cve", "ghsa", "cnvd", "cnnvd", "edb", "cwe", "capec", "attack", "atlas", "cpe", "arxiv")}
    edb = [m.group(1) or m.group(2) for m in EDB_RE.finditer(text)]
    return {
        "cve": sorted({m.upper() for m in CVE_RE.findall(text)}),
        "ghsa": sorted({m.upper() for m in GHSA_RE.findall(text)}),
        "cnvd": sorted({m.upper() for m in CNVD_RE.findall(text)}),
        "cnnvd": sorted({m.upper() for m in CNNVD_RE.findall(text)}),
        "edb": sorted(set(edb)),
        "cwe": sorted({m.upper() for m in CWE_RE.findall(text)}),
        "capec": sorted({m.upper() for m in CAPEC_RE.findall(text)}),
        "attack": sorted({m.upper() for m in ATTACK_RE.findall(text) if m.upper().startswith("T1")}),
        "atlas": sorted({m.upper() for m in ATLAS_RE.findall(text)}),
        "cpe": sorted(set(CPE_RE.findall(text))),
        "arxiv": sorted(set(ARXIV_RE.findall(text))),
    }


def normalize_url(url: str | None) -> str | None:
    """URL 规范化：小写 scheme/host、去追踪参数、去 fragment、去尾斜杠"""
    if not url:
        return None
    try:
        parts = urlsplit(url.strip())
        scheme = parts.scheme.lower() or "https"
        netloc = parts.netloc.lower()
        if netloc.startswith("www."):
            netloc = netloc[4:]
        query = urlencode(sorted((k, v) for k, v in parse_qsl(parts.query) if k.lower() not in TRACKING_PARAMS))
        path = parts.path.rstrip("/") or "/"
        return urlunsplit((scheme, netloc, path, query, ""))
    except Exception:  # noqa: BLE001
        return url.strip()


def url_sha256(url: str | None) -> str | None:
    norm = normalize_url(url)
    return hashlib.sha256(norm.encode()).hexdigest() if norm else None


def text_sha256(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def title_fingerprint(title: str) -> str:
    """标题指纹：NFKC→小写→去标点空白"""
    if not title:
        return ""
    norm = unicodedata.normalize("NFKC", title).lower()
    norm = re.sub(r"[^\w\u4e00-\u9fff]+", "", norm)
    return hashlib.sha256(norm.encode()).hexdigest()


def simhash64(text: str) -> int:
    """SimHash，裁剪到有符号 int64 范围（DB BigInteger）"""
    mask = (1 << 63) - 1
    try:
        from simhash import Simhash
        return Simhash(text[:2000]).value & mask
    except Exception:  # noqa: BLE001
        tokens = re.findall(r"\w+", (text or "")[:2000].lower())
        v = [0] * 64
        for t in tokens:
            h = int(hashlib.md5(t.encode()).hexdigest(), 16)
            for i in range(64):
                v[i] += 1 if (h >> i) & 1 else -1
        return sum((1 << i) for i in range(64) if v[i] > 0) & mask


def hamming(a: int, b: int) -> int:
    return bin(a ^ b).count("1")
