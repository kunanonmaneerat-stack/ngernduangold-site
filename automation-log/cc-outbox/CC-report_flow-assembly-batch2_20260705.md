# CC report — Flow assembly batch 2: 4 _final_ + hold-tl01 (order-assemble-flowbatch2 / order-hold-tl01) — ✅ เสร็จ
executed: 2026-07-05 · zero-budget (ffmpeg local) · ไม่แตะ Pantip/build_site.py/secrets · CC ไม่โพสต์เอง · ใช้กระบวนการเดียวกับ batch 1 เป๊ะ

## 1) watermark — ตรวจ 4/4 (25/55/90%) → ลบเกลี้ยง 4/4
- ลายน้ำ Flow = "✦" ล่างขวา (ตำแหน่งเดียวกับ batch 1) ทุกตัว → ลบด้วย delogo(x545 y1108 w100 h100) + crop 664:1180 → scale 720:1280
- VERIFY bottom-strip @3s: PROOF_batch2_watermark-removed.png = ไม่มี ✦/Veo เหลือ (สำเนาสะอาดเท่านั้นไป _final)

## 2) 4 _final_ (720x1280 · audio คงไว้ · Thai harfbuzz ตรวจ QA_batch2_hooks.png)
| _final_ | ใช้ raw | วัน | hook บนจอ | คอนเทนต์ตรงธีม? |
|---|---|---|---|---|
| _final_tl01b.mp4 | Thai_office_worker_hopeful_smile | 12 ก.ค. | มีรถ = มีทางเลือกหมุนเงิน / รถยังใช้ได้ตามปกติ | ✅ ชายในรถ กังวล→เปิดช่องเก็บของเจอเอกสาร→ยิ้ม (ฉากรถจริง แก้ปัญหา tl01 error) |
| _final_kp05.mp4 | Thai_person_uses_mobile_banking | 16 ก.ค. | เงินสำรองไว้ในที่ถอนไว / ฉุกเฉินเมื่อไหร่ กดใช้ได้ทันที | ✅ หญิงกังวล→แอปธนาคาร→ยิ้ม |
| _final_kp06.mp4 | Person_dropping_coins_into_jars | 18 ก.ค. | ออมทีละนิด ทุกวันเงินเดือนออก / วินัยเล็ก ๆ ที่เปลี่ยนชีวิต | ✅ หยอดเหรียญใส่โหล |
| _final_eb03.mp4 | Thai_person_reading_tablet | 19 ก.ค. | คู่มือ + Worksheet ปลดหนี้ / ทำตามได้ทีละขั้น | ✅ อ่าน e-book บนแท็บเล็ต |
- end-card ทุกตัว (2.8s สุดท้าย, 3 บรรทัดพอดีจอ): ลิงก์ในไบโอ / ngernduangold.com/links (ทอง) / ข้อมูลเพื่อการศึกษา · ผลิตด้วย AI · ไม่มีตัวเลขดอก/ราคาบนจอ

## 3) order-hold-tl01 — EXECUTED ✅
- ถอด _final_tl01 ออกจาก POST-PACK (12 ก.ค. = _final_tl01b แทน) · ย้าย _final_tl01.mp4 + raw_tl01.mp4 → _social-stage/_rejected/ (เก็บไว้ ไม่ลบ + README เหตุผล)
- คลิปใช้ได้จริง: batch1 5 (tl03/tl04/tl05/eb02/kp04) + batch2 4 (tl01b/kp05/kp06/eb03) = **9 ตัว** → คิว 11-19 ก.ค. เต็มครบทุกวันแล้ว

## 4) POST-PACK — 11-19 ก.ค. เต็มครบ · comply_gate 14/14 GATE_OK
11=kp04 · 12=tl01b · 13=tl03 · 14=tl04 · 15=tl05 · 16=kp05 · 17=eb02 · 18=kp06 · 19=eb03 (6-10 = reel เดิม)

## ⚠️ FLAG (ตัดสินใจเอง = assemble ตามสั่ง แต่แจ้ง): kp05 raw ≈ kp04 raw (ไฟล์ซ้ำ)
- Thai_person_uses_mobile_banking (kp05) = **byte-identical (1,996,337 B) กับ raw_kp04** ของ batch 1 → คลิป 11 ก.ค.(kp04) กับ 16 ก.ค.(kp05) = ฟุตเทจเดียวกัน + hook คล้ายมาก (mobile-banking/เงินสำรองถอนไว)
- แม้ห่าง 5 วัน แต่เสี่ยง "คลิปซ้ำ" (post_ledger clip-dedup แยก key อาจไม่จับภาพซ้ำ) → แนะนำ Cowork: สลับ kp05 (16 ก.ค.) ไปใช้ raw kept อื่นในโฟลเดอร์แทน — มีให้เลือก: **Two_coin_stacks_growing** หรือ **Thai_person_sleeps,_money_grows** (ยังไม่ประกอบ) → บอก CC ประกอบทับให้ได้
- CC ประกอบ kp05 ตามที่ order ระบุไว้แล้ว (ไม่ deviate) — รอ Cowork ตัดสินว่าจะสลับไหม

## DoD: _final 4/4 · ลายน้ำเกลี้ยง (proof _wmchk/) · hold-tl01 executed · POST-PACK 11-19 ครบ · comply 14/14 · commit report+order (media local/gitignored)

---
## ADDENDUM — swap _final_kp05 (order-swap-kp05) ✅ เสร็จ
- re-assemble _final_kp05.mp4 ทับ raw ใหม่ **Two_coin_stacks_growing** (2,098,163 B ≠ kp04 → ไม่ซ้ำแล้ว) · content = เหรียญ 2 กองโตขึ้นเรื่อย ๆ = savings growth ตรงธีม
- watermark ✦ ล่างขวา → delogo+crop → **VERIFY bottom-strip เกลี้ยง** (proof: _wmchk/GRID_kp05_coingrowth.png + QA_kp05swap_hook-end.png)
- hook ใหม่บนจอ: "ออมทีละนิด เงินสำรองโตขึ้นเรื่อย ๆ / เริ่มจากก้อนเล็กที่ทำได้จริง" (Thai render ถูก) · end-card เดิม · 720x1280 audio คงไว้
- POST-PACK 16 ก.ค. caption → ธีมออม/เงินโต ("เริ่มจากก้อนเล็ก...โตขึ้นเรื่อย ๆ") · **comply_gate 14/14 GATE_OK**
- kp05-เก่า (mobile-banking = kp04 dup) → _social-stage/_rejected/_final_kp05_mobilebanking-dup.mp4 (เก็บ ไม่ลบ)
- ผล: คิว 11-19 ก.ค. ไม่มีฟุตเทจซ้ำแล้ว (11=kp04 mobile-banking · 16=kp05 coin-growth = คนละคลิป)
