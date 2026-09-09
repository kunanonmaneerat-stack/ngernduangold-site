"""dashboard_agent.py — รีเจน automation-log/dashboard.html ด้วยเลขล่าสุดทุกครั้งที่ loop ยิง
อ่าน ga4-metrics.csv + verdict/queue ล่าสุด -> เขียนหน้า dashboard เดียว (เปิดไฟล์เดิมเห็นเลขใหม่)
ปลอดภัย: อ่าน/เขียนไฟล์เท่านั้น · ใช้: py pipeline/dashboard_agent.py
"""
import os, sys, glob, csv, datetime, re, html, hashlib, tempfile
from pathlib import Path
from types import SimpleNamespace
try:
    import ga4_schema
except ImportError:
    from pipeline import ga4_schema
affiliate_click = ga4_schema.affiliate_click
try:
    import decision_readiness
except ImportError:  # package import path
    from pipeline import decision_readiness

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TOOLS = os.path.join(ROOT, "tools")
if TOOLS not in sys.path:
    sys.path.insert(0, TOOLS)
from private_runtime import SALES_LOG_FILE
try:
    import revenue_ledger
except ImportError:  # package import path
    from pipeline import revenue_ledger

AL = os.path.join(ROOT, "automation-log")
INBOX = os.path.join(AL, "cowork-inbox")
OUT = os.path.join(AL, "dashboard.html")
POLICY_PATH = os.path.join(ROOT, ".system_control", "policy.json")
HOST_IP_PATH = os.path.join(ROOT, ".system_control", "host_ip.json")
DASHBOARD_CONTRACT_VERSION = "11"
GA4_METRIC_GRAIN = "ga4-metrics-source-session-total"
GSC_METRIC_GRAIN = "gsc-pages-url-total"
BANGKOK = datetime.timezone(datetime.timedelta(hours=7))
OPERATING_STATUS_MAX_AGE_DAYS = 7
REVENUE_READER_FILES = (
    revenue_ledger.__file__,
    revenue_ledger.log_sale.__file__,
    revenue_ledger.accesstrade_csv.__file__,
    os.path.join(TOOLS, "private_runtime.py"),
)
ANALYTICS_READER_FILES = (
    decision_readiness.__file__,
    decision_readiness.observation_snapshot.__file__,
    decision_readiness.observation_snapshot.ga4_pull.__file__,
    decision_readiness.observation_snapshot.gsc_pull.__file__,
    decision_readiness.observation_snapshot.ga4_decision_trust.__file__,
    ga4_schema.__file__,
    os.path.join(TOOLS, "content_source_gate.py"),
)


def _sha256(path):
    selected = Path(path)
    if not selected.is_file():
        return "MISSING"
    digest = hashlib.sha256()
    with selected.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _combined_sha256(paths):
    """Hash an ordered input set, including missing-file state and path labels."""
    digest = hashlib.sha256()
    for path in paths:
        selected = Path(path)
        digest.update(str(selected.resolve()).encode("utf-8"))
        digest.update(b"\0")
        if not selected.is_file():
            digest.update(b"MISSING\0")
            continue
        digest.update(b"FILE\0")
        with selected.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        digest.update(b"\0")
    return digest.hexdigest()


def _future_expiry(value, now):
    """Return one canonical exclusive UTC expiry, or ``None`` fail-closed."""
    try:
        expiry = datetime.datetime.fromisoformat(
            str(value or "").replace("Z", "+00:00")
        )
    except (TypeError, ValueError):
        return None
    if expiry.tzinfo is None or expiry.utcoffset() is None or expiry <= now:
        return None
    return expiry.astimezone(datetime.timezone.utc).isoformat(timespec="seconds")


def _bounded_trust(trust, now):
    expiry = _future_expiry(getattr(trust, "expires_at", None), now)
    if trust.trusted is True and expiry is not None:
        return trust, expiry
    if trust.trusted is True:
        return SimpleNamespace(
            trusted=False,
            label="UNTRUSTED",
            reason="trusted source has no live strict-reader expiry",
            schema=getattr(trust, "schema", "unknown"),
            state="INVALID_EXPIRY",
            expires_at=None,
        ), None
    return trust, None


def _strict_nonnegative_int(value):
    """Accept only observation totals produced by the strict CSV readers."""
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        return None
    return value


def _canonical_analytics_metrics(readiness):
    """Bind dashboard headline values to the exact readiness observation.

    GSC query rows intentionally are not used here: Search Console can omit
    anonymized queries, so their sum is not the site/page total.  The strict
    observation uses the page-dimension export for the canonical headline.
    """
    observed = getattr(readiness, "observation", None)
    metrics = observed.get("metrics") if isinstance(observed, dict) else None
    if not isinstance(metrics, dict):
        return {"ga4": None, "gsc": None}
    ga4 = metrics.get("ga4_observed_not_decisionable_unless_trusted")
    gsc = metrics.get("gsc_observed_not_decisionable_unless_current")
    ga4_sessions = (
        _strict_nonnegative_int(ga4.get("sessions"))
        if isinstance(ga4, dict) else None
    )
    gsc_clicks = (
        _strict_nonnegative_int(gsc.get("clicks"))
        if isinstance(gsc, dict) else None
    )
    gsc_impressions = (
        _strict_nonnegative_int(gsc.get("impressions"))
        if isinstance(gsc, dict) else None
    )
    return {
        "ga4": ({"sessions": ga4_sessions}
                if ga4_sessions is not None else None),
        "gsc": ({"clicks": gsc_clicks, "impressions": gsc_impressions}
                if gsc_clicks is not None and gsc_impressions is not None else None),
    }


def _bind_metric_trust(trust, metrics, source):
    """A trusted label cannot survive a missing/malformed headline metric."""
    if trust.trusted is not True or metrics is not None:
        return trust
    return SimpleNamespace(
        trusted=False,
        label="UNTRUSTED",
        reason="%s strict observation metric contract is invalid" % source,
        schema=getattr(trust, "schema", "unknown"),
        state="INVALID_METRIC",
        expires_at=None,
    )


def _latest(pat):
    fs = sorted(glob.glob(os.path.join(INBOX, pat)))
    return fs[-1] if fs else None


def _read(p):
    if not p:
        return ""
    try:
        with open(p, encoding="utf-8") as handle:
            return handle.read()
    except Exception:
        return ""


def _ga4():
    rows, tot = [], {"sessions": 0, "quiz": 0, "conv": 0}
    p = os.path.join(AL, "ga4-metrics.csv")
    if os.path.exists(p):
        try:
            with open(p, encoding="utf-8") as handle:
                for r in csv.DictReader(handle):
                    d = {"src": r.get("source", "?"), "sessions": int(r.get("sessions") or 0),
                         "quiz": int(r.get("quiz_start") or 0), "conv": affiliate_click(r)}
                    rows.append(d)
                    tot["sessions"] += d["sessions"]; tot["quiz"] += d["quiz"]; tot["conv"] += d["conv"]
        except Exception:
            pass
    rows.sort(key=lambda x: x["conv"], reverse=True)
    return rows, tot


def _ga4_trust(readiness=None):
    return readiness.ga4 if readiness is not None else decision_readiness.ga4()


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
            with open(p, encoding="utf-8") as handle:
                s = json.load(handle)
            q = int(s.get("quota", 1000)); u = int(s.get("used", 0)); rem = max(0, q - u)
            d = {"quota": q, "used": u, "remaining": rem, "clips": rem // 15,
                 "pct": int(round(100.0 * u / q)) if q else 0}
        except Exception:
            pass
    return d


def _launch(*, today=None):
    import json
    p = os.path.join(AL, "launch-status.json")
    if not os.path.exists(p):
        return ""
    try:
        with open(p, encoding="utf-8") as handle:
            s = json.load(handle)
    except Exception:
        return ""
    selected_day = today or datetime.datetime.now(BANGKOK).date()
    updated = str(s.get("updated") or "")
    match = re.match(r"^(\d{4}-\d{2}-\d{2})(?:\b|\s|—|-)", updated)
    try:
        updated_day = datetime.date.fromisoformat(match.group(1)) if match else None
        age_days = (selected_day - updated_day).days if updated_day else None
    except (TypeError, ValueError):
        updated_day = None
        age_days = None
    if age_days is None or age_days < 0 or age_days > OPERATING_STATUS_MAX_AGE_DAYS:
        observed = updated_day.isoformat() if updated_day else "UNKNOWN"
        age = str(age_days) if isinstance(age_days, int) and age_days >= 0 else "UNKNOWN"
        return (
            '<div class="card"><h2>🚀 Launch status — UNVERIFIED</h2>'
            '<div class="dc" style="color:#e0a93c">Historical operational notes '
            'are hidden because the last machine-readable update is %s (%s day(s) old). '
            'They are not current analytics, revenue, merchant, or live-release evidence.'
            '</div></div>'
        ) % (html.escape(observed), html.escape(age))
    cmap = {"ok": "#3ddc97", "warn": "#e0a93c", "down": "#ff6b6b", "todo": "#8b98a5"}
    rows = ""
    for c in s.get("channels", []):
        col = cmap.get(c.get("st", "todo"), "#8b98a5")
        rows += ('<div class="bar" style="grid-template-columns:130px 1fr">'
                 '<span class="bl"><span style="display:inline-block;width:8px;height:8px;'
                 'border-radius:50%%;background:%s;margin-right:6px"></span>%s</span>'
                 '<span class="bv" style="text-align:left">%s</span></div>'
                 ) % (col, html.escape(c.get("name", "?")), html.escape(c.get("note", "")))
    # facts-freshness (order-newswatch 2026-07-02): อ่าน "ตรวจล่าสุด: **YYYY-MM-DD**" จาก FACTS_current.md
    try:
        import re as _re, datetime as _dt
        fp = os.path.join(AL, "knowledge-base", "FACTS_current.md")
        m = (_re.search(r"ตรวจล่าสุด:\s*\*\*(\d{4}-\d{2}-\d{2})\*\*", _read(fp))
             if os.path.exists(fp) else None)
        if m:
            fd = _dt.date.fromisoformat(m.group(1))
            age = (_dt.date.today() - fd).days
            fcol = "#e0a93c" if age > 14 else "#3ddc97"
            fnote = " (เกิน 14 วัน — รัน newswatch/อัปเดต FACTS)" if age > 14 else ""
            rows += ('<div class="bar" style="grid-template-columns:130px 1fr">'
                     '<span class="bl"><span style="display:inline-block;width:8px;height:8px;'
                     'border-radius:50%%;background:%s;margin-right:6px"></span>📚 facts</span>'
                     '<span class="bv" style="text-align:left;color:%s">ตรวจล่าสุด %s · อายุ %d วัน%s</span></div>'
                     ) % (fcol, fcol, m.group(1), age, fnote)
    except Exception:
        pass
    pend = "".join("<tr><td>%s</td></tr>" % html.escape(x) for x in s.get("pending", []))
    card = ('<div class="card"><h2>🚀 Launch — %s <span style="color:#5b6673;font-weight:400">'
            '(อัปเดต %s · แก้ที่ automation-log/launch-status.json)</span></h2>%s'
            ) % (html.escape(s.get("product", "")), html.escape(s.get("updated", "")), rows)
    if pend:
        card += '<h2 style="margin-top:12px">⏳ รอดำเนินการ</h2><table>%s</table>' % pend
    card += "</div>"
    return card


# ===== เพิ่ม 25 ก.ค. 2026: ให้ตรงยุทธศาสตร์ patient SEO + North Star =====
def _sales(*, today=None, now=None):
    """Strict 28-day affiliate commission North Star from the private ledger."""
    decision_time = now or datetime.datetime.now(BANGKOK)
    if decision_time.tzinfo is None or decision_time.utcoffset() is None:
        raise ValueError("dashboard revenue decision time must be timezone-aware")
    selected_day = today or decision_time.astimezone(BANGKOK).date()
    result = revenue_ledger.read_affiliate_revenue(
        SALES_LOG_FILE, today=selected_day, days=28, now=decision_time
    )
    contract_errors = (
        revenue_ledger.learning_contract_errors(
            result, expected_end=selected_day, observed_at=decision_time
        )
        if result.get("trusted") is True else []
    )
    trusted = result.get("trusted") is True and not contract_errors
    return {
        "trusted": trusted,
        "net_28d": result.get("verified_revenue_thb") if trusted else None,
        "n_28d": result.get("verified_transactions") if trusted else None,
        "pending_28d": result.get("pending_amount_thb") if trusted else None,
        "pending_n_28d": (result.get("pending_transactions")
                           if trusted else None),
        "by_src": result.get("by_source", {}) if trusted else {},
        "pending_by_src": (result.get("pending_by_source", {})
                           if trusted else {}),
        "state": result.get("reconciliation_state") or "UNRECONCILED",
        "quality_state": result.get("quality_state") or "UNAVAILABLE",
        "expires_at": result.get("trust_expires_at") if trusted else None,
        "error": ("; ".join(contract_errors) if contract_errors
                  else result.get("error") or ""),
    }


def _gsc(readiness=None, metrics=None):
    """Read GSC only when its hash-bound, non-truncated 28-day bundle is current."""
    trust = readiness or decision_readiness.gsc()
    out = {"clicks": None, "impr": None, "n_q": None, "watch": [],
           "trusted": bool(trust.trusted), "state": trust.state,
           "reason": trust.reason}
    if not trust.trusted:
        return out
    if not isinstance(metrics, dict):
        out.update({
            "trusted": False,
            "state": "INVALID_METRIC",
            "reason": "GSC strict observation metric contract is invalid",
        })
        return out
    out.update({
        "clicks": metrics["clicks"],
        "impr": metrics["impressions"],
        "n_q": 0,
    })
    p = os.path.join(AL, "gsc-queries.csv")
    if os.path.exists(p):
        with open(p, encoding="utf-8") as handle:
            for r in csv.DictReader(handle):
                try:
                    out["n_q"] += 1
                except Exception:
                    pass
    # 2 cluster ที่เฝ้าตาม SEO-OPPORTUNITY
    pp = os.path.join(AL, "gsc-pages.csv")
    if os.path.exists(pp):
        with open(pp, encoding="utf-8") as handle:
            for r in csv.DictReader(handle):
                pg = (r.get("page") or "")
                for key, label in (("car-still-installment-loan", "รถผ่อนไม่หมด"),
                                   ("credit-card-salary-30000", "บัตร/เงินเดือน 30000")):
                    if key in pg:
                        try:
                            out["watch"].append({"label": label,
                                                 "impr": int(float(r.get("impressions", 0) or 0)),
                                                 "pos": round(float(r.get("position", 0) or 0), 1)})
                        except Exception:
                            pass
    return out


def _indexnudge():
    """สถานะ index coverage จาก nudge log"""
    import json
    p = os.path.join(AL, "gsc-index-nudge-log.jsonl")
    req = skip = 0
    last = ""
    if os.path.exists(p):
        with open(p, encoding="utf-8") as handle:
            for line in handle:
                try:
                    r = json.loads(line)
                    a = r.get("action", "")
                    if a == "requested": req += 1
                    elif a == "skip": skip += 1
                    last = (r.get("ts", "") or "")[:10] or last
                except Exception:
                    pass
    return {"requested": req, "indexed_skip": skip, "last": last}


def _funnel(*, today=None):
    """สถานะปลายทางฟันเนล — อ่านจากบันทึกล่าสุด (funnel-endpoint-check เขียนไว้)"""
    import glob as _g
    files = sorted(_g.glob(os.path.join(AL, "LINE-FUNNEL-*.md")), reverse=True)
    if not files:
        return {"state": "ยังไม่มีรายงาน", "ok": None, "date": ""}
    txt = _read(files[0])
    ok = ("แชท | 🔴 ปิด | ✅ เปิด" in txt) or ("แชท** = เปิด" in txt) or ("✅ เปิด" in txt)
    d = re.search(r"(\d{4})(\d{2})(\d{2})", os.path.basename(files[0]))
    selected_day = today or datetime.datetime.now(BANGKOK).date()
    try:
        report_day = datetime.date.fromisoformat("-".join(d.groups())) if d else None
        age_days = (selected_day - report_day).days if report_day else None
    except (TypeError, ValueError):
        report_day = None
        age_days = None
    if age_days is None or age_days < 0 or age_days > OPERATING_STATUS_MAX_AGE_DAYS:
        observed = report_day.isoformat() if report_day else "UNKNOWN"
        return {
            "state": "UNVERIFIED — funnel status report is stale or undated (%s)" % observed,
            "ok": None,
            "date": observed,
        }
    return {"state": "แชทเปิด + auto-reply 24 ชม." if ok else "ต้องตรวจ",
            "ok": ok, "date": ("%s-%s-%s" % d.groups()) if d else ""}


def build(*, now=None):
    now_dt = now or datetime.datetime.now(BANGKOK)
    if now_dt.tzinfo is None or now_dt.utcoffset() is None:
        raise ValueError("dashboard build time must be timezone-aware")
    now_dt = now_dt.astimezone(BANGKOK)
    local_day = now_dt.date()
    sales_hash_before = _sha256(SALES_LOG_FILE)
    reader_hash_before = _combined_sha256(REVENUE_READER_FILES)
    dashboard_producer_hash_before = _sha256(__file__)
    analytics_reader_hash_before = _combined_sha256(ANALYTICS_READER_FILES)
    analytics_inputs = [
        os.path.join(AL, "ga4-snapshot.json"),
        os.path.join(AL, "ga4-metrics.csv"),
        os.path.join(AL, "ga4-pages.csv"),
        os.path.join(AL, "ga4-funnel.csv"),
        os.path.join(AL, "ga4-pilot-sessions.csv"),
        os.path.join(AL, "gsc-snapshot.json"),
        os.path.join(AL, "gsc-queries.csv"),
        os.path.join(AL, "gsc-pages.csv"),
    ]
    analytics_input_hash_before = _combined_sha256(analytics_inputs)
    # One readiness snapshot prevents GA4 and GSC labels from being calculated
    # from different filesystem states during the same dashboard build.
    readiness = decision_readiness.read(now=now_dt, today=local_day)
    rows, tot = _ga4()
    analytics_metrics = _canonical_analytics_metrics(readiness)
    ga4_trust = _bind_metric_trust(
        _ga4_trust(readiness), analytics_metrics["ga4"], "GA4"
    )
    gsc_trust = _bind_metric_trust(
        readiness.gsc, analytics_metrics["gsc"], "GSC"
    )
    ga4_trust, ga4_expiry = _bounded_trust(ga4_trust, now_dt)
    gsc_trust, gsc_expiry = _bounded_trust(gsc_trust, now_dt)
    verdict, decision = _verdict()
    q = _queue()
    cr = _credits()
    lc = _launch(today=local_day)
    sales = _sales(today=local_day, now=now_dt)
    revenue_expiry = _future_expiry(sales.get("expires_at"), now_dt)
    if sales["trusted"] and revenue_expiry is None:
        sales = {
            **sales,
            "trusted": False,
            "net_28d": None,
            "n_28d": None,
            "pending_28d": None,
            "pending_n_28d": None,
            "by_src": {},
            "pending_by_src": {},
            "state": "UNRECONCILED",
            "quality_state": "INVALID_EXPIRY",
            "error": "trusted revenue has no live strict-reader expiry",
        }
    gsc = _gsc(gsc_trust, analytics_metrics["gsc"])
    idx = _indexnudge()
    fn = _funnel(today=local_day)
    pkgs = len(glob.glob(os.path.join(AL, "content-packages",
              local_day.strftime("%Y%m%d") + "*")))
    now = now_dt.strftime("%d/%m/%Y %H:%M")
    generated_at = now_dt.isoformat(timespec="seconds")
    sales_hash = _sha256(SALES_LOG_FILE)
    # The strict result also depends on lifecycle validation, AccessTrade
    # evidence validation and private path resolution.  Hashing only
    # revenue_ledger.py let an importer change leave a stale dashboard looking
    # provenance-current until the next semantic comparison happened to run.
    reader_hash = _combined_sha256(REVENUE_READER_FILES)
    dashboard_producer_hash = _sha256(__file__)
    analytics_input_hash = _combined_sha256(analytics_inputs)
    if analytics_input_hash != analytics_input_hash_before:
        raise RuntimeError("analytics inputs changed while dashboard was generated")
    analytics_reader_hash = _combined_sha256(ANALYTICS_READER_FILES)
    if sales_hash != sales_hash_before:
        raise RuntimeError("sales input changed while dashboard was generated")
    if reader_hash != reader_hash_before:
        raise RuntimeError("revenue readers changed while dashboard was generated")
    if dashboard_producer_hash != dashboard_producer_hash_before:
        raise RuntimeError("dashboard producer changed while dashboard was generated")
    if analytics_reader_hash != analytics_reader_hash_before:
        raise RuntimeError("analytics readers changed while dashboard was generated")
    mx = max([r["conv"] for r in rows] + [1])
    bars = ""
    for r in rows if ga4_trust.trusted else []:
        if r["sessions"] == 0 and r["conv"] == 0:
            continue
        w = int(100 * r["conv"] / mx)
        bars += ('<div class="bar"><span class="bl">%s</span>'
                 '<span class="bt"><i style="width:%d%%"></i></span>'
                 '<span class="bv">%d affiliate_click · %d sess</span></div>') % (html.escape(r["src"]), w, r["conv"], r["sessions"])
    if ga4_trust.trusted:
        qrows = "".join(
            "<tr><td>%s</td></tr>" % html.escape(
                line.strip("| ").replace("|", " · ")
            )
            for line in q[:9]
        )
        queue_heading = "ตารางคิวโพสต์ (timing diagnostic จาก GA4 ที่ trusted)"
    else:
        qrows = (
            "<tr><td>UNAVAILABLE — GA4 timing/cadence decisions are blocked: %s</td></tr>"
            % html.escape(ga4_trust.reason)
        )
        queue_heading = "ตารางคิวโพสต์ — timing/cadence UNAVAILABLE"
    proven = "PROVEN" in verdict
    vcolor = "#1D9E75" if proven else ("#BA7517" if "INSUFFICIENT" in verdict else "#A32D2D")
    doc = """<!doctype html><html lang="th"><head><meta charset="utf-8">
<meta name="ngernduangold-dashboard-contract" content="%DASHCONTRACT%">
<meta name="ngernduangold-dashboard-generated-at" content="%DASHGENERATED%">
<meta name="ngernduangold-sales-input-sha256" content="%SALEHASH%">
<meta name="ngernduangold-revenue-reader-sha256" content="%READERHASH%">
<meta name="ngernduangold-dashboard-producer-sha256" content="%DASHPRODUCERHASH%">
<meta name="ngernduangold-analytics-input-sha256" content="%ANALYTICSINPUTHASH%">
<meta name="ngernduangold-analytics-reader-sha256" content="%ANALYTICSREADERHASH%">
<meta name="ngernduangold-revenue-trusted" content="%REVTRUSTED%">
<meta name="ngernduangold-revenue-state" content="%REVSTATE%">
<meta name="ngernduangold-revenue-quality-state" content="%REVQUALITYSTATE%">
<meta name="ngernduangold-revenue-expires-at" content="%REVEXPIRES%">
<meta name="ngernduangold-revenue-paid-net-thb" content="%REVPAIDNET%">
<meta name="ngernduangold-revenue-paid-count" content="%REVPAIDCOUNT%">
<meta name="ngernduangold-revenue-pending-amount-thb" content="%REVPENDINGAMOUNT%">
<meta name="ngernduangold-revenue-pending-count" content="%REVPENDINGCOUNT%">
<meta name="ngernduangold-ga4-trusted" content="%GA4TRUSTED%">
<meta name="ngernduangold-ga4-state" content="%GA4STATE%">
<meta name="ngernduangold-ga4-expires-at" content="%GA4EXPIRES%">
<meta name="ngernduangold-ga4-metric-grain" content="%GA4METRICGRAIN%">
<meta name="ngernduangold-gsc-trusted" content="%GSCTRUSTED%">
<meta name="ngernduangold-gsc-state" content="%GSCMETASTATE%">
<meta name="ngernduangold-gsc-expires-at" content="%GSCEXPIRES%">
<meta name="ngernduangold-gsc-metric-grain" content="%GSCMETRICGRAIN%">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>ngernduangold — Local Control Dashboard</title>
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
<h1><span class="dot"></span>ngernduangold — Local Control Dashboard</h1>
<div class="sub">สร้างล่าสุด %NOW% · ความสดและความน่าเชื่อถือแยกตามแต่ละแหล่งข้อมูล · สถานะ Windows task ตรวจแยกต่างหาก</div>
<div class="kpis">
<div class="kpi" style="border-color:#3d8f6a"><b data-dashboard-source="revenue" data-dashboard-metric="revenue-28d" style="color:#3ddc97">%SALE28%</b><span>🎯 Verified affiliate revenue 28 วัน (<span data-dashboard-source="revenue" data-dashboard-metric="revenue-paid-count">%NSALE28%</span> paid commission · <span data-dashboard-state-source="revenue">%SALESTATE%</span>)</span></div>
<div class="kpi"><b data-dashboard-source="gsc" data-dashboard-metric="gsc-impressions">%GIMPR%</b><span>GSC observed impressions (28 วัน · <span data-dashboard-state-source="gsc">%GSCSTATE%</span>)</span></div>
<div class="kpi"><b data-dashboard-source="gsc" data-dashboard-metric="gsc-clicks">%GCLICK%</b><span>GSC observed clicks · <span data-dashboard-state-source="gsc">%GSCSTATE%</span></span></div>
<div class="kpi"><b data-dashboard-source="ga4" data-dashboard-metric="ga4-sessions">%SESS%</b><span>GA4 sessions observed · <span data-dashboard-state-source="ga4">%GA4TRUST%</span></span></div>
</div>
%LAUNCH%
<div class="card" style="border-color:#3d8f6a"><h2>🎯 North Star — verified affiliate commission (private ledger)</h2>
<div class="vd" data-dashboard-source="revenue" style="color:#3ddc97">%SALE28% สุทธิใน 28 วัน · %NSALE28% รายการ paid</div>
<div class="dc"><b>Pending commission — not paid revenue:</b> <span data-dashboard-source="revenue" data-dashboard-metric="revenue-pending-count">%PENDINGCOUNT%</span> รายการ · <span data-dashboard-source="revenue" data-dashboard-metric="revenue-pending-amount">%PENDINGAMOUNT%</span></div>
<div class="dc" data-dashboard-source="revenue">%SALESRC%<br><span style="color:#8b98a5;font-size:11.5px">นับเฉพาะ product=affiliate-commission สถานะ paid; pending/approved ไม่ใช่ verified revenue และข้อมูลที่ reconcile/freshness ไม่ครบจะแสดง UNAVAILABLE ไม่ใช่ 0</span></div></div>
<div class="card"><h2>🔍 SEO (patient · ตัววัดหลัก) — 2 cluster ที่เฝ้า</h2>
<div class="dc" data-dashboard-source="gsc">%GWATCH%</div>
<div class="dc" style="margin-top:8px">index-nudge: ขอ index ไปแล้ว <b>%IDXREQ%</b> หน้า · ที่ index อยู่แล้ว %IDXOK% · ล่าสุด %IDXLAST%<br>
<span style="color:#8b98a5;font-size:11.5px">เมตริกชัยชนะ = 2 cluster ขยับต่ำกว่าอันดับ 30 · คาด 6–12 สัปดาห์ · GA4 รายวันเงียบ = ปกติของเกมนี้</span></div></div>
<div class="card"><h2>💬 ปลายทางฟันเนล (LINE OA) — จุดที่เคยตายเงียบ</h2>
<div class="vd" style="color:%FNCOLOR%;font-size:13.5px">%FNSTATE%</div>
<div class="dc"><span style="color:#8b98a5;font-size:11.5px">ตรวจอัตโนมัติทุกพุธ 09:40 (funnel-endpoint-check) · เคสเดิม 25 ก.ค.: แชทถูกปิด = ขายไม่ได้เลยทั้งที่ต้นทางปกติ</span></div></div>
<div class="card"><h2>affiliate_click รายช่อง (intent only · ไม่ใช่ conversion/รายได้ · <span data-dashboard-state-source="ga4">%GA4TRUST%</span>)</h2>
<div class="dc" data-dashboard-source="ga4" style="margin-bottom:8px">%GA4TRUSTREASON%</div><div data-dashboard-source="ga4">%BARS%</div></div>
<div class="card"><h2>🗓️ %QUEUEHEADING%</h2>
<table>%QROWS%</table></div>
<div class="ft">ngernduangold growth loop · ยุทธศาสตร์: patient SEO งบศูนย์ (เคาะ 21 ก.ค.) · North Star = ยอดขายจริง · คนกดโพสต์/deploy เท่านั้น</div>
</div><script>
(function () {
  "use strict";
  function meta(name) {
    return document.querySelector('meta[name="ngernduangold-' + name + '"]');
  }
  function expire(source) {
    var trust = meta(source + '-trusted');
    var state = meta(source + '-state');
    var quality = source === 'revenue' ? meta('revenue-quality-state') : null;
    if (trust) trust.content = 'false';
    if (state) state.content = 'STALE_AT_VIEW';
    if (quality) quality.content = 'STALE_AT_VIEW';
    if (source === 'revenue') {
      ['revenue-paid-net-thb', 'revenue-paid-count',
       'revenue-pending-amount-thb', 'revenue-pending-count'].forEach(
        function (name) {
          var value = meta(name);
          if (value) value.content = 'UNAVAILABLE';
        }
      );
    }
    document.querySelectorAll('[data-dashboard-source="' + source + '"]').forEach(
      function (node) { node.textContent = 'UNAVAILABLE'; }
    );
    document.querySelectorAll('[data-dashboard-state-source="' + source + '"]').forEach(
      function (node) { node.textContent = 'STALE_AT_VIEW'; }
    );
  }
  function enforce() {
    ['revenue', 'ga4', 'gsc'].forEach(function (source) {
      var trust = meta(source + '-trusted');
      if (!trust || trust.content !== 'true') return;
      var expiry = meta(source + '-expires-at');
      var deadline = Date.parse(expiry ? expiry.content : '');
      if (!Number.isFinite(deadline) || Date.now() >= deadline) expire(source);
    });
  }
  enforce();
  window.setInterval(enforce, 60000);
}());
</script></body></html>"""
    sales_detail = (
        " · ".join("%s %s฿" % (k, format(v, ",.2f"))
                   for k, v in sorted(sales["by_src"].items(), key=lambda x: -x[1]))
        or "<i style='color:#8b98a5'>reconciled source export ยืนยัน 0 paid commission ในหน้าต่างนี้</i>"
        if sales["trusted"] else
        "<i style='color:#e0a93c'>UNRECONCILED — รายได้ยังใช้ตัดสินไม่ได้และห้ามตีความเป็นศูนย์: %s</i>" %
        html.escape(sales["error"] or "source reconciliation is incomplete")
    )
    ga4_value = (str(analytics_metrics["ga4"]["sessions"])
                 if ga4_trust.trusted else "UNAVAILABLE")
    revenue_value = ((format(sales["net_28d"], ",.2f") + "฿")
                     if sales["trusted"] else "UNAVAILABLE")
    revenue_count = str(sales["n_28d"]) if sales["trusted"] else "UNAVAILABLE"
    pending_amount = ((format(sales["pending_28d"], ",.2f") + "฿")
                      if sales["trusted"] else "UNAVAILABLE")
    pending_count = (str(sales["pending_n_28d"])
                     if sales["trusted"] else "UNAVAILABLE")
    revenue_paid_canonical = (format(sales["net_28d"], ".2f")
                              if sales["trusted"] else "UNAVAILABLE")
    pending_canonical = (format(sales["pending_28d"], ".2f")
                         if sales["trusted"] else "UNAVAILABLE")
    gsc_impressions = str(gsc["impr"]) if gsc["trusted"] else "UNAVAILABLE"
    gsc_clicks = str(gsc["clicks"]) if gsc["trusted"] else "UNAVAILABLE"
    bars_value = bars
    if not bars_value:
        bars_value = (
            "<i style='color:#e0a93c'>UNAVAILABLE — %s</i>"
            % html.escape(ga4_trust.reason)
            if not ga4_trust.trusted else
            "<i style='color:#8b98a5'>ยังไม่มีข้อมูล</i>"
        )
    doc = (doc.replace("%NOW%", now).replace("%SESS%", ga4_value)
           .replace("%CONV%", str(tot["conv"])).replace("%QUIZ%", str(tot["quiz"]))
           .replace("%PKG%", str(pkgs)).replace("%BARS%", bars_value)
           .replace("%VCOLOR%", vcolor).replace("%VERDICT%", html.escape(verdict))
           .replace("%DECISION%", html.escape(decision)).replace("%QROWS%", qrows or "<tr><td>—</td></tr>")
           .replace("%QUEUEHEADING%", html.escape(queue_heading))
           .replace("%LAUNCH%", lc)
           .replace("%SALE28%", revenue_value)
           .replace("%NSALE28%", revenue_count)
           .replace("%PENDINGAMOUNT%", pending_amount)
           .replace("%PENDINGCOUNT%", pending_count)
           .replace("%SALESTATE%", html.escape(
               sales["state"] + "/" + sales["quality_state"]
           ))
           .replace("%SALESRC%", sales_detail)
           .replace("%GIMPR%", gsc_impressions)
           .replace("%GCLICK%", gsc_clicks)
           .replace("%GSCSTATE%", html.escape(gsc["state"]))
           .replace("%GWATCH%", (" · ".join("<b>%s</b> %d imp · อันดับ %s" % (w["label"], w["impr"], w["pos"]) for w in gsc["watch"])
                                 or "<i style='color:#8b98a5'>GSC ใช้ตัดสินไม่ได้ — %s</i>" % html.escape(gsc["reason"])))
           .replace("%IDXREQ%", str(idx["requested"])).replace("%IDXOK%", str(idx["indexed_skip"]))
           .replace("%IDXLAST%", idx["last"] or "—")
           .replace("%FNSTATE%", html.escape(fn["state"]))
           .replace("%FNCOLOR%", "#3ddc97" if fn["ok"] else "#BA7517"))
    doc = (doc.replace("%GA4TRUST%", html.escape(ga4_trust.label))
           .replace("%GA4TRUSTREASON%", html.escape(ga4_trust.reason))
           .replace("%DASHCONTRACT%", DASHBOARD_CONTRACT_VERSION)
           .replace("%DASHGENERATED%", html.escape(generated_at))
           .replace("%SALEHASH%", sales_hash)
           .replace("%READERHASH%", reader_hash)
           .replace("%DASHPRODUCERHASH%", dashboard_producer_hash)
           .replace("%ANALYTICSINPUTHASH%", analytics_input_hash)
           .replace("%ANALYTICSREADERHASH%", analytics_reader_hash)
           .replace("%REVTRUSTED%", "true" if sales["trusted"] else "false")
           .replace("%REVSTATE%", html.escape(sales["state"]))
           .replace("%REVQUALITYSTATE%", html.escape(sales["quality_state"]))
           .replace("%REVEXPIRES%", html.escape(revenue_expiry or "UNAVAILABLE"))
           .replace("%REVPAIDNET%", revenue_paid_canonical)
           .replace("%REVPAIDCOUNT%", revenue_count)
           .replace("%REVPENDINGAMOUNT%", pending_canonical)
           .replace("%REVPENDINGCOUNT%", pending_count)
           .replace("%GA4TRUSTED%", "true" if ga4_trust.trusted else "false")
           .replace("%GA4STATE%", html.escape(ga4_trust.state))
           .replace("%GA4EXPIRES%", html.escape(ga4_expiry or "UNAVAILABLE"))
           .replace("%GA4METRICGRAIN%", GA4_METRIC_GRAIN)
           .replace("%GSCTRUSTED%", "true" if gsc["trusted"] else "false")
           .replace("%GSCMETASTATE%", html.escape(gsc["state"]))
           .replace("%GSCEXPIRES%", html.escape(gsc_expiry or "UNAVAILABLE"))
           .replace("%GSCMETRICGRAIN%", GSC_METRIC_GRAIN))
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", dir=os.path.dirname(OUT),
        prefix=".dashboard-", suffix=".html", delete=False
    ) as handle:
        temporary = handle.name
        handle.write(doc)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, OUT)
    print("[dashboard_agent] -> " + OUT + " | sessions=%s affiliate_click=%s ga4_trust=%s verdict=%s" %
          (ga4_value, str(tot["conv"]) if ga4_trust.trusted else "UNAVAILABLE",
           ga4_trust.label, verdict[:30]))
    return OUT


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    build()
