# 捞针 · Nereid — 智能体驱动的 AI 安全知识情报系统

> 大海捞针，我们捞给你看。（工程代号：SecAgent）

> 第三届"中国电子杯"高校 ICT 产教融合创新大赛 · 赛题九（奇安信命题）
> 杭州电子科技大学 具身智能实验室

## 系统能力

- **情报监测**：11 类数据源（CVE 官方库准实时同步、NVD、GHSA、OSV、CISA KEV、ExploitDB、厂商 CSAF、AI 专用库、20+ 中英文安全社区 RSS、邮件列表、社交聚合、中文政策源），四层去重（URL 哈希→编号对齐→SimHash→MinHash-LSH），核心链路延迟 ≤1 小时
- **情报富化**：10+ 维度——CVSS/EPSS/KEV/SSVC 评分、PoC 发现+可信度分级、受影响资产测绘（奇安信 Hunter）、论文关联、CWE→CAPEC→ATT&CK/ATLAS 映射、受影响版本解析、修复建议、中文摘要、相似漏洞、攻击链自动生成，置信度合并 + abstain 机制
- **情报问答**：Agentic RAG——查询路由/分解、dense+sparse 混合检索、重排序、CRAG 纠偏、Neo4j 知识图谱桥接多跳推理、行内引用、可解释推理链、多轮对话
- **AI 安全知识底座**：L1-L6 资产分层 × OWASP LLM Top10/ASI Top10 × MITRE ATLAS × 中文政策法规 三维情报立方体
- **智能体架构**：LangGraph 三层混合——确定性 DAG（采集流水线）+ Supervisor-as-Tools（问答）+ Planner-Executor-Critic（分析报告）

## 快速启动

```bash
cp .env.example .env          # 填入 DEEPSEEK_API_KEY / HUNTER_API_KEY 等
cd deploy && docker compose up -d          # 全部服务
# 或仅起基础设施本地开发：
docker compose up -d postgres qdrant neo4j redis
cd ../backend && python -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/uvicorn app.main:app --port 8000   # 后端
.venv/bin/python -m app.scheduler.runner     # 调度器（另开终端）
cd ../frontend && npm install && npm run dev # 前端 :3000
```

- 前端大屏：http://localhost:3200（容器）/ :3000（dev）
- API 文档：http://localhost:8000/docs
- Neo4j Browser：http://localhost:7474（neo4j / .env 密码）
- Grafana：http://localhost:3101（admin / .env 密码）

## 目录结构

```
backend/app/
  collectors/   # 采集器：structured.py(结构化源) feeds.py(RSS/政策/厂商) registry.py(调度)
  enrichment/   # 8个富化worker + pipeline.py 编排（确定性源→LLM→校验合并）
  rag/          # embedder/qdrant/indexer/retriever/kg/query_agent
  agents/       # LangGraph：pipeline_graph DAG / analyst 报告
  services/     # dedup(4层) / ingest / kg / hunter / ssvc
  api/          # REST + SSE
  scheduler/    # APScheduler 周期编排
frontend/       # Next.js 14：大屏/情报/图谱/问答/报告/源健康
deploy/         # docker-compose + prometheus/grafana
docs/           # 赛题分析/架构/调研/报告
scripts/        # demo_seed / eval_qa / notion_sync / build_notion_doc
```

## 验证命令

```bash
cd backend && PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 .venv/bin/python -m pytest tests/ -x -q
.venv/bin/python ../scripts/demo_seed.py        # 12条种子情报
.venv/bin/python ../scripts/eval_qa.py --live   # 多跳问答评测（需 API 在跑）
```

## 已知限制

- Hunter API 需付费账号权限；无权限时自动降级为 `is_simulated` 标记的模拟资产数据
- cisa.gov 国内不可达 → 自动切 GitHub KEV 镜像
- api.github.com 未认证 403 → 配 `GITHUB_TOKEN` 启用 GHSA 全量采集
- GPU 驱动异常 → embedding/reranker 走 CPU ONNX（fastembed）

## 评分映射

| 指标 | 设计 |
|---|---|
| 监测完整性 15 | 11类源+准实时 git/webhook+四层去重 |
| 富化完整性 15 | 10+维+关联推理+置信度合并 |
| 问答完整性 15 | 跨文档多跳+KG桥接+推理链可视化+多轮 |
| 时效 5 | 核心链路 ≤1h（cvelistV5 15min 增量） |
| 富化准确率 5 | 官方字段锁死+校验器+abstain |
| 问答质量 | 自建 KG 路径多跳评测集 |
| Agent 15 | 三层混合架构+工具调用+HITL |
| 工程 10 | 全容器化+Prometheus/Grafana+CI |
