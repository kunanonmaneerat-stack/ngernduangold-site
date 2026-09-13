# ส่งมอบงานโพสต์ให้ Grok bot — บทบาท · หน้าสัมผัส · ข้อห้าม (13 ก.ย. 2026)

> **CODEX REVIEW 2026-09-13 — PREPARED, NOT ACTIVATED.** อ่าน `automation-log/cowork-inbox/CODEX_grok-handoff-review_20260913.md` และ `.system_control/grok_handoff.json` ประกอบฉบับนี้ก่อนใช้ รูทีน 0 เป็น read-only เท่านั้น; ตารางด้านล่างเป็นข้อเสนอ ไม่ใช่ scheduler ที่เปิดแล้ว; `channel_readiness: READY` หมายถึงวางแผนได้ ไม่ใช่อนุมัติโพสต์ `grok_gate.py`, `grok_jobcards.py`, `grok_ingest.py` ที่อ้างเป็นงานออกแบบ ยังไม่พบไฟล์ขณะตรวจ จึงยังไม่มี claim/result transport ที่ทดสอบผ่าน ห้ามใช้ตัวอย่าง JSON หรือ owner_approved=true เป็นหลักฐานอนุมัติจริง ต้องผ่าน private one-time receipt และด่านปัจจุบัน การมอบหมาย Pantip/CC ในเอกสารนี้ไม่เปิดสิทธิ์ที่ policy ปิดอยู่

*คำสั่งเจ้าของ: "ยกโปรเจกต์นี้ให้ Grok ดูแลงานโพสต์ · Cowork จัดบทบาทและส่งมอบให้เก่งสุดเหมาะสุด · มี Codex (astra high) ด้วย · ทำร่วมกันทันที"*

> **หลักการเดียวที่ทุกอย่างในไฟล์นี้ยึด:** Grok เป็น **มือ** ไม่ใช่ **หัว**
> Grok กดโพสต์สิ่งที่ผ่านด่านแล้ว บันทึกผลจริง แล้วรายงาน — ไม่เขียนเนื้อหา ไม่ตัดสินว่าอะไรออก ไม่แก้กฎ
> เหตุผลไม่ใช่ความไม่ไว้ใจ Grok แต่เพราะ**ระบบนี้เคยเสียหายทุกครั้งที่ "มือ" เริ่มคิดเอง** (ledger ที่เชื่อ `lastRunAt` 12 วัน · UNKNOWN ที่ถูกยุบเป็น BLOCKED · attempt ที่ไม่ใช่การจอง)

---

## 1. ใครทำอะไร — ตารางบทบาท

| บทบาท | ทำ | **ไม่ทำเด็ดขาด** |
|---|---|---|
| **เจ้าของ** | อนุมัติชิ้นงานรายชิ้น · ตัดสิน gate ที่มีวันที่ · ถือบัญชีทุกช่อง · GA4 Admin · หมุนคีย์ | — |
| **Grok** — ผู้ปฏิบัติงานเผยแพร่ภายนอก | รับใบงานที่ผ่านด่านแล้ว → **จอง** → กดโพสต์ → **ยืนยันด้วย URL จริง** → รายงานผลตาม schema | เขียน/แก้เนื้อหา · เลือกว่าโพสต์อะไร · แตะรีโป · แตะรหัสผ่าน/token · โพสต์ Pantip · เปลี่ยน BLOCKED เป็นพร้อมเอง · พูดในนามตัวเอง (`forbidden_public_speakers`) |
| **Codex (astra high)** — ด่านและโครงสร้าง | **ด่าน compliance ก่อน Grok หยิบใบงาน** (`tools/grok_gate.py`) · ส่งออกใบงาน (`tools/grok_jobcards.py`) · รับผลเข้า ledger (`tools/grok_ingest.py`) · ดูแล guard/receipt/calendar/เทสต์ · re-activate attestation | อนุมัติแทนเจ้าของ · โพสต์เอง · push |
| **Cowork** — ออกแบบงานและตาราง | ออกแบบรูทีน/ตาราง · รายงานความพร้อม (`channel_readiness`) · ตรวจ audit/ขอบเขต · ประสานสามฝ่าย · สรุปให้เจ้าของ | แก้โค้ดที่ Codex เป็นเจ้าของโดยไม่ส่ง review · เปิดสิทธิ์ช่อง |
| **CC (Claude Code)** | Pantip (เจ้าของสั่งไว้ "Pantip ให้ CC ถือ") · comment loop · heartbeat · งานที่ต้องคุมเบราว์เซอร์บนเครื่องนี้ | โพสต์ช่องที่ยกให้ Grok ซ้ำ |

**Pantip ไม่อยู่ในการส่งมอบนี้** — FINAL WARNING ผิดซ้ำ = แบนถาวร · `publication_authorized=false` จนกว่า review 18 ส.ค. จะปิด · CC ถือต่อ

## 2. เส้นทางของหนึ่งโพสต์ — ใครแตะตรงไหน

```
เจ้าของอนุมัติชิ้นงาน (approval รายชิ้น)
        │
        ▼
Codex: grok_gate.py  ──BLOCKED(ชื่อ field)──▶ หยุด รายงานเจ้าของ
        │ READY                               ──UNKNOWN(ตรวจอะไรไม่ได้)──▶ หยุด ห้ามยุบเป็น BLOCKED
        ▼
Codex: grok_jobcards.py  ──▶  ใบงาน JSON (schema §4) วางที่ handoff ที่ Grok อ่านได้
        │
        ▼
Grok รูทีน 2: ตรวจซ้ำสิ่งที่เปลี่ยนได้ (hash ตรง · slot ยังไม่หมด · โควตาวันนี้)
        │
        ▼
Grok ส่ง CLAIM ก่อนแตะแพลตฟอร์ม  ──▶  Codex: grok_ingest.py เขียนแถว claim ใน ledger (ล็อกกันยิงซ้ำ)
        │  ได้ claim_ack เท่านั้นจึงไปต่อ · ไม่ได้ = หยุด
        ▼
Grok กดโพสต์ → เปิด URL ที่ได้ → เทียบข้อความ/บัญชี/เวลา กับใบงาน
        │
        ▼
Grok ส่ง RESULT (posted+URL | failed+เหตุ | unknown+มองไม่เห็นอะไร)  ──▶  grok_ingest.py เขียนแถวผล
        │
        ▼
Cowork/CC ตรวจกระทบยอดวันถัดไป: URL ยังอยู่ · ledger ครบ · เพดานไม่เกิน
```

**สองกฎที่ทำให้เส้นทางนี้ไม่พัง**
1. **ไม่มี claim_ack = ไม่โพสต์** — เพราะ `attempt` ที่ระบบเก่าใช้ไม่ได้กันยิงซ้ำ (Codex พิสูจน์จาก `post_ledger.py:229` วันที่ 9 ก.ย.) · claim ผ่าน `claim_text_publication` ที่จองภายใต้ lock
2. **นับสำเร็จได้ต่อเมื่อเปิด URL แล้วเห็นข้อความตรงใบงาน** — "ส่งคำสั่งไปแล้ว" ≠ "โพสต์ขึ้นแล้ว"

## 3. ความจริง ณ วันส่งมอบ — อะไรพร้อม อะไรยัง

`python tools/channel_readiness.py --actor grok` (13 ก.ย.):

| ช่อง·ขา | ชั้น 1-6 | หมายเหตุ |
|---|---|---|
| youtube video · facebook text · facebook comment · threads video | ✅ READY | วางแผนได้ |
| facebook video (Reel) | 🔴 owner-only | ไม่ส่งมอบ |
| tiktok · instagram · pinterest | 🔴 state ปิด | รอ gate/การทดสอบของเจ้าของ |
| pantip | 🔴 สิทธิ์ปิด | CC ถือ |

**แต่ใบงานที่ผ่านด่านแล้ว = 0 ใบ** — ปฏิทินมี 65 placements เป็น `PLANNED_BLOCKED` ทั้งหมด (64 ใบหมดอายุ · 1 ใบของ 11 ก.ย. ที่ผ่านไปแล้ว) · ยกกำแพงแล้วแต่**ยังไม่มีของที่อนุมัติแล้วให้กด**
⇒ สัปดาห์แรกของ Grok คือ **รูทีน 0 (พิสูจน์ความสามารถ) + รูทีน 1 (ตรวจความพร้อมทุกเช้า)** · รูทีน 2 (โพสต์) เริ่มวันที่ใบงานใบแรกผ่านด่าน Codex — ไม่ก่อนนั้น

**สิ่งที่ยังไม่รู้และห้ามเดา:** Grok โพสต์ช่องไหนได้จริง · อ่านไฟล์/URL ได้ไหม · ส่งผลกลับทางไหน — รูทีน 0 มีไว้ตอบเรื่องนี้ ไม่ใช่ให้ผมสันนิษฐาน (ผมเคยสันนิษฐานผิดแล้วครั้งหนึ่งเรื่อง Meta token)

## 4. Schema ใบงาน (Codex ส่งออก · Grok อ่าน) — ไฟล์เดียวต่อสล็อต

```json
{
  "job_id": "<placement_id>@<slot ISO Asia/Bangkok>",
  "channel": "threads", "leg": "video", "account": "@ngernduangold",
  "scheduled_at": "2026-09-15T12:30:00+07:00",
  "window": {"not_before": "2026-09-15T12:20:00+07:00", "not_after": "2026-09-15T13:30:00+07:00"},
  "content": {"text": "…ข้อความฉบับสุดท้าย…", "text_sha256": "…", "media_ref": "…", "media_sha256": "…"},
  "disclosure_included": true,
  "gate": {"verdict": "READY", "checked_by": "codex", "checked_at": "…", "checks_sha256": "…"},
  "approval": {"owner_approved": true, "piece_id": "…", "approved_at": "…"},
  "limits": {"posts_per_day": 2, "min_gap_hours": 3, "posted_today_before_this": 0},
  "forbidden_in_text": ["การันตี", "ดอกเบี้ย 0%", "อนุมัติแน่นอน", "199"],
  "report": {"claim_to": "<endpoint/ไฟล์ตาม rutine 0>", "result_to": "<เดียวกัน>"}
}
```
`window.not_after` ผ่านแล้ว = ใบงานตาย ห้าม backfill (กฎเดิมของ calendar guard)

## 5. Schema ผลจาก Grok (Grok ส่ง · Codex ingest)

```json
{"kind": "claim",  "job_id": "…", "at": "…", "text_sha256_seen": "…"}
{"kind": "result", "job_id": "…", "at": "…", "result": "posted|failed|unknown",
 "post_url": "…", "verified": {"url_opened": true, "text_matches": true, "account_matches": true},
 "error": "…", "could_not_see": "…"}
```
`result=unknown` ต้องมี `could_not_see` · `result=posted` ต้องมี `post_url` และ `verified` ครบสามข้อเป็น true · ไม่ครบ = ingest ปฏิเสธ ไม่เขียน posted

## 6. ข้อห้ามที่ไม่ขึ้นกับสิทธิ์ (ใส่ในทุกรูทีนของ Grok แบบคำต่อคำ)

- ห้ามขอ/รับ/พิมพ์ token รหัสผ่าน API key · เจอหน้า login = หยุดและรายงาน
- ห้ามโพสต์ถ้าไม่มี claim_ack · ห้ามโพสต์นอก window · ห้ามเกิน 2/วัน/ช่อง ห่าง <3 ชม.
- ห้ามแก้ข้อความแม้แต่ตัวเดียว — hash ไม่ตรง = หยุด
- ห้ามตัวเลข/การันตีดอกเบี้ย · ห้าม CTA 199฿ (สินค้ายังไม่มีของ) · disclosure ต้องอยู่ครบ
- ห้าม ads/boost/โปรโมตเสียเงินทุกรูปแบบ (zero-budget)
- ห้ามพูดในนาม Grok/AI/agent ใด — ทุกข้อความพูดในนามเพจ
- ห้ามแตะ Pantip · ห้ามแตะ Facebook Reel (ขาของเจ้าของ)
- ห้ามยุบ UNKNOWN เป็น BLOCKED และห้ามยก BLOCKED เป็นพร้อม

## 7. ตารางเวลา (Asia/Bangkok)

| เวลา | ใคร | อะไร |
|---|---|---|
| 07:00 | cron | run_daily (guard · readiness ของระบบ) |
| 08:00 | Codex | `grok_gate` + `grok_jobcards` → วางใบงานของวัน (ถ้ามีชิ้นที่อนุมัติ) |
| 08:30 | Grok รูทีน 1 | ตรวจความพร้อมใบงาน → READY/BLOCKED/UNKNOWN รายใบ |
| 12:30 · 18:30 | Grok รูทีน 2 | สล็อตโพสต์ (สูงสุด 2/ช่อง ห่าง ≥3 ชม. — วัดจาก ledger) |
| 21:00 | Cowork/CC | กระทบยอด: URL ยังอยู่ · ledger ครบ · รายงานเจ้าของบรรทัดเดียวต่อช่อง |
| อาทิตย์ 08:30 | cron | run_weekly (รวม test_sweep) |

## 8. วันที่ 1 — ทำอะไรวันนี้

1. **เจ้าของ:** วางรูทีน 0 ลงหน้า "สร้างรูทีน" ของ Grok (`automation-log/grok-routines/ROUTINE-0_capability-probe.md`) ให้มันรัน 1 ครั้ง แล้วส่งผลกลับมา
2. **Codex (ส่งสเปกแล้ว):** สร้าง `grok_gate.py` · `grok_jobcards.py` · `grok_ingest.py` พร้อมเทสต์ · re-activate receipt attestation
3. **Cowork:** อ่านผลรูทีน 0 → เติมช่อง `report.claim_to/result_to` และรายชื่อช่องที่ Grok เข้าถึงจริงลงใบงาน schema → วางรูทีน 1 · เขียน `publication_control.handover_20260913` ลง policy
4. **ยังไม่มีใครโพสต์** จนกว่าใบงานใบแรกจะออกจาก `grok_gate` ด้วย READY และเจ้าของอนุมัติรายชิ้น

## 9. เกณฑ์ว่าการส่งมอบ "สำเร็จ" — วัดได้ ไม่ใช่รู้สึก

- Grok โพสต์ 10 ใบติดต่อกันโดย ledger มี claim → result ครบทุกใบ และ URL ทุกอันเปิดได้ในการกระทบยอด
- 0 ครั้งที่โพสต์โดยไม่มี claim_ack · 0 ครั้งที่เกินเพดาน · 0 ครั้งที่ hash ไม่ตรง
- ทุก UNKNOWN ของ Grok มี `could_not_see` ที่คนอ่านแล้วรู้ว่าต้องไปดูอะไร
ถึงตรงนั้นค่อยขยายช่อง (IG/Pinterest/TikTok เมื่อ gate ผ่าน) — ไม่ก่อน
