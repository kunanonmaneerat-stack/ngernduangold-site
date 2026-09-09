# 💰 SALES TRACKING — North Star คือรายได้ที่จ่ายแล้ว

ระบบแยก lifecycle เป็น `pending`, `approved`, `paid`, `rejected`, `cancelled` และ `refunded` อย่างชัดเจน เฉพาะ `paid` เท่านั้นที่นับเป็น North Star; `pending`/`approved` ใช้ติดตามสถานะ แต่ห้ามเรียกเป็นรายได้ ห้ามเลือก winner และห้าม scale

ข้อมูลจริงทั้งหมดต้องอยู่ใต้ `.local-private/runtime/` ซึ่งถูก ignore จาก Git ห้ามใส่ชื่อ เบอร์ อีเมล รหัสดิบของผู้ให้บริการ หรือข้อมูลลูกค้าลง public log

## บันทึก lifecycle ทั่วไป

ใช้กับหลักฐานที่ไม่ใช่ AccessTrade CSV และต้องระบุสถานะทุกครั้ง:

```text
py tools\log_sale.py --event-id <unique-event-id> --sale-id <stable-sale-id> --product affiliate-commission --amount <THB> --fee 0.00 --status pending --source direct --ref <non-PII-provider-ref>
```

- `event_id` ไม่ซ้ำสำหรับแต่ละการเปลี่ยนสถานะ
- `sale_id` คงเดิมตลอด lifecycle เดียวกัน
- การเปลี่ยนจาก `pending` → `approved` → `paid` ต้องเพิ่ม event ใหม่ ห้ามแก้แถวเดิม
- สถานะถอยหลัง, ยอดไม่ตรง, event ซ้ำ หรือ terminal state ที่ถูกนำกลับมาใช้จะถูกปฏิเสธ

## นำเข้ารายงาน AccessTrade

AccessTrade ต้องใช้เส้นทางหลักฐานเฉพาะ ห้ามคีย์ยอดจากหน้าจอเข้า ledger โดยตรง

1. ในหน้ารายงาน conversion ที่ล็อกอินแล้ว เลือก `วันที่เกิดผล`, `สถานะทั้งหมด`, `ทุกแคมเปญ` และช่วงวันที่ที่ต้องการ แล้วดาวน์โหลด CSV โดยไม่คลิกลิงก์ affiliate
2. คัดลอก CSV แบบ byte-exact ไปใต้ `.local-private/runtime/access-trade/raw/` และบันทึก SHA-256/จำนวนแถว
3. สร้าง browser-evidence schema 2 ใต้ `.local-private/runtime/access-trade/evidence/` โดยระบุ URL รายงานทางการ, filter, เวลา Asia/Bangkok, จำนวน conversion, reward THB และ `sub_id_available` ตามจริง ห้ามเก็บ raw ID/PII
4. สร้าง receipt แบบ hash-bound:

```text
py tools\import_accesstrade_csv.py --source <private-raw.csv> --output <private-receipt.json> --expected-raw-sha256 <sha256> --expected-row-count <rows> --browser-evidence <private-browser-evidence.json> --browser-evidence-sha256 <sha256> --coverage-start <YYYY-MM-DD> --coverage-end <YYYY-MM-DD> --extracted-at <ISO-8601+07:00> --verification-mode authenticated_browser_read_only --date-basis effect_date --status-filter ALL --campaign-filter ALL --asserted-conversion-count <count> --asserted-reward-thb <0.00> --sale-id <existing-sale-id> --event-id <existing-event-id> --ledger-ref accesstrade-dashboard-<monYYYY> --channel-source atth --fee 0.00
```

5. ทำ frozen copy ของ `sales-intake.jsonl`, ตรวจ SHA-256 ก่อน/หลัง copy ให้ตรงกัน และบันทึกเวลา freeze
6. Reconcile แบบ atomic โดยส่ง receipt, raw CSV และ browser evidence ที่เป็นชุดเดียวกัน:

```text
py tools\reconcile_sales.py --source <private-frozen-intake.jsonl> --source-system accesstrade-authenticated-export --coverage-start <YYYY-MM-DD> --coverage-end <YYYY-MM-DD> --extracted-at <freeze-ISO-8601+07:00> --expected-sha256 <frozen-sha256> --expected-row-count <rows> --upstream-evidence <private-receipt.json> --expected-upstream-evidence-sha256 <receipt-sha256> --upstream-raw-csv <private-raw.csv> --upstream-browser-evidence <private-browser-evidence.json> --replace
```

ระบบจะเปิดตรวจ CSV/evidence/receipt ซ้ำ, pin hash ของ candidate, ตรวจไฟล์ที่ติดตั้งแล้ว และ rollback หากไบต์หรือ provenance เปลี่ยน Output นอก private runtime จะถูกปฏิเสธก่อนเขียนไฟล์

> Importer รองรับ export 0–1 แถวโดยตรง และรองรับหลายแถวเฉพาะเมื่อมี
> `--row-bindings` พร้อม SHA-256 ของ binding specification schema 1 ซึ่งจับคู่
> `source_row_sha256` กับ `sale_id`/`event_id` แบบหนึ่งต่อหนึ่งครบทุกแถวเท่านั้น
> หาก mapping ขาด ซ้ำ คลุมไม่ครบ หรือไม่ผูกกับ raw CSV ไฟล์เดียวกัน ระบบจะหยุดแบบ fail-closed

## ดูผล

```text
py tools\sales_week.py
py tools\sales_week.py 2026-08-17
```

`sales_week.py` จัดกลุ่มตามวันที่ conversion จึงอาจไม่แสดง pending เก่าที่อยู่นอกสัปดาห์นั้น ส่วน dashboard/learning readiness อ่านทั้ง coverage window และต้องแสดง paid/pending แยกกัน

สถานะ reconcile ล่าสุด ณ 30 ส.ค. 2026 เวลา 21:58 Asia/Bangkok: ช่วง `2026-08-03..2026-08-30` ครบ 28 วัน, schema 5 `CURRENT`, paid 0 บาท/0 รายการ, pending 0 บาท/0 รายการ, conversion ทั้งหมด 0 รายการ, attribution `UNATTRIBUTED / MERCHANT_TOTAL_ONLY`, `page_cta_attribution_ready=false` หลักฐานชุดนี้หมดอายุแบบ exclusive เมื่อ `2026-08-31T00:00:00+07:00`; หลังเวลานั้นต้อง reconcile rolling window ใหม่และห้ามคงคำว่า `CURRENT` หรือแสดง 0 เป็นค่าปัจจุบัน

## ไฟล์สำคัญ

- Intake จริง: `.local-private/runtime/sales-intake.jsonl`
- Ledger ที่ reconcile แล้ว: `.local-private/runtime/sales-log.jsonl`
- หลักฐาน AccessTrade: `.local-private/runtime/access-trade/`
- `automation-log/sales-log.jsonl` เป็น public placeholder เท่านั้น ไม่ใช่สมุดยอดขาย
