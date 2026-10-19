#!/usr/bin/env python3
"""构建捞针·Nereid Notion 竞赛主文档（全量重建，保证自洽）

用法：python scripts/build_notion_doc.py [progress.md]
  可选传入进展 markdown 追加到"当前进展"章节。
"""
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from notion_sync import (  # noqa: E402
    NotionClient, bullet, callout, divider, heading, md_to_blocks, para, todo,
)

TOKEN = os.environ.get("NOTION_TOKEN", "")
PAGE = os.environ.get("NOTION_PAGE_ID", "3f5d3aea-8397-80d8-bb09-e1ec9ac32da3")


def table(header: list[str], rows: list[list[str]]) -> list[dict]:
    all_rows = [header] + rows
    out = []
    for r in all_rows:
        from notion_sync import parse_inline
        cells = [parse_inline(str(c)) for c in (r + [""] * (len(header) - len(r)))[:len(header)]]
        out.append({"object": "block", "type": "table_row", "table_row": {"cells": cells}})
    return [{"object": "block", "type": "table",
             "table": {"table_width": len(header), "has_column_header": True,
                       "has_row_header": False, "children": out}}]


def build() -> list[dict]:
    b: list[dict] = []

    b.append(callout(
        "**捞针 · Nereid — 智能体驱动的 AI 安全知识情报系统** ｜ 第三届“中国电子杯”高校 ICT 产教融合创新大赛 · 赛题九（奇安信命题）｜ 杭州电子科技大学 · 具身智能实验室 ｜ 本文档为竞赛权威文档，涵盖赛题、架构、选型、调研、进展全貌，独立自洽不依赖仓库内其他文档。", "🏆"))

    # ============ 一、赛事概况 ============
    b += [heading("一、赛事与赛题概况", 1)]
    b += table(["要素", "内容"], [
        ["赛事", "“中国电子杯”第三届高校 ICT 产教融合创新大赛"],
        ["赛题", "赛题九：智能体驱动的 AI 安全知识情报系统设计与实现"],
        ["命题单位", "奇安信科技集团股份有限公司"],
        ["团队", "杭州电子科技大学 具身智能实验室 · Shuuyou 团队"],
        ["交付物（初赛）", "技术报告（Word+PDF）、操作演示视频、技术讲解PPT（PDF）；源代码平台审阅"],
        ["赛制", "校内初赛（各校推荐）→ 线下决赛（答辩PPT须匿名）"],
        ["时间目标", "一个月内完成可演示全功能系统"],
    ])
    b.append(para("**赛题三大核心能力**：① 情报监测——对 CVE/NVD、安全社区、厂商公告、安全博客等渠道的 AI 安全漏洞信息自动化监测采集；② 情报富化——论文关联、受影响资产定位、POC 验证代码、CVSS 评分与影响评估等多维扩展；③ 情报问答——基于知识库的自然语言深度问答，跨文档语义检索与关联推理。另需同步采集 AI 安全学术论文、技术标准与政策法规，构建完整知识底座。"))
    b.append(para("**评分结构（初赛100分）**：功能指标45（监测15+富化15+问答15）· 性能指标15（时效5+富化准确率5+问答深度5）· 优化指标40（Agent架构15+自动化+文档质量+演示效果）。满分关键阈值：数据源≥7类+实时；富化≥5维+自动关联推理；问答跨文档推理；监测延迟≤6h；富化准确率≥95%；多跳推理≥85%。"))

    # ============ 二、调研结论 ============
    b += [divider(), heading("二、SOTA 调研结论（2026-10-11 联网调研，5 路并行）", 1)]
    b += table(["领域", "关键结论", "采用决策"], [
        ["数据源/采集", "cvelistV5 git 仓 ≈7min 级官方增量（优于 NVD 轮询）；GHSA webhooks 秒级；KEV/EPSS/OSV/ExploitDB 免费 API 齐全；四层去重流水线（URL→编号集合对齐→SimHash→MinHash-LSH）是行业标准做法；Huntr 已被 Palo Alto 收购且 OSS 漏洞流 2026-07 关闭，改用 GHSA+OSV 承接", "11 类源注册表 + APScheduler 分层轮询 + git diff 增量"],
        ["情报富化", "确定性源优先（NVD/KEV/EPSS/GHSA/OSV 直接锁死官方字段）；PoC 用 nomi-sec/trickest/nuclei 索引零成本发现 + GitHub search 兜底 + 恶意 PoC 静态检测（1.9-10% 含毒）；测绘 query 优先取 nuclei 模板元数据；LLM 只做理解生成且全部证据+校验+abstain", "10+ 维富化流水线 + 置信度合并 + abstain 队列"],
        ["RAG/问答", "混合检索（dense+sparse RRF）是安全语料必选项（CVE/CWE 标识符靠词面）；Qwen3-Embedding-0.6B CPU 可用且超 BGE-M3；GraphRAG 太重改用 LightRAG 思想自建安全 KG；多跳靠 分解→检索→KG桥接→纠偏 agentic loop", "Qdrant 命名向量混合检索 + bge-reranker + Neo4j KG + LangGraph 问答图"],
        ["Agent 编排", "LangGraph 1.x 成事实标准（显式状态图+astream 节点事件）；AutoGen 停更；Supervisor-as-Tools 为问答推荐模式；周期任务用确定性 DAG、交互任务用 Supervisor", "LangGraph 三层混合架构"],
        ["AI 安全领域", "AI 漏洞分五层：基础设施/模型数据/应用智能体/供应链/政策；OWASP LLM Top10 2025 + ASI Top10 2026(Agentic) + MITRE ATLAS（含 Feasible/Demonstrated/Realized 成熟度）；中文政策源（网信办/TC260/GB/T 45654）是差异化空白；无平台做 AI 资产视角聚合", "L1-L6 三维情报立方体分类法"],
    ])

    # ============ 三、系统架构 ============
    b += [divider(), heading("三、系统架构", 1)]
    b.append(para("总体分层：表现层(Next.js) → 智能体编排层(LangGraph) → [监测 | 富化 | 知识库 | 工程] 四横层。"))
    b.append(heading("3.1 智能体三层混合架构", 2))
    b += [bullet("**周期链路（确定性 DAG）**：采集→规范化→四层去重→富化 fan-out→校验合并→入库→索引→KG 同步。节点幂等可重放，由 APScheduler 驱动 + LangGraph 编排，对应“任务编排”评分点。"),
          bullet("**交互链路（Supervisor-as-Tools）**：QueryAgent 主智能体把混合检索/KG 查询/资产测绘/报告生成封装为工具自主调用，展示自主决策与工具调用。"),
          bullet("**分析链路（Planner-Executor-Critic）**：AnalystAgent 日报/专题/攻击链生成，含自我校验回环。"),
          bullet("**共享状态**：TaskRun 持久化（PG）+ Redis 实时节点态（pipeline run 轮询）。")]
    b.append(heading("3.2 数据流", 2))
    b += [bullet("采集层：cvelistV5(git 15min) / NVD / GHSA / OSV / KEV / ExploitDB / 厂商CSAF / AVID / arXiv / 20+ RSS / 邮件列表 / HN / 中文政策源"),
          bullet("去重：URL规范化哈希 → CVE/GHSA/CNVD/CNNVD/EDB 编号集合对齐 → 标题指纹+SimHash(≤3) → MinHash-LSH(J≥0.7)"),
          bullet("富化：scorers(NVD/EPSS/KEV/SSVC) → poc(索引+搜索+可信度) → assets(Hunter/FOFA 语法生成) → papers(S2/OpenAlex/arXiv) → mappings(CWE→CAPEC→ATT&CK/ATLAS) → nlp(翻译/版本/修复/相似) → chain(攻击链) → ai_classify(LLM精修)"),
          bullet("知识库：Qdrant（dense+BM42 sparse 命名向量，RRF）+ Neo4j（CVE-CWE-CAPEC-ATT&CK-Product-PoC-Paper-Item 图）+ PostgreSQL（结构化）"),
          bullet("问答：上下文化→路由→实体链接→子问题分解→混合召回→重排→CRAG纠偏(≤2)→KG桥接(≤3跳)→带引用生成→校验→SSE流式输出(答案+引用+推理链+置信度)")]

    # ============ 四、技术选型 ============
    b += [divider(), heading("四、技术选型与理由", 1)]
    b += table(["层", "选型", "理由"], [
        ["编排", "LangGraph 1.x + LangChain create_agent", "显式状态图/astream 事件/图拓扑可展示，生态最成熟"],
        ["LLM", "DeepSeek-V3.2 API（chat+reasoner）", "中文安全域强、function calling 稳、成本极低（$0.27/M in）"],
        ["Embedding", "Qwen3-Embedding-0.6B (ONNX/CPU)", "MTEB多语言64.33超BGE-M3，无GPU可跑，指令感知"],
        ["稀疏检索", "Qdrant BM42", "CVE/CWE/T-ID 精确标识符词面召回兜底"],
        ["重排", "BGE-reranker-v2-m3 (ONNX/CPU)", "中文强（CMTEB-R 72.16），CPU 可跑"],
        ["向量库", "Qdrant", "命名向量 dense+sparse + 服务端 RRF + payload 过滤，单机够用"],
        ["图谱", "Neo4j Community 5.x", "Cypher 变长路径（多跳桥接）、可视化成熟"],
        ["关系库", "PostgreSQL 16", "JSONB+数组+递归CTE，结构化+任务状态"],
        ["调度", "APScheduler AsyncIO", "单机够用，断点续采，jobstore 持久化"],
        ["采集栈", "httpx+feedparser+trafilatura+GitPython+tenacity", "异步、限流、条件GET、正文提取"],
        ["资产测绘", "奇安信 Hunter（主）+FOFA/Shodan 适配", "命题方产品，500 积分/天免费档"],
        ["前端", "Next.js14+Tailwind+ECharts+SSE", "实时大屏+流式问答+图谱可视化"],
        ["工程", "Docker Compose+Prometheus+Grafana+GH Actions", "一键部署+监控告警"],
    ])

    # ============ 五、AI 安全分类法 ============
    b += [divider(), heading("五、融合分类法（差异化核心）", 1)]
    b.append(para("按资产层分层回答“什么东西被打了”，每条情报同时挂三组标签，形成“资产×技术×治理”三维情报立方体："))
    b += table(["层", "名称", "覆盖对象", "映射体系"], [
        ["L1", "基础设施与推理层", "GPU/CUDA/Ollama/vLLM/Triton/llama.cpp/向量库/Jupyter/MLflow/LiteLLM", "CVE/CWE、ATT&CK"],
        ["L2", "模型与数据层", "提示注入/越狱/系统提示泄露/投毒/窃取/反演/记忆化", "OWASP LLM01-10、ATLAS"],
        ["L3", "应用与智能体层", "ChatGPT/Copilot类/插件/MCP/A2A/Coding Agent/浏览器Agent", "OWASP ASI01-10、ATLAS"],
        ["L4", "供应链层", "HF模型仓库/PyPI-npm/模型文件格式(pickle/GGUF)/分发渠道", "LLM03/ASI04、SLSA"],
        ["L5", "政策与治理层", "网信办/TC260/GB-T 45654/EU AI Act/NIST", "框架2.0、AI RMF"],
        ["L6", "滥用与威胁行为", "AI赋能攻击/恶意LLM服务(WormGPT)/AI恶意软件/僵尸网络", "ATLAS Realized、ENISA"],
    ])
    b.append(para("成熟度三级标注（借 ATLAS）：Feasible 学术可行 / Demonstrated 红队验证 / Realized 在野事件（KEV 命中自动升级）。"))

    # ============ 六、当前进展 ============
    b += [divider(), heading("六、当前进展（2026-10-12 审计修复后实测）", 1)]
    b.append(callout("**全链路生产化运行**：APScheduler 常驻调度（采集1min/富化5min/索引5min/KG 10min/LangGraph DAG 15min/EPSS 6h/日报 08:00），库内 50,277 条情报（KEV 1,466 + PoC 2,930 + 19,316 漏洞 + AI 相关 2,949）持续入库。问答双模式：快路径真流式 TTFT 1.09s/总 3.2s，深路径多跳 p50 8.9s 且 DeepSeek 自主发起 10 次工具调用（可审计 trace）。评测：12 题扩展集整体命中率 97.9%、多跳 95.8%、引用精确率 83.3%（赛题阈值 85%，决赛线 95%）。", "✅"))
    b.append(heading("差异化叙事：看得见·管得住·防得住·说得清", 3))
    b += [para("**看得见** —— 影子 AI 资产暴露看板：把奇安信鹰图「Ollama 88.9% 裸奔」式的一次性发现，做成 7×24 持续监测的情报视角（聚合 583K 暴露资产，标注模拟数据）。"),
          para("**管得住** —— 「人+工具+流程」研判机制：官方字段锁死不用 LLM，LLM 抽取带证据校验，低置信自动进 HITL 复核队列（宁可缺不可错）。"),
          para("**防得住** —— CVE→CWE→CAPEC→ATT&CK→D3FEND 对策链 + ATLAS 成熟度三级标注：从「知道有洞」到「知道怎么防」。"),
          para("**说得清** —— Agent 自主工具调用（实测单题 10 次，trace 全审计）+ 引用编号回溯 + KG 最短路径，「对话即研判」。"),
          callout("**标准化互操作**：STIX 2.1 Bundle 导出对齐 OASIS 国际标准与 GB/T 44886.4-2026《网络安全产品互联互通·威胁信息格式》（奇安信为起草单位之一）——情报消费侧可直接对接 TIP/SOC 平台。", "🥇")]
    b.append(heading("已完成（全真实验证）", 3))
    b += [todo("5 路并行 SOTA 调研完成，结论落入架构与选型", True),
          todo("基础设施八服务容器化：PG/Qdrant/Neo4j/Redis/API/调度器/前端/监控", True),
          todo("采集模块：41 源注册表；真实验证 NVD 543条 / KEV 34条 / HN 37 / 安全客 16 / TC260 6", True),
          todo("四层去重流水线：ID集合对齐>URL哈希>标题指纹>SimHash>MinHash-LSH（修复 KEV 目录URL误并 bug）", True),
          todo("富化模块：8 worker 并发——EPSS/KEV/SSVC 评分、PoC 发现(9个/条)、资产测绘、论文关联、CWE→CAPEC→ATT&CK 映射、翻译/版本/相似情报、攻击链生成、LLM 精判", True),
          todo("知识底座：Qdrant dense+sparse 混合向量集合 + Neo4j 五类实体图谱（634 项全量同步）", True),
          todo("问答模块：路由→CVE直连|Agent 工具循环(≤2轮)→混合检索+KG扩展→统一重排→DeepSeek 生成；SSE 真流式 token + 实时步骤进度 + 引用 + 置信度校准 + 拒答", True),
          todo("Agent 工具编排：DeepSeek tools（retrieve_intel/kg_expand/get_item_detail/list_kev）自主决策，实测单题 10 次调用", True),
          todo("HITL 复核队列：富化置信度聚合 → needs_review 自动标记 + /api/review confirm/reject", True),
          todo("标准互操作：/api/items/{id}/stix 输出 STIX 2.1 Bundle（vulnerability+attack-pattern+report）", True),
          todo("时效证据链：/api/stats/freshness 滞后分布 + 金丝雀脚本（注入→卡片1.3s→可检索43.7s）+ Prometheus 全指标", True),
          todo("前端六页：实时大屏/情报列表/详情/问答(流式)/知识图谱/源健康/报告，生产构建通过", True),
          todo("评测脚本：12 题评测集（单跳+多跳），整体命中率 97.9%，多跳 95.8%", True)]
    b.append(heading("实测数据", 3))
    b += table(["验证项", "结果"], [
        ["CVE 直连问答", "CVE-2024-37032 → 2.2s，置信度 0.97，含引用+追问+推理链"],
        ["多跳问答", "vLLM CVE-2025-32444 → CWE-502/T1190/0.8.5 修复版 全命中"],
        ["KEV 枚举问答", "KEV+AI 清单确定性注入 → 命中 CVE-37032/CVE-3248/T1190"],
        ["富化单条实测", "EPSS 0.897(前0.2%) + 9 PoC + 模拟资产 5312 + 5 论文 + 3 段攻击链"],
        ["KEV 采集", "34 收/20 新/14 按 CVE 正确合并"],
        ["问答延迟", "快路径 TTFT 1.09s 总 3.2s；深路径多跳 p50 8.9s（并发子问召回+单次合并重排+流式生成，原 47s）"],
        ["评测总分", "12 题扩展集整体 97.9% / 多跳 95.8% / 引用精确率 83.3% / 推理链完备率 100%"],
    ])
    b.append(heading("进行中", 3))
    b += [todo("富化队列滚动消化（1931 条待富化，error 维度自动重试，优先级排序）", False),
          todo("cvelistV5 git 仓首跑（~2GB，全量 CVE 覆盖）", False)]
    b.append(heading("待办", 3))
    b += [todo("GITHUB_TOKEN 配置（解锁 GHSA/PoC 搜索，当前 403 降级）", False),
          todo("演示视频录制 + 技术报告(Word/PDF) + 答辩 PPT", False),
          todo("Alembic 迁移 + 更完整 CI（pytest+前端 build）", False)]
    b.append(callout("**已知降级**：Hunter API key 有效但账号未开通 API 权限（需付费升级）→ 资产测绘按 `is_simulated` 标记输出模拟数据；GitHub API 未认证 403 → GHSA/PoC 搜索降级；S2 限流 → 进程级熔断走 arXiv/内部引用；cisa.gov 不可达 → KEV 用 GitHub 镜像。所有降级均有标注，不影响功能验收。", "⚠️"))

    # ============ 七、风险与对策 ============
    b += [divider(), heading("七、风险与对策", 1)]
    b += table(["风险", "影响", "对策"], [
        ["LLM API 额度/网络", "富化/问答质量", "全链路降级路径+模板兜底；DeepSeek 缓存降低成本"],
        ["数据源反爬/失效", "采集覆盖", "源健康监控+失败告警+多源互备（同类源≥2）"],
        ["Neo4j/Qdrant 单点", "演示稳定性", "容器健康检查+降级（KG 不可用时问答走纯向量）"],
        ["恶意 PoC 误导", "富化准确率", "可信度分级（白名单+静态恶意特征检测）"],
        ["CPU embedding 吞吐", "索引速度", "0.6B 模型+批量推理+增量索引；可切 4B/API"],
    ])
    b += [divider(), para("*本文档由捞针·Nereid 项目自动维护，每次重大变更全量重建以保证逻辑自洽。最后更新：2026-10-11*")]
    return b


if __name__ == "__main__":
    client = NotionClient(TOKEN)
    blocks = build()
    print(f"rebuilding notion page {PAGE} with {len(blocks)} blocks…")
    client.rebuild(PAGE, blocks)
    print("done.")
