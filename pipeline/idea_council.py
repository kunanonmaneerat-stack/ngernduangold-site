"""idea_council.py — agent เพิ่มความหลากหลาย + ยกระดับไอเดีย (ใช้ free_llm หลายมุมมอง).

ปั่นไอเดียจาก persona ต่างกัน -> สังเคราะห์ท็อปไอเดียจัดอันดับ effort/impact
-> automation-log/ideas-<ts>.md. (ใช้ทุกโมเดลที่เรามีในพูล, $0)
ใช้:  py pipeline/idea_council.py "หัวข้อ/โจทย์"
"""
import os, sys, datetime
try:  # cp874-safe: UTF-8 stdout/stderr so Thai/emoji prints never crash on Windows console (idempotent)
    import sys as _sys; _sys.stdout.reconfigure(encoding="utf-8", errors="replace"); _sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import free_llm

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PERSONAS = {
 'growth': 'คุณเป็น growth hacker สายการเงิน คิดวิธีโตเร็วแบบ unconventional แต่ถูกระเบียบ',
 'viral':  'คุณเป็นครีเอเตอร์คอนเทนต์ไวรัลไทย เก่ง hook 3 วิแรก มุมเล่าที่คนหยุดดู',
 'trust':  'คุณเป็นนักการเงินอนุรักษ์นิยม เน้น trust/คปภ./social proof ลดความกังวลคนดู',
 'funnel': 'คุณเป็น CRO ผู้เชี่ยวชาญ funnel เปลี่ยน traffic เป็น quiz/lead',
}


def run(topic):
    ideas = {}
    for k, sysp in PERSONAS.items():
        t, _ = free_llm.generate('เสนอ 3 ไอเดียเฉพาะตัว (สั้น bullet) สำหรับ: ' + topic,
                                 system=sysp, max_tokens=500, temperature=0.7)
        ideas[k] = (t or '').strip()
    blob = '\n\n'.join('[' + k + ']\n' + v for k, v in ideas.items())
    synth, _ = free_llm.generate(
        'รวมไอเดียทั้งหมด เลือก 5 ที่ทำได้จริง + ต่างมุม จัดอันดับ effort/impact พร้อมเหตุผลสั้น:\n\n' + blob,
        max_tokens=800, temperature=0.4)
    ts = datetime.datetime.now().strftime('%Y%m%d-%H%M%S')
    p = os.path.join(ROOT, 'automation-log', 'ideas-' + ts + '.md')
    with open(p, 'w', encoding='utf-8') as f:
        f.write('# IDEAS — ' + topic + ' (' + ts + ')\n\n## ท็อป 5 (สังเคราะห์)\n' +
                (synth or '') + '\n\n## ดิบจากแต่ละมุม\n' + blob)
    return p, synth


if __name__ == '__main__':
    topic = sys.argv[1] if len(sys.argv) > 1 else 'เพิ่ม traffic+conversion ngernduangold'
    p, s = run(topic)
    print('ideas ->', p)
