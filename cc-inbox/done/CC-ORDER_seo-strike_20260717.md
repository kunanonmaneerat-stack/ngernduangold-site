# CC-ORDER: SEO Strike — canonical fix + อัปเกรด 2 หน้าเป้า (17 ก.ค. 2026)

สั่งโดย: Cowork (เจ้าของอนุมัติ "ลุยตามแผน") · แหล่งข้อมูล: `cc-inbox/SEO-STRIKE_20260717.md` (อ่านทั้งไฟล์ก่อนเริ่ม — มี content block พร้อมวาง)
บริบท: GSC 28 วัน ทั้งเว็บ 0 คลิก มีแต่ impressions · เป้า = เปลี่ยน impressions เป็นคลิกใน 2–4 สัปดาห์

## กติกาเหล็ก (ห้ามละเมิด)
- ห้ามตัวเลขดอกเบี้ย/การันตีอนุมัติ ทุกจุดที่แก้
- disclosure เดิมของทุกหน้าคงอยู่ครบ ("ข้อมูลเพื่อการศึกษา…" / "มีลิงก์พันธมิตร" ที่มีอยู่แล้ว) · ห้ามเพิ่มลิงก์ affiliate ใหม่
- ห้ามแตะ: Pantip ทุกกรณี · .system_control/content_manifest.json · secrets/* · tools/post_guard.py (เพิ่ง patch คืนนี้)
- ไฟล์ UTF-8 · commit เป็นช่วงๆ แยกตาม FIX message ไทย · push ได้ (Netlify deploy อัตโนมัติ) · ห้าม push ถ้า build local ไม่ผ่าน
- ทุก [ตรวจสอบ] ใน content ที่ยกมาจาก SEO-STRIKE: รีวิวถ้อยคำให้เป็นกลาง-ไม่การันตี แล้ว "ลบ marker ออก" ก่อนเผยแพร่ (ห้ามปล่อย [ตรวจสอบ] ขึ้นเว็บ)

## FIX-1 (ทำก่อน — ปลดล็อกทั้งเว็บ): รวมสัญญาณ URL ซ้ำ .html
ปัญหา: GSC เห็นทุกหน้าเป็น 2 URL (มี/ไม่มี .html) สัญญาณแตกครึ่ง เช่น /credit-card-salary-30000-2026 (29 impr) กับ .html (12 impr)
ทำใน build_site.py (ศึกษาโครงสร้างก่อนแก้):
1. **canonical**: ทุกหน้าที่ generate ใส่ `<link rel="canonical" href="https://ngernduangold.com/<slug>">` (เวอร์ชันไม่มี .html เสมอ) — ถ้ามี canonical เดิมอยู่แล้วบางหน้า ให้ normalize เป็นแบบไม่มี .html ทั้งหมด
2. **301 redirect**: generate ไฟล์ `_redirects` (Netlify) ใน output dir — บรรทัดต่อหน้า: `/<slug>.html /<slug> 301` สำหรับทุกหน้า html ที่ build (ยกเว้น index) · ถ้ามี _redirects เดิม ต้อง merge ไม่ทับของเก่า · ระวัง redirect loop: ตรวจว่า Netlify ยัง serve /<slug> ได้ปกติหลัง 301 (Netlify map /<slug> → slug.html ภายในเอง — ทดสอบจริงหลัง deploy)
3. **internal links + sitemap**: สแกน HTML ที่ generate — internal href ที่ลงท้าย .html → เปลี่ยนเป็นไม่มี .html · sitemap.xml ต้องมีเฉพาะ URL ไม่มี .html
ตรวจรับ FIX-1 (หลัง deploy):
- `curl -sI https://ngernduangold.com/credit-card-salary-30000-2026.html` → 301 + Location ไม่มี .html
- `curl -s https://ngernduangold.com/credit-card-salary-30000-2026 | grep canonical` → href ไม่มี .html
- สุ่ม 3 หน้าอื่น + หน้าแรก → 200 ปกติ · sitemap ไม่มี .html สักบรรทัด

## FIX-2: อัปเกรด /car-still-installment-loan-2026 (72 impr รอ, pos ~50)
ใช้ content จาก SEO-STRIKE §FIX-2 ทั้งก้อน:
1. เปลี่ยน title เป็น: `รถผ่อนไม่หมด จำนำได้ไหม? ทางเลือกโอนเล่มและรีไฟแนนซ์ที่ควรรู้` + meta description ตามไฟล์
2. ย่อหน้าเปิดใหม่ (ตอบคำถามใน 2 ประโยคแรก) วางเหนือเนื้อหาเดิม — เนื้อหาเดิมคงไว้ต่อท้าย ปรับ heading ให้ไหล
3. เพิ่ม section "คำถามที่พบบ่อย" 4 ข้อ (รถผ่อนไม่หมดจำนำได้ไหม / เกิน 20 ปี / เกิน 25 ปี / 15 ปี) — ถ้อยคำตามไฟล์ (หลังรีวิว marker)
4. ฝัง JSON-LD FAQPage (โครงในไฟล์) — validate ด้วย schema checker ก่อน commit
5. h1/h2 ต้องมีวลี "รถผ่อนไม่หมด" อย่างน้อย 1 จุดแบบธรรมชาติ

## FIX-3: อัปเกรด /credit-card-salary-30000-2026 (41 impr รวม, pos ~32)
1. title: มีวลี "เงินเดือน 30000 วงเงินบัตรเครดิต" + meta ตามแนว SEO-STRIKE §FIX-3
2. เพิ่ม section "เงินเดือน 30,000 ขอวงเงินได้ประมาณเท่าไหร่" — **ยืนยันเกณฑ์จากแหล่งทางการก่อนเผยแพร่**: ธปท. https://www.bot.or.th/th/satang-story/digital-fin-lit/creditcard.html (Codex ตรวจแล้วพบเกณฑ์ รายได้ 30,000–<50,000 → วงเงินไม่เกิน 3 เท่าของรายได้) → เขียนเป็น "ตามเกณฑ์ ธปท. …ไม่เกิน 3 เท่าของรายได้ต่อเดือน" พร้อมกำกับว่าแต่ละธนาคารอนุมัติจริงต่ำกว่าเพดานได้ · ถ้าเข้าหน้า ธปท. ไม่ได้/ข้อมูลไม่ตรง → ตัดตัวเลขออก เขียนเชิงหลักการอย่างเดียว
3. ห้ามเลขดอกเบี้ยเด็ดขาด (วงเงิน-เท่าของรายได้ = โอเค เพราะเป็นเกณฑ์ทางการ ไม่ใช่ดอกเบี้ย)

## หลัง deploy ทั้งหมด
1. รัน smoke: ทุก URL ใน automation-log/gsc-pages.csv (แบบไม่มี .html) ต้อง 200 · affiliate_click ยังทำงานบน 2 หน้าที่แก้ (เปิดหน้า เช็ค console/network ว่า event ยิงตามเดิม — Playwright ตามแพทเทิร์น cc-conversion-cro เดิม)
2. เขียนรายงาน `automation-log/CC-REPORT_seo-strike_20260718.md`: สิ่งที่เปลี่ยนต่อ FIX + ผล curl ตรวจรับ + commit hashes + สิ่งที่ตัดสินใจต่างจาก order (ถ้ามี) พร้อมเหตุผล
3. แจ้งใน report: แนะเจ้าของกด "Validate fix"/Request indexing 2 หน้าเป้าใน GSC UI (ทางเลือก ไม่บังคับ)

## นิยามเสร็จ (Definition of Done)
FIX-1 curl ผ่านครบ · FIX-2/3 ขึ้นเว็บจริงพร้อม canonical ถูก · ไม่มี [ตรวจสอบ] หลุด · ไม่มีเลขดอกเบี้ย · build ผ่าน · report ครบ
