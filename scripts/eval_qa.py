#!/usr/bin/env python3
"""多跳问答评测：基于库内真实 CVE 的桥接型问题评测

口径声明（诚实标注）：
- 题集为自建（覆盖单跳事实/多跳桥接/枚举/推理四类），expect 为关键词子串命中
- cite_precision 校验"引用编号存在于返回 citations 集合"（编号存在性，非内容正确性）
- 适用于回归与演示；对外宣称时须注明"自建题集口径"，盲评集另行人工标注

用法: cd backend && .venv/bin/python ../scripts/eval_qa.py [--n 20] [--live]
  --live 走 POST /api/qa/chat；默认直接调 query_agent.stream_answer 收集 done 事件
输出：准确率、延迟分布、逐题结果 JSON
"""
import asyncio
import json
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))


# 内置多跳评测集（基于库内真实 CVE 的 KG 可答问题；自建口径见模块 docstring）
EVAL_QUESTIONS = [
    # 单跳事实
    {"q": "CVE-2025-32444 影响哪个组件？严重度是多少？", "type": "single",
     "expect": ["vllm", "critical", "9.8"], "hops": 1},
    {"q": "Ollama Probllama 漏洞的 CVE 编号是什么？", "type": "single",
     "expect": ["CVE-2024-37032"], "hops": 1},
    {"q": "CVE-2025-3248 是否已被在野利用？", "type": "single",
     "expect": ["kev", "是", "在野"], "hops": 1},
    # 多跳桥接（需跨文档/实体推理）
    {"q": "vLLM 的 PyNcclPipe RCE 漏洞（CVE-2025-32444）利用了哪类弱点，对应的 ATT&CK 攻击技术是什么？如何修复？",
     "type": "multi", "expect": ["CWE-502", "反序列化", "T1190", "0.8.5"], "hops": 3},
    {"q": "我们内网部署了 Ollama 和 Milvus 2.4，请分析面临的已公开漏洞风险及处置建议。",
     "type": "multi", "expect": ["CVE-2024-37032", "CVE-2025-64513", "升级", "认证"], "hops": 2},
    {"q": "MCP 生态今年曝出的安全漏洞有哪些共性？给出开发和部署侧的防护建议。",
     "type": "multi", "expect": ["CVE-2025-6514", "投毒", "供应链", "最小权限"], "hops": 3},
    {"q": "哪些 AI 基础设施漏洞已被 CISA KEV 收录并遭在野利用？它们的攻击链有什么共同点？",
     "type": "multi", "expect": ["CVE-2025-3248", "CVE-2024-37032", "CVE-2023-48022", "T1190"], "hops": 3},
    {"q": "提示注入类事件（如 EchoLeak）与基础设施类漏洞在缓解措施上有什么本质差异？",
     "type": "multi", "expect": ["RAG", "过滤", "输入", "补丁"], "hops": 2},
    # ---- 扩展集：资产暴露 / 攻击链 / 政策标准 / 时效枚举 ----
    {"q": "Ollama 暴露在公网的资产面临 Probllama 漏洞风险时，应该优先做哪三件事？",
     "type": "single", "expect": ["升级", "0.1.34", "认证"], "hops": 1, "cat": "asset"},
    {"q": "CVE-2024-37032 从初始访问到命令执行再到资源劫持的完整攻击链是怎样的？",
     "type": "multi", "expect": ["T1190", "T1059", "T1105", "遍历"], "hops": 3, "cat": "chain"},
    {"q": "《生成式人工智能服务安全基本要求》对训练数据和生成内容提出了哪些合规要求？",
     "type": "single", "expect": ["训练数据", "安全", "内容"], "hops": 1, "cat": "policy"},
    {"q": "列出库中 severity 为 critical 且有公开 PoC 的 AI 相关漏洞。",
     "type": "single", "expect": ["CVE-", "critical", "PoC"], "hops": 1, "cat": "enum"},
]


async def run_eval(live: bool, n: int) -> None:
    results = []
    qs = EVAL_QUESTIONS[:n]
    for i, item in enumerate(qs):
        t0 = time.time()
        answer, trace, cites = "", {}, []
        if live:
            import httpx
            async with httpx.AsyncClient(timeout=180) as c:
                async with c.stream("POST", "http://localhost:8000/api/qa/chat",
                                    json={"question": item["q"], "deep": True}) as r:
                    buf = ""
                    async for line in r.aiter_lines():
                        if line.startswith("data:"):
                            try:
                                d = json.loads(line[5:].strip())
                                if isinstance(d, dict) and "answer" in d:
                                    answer = d["answer"]
                                    trace = d.get("trace", {})
                                    cites = d.get("citations", [])
                            except json.JSONDecodeError:
                                buf += line
        else:
            try:
                from app.rag.query_agent import stream_answer
                async for ev in stream_answer(item["q"], f"eval-{i}", [], deep=True):
                    if ev.get("type") == "done":
                        answer = ev["data"].get("answer", "")
                        trace = ev["data"].get("trace", {})
                        cites = ev["data"].get("citations", [])
            except Exception as e:  # noqa: BLE001
                answer = f"__ERROR__ {e}"
        latency = time.time() - t0
        a = answer.lower()
        hits = [k for k in item["expect"] if k.lower() in a]
        # 引用精度：答案中的 [n] 引用必须在 citations 集合内
        import re as _re
        cite_n = set(_re.findall(r"\[(\d+)\]", answer))
        cite_ok = len(cite_n) == 0 or len(cite_n - {str(c.get("n")) for c in cites}) == 0
        results.append({
            "q": item["q"][:60], "type": item["type"], "hops": item["hops"],
            "cite_precision": cite_ok, "trace_steps": len(trace.get("steps", [])),
            "expect_hits": f"{len(hits)}/{len(item['expect'])}",
            "hit_rate": round(len(hits) / len(item["expect"]), 2),
            "latency_s": round(latency, 1), "missed": [k for k in item["expect"] if k.lower() not in a],
        })
        print(f"[{i+1}/{len(qs)}] {item['type']:6s} hits={len(hits)}/{len(item['expect'])} "
              f"lat={latency:.1f}s missed={[k for k in item['expect'] if k.lower() not in a]}")

    acc = sum(r["hit_rate"] for r in results) / len(results)
    multi = [r for r in results if r["type"] == "multi"]
    macc = sum(r["hit_rate"] for r in multi) / len(multi) if multi else 0
    lat = sorted(r["latency_s"] for r in results)
    print("\n===== 评测结果 =====")
    cite_acc = sum(1 for r in results if r.get("cite_precision")) / len(results)
    tool_ev = sum(1 for r in results if r["trace_steps"] >= 3) / len(results)
    print(f"整体命中率: {acc:.1%}  |  多跳命中率: {macc:.1%}  |  p50={lat[len(lat)//2]}s p95={lat[-1]}s")
    print(f"引用精确率: {cite_acc:.1%}  |  推理链完备率(≥3步): {tool_ev:.1%}")
    out = os.path.join(os.path.dirname(__file__), "..", "reports", "eval_qa.json")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    json.dump({"overall": acc, "multi_hop": macc, "cite_precision": cite_acc,
               "trace_coverage": tool_ev, "results": results}, open(out, "w"), ensure_ascii=False, indent=2)
    print(f"写入 {out}")


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=len(EVAL_QUESTIONS))
    ap.add_argument("--live", action="store_true")
    a = ap.parse_args()
    asyncio.run(run_eval(a.live, a.n))
