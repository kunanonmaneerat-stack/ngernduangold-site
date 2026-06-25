"""batch_scheduler.py — Agent จัดแพ็ก 'ตั้งเวลาล่วงหน้า' (กันพลาดโอกาสเวลาไม่ว่าง)
อ่าน post-plan.json -> จัดคลิปเป็นแพ็กรายสัปดาห์ (7 คลิป/แพ็ก) พร้อมก๊อปวางลงตัวตั้งเวลาแพลตฟอร์ม
-> เขียน cowork-inbox/batch-schedule.md : ทำ 1 ครั้ง/สัปดาห์ (~15 นาที) แล้วแพลตฟอร์มโพสต์เองตามเวลา
ปลอดภัย: ร่าง/แพลนเท่านั้น ไม่โพสต์/ไม่ตั้งเวลาแทน (เจ้าของกดตั้งเวลาเอง)
ใช้: py pipeline/batch_scheduler.py [คลิปต่อแพ็ก=7]
"""
import os, sys, json, datetime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
AL = os.path.join(ROOT, "automation-log")
INBOX = os.path.join(AL, "cowork-inbox")
PLAN = os.path.join(AL, "post-plan.json")
FLOW_URL = "https://labs.google/fx/tools/flow"
DAYS_TH = {0: "อา", 1: "จ", 2: "อ", 3: "พ", 4: "พฤ", 5: "ศ", 6: "ส"}

HOWTO = [
    "## วิธีตั้งเวลาล่วงหน้า (ฟรี ไม่ต้องลงโปรแกรม — โพสต์เองแม้คุณไม่ว่าง)",
    "- **IG Reels + FB**: Meta Business Suite (business.facebook.com) -> Create Reel -> อัปคลิป -> Schedule ตั้งวัน/เวลาได้เป็นเดือน ทำทีเดียวหลายคลิป",
    "- **TikTok**: tiktok.com (เว็บ) -> Upload -> สลับ 'Schedule' ตั้งเวลาได้ล่วงหน้าสูงสุด 10 วัน",
    "- **YouTube Shorts**: YouTube Studio -> Upload -> Schedule ตั้งวัน/เวลาได้",
    "- เคล็ด: ทำเป็นรอบ (สัปดาห์ละครั้ง) อัป+ตั้งเวลา 7 คลิปรวด -> ทั้งสัปดาห์โพสต์เองอัตโนมัติ คุณไม่ต้องแตะรายวัน",
    "- ทางเลือกครบจบที่เดียว: ต่อ Postiz/Buffer (ตั้งเวลาข้ามแพลตฟอร์มจากแดชบอร์ดเดียว) — ดูปุ่มเชื่อมต่อด้านล่างแชต",
]


def _d(iso):
    try:
        dt = datetime.date.fromisoformat(iso)
        return "%s %02d/%02d" % (DAYS_TH[(dt.weekday() + 1) % 7], dt.day, dt.month)
    except Exception:
        return iso


def run(per=7):
    if not os.path.exists(PLAN):
        print("ยังไม่มี post-plan.json — รัน post_dispatcher.py ก่อน"); return
    plan = json.load(open(PLAN, encoding="utf-8")).get("plan", [])
    n = len(plan)
    nb = (n + per - 1) // per
    L = ["# 🗓️ แพ็กตั้งเวลาล่วงหน้า — กันพลาดโอกาสเวลาไม่ว่าง (batch_scheduler)",
         "> %d คลิป แบ่ง %d แพ็ก (สัปดาห์ละ ~%d คลิป) · ทำแพ็กละ 1 ครั้ง ~15 นาที แล้วแพลตฟอร์มยิงเอง" % (n, nb, per),
         "> ทุกคลิป CTA: คอมเมนต์ \"เช็กสิทธิ์\" · ก่อนอัปใส่ข้อความบนจอ(ไทย)+เสียงตามตาราง shot", ""] + HOWTO + [""]
    for b in range(nb):
        chunk = plan[b * per:(b + 1) * per]
        if not chunk:
            continue
        d0, d1 = _d(chunk[0]["day"]), _d(chunk[-1]["day"])
        L += ["## 📦 แพ็ก %d — ตั้งเวลาช่วง %s ถึง %s (อัป+ตั้งเวลาทีเดียว %d คลิป)" % (b + 1, d0, d1, len(chunk)),
              "ครั้งเดียว: โหลด %d คลิปจาก Flow (%s) แล้วตั้งเวลาตามนี้:" % (len(chunk), FLOW_URL), ""]
        for p in chunk:
            L += ["**%s · %s · %s**" % (_d(p["day"]), p.get("topic", ""), p.get("label", "")),
                  "- เวลา: TikTok %02d:00 · IG Reels %02d:00 · YT Shorts %02d:00" %
                  (p.get("tiktok", 19), p.get("ig", 20), p.get("yt", 18)),
                  "- แคปชัน (ก๊อปวางได้): %s" % p.get("caption", ""),
                  "- แฮชแท็ก: %s" % p.get("hashtags", ""),
                  "- ปิดท้าย: คอมเมนต์ \"เช็กสิทธิ์\"", ""]
    os.makedirs(INBOX, exist_ok=True)
    fp = os.path.join(INBOX, "batch-schedule.md")
    open(fp, "w", encoding="utf-8").write("\n".join(L))
    print("[batch_scheduler] %d คลิป -> %d แพ็ก -> %s" % (n, nb, fp))
    return fp


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    per = int(sys.argv[1]) if len(sys.argv) > 1 and sys.argv[1].isdigit() else 7
    run(per)
