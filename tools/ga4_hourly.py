# ga4_hourly.py — พิสูจน์ว่า traffic กระจุกช่วงไหนของวัน (19 ก.ค. 2026)
# ใช้ auth เดียวกับ pipeline/ga4_pull.py (service account / OAuth token / ADC)
import os, sys, io, json, datetime

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "pipeline"))
import ga4_pull as G

from google.analytics.data_v1beta import BetaAnalyticsDataClient
from google.analytics.data_v1beta.types import RunReportRequest, DateRange, Dimension, Metric

prop = G._get("GA4_PROPERTY_ID", "541618281")
creds = None
for fn in ("_creds", "_credentials", "get_creds", "_auth"):
    if hasattr(G, fn):
        try:
            creds = getattr(G, fn)()
            break
        except Exception:
            pass

client = BetaAnalyticsDataClient(credentials=creds) if creds else BetaAnalyticsDataClient()

req = RunReportRequest(
    property="properties/%s" % prop,
    date_ranges=[DateRange(start_date="2026-07-13", end_date="2026-07-19")],
    dimensions=[Dimension(name="date"), Dimension(name="hour")],
    metrics=[Metric(name="sessions")],
)
resp = client.run_report(req)
rows = {}
for r in resp.rows:
    d = r.dimension_values[0].value
    h = int(r.dimension_values[1].value)
    s = int(r.metric_values[0].value)
    rows.setdefault(d, {})[h] = s

lines = []
tot_before, tot_after = 0, 0
for d in sorted(rows):
    hh = rows[d]
    before = sum(v for k, v in hh.items() if k < 19)
    after = sum(v for k, v in hh.items() if k >= 19)
    tot_before += before
    tot_after += after
    peak = sorted(hh.items(), key=lambda x: -x[1])[:3]
    lines.append("%s | total=%d | before19=%d | after19=%d | peak_hours=%s" % (
        d, before + after, before, after, ",".join("%02d:00(%d)" % (k, v) for k, v in peak)))
lines.append("SUM 13-19Jul | before19=%d (%.0f%%) | after19=%d (%.0f%%)" % (
    tot_before, 100.0 * tot_before / max(1, tot_before + tot_after),
    tot_after, 100.0 * tot_after / max(1, tot_before + tot_after)))

out = "\n".join(lines)
io.open(os.path.join(ROOT, "automation-log", "_ga4_hourly.txt"), "w", encoding="utf-8").write(out)
print(out.encode("ascii", "replace").decode("ascii"))
