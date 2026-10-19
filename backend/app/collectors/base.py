"""采集器基类与统一数据契约

每个采集器实现 collect(source) -> list[RawItemData]，由 ingest 服务统一落库+去重。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from app.db.models import Source


@dataclass
class RawItemData:
    """采集器产出的标准化原始条目"""
    title: str
    url: str | None = None
    native_id: str | None = None          # 源内唯一ID（guid/CVE-ID/GHSA-ID/arxiv-id...）
    author: str | None = None
    published_at: datetime | None = None
    content_text: str | None = None       # 正文（已提取）
    summary: str | None = None            # 源方摘要（可选）
    lang: str | None = None               # zh|en|mixed
    raw: dict[str, Any] = field(default_factory=dict)  # 原始负载（保留溯源）
    item_type: str = "article"            # vuln|advisory|exploit|article|paper|incident|policy|model_sec
    # 可选的预提取字段（结构化源直接给）
    cve_ids: list[str] = field(default_factory=list)
    ghsa_ids: list[str] = field(default_factory=list)
    cwe_ids: list[str] = field(default_factory=list)
    vendors: list[str] = field(default_factory=list)
    products: list[str] = field(default_factory=list)
    severity: str | None = None
    cvss_v31_score: float | None = None
    cvss_v31_vector: str | None = None
    cvss_v40_score: float | None = None
    cvss_v40_vector: str | None = None
    packages: list[str] = field(default_factory=list)   # 受影响包 purl/ecosystem 标识（GHSA/OSV）


class BaseCollector:
    """采集器基类：子类实现 collect()"""

    name: str = "base"
    source_type: str = "blog_rss"

    async def collect(self, source: Source) -> tuple[list[RawItemData], dict]:
        """返回 (items, new_state)。new_state 写回 source.state 做增量游标。"""
        raise NotImplementedError
