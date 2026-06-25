"""executor.py — agent รวมข้อมูล (aggregator) + ส่ง execute ให้ Claude Code.

อ่านคิวที่ผ่านสภา council-<date>.md (= แผนที่ตรวจ 5 ชั้นแล้ว) -> ประกอบเป็น work order
-> ส่งให้ Claude Code ผ่าน cc_bridge.send (เขียน cc-inbox/ + ping Telegram).

สโคปที่สั่ง CC = ทำ draft/variation หลายแพลตฟอร์มเท่านั้น ห้ามโพสต์/commit/deploy.
รัน:  py pipeline/executor.py
"""
import os, sys, glob, datetime
try:  # cp874-safe: UTF-8 stdout/stderr so Thai/emoji prints never crash on Windows console (idempotent)
    import sys as _sys; _sys.stdout.reconfigure(encoding="utf-8", errors="replace"); _sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import cc_bridge

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
LOG = os.path.join(ROOT, 'automation-log')


def latest_council():
    fs = sorted(glob.glob(os.path.join(LOG, 'council-*.md')))
    return fs[-1] if fs else None


def extract_plan(path):
    """ดึง (เคส, คำตอบที่ตรวจแล้ว) ตัด <details> รายงานตรวจออก."""
    blocks, cur, keep = [], None, False
    for line in open(path, encoding='utf-8'):
        if line.startswith('## เคส'):
            if cur and cur['answer']:
                blocks.append(cur)
            cur = {'case': line[7:].strip().lstrip(':').strip(), 'answer': []}
            keep = False
        elif cur is not None:
            if line.startswith('### ✅'):
                keep = True; continue
            if line.startswith('<details') or line.startswith('---'):
                keep = False
            if keep and line.strip() and not line.startswith('_'):
                cur['answer'].append(line.rstrip())
    if cur and cur['answer']:
        blocks.append(cur)
    return blocks


def build_order(blocks, ts):
    L = []
    L.append('# WORK ORDER -> Claude Code  (' + ts + ')')
    L.append('')
    L.append('> สโคปปลอดภัย: ทำ **draft/variation เท่านั้น** — ห้ามโพสต์ ห้าม commit ห้าม deploy')
    L.append('> เสร็จแล้วเขียนผลลง `automation-log/cc-outbox/result-' + ts + '.md` (รูปแบบดู CC-PROTOCOL.md)')
    L.append('')
    L.append('## สิ่งที่ต้องทำกับคำตอบที่ผ่านสภาแต่ละข้อ')
    L.append('1. **Threads** — question-hook 1-2 บรรทัด + ปิดท้ายชวนคุย DM (ไม่มีลิงก์)')
    L.append('2. **Facebook group** — โพสต์ value 3-5 บรรทัด (ไม่มีลิงก์)')
    L.append('3. **TikTok/Reels** — สคริปต์พูด ≤20 วินาที (hook 3 วิแรกต้องสะดุด)')
    L.append('4. **ปรับปรุง** — 1 ข้อเสนอยกระดับเนื้อหา/ฟันเนล (วิเคราะห์ read-only)')
    L.append('')
    L.append('## วัตถุดิบ (คำตอบตรวจ 5 ชั้นแล้ว)')
    L.append('')
    for i, b in enumerate(blocks, 1):
        L.append('### ' + str(i) + '. ' + b['case'])
        L.append('\n'.join(b['answer']).strip())
        L.append('')
    return '\n'.join(L)


def main():
    src = latest_council()
    if not src:
        print('no council queue found'); return
    blocks = extract_plan(src)
    if not blocks:
        print('council queue has no verified answers'); return
    ts = datetime.datetime.now().strftime('%Y%m%d-%H%M%S')
    body = build_order(blocks, ts)
    p = cc_bridge.send('execute ' + str(len(blocks)) + ' เคส -> คอนเทนต์หลายแพลตฟอร์ม', body)
    print('aggregated', len(blocks), 'verified cases from', os.path.basename(src))
    print('-> CC inbox:', p)


if __name__ == '__main__':
    main()
