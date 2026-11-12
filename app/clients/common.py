import json
import logging
from typing import Any

import httpx

from app.config import get_settings
from app.core.redis_client import get_redis

log = logging.getLogger(__name__)

_http: httpx.AsyncClient | None = None


def get_http() -> httpx.AsyncClient:
    global _http
    if _http is None:
        _http = httpx.AsyncClient(timeout=get_settings().http_timeout_seconds)
    return _http


async def close_http() -> None:
    global _http
    client, _http = _http, None
    if client is not None:
        try:
            await client.aclose()
        except Exception:  # noqa: BLE001 - lỗi khi đóng không được làm sập quá trình tắt service
            pass


class UpstreamError(Exception):
    """Service nội bộ không phản hồi hoặc trả lỗi."""


async def fetch_result(url: str, params: dict[str, Any] | None = None) -> Any:
    """GET và bóc trường `result` của ApiResponse {code, message, result}."""
    try:
        resp = await get_http().get(url, params=params)
        resp.raise_for_status()
        return resp.json().get("result")
    except (httpx.HTTPError, ValueError) as e:
        log.warning("Gọi %s thất bại: %s", url, e)
        raise UpstreamError(str(e)) from e


async def cached_fetch(cache_key: str, ttl: int, url: str, params: dict[str, Any] | None = None) -> Any:
    """fetch_result + cache Redis. Redis lỗi thì đi thẳng tới service."""
    try:
        cached = await get_redis().get(cache_key)
        if cached:
            return json.loads(cached)
    except Exception:  # noqa: BLE001
        pass
    data = await fetch_result(url, params)
    try:
        await get_redis().set(cache_key, json.dumps(data, ensure_ascii=False), ex=ttl)
    except Exception:  # noqa: BLE001
        pass
    return data
