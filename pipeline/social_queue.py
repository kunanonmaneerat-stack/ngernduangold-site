"""social_queue.py — 6 agent รับคิว draft รายแพลตฟอร์ม (router).

อ่าน creative-brief ล่าสุด (จาก head_creative) -> แยกแต่ละแพลตฟอร์ม
-> social-queue/<platform>/(ready|flagged)-<ts>.md  (ไม่โพสต์ แค่จัดคิวรายแพลตฟอร์ม)
ใช้:  py pipeline/social_queue.py
"""
import os, sys, glob, datetime, re
try:  # cp874-safe: UTF-8 stdout/stderr so Thai/emoji prints never crash on Windows console (idempotent)
    import sys as _sys; _sys.stdout.reconfigure(encoding="utf-8", errors="replace"); _sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import platform_agents

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOG = os.path.join(ROOT, 'automation-log')
SQ = os.path.join(LOG, 'social-queue')
NAME2KEY = {v[0]: k for k, v in platform_agents.PLATFORMS.items()}


def latest_brief():
    fs = sorted(glob.glob(os.path.join(LOG, 'creative-brief-*.md')))
    return fs[-1] if fs else None


def route(path):
    ts = datetime.datetime.now().strftime('%Y%m%d-%H%M%S')
    text = open(path, encoding='utf-8').read()
    n = 0
    for chunk in re.split(r'\n## ', text)[1:]:
        head = chunk.split('\n', 1)[0]
        name = head.split('  —')[0].strip()
        key = NAME2KEY.get(name)
        if not key:
            continue
        ok = 'PASS' in head
        body = chunk.split('\n', 1)[1] if '\n' in chunk else ''
        body = body.split('\n---', 1)[0].strip()
        d = os.path.join(SQ, key)
        os.makedirs(d, exist_ok=True)
        status = 'ready' if ok else 'flagged'
        with open(os.path.join(d, status + '-' + ts + '.md'), 'w', encoding='utf-8') as f:
            f.write('# ' + name + ' draft (' + status + ')\n\n' + body + '\n')
        n += 1
    return n, ts


def main():
    b = latest_brief()
    if not b:
        print('no creative-brief found (รัน head_creative.py ก่อน)'); return
    n, ts = route(b)
    print('routed', n, 'platform drafts ->', SQ, '(' + ts + ')')


if __name__ == '__main__':
    main()
