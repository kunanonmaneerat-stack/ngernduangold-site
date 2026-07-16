# SPEC (dry-run เท่านั้น — ห้าม build รอบนี้) — Refinance "ประหยัดเท่าไหร่" upgrade · 16 ก.ค. 2026

## ⚠️ FLAG ก่อนอ่าน: เครื่องคำนวณรีไฟแนนซ์ LIVE อยู่แล้ว
`https://ngernduangold.com/refinance-savings-calculator` (ขึ้น 11 ก.ค., pattern `_TOOL_PAGES`, PMT amortized เดิม/ใหม่ + จุดคุ้มทุน + การ์ดแชร์ PNG + crosslinks + banner บทความ 4+1 หน้า)
→ **ข้อเสนอ: ENHANCE ตัวที่มี ไม่สร้าง `/refinance-calculator` ใหม่** (กัน slug ซ้ำซ้อน/SEO cannibalization — บทเรียนเดียวกับ D1/quiz) · ถ้า Cowork ยืนยันต้องการหน้าแยก ให้ 301 ตัวเก่าหรือระบุเหตุผล

## Delta ที่สเปกนี้เพิ่ม (ตาม order 16 ก.ค. + สิ่งที่ตัว live ยังไม่มี)
1. **โหมด "ไม่รู้ดอกเบี้ยใหม่" (slider เงื่อนไขสมมติ)** — จุดต่างหลักจากตัว live (ที่ต้องกรอกดอกใหม่เอง):
   - อินพุต: ยอดหนี้คงเหลือ · ค่างวดปัจจุบัน · จำนวนงวดที่เหลือ (ตาม order — derive ดอกปัจจุบันโดยประมาณจาก 3 ตัวนี้ด้วย IRR bisection ฝั่ง client)
   - slider "สมมติดอกใหม่ต่ำกว่าเดิม X ส่วน" แบบช่วงกว้าง (เช่น ลดเล็กน้อย/ปานกลาง/มาก — **ไม่มีเลขดอกเบี้ยเจาะจง**, แสดงผลเป็น "ช่วงประหยัด ~ต่ำ–สูง บาท")
   - เอาต์พุต: ช่วงค่างวดใหม่ + ช่วงดอกรวมที่ลด + ประโยคระวัง "เช็กใบเสนอจริงก่อนตัดสินใจ"
2. **Sticky CTA ล่างจอ** (pattern เดียวกับ /debt-health-check ที่ทำแล้ว): ปุ่ม affiliate รีไฟแนนซ์/รวมหนี้ + ปุ่ม LINE OA
3. **CTA affiliate ตรง** (rel="sponsored" + "มีลิงก์พันธมิตร"): ตัวเลือก 2 ทางให้ Cowork ตัดสิน —
   (ก) คงหน้ากลาง /debt-consolidation-2026 (ปัจจุบัน — trust-first, conv จากหน้ากลางพิสูจน์แล้ว)
   (ข) เพิ่มปุ่มตรง atth.me เงินเทอร์โบ/Kashjoy (จาก recommend_map) ใต้ผลลัพธ์ พร้อม disclosure box — เพิ่ม 2 ลิงก์เข้า check_affiliate (17→19)
4. GA event: `refi_result_view` + `refi_slider_change` (วัด engagement ก่อนตัดสินใจ A/B ข้อ 3)

## Implementation (เมื่ออนุมัติ)
- แก้ `refinance-savings-calculator.html` (root, python I/O byte-safe) — ไม่แตะสูตร PMT เดิม (F3 test-case 300k/16→9/36=+36,259 ต้องยังผ่าน)
- gates เดิมครบ + comply: ไม่มีเลข % ใหม่ใด ๆ (slider เป็นเชิงสัดส่วน/ช่วงคำ ไม่ใช่ตัวเลขดอก) · build 1 ครั้ง
- Acceptance: mobile · โหมด slider ให้ช่วงตัวเลขสมเหตุผล (bisection converge) · sticky CTA ทำงาน · affiliate rel+disclosure ครบ (ถ้าเลือก ข)

**สถานะ: รอ Cowork/เจ้าของรีวิว — เลือก (ก)/(ข) + ยืนยัน enhance-not-new — แล้วสั่ง apply**
