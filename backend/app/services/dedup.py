"""四层去重与跨源实体对齐流水线

L1 URL 规范化哈希 → L2 编号实体对齐（CVE/GHSA/CNVD/CNNVD/EDB union-find）
→ L3 标题指纹 + SimHash → L4 MinHash-LSH / 向量近重复
"""
from __future__ import annotations

from datasketch import MinHash, MinHashLSH
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.ids import extract_ids, hamming, simhash64, title_fingerprint, url_sha256
from app.core.logging import get_logger
from app.db.models import DedupCluster, Item, RawItem

log = get_logger("dedup")

# 全局 MinHash LSH 索引（进程内；重启后从 DB 重建）
_lsh = MinHashLSH(threshold=0.7, num_perm=128)
_lsh_loaded = False


def _minhash(text: str) -> MinHash:
    m = MinHash(num_perm=128)
    text = (text or "")[:3000].lower()
    shingles = {text[i:i + 5] for i in range(0, max(0, len(text) - 4), 3)}
    for s in shingles:
        m.update(s.encode())
    return m


async def _load_lsh(db: AsyncSession) -> None:
    global _lsh_loaded
    if _lsh_loaded:
        return
    rows = (await db.execute(select(RawItem.id, RawItem.content_text).limit(50000))).all()
    for rid, text in rows:
        if text:
            try:
                _lsh.insert(rid, _minhash(text))
            except ValueError:
                pass
    _lsh_loaded = True
    log.info("lsh_loaded", count=len(rows))


async def find_match(db: AsyncSession, raw: RawItem, extracted: dict) -> tuple[Item | None, str, float]:
    """为 raw_item 找已有 Item（情报卡片）。返回 (item, method, score)"""
    await _load_lsh(db)

    # L2: 编号实体对齐（CVE/GHSA/CNVD 任一命中即合并；优先于 URL，防目录页误合并）
    cve_ids = extracted.get("cve", [])
    if cve_ids:
        it = (await db.execute(
            select(Item).where(Item.cve_ids.overlap(cve_ids)).limit(1)
        )).scalar_one_or_none()
        if it:
            return it, "entity", 1.0
    ghsa_ids = extracted.get("ghsa", [])
    if ghsa_ids:
        it = (await db.execute(
            select(Item).where(Item.ghsa_ids.overlap(ghsa_ids)).limit(1)
        )).scalar_one_or_none()
        if it:
            return it, "entity", 1.0
    for field, key in ((Item.cnvd_ids, "cnvd"), (Item.cnnvd_ids, "cnnvd"), (Item.edb_ids, "edb")):
        ids = extracted.get(key, [])
        if ids:
            it = (await db.execute(select(Item).where(field.overlap(ids)).limit(1))).scalar_one_or_none()
            if it:
                return it, "entity", 1.0

    # L1: URL 哈希（仅当双方 CVE 集合不冲突时合并，避免聚合页同 URL 误并）
    if raw.url_sha256:
        it = (await db.execute(
            select(Item).where(Item.url_sha256 == raw.url_sha256).limit(1)
        )).scalar_one_or_none()
        if it and _id_compatible(it, extracted):
            return it, "url_hash", 1.0

    # L3: 标题指纹精确 + SimHash 近重复
    fp = title_fingerprint(raw.title or "")
    if fp:
        it = (await db.execute(select(Item).where(Item.title_fingerprint == fp).limit(1))).scalar_one_or_none()
        if it and _id_compatible(it, extracted):
            return it, "fingerprint", 1.0
    sh = simhash64((raw.title or "") + " " + (raw.content_text or "")[:500])
    candidates = (await db.execute(
        select(Item).where(Item.simhash64.isnot(None)).order_by(Item.first_seen_at.desc()).limit(2000)
    )).scalars().all()
    for it in candidates:
        if hamming(sh, it.simhash64 or 0) <= 3 and _id_compatible(it, extracted):
            return it, "simhash", 0.95

    # L4: MinHash-LSH 正文近重复（转载稿合并）
    if raw.content_text:
        try:
            results = _lsh.query(_minhash(raw.content_text))
            if results:
                # 找到这些 raw_item 所属的 item
                rows = (await db.execute(
                    select(DedupCluster.item_id).where(DedupCluster.raw_item_id.in_(results[:10])).limit(1)
                )).scalars().all()
                if rows:
                    it = (await db.execute(select(Item).where(Item.id == rows[0]).limit(1))).scalar_one_or_none()
                    if it:
                        return it, "minhash", 0.85
        except Exception:  # noqa: BLE001
            pass

    return None, "new", 0.0


def _id_compatible(item: Item, extracted: dict) -> bool:
    """URL/指纹匹配附加守卫：双方均携带编号且不相交 → 不合并"""
    new_ids = set(extracted.get("cve", [])) | set(extracted.get("ghsa", []))
    if not new_ids:
        return True
    old_ids = set(item.cve_ids or []) | set(item.ghsa_ids or [])
    if not old_ids:
        return True  # 旧条目无编号 → 视作文档聚合页，允许 URL 合并
    return bool(old_ids & new_ids)


def register_minhash(raw: RawItem) -> None:
    if raw.content_text:
        try:
            _lsh.insert(raw.id, _minhash(raw.content_text))
        except ValueError:
            pass
