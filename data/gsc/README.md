# GSC CSV fallback (WO-3)
โหมดหลักของ internal_link_sprint.py = GSC live API (ga4-token). ถ้า API ใช้ไม่ได้:
1. GSC → Performance → Search results → ปุ่ม Export (มุมขวาบน) → CSV
2. แตก zip แล้ววางไฟล์ `Queries.csv` ที่โฟลเดอร์นี้ (ตั้งชื่ออะไรก็ได้ .csv)
3. รัน `python tools/seo/internal_link_sprint.py` ใหม่
