"""AI 安全分类体系：L1-L6 资产层 × OWASP LLM/ASI × ATLAS 标签

融合分类法（答辩差异化核心）：
- L1 基础设施与推理层: GPU/CUDA/Ollama/vLLM/Triton/llama.cpp/向量库/Jupyter/MLflow
- L2 模型与数据层: 越狱/注入/系统提示泄露/投毒/窃取/反演/记忆化
- L3 应用与智能体层: ChatGPT/Copilot类产品/插件/MCP/A2A/Coding Agent/浏览器Agent
- L4 供应链层: HF模型仓库/PyPI-npm包/模型文件格式/分发渠道
- L5 政策与治理层: 网信办/TC260/GB标准/EU AI Act/NIST
- L6 滥用与威胁行为: AI赋能攻击/恶意LLM服务/AI恶意软件
"""
from __future__ import annotations

# ---- L1: 基础设施与推理层关键词（产品/组件名 → AI资产标签）----
AI_INFRA_PRODUCTS = {
    "ollama", "vllm", "triton inference server", "tritonserver", "llama.cpp", "llamacpp",
    "sglang", "lmdeploy", "text-generation-inference", "tgi", "tensorrt", "tensorrt-llm",
    "ray", "dask", "mlflow", "clearml", "kubeflow", "jupyter", "jupyterlab", "notebook",
    "milvus", "chromadb", "chroma", "qdrant", "weaviate", "pinecone", "pgvector", "faiss",
    "elasticsearch vector", "langflow", "flowise", "dify", "anything-llm", "open-webui", "open webui",
    "litellm", "one-api", "new-api", "fastchat", "localai", "gpt4all", "llamafile",
    "pytorch", "tensorflow", "transformers", "huggingface", "gradio", "streamlit",
    "cuda", "nvidia", "gpu driver", "nccl", "onnxruntime", "deepspeed", "peft", "trl",
    "langchain", "langgraph", "llamaindex", "llama-index", "haystack", "semantic kernel",
    "autogen", "crewai", "dspy", "guidance", "outlines", "vanna", "db-gpt",
    "comfyui", "stable-diffusion-webui", "invokeai", "fooocus", "kohya",
    "label-studio", "labelstudio", "airflow ml", "zenml", "bentoml", "seldon",
    "torchserve", "triton", "xinference", "skyvern", "browser-use",
}

# ---- L2: 模型与数据层风险关键词 ----
L2_KEYWORDS = {
    "prompt injection", "提示注入", "提示词注入", "jailbreak", "越狱",
    "system prompt leak", "系统提示词", "system prompt leakage",
    "data poisoning", "数据投毒", "model poisoning", "模型投毒", "backdoor",
    "model extraction", "模型窃取", "model inversion", "模型反演",
    "membership inference", "成员推断", "training data extraction", "训练数据泄露",
    "evasion attack", "对抗样本", "adversarial example", "adversarial attack",
    "rag poisoning", "knowledge poisoning", "embedding inversion",
    "instruction hierarchy", "indirect prompt injection", "间接提示注入",
}

# ---- L3: 应用与智能体层关键词 ----
L3_KEYWORDS = {
    "mcp server", "model context protocol", "mcp tool", "tool poisoning",
    "ai agent", "智能体", "autonomous agent", "agentic", "a2a protocol",
    "chatgpt", "copilot", "gemini", "claude", "cursor", "windsurf", "devin",
    "claude code", "amazon q", "codeium", "continue.dev", "aider",
    "comet browser", "ai browser", "computer use", "browser agent",
    "plugin", "connector", "gpts", "rag application",
    "excessive agency", "tool misuse", "agent hijack", "goal hijack",
    "memory poisoning", "context poisoning", "inter-agent",
}

# ---- L4: 供应链层关键词 ----
L4_KEYWORDS = {
    "malicious model", "恶意模型", "pickle", "safetensors", "gguf", "keras",
    "model file", "模型文件", "supply chain", "供应链", "typosquatting",
    "slopsquatting", "dependency confusion", "malicious package", "恶意包",
    "huggingface.co", "modelscope", "pypi", "npm package", "model hub",
    "rug pull", "weights", "checkpoint", "poisoned dataset",
}

# ---- L5: 政策与治理层关键词 ----
L5_KEYWORDS = {
    "网信办", "cac.gov", "tc260", "生成式人工智能", "备案", "ai regulation",
    "ai act", "nist ai", "人工智能安全治理", "治理框架", "gb/t", "标准",
    "生成式人工智能服务管理", "深度合成", "算法备案", "安全评估",
    "executive order", "executive order ai", "eu ai act", "iso 42001",
    "政策", "法规", "监管", "合规", "国家标准",
}

# ---- L6: 滥用与威胁行为关键词 ----
L6_KEYWORDS = {
    "wormgpt", "fraudgpt", "malicious llm", "deepfake", "深伪",
    "ai-powered attack", "ai generated malware", "llm phishing", "ai钓鱼",
    "ai malware", "sesameop", "lamehug", "僵尸网络", "botnet",
    "shadowray", "flodrix", "cryptomining", "挖矿",
}

# ---- OWASP LLM Top 10 2025 关键词映射 ----
OWASP_LLM_RULES = {
    "LLM01": {"prompt injection", "提示注入", "提示词注入", "indirect injection", "间接注入", "xpia"},
    "LLM02": {"sensitive information", "敏感信息泄露", "data leak", "pii", "credential leak", "信息泄露"},
    "LLM03": {"supply chain", "供应链", "malicious model", "恶意模型", "slopsquatting", "pickle"},
    "LLM04": {"poisoning", "投毒", "backdoor", "后门", "sleeper agent"},
    "LLM05": {"output handling", "输出处理", "unvalidated output", "xss", "ssrf"},
    "LLM06": {"excessive agency", "过度代理", "excessive permission", "权限过大"},
    "LLM07": {"system prompt", "系统提示词", "prompt leak", "提示词泄露"},
    "LLM08": {"vector", "embedding", "向量", "嵌入", "rag", "knowledge base", "知识库"},
    "LLM09": {"misinformation", "错误信息", "hallucination", "幻觉"},
    "LLM10": {"unbounded consumption", "资源消耗", "denial of service", "dos", "拒绝服务"},
}

# ---- OWASP Agentic Top 10 (ASI) 2026 关键词映射 ----
OWASP_ASI_RULES = {
    "ASI01": {"goal hijack", "目标劫持", "intent manipulation"},
    "ASI02": {"tool misuse", "工具滥用", "tool exploitation"},
    "ASI03": {"privilege abuse", "权限滥用", "identity abuse", "身份滥用", "提权"},
    "ASI04": {"agentic supply chain", "mcp supply", "供应链", "mcp server", "rug pull"},
    "ASI05": {"code execution", "代码执行", "rce", "远程代码执行"},
    "ASI06": {"memory poisoning", "记忆投毒", "context poisoning", "上下文投毒"},
    "ASI07": {"inter-agent", "agent communication", "a2a", "智能体通信"},
    "ASI08": {"cascading", "级联", "chain failure"},
    "ASI09": {"trust exploitation", "信任利用", "human-agent"},
    "ASI10": {"rogue agent", "失控", "self-replicat", "autonomous drift"},
}

LAYER_NAMES = {
    "L1": "基础设施与推理层", "L2": "模型与数据层", "L3": "应用与智能体层",
    "L4": "供应链层", "L5": "政策与治理层", "L6": "滥用与威胁行为",
}

OWASP_LLM_NAMES = {
    "LLM01": "提示词注入", "LLM02": "敏感信息泄露", "LLM03": "供应链风险",
    "LLM04": "数据与模型投毒", "LLM05": "输出处理不当", "LLM06": "过度代理权",
    "LLM07": "系统提示词泄露", "LLM08": "向量与嵌入弱点", "LLM09": "错误信息", "LLM10": "无界消耗",
}

OWASP_ASI_NAMES = {
    "ASI01": "智能体目标劫持", "ASI02": "工具滥用与利用", "ASI03": "身份与权限滥用",
    "ASI04": "智能体供应链", "ASI05": "意外代码执行", "ASI06": "记忆与上下文投毒",
    "ASI07": "智能体间通信不安全", "ASI08": "级联失效", "ASI09": "人机信任利用", "ASI10": "失控智能体",
}


def classify(text: str, products: list[str] | None = None) -> dict:
    """关键词规则分类器（第一层）；LLM 二次判读在 enrichment 中补充

    Returns: {ai_relevance_score, ai_layer, owasp_llm, owasp_asi}
    """
    t = (text or "").lower()
    prod_set = {p.lower() for p in (products or [])}

    scores = {"L1": 0.0, "L2": 0.0, "L3": 0.0, "L4": 0.0, "L5": 0.0, "L6": 0.0}

    # L1: 产品名命中（强信号，产品名精准）——已知 AI 组件直接高相关
    hits_l1 = [p for p in AI_INFRA_PRODUCTS if p in t or p in prod_set]
    if hits_l1:
        scores["L1"] += 0.6 + min(len(hits_l1) - 1, 3) * 0.1
    for kw, w in (("L2", L2_KEYWORDS), ("L3", L3_KEYWORDS), ("L4", L4_KEYWORDS),
                  ("L5", L5_KEYWORDS), ("L6", L6_KEYWORDS)):
        hits = [k for k in w if k in t]
        scores[kw] += min(len(hits), 4) * 0.25

    # 智能体/AI 通用词的弱信号
    weak = sum(1 for k in ("llm", "大模型", "ai ", "人工智能", "gpt-", "foundation model") if k in t)
    base = min(weak * 0.05, 0.15)

    total = max(scores.values()) + base
    layer = max(scores, key=scores.get) if max(scores.values()) > 0 else None
    relevance = min(1.0, total)

    owasp_llm = [k for k, kws in OWASP_LLM_RULES.items() if any(kw in t for kw in kws)]
    owasp_asi = [k for k, kws in OWASP_ASI_RULES.items() if any(kw in t for kw in kws)]

    return {
        "ai_relevance_score": round(relevance, 3),
        "ai_layer": layer,
        "owasp_llm": owasp_llm,
        "owasp_asi": owasp_asi,
        "layer_scores": {k: round(v, 3) for k, v in scores.items()},
    }


def is_ai_related(text: str, products: list[str] | None = None, threshold: float = 0.3) -> bool:
    return classify(text, products)["ai_relevance_score"] >= threshold
