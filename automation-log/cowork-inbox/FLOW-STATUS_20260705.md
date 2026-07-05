# FLOW re-pull — สถานะ 5 ก.ค. (Cowork) → ทำต่อ session สด

## ✅ ข่าวดี: reCAPTCHA/throttle เคลียร์แล้ว
- Flow (labs.google/fx/tools/flow) login PRO ปกติ · ไม่มี CAPTCHA block · เข้าโปรเจกต์ได้
- โปรเจกต์: "02 ก.ค. 11:15" (id c78f85c7-6fc1-4694-b97f-470d4e31b990)

## ✅ เจอคลิป title-loan ที่ถูกต้อง (แทน tl01 error!)
- edit id: **b50bffc1-53a3-4f2d-ac4f-9f26db0aee5d**
- title: "Thai office worker hopeful smile"
- prompt: "Vertical 9:16 realistic cinematic: Thai office worker early 30s sits in parked sedan looking stressed about money, sighs..."
- = ตรงธีมจำนำทะเบียน 100% (มีรถ+เครียดเงิน→หาทางออก) · ใช้ตัวนี้แทน raw_tl01 (หญิงเต้น=ผิด)

## ⚠️ ติดปัญหา download (ต้อง debug รอบสด)
- คลิก Download icon แล้ว **ไฟล์ไม่ลง C:\Users\nL_ku\Downloads** (ตรวจแล้วไม่มี mp4 ใหม่)
- สาเหตุที่เป็นไปได้: (a) มี dropdown เลือก resolution ที่ต้องคลิกต่อ (b) Flow เตรียมไฟล์ >28s (c) download path ต่าง (OneDrive?)
- คลิปอื่นในโปรเจกต์ thumbnail ดำ/หลายตัว "Queued" (zombie ค้าง) → ต้อง hover/คลิก verify ทีละตัวก่อนดึง (กัน error แบบ tl01)
- **สาเหตุจริงที่เจอ (5 ก.ค.):** เปิด edit view แล้ว **player กลางดำ readyState 0** (video ไม่โหลด) แม้ลอง video-center click + play button + Download 2 ครั้ง → Download ไม่ลงไฟล์เพราะ player ไม่โหลด video · timeline ว่าง = generation ยังไม่ถูก add เข้า scene
- **วิธีที่เคยเวิร์ค (task #21, ดึง 6 คลิปสำเร็จ):** คลิปที่ render/preview พร้อมใน history-strip ด้านบนดึงได้ · คลิปที่ player ดำต้อง reload หน้า / รอ render / เลือก generation อื่นใน history-strip ที่ preview ขึ้นแล้ว
- **ลอง session สด:** reload project → เลือกคลิปที่ thumbnail preview ขึ้นชัด (ไม่ดำ) → video-center click → รอ player โหลด (เห็นเฟรมแรก) → Download → รอ 28s → เช็ค C:\Users\nL_ku\Downloads

## 📋 ต้องทำ (session สด, context โล่ง):
1. เข้าโปรเจกต์ → คลิปที่ต้องดึง: tl01-ถูก(b50bffc1) + kp05/eb01/kp02/kp03/tl06
2. แต่ละคลิป: คลิกเปิด → อ่าน prompt ยืนยันธีม → Download → debug จนไฟล์ลง Downloads → ย้าย _social-stage/_raw/
3. append RAW-READY → CC ประกอบเติม POST-PACK 12/16/18/19 ก.ค.
