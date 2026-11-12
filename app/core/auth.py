"""Xác thực JWT (HS512) do user-service phát hành. Bắt buộc đăng nhập."""
from dataclasses import dataclass

import jwt
from fastapi import Header, HTTPException

from app.config import get_settings


@dataclass(frozen=True)
class CurrentUser:
    user_id: str  # claim `sub` = uuid của user
    role: str | None


def decode_token(token: str, secret: str) -> CurrentUser:
    if len(secret.encode("utf-8")) < 64:
        # user-service cũng yêu cầu >= 64 byte cho HS512
        raise HTTPException(status_code=503, detail="Chatbot chưa được cấu hình JWT_SECRET_KEY hợp lệ")
    try:
        payload = jwt.decode(
            token,
            secret.encode("utf-8"),
            algorithms=["HS512"],
            options={"require": ["exp", "sub"]},
        )
    except jwt.PyJWTError:
        raise HTTPException(status_code=401, detail="Token không hợp lệ hoặc đã hết hạn")
    return CurrentUser(user_id=str(payload["sub"]), role=payload.get("role"))


async def get_current_user(authorization: str | None = Header(default=None)) -> CurrentUser:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Vui lòng đăng nhập để sử dụng trợ lý AI")
    return decode_token(authorization[7:].strip(), get_settings().jwt_secret_key)
