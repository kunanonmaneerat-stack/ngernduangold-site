# COMPLIANCE CHECKLIST — ผ่านครบทุกข้อก่อนปล่อยคอนเทนต์ (แบรนด์การเงิน)

## ทุกโพสต์/ทุกช่อง
- [ ] `channels.<channel>.publication_authorized=true` ณ เวลาลงมือ + actor capability + calendar placement `publication_authorized=true` + schema-v2 private one-time receipt ที่ bind target/content/placement/caption/asset/slot และ SHA-256 ของ policy/roles/calendar/content+validation/media-QA; ค่า missing/false/hash drift/นอก Asia/Bangkok slot window = หยุดโดยไม่ consume
- [ ] ไม่มีตัวเลขดอกเบี้ย % ตายตัว — ถ้าจำเป็นใช้ "ตามเพดาน ธปท." / "เช็กกับผู้ให้บริการ"
- [ ] มี "ข้อมูลเพื่อการศึกษา ไม่ใช่คำแนะนำทางการเงิน"
- [ ] คลิปที่เจนด้วย AI → มี "ผลิตด้วย AI" (+ เปิด AI-label toggle ในแพลตฟอร์มที่มี)
- [ ] ความถี่: อ่าน `.system_control/policy.json → limits` และ per-channel override ณ เวลาลงมือ ห้ามจำตัวเลขจากเอกสารนี้
- [ ] เช็ก dedup ก่อนโพสต์ (post_ledger ±16 วัน · publisher มี dedup ในตัว)

## เฉพาะโพสต์ affiliate (affiliate:true ใน manifest)
- [ ] มีข้อความ "มีลิงก์พันธมิตร" ในแคปชัน/บอดี้
- [ ] บนหน้าเว็บ: ลิงก์ affiliate มี rel="sponsored" + disclosure ในหน้าเดียวกัน
- [ ] ไม่คัดลอก merchant copy ที่มีเลขดอกเบี้ย

## เฉพาะช่อง
- [ ] TikTok/IG/Threads: **ไม่มี URL ในตัวโพสต์** → "ลิงก์ในไบโอ" เท่านั้น (reach)
- [ ] FB: ลิงก์อยู่**คอมเมนต์แรก**เท่านั้น ไม่อยู่ในบอดี้
- [ ] Pantip: manual pilot อยู่ช่วง `OBSERVING_48H`; one-time approval เดิมถูกใช้แล้ว ห้ามโพสต์ครั้งถัดไปก่อน review due + fresh owner confirmation
- [ ] IG/Pinterest: paused; TikTok: `testing_blocked` เป็นแผน 14 วันเท่านั้นและ publishable=0 จนทุก blocker ผ่าน

## เว็บไซต์ (ก่อน owner-controlled release)
- [ ] privacy guard ผ่านก่อน push/deploy · comply_gate ผ่าน · static affiliate check ผ่านโดยยิง redirect 0 ครั้ง · smoke ทุกหน้า · live/local parity ผ่าน; ผล local PASS ไม่ใช่อำนาจ deploy
- [ ] ไทย byte-safe: python I/O + UFFFD=0 + git blob verify · ห้าม PII/token/รายได้จริงลง repo
