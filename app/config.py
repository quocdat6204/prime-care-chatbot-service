from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # OpenAI
    # repr=False: khoá bí mật không bao giờ lộ trong log, traceback hay thông báo lỗi của test
    openai_api_key: str = Field(default="", repr=False)
    openai_chat_model: str = "gpt-4o-mini"
    openai_timeout_seconds: float = 30.0
    openai_max_output_tokens: int = 700
    openai_temperature: float = 0.3

    # "model": model tự hiểu ý định đặt lịch/xem lịch hẹn và tự gọi công cụ (code chỉ giữ quyền phủ quyết khi người dùng phủ định)
    # "rules": ép nút theo từ khoá trong câu người dùng (chắc chắn có nút nhưng mù với cách nói lạ)
    intent_mode: str = "model"
    # Model suy luận (gpt-5, o1, o3, o4...) không nhận temperature và cần nhiều token hơn vì tính cả token suy nghĩ
    openai_reasoning_max_tokens: int = 2500

    # Service
    chatbot_service_port: int = 9004

    # JWT (HS512, dùng chung với user-service)
    jwt_secret_key: str = Field(default="", repr=False)

    # Redis
    redis_host: str = "localhost"
    redis_port: int = 6379

    # Service khác
    user_service_url: str = "http://localhost:9001"
    clinic_service_url: str = "http://localhost:9003"
    http_timeout_seconds: float = 8.0

    # Eureka
    eureka_enabled: bool = True
    eureka_url: str = "http://localhost:8761/eureka/"
    eureka_instance_host: str = ""

    # Giới hạn
    max_message_chars: int = 500
    rate_limit_per_minute: int = 20
    history_max_messages: int = 20
    history_context_messages: int = 10
    history_ttl_seconds: int = 24 * 3600
    max_tool_rounds: int = 3

    # Cache
    doctors_cache_seconds: int = 300
    services_cache_seconds: int = 120

    timezone: str = "Asia/Ho_Chi_Minh"


@lru_cache
def get_settings() -> Settings:
    return Settings()
