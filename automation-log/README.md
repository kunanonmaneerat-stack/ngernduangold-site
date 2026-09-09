# automation-log — proof-of-run ของ ngernduangold routines

> ⚠️ **LOCAL-ONLY AUTHORITY NOTICE 2026-08-16:** โฟลเดอร์นี้เป็นหลักฐานในเครื่อง ไม่ใช่คำสั่ง commit/push/deploy/notify และไม่ใช่หลักฐานว่างานภายนอกสำเร็จ การส่งออกต้องเป็น owner-controlled action แยกต่างหากตาม `.system_control/role_capabilities.json`

**ทำไมมี:** automation รันบน desktop scheduler และ Windows task บางส่วน โฟลเดอร์นี้บันทึก proof-of-run ในเครื่องเท่านั้น ขณะนี้ทุกช่องมี `publication_authorized=false`; แผนและไฟล์พร้อมใช้ไม่เท่ากับได้รับอนุญาตให้โพสต์

**ดูสถานะล่าสุด:** [`latest.md`](latest.md) — ตาราง last-run + status ต่อ routine
**ประวัติเต็ม:** `YYYY-MM.jsonl` — 1 บรรทัด/รอบ (`{ts, routine, status, summary, metrics}`)

**กฎเหล็ก:** `config ≠ delivered` — `status:registered` = ตั้งไว้แต่ยังไม่ fire; `status:ok` = fire จริงแล้ว (มี ts + summary จากการรันจริง).

**⚠️ repo public:** ห้ามใส่ข้อมูลอ่อนไหว (รายได้/PII/token) ใน log — ใส่ได้แค่ status/count/permalink สาธารณะ.

**Netlify:** ไฟล์เหล่านี้อยู่ repo root → publish=`site/` จึง **ไม่ขึ้นเว็บจริง** (เห็นเฉพาะบน GitHub).

## วิธีให้ routine บันทึกในเครื่อง
```bash
python automation-log/log_run.py --routine <name> --status ok \
  --summary "สรุปสั้น" --metrics '{"key":"val"}'
```
(หรือ `from log_run import log_run; log_run(name,status,summary,metrics)`) ห้าม routine stage/commit/push หรือส่งข้อมูลออกภายนอก
