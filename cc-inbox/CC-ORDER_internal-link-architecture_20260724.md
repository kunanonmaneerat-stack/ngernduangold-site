# WORK ORDER → Claude Code: internal-link architecture ทั้งเว็บ — ฆ่า orphan เร่ง index coverage (24 ก.ค. 2026 · จาก Cowork)

> บริบท: ยุทธศาสตร์ patient SEO (STRATEGY-DECISION_20260721) · GSC index audit พบ 83 หน้า discovered-not-indexed (SEO-OPPORTUNITY_20260721.md) · คอขวดจริง = index coverage + domain authority ไม่ใช่จำนวนหน้า · debt-letter-kit พิสูจน์แล้ว: เพิ่ม internal link → หลุด orphan (referring 1→5) · งานนี้ = ขยายให้เป็น "ระบบ" ทั้งเว็บ
> เป้า: **ทุกหน้า content มี inbound contextual internal link >=3 จากหน้าที่หัวข้อเกี่ยวข้องกัน** (Google crawl+index ง่ายขึ้น) · lever งบศูนย์ที่คุ้มสุดตอนนี้
> กฎเดิม: UTF-8 · ห้าม git add -A · ห้ามแตะ secrets/ · แก้เฉพาะ build_site.py · ห้ามคำต้องห้าม (อนุมัติง่าย/แน่นอน/ไว, ไม่เช็คบูโร, การันตี, รับรองผล) · ห้ามเลขดอกเบี้ย/% ใน anchor

## เฟส 1 — วัดก่อน (สร้าง analyzer ชั่วคราว)
เขียนสคริปต์ชั่วคราว (เช่น tools/_link_audit.py — ลบทีหลังได้ ไม่ต้อง commit) ที่:
1. build เว็บก่อน (`set SITE_GA=G-17PPE0M1B8` + `python build_site.py`) แล้วสแกน `site/*.html`
2. นับ **inbound internal link ต่อหน้า** (จำนวนหน้าอื่นที่ลิงก์มาหาหน้านี้ — นับ href ที่ชี้มา canonical slug ของหน้านั้น, unique source page)
3. ออกรายงาน: หน้าที่ inbound < 3 (= orphan/near-orphan) เรียงจากน้อยไปมาก + แท็ก cluster ของแต่ละหน้า
4. **priority ที่ต้องแก้ก่อน** (money/North Star): debt-letter-kit, debt-calculator, debt-health-check, loan-cash-2026, car-still-installment-loan-2026, credit-card-salary-30000-2026 + หน้าที่ GSC มี impression · แล้วตามด้วยหน้า content ที่เหลือที่ inbound<3

## เฟส 2 — เติมลิงก์แบบมีระบบ (build_site.py เท่านั้น)
สำหรับแต่ละหน้า inbound<3: เพิ่ม inbound จากหน้า "พี่น้องหัวข้อเดียวกัน" (cluster) ให้ถึง >=3
- **จัด cluster ตามหัวข้อ:** หนี้/ปลดหนี้ · บัตรเครดิต · สินเชื่อ/จำนำทะเบียน/รีไฟแนนซ์ · ออมเงิน · ประกัน · ภาษี/สิทธิลูกหนี้ (ดูจาก slug + หมวดในหน้า)
- ใช้กลไกที่มีอยู่: **inline `.ilinks`** (เนียน ส่ง signal ดี) หรือ related-block (`.related` body1..body18) — เลือกให้เหมาะกับหน้า
- **เพดานกันสแปม:** เพิ่มลิงก์ contextual **ไม่เกิน 2 อัน/หน้า source ต่อรอบ** · anchor = ข้อความบรรยายหัวข้อปลายทางแบบธรรมชาติ (ตรง search intent) ไม่ใช่ keyword ยัด · ห้ามลิงก์ซ้ำคู่เดิม (dup-check ก่อนเพิ่ม)
- **ห้ามแตะ** .ilinks ที่เพิ่มรอบ 21-24 ก.ค. (debt-letter-kit/car-still/salary-30000 ทำแล้ว) · ต่อยอดไม่ทับ
- ทำเป็น "wave": รอบนี้เอาให้ครบ **กลุ่ม priority money + หน้า orphan สนิท (inbound 0-1) ทั้งหมดก่อน** · ถ้าเหลือหน้า inbound=2 จำนวนมาก แยกเป็น order รอบหน้าได้ (รายงานว่าเหลือกี่หน้า)

## ⛔ COMPLIANCE (ผิดข้อเดียว = งานเสีย)
- anchor/ข้อความใหม่ห้ามมีคำต้องห้าม/เลขดอก/% · ห้ามแตะ CTA/affiliate/เนื้อหาหน้าอื่น (เฉพาะเพิ่ม internal link)
- ทุกหน้ายังต้องมี disclosure ครบตาม POSTING-POLICY

## ✅ BUILD GATE (บังคับก่อน commit)
1. `set SITE_GA=G-17PPE0M1B8` -> `python build_site.py` -> `python tools/postdeploy_smoke.py --src site` = PASS ทุกหน้า
2. รัน analyzer ซ้ำ: **ยืนยันหน้า priority + orphan-สนิท ทุกหน้ามี inbound >=3 แล้ว** (ก่อน/หลัง เทียบเป็นตาราง)
3. ไม่มีหน้าไหน inbound ลดลง (เพิ่มอย่างเดียว) · smoke ไม่หลุด assert ใด
4. ไม่ผ่าน = หยุด แก้ให้ผ่าน ห้าม commit

## 🚀 หลัง gate PASS
- `git add build_site.py site/` -> commit "seo: systematic internal-link architecture — kill orphans, inbound>=3 on money+priority pages (index-coverage lever)" -> `git push origin main`
- ลบ tools/_link_audit.py ชั่วคราว (หรือปล่อยไว้ถ้าจะใช้ตรวจรอบหน้า แต่ไม่ commit ถ้าไม่จำเป็น)
- ย้าย order นี้เข้า cc-inbox/done/

## 📤 รายงาน -> cc-outbox/result-internal-link-arch-20260724-<ts>.md
- ก่อน/หลัง: กี่หน้าที่ inbound<3 -> เหลือเท่าไร · ตารางหน้า priority (inbound ก่อน->หลัง) · เพิ่มลิงก์รวมกี่เส้น · smoke PASS? · push commit hash · เหลือ wave ถัดไปกี่หน้า (ถ้ามี)

---
## 🔧 PHASE 0 (ทำก่อน · quick compliance fix — เจอจาก LINE-funnel audit 24 ก.ค.)
หน้า /links hero (build_site.py **บรรทัด ~2640**) มีคำต้องห้าม "อนุมัติไว" ใน tagline การตลาด (ไม่ใช่ชื่อหน้า SEO):
- **เดิม:** `<p class="tag">บัตรเครดิต • สินเชื่อ • ออมเงิน ฉบับมนุษย์เงินเดือน — เทียบของจริง อนุมัติไว สมัครออนไลน์<br>`
- **ใหม่:** `<p class="tag">บัตรเครดิต • สินเชื่อ • ออมเงิน ฉบับมนุษย์เงินเดือน — เทียบของจริง ก่อนตัดสินใจ สมัครออนไลน์<br>`
- แก้เฉพาะจุดนี้จุดเดียว (exact-string find/replace)

**อย่าแตะจุดอื่นที่มี "อนุมัติไว/อนุมัติง่าย":** ตรวจแล้ว = (ก) ชื่อหน้า/related-card ของ credit-card-easy-approval-2026 ที่จับ search query จริง (grandfathered ตามมติเดิม ห้ามแก้ กระทบ SEO) · (ข) คำเตือนมิจฉาชีพ ("ระวังโฆษณา อนุมัติไว ไม่เช็กบูโร = มิจ") ซึ่ง compliant อยู่แล้ว · "การันตี" 39 จุด = "ไม่การันตี" disclosure ทั้งหมด (ถูกต้อง ห้ามแตะ) · รวม PHASE 0 นี้เข้า build เดียวกับ internal-link ด้านบน ผ่าน gate เดียวกัน