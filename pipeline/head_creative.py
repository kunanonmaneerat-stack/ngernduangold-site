"""head_creative.py — Head of Creative (web & social): รวมงาน 5 agent แพลตฟอร์ม -> ส่ง Cowork.

ดึงวัตถุดิบล่าสุดจากคิวสภา -> สั่ง agent ทั้ง 5 แพลตฟอร์ม (FB/IG/TikTok/YT/Threads)
-> รวมเป็น creative brief (มี comply verdict ต่อแพลตฟอร์ม) -> automation-log/creative-brief-<ts>.md
-> ping Cowork ให้วิเคราะห์/คุมต่อ.
ใช้:  py pipeline/head_creative.py
"""
import os, sys, glob, datetime
try:  # cp874-safe: UTF-8 stdout/stderr so Thai/emoji prints never crash on Windows console (idempotent)
    import sys as _sys; _sys.stdout.reconfigure(encoding="utf-8", errors="replace"); _sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import platform_agents, executor, cc_bridge

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOG = os.path.join(ROOT, 'automation-log')


def latest_material():
    fs = sorted(glob.glob(os.path.join(LOG, 'council-*.md')))
    if not fs:
        return ''
    blocks = executor.extract_plan(fs[-1])
    return (blocks[0]['case'] + '\n' + '\n'.join(blocks[0]['answer'])) if blocks else ''


def main():
    material = latest_material()
    if not material:
        print('no material in council queue'); return
    ts = datetime.datetime.now().strftime('%Y%m%d-%H%M%S')
    p = os.path.join(LOG, 'creative-brief-' + ts + '.md')
    passes = 0
    with open(p, 'w', encoding='utf-8') as f:
        f.write('# CREATIVE BRIEF (head: web & social) — ' + ts + '\n\n')
        f.write('> วัตถุดิบ: ' + material.splitlines()[0] + '\n')
        f.write('> Cowork: เลือกตัวที่จะดันจริง + สั่งรอบถัดไป\n\n')
        for key in platform_agents.PLATFORMS:
            r = platform_agents.run(key, material)
            passes += 1 if r['ok'] else 0
            v = '✅ PASS' if r['ok'] else '⚠️ ' + '; '.join(r['issues'])
            f.write('## ' + r['platform'] + '  — ' + v + '  (' + str(r['model']) + ')\n\n')
            f.write((r['content'] or '').strip() + '\n\n---\n\n')
    if "\ufffd" in open(p, encoding="utf-8").read():
        import sys as _s; _s.stderr.write("[head_creative] WARN U+FFFD in " + p + "\n")
    cc_bridge.ping('Head creative: brief 5 แพลตฟอร์มพร้อม (' + str(passes) + '/5 PASS) -> creative-brief-' + ts + '.md')
    print('creative brief ->', p, '| pass', passes, '/', len(platform_agents.PLATFORMS))


if __name__ == '__main__':
    main()
