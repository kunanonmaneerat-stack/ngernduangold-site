"""post_dispatcher.py — Agent สะพาน: 'สอบถามวิดีโอจาก Cowork' -> สร้างตารางโพสต์เต็ม -> ส่ง post agent
อ่านคลังวิดีโอ (video-ingest.json/video-out) + EXPECTED (คลิปที่เจนแล้วใน Flow)
-> ปฏิทินโพสต์ 1 คลิป/วัน cross-post TikTok + IG Reels + YT Shorts ตามเวลาดีสุดต่อแพลตฟอร์ม (post_timing)
-> เขียน: cowork-inbox/post-plan-<ts>.md (ตารางรวม + ตาราง IG เฉพาะ) + automation-log/content-calendar.html + post-plan.json
ปลอดภัย: อ่าน/เขียนไฟล์เท่านั้น · คนกดโพสต์เอง
ใช้: py pipeline/post_dispatcher.py   |   status
"""
import os, sys, json, glob, datetime, html

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
AL = os.path.join(ROOT, "automation-log")
INBOX = os.path.join(AL, "cowork-inbox")
LIB = os.path.join(AL, "video-out")
INGEST = os.path.join(AL, "video-ingest.json")
CAL = os.path.join(AL, "content-calendar.html")
FLOW_URL = "https://labs.google/fx/tools/flow"
DAYS_TH = {0: "อา", 1: "จ", 2: "อ", 3: "พ", 4: "พฤ", 5: "ศ", 6: "ส"}

# คลิปที่เจนแล้วใน Flow (source of truth ของลำดับ) — (slug, ชื่อหัวข้อไทย, [ฉาก])
EXPECTED = [
    ("debt-consolidate", "หนี้บัตร/รวมหนี้",
     ["01-hook ความรู้สึกติดกับดัก", "02-problem ยอดไม่ลด", "03-solution ทางเลือก", "04-caution รับผิดชอบ", "05-action เช็กสิทธิ์"]),
    ("save-paycheck", "เงินเดือนชนเดือน/ออม",
     ["01-hook เงินหายวันเดียว", "02-เขียนโน้ตหักก่อนใช้", "03-ตั้งโอนอัตโนมัติ", "04-ยิ้มถือสมุด", "05-เหรียญหยอด", "06-planner เปิด"]),
    ("title-loan", "สินเชื่อทะเบียนรถ",
     ["01-hook นั่งในรถกังวล", "02-นับเงินไม่พอ", "03-ใช้รถได้ระหว่างกู้", "04-เทียบดอกเบี้ย", "05-เช็กสิทธิ์"]),
    ("emergency-fund", "เงินสำรองฉุกเฉิน",
     ["01-hook บิลไม่คาดฝัน", "02-กระเป๋าว่าง", "03-หยอดเงินใส่โหล", "04-วางแผนทีละขั้น", "05-แอปออมเงิน"]),
    ("first-card", "บัตรเครดิตใบแรก",
     ["01-hook ถือบัตรเปล่า", "02-อ่าน fine print", "03-จดข้อควรรู้", "04-จ่ายเต็มตามรอบ", "05-เทียบ/เช็กสิทธิ์"]),
    ("refinance", "รีไฟแนนซ์บ้าน",
     ["01-hook กองเอกสารกู้บ้าน", "02-ดอกเบี้ยพุ่ง", "03-เทียบสัญญา", "04-เช็กลิสต์ค่าธรรมเนียม", "05-เทียบ/เช็กสิทธิ์"]),
    ("credit-score", "เครดิตบูโร/สกอร์",
     ["01-hook ดูสกอร์ในมือถือ", "02-จดหมายปฏิเสธ", "03-อ่านรายงานเครดิต", "04-จ่ายตรงเวลา", "05-เช็กสกอร์ในแอป"]),
]
CAP = {
    "debt-consolidate": ("หนี้บัตรหลายใบ จ่ายขั้นต่ำยอดไม่ลด? รู้จักสินเชื่อรวมหนี้แบบเข้าใจง่าย",
                         "#fyp #การเงินส่วนบุคคล #รวมหนี้ #หนี้บัตรเครดิต #เงินเดือนสมองทอง"),
    "save-paycheck": ("เงินเดือนชนเดือน? เริ่ม 'หักก่อนใช้' อัตโนมัติ ออมได้จริงไม่ต้องรอเหลือ",
                      "#fyp #การเงินส่วนบุคคล #ออมเงินง่ายๆ #เงินเดือนชนเดือน #เงินเดือนสมองทอง"),
    "title-loan": ("ต้องการเงินด่วนแต่ยังอยากใช้รถ? เข้าใจสินเชื่อทะเบียนรถก่อนตัดสินใจ",
                   "#fyp #การเงินส่วนบุคคล #สินเชื่อทะเบียนรถ #เงินด่วน #เงินเดือนสมองทอง"),
    "emergency-fund": ("เงินสำรองฉุกเฉินสำคัญแค่ไหน? เริ่มทีละนิดให้ถึง 3-6 เดือน",
                       "#fyp #การเงินส่วนบุคคล #เงินสำรองฉุกเฉิน #ออมเงิน #เงินเดือนสมองทอง"),
    "first-card": ("บัตรเครดิตใบแรก? รู้ก่อนสมัคร จ่ายเต็มทุกรอบ ไม่กลายเป็นหนี้",
                   "#fyp #การเงินส่วนบุคคล #บัตรเครดิต #วางแผนการเงิน #เงินเดือนสมองทอง"),
    "refinance": ("ผ่อนบ้านดอกเบี้ยพุ่งหลังหมดโปร? รีไฟแนนซ์ช่วยลดดอกได้ รู้ก่อนตัดสินใจ",
                  "#fyp #การเงินส่วนบุคคล #รีไฟแนนซ์บ้าน #สินเชื่อบ้าน #เงินเดือนสมองทอง"),
    "credit-score": ("ขอกู้ไม่ผ่านไม่รู้สาเหตุ? เข้าใจเครดิตบูโร/เครดิตสกอร์ เช็กก่อนยื่นกู้",
                     "#fyp #การเงินส่วนบุคคล #เครดิตบูโร #เครดิตสกอร์ #เงินเดือนสมองทอง"),
}
KW = "เช็กสิทธิ์"


def _library():
    items = []
    if os.path.exists(INGEST):
        try:
            items = json.load(open(INGEST, encoding="utf-8")).get("items", [])
        except Exception:
            items = []
    return items


def _platform_hours():
    d = {"tiktok": 21, "ig": 20, "yt": 20}
    try:
        import post_timing
        s = post_timing.analyze().get("slots", {})
        for p in d:
            if s.get(p):
                d[p] = s[p][0][0]
    except Exception:
        pass
    return d


def _clips():
    """รายการคลิปทั้งหมด (จาก EXPECTED) + แนบ path ถ้ามีในคลัง"""
    lib = _library()
    out = []
    for slug, th, scenes in EXPECTED:
        libt = [it for it in lib if it.get("topic") == slug]
        for i, sc in enumerate(scenes):
            f = libt[i]["dest"] if i < len(libt) else ""
            out.append({"slug": slug, "topic_th": th, "label": sc, "file": f})
    return out


def dispatch():
    clips = _clips()
    hrs = _platform_hours()
    start = datetime.date.today() + datetime.timedelta(days=1)
    in_lib = sum(1 for c in clips if c["file"])
    ts = datetime.datetime.now().strftime("%Y%m%d-%H%M")

    rows = []          # ตารางรวม
    ig_rows = []       # ตาราง IG เฉพาะ
    plan = []
    for i, c in enumerate(clips):
        day = start + datetime.timedelta(days=i)
        dstr = "%s %02d/%02d" % (DAYS_TH[(day.weekday() + 1) % 7], day.day, day.month)
        cap, tags = CAP.get(c["slug"], (c["topic_th"], "#fyp #การเงินส่วนบุคคล #เงินเดือนสมองทอง"))
        rows.append((dstr, c["topic_th"], c["label"], hrs["tiktok"], hrs["ig"], hrs["yt"], bool(c["file"])))
        ig_rows.append((dstr, hrs["ig"], c["topic_th"], c["label"], cap, tags))
        plan.append({"day": day.isoformat(), "topic": c["topic_th"], "label": c["label"],
                     "file": c["file"], "tiktok": hrs["tiktok"], "ig": hrs["ig"], "yt": hrs["yt"],
                     "caption": cap, "hashtags": tags, "cta": "คอมเมนต์ " + KW})

    # ---------- markdown ----------
    L = ["# 🗓️ ตารางโพสต์คอนเทนต์ (post_dispatcher -> post agent) " + datetime.datetime.now().strftime("%Y-%m-%d %H:%M"),
         "> %d คลิป · 1 คลิป/วัน cross-post 3 แพลตฟอร์ม · เวลาดีสุด: TikTok %02d:00 · IG Reels %02d:00 · YT Shorts %02d:00" %
         (len(clips), hrs["tiktok"], hrs["ig"], hrs["yt"]),
         "> ทุกคลิปปิดท้าย CTA: คอมเมนต์ \"%s\" -> auto-DM /quiz · ก่อนโพสต์ใส่ข้อความบนจอ(ไทย)+เสียงตามตาราง shot" % KW,
         "> ไฟล์ในเครื่องแล้ว %d/%d คลิป%s" % (in_lib, len(clips),
            "" if in_lib == len(clips) else " — ที่เหลือโหลดจาก Flow ก่อน (ดูท้ายไฟล์)"),
         "", "## ตารางรวม",
         "| วัน | หัวข้อ · ฉาก | TikTok | IG Reels | YT Shorts | ไฟล์ |",
         "|---|---|---|---|---|---|"]
    for d, th, lb, tk, ig, yt, hasf in rows:
        L.append("| %s | %s · %s | %02d:00 | %02d:00 | %02d:00 | %s |" %
                 (d, th, lb, tk, ig, yt, "✅" if hasf else "⬇️รอโหลด"))
    L += ["", "## 📸 ตาราง IG Reels (เฉพาะ Instagram)",
          "| วัน · เวลา | คลิป | แคปชัน IG | แฮชแท็ก |", "|---|---|---|---|"]
    for d, ig, th, lb, cap, tags in ig_rows:
        L.append("| %s %02d:00 | %s · %s | %s | %s |" % (d, ig, th, lb, cap, tags))
    if in_lib < len(clips):
        L += ["", "## ⬇️ ก่อนโพสต์: โหลดคลิปจาก Flow (1 คลิก/คลิป)",
              "1. เปิด %s -> คลิปละ: คลิก -> Download (มุมขวาบน) -> ลง Downloads" % FLOW_URL,
              "2. `py pipeline\\video_downloader.py scan`  แล้ว  `py pipeline\\post_dispatcher.py` (ตารางจะเติม path ✅ ให้เอง)"]
    os.makedirs(INBOX, exist_ok=True)
    open(os.path.join(INBOX, "post-plan-" + ts + ".md"), "w", encoding="utf-8").write("\n".join(L))
    json.dump({"updated": ts, "clips": len(clips), "in_lib": in_lib, "hours": hrs, "plan": plan},
              open(os.path.join(AL, "post-plan.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=2)

    _calendar_html(rows, ig_rows, hrs, in_lib, len(clips))
    print("[post_dispatcher] ตาราง %d คลิป (ในเครื่อง %d) · IG %02d:00 · -> post-plan-%s.md + content-calendar.html" %
          (len(clips), in_lib, hrs["ig"], ts))
    return plan


def _calendar_html(rows, ig_rows, hrs, in_lib, total):
    now = datetime.datetime.now().strftime("%d/%m/%Y %H:%M")
    tr = ""
    for d, th, lb, tk, ig, yt, hasf in rows:
        tr += ("<tr><td>%s</td><td class='tp'>%s<span>%s</span></td>"
               "<td>%02d:00</td><td class='ig'>%02d:00</td><td>%02d:00</td><td>%s</td></tr>") % (
               html.escape(d), html.escape(th), html.escape(lb), tk, ig, yt, "✅" if hasf else "⬇️")
    igtr = ""
    for d, ig, th, lb, cap, tags in ig_rows:
        igtr += ("<tr><td>%s %02d:00</td><td class='tp'>%s<span>%s</span></td>"
                 "<td>%s</td><td class='tag'>%s</td></tr>") % (
                 html.escape(d), ig, html.escape(th), html.escape(lb), html.escape(cap), html.escape(tags))
    doc = """<!doctype html><html lang="th"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>ngernduangold — ตารางโพสต์</title>
<style>
body{font-family:'Leelawadee UI',Tahoma,system-ui,sans-serif;margin:0;background:#0f1419;color:#e6edf3}
.wrap{max-width:960px;margin:0 auto;padding:22px 16px}
h1{font-size:19px;margin:0 0 2px}.sub{color:#8b98a5;font-size:12px;margin-bottom:8px}
h2{font-size:14px;color:#b8c4d0;margin:20px 0 8px}
table{width:100%;border-collapse:collapse;font-size:12px;background:#1a222c;border-radius:10px;overflow:hidden}
th,td{padding:7px 9px;text-align:left;border-top:1px solid #2a3540;vertical-align:top}
th{background:#222c38;color:#b8c4d0;font-size:11px}
.tp{font-weight:600;color:#cdd6e0}.tp span{display:block;color:#8b98a5;font-weight:400;font-size:11px}
.ig{color:#E1306C;font-weight:700}.tag{color:#8b98a5;font-size:11px}
.pill{display:inline-block;background:#1D9E75;color:#fff;font-size:11px;padding:2px 9px;border-radius:20px;margin-left:6px}
.igband{background:linear-gradient(90deg,#F58529,#DD2A7B,#8134AF);padding:2px;border-radius:11px;margin-top:6px}
.igband table{border-radius:9px}
.ft{color:#5b6673;font-size:11px;margin-top:12px;text-align:center}
.dot{display:inline-block;width:8px;height:8px;border-radius:50%;background:#3ddc97;margin-right:6px}
</style></head><body><div class="wrap">
<h1><span class="dot"></span>ตารางโพสต์คอนเทนต์วิดีโอ <span class="pill">%TOT% คลิป</span></h1>
<div class="sub">อัปเดต %NOW% · 1 คลิป/วัน cross-post · TikTok %TK%:00 · <b style="color:#E1306C">IG Reels %IG%:00</b> · YT Shorts %YT%:00 · ในเครื่อง %INLIB%/%TOT% · CTA: คอมเมนต์ "เช็กสิทธิ์"</div>
<h2>ตารางรวม (TikTok + IG Reels + YT Shorts)</h2>
<table><tr><th>วัน</th><th>หัวข้อ · ฉาก</th><th>TikTok</th><th>IG Reels</th><th>YT Shorts</th><th>ไฟล์</th></tr>%TR%</table>
<h2>📸 ตาราง IG Reels (เฉพาะ Instagram)</h2>
<div class="igband"><table><tr><th>วัน · เวลา</th><th>คลิป</th><th>แคปชัน IG</th><th>แฮชแท็ก</th></tr>%IGTR%</table></div>
<div class="ft">ngernduangold growth loop · คนกดโพสต์เอง · โหลดคลิปจาก Flow ก่อน แล้ว video_downloader+post_dispatcher เติมตารางให้</div>
</div></body></html>"""
    doc = (doc.replace("%NOW%", now).replace("%TOT%", str(total)).replace("%INLIB%", str(in_lib))
           .replace("%TK%", "%02d" % hrs["tiktok"]).replace("%IG%", "%02d" % hrs["ig"]).replace("%YT%", "%02d" % hrs["yt"])
           .replace("%TR%", tr).replace("%IGTR%", igtr))
    open(CAL, "w", encoding="utf-8").write(doc)


def status():
    print("[post_dispatcher] คลิปในคลัง:", len(_library()), "· EXPECTED:", sum(len(s) for _, _, s in EXPECTED))


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    if len(sys.argv) > 1 and sys.argv[1] == "status":
        status()
    else:
        dispatch()
