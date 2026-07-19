# ga4_today.py - sessions + channel breakdown for a given date (default today)
import os, sys, io, datetime
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "pipeline"))
import ga4_pull as G
from google.analytics.data_v1beta import BetaAnalyticsDataClient
from google.analytics.data_v1beta.types import RunReportRequest, DateRange, Dimension, Metric

day = sys.argv[1] if len(sys.argv) > 1 else datetime.date.today().isoformat()
prop = G._get("GA4_PROPERTY_ID", "541618281")
creds = None
for fn in ("_creds", "_credentials", "get_creds", "_auth"):
    if hasattr(G, fn):
        try:
            creds = getattr(G, fn)(); break
        except Exception: pass
c = BetaAnalyticsDataClient(credentials=creds) if creds else BetaAnalyticsDataClient()

def rep(dims, metrics, start, end):
    r = c.run_report(RunReportRequest(property="properties/%s" % prop,
        date_ranges=[DateRange(start_date=start, end_date=end)],
        dimensions=[Dimension(name=d) for d in dims],
        metrics=[Metric(name=m) for m in metrics]))
    return [([v.value for v in row.dimension_values], [v.value for v in row.metric_values]) for row in r.rows]

out = []
out.append("== DAY %s ==" % day)
for d, m in rep(["hour"], ["sessions","totalUsers"], day, day):
    out.append("  %s:00  sessions=%s users=%s" % (d[0].zfill(2), m[0], m[1]))
tot = rep([], ["sessions","totalUsers","eventCount"], day, day)
out.append("  TOTAL %s" % (tot[0][1] if tot else "0"))
out.append("== CHANNEL %s ==" % day)
for d, m in rep(["sessionDefaultChannelGroup"], ["sessions"], day, day):
    out.append("  %-22s %s" % (d[0], m[0]))
out.append("== LAST 7 DAYS ==")
for d, m in rep(["date"], ["sessions"], "7daysAgo", "today"):
    out.append("  %s  %s" % (d[0], m[0]))
s = "\n".join(out)
io.open(os.path.join(ROOT, "automation-log", "_ga4_today.txt"), "w", encoding="utf-8").write(s)
print(s.encode("ascii","replace").decode("ascii"))
