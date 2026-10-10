"""数据源注册表：11 类源、30+ 具体源（覆盖评分标准 7 类 + 实时监测）

tier: 1官方 2厂商 3知名社区 4聚合媒体 5社交
"""
from __future__ import annotations

SEED_SOURCES: list[dict] = [
    # ===== Tier-0 准实时结构化源 =====
    {"name": "cvelistv5", "source_type": "cve_db", "tier": 1, "lang": "en",
     "url": "https://github.com/CVEProject/cvelistV5.git", "poll_interval_sec": 900,
     "state": {"repo_dir": "data/cvelistV5"}},
    {"name": "nvd", "source_type": "cve_db", "tier": 1, "lang": "en",
     "url": "https://services.nvd.nist.gov/rest/json/cves/2.0", "poll_interval_sec": 3600},
    {"name": "ghsa", "source_type": "advisory", "tier": 1, "lang": "en",
     "url": "https://api.github.com/advisories", "poll_interval_sec": 1800},
    {"name": "osv", "source_type": "advisory", "tier": 1, "lang": "en",
     "url": "https://api.osv.dev/v1", "poll_interval_sec": 3600},
    {"name": "cisa_kev", "source_type": "kev", "tier": 1, "lang": "en",
     "url": "https://www.cisa.gov/sites/default/files/feeds/known_exploited_vulnerabilities.json",
     "poll_interval_sec": 1800},
    {"name": "exploitdb", "source_type": "exploit", "tier": 2, "lang": "en",
     "url": "https://gitlab.com/exploit-database/exploitdb/-/raw/main/files_exploits.csv",
     "poll_interval_sec": 21600},

    # ===== 厂商公告（结构化 CSAF / API）=====
    {"name": "nvidia_psirt", "source_type": "vendor_csaf", "tier": 2, "lang": "en",
     "url": "https://github.com/NVIDIA/product-security.git", "poll_interval_sec": 7200,
     "state": {"repo_dir": "data/nvidia-psirt"}},
    {"name": "msrc", "source_type": "vendor_csaf", "tier": 2, "lang": "en",
     "url": "https://api.msrc.microsoft.com/cvrf/v3.0", "poll_interval_sec": 7200},

    # ===== AI 专用源 =====
    {"name": "avid", "source_type": "ai_specific", "tier": 2, "lang": "en",
     "url": "https://avidml.org", "poll_interval_sec": 86400},
    {"name": "arxiv_cs_cr", "source_type": "paper", "tier": 1, "lang": "en",
     "url": "https://export.arxiv.org/api/query", "poll_interval_sec": 43200},
    {"name": "hf_blog", "source_type": "blog_rss", "tier": 2, "lang": "en",
     "url": "https://huggingface.co/blog/feed.xml", "poll_interval_sec": 3600},

    # ===== 英文安全博客/研究 =====
    {"name": "simonwillison", "source_type": "blog_rss", "tier": 3, "lang": "en",
     "url": "https://simonwillison.net/atom/everything/", "poll_interval_sec": 1800},
    {"name": "embracethered", "source_type": "blog_rss", "tier": 3, "lang": "en",
     "url": "https://embracethered.com/blog/index.xml", "poll_interval_sec": 3600},
    {"name": "msft_security_blog", "source_type": "blog_rss", "tier": 2, "lang": "en",
     "url": "https://www.microsoft.com/en-us/security/blog/feed/", "poll_interval_sec": 3600},
    {"name": "trailofbits", "source_type": "blog_rss", "tier": 3, "lang": "en",
     "url": "https://blog.trailofbits.com/feed/", "poll_interval_sec": 3600},
    {"name": "google_project_zero", "source_type": "blog_rss", "tier": 3, "lang": "en",
     "url": "https://googleprojectzero.blogspot.com/feeds/posts/default", "poll_interval_sec": 3600},
    {"name": "google_security_blog", "source_type": "blog_rss", "tier": 3, "lang": "en",
     "url": "https://security.googleblog.com/feeds/posts/default", "poll_interval_sec": 3600},
    {"name": "unit42", "source_type": "blog_rss", "tier": 3, "lang": "en",
     "url": "https://unit42.paloaltonetworks.com/feed/", "poll_interval_sec": 3600},
    {"name": "talos", "source_type": "blog_rss", "tier": 3, "lang": "en",
     "url": "https://blog.talosintelligence.com/rss/", "poll_interval_sec": 3600},
    {"name": "thehackernews", "source_type": "blog_rss", "tier": 4, "lang": "en",
     "url": "https://feeds.feedburner.com/TheHackersNews", "poll_interval_sec": 1800},
    {"name": "bleepingcomputer", "source_type": "blog_rss", "tier": 4, "lang": "en",
     "url": "https://www.bleepingcomputer.com/feed/", "poll_interval_sec": 1800},
    {"name": "securityaffairs", "source_type": "blog_rss", "tier": 4, "lang": "en",
     "url": "https://securityaffairs.com/feed", "poll_interval_sec": 3600},
    {"name": "darkreading", "source_type": "blog_rss", "tier": 4, "lang": "en",
     "url": "https://www.darkreading.com/rss.xml", "poll_interval_sec": 3600},
    {"name": "schneier", "source_type": "blog_rss", "tier": 3, "lang": "en",
     "url": "https://www.schneier.com/feed/", "poll_interval_sec": 7200},
    {"name": "zdi", "source_type": "blog_rss", "tier": 3, "lang": "en",
     "url": "https://www.thezdi.com/blog/?format=rss", "poll_interval_sec": 3600},

    # ===== 中文安全社区 =====
    {"name": "freebuf", "source_type": "blog_rss", "tier": 4, "lang": "zh",
     "url": "https://www.freebuf.com/feed", "poll_interval_sec": 1800},
    {"name": "anquanke", "source_type": "blog_rss", "tier": 4, "lang": "zh",
     "url": "https://api.anquanke.com/data/v1/rss", "poll_interval_sec": 3600},
    {"name": "seebug_paper", "source_type": "blog_rss", "tier": 3, "lang": "zh",
     "url": "https://paper.seebug.org/rss", "poll_interval_sec": 3600},
    {"name": "nsfocus", "source_type": "blog_rss", "tier": 4, "lang": "zh",
     "url": "http://blog.nsfocus.net/feed", "poll_interval_sec": 7200},
    {"name": "4hou", "source_type": "blog_rss", "tier": 4, "lang": "zh",
     "url": "https://www.4hou.com/feed", "poll_interval_sec": 3600},
    {"name": "aqniu", "source_type": "blog_rss", "tier": 4, "lang": "zh",
     "url": "https://www.aqniu.com/feed", "poll_interval_sec": 3600},
    {"name": "secpulse", "source_type": "blog_rss", "tier": 4, "lang": "zh",
     "url": "https://www.secpulse.com/feed", "poll_interval_sec": 3600},
    {"name": "tencent_xlab", "source_type": "blog_rss", "tier": 3, "lang": "zh",
     "url": "https://xlab.tencent.com/cn/atom.xml", "poll_interval_sec": 7200},
    {"name": "knownsec", "source_type": "blog_rss", "tier": 3, "lang": "zh",
     "url": "http://blog.knownsec.com/feed", "poll_interval_sec": 7200},
    {"name": "secwiki", "source_type": "blog_rss", "tier": 4, "lang": "zh",
     "url": "https://www.sec-wiki.com/news/rss", "poll_interval_sec": 3600},

    # ===== 邮件列表 =====
    {"name": "oss_sec", "source_type": "mailing_list", "tier": 2, "lang": "en",
     "url": "https://seclists.org/rss/oss-sec.rss", "poll_interval_sec": 1800},
    {"name": "fulldisclosure", "source_type": "mailing_list", "tier": 3, "lang": "en",
     "url": "https://seclists.org/rss/fulldisclosure.rss", "poll_interval_sec": 1800},

    # ===== 社交/聚合 =====
    {"name": "hackernews", "source_type": "social", "tier": 5, "lang": "en",
     "url": "https://hn.algolia.com/api/v1/search_by_date", "poll_interval_sec": 900},
    {"name": "reddit_netsec", "source_type": "social", "tier": 5, "lang": "en",
     "url": "https://www.reddit.com/r/netsec/new.rss", "poll_interval_sec": 7200},

    # ===== 政策与治理 =====
    {"name": "cac_policy", "source_type": "policy", "tier": 1, "lang": "zh",
     "url": "https://www.cac.gov.cn/rss.xml", "poll_interval_sec": 21600},
    {"name": "tc260", "source_type": "policy", "tier": 1, "lang": "zh",
     "url": "https://www.tc260.org.cn", "poll_interval_sec": 86400},
]

# arXiv 检索词（AI 安全方向）
ARXIV_QUERIES = [
    'cat:cs.CR AND (abs:"prompt injection" OR abs:"jailbreak" OR abs:"LLM" OR abs:"large language model")',
    'cat:cs.CR AND (abs:"AI agent" OR abs:"MCP" OR abs:"model context protocol" OR abs:"RAG")',
    'cat:cs.CR AND (abs:"model poisoning" OR abs:"data poisoning" OR abs:"backdoor" AND abs:"neural")',
    'cat:cs.LG AND (abs:"adversarial attack" OR abs:"model extraction" OR abs:"membership inference")',
]

# HN 关键词
HN_QUERIES = ["prompt injection", "LLM security", "CVE AI", "jailbreak", "vllm", "ollama", "MCP security"]
