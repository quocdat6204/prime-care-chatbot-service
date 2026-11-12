import logging
from typing import Any

from app.clients.common import cached_fetch, fetch_result
from app.config import get_settings

log = logging.getLogger(__name__)

SERVICE_PAGE_SIZE = 15  # clinic-service chỉ trả tối đa 15 dịch vụ mỗi lần

SERVICE_TYPES = {
    "DENTAL": "Nha khoa",
    "LAB_TEST": "Xét nghiệm",
    "IMAGING": "Chẩn đoán hình ảnh",
}
SHIFTS = {
    "MORNING": "Ca sáng (08:00 - 12:00)",
    "AFTERNOON": "Ca chiều (13:30 - 17:30)",
}


async def find_services(keyword: str | None = None) -> list[dict[str, Any]]:
    s = get_settings()
    kw = (keyword or "").strip().lower()[:60]  # giới hạn độ dài: keyword do model sinh ra, dùng làm khoá cache
    raw = await cached_fetch(
        f"chat:cache:services:{kw}",
        s.services_cache_seconds,
        f"{s.clinic_service_url}/internal/clinic/chatbot/services",
        {"keyword": kw} if kw else None,
    )
    out = []
    for item in raw or []:
        out.append(
            {
                "name": item.get("name"),
                "type": SERVICE_TYPES.get(item.get("serviceType") or "", item.get("serviceType")),
                "price_vnd": int(item["price"]) if item.get("price") is not None else None,
                "room": item.get("roomNumber"),
                "description": item.get("description"),
            }
        )
    return out


async def get_sessions(date: str, doctor_id: int | None = None) -> list[dict[str, Any]]:
    """Ca khám theo ngày. Không cache vì số chỗ trống thay đổi liên tục."""
    s = get_settings()
    params: dict[str, Any] = {"date": date}
    if doctor_id is not None:
        params["doctorId"] = doctor_id
    raw = await fetch_result(f"{s.clinic_service_url}/internal/clinic/chatbot/sessions", params)
    log.info("get_sessions date=%s doctor_id=%s -> %d ca khám đang mở", date, doctor_id, len(raw or []))
    out = []
    for item in raw or []:
        slots = item.get("availableSlots")
        if slots is None:
            slots = max(0, int(item.get("maxPatients") or 0) - int(item.get("lastQueueNumber") or 0))
        out.append(
            {
                "doctor_id": item.get("doctorId"),
                "doctor_name": item.get("doctorName"),
                "date": item.get("examDate"),
                "shift": SHIFTS.get(item.get("shift") or "", item.get("shift")),
                "available_slots": slots,
                "max_patients": item.get("maxPatients"),
                "exam_fee_vnd": int(item["examinationFee"]) if item.get("examinationFee") is not None else None,
            }
        )
    return out
