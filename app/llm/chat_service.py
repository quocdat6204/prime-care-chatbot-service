"""Vòng xử lý một tin nhắn: guard -> OpenAI tool calling (tối đa N vòng) -> hậu xử lý -> lưu lịch sử."""
import asyncio
import hashlib
import json
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse
from zoneinfo import ZoneInfo

from openai import APIError, APITimeoutError, AuthenticationError, RateLimitError

from app.clients import user as user_client
from app.config import get_settings
from app.llm import guard
from app.llm.client import get_openai
from app.llm.tools import (
    HINT_TYPE,
    TOOL_DEFINITIONS,
    TOOL_INTENTS,
    appointments_action,
    booking_action,
    build_booking_url,
    execute_tool,
)
from app.memory import history

log = logging.getLogger(__name__)

_PROMPT_TEMPLATE = (Path(__file__).resolve().parent / "prompts" / "system.txt").read_text(encoding="utf-8")
_WEEKDAYS = ["Thứ Hai", "Thứ Ba", "Thứ Tư", "Thứ Năm", "Thứ Sáu", "Thứ Bảy", "Chủ Nhật"]

DEFAULT_SUGGESTIONS = ["Bác sĩ nào đang có lịch khám?", "Bảng giá dịch vụ nha khoa", "Hướng dẫn đặt lịch khám"]
SUGGESTIONS_BY_INTENT = {
    "CHECK_SCHEDULE": ["Đặt lịch khám ngay", "Xem lịch ngày mai", "Bảng giá dịch vụ"],
    "DOCTOR_INFO": ["Bác sĩ nào đang có lịch?", "Đặt lịch khám ngay", "Bảng giá dịch vụ"],
    "CHECK_SERVICE": ["Đặt lịch khám ngay", "Bác sĩ nào đang có lịch?", "Dịch vụ khác"],
    "BOOKING": ["Bác sĩ nào đang có lịch?", "Bảng giá dịch vụ", "Địa chỉ phòng khám"],
    "MY_APPOINTMENTS": ["Đặt lịch hẹn mới", "Bác sĩ nào đang có lịch?", "Bảng giá dịch vụ"],
    "CLINIC_INFO": ["Đặt lịch khám ngay", "Bảng giá dịch vụ", "Bác sĩ nào đang có lịch?"],
}

EMERGENCY_SUGGESTIONS = ["Hotline và địa chỉ phòng khám"]

MSG_NO_KEY ="Dạ hiện trợ lý AI chưa được cấu hình. Bạn vui lòng liên hệ hotline +84 123456789 để được hỗ trợ nhé!"
MSG_BUSY = "Dạ xin lỗi, trợ lý AI đang bận. Bạn vui lòng thử lại sau ít phút hoặc gọi hotline +84 123456789 nhé!"
MSG_EMPTY = "Dạ, bạn cần hỗ trợ thông tin gì về phòng khám hoặc nha khoa ạ?"
EMERGENCY_NOTICE = (
    "⚠️ Dấu hiệu bạn mô tả có thể nghiêm trọng. Vui lòng đến cơ sở y tế/cấp cứu gần nhất ngay, "
    "không nên chờ đặt lịch.\n\n"
)

_REASONING_MODEL_PREFIXES = ("o1", "o3", "o4", "gpt-5")


def build_system_prompt(now: datetime | None = None) -> str:
    tz = ZoneInfo(get_settings().timezone)
    now = now or datetime.now(tz)
    return _PROMPT_TEMPLATE.format(
        weekday=_WEEKDAYS[now.weekday()],
        today=now.strftime("%Y-%m-%d"),
        calendar=_calendar(now),
    )


def _calendar(now: datetime, days: int = 14) -> str:
    """Bảng ngày-thứ cho 14 ngày tới. Model tính thứ trong tuần không ổn định (từng đổi 'cuối tuần' ra thứ Sáu),
    nên đưa sẵn bảng để nó tra thay vì tự tính."""
    labels = {0: " (hôm nay)", 1: " (ngày mai)"}
    parts = []
    for i in range(days):
        d = now + timedelta(days=i)
        parts.append(f"{_WEEKDAYS[d.weekday()]} {d.strftime('%Y-%m-%d')}{labels.get(i, '')}")
    return "; ".join(parts)


def _now_hhmm() -> str:
    return datetime.now(ZoneInfo(get_settings().timezone)).strftime("%H:%M")


def _anon_user_tag(user_id: str) -> str:
    """Định danh ẩn danh gửi cho OpenAI (không gửi uuid/email thật)."""
    return hashlib.sha256(user_id.encode()).hexdigest()[:32]


def _sampling_kwargs() -> dict[str, Any]:
    """Tham số sinh văn bản theo loại model (model suy luận không nhận temperature)."""
    s = get_settings()
    if s.openai_chat_model.lower().startswith(_REASONING_MODEL_PREFIXES):
        return {"max_completion_tokens": max(s.openai_max_output_tokens, s.openai_reasoning_max_tokens)}
    return {"temperature": s.openai_temperature, "max_completion_tokens": s.openai_max_output_tokens}


def _parse_tool_args(raw: str | None) -> dict[str, Any]:
    try:
        args = json.loads(raw or "{}")
    except ValueError:
        return {}
    return args if isinstance(args, dict) else {}


async def _run_model(user_id: str, user_message: str) -> tuple[str, list[str], list[dict[str, Any]]]:
    """Trả (reply, tools_used, actions)."""
    s = get_settings()
    client = get_openai()
    if client is None:
        return MSG_NO_KEY, [], []

    messages: list[dict[str, Any]] = [{"role": "system", "content": build_system_prompt()}]
    messages += await history.get_context_messages(user_id)
    messages.append({"role": "user", "content": user_message})

    tools_used: list[str] = []
    actions: list[dict[str, Any]] = []

    # Ý định rõ ràng thì tạo nút ngay bằng code, không để model quyết định có hỏi lại hay không:
    #  - chỉ nói "muốn đặt lịch" (chưa nêu bác sĩ/ngày) -> nút đặt lịch
    #  - hỏi/hủy/đổi lịch đã đặt                        -> nút "Lịch hẹn của tôi"
    forced_tool = None
    if s.intent_mode == "rules":  # chế độ "model": để model tự hiểu ý và tự gọi công cụ
        if guard.is_plain_booking_request(user_message):
            forced_tool = "get_booking_link"
        elif guard.wants_my_appointments(user_message):
            forced_tool = "get_appointments_link"
    if forced_tool:
        result, acts = await execute_tool(forced_tool, {})
        tools_used.append(forced_tool)
        actions.extend(acts)
        messages.append(
            {
                "role": "assistant",
                "content": None,
                "tool_calls": [{"id": "auto_tool", "type": "function",
                                "function": {"name": forced_tool, "arguments": "{}"}}],
            }
        )
        messages.append({"role": "tool", "tool_call_id": "auto_tool", "content": json.dumps(result, ensure_ascii=False)})

    async def _call(c):
        return c, await execute_tool(c.function.name, _parse_tool_args(c.function.arguments))

    for round_no in range(s.max_tool_rounds + 1):
        final_round = round_no == s.max_tool_rounds  # hết lượt gọi tool -> ép model trả lời
        resp = await client.chat.completions.create(
            model=s.openai_chat_model,
            messages=messages,
            tools=TOOL_DEFINITIONS,
            tool_choice="none" if final_round else "auto",
            user=_anon_user_tag(user_id),
            **_sampling_kwargs(),
        )
        msg = resp.choices[0].message
        if resp.usage:
            log.info(
                "openai model=%s round=%d prompt_tokens=%d completion_tokens=%d",
                s.openai_chat_model, round_no, resp.usage.prompt_tokens, resp.usage.completion_tokens,
            )

        if not msg.tool_calls:
            return (msg.content or "").strip() or MSG_BUSY, tools_used, actions

        messages.append(
            {
                "role": "assistant",
                "content": msg.content,
                "tool_calls": [
                    {"id": c.id, "type": "function", "function": {"name": c.function.name, "arguments": c.function.arguments}}
                    for c in msg.tool_calls
                ],
            }
        )
        for c, (result, acts) in await asyncio.gather(*[_call(c) for c in msg.tool_calls]):
            if "error" not in result:  # công cụ lỗi (vd không tìm thấy bác sĩ) không tính là đã tra cứu
                tools_used.append(c.function.name)
            actions.extend(acts)
            messages.append({"role": "tool", "tool_call_id": c.id, "content": json.dumps(result, ensure_ascii=False)})

    return MSG_BUSY, tools_used, actions  # không tới được, phòng hờ


def _dedupe_actions(actions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen, out = set(), []
    for a in actions:
        key = (a.get("type"), a.get("url"))
        if key not in seen:
            seen.add(key)
            out.append(a)
    return out


async def _attach_doctor_to_booking(message: str, actions: list[dict[str, Any]]) -> None:
    """Người dùng nêu đích danh một bác sĩ (khớp đúng 1 người) -> nút đặt lịch phải kèm ĐÚNG bác sĩ đó.
    Bổ sung nếu chưa có doctorId, và sửa nếu model lỡ đưa mã bác sĩ khác."""
    booking = [a for a in actions if a.get("type") == "booking"]
    if not booking:
        return
    try:
        doctor_id = await user_client.match_doctor_in_text(message)
    except Exception:  # noqa: BLE001 - không tra được thì giữ nút như cũ
        return
    if not doctor_id:
        return
    for a in booking:
        query = parse_qs(urlparse(a["url"]).query)
        date = (query.get("date") or [None])[0]
        a["url"] = build_booking_url(date, doctor_id)


def _ensure_buttons(message: str, reply: str, tools_used: list[str], actions: list[dict[str, Any]],
                    hint: dict[str, Any] | None, rules: bool = False) -> None:
    """Bổ sung/gỡ nút. Chế độ rules: đảm bảo có nút theo từ khoá của người dùng. Chế độ model: chỉ dựa vào
    quyết định của model (công cụ nó gọi), code chỉ giữ quyền phủ quyết khi người dùng phủ định."""
    has = lambda t: any(a.get("type") == t for a in actions)  # noqa: E731
    if guard.refuses_booking(message):
        # Người dùng nói rõ KHÔNG muốn đặt lịch -> không đẩy nút, kể cả khi model lỡ tạo
        actions[:] = [a for a in actions if a.get("type") != "booking"]
        while "get_booking_link" in tools_used:
            tools_used.remove("get_booking_link")
        return
    if rules and guard.wants_my_appointments(message):
        if not has("appointments"):
            actions.append(appointments_action())
        return
    if has("booking"):
        return
    user_wants = rules and guard.wants_booking(message)
    # Bot khuyên đặt lịch, hoặc vừa tra lịch -> kèm nút luôn (trừ tình huống cấp cứu)
    bot_suggests = not guard.looks_like_emergency(message) and (
        guard.reply_suggests_booking(reply) or "get_schedule" in tools_used
    )
    if user_wants or bot_suggests:
        actions.append(booking_action(build_booking_url(hint["date"], hint["doctor_id"])) if hint else booking_action())
        if user_wants:  # chỉ khi người dùng chủ động xin đặt lịch mới coi là intent BOOKING
            tools_used.append("get_booking_link")


def _resolve_intent(tools_used: list[str], actions: list[dict[str, Any]]) -> str:
    if any(a.get("type") == "appointments" for a in actions):
        return "MY_APPOINTMENTS"
    if "get_booking_link" in tools_used:
        return "BOOKING"
    if "get_schedule" in tools_used:
        return "CHECK_SCHEDULE"
    intent = "GENERAL"
    for t in tools_used:
        intent = TOOL_INTENTS.get(t, intent)
    return intent


def _drop_booking_suggestions(suggestions: list[str]) -> list[str]:
    return [x for x in suggestions if "đặt lịch" not in x.lower()]


def _suggestions_for(intent: str, actions: list[dict[str, Any]], emergency: bool = False,
                     refused_booking: bool = False) -> list[str]:
    if emergency:
        return EMERGENCY_SUGGESTIONS  # không gợi ý đặt lịch/giá khi người dùng đang gặp tình huống nguy hiểm
    suggestions = SUGGESTIONS_BY_INTENT.get(intent, DEFAULT_SUGGESTIONS)
    if refused_booking or any(a.get("type") == "booking" for a in actions):
        # Đã có nút đặt lịch thật, hoặc người dùng nói chưa muốn đặt -> không gợi ý câu "đặt lịch"
        suggestions = _drop_booking_suggestions(suggestions)
    return suggestions


async def process_message(user_id: str, raw_message: str) -> dict[str, Any]:
    message = (raw_message or "").strip()
    if not message:
        return {"reply": MSG_EMPTY, "intent": "GENERAL", "suggestions": DEFAULT_SUGGESTIONS, "actions": []}

    await history.save_message(user_id, {"sender": "user", "text": message, "time": _now_hhmm()})

    injection = guard.looks_like_injection(message)
    if injection:
        reply, tools_used, actions = guard.REFUSAL_INJECTION, [], []
    else:
        try:
            reply, tools_used, actions = await _run_model(user_id, message)
        except AuthenticationError as e:
            log.error("OPENAI_API_KEY không hợp lệ (key OpenAI phải bắt đầu bằng 'sk-'): %s", e)
            reply, tools_used, actions = MSG_NO_KEY, [], []
        except (APITimeoutError, RateLimitError, APIError) as e:
            log.error("Lỗi OpenAI: %s", e)
            reply, tools_used, actions = MSG_BUSY, [], []

    # Gợi ý nội bộ từ get_schedule (ngày/bác sĩ vừa tra) - không trả ra ngoài
    hint = next((a for a in actions if a.get("type") == HINT_TYPE), None)
    actions = [a for a in actions if a.get("type") != HINT_TYPE]

    if not injection:
        if guard.looks_like_emergency(message) and reply not in (MSG_NO_KEY, MSG_BUSY) and not any(
            k in reply.lower() for k in ("cấp cứu", "cơ sở y tế", "bệnh viện")
        ):
            reply = EMERGENCY_NOTICE + reply  # bảo đảm lời khuyên cấp cứu có mặt dù model quên
        _ensure_buttons(message, reply, tools_used, actions, hint, rules=get_settings().intent_mode == "rules")
        await _attach_doctor_to_booking(message, actions)

    actions = _dedupe_actions(actions)
    intent = _resolve_intent(tools_used, actions)
    suggestions = _suggestions_for(
        intent, actions,
        emergency=not injection and guard.looks_like_emergency(message),
        refused_booking=guard.refuses_booking(message),
    )

    await history.save_message(
        user_id,
        {"sender": "bot", "text": reply, "time": _now_hhmm(), "suggestions": suggestions, "actions": actions},
    )
    return {"reply": reply, "intent": intent, "suggestions": suggestions, "actions": actions}
