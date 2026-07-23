# CC Order — "ขยายตัวชนะ" (data-driven จาก GA4 จริง 10 ก.ค.)
ที่มา: traffic-monitor-20260710-0816 (GA4 จริง) · Cowork ทำ code ไม่ push — **CC implement + build + push + verify**

## ข้อมูลที่ยึด (GA4 จริง — พิสูจน์แล้ว)
- funnel แปลงดี: 321 sessions → affiliate_click 71 = **conv/session 22%** · คอขวด = reach ล้วน
- **หน้าทำเงินสุด: /kept-savings-2026 = 28 views → 26 conv (~93%!)** · /links (26) · /title-loan-2026 (16→10) · /debt-consolidation-2026 (13→3 เท่านั้น)
- own-product sales = 0 → ยืนยันปิด Gumroad→LINE ถูกทาง (แก้ไปแล้ว)
- เป้า: ทุก reach ที่เข้ามา อย่าให้รั่ว → ดันไป winner

## แก้ #1 (คุ้มสุด) — เพิ่ม CTA "เงินสำรองดอกสูง" (/kept-savings) ในเครื่องคำนวณ หลังปลดหนี้
เหตุผล: หน้านี้แปลง ~93% · คนที่เพิ่งเห็น "เดือนปลอดหนี้" คือจังหวะเป๊ะที่จะพูดเรื่อง "กันกลับไปเป็นหนี้ = มีเงินสำรอง"
แทรกใน `#results` **ต่อจาก refiCta** (บล็อกใหม่ สไตล์เขียวอ่อน/แยกจาก refi):
```html
<div class="cta cta-save" id="saveCta">
  <h3>🛡️ ปลดหนี้แล้ว อย่าให้วนกลับ</h3>
  <p>พอเริ่มปลดหนี้ได้ ขั้นต่อไปคือ<strong>กันเงินสำรองฉุกเฉิน</strong>ไว้ในบัญชีที่ถอนได้ไว แต่ได้ดอกสูงกว่าออมทรัพย์ทั่วไป — บิลฉุกเฉินมาจะได้ไม่ต้องกลับไปกู้</p>
  <a class="btn btn-save" href="/kept-savings-2026.html?utm_source=calculator&utm_medium=verdict&utm_campaign=kept_wedge">💰 ดูบัญชีออมดอกสูง สมัครฟรี →</a>
  <small>หน้าปลายทางมีลิงก์พันธมิตร · ข้อมูลเพื่อการศึกษา ไม่ใช่คำแนะนำเฉพาะบุคคล</small>
</div>
```

## แก้ #2 — routing ภายในไป winner จากหน้าทราฟฟิกสูง
- `/links` (hub, 117 views/26 conv): ตรวจว่า **kept-savings + title-loan อยู่ตำแหน่งเด่นบนสุด** (2 ตัวนี้แปลงดีสุด) — ถ้ายังไม่เด่น ให้ดันขึ้น
- ท้ายบทความ debt-cluster 9 หน้า (ที่เพิ่งใส่แบนเนอร์ calculator): เพิ่มลิงก์ contextual ไป **/kept-savings-2026** ("ปลดหนี้แล้วเริ่มเงินสำรองดอกสูง") — เฉพาะที่เข้าบริบท
- หน้า `/debt-consolidation-2026` แปลงต่ำ (3/13) เทียบ title-loan/kept → ตรวจว่า CTA affiliate ในหน้านั้นชัด/อยู่ above fold ไหม

## ก่อน push (ตามมาตรฐานเดิม)
1. `python check_affiliate_links` — kept + ทุกลิงก์ live
2. เปิด calculator: กรอกเลข → refiCta + **saveCta** โผล่พร้อมกัน + ปุ่มถูก utm · ไม่มี JS error
3. comply_gate ผ่าน (ระวัง bare % — อย่าใส่ตัวเลขดอกโต้งๆ) · smoke/link_check · build_site.py ท้ายสุด · push + verify

## บริบทเชิงกลยุทธ์ (ให้ CC เข้าใจว่าทำไม)
funnel พิสูจน์แล้ว 22% conv → เกม 90 วันคือ "หา reach + อย่าให้รั่ว" · SEO striking-distance ยังไม่คุ้ม (impression 1-15) · community (Pantip 16 ก.ค. / FB now) = reach หลัก (human-driven) · งานนี้ = squeeze conversion จาก reach ที่มี
