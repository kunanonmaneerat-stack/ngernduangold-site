# CC ORDER — Watermark fix + QA gate (ngernduangold IG reels)
Issued by: Cowork · Date: 2026-07-09 · Priority: HIGH · Repo: C:\Users\nL_ku\ngernduangold-site
(This is the CONSOLIDATED order; it supersedes all earlier drafts/appends of this file.)

## TL;DR (ไทย)
reel เก่าบางตัวมีลายน้ำ Veo (✦ sparkle) หลุด เพราะแถบ scrim ทับล่างแบบ "คงที่" แต่ลายน้ำมัน "ลอย/ดริฟต์" ขึ้นเหนือแถบในบางเฟรม. Cowork ลบไปแล้ว 5 ตัวที่เห็นลายน้ำชัด (ยืนยันด้วยตา). งาน CC 7 ข้อ: (1) frame-scan หาหลักฐาน root cause (2) แก้ pipeline ให้ render สะอาดจริง (3) สร้างตัวตรวจลายน้ำ (QA gate) (4) ผูก gate เข้า run_daily + task ตรวจรายวันที่มีอยู่ (อุดรูโหว่) (5) re-render 5 หัวข้อที่ลบให้สะอาด (6) frame-scan ยืนยัน 2 ตัว footage ที่เก็บไว้ (7) รายงานกลับ + วาง clean render ให้ Cowork โพสต์. **ห้ามแตะ reel สะอาดใน KEEP-LIST. ห้าม re-enable บอทยิง reel. CC เท่านั้นที่ push git; Cowork ไม่ push. Cowork เท่านั้นที่ล/โพสต์ IG.**

## GUARDRAILS (บังคับ)
- Division: Cowork = โพสต์ social + คุมเบราว์เซอร์ + ลบ/โพสต์ IG. CC = render/แก้ pipeline/แก้ scheduled task/commit+push git. CC ห้ามโพสต์หรือลบ IG เอง.
- ZERO watermark: ห้าม render/ส่งต่อ/โพสต์คลิปใดที่มี Veo ✦ ในบริเวณที่ไม่ถูกทับ เด็ดขาด.
- KEEP-LIST: ห้ามลบ/แทนที่ตัวใน KEEP-LIST เว้นแต่ frame-scan ของ CC "พิสูจน์" ว่ามีลายน้ำ — และถ้าเจอ ให้แจ้ง Cowork มาลบ/สลับ (CC ไม่แตะ IG เอง).
- no-bot-post policy คงเดิม: ห้าม re-enable task ig-reels-post / video-post (บอทยิง = ต้นเหตุ shadowban). Cowork โพสต์แทนมือ 1/ช่อง/วัน.
- disclosure ("ผลิตด้วย AI" + affiliate) + hook + 1080x1920 ต้องอยู่ครบทุก render.
- ห้ามใส่ตัวเลข/การันตีดอกเบี้ยในคอนเทนต์. build_site.py ถ้าแตะ = push แยกท้ายสุด (Netlify ignore) — ปกติงานนี้ไม่ต้องแตะ.

## BACKGROUND — เกิดอะไรขึ้น
- Source footage: media/clips/*-2026.mp4 = คลิป Google Flow (Veo). แต่ละไฟล์มี sparkle watermark (✦) ที่ "เคลื่อนที่/ดริฟต์" อยู่โซนขวาล่างค่อนกลาง.
- pipeline รายวันเอาแถบ scrim ทึบล่างแบบคงที่ (~30-38% ล่าง, _hb_batch.py) ไปทับ — ล้มเหลว เพราะ ✦ ดริฟต์ขึ้นเหนือแถบในบางเฟรม จึงโผล่.
- ผล: reel IG หลายตัวโชว์ลายน้ำ. Cowork ลบ 5 ตัวที่ชัดแล้ว (ดู INVENTORY).
- รูโหว่: task ตรวจรายวัน ngernduangold-video-post-verify ควรจับ "ไม่มีลายน้ำ" แต่จับไม่ได้ = มันไม่ได้ frame-scan จริง (น่าจะเช็กแค่ชื่อไฟล์/ขนาด/hook). ต้องอุด.

## INVENTORY
### DELETED โดย Cowork (เห็น ✦ ชัด) -> ต้อง RE-RENDER สะอาด (T5)
1. title-loan            (เดิม reel/DaVOfQJAONJ, 58v)
2. emergency-fund        (เดิม reel/DaSpoCiCdsf, 11v)
3. compound-interest / save-early   (เดิม reel/DaQEz5gDhMw, 0v)
4. save-small (5-10%) / jars        (เดิม reel/DaNgCXMD60V, 54v)
5. auto-save / loan-doc  (เดิม reel/DaK7OE5lCGy, 3v)

### KEEP-LIST -> ห้ามแตะ เว้นแต่ frame-scan พิสูจน์ลายน้ำ
- reel/DaBD2iIPWfl  save-first (ชาย+เอกสาร, 13v) — เจ้าของยืนยันว่าสะอาด. FRAME-SCAN ยืนยัน (T6). ถ้าสะอาด = ปล่อยไว้.
- reel/DaRaYRLD80W  e-book launch (59฿, 35v) — footage + end-card สะอาด. FRAME-SCAN เฉพาะช่วง footage (T6). ถ้าสะอาด = เก็บ.
- reel kinetic-text พื้นดำ คลัสเตอร์บัตรเครดิต (5v/9v/15v/81v/84v) — ข้อความล้วนจาก 07_render ไม่มี footage ไม่มีลายน้ำ = ปล่อยไว้.

## TASKS

### T1 — AUDIT (frame-scan ทุกไฟล์ + สร้างหลักฐาน)
- รวบรายการ mp4 ทั้งหมดที่ pipeline โพสต์ได้: _vidout/*.mp4, _vidout/**/*.mp4, media/clips/*-2026.mp4, และไฟล์ reel ที่เคยโพสต์ (ถ้ามีสำเนา local).
- แต่ละไฟล์: ดึงเฟรมด้วย ffmpeg ทั่วทั้งความยาว (เช่น fps=2 หรือทุก 0.5s).
- ตรวจ Veo ✦: จุดสว่างเล็กกึ่งโปร่งแสงที่ "ดริฟต์" ในแถบขวาล่าง. วิธีปฏิบัติ: crop โซนล่าง ~45% + ครึ่งขวา แล้วหา bright-blob เล็กที่ปรากฏต่อเนื่องหลายเฟรม (แยกจากคอนเทนต์) — ทำ template-match กลิฟ ✦ หรือ persistent-bright-cluster detector; flag ถ้าพบใน > เกณฑ์ % ของเฟรม.
- OUTPUT: automation-log/watermark-audit_20260709.md — ต่อไฟล์ PASS/FAIL + timestamp/เฟรมที่พบ + แนบ PNG เฟรมตัวอย่างเป็นหลักฐาน. บันทึก "drift bounds" (min/max x,y ของ ✦) ต่อคลิป สำหรับใช้ใน T2.

### T2 — FIX render pipeline (ให้ทับได้จริง)
เลือกวิธีตามลำดับความชอบ:
  (a) PREFER kinetic-text: ถ้าหัวข้อทำเป็น reel ข้อความพื้นดำ (tiktok-pipeline/src/07_render.py) ได้ ใช้อันนี้ — ไม่มี footage = ไม่มีลายน้ำ (นี่คือเหตุผลที่ reel คลัสเตอร์บัตรเครดิตสะอาด).
  (b) ถ้าจำเป็นต้องใช้ footage: CROP ลายน้ำออกนอกเฟรม — คำนวณ crop จาก drift bounds (T1) แล้ว scale/crop กลับ 1080x1920.
  (c) ถ้า crop เสียองค์ประกอบมาก: ทับด้วย element ทึบที่คลุม "ตลอดเส้นทางดริฟต์" (full-drift-bounds) ไม่ใช่แถบเล็กคงที่.
- เลิกใช้ scrim คงที่ ~30-38% เดิม. ระบุในโค้ด/คอมเมนต์ว่าเปลี่ยนวิธีเพราะลายน้ำดริฟต์.

### T3 — QA GATE (สร้างตัวตรวจลายน้ำ reusable)
- สร้างสคริปต์ เช่น tiktok-pipeline/src/qa_watermark.py: รับ path mp4 -> sample เฟรม -> คืน PASS/FAIL (+ หลักฐานเฟรม) ด้วย detector จาก T1.
- UNIT-PROOF (บังคับ): assert FAIL กับคลิปลายน้ำที่รู้ผล 1 ตัว (เช่น media/clips/*-2026.mp4) และ PASS กับ output 07_render สะอาด 1 ตัว. commit เทสต์ไว้.

### T4 — WIRE gate เข้าระบบ (อุดรูโหว่เกิดซ้ำ)
- เรียก qa_watermark ใน run_daily ก่อน "โพสต์/ส่งต่อ" ทุกครั้ง — FAIL = hard-block (ไม่ส่งต่อ).
- แก้ scheduled task ที่มีอยู่จริง: C:\Users\nL_ku\Claude\Scheduled\ngernduangold-video-post-verify\SKILL.md ให้รัน qa_watermark กับไฟล์ที่จะโพสต์/เพิ่งโพสต์จริง แล้ว "แจ้งเตือนดัง + ระบุชื่อไฟล์ + block/flag" เมื่อ FAIL (ไม่ใช่เช็กแค่ 1080x1920/hook/ชื่อไฟล์). นี่คือรูที่ปล่อย 5 reel หลุด — ต้องปิด.
- ก่อน re-enable ตัวโพสต์ reel ใด ๆ ในอนาคต: source ต้องเป็น _vidout/clean/ (T5) เท่านั้น ห้าม media/clips/*-2026.mp4 ดิบ.

### T5 — RE-RENDER 5 หัวข้อที่ลบ ให้สะอาด
- สร้าง reel สะอาดของ title-loan, emergency-fund, compound-interest, save-small, auto-save -> _vidout/clean/reel_<topic>-2026_clean.mp4 ทุกไฟล์ต้องผ่าน qa_watermark. PREFER kinetic-text (07_render) เพื่อเลี่ยง footage. คง hook + disclosure + 1080x1920.
- เขียน automation-log/clean-renders-ready_20260709.md: รายชื่อไฟล์เสร็จ + หัวข้อ + แคปชันพร้อมโพสต์ เพื่อ Cowork หยิบไปโพสต์ (1/ช่อง/วัน human-paced).

### T6 — VERIFY 2 ตัว footage ใน KEEP-LIST
- frame-scan DaBD2iIPWfl (save-first) และ DaRaYRLD80W (e-book) ด้วย qa_watermark.
- PASS -> ยืนยัน KEEP (ปล่อย live). FAIL -> เพิ่มเข้า re-render + แจ้ง Cowork ให้ลบ/สลับ (CC ห้ามลบ IG เอง).

### T7 — REPORT + HANDOFF
- เขียน automation-log/watermark-fix-report_20260709.md: ผล audit ทุกไฟล์ (PASS/FAIL), วิธีแก้ pipeline ที่ใช้, สถานะ QA gate + verify-task (พร้อมผล unit test), รายชื่อ clean render พร้อมโพสต์, คำตัดสิน 2 ตัว KEEP-LIST, ความเสี่ยงคงเหลือ.
- commit + push โค้ด/สคริปต์/แก้ task. ทิ้ง report + clean renders ไว้ให้ Cowork. (ห้าม push ถ้าแตะ build_site.py — แยกท้ายสุด)

## DELIVERABLES (สรุปสิ่งที่ต้องส่ง)
1. automation-log/watermark-audit_20260709.md (+ เฟรมหลักฐาน)
2. tiktok-pipeline/src/qa_watermark.py + unit test (FAIL คลิปลายน้ำ / PASS คลิปสะอาด)
3. pipeline ที่แก้แล้ว (07_render preferred / crop / full-drift cover) + run_daily เรียก qa_watermark
4. ngernduangold-video-post-verify SKILL.md ที่ frame-scan จริง
5. _vidout/clean/reel_*-2026_clean.mp4 (5 หัวข้อ) + clean-renders-ready_20260709.md
6. คำตัดสิน frame-scan ของ DaBD2iIPWfl + DaRaYRLD80W
7. watermark-fix-report_20260709.md + git push


---
## OWNER DIRECTIVE (2026-07-09) — Flow-clean + text is the PRIMARY method (supersedes T2/T5 ordering)
Owner reminder (has said this before): Google Flow (Veo) clips ARE usable — do NOT abandon them. Accepted method:
  1. Remove the watermark: CROP the ✦ out of frame, or COVER its full drift path (not a fixed small scrim). Keep 1080x1920.
  2. Add platform-appropriate TEXT overlay (hook + key line), fit per platform (IG / TikTok / YouTube).
  3. Output a CLEAN video and post that.

=> T5 (the 5 deleted topics: title-loan, emergency-fund, compound-interest, save-small, auto-save): PRIMARY = take each topic's EXISTING Flow clip from media/clips/, remove watermark + add platform-fit text, output _vidout/clean/reel_<topic>-2026_clean.mp4 (must pass qa_watermark). Kinetic-text (07_render) is an ACCEPTABLE ALTERNATIVE only if no usable Flow clip exists — not the default.
=> This is the real fix. Cowork may post a static pin (media/pins/pin_<topic>-2026.png) as a SAME-DAY stopgap only; the clean Flow video is the permanent replacement Cowork will re-post once you deliver it.


---
## OWNER DIRECTIVE (2026-07-09) — USE THE FULL (free/owned) TOOLKIT to its potential
Cowork probed the AI video studio MCP = Higgsfield = PAID (credits/subscription) -> EXCLUDED per zero-budget. Use only free/owned tools.

Free/owned arsenal:
- Google Flow (Veo): source AI video (owner has it; Cowork drives via browser)
- Google Stitch: design/cover/graphic gen (free; Cowork drives via browser)
- Adobe CC (adobe-for-creativity plugin): quick-cut, social-variations reframe (IG 4:5 / TikTok 9:16 / YT 16:9), design-from-template, image generative-fill/vectorize -> REQUIRES connector authorized in settings
- canvas-design / theme-factory / algorithmic-art skills: original graphics (free, local)
- CC tiktok-pipeline + ffmpeg: crop/cover watermark, burn captions, assemble, QA gate

CLEAN-REEL ENGINE (production method for T5 + all future reels):
1. Source = existing Flow clip (or gen new via Flow)
2. Remove watermark = ffmpeg crop out / cover full ✦ drift path (CC) [reliable; do not use fixed small scrim]
3. Burn platform caption/text (hook + key line) sized per platform
4. Reframe per platform (IG 4:5, TikTok/YT 9:16) = Adobe social-variations or ffmpeg
5. Cover / graphic elements = Stitch + canvas-design / theme-factory
6. QA gate (qa_watermark) MUST pass before handoff
7. Cowork posts 1/channel/day, human-paced (no bot blast)
Do NOT use Higgsfield/any paid gen unless owner explicitly authorizes spend.


---
## ADOBE CAPABILITY CHECK (Cowork, 2026-07-09) — accurate tool routing
Adobe connector is LIVE (init OK). Verified limits: Adobe REFUSES watermark removal (copyright block) and has NO generative-fill / object-removal / video-gen / video-region-crop in this env. Adobe is NOT the watermark remover.
Accurate split for the clean-reel engine:
- Remove Veo watermark from footage = CC ffmpeg crop/cover ONLY. OR sidestep entirely: CC 07_render kinetic-text reel (no footage = no watermark) = fastest 100% clean, same style as the already-clean credit-card reels.
- Adobe DOES: video_resize (reframe IG 4:5 / TikTok+YT 9:16), video_create_quick_cut (reel from footage), Express design + animate_design + image crop/adjust/outpaint for covers & graphics.
- Higgsfield/any paid gen = excluded (zero-budget).
FAST PATH for the 5 deleted topics: CC kinetic-text render -> Adobe reframe per platform -> Cowork posts 1/day. For topics wanting the Flow-footage look: CC crop/cover the watermark -> Adobe reframe. Adobe never asked to remove a watermark.
