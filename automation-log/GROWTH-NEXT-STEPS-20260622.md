# 🚀 แผนทำอะไรต่อ — โหมดเก็บเกี่ยว (22 มิ.ย. 2026)
> สรุปจาก audit: เว็บพร้อม index 100% (43 หน้า, schema/canonical/robots ครบ, GSC verified, GA4 ติด)
> คอขวด = **ทราฟฟิก ไม่ใช่คอนเทนต์** → หยุดผลิต เปลี่ยนเป็น index + กระจาย + วัดผล + ปลดล็อกรายได้

═══════════════════════════════════════════
## ✅ STEP 1 — push ให้ขึ้นครบ (ทำเลย, 1 คำสั่ง)
ชุดนี้รวม 3 บทความสุดท้าย (#31 ประกันสุขภาพ, #32 กองทุนรวม, #33 เกษียณ) + แถบ "คู่มือแนะนำ" หน้าแรก
```
cd C:\Users\nL_ku\ngernduangold-site
git add build_site.py
git commit -m "home: featured-guides strip + retirement/mutual-fund/health-insurance"
git push
```
→ Netlify build+smoke ~1-2 นาที → เว็บครบ 43 หน้า live

═══════════════════════════════════════════
## ⭐ STEP 2 — Google Search Console: ดัน index (คุ้มสุด, ทำครั้งเดียว)
ทำไม: ไม่ส่ง = Google ค่อย ๆ เจอเอง (เป็นสัปดาห์-เดือน) · ส่ง = index ใน 2-3 วัน
1. เปิด https://search.google.com/search-console → เลือก property ngernduangold.netlify.app
   (ถ้ายังไม่มี property: Add property > URL prefix > ใส่ https://ngernduangold.netlify.app > ยืนยันด้วยไฟล์ google068178fb9e4f38c9.html ที่ verified อยู่แล้ว)
2. เมนูซ้าย > Sitemaps > ช่อง "Add a new sitemap" พิมพ์  sitemap.xml  > Submit
   (URL เต็ม: https://ngernduangold.netlify.app/sitemap.xml)
3. เมนูบน > URL Inspection > วางทีละ URL ของ 10 บทความใหม่ > กด "Request Indexing"
   (ทำ 5-10 URL สำคัญก่อนก็พอ ระบบจะไล่ที่เหลือจาก sitemap)
   URL สำคัญ:
   - https://ngernduangold.netlify.app/credit-bureau-check-2026.html
   - https://ngernduangold.netlify.app/pay-off-credit-card-debt-2026.html
   - https://ngernduangold.netlify.app/credit-card-interest-2026.html
   - https://ngernduangold.netlify.app/loan-online-legal-2026.html
   - https://ngernduangold.netlify.app/tax-deduction-salary-2026.html
   - https://ngernduangold.netlify.app/credit-card-salary-20000-2026.html
   - https://ngernduangold.netlify.app/credit-card-salary-30000-2026.html
   - https://ngernduangold.netlify.app/health-insurance-salary-2026.html
   - https://ngernduangold.netlify.app/mutual-fund-beginner-2026.html
   - https://ngernduangold.netlify.app/retirement-planning-salary-2026.html

═══════════════════════════════════════════
## 📣 STEP 3 — เริ่มโพสต์ (ทราฟฟิกแรกทันที ระหว่างรอ SEO)
ใช้ไฟล์ ARTICLES-multichannel-v3-20260622.md (ก๊อปวางได้เลย ลิงก์ติด utm รายช่อง)
- Threads: วันละ 1-2 ชิ้น (อย่ารัวทีเดียว)
- Pantip: เลือกกระทู้ตรงคำถาม ตอบมีสาระก่อน แปะลิงก์เดียวท้าย (กัน flag)
- TikTok/YT: คลิปคลัง credit-score/debt/title-loan map หัวข้อ 1,3,5 ได้เลย
- (FB/IG: คลิป 36 ตัวใน post-plan.json เริ่ม 23 มิ.ย. — เดินตามตารางเดิม)

═══════════════════════════════════════════
## 💰 STEP 4 — ปลดล็อกรายได้คลัสเตอร์ใหม่ (ต้องใช้บัญชี AccessTrade คุณ)
ปัญหา: คลัสเตอร์ ภาษี/ประกันสุขภาพ/กองทุน/เกษียณ ยัง convert ไม่ได้ดี
เพราะ affiliate list มีแค่ travel/pa/car (ไม่มี health/life/บำนาญ/กองทุน)
→ เข้า AccessTrade dashboard ดึง "Get Link" ของแคมเปญเหล่านี้ (ถ้าได้รับอนุมัติ) ส่ง atth.me ให้ผม:
  [ ] ประกันสุขภาพ (health) — เช่น AXA Health / Cigna / รพ.ที่มีแคมเปญ
  [ ] ประกันชีวิต/สะสมทรัพย์ (life)
  [ ] ประกันบำนาญ (pension/annuity)
  [ ] กองทุน/แอปลงทุน (ถ้ามีแคมเปญ เช่น โบรกฯ/แอปกองทุน)
ผมจะเสียบเข้า INSURANCE list + ปุ่มในบทความที่เกี่ยวให้อัตโนมัติ (1 รอบแก้ build_site.py)

═══════════════════════════════════════════
## 📊 STEP 5 — วัดผล (หลังโพสต์/index ~1-2 สัปดาห์)
- GA4 > Reports > Acquisition > Traffic acquisition → ดู utm_source ช่องไหนส่งคนมามากสุด
- GA4 > Engagement > Pages → บทความไหนคนเข้ามากสุด/อยู่นาน
- GA4 > Events > affiliate_click → หน้าไหนคลิกลิงก์พันธมิตรมากสุด (= ใกล้รายได้)
- GSC > Performance → คำค้นไหนเริ่มติด + หน้าไหน impression ขึ้น
→ เจอคลัสเตอร์/ช่องที่มาแรง = บอกผม ผมเขียนเสริม + ทำคลิปเฉพาะจุดนั้น (คุ้มกว่าเขียนมั่ว)

═══════════════════════════════════════════
ลำดับความคุ้ม: STEP 1 → 2 → 3 ทำได้ทันที (ปลดล็อกทราฟฟิก) · STEP 4 เมื่อสะดวกเข้า AccessTrade · STEP 5 รอบหน้า
