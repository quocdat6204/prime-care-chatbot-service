import logging
import socket
from contextlib import asynccontextmanager
from urllib.parse import urlparse

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.api.chat import router as chat_router
from app.clients.common import close_http
from app.config import get_settings
from app.core.redis_client import close_redis

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("chatbot")


def detect_instance_host(eureka_url: str) -> str:
    """IP của card mạng dùng để tới Eureka (Eureka ở localhost thì ra 127.0.0.1)."""
    parsed = urlparse(eureka_url)
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.connect((parsed.hostname or "localhost", parsed.port or 8761))  # UDP: không gửi gói nào
            return sock.getsockname()[0]
    except OSError:
        return "127.0.0.1"


@asynccontextmanager
async def lifespan(app: FastAPI):
    s = get_settings()
    eureka_started = False
    if s.openai_api_key.strip() == "":
        log.warning("OPENAI_API_KEY chưa được cấu hình - chatbot sẽ trả thông báo 'chưa cấu hình'.")
    if s.eureka_enabled:
        try:
            from py_eureka_client import eureka_client

            # Không để thư viện tự đoán IP: trên Windows nó hay lấy nhầm card mạng ảo
            # (169.254.x.x) khiến gateway không gọi tới được chatbot.
            host = s.eureka_instance_host or detect_instance_host(s.eureka_url)
            kwargs = {"instance_host": host, "instance_ip": host}
            log.info("Đăng ký Eureka với địa chỉ %s:%s", host, s.chatbot_service_port)
            await eureka_client.init_async(
                eureka_server=s.eureka_url,
                app_name="chatbot-service",
                instance_port=s.chatbot_service_port,
                **kwargs,
            )
            eureka_started = True
            log.info("Đã đăng ký Eureka: %s", s.eureka_url)
        except Exception as e:  # noqa: BLE001 - lỗi Eureka không được làm sập service
            log.error("Không đăng ký được Eureka (%s). Gateway lb://chatbot-service sẽ không thấy service.", e)
    yield
    if eureka_started:
        try:
            await eureka_client.stop_async()
        except Exception:  # noqa: BLE001
            pass
    await close_http()
    await close_redis()


app = FastAPI(title="PrimeCare Chatbot Service", lifespan=lifespan)
app.include_router(chat_router)


@app.exception_handler(HTTPException)
async def http_exc_handler(_: Request, exc: HTTPException):
    return JSONResponse(status_code=exc.status_code, content={"code": 1000 + exc.status_code, "message": exc.detail})


@app.exception_handler(RequestValidationError)
async def validation_exc_handler(_: Request, exc: RequestValidationError):
    return JSONResponse(status_code=422, content={"code": 1422, "message": "Dữ liệu gửi lên không hợp lệ"})


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app.main:app", host="0.0.0.0", port=get_settings().chatbot_service_port)
