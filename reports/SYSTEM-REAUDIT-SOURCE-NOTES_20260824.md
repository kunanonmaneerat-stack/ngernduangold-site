# Source notes — re-audit ระบบเงินเดือนสมองทอง 2026-08-24

เอกสารนี้เป็น source notes สำหรับรายงานแบบ interactive เท่านั้น ไม่ใช่ใบอนุญาตโพสต์ ตอบคอมเมนต์ ตั้งเวลา deploy หรือรับรองรายได้

- evidence bundle: `.local-private/runtime/improvement-runs/reaudit-20260823-214659-final`
- observed at: `2026-08-24 04:47 Asia/Bangkok`
- validation: `PASS / VALID_WITH_BLOCKERS`
- maturity score: `49/100` (`raw_score=55` แต่ถูก hard-blocker cap ที่ 49)
- progression: `IMPROVED +9`; criterion ที่ผ่านเพิ่มคือ `revenue_ledger_trusted`
- publication readiness: `BLOCKED`
- growth experiment: `BLOCKED`
- external actions performed in this re-audit: none

## Outcome

ระบบควบคุมภายในและ local release แข็งแรงขึ้นอย่างมีหลักฐาน แต่ยังไม่ควรโพสต์หรือ deploy: 7 placements ใน 48 ชั่วโมงข้างหน้าทั้งหมดเป็น `PLANNED_BLOCKED`; ไม่มีชิ้นใดผ่านครบทุก gate เพื่อเข้าสู่ `READY_FOR_OWNER_APPROVAL`. การบล็อกนี้เป็นพฤติกรรมที่ถูกต้อง ไม่ใช่เหตุผลให้เปลี่ยนสถานะเอง

## Defects found and corrected in this re-audit

1. JSON/ledger readers บางจุดยอมรับ duplicate keys, non-finite numbers หรือ Markdown identity ที่กำกวม — เปลี่ยนเป็น strict, stable, fail-closed readers และเพิ่ม regression tests
2. quota/gap ของ Facebook เคยแยกตาม account ทั้งที่ policy จำกัดตาม channel — แก้ให้ใช้ `policy_channel`; พบ conflict จริง 4 จุดและย้ายเฉพาะ `p2-09..p2-12` จาก 13:10 เป็น 15:50 โดยคง `PLANNED_BLOCKED`
3. Google RSS ตอบ HTTP 200 พร้อม header literal `Content-Type: None` ทั้งที่ body เป็น RSS ถูกต้อง — เพิ่ม fallback แบบแคบที่ผูก exact URL/host/size/hash/XML root; ค่า none/null/unknown แบบอื่นและ non-RSS ยังถูกบล็อก
4. release parser เคยรับ JSON ที่กำกวม — เปลี่ยนเป็น strict loader ที่ปฏิเสธ duplicate keys, NaN/Infinity และ overflow
5. merchant/link gate เคยตรวจ anchor เป็นหลักและพลาด URL ที่ซ่อนใน executable surfaces — เพิ่มการตรวจ iframe/meta/form/object/embed/script/srcdoc/event/javascript, nested template/escape/percent/data และ Unicode/IDNA normalization ภายใต้ขอบเขตแบบ bounded
6. quiz เคยพาไป affiliate route โดยตรง — เปลี่ยนเป็น guide-first และลิงก์ไป internal guide เท่านั้น
7. task-receipt consumer เคยเสี่ยงผูก task/runner/tool ไม่ตรงและตีความ receipt เก่าไม่ชัด — เพิ่ม exact binding, chronology/future/terminal validation และแยก historical diagnostics ออกจาก current control state
8. positive freshness test ผูกกับ live calendar/source snapshot จึงล้มเมื่อหลักฐานหมดอายุอย่างถูกต้อง — เปลี่ยนเป็น frozen fixture และเพิ่ม negative test ว่าการเปลี่ยน bound input ต้องบล็อก โดยไม่ผ่อน guard
9. `pipeline/content_council.py` เปิดไฟล์โดยไม่ปิด 3 จุด — เปลี่ยนเป็น context-managed reads; ResourceWarning check ผ่าน
10. รายงานเก่าที่อ้าง `100/100` และ “ไม่พบข้อบกพร่อง” ถูกทำเครื่องหมาย `SUPERSEDED`; ห้ามใช้เป็นสถานะปัจจุบัน

## Verified current state

| Control | Current evidence | State |
|---|---:|---|
| Local site smoke | 70/70 pages; 110 affiliate buttons | PASS |
| Merchant/offer gate | 16 products; 2 promotions; 110 placements; 98 documents | PASS |
| Media hash + watermark QA | 45 canonical videos + 1 canonical image; 0 findings | PASS technical |
| Privacy | 197 candidate files; 0 findings | PASS |
| Public identity | 76 pages; 161 caption fields; 44 knowledge rows; 10 outward prompts | PASS |
| Manifest | 23 items; 0 errors | PASS |
| Content calendar | 65 placements; 0 publishable; 6 publication blockers; 0 structural findings | BLOCKED |
| Permanent dedup | 90/125 complete (72.0%); 35 incomplete | BLOCKED incomplete history |
| Week exact-copy receipt | 7/7 candidate copy rows still match, but the dated calendar/source bindings changed after the receipt | BLOCKED stale evidence; preserve the old receipt and issue a new version only after the bound inputs stabilize |
| Official sources | 31/31 successful; 12 changed; 0 errors; 31 pending reviews | FRESH_REVIEW_REQUIRED |
| GSC | current 28-day bundle; 23 page rows + 10 query rows | CURRENT |
| GA4 | stale/invalid metadata and untrusted internal-traffic coverage | BLOCKED |
| AccessTrade revenue evidence | current/reconciled; one pending transaction ฿35; paid 0 | CURRENT evidence, zero verified paid revenue |
| Live/local parity | production 0/72 pages match audited release | BLOCKED |
| Release candidate | local archive verified; no deploy | READY LOCALLY, NOT AUTHORIZED EXTERNALLY |

Local release identity: `sha256:c84f4d10be940850979fca5622b5c6544371fadb0f0c36362f31d6289c1a7f59`.

An independent read-only recovery audit found `0/35` remaining dedup rows with an immutable byte-exact local source. The set is 14 YouTube comments with no stored text, 17 social comments with prefix-only text, and 4 manual/descriptor rows. Similar drafts diverge from the recorded prefix and therefore cannot be used. No hash or delivery claim was fabricated; these rows remain fail-closed until exact platform/export evidence is obtained.

Verified candidate archive: `release/candidates/candidate-e12e51343e0c6160508fc08cc4197982b74da38664d3e1fc2c1ac980c87584ba.zip`, SHA-256 `e12e51343e0c6160508fc08cc4197982b74da38664d3e1fc2c1ac980c87584ba`, 139 members, 168,233,209 bytes. This is local evidence, not deployment authority.

## 48-hour state classification

Window: `2026-08-24 04:47` through `2026-08-26 04:47` Asia/Bangkok.

| State | Count | Interpretation |
|---|---:|---|
| READY_FOR_OWNER_APPROVAL | 0 | no placement passes every source, dedup, media, identity, release and authority gate |
| BLOCKED | 7 | Threads 2, Facebook main 2, Facebook page 2 = 1, TikTok 2; all remain `PLANNED_BLOCKED` |
| SKIP | 0 | no 48-hour calendar row is a skip |
| COMPLETED_BLOCKED | 23 historical rows | old blocked slots are retained as history and must not be backfilled |
| RUNNER_FAILED | 0 latest runs | latest daily and weekly receipts both ended normally with blockers; one older 7-day failure remains evidence |
| MISSED | 0 eligible slots | no eligible/publishable slot was missed; Windows Scheduler reports zero missed runs |

The seven blocked placements are `kn-37` on Threads/Facebook, `tt-r14-08` on TikTok, `kn-38` on Threads/Facebook, `p2-11` on Facebook page 2, and `tt-r14-09` on TikTok.

## Runtime and 7-day trend

- Latest `ngernduangold_daily`: `FINISHED / COMPLETED_WITH_BLOCKERS`, 26 steps, `final_rc=2`, normal end
- Latest `ngernduangold_weekly`: `FINISHED / COMPLETED_WITH_BLOCKERS`, 10 steps, `final_rc=2`, normal end
- Windows tasks: both enabled/Ready, exact actions point to `pipeline/run_daily.cmd` and `pipeline/run_weekly.cmd`, `Missed=0`; exit 2 is a safe blocker signal, not proof of runner crash
- 7-day receipt view: 6 observed/6 terminal, 0 stuck, 4 completed-with-blockers, 1 runner-failed, 1 unverified-nonzero
- Trusted 7-day terminal rate remains unavailable because one pre-repair weekly receipt inside the active window has an internally inconsistent step classification; it is preserved as audit evidence and not rewritten
- Error learning: 4 open incidents, 3 recurring, 1 reappeared (`official_source_review` after a valid source refresh), 3 resolved (`gsc_not_current`, `official_source_snapshot_unavailable`, `revenue_ledger_unavailable`)

## Revenue and measurement interpretation

The AccessTrade browser session was used read-only to download the current conversion report. The private receipt is hash-bound and reconciled through 2026-08-24. It shows one `pending` KTC Proud conversion worth ฿35. Pending is not paid revenue, so verified/paid affiliate revenue remains ฿0 and may not be used to select winners or scale. Attribution is merchant-total-only because no sub-id exists.

GSC is current and decisionable for search diagnostics. GA4 is not decisionable because internal-traffic coverage is not trusted across the full 28-day window and its metadata bundle is invalid/stale. Consequently clicks, sessions, timing, channel winners and scale decisions remain blocked.

Merchant runtime scanning is intentionally bounded static analysis. It covers the tested constant/escape/template/percent/data/sink threat model, but it is not a proof of every possible Turing-complete JavaScript dataflow; external publication therefore still requires the independent live/local release and per-piece gates.

## Three highest-priority next actions

1. Owner verifies the private egress identity outside the scheduled task; then Codex may repair GA4 internal-traffic coverage and repull one exact 28-day bundle.
2. Owner reviews the 31 exact official-source claim packets. No source acknowledgement is recorded automatically; only content IDs whose exact source scope passes may progress.
3. Obtain immutable exact platform/export evidence for the 35 legacy dedup rows (or keep them blocked), then complete exact media/listening receipts and the governed live release. Only after production matches the audited candidate can an exact content+caption+media+account+slot packet be requested for owner approval.

## Verification evidence

- full pytest: 579 passed, 318 subtests passed
- pipeline unittest with `ResourceWarning` escalated: 300 passed
- preflight meta-suite: 275 checks, 0 failed
- freshness focused tests: 8 passed
- merchant adversarial suite: 126 passed
- `git diff --check`: no whitespace errors (Windows line-ending warnings only)
- improvement loop validation: `passed=true`, bundle status `COMPLETED_WITH_BLOCKERS`

## Explicitly not touched

No post, comment, reply, like, reaction, social schedule, tracker click, synthetic traffic, source acknowledgement, paid API/LLM call, Google Flow generation, commit, push, deploy, scheduler mutation or external notification was performed.
