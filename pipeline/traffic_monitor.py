"""traffic_monitor.py — Agent เฝ้า traffic: รวมสัญญาณรายช่องจาก metrics.csv + GA4 observed intent
ช่อง = prefix ก่อน '-' ตัวแรกของคอลัมน์ source (fb/ig/tiktok/pantip/threads/yt/pinterest)
คอลัมน์ metrics.csv: source,topic,views,clicks,quiz_start,conversion
GA4: อ่าน ga4-funnel.csv + ga4-metrics.csv + ga4-pages.csv ถ้ามี (จาก ga4_pull.py)
legacy commerce observation: อ่าน gumroad-sales.csv ถ้ามี (เจ้าของ export มือจาก Gumroad — zero-budget ไม่มี API)
ออก: traffic-monitor-<ts>.md + คืน dict · ปลอดภัย: อ่าน/เขียนไฟล์เท่านั้น
"""
import os, sys, csv, datetime
try:
    from ga4_schema import affiliate_click
except ImportError:
    from pipeline.ga4_schema import affiliate_click
try:
    import decision_readiness
except ImportError:  # package import path
    from pipeline import decision_readiness
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
AL = os.path.join(ROOT, "automation-log")
METRICS = os.path.join(AL, "metrics.csv")
GA4_FUNNEL = os.path.join(AL, "ga4-funnel.csv")
GA4_METRICS = os.path.join(AL, "ga4-metrics.csv")
GA4_PAGES = os.path.join(AL, "ga4-pages.csv")
SALES = os.path.join(AL, "gumroad-sales.csv")
OUTDIR = AL
POLICY_PATH = os.path.join(ROOT, ".system_control", "policy.json")
HOST_IP_PATH = os.path.join(ROOT, ".system_control", "host_ip.json")

CHANNELS = ["fb", "ig", "tiktok", "pantip", "threads", "yt", "pinterest"]


def _channel(src):
    s = (src or "").strip().lower()
    for c in CHANNELS:
        if s == c or s.startswith(c + "-") or s.startswith("example-" + c) or s.startswith(c):
            return c
    if s.startswith("example-"):
        s = s[len("example-"):]
    return s.split("-")[0] if s else "unknown"


def _rows(path):
    if not os.path.exists(path):
        return []
    try:
        with open(path, encoding="utf-8") as f:
            return list(csv.DictReader(f))
    except Exception:
        return []


def collect():
    rows = _rows(METRICS)
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


def _i(r, k):
    try:
        return int(float(r.get(k, 0) or 0))
    except Exception:
        return 0


def ga4_summary():
    """อ่าน GA4 csv (จาก ga4_pull.py) -> dict สำหรับ section 'GA4 (จริง)'. ไฟล์ไหนไม่มี -> ข้ามส่วนนั้น"""
    out = {"funnel": [], "sources": [], "pages": []}
    out["funnel"] = [(r.get("stage", "?"), _i(r, "count")) for r in _rows(GA4_FUNNEL)]
    out["sources"] = sorted(
        [(r.get("source", "?"), _i(r, "sessions"), _i(r, "quiz_start"), affiliate_click(r))
         for r in _rows(GA4_METRICS)], key=lambda x: -x[3])
    out["pages"] = sorted(
        [(r.get("page", "?"), _i(r, "views"), affiliate_click(r)) for r in _rows(GA4_PAGES)],
        key=lambda x: (-x[2], -x[1]))[:8]
    return out


def ga4_trust():
    return decision_readiness.ga4()


def sales_summary():
    """Legacy manual Gumroad observation. It is never verified revenue.

    ``has_data`` remains false even when rows are syntactically valid because this
    file has no immutable source snapshot or reconciliation metadata.  The
    authoritative revenue path is the reconciled JSONL ledger.
    """
    if not os.path.exists(SALES):
        return ("legacy manual commerce observation: — (UNRECONCILED; excluded from verified revenue; "
                "ยังไม่มีไฟล์ gumroad-sales.csv)"), False
    try:
        with open(SALES, encoding="utf-8-sig", newline="") as handle:
            fields = set(csv.DictReader(handle).fieldnames or [])
    except OSError:
        return ("legacy manual commerce observation: UNRECONCILED — อ่าน gumroad-sales.csv ไม่ได้; "
                "excluded from verified revenue"), False
    if fields != {"date", "units", "amount_thb"}:
        return ("legacy manual commerce observation: UNRECONCILED — schema ต้องเป็น "
                "date,units,amount_thb และไม่มี PII; excluded from verified revenue"), False
    rows = _rows(SALES)
    if not rows:
        return ("legacy manual commerce observation: — (UNRECONCILED; excluded from verified revenue; "
                "ยังไม่มีแถวข้อมูล)"), False
    valid = []
    try:
        for row in rows:
            datetime.date.fromisoformat(str(row.get("date", "")))
            units = int(row.get("units", 0))
            amount = float(row.get("amount_thb", 0))
            if units < 0 or amount < 0:
                raise ValueError("negative")
            valid.append((row, units, amount))
    except (TypeError, ValueError):
        return ("legacy manual commerce observation: UNRECONCILED — พบวันที่/units/amount_thb "
                "ที่อ่านไม่ได้; excluded from verified revenue"), False
    if not valid:
        return ("legacy manual commerce observation: — (UNRECONCILED; excluded from verified revenue; "
                "ไฟล์มีแต่ header)"), False
    units = sum(item[1] for item in valid)
    amt = sum(item[2] for item in valid)
    last = max(item[0].get("date", "") for item in valid)
    return ("legacy manual commerce observation (UNRECONCILED; excluded from verified revenue): "
            "%d ชิ้น · %.0f บาท · ล่าสุด %s" % (units, amt, last)), False


def run():
    agg, rows = collect()
    ga4 = ga4_summary()
    trust = ga4_trust()
    ts = datetime.datetime.now().strftime("%Y%m%d-%H%M")
    lines = ["# Traffic Monitor — สัญญาณรายช่อง (" + ts + ")",
             "> ที่มา: metrics.csv (" + str(len(rows)) + " แถว) · ช่อง = prefix ของ source · "
             "metrics.csv = ยอด reach ฝั่งโซเชียล (กรอก/sync มือ) — ดูของจริงที่ section GA4 ด้านล่าง",
             "",
             "| ช่อง | โพสต์ | views | clicks | quiz_start | legacy_intent* | CTR% | intent/click% |",
             "|---|---|---|---|---|---|---|---|"]
    tot = {"posts": 0, "views": 0, "clicks": 0, "quiz_start": 0, "conversion": 0}
    listed = sorted(agg, key=lambda c: -agg[c]["views"])
    for ch in listed:
        a = agg[ch]
        for k in tot:
            tot[k] += a[k]
        ctr = (100.0 * a["clicks"] / a["views"]) if a["views"] else 0
        conv = (100.0 * a["conversion"] / a["clicks"]) if a["clicks"] else 0
        lines.append("| %s | %d | %d | %d | %d | %d | %.1f | %.1f |" %
                     (ch, a["posts"], a["views"], a["clicks"], a["quiz_start"], a["conversion"], ctr, conv))
    for ch in CHANNELS:                       # ช่องมาตรฐานที่ metrics.csv ยังไม่ track -> โชว์ n/a กันหลงคิดว่า 0
        if ch not in agg:
            lines.append("| %s | 0 | n/a | n/a | n/a | n/a | – | – |" % ch)
    lines.append("")
    lines.append("รวม (metrics.csv): views=%d clicks=%d quiz_start=%d legacy_intent=%d" %
                  (tot["views"], tot["clicks"], tot["quiz_start"], tot["conversion"]))
    lines.append("_*legacy_intent อ่านจากคอลัมน์เดิม `conversion` ใน metrics.csv; ถือเป็นเพียง intent ไม่ใช่รายได้._")

    # ---- GA4 (จริง) — ตัวเลขจาก GA4 API ผ่าน ga4_pull.py (host-excluded) ----
    lines.append("")
    lines.append("## GA4 observed intent — Decision Trust=%s" % trust.label)
    lines.append("> %s" % trust.reason)
    if ga4["funnel"] or ga4["sources"] or ga4["pages"]:
        if ga4["funnel"]:
            lines.append("funnel: " + " -> ".join("%s=%d" % (s, c) for s, c in ga4["funnel"]))
        if ga4["sources"]:
            lines.append("")
            lines.append("| source (GA4) | sessions | quiz_start | affiliate_click (intent) |")
            lines.append("|---|---|---|---|")
            for s, sess, qs, cv in ga4["sources"]:
                lines.append("| %s | %d | %d | %d |" % (s, sess, qs, cv))
        if ga4["pages"]:
            lines.append("")
            lines.append("| หน้า (GA4 observed) | views | affiliate_click (intent) |")
            lines.append("|---|---|---|")
            for p, v, cv in ga4["pages"]:
                lines.append("| %s | %d | %d |" % (p, v, cv))
    else:
        lines.append("_ยังไม่มี ga4-*.csv — รัน pipeline/ga4_pull.py ก่อน_")

    # ---- legacy manual commerce observation (not verified revenue) ----
    sl, _has = sales_summary()
    lines.append("")
    lines.append("## Legacy manual commerce observation (not verified revenue)")
    lines.append(sl)

    out = os.path.join(OUTDIR, "traffic-monitor-" + ts + ".md")
    with open(out, "w", encoding="utf-8") as handle:
        handle.write("\n".join(lines))
    print("[traffic_monitor] -> " + out)
    return {"agg": agg, "total": tot, "rows": len(rows), "ts": ts, "file": out,
            "ga4": ga4, "ga4_trusted": bool(trust.trusted), "ga4_trust": trust.label}


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    r = run()
    print("channels:", list(r["agg"].keys()), "| total views:", r["total"]["views"])
