"""统一 HTTP 客户端：每源令牌桶限流 + 指数退避重试 + 条件GET"""
from __future__ import annotations

import asyncio
import time
from collections import defaultdict

import httpx
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from app.config import get_settings
from app.core.logging import get_logger

log = get_logger("http")


class RateLimiter:
    """每域名令牌桶（简单间隔限流）"""

    def __init__(self):
        self._locks: dict[str, asyncio.Lock] = defaultdict(asyncio.Lock)
        self._last: dict[str, float] = {}
        self._min_interval: dict[str, float] = {}

    def set_interval(self, host: str, seconds: float) -> None:
        self._min_interval[host] = seconds

    async def acquire(self, host: str) -> None:
        interval = self._min_interval.get(host, 1.0)
        async with self._locks[host]:
            now = time.monotonic()
            wait = self._last.get(host, 0) + interval - now
            if wait > 0:
                await asyncio.sleep(wait)
            self._last[host] = time.monotonic()


rate_limiter = RateLimiter()
# 默认限流（秒/请求）
rate_limiter.set_interval("services.nvd.nist.gov", 6.0 if not get_settings().nvd_api_key else 1.0)
rate_limiter.set_interval("api.github.com", 2.0)
rate_limiter.set_interval("export.arxiv.org", 3.0)
rate_limiter.set_interval("api.semanticscholar.org", 1.0)
rate_limiter.set_interval("hunter.qianxin.com", 2.0)
rate_limiter.set_interval("hn.algolia.com", 1.0)
rate_limiter.set_interval("api.osv.dev", 0.3)
rate_limiter.set_interval("www.cisa.gov", 2.0)
rate_limiter.set_interval("api.first.org", 1.0)

_client: httpx.AsyncClient | None = None


def get_client() -> httpx.AsyncClient:
    global _client
    if _client is None:
        s = get_settings()
        _client = httpx.AsyncClient(
            timeout=httpx.Timeout(s.request_timeout, connect=10.0),
            headers={"User-Agent": s.user_agent, "Accept-Encoding": "gzip, deflate"},
            follow_redirects=True,
            limits=httpx.Limits(max_connections=50, max_keepalive_connections=20),
        )
    return _client


class FetchError(Exception):
    pass


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=30),
    retry=retry_if_exception_type((httpx.TransportError, httpx.TimeoutException, FetchError)),
    reraise=True,
)
async def fetch(
    url: str,
    *,
    method: str = "GET",
    headers: dict | None = None,
    params: dict | None = None,
    json_body: dict | None = None,
    content: bytes | None = None,
    etag: str | None = None,
    last_modified: str | None = None,
    rate_limit: bool = True,
) -> httpx.Response:
    """统一抓取入口：限流+条件GET+重试。304 时返回 status_code=304 的响应。"""
    client = get_client()
    host = httpx.URL(url).host
    if rate_limit:
        await rate_limiter.acquire(host)
    hdrs = dict(headers or {})
    if etag:
        hdrs["If-None-Match"] = etag
    if last_modified:
        hdrs["If-Modified-Since"] = last_modified
    resp = await client.request(method, url, headers=hdrs, params=params, json=json_body, content=content)
    if resp.status_code == 429:
        retry_after = float(resp.headers.get("Retry-After", "10"))
        log.warning("rate_limited", host=host, retry_after=retry_after)
        await asyncio.sleep(min(retry_after, 60))
        raise FetchError(f"429 from {host}")
    if resp.status_code >= 500:
        raise FetchError(f"{resp.status_code} from {url}")
    return resp
