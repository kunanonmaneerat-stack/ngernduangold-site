"""Produce a fail-closed diagnostic from manual reach, GA4 intent, and money.

GA4 affiliate clicks are interest signals, never conversions or revenue.  The
module may display observed GA4 counts while trust is blocked, but it must not
select a winner, change cadence, or recommend scaling from those counts.
"""
import os, sys, datetime, tempfile
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import traffic_monitor as tm
import decision_readiness
import revenue_ledger

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TOOLS = os.path.join(ROOT, "tools")
if TOOLS not in sys.path:
    sys.path.insert(0, TOOLS)
from private_runtime import SALES_LOG_FILE

INBOX = os.path.join(ROOT, "automation-log", "cowork-inbox")
GA4_FILE = os.path.join(ROOT, "automation-log", "ga4-metrics.csv")
POLICY_PATH = os.path.join(ROOT, ".system_control", "policy.json")
HOST_IP_PATH = os.path.join(ROOT, ".system_control", "host_ip.json")


SALES_LOG = str(SALES_LOG_FILE)


def read_sales(today=None):
    """Use the one strict 28-day affiliate money contract shared by the loop."""
    selected_day = today or datetime.date.today()
    result = revenue_ledger.read_affiliate_revenue(
        SALES_LOG, today=selected_day, days=28
    )
    trusted = bool(result.get("trusted"))
    count = result.get("paid_transactions") if trusted else None
    baht = result.get("net_revenue_thb") if trusted else None
    return {
        "count": count,
        "baht": baht,
        "affiliate_commission_count": count,
        "affiliate_commission_baht": baht,
        "has_log": os.path.exists(SALES_LOG),
        "trusted": trusted,
        "state": result.get("reconciliation_state") or "UNRECONCILED",
        "errors": [] if trusted else [result.get("error") or "sales ledger unavailable"],
    }


def _ga4_trust():
    return decision_readiness.ga4()


def _pct(n, d):
    return (100.0 * n / d) if d else 0.0


def _load_ga4():
    """Read observed GA4 intent signals and attach decision-trust state."""
    trust = _ga4_trust()
    res = {"sessions": 0, "quiz_start": 0, "conversion": 0, "buy_intent": 0, "channels": [],
           "affiliate_click": 0, "connected": False, "by_channel": {},
           "trusted": bool(trust.trusted), "trust_label": trust.label,
           "trust_reason": trust.reason, "trust_schema": trust.schema}
    if not os.path.exists(GA4_FILE):
        return res
    import csv
    try:
        with open(GA4_FILE, encoding="utf-8") as f:
            for row in csv.DictReader(f):
                s = int(row.get("sessions") or 0)
                q = int(row.get("quiz_start") or 0)
                c = int(row.get("affiliate_click") or row.get("conversion") or 0)  # หัวเก่า=conversion (ก่อน 1 ส.ค. 2026)
                src = row.get("source") or "?"
                res["sessions"] += s
                res["quiz_start"] += q
                res["conversion"] += c
                res["affiliate_click"] += c
                res["buy_intent"] += int(row.get("buy_intent_click") or 0)
                res["by_channel"][src] = {"sessions": s, "quiz_start": q,
                                           "conversion": c, "affiliate_click": c}
                if s > 0:
                    res["channels"].append(src)
        res["connected"] = True
    except Exception:
        pass
    return res


def analyze(today=None):
    r = tm.run()
    agg, tot = r["agg"], r["total"]
    rows_n = r["rows"]
    ga4 = _load_ga4()
    sales = read_sales(today=today)
    channels_with_data = [c for c in agg if agg[c].get("views", 0) > 0]
    chan_union = set(channels_with_data) | set(ga4["channels"])

    observed = []
    if ga4["trusted"]:
        observed = sorted(
            ga4["by_channel"].items(),
            key=lambda item: (item[1]["affiliate_click"], item[1]["sessions"]),
            reverse=True,
        )
        observed = [(name, values) for name, values in observed
                    if values["affiliate_click"] > 0][:4]
    observed_text = ", ".join(
        "%s (%d affiliate_click / %d sessions)" %
        (name, values["affiliate_click"], values["sessions"])
        for name, values in observed
    ) or "—"

    gaps = []
    if not ga4["connected"]:
        gaps.append("ยังไม่มี GA4 snapshot ให้อ่าน")
    if not ga4["trusted"]:
        gaps.append("GA4 Decision Trust=UNTRUSTED: %s" % ga4["trust_reason"])
    if not sales["trusted"]:
        gaps.append("สมุดรายได้ยังไม่ trusted: %s" %
                    ("; ".join(sales["errors"][:2]) or "unknown error"))

    if not ga4["trusted"]:
        verdict = "UNTRUSTED: GA4 ใช้เป็นหลักฐานตัดสินไม่ได้"
        decision = ("แสดง sessions/affiliate_click ได้เฉพาะเป็น observed diagnostics; "
                    "ห้ามเลือกช่องชนะ เพิ่มความถี่ เปลี่ยนเวลาโพสต์ หรือ scale "
                    "จนกว่า internal-traffic coverage จะผ่าน")
    elif not sales["trusted"]:
        verdict = "BLOCKED: หลักฐานรายได้ไม่น่าเชื่อถือ"
        decision = ("แก้ schema/status ของ private sales ledger ก่อน; affiliate_click "
                    "ไม่สามารถใช้ทดแทนรายได้หรืออนุญาตให้ scale ได้")
    elif sales["affiliate_commission_count"] > 0:
        verdict = ("REVENUE EVIDENCE: มี paid affiliate commission %d รายการ · %.0f บาท" %
                   (sales["affiliate_commission_count"], sales["affiliate_commission_baht"]))
        decision = ("ใช้ channel_source/content attribution จากรายการ commission เป็นหลัก; "
                    "รายงานนี้ไม่เลือกผู้ชนะหรือ scale จากจำนวนคลิกอัตโนมัติ")
    elif ga4["affiliate_click"] > 0 or ga4["quiz_start"] > 0:
        verdict = ("INTENT ONLY: affiliate_click %d · quiz_start %d · paid affiliate commission 0" %
                   (ga4["affiliate_click"], ga4["quiz_start"]))
        decision = ("ห้ามเรียกคลิกว่า conversion/รายได้ และห้าม scale; "
                    "รอ approved commission ที่ผูกกับ source/content หรือตรวจว่าปลายทางรับเงินทำงาน")
    else:
        verdict = "INSUFFICIENT: ยังไม่มี downstream intent หรือ affiliate commission"
        decision = ("รักษาการวัดผล แต่ห้ามสรุปว่าช่องหรือ funnel ชนะ/แพ้ "
                    "จนกว่าจะมีหลักฐานปลายทางที่เชื่อถือได้")

    click_events_per_100_sessions = (
        _pct(ga4["affiliate_click"], ga4["sessions"])
        if ga4["trusted"] else None
    )
    quiz_events_per_100_sessions = (
        _pct(ga4["quiz_start"], ga4["sessions"])
        if ga4["trusted"] else None
    )
    ts = r["ts"]
    out = [
        "# Traffic Analyst — decision safety (" + ts + ")",
        "> manual reach + GA4 observed intent + verified money ledger; คลิกไม่ใช่รายได้",
        "",
        "## สรุปข้อมูลปัจจุบัน",
        "- manual metrics: %d แถว · ช่องที่มีข้อมูล: %s" %
        (rows_n, ", ".join(sorted(chan_union)) or "—"),
        "- manual reach: views=%d clicks=%d" % (tot["views"], tot["clicks"]),
        "- GA4 observed: sessions=%d quiz_start=%d affiliate_click=%d buy_intent_click=%d" %
        (ga4["sessions"], ga4["quiz_start"], ga4["affiliate_click"], ga4["buy_intent"]),
        "- GA4 Decision Trust=%s — %s" % (ga4["trust_label"], ga4["trust_reason"]),
    ]
    if observed:
        out.append("- observed affiliate_click distribution (ไม่ใช่อันดับรายได้): " + observed_text)
    revenue_line = (
        "- **verified affiliate revenue (paid net of refunds)**: %.0f baht · paid commission=%d" %
        (sales["baht"], sales["affiliate_commission_count"])
        if sales["trusted"] else
        "- **verified affiliate revenue**: unavailable · %s · do not interpret as zero" %
        sales["state"]
    )
    rate_line = (
        "- diagnostic event density: affiliate_click events/100 sessions=%.1f · "
        "quiz_start events/100 sessions=%.1f (events can repeat within a session)" %
        (click_events_per_100_sessions, quiz_events_per_100_sessions)
        if ga4["trusted"] else
        "- diagnostic event density: suppressed while GA4 Decision Trust is UNTRUSTED"
    )
    out.extend([
        "",
        "## ความหมายที่ห้ามสลับกัน",
        "- **affiliate_click**: %d — คลิกแสดงความสนใจ ไม่ใช่ conversion/รายได้" % ga4["affiliate_click"],
        "- **buy_intent_click**: %d — เจตนาซื้อ ยังไม่ใช่ยอดขาย" % ga4["buy_intent"],
        revenue_line,
        rate_line,
        "",
        "## ช่องว่างข้อมูล",
    ])
    out += ["- " + gap for gap in gaps] or ["- ไม่พบ data-contract blocker"]
    out += ["", "## VERDICT", "**" + verdict + "**", "", "## DECISION", decision]

    os.makedirs(INBOX, exist_ok=True)
    vp = os.path.join(INBOX, "traffic-verdict-" + ts + ".md")
    with tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", dir=INBOX, prefix=".traffic-verdict-", delete=False
    ) as destination:
        temporary = destination.name
        destination.write("\n".join(out))
        destination.flush()
        os.fsync(destination.fileno())
    os.replace(temporary, vp)
    print("[traffic_analyst] -> " + vp)
    print("[traffic_analyst] VERDICT: " + verdict)
    print("[traffic_analyst] DECISION: " + decision[:160])
    return {"verdict": verdict, "decision": decision, "file": vp,
            "enough": bool(ga4["trusted"] and sales["trusted"]),
            "ga4_trusted": ga4["trusted"],
            "paid_affiliate_commission": sales["affiliate_commission_count"]}


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    analyze()
