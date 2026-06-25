"""post_prepare.py — เตรียมโพสต์รายแพลตฟอร์ม (พร้อมวาง — คนกด publish เอง).

อ่าน review ที่ READY -> ทำแพ็กพร้อมวาง (เวลาโพสต์แนะนำ + เช็กลิสต์ก่อน publish + เนื้อหา)
-> post-ready/<platform>/post-<ts>.md
** ไม่เชื่อม API โพสต์เอง — การ publish เป็นของคน (กันพลาด + ระเบียบ คปภ./ธปท.) **
ใช้:  py pipeline/post_prepare.py
"""
import os, sys, glob, datetime
try:  # cp874-safe: UTF-8 stdout/stderr so Thai/emoji prints never crash on Windows console (idempotent)
    import sys as _sys; _sys.stdout.reconfigure(encoding="utf-8", errors="replace"); _sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import platform_agents

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOG = os.path.join(ROOT, 'automation-log')
SR = os.path.join(LOG, 'social-review')
PR = os.path.join(LOG, 'post-ready')
BESTTIME = {'pantip': '20:00-22:00', 'fb': '12:00 หรือ 19:00', 'ig': '18:00-20:00',
            'tiktok': '19:00-21:00', 'yt': '18:00-20:00', 'threads': '08:00 หรือ 21:00'}
SCHED = {'pantip': 'โพสต์มือ (ฟอรัมไม่มีตัวจัดตาราง)',
         'fb': 'Meta Business Suite — ฟรี ตั้งล่วงหน้า 75 วัน',
         'ig': 'Meta Business Suite — ฟรี (ต้องบัญชี Professional)',
         'tiktok': 'TikTok Studio — ฟรี ตั้งล่วงหน้า 10 วัน',
         'yt': 'YouTube Studio — ฟรี',
         'threads': 'โพสต์มือ/แอป Threads (ยังไม่มีตัวจัดตารางฟรีในตัว)'}


def main():
    ts = datetime.datetime.now().strftime('%Y%m%d-%H%M%S')
    n = 0
    for key in platform_agents.PLATFORMS:
        fs = sorted(glob.glob(os.path.join(SR, key, 'review-*.md')))
        if not fs:
            continue
        txt = open(fs[-1], encoding='utf-8').read()
        if 'READY' not in txt.split('\n', 1)[0]:
            continue
        content = txt.split('---\n', 1)[-1]
        d = os.path.join(PR, key); os.makedirs(d, exist_ok=True)
        with open(os.path.join(d, 'post-' + ts + '.md'), 'w', encoding='utf-8') as f:
            f.write('# พร้อมโพสต์ ' + platform_agents.PLATFORMS[key][0] + ' (' + ts + ')\n\n')
            f.write('เวลาโพสต์แนะนำ: ' + BESTTIME.get(key, '-') + '\n')
            f.write('โหลดเข้าตัวจัดตารางฟรี: ' + SCHED.get(key, '-') + '\n\n')
            f.write('## ✅ เช็กก่อนกด publish (คุณทำเอง)\n'
                    '- [ ] เช็กชื่อสถาบัน/ตัวเลขให้ตรงจริง (โมเดลอาจแต่ง)\n'
                    '- [ ] ลิงก์อยู่ DM/bio ไม่ใช่ในโพสต์\n'
                    '- [ ] ถ้าพูดสินเชื่อ มีคำเตือน "กู้เท่าที่จำเป็น"\n\n')
            f.write('## เนื้อหาพร้อมวาง\n' + content)
        n += 1
        print('prepared', key)
    print('post-ready packages:', n, '-> ' + PR + '  (คนกด publish เอง)')


if __name__ == '__main__':
    main()
