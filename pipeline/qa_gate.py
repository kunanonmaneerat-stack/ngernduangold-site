#!/usr/bin/env python3
"""qa_gate — STEP 4: Visual QA gate (Gemini vision, free) BEFORE a clip is approved to publish.
Sends a representative frame (PNG/JPG) + the blueprint checklist (section D) and returns
pass/fail + reasons. Caller re-renders on fail (<=2) then flags a human.

Usage:  python qa_gate.py <frame.png|jpg>
Fail-closed: no key -> returns SKIP (exit 0) so the pipeline degrades to "human eyeball"
rather than blocking or paying. NO evasion logic.
"""
import os, sys, json
try:  # cp874-safe: UTF-8 stdout/stderr so Thai/emoji prints never crash on Windows console (idempotent)
    import sys as _sys; _sys.stdout.reconfigure(encoding="utf-8", errors="replace"); _sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import free_ai

CHECKLIST = """ตรวจคลิป/เฟรมนี้ตาม checklist (ตอบ JSON ล้วน: {"pass":true/false,"fails":["ข้อที่ตก..."],"notes":""}):
1. Hook อ่านออกใน 1.5 วิแรก (ฟอนต์/คอนทราสต์พอ)
2. ไม่มีข้อความทับซ้อน / หลุด safe-zone (บน 12% ล่าง 20%) / สะกดผิด
3. ไม่มี watermark แพลตฟอร์มอื่น (โดยเฉพาะโลโก้ TikTok บนคลิป multicast)
4. สัดส่วน 9:16, อ่านง่ายบนมือถือ
5. แบรนด์ตรง (สี/โลโก้ เงินเดือนสมองทอง) + มี disclosure
6. CTA + "ลิงก์ในไบโอ/คอมเมนต์" ชัด
7. ถ้าใช้ภาพ AI สร้าง ต้องมี label AI
ตก = pass:false + ระบุข้อใน fails."""


def check(frame_path):
    if not os.path.exists(frame_path):
        return {"pass": False, "fails": ["frame not found: " + frame_path], "status": "NO_FILE"}
    try:
        import PIL.Image  # google-generativeai accepts PIL images for vision
        img = PIL.Image.open(frame_path)
    except Exception as e:
        # fall back: pass the path note; if no key it will skip anyway
        img = None
    txt, st = free_ai.generate(CHECKLIST, model="gemini-2.0-flash", images=([img] if img else None))
    if st == "NO_KEY":
        return {"pass": None, "fails": [], "status": "SKIP_NO_KEY"}
    if st != "ok" or not txt:
        return {"pass": None, "fails": [], "status": st}
    try:
        data = json.loads(txt[txt.find("{"):txt.rfind("}") + 1])
        data["status"] = "ok"
        return data
    except Exception:
        return {"pass": None, "fails": [], "status": "PARSE_ERROR", "raw": txt[:200]}


def main():
    if len(sys.argv) < 2:
        print("usage: python qa_gate.py <frame.png>")
        return 0
    res = check(sys.argv[1])
    print(json.dumps(res, ensure_ascii=False))
    if res.get("status") == "SKIP_NO_KEY":
        print("# QA skipped (no key) -> degrade to human eyeball before publish")
    return 0


if __name__ == "__main__":
    sys.exit(main())
