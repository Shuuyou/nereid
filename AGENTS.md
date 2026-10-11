# SecAgent 项目知识（供后续会话/Agent 使用）

## 项目背景
- 竞赛：第三届"中国电子杯"ICT产教融合大赛 赛题九（奇安信命题）——智能体驱动的 AI 安全知识情报系统
- 团队：杭电具身智能实验室 Shuuyou；目标：冠军；交付期：1 个月内
- 评分：监测15+富化15+问答15（功能）| 时效5+富化准确率5+问答深度5（性能）| Agent15+工程10+文档+演示（优化）
- 权威文档：Notion（token 见任务下发，page_id=3f5d3aea-8397-80d8-bb09-e1ec9ac32da3），scripts/build_notion_doc.py 全量重建

## 技术栈
- 后端 Python3.12 + FastAPI + SQLAlchemy(async) + LangGraph；前端 Next.js14+Tailwind+ECharts
- 存储：PostgreSQL(5433)/Qdrant(6333,dense+sparse)/Neo4j(7474,7687)/Redis(6380)
- LLM：DeepSeek API（chat_structured JSON 输出）；Embedding：fastembed ONNX CPU（Qwen3-Embedding-0.6B + BM42 sparse + bge-reranker-v2-m3）
- 测绘：Hunter（key 已给但**账号无API权限**，走 is_simulated 降级）

## 运行
- 基础设施：`cd deploy && docker compose up -d postgres qdrant neo4j redis`
- 后端：`cd backend && .venv/bin/uvicorn app.main:app --port 8000`（venv 在 backend/.venv）
- 调度：`.venv/bin/python -m app.scheduler.runner`；演示数据：`.venv/bin/python ../scripts/demo_seed.py`
- 测试：`PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 .venv/bin/python -m pytest tests -q`（必须禁用插件自加载，系统装有ROS会冲突）
- Notion 同步：`NOTION_TOKEN=xxx python3 scripts/build_notion_doc.py`

## 环境坑（已踩过）
- 本机 GPU 驱动版本不匹配不可用 → embedding/reranker 全走 CPU ONNX
- cisa.gov 直连不可达 → KEV 用 github.com/cisagov/kev-data raw 镜像兜底
- api.github.com 未认证 403/限流 → 需要 GITHUB_TOKEN（未配置）
- pytest 插件自加载会拉起 ROS 模块 → PYTEST_DISABLE_PLUGIN_AUTOLOAD=1
- .env 主机名为 localhost（本地开发），compose 容器侧由 environment 覆盖为服务名

## 代码契约（勿破坏）
- collectors：实现 collect(source)->(list[RawItemData], new_state)，由 registry.run_source 统一 ingest_items
- enrichment workers：返回 {status,confidence,note,fields,extra,rows}；pipeline 负责合并写回；子表 rows→{pocs:Poc, assets:AssetStat, papers:Paper, mappings:MappingLink} delete+insert 幂等
- enrichment worker 不得直接改 item/写库；LLM 一律走 common.llm_*（无 key 自动降级）
- rag：index_item(item) 幂等（先删后插）；retrieve(q)->item级证据；kg sync_item MERGE 幂等
- query_agent：`app.rag.query_agent.stream_answer`（勿写 app.agents.query_agent）
- api/routes.py：前端契约已锁定（SSE: status|token|trace|citations|done）
- query_agent.answer()=非流式评测入口；stream_answer=SSE 真流式（_prepare 共享流水线）
- LLM 工具调用：chat(tools=AGENT_TOOLS) ≤2 轮；工具 retrieve_intel/kg_expand/get_item_detail/list_kev
- Item 字段无 title_en/summary_en/lang/ai_layers —— 只有 title/title_zh/summary/summary_zh/ai_layer（单数）

## 已验证的接口（2026-10-11）
- GET /api/stats/freshness 时效看板；GET /api/review HITL 复核队列；POST /api/review/{id}/{confirm|reject}
- GET /api/feed/stream SSE 实时推送（前端 subscribeFeed 已消费）；GET /api/items/{id}/stix STIX2.1 导出
- GET /api/pipeline/graph LangGraph DAG 结构；POST /api/pipeline/run/{sid} 触发全链 DAG
- 金丝雀：scripts/canary_freshness.py 全链路 43.7s；快路径 QA ~3s TTFT 1.1s；深路径多跳 ~14s
- EPSS 刷新：批量 API（refresh_epss_all），KEV 走 github 镜像（cisa.gov 不可达）

## 新增契约（2026-10-12 审计修复后）
- **事务纪律**：enrich_item 与 run_source 均为"读(短事务)→外部调用(无会话)→写(短事务)"三阶段；worker 期禁开 DB 事务
- **跨进程锁**：enrich 用 extra._enrich_lock 时间戳（15min 过期窃取）；enrichment 判已完成 = has_key("scorers")
- **Redis 已消费**：pipeline DAG 运行态写 `pipeline:run:{id}` hash + `pipeline:runs` list；金丝雀指标走 POST /api/internal/canary 进 API 进程
- **数据文件入仓**：data/cwe_capec.json、data/attack_ai.json 已跟踪（.gitignore 只排除 data/cvelistV5/）；mappings 读顶层 CWE-* 键与 attck/atlas/cwe_to_atlas
- **演示诚信**：demo 条目走 ingest_items 真实管线 + extra.is_demo=true + source_names=["demo"]；freshness 统计排除 is_demo/canary；is_kev 只由真实 KEV 数据置位
- **前端 API**：同源 /api 反代（next.config rewrites → BACKEND_URL），不再依赖 NEXT_PUBLIC_API_URL 构建期变量
- **金丝雀**：scripts/canary_freshness.py 默认跑完自动清理条目（--keep 保留）

## 子 Agent 注意事项
- 后台子 Agent 曾被回收且仍可能写盘冲突 → 实现类任务自己写，别让子 Agent 写共享文件
- enrichment/*.py 曾被覆写导致 extract_cwes/item.lang/ai_layers 旧版回归，修复后需 grep 验证
