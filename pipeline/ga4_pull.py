"""ga4_pull.py - ดึงจำนวน affiliate_click จาก GA4 (Data API) -> ga4-metrics.csv + ga4-pages.csv

ชื่อคอลัมน์คือ "affiliate_click" ไม่ใช่ "conversion" โดยตั้งใจ: มันคือ*การคลิก* ไม่ใช่เงิน
จะเป็นเงินก็ต่อเมื่อ AccessTrade อนุมัติ conversion ทีหลัง การเรียกมันว่า conversion
ทำให้รายงาน 1 ส.ค. 2026 สรุปว่า "funnel แปลงผลจริง" ขณะที่ยอดขายจริงเป็น 0 มาตลอด
auth: (1) service-account secrets/ga4-sa.json ถ้ามี (2) OAuth secrets/ga4-token.json (3) ADC
ปลอดภัย: อ่าน GA4 อย่างเดียว + เขียน csv เท่านั้น
ต้องมี: pip install google-analytics-data google-auth ; ENV GA4_PROPERTY_ID (เลขล้วน)
"""
import os, sys, csv, datetime

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
OUT = os.path.join(ROOT, "automation-log", "ga4-metrics.csv")
OUT_PAGES = os.path.join(ROOT, "automation-log", "ga4-pages.csv")
LOG = os.path.join(ROOT, "automation-log", "ga4_pull.log")
DAYS = 28
QUIZ_PATH = os.environ.get("GA4_QUIZ_PATH", "/quiz")
CONV_EVENT = os.environ.get("GA4_CONV_EVENT", "affiliate_click")
# ความตั้งใจซื้อสินค้าของเราเอง (ปุ่มบนหน้าขาย) - คนละเรื่องกับ affiliate_click ซึ่งเป็นการคลิก
# ออกไปหาผู้ให้บริการภายนอก ถ้ารวมเป็นตัวเลขเดียวจะแยกไม่ออกว่าคนสนใจ "สินค้าเรา" หรือ
# "ข้อเสนอของคนอื่น" ซึ่งเป็นคำถามที่ต้องตอบในรอบวัดผล 8 ส.ค. 2026
BUY_INTENT_EVENT = os.environ.get("GA4_BUY_INTENT_EVENT", "buy_intent_click")
SCOPES = ["https://www.googleapis.com/auth/analytics.readonly", "https://www.googleapis.com/auth/webmasters.readonly"]  # shared token with gsc_pull: keep BOTH so refresh-rewrite never strips webmasters


def _get(name, default=""):
    v = os.environ.get(name)
    if v:
        return v
    try:
        import winreg
        k = winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment")
        val, _ = winreg.QueryValueEx(k, name)
        winreg.CloseKey(k)
        return val
    except Exception:
        return default


def _log(m):
    line = "[%s] %s" % (datetime.datetime.now().isoformat(timespec="seconds"), m)
    try:
        open(LOG, "a", encoding="utf-8").write(line + "\n")
    except Exception:
        pass
    print(line)


def _norm(src, med):
    s = (src or "").lower()
    m = (med or "").lower()
    table = {"instagram": "ig", "ig": "ig", "l.instagram": "ig",
             "facebook": "fb", "fb": "fb", "m.facebook": "fb", "l.facebook": "fb",
             "tiktok": "tiktok", "threads": "threads",
             "pantip": "pantip", "youtube": "yt", "yt": "yt"}
    for key, val in table.items():
        if key in s:
            return val
    if "ig" in m:
        return "ig"
    if "fb" in m or "facebook" in m:
        return "fb"
    if s in ("(direct)", "", "(not set)"):
        return "direct"
    return s.split(".")[0] or "other"


def _credentials():
    cred = _get("GA4_SA_JSON") or os.path.join(ROOT, "secrets", "ga4-sa.json")
    if os.path.exists(cred):
        try:
            from google.oauth2 import service_account
            _log("auth = service-account file")
            return service_account.Credentials.from_service_account_file(cred, scopes=SCOPES)
        except Exception as e:
            _log("load SA file fail (%s) -> try ADC" % e)
    token = os.path.join(ROOT, "secrets", "ga4-token.json")
    if os.path.exists(token):
        try:
            from google.oauth2.credentials import Credentials
            from google.auth.transport.requests import Request
            c = Credentials.from_authorized_user_file(token, SCOPES)
            if c and c.expired and c.refresh_token:
                c.refresh(Request())
                open(token, "w", encoding="utf-8").write(c.to_json())
            _log("auth = OAuth token (secrets/ga4-token.json)")
            return c
        except Exception as e:
            _log("load OAuth token fail (%s) -> try ADC" % e)
    try:
        import google.auth
        creds, _proj = google.auth.default(scopes=SCOPES)
        _log("auth = ADC (gcloud application-default)")
        return creds
    except Exception as e:
        _log("no auth -> run ga4_auth.py (OAuth) or gcloud login (%s)" % e)
        return None


def fold_event_rows(rows, slot):
    """Add one GA4 event report into the per-channel aggregate.

    rows: iterable of (session_source, event_name, count).  slot: channel -> dict.

    Why this is a function instead of the inline loop it used to be
    ---------------------------------------------------------------
    Until 9 Aug 2026 the inline version computed the channel `c` only inside the
    affiliate_click branch, so the buy_intent_click branch spent whatever channel the
    PREVIOUS affiliate row had left in `c`.  GA4 returns rows ordered by count, so the
    only two buy_intent_click events on record - both (direct), both our own install-day
    test on 1 Aug - were filed under `pantip`, the last affiliate row seen.

    That one leaked variable is what put "2 buy-intent clicks, both from Pantip" into the
    8 Aug strategy note, which then ranked Pantip first partly because it looked like the
    only channel producing purchase intent.  The bug is invisible in review and invisible
    in the output file: every number still adds up, it is just filed under the wrong name.
    Hence a test that pins the exact production ordering (test_ga4_attribution.py).
    """
    for src, ev, n in rows:
        if ev not in (BUY_INTENT_EVENT, CONV_EVENT):
            continue
        c = _norm(src, "")
        key = "buy_intent_click" if ev == BUY_INTENT_EVENT else "affiliate_click"
        slot(c)[key] += int(n or 0)


def _host_exclude():
    """Exclude synthetic localhost test traffic from every report (build once, reuse)."""
    from google.analytics.data_v1beta.types import Filter, FilterExpression
    return FilterExpression(not_expression=FilterExpression(
        filter=Filter(field_name="hostName",
                      in_list_filter=Filter.InListFilter(values=["127.0.0.1", "localhost"]))))


def pull():
    pid = _get("GA4_PROPERTY_ID")
    if not pid:
        _log("ยังไม่ได้ตั้ง GA4_PROPERTY_ID -> ข้าม (ดู GA4-CONNECT-SETUP.md)")
        return None
    try:
        from google.analytics.data_v1beta import BetaAnalyticsDataClient
        from google.analytics.data_v1beta.types import RunReportRequest, DateRange, Dimension, Metric
    except Exception as e:
        _log("ยังไม่ได้ติดตั้งไลบรารี -> pip install google-analytics-data google-auth (%s)" % e)
        return None
    creds = _credentials()
    if creds is None:
        return None
    try:
        client = BetaAnalyticsDataClient(credentials=creds)
        hx = _host_exclude()
        dr = [DateRange(start_date="%ddaysAgo" % DAYS, end_date="today")]
        prop = "properties/%s" % pid
        agg = {}

        def slot(c):
            return agg.setdefault(c, {"sessions": 0, "quiz_start": 0, "affiliate_click": 0, "buy_intent_click": 0})

        rep = client.run_report(RunReportRequest(
            property=prop, date_ranges=dr, dimension_filter=hx,
            dimensions=[Dimension(name="sessionSource"), Dimension(name="sessionMedium")],
            metrics=[Metric(name="sessions")]))
        for row in rep.rows:
            c = _norm(row.dimension_values[0].value, row.dimension_values[1].value)
            slot(c)["sessions"] += int(row.metric_values[0].value or 0)

        rep2 = client.run_report(RunReportRequest(
            property=prop, date_ranges=dr, dimension_filter=hx,
            dimensions=[Dimension(name="sessionSource"), Dimension(name="pagePath")],
            metrics=[Metric(name="screenPageViews")]))
        for row in rep2.rows:
            path = row.dimension_values[1].value or ""
            if QUIZ_PATH in path:
                c = _norm(row.dimension_values[0].value, "")
                slot(c)["quiz_start"] += int(row.metric_values[0].value or 0)

        try:
            rep3 = client.run_report(RunReportRequest(
                property=prop, date_ranges=dr, dimension_filter=hx,
                dimensions=[Dimension(name="sessionSource"), Dimension(name="eventName")],
                metrics=[Metric(name="eventCount")]))
            fold_event_rows(((row.dimension_values[0].value or "",
                              row.dimension_values[1].value or "",
                              row.metric_values[0].value) for row in rep3.rows), slot)
        except Exception as e:
            _log("ดึง affiliate_click event ไม่ได้ (%s)" % e)

        rows = [("source", "sessions", "quiz_start", "affiliate_click", "buy_intent_click")]
        for c in sorted(agg):
            d = agg[c]
            rows.append((c, d["sessions"], d["quiz_start"], d["affiliate_click"], d["buy_intent_click"]))
        with open(OUT, "w", newline="", encoding="utf-8") as f:
            csv.writer(f).writerows(rows)
        ts = sum(d["sessions"] for d in agg.values())
        tq = sum(d["quiz_start"] for d in agg.values())
        tc = sum(d["affiliate_click"] for d in agg.values())
        tb = sum(d["buy_intent_click"] for d in agg.values())
        _log("OK -> ga4-metrics.csv | source=%d sessions=%d quiz=%d affiliate_click=%d buy_intent=%d" % (len(agg), ts, tq, tc, tb))
        return {"file": OUT, "channels": len(agg), "sessions": ts, "quiz_start": tq, "affiliate_click": tc, "buy_intent_click": tb}
    except Exception as e:
        _log("ดึง GA4 ล้มเหลว (%s) - เช็ก Property ID / auth / สิทธิ์ property" % e)
        return None


def pull_pages():
    pid = _get("GA4_PROPERTY_ID")
    if not pid:
        return None
    try:
        from google.analytics.data_v1beta import BetaAnalyticsDataClient
        from google.analytics.data_v1beta.types import RunReportRequest, DateRange, Dimension, Metric
    except Exception:
        return None
    creds = _credentials()
    if creds is None:
        return None
    try:
        client = BetaAnalyticsDataClient(credentials=creds)
        hx = _host_exclude()
        dr = [DateRange(start_date="%ddaysAgo" % DAYS, end_date="today")]
        prop = "properties/%s" % pid
        pages = {}

        def slot(p):
            return pages.setdefault(p, {"views": 0, "affiliate_click": 0})

        rep = client.run_report(RunReportRequest(
            property=prop, date_ranges=dr, dimension_filter=hx,
            dimensions=[Dimension(name="pagePath")],
            metrics=[Metric(name="screenPageViews")]))
        for row in rep.rows:
            slot(row.dimension_values[0].value or "/")["views"] += int(row.metric_values[0].value or 0)
        try:
            rep2 = client.run_report(RunReportRequest(
                property=prop, date_ranges=dr, dimension_filter=hx,
                dimensions=[Dimension(name="pagePath"), Dimension(name="eventName")],
                metrics=[Metric(name="eventCount")]))
            for row in rep2.rows:
                if (row.dimension_values[1].value or "") == CONV_EVENT:
                    slot(row.dimension_values[0].value or "/")["affiliate_click"] += int(row.metric_values[0].value or 0)
        except Exception:
            pass
        rows = [("page", "views", "affiliate_click")]
        for p in sorted(pages, key=lambda k: -pages[k]["views"]):
            rows.append((p, pages[p]["views"], pages[p]["affiliate_click"]))
        with open(OUT_PAGES, "w", newline="", encoding="utf-8") as f:
            csv.writer(f).writerows(rows)
        _log("OK -> ga4-pages.csv | pages=%d" % len(pages))
        return {"file": OUT_PAGES, "pages": len(pages)}
    except Exception as e:
        _log("ดึง GA4 pages ล้มเหลว (%s)" % e)
        return None


def pull_funnel():
    """One report -> ga4-funnel.csv: quiz_start -> quiz_complete -> recommendation_view -> affiliate_click."""
    pid = _get("GA4_PROPERTY_ID")
    if not pid:
        return None
    try:
        from google.analytics.data_v1beta import BetaAnalyticsDataClient
        from google.analytics.data_v1beta.types import RunReportRequest, DateRange, Dimension, Metric
    except Exception:
        return None
    creds = _credentials()
    if creds is None:
        return None
    try:
        client = BetaAnalyticsDataClient(credentials=creds)
        hx = _host_exclude()
        dr = [DateRange(start_date="%ddaysAgo" % DAYS, end_date="today")]
        prop = "properties/%s" % pid
        counts = {}
        rep = client.run_report(RunReportRequest(
            property=prop, date_ranges=dr, dimension_filter=hx,
            dimensions=[Dimension(name="eventName")],
            metrics=[Metric(name="eventCount")]))
        for row in rep.rows:
            counts[row.dimension_values[0].value or ""] = int(row.metric_values[0].value or 0)
        stages = ["quiz_start", "quiz_complete", "recommendation_view", "affiliate_click"]
        out = [("stage", "count", "step_conv_pct")]
        prev = None
        for st in stages:
            n = counts.get(st, 0)
            pct = "" if not prev else round(n / prev * 100, 1)
            out.append((st, n, pct))
            prev = n
        out_funnel = os.path.join(ROOT, "automation-log", "ga4-funnel.csv")
        with open(out_funnel, "w", newline="", encoding="utf-8") as f:
            csv.writer(f).writerows(out)
        _log("OK -> ga4-funnel.csv | " + " -> ".join("%s=%d" % (s, counts.get(s, 0)) for s in stages))
        return {"file": out_funnel, "counts": {s: counts.get(s, 0) for s in stages}}
    except Exception as e:
        _log("GA4 funnel pull failed (%s)" % e)
        return None


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    pull()
    pull_pages()
    pull_funnel()
