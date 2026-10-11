"""LLM 客户端：DeepSeek 主用，OpenAI兼容协议，支持结构化输出与多模型fallback"""
from __future__ import annotations

import json
from typing import Any, TypeVar

import openai
from pydantic import BaseModel
from tenacity import retry, stop_after_attempt, wait_exponential

from app.config import get_settings
from app.core.logging import get_logger

log = get_logger("llm")
T = TypeVar("T", bound=BaseModel)

_clients: dict[str, openai.AsyncOpenAI] = {}


def _get_client(provider: str = "deepseek") -> openai.AsyncOpenAI:
    if provider in _clients:
        return _clients[provider]
    s = get_settings()
    if provider == "deepseek":
        client = openai.AsyncOpenAI(api_key=s.deepseek_api_key, base_url=s.deepseek_base_url, timeout=120.0)
    elif provider == "dashscope":
        client = openai.AsyncOpenAI(api_key=s.dashscope_api_key, base_url=s.dashscope_base_url, timeout=120.0)
    else:
        client = openai.AsyncOpenAI(api_key=s.openai_api_key, base_url=s.openai_base_url or None, timeout=120.0)
    _clients[provider] = client
    return client


def default_model(reasoning: bool = False) -> str:
    s = get_settings()
    return s.deepseek_reasoner_model if reasoning else s.deepseek_chat_model


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=20), reraise=True)
async def chat(
    messages: list[dict[str, str]],
    *,
    model: str | None = None,
    reasoning: bool = False,
    temperature: float = 0.1,
    max_tokens: int = 4096,
    response_format: dict | None = None,
    tools: list[dict] | None = None,
    tool_choice: Any = None,
    provider: str = "deepseek",
) -> dict[str, Any]:
    """统一聊天补全。返回 {content, reasoning_content?, tool_calls?, usage}"""
    client = _get_client(provider)
    kwargs: dict[str, Any] = {
        "model": model or default_model(reasoning),
        "messages": messages,
        "max_tokens": max_tokens,
    }
    if not reasoning:
        kwargs["temperature"] = temperature
    if response_format:
        kwargs["response_format"] = response_format
    if tools:
        kwargs["tools"] = tools
        if tool_choice:
            kwargs["tool_choice"] = tool_choice
    resp = await client.chat.completions.create(**kwargs)
    msg = resp.choices[0].message
    return {
        "content": msg.content or "",
        "reasoning_content": getattr(msg, "reasoning_content", None),
        "tool_calls": [tc.model_dump() for tc in (msg.tool_calls or [])],
        "usage": resp.usage.model_dump() if resp.usage else {},
        "finish_reason": resp.choices[0].finish_reason,
    }


async def chat_stream(
    messages: list[dict[str, str]],
    *,
    model: str | None = None,
    reasoning: bool = False,
    temperature: float = 0.1,
    max_tokens: int = 4096,
    provider: str = "deepseek",
):
    """真流式聊天补全：逐 delta 产出文本（SSE token 直通）"""
    client = _get_client(provider)
    kwargs: dict = {
        "model": model or default_model(reasoning),
        "messages": messages,
        "max_tokens": max_tokens,
        "stream": True,
    }
    if not reasoning:
        kwargs["temperature"] = temperature
    stream = await client.chat.completions.create(**kwargs)
    async for chunk in stream:
        if not chunk.choices:
            continue
        delta = chunk.choices[0].delta
        piece = getattr(delta, "content", None) or ""
        if piece:
            yield piece


async def chat_structured(
    messages: list[dict[str, str]],
    schema: type[T],
    *,
    model: str | None = None,
    reasoning: bool = False,
    max_retries: int = 2,
) -> T:
    """结构化输出：JSON mode + pydantic 校验 + 重试"""
    schema_hint = json.dumps(schema.model_json_schema(), ensure_ascii=False)
    sys_suffix = f"\n必须只输出符合以下 JSON Schema 的 JSON 对象，不要输出任何其他内容：\n{schema_hint}"
    msgs = [dict(m) for m in messages]
    if msgs and msgs[0].get("role") == "system":
        msgs[0]["content"] += sys_suffix
    else:
        msgs.insert(0, {"role": "system", "content": sys_suffix.lstrip()})

    last_err: Exception | None = None
    for attempt in range(max_retries + 1):
        try:
            out = await chat(
                msgs, model=model, reasoning=reasoning,
                response_format={"type": "json_object"},
            )
            data = json.loads(out["content"])
            return schema.model_validate(data)
        except Exception as e:  # noqa: BLE001
            last_err = e
            log.warning("structured_output_retry", attempt=attempt, error=str(e)[:200])
            msgs.append({"role": "user", "content": f"输出无效（{e}）。请严格按 Schema 重新输出 JSON。"})
    raise RuntimeError(f"structured output failed: {last_err}")


async def embed_text_via_llm(text: str) -> str:
    """占位：本地 embedding 走 core.embeddings，不用 LLM"""
    raise NotImplementedError
