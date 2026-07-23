# CC Order — อุดจุดรั่วเงิน + ต่อ affiliate ที่ debt-calculator (10 ก.ค. 2026)
ที่มา: consult Gemini + Fable 5 (ดู REVENUE-STARTER-KIT_2026-07-10.md) · Fable: "affiliate รีไฟแนนซ์/รวมหนี้ = เครื่องยนต์เงินหลัก, Gumroad = จุดรั่ว" · Cowork ทำ code ไม่ push — **CC implement + build + push + verify**

ไฟล์: `debt-calculator.html` (root source) → build → `site/debt-calculator.html`

## แก้ #1 — เปลี่ยนปุ่ม toolkit 199฿ จาก Gumroad → LINE/พร้อมเพย์ (จุดรั่วเงินอันดับ 1)
บรรทัด ~117 ปัจจุบัน:
```html
<a class="btn btn-kit" href="https://ngernduangold.gumroad.com/l/debt-toolkit?utm_source=calculator&utm_medium=leadmagnet&utm_campaign=toolkit199" target="_blank" rel="noopener">🧰 ชุดเครื่องมือ 199฿</a>
```
เปลี่ยนเป็น (สั่งซื้อทางไลน์ → โอนพร้อมเพย์ 080-063-8891 → ส่งไฟล์มือ):
```html
<a class="btn btn-kit" href="https://line.me/R/ti/p/@804qodya" target="_blank" rel="noopener" data-note="สั่งทางไลน์ โอนพร้อมเพย์ ส่งไฟล์ทันที">🧰 สั่งชุดเครื่องมือ 199฿ (ทางไลน์)</a>
```
> เหตุผล: คนไทยกลัวหน้าเช็คเอาต์ต่างชาติ/ลิงก์นอก → ยอดตก · ปิดในไลน์ด้วยพร้อมเพย์ trust สูงกว่ามาก (ทั้ง Gemini+Fable ยืนยัน) · เก็บ Gumroad ไว้เป็นทางเลือกรองใน /links ได้ถ้าต้องการบัตรเครดิต

## แก้ #2 — เพิ่ม affiliate CTA "รวมหนี้/รีไฟแนนซ์" ตรงจุด intent สูงสุด (หลังเห็นเดือนปลอดหนี้)
แทรก **หลังบรรทัด 110** (ปิด `<div class="results">`) ก่อน `<div class="cta">` — บล็อกนี้โชว์ตอน results ขึ้น (ให้ JS `calc()` เอา class active มาโชว์ หรือใส่ไว้ในโซน results ให้ขึ้นพร้อมผลลัพธ์):
```html
<div class="cta cta-refi" id="refiCta">
  <h2>💡 ดอกกินยอดจนแทบไม่ลด?</h2>
  <p>ถ้าดอกเฉลี่ยของคุณสูง (บัตร ~16–25%/ปี) การ<strong>รวมหนี้หลายก้อนให้เหลือก้อนเดียวดอกต่ำลง</strong> อาจช่วยให้ยอดลดเร็วขึ้น — เทียบจุดคุ้มก่อนตัดสินใจ</p>
  <a class="btn btn-refi" href="/debt-consolidation-2026.html?utm_source=calculator&utm_medium=verdict&utm_campaign=refi_wedge">📊 ดูวิธีรวมหนี้ + เทียบสินเชื่อ →</a>
  <a class="btn btn-title" href="/car-title-loan-compare-2026.html?utm_source=calculator&utm_medium=verdict&utm_campaign=titleloan_wedge">🚗 มีรถปลอดภาระ? เทียบสินเชื่อทะเบียนรถ →</a>
  <small>หน้าปลายทางมีลิงก์พันธมิตร · ข้อมูลเพื่อการศึกษา ไม่ใช่คำแนะนำเฉพาะบุคคล</small>
</div>
```
> ส่งไป **บทความ /debt-consolidation-2026.html + /car-title-loan-compare-2026.html** (ซึ่งมี affiliate offers + disclosure อยู่แล้ว) — ไม่วาง raw affiliate ในเครื่องคำนวณ ปลอดภัย on-brand · recommend_map มี refinance/srisawad/carforcash/happycash/ktcproud พร้อม
> สไตล์ `.cta-refi` ให้ต่างจาก `.cta` ขายของนิดหน่อย (เช่นเส้นขอบทอง) เพื่อไม่ให้ดูยัดขาย

## แก้ #3 — โผล่เครื่องคำนวณให้ชัดจากบทความคลัสเตอร์หนี้ (ถ้ายังไม่ครบ)
ตรวจว่าหน้า debt-cluster (debt-consolidation, debt-restructuring, close-debt-fast, credit-card-interest ฯลฯ) มีปุ่มลิงก์ไป `/debt-calculator` เด่นๆ ต้นบทความ — เพิ่มให้ครบ (calculator = จุด convert สูงสุด)

## ก่อน push
1. `python check_affiliate_links.py` — ยืนยันลิงก์พันธมิตร live ทั้งหมด
2. เปิด debt-calculator ใน browser: กรอกเลขทดสอบ → ผลลัพธ์ขึ้นปกติ + refiCta โผล่ + ปุ่ม LINE 199฿ ชี้ไลน์ + ไม่มี JS error
3. build + push + verify บน ngernduangold.com/debt-calculator

## หมายเหตุที่ต้อง sync
- LINE OA: เจ้าของตั้ง Welcome message + PromptPay QR (คัดลอกจาก REVENUE-STARTER-KIT ②) — งานในแอป LINE ไม่ใช่ repo
- Pantip Consult Engine: ใช้ PANTIP-SPRINT-REPLY-TEMPLATE — pantip-daily-opportunity ร่าง → เจ้าของรีวิว → โพสต์ (ห้าม auto)
- Brand search: บนทุกช่องให้ชี้ค้น "ngernduangold" (อังกฤษ) — ชื่อไทยเสิร์ชไม่เจอ (ชน "สมอทอง")
