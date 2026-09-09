"""daily_post_reminder.py — local-only posting-card renderer.
อ่าน post-plan.json -> เขียนการ์ดใน cowork-inbox เท่านั้น:
 - ทุกวัน: คลิป 'ของวันนี้/คิวถัดไป' (โหลดคลิปไหน + TikTok/IG/YT เวลา + แคปชัน + แฮชแท็ก + CTA + ลิงก์ Flow)
 - วันอาทิตย์ (BATCH DAY): การ์ด 'ตั้งเวลา 7 คลิปสัปดาห์หน้ารวดเดียว' ผ่านตัวตั้งเวลาฟรี (Meta Business Suite/TikTok/YouTube)
ไม่มี transport, notification, browser, scheduler หรือ publication mutationใด ๆ
ใช้: py pipeline/daily_post_reminder.py
"""
import os, sys, json, datetime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
AL = os.path.join(ROOT, "automation-log")
INBOX = os.path.join(AL, "cowork-inbox")
PLAN = os.path.join(AL, "post-plan.json")
FLOW_URL = "https://labs.google/fx/tools/flow"
BATCH_WEEKDAY = 6   # 6=อาทิตย์ (Mon=0..Sun=6) — วันตั้งเวลาทั้งสัปดาห์
DAYS_TH = {0: "อา", 1: "จ", 2: "อ", 3: "พ", 4: "พฤ", 5: "ศ", 6: "ส"}


def _plan():
    if not os.path.exists(PLAN):
        return []
    try:
        with open(PLAN, encoding="utf-8") as handle:
            return json.load(handle).get("plan", [])
    except Exception:
        return []


def _d(iso):
    try:
        dt = datetime.date.fromisoformat(iso)
        return "%s %02d/%02d" % (DAYS_TH[(dt.weekday() + 1) % 7], dt.day, dt.month)
    except Exception:
        return iso


def _pick(plan):
    today = datetime.date.today().isoformat()
    same = [p for p in plan if p.get("day") == today]
    if same:
        return same, "วันนี้"
    future = sorted([p for p in plan if p.get("day", "") >= today], key=lambda p: p["day"])
    if future:
        return [future[0]], "คิวถัดไป (" + _d(future[0]["day"]) + ")"
    return ([plan[0]], "เริ่มคิว") if plan else ([], "-")


def _daily_card(plan):
    picks, when = _pick(plan)
    if not picks:
        return "ยังไม่มีคลิปในตาราง — รัน post_dispatcher.py"
    p = picks[0]
    f = p.get("file") or ""
    dl = ("ไฟล์พร้อมในเครื่อง: %s" % f) if f else ("⬇️ โหลดคลิปจาก Flow ก่อน: %s" % FLOW_URL)
    return "\n".join([
        "📣 โพสต์ %s — ngernduangold" % when, "",
        "🎬 %s · %s" % (p.get("topic", ""), p.get("label", "")),
        dl,
        "📱 TikTok %02d:00   📸 IG Reels %02d:00   ▶️ YT Shorts %02d:00" %
        (p.get("tiktok", 19), p.get("ig", 20), p.get("yt", 18)),
        "📝 แคปชัน: " + p.get("caption", ""),
        "#️⃣ " + p.get("hashtags", ""),
        "💬 ปิดท้าย CTA: คอมเมนต์ \"เช็กสิทธิ์\"",
        "(ใส่ข้อความบนจอไทย+เสียงตามตาราง shot ก่อนโพสต์ · กดโพสต์เอง)"])


def _batch_card(plan):
    today = datetime.date.today().isoformat()
    nxt = sorted([p for p in plan if p.get("day", "") >= today], key=lambda p: p["day"])[:7]
    if not nxt:
        return None
    L = ["📦 BATCH DAY (อาทิตย์) — ตั้งเวลาทั้งสัปดาห์รวดเดียว ~15 นาที กันพลาดเวลาไม่ว่าง",
         "ตัวตั้งเวลาฟรี: Meta Business Suite (IG+FB) · TikTok (เว็บ, ≤10วัน) · YouTube Studio",
         "เปิด batch-schedule.md แล้วโหลด+ตั้งเวลา 7 คลิปนี้:"]
    for p in nxt:
        L.append("• %s · %s %s — TikTok %02d:00/IG %02d:00/YT %02d:00" %
                 (_d(p["day"]), p.get("topic", ""), p.get("label", ""),
                  p.get("tiktok", 19), p.get("ig", 20), p.get("yt", 18)))
    L.append("ตั้งเวลาเสร็จ = ทั้งสัปดาห์โพสต์เองอัตโนมัติ ✅")
    return "\n".join(L)


def run():
    plan = _plan()
    os.makedirs(INBOX, exist_ok=True)
    daily = _daily_card(plan)
    msgs = [daily]
    if datetime.date.today().weekday() == BATCH_WEEKDAY:
        b = _batch_card(plan)
        if b:
            msgs.insert(0, b)   # วันอาทิตย์: ส่งการ์ด batch นำหน้า
    today = datetime.date.today().isoformat()
    card_path = os.path.join(INBOX, "today-post-" + today + ".md")
    with open(card_path, "w", encoding="utf-8") as handle:
        handle.write("\n\n---\n\n".join(msgs))
    print("[daily_post_reminder] เขียน %d การ์ด%sแบบ local-only:" % (len(msgs), " (รวม BATCH DAY) " if len(msgs) > 1 else ""))
    print("\n\n".join(msgs))
    print("[daily_post_reminder] external notification: DISABLED")
    return msgs


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    run()
