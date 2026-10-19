# SecAgent 项目知识（供后续会话/Agent 使用）

## 命名
- **公开品牌：捞针 · Nereid**（智能体驱动的 AI 安全知识情报系统）。用户面向：UI 标题、Logo、文档、PPT、Notion 用「捞针 · Nereid」
- **工程代号：SecAgent** 保留不变——容器名、DB 名、`secagent_` 指标前缀、包名、路径均为内部标识
- 命名寓意：「捞针」=大海捞针=从海量信息中捞出那根针（LLM 圈 NIAH 检索测试圈内梗）；Nereid=希腊神话海中宁芙群，喻多智能体在深海中寻针；也是海王星最远的卫星=深空哨兵

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
- **systemd 自愈（推荐）**：`~/.config/systemd/user/nereid-{backend,scheduler,frontend}.service`，linger 已开 → 重启自动拉起。手动起进程前先 `systemctl --user stop nereid-*` 防端口冲突
- 基础设施：`cd deploy && docker compose up -d postgres qdrant neo4j redis`（compose restart 策略自愈）
- 后端：`cd backend && .venv/bin/uvicorn app.main:app --port 8000`（venv 在 backend/.venv）
- 调度：`.venv/bin/python -m app.scheduler.runner`；演示数据：`.venv/bin/python ../scripts/demo_seed.py`
- 前端生产预览：`scripts/start_frontend.sh`（standalone 需拷 static/public，端口 3200）
- 测试：`PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 .venv/bin/python -m pytest tests -q`（必须禁用插件自加载，系统装有ROS会冲突）
- Notion 同步：`NOTION_TOKEN=xxx python3 scripts/build_notion_doc.py`
- 批量回填：`scripts/enrich_backfill.py --limit N --type vuln`（Semaphore(4)并发+断点续跑）

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

## 新增契约（2026-10-18 SOTA 对齐后）
- **LangGraph durable execution**：pipeline_graph 挂 AsyncPostgresSaver checkpointer，run 与 thread_id=`pipeline-{run_id}` 绑定；PG 挂降级 MemorySaver；`resume_pipeline(run_id, sid)` 断点续跑；演示入口 `POST /api/pipeline/resume/{run_id}`（先手动 kill 运行中流水线再调，LangGraph 从 PG checkpoint 续跑）
- **QA 评测口径（评委可核）**：reports/eval_q.json 已入仓——整体 97.9% / 多跳 95.8% / 引用 83.3% / 推理链 100%（12 题 deep live）；reports/eval_enrichment.json——字段准确率 99.2% / 召回 100%（n=30 分层抽样）。文档/PPT 数字必须与这两份 JSON 一致，禁写 100%
- **前端中文映射层**：`frontend/lib/labels.ts` 集中所有枚举→中文（item_type/review_status/enrich 维度/源类型/CVSS source/SSVC/exploit_maturity/poc_credibility/report_type/tag 类型/运行状态）。新增用户可见枚举必须走 zh()，禁裸渲染后端 enum
- **用户可见性红线**：后台内部词（Redis key、API 路径、FIG_*、worker 名、snake_case step 名、raw traceback）不得出现在 UI；错误信息截断+详情进 title
- **优先级两段式（Qualys QVS 式）**：ingest._priority —— KEV/weaponized/SSVC-active 直接置顶桶 [6,8]；其余 65%CVSS+35%(EPSS+exploit成熟度+AI相关)
- **EPSS 官方口径**：refresh_epss_all 走每日 CSV 全量（epss_scores-current.csv.gz，1 请求覆盖全库，~39万 CVE）；CSV 挂回退批量 API；extra.epss_as_of/epss_model_version/epss_fetched_at 记录快照
- **CVSS 层级兜底**：cvelistV5 本地克隆解析 CNA + **ADP 容器**（CISA Vulnrichment 给无评分 CVE 补 CVSS/CWE）；NVD metrics 按 type=="Primary" 优先；extra.cvss_source 记录分值出处（cna|adp:xxx|nvd）
- **评测口径可辩护**：eval_enrichment 分层随机抽样（severity×年份，ID 层均匀随机）；EPSS 评测前对样本同快照刷新消除漂移假阴性
- **个性化推荐**：PUT/GET /api/profile/{name}；GET /api/feed/personalized；POST /api/feed/{id}/feedback；GET /api/feed/digest（规则匹配+向量召回+matched_entities/why 解释+反馈闭环）
- **systemd**：三 user service + linger；前端 standalone 每次 build 后 systemd 重启（旧 nohup 进程会抢端口——先杀再起）

## 新增契约（2026-10-19 时效检索修复后）
- **时效语义**：查询层统一 `effective_at = COALESCE(published_at, first_seen_at)`；`published_at` 只存真实披露时间（KEV collector 不再写 dateAdded）；排序全部 `coalesce desc`（PG NULLS FIRST 坑已修）
- **时间解析确定性**：`_parse_since(question)` 正则表产绝对窗口，覆盖 LLM 路由的 filters.since；LLM 不计算日期（_route_sys 注入 today 仅兜底）
- **trend/时效 SQL 枚举**：`_recent_items(since, severities)` 直接窗口枚举+COUNT 注入 context（向量检索给不出总数）；deep/fast 路径都接
- **时效过滤权威层**：水合后 DB 字段过滤（`_time_ok`），`since` 不下推向量层（存量 payload NULL）；CRAG-lite：窗口×4→全放开
- **ai_classify L1-L6 定义必须与 core/taxonomy.py 一致**（L1=基础设施推理…L6=滥用威胁）——2026-10-19 前 LLM 写的 ai_layer 是错层数据
- **published_at 回填**：`scripts/published_backfill.py --apply` 从 cvelistV5 datePublished 回填并清 indexed_hash（重索引待逐条 ingest 触发）

## 新增契约（2026-10-19 HITL 队列治理 SOTA 对齐后）
- **置信度均分只统计 status≠skipped 的维度**（pipeline.py）：skipped="不适用"非低置信；计入会把薄记录批量误判 needs_review（曾致 16k 假队列）。item.confidence 同口径已回填
- **入队谓词**：≥3 维 error，或高价值（KEV|severity∈{critical,high}|ai_relevance≥0.3）且 attempted 均分<0.4——队列语义="值得人看且系统拿不准"
- **复核动作语义**（routes.py）：confirm→confirmed / reject→**rejected**（非 auto，labels.ts 有映射）/ undo→needs_review；每次判决写 TaskRun(task_name="review") 审计 + extra.review_decision 归因（actor/at/action）
- **批量分诊**：POST /api/review/bulk/{action} body={ids}（≤500/次）
- **队列设计红线**：skipped 不计均分；瞬时基础设施错误应走重试通道非人审（Splunk finding/notable 分层原则）；排序用 priority_score×(1-confidence)；积压与待办分层展示；auto-resolve 规则未来须过 ≥0.98 精度回测护栏（Stripe Radar 惯例）
- **/api/review count 字段**=COUNT(*) 真实总数（非本页行数），配 offset 分页
