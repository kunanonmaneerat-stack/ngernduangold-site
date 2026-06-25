"""art_agents.py — agent ดูแล art + graphic + head of art/graphic (ยกระดับหน้าตาเว็บ).

run(key, ctx) -> ข้อเสนอออกแบบจาก free_llm · main() -> head รวม art+graphic -> work order ให้ CC.
สโคป: เสนอ (read-only) -> Claude Code implement (คนอนุมัติ) ไม่ commit/deploy เอง.
ใช้:  py pipeline/art_agents.py
"""
import os, sys, glob, datetime
try:  # cp874-safe: UTF-8 stdout/stderr so Thai/emoji prints never crash on Windows console (idempotent)
    import sys as _sys; _sys.stdout.reconfigure(encoding="utf-8", errors="replace"); _sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import free_llm, cc_bridge

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SITE = os.path.join(ROOT, 'site')
ROLES = {
 'art': ('Art Director', 'ทิศทางศิลป์: โทนสี/mood แบรนด์การเงินที่ "น่าเชื่อถือแต่มีชีวิตชีวา ไม่น่าเบื่อ", ภาพประกอบ/ไอคอน, hero ที่ดึงดูด, จังหวะภาพ'),
 'graphic': ('Graphic Designer', 'งานกราฟิก: layout, typography, ลำดับชั้น, spacing, ปุ่ม/การ์ด, ความสม่ำเสมอ, อ่านง่าย+โหลดเร็วบนมือถือ'),
}
PERSONA = ('คุณเป็น {role} ของเว็บการเงินไทย ngernduangold เป้าหมาย: สวย สะอาด น่าเชื่อถือ มีชีวิตชีวา '
           'ไม่น่าเบื่อ ใช้ง่าย โหลดเร็ว · เสนอเป็นข้อๆ ทำได้จริงด้วย HTML/CSS')


def _site_snapshot():
    fs = sorted(glob.glob(os.path.join(SITE, '*.html')))
    head = open(fs[0], encoding='utf-8', errors='ignore').read()[:1500] if fs else ''
    return 'จำนวนหน้า ' + str(len(fs)) + ' · ตัวอย่าง HTML หน้าแรก:\n' + head


def run(key, ctx):
    role, brief = ROLES[key]
    t, m = free_llm.generate(
        'ดูสภาพเว็บปัจจุบันแล้วเสนอ 5 ปรับปรุงเฉพาะด้านคุณ (' + brief + ') ทำได้จริง ระบุไฟล์/จุดที่ควรแก้:\n\n' + ctx,
        system=PERSONA.format(role=role), max_tokens=900, temperature=0.5)
    return role, (t or '').strip(), m


def main():
    ctx = _site_snapshot()
    ts = datetime.datetime.now().strftime('%Y%m%d-%H%M%S')
    body = ('# WORK ORDER -> Claude Code: ยกระดับหน้าตาเว็บ (head of art & graphic) ' + ts + '\n\n'
            '> สโคป: ปรับ HTML/CSS ให้สวย/น่าเชื่อถือ/มีชีวิตชีวา · คงโหลดเร็ว+มือถือ · ห้าม commit/deploy เอง รอ owner OK\n\n')
    for k in ROLES:
        role, txt, m = run(k, ctx)
        body += '## ' + role + ' (' + str(m) + ')\n' + txt + '\n\n'
    p = cc_bridge.send('ยกระดับหน้าตาเว็บ (art+graphic)', body)
    cc_bridge.ping('Head of art & graphic: บรีฟปรับเว็บ -> ' + os.path.basename(p) + ' (Cowork คุมต่อ)')
    print('art brief -> CC inbox:', p)


if __name__ == '__main__':
    main()
