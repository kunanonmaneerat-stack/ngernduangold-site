# CC report — Flow assembly batch 1: 6 _final_ (order-assemble-5clips/-flow-assembly) — ✅ เสร็จ
executed: 2026-07-05 · zero-budget (ffmpeg local, ไม่มี paid/AI-gen) · ไม่แตะ Pantip/build_site.py/secrets · CC ไม่โพสต์เอง

## 1) _wmchk (ลายน้ำ) — ตรวจ 6/6 (เฟรม 25/55/90%) → grid ใน _social-stage/_wmchk/
- พบลายน้ำ Flow ทุกตัว: **tl01 = "Veo"** (ล่างขวาสุด y≈1250) · **tl03/tl04/tl05/eb02/kp04 = "✦"** (ล่างขวา y≈1130-1190)
- ลบด้วย: `delogo` (interpolate กล่อง ✦ x545 y1108 w100 h100) + `crop 664:1180` (zoom ~8% ตัด Veo ล่างสุด) → scale 720:1280
- **VERIFY ลบเกลี้ยง 6/6** (bottom-strip @3s: PROOF_watermark-removed_bottoms.png = ไม่มี Veo/✦ เหลือ) — สำเนาสะอาดเท่านั้นที่ไป _final_

## 2) overlay + _final_ (720x1280, audio คงไว้, ผลิตด้วย ffmpeg drawtext harfbuzz Thai shaping)
| _final_ | hook บนจอ (2 บรรทัด) | dur | หมายเหตุคอนเทนต์ |
|---|---|---|---|
| _final_tl01.mp4 | รถคันนี้ = เงินสำรองที่ลืมไป / จำนำเล่ม รถยังขับได้ปกติ | 7.8s | ⚠️ ภาพดิบ = ผู้หญิงเต้นบนรูฟท็อป (ไม่มีรถ) — overlay ตามสั่ง แต่ภาพไม่ตรงธีมจำนำทะเบียน 100% → Cowork review ว่าจะใช้/สลับ/regen |
| _final_tl03.mp4 | หนี้บัตร 3 ใบ ปิดด้วยดอกที่ถูกกว่า / รวมให้เหลือก้อนเดียว จ่ายที่เดียว | 8.0s | ✓ มือถือบัตร 3 ใบ → ลิ้นชัก ตรงธีม |
| _final_tl04.mp4 | จำนำเล่มแล้ว รถยังขับได้ไหม / ได้ — เล่มอยู่กับผู้ให้สินเชื่อ รถอยู่กับเรา | 8.0s | ✓ ผู้หญิงขับรถ ตรงธีม |
| _final_tl05.mp4 | 3 อย่างต้องเช็กก่อนเซ็น / ดอกรวม · ค่าธรรมเนียม · ค่างวดไหวไหม | 10.0s | ✓ มือเช็กลิสต์+เซ็น ตรงธีม |
| _final_eb02.mp4 | 35 หน้า ย่อยวิธีปลดหนี้ให้ทำตามได้ / คู่มือ + Worksheet ลิงก์ในไบโอ | 8.0s | ✓ อ่าน e-book บนแท็บเล็ต ตรงธีม |
| _final_kp04.mp4 | เงินสำรองที่ถอนได้ทันที / ฉุกเฉินเมื่อไหร่ กดใช้ได้เลย | 8.0s | ✓ กังวล→เช็กแอปออม→ยิ้ม ตรงธีม |
- end-card ท้ายทุกตัว (โผล่ ~2.8s สุดท้าย): "ลิงก์ในไบโอ" / "ngernduangold.com/links" (ทอง) / "ข้อมูลเพื่อการศึกษา · ผลิตด้วย AI" — 3 บรรทัดพอดีจอ (แก้ → arrow ที่ font ไม่มี = ตัดออก)
- **ไม่มีตัวเลขดอกเบี้ย/ราคาบนจอ** ทุกตัว (3/35/3-ใบ = จำนวนนับ ไม่ใช่ rate/price) · Thai render ถูกต้อง (harfbuzz) ตรวจด้วย QA_hooks*.png

## 3) POST-PACK_week_20260706-0712.md อัปเดตแล้ว
- แทน filler: **11 ก.ค.=_final_kp04** (kept) · **12 ก.ค.=_final_tl01** (title-loan) · เพิ่มสัปดาห์ **13-19 ก.ค.**: 13=tl03 14=tl04 15=tl05 (title-loan เกาะกลุ่มเพราะ batch1 มี kept แค่ 1) · 17=eb02 (ebook, คู่ศุกร์)
- **16/18/19 ก.ค. = รอ Flow batch หน้า** (kp05/eb01/kp02/kp03/tl06) → CC เติมเมื่อ RAW-READY ถัดไปมา (จะช่วยสลับธีมให้สวยขึ้น)
- **comply_gate ทุกแคปชัน = GATE_OK 11/11** (แก้ FB-comment เดิม 9 ก.ค. "20%" → เลี่ยง bare-% ด้วย) · TikTok +#fyp + ตัด URL ตามสไตล์ QUEUE

## 4) DoD
_final_ 6/6 เสร็จ · ลายน้ำเกลี้ยง (proof แนบใน _wmchk/) · POST-PACK อัปเดต+gate ผ่าน · ไม่แตะ build_site.py → commit เฉพาะ report+order (mp4/POST-PACK อยู่ _social-stage gitignored = local/Drive, ไม่เข้า public repo ตามกติกา media)
## เหลือ: Cowork review tl01 (ภาพไม่ตรงธีม) + ดึง Flow batch หน้า 5 คลิป → append RAW-READY → CC ประกอบ 16/18/19
