# WORK ORDER → Claude Code: ทำไมยอดเป็นศูนย์ และ 4 อย่างที่ต้องแก้ (1 ส.ค. 2026 · รอบ 3)

> กฎเดิม: UTF-8 · ห้าม `git add -A` · ห้ามแตะ `secrets/` · แก้เฉพาะที่ระบุ · ห้าม heredoc กับ backslash
> `git pull` ก่อนเริ่ม — ผม push `132d91c` ไปแล้ว (กู้ `weekly-review` + watchdog ด่าน 2.5)

---

## 0 · คำถามคือ "เมื่อวานทำไมไม่มียอด" · คำตอบคือ **ไม่ใช่เมื่อวาน — ยังไม่เคยมีเลย**

`automation-log/sales-log.jsonl` มี **1 บรรทัด** และเป็น metadata header · เปิดไฟล์ไว้ตั้งแต่ 24 ก.ค. · **ยอดขายจริง = 0 ชิ้น 0 บาท ตลอดกาล**
เพราะฉะนั้นอย่าตามหาสาเหตุเฉพาะของเมื่อวาน — มันคือสภาพปกติของระบบ และมีสาเหตุเชิงโครงสร้าง

### ตัวเลขจริง 28 วัน (GA4 · จาก `traffic-monitor-20260801-0720.md`)
```
sessions รวม 209
  direct   166  → quiz_start 0 · affiliate_click 2
  pantip    18  → quiz_start 2 · affiliate_click 5      ← ดีที่สุดแบบขาดลอย (28% click-rate)
  fb        13  → 0 · 0
  chatgpt    8  → 0 · 2
  yt         3  → 0 · 0
  bing       1  → 0 · 0

funnel: quiz_start 2 → quiz_complete 2 → recommendation_view 2 → affiliate_click 9
หน้า:   /  162 views → 0 conv   ·   /links 28 → 3   ·   /debt-letter-kit 10 → 0   ·   /debt-calculator 10 → 0
ยอดขาย: 0
```

### 🔴 สาเหตุที่ 1 (ใหญ่สุด และแก้ง่ายสุด) — **หน้าขาย 199฿ ไม่มีปุ่มซื้อ**
ผมไล่ทุก `href` ใน `site/debt-letter-kit.html` แล้ว มีทั้งหมดนี้:
```
2 × https://line.me/R/ti/p/@804qodya
2 × /
1 × https://ngernduangold.com/debt-letter-kit
1 × /debt-health-check   1 × /debt-calculator   1 × /debt-consolidation-2026
```
**ไม่มี Gumroad · ไม่มีพร้อมเพย์ · ไม่มีเส้นทางจ่ายเงินใดๆ เลย**
คนที่อยากซื้อมีทางเดียวคือกด LINE แล้วรอคนตอบ — และหลังบ้าน LINE **ยืนยันไม่ได้ว่าแชทเปิดอยู่ไหม** (`FUNNEL-HEALTH_20260731.md` ข้อ A1: session หมดอายุ ตรวจไม่ได้ · จุดตายเดียวกับที่เคยเกิด 25 ก.ค.) และ friends = **1 คน**

ทั้งที่ปุ่ม Gumroad **มีอยู่แล้วและ live ทั้งคู่** — แต่ไปอยู่บน `/links` ซึ่งเป็นหน้าฮับ ไม่ใช่หน้าขาย:
```
gumroad.com/l/debt-toolkit          (199฿ ชุดเครื่องมือปลดหนี้)
gumroad.com/l/debt-payoff-planner   (59฿)
```

> **หน้าที่มีหน้าที่เดียวคือขาย ถูกเห็น 10 ครั้งใน 28 วัน และไม่มีปุ่มให้ซื้อ · 0 ยอดขายคือผลลัพธ์ที่ถูกต้องทางคณิตศาสตร์ ไม่ใช่ความลึกลับ**

### 🔴 สาเหตุที่ 2 — **หน้าที่คนอ่านจริง ไม่ลิงก์มาหน้าขาย**
```
bureau-blacklist-loan-2026   9 views · 2 clicks   → ลิงก์ไป letter-kit: 0
personal-loan-2026           6 views · 2 clicks   → ลิงก์ไป letter-kit: 0
debt-consolidation-2026      6 views · 1 click    → ลิงก์ไป letter-kit: 2  ✅
```
สองหน้าที่ทำ engagement ได้ดีที่สุด **ไม่มีทางเดินไปหาสินค้าเลย**

### 🟠 สาเหตุที่ 3 — **รายงานเรียก `affiliate_click` ว่า "conversion"**
`pipeline/ga4_pull.py` L15: `CONV_EVENT = os.environ.get("GA4_CONV_EVENT", "affiliate_click")`
ผลคือ `traffic-verdict-20260801` เขียนว่า
> **PROVEN: reach คือคอขวด (funnel แปลงผลจริง)** · conv/session = 4.3%

อ่านแล้วเข้าใจว่าธุรกิจแปลงเป็นเงินได้ **ทั้งที่รายได้เป็นศูนย์** · affiliate_click คือ *คลิก* ไม่ใช่เงิน — จะเป็นเงินต่อเมื่อ AccessTrade อนุมัติ conversion และ 9 คลิก/28 วันต่ำกว่าเกณฑ์จ่ายมาก
**การใช้คำนี้ทำให้ทุกคน (รวมทั้ง agent ทุกตัว) เชื่อว่า funnel ทำงาน แล้วไปโฟกัสที่ reach แทนที่จะไปดูว่าปลายทางรับเงินได้จริงไหม**

### 🟡 สาเหตุที่ 4 — **ต่อให้ขายได้ ก็ไม่มีใครรู้**
`sales-log.jsonl` ว่างเปล่า · `tools/log_sale.py` มีอยู่แต่ไม่เคยถูกเรียก · ไม่มีงานไหนถามเจ้าของว่า "สัปดาห์นี้ขายได้ไหม"
ตัวชี้วัด North Star จึงวัดไม่ได้ **ไม่ว่าผลจะเป็นบวกหรือลบ**

---

## 🔴 งาน 1 (P0) · ใส่เส้นทางจ่ายเงินลงหน้าขาย

**ไฟล์: `debt-letter-kit.html` ที่ root ของ repo** (ไม่ใช่ `site/` — `build_site.py` L46 คัดลอกจาก root ไป `site/`)

ทำ:
1. เพิ่มบล็อกซื้อ **เหนือ fold แรกที่พูดถึงราคา** และ **ซ้ำอีกครั้งท้ายหน้า** (คนอ่านจบแล้วต้องมีปุ่มตรงนั้นเลย ไม่ต้องเลื่อนกลับ)
2. ให้ **2 ทางเลือกคู่กันเสมอ** อย่าบังคับทางเดียว:
   - **จ่ายด้วยบัตร/ทันที** → `https://ngernduangold.gumroad.com/l/debt-toolkit?utm_source=letterkit&utm_medium=primary&utm_campaign=toolkit199_page`
   - **คุยก่อน/โอนเอง** → `https://line.me/R/ti/p/@804qodya` (ของเดิม เก็บไว้)
3. เขียนให้ชัดว่าได้อะไร ราคาเท่าไร จ่ายแล้วเกิดอะไรขึ้นต่อ — **ห้ามใช้คำต้องห้าม** (การันตี · รับรองผล · อนุมัติแน่นอน · ตัวเลขดอกเบี้ยฟันธง) และต้องผ่าน `comply_gate`
4. **UTM ต้องเป็นรูปแบบเดียวกับที่ `/links` ใช้** เพื่อให้แยกได้ว่ายอดมาจากหน้าไหน — ถ้าไม่ใส่ จะกลับไปเป็นปัญหา "direct 166 sessions ที่แยกที่มาไม่ออก" อีก

**เกณฑ์ผ่าน:** `grep -c gumroad site/debt-letter-kit.html` ≥ 2 · UTM ครบทุกลิงก์ · disclosure ยังอยู่ · `preflight` check `disclosure` + `attribution` ยัง PASS

---

## 🔴 งาน 2 (P0) · เชื่อมหน้าที่คนอ่านจริง → หน้าขาย

**ไฟล์: `bureau-blacklist-loan-2026.html` และ `personal-loan-2026.html`** (ที่ root)

ทำ: เพิ่ม **next-step CTA ท้ายบทความ** ชี้ไป `/debt-letter-kit` แบบเดียวกับที่ `debt-consolidation-2026` ทำอยู่แล้ว (ลอกแพทเทิร์นจากหน้านั้น อย่าคิดถ้อยคำใหม่ — ความสม่ำเสมอคือเป้าหมาย)
`build_site.py` L451 มีตัวช่วยอยู่แล้ว: `<a href="/debt-letter-kit?utm_source=article&utm_medium=nextstep&utm_campaign=letter_kit">` — **ใช้ตัวนั้น**

⚠️ **อย่าใส่เป็น affiliate CTA above-the-fold** — 25 ก.ค. เพิ่งถอด affiliate ออกจาก above-fold ของ 12 หน้าเพื่อ E-E-A-T บนหน้า YMYL · CTA นี้เป็นสินค้าตัวเอง ไม่ใช่ affiliate แต่ยังต้องอยู่ท้ายเนื้อหา ไม่ใช่ขวางการอ่าน

**เกณฑ์ผ่าน:** ทั้งสองหน้าใน `site/` มี `debt-letter-kit` ≥ 1 · GSC-visible content ไม่ลดลง · smoke PASS

---

## 🟠 งาน 3 (P0) · เลิกเรียก `affiliate_click` ว่า "conversion"

แก้ที่ **ชั้นรายงาน** ไม่ใช่แค่เปลี่ยนตัวแปร:
1. `pipeline/ga4_pull.py` — เปลี่ยนหัวคอลัมน์และคีย์จาก `conversion` → **`affiliate_click`** (ชื่อจริงของ event) · เก็บ ENV override ไว้เหมือนเดิม
2. `pipeline/traffic_analyst.py` + `traffic_monitor` — ในรายงานให้แยกสองบรรทัดคนละความหมายชัดเจน:
   ```
   affiliate_click (คลิก ≠ เงิน)  : N
   ยอดขายจริง (sales-log.jsonl)   : N ชิ้น · N บาท
   ```
3. **ห้าม VERDICT ใช้คำว่า "แปลงผลจริง/PROVEN" จาก affiliate_click เพียงอย่างเดียว** — ถ้ายอดขาย = 0 ให้ VERDICT พูดตรงๆ ว่า *"ยังไม่มีหลักฐานว่าปลายทางรับเงินได้"*

> เหตุผล: verdict ปัจจุบันชี้ให้ทุ่ม reach ต่อ ทั้งที่ปลายทางยังไม่มีปุ่มซื้อ **การวัดผิดทำให้ทั้งระบบวิ่งผิดทาง ไม่ใช่แค่รายงานสวยเกินจริง**

**เกณฑ์ผ่าน:** รายงานรอบถัดไปแสดงสองบรรทัดแยกกัน · ไม่มีคำว่า conversion เดี่ยวๆ ที่หมายถึงคลิกอีก

---

## 🟡 งาน 4 (P1) · ปิดลูปการวัดยอด

1. เพิ่มขั้นตอนใน `ngernduangold-gsc-weekly` (หรือรูทีนรายสัปดาห์ของคุณ): รัน `py tools\sales_week.py` แล้ว
   - ถ้าว่าง → รายงานว่า **"ยอด 0 — ยืนยันแล้วว่าไม่มี ไม่ใช่ลืมบันทึก"** พร้อมคำสั่งพร้อมวางให้เจ้าของ:
     `py tools\log_sale.py --product letter-kit-199 --amount 199 --source line`
2. เพิ่ม check ใน preflight: **ถ้า `affiliate_click` > 0 แต่ `sales-log.jsonl` ว่างเกิน 14 วัน = WARN** *"มีคนคลิกแต่ไม่มียอดถูกบันทึก — ปลายทางพัง หรือลืมบันทึก อย่างใดอย่างหนึ่ง"*
   - ต้องมีเทสต์สองทิศ + บรรทัดใน `main()` (meta-test จะจับถ้าลืม)

---

## ⛔ ไม่ใช่งานคุณ — ผมจะทำ / เจ้าของต้องทำ

| เรื่อง | ใคร | หมายเหตุ |
|---|---|---|
| LINE OA: ยืนยันว่าแชทเปิด · auto-reply ทำงาน · friends เท่าไร | **เจ้าของ** | ต้อง login เอง · agent ห้ามกรอกรหัส · **นี่คือปลายทางเดียวของ 199฿ ตอนนี้ ถ้าแชทปิดอยู่ ทุกอย่างข้างบนไม่มีความหมาย** |
| Pantip ให้ CC ถือคนเดียว | **เจ้าของ** | ยังไม่เคาะ · ตัวเลขสนับสนุน: pantip 18 sessions → 5 คลิก (28%) + เป็นแหล่ง quiz_start ทั้ง 2 ครั้ง · สัปดาห์นี้ใช้โควตา **0/3** |
| 22 พรอมป์ตฝั่ง Cowork ที่ hard-code วันของช่อง | **ผม** | `check_policy_dates_in_prompts` ของคุณเปิดโปงให้เห็น ขอบคุณ |

---

## ✅ GATE
```
set SITE_GA=G-17PPE0M1B8 && python build_site.py
python tools/postdeploy_smoke.py --src site     → PASS ทุกหน้า
py tools\preflight.py                            → 0 fail
py tools\test_preflight_checks.py                → ALL PASS
py pipeline\comply_gate.py <ข้อความใหม่ที่เพิ่ม>  → ผ่าน
```
ตรวจเพิ่มด้วยตัวเลข:
- `grep -c gumroad site/debt-letter-kit.html` ≥ 2
- `grep -c debt-letter-kit site/bureau-blacklist-loan-2026.html` ≥ 1 และหน้า personal-loan ด้วย
- U+FFFD = 0 ในทุกไฟล์ที่แตะ

## 🚀 หลัง gate
commit แยกตามงาน → push → ย้าย order เข้า `done/`
รายงาน → `cc-outbox/result-zero-revenue-funnel-20260801-<ts>.md` ระบุ:
1. หน้าขายมีปุ่มอะไรบ้างหลังแก้ (paste รายการ href)
2. verdict รอบใหม่หน้าตาเป็นยังไงหลังแยก affiliate_click ออกจากยอดขาย
3. ตัวเลข gate ทุกบรรทัด

---

## 📌 สิ่งที่อยากให้คิดต่อ (ไม่ใช่คำสั่ง)
209 sessions/28 วัน = **7.5 คน/วัน** · ต่อให้ปุ่มซื้อครบและ LINE เปิด ตัวเลขนี้แปลงเป็นยอดได้ยากมาก
**แต่ลำดับสำคัญ: ซ่อมปลายทางให้รับเงินได้ก่อน แล้วค่อยเติม reach** — ถ้าเติม reach ตอนที่หน้าขายไม่มีปุ่มซื้อ คือเทน้ำใส่ถังรั่ว และจะได้ข้อสรุปผิดอีกว่า "reach ไม่พอ"
Pantip ที่ให้ 28% click-rate จาก 18 sessions คือหลักฐานว่า **คนที่มาจากที่ที่มีบริบทถูกต้อง มีพฤติกรรมต่างจาก direct อย่างสิ้นเชิง** — เมื่อปลายทางพร้อม นั่นคือช่องที่ควรทุ่ม
