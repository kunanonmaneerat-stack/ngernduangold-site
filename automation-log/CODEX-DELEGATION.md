# กติกามอบงาน Codex (gpt-5.6-terra) — มือปฏิบัติการสำรอง (17 ก.ค. 2026)

เจ้าของสั่ง: ใช้ Codex ให้มากที่สุดเพื่อประหยัด token ของ Cowork และให้ Codex "กดงานแทน" ได้เมื่อ Cowork ทำไม่ได้/ไม่สะดวก

## ลำดับมือทำงาน
1. **ระบบอัตโนมัติ** (scheduled/scripts) — งานประจำทั้งหมด
2. **Codex** — งานไฟล์/สคริปต์/โค้ด/วิเคราะห์ข้อมูลในเครื่อง ทุกอย่างที่สั่งเป็น spec ได้
3. **Cowork** — งานที่ต้องใช้ browser extension (trusted click), วิจารณญาณ, หรือคุยกับเจ้าของ
4. **เจ้าของ** — เฉพาะที่เหลือจริงๆ: โพสต์ Pantip (นโยบาย), ผลิตคลิป, ตอบคอมเมนต์/LINE

## วิธีสั่ง Codex (มาตรฐาน)
1. เขียน spec: `automation-log/_spec_codexN.md` (ไทย UTF-8, ระบุไฟล์ที่แตะได้, เกณฑ์ตรวจรับ, รูปแบบรายงาน)
2. รัน: `tools\codex_run.cmd automation-log\_spec_codexN.md automation-log\_codexN_out.md`
3. ตรวจรับด้วยหลักฐานจริง (validate/compile/run) — อย่าเชื่อรายงานเปล่า

## ขอบเขต "กดงานแทน" ของ Codex บนเครื่อง
- ✅ รันสคริปต์/คำสั่งในเครื่องได้เต็มที่ (PowerShell/py/git อ่าน) รวมสคริปต์ Win32 แบบ tools/picker_fill.ps1
- ✅ แก้ไฟล์ใน repo ตาม spec · รัน validate/test
- ⚠️ งานคลิก UI เบราว์เซอร์ (Threads/Studio/Business Suite) = ของ Cowork ก่อนเสมอ (extension = trusted click) — Codex เป็นตัวสำรองผ่านสคริปต์ Win32 เฉพาะเมื่อ Cowork ติดและมี runbook ชัด
- ⛔ ห้ามตลอดไป: git push · git add -A · แตะ token/secret · โพสต์ Pantip · ลบไฟล์นอก spec · แตะ build_site.py เกิน deliverable

## บทเรียนที่ Codex ต้องรู้ (ใส่ใน spec ทุกครั้งที่เกี่ยว)
- เครื่องนี้ไม่มีคำสั่ง `py` ใน shell ของ Codex → ใช้ `python` (hermes venv)
- console เป็น cp874 → ห้าม print emoji/ไทยตรงๆ ใน python stdout (ใช้ ensure_ascii หรือเขียนลงไฟล์)
- git จะเตือน LF→CRLF = ปกติ ไม่ใช่ error

## กฎเหล็ก 3 จังหวะ (รับจากคู่มือ Fable5+Sol ของเจ้าของ 17 ก.ค. — ตรงกับบทเรียน Codex รอบ 7 vs 8)
1. **วางแผนครั้งเดียว**: Cowork เขียน spec จบในไฟล์เดียว (steps + เกณฑ์ตรวจรับ + edge cases)
2. **มือทำงานลำพัง**: Codex รันจนจบ — **Cowork ห้ามอยู่ใน loop กลางทาง** (ห้าม poll ถี่/สั่งแก้ทีละนิด — แพงและช้ากว่า) spec ใหญ่ให้หั่นเป็น spec เล็กหลายรอบแทน
3. **QA ครั้งเดียวปิดท้าย**: ตรวจรับด้วยหลักฐานจริงรอบเดียวหลังงานจบ
หลักฐาน: รอบ 7 (spec ใหญ่ + poll คั่น) = ~3 ชม. · รอบ 8 (spec เล็ก จบ-รอ-ตรวจ) = 2 นาที

## โควตา
- รอบปัจจุบัน: reset แล้ว (17 ก.ค.) + เจ้าของ reset ได้อีก 1 ครั้ง → ใช้ได้เต็มมือ ใกล้หมดค่อยแจ้งเจ้าของ
