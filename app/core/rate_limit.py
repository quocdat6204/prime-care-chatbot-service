import time

from fastapi import HTTPException

from app.config import get_settings
from app.core.redis_client import get_redis


async def check_rate_limit(user_id: str) -> None:
    """Tối đa N tin/phút/người. Redis lỗi thì bỏ qua giới hạn (không chặn người dùng)."""
    s = get_settings()
    window = int(time.time() // 60)
    key = f"chat:rl:{user_id}:{window}"
    try:
        r = get_redis()
        count = await r.incr(key)
        if count == 1:
            await r.expire(key, 70)
    except Exception:
        return
    if count > s.rate_limit_per_minute:
        raise HTTPException(status_code=429, detail="Bạn gửi tin quá nhanh, vui lòng thử lại sau ít phút")
