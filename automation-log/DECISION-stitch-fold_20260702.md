# DECISION — Stitch fold หน้าแรก: DEFER (Cowork ตัดสินตาม owner mandate, 2 ก.ค. 2569)
> ธง CC ค้างตั้งแต่ 22 มิ.ย.: จะเอา preview-home (art-direction/20260622-104514/preview-home.html — redesign dark+gold luxury) merge เข้า build_site.py ไหม

## มติ: ยังไม่ merge — เก็บ preview ไว้ revisit ทีหลัง
เหตุผล (ตามข้อมูลจริง GA4 268 sessions/28วัน):
1. **homepage 139 views → 0 conversion** — หน้าแรกไม่ใช่จุดที่รายได้เกิด · การ convert เกิดที่ /links → Gumroad / affiliate ตรง
2. **คอขวด = reach ไม่ใช่หน้าตา** (verdict dashboard: PROVEN reach คือคอขวด) — เวลา/ความเสี่ยงควรไปที่เพิ่ม reach (คลิป/โพสต์/SEO) ไม่ใช่ปรับ cosmetic หน้าแรก
3. **ความเสี่ยง regression** — ยัด HTML redesign เข้า build_site.py แตะ template หลัก บนหน้าที่ traffic ผ่านน้อย+ไม่ convert = downside > upside ตอนนี้

## เงื่อนไข revisit (เปิดธงใหม่เมื่อ):
- reach ขึ้นจน homepage traffic เริ่มมี conversion intent (affiliate_click จากหน้าแรก > 0 ต่อเนื่อง) **หรือ**
- มี A/B ยืนยันว่า fold ใหม่เพิ่ม click-through ไป /links จริง
- ไฟล์ preview เก็บที่เดิม ไม่ลบ

## CC action: archive ธง fold นี้ออกจาก pending/handoff (ไม่ใช่ backlog ที่ต้องทำ) · ไม่แตะ build_site.py
