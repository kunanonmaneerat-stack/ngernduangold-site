"""head_social_review.py — Head of Social Review.

รวมผล review รายแพลตฟอร์ม (social-review/<platform>/) -> ตารางสรุป
-> head-social-review-<ts>.md -> ping Cowork ให้คุมต่อ (เลือกตัว READY ไปโพสต์ · FIX ส่งกลับ).
ใช้:  py pipeline/head_social_review.py
"""
import os, sys, glob, datetime
try:  # cp874-safe: UTF-8 stdout/stderr so Thai/emoji prints never crash on Windows console (idempotent)
    import sys as _sys; _sys.stdout.reconfigure(encoding="utf-8", errors="replace"); _sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import platform_agents, cc_bridge

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOG = os.path.join(ROOT, 'automation-log')
SR = os.path.join(LOG, 'social-review')


def main():
    ts = datetime.datetime.now().strftime('%Y%m%d-%H%M%S')
    rows, ready = [], 0
    for key in platform_agents.PLATFORMS:
        fs = sorted(glob.glob(os.path.join(SR, key, 'review-*.md')))
        if not fs:
            rows.append((key, 'ไม่มี draft')); continue
        head = open(fs[-1], encoding='utf-8').read().split('\n', 1)[0]
        v = head.split('—', 1)[-1].strip() if '—' in head else '?'
        if v == 'READY':
            ready += 1
        rows.append((key, v))
    p = os.path.join(LOG, 'head-social-review-' + ts + '.md')
    with open(p, 'w', encoding='utf-8') as f:
        f.write('# HEAD OF SOCIAL REVIEW — ' + ts + '\n\n')
        f.write('> Cowork: เลือกตัว READY ไปเตรียมโพสต์ (post_prepare) · ตัว FIX ส่งกลับ platform_agents ปรับ\n\n')
        f.write('| แพลตฟอร์ม | สถานะ |\n|---|---|\n')
        for k, v in rows:
            f.write('| ' + k + ' | ' + v + ' |\n')
    cc_bridge.ping('Head of Social Review: ' + str(ready) + ' READY -> head-social-review-' + ts + '.md (Cowork คุมต่อ)')
    print('head social review ->', p, '| READY', ready)


if __name__ == '__main__':
    main()
