"""content_review.py — เอเจนต์รีวิวคอนเทนต์: สแกนแพ็กเกจล่าสุด → ธง "ต้อง verify ก่อนโพสต์"

comply_gate จับคำต้องห้าม แต่ไม่จับความถูกต้องข้อเท็จจริง (LLM เคยแต่งชื่อแบงก์/ตัวเลขผิด)
เอเจนต์นี้สแกนหา "จุดเสี่ยงข้อเท็จจริง" แล้วเขียน checklist สั้น ๆ ให้คนตรวจเร็ว ๆ ก่อนโพสต์
ปลอดภัย: อ่าน+เขียนไฟล์ checklist เท่านั้น ไม่แก้คอนเทนต์/ไม่โพสต์

ใช้:  py pipeline/content_review.py            # รีวิวแพ็กเกจล่าสุด
      py pipeline/content_review.py <path.md>  # รีวิวไฟล์ที่ระบุ
"""
import sys, os, re, glob, datetime
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PKG_DIR = os.path.join(ROOT, "automation-log", "content-packages")
INBOX = os.path.join(ROOT, "automation-log", "cowork-inbox")

# ชื่อแบรนด์/ผู้ให้บริการที่ "ถ้าโผล่ ต้องเช็กว่าถูกและยังให้บริการ" (LLM ชอบจับคู่ผิด/อ้างของเลิกแล้ว)
BRANDS = ["KTC", "กสิกร", "kbank", "SCB", "ไทยพาณิชย์", "กรุงศรี", "krungsri", "กรุงไทย", "krungthai",
          "ttb", "ทีเอ็มบี", "ทีทีบี", "UOB", "ยูโอบี", "ซิตี้", "citi", "กรุงเทพ", "bbl", "ออมสิน",
          "เกียรตินาคิน", "kkp", "ทิสโก้", "tisco", "อิออน", "aeon", "อิ ออน", "first choice",
          "ktc proud", "happycash", "umay", "ยูเมะ", "ศรีสวัสดิ์", "เงินติดล้อ", "ngern tid lor"]


def review_text(txt):
    flags = []
    # 1) แบรนด์/ผู้ให้บริการที่อ้างเฉพาะเจาะจง
    low = txt.lower()
    found = sorted({b for b in BRANDS if b.lower() in low})
    if found:
        flags.append(("ชื่อแบรนด์/ผู้ให้บริการเฉพาะ", "เช็กว่าสะกด/จับคู่ถูก + ยังให้บริการจริง (LLM เคยอ้างผิด เช่น KTC≠กสิกร, แบรนด์ที่เลิกแล้ว): " + ", ".join(found)))
    # 2) ตัวเลขเปอร์เซ็นต์ดอกเบี้ย/เกณฑ์ — ต้องเป็นช่วง + อ้างอิงทางการ
    pcts = re.findall(r"\d+(?:\.\d+)?\s*[-–]?\s*\d*\s*%", txt)
    if pcts:
        flags.append(("ตัวเลข %", "ยืนยันเป็นช่วงกว้าง + กำกับ 'เช็กกับผู้ให้บริการ': " + ", ".join(sorted(set(pcts))[:8])))
    # 3) ตัวเลขเงินบาทเฉพาะเจาะจง (วงเงิน/ค่าธรรมเนียม)
    bahts = re.findall(r"\d[\d,]{2,}\s*บาท", txt)
    if bahts:
        flags.append(("ตัวเลขเงินบาท", "เป็นตัวอย่าง/ช่วง ไม่ใช่คำมั่น: " + ", ".join(sorted(set(bahts))[:8])))
    # 4) คำมั่น/การันตีที่หลุด comply (เผื่อ)
    risky = [w for w in ["การันตี", "รับรอง", "อนุมัติแน่", "ผ่านชัวร์", "100%", "ดีที่สุด"] if w in txt]
    if risky:
        flags.append(("คำเสี่ยงโอ้อวด/การันตี", "ตัดออก/ทำให้นุ่มลง: " + ", ".join(risky)))
    return flags


def run(path=None):
    if not path:
        files = sorted(glob.glob(os.path.join(PKG_DIR, "*.md")), key=os.path.getmtime, reverse=True)
        if not files:
            print("[content_review] ไม่มีแพ็กเกจ"); return None
        path = files[0]
    txt = open(path, encoding="utf-8").read()
    # แยกรายช่อง (## หัวข้อ) เพื่อชี้ว่าจุดเสี่ยงอยู่ช่องไหน
    blocks = re.split(r"\n(?=## )", txt)
    out = [f"# 🔎 Content Review — verify ก่อนโพสต์",
           f"> ไฟล์: `{os.path.basename(path)}` · รีวิว {datetime.datetime.now().strftime('%Y-%m-%d %H:%M')}",
           "> comply ผ่านแล้ว (คำต้องห้าม) — ด้านล่างคือ 'ข้อเท็จจริงที่ต้องเช็กตาเอง' ก่อนโพสต์\n"]
    any_flag = False
    for b in blocks:
        head = b.splitlines()[0] if b.strip() else ""
        if not head.startswith("## "):
            continue
        fl = review_text(b)
        if fl:
            any_flag = True
            out.append(f"\n### {head[3:].strip()}")
            for label, detail in fl:
                out.append(f"- ⚠️ **{label}** — {detail}")
    if not any_flag:
        out.append("\n✅ ไม่พบจุดเสี่ยงข้อเท็จจริงเด่น ๆ — ยังควรอ่านคร่าว ๆ ก่อนโพสต์")
    os.makedirs(INBOX, exist_ok=True)
    rp = os.path.join(INBOX, "review-" + datetime.datetime.now().strftime("%Y%m%d-%H%M") + ".md")
    open(rp, "w", encoding="utf-8").write("\n".join(out))
    print(f"[content_review] -> {rp}")
    print(f"[content_review] {'มีจุดต้อง verify' if any_flag else 'ผ่านสะอาด'}")
    return rp


if __name__ == "__main__":
    try: sys.stdout.reconfigure(encoding="utf-8")
    except Exception: pass
    run(sys.argv[1] if len(sys.argv) > 1 else None)
