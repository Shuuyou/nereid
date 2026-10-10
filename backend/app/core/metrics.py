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
