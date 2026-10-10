"""SecAgent 数据模型 —— 全系统共享的数据契约

分层：
- sources：数据源注册与增量游标状态
- raw_items：采集原始层（一源一条）
- items：情报卡片层（跨源去重合并后的聚合实体）
- item_sources：卡片↔原始条目多对多溯源
- pocs / asset_stats / papers / mapping_links：富化维度表
- task_runs：任务可观测
- qa_sessions / qa_messages：问答会话
- reports：自动生成的情报报告
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    BigInteger, Boolean, DateTime, Float, ForeignKey, Index, Integer,
    String, Text, UniqueConstraint, func,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def gen_uuid() -> str:
    return uuid.uuid4().hex


class Base(DeclarativeBase):
    pass


class Source(Base):
    """数据源注册表 + 增量采集游标"""
    __tablename__ = "sources"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(128), unique=True)
    source_type: Mapped[str] = mapped_column(String(32))  # cve_db|advisory|kev|exploit|blog_rss|mailing_list|social|paper|policy|ai_specific|vendor_csaf
    url: Mapped[str] = mapped_column(String(1024))
    tier: Mapped[int] = mapped_column(Integer, default=3)  # 1官方 2厂商 3社区 4聚合 5社交
    lang: Mapped[str] = mapped_column(String(8), default="en")
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    poll_interval_sec: Mapped[int] = mapped_column(Integer, default=3600)
    state: Mapped[dict] = mapped_column(JSONB, default=dict)  # etag/last_modified/cursor/last_commit
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_success_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(Text)
    consecutive_failures: Mapped[int] = mapped_column(Integer, default=0)
    total_items: Mapped[int] = mapped_column(Integer, default=0)


class RawItem(Base):
    """采集原始条目"""
    __tablename__ = "raw_items"
    __table_args__ = (
        UniqueConstraint("source_id", "native_id", name="uq_raw_source_native"),
        Index("ix_raw_fetched", "fetched_at"),
        Index("ix_raw_status", "process_status"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    source_id: Mapped[int] = mapped_column(ForeignKey("sources.id"))
    native_id: Mapped[str | None] = mapped_column(String(256))
    url: Mapped[str | None] = mapped_column(String(2048))
    url_sha256: Mapped[str | None] = mapped_column(String(64), index=True)
    title: Mapped[str] = mapped_column(Text)
    author: Mapped[str | None] = mapped_column(String(256))
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    lang: Mapped[str | None] = mapped_column(String(8))
    content_text: Mapped[str | None] = mapped_column(Text)
    raw: Mapped[dict] = mapped_column(JSONB, default=dict)
    process_status: Mapped[str] = mapped_column(String(16), default="new")  # new|clustered|skipped|error


class Item(Base):
    """情报卡片：跨源去重合并后的聚合实体（CVE漏洞/公告/文章/论文/事件/政策）"""
    __tablename__ = "items"
    __table_args__ = (
        Index("ix_items_published", "published_at"),
        Index("ix_items_cve", "cve_ids", postgresql_using="gin"),
        Index("ix_items_layer", "ai_layer"),
        Index("ix_items_status", "review_status"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    item_type: Mapped[str] = mapped_column(String(24), default="article")  # vuln|advisory|exploit|article|paper|incident|policy|model_sec
    title: Mapped[str] = mapped_column(Text)
    title_zh: Mapped[str | None] = mapped_column(Text)
    summary: Mapped[str | None] = mapped_column(Text)
    summary_zh: Mapped[str | None] = mapped_column(Text)
    content_text: Mapped[str | None] = mapped_column(Text)
    url: Mapped[str | None] = mapped_column(String(2048))
    url_sha256: Mapped[str | None] = mapped_column(String(64), index=True)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    # 标识符（跨源对齐键）
    cve_ids: Mapped[list] = mapped_column(ARRAY(String), default=list)
    ghsa_ids: Mapped[list] = mapped_column(ARRAY(String), default=list)
    cnvd_ids: Mapped[list] = mapped_column(ARRAY(String), default=list)
    cnnvd_ids: Mapped[list] = mapped_column(ARRAY(String), default=list)
    edb_ids: Mapped[list] = mapped_column(ARRAY(String), default=list)
    cwe_ids: Mapped[list] = mapped_column(ARRAY(String), default=list)

    # 资产实体
    vendors: Mapped[list] = mapped_column(ARRAY(String), default=list)
    products: Mapped[list] = mapped_column(ARRAY(String), default=list)
    packages: Mapped[list] = mapped_column(ARRAY(String), default=list)  # purl风格 pkg:eco/name
    affected_versions: Mapped[str | None] = mapped_column(Text)
    cpes: Mapped[list] = mapped_column(ARRAY(String), default=list)

    # 评分与利用信号
    severity: Mapped[str | None] = mapped_column(String(16))  # critical|high|medium|low|none
    cvss_v31_score: Mapped[float | None] = mapped_column(Float)
    cvss_v31_vector: Mapped[str | None] = mapped_column(String(128))
    cvss_v40_score: Mapped[float | None] = mapped_column(Float)
    cvss_v40_vector: Mapped[str | None] = mapped_column(String(256))
    epss_score: Mapped[float | None] = mapped_column(Float)
    epss_percentile: Mapped[float | None] = mapped_column(Float)
    is_kev: Mapped[bool] = mapped_column(Boolean, default=False)
    kev_date_added: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    has_poc: Mapped[bool] = mapped_column(Boolean, default=False)
    exploit_maturity: Mapped[str | None] = mapped_column(String(24))  # weaponized|poc|none
    priority_score: Mapped[float | None] = mapped_column(Float)

    # AI 安全分类（三维情报立方体）
    ai_relevance_score: Mapped[float] = mapped_column(Float, default=0.0)
    ai_layer: Mapped[str | None] = mapped_column(String(8))  # L1基础设施/L2模型数据/L3应用智能体/L4供应链/L5政策治理/L6滥用威胁
    owasp_llm: Mapped[list] = mapped_column(ARRAY(String), default=list)   # LLM01-LLM10
    owasp_asi: Mapped[list] = mapped_column(ARRAY(String), default=list)   # ASI01-ASI10
    atlas_techniques: Mapped[list] = mapped_column(ARRAY(String), default=list)
    attack_techniques: Mapped[list] = mapped_column(ARRAY(String), default=list)  # ATT&CK T-id
    technique_maturity: Mapped[str | None] = mapped_column(String(16))  # feasible|demonstrated|realized

    # 元信息
    source_count: Mapped[int] = mapped_column(Integer, default=1)
    source_names: Mapped[list] = mapped_column(ARRAY(String), default=list)
    reliability_score: Mapped[float] = mapped_column(Float, default=0.5)
    confidence: Mapped[float] = mapped_column(Float, default=0.5)
    review_status: Mapped[str] = mapped_column(String(16), default="auto")  # auto|needs_review|confirmed
    title_fingerprint: Mapped[str | None] = mapped_column(String(64), index=True)
    simhash64: Mapped[int | None] = mapped_column(BigInteger)
    enrichment: Mapped[dict] = mapped_column(JSONB, default=dict)   # 各富化维度摘要 {dim: {status,confidence,...}}
    attack_chain: Mapped[dict | None] = mapped_column(JSONB)        # Attack Flow 风格攻击链
    extra: Mapped[dict] = mapped_column(JSONB, default=dict)

    sources_rel: Mapped[list["ItemSource"]] = relationship(back_populates="item", cascade="all, delete-orphan")
    pocs: Mapped[list["Poc"]] = relationship(back_populates="item", cascade="all, delete-orphan")
    papers: Mapped[list["Paper"]] = relationship(back_populates="item", cascade="all, delete-orphan")


class ItemSource(Base):
    """情报卡片 ↔ 原始条目（多源溯源）"""
    __tablename__ = "item_sources"
    __table_args__ = (UniqueConstraint("item_id", "raw_item_id", name="uq_item_raw"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    item_id: Mapped[str] = mapped_column(ForeignKey("items.id", ondelete="CASCADE"), index=True)
    raw_item_id: Mapped[str] = mapped_column(ForeignKey("raw_items.id", ondelete="CASCADE"), index=True)
    source_name: Mapped[str] = mapped_column(String(128))
    url: Mapped[str | None] = mapped_column(String(2048))
    is_primary: Mapped[bool] = mapped_column(Boolean, default=False)
    item: Mapped[Item] = relationship(back_populates="sources_rel")


class Poc(Base):
    """POC/EXP 发现记录（含可信度分级）"""
    __tablename__ = "pocs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    item_id: Mapped[str] = mapped_column(ForeignKey("items.id", ondelete="CASCADE"), index=True)
    url: Mapped[str] = mapped_column(String(2048))
    platform: Mapped[str] = mapped_column(String(32))  # github|exploitdb|nuclei|packetstorm|metasploit|sploitus|other
    title: Mapped[str | None] = mapped_column(Text)
    stars: Mapped[int | None] = mapped_column(Integer)
    author: Mapped[str | None] = mapped_column(String(256))
    verified: Mapped[bool] = mapped_column(Boolean, default=False)
    credibility: Mapped[str] = mapped_column(String(16), default="community")  # trusted|community|suspicious|malicious
    credibility_reasons: Mapped[dict] = mapped_column(JSONB, default=dict)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    item: Mapped[Item] = relationship(back_populates="pocs")


class AssetStat(Base):
    """受影响互联网资产测绘结果"""
    __tablename__ = "asset_stats"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    item_id: Mapped[str] = mapped_column(ForeignKey("items.id", ondelete="CASCADE"), index=True)
    platform: Mapped[str] = mapped_column(String(16))  # hunter|fofa|quake|shodan|censys
    query: Mapped[str] = mapped_column(Text)
    total_count: Mapped[int] = mapped_column(Integer, default=0)
    sample: Mapped[dict] = mapped_column(JSONB, default=list)  # top hosts [{ip,port,title,country,...}]
    is_simulated: Mapped[bool] = mapped_column(Boolean, default=False)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Paper(Base):
    """关联学术论文/分析文章"""
    __tablename__ = "papers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    item_id: Mapped[str] = mapped_column(ForeignKey("items.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(Text)
    url: Mapped[str | None] = mapped_column(String(2048))
    venue: Mapped[str | None] = mapped_column(String(256))
    year: Mapped[int | None] = mapped_column(Integer)
    authors: Mapped[str | None] = mapped_column(Text)
    abstract: Mapped[str | None] = mapped_column(Text)
    source: Mapped[str] = mapped_column(String(32))  # semantic_scholar|openalex|arxiv|reference
    relevance_score: Mapped[float | None] = mapped_column(Float)
    paper_role: Mapped[str | None] = mapped_column(String(32))  # analysis|detection|survey|exploit
    doi: Mapped[str | None] = mapped_column(String(128))
    arxiv_id: Mapped[str | None] = mapped_column(String(32))
    item: Mapped[Item] = relationship(back_populates="papers")


class MappingLink(Base):
    """CVE→CWE→CAPEC→ATT&CK/ATLAS 关联链"""
    __tablename__ = "mapping_links"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    item_id: Mapped[str] = mapped_column(ForeignKey("items.id", ondelete="CASCADE"), index=True)
    cve_id: Mapped[str | None] = mapped_column(String(32), index=True)
    cwe_id: Mapped[str | None] = mapped_column(String(32), index=True)
    capec_id: Mapped[str | None] = mapped_column(String(32))
    attack_technique: Mapped[str | None] = mapped_column(String(32), index=True)  # ATT&CK T-id
    atlas_technique: Mapped[str | None] = mapped_column(String(32))               # ATLAS AML.T-id
    source: Mapped[str] = mapped_column(String(32))  # nvd|ctid|cve2capec|llm|official
    confidence: Mapped[float] = mapped_column(Float, default=0.5)


class TaskRun(Base):
    """任务运行记录（可观测性）"""
    __tablename__ = "task_runs"
    __table_args__ = (Index("ix_task_name_time", "task_name", "started_at"),)

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    task_name: Mapped[str] = mapped_column(String(128), index=True)
    item_id: Mapped[str | None] = mapped_column(String(32), index=True)
    status: Mapped[str] = mapped_column(String(16), default="running")  # running|success|error|skipped
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    detail: Mapped[dict] = mapped_column(JSONB, default=dict)


class QaSession(Base):
    __tablename__ = "qa_sessions"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    title: Mapped[str | None] = mapped_column(String(256))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    meta: Mapped[dict] = mapped_column(JSONB, default=dict)


class QaMessage(Base):
    __tablename__ = "qa_messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    session_id: Mapped[str] = mapped_column(ForeignKey("qa_sessions.id", ondelete="CASCADE"), index=True)
    role: Mapped[str] = mapped_column(String(16))  # user|assistant
    content: Mapped[str] = mapped_column(Text)
    trace: Mapped[dict] = mapped_column(JSONB, default=dict)      # 推理链：路由/子问题/证据/KG路径
    citations: Mapped[dict] = mapped_column(JSONB, default=list)  # [{n,title,url,item_id,score}]
    confidence: Mapped[float | None] = mapped_column(Float)
    latency_ms: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Report(Base):
    """自动生成的情报报告（日报/周报/专题）"""
    __tablename__ = "reports"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    report_type: Mapped[str] = mapped_column(String(24))  # daily|weekly|topic|incident
    title: Mapped[str] = mapped_column(String(512))
    period_start: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    period_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    content_md: Mapped[str] = mapped_column(Text)
    stats: Mapped[dict] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class DedupCluster(Base):
    """近重复簇（审计用）"""
    __tablename__ = "dedup_clusters"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    raw_item_id: Mapped[str] = mapped_column(String(32), index=True)
    item_id: Mapped[str] = mapped_column(String(32), index=True)
    match_method: Mapped[str] = mapped_column(String(24))  # url_hash|entity|fingerprint|simhash|minhash|vector|new
    match_score: Mapped[float | None] = mapped_column(Float)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
