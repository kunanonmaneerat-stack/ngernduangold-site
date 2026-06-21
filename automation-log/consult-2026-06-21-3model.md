# 🧠 3-Model Consult — Traffic→Conversion (2026-06-21)

> **Scope จริงของรอบนี้ (ซื่อสัตย์):** ผมรันจาก **Cowork session** = ทำได้แค่ leg ของ **Opus** + เขียน brief + sync repo.
> ผม **เรียก Gemini/Qwen สดเองไม่ได้** (รันเป็น Python ใต้ env key ของเจ้าของบนเครื่อง Windows) และ **trigger Hermes / CC เองไม่ได้** (อยู่บนเครื่องคุณ).
> engine SKILL / Daily Intent Engine / playbook **ไม่อยู่ใน repo นี้** → ผมอิงจาก ledger (`latest.md`) เป็นหลัก ไม่ re-derive.

---

## A) State snapshot (จาก `automation-log/latest.md` — ไม่ re-derive)

| มิติ | ความจริงล่าสุด | ref |
|---|---|---|
| First signal | affiliate_click **33 lifetime** (TH only, **6 real users**) · **AccessTrade conversion = 0 · revenue = 0 lifetime** · today **2 clicks (−92.59%)** | first-signal 06-20 |
| Link health | affiliate 8/8 OK (atth.me 200 + redirect) | link-health 06-21 |
| Funnel/CRO | ทำครบ: CTA clarity + personalize + microcopy + social-proof(non-fab) + prep-checklist + mobile sticky · Playwright no-regress | cc-conversion-cro 06-20 |
| Quiz | 93→1-3 best-fit + events (start/complete/recommendation_view) + recommend_map · 2Q · hero CTA above-the-fold | funnel-fix / quiz-tune 06-20 |
| Data hygiene | GA opt-out บน localhost/QA → funnel ไม่เพี้ยน · **STANDBY บน money/quiz จน quiz_start ≥ 30–50** | data-hygiene 06-20 |
| Distribution | **bot-posting suspended ตั้งแต่ 06-19** (FB suspension) · FB/IG/YT last-live 06-19 · Threads/TikTok login-wall | delivery-verify 06-20 |
| Qwen | **partial — pending owner PART A (key + setx + restart)** | cc-qwen-setup 06-20 |
| Gemini | free flash live ใน pipeline · scheduler รอ owner env key | free-pipeline 06-18 |

---

## B) Opus leg — diagnosis (ตรงประเด็น)

1. **Constraint ที่ผูกคอ = ปริมาณทราฟฟิก ไม่ใช่ funnel.** 33 clicks lifetime → 0 conversion ใน affiliate สาย loan/card (approval-gated) = **noise ที่คาดได้** ไม่ใช่ CRO พัง. ledger เองสั่ง STANDBY จน quiz_start ≥ 30–50 อยู่แล้ว → **หยุดจูน funnel เพิ่ม** (diminishing returns).
2. **ของจริงที่ไฟไหม้ = distribution ตายตั้งแต่ 06-19.** today 2 clicks (−92.6%) สอดคล้องกับ posting suspended. ไม่มี top-of-funnel = consult/engine ใดก็ไม่มีผล. **นี่คือ P0.**
3. **ช่องโหว่ attribution ที่ยังไม่พิสูจน์:** "conv 0" อาจไม่ใช่แค่ volume น้อย แต่ **sub_id อาจไม่ถึง AccessTrade**. 33 clicks ควรเห็นใน dashboard ฝั่ง AccessTrade — ถ้าไม่เห็น = tracking gap (แก้คุ้มกว่าจูน CTA ต่อ).
4. **Offer×audience:** TikTok cold traffic + loan/card = friction สูง. insurance-travel (MSIG/SCB ต่อ live แล้ว) friction ต่ำกว่า → ใช้ warm-up traffic เทไป low-friction conversion ก่อน.

## B2) Opus — prioritized actions
- **P0 — กู้ distribution:** เคลียร์ FB suspension + เดินช่องที่ไม่ติด login-wall automation · TikTok อัปมือจาก `ready-for-cowork/production-manifest.json` (พร้อมแล้ว 21 clips/captions compliance-pass).
- **P1 — attribution audit:** เช็ก AccessTrade dashboard ว่ารับ 33 clicks + sub_id จริงไหม → ยืนยันว่า 0 conv = volume ไม่ใช่ tracking.
- **P2 — re-route intent:** Daily Intent Engine เล็งทราฟฟิกไป **2–3 offer ที่ convert ง่ายสุด** (insurance-travel + 1 card lifestyle) แทนการกระจายกว้าง. **อย่ากว้าง.**
- **STANDBY (ยืนยันตาม ledger):** ไม่ต้องจูน money/quiz page เพิ่มจน quiz_start ≥ 30–50.

---

## C) Gemini leg — รอ owner relay (คำถามให้ตอบ apples-to-apples)
รัน `pipeline/trend_ingest.py` + (SEO/keyword angle) แล้ว relay:
1. 3 intent/หัวข้อที่ volume กำลังมา (TH personal-finance) — อันไหนคุ้มดันสัปดาห์นี้?
2. ช่องไหนคืน traffic เร็วสุดหลัง suspension (SEO organic vs Threads vs TikTok)?
3. มี keyword low-competition ที่ map กับ offer live (insurance-travel/card-lifestyle) ไหม?

## D) Qwen leg — รอ owner relay (หลังทำ PART A)
รัน `tiktok-pipeline/src/01_research.py → 02_script.py → 03_compliance.py` แล้ว relay:
1. script angle ของ 2–3 priority intent (P2) — hook ไหน compliance-pass + convert?
2. number_warnings[] ที่ต้องเช็กแหล่งจริง?

## E) Synthesis rule (ผมจะ merge ยังไงเมื่อได้ครบ)
ถ่วงน้ำหนัก: **distribution-recovery (Opus) > intent-priority (Gemini) > script-angle (Qwen)**. ทับซ้อน = เลือกตัวที่ไม่ fabricate + อยู่ใน offer ที่ live. Output = 1 prioritized brief ให้ Daily Intent Engine.

---

## F) Owner / CC handoff (สิ่งที่ "ผมทำให้ไม่ได้จากตรงนี้")
1. **Qwen PART A:** `setx QWEN_API_KEY "sk-..."` (openrouter.ai/keys) → ปิด/เปิด terminal ใหม่ → verify `python tiktok-pipeline/src/02_script.py --dry-run` แล้วลองมี key.
2. **Gemini:** ยืนยัน Google AI Studio key อยู่ใน env (free flash).
3. **สั่ง Daily Intent Engine / Hermes:** รันบนเครื่องคุณผ่าน CC (Claude Code) — ผม trigger ข้าม session ไม่ได้.
4. **Relay กลับ:** วางผล Gemini + Qwen ในแชต → ผม synthesize เป็น brief เดียวให้ทันที.
