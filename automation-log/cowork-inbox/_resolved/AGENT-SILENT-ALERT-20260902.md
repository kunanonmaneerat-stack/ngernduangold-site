# 🔴 Claude scheduler มีงานพลาด/ล้มเหลว/ค้าง

เขียนโดย `tools/agent_gap_check.py` จาก Claude scheduler registries เมื่อ 2026-09-02 07:00 Asia/Bangkok

- 18 missed-or-stuck, 0 current runner-failed, 2 last-attempt runner-failed, 0 stuck and 0 completed-blocked; 3 unknown and 0 started-unverified
- current `RUNNER_FAILED`: `0`; latest older attempt `RUNNER_FAILED`: `2`
- ตรวจแบบ read-only จาก registry จริง; ไม่ได้เปิด Claude, Run now หรือแก้ schedule

## งานที่บล็อก
- `cowork/cowork-task-watchdog` — MISSED_OR_STUCK; due `2026-09-01T08:00:00+07:00`; lastScheduledFor `2026-08-30T08:00:00+07:00`; lastRunAt `2026-08-30T08:07:19.131000+07:00`; session `NO_EXPLICIT_ERROR`; last_attempt `COMPLETION_UNVERIFIED`
- `cowork/ngernduangold-weekly-review` — MISSED_OR_STUCK; due `2026-08-31T09:00:00+07:00`; lastScheduledFor `2026-08-24T09:00:00+07:00`; lastRunAt `2026-08-30T01:53:09.964000+07:00`; session `NO_EXPLICIT_ERROR`; last_attempt `COMPLETION_UNVERIFIED`
- `cowork/ngernduangold-channel-heartbeat` — MISSED_OR_STUCK; due `2026-09-01T21:00:00+07:00`; lastScheduledFor `2026-08-30T21:00:00+07:00`; lastRunAt `2026-08-30T21:09:48.536000+07:00`; session `NO_EXPLICIT_ERROR`; last_attempt `COMPLETION_UNVERIFIED`
- `cowork/ngernduangold-uptime-monitor` — MISSED_OR_STUCK; due `2026-09-02T00:00:00+07:00`; lastScheduledFor `2026-08-30T12:00:00+07:00`; lastRunAt `2026-08-30T12:04:24.589000+07:00`; session `NO_EXPLICIT_ERROR`; last_attempt `COMPLETION_UNVERIFIED`
- `cowork/ngernduangold-drive-backup` — MISSED_OR_STUCK; due `2026-09-01T22:00:00+07:00`; lastScheduledFor `2026-08-29T22:00:00+07:00`; lastRunAt `2026-08-30T02:19:06.460000+07:00`; session `SESSION_LIMIT`; last_attempt `RUNNER_FAILED`
- `cowork/ngernduangold-video-post-verify` — MISSED_OR_STUCK; due `2026-09-01T21:30:00+07:00`; lastScheduledFor `2026-08-30T21:30:00+07:00`; lastRunAt `2026-08-30T21:32:32.676000+07:00`; session `NO_EXPLICIT_ERROR`; last_attempt `COMPLETION_UNVERIFIED`
- `cowork/daily-social-post-reminder` — MISSED_OR_STUCK; due `2026-09-01T08:00:00+07:00`; lastScheduledFor `2026-08-30T08:00:00+07:00`; lastRunAt `2026-08-30T08:09:29.294000+07:00`; session `NO_EXPLICIT_ERROR`; last_attempt `COMPLETION_UNVERIFIED`
- `cowork/ngernduangold-fb-evening-safetynet` — MISSED_OR_STUCK; due `2026-09-01T19:00:00+07:00`; lastScheduledFor `2026-08-30T19:00:00+07:00`; lastRunAt `2026-08-30T19:08:31.964000+07:00`; session `NO_EXPLICIT_ERROR`; last_attempt `COMPLETION_UNVERIFIED`
- `cowork/ngernduangold-fb-page-comment-link` — MISSED_OR_STUCK; due `2026-09-01T21:30:00+07:00`; lastScheduledFor `2026-08-30T21:30:00+07:00`; lastRunAt `2026-08-30T21:32:19.533000+07:00`; session `NO_EXPLICIT_ERROR`; last_attempt `COMPLETION_UNVERIFIED`
- `cowork/ngernduangold-post-guard-daily` — MISSED_OR_STUCK; due `2026-09-01T19:25:00+07:00`; lastScheduledFor `2026-08-30T19:25:00+07:00`; lastRunAt `2026-08-30T19:26:58.780000+07:00`; session `NO_EXPLICIT_ERROR`; last_attempt `COMPLETION_UNVERIFIED`
- `cowork/ngernduangold-knowledge-post-noon` — MISSED_OR_STUCK; due `2026-09-01T12:30:00+07:00`; lastScheduledFor `2026-08-30T12:30:00+07:00`; lastRunAt `2026-08-30T12:39:48.376000+07:00`; session `NO_EXPLICIT_ERROR`; last_attempt `COMPLETION_UNVERIFIED`
- `cowork/ngernduangold-fbgroup-listen` — MISSED_OR_STUCK; due `2026-09-01T10:20:00+07:00`; lastScheduledFor `2026-08-30T10:20:00+07:00`; lastRunAt `2026-08-30T10:20:44.401000+07:00`; session `NO_EXPLICIT_ERROR`; last_attempt `COMPLETION_UNVERIFIED`
- `cowork/ngernduangold-funnel-endpoint-check` — MISSED_OR_STUCK; due `2026-08-26T09:40:00+07:00`; lastScheduledFor `2026-08-26T09:40:00+07:00`; lastRunAt `2026-08-30T02:22:04.177000+07:00`; session `SESSION_LIMIT`; last_attempt `RUNNER_FAILED`
- `ccd/ngernduangold-pantip-monitor` — MISSED_OR_STUCK; due `2026-08-31T08:10:00+07:00`; lastScheduledFor `2026-08-28T08:10:00+07:00`; lastRunAt `2026-08-30T01:52:05.105000+07:00`; session `NO_EXPLICIT_ERROR`; last_attempt `COMPLETION_UNVERIFIED`
- `ccd/ngernduangold-delivery-heartbeat` — MISSED_OR_STUCK; due `2026-09-01T08:25:00+07:00`; lastScheduledFor `2026-08-30T08:25:00+07:00`; lastRunAt `2026-08-30T08:29:47.295000+07:00`; session `NO_EXPLICIT_ERROR`; last_attempt `COMPLETION_UNVERIFIED`
- `ccd/ngernduangold-delivery-verify` — MISSED_OR_STUCK; due `2026-09-01T21:13:00+07:00`; lastScheduledFor `2026-08-30T21:13:00+07:00`; lastRunAt `2026-08-30T21:17:26.650000+07:00`; session `NO_EXPLICIT_ERROR`; last_attempt `COMPLETION_UNVERIFIED`
- `ccd/ngernduangold-comment-loop` — MISSED_OR_STUCK; due `2026-09-01T12:47:00+07:00`; lastScheduledFor `2026-08-30T12:47:00+07:00`; lastRunAt `2026-08-30T12:52:41.122000+07:00`; session `NO_EXPLICIT_ERROR`; last_attempt `COMPLETION_UNVERIFIED`
- `ccd/ngernduangold-first-signal` — MISSED_OR_STUCK; due `2026-09-01T12:18:00+07:00`; lastScheduledFor `2026-08-30T12:18:00+07:00`; lastRunAt `2026-08-30T12:24:52.805000+07:00`; session `NO_EXPLICIT_ERROR`; last_attempt `COMPLETION_UNVERIFIED`

## งานที่ยังห้ามสรุปว่า PASS
- `cowork/ngernduangold-agent-auditor` — UNKNOWN; หลักฐานยังไม่พอสำหรับ PASS
- `ccd/ngernduangold-link-health` — UNKNOWN; หลักฐานยังไม่พอสำหรับ PASS
- `ccd/ngernduangold-clicktest` — UNKNOWN; หลักฐานยังไม่พอสำหรับ PASS

## ขอบเขตความจริง
`lastRunAt` พิสูจน์ได้เพียงเริ่มงาน ไม่ใช่เสร็จงาน; งานที่เริ่มแล้วจึงเป็น
`STARTED_UNVERIFIED` จนกว่าจะมี deliverable/receipt ของงานนั้น

## การกู้ระบบอย่างปลอดภัย
1. ตรวจ backlog และแยกงาน read-only ออกจากงานที่โพสต์/ตอบ/เขียนภายนอกก่อน
2. ให้ owner เปิด Claude Desktop และยืนยัน account/plan พร้อมแล้วเท่านั้น
3. ห้าม Run now เหมารวม เพราะ enabled backlog บางงานมี external side effects
4. หลัง cron ถัดไป ตรวจ registry + deliverable ใหม่; ห้ามถือว่าเปิดแอปแล้วเท่ากับสำเร็จ

_ไฟล์นี้จะถูกลบเมื่อ scheduler ไม่มี due slot ที่พลาดและแกนอื่นไม่พบ regression_
