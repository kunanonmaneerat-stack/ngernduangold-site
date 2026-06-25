"""posting_kit.py — สร้าง posting-kit.html: ชุดโพสต์กดง่ายสุดสำหรับเจ้าของ
อ่าน post-plan.json -> การ์ดรายคลิป (เรียงตามลำดับโพสต์) พร้อมปุ่ม คัดลอก path ไฟล์ + คัดลอกแคปชัน + เวลา
เจ้าของ: กดเพิ่มวิดีโอ -> วาง path -> Enter -> กดคัดลอกแคปชัน -> วาง -> ตั้งเวลา -> Schedule
ปลอดภัย: สร้างไฟล์ HTML เท่านั้น · ใช้: py pipeline/posting_kit.py
"""
import os, sys, json, html, datetime
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
AL = os.path.join(ROOT, "automation-log")
PLAN = os.path.join(AL, "post-plan.json")
OUT = os.path.join(AL, "posting-kit.html")
WIN_ROOT = r"C:\Users\nL_ku\ngernduangold-site"
SBX_ROOT = ROOT
DAYS_TH = {0: "อา", 1: "จ", 2: "อ", 3: "พ", 4: "พฤ", 5: "ศ", 6: "ส"}


def winpath(p):
    if p and p.startswith(SBX_ROOT):
        p = WIN_ROOT + p[len(SBX_ROOT):]
    return p.replace("/", "\\")


def _d(iso):
    try:
        dt = datetime.date.fromisoformat(iso)
        return "%s %02d/%02d" % (DAYS_TH[(dt.weekday() + 1) % 7], dt.day, dt.month)
    except Exception:
        return iso


def build():
    plan = json.load(open(PLAN, encoding="utf-8")).get("plan", [])
    cards = ""
    for i, p in enumerate(plan, 1):
        wp = winpath(p.get("file", ""))
        cap = "%s 👇 คอมเมนต์ \"เช็กสิทธิ์\" รับตัวช่วยฟรีทาง DM\n%s" % (p.get("caption", ""), p.get("hashtags", ""))
        wk = (i - 1) // 7 + 1
        cards += """
<div class="card" data-wk="%d">
  <div class="hd"><b>#%02d</b> <span class="tp">%s · %s</span>
    <span class="wkpill">สัปดาห์ %d</span></div>
  <div class="meta">📅 %s &nbsp;·&nbsp; TikTok %02d:00 · <b style="color:#E1306C">IG %02d:00</b> · YT %02d:00</div>
  <div class="file"><code id="f%d">%s</code></div>
  <div class="btns">
    <button class="b1" onclick="cp('f%d',this)">📋 คัดลอก path ไฟล์</button>
    <button class="b2" onclick="cp('c%d',this)">📝 คัดลอกแคปชัน</button>
  </div>
  <textarea id="c%d" class="cap" readonly>%s</textarea>
</div>""" % (wk, i, html.escape(p.get("topic", "")), html.escape(p.get("label", "")), wk,
            _d(p.get("day", "")), p.get("tiktok", 19), p.get("ig", 20), p.get("yt", 18),
            i, html.escape(wp), i, i, i, html.escape(cap))

    doc = """<!doctype html><html lang="th"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>ชุดโพสต์กดง่าย — ngernduangold</title>
<style>
body{font-family:'Leelawadee UI',Tahoma,system-ui,sans-serif;margin:0;background:#0f1419;color:#e6edf3}
.wrap{max-width:680px;margin:0 auto;padding:18px 14px 60px}
h1{font-size:18px;margin:0 0 4px}.sub{color:#8b98a5;font-size:12.5px;line-height:1.7;margin-bottom:12px}
.how{background:#16202b;border:1px solid #2a3540;border-radius:10px;padding:10px 12px;font-size:12.5px;color:#b8c4d0;line-height:1.8;margin-bottom:14px}
.how b{color:#3ddc97}
.filter{display:flex;gap:6px;flex-wrap:wrap;margin-bottom:12px}
.filter button{background:#1a222c;border:1px solid #2a3540;color:#cdd6e0;border-radius:20px;padding:5px 12px;font-size:12px;cursor:pointer}
.filter button.on{background:#1D9E75;border-color:#1D9E75;color:#fff}
.card{background:#1a222c;border:1px solid #2a3540;border-radius:12px;padding:12px 13px;margin-bottom:11px}
.hd{font-size:14px}.hd b{color:#3ddc97;margin-right:6px}.tp{color:#cdd6e0}
.wkpill{float:right;background:#222c38;color:#8b98a5;font-size:10.5px;padding:2px 8px;border-radius:20px}
.meta{color:#8b98a5;font-size:12px;margin:6px 0 8px}
.file{background:#0f1419;border-radius:7px;padding:7px 9px;margin-bottom:8px;overflow:auto}
.file code{color:#9fd0ff;font-size:11.5px;white-space:nowrap}
.btns{display:flex;gap:8px}
.btns button{flex:1;border:0;border-radius:8px;padding:10px;font-size:13px;font-weight:600;cursor:pointer}
.b1{background:#2a6fdb;color:#fff}.b2{background:#1D9E75;color:#fff}
.btns button.done{background:#3ddc97;color:#06281c}
.cap{width:100%;box-sizing:border-box;margin-top:8px;background:#0f1419;color:#cdd6e0;border:1px solid #2a3540;border-radius:7px;padding:8px;font-size:12px;height:62px;resize:vertical;font-family:inherit}
.ft{color:#5b6673;font-size:11px;text-align:center;margin-top:14px}
</style></head><body><div class="wrap">
<h1>📋 ชุดโพสต์กดง่าย — เงินเดือนสมองทอง</h1>
<div class="sub">36 คลิป เรียงตามลำดับโพสต์ · เปิดไฟล์นี้บนเครื่องที่จะโพสต์</div>
<div class="how">
<b>วิธีโพสต์ 1 คลิป (~30 วิ):</b><br>
1) ใน Business Suite กด <b>สร้างคลิป Reels</b> → <b>เพิ่มวิดีโอ</b><br>
2) ในหน้าต่างเลือกไฟล์ กด <b>คัดลอก path ไฟล์</b> ที่นี่ → คลิกช่อง "ชื่อไฟล์" ในหน้าต่าง → <b>Ctrl+V</b> → Enter<br>
3) กด <b>คัดลอกแคปชัน</b> → คลิกช่องข้อความ → <b>Ctrl+V</b><br>
4) เลือก IG+FB → <b>ถัดไป</b> → กำหนดเวลา ตามเวลาในการ์ด → <b>Schedule</b>
</div>
<div class="filter">
<button class="on" onclick="flt(0,this)">ทั้งหมด</button>
<button onclick="flt(1,this)">สัปดาห์ 1</button><button onclick="flt(2,this)">สัปดาห์ 2</button>
<button onclick="flt(3,this)">สัปดาห์ 3</button><button onclick="flt(4,this)">สัปดาห์ 4</button>
<button onclick="flt(5,this)">สัปดาห์ 5</button><button onclick="flt(6,this)">สัปดาห์ 6</button>
</div>
%CARDS%
<div class="ft">ทุกคลิปปิดท้าย CTA: คอมเมนต์ "เช็กสิทธิ์" · คนกดโพสต์เอง</div>
</div>
<script>
function cp(id,btn){var el=document.getElementById(id);var t=el.tagName=='TEXTAREA'?el.value:el.textContent;
navigator.clipboard.writeText(t).then(function(){var o=btn.textContent;btn.textContent='✓ คัดลอกแล้ว';btn.classList.add('done');
setTimeout(function(){btn.textContent=o;btn.classList.remove('done');},1400);});}
function flt(w,btn){document.querySelectorAll('.filter button').forEach(function(b){b.classList.remove('on');});btn.classList.add('on');
document.querySelectorAll('.card').forEach(function(c){c.style.display=(w==0||c.dataset.wk==w)?'':'none';});}
</script></body></html>"""
    open(OUT, "w", encoding="utf-8").write(doc.replace("%CARDS%", cards))
    print("[posting_kit] -> %s (%d คลิป)" % (OUT, len(plan)))
    return OUT


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    build()
