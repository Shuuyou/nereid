FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    git gcc g++ curl wget && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# 构建期预热 ONNX 模型到镜像层（dense+sparse+reranker），断网冷启动检索链路仍可用
# HF_ENDPOINT 可指向国内镜像：https://hf-mirror.com
ARG HF_ENDPOINT=""
RUN python - <<'WARM'
import os
os.environ.setdefault("HF_ENDPOINT", os.environ.get("HF_ENDPOINT", "") or "https://huggingface.co")
try:
    from fastembed import TextEmbedding, SparseTextEmbedding, TextCrossEncoder
    TextEmbedding("Qwen/Qwen3-Embedding-0.6B")
    SparseTextEmbedding("Qdrant/bm42-all-minilm-l6-v2-attentions")
    TextCrossEncoder("BAAI/bge-reranker-v2-m3")
    print("[prewarm] embedding/sparse/reranker cached")
except Exception as e:
    print(f"[prewarm] skipped: {e}")  # 不阻断构建；运行期会再拉取
WARM

ENV PYTHONUNBUFFERED=1 PYTHONPATH=/app

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
