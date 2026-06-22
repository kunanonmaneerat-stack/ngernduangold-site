# -*- coding: utf-8 -*-
"""stylist.py — agent Stylist: เปิดดู preview -> ปรับให้ถูกต้อง+ถูกจริต -> ส่ง Claude Code.

flow (ต่อจาก art_to_stitch -> Stitch -> preview):
  1) อ่าน preview-home.html ล่าสุด (หรือ path ที่ส่งมา)
  2) ตรวจ 'ถูกต้อง' (deterministic): viewport, lang, ฟอนต์แบรนด์, โทนทอง, comply (ช่วง/ธปท./affiliate),
     ไม่มีชื่อแบงก์ใน hero, มือถือ (@media), การ์ดมน, sticky header, ฟอนต์ไม่เล็กเกิน
  3) ปรับ 'ถูกจริต+a11y' (safe auto-fix ที่ไม่เปลี่ยนลุค): theme-color, focus-visible,
     prefers-reduced-motion, ปุ่ม/ลิงก์มี aria where ว่าง -> เขียน *.styled.html
  4) เขียน stylist-report.md + ส่ง work order ให้ Claude Code (cc_bridge.send) ให้ apply+fold เข้า build_site.py
  -> cc_monitor / cc_review รายงานกลับ Cowork (มีอยู่แล้ว ไม่สร้างซ้ำ)
ใช้:  py pipeline/stylist.py  [path/to/preview.html]
"""
import os, sys, re, glob, datetime
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ARTDIR = os.path.join(ROOT, 'automation-log', 'art-direction')
BANKS = ['กรุงศรี', 'krungsri', 'kept', 'ktc', 'scb', 'กสิกร', 'kbank', 'ttb', 'ศรีสวัสดิ์', 'citibank', 'uob']


def _latest_preview():
    fs = sorted(glob.glob(os.path.join(ARTDIR, '*', 'preview-home*.html')))
    return fs[-1] if fs else ''


def review(html):
    """deterministic checks -> (passes, findings[])"""
    low = html.lower()
    hero = ''
    m = re.search(r'class="hero".*?</section>', html, re.S)
    if m:
        hero = m.group(0)
    chk = []
    def ck(ok, label, fix=''):
        chk.append((ok, label, fix))
    ck('name="viewport"' in low, 'มี viewport meta (มือถือ)', 'เพิ่ม <meta name=viewport ...>')
    ck('lang="th"' in low, 'ตั้ง lang=th', 'เพิ่ม lang="th" ที่ <html>')
    ck('noto serif thai' in low and 'ibm plex sans thai' in low, 'ฟอนต์แบรนด์ครบ (Noto Serif Thai+IBM Plex Sans Thai)', 'ใช้ฟอนต์แบรนด์เดิม')
    ck(('#c5a880' in low) or ('#e0b23c' in low) or ('--gold' in low), 'โทนทองแบรนด์', 'ใช้ token ทอง --gold')
    ck(('@media' in low), 'มี breakpoint มือถือ', 'เพิ่ม @media สำหรับมือถือ')
    ck(('position:sticky' in low or 'position: sticky' in low), 'header sticky', 'ทำ header sticky')
    ck(('border-radius' in low), 'การ์ดมน (rounded)', 'ใส่ border-radius การ์ด')
    ck(('ช่วง' in html or 'ไม่การันตี' in html), 'comply: ช่วง/ไม่การันตี', 'เพิ่มถ้อยคำ ช่วง/ไม่การันตี')
    ck(('ธปท' in html), 'comply: โน้ต ธปท.', 'เพิ่มโน้ต ธปท. Responsible Lending')
    ck(('affiliate' in low or 'พันธมิตร' in html), 'มี affiliate disclosure', 'เพิ่มประโยค disclosure ลิงก์พันธมิตร')
    ck(('เช็กสิทธิ์' in html), 'CTA "เช็กสิทธิ์" (DM)', 'เพิ่ม CTA คอมเมนต์/DM เช็กสิทธิ์')
    bank_in_hero = [b for b in BANKS if b in hero.lower()]
    ck(not bank_in_hero, 'ไม่มีชื่อแบงก์ใน hero', 'เอาชื่อแบงก์ออกจาก hero: ' + ', '.join(bank_in_hero))
    tiny = re.findall(r'font-size:\s*(\d+(?:\.\d+)?)px', low)
    smallest = min([float(x) for x in tiny], default=99)
    ck(smallest >= 12, 'ฟอนต์ไม่เล็กเกิน (>=12px)', 'ฟอนต์เล็กสุด ' + str(smallest) + 'px ควร >=12')
    passes = sum(1 for ok, _, _ in chk if ok)
    return passes, chk


SAFE_POLISH = """
<!-- stylist a11y+taste polish (additive, ไม่เปลี่ยนลุค) -->
<meta name="theme-color" content="#0f0f12">
<style>
:focus-visible{outline:2px solid var(--gold-deep,#e0b23c);outline-offset:2px;border-radius:8px}
@media (prefers-reduced-motion:reduce){*{transition:none!important;scroll-behavior:auto!important}}
a,button{-webkit-tap-highlight-color:transparent}
.cat,.art{will-change:transform}
</style>
"""


def polish(html):
    if 'stylist a11y+taste polish' in html:
        return html, False
    if '</head>' in html:
        return html.replace('</head>', SAFE_POLISH + '</head>', 1), True
    return html, False


def main():
    src = sys.argv[1] if len(sys.argv) > 1 else _latest_preview()
    if not src or not os.path.exists(src):
        print('no preview found'); return
    html = open(src, encoding='utf-8', errors='ignore').read()
    passes, chk = review(html)
    styled, changed = polish(html)
    out_html = src.replace('.html', '.styled.html')
    open(out_html, 'w', encoding='utf-8').write(styled)

    ts = datetime.datetime.now().strftime('%Y%m%d-%H%M%S')
    d = os.path.dirname(src)
    rep = os.path.join(d, 'stylist-report-' + ts + '.md')
    fails = [(label, fix) for ok, label, fix in chk if not ok]
    with open(rep, 'w', encoding='utf-8') as f:
        f.write('# STYLIST REPORT — ' + ts + '\n\n')
        f.write('ตรวจ preview: ' + os.path.basename(src) + ' · ผ่าน ' + str(passes) + '/' + str(len(chk)) + '\n\n')
        f.write('## เช็กลิสต์ ถูกต้อง+ถูกจริต\n')
        for ok, label, fix in chk:
            f.write(('- ✅ ' if ok else '- ⚠️ ') + label + (('  → ' + fix) if (not ok and fix) else '') + '\n')
        f.write('\n## ปรับให้ (safe auto-fix, ไม่เปลี่ยนลุค)\n')
        f.write('- a11y: focus-visible outline, prefers-reduced-motion, theme-color, tap-highlight\n')
        f.write('- ไฟล์: ' + os.path.basename(out_html) + (' (เพิ่ม polish แล้ว)' if changed else ' (มี polish อยู่แล้ว)') + '\n')
        # free_llm taste enrichment (optional)
        try:
            import free_llm
            t, mdl = free_llm.generate(
                'คุณเป็น senior stylist เว็บการเงินไทย โทนทอง-บนเข้ม. ดู checklist ที่ตกแล้วเสนอ 3 ปรับ '
                '"ให้ถูกจริต" (จังหวะ spacing, ความเรียบหรู, gold ใช้พอดี) สั้นๆ ทำได้จริงด้วย CSS:\n' +
                '; '.join(l for l, _ in fails) or 'ทุกข้อผ่าน',
                max_tokens=400, temperature=0.4)
            if t and t.strip():
                f.write('\n## ข้อเสนอ stylist (AI ' + str(mdl) + ')\n' + t.strip() + '\n')
        except Exception as e:
            f.write('\n> (free_llm ข้าม: ' + str(e)[:40] + ')\n')

    # ส่งงานให้ Claude Code
    body = ('# WORK ORDER -> Claude Code: apply stylist polish + fold เข้า build_site.py ' + ts + '\n\n'
            '> จาก stylist agent · สโคป: presentation เท่านั้น · ❌ ไม่ commit/deploy เอง รอ owner OK\n\n'
            '## สิ่งที่ต้องทำ\n'
            '1. ใช้ styled preview เป็นต้นแบบ: ' + os.path.basename(out_html) + '\n'
            '2. fold hero+หมวดหน้าแรกเข้า template ใน build_site.py — คงเป๊ะ: GA_SNIPPET, affiliate class (hubbtn/cta/go + rel=sponsored + data-provider + utm()), canonical/OG/sitemap, /quiz\n'
            '3. แก้ checklist ที่ยังตก (ถ้ามี):\n')
    for label, fix in fails:
        body += '   - ' + label + ' → ' + fix + '\n'
    if not fails:
        body += '   - (ผ่านทุกข้อ — โฟกัส fold + รักษา tracking/SEO)\n'
    body += ('4. รัน build_site.py local → verify GA4 affiliate_click ยิง + ทุกหน้ามี canonical/OG → owner deploy\n\n'
             '## ผล -> cc-outbox/result-<ts>.md (+ ## ธงต้องขออนุมัติ)\n')
    try:
        import cc_bridge
        p = cc_bridge.send('stylist: apply polish + fold homepage', body)
        print('order ->', os.path.basename(p))
    except Exception as e:
        # fallback: เขียน order ตรงๆ ถ้า ping ใช้ไม่ได้ (sandbox)
        inbox = os.path.join(ROOT, 'automation-log', 'cc-inbox')
        os.makedirs(inbox, exist_ok=True)
        p = os.path.join(inbox, 'order-stylist-' + ts + '.md')
        open(p, 'w', encoding='utf-8').write(body)
        print('order (direct) ->', os.path.basename(p), '| ping skip:', str(e)[:40])
    print('STYLIST: pass', passes, '/', len(chk), '| report ->', rep, '| styled ->', out_html)
    return rep


if __name__ == '__main__':
    main()
