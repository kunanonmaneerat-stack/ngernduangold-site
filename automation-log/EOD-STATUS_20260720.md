# สรุปปิดวัน 20 ก.ค. 2026 (Cowork · ~19:30)

## ✅ เสร็จ + ยืนยันจากหลักฐาน
| งาน | หลักฐาน |
|---|---|
| knowledge-post เที่ยง kn-02 | ledger 12:47 Threads + 12:50 FB (เครื่องรันเองครั้งแรก) |
| Pantip คห.3 กระทู้ 44168590 | ledger 18:42 · ตรวจ /comment3 บนหน้าเว็บ |
| เพจ 2 แก้ครบ 3 จุด (bio/URL/ปก) | ตรวจหน้าเพจแล้ว 19 ก.ค. |
| เครื่องเพจ 2 + คลัง 8 โพสต์ | QA ผ่าน 0 คำต้องห้าม · รันแรก 21 ก.ค. 13:14 |
| FB Groups identity bug | แก้ SKILL ใหม่ทั้งไฟล์ + ด่าน 0/0.5 + group id 7 กลุ่ม |
| **บั๊ก post_guard: Threads OK ปลอม** | แก้แล้ว — knowledge-post (type=text) ไม่ถูกนับเป็นคลิปรายวันอีก · รันทดสอบได้ THREADS UNKNOWN ถูกต้อง |

## 🔴 ค้าง — ติด background-tab wall เดียวกัน 2 งาน
คลิป Threads วันนี้ (2026-07-20_debt-health-check) + คอมเมนต์กลุ่ม FB (ปรึกษาหนี้บัตรฯ ร่างพร้อมใน FBGROUP-DRAFT-READY)
- อัปโหลดคลิปเข้า composer ได้ แต่ Threads ไม่ประมวลผลวิดีโอเมื่อ document.visibilityState=hidden (แท็บอยู่เบื้องหลัง)
- ปิด composer สะอาดแล้ว ไม่มีโพสต์ครึ่งๆ ค้าง · โปรไฟล์ยืนยันคลิปยังไม่ขึ้น
- **ปลดล็อกทั้งคู่ด้วยการเดียว: เจ้าของคลิกแท็บ Facebook/Threads ให้อยู่หน้าจอ แล้วบอก Cowork**

## ⚠️ ปัญหาระบบที่เหลือ (guard ตาบอด 3 ช่อง — งานพรุ่งนี้)
YouTube UNKNOWN (token หมดอายุ) · IG BLOCKED (ไม่มี credential) · TikTok UNKNOWN (อ่าน profile ไม่ได้)
→ 3/5 ช่องยังตรวจไม่ได้ว่าโพสต์ขึ้นจริง · เป็นงานถัดไป ไม่ใช่รายวัน

## จุดที่ได้บทเรียนวันนี้
1. อ่าน timestamp ของข้อมูลก่อนตีความเป็นเวลาปัจจุบัน (พลาดบอก "ตี 1")
2. FB group/identity ผูกกับ "โปรไฟล์/เพจ" ที่ active — สลับแล้วต้องสลับกลับ
3. guard ที่ match กว้างเกิน (channel+date) ทำให้ผ่านทั้งที่ของจริงไม่ขึ้น — ต้อง match ให้เจาะจง type


## ✅ อัปเดต ~20:05 — คลิป Threads โพสต์สำเร็จ (หลังเปิด Chrome ใหม่)
เจ้าของชี้ว่า Chrome ปิดอยู่ → เปิด Chrome ใหม่ผ่าน Start-Process → extension reconnect → แท็บใหม่ได้ viewport เต็ม (780x538)
แต่ file_upload วิดีโอยังไม่แนบเพราะ visibilityState=hidden (แท็บ Threads อยู่หลัง แท็บ FB เป็น active)
→ SendKeys Ctrl+9 สลับไปแท็บ Threads (แท็บสุดท้าย) → visibilityState=visible → **วิดีโอแนบทันที (videos:1)**
→ paste แคปชัน + กดโพสต์ → ยืนยันโปรไฟล์ "เช็กสุขภาพหนี้ 60 วิ" ขึ้น "1 นาที" · ledger source=cowork-manual-recovery
**บทเรียนสำคัญ: Threads video ต้อง visibilityState=visible เท่านั้น — viewport เต็มยังไม่พอ · การสลับให้แท็บเป็น active tab (Ctrl+9) คือกุญแจ**

## ❌ คอมเมนต์กลุ่ม FB (โพสต์ CozyPear5571) — ทำไม่ได้ถาวร
เปิดหน้าจริง viewport เต็มแล้วเห็นชัด: **"ได้มีการปิดการแสดงความคิดเห็นไว้สำหรับโพสต์นี้"** (JS check เช้านี้ผิดเพราะข้อความอยู่นอก [role=article])
→ โพสต์นี้คอมเมนต์ไม่ได้เลย ไม่ใช่ปัญหา identity/tab · fbgroup-listen พรุ่งนี้ต้องข้ามโพสต์นี้ หาโพสต์ที่คอมเมนต์เปิด
→ ควรเพิ่มเช็ค "ปิดการแสดงความคิดเห็น" เข้า fbgroup-listen ก่อนร่าง (กันร่างเสียเปล่า)
