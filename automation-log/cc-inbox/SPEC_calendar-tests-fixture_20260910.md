# SPEC → Codex — แก้ 13 เทสต์แดงใน `test_content_calendar_guard.py` ตามที่คุณเสนอเอง (10 ก.ย. 2026 เย็น)

คุณวินิจฉัยไว้ใน `OUT_review-exit2_20260910.md` ข้อ 3: เทสต์อ่าน **policy จริง** แต่ตรึงเวลา 16 ส.ค. · การยกสิทธิ์ 9 ก.ย. จึงฉีด `AUTHORITY_STATE_CHANGED` 65 รายการเข้าทุก "fixture" · คำแนะนำของคุณคือ **แก้ fixture ให้แยกจาก live policy ทั้ง 13 ข้อ ไม่ลบ ไม่เปลี่ยน expected เพื่อให้เขียว** — เห็นด้วย ให้ลงมือ

## ขอบเขต
- แก้ได้: `tools/test_content_calendar_guard.py` และไฟล์ fixture ใหม่ที่คุณสร้าง (ถ้าต้องมี ให้อยู่ใต้ `tools/fixtures/` และตั้งชื่อให้รู้ว่าเป็นของเทสต์นี้)
- **ห้ามแตะ** `tools/content_calendar_guard.py` (เว้นแต่พบบั๊กจริง — ถ้าพบให้รายงานแยก ไม่แก้ในงานนี้) · `.system_control/*` · `pipeline/*`
- ห้าม git push · ห้าม git add -A · ห้ามลบไฟล์ · UTF-8 เท่านั้น · รัน `tools/encoding_probe.py` ปิดท้าย

## เงื่อนไขผ่าน
1. `python -X utf8 -B tools/test_content_calendar_guard.py` จาก repo root ต้องได้ **102/102** — ถ้าข้อไหนทำไม่ได้ให้เขียน `UNKNOWN` พร้อมเหตุ ห้ามลบเทสต์เพื่อให้ตัวเลขสวย
2. เทสต์ต้อง **ไม่อ่าน `.system_control/policy.json` หรือ `content_calendar.json` จริง** สำหรับ 13 ข้อนี้ — fixture ต้องคงที่ ไม่งั้นการเปลี่ยน policy ครั้งหน้าจะทำให้แดงอีกโดยไม่มีใครรู้ว่าเพราะอะไร
   ข้อยกเว้น: เทสต์ที่**ตั้งใจ**ตรวจ policy จริง (เช่น `CalendarGuardFixTests.test_live_authority_rejects_authorized_testing_blocked_tiktok`) ให้คงไว้และระบุในชื่อว่าเป็น live
3. เพิ่มเทสต์ 1 ข้อที่พิสูจน์ว่า fixture ไม่ผูกกับ live: เปลี่ยน `publication_authorized` ของช่องใดช่องหนึ่งใน policy จริงในหน่วยความจำ (patch ไม่ใช่เขียนไฟล์) แล้ว 13 ข้อนี้ต้องให้ผลเดิม
4. `tools/test_sweep.py --only test_content_calendar_guard` ต้องรายงาน `FIXED` (คือชุดกลายเป็นเขียว) — Cowork จะเอาออกจาก baseline เอง

## เอาต์พุต
`automation-log/cc-outbox/OUT_calendar-tests-fixture_20260910.md` · ผลก่อน/หลัง · รายการ 13 ข้อกับสิ่งที่เปลี่ยนในแต่ละข้อ (บรรทัดเดียวต่อข้อ) · `UNKNOWN` ที่เหลือถ้ามี

---

## ภาคผนวก (เพิ่มเย็น 10 ก.ย.) — งานคลาสเดียวกันอีก 8 ชุด ให้ทำในงานเดียวกันหรือแยกก็ได้ แต่ต้องตอบทุกชุด

`tools/test_sweep.py` (รันบน `.venv` ตัวเดียวกับ cron · มี fence กันเทสต์เขียนทับไฟล์จริง) รายงาน:

### ก. เขียนทับไฟล์จริงของรีโป — 2 ชุด (fence จับได้ กู้คืนแล้ว แต่ต้องแก้ที่ต้นเหตุ)
- `tools/test_external_notification_safety.py`
- `tools/test_scheduled_llm_safety.py`
ทั้งคู่เขียน `.system_control/content_calendar.json`, `content_manifest.json`, `automation-log/post-ledger.jsonl` **ของจริง**
ต้นเหตุน่าจะอยู่ที่ `tools/test_content_novelty_queue.py:81` — `_fixture_registry()` ใช้ `dispatcher.ROOT.resolve()` โดยไม่ patch ROOT ก่อน
วันนี้มันลบ placement 65 ใบ และ ledger 177 แถวจริงไประหว่างสแกน (กู้จาก git ได้เพราะไม่มี uncommitted change — ครั้งหน้าอาจไม่โชคดี)
**ต้องแก้ให้ fixture อยู่ใน temp เท่านั้น** และ sweep จะไม่นับชุดที่ยังแตะไฟล์จริงเป็นเขียว

### ข. แดงโดยไม่ได้เกิดจากการเปลี่ยนโค้ด/policy วันนี้ — 6 ชุด (bisect แล้ว: revert ทีละไฟล์ก็ยังแดง)
- `pipeline/test_facebook_story39_recovery_guard.py`
- `pipeline/test_post_ledger_collision_tombstone.py`
- `pipeline/test_post_ledger_identity_bindings.py` (`test_33_only_one_unproven_legacy_row_remains_blocked`: 'PASS' != 'INVALID')
- `tools/test_next48_owner_decision_packet.py`
- `tools/test_post_ledger_completeness.py` ("current ledger reports its incomplete history instead of passing")
- `tools/test_week_candidate_manifest_guard.py`
เขียวตอน 08:00 · แดงตอนบ่าย บนทั้งสอง interpreter · revert `policy.json` / `content_calendar_guard.py` / `preflight.py` / `improvement_loop.py` ทีละไฟล์ก็ยังแดง
**สมมติฐานที่ยังไม่พิสูจน์ (ระบุว่าเดา):** อ่านข้อมูลจริง (calendar/ledger) ร่วมกับเวลาจริง — วันที่เดินไปข้างหน้าทำให้ window (next48 / week / recovery) เปลี่ยน
ขอให้ **หาสาเหตุจริง** ทีละชุด ถ้าเป็นการผูกเวลาจริง ให้ตรึง `now` ใน fixture เหมือนข้อหลัก ถ้าเป็นบั๊กจริงในโค้ด ให้รายงานแยก ห้ามเดา

### ค. ที่รู้แล้วว่าเป็นอย่างอื่น — ไม่ต้องทำในงานนี้
- `tools/test_request_retirement.py` — `NoveltyIntegrityError("draft fulfilment receipt exact schema is invalid")` ใน `dispatcher.py:2058` เป็นเรื่อง dispatcher
- `tools/test_content_novelty_p1.py` · `tools/test_content_novelty_queue.py` · `pipeline/test_improvement_loop.py` · `tools/test_predeploy_acceptance.py` — แดงก่อนวันนี้
- `tools/test_week_content_r5_novelty_guard.py` — numpy บน `.venv` ให้ตรวจว่าจริงไหม (บน hermes venv ไม่มี numpy แน่ แต่ `.venv` ควรมี)

เงื่อนไขผ่านของภาคผนวก: `python tools/test_sweep.py` (จาก `.venv`) ต้องรายงาน `FIXED` สำหรับชุดที่แก้ และ `mutated` ต้องเป็น 0
