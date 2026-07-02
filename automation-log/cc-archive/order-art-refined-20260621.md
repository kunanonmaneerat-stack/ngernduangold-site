# WORK ORDER -> Claude Code: ยกระดับหน้าตาเว็บ (Cowork เกลาแล้ว · แม่นยำ)

> แก้ที่ **build_site.py (CSS/template) เท่านั้น** · คงโหลดเร็ว+มือถือ · ห้าม commit/deploy รอ owner OK
> เว็บมีดีไซน์ดีอยู่แล้ว: navy #0F172A + gold #C5A880, Noto Serif Thai + IBM Plex Sans Thai, card/CTA system,
> เพิ่ง polish hover/focus/transition + เพิ่ม trust line ใน footer → **ต่อยอด ไม่รื้อ ไม่เพิ่มฟอนต์ซ้ำ**

## งาน (เรียงตาม leverage → conversion/trust)
1. **Trust band ใต้ header ทุกหน้า** (consult ชี้ว่า trust สำคัญสุด)
   - แถวเล็ก 3 จุด: "อัปเดต 2026" · "อ้างอิงหน้าทางการของผู้ให้บริการ" · "เทียบหลายเจ้า"
   - สไตล์เบา ใช้ var(--gold-soft)/var(--line) ไม่บัง content · มือถือยุบเป็นบรรทัดเดียวได้
2. **Hero ให้มีชีวิตขึ้น** (ตอนนี้ text-only gradient)
   - เพิ่ม SVG inline เบาๆ (ห้ามโหลดรูปนอก) แนว minimal เส้น gold (โล่/กราฟขึ้น/เหรียญ) + แถบ "เทียบ 10+ ตัวเลือก · ใช้เวลา ~1 นาที"
3. **ไอคอนหน้าการ์ด** เพิ่ม emoji/SVG เล็ก (บัตร/บ้าน/รถ/ออม) เพิ่ม scannability + ชีวิตชีวา
4. **CTA microcopy** ใต้ปุ่ม: "ไม่ผูกมัด · เช็กสิทธิ์เบื้องต้นใน ~1 นาที" (เลี่ยงคำการันตี)
5. **มือถือ** เช็ก tap target ≥44px · spacing การ์ด/ปุ่ม · ตารางเทียบเลื่อนลื่น

## ห้าม
- ห้ามแตะ affiliate links/utm/โครงสร้าง funnel (/quiz, /links) · ห้ามเพิ่ม external script/font · ห้าม commit/deploy
- คปภ: ห้ามคำการันตี · ตัวเลขเป็นช่วง + อ้างอิงหน้าทางการ

## เสร็จแล้ว
รัน `py build_site.py` เช็กไม่พัง → เขียนผล (ไฟล์ที่แก้ + สรุป) ที่ `cc-outbox/result-<ts>.md` → cc_review เก็บให้ Cowork
