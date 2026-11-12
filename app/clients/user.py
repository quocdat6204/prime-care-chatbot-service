import re
import unicodedata
from typing import Any

from app.clients.common import cached_fetch
from app.config import get_settings

RANK_TITLES = {
    "PROFESSOR": "Giáo sư",
    "DOCTORATE": "Tiến sĩ",
    "MASTER": "Thạc sĩ",
}


_TITLE_PREFIX_RE = re.compile(r"^(GS|PGS|TS|ThS|BS|CKI{1,2}|BSCK\w*)\b", re.IGNORECASE)


def normalize(text: str) -> str:
    """Bỏ dấu tiếng Việt, hạ chữ thường, gộp khoảng trắng - để so tên không phân biệt dấu."""
    text = text.replace("đ", "d").replace("Đ", "D")
    text = unicodedata.normalize("NFD", text)
    text = "".join(c for c in text if unicodedata.category(c) != "Mn")
    return re.sub(r"\s+", " ", text).strip().lower()


async def list_doctors() -> list[dict[str, Any]]:
    """Chỉ giữ id, tên, học hàm. KHÔNG lấy ava (có thể là base64 rất lớn), email, sđt."""
    s = get_settings()
    raw = await cached_fetch(
        "chat:cache:doctors", s.doctors_cache_seconds, f"{s.user_service_url}/users/doctors"
    )
    doctors = []
    for d in raw or []:
        name = d.get("fullName")
        # Tên trong DB thường đã có học hàm ("GS. TS. ...") -> không thêm lần nữa
        has_title = bool(name and _TITLE_PREFIX_RE.match(name.strip()))
        doctors.append(
            {
                "id": d.get("id"),
                "name": name,
                "title": None if has_title else RANK_TITLES.get(d.get("rank") or "", None),
            }
        )
    return doctors


_NAME_STOPWORDS = {"van", "thi", "ths", "pgs"}


async def match_doctor_in_text(text: str) -> int | None:
    """Tìm bác sĩ được nhắc trong câu (chỉ khi câu có 'bác sĩ/bs/dr').
    Chỉ trả id khi khớp ĐÚNG MỘT bác sĩ, nhập nhằng thì trả None để không chọn nhầm người."""
    n = normalize(text)
    if not re.search(r"\b(bac si|bs|dr)\b", n):
        return None
    words = set(re.findall(r"[a-z0-9]+", n))
    hits = []
    for d in await list_doctors():
        tokens = [t for t in normalize(d["name"] or "").split(" ") if len(t) >= 3 and t not in _NAME_STOPWORDS]
        if any(t in words for t in tokens):
            hits.append(d["id"])
    return hits[0] if len(hits) == 1 else None


async def find_doctors(name: str | None = None) -> list[dict[str, Any]]:
    doctors = await list_doctors()
    if not name or not name.strip():
        return doctors
    q = normalize(name)
    tokens = q.split(" ")
    return [d for d in doctors if d["name"] and all(t in normalize(d["name"]) for t in tokens)]
