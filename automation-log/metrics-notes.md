# metrics.csv — ที่มา + ข้อจำกัด (อัปเดต 2026-06-21)
- **IG**: views/reach = ข้อมูลจริงจาก Meta Graph (ngernduangold) ดึงสดผ่าน Cowork
- **FB**: API คืน insights=null (Meta ไม่ให้ reach/views ของ FB ผ่าน MCP นี้) → views ใส่ 0 เป็น placeholder ไม่ใช่ reach จริง = 0 · FB ให้แค่ like/comment/share (ตอนนี้ ~0)
- **clicks/quiz_start/conversion**: ยังเป็น 0 ทุกแถว — ต้องเชื่อม **GA4** (utm_source=ig/fb อยู่ในลิงก์แล้ว) หรือกรอกมือ จึงจะมีข้อมูล conversion จริง → analyst ถึงพิสูจน์ได้
- อัปเดตต่อเนื่อง: scheduled task ดึง IG/FB รายสัปดาห์ + เขียนทับ metrics.csv (Cowork ทำผ่าน Meta MCP)
