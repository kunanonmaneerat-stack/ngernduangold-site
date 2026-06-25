# -*- coding: utf-8 -*-
"""art_to_stitch.py — Head of Art & Graphic -> Cowork -> Google Stitch.

อ่านเว็บปัจจุบัน -> ออก 3 อย่าง:
  1) art-direction brief (ไทย) — ทิศทางศิลป์ที่จะยกระดับ
  2) Google Stitch prompt (อังกฤษ พร้อมวางที่ stitch.withgoogle.com)
  3) cc-routing — งานที่ "Claude Code ทำดีกว่า" (implement โค้ด) แยกชัด
เขียนที่ automation-log/art-direction/<ts>/ แล้ว ping Cowork.

flow:  art_to_stitch (ตัวนี้) -> Cowork เอา stitch-prompt ไปเจนที่ Stitch
       -> ผลดีไซน์ -> cc_bridge.send ให้ Claude Code implement
       -> cc_monitor / cc_review -> กลับมา Cowork วิเคราะห์ต่อ
ใช้:  py pipeline/art_to_stitch.py
"""
import os, sys, re, glob, datetime
try:  # cp874-safe UTF-8 stdout/stderr (idempotent)
    import sys as _sys; _sys.stdout.reconfigure(encoding="utf-8", errors="replace"); _sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SITE = os.path.join(ROOT, 'site')
OUTDIR = os.path.join(ROOT, 'automation-log', 'art-direction')

BRAND = 'เงินเดือนสมองทอง'
TAGLINE = 'การเงินมนุษย์เงินเดือน · บัตรเครดิต ออมเงิน ลงทุน ย่อยง่าย'
EN_BRAND = 'Ngern Duan Gold (Golden Salary Brain) — Thai personal-finance guide'

# โทนแบรนด์ปัจจุบัน (ดึงจาก site จริง): ทอง/ครีม พรีเมียมบนพื้นเข้ม + slate
PALETTE_HINT = ('gold #C5A880 / #D8C29A / #c79a32 / #e0b23c, cream #f3ecd9 / #faf7ef, '
                'ink #0f0f12 / #1a1a1f / #1c1c24, slate #0F172A / #1E293B / #64748B / #F8FAFC')


def _snapshot():
    pages = sorted(glob.glob(os.path.join(SITE, '*.html')))
    idx = os.path.join(SITE, 'index.html')
    html = open(idx, encoding='utf-8', errors='ignore').read() if os.path.exists(idx) else ''
    cols = sorted(set(re.findall(r'#[0-9a-fA-F]{6}', html)))
    secs = re.findall(r'<h2[^>]*>(.*?)</h2>', html, re.S)[:8]
    secs = [re.sub(r'<[^>]+>', '', s).strip()[:40] for s in secs]
    return {'npages': len(pages), 'colors': cols[:14], 'sections': [s for s in secs if s]}


def stitch_prompt(snap):
    """English prompt พร้อมวางใน Google Stitch (ทำงานดีสุดเป็นอังกฤษ)."""
    return f"""Design a modern, trustworthy HOMEPAGE for a Thai personal-finance content & affiliate website.

BRAND: "{BRAND}" ({EN_BRAND}). Tagline (Thai): "{TAGLINE}".
AUDIENCE: Thai salaried workers (20-40) on mobile, comparing credit cards, savings, loans, insurance. They want clarity and trust, not hype.

ART DIRECTION: premium but friendly fintech. Keep the brand's signature GOLD-on-DARK identity but make it cleaner, lighter on the eyes, and faster-feeling. Palette: {PALETTE_HINT}. Use gold as accent (CTAs, highlights, icons) — not as large fills. Generous whitespace, soft rounded cards (16-20px radius), subtle depth/shadows, one clear accent per section. Mobile-first, fast, accessible (AA contrast). Thai-language UI text, large readable Thai type, clear visual hierarchy.

PAGE SECTIONS (top to bottom):
1. Sticky slim header: logo "เงินเดือนสมองทอง", nav (บัตรเครดิต · ออมเงิน · สินเชื่อ · ประกัน · บทความ), search icon.
2. Hero: bold headline value prop + 1-line subhead, a prominent search/compare bar, and a trust line ("ข้อมูลย่อยง่าย เทียบก่อนตัดสินใจ"). Calm gold gradient accent, not loud.
3. Category cards (4): บัตรเครดิต / ออมเงิน / สินเชื่อ / ประกัน — each an icon, short label, 1-line benefit. Tap-friendly.
4. Featured articles (3-4 cards): thumbnail, Thai title, 2-line teaser, reading time.
5. "ทำไมต้องเชื่อเรา" trust strip: 3 mini points (เป็นกลาง · เทียบเงื่อนไขล่าสุด · ไม่ขายตรง) + ธปท. Responsible-Lending note.
6. Soft CTA band: "คอมเมนต์/ทัก DM 'เช็กสิทธิ์' รับตัวเทียบฟรี" with a friendly button (link goes to DM/bio, not inline).
7. Footer: about, disclaimer, affiliate-disclosure line, sitemap links.

CONSTRAINTS: responsive (mobile + desktop), light-and-dark friendly, no stock-photo clutter, finance-compliant tone (ranges not guarantees, no specific bank/product names in hero). Output clean semantic HTML + CSS that a developer can drop into a static site.

Generate the homepage now, then I will iterate on the category cards and hero."""


def brief(snap):
    """art-direction brief ไทย (พยายามใช้ free_llm, มี fallback template)."""
    base = (f"# ART-DIRECTION BRIEF — Head of Art & Graphic\n\n"
            f"แบรนด์: {BRAND} · {TAGLINE}\n"
            f"เว็บปัจจุบัน: {snap['npages']} หน้า · โทนสีหลัก: {', '.join(snap['colors'][:8])}\n"
            f"เซกชันหน้าแรกที่เจอ: {', '.join(snap['sections']) or '-'}\n\n"
            "## ทิศทางยกระดับ (จากของเดิม → เป้าหมาย)\n"
            "1. คงเอกลักษณ์ทอง-บน-เข้ม แต่ทำให้ 'สะอาด+โปร่ง+เร็วขึ้น' — ทองเป็น accent ไม่ใช่พื้นใหญ่\n"
            "2. ลำดับชั้นชัด: hero มี value prop + แถบค้นหา/เทียบ + บรรทัดสร้างความเชื่อใจ\n"
            "3. การ์ดหมวด 4 อัน (บัตร/ออม/สินเชื่อ/ประกัน) ปุ่มแตะง่ายบนมือถือ\n"
            "4. แถบความน่าเชื่อถือ: เป็นกลาง · เทียบเงื่อนไขล่าสุด · ไม่ขายตรง + โน้ต ธปท.\n"
            "5. CTA นุ่ม: คอมเมนต์/DM 'เช็กสิทธิ์' (ลิงก์ไป DM/bio ไม่ใส่ในเนื้อ)\n"
            "6. มือถือมาก่อน · คอนทราสต์ AA · Thai type อ่านง่าย · โหลดเร็ว\n")
    try:
        import free_llm
        ctx = (f"เว็บการเงินไทย {BRAND}. โทนปัจจุบัน: ทอง/ครีมบนพื้นเข้ม. หน้า {snap['npages']}. "
               f"สี: {', '.join(snap['colors'][:8])}. ช่วยเสนอ 5 มูฟยกระดับดีไซน์ให้ 'สวย น่าเชื่อถือ "
               "มีชีวิตชีวา โหลดเร็ว มือถือ' ทำได้จริงด้วย HTML/CSS ระบุจุดที่แก้:")
        t, m = free_llm.generate(ctx, max_tokens=700, temperature=0.5)
        if t and t.strip():
            base += f"\n## ข้อเสนอเสริมจาก AI ({m})\n{t.strip()}\n"
    except Exception as e:
        base += f"\n> (free_llm ข้าม: {str(e)[:50]})\n"
    return base


CC_ROUTING = """# ROUTING — งานที่ Claude Code ทำได้ดีกว่า (ส่งผ่าน cc_bridge.send)

> เกณฑ์: งานแตะโค้ด/หลายไฟล์/ต้องคงพฤติกรรมเดิม (GA4, affiliate tracking, SEO, speed) = CC ทำดีกว่า Cowork

- [CC] แปลงดีไซน์จาก Google Stitch -> โค้ดจริงใน build_site.py (template homepage) คงโครงสร้าง GA4/affiliate/utm
- [CC] ทำ component การ์ดหมวด + hero + trust strip ให้ responsive + AA contrast
- [CC] รักษา performance (inline critical CSS, ไม่เพิ่ม JS หนัก, รูป lazy)
- [CC] regression: ทุกหน้ายังมี canonical/OG/sitemap/quiz เดิม
- [Cowork] ตัดสินใจดีไซน์ไหนเอา, คุม Stitch, อนุมัติก่อน deploy
- [Owner] กด deploy จริง (CC ห้าม commit/push/deploy เอง)
"""


def main():
    snap = _snapshot()
    ts = datetime.datetime.now().strftime('%Y%m%d-%H%M%S')
    d = os.path.join(OUTDIR, ts)
    os.makedirs(d, exist_ok=True)
    p_brief = os.path.join(d, 'brief.md')
    p_stitch = os.path.join(d, 'stitch-prompt.txt')
    p_route = os.path.join(d, 'cc-routing.md')
    open(p_brief, 'w', encoding='utf-8').write(brief(snap))
    open(p_stitch, 'w', encoding='utf-8').write(stitch_prompt(snap))
    open(p_route, 'w', encoding='utf-8').write(CC_ROUTING)
    # ping Cowork (ผ่าน cc_bridge ใช้ Hermes เดิม)
    try:
        import cc_bridge
        cc_bridge.ping('Head of Art&Graphic: บรีฟ+Stitch prompt พร้อม -> automation-log/art-direction/' + ts +
                       '/ (Cowork: เอา stitch-prompt.txt ไปเจนที่ stitch.withgoogle.com)')
    except Exception as e:
        print('ping skip:', str(e)[:60])
    print('ART-DIRECTION ->', d)
    print(' brief :', p_brief)
    print(' stitch:', p_stitch)
    print(' route :', p_route)
    return d


if __name__ == '__main__':
    main()
