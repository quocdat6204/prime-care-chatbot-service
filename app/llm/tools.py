"""Định nghĩa tool cho OpenAI và hàm thực thi.

Mỗi tool trả về dict JSON-serializable. Lỗi upstream được đổi thành {"error": ...}
để model nói "chưa tra cứu được" thay vì bịa.
"""
import asyncio
import json
from datetime import date as date_cls
from datetime import timedelta
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

from app.clients import clinic, user
from app.clients.common import UpstreamError

_CLINIC_INFO = json.loads(
    (Path(__file__).resolve().parent.parent / "data" / "clinic_info.json").read_text(encoding="utf-8")
)

BOOKING_PATH = "/patient/booking"
APPOINTMENTS_PATH = "/patient/appointments"
BOOKING_LABEL = "Đặt lịch hẹn"
HINT_TYPE = "_hint"


def booking_action(url: str = BOOKING_PATH) -> dict[str, Any]:
    return {"type": "booking", "label": BOOKING_LABEL, "url": url}


def appointments_action() -> dict[str, Any]:
    return {"type": "appointments", "label": "Lịch hẹn của tôi", "url": APPOINTMENTS_PATH}

TOOL_DEFINITIONS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "get_clinic_info",
            "description": "Lấy thông tin phòng khám: hotline, email, địa chỉ các cơ sở, giờ làm việc theo ca, cách đặt lịch, thanh toán, FAQ.",
            "parameters": {"type": "object", "properties": {}, "additionalProperties": False},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "find_doctors",
            "description": "Tra danh sách bác sĩ của phòng khám (id, họ tên, học hàm). Truyền name để lọc theo tên; bỏ trống để lấy tất cả.",
            "parameters": {
                "type": "object",
                "properties": {"name": {"type": "string", "description": "Tên hoặc một phần tên bác sĩ, có thể không dấu"}},
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "find_services",
            "description": "Tra dịch vụ và giá của phòng khám (nha khoa, xét nghiệm, chẩn đoán hình ảnh). Truyền keyword (ví dụ 'nhổ răng', 'x-quang', 'cao răng'); bỏ trống để lấy các dịch vụ tiêu biểu.",
            "parameters": {
                "type": "object",
                "properties": {"keyword": {"type": "string", "description": "Từ khóa tên dịch vụ"}},
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_schedule",
            "description": "Tra các ca khám đang mở: bác sĩ, ngày, ca, số chỗ còn trống, phí khám. Mặc định tra 1 ngày; truyền days (tối đa 7) để tra nhiều ngày liên tiếp bắt đầu từ date (ví dụ cả tuần). Có thể lọc theo bác sĩ: ƯU TIÊN truyền doctor_name (đúng tên bệnh nhân nhắc, hệ thống tự tìm bác sĩ); chỉ dùng doctor_id khi đã lấy được từ find_doctors, TUYỆT ĐỐI không tự đoán doctor_id.",
            "parameters": {
                "type": "object",
                "properties": {
                    "date": {"type": "string", "description": "Ngày dạng YYYY-MM-DD"},
                    "doctor_name": {"type": "string", "description": "Tên (hoặc một phần tên) bác sĩ bệnh nhân nhắc tới, tùy chọn"},
                    "doctor_id": {"type": "integer", "description": "ID bác sĩ, tùy chọn"},
                    "days": {"type": "integer", "description": "Số ngày liên tiếp cần tra, từ 1 đến 7 (mặc định 1)"},
                },
                "required": ["date"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_booking_link",
            "description": "Tạo nút/liên kết mở trang đặt lịch khám trên website (có thể kèm ngày và/hoặc bác sĩ). Chỉ gọi khi bệnh nhân THỰC SỰ muốn đặt lịch hoặc cần hướng dẫn đặt; KHÔNG gọi nếu họ phủ định (không muốn đặt) hoặc chỉ hỏi thông tin.",
            "parameters": {
                "type": "object",
                "properties": {
                    "date": {"type": "string", "description": "Ngày dạng YYYY-MM-DD, tùy chọn"},
                    "doctor_name": {"type": "string", "description": "Tên bác sĩ bệnh nhân nhắc tới, tùy chọn (ưu tiên hơn doctor_id; không tự đoán id)"},
                    "doctor_id": {"type": "integer", "description": "ID bác sĩ, tùy chọn"},
                },
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_appointments_link",
            "description": "Tạo nút mở trang 'Lịch hẹn của tôi' để bệnh nhân tự xem, hủy hoặc đổi các lịch đã đặt. Gọi khi bệnh nhân hỏi về lịch hẹn của CHÍNH HỌ (xem, hủy, đổi, kiểm tra đã đặt chưa), kể cả khi họ không dùng từ 'lịch hẹn'. Bot không thể xem hay hủy lịch hộ.",
            "parameters": {"type": "object", "properties": {}, "additionalProperties": False},
        },
    }
]

# Tool nào -> intent (frontend dùng để hiển thị gợi ý)
TOOL_INTENTS = {
    "get_clinic_info": "CLINIC_INFO",
    "find_doctors": "DOCTOR_INFO",
    "find_services": "CHECK_SERVICE",
    "get_schedule": "CHECK_SCHEDULE",
    "get_booking_link": "BOOKING",
    "get_appointments_link": "MY_APPOINTMENTS",
}


def _valid_date(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    try:
        date_cls.fromisoformat(value)
        return value
    except ValueError:
        return None


def _valid_id(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int) and value > 0:
        return value
    if isinstance(value, str) and value.isdigit() and int(value) > 0:
        return int(value)
    return None


def _valid_days(value: Any) -> int:
    """Số ngày tra lịch: 1..7, mặc định 1."""
    try:
        n = int(value)
    except (TypeError, ValueError):
        return 1
    return max(1, min(7, n))


class DoctorError(Exception):
    """Không xác định được bác sĩ mà model nhắc tới (không tìm thấy, nhiều người trùng, hoặc id sai)."""


async def _resolve_doctor(args: dict[str, Any]) -> dict[str, Any] | None:
    """Trả {'id','name'} của bác sĩ được chỉ định, hoặc None nếu không chỉ định ai.

    Không tin mã bác sĩ do model tự đoán: ưu tiên doctor_name (tìm trong danh sách thật), còn doctor_id thì phải
    tồn tại trong danh sách. Sai/nhập nhằng -> DoctorError để model tra lại thay vì tra nhầm lịch người khác."""
    name = args.get("doctor_name")
    if isinstance(name, str) and name.strip():
        matches = await user.find_doctors(name)
        if len(matches) == 1:
            return {"id": matches[0]["id"], "name": matches[0]["name"]}
        if not matches:
            raise DoctorError(f"Không tìm thấy bác sĩ tên '{name.strip()}' trong phòng khám. Hãy báo bệnh nhân và gợi ý xem danh sách bác sĩ.")
        names = ", ".join(m["name"] for m in matches)
        raise DoctorError(f"Có nhiều bác sĩ khớp '{name.strip()}': {names}. Hãy hỏi bệnh nhân muốn bác sĩ nào.")
    doc_id = _valid_id(args.get("doctor_id"))
    if doc_id is None:
        return None
    for d in await user.list_doctors():
        if d["id"] == doc_id:
            return {"id": d["id"], "name": d["name"]}
    raise DoctorError("doctor_id không tồn tại. Hãy dùng doctor_name hoặc tra find_doctors, không tự đoán id.")


def build_booking_url(date: str | None, doctor_id: int | None) -> str:
    params: dict[str, Any] = {}
    if date:
        params["date"] = date
    if doctor_id:
        params["doctorId"] = doctor_id
    return f"{BOOKING_PATH}?{urlencode(params)}" if params else BOOKING_PATH


async def execute_tool(name: str, args: dict[str, Any]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Trả (kết quả cho model, danh sách action cho frontend)."""
    actions: list[dict[str, Any]] = []
    try:
        if name == "get_clinic_info":
            return _CLINIC_INFO, actions

        if name == "find_doctors":
            doctors = await user.find_doctors(args.get("name"))
            return {"count": len(doctors), "doctors": doctors[:30]}, actions

        if name == "find_services":
            services = await clinic.find_services(args.get("keyword"))
            result: dict[str, Any] = {"count": len(services), "services": services}
            if len(services) >= clinic.SERVICE_PAGE_SIZE:
                result["note"] = "Danh sách có thể chưa đầy đủ (hệ thống giới hạn số dịch vụ trả về); hãy gợi ý bệnh nhân hỏi tên dịch vụ cụ thể hơn."
            return result, actions

        if name == "get_schedule":
            d = _valid_date(args.get("date"))
            if not d:
                return {"error": "Ngày không hợp lệ, cần định dạng YYYY-MM-DD"}, actions
            doctor = await _resolve_doctor(args)
            doc = doctor["id"] if doctor else None
            days = _valid_days(args.get("days"))
            start = date_cls.fromisoformat(d)
            dates = [(start + timedelta(days=i)).isoformat() for i in range(days)]
            per_day = await asyncio.gather(*[clinic.get_sessions(x, doc) for x in dates])
            sessions = [s for day in per_day for s in day]
            with_slots = sum(1 for s in sessions if (s.get("available_slots") or 0) > 0)
            # gợi ý nội bộ để nút đặt lịch tự kèm đúng ngày/bác sĩ; bị lọc trước khi trả về frontend
            actions.append({"type": HINT_TYPE, "date": d, "doctor_id": doc})
            result = {
                "date": d, "from_date": d, "to_date": dates[-1], "days": days,
                "count": len(sessions), "open_sessions": len(sessions), "sessions_with_free_slots": with_slots,
                "sessions": sessions,
            }
            if doctor:
                result["doctor"] = doctor  # để model gọi đúng tên bác sĩ đã được tra
            if not sessions:
                result["note"] = ("Hệ thống KHÔNG có ca khám nào đang mở trong khoảng này (chưa có ca được tạo hoặc ca đã đóng; "
                                  "ngày đã qua luôn không có ca). Hãy nói đúng như vậy, đừng nói là 'hết chỗ'.")
            elif with_slots == 0:
                result["note"] = "Có ca khám đang mở nhưng TẤT CẢ đã hết chỗ."
            return result, actions

        if name == "get_appointments_link":
            actions.append(appointments_action())
            return {"ok": True, "note": "Đã tạo nút 'Lịch hẹn của tôi'. Bệnh nhân tự xem, hủy hoặc đổi lịch ở trang đó; bạn không thể xem hay hủy hộ."}, actions

        if name == "get_booking_link":
            d = _valid_date(args.get("date"))
            doctor = await _resolve_doctor(args)
            url = build_booking_url(d, doctor["id"] if doctor else None)
            actions.append(booking_action(url))
            return {"ok": True, "note": "Đã tạo nút Đặt lịch cho bệnh nhân."}, actions

        return {"error": f"Công cụ không tồn tại: {name}"}, actions
    except DoctorError as e:
        return {"error": str(e)}, []
    except UpstreamError:
        return {"error": "Không tra cứu được dữ liệu từ hệ thống phòng khám lúc này."}, actions
