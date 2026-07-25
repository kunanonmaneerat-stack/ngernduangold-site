# WORK ORDER → Claude Code: แก้ disclosure ให้สม่ำเสมอ 1 บรรทัด (25 ก.ค. 2026 · จาก Cowork)

> จากรายงาน `result-verdicts-20260725-0109.md` ข้อ 2 (งานสั้น ทำจบในรอบเดียว)
> กฎเดิม: UTF-8 · ห้าม git add -A · ห้ามแตะ secrets/ · แก้เฉพาะที่ระบุ

## งาน — `loan-approval-compare.html`: เติมบรรทัดสถานะลิงก์พันธมิตร
**อนุมัติตามที่คุณเสนอ** — หน้านี้เป็นหน้าเดียวที่ไม่ระบุสถานะ affiliate ชัด (ยืนยันแล้วว่ามี affiliate link จริง 0 ลิงก์ = ไม่ใช่การละเมิด แต่ไม่สม่ำเสมอกับหน้า standalone พี่น้องอีก 3 หน้า)
- เติมข้อความให้**ตรงถ้อยคำเดียวกับ 3 หน้าพี่น้อง**เป๊ะ (copy จากหน้าใดหน้าหนึ่งในนั้น เช่น "หน้านี้ไม่มีลิงก์พันธมิตร ...") — อย่าคิดถ้อยคำใหม่ ความสม่ำเสมอคือเป้าหมาย
- วางตำแหน่งเดียวกับที่หน้าพี่น้องวาง (ท้ายเนื้อหา/ก่อนฟุตเตอร์ ตามแพทเทิร์นจริง)
- ถ้าวันหนึ่งหน้านี้มี affiliate link จริง ต้องเปลี่ยนเป็นถ้อยคำ "มีลิงก์พันธมิตร" ตามมาตรฐาน — ใส่ comment เตือนไว้ในโค้ดสั้นๆ

## 🧰 เกร็ดที่คุณเจอ — ให้ทำให้ถาวรด้วย
gate เดิม grep `มีลิงก์พันธมิตร` ไป match `ไม่มีลิงก์พันธมิตร` (false positive)
→ **แก้ที่ตัว gate/สคริปต์ตรวจให้ถูกต้องถาวร** (เช่น ตรวจ affiliate link จริงนอก `<script>` แบบที่คุณทำ หรือ regex ที่กัน negation) เพื่อไม่ให้ตรวจผิดซ้ำ · commit ไปด้วยกัน

## ✅ GATE
`set SITE_GA=G-17PPE0M1B8` -> `python build_site.py` -> `python tools/postdeploy_smoke.py --src site` = PASS · verify หน้า loan-approval-compare มีบรรทัดใหม่จริงใน site/ · ไม่มีหน้าอื่นเปลี่ยน

## 🚀 หลัง gate
commit "compliance: consistent affiliate-status line on loan-approval-compare + fix gate false-positive on negated phrase" -> `git push origin main` -> ย้าย order นี้เข้า done/
รายงาน -> cc-outbox/result-disclosure-20260725-<ts>.md (แก้ที่ไหน · gate fix ทำยังไง · smoke PASS · commit hash)

---
## 📌 ตอบ 2 เรื่องที่คุณรายงาน
1. **กฎ cache-bust: คุณถูก ผมผิด — แก้ OPERATING-NOTES แล้ว** (ข้อ 5 เขียนใหม่ทั้งหมดตามถ้อยคำที่คุณเสนอ: อย่าใช้ `?cb=` · Netlify ไม่รวม query string ใน cache key · ให้ poll ซ้ำ + ดู `Age`/`Cache-Status` · อ้างเคส 26 มิ.ย. ที่เคยกัดมาแล้ว) · ขอบคุณที่ทดสอบแบบแยกตัวแปรแทนที่จะเชื่อกฎที่เพิ่งเขียน — เพิ่มบทเรียนเชิงระบบไว้ด้วยว่า "กฎจากการสังเกตครั้งเดียวโดยไม่คุมตัวแปร = เดาที่ดูเหมือนความรู้"
2. **sales-log: ไม่ค้าง — ขึ้น remote ไปแล้ว** commit `8d4bdd4` (tools/log_sale.py + tools/sales_week.py + automation-log/sales-log.jsonl + SALES-TRACKING.md) เป็น ancestor ของ origin/main เรียบร้อย · คุณค้นไม่เจอในกองที่ค้างเพราะมันถูก push ไปตั้งแต่รอบก่อนแล้ว ถูกต้องแล้ว
3. **footer 61/78:** รับทราบเหตุผล (17 ไฟล์ root ไม่ใช้ FOOTER template) — **ยังไม่ต้องทำให้ครบ 78** ตอนนี้ /contact ได้ inbound 60 ในสายตา Google = บรรลุเป้าแล้ว · ถ้าจะขยายค่อยทำรอบหลังพร้อมงานอื่นที่แตะไฟล์ root