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
RESPONSIBLE_LINE = "\u0e01\u0e39\u0e49\u0e40\u0e17\u0e48\u0e32\u0e17\u0e35\u0e48\u0e08\u0e33\u0e40\u0e1b\u0e47\u0e19\u0e41\u0e25\u0e30\u0e0a\u0e33\u0e23\u0e30\u0e04\u0e37\u0e19\u0e44\u0e2b\u0e27"
LEGACY_RESPONSIBLE_LINE = "\u0e01\u0e39\u0e49\u0e40\u0e17\u0e48\u0e32\u0e17\u0e35\u0e48\u0e08\u0e33\u0e40\u0e1b\u0e47\u0e19\u0e41\u0e25\u0e30\u0e0a\u0e33\u0e23\u0e30\u0e04\u0e37\u0e19\u0e15\u0e32\u0e21\u0e01\u0e33\u0e2b\u0e19\u0e14"
LENDING_TERMS = [
    "\u0e01\u0e39\u0e49", "\u0e2a\u0e34\u0e19\u0e40\u0e0a\u0e37\u0e48\u0e2d", "\u0e1a\u0e31\u0e15\u0e23\u0e40\u0e04\u0e23\u0e14\u0e34\u0e15",
]
BANNED_LENDING_PATTERNS = [
    r"\u0e43\u0e04\u0e23\s*[\u0e46]?\s*\u0e01\u0e47?\u0e01\u0e39\u0e49\u0e44\u0e14\u0e49",
    r"\u0e44\u0e21\u0e48\u0e14\u0e39\s*\u0e40\u0e04\u0e23\u0e14\u0e34\u0e15",
    r"\u0e44\u0e21\u0e48\u0e40\u0e0a[\u0e47\u0e47]\u0e04\s*(?:\u0e40\u0e04\u0e23\u0e14\u0e34\u0e15\s*)?\u0e1a\u0e39\u0e42\u0e23",
    r"\u0e44\u0e21\u0e48\u0e40\u0e0a[\u0e47\u0e47]\u0e04.{0,20}(?:\u0e01\u0e39\u0e49|\u0e2a\u0e34\u0e19\u0e40\u0e0a\u0e37\u0e48\u0e2d)",
    r"\u0e15\u0e34\u0e14\u0e1a\u0e39\u0e42\u0e23\s*\u0e01\u0e47?\s*\u0e01\u0e39\u0e49\u0e44\u0e14\u0e49",
    r"\u0e01\u0e39\u0e49\s*(?:\u0e40\u0e07\u0e34\u0e19)?\s*(?:\u0e40\u0e23\u0e37\u0e48\u0e2d\u0e07)?\s*\u0e07\u0e48\u0e32\u0e22",
    r"\u0e2d\u0e19\u0e38\u0e21\u0e31\u0e15\u0e34\s*\u0e07\u0e48\u0e32\u0e22",
    r"\u0e41\u0e04\u0e48\s*(?:\u0e21\u0e35\u0e23\u0e16|\u0e16\u0e37\u0e2d\u0e40\u0e25\u0e48\u0e21\u0e17\u0e30\u0e40\u0e1a\u0e35\u0e22\u0e19).{0,40}\u0e01\u0e39\u0e49\u0e44\u0e14\u0e49",
    r"\u0e23\u0e31\u0e1a\u0e40\u0e07\u0e34\u0e19\u0e2a\u0e14\u0e44\u0e14\u0e49\u0e17\u0e31\u0e19\u0e17\u0e35",
    r"\u0e02\u0e2d\u0e07\u0e21\u0e31\u0e19\u0e15\u0e49\u0e2d\u0e07\u0e21\u0e35",
    r"\u0e2d\u0e22\u0e32\u0e01\u0e44\u0e14\u0e49\u0e15\u0e49\u0e2d\u0e07\u0e44\u0e14\u0e49",
    r"\u0e44\u0e2e\u0e42\u0e0b\u0e01\u0e48\u0e2d\u0e19.{0,20}\u0e04\u0e48\u0e2d\u0e22\u0e1c\u0e48\u0e2d\u0e19\u0e17\u0e35\u0e2b\u0e25\u0e31\u0e07",
]

# กฎฉีดเข้าพรอมป์ตทุก agent ที่ผลิตคอนเทนต์ (กันแต่ต้นทาง ดีกว่าแก้ทีหลัง)
RULE = ("เขียนสุภาพ เป็นกลาง ไม่โอ้อวด ไม่รับประกัน/ไม่ฟันธงผลลัพธ์ ไม่ใช้คำเร่งเร้าหรือคำขายของ; "
        "ตัวเลขดอกเบี้ย/ค่าธรรมเนียม/เปอร์เซ็นต์ ให้เป็นช่วงกว้างๆ พร้อมกำกับ 'เช็กกับธนาคารอีกที' เสมอ; "
        "วางตัวเป็นการ 'รวบรวม/เปรียบเทียบข้อมูล' ไม่ใช่ที่ปรึกษาการเงินที่มีใบอนุญาต; "
        "ถ้าพูดเรื่องกู้/สินเชื่อ แนบคำเตือน '" + RESPONSIBLE_LINE + "' (Responsible Lending ธปท.); "
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
    warns = []
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
    for pattern in BANNED_LENDING_PATTERNS:
        if re.search(pattern, text, flags=re.IGNORECASE):
            issues.append("official Responsible Lending prohibited phrase")
            break
    if re.search(r"\d+\s*%", text) and not any(h in text for h in CAVEAT_HINTS):
        issues.append("มีตัวเลข % แต่ไม่มีคำกำกับให้เช็ก/ประมาณ")
    if re.search(r"\b0\s*%", text):
        issues.append("เคลม 0% ตรงๆ เสี่ยงการันตี -> ใส่เงื่อนไข/ช่วงเวลา + 'เช็กกับธนาคาร'")
    if any(term in text for term in LENDING_TERMS) and RESPONSIBLE_LINE not in text:
        issues.append("missing Responsible Lending warning")
    if LEGACY_RESPONSIBLE_LINE in text and RESPONSIBLE_LINE not in text:
        warns.append("WARN legacy Responsible Lending wording; use current standard warning")
    # STALE-FACTS warn (ไม่ block — FACTS_current.md 2026-07-02): ตัวเลข/มาตรการที่ตกยุคแล้ว
    if re.search(r"ขั้นต่ำ\s*5\s*(-\s*10\s*)?%", text):
        warns.append("WARN stale-fact: 'จ่ายขั้นต่ำ 5%' ตกยุค — ปัจจุบัน 8% ถึง 31 ธ.ค. 69 (ดู knowledge-base/FACTS_current.md)")
    if re.search(r"คุณสู้.{0,3}เราช่วย", text) and re.search(r"ลงทะเบียน|สมัครได้|รีบสมัคร|สมัครเลย", text):
        warns.append("WARN stale-fact: 'คุณสู้ เราช่วย' ปิดรับแล้ว (30 ก.ย. 68) — ห้ามชวนสมัคร ใช้เล่าอ้างอิงอดีตเท่านั้น")
    return (len(issues) == 0, issues + warns)


def check_post(text, channel=None):
    """check() + text-dedup ต่อช่อง (POSTING-POLICY_antispam_20260702).
    channel=None -> เช็กเนื้อหาอย่างเดียว. duplicate -> GATE_FAIL พร้อมชี้โพสต์เดิมที่ชน."""
    ok, issues = check(text)
    if channel:
        try:
            _al = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "automation-log")
            if _al not in sys.path:
                sys.path.insert(0, _al)
            import post_ledger
            dup, reason, _prior = post_ledger.is_duplicate_text(channel, text)
            if dup:
                ok = False
                issues.append("GATE_FAIL duplicate-text (" + post_ledger.norm_channel(channel) + "): " + reason)
        except Exception as e:  # dedup cannot be proven -> publication must stop
            ok = False
            issues.append("GATE_FAIL text-dedup unavailable (" + str(e)[:80] + ")")
    return ok, issues


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
