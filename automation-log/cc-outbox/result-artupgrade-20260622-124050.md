# CC RESULT (implement homepage redesign) 20260622-124050

ทำโดย: Cowork-as-Claude (engine เอง) ตาม head-of-art brief + Stitch direction 'Golden Salary Finance Homepage'

## สิ่งที่ทำ
- ร่างหน้าแรกยกระดับเป็นไฟล์ preview เปิดดูได้จริง: `automation-log/art-direction/20260622-104514/preview-home.html`
- ธีมทอง-บนเข้มแบบ refined (ทองเป็น accent, การ์ดมน 16-20px, AA contrast, มือถือมาก่อน)
- ครบ 7 เซกชันตามบรีฟ: sticky header+nav+search · hero+แถบค้นหา+trust line · 4 การ์ดหมวด · 3 บทความ · trust strip+ธปท.note · CTA band (DM เช็กสิทธิ์) · footer+affiliate disclosure
- ใช้ design tokens เดิม (Noto Serif Thai หัว / IBM Plex Sans Thai เนื้อ / โทน gold #C5A880 #e0b23c)
- copy comply-safe: ช่วงไม่การันตี · ไม่มีชื่อแบงก์ใน hero · ลิงก์ขายไม่อยู่ในเนื้อ (DM/หน้าผู้ให้บริการ)

## ธงต้องขออนุมัติ (รอเจ้าของ/Cowork ก่อนแตะ site จริง)
- [ ] เปิด `preview-home.html` ดูหน้าตา — โอเคไหม / อยากปรับสี/คำ/เซกชันไหน
- [ ] ถ้าโอเค → fold เข้า build_site.py: แทนบล็อก hero+หมวดหน้าแรก โดย **คงไว้เป๊ะ**: GA_SNIPPET, คลาส affiliate (hubbtn/cta/go + rel=sponsored + data-provider + utm()), canonical/OG/sitemap, /quiz
- [ ] รัน build_site.py local → ตรวจ GA4 affiliate_click ยังยิง + ทุกหน้ายังมี canonical/OG → owner กด deploy (CC/Cowork ไม่ deploy เอง)
- [ ] (ถ้าต้องการเป๊ะตาม Stitch) เจ้าของ copy โค้ดจากโปรเจกต์ Stitch มาวาง → รอบสอง merge styling ละเอียด

## หมายเหตุ integration
- preview เป็น standalone (ฟอนต์ผ่าน Google Fonts) — ตอน fold เข้าเว็บจริงใช้ token/ฟอนต์ที่มีอยู่แล้วใน CSS เดิม ไม่ต้องโหลดซ้ำ
- ไม่แตะ logic affiliate/quiz/GA — เป็นงานชั้น presentation เท่านั้น
