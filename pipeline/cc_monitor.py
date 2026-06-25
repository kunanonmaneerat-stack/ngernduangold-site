# -*- coding: utf-8 -*-
"""cc_monitor.py — agent เฝ้าสถานะงาน Claude Code -> ส่งสรุปให้ Cowork.

อ่าน (read-only, ไม่ย้ายไฟล์) สถานะ:
  - cc-inbox : ออเดอร์ค้าง (CC ยังไม่ทำ)
  - cc-outbox: ผลที่ CC ทำเสร็จ รอ review/consume
  - cc-archive: ออเดอร์ที่ทำไปแล้ว
ดึง 'ธงต้องขออนุมัติ' จากผลล่าสุด -> เขียน cowork-inbox/cc-status-<ts>.md + ping Cowork.

ต่างจาก cc_review/report_to_cowork (ที่ collect() = ย้ายผลเข้า archive แล้วรีวิวลึก):
ตัวนี้ = 'จอมอนิเตอร์' บอกว่าตอนนี้วงจรอยู่ตรงไหน ค้างไหม มีอะไรรอ Cowork ตัดสิน.
ใช้:  py pipeline/cc_monitor.py
"""
import os, sys, glob, re, datetime
try:  # cp874-safe UTF-8 stdout/stderr (idempotent)
    import sys as _sys; _sys.stdout.reconfigure(encoding="utf-8", errors="replace"); _sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOG = os.path.join(ROOT, 'automation-log')
INBOX = os.path.join(LOG, 'cc-inbox')
OUTBOX = os.path.join(LOG, 'cc-outbox')
ARCH = os.path.join(LOG, 'cc-archive')
COWORK_IN = os.path.join(LOG, 'cowork-inbox')


def _ls(d, pat='*.md'):
    return sorted(glob.glob(os.path.join(d, pat)))


def _age_min(path):
    try:
        return round((datetime.datetime.now().timestamp() - os.path.getmtime(path)) / 60, 1)
    except Exception:
        return -1


def _flags(text):
    """ดึงบรรทัดใต้หัวข้อ 'ธงต้องขออนุมัติ' (สิ่งที่ CC อยากแก้ของจริง รอ owner)."""
    out = []
    m = re.search(r'ธง.*?อนุมัติ', text)
    if m:
        tail = text[m.end():]
        for ln in tail.splitlines():
            s = ln.strip(' -*\t')
            if s.startswith('#'):
                break
            if s:
                out.append(s[:140])
            if len(out) >= 6:
                break
    return out


def main():
    pending = _ls(INBOX, 'order-*.md')
    results = _ls(OUTBOX)
    done = _ls(ARCH, 'order-*.md')

    ts = datetime.datetime.now().strftime('%Y%m%d-%H%M%S')
    os.makedirs(COWORK_IN, exist_ok=True)
    p = os.path.join(COWORK_IN, 'cc-status-' + ts + '.md')

    # สถานะวงจร
    if pending and not results:
        state = '⏳ รอ Claude Code execute (' + str(len(pending)) + ' ออเดอร์ค้าง)'
    elif results:
        state = '📥 มีผล CC ' + str(len(results)) + ' รอ Cowork review/consume'
    else:
        state = '✅ ว่าง — ไม่มีออเดอร์ค้าง/ผลรอ'

    lines = ['# CC STATUS (monitor → Cowork) — ' + ts, '', '**สถานะวงจร:** ' + state, '']
    lines.append('| ช่อง | จำนวน | ล่าสุด(นาที) |')
    lines.append('|---|---|---|')
    lines.append('| cc-inbox (รอ CC) | ' + str(len(pending)) + ' | ' +
                 (str(_age_min(pending[-1])) if pending else '-') + ' |')
    lines.append('| cc-outbox (รอ Cowork) | ' + str(len(results)) + ' | ' +
                 (str(_age_min(results[-1])) if results else '-') + ' |')
    lines.append('| cc-archive (เสร็จ) | ' + str(len(done)) + ' | - |')
    lines.append('')

    if pending:
        lines.append('## ออเดอร์ค้างใน cc-inbox')
        for f in pending:
            lines.append('- ' + os.path.basename(f) + '  (อายุ ' + str(_age_min(f)) + ' นาที)')
        lines.append('')

    flagged = []
    if results:
        lines.append('## ผลที่ CC ทำเสร็จ (รอ Cowork)')
        for f in results:
            txt = open(f, encoding='utf-8', errors='ignore').read()
            fl = _flags(txt)
            flagged += fl
            lines.append('- ' + os.path.basename(f) + (' · 🚩 ธงรออนุมัติ ' + str(len(fl)) if fl else ''))
        lines.append('')
    if flagged:
        lines.append('## 🚩 ธงรอ Cowork/Owner ตัดสิน')
        for x in flagged[:10]:
            lines.append('- ' + x)
        lines.append('')

    lines.append('> ขั้นต่อไป: ' + (
        'เปิด Claude Code เคลียร์ cc-inbox' if (pending and not results)
        else 'รัน report_to_cowork.py / cc_review.py เพื่อรีวิวลึกแล้วสั่งรอบใหม่' if results
        else 'พร้อมรับงานใหม่ (art_to_stitch / cc_bridge.send)'))

    open(p, 'w', encoding='utf-8').write('\n'.join(lines) + '\n')

    try:
        import cc_bridge
        cc_bridge.ping('CC monitor: ' + state + ' -> cowork-inbox/cc-status-' + ts + '.md' +
                       (' · 🚩 ธงรออนุมัติ ' + str(len(flagged)) if flagged else ''))
    except Exception as e:
        print('ping skip:', str(e)[:60])
    print('CC STATUS ->', p, '|', state)
    return p


if __name__ == '__main__':
    main()
