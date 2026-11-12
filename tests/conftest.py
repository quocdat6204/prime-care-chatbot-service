"""Mặc định test chạy chế độ 'rules' (xác định, không phụ thuộc model). Test của chế độ 'model' tự bật bằng fixture model_mode."""
import os

os.environ["INTENT_MODE"] = "rules"  # đặt trước khi Settings được tạo; biến môi trường thắng file .env

import pytest  # noqa: E402

from app.config import get_settings  # noqa: E402


@pytest.fixture
def model_mode(monkeypatch):
    s = get_settings()
    monkeypatch.setattr(s, "intent_mode", "model")
    return s
