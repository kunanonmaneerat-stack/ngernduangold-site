"""cc_runner.py — ตัว execute สำรอง (เมื่อ Claude Code ไม่ว่าง).

อ่านออเดอร์เก่าสุดใน cc-inbox -> ใช้ free_llm ทำคอนเทนต์หลายแพลตฟอร์ม -> เขียนผล cc-outbox
-> ย้ายออเดอร์เข้า cc-archive. (Claude Code = ตัวหลัก; ตัวนี้กันลูปค้างเมื่อ CC ไม่ว่าง)
สโคปปลอดภัย: ทำ draft เท่านั้น ไม่โพสต์/commit/deploy.
"""
import os, sys, glob, shutil
try:  # cp874-safe: UTF-8 stdout/stderr so Thai/emoji prints never crash on Windows console (idempotent)
    import sys as _sys; _sys.stdout.reconfigure(encoding="utf-8", errors="replace"); _sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import free_llm
import comply_gate

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
LOG = os.path.join(ROOT, 'automation-log')
INBOX = os.path.join(LOG, 'cc-inbox')
OUTBOX = os.path.join(LOG, 'cc-outbox')
ARCH = os.path.join(LOG, 'cc-archive')
SYS = "คุณคือ executor ทำคอนเทนต์โซเชียลการเงินไทย value-first คปภ-safe ไม่มีลิงก์ในโพสต์ ไม่ขายตรง"


def main():
    orders = sorted(glob.glob(os.path.join(INBOX, 'order-*.md')))
    if not orders:
        print('no order in cc-inbox'); return
    order = orders[0]
    ts = os.path.basename(order)[6:-3]
    body = open(order, encoding='utf-8').read()
    txt, m = free_llm.generate(
        'ทำตามออเดอร์นี้: ต่อแต่ละเคสให้ Threads(hook+ชวน DM) / Facebook(value 3-5 บรรทัด) / '
        'TikTok(สคริปต์ ≤20 วิ) + 1 ข้อปรับปรุงฟันเนล. [กฎบังคับ] ' + comply_gate.RULE + ':\n\n' + body,
        system=SYS, max_tokens=1800)
    txt2, ok, issues = comply_gate.gate(txt or '')
    stamp = '✅ compliance PASS' if ok else '⚠️ ยังติด: ' + '; '.join(issues)
    os.makedirs(OUTBOX, exist_ok=True); os.makedirs(ARCH, exist_ok=True)
    out = os.path.join(OUTBOX, 'result-' + ts + '.md')
    with open(out, 'w', encoding='utf-8') as f:
        f.write('# CC RESULT ' + ts + ' (auto-exec: ' + str(m) + ' · ' + stamp + ')\n\n' + (txt2 or 'EMPTY'))
    shutil.move(order, os.path.join(ARCH, os.path.basename(order)))
    print('executed by', m, '| comply:', 'PASS' if ok else 'FIXED', issues, '->', out)


if __name__ == '__main__':
    main()
