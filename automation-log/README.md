# automation-log — proof-of-run ของ ngernduangold routines

**ทำไมมี:** automation รันบน Claude Code desktop scheduler (ไม่ใช่ GitHub Actions — routine ต้องใช้ browser+Postiz/Meta MCP+ไฟล์ local). Cowork มองไม่เห็น scheduler นั้น → โฟลเดอร์นี้คือ **สะพาน** ให้ทุกรอบที่ routine fire ถูกบันทึกลง GitHub (Cowork เปิดดูได้).

**ดูสถานะล่าสุด:** [`latest.md`](latest.md) — ตาราง last-run + status ต่อ routine
**ประวัติเต็ม:** `YYYY-MM.jsonl` — 1 บรรทัด/รอบ (`{ts, routine, status, summary, metrics}`)

**กฎเหล็ก:** `config ≠ delivered` — `status:registered` = ตั้งไว้แต่ยังไม่ fire; `status:ok` = fire จริงแล้ว (มี ts + summary จากการรันจริง).

**⚠️ repo public:** ห้ามใส่ข้อมูลอ่อนไหว (รายได้/PII/token) ใน log — ใส่ได้แค่ status/count/permalink สาธารณะ.

**Netlify:** ไฟล์เหล่านี้อยู่ repo root → publish=`site/` จึง **ไม่ขึ้นเว็บจริง** (เห็นเฉพาะบน GitHub).

## วิธีให้ routine บันทึก (เรียกตอนจบทุกรอบ)
```bash
python automation-log/log_run.py --routine <name> --status ok \
  --summary "สรุปสั้น" --metrics '{"key":"val"}'
git -C C:/Users/nL_ku/ngernduangold-site add automation-log
git -C C:/Users/nL_ku/ngernduangold-site commit -m "runlog: <name>" && git push
```
(หรือ `from log_run import log_run; log_run(name,status,summary,metrics)` แล้ว commit+push)
