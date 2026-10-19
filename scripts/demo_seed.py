#!/usr/bin/env python3
"""演示种子数据：注入代表性 AI 安全漏洞情报，保证无外部数据时也能完整演示

用法: cd backend && ../scripts/demo_seed.py（或 PYTHONPATH=. .venv/bin/python ../scripts/demo_seed.py）
"""
import asyncio
import os
import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from app.collectors.base import RawItemData  # noqa: E402
from app.db.models import Item, Source  # noqa: E402
from app.db.session import get_session_factory, init_db  # noqa: E402
from sqlalchemy import select  # noqa: E402

NOW = datetime.now(timezone.utc)

DEMO_ITEMS = [
    dict(
        item_type="vuln", title="vLLM PyNcclPipe pickle deserialization RCE (CVE-2025-32444)",
        title_zh="vLLM PyNcclPipe pickle 反序列化远程代码执行漏洞",
        summary_zh="vLLM Mooncake 集成中 KV-Cache 传输通道通过未加密 ZeroMQ 监听全部接口并使用 pickle.loads 反序列化，未授权攻击者可远程执行代码。影响 vLLM 0.6.5-0.8.5。",
        summary="vLLM's Mooncake integration listens on all interfaces via unencrypted ZeroMQ and deserializes with pickle.loads — unauthenticated RCE. Affects 0.6.5–0.8.5.",
        url="https://github.com/vllm-project/vllm/security/advisories/GHSA-hjq4-87xh-g4fv",
        published_at=NOW - timedelta(days=160), severity="critical",
        cvss_v31_score=9.8, cvss_v31_vector="CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:H/I:H/A:H",
        epss_score=0.42, epss_percentile=0.97, is_kev=False, has_poc=True,
        exploit_maturity="poc", priority_score=0.91,
        cve_ids=["CVE-2025-32444"], ghsa_ids=["GHSA-HJQ4-87XH-G4FV"], cwe_ids=["CWE-502"],
        vendors=["vllm-project"], products=["vllm"],
        packages=["pkg:pypi/vllm"], affected_versions=">=0.6.5,<=0.8.5; fixed in 0.8.5+",
        ai_relevance_score=0.98, ai_layer="L1",
        owasp_llm=[], owasp_asi=["ASI05"],
        attack_techniques=["T1190", "T1059"], atlas_techniques=["AML.T0043"],
        technique_maturity="demonstrated",
        source_names=["ghsa", "nvd", "cvelistv5"], source_count=3, reliability_score=0.97,
        review_status="confirmed",
        enrichment={"scorers": {"status": "ok", "confidence": 1.0}, "poc": {"status": "ok", "confidence": 0.9},
                    "assets": {"status": "ok"}, "mappings": {"status": "ok"}, "nlp": {"status": "ok"}},
    ),
    dict(
        item_type="vuln", title="Ollama unauthenticated path traversal RCE 'Probllama' (CVE-2024-37032)",
        title_zh="Ollama 未授权路径遍历远程代码执行漏洞（Probllama）",
        summary_zh="Ollama 服务端 /api/pull 接口缺少路径校验，攻击者可上传恶意 manifest 实现任意文件写与远程代码执行。全球上万实例无认证暴露，已被僵尸网络在野利用。",
        summary="Ollama /api/pull lacks path validation — malicious manifest upload leads to arbitrary file write and RCE. 10k+ unauthenticated internet-exposed instances; exploited in the wild.",
        url="https://www.wiz.io/blog/probllama-ollama-vulnerability-cve-2024-37032",
        published_at=NOW - timedelta(days=500), severity="critical",
        cvss_v31_score=9.1, cvss_v31_vector="CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:H/I:H/A:H",
        epss_score=0.87, epss_percentile=0.99, is_kev=True, has_poc=True,
        exploit_maturity="weaponized", priority_score=0.97, kev_date_added=NOW - timedelta(days=300),
        cve_ids=["CVE-2024-37032"], cwe_ids=["CWE-22", "CWE-345"],
        vendors=["ollama"], products=["ollama"], packages=["pkg:github/ollama/ollama"],
        affected_versions="<0.1.34; fixed in 0.1.34",
        ai_relevance_score=0.99, ai_layer="L1", owasp_llm=[], owasp_asi=["ASI05"],
        attack_techniques=["T1190", "T1059", "T1105"], technique_maturity="realized",
        source_names=["ghsa", "nvd", "cisa_kev", "unit42"], source_count=4, reliability_score=1.0,
        review_status="confirmed",
        enrichment={"scorers": {"status": "ok"}, "poc": {"status": "ok"}, "assets": {"status": "ok", "note": "hunter"}},
    ),
    dict(
        item_type="vuln", title="Langflow unauthenticated code validation RCE (CVE-2025-3248)",
        title_zh="Langflow 未认证代码校验接口远程代码执行漏洞",
        summary_zh="Langflow /api/v1/validate/code 接口未认证可访问，AST 解析后 exec 函数定义的 decorator/默认值执行路径可执行任意 Python 代码。已入 CISA KEV，Flodrix 僵尸网络在野利用。",
        summary="Langflow /api/v1/validate/code is unauthenticated; decorator/default-value execution path after AST parsing yields arbitrary code exec. Listed in CISA KEV; exploited by Flodrix botnet.",
        url="https://nvd.nist.gov/vuln/detail/CVE-2025-3248",
        published_at=NOW - timedelta(days=190), severity="critical",
        cvss_v31_score=9.8, epss_score=0.91, epss_percentile=0.99, is_kev=True,
        kev_date_added=NOW - timedelta(days=150), has_poc=True, exploit_maturity="weaponized",
        priority_score=0.98, cve_ids=["CVE-2025-3248"], cwe_ids=["CWE-306", "CWE-94"],
        vendors=["langflow"], products=["langflow"], packages=["pkg:pypi/langflow"],
        affected_versions="<1.3.0; fixed in 1.3.0",
        ai_relevance_score=0.97, ai_layer="L1", owasp_llm=[], owasp_asi=["ASI05"],
        attack_techniques=["T1190", "T1059.007"], technique_maturity="realized",
        source_names=["nvd", "cisa_kev", "trendmicro"], source_count=3, reliability_score=0.98,
        review_status="confirmed",
    ),
    dict(
        item_type="incident", title="EchoLeak — Microsoft 365 Copilot zero-click prompt injection (CVE-2025-32711)",
        title_zh="EchoLeak：Microsoft 365 Copilot 零点击提示注入致数据外泄",
        summary_zh="Aim Labs 发现的首例生产系统零点击提示注入：恶意邮件被 Copilot RAG 检索执行，绕过 XPIA 分类器与链接过滤，自动加载图片经 Teams 代理外带，无交互窃取上下文数据。",
        summary="First zero-click prompt injection in a production system: a malicious email triggers exfiltration when M365 Copilot retrieves it via RAG, bypassing XPIA classifier and link filtering.",
        url="https://www.aim.security/lp/aim-labs-echoleak-blogpost",
        published_at=NOW - timedelta(days=130), severity="high",
        cvss_v31_score=9.3, cve_ids=["CVE-2025-32711"], cwe_ids=["CWE-77"],
        vendors=["microsoft"], products=["microsoft 365 copilot"],
        ai_relevance_score=0.99, ai_layer="L3", owasp_llm=["LLM01", "LLM02"], owasp_asi=["ASI01"],
        attack_techniques=["T1059", "T1567"], atlas_techniques=["AML.T0051.000"],
        technique_maturity="realized", exploit_maturity="poc",
        source_names=["simonwillison", "thehackernews", "nvd"], source_count=3, reliability_score=0.95,
        review_status="confirmed",
    ),
    dict(
        item_type="vuln", title="mcp-remote OS command injection via malicious authorization_endpoint (CVE-2025-6514)",
        title_zh="mcp-remote 恶意 authorization_endpoint 致操作系统命令注入",
        summary_zh="mcp-remote 连接恶意 MCP 服务器时，authorization_endpoint 返回 file: URI 可触发 OS 命令注入，首个真实场景 MCP 客户端整机 RCE。影响 0.0.5–0.1.15。",
        summary="mcp-remote connecting to a malicious MCP server: authorization_endpoint returning a file: URI triggers OS command injection — first real-world MCP client RCE. Affects 0.0.5–0.1.15.",
        url="https://nvd.nist.gov/vuln/detail/CVE-2025-6514",
        published_at=NOW - timedelta(days=95), severity="critical",
        cvss_v31_score=9.6, epss_score=0.12, has_poc=True, exploit_maturity="poc",
        priority_score=0.88, cve_ids=["CVE-2025-6514"], cwe_ids=["CWE-78"],
        vendors=["modelcontextprotocol"], products=["mcp-remote"], packages=["pkg:npm/mcp-remote"],
        affected_versions=">=0.0.5,<=0.1.15",
        ai_relevance_score=0.98, ai_layer="L3", owasp_llm=[], owasp_asi=["ASI04", "ASI05"],
        attack_techniques=["T1190", "T1059"], technique_maturity="demonstrated",
        source_names=["nvd", "jfrog", "ghsa"], source_count=3, reliability_score=0.95,
        review_status="confirmed",
    ),
    dict(
        item_type="vuln", title="PyTorch torch.load weights_only=True bypass RCE (CVE-2025-32434)",
        title_zh="PyTorch torch.load weights_only=True 绕过反序列化 RCE",
        summary_zh="PyTorch ≤2.6.0 中 torch.load 开启 weights_only=True 仍可被绕过实现反序列化 RCE，打破了 weights_only 即安全的普遍认知，影响所有加载不可信模型权重的场景。",
        summary="In PyTorch ≤2.6.0, torch.load with weights_only=True can still be bypassed for deserialization RCE — breaking the assumption that weights_only is safe.",
        url="https://nvd.nist.gov/vuln/detail/CVE-2025-32434",
        published_at=NOW - timedelta(days=180), severity="critical",
        cvss_v31_score=9.8, epss_score=0.08, has_poc=True, exploit_maturity="poc",
        priority_score=0.85, cve_ids=["CVE-2025-32434"], cwe_ids=["CWE-502"],
        vendors=["pytorch"], products=["pytorch"], packages=["pkg:pypi/torch"],
        affected_versions="<=2.6.0; fixed in 2.6.0",
        ai_relevance_score=0.96, ai_layer="L4", owasp_llm=["LLM03"], owasp_asi=["ASI04"],
        attack_techniques=["T1195", "T1059"], technique_maturity="demonstrated",
        source_names=["nvd", "github_poc"], source_count=2, reliability_score=0.9,
    ),
    dict(
        item_type="incident", title="ShadowRay 2.0 — 23万+ Ray 集群被劫持挖矿 (CVE-2023-48022 disputed)",
        title_zh="ShadowRay 2.0：23万+ Ray 集群遭劫持构建 GPU 挖矿僵尸网络",
        summary_zh="Ray Jobs API 无认证 RCE（CVE-2023-48022，官方定性'按设计'的争议 CVE）。IronErn440 组织构建自传播 GPU 挖矿/窃密/DDoS 僵尸网络，蠕虫式跨集群扩散，攻击载荷由 AI 生成。",
        summary="Ray Jobs API unauthenticated RCE (disputed CVE 'by design'). IronErn440 built a self-propagating GPU cryptomining botnet worming across clusters — attack payloads AI-generated.",
        url="https://www.oligo.security/blog/shadowray-2-0",
        published_at=NOW - timedelta(days=25), severity="critical",
        cvss_v31_score=9.8, cve_ids=["CVE-2023-48022"], cwe_ids=["CWE-306"],
        vendors=["anyscale"], products=["ray"], packages=["pkg:pypi/ray"],
        ai_relevance_score=0.98, ai_layer="L6", owasp_llm=[], owasp_asi=["ASI05"],
        attack_techniques=["T1190", "T1496", "T1059"], technique_maturity="realized",
        is_kev=True, has_poc=True, exploit_maturity="weaponized", priority_score=0.96,
        source_names=["oligo", "cisa_kev", "bleepingcomputer"], source_count=3, reliability_score=0.93,
        review_status="confirmed",
    ),
    dict(
        item_type="vuln", title="Milvus Proxy sourceID header auth bypass (CVE-2025-64513)",
        title_zh="Milvus Proxy sourceID 请求头伪造致认证绕过",
        summary_zh="Milvus Proxy 信任客户端 sourceID 头，伪造可获得全集群管理员权限。<2.4.24/2.5.21/2.6.5 全部受影响，网关删除 sourceID 头可临时缓解。",
        summary="Milvus Proxy trusts client-supplied sourceID header — forging it grants full cluster admin. All versions <2.4.24/2.5.21/2.6.5 affected.",
        url="https://nvd.nist.gov/vuln/detail/CVE-2025-64513",
        published_at=NOW - timedelta(days=30), severity="critical",
        cvss_v31_score=9.4, epss_score=0.05, has_poc=False, exploit_maturity="none",
        priority_score=0.78, cve_ids=["CVE-2025-64513"], cwe_ids=["CWE-290", "CWE-306"],
        vendors=["milvus-io"], products=["milvus"], packages=["pkg:go/github.com/milvus-io/milvus"],
        affected_versions="<2.4.24,>=2.5.0<2.5.21,>=2.6.0<2.6.5",
        ai_relevance_score=0.97, ai_layer="L1", owasp_llm=["LLM08"], owasp_asi=["ASI03"],
        attack_techniques=["T1190", "T1078"], technique_maturity="feasible",
        source_names=["nvd", "ghsa"], source_count=2, reliability_score=0.9,
    ),
    dict(
        item_type="article", title="MCP Tool Poisoning: 工具描述注入劫持智能体（Invariant Labs）",
        title_zh="MCP 工具投毒：工具描述中的隐形指令劫持智能体行为",
        summary_zh="Invariant Labs 确立 MCP 工具投毒（TPA）概念：工具描述中嵌入对人不可见、对模型可见的恶意指令，可劫持 Agent 行为、外带数据、覆盖可信服务器指令。聚合平台审核全部失守。",
        summary="Invariant Labs established Tool Poisoning Attack (TPA): instructions invisible to humans but visible to models embedded in tool descriptions can hijack agent behavior and exfiltrate data.",
        url="https://invariantlabs.ai/blog/mcp-security-notification-tool-poisoning-attacks",
        published_at=NOW - timedelta(days=200),
        vendors=["modelcontextprotocol"], products=["mcp server"],
        ai_relevance_score=0.99, ai_layer="L3", owasp_llm=["LLM01"], owasp_asi=["ASI04"],
        atlas_techniques=["AML.T0051.002"], technique_maturity="demonstrated",
        source_names=["embracethered", "thehackernews"], source_count=2, reliability_score=0.85,
    ),
    dict(
        item_type="policy", title="GB/T 45654-2025《网络安全技术 生成式人工智能服务安全基本要求》正式实施",
        title_zh="GB/T 45654-2025《网络安全技术 生成式人工智能服务安全基本要求》正式实施",
        summary_zh="2025年11月1日实施的生成式AI服务安全国家标准：涵盖训练语料安全、模型安全、安全措施与评估方法，配套 GB/T 45652（预训练数据）、GB/T 45674（数据标注）。",
        summary="National standard for generative AI service security effective 2025-11-01: covers training corpus security, model security, safeguards and assessment.",
        url="https://openstd.samr.gov.cn/bzgk/gb/newGbInfo?hcno=45654",
        published_at=NOW - timedelta(days=344),
        ai_relevance_score=0.95, ai_layer="L5",
        source_names=["tc260", "cac_policy"], source_count=2, reliability_score=0.95,
    ),
    dict(
        item_type="incident", title="DeepSeek ClickHouse 未授权访问泄露百万行日志（Wiz）",
        title_zh="DeepSeek ClickHouse 未授权访问暴露百万行日志（含聊天历史与API密钥）",
        summary_zh="Wiz 发现 DeepSeek oauth2callback/dev 子域 9000 端口无认证开放 ClickHouse，暴露百万行日志流：明文聊天历史、API 密钥、后端细节、内部基础设施，数小时内修复。",
        summary="Wiz found DeepSeek's ClickHouse open without auth on port 9000 — a million log lines incl. plaintext chat history, API keys, backend internals. Fixed within hours.",
        url="https://www.wiz.io/blog/wiz-research-exposes-deepseek-database-leak",
        published_at=NOW - timedelta(days=620), severity="high",
        vendors=["deepseek"], products=["deepseek clickhouse"],
        ai_relevance_score=0.92, ai_layer="L3", owasp_llm=["LLM02"], owasp_asi=[],
        attack_techniques=["T1190", "T1005"], technique_maturity="realized",
        source_names=["wiz", "thehackernews"], source_count=2, reliability_score=0.9,
    ),
    dict(
        item_type="incident", title="Unverified: 开源推理框架供应链投毒传闻（多源矛盾待核实）",
        title_zh="未经证实：某开源推理框架镜像仓库疑似投毒，社区报告相互矛盾",
        summary_zh="社区渠道流传某开源推理框架官方镜像仓库遭投毒的说法，但官方公告与仓库签名核验结果相互矛盾，威胁级别与影响面暂无法定论——典型需要人工研判的低置信情报。",
        summary="Community channels report suspected poisoning of an OSS inference framework registry, but official statements and signature checks conflict — threat level undetermined.",
        url="https://example.com/demo/unverified-registry-poisoning",
        published_at=NOW - timedelta(days=2), severity="high",
        vendors=["demo-vendor"], products=["demo-framework"],
        ai_relevance_score=0.9, ai_layer="L4", owasp_asi=["ASI04"],
        source_names=["demo"], source_count=1, reliability_score=0.3,
    ),
    dict(
        item_type="vuln", title="LangChain serialization injection via 'lc' key (GHSA-c67j-w6g6-q2cm)",
        title_zh="LangChain 序列化注入：'lc' 键未转义致任意类实例化与机密泄露",
        summary_zh="LangChain dumps/loads 未转义 'lc' 键，攻击者可注入构造器实例化可信命名空间内任意 Serializable 类，secrets_from_env 可泄露环境机密；修复引入 allowed_objects 白名单。",
        summary="LangChain dumps/loads didn't escape the 'lc' key — injected constructors instantiate arbitrary Serializable classes and secrets_from_env leaks secrets.",
        url="https://github.com/langchain-ai/langchain/security/advisories/GHSA-c67j-w6g6-q2cm",
        published_at=NOW - timedelta(days=290), severity="high",
        cvss_v31_score=8.3, ghsa_ids=["GHSA-C67J-W6G6-Q2CM"], cwe_ids=["CWE-502"],
        vendors=["langchain-ai"], products=["langchain"], packages=["pkg:pypi/langchain-core"],
        affected_versions="<0.3.81",
        ai_relevance_score=0.99, ai_layer="L1", owasp_llm=["LLM03"], owasp_asi=["ASI04"],
        attack_techniques=["T1195", "T1059"], technique_maturity="demonstrated", has_poc=True,
        exploit_maturity="poc", priority_score=0.82,
        source_names=["ghsa", "nvd"], source_count=2, reliability_score=0.92,
    ),
]


async def main() -> None:
    """演示种子走真实 ingest 管线：RawItem/ItemSource/去重/下游富化全链路留痕。
    诚信约束：不手写 is_kev/epss/has_poc（由真实 KEV/EPSS 源富化），
    source_names 如实为 ["demo"]，extra.is_demo=true 标记以便统计剔除。"""
    await init_db()
    async with get_session_factory()() as db:
        src = (await db.execute(select(Source).where(Source.name == "demo"))).scalar_one_or_none()
        if not src:
            src = Source(name="demo", source_type="demo", tier=1, lang="mixed",
                         url="local://demo", poll_interval_sec=86400 * 365, enabled=False,
                         state={"tags": ["demo"]})
            db.add(src)
            await db.commit()
            await db.refresh(src)
        raws = [RawItemData(
            title=d.get("title") or d.get("title_zh") or "",
            url=d.get("url"), native_id=d.get("url") or d["title"],
            published_at=d.get("published_at"), lang=d.get("lang") or "en",
            summary=d.get("summary"), content_text=d.get("content_text") or d.get("summary"),
            item_type=d.get("item_type", "article"),
            cve_ids=d.get("cve_ids", []), cwe_ids=d.get("cwe_ids", []),
            vendors=d.get("vendors", []), products=d.get("products", []),
            severity=d.get("severity"), cvss_v31_score=d.get("cvss_v31_score"),
            raw={"demo": True},
        ) for d in DEMO_ITEMS]
        from app.services.ingest import ingest_items
        stats = await ingest_items(db, src, raws)
        urls = [d.get("url") for d in DEMO_ITEMS if d.get("url")]
        if urls:
            from sqlalchemy import text as _t
            await db.execute(_t(
                "UPDATE items SET extra = jsonb_set(COALESCE(extra,'{}'::jsonb),"
                " '{is_demo}', 'true'::jsonb) WHERE url = ANY(:urls)"),
                {"urls": urls})
        await db.commit()
        # HITL 演示位：未经证实条目写入"跑了但不完整"的富化态 + needs_review，
        # 复核队列可现场演示 确认/回炉/重富化/撤销 闭环（is_demo 已标记，统计剔除）
        from sqlalchemy import text as _t2
        await db.execute(_t2(
            "UPDATE items SET review_status='needs_review', confidence=0.38, "
            " enrichment=jsonb_build_object("
            "   'nlp',       jsonb_build_object('status','ok','confidence',0.62,'note','zh summary ok'),"
            "   'scorers',   jsonb_build_object('status','partial','confidence',0.30,'note','无官方评分源可查'),"
            "   'ai_classify',jsonb_build_object('status','partial','confidence',0.22,'note','层级归属存疑 L3/L4'),"
            "   'mappings',  jsonb_build_object('status','skipped','confidence',0,'note','no cwes'),"
            "   'poc',       jsonb_build_object('status','skipped','confidence',0,'note','no cve_ids'),"
            "   'assets',    jsonb_build_object('status','skipped','confidence',0,'note','no products to map'),"
            "   'papers',    jsonb_build_object('status','skipped','confidence',0,'note','no related papers'),"
            "   'chain',     jsonb_build_object('status','skipped','confidence',0,'note','no chain basis'))"
            " WHERE url = 'https://example.com/demo/unverified-registry-poisoning'"))
        await db.commit()
    print(f"seeded via ingest pipeline: {stats}")





if __name__ == "__main__":
    asyncio.run(main())
