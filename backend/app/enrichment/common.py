"""富化公共助手：WorkerResult 契约 / LLM 降级封装 / 校验工具

Worker 契约（所有 enrichment worker 遵守）：
- async def run(item, ctx) -> dict，**不得直接修改 item 或写库**（item 只读）；
- 返回 {
    "status": "ok|partial|skipped|error",
    "confidence": 0-1,
    "note": str,                # 人类可读说明
    "data_keys": [...],         # 产出的数据键（审计）
    "fields": {Item字段: 值},    # 由 pipeline 合并写回 Item
    "extra":  {key: 值},        # 浅合并进 item.extra
    "rows":   {"pocs"|"assets"|"papers"|"mappings": [dict, ...]},  # 子表行（delete+insert 幂等）
  }
- 所有网络调用走 core.http.fetch；LLM 一律经本模块 llm_* 包装（无 key 自动返回 None）。
"""
from __future__ import annotations

import base64
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, TypeVar

from pydantic import BaseModel
from sqlalchemy.ext.asyncio import async_sessionmaker, AsyncSession

from app.config import get_settings
from app.core import llm
from app.core.logging import get_logger

log = get_logger("enrich")

# 富化维度名（enrichment JSONB 键）
DIMS = ["scorers", "poc", "assets", "papers", "mappings", "nlp", "chain", "ai_classify"]

T = TypeVar("T", bound=BaseModel)


@dataclass
class Ctx:
    """worker 运行上下文：只提供一个独立 session 工厂（禁止共享 pipeline session 并发写）"""
    sf: async_sessionmaker[AsyncSession]


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def W(status: str, confidence: float = 0.0, note: str = "", **kw: Any) -> dict:
    """构造 worker 结果"""
    return {"status": status, "confidence": round(confidence, 3), "note": note[:500],
            "ts": now_iso(), "data_keys": [], "fields": {}, "extra": {}, "rows": {}, **kw}


def ok(note: str = "", confidence: float = 1.0, **kw: Any) -> dict:
    return W("ok", confidence, note, **kw)


def partial(note: str = "", confidence: float = 0.5, **kw: Any) -> dict:
    return W("partial", confidence, note, **kw)


def skipped(note: str = "", **kw: Any) -> dict:
    return W("skipped", 0.0, note, **kw)


def error(note: str = "", **kw: Any) -> dict:
    return W("error", 0.0, note, **kw)


# ---------- LLM 降级封装 ----------

def llm_provider() -> str | None:
    s = get_settings()
    if s.deepseek_api_key:
        return "deepseek"
    if s.openai_api_key:
        return "openai"
    return None


def llm_enabled() -> bool:
    return llm_provider() is not None


async def llm_text(messages: list[dict[str, str]], *, max_tokens: int = 2000,
                   temperature: float = 0.1) -> str | None:
    """纯文本 LLM 调用；无 key/异常一律返回 None（优雅降级）"""
    provider = llm_provider()
    if not provider:
        return None
    try:
        out = await llm.chat(messages, max_tokens=max_tokens,
                             temperature=temperature, provider=provider)
        return out.get("content") or None
    except Exception as e:  # noqa: BLE001
        log.warning("llm_text_failed", error=str(e)[:200])
        return None


async def llm_struct(messages: list[dict[str, str]], schema: type[T]) -> T | None:
    """结构化 LLM 调用；无 key/异常一律返回 None"""
    provider = llm_provider()
    if not provider:
        return None
    try:
        if provider == "deepseek":
            # chat_structured 不接收 provider 参数，固定走 deepseek client
            return await llm.chat_structured(messages, schema)
        return await _struct_openai(messages, schema)
    except Exception as e:  # noqa: BLE001
        log.warning("llm_struct_failed", error=str(e)[:200])
        return None


async def _struct_openai(messages: list[dict[str, str]], schema: type[T]) -> T | None:
    """openai provider 的结构化兜底：JSON mode + pydantic 校验"""
    import json
    schema_hint = json.dumps(schema.model_json_schema(), ensure_ascii=False)
    msgs = [{"role": "system", "content": f"只输出符合此 Schema 的 JSON：{schema_hint}"}] + messages
    out = await llm.chat(msgs, provider="openai", response_format={"type": "json_object"})
    return schema.model_validate(json.loads(out["content"]))


# ---------- 通用工具 ----------

def b64q(query: str) -> str:
    """测绘语法 base64url（Hunter/FOFA 均用 base64 传 query）"""
    return base64.b64encode(query.encode("utf-8")).decode("ascii")


_VERSION_RE = re.compile(r"^[<>!=~^*\s]*v?\d[\w.\-+]*$", re.I)


def valid_version(v: str | None) -> bool:
    """版本号格式校验（确定性闸门，过滤 LLM 幻觉）"""
    return bool(v) and len(v) < 60 and bool(_VERSION_RE.match(v.strip()))


_STOP = {"the", "a", "an", "of", "in", "for", "and", "or", "to", "via", "on", "with",
         "is", "are", "was", "were", "by", "at", "that", "this", "from", "as", "be",
         "cve", "vulnerability", "allows", "could", "lead", "when", "not", "an", "a"}


def token_overlap(a: str | None, b: str | None) -> float:
    """标题/摘要 token Jaccard 相似度（论文相关性、零成本相关性判定）"""
    ta = {t for t in re.findall(r"[a-zA-Z][\w.-]+", (a or "").lower()) if t not in _STOP}
    tb = {t for t in re.findall(r"[a-zA-Z][\w.-]+", (b or "").lower()) if t not in _STOP}
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / len(ta | tb)


def parse_dt(s: str | None) -> datetime | None:
    """宽松 ISO 日期解析"""
    if not s:
        return None
    try:
        dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:  # noqa: BLE001
        return None


def merge_list(a: list | None, b: list | None) -> list:
    return sorted(set(a or []) | set(b or []))
