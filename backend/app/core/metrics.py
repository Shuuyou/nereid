"""Prometheus 指标"""
from prometheus_client import Counter, Gauge, Histogram

items_collected = Counter("secagent_items_collected_total", "采集条目数", ["source"])
items_new = Counter("secagent_items_new_total", "新增情报卡片数")
items_merged = Counter("secagent_items_merged_total", "合并条目数")
enrich_runs = Counter("secagent_enrich_runs_total", "富化执行数", ["status"])
qa_queries = Counter("secagent_qa_queries_total", "问答请求数", ["route"])
qa_latency = Histogram("secagent_qa_latency_seconds", "问答延迟", buckets=(0.5, 1, 2, 3, 5, 8, 15, 30))
source_lag = Gauge("secagent_source_lag_seconds", "数据源滞后秒数", ["source"])
source_errors = Gauge("secagent_source_errors", "数据源连续失败数", ["source"])
collection_duration = Histogram("secagent_collection_seconds", "单源采集耗时", ["source"])
kg_nodes = Gauge("secagent_kg_nodes", "知识图谱节点数", ["label"])
index_size = Gauge("secagent_index_chunks", "向量索引块数")

# 时效指标：披露→落库 / 披露→可见（性能分"时效"的证据链）
ingest_delay = Histogram(
    "secagent_ingest_delay_seconds", "源方披露→raw落库延迟", ["source"],
    buckets=(60, 300, 900, 1800, 3600, 7200, 21600, 86400, 604800))
item_freshness = Histogram(
    "secagent_item_freshness_seconds", "披露→情报卡片可见延迟",
    buckets=(300, 900, 1800, 3600, 7200, 21600, 86400, 604800))
canary_e2e = Gauge("secagent_canary_e2e_seconds", "金丝雀端到端最新耗时", ["stage"])
qa_route_latency = Histogram(
    "secagent_qa_route_latency_seconds", "问答各阶段耗时", ["stage"],
    buckets=(0.1, 0.5, 1, 2, 5, 10, 20, 40))
