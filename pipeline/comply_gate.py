"""comply_gate.py — ชั้นตรวจ compliance อัตโนมัติ คั่นหลัง CC ก่อนเข้าคิวโพสต์.

check(text) : สแกนคำ trigger ต้องห้าม + เช็กว่าตัวเลข %/ดอกเบี้ย มี caveat กำกับ
              -> (ok: bool, issues: list[str])   [pure stdlib — รันที่ไหนก็ได้]
fix(text, issues) : แก้ด้วย free_llm แล้วคืนข้อความใหม่ (ต้องมีคีย์/เน็ต)
gate(text) : check -> ถ้า fail ลอง fix -> check ซ้ำ -> คืน (text2, ok, issues)
"""
import re, os, sys
try:  # cp874-safe: UTF-8 stdout/stderr so Thai/emoji prints never crash on Windows console (idempotent)
    import sys as _sys; _sys.stdout.reconfigure(encoding="utf-8", errors="replace"); _sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

TRIGGERS = ["ฟรีไม่มี", "ฟรี 100", "ผ่านแน่นอน", "อนุมัติแน่นอน", "การันตี", "รับรองผล",
            "รวยเร็ว", "รวยไว", "ได้เงินชัวร์", "ปิดหนี้ได้ 100", "ไร้ความเสี่ยง",
            "คลิกเลย", "กู้ผ่านทุก", "ผ่านทุกราย", "ดอกถูกที่สุด", "ดีที่สุดในไทย"]
CAVEAT_HINTS = ["เช็ก", "เช็ค", "สอบถาม", "ขึ้นกับ", "แล้วแต่", "อีกที", "ตรวจสอบ", "ประมาณ", "ราว"]

# กฎฉีดเข้าพรอมป์ตทุก agent ที่ผลิตคอนเทนต์ (กันแต่ต้นทาง ดีกว่าแก้ทีหลัง)
RULE = ("เขียนสุภาพ เป็นกลาง ไม่โอ้อวด ไม่รับประกัน/ไม่ฟันธงผลลัพธ์ ไม่ใช้คำเร่งเร้าหรือคำขายของ; "
        "ตัวเลขดอกเบี้ย/ค่าธรรมเนียม/เปอร์เซ็นต์ ให้เป็นช่วงกว้างๆ พร้อมกำกับ 'เช็กกับธนาคารอีกที' เสมอ; "
        "วางตัวเป็นการ 'รวบรวม/เปรียบเทียบข้อมูล' ไม่ใช่ที่ปรึกษาการเงินที่มีใบอนุญาต; "
        "ถ้าพูดเรื่องกู้/สินเชื่อ แนบแนวคิด 'กู้เท่าที่จำเป็นและชำระคืนตามกำหนด' (Responsible Lending ธปท.); "
        "ลิงก์อยู่ DM/bio เท่านั้น; คืนเฉพาะคอนเทนต์ที่พร้อมใช้ ไม่ต้องมีคำนำหรือหมายเหตุการแก้")


NEGATABLE = {"การันตี", "รับรองผล"}  # guarantee-of-result words: COMPLIANT when negated
_NEG_CUES = ["ไม่", "ปฏิเสธ"]
_SENT_END = ".!?\n"

def _negated(text, pos):
    """True if a negation cue appears within ~20 chars left of pos with no sentence-end between."""
    left = text[max(0, pos - 20):pos]
    ci = max((left.rfind(c) for c in _NEG_CUES), default=-1)
    if ci < 0:
        return False
    return not any(ch in _SENT_END for ch in left[ci:])


def check(text):
    issues = []
    for w in TRIGGERS:
        if w not in text:
            continue
        if w in NEGATABLE:
            i, hit = 0, False
            while True:
                q = text.find(w, i)
                if q < 0:
                    break
                if not _negated(text, q):
                    hit = True; break
                i = q + len(w)
            if not hit:
                continue
        issues.append("คำ trigger ต้องห้าม: '" + w + "'")
    if re.search(r"\d+\s*%", text) and not any(h in text for h in CAVEAT_HINTS):
        issues.append("มีตัวเลข % แต่ไม่มีคำกำกับให้เช็ก/ประมาณ")
    if re.search(r"\b0\s*%", text):
        issues.append("เคลม 0% ตรงๆ เสี่ยงการันตี -> ใส่เงื่อนไข/ช่วงเวลา + 'เช็กกับธนาคาร'")
    return (len(issues) == 0, issues)


def fix(text, issues):
    import free_llm
    prompt = ("เขียนคอนเทนต์นี้ใหม่ให้สุภาพ เป็นกลาง: " + RULE +
              "\nคงสไตล์/โครงเดิม คืนเฉพาะคอนเทนต์ที่แก้แล้ว ไม่มีคำนำ/หมายเหตุ:\n\n" + text)
    t, _ = free_llm.generate(prompt, max_tokens=1800, temperature=0.3)
    return t or text


def gate(text):
    ok, issues = check(text)
    if ok:
        return text, True, []
    fixed = fix(text, issues)
    ok2, issues2 = check(fixed)
    return fixed, ok2, issues2


if __name__ == "__main__":
    bad = "หนี้บัตร 240k ส่ง DM มาเลย ฟรีไม่มีค่าใช้จ่าย ลดดอกได้ 12-15% และผ่อน 0% 6 เดือน"
    ok, iss = check(bad)
    print("BAD ->", ok, iss)
    good = "หนี้บัตร 240k ทักมาคุยกันได้ ดอกเบี้ยลดได้ราว 12-15% ต้องเช็กกับธนาคารอีกที"
    print("GOOD ->", check(good))
