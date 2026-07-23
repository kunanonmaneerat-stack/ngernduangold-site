# CC-ORDER: เร่ง recrawl 2 หน้า SEO Strike — Request indexing ใน GSC (18 ก.ค. 2026)

สั่งโดย: Cowork (เจ้าของสั่ง "ให้ CC จัดการเลย") · ต่อเนื่องจาก CC-ORDER_seo-strike (ผ่านตรวจรับ 17/17 แล้ว — ดู automation-log/COWORK-ACCEPT_seo-strike_20260718.md)

## เป้าหมาย
กด "Request indexing" (ไทย: "ขอการจัดทำดัชนี") ใน Google Search Console ให้ 2 URL:
1. `https://ngernduangold.com/car-still-installment-loan-2026`
2. `https://ngernduangold.com/credit-card-salary-30000-2026`

ข้อเท็จจริงที่ยืนยันแล้ว: property `https://ngernduangold.com/` **verified และบัญชี Google ของเครื่องนี้มีสิทธิ์จริง** (gsc_pull.py ดึงข้อมูลผ่าน API สำเร็จ 17 ก.ค. 19:45 ด้วย ga4-token.json) — อย่าเสียเวลาไป verify property ใหม่ ถ้าใน UI ไม่เห็น ให้เช็ค account switcher ก่อน (ต้องเป็นบัญชีเดียวกับที่ออก ga4-token)

## กติกาเหล็ก (เด็ดขาด)
- **ห้ามกรอกรหัสผ่าน / 2FA / recovery ใดๆ ทุกกรณี** — ใช้ session ที่ล็อกอินค้างอยู่แล้วเท่านั้น เจอหน้า login/challenge/"verify it's you" → หยุดเส้นทางนั้นทันที ไปแผนสำรอง
- ห้ามพยายาม bypass bot detection · ห้ามใช้ Google Indexing API กับหน้า content ทั่วไป (ผิด guideline — API นั้นสำหรับ JobPosting/BroadcastEvent เท่านั้น)
- ใน GSC แตะเฉพาะ URL Inspection + ปุ่ม Request indexing (+ Sitemaps ตามข้อ optional) — **ห้ามแตะ Removals / Settings / Users**
- ห้ามปิด/รีสตาร์ต Chrome ของเจ้าของโดยไม่จำเป็น (มีหน้าต่างงานเปิดอยู่ ~10 บาน) — ถ้าเส้นทางที่เลือกจำเป็นต้องปิด Chrome ให้ข้ามไปแผนสำรอง B แทน
- โควตา Request indexing ~10 URL/วัน — เราใช้ 2 พอดี ห้ามยิงเกิน

## แผนหลัก A — Playwright ใช้ session จริง
1. เช็คก่อน: Chrome ของเจ้าของเปิดอยู่ไหม (`tasklist | find "chrome"`)
   - **ถ้าเปิดอยู่**: ห้ามแย่ง profile (มี lock) — ลอง CDP: เช็คว่ามี debug port ไหม (`curl -s http://127.0.0.1:9222/json/version`) · ปกติจะไม่มี → ข้ามไป A2
   - A2: ใช้ Playwright `launch_persistent_context` กับ **โปรไฟล์สำเนา**: copy เฉพาะ `Default/Network/Cookies*` + `Default/Cookies*` ไป temp profile ใหม่ มัก **ไม่พอ** สำหรับ Google (ต้องการ state อื่น) — ลองได้ 1 ครั้ง ถ้าเจอ login wall → แผน B ทันที ห้ามวน
   - **ถ้า Chrome ปิดอยู่**: `launch_persistent_context(user_data_dir="C:\\Users\\nL_ku\\AppData\\Local\\Google\\Chrome\\User Data", channel="chrome", headless=False)` → session ล็อกอินติดมาเอง (เส้นทางนี้เวิร์กสุด)
2. ไป `https://search.google.com/search-console?resource_id=https://ngernduangold.com/` → ยืนยันว่าเข้า property ได้ (เห็น Overview ไม่ใช่หน้า welcome)
3. ช่อง "Inspect any URL" ด้านบน → วาง URL ที่ 1 → Enter → รอผล inspect (อาจ 10–30 วิ) → กดปุ่ม **"REQUEST INDEXING" / "ขอการจัดทำดัชนี"** → รอ dialog ยืนยัน "Indexing requested" → screenshot เก็บที่ `automation-log/gsc-reqindex-1.png`
4. ทำซ้ำกับ URL ที่ 2 → `automation-log/gsc-reqindex-2.png`
5. (optional ถ้าราบรื่น) เมนู Sitemaps → resubmit `sitemap.xml` 1 ครั้ง
6. ปิด context ให้เรียบร้อย — ถ้าใช้โปรไฟล์จริง อย่าทิ้ง process ค้าง (เจ้าของต้องเปิด Chrome ต่อได้ปกติ)

## แผนสำรอง B — สัญญาณ recrawl ผ่าน sitemap (ทำเมื่อ A ติด login/lock)
1. ใน build_site.py หรือ sitemap generator: อัป `<lastmod>` ของ 2 URL เป้าเป็นวันนี้ (ถ้า sitemap ไม่มี lastmod ให้เพิ่มเฉพาะ 2 entry นี้) → build → ตรวจ local → commit + push (Netlify deploy)
2. ตรวจ live: `curl -s https://ngernduangold.com/sitemap.xml | grep -A2 car-still` เห็น lastmod ใหม่
3. หมายเหตุใน report ว่าเจ้าของยังกด Request indexing มือได้ภายหลัง (แนบ 2 URL ให้ copy)

## รายงาน
เขียน `automation-log/CC-REPORT_gsc-reqindex_20260718.md`: เส้นทางที่ใช้ (A แบบไหน/B) · ผลแต่ละ URL · screenshot paths · อุปสรรค · ถ้าจบที่ B ให้ระบุชัดว่า "เจ้าของกดมือ 2 นาทีเมื่อสะดวก = เร็วกว่า"

## Definition of Done
อย่างใดอย่างหนึ่ง: (ก) "Indexing requested" ครบ 2 URL พร้อม screenshot · หรือ (ข) แผน B deploy แล้ว + curl เห็น lastmod ใหม่ + report บอกทางมือที่เหลือ — ห้ามจบแบบไม่มีทั้ง ก และ ข
