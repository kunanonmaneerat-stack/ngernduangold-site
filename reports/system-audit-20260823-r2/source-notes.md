# Source notes — system-audit-20260823-r2

หลักฐานทุกชิ้นเป็น local/read-only เว้นแต่ระบุไว้ ไม่มีตัวเลข analytics หรือรายได้ใดถูกใช้เป็น outcome เมื่อ trust contract ไม่ผ่าน

| Source | ใช้ยืนยัน | ข้อจำกัด |
|---|---|---|
| `.local-private/runtime/improvement-runs/comprehensive-audit-20260823-r6/run.json` | สถานะรอบ, score, incident, validation | private local evidence; ไม่ใช่ public artifact |
| `.local-private/runtime/improvement-runs/comprehensive-audit-20260823-r6/observation.json` | readiness, guard outputs, media, local/live parity, GA4/GSC/revenue/source states | observed analytics ถูก suppress จากการตัดสินเมื่อ untrusted/stale |
| `.local-private/runtime/improvement-runs/comprehensive-audit-20260823-r6/maturity-scorecard.json` | คะแนน 40/100 และเกณฑ์แต่ละมิติ | เป็น provisional daily score ไม่ใช่รายได้หรือ business result |
| `.local-private/runtime/improvement-runs/comprehensive-audit-20260823-r6/validation.json` | `VALID_WITH_BLOCKERS`, guard summary | validation pass หมายถึง bundle ถูกต้อง ไม่ได้หมายถึงพร้อมโพสต์ |
| `.system_control/content_calendar.json` + `tools/content_calendar_guard.py --json` | 65 placements, 0 publishable, 7 blocked ใน 48h, structural 0 | ทุก placement ยัง `PLANNED_BLOCKED`; ห้าม promote |
| `automation-log/knowledge-base/*source-registry.json` + `official-news-snapshot.json` | exact content/source mappings และ source blockers | ไม่มี owner-controlled acknowledgement verifier; snapshot invalid/pending |
| `automation-log/post-ledger.jsonl` + dedup guards | coverage 44/125 และ duplicate group 1 | ledger append-only ไม่ถูกแก้ย้อนหลัง |
| `guard-evidence/subprocess/daily_media_gate-3fbcdba44ff8.txt` | วิดีโอ 24 + ภาพ 1 ผ่าน media/watermark QA | dynamic future assets = 0; ใช้กับไฟล์ canonical ปัจจุบันเท่านั้น |
| `guard-evidence/subprocess/postdeploy_smoke-914aa7f0d098.txt` | local build 70/70, 140 buttons | ไม่พิสูจน์ production |
| `guard-evidence/subprocess/postdeploy_smoke-225a5227f900.txt` | live/release 0/72, 185 buttons และ release drift | เป็น read-only production observation; ไม่ deploy |
| `guard-evidence/subprocess/merchant_offer_gate-81442190f1f1.txt` | 16 products, 2 promotions, 140 placements, 97 documents | ตรวจโครงสร้าง/hash ใน scope; ไม่เปิด tracking redirect หรือสร้าง click |
| Windows `Get-ScheduledTask`/`Get-ScheduledTaskInfo` ณ 23 ส.ค. 14:54 | task Ready, missed 0, last/next run | last result 2 ไม่มี schema-2 receipt เพราะ instrumentation เริ่มหลังรอบเช้า จึงไม่อ้าง terminal reason |
| test runs ในรอบนี้ | tools 172, pipeline 177, preflight 260, publication 40, YT 21 | จำนวนชุดมี overlap บางส่วน จึงไม่รวมเป็น unique grand total |

## Unverified or deliberately withheld

- AccessTrade login ไม่ได้เปิดใช้ในรอบนี้ตาม fence; ไม่มีการเปิด tracker หรือดึง redirect
- paid/verified affiliate revenue เป็น `null` เพราะ coverage stale/unreconciled ไม่ใช่ `0`
- GA4/GSC observed values ไม่ถูกนำมา rank content/channel/timing
- ไม่มี owner approval request เพราะไม่มีชิ้นใดผ่านทุก gate
- ไม่มีการยืนยันว่า Windows last result 2 เป็น business blocker หรือ runner failure จนกว่าจะมี receipt รอบ scheduled ถัดไป

## Read-only/external fences honored

ไม่โพสต์ ไม่ตั้งเวลา ไม่ตอบ/กดไลก์ ไม่ acknowledge source ไม่สร้าง test traffic ไม่ใช้ paid API/LLM ไม่ deploy ไม่ commit/push และไม่แก้ Scheduled Task

