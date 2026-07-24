# 💰 SALES TRACKING — วัด North Star (รายได้จริง) (ตั้งขึ้น 24 ก.ค. 2026)

ยุทธศาสตร์บอกว่า "ยอดขายที่โอนจริง = metric ตัดสิน" — ก่อนหน้านี้วัดด้วยการถามเจ้าของ (มองไม่เห็นเทรนด์) · ตอนนี้บันทึกเป็นระบบแล้ว

## บันทึกทุกดีลที่ปิด (เจ้าของ/Cowork รันหลังปิดการขาย)
```
py tools\log_sale.py --product letter-kit-199 --amount 199 --source line --note "ปิดผ่านแชท"
py tools\log_sale.py --product ebook-59 --amount 59 --source gumroad
py tools\log_sale.py --product affiliate-commission --amount 85 --source fb --note "happycash approved"
```
- `--product`: letter-kit-199 / ebook-59 / affiliate-commission
- `--source`: line / gumroad / fb / fb-page2 / threads / ig / yt / pinterest / pantip / direct / organic
- **ห้ามลง PII ลูกค้า** (ชื่อ/เบอร์/อีเมล) — สคริปต์จะปฏิเสธถ้าเจอเบอร์/อีเมลใน ref/note · บันทึกแค่ สินค้า/ยอด/ช่องที่มา

## ดูสรุปรายสัปดาห์
```
py tools\sales_week.py            # สัปดาห์นี้ (จ.-อา.)
py tools\sales_week.py 2026-07-14 # สัปดาห์ที่คร่อมวันนั้น
```
→ โชว์ จำนวนดีล · รายได้รวม · แยกตามสินค้า · แยกตาม channel_source (รู้ว่าเงินมาจากช่องไหน)

## อยู่ไหน
- ข้อมูล: `automation-log/sales-log.jsonl` (tracked ใน git = สำรองบน GitHub)
- weekly-review (จันทร์) ดึง sales_week.py อัตโนมัติในหัวข้อ North Star แล้ว
