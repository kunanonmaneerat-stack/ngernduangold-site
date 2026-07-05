# ORDER → CC — ประกอบ _final Flow batch 2 (4 คลิป: 12/16/18/19 ก.ค.) · 5 ก.ค. Cowork

> อ้างอิงกระบวนการเดิมที่ทำสำเร็จ: `cc-outbox/CC-report_flow-assembly_20260705.md` (batch 1 = 6 _final)
> ใช้ params/ขั้นตอนชุดเดียวกันเป๊ะ ยกเว้นไฟล์ input + hook text ต่อคลิป (ระบุด้านล่าง)

## INPUT — 12 คลิปดิบพร้อมแล้ว (Cowork ดึงด้วย Flow "Download Project" 5 ก.ค.)
- โฟลเดอร์: `automation-log/_social-stage/_raw/_flowproj_20260705/` (gitignored=local)
- 12 ไฟล์ (ชื่อ=prompt): Thai_office_worker_hopeful_smile · Thai_woman_drives_car_city · Thai_person_uses_mobile_banking · Person_dropping_coins_into_jars · Two_coin_stacks_growing · Thai_person_sleeps_money_grows · Thai_person_reading_tablet · Thai_person_filling_budget_worksheet · Thai_person_ticking_checkboxes · Hands_placing_credit_cards · Man_looks_at_smartphone_chat (+_2)

## งาน: ประกอบ 4 _final เติมช่องว่าง POST-PACK
| _final | ใช้ไฟล์ดิบ | วัน | ธีม | hook บนจอ (2 บรรทัด, ห้ามมีตัวเลขดอก/ราคา) |
|---|---|---|---|---|
| _final_tl01b | **Thai_office_worker_hopeful_smile** | 12 ก.ค. | จำนำทะเบียน (แทน tl01 error) | "มีรถ = มีทางเลือกหมุนเงิน" / "รถยังใช้ได้ตามปกติ" |
| _final_kp05 | **Thai_person_uses_mobile_banking** | 16 ก.ค. | ออม/เงินสำรอง | "เงินสำรองไว้ในที่ถอนไว" / "ฉุกเฉินเมื่อไหร่ กดใช้ได้ทันที" |
| _final_kp06 | **Person_dropping_coins_into_jars** | 18 ก.ค. | ออม/สร้างนิสัย | "ออมทีละนิด ทุกวันเงินเดือนออก" / "วินัยเล็ก ๆ ที่เปลี่ยนชีวิต" |
| _final_eb03 | **Thai_person_reading_tablet** | 19 ก.ค. | e-book/คู่มือ | "คู่มือ + Worksheet ปลดหนี้" / "ทำตามได้ทีละขั้น" |

## STEP 1 — watermark check + removal (เหมือน batch 1)
- ตรวจ 4/4 ที่เฟรม 25/55/90% → หาลายน้ำ Flow (✦ ล่างขวา หรือ Veo ล่างสุด)
- ลบ: `delogo` (interpolate กล่อง ✦ ~x545 y1108 w100 h100) + `crop 664:1180` (zoom ~8% ตัด Veo) → `scale 720:1280`
- VERIFY ลบเกลี้ยง (bottom-strip @3s ต้องไม่มี Veo/✦) — สำเนาสะอาดเท่านั้นไป _final

## STEP 2 — overlay + end-card (ffmpeg drawtext harfbuzz Thai, Leelawadee UI)
- รันจาก cwd=scratchpad + ใช้ **bare relative** font/textfile names (colon ใน Windows path พัง drawtext parser)
- hook 2 บรรทัดต่อคลิป (ตามตาราง) โผล่ต้นคลิป
- end-card ~2.8s สุดท้าย 3 บรรทัดพอดีจอ: "ลิงก์ในไบโอ" / "ngernduangold.com/links" (ทอง) / "ข้อมูลเพื่อการศึกษา · ผลิตด้วย AI"
- คงเสียงเดิม · output 720x1280 · ตรวจ Thai render ด้วย QA_hooks*.png

## STEP 3 — captions + comply
- เขียน caption IG/TikTok/YT + FB-comment ต่อคลิป (สไตล์ POST-PACK เดิม) · eb03 disclosure = "มีลิงก์ขายคู่มือของเราเอง"
- รัน `comply_gate.check_post()` ทุก caption → ต้อง GATE_OK · เลี่ยง bare-% · TikTok +#fyp ตัด URL

## STEP 4 — POST-PACK update
- แก้ `_social-stage/POST-PACK_week_20260706-0712.md` + ส่วน 13-19: ช่อง **12=_final_tl01b · 16=_final_kp05 · 18=_final_kp06 · 19=_final_eb03**
- (12 ก.ค. เดิม=tl01 error → order-hold-tl01 ให้ถอด — ตัวนี้ tl01b มาแทน)

## STEP 5 — commit/push (กติกาเดิม เข้ม)
- media (_final/_raw/POST-PACK) = gitignored → อยู่ local เท่านั้น ห้าม commit
- commit เฉพาะ: report `cc-outbox/CC-report_flow-assembly-batch2_20260705.md` + order นี้
- ถ้าแตะ build_site.py = **push แยก commit ท้ายสุด** (Netlify ignore rule) — งานนี้ไม่ควรแตะ build_site.py
- zero-budget: ffmpeg local เท่านั้น ห้าม paid/AI-gen · การ์ด free_ai.py ห้ามปิด

## DoD
_final 4/4 · ลายน้ำเกลี้ยง (proof แนบ _wmchk/) · POST-PACK อัปเดต · comply GATE_OK ทุก caption · report → cc-outbox · push report+order (ไม่มี media)

## เหลือให้ Cowork/เจ้าของ: โพสต์รายวันตามคิว (เจ้าของยืนยันในแชต) · Pantip owner กด รับทราบ · IG/TikTok เติมจาก POST-PACK
