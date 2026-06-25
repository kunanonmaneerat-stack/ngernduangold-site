"""ask_cowork.py — agent escalation: ไม่แน่ใจทางเลือกไหนดีสุด -> วนกลับมาถาม Cowork.

ask(question, options, context) : เขียน automation-log/ask-cowork/q-<ts>.md + ping Telegram
pending()                        : ลิสต์คำถามที่ Cowork ยังไม่ตอบ
Cowork อ่านไฟล์ เติมใต้ "## ตัดสินใจ (Cowork)" -> agent อ่านไปทำต่อ.
แทรกในทุก agent: ถ้า confidence ต่ำ/ก้ำกึ่ง เรียก ask() แล้วหยุดรอ แทนการเดาเอง.
"""
import os, sys, glob, datetime
try:  # cp874-safe: UTF-8 stdout/stderr so Thai/emoji prints never crash on Windows console (idempotent)
    import sys as _sys; _sys.stdout.reconfigure(encoding="utf-8", errors="replace"); _sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import cc_bridge

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ASK = os.path.join(ROOT, 'automation-log', 'ask-cowork')
MARK = '_(Cowork เติมคำตอบที่นี่)_'


def ask(question, options=None, context=''):
    os.makedirs(ASK, exist_ok=True)
    ts = datetime.datetime.now().strftime('%Y%m%d-%H%M%S')
    p = os.path.join(ASK, 'q-' + ts + '.md')
    with open(p, 'w', encoding='utf-8') as f:
        f.write('# ถาม Cowork (' + ts + ')\n\n**คำถาม:** ' + question + '\n\n')
        if options:
            f.write('**ตัวเลือก:**\n')
            for i, o in enumerate(options, 1):
                f.write('- (' + str(i) + ') ' + o + '\n')
            f.write('\n')
        if context:
            f.write('**บริบท:**\n' + context + '\n\n')
        f.write('## ตัดสินใจ (Cowork)\n' + MARK + '\n')
    cc_bridge.ping('Cowork ต้องตัดสินใจ: ' + question[:80] + ' -> ask-cowork/q-' + ts + '.md')
    return p


def pending():
    out = []
    for f in sorted(glob.glob(os.path.join(ASK, 'q-*.md'))):
        body = open(f, encoding='utf-8').read().split('## ตัดสินใจ (Cowork)', 1)[-1]
        if MARK in body or len(body.strip()) < 30:
            out.append(os.path.basename(f))
    return out


if __name__ == '__main__':
    print('pending:', pending())
