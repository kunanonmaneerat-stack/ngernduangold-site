# -*- coding: utf-8 -*-
# Generate 3 portrait (1080x1350) Pinterest infographics for the secured-loan cluster,
# matching the existing infographic template (navy+gold, Noto Serif Thai + Sarabun).
# noindex -> smoke skips them. Capture (html2canvas) happens later in a Chrome session.
import io

CSS = """*{margin:0;padding:0;box-sizing:border-box}
:root{--navy:#0F172A;--gold:#C5A880;--gold-lt:#D8C29A;--warm:#F5EFE3;--muted:#9AA4B2;--line:rgba(197,168,128,.22);
--serif:'Noto Serif Thai',Georgia,serif;--sans:'Sarabun','Leelawadee UI','Tahoma',sans-serif;}
html,body{width:1080px;height:1350px}
body{font-family:var(--sans);color:var(--warm);background:radial-gradient(120% 80% at 80% -10%,#233047 0%,#0F172A 46%,#0A0F1C 100%);
padding:64px 70px 54px;display:flex;flex-direction:column;position:relative;overflow:hidden}
body::before{content:"";position:absolute;right:-160px;top:-120px;width:520px;height:520px;border-radius:50%;
background:radial-gradient(circle,rgba(197,168,128,.16),transparent 62%)}
.brand{display:flex;align-items:center;gap:13px;font-weight:700;font-size:30px}
.brand .coin{width:46px;height:46px;border-radius:50%;background:linear-gradient(145deg,#E7Cf9b,#C5A880 55%,#9c7e4f);
display:flex;align-items:center;justify-content:center;font-size:24px;color:#3a2c10;box-shadow:0 4px 14px rgba(0,0,0,.4)}
.brand .nm{color:var(--gold-lt)}
.kick{margin-top:34px;display:inline-block;align-self:flex-start;font-weight:600;font-size:24px;color:var(--navy);
background:linear-gradient(145deg,#E7Cf9b,#C5A880);padding:8px 20px;border-radius:999px;letter-spacing:.3px}
h1{font-family:var(--serif);font-weight:700;font-size:74px;line-height:1.18;margin-top:26px;color:#fff}
h1 .hl{color:var(--gold-lt)}
.sub{font-size:29px;color:var(--muted);margin-top:18px;font-weight:500;line-height:1.5}
.pts{margin-top:40px;display:flex;flex-direction:column;gap:22px}
.pt{display:flex;align-items:flex-start;gap:22px;background:rgba(197,168,128,.07);border:1px solid var(--line);
border-radius:18px;padding:24px 26px}
.pt .ck{flex:none;width:48px;height:48px;border-radius:50%;background:linear-gradient(145deg,#E7Cf9b,#C5A880);
display:flex;align-items:center;justify-content:center;color:var(--navy);font-size:28px;font-weight:800}
.pt .tx{font-size:31px;font-weight:600;color:var(--warm);line-height:1.34}
.note{margin-top:30px;display:flex;align-items:flex-start;gap:14px;font-size:23px;color:var(--gold-lt);font-weight:600;line-height:1.45}
.note .ic{font-size:26px}
.foot{margin-top:auto;padding-top:30px;border-top:1.5px solid var(--line);display:flex;align-items:flex-end;justify-content:space-between;gap:20px}
.cta .t1{font-size:23px;color:var(--muted);font-weight:500}
.cta .t2{font-size:36px;font-weight:700;color:var(--gold-lt);margin-top:4px}
.cta .t2 .arrow{color:#fff}
.disc{font-size:16.5px;color:#6b7486;max-width:340px;text-align:right;line-height:1.5}"""

TPL = """<!doctype html><html lang="th"><head><meta charset="utf-8">
<title>{title}</title><meta name="robots" content="noindex">
<meta property="og:title" content="{ogt}"><meta property="og:description" content="{ogd}">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Noto+Serif+Thai:wght@500;700&family=Sarabun:wght@400;500;600;700&display=swap" rel="stylesheet">
<style>{css}</style></head>
<body>
  <div class="brand"><span class="coin">฿</span><span class="nm">เงินเดือนสมองทอง</span></div>
  <span class="kick">{kick}</span>
  <h1>{h1}</h1>
  <div class="sub">{sub}</div>
  <div class="pts">{pts}</div>
  <div class="note"><span class="ic">⚠️</span><span>{note}</span></div>
  <div class="foot">
    <div class="cta"><div class="t1">อ่านเต็ม + เทียบเงื่อนไขจริง</div>
      <div class="t2">ngernduangold.netlify.app <span class="arrow">→</span></div></div>
    <div class="disc">{disc}</div>
  </div>
</body></html>"""

DISC = "ข้อมูลเพื่อการศึกษา · เงื่อนไข/ดอกเบี้ย/วงเงิน/การอนุมัติเป็นไปตามผู้ให้บริการ ยึดแนวทาง Responsible Lending ของ ธปท. กู้เท่าที่จำเป็นและผ่อนไหว"

CFG = [
 dict(fn="home-land-for-cash-infographic.html",
   title="บ้าน/ที่ดินแลกเงิน 2026 — สินเชื่อมีหลักประกัน | เงินเดือนสมองทอง",
   ogt="บ้าน/ที่ดินแลกเงิน 2026 — สินเชื่อมีหลักประกัน วงเงินสูง",
   ogd="ใช้บ้าน/คอนโด/ที่ดินค้ำ วงเงินสูง ดอกต่ำกว่าบัตร ยังอยู่อาศัยได้ — เงินเดือนสมองทอง",
   kick="สินเชื่อมีหลักประกัน · 2026",
   h1='บ้าน/ที่ดิน<br><span class="hl">แลกเงิน</span>',
   sub="ใช้บ้าน/คอนโด/ที่ดินที่มีอยู่ค้ำ — วงเงินสูง ยังอยู่อาศัยได้",
   pts=["วงเงินสูงตามราคาประเมินหลักทรัพย์","ดอกมักต่ำกว่าบัตร/จำนำทะเบียนรถ",
        "ยังอยู่อาศัย/ใช้ที่ดินได้ (จำนอง ≠ ขายฝาก)","ต้องเป็นชื่อเรา · เทียบหลายเจ้าก่อนเซ็น"],
   note="เอาบ้านค้ำมีความเสี่ยงถูกบังคับหลักประกันหากผ่อนไม่ไหว — กู้เท่าที่จำเป็น"),
 dict(fn="motorcycle-title-loan-infographic.html",
   title="จำนำทะเบียนมอเตอร์ไซค์ 2026 — ยังขับได้ | เงินเดือนสมองทอง",
   ogt="จำนำทะเบียนมอเตอร์ไซค์ 2026 — ได้เงินด่วน ยังขับรถได้",
   ogd="เอาเล่มทะเบียนมอไซค์ค้ำ ได้เงินด่วน ยังขับรถได้ ดอกถูกกว่านอกระบบ — เงินเดือนสมองทอง",
   kick="จำนำทะเบียน · 2026",
   h1='จำนำทะเบียน<br><span class="hl">มอเตอร์ไซค์</span>',
   sub="เอาเล่มทะเบียนมอไซค์ค้ำ — ได้เงินด่วน ยังขับรถได้",
   pts=["ยังขับรถได้ตามปกติ (เอาเล่มค้ำ)","รู้ผลไว เหมาะเงินด่วนก้อนเล็ก-กลาง",
        "ดอกถูกกว่าหนี้นอกระบบมาก","ดูดอกแบบลดต้นลดดอก + ผู้ให้บริการมีใบอนุญาต"],
   note="รถคือหลักประกัน — กู้เท่าที่ผ่อนไหว เลี่ยงแบบโอนเล่ม"),
 dict(fn="car-refinance-infographic.html",
   title="รีไฟแนนซ์รถ 2026 — ลดดอก/ลดค่างวด | เงินเดือนสมองทอง",
   ogt="รีไฟแนนซ์รถ 2026 — ลดดอก/ลดค่างวด",
   ogd="ยังผ่อนรถอยู่ ทำสัญญาใหม่ลดดอก/ค่างวด บางกรณีได้เงินส่วนต่าง — เงินเดือนสมองทอง",
   kick="รีไฟแนนซ์รถ · 2026",
   h1='รีไฟแนนซ์<span class="hl">รถ</span>',
   sub="ยังผ่อนรถอยู่ — ทำสัญญาใหม่ ลดดอก/ลดค่างวด",
   pts=["ลดดอก/ค่างวดต่อเดือนให้เบาลง","บางกรณีได้เงินส่วนต่างเพิ่ม (cash-out)",
        "ยังขับรถได้ปกติ","ดูดอกรวมตลอดสัญญา ไม่ใช่แค่ค่างวด"],
   note="เทียบดอกรวม + ค่าปิดสัญญาเดิม ก่อนตัดสินใจ"),
]

for c in CFG:
    pts="".join(f'<div class="pt"><span class="ck">✓</span><span class="tx">{p}</span></div>' for p in c["pts"])
    html=TPL.format(title=c["title"],ogt=c["ogt"],ogd=c["ogd"],css=CSS,kick=c["kick"],
                    h1=c["h1"],sub=c["sub"],pts=pts,note=c["note"],disc=DISC)
    io.open(c["fn"],"w",encoding="utf-8").write(html)
    print("wrote",c["fn"],len(html),"bytes")

# patch copy-list
P="build_site.py"; s=io.open(P,encoding="utf-8").read()
anc='("budget-503020-infographic.html","budget-503020-infographic.html")]'
assert s.count(anc)==1,("copylist",s.count(anc))
add=('("budget-503020-infographic.html","budget-503020-infographic.html"),'
     '("home-land-for-cash-infographic.html","home-land-for-cash-infographic.html"),'
     '("motorcycle-title-loan-infographic.html","motorcycle-title-loan-infographic.html"),'
     '("car-refinance-infographic.html","car-refinance-infographic.html")]')
s=s.replace(anc,add,1)
io.open(P,"w",encoding="utf-8").write(s)
print("OK: copy-list patched (+3 loan infographics)")
