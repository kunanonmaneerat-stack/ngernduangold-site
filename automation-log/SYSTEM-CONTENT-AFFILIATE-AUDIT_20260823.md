# รายงานตรวจระบบคอนเทนต์และ Affiliate — 23 สิงหาคม 2026

สถานะรวม: **VALID_WITH_BLOCKERS / ห้ามเผยแพร่หรือ deploy อัตโนมัติ**

ระบบภายในถูกแก้ให้ใช้ชุดลิงก์ AccessTrade ปัจจุบันและตรวจงานซ้ำ/ความสดใหม่แบบ fail-closed แล้ว แต่เว็บไซต์ production ยังเป็น release เก่าและชุดโพสต์สัปดาห์ใหม่ยังไม่ผ่านทุก gate จึงยังไม่มีชิ้นใดอยู่ใน `READY_FOR_OWNER_APPROVAL` และไม่มีการโพสต์ ตั้งเวลา ตอบคอมเมนต์ เปิด tracker สร้าง test traffic ใช้เครดิต Google Flow commit push หรือ deploy ในรอบนี้

## Executive Summary

- ชุด `week-content-20260824-30-r5` มี 7 candidate, 23 public variants, 7 วิดีโอ และ 4 รูป ตรวจไม่พบ exact/near collision กับข้อความประวัติ 4,508 รายการและ media ประวัติ 67 ชิ้น แต่ผลนี้เป็นหลักฐานแบบ bounded corpus ไม่ใช่การรับรองประวัติทั้งหมด
- permanent dedup ดีขึ้นจาก 57/125 (45.6%) เป็น 90/125 (72.0%) ด้วย append-only bindings ใหม่ 33 รายการ เหลือ 35 แถว prefix-only ที่ไม่มี full exact copy จึงคงเป็น `UNKNOWN` และห้ามเดา
- TikTok `titleloan` ที่ซ้ำในประวัติถูกทำ tombstone แบบ non-reusable แล้ว แต่ไม่ได้แก้หรืออ้างว่า external delivery ของสองแถวเดิมเป็นจริง; สถานะยัง `UNKNOWN_NO_INFERENCE`
- copy ทั้ง 7 ชิ้นเป็น evergreen behavioral exact-copy ไม่มีราคา ดอกเบี้ย เปอร์เซ็นต์ สินค้า merchant โปรโมชั่น tracker หรือคำว่า current/latest; เปลี่ยนแม้แต่ข้อความหรือ pack hash ใด ๆ จะทำให้ freshness receipt ใช้ไม่ได้
- AccessTrade ถูกตรวจจาก publisher dashboard ที่ล็อกอินอยู่: 16 แคมเปญใน registry แบ่งเป็น active/approved 14 และ paused 2 (Kept, Tune Protect Health) ส่วน local generated site ผ่าน 110 affiliate placements และไม่มี paused/legacy tracker literal
- production ยังไม่ทัน local fix: พบ tracker เสี่ยง 5 รหัสบนหน้าสาธารณะ จึงเป็น `BLOCKED_STALE_RELEASE` จนกว่าจะมี owner-approved deploy และ post-deploy smoke
- Google Flow ใช้ได้เฉพาะคิดแนวทาง ภาพอ้างอิงชั่วคราว และ storyboard เพราะ Flow output มี invisible SynthID ตามเอกสาร Google; strict no-watermark policy จึงไม่อนุญาต Flow pixel/audio ใน final asset
- 11 final candidate assets ผ่าน technical origin/hash/visible-watermark QA และยืนยันไม่มี Flow output แต่ยังไม่มี subjective human audio listening
- calendar มี 65 placements และทั้งหมดเป็น `PLANNED_BLOCKED`; 7 placement อยู่ใน 48 ชั่วโมงข้างหน้าและทั้ง 7 ยัง blocked; 23 slot เก่าไม่ใช่ eligible miss และห้าม backfill/rerun

## State classification

| State | จำนวน/ขอบเขต | ข้อสรุป |
|---|---:|---|
| READY_FOR_OWNER_APPROVAL | 0 | ยังไม่มีชิ้นใดผ่าน source, permanent dedup, calendar, authority, live-local release และ exact per-piece approval ครบ |
| BLOCKED | 65 calendar placements | publishable=0; production affiliate ยัง stale; permanent dedup ยัง incomplete |
| SKIP | 4 controls | legacy duplicate queue, Kept affiliate, Tune affiliate และ Flow final media ถูกกันออกตามนโยบาย |
| COMPLETED_BLOCKED | r5 authoring + latest runners | งานตรวจ/แก้ภายในสำเร็จ แต่ gate การเผยแพร่ยังปิด |
| RUNNER_FAILED | 0 current final runs | latest daily/weekly จบ `normal_end`; ประวัติ 7 วันยังเก็บหนึ่ง failure ก่อนซ่อมและหนึ่ง invalid receiptไว้ตามจริง |
| MISSED | 0 eligible publication slots | slot เก่า 23 รายการล้วนเป็น PLANNED_BLOCKED จึงไม่ backfill; Claude/Cowork registry ไม่มีหลักฐาน run ใหม่ตั้งแต่ 18 ส.ค. และจัดเป็น missed-or-stuck เฉพาะ scheduler liveness |

## งานใหม่และการกันโพสต์ซ้ำ

หลักฐาน r5 ปัจจุบันผูกกับ pack SHA-256 `0ACD60E0D44F689841C8AAF2C7AF1ADAADA6A5E03CCCAF87C3B626BE84A21A28`

- candidate id collision: 0
- historical exact text collision: 0
- deterministic near text collision: 0
- historical exact media collision: 0
- deterministic near media collision: 0
- cross-candidate blocking collision: 0
- expected same-candidate channel adaptations และ superseded draft media ถูกแยกจาก independent historical-public collision

ข้อจำกัดยังคงอยู่: 35 legacy rows ไม่มี full exact public copy จึงไม่สามารถประกาศ universal novelty ได้ ระบบจึงใช้ verdict `BLOCKED_SYSTEM_HISTORY_NO_R5_COLLISION_DETECTED` และไม่เปลี่ยนเป็น PASS เอง

## ความสดใหม่ของคอนเทนต์

ชุด r5 ผ่าน `PASS_EVERGREEN_EXACT_COPY` ถึง 30 สิงหาคม 2026 เฉพาะเมื่อ exact copy และ pack hash คงเดิม เนื้อหาไม่อ้างข้อมูลที่เสื่อมตามเวลา จึงไม่ต้องดึงข่าวมาแปลงเป็นข้ออ้างใหม่

ส่วน official-news snapshot รวมยัง stale: 31 แหล่งถูกตั้งค่า, สำเร็จ 30, เปลี่ยน 13, error 1 และรอ owner review 31 รายการ จึงห้าม promote factual calendar content โดยอัตโนมัติ Content calendar guard ประเมิน source-bound content 37 รายการและอนุญาต 0 รายการตาม fail-closed contract

## Affiliate currentness

หลักฐานจาก AccessTrade ใช้วิธีอ่านสถานะแคมเปญและคัดลอก tracker จาก promotion modal โดยไม่เปิด tracker และไม่สร้าง synthetic click

| รายการ | สถานะล่าสุด | การแก้ใน local build |
|---|---|---|
| Active/approved campaigns | 14 | ผูก network + campaign id + tracker tuple และตรวจ 110 placements |
| Kept campaign 955 | PAUSED | เอา affiliate CTA ออก ใช้ direct official fallback และข้อความกลาง |
| Tune Protect Health campaign 890 | PAUSED | เอา affiliate placement ออกจาก generated output |
| AXA PA campaign 653 | APPROVED | เปลี่ยน legacy `go/PhAKgrKX` เป็น tracker ที่ตรวจแล้ว `003ump002a0x` |
| KTC PROUD / HappyCash promo claims | ACTIVE แต่มีเงื่อนไข | gate บังคับ qualifier อยู่ในเอกสารเดียวกับ claim |

ผล local:

- 16 products, 2 promotions, 98 documents
- 110 affiliate placements, 14 unique active trackers
- paused/unregistered/mismatched tracker problems: 0
- Kept direct official fallbacks: 25
- legacy danger literalsใน generated `site/`: 0

ผล production:

- `00d9uk002a0x` — Kept paused
- `00bofm002a0x` — Tune Protect Health paused
- `004brg002a0x` — FWD paused
- `00dayn002a0x` — generic Krungsri mismatch
- `go/sdI3wlH5` — Lady Titanium ยังไม่ผูกกับ registry ปัจจุบัน

จึงห้ามเรียก production ว่าอัปเดตแล้วจนกว่า release จะ deploy และ smoke test ยืนยันหน้า live

## Google Flow และ media policy

Flow ถูกจัดเป็น `IDEATION_STORYBOARD_ONLY` เพื่อใช้เครดิตกับการทดลอง concept, shot list, pacing และ storyboard ที่ไม่เข้า final asset ห้ามนำ Flow pixel/audio มาครอป trace composite หรือ remix ในงานปลายทางภายใต้นโยบาย no-watermark-any-kind

Final route ที่อนุญาตคือ local HTML/SVG/CSS, browser render, FFmpeg และ Windows TTS พร้อม hash-bound receipt, origin attestation และ watermark QA ปัจจุบัน 11/11 assets ผ่าน technical gate และ `contains_flow_pixels=false`, `contains_flow_audio=false`, `synthid_expected=false`

## ความเป็นส่วนตัวและ public identity

- privacy guard ผ่าน 92 candidate files, 0 findings หลังแก้ false positive ของ tracker KTC แบบจำกัดเฉพาะ HTTPS `atth.me` grammar ที่ตรวจได้
- adversarial tests ยืนยันว่าเบอร์โทรจริง, URL host ผิด, HTTP, query/fragment หรือ path ดัดแปลงยังถูกจับแบบ fail-closed
- public identity ผ่านในนามเพจเท่านั้น: 76 pages, 161 caption fields, 44 knowledge rows และ 10 outward prompts

## Calendar และ runner

- 65/65 placements = `PLANNED_BLOCKED`
- 29 placements อยู่ระหว่าง 24–30 สิงหาคม; r5 ยังเป็น replacement candidate และไม่ถูกผูกทับรายการเดิมอัตโนมัติ
- 7 placements อยู่ใน 48 ชั่วโมงข้างหน้า: 24 ส.ค. 3 รายการ และ 25 ส.ค. 4 รายการ; ทุกชิ้นยัง blocked
- 23 historical slots เป็น stale PLANNED_BLOCKED และไม่ถูก backfill/rerun
- latest weekly: FINISHED, 10 steps, final_rc=2, normal_end, `COMPLETED_WITH_BLOCKERS`
- latest daily: FINISHED, 26 steps, final_rc=2, normal_end, `COMPLETED_WITH_BLOCKERS`

## จุดเสี่ยงต่อรายได้

1. production tracker เสี่ยง 5 รหัสยังไม่ถูกปล่อย fix จึงอาจพาผู้ใช้ไปยังแคมเปญ paused หรือ attribution ที่ยืนยันไม่ได้
2. verified affiliate revenue ยัง `UNAVAILABLE / STALE_COVERAGE`; ห้ามตีความเป็นศูนย์และห้ามขยาย volume จากตัวเลขที่ยัง reconcile ไม่ได้
3. GA4 bundle ยัง `UNTRUSTED / INVALID_METADATA`; GSC bundle current แต่ใช้แทน revenue verification ไม่ได้
4. การไม่มี publishable slots ทำให้ไม่มี conversion opportunity ใหม่ แต่การฝืนโพสต์จะเพิ่มความเสี่ยง duplicate, stale claim และ broken attribution

## ลำดับยกระดับสามงานสำคัญ

1. นำ local affiliate repair เข้า owner-approved release แล้วรัน post-deploy smoke แบบไม่สร้าง tracker traffic เพื่อปิด tracker เสี่ยงบน production
2. ปิด 35 dedup UNKNOWN ด้วยหลักฐาน full exact copy ที่พิสูจน์ได้เท่านั้น แล้วกำหนด slot ownership ก่อน bind r5 เพื่อไม่ทับหรือ rerun 29 placements เดิม
3. เคลียร์ content-scoped source review, GA4 metadata และ AccessTrade transaction/revenue reconciliation ก่อนตัดสินใจเพิ่มปริมาณโพสต์หรือย้ายงบ/แรงไปที่ merchant ใด

## Verification

- permanent dedup/tombstone/novelty adversarial tests: 51/51 PASS
- merchant offer gate: 53/53 PASS; generated scope 110 placements PASS
- freshness guard tests: 7/7 PASS; live authoring verdict PASS but publication BLOCKED
- Flow-origin tests: 4/4 PASS; live gate 11 assets PASS
- privacy tests: 15/15 PASS; live scan 92 files PASS
- media publish guard: 10/10 PASS
- public identity tests: 12/12 PASS
- content compliance tests: 4/4 PASS
- affiliate health: 110 links, 0 local problems

## External action attestation

Posts 0, schedules 0, replies 0, likes/reactions 0, tracker clicks 0, test traffic 0, source acknowledgements 0, Flow generations 0, Flow credits 0, commits 0, pushes 0 และ deploys 0

## Evidence index

- `automation-log/WEEK-CONTENT-QA_20260823.json`
- `automation-log/WEEK-CONTENT-FRESHNESS_20260823.json`
- `automation-log/dedup-evidence/WEEK-CONTENT-R5-NOVELTY-RECEIPT_20260823.json`
- `automation-log/dedup-evidence/POST-LEDGER-REMEDIATION-RECEIPT_20260823.json`
- `automation-log/AFFILIATE-CURRENTNESS-RECEIPT_20260823.json`
- `.system_control/merchant_offers.json`
- `.system_control/generative_media_policy.json`
- `automation-log/GOOGLE-FLOW-DECISION_20260823.md`
- `automation-log/media-qa/WEEK-TIKTOK-QUOTE-CANDIDATES_QA_R5_20260823.md`
