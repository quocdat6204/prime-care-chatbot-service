"""Lịch sử hội thoại theo từng user (Redis list). Mỗi user có key riêng, không dùng chung."""
import json
import logging
from typing import Any

from app.config import get_settings
from app.core.redis_client import get_redis

log = logging.getLogger(__name__)


def _key(user_id: str) -> str:
    return f"chat:history:{user_id}"


async def save_message(user_id: str, message: dict[str, Any]) -> None:
    s = get_settings()
    try:
        r = get_redis()
        key = _key(user_id)
        await r.rpush(key, json.dumps(message, ensure_ascii=False))
        await r.ltrim(key, -s.history_max_messages, -1)
        await r.expire(key, s.history_ttl_seconds)
    except Exception as e:  # noqa: BLE001
        log.warning("Không lưu được lịch sử chat: %s", e)


async def get_history(user_id: str) -> list[dict[str, Any]]:
    try:
        raw = await get_redis().lrange(_key(user_id), 0, -1)
    except Exception as e:  # noqa: BLE001
        log.warning("Không đọc được lịch sử chat: %s", e)
        return []
    out: list[dict[str, Any]] = []
    for item in raw:
        try:
            out.append(json.loads(item))
        except ValueError:
            continue
    return out


async def clear_history(user_id: str) -> None:
    try:
        await get_redis().delete(_key(user_id))
    except Exception as e:  # noqa: BLE001
        log.warning("Không xoá được lịch sử chat: %s", e)


async def get_context_messages(user_id: str) -> list[dict[str, str]]:
    """Các tin gần nhất dạng role/content cho LLM (chỉ văn bản)."""
    s = get_settings()
    history = await get_history(user_id)
    msgs = []
    for m in history[-s.history_context_messages:]:
        role = "user" if m.get("sender") == "user" else "assistant"
        text = m.get("text")
        if text:
            msgs.append({"role": role, "content": text})
    return msgs
