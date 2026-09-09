"""post_timing.py — Agent วิเคราะห์ช่วงเวลาโพสต์ที่ให้ผลสูงสุด
ใช้ GA4 จริง (sessions ต่อ ชม./วัน — ออดิเอนซ์ active เมื่อไหร่) + heuristic การเงินไทย
-> ส่งสล็อตเวลาดีสุดต่อแพลตฟอร์มให้ post_agent · อ่าน GA4 อย่างเดียว + เขียนไฟล์
ใช้: py pipeline/post_timing.py
"""
import os, sys, datetime, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ga4_pull
from pantip_eligibility import evaluate_pantip_eligibility
try:
    from ga4_decision_trust import evaluate_ga4_decision_trust
except ImportError:
    from pipeline.ga4_decision_trust import evaluate_ga4_decision_trust

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INBOX = os.path.join(ROOT, "automation-log", "cowork-inbox")
POLICY_PATH = os.path.join(ROOT, ".system_control", "policy.json")
HOST_IP_PATH = os.path.join(ROOT, ".system_control", "host_ip.json")
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

POLICY_CHANNEL = {
    "fb": "facebook",
    "ig": "instagram",
    "tiktok": "tiktok",
    "threads": "threads",
    "pantip": "pantip",
    "yt": "youtube",
}
ALLOWED_STATES = {"active", "manual"}
MIN_SOCIAL_SESSIONS = 30
SOCIAL_SOURCE_HINTS = (
    "facebook", "fb.com", "threads", "youtube", "youtu.be", "pantip",
    "instagram", "pinterest", "tiktok",
)


def eligible_platforms(policy_path=POLICY_PATH, today=None, *, now=None):
    try:
        with open(policy_path, encoding="utf-8") as fh:
            policy = json.load(fh)
            channels = (policy.get("channels") or {})
    except Exception:
        return []
    if today is None:
        if isinstance(now, datetime.datetime):
            today = now.date()
        elif isinstance(now, datetime.date):
            today = now
        else:
            today = datetime.date.today()
    evaluation_time = now if now is not None else today
    result = []
    for platform in HEUR:
        channel = channels.get(POLICY_CHANNEL[platform])
        if not isinstance(channel, dict):
            continue
        state = channel.get("state")
        phase_until = channel.get("phase_until")
        allowed = state in ALLOWED_STATES
        if state == "limited":
            try:
                phase_expired = datetime.date.fromisoformat(str(phase_until)) < today
                weekly_quota = int(channel.get("weekly_quota") or 0)
                allowed = not phase_expired and weekly_quota > 0
            except (TypeError, ValueError):
                allowed = False
        if platform == "pantip":
            allowed = evaluate_pantip_eligibility(
                policy, now=evaluation_time
            ).allowed
        if allowed:
            result.append(platform)
    return result


def is_social_source(source):
    """Return True only for known social/referral sources used by this project."""
    value = str(source or "").strip().lower()
    if value in {"", "(direct)", "direct", "(not set)"}:
        return False
    return value == "fb" or any(hint in value for hint in SOCIAL_SOURCE_HINTS)


def social_counts(records):
    """Aggregate (bucket, source, sessions), excluding direct/search/AI/internal."""
    counts = {}
    for bucket, source, sessions in records:
        if not is_social_source(source):
            continue
        try:
            key = int(bucket)
            value = int(sessions or 0)
        except (TypeError, ValueError):
            continue
        counts[key] = counts.get(key, 0) + value
    return counts


def _ga4_trust():
    try:
        return evaluate_ga4_decision_trust(POLICY_PATH, HOST_IP_PATH)
    except Exception as exc:
        return type("TrustFailure", (), {
            "trusted": False,
            "label": "UNTRUSTED",
            "reason": "GA4 trust check could not run (%s)" % type(exc).__name__,
        })()


def ga4_peaks(trust=None):
    """Social-only sessions by hour/day; direct/search/AI/internal are excluded."""
    trust = trust or _ga4_trust()
    if not bool(trust.trusted):
        return {}, {}, False
    pid = ga4_pull._get("GA4_PROPERTY_ID")
    creds = ga4_pull._credentials()
    if not pid or creds is None:
        return {}, {}, False
    try:
        from google.analytics.data_v1beta import BetaAnalyticsDataClient
        from google.analytics.data_v1beta.types import RunReportRequest, DateRange, Dimension, Metric
        client = BetaAnalyticsDataClient(credentials=creds)
        start_date, end_date = ga4_pull._api_window()
        dr = [DateRange(start_date=start_date, end_date=end_date)]
        prop = "properties/%s" % pid
        host_filter = ga4_pull._host_exclude()
        by_hour, by_day = {}, {}
        rh = client.run_report(RunReportRequest(property=prop, date_ranges=dr,
                dimension_filter=host_filter,
                dimensions=[Dimension(name="hour"), Dimension(name="sessionSource")],
                metrics=[Metric(name="sessions")]))
        by_hour = social_counts((
            row.dimension_values[0].value,
            row.dimension_values[1].value,
            row.metric_values[0].value,
        ) for row in rh.rows)
        rd = client.run_report(RunReportRequest(property=prop, date_ranges=dr,
                dimension_filter=host_filter,
                dimensions=[Dimension(name="dayOfWeek"), Dimension(name="sessionSource")],
                metrics=[Metric(name="sessions")]))
        by_day = social_counts((
            row.dimension_values[0].value,
            row.dimension_values[1].value,
            row.metric_values[0].value,
        ) for row in rd.rows)
        return by_hour, by_day, True
    except Exception as e:
        print("[post_timing] ดึง GA4 รายชั่วโมงไม่ได้ (%s) — ใช้ heuristic" % str(e)[:80])
        return {}, {}, False


def analyze():
    trust = _ga4_trust()
    by_hour, by_day, ok = ga4_peaks(trust=trust)
    total_sess = sum(by_hour.values())
    # ชั่วโมงพีคจาก GA4 (ถ้ามีข้อมูลพอ)
    top_hours = [h for h, _ in sorted(by_hour.items(), key=lambda kv: kv[1], reverse=True)[:6]] if total_sess >= MIN_SOCIAL_SESSIONS else []
    top_days = [d for d, _ in sorted(by_day.items(), key=lambda kv: kv[1], reverse=True)[:3]] if sum(by_day.values()) >= MIN_SOCIAL_SESSIONS else []

    def near_peak(hr):
        return any(abs(hr - ph) <= 1 for ph in top_hours)

    slots = {}
    for plat in eligible_platforms():
        windows = HEUR[plat]
        scored = []
        for hr, label in windows:
            score = 2 + (3 if near_peak(hr) else 0)   # heuristic 2 + boost ถ้าตรงพีค GA4
            tag = label + (" + พีค GA4" if near_peak(hr) else "")
            scored.append((hr, tag, score))
        scored.sort(key=lambda x: x[2], reverse=True)
        slots[plat] = scored[:3]

    if not bool(trust.trusted):
        src = "heuristic only (GA4 Decision Trust=UNTRUSTED; timing decisions blocked)"
    elif ok and total_sess >= MIN_SOCIAL_SESSIONS:
        src = "GA4 social-only (%d sessions; direct/internal excluded) + heuristic" % total_sess
    elif ok:
        src = "heuristic only (GA4 social sample %d < %d; direct/internal excluded)" % (total_sess, MIN_SOCIAL_SESSIONS)
    else:
        src = "heuristic only (GA4 unavailable)"
    ts = datetime.datetime.now().strftime("%Y%m%d-%H%M")
    out = ["# Post Timing — ช่วงเวลาโพสต์ที่ให้ผลสูงสุด (" + ts + ")",
           "> ที่มา: " + src, ""]
    if top_hours:
        out.append("ชั่วโมงที่ออดิเอนซ์ active สุด (GA4): " + ", ".join("%02d:00" % h for h in sorted(top_hours)))
    if top_days:
        out.append("วันที่ traffic ดีสุด (GA4): " + ", ".join(DAYS.get(d, "?") for d in top_days))
    out.append("")
    out.append("## สล็อตเวลาแนะนำต่อแพลตฟอร์ม")
    for plat in slots:
        ss = ", ".join("%02d:00 (%s)" % (h, tag) for h, tag, _ in slots[plat])
        out.append("- **%s**: %s" % (plat.upper(), ss))
    os.makedirs(INBOX, exist_ok=True)
    fp = os.path.join(INBOX, "post-timing-" + ts + ".md")
    with open(fp, "w", encoding="utf-8") as handle:
        handle.write("\n".join(out))
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
