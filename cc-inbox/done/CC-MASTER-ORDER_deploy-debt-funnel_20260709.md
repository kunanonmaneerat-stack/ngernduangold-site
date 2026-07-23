# 🧭 MASTER CC ORDER — Deploy debt-wedge funnel · 9 ก.ค. 2026
รวม ORDER-line-oa-wire + ORDER-pivot-execute เป็นคำสั่งเดียว รันได้เลย
**หลักการ: idempotent (เช็คก่อนแก้ ถ้าทำแล้วข้าม) · build_site.py แตะเมื่อไหร่ = commit/push แยกท้ายสุด (Netlify ignore rule) · ไม่มีตัวเลข/การันตีดอกเบี้ย · disclosure + affiliate disclosure ครบ**

ค่าคงที่:
- LINE add-friend: `https://line.me/R/ti/p/@804qodya`
- Gumroad ชุด 199฿: `https://ngernduangold.gumroad.com/l/debt-toolkit`
- e-book 59฿: Gumroad เดิม (คง primary purchase CTA)

---

## TASK 1 — Deploy หน้า /debt-calculator
ไฟล์ `debt-calculator.html` วางที่ repo root แล้ว (Cowork · ผ่าน QA คณิต Snowball/Avalanche + NPER)
1. เปิด `build_site.py` หา logic ที่ copy standalone `*.html` → `site/`
   - ถ้าใช้ **list ตายตัว** → เพิ่ม `"debt-calculator.html"` เข้า list
   - ถ้า copy `*-infographic.html`/glob → เพิ่มให้ครอบ `debt-calculator.html` (หรือ copy ตรง ๆ)
2. Pretty URL: แก้ `site/_redirects` เพิ่มบรรทัด (เช็ค format เดิมก่อน):
   ```
   /debt-calculator    /debt-calculator.html    200
   ```
3. ยืนยันใน `debt-calculator.html`: `#lineBtn` href = `https://line.me/R/ti/p/@804qodya` target=_blank (Cowork wire แล้ว — แค่ตรวจ)
4. **Smoke:** build เสร็จ → `site/debt-calculator.html` มีจริง · เปิด /debt-calculator โหลดได้ · ปุ่ม "คำนวณ" แสดง Snowball/Avalanche (JS inline ไม่มี dep นอก)
5. **อัปเดตปุ่ม 199฿ ในเครื่องคำนวณ:** ใน `debt-calculator.html` เปลี่ยน href ปุ่ม `.btn-kit` (🧰 ชุดเครื่องมือ 199฿) จาก `/links?...toolkit199` → `https://ngernduangold.gumroad.com/l/debt-toolkit` (product live แล้ว · ยิงตรง Gumroad) · หมายเหตุ `#lineBtn` = `@804qodya` ถูกแล้ว ไม่ต้องแตะ · ปุ่ม 59฿ (`.btn-book`) → /links คงเดิม

## TASK 2 — ปุ่ม "แอด LINE (ฟรี)" ทุกหน้า
1. หา nav/header component ใน `build_site.py` (constant HEADER/NAV) หรือ `components/`
2. เพิ่มลิงก์/ปุ่ม **"แอด LINE"** → `https://line.me/R/ti/p/@804qodya` (target=_blank rel=noopener) · สไตล์กลมกลืน nav เดิม + accent เขียว LINE ได้
3. ต้องขึ้น **ทุกหน้า**

## TASK 3 — หน้า /links: การ์ด LINE + ชุด 199฿ + funnel-fix
(source = `links.html` ใน build_site.py)
1. บนสุด: การ์ด **"แอด LINE (ฟรี) — รับเครื่องคำนวณปลดหนี้ + ปรึกษาต่อ"** → LINE add-friend
2. การ์ดสินค้าใหม่: **"🧰 ชุดเครื่องมือปลดหนี้ (Excel) — 199฿"** → Gumroad toolkit URL
3. **funnel-fix (Gemini):** จัด e-book 59฿ เป็น **primary CTA เด่นบนสุด** แยกออกจากลิสต์ affiliate ชัดเจน · affiliate จัดเป็นหมวดแยก**ด้านล่าง** (ลด choice overload)
4. หน้าขาย e-book: เพิ่ม social proof ("อัปเดต ก.ค. 69 · worksheet ครบ") + ตัวอย่างเนื้อหา/สารบัญ ถ้ามี

## TASK 4 — Reposition wedge
1. Homepage hero + `<title>`/meta + og: เพิ่ม positioning **"ปลดหนี้ด้วยตัวเลขจริง ไม่ขายฝัน"** (คงชื่อแบรนด์)
2. /about + og-default sync tagline เดียวกัน
3. อย่าลบ cluster อื่น (ประกัน/บัตร) — แค่ให้ธีมหนี้/รีไฟแนนซ์เด่นสุดใน nav/หน้าแรก

## TASK 5 — SEO
1. internal link จากบทความ traffic ดีสุด → cluster หนี้/รีไฟแนนซ์ + /debt-calculator
2. bump priority ใน `sitemap.xml` ให้ 3 หน้าหนี้ที่ดีสุด
3. (เจ้าของกด GSC Request-Indexing เอง — CC ทำแทนไม่ได้)

---
## ลำดับ commit/push
1. commit หน้าเว็บ/เนื้อหา/redirects (ไม่แตะ build_site.py) ก่อน
2. commit **build_site.py แยก push ท้ายสุด** (กฎ Netlify ignore)
3. รายงานสิ่งที่แก้ + ผล smoke test แต่ละ TASK

## Definition of Done
/debt-calculator LIVE · ปุ่มแอด LINE ทุกหน้า · /links มีการ์ด LINE + ชุด 199฿ + e-book เด่น · tagline ปลดหนี้ขึ้นหน้าแรก · sitemap/internal link อัปเดต · 0 broken link · disclosure ครบ
