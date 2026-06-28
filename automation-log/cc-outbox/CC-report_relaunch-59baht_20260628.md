# CC report — e-book relaunch @ 59฿ (STEP 5 + 6) — ✅ LIVE
ref: TASK relaunch 59฿ (Cowork) · 2026-06-28

## STEP 5 — /links button 129฿ -> 59฿ (+ page-count fix) : DONE, LIVE
- build_site.py button: `— 129฿` -> `— 59฿` AND `e-book 9 หน้า` -> `e-book 35 หน้า`
  * ⚠️ NOTE: task ระบุแค่ราคา แต่ปุ่มยังเขียน "9 หน้า" (ของเก่า) ทั้งที่ product ใหม่ = 35 หน้า (Cowork ลบ PDF 9 หน้าแล้ว). CC แก้ 9->35 ด้วย เพื่อกัน mismatch บนปุ่ม live (CONTINUE note ยืนยัน "เล่มนี้ 35 หน้า"). ถ้าไม่ต้องการ บอกได้
- commit c52f59b -> push (6dd05a3..c52f59b) -> Netlify rebuild
- VERIFY LIVE (https://ngernduangold.com/links): 59฿=1 · **129฿=0** · 35 หน้า=1 · ebook-slug ครบ · rel="noopener" (ไม่มี sponsored/nofollow) · URL ปลายทาง ngernduangold.gumroad.com/l/debt-payoff-planner คงเดิม
- gates: smoke 60/60 PASS · byte-safe (0 mojibake)

## STEP 6 — captions 129฿ -> 59฿ : DONE
- แก้ทั้ง 2 ไฟล์: _product1_launch_promo_captions_20260628.md (x5) + _product1_promo_captions_20260628.md (x4) -> 129฿ เหลือ 0 ทั้งคู่ · comply_gate OK ทั้งคู่ · byte-safe
- ไม่แตะเลขหน้าใน caption (caption ไม่ระบุหน้า ตามที่สั่ง) · _CONTINUE-relaunch-59baht note ไม่แตะ (มันคือบันทึกการเปลี่ยน 129->59 เก็บไว้เป็นประวัติ)

## STEP 8 — UNBLOCKED (Cowork/owner)
ปุ่ม /links = 59฿ live แล้ว -> คลิกแล้วเจอราคาตรง. พร้อม re-stage: caption 59฿ + คลิป outputs/ebook-promo-9x16.mp4 (card4=59฿) · ลำดับ Threads/FB -> IG/TikTok/YT · Cowork stage, owner กดโพสต์.
