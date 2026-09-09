"""Read-only GA4 diagnostic for one Bangkok calendar day.

This report is deliberately diagnostic-only. Decision-grade analytics come
from ``pipeline/ga4_pull.py`` and its hash-bound snapshot contract. A missing
property, credential, client, or API result must therefore make this command
unavailable instead of silently switching identity or writing a partial file.
"""
import argparse
import datetime
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "pipeline"))
import ga4_pull as G

OUT = os.path.join(ROOT, "automation-log", "_ga4_today.txt")


class DiagnosticUnavailable(RuntimeError):
    """A required local setting, credential, library, or API result is absent."""


def _selected_day(value=None, now=None):
    if value is None:
        captured = now or datetime.datetime.now(G.BANGKOK)
        if captured.tzinfo is None or captured.utcoffset() is None:
            raise ValueError("now must be timezone-aware")
        return captured.astimezone(G.BANGKOK).date().isoformat()
    selected = str(value).strip()
    try:
        parsed = datetime.date.fromisoformat(selected)
    except ValueError as exc:
        raise ValueError("day must be YYYY-MM-DD") from exc
    if selected != parsed.isoformat():
        raise ValueError("day must be canonical YYYY-MM-DD")
    return selected


class _Constructors(tuple):
    """Tuple-compatible request constructors plus one frozen property id."""

    def __new__(cls, values, property_id):
        obj = super().__new__(cls, values)
        obj.property_id = property_id
        return obj


def _rows(client, constructors, dimensions, metrics, start, end):
    RunReportRequest, DateRange, Dimension, Metric = constructors
    response = client.run_report(RunReportRequest(
        property="properties/%s" % constructors.property_id,
        date_ranges=[DateRange(start_date=start, end_date=end)],
        dimensions=[Dimension(name=name) for name in dimensions],
        metrics=[Metric(name=name) for name in metrics],
    ))
    if response is None or not hasattr(response, "rows"):
        raise DiagnosticUnavailable("GA4 returned no report object")
    output = []
    for row in list(getattr(response, "rows", None) or []):
        dim_values = [str(value.value) for value in row.dimension_values]
        metric_values = [str(value.value) for value in row.metric_values]
        if len(dim_values) != len(dimensions) or len(metric_values) != len(metrics):
            raise DiagnosticUnavailable("GA4 response shape does not match request")
        output.append((dim_values, metric_values))
    return output


def collect(day=None, api=None, now=None):
    selected = _selected_day(day, now=now)
    property_id = G._property_id()
    if not property_id:
        raise DiagnosticUnavailable("GA4_PROPERTY_ID is missing or invalid")
    selected_api = api if api is not None else G._api_client()
    if not selected_api or len(selected_api) != 5:
        raise DiagnosticUnavailable("GA4 read client is unavailable")
    client = selected_api[0]
    constructors = _Constructors(selected_api[1:], property_id)

    hourly = _rows(client, constructors, ["hour"], ["sessions", "totalUsers"], selected, selected)
    totals = _rows(client, constructors, [], ["sessions", "totalUsers", "eventCount"], selected, selected)
    channels = _rows(client, constructors, ["sessionDefaultChannelGroup"], ["sessions"], selected, selected)
    last_day = datetime.date.fromisoformat(selected)
    first_day = last_day - datetime.timedelta(days=6)
    last_seven = _rows(
        client, constructors, ["date"], ["sessions"], first_day.isoformat(), selected,
    )
    if len(totals) > 1:
        raise DiagnosticUnavailable("GA4 total query returned more than one row")
    total_metrics = totals[0][1] if totals else ["0", "0", "0"]
    return {
        "day": selected,
        "hourly": hourly,
        "totals": total_metrics,
        "channels": channels,
        "last_seven": last_seven,
    }


def build_report(report):
    day = report["day"]
    out = [
        "DIAGNOSTIC ONLY - raw GA4 read; not decision-grade",
        "== DAY %s ==" % day,
    ]
    for dimensions, metrics in report["hourly"]:
        out.append("  %s:00  sessions=%s users=%s" % (dimensions[0].zfill(2), metrics[0], metrics[1]))
    sessions, users, events = report["totals"]
    out.append("  TOTAL sessions=%s users=%s events=%s" % (sessions, users, events))
    out.append("== CHANNEL %s ==" % day)
    for dimensions, metrics in report["channels"]:
        out.append("  %-22s %s" % (dimensions[0], metrics[0]))
    out.append("== 7 DAYS THROUGH %s ==" % day)
    for dimensions, metrics in report["last_seven"]:
        out.append("  %s  %s" % (dimensions[0], metrics[0]))
    return "\n".join(out)


def write_report(text, output_path=OUT):
    directory = os.path.dirname(os.path.abspath(output_path))
    os.makedirs(directory, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=".ga4-today-", suffix=".tmp", dir=directory)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, output_path)
    except Exception:
        try:
            os.unlink(temporary)
        except OSError:
            pass
        raise


def main(argv=None, *, api=None, now=None, output_path=OUT):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("day", nargs="?", help="calendar date in YYYY-MM-DD")
    args = parser.parse_args(argv)
    try:
        text = build_report(collect(args.day, api=api, now=now))
        write_report(text, output_path=output_path)
    except Exception as exc:
        print("[ga4_today] UNAVAILABLE (%s)" % type(exc).__name__, file=sys.stderr)
        return 2
    print(text.encode("ascii", "replace").decode("ascii"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
