"""content_council.py — สภา multi-agent ตรวจสอบเนื้อหา ngernduangold.

ใช้ free_llm pool (GLM/Qwen คุณภาพดี) เป็นสมองของทุก agent · แต่ละ agent = LLM call ที่มี role เฉพาะ
chain:  expert(การเงิน/คปภ.) -> compliance(ระเบียบ) -> value(ประโยชน์) -> review(กันมั่ว+freshness) -> correct(แก้ให้ถูก) -> aggregate(รวม+เข้าคิว)

ปลอดภัยโดยออกแบบ: ผลิต "draft ที่ตรวจแล้ว" เข้าคิวรอคน approve · ไม่โพสต์ ไม่ commit ไม่ deploy.
ใช้:  python content_council.py "เคส/หัวข้อ"     (เขียนผลลง automation-log/council-<date>.md)
      from content_council import run; final, report = run("...")
"""
import os, sys, json, datetime
try:  # Windows cp874 console crashes on emoji/Thai in print — force UTF-8, never raise
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import free_llm

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)


def _banned_words():
    try:
        d = json.load(open(os.path.join(ROOT, 'tiktok-pipeline', 'compliance_rules.json'), encoding='utf-8'))
        words = []
        for k in ('banned', 'banned_words', 'forbidden', 'prohibited', 'deny'):
            v = d.get(k)
            if isinstance(v, list):
                words += [str(x) for x in v]
            elif isinstance(v, dict):
                words += list(v.keys())
        return ", ".join(words[:40]) if words else "การันตี, ผ่านแน่นอน, รวยเร็ว, ฟรี 100%, กู้ผ่านทุกราย"
    except Exception:
        return "การันตี, ผ่านแน่นอน, รวยเร็ว, ฟรี 100%, กู้ผ่านทุกราย"

BANNED = _banned_words()


def _cases(topic):
    """poor-man's RAG: ดึงจุดเจ็บจริงคนไทยจาก real_cases.md ที่ตรงกับ topic."""
    try:
        lines = [l.strip() for l in open(os.path.join(HERE, 'real_cases.md'), encoding='utf-8')
                 if l.strip() and not l.startswith('#')]
    except Exception:
        return ''
    words = set(w for w in topic.replace('/', ' ').split() if len(w) > 2)
    hit = [l for l in lines if any(w in l for w in words)]
    return ' · '.join((hit or lines[:2])[:3])


SYS = {
 "expert":  "คุณเป็นผู้เชี่ยวชาญการเงินส่วนบุคคลและประกันภัย (คปภ.) ของไทย ตอบแม่นยำ อิงข้อเท็จจริง value-first ไม่ขายฝัน ไม่แต่งตัวเลข",
 "comply":  "คุณเป็นเจ้าหน้าที่ตรวจ compliance โฆษณาการเงิน/คปภ. ที่เข้มงวดและรู้ระเบียบครบถ้วน ตรวจให้ผ่านเฉพาะที่ถูกต้องจริง",
 "value":   "คุณเป็นผู้เชี่ยวชาญด้านคุณค่าต่อผู้ใช้ ประเมินว่าเนื้อหาช่วยแก้ปัญหาจริงและมี bridge แนบเนียน ไม่สแปม",
 "review":  "คุณเป็น QA reviewer จับ output ที่ภาษาเพี้ยน/ปนภาษา/ข้อมูลแต่งเอง/ออกนอกเรื่อง อย่างละเอียด",
 "correct": "คุณเป็นบรรณาธิการ แก้เนื้อหาให้ถูกต้องตาม feedback ทั้งหมด คงโทนเป็นธรรมชาติ",
}


def agent(role, user, max_tokens=1500):
    t, m = free_llm.generate(user, system=SYS[role], max_tokens=max_tokens, temperature=0.3)
    return (t or "").strip(), (m or "?")


def run(topic):
    rep = {}
    ctx = _cases(topic)
    draft, rep['m_expert'] = agent("expert",
        (("บริบทจุดเจ็บจริงของคนไทย (ใช้ให้เนื้อหาจี้จุด ไม่ลอยๆ): " + ctx + "\n\n") if ctx else "") +
        "ร่างคำตอบ Pantip แบบ value-first สำหรับเคส: " + topic +
        "\nกฎ: ไม่มีลิงก์ในคำตอบ, คปภ-safe (ประกันไม่การันตีผล), ไม่ fabricate ตัวเลข, ปิดท้ายชวนคุยต่อทาง DM/โปรไฟล์ แบบไม่สแปม")
    rep['compliance'], _ = agent("comply",
        "ตรวจคำตอบนี้ตามระเบียบโฆษณาการเงิน/คปภ. คำต้องห้าม: " + BANNED +
        "\nสรุป PASS หรือ FAIL แล้วลิสต์ปัญหาเป็นข้อ (ถ้ามี):\n\n" + draft, 700)
    rep['value'], _ = agent("value",
        "ประเมินว่าคำตอบนี้มีคุณค่าจริงต่อคนถามไหม + bridge ไป DM แนบเนียนไหม ลิสต์จุดอ่อน:\n\n" + draft, 500)
    rep['review'], _ = agent("review",
        "ตรวจหา: (ก)ภาษาเพี้ยน/ปนภาษา (ข)ข้อมูลมั่ว/แต่งเอง (ค)ออกนอกเรื่อง (ง)ตัวเลขที่ต้องเช็กแหล่งจริง ลิสต์ปัญหา:\n\n" + draft, 600)
    final, rep['m_final'] = agent("correct",
        "แก้คำตอบให้ถูกต้องตาม feedback ทุกข้อ. บังคับ: (1) สไตล์ Pantip คุยกันสั้นกระชับเป็นย่อหน้า ไม่ใช่บทความหัวข้อย่อยเยอะ "
        "(2) ตัวเลขดอกเบี้ย/ค่าธรรมเนียม = ช่วงกว้างๆ + กำกับ 'เช็กกับธนาคาร/หน้าบัตรอีกที' ห้ามฟันธงเป๊ะ "
        "(3) ปิดท้ายด้วยสะพานชวนคุยต่อทาง DM/โปรไฟล์ แบบไม่สแปม. คืน 'คำตอบสุดท้าย' อย่างเดียว ภาษาไทย ไม่มีลิงก์:\n\n"
        "[คำตอบเดิม]\n" + draft + "\n\n[Compliance]\n" + rep['compliance'] +
        "\n\n[Value]\n" + rep['value'] + "\n\n[Review]\n" + rep['review'], 1500)
    return final, rep


def _write_queue(topic, final, rep):
    d = datetime.date.today().isoformat()
    p = os.path.join(ROOT, 'automation-log', 'council-' + d + '.md')
    with open(p, 'a', encoding='utf-8') as f:
        f.write("## เคส: " + topic + "\n")
        f.write("_draft=" + rep['m_expert'] + " · final=" + rep['m_final'] + " · ตรวจ 5 ชั้น_\n\n")
        f.write("### ✅ คำตอบ (ตรวจแล้ว — รอ approve ก่อนโพสต์)\n" + final + "\n\n")
        f.write("<details><summary>รายงานการตรวจ</summary>\n\n**Compliance:** " + rep['compliance'] +
                "\n\n**Value:** " + rep['value'] + "\n\n**Review:** " + rep['review'] + "\n</details>\n\n---\n\n")
    if "\ufffd" in open(p, encoding="utf-8").read():
        import sys as _s; _s.stderr.write("[content_council] WARN U+FFFD in " + p + "\n")
    return p


if __name__ == "__main__":
    topic = sys.argv[1] if len(sys.argv) > 1 else "หนี้บัตรเครดิต+บัตรกดเงินสด รวม 240,000 มี notice อยากไปไกล่เกลี่ย"
    final, rep = run(topic)
    path = _write_queue(topic, final, rep)
    print("DRAFT model:", rep['m_expert'], "| FINAL model:", rep['m_final'])
    print("QUEUE ->", path)
    print("\n=== FINAL (ตรวจแล้ว) ===\n" + final)
