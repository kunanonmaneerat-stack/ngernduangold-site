"""traffic_monitor.py — Agent เฝ้า traffic: รวมสัญญาณรายช่องจาก metrics.csv
ช่อง = prefix ก่อน '-' ตัวแรกของคอลัมน์ source (ig/fb/tiktok/pantip/threads/yt)
คอลัมน์: source,topic,views,clicks,quiz_start,conversion
ออก: ตารางต่อช่อง (posts, views, clicks, quiz_start, conversion, CTR%, conv%) -> traffic-monitor-<ts>.md + คืน dict
ปลอดภัย: อ่าน/เขียนไฟล์เท่านั้น
"""
import os, sys, csv, datetime
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
METRICS = os.path.join(ROOT, "automation-log", "metrics.csv")
OUTDIR = os.path.join(ROOT, "automation-log")

CHANNELS = ["fb", "ig", "tiktok", "pantip", "threads", "yt"]


def _channel(src):
    s = (src or "").strip().lower()
    for c in CHANNELS:
        if s == c or s.startswith(c + "-") or s.startswith("example-" + c) or s.startswith(c):
            return c
    if s.startswith("example-"):
        s = s[len("example-"):]
    return s.split("-")[0] if s else "unknown"


def collect():
    rows = []
    if os.path.exists(METRICS):
        with open(METRICS, encoding="utf-8") as f:
            for r in csv.DictReader(f):
                rows.append(r)
    agg = {}
    for r in rows:
        ch = _channel(r.get("source", ""))
        a = agg.setdefault(ch, {"posts": 0, "views": 0, "clicks": 0, "quiz_start": 0, "conversion": 0})
        a["posts"] += 1
        for k in ("views", "clicks", "quiz_start", "conversion"):
            try:
                a[k] += int(float(r.get(k, 0) or 0))
            except Exception:
                pass
    return agg, rows


def run():
    agg, rows = collect()
    ts = datetime.datetime.now().strftime("%Y%m%d-%H%M")
    lines = ["# Traffic Monitor — สัญญาณรายช่อง (" + ts + ")",
             "> ที่มา: metrics.csv (" + str(len(rows)) + " แถว) · ช่อง = prefix ของ source",
             "",
             "| ช่อง | โพสต์ | views | clicks | quiz_start | conversion | CTR% | conv% |",
             "|---|---|---|---|---|---|---|---|"]
    tot = {"posts": 0, "views": 0, "clicks": 0, "quiz_start": 0, "conversion": 0}
    for ch in sorted(agg, key=lambda c: -agg[c]["views"]):
        a = agg[ch]
        for k in tot:
            tot[k] += a[k]
        ctr = (100.0 * a["clicks"] / a["views"]) if a["views"] else 0
        conv = (100.0 * a["conversion"] / a["clicks"]) if a["clicks"] else 0
        lines.append("| %s | %d | %d | %d | %d | %d | %.1f | %.1f |" %
                     (ch, a["posts"], a["views"], a["clicks"], a["quiz_start"], a["conversion"], ctr, conv))
    lines.append("")
    lines.append("รวม: views=%d clicks=%d quiz_start=%d conversion=%d" %
                 (tot["views"], tot["clicks"], tot["quiz_start"], tot["conversion"]))
    out = os.path.join(OUTDIR, "traffic-monitor-" + ts + ".md")
    open(out, "w", encoding="utf-8").write("\n".join(lines))
    print("[traffic_monitor] -> " + out)
    return {"agg": agg, "total": tot, "rows": len(rows), "ts": ts, "file": out}


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    r = run()
    print("channels:", list(r["agg"].keys()), "| total views:", r["total"]["views"])
