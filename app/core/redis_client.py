import redis.asyncio as redis

from app.config import get_settings

_client: redis.Redis | None = None


def get_redis() -> redis.Redis:
    global _client
    if _client is None:
        s = get_settings()
        _client = redis.Redis(host=s.redis_host, port=s.redis_port, decode_responses=True)
    return _client


async def close_redis() -> None:
    """Đóng kết nối khi tắt service. Lỗi khi đóng (vd vòng lặp đã đóng) không được làm sập quá trình tắt."""
    global _client
    client, _client = _client, None
    if client is not None:
        try:
            await client.aclose()
        except Exception:  # noqa: BLE001
            pass
