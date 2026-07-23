# CC TASK — เพิ่มลิงก์ e-book ลงหน้า /links (link-in-bio hub)

สร้างโดย Cowork · 2026-06-28 · ผูกกับ Product #1 (e-book ปลดหนี้บัตรเครดิต) ที่ขายสดบน Gumroad แล้ว

## เป้าหมาย
เพิ่มปุ่มขาย **คู่มือของเราเอง** (e-book + Worksheet) ลงหน้า `/links` ให้คนที่มาจาก bio เห็น = เปิดช่องทางรายได้ digital product ช่องแรก

**ลิงก์ขาย (verified live, มีปุ่ม "I want this!"):**
`https://ngernduangold.gumroad.com/l/debt-payoff-planner`
ราคา 129฿ (Gumroad แสดง $3.49) · e-book PDF 9 หน้า + Excel worksheet กรอกได้

## ไฟล์ที่แก้
`build_site.py` → ตัวแปร `links_body` (รอบ ๆ บรรทัด ~2449)

## จุดแทรก (anchor)
แทรก **ต่อจาก** บรรทัด Quiz CTA hubbtn นี้ (ปัจจุบัน ~บรรทัด 2449):

```
<a class="hubbtn" href="/quiz" style="background:linear-gradient(180deg,#3a3a44,#2a2a32);color:var(--gold-lt)">🧭 ไม่รู้เริ่มตรงไหน? ทำ Quiz 30 วิ →<small style="color:#c8c8d0">ตอบ 2 คำถาม จับคู่บัตร/สินเชื่อ/ออม ที่เหมาะกับคุณ</small></a>
```

## snippet ที่จะแทรก (วางต่อท้าย anchor ด้านบน — byte-safe Thai)
```
<a class="hubbtn" href="https://ngernduangold.gumroad.com/l/debt-payoff-planner" target="_blank" rel="noopener" style="background:linear-gradient(180deg,#c8941a,#a87a12);color:#1a1305">📘 คู่มือ + Worksheet ปลดหนี้บัตรเครดิต — 129฿<small style="color:#3a2c08">e-book 9 หน้า + Excel กรอกได้ · จาก "จ่ายขั้นต่ำไม่จบ" สู่ "ปลดหนี้เป็นระบบ" · คู่มือของเราเอง</small></a>
```

## กฎ compliance (สำคัญ — ห้ามพลาด)
1. **นี่คือสินค้าของเราเอง ไม่ใช่ affiliate** → ใช้ `rel="noopener"` เท่านั้น **ห้ามใส่** `sponsored`/`nofollow` (จะหลอก search engine ว่าเป็น paid link ทั้งที่ไม่ใช่)
2. ป้ายกำกับมีคำว่า "คู่มือของเราเอง" ชัดเจน = โปร่งใส ไม่อ้างเกินจริง
3. หน้า Gumroad มี disclaimer + affiliate disclosure + "ไม่การันตี" ครบแล้ว (เนื้อหา e-book ผ่าน fact-check + comply แล้ว) — ฝั่ง /links ไม่ต้องเพิ่ม disclaimer ใหม่ ของเดิมยังถูกต้อง
4. **ห้ามนำไฟล์สินค้า (PDF/xlsx) เข้า repo public** — ไฟล์อยู่ใน outputs เท่านั้น task นี้แตะแค่ลิงก์ภายนอก

## ขั้นตอน
1. แก้ `build_site.py` ตามข้างบน (แทรก snippet ต่อจาก Quiz CTA)
2. `python build_site.py`
3. verify: `grep -c "l/debt-payoff-planner" site/links.html` ต้องได้ ≥1 · เปิด site/links.html เช็กปุ่มขึ้น + ภาษาไทยไม่เพี้ยน (byte-safe)
4. รัน comply_gate / link_check ตามปกติถ้ามีใน pipeline
5. commit + push (Windows git) — **หยุดที่ push gate รอ owner อนุมัติตามขั้นตอนเดิม**

## หมายเหตุ
- ใส่ใต้ Quiz CTA = ตำแหน่ง visibility สูง (คนเห็นเป็นอันดับต้น ๆ) — ถ้า CC เห็นว่าควรอยู่ตำแหน่งอื่น (เช่น hubsec แยก id="guide") ปรับได้ตามดุลพินิจ ขอแค่เด่นพอ
- ยังไม่ทำ pickcard ใน .hubpick (grid ตอนนี้ 4 อันลงตัว 2x2 — เพิ่มอันที่ 5 จะเสียสมดุล) เว้นไว้ก่อน
