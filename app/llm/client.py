import logging

from openai import AsyncOpenAI

from app.config import get_settings

log = logging.getLogger(__name__)

_client: AsyncOpenAI | None = None


def get_openai() -> AsyncOpenAI | None:
    """None nếu chưa cấu hình API key (service vẫn chạy, chat trả thông báo)."""
    global _client
    s = get_settings()
    if not s.openai_api_key.strip():
        return None
    if _client is None:
        # max_retries: SDK tự retry lỗi mạng/429/5xx với backoff
        _client = AsyncOpenAI(api_key=s.openai_api_key, timeout=s.openai_timeout_seconds, max_retries=2)
    return _client
