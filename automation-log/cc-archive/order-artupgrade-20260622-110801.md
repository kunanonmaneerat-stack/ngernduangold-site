# WORK ORDER -> Claude Code: ยกระดับหน้าตาเว็บ (homepage redesign) 20260622-110801

> มาจาก: head-of-art agent (art_to_stitch.py) · routing flag = งานนี้ CC ทำดีกว่า Cowork
> สโคป (CC-PROTOCOL): ร่างโค้ดเป็น proposal เขียนที่ cc-outbox + ใส่ 'ธงต้องขออนุมัติ' · ❌ ไม่ commit/deploy เอง

## สิ่งที่ต้องทำ
1. ร่าง homepage ใหม่ของ build_site.py (template index) ตาม ART BRIEF ด้านล่าง — คง GA4/affiliate/utm/canonical/OG เดิม 100%
2. คงโหลดเร็ว+มือถือ: critical CSS inline, ไม่เพิ่ม JS หนัก, รูป lazy, AA contrast
3. ทำเป็น diff/ตัวอย่าง HTML+CSS ใน cc-outbox/result-artupgrade-20260622-110801.md (ยังไม่แตะ site จริงจนเจ้าของ OK)
4. ถ้ามี Google Stitch export (HTML) ทีหลัง -> รอบสองค่อย merge styling เข้า template

## ART BRIEF (จาก head-of-art)
```
# ART-DIRECTION BRIEF — Head of Art & Graphic

แบรนด์: เงินเดือนสมองทอง · การเงินมนุษย์เงินเดือน · บัตรเครดิต ออมเงิน ลงทุน ย่อยง่าย
เว็บปัจจุบัน: 33 หน้า · โทนสีหลัก: #06c755, #0F172A, #1877f2, #1E293B, #1a1a1f, #1f9d55, #3a3a44, #5b5b66
เซกชันหน้าแรกที่เจอ: บทความล่าสุด

## ทิศทางยกระดับ (จากของเดิม → เป้าหมาย)
1. คงเอกลักษณ์ทอง-บน-เข้ม แต่ทำให้ 'สะอาด+โปร่ง+เร็วขึ้น' — ทองเป็น accent ไม่ใช่พื้นใหญ่
2. ลำดับชั้นชัด: hero มี value prop + แถบค้นหา/เทียบ + บรรทัดสร้างความเชื่อใจ
3. การ์ดหมวด 4 อัน (บัตร/ออม/สินเชื่อ/ประกัน) ปุ่มแตะง่ายบนมือถือ
4. แถบความน่าเชื่อถือ: เป็นกลาง · เทียบเงื่อนไขล่าสุด · ไม่ขายตรง + โน้ต ธปท.
5. CTA นุ่ม: คอมเมนต์/DM 'เช็กสิทธิ์' (ลิงก์ไป DM/bio ไม่ใส่ในเนื้อ)
6. มือถือมาก่อน · คอนทราสต์ AA · Thai type อ่านง่าย · โหลดเร็ว
```

## STITCH PROMPT (อ้างอิงดีไซน์เป้าหมาย)
```
Design a modern, trustworthy HOMEPAGE for a Thai personal-finance content & affiliate website.

BRAND: "เงินเดือนสมองทอง" (Ngern Duan Gold (Golden Salary Brain) — Thai personal-finance guide). Tagline (Thai): "การเงินมนุษย์เงินเดือน · บัตรเครดิต ออมเงิน ลงทุน ย่อยง่าย".
AUDIENCE: Thai salaried workers (20-40) on mobile, comparing credit cards, savings, loans, insurance. They want clarity and trust, not hype.

ART DIRECTION: premium but friendly fintech. Keep the brand's signature GOLD-on-DARK identity but make it cleaner, lighter on the eyes, and faster-feeling. Palette: gold #C5A880 / #D8C29A / #c79a32 / #e0b23c, cream #f3ecd9 / #faf7ef, ink #0f0f12 / #1a1a1f / #1c1c24, slate #0F172A / #1E293B / #64748B / #F8FAFC. Use gold as accent (CTAs, highlights, icons) — not as large fills. Generous whitespace, soft rounded cards (16-20px radius), subtle depth/shadows, one clear accent per section. Mobile-first, fast, accessible (AA contrast). Thai-language UI text, large readable Thai type, clear visual hierarchy.

PAGE SECTIONS (top to bottom):
1. Sticky slim header: logo "เงินเดือนสมองทอง", nav (บัตรเครดิต · ออมเงิน · สินเชื่อ · ประกัน · บทความ), search icon.
2. Hero: bold headline value prop + 1-line subhead, a prominent search/compare bar, and a trust line ("ข้อมูลย่อยง่าย เทียบก่อนตัดสินใจ"). Calm gold gradient accent, not loud.
3. Category cards (4): บัตรเครดิต / ออมเงิน / สินเชื่อ / ประกัน — each an icon, short label, 1-line benefit. Tap-friendly.
4. Featured articles (3-4 cards): thumbnail, Thai title, 2-line teaser, reading time.
5. "ทำไมต้องเชื่อเรา" trust strip: 3 mini points (เป็นกลาง · เทียบเงื่อนไขล่าสุด · ไม่ขายตรง) + ธปท. Responsible-Lending note.
6. Soft CTA band: "คอมเมนต์/ทัก DM 'เช็กสิทธิ์' รับตัวเทียบฟรี" with a friendly button (link goes to DM/bio, not inline).
7. Footer: about, disclaimer, affiliate-disclosure line, sitemap links.

CONSTRAINTS: responsive (mobile + desktop), light-and-dark friendly, no stock-photo clutter, finance-compliant tone (ranges not guarantees, no specific bank/product names in hero). Output clean semantic HTML + CSS that a developer can drop into a static site.

Generate the homepage now, then I will iterate on the category cards and hero.```

# ROUTING — งานที่ Claude Code ทำได้ดีกว่า (ส่งผ่าน cc_bridge.send)

> เกณฑ์: งานแตะโค้ด/หลายไฟล์/ต้องคงพฤติกรรมเดิม (GA4, affiliate tracking, SEO, speed) = CC ทำดีกว่า Cowork

- [CC] แปลงดีไซน์จาก Google Stitch -> โค้ดจริงใน build_site.py (template homepage) คงโครงสร้าง GA4/affiliate/utm
- [CC] ทำ component การ์ดหมวด + hero + trust strip ให้ responsive + AA contrast
- [CC] รักษา performance (inline critical CSS, ไม่เพิ่ม JS หนัก, รูป lazy)
- [CC] regression: ทุกหน้ายังมี canonical/OG/sitemap/quiz เดิม
- [Cowork] ตัดสินใจดีไซน์ไหนเอา, คุม Stitch, อนุมัติก่อน deploy
- [Owner] กด deploy จริง (CC ห้าม commit/push/deploy เอง)

## ฟอร์แมตผล (cc-outbox/result-artupgrade-20260622-110801.md)
- สรุปสิ่งที่แก้ + โค้ด template ใหม่ + ## ธงต้องขออนุมัติ (จุดที่อยากแตะ site จริง รอเจ้าของ)
