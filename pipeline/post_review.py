"""post_review.py — 6 agent review post รายแพลตฟอร์ม (QA ก่อนโพสต์).

อ่าน draft ล่าสุดใน social-queue/<platform>/ -> comply_gate.check + เช็กลิสต์เฉพาะแพลตฟอร์ม
-> social-review/<platform>/review-<ts>.md (verdict READY/FIX + เช็กลิสต์). ไม่โพสต์.
ใช้:  py pipeline/post_review.py
"""
import os, sys, glob, datetime
try:  # cp874-safe: UTF-8 stdout/stderr so Thai/emoji prints never crash on Windows console (idempotent)
    import sys as _sys; _sys.stdout.reconfigure(encoding="utf-8", errors="replace"); _sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import comply_gate, platform_agents

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOG = os.path.join(ROOT, 'automation-log')
SQ = os.path.join(LOG, 'social-queue')
SR = os.path.join(LOG, 'social-review')

CHECKS = {
 'pantip':  ['value-first ไม่ดูเป็นโฆษณา', 'ไม่มีลิงก์ในคำตอบ', 'ปิดท้ายชวน DM แนบเนียน'],
 'fb':      ['เปิดด้วยปัญหาที่คนอิน', 'มีคำเตือน Responsible Lending', 'ไม่มีลิงก์ในโพสต์'],
 'ig':      ['สไลด์ 1 = hook', 'ระบุเงื่อนไขสำคัญในสไลด์', 'ลิงก์ bio เท่านั้น'],
 'tiktok':  ['hook 3 วิแรกสะดุด', 'มี text overlay คำเตือนหนี้', 'CTA คอมเมนต์/DM'],
 'yt':      ['ชื่อคลิปมีคีย์เวิร์ด SEO', 'เปรียบเทียบตามจริง', 'ลิงก์ pinned comment'],
 'threads': ['hook ชวนถก ไม่โจมตีสถาบัน', 'thread มีประโยชน์ก่อนชวน', 'กรอบ "รวบรวมข้อมูล"'],
}


def main():
    ts = datetime.datetime.now().strftime('%Y%m%d-%H%M%S')
    total = 0
    for key in platform_agents.PLATFORMS:
        drafts = sorted(glob.glob(os.path.join(SQ, key, '*.md')))
        if not drafts:
            continue
        latest = drafts[-1]
        body = open(latest, encoding='utf-8').read()
        ok, issues = comply_gate.check(body)
        verdict = 'READY' if ok else 'FIX: ' + '; '.join(issues)
        chk = '\n'.join('- [ ] ' + c for c in CHECKS.get(key, []))
        rd = os.path.join(SR, key); os.makedirs(rd, exist_ok=True)
        with open(os.path.join(rd, 'review-' + ts + '.md'), 'w', encoding='utf-8') as f:
            f.write('# review ' + key + ' — ' + verdict + '\n\nเช็กลิสต์ก่อนโพสต์ (คนติ๊ก):\n' + chk + '\n\n---\n' + body)
        total += 1
        print(key, '->', verdict)
    print('reviewed', total, 'platforms ->', SR)


if __name__ == '__main__':
    main()
