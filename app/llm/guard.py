"""Lớp chặn bằng quy tắc, chạy TRƯỚC khi gọi model (rẻ và chắc chắn hơn chỉ dựa vào prompt)."""
import re

from app.clients.user import normalize

_INJECTION_PATTERNS = [
    r"ignore (all |any )?(the )?(previous|prior|above) (instructions|prompts?)",
    r"disregard (all |any )?(the )?(previous|prior|above)",
    r"(reveal|show|print|repeat) (your |the )?(system )?(prompt|instructions)",
    r"you are now",
    r"developer mode",
    r"jailbreak",
    # cần có từ chỉ "toàn bộ" hoặc "trước đó" để không chặn nhầm câu như "tôi quên hướng dẫn đặt lịch"
    r"(bo qua|quen) (moi|tat ca|het) (huong dan|chi dan|quy tac|lenh)",
    r"(bo qua|quen) .{0,12}(huong dan|chi dan|quy tac|lenh).{0,15}(truoc do|truoc day|ban dau|o tren)",
    r"system prompt|prompt he thong|huong dan he thong",
    r"dong vai .{0,30}(khong gioi han|khong bi rang buoc)",
]
_INJECTION_RE = re.compile("|".join(_INJECTION_PATTERNS))

REFUSAL_INJECTION = (
    "Dạ, mình chỉ có thể hỗ trợ các thông tin về phòng khám PrimeCare: bác sĩ, dịch vụ và giá, "
    "lịch khám, đặt lịch và kiến thức nha khoa cơ bản. Bạn cần mình giúp gì trong những mục này ạ?"
)


# --- Nhận diện ý định đặt lịch / xem lịch hẹn (chạy trên chuỗi đã bỏ dấu) ---
_BOOKING_RE = re.compile(r"\bdat (lich|hen)\b|hen kham|dang ky kham|\bbook(ing)?\b|muon (kham|hen)\b")
_MY_APPOINTMENTS_RE = re.compile(
    r"(lich hen|lich kham|lich da dat|cuoc hen)( cua)? (toi|minh|da dat)|xem lich (da|hen)|\bhuy lich\b|\bdoi lich\b"
)
# Nếu tin nhắn đã nêu bác sĩ/ngày thì để model tự tra rồi tạo link kèm tham số
_QUALIFIER_RE = re.compile(
    r"bac si|\bbs\b|\bdr\b|ngay|\bmai\b|hom nay|thu (hai|ba|tu|nam|sau|bay|[2-7])|chu nhat|\bcn\b|tuan|\d{1,2}/\d{1,2}|\d{4}-\d{2}-\d{2}"
)


# Phủ định đứng ngay trước hành động ("không đặt lịch", "chưa muốn đặt lịch", "đừng hủy lịch").
# Cố tình hẹp: "không biết cách đặt lịch" hay "có đặt lịch được không?" KHÔNG phải phủ định.
_NEG = r"(?:khong|chua|dung|khoi)\s+(?:can\s+|muon\s+|phai\s+|nen\s+|co nhu cau\s+)?"
_BOOKING_NEGATED_RE = re.compile(_NEG + r"(?:dat lich|dat hen|hen kham|dang ky kham|book(?:ing)?)\b")
_APPOINTMENTS_NEGATED_RE = re.compile(_NEG + r"(?:huy lich|doi lich)\b")
_PLAIN_MAX_WORDS = 12  # câu dài/phức tạp thì để model tự hiểu, không ép nút


def refuses_booking(message: str) -> bool:
    """Người dùng nói rõ là KHÔNG muốn đặt lịch."""
    return bool(_BOOKING_NEGATED_RE.search(normalize(message)))


def wants_my_appointments(message: str) -> bool:
    n = normalize(message)
    return bool(_MY_APPOINTMENTS_RE.search(n)) and not _APPOINTMENTS_NEGATED_RE.search(n)


def wants_booking(message: str) -> bool:
    n = normalize(message)
    return bool(_BOOKING_RE.search(n)) and not _MY_APPOINTMENTS_RE.search(n) and not _BOOKING_NEGATED_RE.search(n)


def is_plain_booking_request(message: str) -> bool:
    """Chỉ nói muốn đặt lịch (ngắn gọn, chưa nêu bác sĩ/ngày) -> trả nút ngay, không hỏi lại."""
    return (
        wants_booking(message)
        and not _QUALIFIER_RE.search(normalize(message))
        and len(message.split()) <= _PLAIN_MAX_WORDS
    )



def looks_like_injection(message: str) -> bool:
    return bool(_INJECTION_RE.search(normalize(message)))


_EMERGENCY_RE = re.compile(
    r"sung (to )?(lan|xuong)|lan xuong co|sot cao|kho (nuot|tho)|chay mau (khong|mai|nhieu)|cap cuu|"
    r"chan thuong ham|gay (ham|rang)|ngat|bat tinh"
)


def looks_like_emergency(message: str) -> bool:
    return bool(_EMERGENCY_RE.search(normalize(message)))


_REPLY_BOOKING_RE = re.compile(r"\bdat (lich|hen)\b|\bnut dat\b")


def reply_suggests_booking(reply: str) -> bool:
    """Câu trả lời của bot có khuyên/đề nghị đặt lịch hay không (mẫu hẹp hơn so với câu của người dùng:
    'bạn muốn khám ngày nào?' không phải là đề nghị đặt lịch)."""
    return bool(_REPLY_BOOKING_RE.search(normalize(reply)))
