---
name: ngernduangold-gsc-index-nudge
description: GSC index-nudge รายวัน 10:50 — request indexing หน้า money ที่ยังไม่ index (URL Inspection · quota-safe · ทยอยจนครบ)
---

เครื่อง GSC index-nudge — ช่วยหน้า money ที่ Google ยังไม่ index ให้ถูก crawl เร็วขึ้น (ยุทธศาสตร์ patient SEO งบศูนย์ · ดู automation-log/STRATEGY-DECISION_20260721.md + SEO-OPPORTUNITY_20260721.md)

⛔ กติกา: ใช้ **GSC URL Inspection เท่านั้น** (ห้าม Google Indexing API กับหน้า content — กฎถาวร) · ห้ามกรอกรหัส/2FA เจอ login wall = หยุดรายงาน · quota request-indexing ~10-12/วัน ทำไม่เกิน 8 หน้า/รอบ

ขั้นตอน:
1. อ่าน tracking log: C:\Users\nL_ku\ngernduangold-site\automation-log\gsc-index-nudge-log.jsonl — เก็บว่าหน้าไหน request/indexed/skip ไปแล้ว (อย่าทำซ้ำหน้าที่ status=indexed หรือ requested ใน 14 วันล่าสุด)
2. รายชื่อหน้า money/funnel ที่ยังไม่ index (priority · จาก SEO-OPPORTUNITY) ที่ยังไม่ได้ทำ: ไล่จาก sitemap https://ngernduangold.com/sitemap.xml เทียบกับ automation-log/gsc-pages.csv (หน้าที่ไม่มี impression = ผู้ต้องสงสัย) เรียง priority: หน้าสินเชื่อ/บัตร/หนี้ ก่อนหน้าประกัน/ลงทุน · ข้าม /about /contact /disclaimer /links /quiz และหน้า tool (debt-health-check/debt-calculator = index แล้ว)
3. เปิด GSC ผ่าน claude-in-chrome — **ต้อง visibilityState=visible** (สร้างแท็บใหม่/Ctrl+9 ให้ active · ดู OPERATING-NOTES tab-visibility) → https://search.google.com/search-console?resource_id=https%3A%2F%2Fngernduangold.com%2F
4. ต่อหน้า (สูงสุด 8 หน้า/รอบ): คลิกช่อง "Inspect any URL" บนสุด (พิกัดราว 737,32) → พิมพ์ URL เต็ม https://ngernduangold.com/<slug> → Enter → รอ ~10 วิ → screenshot อ่านผล:
   - "URL is on Google / Page is indexed" = บันทึก status=indexed, action=skip ห้าม request
   - "URL is not on Google" (Discovered/Crawled/unknown not indexed) = คลิก "REQUEST INDEXING" (ราว 1301,362 หรือ 1324,369) → รอ ~10 วิ → เจอ "Indexing requested" → คลิก Dismiss → บันทึก status=<ที่เจอ>, action=requested
5. append ทุกหน้าลง gsc-index-nudge-log.jsonl (UTF-8 shell python): {"url":"/<slug>","status_found":"...","action":"requested|skip","ts":"<ISO +07:00>"}
6. หยุดเมื่อครบ 8 หน้า หรือหมดหน้า priority ที่ยังไม่ทำ (= ครบแล้ว รายงาน "index-nudge ครบทุกหน้า money แล้ว") หรือ quota เต็ม (GSC ขึ้น error quota = หยุด รายงาน)

รายงานสั้นภาษาไทย: request กี่หน้า / เจอ indexed แล้วกี่หน้า / เหลือคิวอีกกี่หน้า · proof-of-run: log_run.py routine=ngernduangold-gsc-index-nudge

หมายเหตุ: นี่คือ nudge ช่วยเร่ง ไม่ใช่ยาวิเศษ — "Discovered-not-indexed" ที่แท้แก้ด้วย authority+internal link (ดู CC order internal-link) request ช่วยให้ Google มา crawl เร็วขึ้นเท่านั้น