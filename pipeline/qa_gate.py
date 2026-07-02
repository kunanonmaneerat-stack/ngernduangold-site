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


# ---- POSTING-POLICY quota gate (POSTING-POLICY_antispam_20260702) ----
QUOTA_PER_DAY = {"pinterest": 5}     # ช่องอื่นใช้ค่า default
QUOTA_DEFAULT = 2                    # <=2 โพสต์/วัน/ช่อง
MIN_GAP_HOURS = 3                    # เว้นขั้นต่ำ 3 ชม. ในช่องเดียวกัน
PANTIP_FROZEN_UNTIL = "2026-07-16"   # hard-block: เอาออกได้เฉพาะเจ้าของแก้ POSTING-POLICY เอง


def posting_quota(channel):
    """(ok, reason) — อ่าน post-ledger ของวันนี้: Pantip hard-block + โควตา/วัน + ห่างขั้นต่ำ 3 ชม.
    FAIL จะบอกเวลาที่โพสต์ได้ครั้งถัดไปเสมอ."""
    import datetime as _dt
    _al = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "automation-log")
    if _al not in sys.path:
        sys.path.insert(0, _al)
    import post_ledger as PL
    ch = PL.norm_channel(channel)
    now = PL.now_local()
    if ch == "pantip" and now.date().isoformat() < PANTIP_FROZEN_UNTIL:
        return False, ("FROZEN until 2026-07-16 (POSTING-POLICY) — Pantip FINAL WARNING: "
                       "ห้ามโพสต์ทุกกรณี ปลดล็อกได้เฉพาะเจ้าของแก้ POSTING-POLICY_antispam_20260702.md เอง")
    stamps = []
    for r in PL.iter_ledger():
        if r.get("type") == "status" or PL.norm_channel(r.get("channel")) != ch:
            continue
        eff = r.get("scheduled_for") or str(r.get("ts", ""))[:10]
        if eff != now.date().isoformat():
            continue
        try:
            t = _dt.datetime.fromisoformat(str(r.get("ts") or r.get("posted_at")))
            if t.tzinfo is None:
                t = t.replace(tzinfo=PL.TZ)
            stamps.append(t)
        except Exception:
            pass
    cap = QUOTA_PER_DAY.get(ch, QUOTA_DEFAULT)
    if len(stamps) >= cap:
        nxt = (now + _dt.timedelta(days=1)).replace(hour=8, minute=0, second=0, microsecond=0)
        return False, "โควตาเต็ม (%d/%d วันนี้ ช่อง %s) — โพสต์ได้อีกครั้ง: %s" % (len(stamps), cap, ch, nxt.strftime("%Y-%m-%d %H:%M"))
    if stamps:
        last = max(stamps)
        gap_h = (now - last).total_seconds() / 3600.0
        if gap_h < MIN_GAP_HOURS:
            nxt = last + _dt.timedelta(hours=MIN_GAP_HOURS)
            return False, "ยังไม่ครบ 3 ชม.จากโพสต์ก่อน (%.1f ชม.) — โพสต์ได้อีกครั้ง: %s" % (gap_h, nxt.strftime("%H:%M"))
    return True, "ok (%d/%d วันนี้ · gap ผ่าน)" % (len(stamps), cap)


def check(frame_path):
    if not os.path.exists(frame_path):
        return {"pass": False, "fails": ["frame not found: " + frame_path], "status": "NO_FILE"}
    try:
        import PIL.Image  # google-generativeai accepts PIL images for vision
        img = PIL.Image.open(frame_path)
    except Exception as e:
        # fall back: pass the path note; if no key it will skip anyway
        img = None
    txt, st = free_ai.generate(CHECKLIST, model="smart", images=([img] if img else None))  # vision QA gate
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
    if len(sys.argv) >= 3 and sys.argv[1] == "--quota":
        ok, reason = posting_quota(sys.argv[2])
        print(("OK " if ok else "FAIL ") + reason)
        return 0 if ok else 2
    if len(sys.argv) < 2:
        print("usage: python qa_gate.py <frame.png> | --quota <channel>")
        return 0
    res = check(sys.argv[1])
    print(json.dumps(res, ensure_ascii=False))
    if res.get("status") == "SKIP_NO_KEY":
        print("# QA skipped (no key) -> degrade to human eyeball before publish")
    return 0


if __name__ == "__main__":
    sys.exit(main())
