"""Redis 客户端单例 —— 任务/运行状态存储（pipeline runs、轻量缓存）"""
from __future__ import annotations

import redis.asyncio as aioredis

from app.config import get_settings

_rds = None


def rds() -> aioredis.Redis:
    global _rds
    if _rds is None:
        s = get_settings()
        _rds = aioredis.Redis(host=s.redis_host, port=s.redis_port, decode_responses=True)
    return _rds
