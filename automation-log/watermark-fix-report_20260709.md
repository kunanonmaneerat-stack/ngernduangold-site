# Watermark fix report (CC ORDER 2026-07-09) — ✅ T1-T7 ครบ
executed: 2026-07-09/10 · zero-budget (PIL+numpy+ffmpeg) · CC ไม่แตะ IG ✓ · no-bot-post คงเดิม (ไม่ re-enable ig-reels-post/video-post) ✓ · build_site.py ไม่แตะ ✓

## T1 AUDIT — ผลเต็ม: automation-log/watermark-audit_20260709.md
- **FAIL 8**: media/clips ดิบ 7/7 (✦ home zone x79-87% y88-93%) + _vidout/hybrid_debt (✦ ทะลุ scrim ที่ 1080p) · **PASS 24**: reel_* 7, _final_* 16+ebook-promo, clean ใหม่ 5
- หลักฐานเฟรม (กรอบแดง): automation-log/wm-evidence/*.png (18MB — เก็บ local ตาม media policy, ไม่ commit)
- **ROOT CAUSE พิสูจน์แล้ว**: (1) ✦ อยู่ในทุกคลิป Veo ดิบ ตำแหน่ง home คงที่+ดริฟต์เล็ก+กระพริบ (2) scrim _hb_batch เป็นกึ่งโปร่ง (alpha≤0.90) → ลายน้ำทะลุบนฉากสว่าง — ไม่ใช่แค่ "ดริฟต์เหนือแถบ" แต่ "ทะลุแถบ" ด้วย (hybrid_debt = หลักฐาน) (3) verify task เดิมไม่ frame-scan

## T2 PIPELINE FIX — _hb_batch.py
- filter ใหม่: **crop iw:ih*0.87 (ตัดล่าง 13% ของ source)** ก่อน scale → ตัด ✦ ออก "เชิงกายภาพ" (top ของ ✦ = 88.4%h, margin ~1.4%) · scrim เหลือหน้าที่ readability เท่านั้น + คอมเมนต์เหตุผลในโค้ด
- PROOF: title-loan ดิบ (FAIL 30/30) → ผ่าน chain ใหม่ → **PASS 0/30**
- ทางเลือก (a) kinetic-text ถูกใช้เป็นหลักใน T5 (ตามลำดับความชอบของ order)

## T3 QA GATE — tiktok-pipeline/src/qa_watermark.py + test_qa_watermark.py
- detector: NCC template-match รูป ✦ (สังเคราะห์ astroid, ไม่ติด bias พื้นหลัง) + spatial-recurrence (จับการกระพริบ/ดริฟต์) + integral-image normalization · CLI exit 2 = FAIL/บล็อก · --evidence-dir แนบเฟรมพิสูจน์ · รองรับ glob บน cmd
- คาลิเบรตจริง: ✦ score ~0.95 vs คอนเทนต์สว่าง ≤0.69 → THR 0.78 · validate ชุด dirty 7/7 FAIL + clean 22/22 PASS (แยกได้ 100% ทั้งสองชุด)
- **UNIT-PROOF 2/2 PASS** (FAIL fixture = media/clips/title-loan ดิบ · PASS fixture = 07_render kinetic) — commit แล้ว

## T4 WIRE — อุดรูโหว่
- run_daily.cmd: สแกน `_vidout/clean/*.mp4` + `_social-stage/_final_*.mp4` ทุกเช้า — FAIL → เขียน `cowork-inbox/WATERMARK-ALERT.md` (DO NOT POST) · ทดสอบ command จริงแล้ว (ทุก staging PASS = ไม่มี alert)
- runbook `ngernduangold-video-post-verify` แก้แล้ว: เพิ่มข้อ 3 บังคับ frame-scan ด้วย qa_watermark ต่อไฟล์ที่จะโพสต์/เพิ่งโพสต์ + แจ้งดังพร้อมชื่อไฟล์/evidence + กติกา "source ต้องมาจาก _vidout/clean หรือ _final_ เท่านั้น ห้าม media/clips ดิบ"
- no-bot-post: ไม่ re-enable task โพสต์ใดๆ ✓

## T5 RE-RENDER 5 หัวข้อ — ✅ 5/5 PASS gate (kinetic-text 07_render, ไม่มี footage)
_vidout/clean/: reel_title-loan / emergency-fund / compound-interest / save-small / auto-save (-2026_clean.mp4) — 1080x1920, hook+brand+tagline+disclosure ในตัว, ไม่มีตัวเลขดอกเบี้ย, comply_gate GATE_OK ทุก spec+แคปชัน · specs commit ไว้ที่ tiktok-pipeline/drafts/clean-specs-20260709/ · **แคปชันพร้อมโพสต์: automation-log/clean-renders-ready_20260709.md**

## T6 KEEP-LIST verdicts
- **DaRaYRLD80W (e-book)**: source local = _social-stage/ebook-promo-9x16.mp4 → qa_watermark **PASS 0/41 เฟรม** → ✅ **KEEP ยืนยัน**
- **DaBD2iIPWfl (save-first ชาย+เอกสาร)**: ไฟล์ local ที่ map ตรงตัว "ระบุแน่ชัดไม่ได้" (ไฟล์ render ชุดที่โพสต์รอบนั้นถูกล้าง) — แต่ render ที่รอดทุกตัวใน _vidout/_social-stage **PASS หมด** และตัวที่ FAIL มีแค่ดิบ+hybrid_debt (ไม่เคยโพสต์) → ⚠️ **CONDITIONAL KEEP**: แนะนำ Cowork เปิดดูมุมขวาล่างของ reel นี้ในแอปครั้งเดียว (CC ดึงวิดีโอจาก IG ไม่ได้ตามการแบ่งงาน) — ถ้าเห็น ✦ ให้ลบแล้วใช้ reel_save-small/auto-save clean แทน
- kinetic คลัสเตอร์บัตรเครดิต: ไม่มี footage โดยโครงสร้าง → KEEP (ไม่ต้องสแกน)

## ความเสี่ยงคงเหลือ
1) DaBD2iIPWfl รอ Cowork eyeball ครั้งเดียว (ด้านบน) 2) NCC จูนกับ ✦ ตัวปัจจุบัน — ถ้า Google เปลี่ยนดีไซน์ลายน้ำ ต้อง re-calibrate (unit test จะจับ: dirty fixture จะเลิก FAIL) 3) เฟรม sampling fps=3 — sparkle ที่โผล่ <0.3s อาจหลุดเฟรมสุ่ม (ต่ำมาก: กระพริบยาวกว่านั้น) 4) evidence 18MB อยู่ local เท่านั้น (Drive backup ครอบ)
