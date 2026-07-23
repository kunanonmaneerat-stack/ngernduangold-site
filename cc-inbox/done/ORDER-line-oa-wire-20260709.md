# ORDER — Deploy debt-calculator + wire LINE OA · 9 ก.ค. 2026
เจ้าของยืนยัน pivot: **LINE OA = North Star (owned audience)** · **debt-calculator = lead magnet**
Cowork ได้ stage ไฟล์ `debt-calculator.html` ไว้ที่ repo root แล้ว (ผ่าน QA: คณิต Snowball/Avalanche ถูก, ตรวจจับเคส "จ่ายขั้นต่ำไม่พอตัดต้น" แล้วเตือนแทนเลขปลอม)

## PART A — Deploy หน้า debt-calculator (ทำได้เลย ไม่ต้องรอ LINE)
1. ตรวจ `build_site.py` ว่า copy `debt-calculator.html` → `site/` หรือยัง
   - ถ้า build ใช้ list/pattern ตายตัว → เพิ่ม `debt-calculator.html` เข้า list
   - ถ้า copy standalone *.html อยู่แล้ว (เหมือน *-infographic.html) → ผ่าน
2. เพิ่ม pretty URL ใน `site/_redirects` (เช็ค format เดิมก่อน): `/debt-calculator   /debt-calculator.html   200`
3. **อย่าเพิ่งแตะ `#lineBtn`** — ตอนนี้ชี้ `/links` ไว้ (ปลอดภัย ไม่พัง) รอ lin.ee ค่อยสลับใน PART B
4. build + push — **ถ้าแตะ `build_site.py` ให้ commit/push แยกท้ายสุด** (กฎ Netlify ignore ของเจ้าของ)
5. Smoke: เปิด `/debt-calculator` โหลดได้ + ปุ่ม "คำนวณ" แสดงผล Snowball/Avalanche จริง

## PART B — Wire LINE OA ✅ พร้อมทำได้เลย (บัญชีสร้างเสร็จ 9 ก.ค.)
- **Basic ID = `@804qodya`** · add-friend URL (ยืนยัน format LINE Developers): **`https://line.me/R/ti/p/@804qodya`**
1. `debt-calculator.html` → Cowork wire `#lineBtn` เป็น add-friend URL แล้ว (target=_blank) — CC แค่ตรวจว่าอยู่ครบตอน build
2. เพิ่มปุ่ม **"แอด LINE (ฟรี)"** ใน header/nav ทุกหน้า (component) → `https://line.me/R/ti/p/@804qodya` (target=_blank rel=noopener)
3. เพิ่มการ์ด lead-magnet ด้านบน `/links` → "รับเครื่องคำนวณปลดหนี้ฟรี + ปรึกษาต่อใน LINE" ลิงก์ add-friend เดียวกัน (e-book 59฿ ยังเป็น primary purchase CTA ตาม funnel-fix — LINE = capture ก่อนขาย)
4. rebuild + push (build_site.py แตะเมื่อไหร่ = push ท้ายสุด)
หมายเหตุ: line.me deep link ไม่รับ UTM param — ติดตามยอดแอดผ่าน LINE OA analytics แทน · ถ้าเจ้าของอยากได้ lin.ee (สั้น+trackable) ทีหลัง สลับ href ทีเดียว

## ข้อจำกัด (คงไว้)
- ห้ามตัวเลข/การันตีดอกเบี้ยในหน้า · disclosure "ประมาณเพื่อการศึกษา ไม่ใช่คำแนะนำการเงิน + มีลิงก์พันธมิตร" ต้องอยู่ครบ
- media gitignored (local) · commit เฉพาะ report+order+หน้าเว็บ
- build_site.py = push แยกท้ายสุดเสมอ

## ฝั่งเจ้าของ (ไม่ใช่งาน CC)
- ตั้ง greeting / rich menu / auto-reply ใน LINE OA Manager (ดู outputs/LINE-OA-SETUP-PACK_20260709.md)
- อัปเดต bio ทุกช่อง (IG/Threads/YouTube/Pinterest/FB) ใส่ lin.ee
