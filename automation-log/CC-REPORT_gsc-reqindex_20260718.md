# CC-REPORT — เร่ง recrawl 2 หน้า SEO Strike (order 18 ก.ค. 2026)

สถานะ: **จบที่แผน B สำเร็จ (DoD ข้อ ข)** · commit `50a5a04` · แผน A ติดข้อจำกัดทางเทคนิคทุกเส้น (รายละเอียดล่าง)

## สรุป 1 บรรทัด

Request indexing ผ่าน UI ทำไม่ได้จากเครื่องนี้โดยไม่ล็อกอินใหม่/ไม่ปิด Chrome → deploy สัญญาณ recrawl ผ่าน sitemap แทน: `<lastmod>2026-07-18</lastmod>` เฉพาะ 2 URL เป้า ขึ้น live ยืนยันด้วย curl แล้ว — **เจ้าของกดมือ 2 นาทีเมื่อสะดวก = เร็วกว่า** (ลิงก์พร้อม copy ด้านล่าง)

## เส้นทางที่ลอง (แผน A) และเหตุที่ติด

| เส้น | ผล |
|---|---|
| A0 Claude-in-Chrome extension (session จริง ไม่ต้องปิด Chrome) | extension ไม่ได้เชื่อมต่อกับ session นี้ (`list_connected_browsers = []`) — ถ้า owner เชื่อม extension ไว้ รอบหน้า CC กดให้ได้เลย |
| A1 CDP port 9222 | ไม่เปิด (ตามคาด) |
| A2 Playwright + สำเนา `Network/Cookies` + `Local State` ไป temp profile | **Chrome ล็อกไฟล์ Cookies แบบ exclusive (WinError 32) ตั้งแต่ขั้น copy** — จบ 1 ครั้งตามกติกา ไม่ escalate (VSS/admin = เกินขอบเขต) |
| A3 ใช้ profile จริง | ต้องปิด Chrome → ห้ามตามออร์เดอร์ (งานเจ้าของเปิด ~10 บาน) |
| ทางเลือก API | Search Console API ไม่มี endpoint สั่ง request indexing (มีแต่ inspect) · Indexing API = ต้องห้ามตามออร์เดอร์/guideline · sitemap ping endpoint = Google ปิดไปแล้ว (2023) |

ไม่มีการแตะหน้า login/รหัสผ่าน/2FA ใดๆ ทุกเส้นทาง ✓

## แผน B ที่ deploy แล้ว

- [build_site.py](../build_site.py) sitemap generator: เพิ่ม `_LASTMOD_MIN` override เฉพาะ 2 URL เป้า = `2026-07-18` แบบ `max(BUILD_DATE, override)` → **self-healing**: deploy ครั้งถัดไป BUILD_DATE แซงเองอัตโนมัติ ไม่ต้องตามถอด
- แก้ด้วย python I/O anchored-replace (byte-safe ไฟล์ไทย) + py_compile ผ่าน
- Gates ก่อน push: build ผ่าน · smoke 67/67 · affiliate 17/17 · commit `50a5a04` = commit เดียวของ push (GOTCHA ครบ)

**ตรวจ live ผ่านแล้ว** (`curl sitemap.xml` หลัง deploy ~15 วิ):

```
<url><loc>https://ngernduangold.com/car-still-installment-loan-2026</loc><lastmod>2026-07-18</lastmod>...
<url><loc>https://ngernduangold.com/credit-card-salary-30000-2026</loc><lastmod>2026-07-18</lastmod>...
count lastmod 2026-07-18 ทั้งไฟล์ = 2 (เจาะจงเป้าเท่านั้น ไม่ bump ทั้งไซต์)
```

- ไม่มี screenshot gsc-reqindex-*.png เพราะไม่ถึงขั้น GSC UI

## ทางมือที่เหลือ (เจ้าของ ~2 นาที — เร็วกว่าทุกวิธี)

1. เปิด https://search.google.com/search-console?resource_id=https%3A%2F%2Fngernduangold.com%2F (บัญชีเดียวกับที่ออก ga4-token)
2. ช่องบนสุด "ตรวจสอบ URL" วางทีละอัน → รอผล → กด **"ขอการจัดทำดัชนี" (Request indexing)**:
   - `https://ngernduangold.com/car-still-installment-loan-2026`
   - `https://ngernduangold.com/credit-card-salary-30000-2026`
3. (แถม 10 วิ) เมนู Sitemaps → submit `sitemap.xml` ซ้ำ 1 ครั้ง — จะเห็น lastmod ใหม่ทันที
4. โควตา ~10 URL/วัน — ใช้แค่ 2

## ข้อเสนอถาวร (ให้ Cowork พิจารณา)

ให้ owner ติดตั้ง/เชื่อม **Claude in Chrome extension** ค้างไว้ 1 ครั้ง → งาน GSC UI ทุกรอบหน้า (request indexing, sitemap resubmit, GA4 UI) CC ทำได้เองบน session จริงโดยไม่แตะรหัสผ่านและไม่ต้องปิด Chrome
