# RESULT — แยก clicktest ออกจากสถิติเงิน (order รอบ 6 · 1 ส.ค. 2026)

สถานะ: **เสร็จครบ 5 ขั้น · gate ผ่านทั้ง 4 บรรทัด · พิสูจน์ด้วยตัวเลขทั้งสองด้าน**

## 0 · รับทราบการแก้ `check_policy_dates_in_prompts` — ไม่แย้งสักข้อ

`until` แมตช์ใน **`phase_until`** ซึ่งเป็นชื่อฟิลด์ที่พรอมป์ต*ควรชี้ไป* → พรอมป์ตที่ทำถูกกลับถูกตราว่าผิด
เป็น **บั๊ก substring ตัวที่ 5 ของวัน และอยู่ใน check ที่ผมเขียนขึ้นมาเพื่อจับ drift โดยเฉพาะ** — ผมพลาดกับดักเดียวกับที่ตัวเองเขียนเตือนไว้ในไฟล์นั้น
อีก 3 จุด (ข้าม retired · `_RETIRED` รับมาร์กเกอร์มีของประดับ · `_ABOUT_DRIFT`+`_CH_STATE`) ตรงกับหลักที่เราใช้กับ `check_dead_tooling` อยู่แล้ว **ถูกต้องทั้งหมด**
ที่เทสต์ผมจับ `_CH_STATE` ฝั่ง "กลับมา" ที่หายไปได้ — นั่นคือเหตุผลที่กติกา "เทสต์สองทิศ" มีอยู่ ดีใจที่มันทำงาน

---

## ขั้น 1 · baseline — และตัวเลขขัดแย้งกันตั้งแต่ต้น

| ตัวเลข | ค่า |
|---|---|
| `affiliate_click` ใน GA4 28 วัน (ก่อนแก้) | **9** — direct 2 · chatgpt 2 · pantip 5 |
| clicktest กดกี่ลิงก์ต่อรอบ | **11 เป้าหมาย** (6 หน้า + quiz 4 เส้นทาง + micro-events) — เดิม order ประเมิน ~7 |
| รันจริงกี่รอบใน 28 วัน | **3** (5, 12, 19 ก.ค. — จาก runlog) |
| **คลิกปลอมที่คาดว่าอยู่ในตัวเลข** | **~21–30** |

**21 > 9 — ถ้าคลิกบอทเข้า GA4 หมด ตัวเลขต้องมากกว่านี้** จึงต้องหาความจริงก่อนแก้ ไม่ใช่แก้ตามสมมติฐาน

**สิ่งที่วัดได้จริง (Playwright, context เดียวกับ clicktest เป๊ะ):**
```
user agent : ...HeadlessChrome/148.0.7778.96...      ← GA4 กรอง known bots จาก UA แบบนี้อัตโนมัติ
navigator.webdriver : True
คำขอไป GA4 : POST https://www.google-analytics.com/g/collect?v=2&tid=G-17PPE0M1B8...  (1 คำขอ ต่อการโหลด 1 หน้า)
```
→ **hit ถูกส่งถึง GA4 จริง** แต่ GA4 น่าจะกรองทิ้งที่ฝั่งเซิร์ฟเวอร์ ซึ่งอธิบายช่องว่าง 21 vs 9 ได้พอดี

> **แต่นั่นคือพฤติกรรมที่เราไม่ได้ควบคุม** — พิสูจน์ไม่ได้ว่ากรอง 100% และถ้า Google เปลี่ยนเกณฑ์เมื่อไร เราจะตัดสินใจธุรกิจจากคลิกตัวเองโดยไม่รู้ตัว จึงต้องแก้อยู่ดี

## ขั้น 2 · เลือกวิธี — ปิดที่ต้นทาง (ดีกว่าทั้ง 3 ตัวเลือกใน order)

ตรวจโค้ดแล้วพบว่า clicktest ตรวจผลโดย **wrap `dataLayer.push`** (`add_init_script(WRAP)` — รันก่อน page scripts) ไม่ได้อ่านจาก GA4 เลย
→ **ปิดการส่งออกได้โดยไม่กระทบการตรวจแม้แต่น้อย** ทำสองชั้น:

1. **`window['ga-disable-G-17PPE0M1B8'] = true`** — กลไก opt-out ทางการของ GA · gtag ไม่ยิง hit ออกเลย · **เราควบคุมเอง 100% ไม่ต้องรอใคร**
2. **`traffic_type: 'internal'`** — เผื่อมี hit หลุด GA4 กรองให้อีกชั้น (ต้องเปิด Data Filter ตาม OWNER-CHECKLIST ข้อ 3)

ทำไมไม่ใช้วิธี 1 ของ order เดี่ยว ๆ: `traffic_type` ต้องรอเจ้าของเปิด filter ก่อนถึงจะมีผล · ทำไมไม่ใช้วิธี 3: order เองระบุว่ามันคือ "ลบทีหลัง ไม่ใช่ไม่ปน" — เมื่อปิดที่ต้นทางได้ ก็ไม่ต้องหักย้อนหลังให้ยุ่ง

## ขั้น 3 · พิสูจน์ด้วยตัวเลข — และแยกสองสาเหตุออกจากกัน

**(ก) hit หยุดไหม**
```
คำขอไป google-analytics : 0        ← ก่อนแก้: 1 คำขอต่อการโหลด 1 หน้า
ga-disable flag ติดตั้ง  : True
traffic_type=internal    : True
```

**(ข) clicktest ยังทำงานไหม — สำคัญเท่ากัน** (ถ้าเลขไม่เพิ่มเพราะเครื่องมือพัง = ล้มเหลว)
รัน clicktest ตัวจริง 1 รอบเต็ม: **11/11 หน้า PASS** sub_id ถูกต้องทุกหน้า
```
✅ /links?utm_source=test          sub_id=test_links_kept                      channel=test
✅ /title-loan-2026                sub_id=website_title-loan-2026.html_srisawad channel=website
✅ /credit-card-salary-15000-2026  sub_id=website_salary-15000_krungsri        channel=website
✅ /lifestyle-credit-card-2026     sub_id=lifestyle_..._krungsri               channel=lifestyle
✅ /insurance-compare-2026         sub_id=ins_compare_msig                     channel=ins
✅ /travel-insurance-vacation-2026 sub_id=ins_travelq3_msig                    channel=ins
✅ /quiz x4 เส้นทาง                 sub_id=quiz_*                              channel=quiz
✅ micro-events
```
→ **กรองสำเร็จ และเครื่องมือยังทำงานเต็มที่** — สองอย่างนี้แยกกันแล้วชัดเจน

*หมายเหตุความโปร่งใส:* harness ทดสอบที่ผมเขียนเองรอบแรกจับ event ได้ 0 ทำให้ดูเหมือนพัง — สาเหตุคือผมเดาชื่อฟังก์ชัน interstitial ผิด (`dismiss_interstitial` ทั้งที่จริงคือ `_through_interstitial`) จึงไม่ได้กดผ่าน modal · **เป็นข้อบกพร่องของสคริปต์ทดสอบผม ไม่ใช่ของ clicktest** และเป็นเหตุผลที่ต้องรันตัวจริงเพื่อยืนยัน ไม่ใช่เชื่อ proxy

## ขั้น 4 · `check_synthetic_traffic` — กันไม่ให้เกิดซ้ำ

WARN เมื่อ direct > 50% ของ sessions **และ** `quiz_start` ของ direct = 0
**ผลรันจริงทันที:** `WARN — direct 166 sessions (79%) แต่ไม่มี engagement เลย` ← จับของจริงตั้งแต่รอบแรก
5 เคสทดสอบสองทิศ (ของจริง 1 ส.ค. = WARN · direct ท่วมแต่มี engagement = PASS · direct ไม่ท่วม = PASS · ไม่มี sessions = PASS · ไม่มีไฟล์ = WARN) · **fixture อยู่ใน `tempfile.mkdtemp()`** · เรียกใน `main()` แล้ว (meta-test ยืนยัน 19 checks all wired)

## ขั้น 5 · เตือน weekly-review ล่วงหน้า
เพิ่มหัวข้อแรกใน `ngernduangold-gsc-weekly`: sessions สัปดาห์หน้าจะตกโดยตั้งใจ · ถ้าตก >30% ให้อ่าน `TRAFFIC-DIAGNOSIS_20260801.md` ก่อนสรุปว่าวิกฤต
พร้อมเกณฑ์ตัดสินที่ใช้แทน: **ถ้า sessions ตกแต่ engagement (quiz_start / buy_intent_click) เท่าเดิมหรือดีขึ้น = สะอาดขึ้น ไม่ใช่แย่ลง**

## ✅ Gate
| gate | ผล |
|---|---|
| `preflight.py` | **0 fail** / 4 warn |
| `test_preflight_checks.py` | **138 checks, 0 failed — ALL PASS** (19 checks exercised + wired) |
| `test_post_guard_status.py` | **13 checks, 0 failed** |
| `uptime_check.py --selftest` | **10 cases, 0 failed** |
| คำขอไป GA4 ก่อน/หลัง | **1 → 0** ต่อการโหลดหน้า |
| clicktest หลังแก้ | **11/11 PASS** sub_id ถูกทุกหน้า |
| `_test_*` ค้างใน `tools/` | **ไม่มี** ✓ |
| U+FFFD ในไฟล์ที่แตะ | **0** |

WARN 4: `posting cap` (ประวัติ 31 ก.ค.) · `open decisions` · `sales recorded` · **`synthetic traffic` (ตัวใหม่ — จับของจริง)**

## 📌 ข้อสังเกตที่ตามมาจากงานนี้
`affiliate_click` = 9 นั้น **ส่วนที่เป็นคนจริงน่าจะน้อยกว่า 9** เพราะเราเพิ่งยืนยันว่า hit ของบอทถูกส่งถึง GA4 จริงทุกรอบ (แม้ GA4 น่าจะกรองเกือบหมด แต่ "เกือบ" ไม่ใช่ "ทั้งหมด")
ตั้งแต่วันนี้เป็นต้นไปตัวเลขจะสะอาด — **แต่ตัวเลขย้อนหลังก่อน 1 ส.ค. ควรถือว่ามี noise ปนและห้ามใช้เป็น baseline เปรียบเทียบตรง ๆ** เรื่องนี้สำคัญกับ gate 8 ส.ค. ที่จะอ่านผล 7 วัน: ช่วงข้อมูลนั้นสะอาดทั้งช่วง จึงเทียบกับ 28 วันก่อนหน้าไม่ได้
