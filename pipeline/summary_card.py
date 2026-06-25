"""summary_card.py — เรนเดอร์ภาพสรุปรายวัน PNG (Pillow + ฟอนต์ไทย) สำหรับส่ง Telegram
ใช้เลขจริงล่าสุด (ga4-metrics + verdict ผ่าน dashboard_agent) · ใช้: py pipeline/summary_card.py
"""
import os, sys, datetime
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import dashboard_agent as D
from PIL import Image, ImageDraw, ImageFont

OUT = os.path.join(D.AL, "summary.png")
REG = r"C:\Windows\Fonts\leelawui.ttf"
BLD = r"C:\Windows\Fonts\leelawuib.ttf"
BG = (15, 20, 25); CARD = (26, 34, 44); WHITE = (230, 237, 243)
GRAY = (139, 152, 165); LB = (184, 196, 208); GREEN = (61, 220, 151); AMBER = (186, 117, 23)


def F(sz, bold=False):
    p = BLD if (bold and os.path.exists(BLD)) else REG
    try:
        return ImageFont.truetype(p, sz)
    except Exception:
        return ImageFont.load_default()


def rr(d, xy, r, fill):
    try:
        d.rounded_rectangle(xy, radius=r, fill=fill)
    except Exception:
        d.rectangle(xy, fill=fill)


def wrap(d, text, fnt, maxw):
    words, lines, cur = text.split(" "), [], ""
    for w in words:
        t = (cur + " " + w).strip()
        if d.textlength(t, font=fnt) <= maxw:
            cur = t
        else:
            if cur:
                lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines


def build():
    rows, tot = D._ga4()
    verdict, decision = D._verdict()
    proven = "PROVEN" in verdict
    W, H = 920, 560
    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img)
    d.text((40, 28), "ngernduangold — สรุปรายวัน", font=F(30, True), fill=WHITE)
    d.text((40, 72), datetime.datetime.now().strftime("%d/%m/%Y %H:%M") +
           " · GA4 ปิดวง · ยิงเองทุกเช้า 07:00", font=F(15), fill=GRAY)
    kp = [("GA4 sessions", tot["sessions"]), ("conversion (คลิก affiliate)", tot["conv"]), ("quiz_start", tot["quiz"])]
    bw = (W - 80 - 32) // 3
    for i, (lb, v) in enumerate(kp):
        x = 40 + i * (bw + 16)
        rr(d, [x, 110, x + bw, 200], 14, CARD)
        d.text((x + 18, 122), str(v), font=F(40, True), fill=WHITE)
        d.text((x + 18, 182), lb, font=F(12), fill=GRAY)
    rr(d, [40, 218, W - 40, 392], 14, CARD)
    d.text((58, 232), "conversion รายช่อง (GA4 จริง)", font=F(15, True), fill=LB)
    top = [r for r in rows if r["conv"] > 0][:5]
    mx = max([r["conv"] for r in top] + [1])
    y = 266
    for r in top:
        d.text((58, y - 2), r["src"], font=F(14, True), fill=WHITE)
        barw = int((W - 40 - 320) * r["conv"] / mx)
        rr(d, [150, y + 1, 150 + max(barw, 4), y + 16], 6, GREEN)
        txt = "%d conv · %d sess" % (r["conv"], r["sessions"])
        d.text((W - 60 - d.textlength(txt, font=F(12)), y), txt, font=F(12), fill=GRAY)
        y += 24
    rr(d, [40, 410, W - 40, 520], 14, CARD)
    d.text((58, 422), "VERDICT (พิสูจน์ consult)", font=F(13, True), fill=LB)
    d.text((58, 442), verdict, font=F(18, True), fill=GREEN if proven else AMBER)
    for i, ln in enumerate(wrap(d, decision, F(13), W - 120)[:2]):
        d.text((58, 478 + i * 20), ln, font=F(13), fill=LB)
    cr = D._credits()
    d.text((40, 532), "Flow credits เหลือ %d/%d (~%d คลิป) · คนกดโพสต์/deploy เท่านั้น · เลขจริงจาก GA4"
           % (cr["remaining"], cr["quota"], cr["clips"]), font=F(12), fill=(91, 102, 115))
    img.save(OUT)
    print("[summary_card] -> " + OUT)
    return OUT


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    build()
