from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.config import get_settings
from app.core.auth import CurrentUser, get_current_user
from app.core.rate_limit import check_rate_limit
from app.llm import chat_service
from app.memory import history

router = APIRouter(prefix="/chatbot")


class ChatRequest(BaseModel):
    message: str = ""
    conversationId: str | None = None  # frontend gửi nhưng chưa dùng


def ok(result: Any = None) -> dict[str, Any]:
    return {"code": 1000, "result": result}


@router.post("/message")
async def send_message(body: ChatRequest, user: CurrentUser = Depends(get_current_user)):
    s = get_settings()
    await check_rate_limit(user.user_id)
    message = body.message.strip()[: s.max_message_chars]  # cắt thay vì từ chối
    return ok(await chat_service.process_message(user.user_id, message))


@router.get("/history")
async def get_history(user: CurrentUser = Depends(get_current_user)):
    return ok(await history.get_history(user.user_id))


@router.delete("/history")
async def clear_history(user: CurrentUser = Depends(get_current_user)):
    await history.clear_history(user.user_id)
    return ok("Đã xóa lịch sử trò chuyện thành công!")


@router.get("/health")
async def health():
    return ok("Chatbot Service is running")
