"""post_timing.py — Agent วิเคราะห์ช่วงเวลาโพสต์ที่ให้ผลสูงสุด
ใช้ GA4 จริง (sessions ต่อ ชม./วัน — ออดิเอนซ์ active เมื่อไหร่) + heuristic การเงินไทย
-> ส่งสล็อตเวลาดีสุดต่อแพลตฟอร์มให้ post_agent · อ่าน GA4 อย่างเดียว + เขียนไฟล์
ใช้: py pipeline/post_timing.py
"""
import os, sys, datetime
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ga4_pull

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INBOX = os.path.join(ROOT, "automation-log", "cowork-inbox")
DAYS = {0: "อา", 1: "จ", 2: "อ", 3: "พ", 4: "พฤ", 5: "ศ", 6: "ส"}

# ช่วงเวลาดีสุดตาม best-practice โซเชียลการเงินไทย (ชั่วโมง 24h, ป้ายกำกับ)
HEUR = {
    "fb":      [(12, "พักเที่ยง"), (19, "หลังเลิกงาน"), (21, "ก่อนนอน")],
    "ig":      [(20, "ไพรม์ไทม์"), (19, "หลังเลิกงาน"), (12, "พักเที่ยง")],
    "tiktok":  [(19, "หัวค่ำ"), (21, "ไพรม์ไทม์"), (22, "ดึกคนเล่นเยอะ")],
    "threads": [(8, "เช้าก่อนงาน"), (12, "เที่ยง"), (20, "ค่ำ")],
    "pantip":  [(20, "ค่ำ"), (22, "ดึกคนว่างอ่านยาว")],
    "yt":      [(18, "เลิกงาน"), (20, "ค่ำ")],
}


def ga4_peaks():
    """sessions ต่อ ชม. (0-23) และต่อวัน (0-6) จาก GA4 — คืน (by_hour, by_day, ok)"""
    pid = ga4_pull._get("GA4_PROPERTY_ID")
    creds = ga4_pull._credentials()
    if not pid or creds is None:
        return {}, {}, False
    try:
        from google.analytics.data_v1beta import BetaAnalyticsDataClient
        from google.analytics.data_v1beta.types import RunReportRequest, DateRange, Dimension, Metric
        client = BetaAnalyticsDataClient(credentials=creds)
        dr = [DateRange(start_date="28daysAgo", end_date="today")]
        prop = "properties/%s" % pid
        by_hour, by_day = {}, {}
        rh = client.run_report(RunReportRequest(property=prop, date_ranges=dr,
                dimensions=[Dimension(name="hour")], metrics=[Metric(name="sessions")]))
        for row in rh.rows:
            try:
                h = int(row.dimension_values[0].value)
                by_hour[h] = by_hour.get(h, 0) + int(row.metric_values[0].value or 0)
            except Exception:
                pass
        rd = client.run_report(RunReportRequest(property=prop, date_ranges=dr,
                dimensions=[Dimension(name="dayOfWeek")], metrics=[Metric(name="sessions")]))
        for row in rd.rows:
            try:
                d = int(row.dimension_values[0].value)
                by_day[d] = by_day.get(d, 0) + int(row.metric_values[0].value or 0)
            except Exception:
                pass
        return by_hour, by_day, True
    except Exception as e:
        print("[post_timing] ดึง GA4 รายชั่วโมงไม่ได้ (%s) — ใช้ heuristic" % str(e)[:80])
        return {}, {}, False


def analyze():
    by_hour, by_day, ok = ga4_peaks()
    total_sess = sum(by_hour.values())
    # ชั่วโมงพีคจาก GA4 (ถ้ามีข้อมูลพอ)
    top_hours = [h for h, _ in sorted(by_hour.items(), key=lambda kv: kv[1], reverse=True)[:6]] if total_sess >= 20 else []
    top_days = [d for d, _ in sorted(by_day.items(), key=lambda kv: kv[1], reverse=True)[:3]] if sum(by_day.values()) >= 20 else []

    def near_peak(hr):
        return any(abs(hr - ph) <= 1 for ph in top_hours)

    slots = {}
    for plat, windows in HEUR.items():
        scored = []
        for hr, label in windows:
            score = 2 + (3 if near_peak(hr) else 0)   # heuristic 2 + boost ถ้าตรงพีค GA4
            tag = label + (" + พีค GA4" if near_peak(hr) else "")
            scored.append((hr, tag, score))
        scored.sort(key=lambda x: x[2], reverse=True)
        slots[plat] = scored[:3]

    src = "GA4 จริง (%d sessions) + heuristic" % total_sess if ok and total_sess else "heuristic การเงินไทย (GA4 ข้อมูลน้อย/ยังไม่พอ)"
    ts = datetime.datetime.now().strftime("%Y%m%d-%H%M")
    out = ["# Post Timing — ช่วงเวลาโพสต์ที่ให้ผลสูงสุด (" + ts + ")",
           "> ที่มา: " + src, ""]
    if top_hours:
        out.append("ชั่วโมงที่ออดิเอนซ์ active สุด (GA4): " + ", ".join("%02d:00" % h for h in sorted(top_hours)))
    if top_days:
        out.append("วันที่ traffic ดีสุด (GA4): " + ", ".join(DAYS.get(d, "?") for d in top_days))
    out.append("")
    out.append("## สล็อตเวลาแนะนำต่อแพลตฟอร์ม")
    for plat in ["fb", "ig", "tiktok", "threads", "pantip", "yt"]:
        ss = ", ".join("%02d:00 (%s)" % (h, tag) for h, tag, _ in slots[plat])
        out.append("- **%s**: %s" % (plat.upper(), ss))
    os.makedirs(INBOX, exist_ok=True)
    fp = os.path.join(INBOX, "post-timing-" + ts + ".md")
    open(fp, "w", encoding="utf-8").write("\n".join(out))
    print("[post_timing] -> " + fp + " | source: " + src)
    return {"slots": slots, "top_hours": top_hours, "top_days": top_days,
            "by_hour": by_hour, "source": src, "file": fp}


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    r = analyze()
    for p, ss in r["slots"].items():
        print(p, "->", ", ".join("%02d:00" % h for h, _, _ in ss))
