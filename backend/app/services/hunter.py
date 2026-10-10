"""Hunter（奇安信鹰图）资产测绘适配器 + 模拟降级
Hunter API: https://hunter.qianxin.com/open/api/search  (GET, api_key/search(base64)/page/..)
Key 无效或无权限 → 返回 None → 上层落 simulated=True 的模拟数据。
"""
from __future__ import annotations

import base64
import random

from app.config import get_settings
from app.core.http import fetch
from app.core.logging import get_logger

log = get_logger("hunter")
BASE = "https://hunter.qianxin.com/openApi/search"


def _b64(q: str) -> str:
    return base64.b64encode(q.encode("utf-8")).decode("ascii")


def _query_for(product: str) -> str:
    """按产品指纹构造 Hunter 查询语法"""
    p = product.lower().strip()
    fp = {
        "ollama": 'app="Ollama"',
        "vllm": 'header="X-Served-By" && title="vLLM"',
        "gradio": 'app="Gradio"',
        "jupyter": 'app="Jupyter Server" || app="JupyterLab"',
        "mlflow": 'app="MLflow"',
        "langflow": 'title="Langflow"',
        "flowise": 'title="Flowise"',
        "dify": 'app="Dify" || title="Dify"',
        "ray": 'app="Ray Dashboard"',
        "milvus": 'app="Milvus"',
        "chromadb": 'app="Chroma"',
        "lollms": 'title="LoLLMs"',
        "xinference": 'title="Xinference"',
    }.get(p)
    return fp or f'(title="{product}" || body="{product}") && status_code="200"'


async def search(product: str, page_size: int = 25) -> dict | None:
    """返回 {"assets":[...], "total": n}；无 key/无权限/异常 → None"""
    s = get_settings()
    if not s.hunter_api_key:
        return None
    try:
        resp = await fetch(BASE, params={
            "api-key": s.hunter_api_key,
            "search": _b64(_query_for(product)),
            "page": "1", "page_size": str(page_size),
            "is_web": "3",
        })
        if resp.status_code != 200:
            log.warning("hunter_http", code=resp.status_code)
            return None
        d = resp.json()
        if d.get("code") != 200:
            log.warning("hunter_api_denied", msg=str(d.get("message"))[:120])
            return None
        data = d.get("data") or {}
        return {"total": data.get("total", 0), "assets": data.get("arr") or []}
    except Exception as e:  # noqa: BLE001
        log.warning("hunter_failed", error=str(e)[:150])
        return None


COUNTRIES = ["中国", "美国", "德国", "日本", "韩国", "新加坡", "英国", "法国", "澳大利亚", "印度"]
ISPS = ["阿里云", "腾讯云", "华为云", "AWS", "Azure", "Google Cloud", "电信", "联通"]
PORTS = {"ollama": 11434, "vllm": 8000, "gradio": 7860, "jupyter": 8888, "mlflow": 5000,
         "langflow": 7860, "flowise": 3000, "dify": 80, "ray": 8265, "milvus": 19530}


def simulated_assets(product: str, n: int = 12) -> dict:
    """无 API 权限时的确定性模拟资产（演示/降级，simulated 标记必须保留）"""
    rng = random.Random(product)  # 同产品输出稳定
    port = PORTS.get(product.lower(), rng.choice([80, 443, 8000, 8080, 8443]))
    assets = []
    for _ in range(n):
        a = {
            "ip": ".".join(str(rng.randint(1, 223)) for _ in range(4)),
            "port": port + rng.choice([0, 0, 0, 1, 2]),
            "country": rng.choice(COUNTRIES),
            "org": rng.choice(ISPS),
            "title": f"{product} service",
            "service": "http",
            "simulated": True,
        }
        assets.append(a)
    return {"total": rng.randint(200, 20000), "assets": assets, "simulated": True}
