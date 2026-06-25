"""external_consult.py — agent ปรึกษาภายนอก (Gemini + Opus ผ่านเบราว์เซอร์) -> รวมส่ง Cowork.

prepare(question, context) : เขียน consult-inbox/ask-<ts>.md (บรีฟไปวางถาม)
collect(ts)                : อ่าน consult-outbox/gemini-<ts>.md + opus-<ts>.md -> รวม
                             consult-merged-<ts>.md -> ping Cowork
ขา browser = on-demand: Cowork ขับ Claude-in-Chrome ถาม gemini.google.com (3.5 flash extended)
+ claude.ai (Opus 4.8 max) แล้วเซฟคำตอบตามชื่อ ts. (ต้อง login + คนอยู่ด้วย ไม่ใช่ cron เงียบ)
ใช้:  py pipeline/external_consult.py "คำถาม"   แล้ว   py pipeline/external_consult.py collect <ts>
"""
import os, sys, datetime
try:  # cp874-safe: UTF-8 stdout/stderr so Thai/emoji prints never crash on Windows console (idempotent)
    import sys as _sys; _sys.stdout.reconfigure(encoding="utf-8", errors="replace"); _sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import cc_bridge

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOG = os.path.join(ROOT, 'automation-log')
IN = os.path.join(LOG, 'consult-inbox')
OUT = os.path.join(LOG, 'consult-outbox')


def prepare(question, context=''):
    os.makedirs(IN, exist_ok=True); os.makedirs(OUT, exist_ok=True)
    ts = datetime.datetime.now().strftime('%Y%m%d-%H%M%S')
    p = os.path.join(IN, 'ask-' + ts + '.md')
    with open(p, 'w', encoding='utf-8') as f:
        f.write('# ปรึกษาภายนอก (' + ts + ')\n\n**คำถาม:** ' + question + '\n\n**บริบท:**\n' + context +
                '\n\n---\nเอาบรีฟนี้ไปถาม:\n'
                '- Gemini (gemini.google.com · 3.5 flash extended) -> เซฟที่ consult-outbox/gemini-' + ts + '.md\n'
                '- Opus (claude.ai · 4.8 max) -> เซฟที่ consult-outbox/opus-' + ts + '.md\n'
                'แล้วรัน: py pipeline/external_consult.py collect ' + ts + '\n')
    cc_bridge.ping('ปรึกษาภายนอก: บรีฟพร้อม -> consult-inbox/ask-' + ts + '.md (Cowork ขับ Chrome ถาม Gemini+Opus)')
    return ts, p


def collect(ts):
    g = os.path.join(OUT, 'gemini-' + ts + '.md')
    o = os.path.join(OUT, 'opus-' + ts + '.md')
    gtxt = open(g, encoding='utf-8').read() if os.path.exists(g) else '(ยังไม่มีคำตอบ Gemini)'
    otxt = open(o, encoding='utf-8').read() if os.path.exists(o) else '(ยังไม่มีคำตอบ Opus)'
    m = os.path.join(LOG, 'consult-merged-' + ts + '.md')
    with open(m, 'w', encoding='utf-8') as f:
        f.write('# ปรึกษาภายนอก รวมผล (' + ts + ') — ส่ง Cowork\n\n## Gemini 3.5 flash\n' + gtxt +
                '\n\n## Opus 4.8\n' + otxt +
                '\n\n## Cowork ทำต่อ\nสังเคราะห์ 2 มุม + ของเรา -> ไอเดียยกระดับ -> เขียน orders.txt/แผนรอบใหม่\n')
    cc_bridge.ping('ปรึกษาภายนอก: รวมผล Gemini+Opus -> consult-merged-' + ts + '.md (Cowork คุมต่อ)')
    return m


if __name__ == '__main__':
    if len(sys.argv) > 2 and sys.argv[1] == 'collect':
        print('merged ->', collect(sys.argv[2]))
    else:
        q = sys.argv[1] if len(sys.argv) > 1 else 'วิธีเพิ่ม traffic+conversion ngernduangold ทุกแพลตฟอร์ม'
        ts, p = prepare(q); print('brief ->', p, '| ts', ts)
