"""冒烟测试：不依赖外部服务的单元逻辑"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from app.core.ids import extract_ids, normalize_url, title_fingerprint, simhash64, hamming
from app.core.taxonomy import classify, is_ai_related


def test_extract_ids():
    ids = extract_ids("CVE-2025-32444 affects vLLM, related to CWE-502 and CAPEC-586, see GHSA-hjq4-87xh-g4fv and T1190")
    assert "CVE-2025-32444" in ids["cve"]
    assert "GHSA-HJQ4-87XH-G4FV" in ids["ghsa"]
    assert "CWE-502" in ids["cwe"]
    assert "CAPEC-586" in ids["capec"]
    assert "T1190" in ids["attack"]


def test_normalize_url():
    assert normalize_url("HTTPS://WWW.Example.COM/a/?utm_source=x&b=1#frag") == "https://example.com/a?b=1"


def test_fingerprint():
    assert title_fingerprint("vLLM RCE!") == title_fingerprint("vllm rce")


def test_simhash():
    assert hamming(simhash64("vllm remote code execution"), simhash64("vllm remote code execution")) == 0


def test_taxonomy():
    r = classify("Ollama unauthenticated RCE vulnerability allows remote code execution via model file", ["ollama"])
    assert r["ai_layer"] == "L1" and r["ai_relevance_score"] > 0.5
    r2 = classify("prompt injection attack on LLM agent 提示词注入")
    assert r2["ai_layer"] in ("L2", "L3") and "LLM01" in r2["owasp_llm"]
    assert is_ai_related("vLLM pickle deserialization RCE")


def test_taxonomy_non_ai():
    r = classify("Apache httpd path traversal", [])
    assert r["ai_relevance_score"] < 0.3
