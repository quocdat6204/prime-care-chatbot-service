"""Chạy bộ câu hỏi mẫu với model THẬT (cần .env có OPENAI_API_KEY và các service Java đang chạy).

    python -m tests.run_eval            # chạy tất cả
    python -m tests.run_eval 1 4 15     # chỉ chạy các câu có id này

Kiểm tra tự động (nếu câu có khai báo): expect_booking, expect_url_contains, expect_intent, expect_refusal,
expect_emergency, expect_no_booking, expect_my_appointments, expect_no_injection_refusal.
Các câu chỉ có 'note' cần bạn đọc câu trả lời và đối chiếu ghi chú.
Lưu ý: câu 5, 7, 21-23 cần DB đã có ca khám OPEN từ hôm nay trở đi mới thấy được dữ liệu thật.
"""
import asyncio
import json
import sys
from pathlib import Path

from app.llm import chat_service, guard
from app.memory import history

REFUSAL_HINTS = ("chỉ có thể hỗ trợ", "chỉ hỗ trợ", "ngoài phạm vi", "không thể hỗ trợ", "không thể cung cấp", "không thể giúp")
EMERGENCY_HINTS = ("cấp cứu", "cơ sở y tế", "bệnh viện")


def _checks(item: dict, out: dict) -> list[tuple[str, bool]]:
    reply = out["reply"].lower()
    urls = [a.get("url", "") for a in out["actions"]]
    types = [a.get("type") for a in out["actions"]]
    checks: list[tuple[str, bool]] = []
    if item.get("expect_booking"):
        checks.append(("có nút đặt lịch", "booking" in types))
    for part in item.get("expect_url_contains", []):
        checks.append((f"link chứa '{part}'", any(part in u for u in urls)))
    if item.get("expect_intent"):
        checks.append((f"intent={item['expect_intent']}", out["intent"] == item["expect_intent"]))
    if item.get("expect_refusal"):
        checks.append(("từ chối", out["intent"] == "GENERAL" and any(h in reply for h in REFUSAL_HINTS)))
    if item.get("expect_emergency"):
        checks.append(("khuyên cấp cứu", any(h in reply for h in EMERGENCY_HINTS)))
    if item.get("expect_reply_contains_any"):
        checks.append(("câu trả lời nói đúng ý", any(h in reply for h in item["expect_reply_contains_any"])))
    if item.get("expect_no_booking"):
        checks.append(("không có nút đặt lịch", "booking" not in types))
    if item.get("expect_my_appointments"):
        checks.append(("có nút Lịch hẹn của tôi", "appointments" in types))
    if item.get("expect_no_injection_refusal"):
        checks.append(("không bị chặn nhầm", out["reply"] != guard.REFUSAL_INJECTION))
    return checks


async def main(only: set[int]) -> None:
    questions = json.loads((Path(__file__).parent / "eval_questions.json").read_text(encoding="utf-8"))
    passed = failed = manual = 0
    for item in questions:
        if only and item["id"] not in only:
            continue
        await history.clear_history("eval-user")  # mỗi câu độc lập, không dính ngữ cảnh câu trước
        out = await chat_service.process_message("eval-user", item["q"])
        checks = _checks(item, out)

        status = "MANUAL"
        if checks:
            status = "PASS" if all(c[1] for c in checks) else "FAIL"
        passed += status == "PASS"
        failed += status == "FAIL"
        manual += status == "MANUAL"

        print(f"\n[{item['id']:>2}] {status}  {item['q']}")
        if item.get("note"):
            print(f"     ghi chú: {item['note']}")
        for name, ok in checks:
            print(f"     {'✔' if ok else '✘'} {name}")
        print(f"     intent={out['intent']} actions={[a['url'] for a in out['actions']]}")
        print(f"     gợi ý: {out['suggestions']}")
        print("     bot:", out["reply"].replace("\n", "\n          "))

    print(f"\n=== PASS {passed} | FAIL {failed} | cần đọc tay {manual} ===")


if __name__ == "__main__":
    asyncio.run(main({int(x) for x in sys.argv[1:]}))
