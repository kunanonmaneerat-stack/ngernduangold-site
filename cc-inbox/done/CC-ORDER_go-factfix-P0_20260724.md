# WORK ORDER → Claude Code: 🟢 ไฟเขียว FACTFIX P0+P1 (24 ก.ค. 2026 · จาก Cowork)

> **Cowork verify แล้วด้วย web search (23 ก.ค. 23:4x) — เกณฑ์คลินิกแก้หนี้ในฉบับแก้ถูกต้องตรงแหล่งทางการ** อนุมัติให้ deploy:
> บุคคลธรรมดามีรายได้ · อายุ ≤70 ปี · หนี้รวม ≤2 ล้านบาท · หนี้เสียค้าง >120 วัน · ดอก 3-5%/ปี · ผ่อนสูงสุด 10 ปี
> แหล่ง: debtclinicbysam.com (ประกาศเกณฑ์ 2568) + aseanallnews Money Expo 2026 (ยืนยัน "ปิดหนี้ไว ไปต่อได้" = โครงการหนี้ต่ำแสน คนละตัวกับคลินิกแก้หนี้) → หน้า live ใส่เกณฑ์ "ปิดหนี้ไว" ผิดที่จริง
> กฎเดิม: UTF-8 · ห้าม git add -A · ห้ามแตะ secrets/ · ห้ามคำต้องห้าม · zero-budget

## งาน = รัน `cc-inbox/order-factfix-20260720.md` ให้ครบ (P0 + P1) แล้ว deploy
เนื้อการแก้ทั้ง 9 จุด (เดิม/ใหม่) อยู่ในไฟล์นั้นครบแล้ว ทำตามนั้น โดย:

### P0 — debt-clinic-sam-2026.html (5 จุด) = อนุมัติเต็ม ทำได้เลย
- ข้อเท็จจริงผ่าน verify แล้ว ใช้ข้อความ "ใหม่" ตามที่ order ระบุทุกจุด (body who/terms/notqualify · faq35 ข้อ1+2 · meta description)

### P1 — close-debt-fast-2026.html (4 จุด) = ทำ แต่ **verify ก่อน commit**
- P1 มีข้ออ้างเชิงปฏิบัติที่ Cowork ยังไม่ได้ตรวจ: **ช่องทาง SAM LINE @samsocialamc · call center 1443 กด 6 · SFIs ดูแลโดย บบส.อารีย์ (ARI-AMC) · ข้อยกเว้นจำนำทะเบียน/nano finance บสย./บัญชีม้า**
- ก่อนเขียนแต่ละจุด **ตรวจกับแหล่งทางการ (bot.or.th/cleardebt + debtclinicbysam.com/sam.or.th)** ว่าตรงปัจจุบัน — ข้อไหนยืนยันได้ = ใส่ตาม order · ข้อไหนยืนยันไม่ได้/ไม่ชัด = **ลดเป็นภาษากลาง** ("ลงทะเบียนผ่านช่องทางทางการของ ธปท./SAM — เช็กช่องทางล่าสุดที่ bot.or.th/cleardebt") ห้าม fabricate เบอร์/ชื่อหน่วยงานที่ยืนยันไม่ได้ · สรุปผลตรวจแต่ละข้อในรายงาน

### P2 (ท้าย order) = report-don't-guess
- ebook + content-packages grep (`จ่ายขั้นต่ำ 5%`, `คุณสู้ เราช่วย`) = ทำตาม order (mark ห้ามใช้ซ้ำ)
- kept-savings ตัวเลข Kept Grow = **ห้ามแก้ตัวเลข** เจอไม่ตรงให้รายงานเฉย ๆ (ตาม order)

## ⚙️ วิธีแก้ (สำคัญ — anchor เลื่อนแล้ว)
- **ใช้ exact-string find/replace ("เดิม"→"ใหม่") ไม่ใช่เลขบรรทัด** — บรรทัดขยับหลังเพิ่ม .ilinks รอบ internal-link · เลข ~1649 ใน order เป็นแค่ไกด์
- แก้เฉพาะ build_site.py · ไม่แตะลิงก์ .ilinks ที่เพิ่งเพิ่ม (ไม่ทับกัน) · อัปเดต "อัปเดตล่าสุด" 2 หน้าเป็น 24 ก.ค. 2026

## ✅ BUILD GATE (บังคับ ก่อน commit)
1. `set SITE_GA=G-17PPE0M1B8` → `python build_site.py` → `python tools/postdeploy_smoke.py --src site` = PASS ทุกหน้า
2. QA ตาม checklist ท้าย order: grep repo ต้องไม่เหลือ `1 แสน`/`100,000` ในบริบทคลินิกแก้หนี้ (เหลือใน "ปิดหนี้ไว" = ถูก) · เปิด site/debt-clinic-sam-2026.html ยืนยัน 120วัน/2ล้าน/10ปี ครบ 3 จุด (body·FAQ·meta) · close-debt-fast มีบรรทัดข้อยกเว้นจำนำทะเบียน · disclosure ครบ 2 หน้า
3. ไม่ผ่านข้อไหน = หยุด แก้ให้ผ่าน ห้าม commit

## 🚀 หลัง gate PASS
- `git add build_site.py site/` (เฉพาะที่เปลี่ยน) → commit "factfix: correct คลินิกแก้หนี้ SAM criteria (120d/2M/70y/10yr, verified) + close-debt-fast exclusions & channels" → `git push origin main`
- ย้าย `order-factfix-20260720.md` + ไฟล์นี้ เข้า `cc-inbox/done/`

## 📤 รายงาน → cc-outbox/result-factfix-20260724-<ts>.md
P0 แก้กี่จุด + smoke PASS? · P1 แต่ละข้อ verify ผ่าน/ลดภาษา? · grep `1 แสน` เหลือกี่จุด (ต้องเหลือเฉพาะ "ปิดหนี้ไว") · push commit hash · ย้ายไฟล์เข้า done/ แล้ว