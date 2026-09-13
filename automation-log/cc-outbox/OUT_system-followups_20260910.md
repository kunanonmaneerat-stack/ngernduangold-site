# กู้แผนข้อ 2–3 จากรายงานเดิม — 13 ก.ย. 2026

ฉบับนี้กู้เฉพาะแผนที่สูญหาย ตาม SPEC_grok-gate_20260913.md ข้อ 0 ไม่ได้ลงมือแก้ GA4 หรือปลดระวางปฏิทินในรอบนี้

## 2. GA4 internal traffic — แบบเสนอให้ Cowork

ตัดสินใจเสนอ browser flag ต่อ origin/profile แล้วส่ง traffic_type=internal ก่อน gtag config และทุก event; evaluator ต้องผูกหลักฐานกับ browser profile ที่ตรวจจริง รายการ origin รวม www/non-www และเวอร์ชัน tracking code ห้ามสรุปว่าครอบคลุมทุกเบราว์เซอร์จาก localStorage ใน profile เดียว ต้องทดสอบ request ที่ออกจริงใน profile ที่เจ้าของใช้ และตรวจ GA4 Admin ว่า filter Active + Exclude จับค่าเดียวกัน การอ่านไฟล์บนเครื่องเพียงอย่างเดียวพิสูจน์ค่าที่ส่งจริงหรือการตัดทิ้งที่ GA4 ไม่ได้; ส่วนที่ไม่ได้สังเกตเป็น UNKNOWN

coverage ต้องมีทะเบียน profile/origin ที่ใช้จริง, observation เวลาและ hash ของหลักฐาน flag + request + Admin filter, code hash, และสถานะความครบถ้วน เครื่องอื่น/โหมดส่วนตัว/ล้าง storage/เปลี่ยน profile อยู่นอกหลักฐานเดิม หากไม่มีหลักฐานครบให้คง UNTRUSTED และแสดงเฉพาะข้อมูลดิบ ไม่เรียก traffic ว่าลูกค้าจริง

tools/uptime_check.py fetch() ใช้ urllib.request.urlopen อ่าน HTML ไม่ได้รัน JavaScript และไม่ได้เรียก GA4 collect/Measurement Protocol จึงไม่มี GA4 session จากโค้ดเส้นทางนี้ให้กรอง; HTTP access log เป็นคนละอย่าง ห้ามเหมารวมไปถึง browser automation ซึ่งรัน gtag ได้

GA4-COVERAGE-ATTESTATION-CONTRACT.md ควรเพิ่ม schema ใหม่แยก coverage_method=browser_flag จาก IP, bind profile/origin inventory + emitted-parameter evidence + Admin observation + tracking code SHA-256 แทน cidr_set_sha256 ยังคงหลักฐานเก่าแบบ immutable ไม่ backdate หน้าต่าง 28 วันเริ่มเมื่อยืนยันความครอบคลุมและ filter ทำงานครบจริง; reset เมื่อมีช่องโหว่ coverage, profile/origin เพิ่มโดยไม่ยืนยัน, flag หาย, code/filter เปลี่ยนจนหลักฐานใช้ไม่ได้ ไม่ reset เพราะ ISP เปลี่ยนอย่างเดียว Migration ยังเป็นข้อเสนอ ไม่ได้ทดสอบ GA4 สด

Checklist ระหว่างยังใช้ IP:
1. เจ้าของอ่านค่าปัจจุบันจากแหล่ง private ที่เชื่อถือได้ ไม่คัดลอกลงรายงาน
2. เปิด GA4 Admin ของ property/stream ที่ถูกต้อง เพิ่มกฎ /32 ปัจจุบัน
3. ยืนยัน data filter เป็น Active และ Exclude
4. Cowork ตรวจ Admin แบบ read-only และบันทึก observation ใหม่ข้าง private policy พร้อมเวลาจริงและ fingerprint ของ normalized set
5. ผูก observation SHA-256 ตามสัญญาเดิม เริ่มหน้าต่างใหม่จากวันตรวจ แล้วรัน evaluator; ไม่ย้อนวันที่

## 3. ปลดระวาง 64 placements — แผนที่คงประวัติ

ตรึงขอบเขตด้วย placement_id ที่เป็น PAST_PLACEMENT + STALE_SLOT ใน snapshot ที่อนุมัติ 64 ใบ ไม่เลือกใหม่ด้วยเงื่อนไขวันที่ปัจจุบันจนเผลอรวมใบที่ 65; p2-16__facebook_page2 ต้องคงอยู่ แม้วันนี้วันที่ของใบนั้นผ่านแล้ว

ก่อนเปลี่ยนทำ snapshot bytes ทั้ง content_calendar.json พร้อม SHA-256 และตรวจ 64 IDs ตรงชุดที่อนุมัติ/ไม่มีซ้ำ เขียนทะเบียน retirement แบบ append-only มี event_id, recorded_at, authority reference, snapshot SHA-256, placement IDs และเหตุผล โดยไม่ลบหรือแก้ slot ของแถวต้นฉบับ

guard/consumer ต้อง resolve active placements ผ่านทะเบียนที่ตรวจ hash และ ID binding แล้ว; retired ไม่เข้า runway/publishable และไม่สร้าง finding PAST_PLACEMENT/STALE_SLOT/AUTHORITY_STATE_CHANGED แบบ active แต่ยังแสดง retired count/IDs และแหล่งหลักฐาน รายการที่ไม่ผูกหลักฐานต้อง fail closed ไม่เงียบ Dedup และประวัติยังอ่านครบทุกแถวและทุกอายุ

ก่อนใช้งานต้องมี reverse tests: active/retired, hash drift, ID ไม่รู้จัก/ซ้ำ, replay event, ledger dedup ของ retired, ใบที่ 65 ยัง active, snapshot ค้นประวัติได้, finding ที่ต้องหายเหลือ 0 เฉพาะ 64 ใบ; active stale ใบอื่นยังต้องแจ้งตามจริง เพิ่มทะเบียนและ snapshot ในขอบเขต PROTECTED ของ test_sweep แล้วรัน test_content_calendar_guard และ consumer suites ที่เกี่ยวข้อง

ยังไม่สร้างทะเบียนหรือแก้ consumer ในรอบนี้ เพราะสเปกปัจจุบันให้กู้แผนเท่านั้น การดำเนินการจริงต้องใช้ชื่อไฟล์ที่กำหนดแน่นอนในงาน retirement แยก

encoding_probe: 1 file(s) scanned, 0 need a human, 0 BOM-only
