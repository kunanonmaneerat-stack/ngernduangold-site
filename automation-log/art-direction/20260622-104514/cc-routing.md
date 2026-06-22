# ROUTING — งานที่ Claude Code ทำได้ดีกว่า (ส่งผ่าน cc_bridge.send)

> เกณฑ์: งานแตะโค้ด/หลายไฟล์/ต้องคงพฤติกรรมเดิม (GA4, affiliate tracking, SEO, speed) = CC ทำดีกว่า Cowork

- [CC] แปลงดีไซน์จาก Google Stitch -> โค้ดจริงใน build_site.py (template homepage) คงโครงสร้าง GA4/affiliate/utm
- [CC] ทำ component การ์ดหมวด + hero + trust strip ให้ responsive + AA contrast
- [CC] รักษา performance (inline critical CSS, ไม่เพิ่ม JS หนัก, รูป lazy)
- [CC] regression: ทุกหน้ายังมี canonical/OG/sitemap/quiz เดิม
- [Cowork] ตัดสินใจดีไซน์ไหนเอา, คุม Stitch, อนุมัติก่อน deploy
- [Owner] กด deploy จริง (CC ห้าม commit/push/deploy เอง)
