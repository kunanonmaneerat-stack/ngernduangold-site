"""daily_content.py — รันรายวัน: เลือกหัวข้อถัดไปจาก orders.txt (หมุนตามวัน) แล้วยิง head_content 1 แพ็กเกจ
ทำให้เครื่องยนต์ผลิตคอนเทนต์ 6 ช่องเองทุกวัน → เข้า cowork-inbox (draft รอ owner/Cowork รีวิว+โพสต์)
ปลอดภัย: ผลิต draft เท่านั้น ไม่โพสต์/ไม่ commit/ไม่ deploy
"""
import sys, os, datetime
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try: sys.stdout.reconfigure(encoding="utf-8")
except Exception: pass
import head_content

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ORDERS = os.path.join(ROOT, "automation-log", "orders.txt")


def topics():
    out = []
    if os.path.exists(ORDERS):
        for ln in open(ORDERS, encoding="utf-8"):
            s = ln.strip()
            if s and not s.startswith("#"):
                out.append(s)
    return out


if __name__ == "__main__":
    ts = topics()
    if not ts:
        print("[daily_content] ไม่มีหัวข้อใน orders.txt"); sys.exit(0)
    idx = datetime.date.today().toordinal() % len(ts)  # หมุนหัวข้อตามวัน → ไม่ซ้ำติดกัน
    topic = ts[idx]
    print(f"[daily_content] วันนี้หัวข้อ #{idx + 1}/{len(ts)}: {topic[:50]}")
    head_content.run(topic)
