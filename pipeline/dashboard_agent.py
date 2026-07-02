"""dashboard_agent.py — รีเจน automation-log/dashboard.html ด้วยเลขล่าสุดทุกครั้งที่ loop ยิง
อ่าน ga4-metrics.csv + verdict/queue ล่าสุด -> เขียนหน้า dashboard เดียว (เปิดไฟล์เดิมเห็นเลขใหม่)
ปลอดภัย: อ่าน/เขียนไฟล์เท่านั้น · ใช้: py pipeline/dashboard_agent.py
"""
import os, sys, glob, csv, datetime, re, html

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
AL = os.path.join(ROOT, "automation-log")
INBOX = os.path.join(AL, "cowork-inbox")
OUT = os.path.join(AL, "dashboard.html")


def _latest(pat):
    fs = sorted(glob.glob(os.path.join(INBOX, pat)))
    return fs[-1] if fs else None


def _read(p):
    try:
        return open(p, encoding="utf-8").read() if p else ""
    except Exception:
        return ""


def _ga4():
    rows, tot = [], {"sessions": 0, "quiz": 0, "conv": 0}
    p = os.path.join(AL, "ga4-metrics.csv")
    if os.path.exists(p):
        try:
            for r in csv.DictReader(open(p, encoding="utf-8")):
                d = {"src": r.get("source", "?"), "sessions": int(r.get("sessions") or 0),
                     "quiz": int(r.get("quiz_start") or 0), "conv": int(r.get("conversion") or 0)}
                rows.append(d)
                tot["sessions"] += d["sessions"]; tot["quiz"] += d["quiz"]; tot["conv"] += d["conv"]
        except Exception:
            pass
    rows.sort(key=lambda x: x["conv"], reverse=True)
    return rows, tot


def _verdict():
    t = _read(_latest("traffic-verdict-*.md"))
    v = re.search(r"## VERDICT\s*\n\*\*(.+?)\*\*", t)
    d = re.search(r"## DECISION[^\n]*\n(.+)", t)
    return (v.group(1).strip() if v else "—"), (d.group(1).strip() if d else "—")


def _queue():
    t = _read(_latest("post-queue-*.md"))
    return [l for l in t.splitlines() if l.startswith("| ") and "เวลา" not in l and "---" not in l]


def _credits():
    import json
    p = os.path.join(AL, "flow-credits.json")
    d = {"quota": 1000, "used": 0, "remaining": 1000, "clips": 66, "pct": 0}
    if os.path.exists(p):
        try:
            s = json.load(open(p, encoding="utf-8"))
            q = int(s.get("quota", 1000)); u = int(s.get("used", 0)); rem = max(0, q - u)
            d = {"quota": q, "used": u, "remaining": rem, "clips": rem // 15,
                 "pct": int(round(100.0 * u / q)) if q else 0}
        except Exception:
            pass
    return d


def _launch():
    import json
    p = os.path.join(AL, "launch-status.json")
    if not os.path.exists(p):
        return ""
    try:
        s = json.load(open(p, encoding="utf-8"))
    except Exception:
        return ""
    cmap = {"ok": "#3ddc97", "warn": "#e0a93c", "down": "#ff6b6b", "todo": "#8b98a5"}
    rows = ""
    for c in s.get("channels", []):
        col = cmap.get(c.get("st", "todo"), "#8b98a5")
        rows += ('<div class="bar" style="grid-template-columns:130px 1fr">'
                 '<span class="bl"><span style="display:inline-block;width:8px;height:8px;'
                 'border-radius:50%%;background:%s;margin-right:6px"></span>%s</span>'
                 '<span class="bv" style="text-align:left">%s</span></div>'
                 ) % (col, html.escape(c.get("name", "?")), html.escape(c.get("note", "")))
    pend = "".join("<tr><td>%s</td></tr>" % html.escape(x) for x in s.get("pending", []))
    card = ('<div class="card"><h2>🚀 Launch — %s <span style="color:#5b6673;font-weight:400">'
            '(อัปเดต %s · แก้ที่ automation-log/launch-status.json)</span></h2>%s'
            ) % (html.escape(s.get("product", "")), html.escape(s.get("updated", "")), rows)
    if pend:
        card += '<h2 style="margin-top:12px">⏳ รอดำเนินการ</h2><table>%s</table>' % pend
    card += "</div>"
    return card


def build():
    rows, tot = _ga4()
    verdict, decision = _verdict()
    q = _queue()
    cr = _credits()
    lc = _launch()
    pkgs = len(glob.glob(os.path.join(AL, "content-packages",
              datetime.date.today().strftime("%Y%m%d") + "*")))
    now = datetime.datetime.now().strftime("%d/%m/%Y %H:%M")
    mx = max([r["conv"] for r in rows] + [1])
    bars = ""
    for r in rows:
        if r["sessions"] == 0 and r["conv"] == 0:
            continue
        w = int(100 * r["conv"] / mx)
        bars += ('<div class="bar"><span class="bl">%s</span>'
                 '<span class="bt"><i style="width:%d%%"></i></span>'
                 '<span class="bv">%d conv · %d sess</span></div>') % (html.escape(r["src"]), w, r["conv"], r["sessions"])
    qrows = "".join("<tr><td>%s</td></tr>" % html.escape(l.strip("| ").replace("|", " · ")) for l in q[:9])
    proven = "PROVEN" in verdict
    vcolor = "#1D9E75" if proven else ("#BA7517" if "INSUFFICIENT" in verdict else "#A32D2D")
    doc = """<!doctype html><html lang="th"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>ngernduangold — Live Dashboard</title>
<style>
:root{color-scheme:light dark}
body{font-family:'Leelawadee UI',Tahoma,system-ui,sans-serif;margin:0;background:#0f1419;color:#e6edf3}
.wrap{max-width:860px;margin:0 auto;padding:22px 18px}
h1{font-size:19px;margin:0 0 2px}.sub{color:#8b98a5;font-size:12px;margin-bottom:18px}
.kpis{display:grid;grid-template-columns:repeat(4,1fr);gap:10px;margin-bottom:18px}
@media(max-width:560px){.kpis{grid-template-columns:repeat(2,1fr)}}
.kpi{background:#1a222c;border:1px solid #2a3540;border-radius:12px;padding:12px 14px}
.kpi b{display:block;font-size:24px}.kpi span{color:#8b98a5;font-size:11.5px}
.card{background:#1a222c;border:1px solid #2a3540;border-radius:12px;padding:14px 16px;margin-bottom:14px}
.card h2{font-size:13px;margin:0 0 10px;color:#b8c4d0}
.bar{display:grid;grid-template-columns:80px 1fr 120px;gap:8px;align-items:center;margin:5px 0;font-size:12px}
.bl{color:#cdd6e0;font-weight:600}.bt{background:#0f1419;border-radius:6px;height:14px;overflow:hidden}
.bt i{display:block;height:100%;background:linear-gradient(90deg,#1D9E75,#3ddc97);border-radius:6px}
.bv{color:#8b98a5;font-size:11px;text-align:right}
.vd{font-size:15px;font-weight:700}.dc{color:#b8c4d0;font-size:12.5px;margin-top:6px;line-height:1.6}
table{width:100%;border-collapse:collapse;font-size:11.5px}
td{border-top:1px solid #2a3540;padding:5px 4px;color:#cdd6e0}
.ft{color:#5b6673;font-size:11px;margin-top:8px;text-align:center}
.dot{display:inline-block;width:8px;height:8px;border-radius:50%;background:#3ddc97;margin-right:6px;animation:p 1.4s infinite}
@keyframes p{50%{opacity:.4}}
</style></head><body><div class="wrap">
<h1><span class="dot"></span>ngernduangold — Live Dashboard</h1>
<div class="sub">อัปเดตล่าสุด %NOW% · รีเจนเองทุกเช้า 07:00 (Task Scheduler) · ทุกอย่างฟรี</div>
<div class="kpis">
<div class="kpi"><b>%SESS%</b><span>GA4 sessions (28 วัน)</span></div>
<div class="kpi"><b>%CONV%</b><span>affiliate_click (conversion)</span></div>
<div class="kpi"><b>%QUIZ%</b><span>quiz_start</span></div>
<div class="kpi"><b>%PKG%</b><span>แพ็กเกจคอนเทนต์วันนี้</span></div>
</div>
%LAUNCH%
<div class="card"><h2>💳 Flow credits (วิดีโอ AI)</h2><div class="bar"><span class="bl">ใช้ไป</span><span class="bt"><i style="width:%CREDPCT%%;background:linear-gradient(90deg,#BA7517,#e0a93c)"></i></span><span class="bv">%CREDUSED%/%CREDQUOTA% · เหลือ %CREDREM% (~%CREDCLIPS% คลิป)</span></div></div>
<div class="card"><h2>conversion รายช่อง (GA4 จริง)</h2>%BARS%</div>
<div class="card"><h2>VERDICT (พิสูจน์ consult)</h2>
<div class="vd" style="color:%VCOLOR%">%VERDICT%</div><div class="dc">%DECISION%</div></div>
<div class="card"><h2>🗓️ ตารางคิวโพสต์ (post_agent · เวลาดีสุดจาก GA4)</h2>
<table>%QROWS%</table></div>
<div class="ft">ngernduangold growth loop · GA4 ปิดวง · คนกดโพสต์/deploy เท่านั้น</div>
</div></body></html>"""
    doc = (doc.replace("%NOW%", now).replace("%SESS%", str(tot["sessions"]))
           .replace("%CONV%", str(tot["conv"])).replace("%QUIZ%", str(tot["quiz"]))
           .replace("%PKG%", str(pkgs)).replace("%BARS%", bars or "<i style='color:#8b98a5'>ยังไม่มีข้อมูล</i>")
           .replace("%VCOLOR%", vcolor).replace("%VERDICT%", html.escape(verdict))
           .replace("%DECISION%", html.escape(decision)).replace("%QROWS%", qrows or "<tr><td>—</td></tr>")
           .replace("%CREDPCT%", str(cr["pct"])).replace("%CREDUSED%", str(cr["used"]))
           .replace("%CREDQUOTA%", str(cr["quota"])).replace("%CREDREM%", str(cr["remaining"]))
           .replace("%CREDCLIPS%", str(cr["clips"]))
           .replace("%LAUNCH%", lc))
    open(OUT, "w", encoding="utf-8").write(doc)
    print("[dashboard_agent] -> " + OUT + " | sessions=%d conv=%d verdict=%s" % (tot["sessions"], tot["conv"], verdict[:30]))
    return OUT


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    build()
