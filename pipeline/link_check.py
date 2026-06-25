"""link_check.py — agent ตรวจลิงก์หน้าเว็บ + ส่ง fix ให้ Claude Code.

สแกน site/**/* -> เช็กลิงก์ "ไฟล์" ว่าปลายทางมีจริง · แยก route extensionless (เช่น /quiz) เป็น "ตรวจ live"
-> รายงาน linkcheck-<date>.md · ถ้ามีลิงก์ไฟล์เสียจริง เขียน work order ให้ CC. อ่านอย่างเดียว ไม่แก้/deploy.
ใช้:  py pipeline/link_check.py
"""
import os, re, sys, glob, datetime
try:  # cp874-safe: UTF-8 stdout/stderr so Thai/emoji prints never crash on Windows console (idempotent)
    import sys as _sys; _sys.stdout.reconfigure(encoding="utf-8", errors="replace"); _sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import cc_bridge

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SITE = os.path.join(ROOT, 'site')
LOG = os.path.join(ROOT, 'automation-log')
HREF = re.compile(r'(?:href|src)\s*=\s*["\']([^"\']+)["\']', re.I)
EXTS = ('.html', '.htm', '.css', '.js', '.png', '.jpg', '.jpeg', '.webp', '.svg',
        '.ico', '.gif', '.json', '.xml', '.txt', '.pdf', '.woff', '.woff2')


def _valid_set():
    s = set()
    for f in glob.glob(os.path.join(SITE, '**', '*'), recursive=True):
        if os.path.isfile(f):
            rel = os.path.relpath(f, SITE).replace('\\', '/')
            s.add(rel); s.add(os.path.basename(rel))
    return s


def scan():
    files = glob.glob(os.path.join(SITE, '*.html'))
    valid = _valid_set()
    broken, routes, external = [], {}, {}
    for f in files:
        base = os.path.basename(f)
        html = open(f, encoding='utf-8', errors='ignore').read()
        for link in HREF.findall(html):
            l = link.strip()
            if not l or l[0] == '#' or l.startswith(('mailto:', 'tel:', 'data:', 'javascript:')):
                continue
            if l.startswith(('http://', 'https://', '//')):
                k = l.split('?')[0]; external[k] = external.get(k, 0) + 1; continue
            t = l.split('?')[0].split('#')[0].lstrip('/')
            if not t:
                continue
            if t.lower().endswith(EXTS):
                if not (t in valid or os.path.basename(t) in valid):
                    broken.append((base, l))
            else:
                if not ((t + '.html') in valid or (t + '/index.html') in valid or os.path.basename(t) in valid):
                    routes.setdefault('/' + t, set()).add(base)
    return files, broken, routes, external


def main():
    files, broken, routes, external = scan()
    d = datetime.date.today().isoformat()
    rep = os.path.join(LOG, 'linkcheck-' + d + '.md')
    with open(rep, 'w', encoding='utf-8') as f:
        f.write('# LINK CHECK — ' + d + '\n\n')
        f.write('สแกน ' + str(len(files)) + ' หน้า · ไฟล์ลิงก์เสียจริง ' + str(len(broken)) +
                ' · route ต้องตรวจ live ' + str(len(routes)) + ' · ลิงก์นอก ' + str(len(external)) + '\n\n')
        if broken:
            f.write('## ⚠️ ลิงก์ไฟล์เสียจริง (ปลายทางไม่พบ — ส่ง CC แก้)\n')
            for s, l in broken:
                f.write('- `' + s + '` -> `' + l + '`\n')
            f.write('\n')
        if routes:
            f.write('## 🔎 route ต้องยืนยันว่า resolve บน live (เช่น /quiz=ฟันเนล, /links=ฮับลิงก์)\n')
            f.write('_ไม่ใช่ลิงก์เสียในไฟล์ — ขึ้นกับ build_site.py/Netlify ว่าออก route นี้ไหม ไม่ส่ง CC อัตโนมัติ_\n')
            for r, srcs in sorted(routes.items()):
                f.write('- `' + r + '`  (อ้างจาก ' + str(len(srcs)) + ' หน้า)\n')
            f.write('\n')
        f.write('## ลิงก์ภายนอก (เช็ก affiliate up-to-date)\n')
        for l, n in sorted(external.items(), key=lambda x: -x[1])[:40]:
            f.write('- (' + str(n) + ') ' + l + '\n')
    print('linkcheck ->', rep, '| pages', len(files), '| broken_files', len(broken),
          '| routes', len(routes), '| external', len(external))
    if broken:
        body = ('# WORK ORDER -> Claude Code: แก้ลิงก์ไฟล์เสีย (' + d + ')\n\n'
                '> สโคป: แก้เฉพาะลิงก์ไฟล์ที่ปลายทางไม่พบใน site/ · ห้าม commit/deploy เอง รอ owner OK\n\n')
        for s, l in broken:
            body += '- ไฟล์ `' + s + '`: ลิงก์ `' + l + '` ปลายทางไม่พบ\n'
        cc_bridge.send('แก้ลิงก์ไฟล์เสีย ' + str(len(broken)) + ' จุด', body)
    return rep


if __name__ == '__main__':
    main()
