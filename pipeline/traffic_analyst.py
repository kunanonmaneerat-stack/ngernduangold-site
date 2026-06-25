"""traffic_analyst.py — Agent วิเคราะห์: รับข้อมูลจาก traffic_monitor + GA4 -> ตรวจความพอ/ถูกต้อง
-> พิสูจน์คำแนะนำ consult (bottleneck=reach? funnel แปลงผลไหม?) -> ส่ง verdict + decision ให้ Cowork
กฎ owner: พิสูจน์ไม่ได้ = คงทุก agent ไว้ · พิสูจน์ได้ = ทำตามคำแนะนำให้เกิดประโยชน์สูงสุด
ปลอดภัย: อ่าน/เขียนไฟล์เท่านั้น (ไม่ลบ/ไม่ปิด agent เอง — แค่เสนอ decision ให้ Cowork)
GA4: ใช้ ga4-metrics.csv (จาก ga4_pull.py) เป็น conversion จริง — คำนวณ % และจัดอันดับช่องจาก GA4
"""
import os, sys, datetime
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import traffic_monitor as tm

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INBOX = os.path.join(ROOT, "automation-log", "cowork-inbox")
GA4_FILE = os.path.join(ROOT, "automation-log", "ga4-metrics.csv")
REACH_BASELINE = 500   # traffic ที่ถือว่า "พ้น cold-start" พอจะทดสอบ funnel
MIN_POSTS = 10
MIN_CHANNELS = 2


def _pct(n, d):
    return (100.0 * n / d) if d else 0.0


def _load_ga4():
    """อ่าน conversion จริงจาก GA4 (ga4-metrics.csv) — ตัวปิดช่องวัดผลของ loop"""
    res = {"sessions": 0, "quiz_start": 0, "conversion": 0, "channels": [],
           "connected": False, "by_channel": {}}
    if not os.path.exists(GA4_FILE):
        return res
    import csv
    try:
        with open(GA4_FILE, encoding="utf-8") as f:
            for row in csv.DictReader(f):
                s = int(row.get("sessions") or 0)
                q = int(row.get("quiz_start") or 0)
                c = int(row.get("conversion") or 0)
                src = row.get("source") or "?"
                res["sessions"] += s
                res["quiz_start"] += q
                res["conversion"] += c
                res["by_channel"][src] = {"sessions": s, "quiz_start": q, "conversion": c}
                if s > 0:
                    res["channels"].append(src)
        res["connected"] = True
    except Exception:
        pass
    return res


def analyze():
    r = tm.run()
    agg, tot = r["agg"], r["total"]
    rows_n = r["rows"]
    notes, decision, verdict = [], "", ""

    ga4 = _load_ga4()
    has_conv_data = (tot["quiz_start"] + tot["conversion"] + ga4["quiz_start"] + ga4["conversion"]) > 0
    reach_proxy = max(tot["views"], ga4["sessions"])           # traffic จริง = Meta reach หรือ GA4 sessions
    has_decent_reach = reach_proxy >= REACH_BASELINE
    channels_with_data = [c for c in agg if agg[c]["views"] > 0]
    chan_union = set(channels_with_data) | set(ga4["channels"])
    enough = rows_n >= MIN_POSTS and len(chan_union) >= MIN_CHANNELS and has_conv_data

    # ---- ความพอ/ช่องว่างของข้อมูล ----
    gaps = []
    if not has_conv_data:
        if ga4["connected"]:
            gaps.append("GA4 เชื่อมแล้วแต่ยังไม่มี quiz_start/conversion (ยังไม่มีคนคลิกเข้าเว็บ/quiz — รอ reach)")
        else:
            gaps.append("ยังไม่เชื่อม GA4 = ไม่มีข้อมูล conversion (รัน ga4_pull.py · ดู GA4-CONNECT-SETUP.md)")
    if not has_decent_reach:
        gaps.append("traffic ยังต่ำกว่า baseline (%d) — reach_proxy=%d (Meta reach %d / GA4 sessions %d)"
                    % (REACH_BASELINE, reach_proxy, tot["views"], ga4["sessions"]))
    if len(chan_union) < MIN_CHANNELS:
        gaps.append("มีข้อมูลแค่ %d ช่อง (ต้อง >=%d)" % (len(chan_union), MIN_CHANNELS))
    if rows_n < MIN_POSTS:
        gaps.append("ข้อมูลโพสต์น้อย (%d แถว < %d)" % (rows_n, MIN_POSTS))

    # ---- อัตราจาก GA4 (ของจริง) ----
    conv_per_session = _pct(ga4["conversion"], ga4["sessions"])
    quiz_per_session = _pct(ga4["quiz_start"], ga4["sessions"])
    # ช่อง EV สูงสุด จาก GA4 conversion
    best = sorted(ga4["by_channel"].items(),
                  key=lambda kv: (kv[1]["conversion"], kv[1]["sessions"]), reverse=True)
    top_conv = [(k, v) for k, v in best if v["conversion"] > 0][:4]
    top_str = ", ".join("%s (%d conv / %d sess)" % (k, v["conversion"], v["sessions"]) for k, v in top_conv) or "—"

    # ---- พิสูจน์: bottleneck = reach หรือ conversion ----
    if not enough:
        verdict = "INSUFFICIENT (พิสูจน์ยังไม่ได้)"
        decision = ("คงทุก agent ไว้ทั้งหมดตามกฎ owner + เดินเครื่องเก็บข้อมูลต่อ: "
                    "(1) เชื่อม GA4 หรือกรอกตัวเลขจริงต่อช่อง (2) รอ traffic ทดสอบได้ "
                    "(3) มีข้อมูล >=%d ช่อง ค่อยตัดสิน") % (MIN_CHANNELS)
    else:
        total_conv = tot["conversion"] + ga4["conversion"]
        total_quiz = tot["quiz_start"] + ga4["quiz_start"]
        if total_conv > 0 or total_quiz > 0:
            verdict = "PROVEN: reach คือคอขวด (funnel แปลงผลจริงเมื่อมี traffic)"
            decision = ("ทำตาม consult: FREEZE การสร้างระบบเพิ่ม + ทุ่ม reach ของช่องที่ converted ดีสุด "
                        "(conv/session=%.0f%% · quiz/session=%.0f%% · conv รวม=%d) — ลงแรง: %s"
                        % (conv_per_session, quiz_per_session, total_conv,
                           ", ".join(k for k, _ in top_conv[:3]) or "Pantip/FB"))
        else:
            verdict = "REFUTED: traffic ถึงเกณฑ์แล้วแต่ไม่มี conversion = ปัญหาอยู่ที่ funnel/conversion"
            decision = "consult ถูกบางส่วน: ก่อน freeze ให้แก้ funnel (CTA/quiz/landing) เพราะ traffic มาแล้วแต่ไม่แปลงเป็นเงิน"
        notes.append("ช่อง EV สูงสุด (GA4 conversion): " + top_str)
        if conv_per_session > 0:
            notes.append("อัตราแปลงรวม (GA4): conv/session=%.1f%% · quiz/session=%.1f%%" % (conv_per_session, quiz_per_session))

    ts = r["ts"]
    out = ["# Traffic Analyst — verdict ส่ง Cowork (" + ts + ")",
           "> รับข้อมูลจาก traffic_monitor (" + os.path.basename(r["file"]) + ") + GA4 · ทดสอบคำแนะนำ consult",
           "",
           "## สรุปข้อมูลปัจจุบัน",
           "- แถวข้อมูล: %d · ช่องที่มีข้อมูล: %s" % (rows_n, ", ".join(sorted(chan_union)) or "—"),
           "- Meta reach: views=%d clicks=%d" % (tot["views"], tot["clicks"]),
           "- GA4 (เว็บจริง): %s" % (
               "sessions=%d quiz_start=%d conversion=%d" % (ga4["sessions"], ga4["quiz_start"], ga4["conversion"])
               if ga4["connected"] else "ยังไม่เชื่อม (รัน ga4_pull.py -> ปลดล็อก verdict)")]
    if ga4["connected"] and top_conv:
        out += ["- GA4 conversion รายช่อง (สูงสุด): " + top_str]
    out += ["",
            "## ช่องว่างข้อมูล (ทำไมพิสูจน์ได้/ไม่ได้)"]
    out += ["- " + g for g in gaps] or ["- (ข้อมูลพอ)"]
    out += ["", "## VERDICT", "**" + verdict + "**", "",
            "## DECISION (ตามกฎ owner: พิสูจน์ไม่ได้=คง agent · ได้=ทำตาม)", decision]
    if notes:
        out += ["", "## หมายเหตุ"] + ["- " + n for n in notes]
    os.makedirs(INBOX, exist_ok=True)
    vp = os.path.join(INBOX, "traffic-verdict-" + ts + ".md")
    open(vp, "w", encoding="utf-8").write("\n".join(out))
    print("[traffic_analyst] -> " + vp)
    print("[traffic_analyst] VERDICT: " + verdict)
    print("[traffic_analyst] DECISION: " + decision[:160])
    return {"verdict": verdict, "decision": decision, "file": vp, "enough": enough}


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    analyze()
