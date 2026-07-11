# CC report — /debt-letter-kit LIVE (funnel 199฿) · 11 ก.ค. 2026 (commit ce20e22)

## LIVE: https://ngernduangold.com/debt-letter-kit
โครงครบตาม order: hero → pain → ในชุดมีอะไร (6 การ์ด) → **ตัวอย่างฟรีฉบับที่ 1 เต็มใบ** (กล่องจดหมาย + เคล็ด) → ราคา 199฿ + CTA LINE ใหญ่ + "ทักขอตัวอย่างเพิ่มฟรี" → ทำไมเชื่อเรา (เป็นกลาง/ธปท./ไม่หนุนนอกระบบ) → disclaimer "ผลขึ้นกับดุลยพินิจเจ้าหนี้"
- canonical extensionless + .html→301 + sitemap ✓ · OG navy #0F172A + gold #E9B949 (`og-letter-kit.png` 200) + twitter card ✓ · GA ✓
- **0 affiliate href บนหน้า** (ตรวจแล้ว — คำว่า atth.me ที่เจอใน source = โค้ด GA listener ที่ inject ทุกหน้า ไม่ใช่ลิงก์) · ระบุชัด "สินค้าของแบรนด์เอง ไม่ใช่ค่าธรรมเนียมเจ้าหนี้/หน่วยงานรัฐ"
- ปุ่ม LINE 2 จุด → @804qodya · โปรโตคอลซื้อ: พิมพ์ "จดหมาย" → โอน PromptPay → รับไฟล์ในแชท (owner-side)

## Funnel links ที่เพิ่ม (inbound รวม 9 หน้า)
- **Quiz E/F**: secondary CTA "อยากได้คำพูดเจรจากับเจ้าหนี้?" — โชว์เฉพาะเกรด E/F (ทดสอบจริง: F โชว์+SAM คงเดิม, A ซ่อน) · ไม่แทนที่ consolidation เดิม
- **/debt-calculator**: crosslink "วางแผนแล้ว ลองเจรจาลดดอกเองก่อน →"
- **letter_cta ท้ายบทความ 7 หน้า nego-cluster** (consolidation · restructuring · pay-off-cc · cc-interest · close-fast · clinic-sam · lawsuit) — วางถัดจาก kept_next

## ⚠️ Deviations (review 3-lens จับ + CC แก้ก่อน push)
1. **นับจำนวนขัดแย้งกันเอง (major, confirmed)** — สเปก order นับสองแบบ ("5 ฉบับ + สคริปต์" แต่รายการจริงมีจดหมาย 4 + สคริปต์ 1) → standardize เป็น **"จดหมาย 4 ฉบับ + สคริปต์โทรแบงก์"** ทุก surface (title/meta/H1/buy box/OG/banner) กัน over-promise บนหน้าเก็บเงิน · **ถ้า PDF จริงมีจดหมาย 5 ฉบับ แจ้งมา — flip กลับ 1 commit**
2. ตัวอย่างจดหมาย: "[เลขที่บัตร]" → **"[เลขบัตร 4 ตัวท้าย / เลขอ้างอิงบัญชี]"** (ไม่แนะนำให้เขียนเลขบัตรเต็มใบลงจดหมาย — privacy/fraud risk)
3. เพิ่มคำเตือนใน tip: ฉบับ 1 สำหรับคนประวัติจ่ายดี — อย่าคัดประโยค "ชำระตรงเวลา" ถ้าไม่ตรงจริง (กัน false representation)
4. กล่องจดหมายเปลี่ยนจาก Courier (ไม่มี glyph ไทย → ฟอนต์เพี้ยนปนกัน) เป็น Sarabun/Leelawadee

## Gates + verify
smoke **67/67** · link_check 0 broken · affiliate **17/17 ไม่แตะ** · comply OK · blob UFFFD=0 · live: ตัวอย่างเต็มใบแสดงครบ · mobile 375px ไม่ overflow · **0 console error** · build_site.py commit เดียว (fail-closed guard คุ้มครองแล้ว)

**พร้อมใช้เป็นปลายทาง LINE broadcast #4 + กระสุน Pantip 16 ก.ค.** ("มีชุดจดหมาย+สคริปต์เจรจา ตัวอย่างฟรี → /debt-letter-kit")

---
## FLIP 11 ก.ค. (ค่ำ) — 5 ฉบับ + สคริปต์ (commit db7ef54) ✅ LIVE
PDF จริงอัปเป็น 5 จดหมาย (เพิ่มใบ #3 พักชำระชั่วคราว/เหตุสุดวิสัย) → flip ทุก surface ตาม order:
- title/meta/H1/hero-sub/buy box → "จดหมาย 5 ฉบับ + สคริปต์โทรแบงก์ (PDF 10 หน้า)" · รายการครบ ①ลดดอก ②ปรับโครงสร้าง(ยืดงวด/ลดค่างวด) ③**พักชำระชั่วคราว** ④ประนอมหนี้(ค้าง/ใกล้ค้าง) ⑤ปิดบัญชีลดยอด ⑥สคริปต์โทร (+ตาราง/ช่องทาง ธปท.)
- OG card regen (5 ฉบับ + พักชำระใน subtitle) · banner ท้ายบทความ 7 หน้า → "5 ฉบับ"
- อัปเลขอ้างอิงใน tip ให้ตรงเลขใหม่ (เคยค้างจ่าย → ใช้ฉบับ 2/4)
- คงเดิมครบ: 199฿ · LINE 2 ปุ่ม · disclaimer ดุลยพินิจเจ้าหนี้ · ตัวอย่างฉบับ 1 (เวอร์ชัน privacy-safe "[เลขบัตร 4 ตัวท้าย]" — ตรงกับที่ order ยืนยัน) · 0 affiliate · funnel Quiz E/F + cluster ไม่แตะ
- Gates: smoke 67/67 · link_check 0 · affiliate 17/17 · live verify ทุกจุด "5 ฉบับ" ✓ ไม่เหลือ "4 ฉบับ/9 หน้า" ✓ mobile ไม่ overflow ✓ blob UFFFD=0
