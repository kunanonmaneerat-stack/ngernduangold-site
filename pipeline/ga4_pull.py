"""Read GA4 Data API into one atomic, hash-bound local observation bundle.

ชื่อคอลัมน์คือ "affiliate_click" ไม่ใช่ "conversion" โดยตั้งใจ: มันคือ*การคลิก* ไม่ใช่เงิน
จะเป็นเงินก็ต่อเมื่อ AccessTrade อนุมัติ conversion ทีหลัง การเรียกมันว่า conversion
ทำให้รายงาน 1 ส.ค. 2026 สรุปว่า "funnel แปลงผลจริง" ขณะที่ยอดขายจริงเป็น 0 มาตลอด
auth: (1) service-account secrets/ga4-sa.json ถ้ามี (2) OAuth secrets/ga4-token.json (3) ADC
ปลอดภัย: อ่าน GA4 อย่างเดียว แล้วเลื่อน CSV ทั้งสี่ไฟล์พร้อม sidecar ที่ผูก hash;
ไม่มีการแก้ GA4, publish, deploy หรืออนุญาต bounded pilot จากสคริปต์นี้
ต้องมี: pip install google-analytics-data google-auth ; ENV GA4_PROPERTY_ID (เลขล้วน)
"""
import os, sys, csv, datetime, hashlib, json, math, tempfile
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

try:
    import ga4_schema
except ModuleNotFoundError:  # package import used by focused tests
    from pipeline import ga4_schema

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
OUT = os.path.join(ROOT, "automation-log", "ga4-metrics.csv")
OUT_PAGES = os.path.join(ROOT, "automation-log", "ga4-pages.csv")
OUT_FUNNEL = os.path.join(ROOT, "automation-log", "ga4-funnel.csv")
OUT_PILOT = os.path.join(ROOT, "automation-log", "ga4-pilot-sessions.csv")
OUT_SNAPSHOT = os.path.join(ROOT, "automation-log", "ga4-snapshot.json")
LOG = os.path.join(ROOT, "automation-log", "ga4_pull.log")
DAYS = 28
GA4_ROW_LIMIT = 250_000
GA4_QUERY_NAMES = (
    "source_sessions", "source_events", "page_views", "page_events",
    "funnel_events", "pilot_affiliate_sessions", "pilot_qualified_landings",
)
BANGKOK = datetime.timezone(datetime.timedelta(hours=7))
QUIZ_PATH = os.environ.get("GA4_QUIZ_PATH", "/quiz")
CONV_EVENT = os.environ.get("GA4_CONV_EVENT", "affiliate_click")
QUIZ_START_EVENT = os.environ.get("GA4_QUIZ_START_EVENT", "quiz_start")
# ความตั้งใจซื้อสินค้าของเราเอง (ปุ่มบนหน้าขาย) - คนละเรื่องกับ affiliate_click ซึ่งเป็นการคลิก
# ออกไปหาผู้ให้บริการภายนอก ถ้ารวมเป็นตัวเลขเดียวจะแยกไม่ออกว่าคนสนใจ "สินค้าเรา" หรือ
# "ข้อเสนอของคนอื่น" ซึ่งเป็นคำถามที่ต้องตอบในรอบวัดผล 8 ส.ค. 2026
BUY_INTENT_EVENT = os.environ.get("GA4_BUY_INTENT_EVENT", "buy_intent_click")
ANSWER_SEEN_EVENT = os.environ.get("GA4_ANSWER_SEEN_EVENT", "answer_seen")
LINE_LEAD_EVENT = os.environ.get("GA4_LINE_LEAD_EVENT", "line_lead_click")
INTERNAL_CTA_EVENT = os.environ.get("GA4_INTERNAL_CTA_EVENT", "internal_cta_click")
VIDEO_START_EVENT = os.environ.get("GA4_VIDEO_START_EVENT", "video_start")
EVENT_FIELDS = {
    QUIZ_START_EVENT: "quiz_start",
    CONV_EVENT: "affiliate_click",
    BUY_INTENT_EVENT: "buy_intent_click",
    ANSWER_SEEN_EVENT: "answer_seen",
    LINE_LEAD_EVENT: "line_lead_click",
    INTERNAL_CTA_EVENT: "internal_cta_click",
    VIDEO_START_EVENT: "video_start",
}
PILOT_MEASUREMENT_CONTRACT = {
    "contract_version": 1,
    "primary_metric": "affiliate_click_sessions / qualified_landing_sessions",
    "fields": [
        "affiliate_click_sessions",
        "qualified_landing_sessions",
    ],
    "dimensions": [
        "provider",
        "cta_id",
        "position",
        "content_id",
        "acquisition_content_id",
        "sub_id",
        "channel",
        "campaign",
    ],
    "scopes": {
        "affiliate_click_sessions": "session",
        "qualified_landing_sessions": "session",
    },
    "output_file": "automation-log/ga4-pilot-sessions.csv",
    "snapshot": {
        "schema_version": 3,
        "file_key": "pilot_sessions",
        "query_coverage_keys": [
            "pilot_affiliate_sessions",
            "pilot_qualified_landings",
        ],
        "hash_binding_required": True,
        "pagination_completeness_required": True,
    },
    "queries": {
        "affiliate_click_sessions": {
            "metric": "sessions",
            "dimensions": [
                "eventName",
                "pagePath",
                "landingPagePlusQueryString",
                "sessionManualAdContent",
                "customEvent:provider",
                "customEvent:cta_id",
                "customEvent:position",
                "customEvent:content_id",
                "customEvent:acquisition_content_id",
                "customEvent:sub_id",
                "customEvent:channel",
                "customEvent:campaign",
            ],
        },
        "qualified_landing_sessions": {
            "metric": "sessions",
            "dimensions": [
                "landingPagePlusQueryString",
                "sessionManualAdContent",
            ],
        },
    },
    "target": {
        "canonical_url": "https://ngernduangold.com/credit-card-salary-30000-2026",
        "page_file": "credit-card-salary-30000-2026.html",
        "primary_event": "affiliate_click",
        "provider": "ktccard",
        "cta_id": "salary30000-ktc-lower",
        "position": "after-faq",
        "content_id": "salary30k-2026",
        "sub_id": "website_salary30k-lower_ktccard",
        "channel": "website",
        "campaign": "ktccard",
    },
}
SCOPES = ["https://www.googleapis.com/auth/analytics.readonly", "https://www.googleapis.com/auth/webmasters.readonly"]  # shared token with gsc_pull: keep BOTH so refresh-rewrite never strips webmasters


class ProducerBlocked(RuntimeError):
    """A known prerequisite is unavailable; the producer itself still ran."""


class ProducerRunnerFailed(RuntimeError):
    """Execution, validation, API, or persistence failed unexpectedly."""


def _blocked_result(message, *, exit_contract=False):
    if exit_contract:
        raise ProducerBlocked(message)
    return None


def _failed_result(message, exc, *, exit_contract=False):
    if exit_contract:
        raise ProducerRunnerFailed(message) from exc
    return None


def _api_window(days=DAYS):
    """Return an inclusive GA4 range containing exactly ``days`` dates."""
    if not isinstance(days, int) or days < 1:
        raise ValueError("days must be a positive integer")
    return "%ddaysAgo" % (days - 1), "today"


def _calendar_window(today=None, days=DAYS):
    """Return an absolute, inclusive window bound to one capture date."""
    if not isinstance(days, int) or days < 1:
        raise ValueError("days must be a positive integer")
    end = today or datetime.date.today()
    if not isinstance(end, datetime.date):
        raise TypeError("today must be a date")
    start = end - datetime.timedelta(days=days - 1)
    return start.isoformat(), end.isoformat()


def _capture_context(now=None):
    """Freeze the request window and decision trust before any GA4 query.

    Evaluating trust after the API calls would let a filter/config change during
    a run be labelled as though it protected the data just captured.  The
    returned object is therefore passed unchanged to every query and the
    snapshot sidecar.
    """
    captured = now or datetime.datetime.now().astimezone()
    if captured.tzinfo is None or captured.utcoffset() is None:
        raise ValueError("capture time must be timezone-aware")
    captured = captured.astimezone(BANGKOK)
    start, end = _calendar_window(captured.date(), DAYS)
    # Freeze the property together with the reporting window.  Reading the
    # registry/environment independently in each table pull could otherwise
    # produce one apparently valid bundle whose tables came from different
    # GA4 properties if the setting changed during the run.
    property_id = str(_get("GA4_PROPERTY_ID") or "").strip()
    trust = {
        "trusted": False,
        "label": "UNTRUSTED",
        "reason": "GA4 trust evaluation unavailable at capture time",
        "schema": "unavailable",
        "expires_at": None,
    }
    try:
        from ga4_decision_trust import evaluate_ga4_decision_trust
        result = evaluate_ga4_decision_trust(
            os.path.join(ROOT, ".system_control", "policy.json"),
            os.path.join(ROOT, ".system_control", "host_ip.json"),
            now=captured,
        )
        trust = {
            "trusted": bool(result.trusted),
            "label": str(result.label),
            "reason": str(result.reason),
            "schema": str(result.schema),
            "expires_at": result.expires_at,
        }
    except Exception as exc:
        trust["reason"] = "GA4 trust evaluation failed at capture time (%s)" % type(exc).__name__
    return {
        "captured_at": captured.astimezone(datetime.timezone.utc).isoformat(timespec="seconds"),
        "window_start": start,
        "window_end": end,
        "window_days": DAYS,
        "property_id": property_id,
        "trust": trust,
    }


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


def _property_id(context=None):
    """Return one validated property id, preferring the frozen capture value."""
    if isinstance(context, dict) and "property_id" in context:
        value = context.get("property_id")
    else:
        # Compatibility for direct function callers; ``main`` always supplies
        # a capture context and therefore never re-reads this setting per table.
        value = _get("GA4_PROPERTY_ID")
    selected = str(value or "").strip()
    return selected if selected.isdigit() else ""


def _log(m):
    line = "[%s] %s" % (datetime.datetime.now().isoformat(timespec="seconds"), m)
    try:
        with open(LOG, "a", encoding="utf-8") as handle:
            handle.write(line + "\n")
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


def _clean_dimension(value, *, fallback="", label="dimension", lowercase=True):
    if value is None:
        value = ""
    if not isinstance(value, str):
        raise ValueError("%s must be text" % label)
    cleaned = " ".join(value.strip().split())
    if lowercase:
        cleaned = cleaned.lower()
    return cleaned or fallback


def _canonical_json_hash(value):
    encoded = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _sha256_bytes(value):
    return hashlib.sha256(value).hexdigest()


class _PilotPageParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.canonicals = []
        self.anchors = []

    def handle_starttag(self, tag, attrs):
        values = {str(key).lower(): (value or "") for key, value in attrs}
        selected = str(tag).lower()
        if selected == "link" and "canonical" in values.get("rel", "").lower().split():
            self.canonicals.append(values.get("href", ""))
        elif selected == "a":
            self.anchors.append(values)


def _one_query_value(query, name):
    values = query.get(name)
    if not isinstance(values, list) or len(values) != 1 or not values[0]:
        raise ValueError("pilot CTA %s must have exactly one value" % name)
    return ga4_schema.canonical_pilot_dimension(values[0], {
        "utm_source": "channel",
        "utm_campaign": "campaign",
        "utm_content": "sub_id",
    }[name])


def _pilot_capture_context(repo=None, site_dir=None):
    """Freeze the pilot definition and exact audited CTA before GA4 queries."""
    selected_repo = Path(repo or ROOT).resolve()
    selected_site = Path(site_dir or (selected_repo / "site")).resolve()
    pilot_path = (selected_repo / "release" / "funnel_pilot.json").resolve()
    if pilot_path.parent != (selected_repo / "release").resolve():
        raise ValueError("pilot path escapes release directory")
    try:
        pilot_bytes = pilot_path.read_bytes()
        pilot = json.loads(pilot_bytes.decode("utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError("bounded pilot definition is unreadable") from exc
    if not isinstance(pilot, dict) or pilot.get("schema_version") != 2:
        raise ValueError("bounded pilot definition is unsupported")
    declared = PILOT_MEASUREMENT_CONTRACT
    pilot_measurement = pilot.get("measurement_contract")
    if not isinstance(pilot_measurement, dict):
        raise ValueError("bounded pilot measurement contract is missing")
    expected_contract = {
        "contract_version": declared["contract_version"],
        "primary_metric": declared["primary_metric"],
        "required_fields": declared["fields"],
        "required_dimensions": declared["dimensions"],
        "required_scopes": declared["scopes"],
    }
    for field, expected in expected_contract.items():
        if pilot_measurement.get(field) != expected:
            raise ValueError("bounded pilot measurement %s drifted" % field)

    expected_target = declared["target"]
    pilot_target = pilot.get("target")
    if not isinstance(pilot_target, dict):
        raise ValueError("bounded pilot target is missing")
    for field in (
        "canonical_url", "page_file", "primary_event", "provider", "cta_id",
        "position", "content_id",
    ):
        if pilot_target.get(field) != expected_target[field]:
            raise ValueError("bounded pilot target.%s drifted" % field)

    page_file = expected_target["page_file"]
    if Path(page_file).name != page_file:
        raise ValueError("bounded pilot page_file is unsafe")
    page_path = (selected_site / page_file).resolve()
    if page_path.parent != selected_site:
        raise ValueError("bounded pilot page escapes audited site")
    try:
        page_bytes = page_path.read_bytes()
        page_text = page_bytes.decode("utf-8")
    except (OSError, UnicodeError) as exc:
        raise ValueError("bounded pilot audited page is unreadable") from exc
    parser = _PilotPageParser()
    try:
        parser.feed(page_text)
        parser.close()
    except Exception as exc:
        raise ValueError("bounded pilot audited page is malformed") from exc
    if parser.canonicals != [expected_target["canonical_url"]]:
        raise ValueError("bounded pilot canonical does not match the contract")
    matches = [
        anchor for anchor in parser.anchors
        if anchor.get("data-cta-id") == expected_target["cta_id"]
    ]
    if len(matches) != 1:
        raise ValueError("bounded pilot CTA must occur exactly once")
    anchor = matches[0]
    for attribute, target_field in (
        ("data-provider", "provider"),
        ("data-cta-id", "cta_id"),
        ("data-pos", "position"),
        ("data-content-id", "content_id"),
    ):
        if anchor.get(attribute) != expected_target[target_field]:
            raise ValueError("bounded pilot CTA %s drifted" % attribute)
    rel = set(anchor.get("rel", "").lower().split())
    if not {"sponsored", "nofollow", "noopener"}.issubset(rel):
        raise ValueError("bounded pilot CTA rel contract drifted")
    try:
        href = urlsplit(anchor.get("href", ""))
        query = parse_qs(href.query, keep_blank_values=True, strict_parsing=True)
    except ValueError as exc:
        raise ValueError("bounded pilot CTA URL is invalid") from exc
    derived = {
        "sub_id": _one_query_value(query, "utm_content"),
        "channel": _one_query_value(query, "utm_source"),
        "campaign": _one_query_value(query, "utm_campaign"),
    }
    for field, value in derived.items():
        if value != expected_target[field]:
            raise ValueError("bounded pilot CTA %s drifted" % field)
    landing = urlsplit(expected_target["canonical_url"])
    if (
        landing.scheme != "https" or landing.hostname != "ngernduangold.com"
        or not landing.path or landing.query or landing.fragment
    ):
        raise ValueError("bounded pilot canonical URL is invalid")
    return {
        "pilot_id": pilot.get("pilot_id"),
        "target": {**expected_target, "landing_path": landing.path},
        "pilot_contract_sha256": _sha256_bytes(pilot_bytes),
        "pilot_page_sha256": _sha256_bytes(page_bytes),
        "schema_adapter_sha256": _sha256(ga4_schema.__file__),
        "producer_file_sha256": _sha256(__file__),
        "producer_contract_sha256": _canonical_json_hash(declared),
        "pilot_path": str(pilot_path),
        "page_path": str(page_path),
    }


def _assert_pilot_context_current(context):
    if not isinstance(context, dict):
        raise ValueError("pilot capture context is missing")
    checks = (
        (context.get("pilot_path"), context.get("pilot_contract_sha256"),
         "pilot contract"),
        (context.get("page_path"), context.get("pilot_page_sha256"),
         "pilot page"),
        (ga4_schema.__file__, context.get("schema_adapter_sha256"),
         "pilot schema adapter"),
        (__file__, context.get("producer_file_sha256"),
         "pilot producer"),
    )
    for path, expected, label in checks:
        if not isinstance(path, str) or not isinstance(expected, str):
            raise ValueError("%s binding is incomplete" % label)
        try:
            actual = _sha256(path)
        except OSError as exc:
            raise ValueError("%s is unavailable" % label) from exc
        if actual != expected:
            raise ValueError("%s changed during capture" % label)
    if context.get("producer_contract_sha256") != _canonical_json_hash(
        PILOT_MEASUREMENT_CONTRACT
    ):
        raise ValueError("pilot producer contract changed during capture")


def _attribution(src, med):
    """Keep source and medium distinct while preserving a unique legacy key.

    ``source`` remains the first CSV column consumed by older readers, but it
    now identifies one source/medium pair.  Raw source and medium are also
    emitted as their own columns, so paid and organic rows can never collapse.
    """
    raw_source = _clean_dimension(src, fallback="(direct)", label="sessionSource")
    medium = _clean_dimension(med, fallback="(none)", label="sessionMedium")
    return {
        "key": "%s / %s" % (raw_source, medium),
        "raw_source": raw_source,
        "medium": medium,
        "channel": _norm(raw_source, medium),
    }


def _nonnegative_int(value, label):
    """Parse an API count without silently truncating or zero-filling it."""
    if isinstance(value, bool) or value is None:
        raise ValueError("%s must be a non-negative integer" % label)
    try:
        number = float(value)
    except (TypeError, ValueError):
        raise ValueError("%s must be numeric" % label) from None
    if not math.isfinite(number) or number < 0 or not number.is_integer():
        raise ValueError("%s must be a non-negative integer" % label)
    return int(number)


def _row_dimension(row, index, label):
    try:
        value = row.dimension_values[index].value
    except (AttributeError, IndexError, TypeError):
        raise ValueError("GA4 %s is missing" % label) from None
    if value is not None and not isinstance(value, str):
        raise ValueError("GA4 %s must be text" % label)
    return value or ""


def _row_count(row, index=0, label="metric"):
    try:
        value = row.metric_values[index].value
    except (AttributeError, IndexError, TypeError):
        raise ValueError("GA4 %s is missing" % label) from None
    return _nonnegative_int(value, "GA4 %s" % label)


def _report_rows(report, label):
    rows = getattr(report, "rows", None)
    if rows is None:
        raise ValueError("GA4 %s response has no rows collection" % label)
    try:
        return list(rows)
    except TypeError:
        raise ValueError("GA4 %s rows are malformed" % label) from None


def _report_row_count(report, label):
    """Return the API-declared total; a missing value is never inferred."""
    if not hasattr(report, "row_count"):
        raise ValueError("GA4 %s response has no row_count evidence" % label)
    return _nonnegative_int(report.row_count, "GA4 %s row_count" % label)


def _dimension_identity(row, label):
    values = getattr(row, "dimension_values", None)
    if values is None:
        raise ValueError("GA4 %s row has no dimension identity" % label)
    try:
        identity = tuple(str(value.value) for value in values)
    except (AttributeError, TypeError):
        raise ValueError("GA4 %s row has malformed dimension identity" % label) from None
    if not identity:
        raise ValueError("GA4 %s row has empty dimension identity" % label)
    return identity


def _run_paginated_report(client, RunReportRequest, request_kwargs, label):
    """Fetch every row and retain explicit pagination-completeness evidence."""
    limit = GA4_ROW_LIMIT
    if not isinstance(limit, int) or isinstance(limit, bool) or limit < 1 or limit > 250_000:
        raise ValueError("GA4 row limit must be within 1..250000")
    all_rows = []
    identities = set()
    offsets = []
    page_row_counts = []
    response_row_counts = []
    declared_total = None
    offset = 0
    while True:
        request = dict(request_kwargs)
        request.update({"limit": limit, "offset": offset})
        response = client.run_report(RunReportRequest(**request))
        page = _report_rows(response, label)
        total = _report_row_count(response, label)
        if declared_total is None:
            declared_total = total
        elif total != declared_total:
            raise ValueError("GA4 %s row_count changed during pagination" % label)
        if len(page) > limit or len(all_rows) + len(page) > declared_total:
            raise ValueError("GA4 %s page exceeds declared coverage" % label)
        if len(all_rows) + len(page) < declared_total and len(page) != limit:
            raise ValueError("GA4 %s returned a short intermediate page" % label)
        if declared_total > len(all_rows) and not page:
            raise ValueError("GA4 %s pagination ended before row_count" % label)
        for row in page:
            identity = _dimension_identity(row, label)
            if identity in identities:
                raise ValueError("GA4 %s repeats a dimension row across pages" % label)
            identities.add(identity)
        offsets.append(offset)
        page_row_counts.append(len(page))
        response_row_counts.append(total)
        all_rows.extend(page)
        if len(all_rows) == declared_total:
            break
        offset += limit
    evidence = {
        "api_row_count": declared_total,
        "row_limit": limit,
        "rows_fetched": len(all_rows),
        "pages_fetched": len(offsets),
        "offsets": offsets,
        "page_row_counts": page_row_counts,
        "response_row_counts": response_row_counts,
        "truncated": False,
        "complete": True,
    }
    return all_rows, evidence


def _atomic_csv(path, rows):
    selected = os.path.abspath(path)
    directory = os.path.dirname(selected)
    os.makedirs(directory, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=os.path.basename(selected) + "-", suffix=".tmp",
                                     dir=directory)
    try:
        with os.fdopen(fd, "w", newline="", encoding="utf-8") as handle:
            csv.writer(handle).writerows(rows)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, selected)
    except Exception:
        try:
            os.unlink(temporary)
        except OSError:
            pass
        raise


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
                with open(token, "w", encoding="utf-8") as handle:
                    handle.write(c.to_json())
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


def fold_event_rows(rows, slot, remember=None):
    """Add one GA4 event report into the per-channel aggregate.

    rows: iterable of (session_source, session_medium, event_name, count).
    The legacy three-field form remains accepted by the historical regression
    test, but live pulls always use the four-field attribution contract.

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
    for item in rows:
        try:
            if len(item) == 4:
                src, med, ev, n = item
                attribution = _attribution(src, med)
                key = attribution["key"]
            elif len(item) == 3:
                # Compatibility for the original attribution-bug fixture.
                src, ev, n = item
                med = ""
                attribution = _attribution(src, med)
                key = _norm(src, med)
            else:
                raise ValueError("GA4 event row must have 4 fields")
        except TypeError:
            raise ValueError("GA4 event row is malformed") from None
        ev = _clean_dimension(ev, label="eventName")
        count = _nonnegative_int(n, "GA4 eventCount")
        if ev not in EVENT_FIELDS:
            continue
        if remember is not None:
            remember(key, attribution)
        field = EVENT_FIELDS[ev]
        slot_key = attribution["key"] if len(item) == 4 else _norm(src, med)
        slot(slot_key)[field] += count


def _host_exclude():
    """Exclude synthetic localhost test traffic from every report (build once, reuse)."""
    from google.analytics.data_v1beta.types import Filter, FilterExpression
    return FilterExpression(not_expression=FilterExpression(
        filter=Filter(field_name="hostName",
                      in_list_filter=Filter.InListFilter(values=["127.0.0.1", "localhost"]))))


def _api_client():
    """Create one read-only GA4 client and expose request constructors for testing."""
    try:
        from google.analytics.data_v1beta import BetaAnalyticsDataClient
        from google.analytics.data_v1beta.types import (
            RunReportRequest, DateRange, Dimension, Metric,
        )
    except Exception as exc:
        _log("ยังไม่ได้ติดตั้งไลบรารี -> pip install google-analytics-data google-auth (%s)" % exc)
        return None
    creds = _credentials()
    if creds is None:
        return None
    return (
        BetaAnalyticsDataClient(credentials=creds),
        RunReportRequest,
        DateRange,
        Dimension,
        Metric,
    )


def pull(context=None, output_path=None, *, exit_contract=False):
    pid = _property_id(context)
    if not pid:
        _log("ยังไม่ได้ตั้ง GA4_PROPERTY_ID -> ข้าม (ดู GA4-CONNECT-SETUP.md)")
        return _blocked_result(
            "GA4_PROPERTY_ID is missing or invalid", exit_contract=exit_contract
        )
    api = _api_client()
    if api is None:
        return _blocked_result(
            "GA4 credentials or client dependency are unavailable",
            exit_contract=exit_contract,
        )
    client, RunReportRequest, DateRange, Dimension, Metric = api
    capture = context or _capture_context()
    destination = output_path or OUT
    try:
        hx = _host_exclude()
        dr = [DateRange(start_date=capture["window_start"], end_date=capture["window_end"])]
        prop = "properties/%s" % pid
        agg = {}
        dimensions = {}

        def remember(key, attribution):
            current = dimensions.setdefault(key, dict(attribution))
            if current != attribution:
                raise ValueError("GA4 attribution key collision")

        def slot(key):
            return agg.setdefault(key, {"sessions": 0, **{field: 0 for field in EVENT_FIELDS.values()}})

        session_rows, session_coverage = _run_paginated_report(
            client, RunReportRequest, {
                "property": prop, "date_ranges": dr, "dimension_filter": hx,
                "dimensions": [Dimension(name="sessionSource"),
                               Dimension(name="sessionMedium")],
                "metrics": [Metric(name="sessions")],
                "order_bys": [
                    {"dimension": {"dimension_name": "sessionSource"}},
                    {"dimension": {"dimension_name": "sessionMedium"}},
                ],
            }, "session report")
        for row in session_rows:
            attribution = _attribution(
                _row_dimension(row, 0, "sessionSource"),
                _row_dimension(row, 1, "sessionMedium"),
            )
            remember(attribution["key"], attribution)
            slot(attribution["key"])["sessions"] += _row_count(row, label="sessions")

        source_event_rows, event_coverage = _run_paginated_report(
            client, RunReportRequest, {
                "property": prop, "date_ranges": dr, "dimension_filter": hx,
                "dimensions": [Dimension(name="sessionSource"),
                               Dimension(name="sessionMedium"),
                               Dimension(name="eventName")],
                "metrics": [Metric(name="eventCount")],
                "order_bys": [
                    {"dimension": {"dimension_name": "sessionSource"}},
                    {"dimension": {"dimension_name": "sessionMedium"}},
                    {"dimension": {"dimension_name": "eventName"}},
                ],
            }, "source event report")
        event_rows = []
        for row in source_event_rows:
            event_rows.append((
                _row_dimension(row, 0, "sessionSource"),
                _row_dimension(row, 1, "sessionMedium"),
                _row_dimension(row, 2, "eventName"),
                _row_count(row, label="eventCount"),
            ))
        fold_event_rows(event_rows, slot, remember)

        event_columns = list(dict.fromkeys(EVENT_FIELDS.values()))
        rows = [("source", "raw_source", "medium", "channel", "sessions", *event_columns)]
        for key in sorted(agg):
            d = agg[key]
            attribution = dimensions[key]
            rows.append((key, attribution["raw_source"], attribution["medium"],
                         attribution["channel"], d["sessions"],
                         *(d[field] for field in event_columns)))
        _atomic_csv(destination, rows)
        ts = sum(d["sessions"] for d in agg.values())
        tq = sum(d["quiz_start"] for d in agg.values())
        tc = sum(d["affiliate_click"] for d in agg.values())
        tb = sum(d["buy_intent_click"] for d in agg.values())
        _log("OK -> ga4-metrics.csv | source=%d sessions=%d quiz=%d affiliate_click=%d buy_intent=%d" % (len(agg), ts, tq, tc, tb))
        return {"file": destination, "attributions": len(agg),
                "channels": len({item["channel"] for item in dimensions.values()}),
                "sessions": ts, "quiz_start": tq,
                "affiliate_click": tc, "buy_intent_click": tb,
                "query_coverage": {
                    "source_sessions": session_coverage,
                    "source_events": event_coverage,
                },
                **{field: sum(d[field] for d in agg.values())
                   for field in ("answer_seen", "line_lead_click", "internal_cta_click", "video_start")}}
    except Exception as e:
        _log("ดึง GA4 ล้มเหลว (%s) - เช็ก Property ID / auth / สิทธิ์ property" % e)
        return _failed_result(
            "GA4 metrics query, validation, or write failed",
            e,
            exit_contract=exit_contract,
        )


def pull_pages(context=None, output_path=None, *, exit_contract=False):
    pid = _property_id(context)
    if not pid:
        return _blocked_result(
            "GA4_PROPERTY_ID is missing or invalid", exit_contract=exit_contract
        )
    api = _api_client()
    if api is None:
        return _blocked_result(
            "GA4 credentials or client dependency are unavailable",
            exit_contract=exit_contract,
        )
    client, RunReportRequest, DateRange, Dimension, Metric = api
    capture = context or _capture_context()
    destination = output_path or OUT_PAGES
    try:
        hx = _host_exclude()
        dr = [DateRange(start_date=capture["window_start"], end_date=capture["window_end"])]
        prop = "properties/%s" % pid
        pages = {}

        def slot(p):
            return pages.setdefault(p, {"views": 0, "affiliate_click": 0,
                                         "buy_intent_click": 0,
                                         "answer_seen": 0, "line_lead_click": 0,
                                         "internal_cta_click": 0,
                                         "video_start": 0})

        page_view_rows, view_coverage = _run_paginated_report(
            client, RunReportRequest, {
                "property": prop, "date_ranges": dr, "dimension_filter": hx,
                "dimensions": [Dimension(name="pagePath")],
                "metrics": [Metric(name="screenPageViews")],
                "order_bys": [
                    {"dimension": {"dimension_name": "pagePath"}},
                ],
            }, "page view report")
        for row in page_view_rows:
            page = _clean_dimension(_row_dimension(row, 0, "pagePath"),
                                    fallback="/", label="pagePath", lowercase=False)
            slot(page)["views"] += _row_count(row, label="screenPageViews")
        page_event_rows, event_coverage = _run_paginated_report(
            client, RunReportRequest, {
                "property": prop, "date_ranges": dr, "dimension_filter": hx,
                "dimensions": [Dimension(name="pagePath"),
                               Dimension(name="eventName")],
                "metrics": [Metric(name="eventCount")],
                "order_bys": [
                    {"dimension": {"dimension_name": "pagePath"}},
                    {"dimension": {"dimension_name": "eventName"}},
                ],
            }, "page event report")
        page_events = {
            CONV_EVENT: "affiliate_click",
            BUY_INTENT_EVENT: "buy_intent_click",
            ANSWER_SEEN_EVENT: "answer_seen",
            LINE_LEAD_EVENT: "line_lead_click",
            INTERNAL_CTA_EVENT: "internal_cta_click",
            VIDEO_START_EVENT: "video_start",
        }
        for row in page_event_rows:
            page = _clean_dimension(_row_dimension(row, 0, "pagePath"),
                                    fallback="/", label="pagePath", lowercase=False)
            event_name = _clean_dimension(_row_dimension(row, 1, "eventName"),
                                          label="eventName")
            count = _row_count(row, label="eventCount")
            field = page_events.get(event_name)
            if field:
                slot(page)[field] += count
        rows = [("page", "views", "affiliate_click", "buy_intent_click", "answer_seen",
                 "line_lead_click", "internal_cta_click", "video_start")]
        for p in sorted(pages, key=lambda k: -pages[k]["views"]):
            rows.append((p, pages[p]["views"], pages[p]["affiliate_click"],
                         pages[p]["buy_intent_click"], pages[p]["answer_seen"],
                         pages[p]["line_lead_click"], pages[p]["internal_cta_click"],
                         pages[p]["video_start"]))
        _atomic_csv(destination, rows)
        _log("OK -> ga4-pages.csv | pages=%d" % len(pages))
        return {"file": destination, "pages": len(pages),
                "query_coverage": {
                    "page_views": view_coverage,
                    "page_events": event_coverage,
                }}
    except Exception as e:
        _log("ดึง GA4 pages ล้มเหลว (%s)" % e)
        return _failed_result(
            "GA4 pages query, validation, or write failed",
            e,
            exit_contract=exit_contract,
        )


def pull_funnel(context=None, output_path=None, *, exit_contract=False):
    """Write independent event totals; this is not a user/session sequence funnel."""
    pid = _property_id(context)
    if not pid:
        return _blocked_result(
            "GA4_PROPERTY_ID is missing or invalid", exit_contract=exit_contract
        )
    api = _api_client()
    if api is None:
        return _blocked_result(
            "GA4 credentials or client dependency are unavailable",
            exit_contract=exit_contract,
        )
    client, RunReportRequest, DateRange, Dimension, Metric = api
    capture = context or _capture_context()
    destination = output_path or OUT_FUNNEL
    try:
        hx = _host_exclude()
        dr = [DateRange(start_date=capture["window_start"], end_date=capture["window_end"])]
        prop = "properties/%s" % pid
        counts = {}
        funnel_rows, funnel_coverage = _run_paginated_report(
            client, RunReportRequest, {
                "property": prop, "date_ranges": dr, "dimension_filter": hx,
                "dimensions": [Dimension(name="eventName")],
                "metrics": [Metric(name="eventCount")],
                "order_bys": [
                    {"dimension": {"dimension_name": "eventName"}},
                ],
            }, "funnel event report")
        for row in funnel_rows:
            event_name = _clean_dimension(_row_dimension(row, 0, "eventName"),
                                          label="eventName")
            if not event_name:
                raise ValueError("GA4 eventName must not be empty")
            counts[event_name] = counts.get(event_name, 0) + _row_count(row, label="eventCount")
        stages = ["quiz_start", "quiz_complete", "recommendation_view", "affiliate_click"]
        out = [("stage", "count", "step_conv_pct", "measurement_scope")]
        for st in stages:
            n = counts.get(st, 0)
            out.append((st, n, "", "independent_event_total_not_sequence"))
        _atomic_csv(destination, out)
        _log("OK -> ga4-funnel.csv | " + " -> ".join("%s=%d" % (s, counts.get(s, 0)) for s in stages))
        return {"file": destination, "counts": {s: counts.get(s, 0) for s in stages},
                "measurement_scope": "independent_event_total_not_sequence",
                "query_coverage": {"funnel_events": funnel_coverage}}
    except Exception as e:
        _log("GA4 funnel pull failed (%s)" % e)
        return _failed_result(
            "GA4 funnel query, validation, or write failed",
            e,
            exit_contract=exit_contract,
        )


def _landing_acquisition(landing_value, manual_content, target_path):
    if not isinstance(landing_value, str):
        raise ValueError("GA4 landingPagePlusQueryString must be text")
    try:
        parsed = urlsplit(landing_value.strip())
        query = parse_qs(parsed.query, keep_blank_values=True, strict_parsing=True)
    except ValueError as exc:
        raise ValueError("GA4 landing page is malformed") from exc
    if parsed.path.rstrip("/") != target_path.rstrip("/"):
        return None
    content_id_values = query.get("content_id") or []
    utm_content_values = query.get("utm_content") or []
    if len(content_id_values) > 1 or len(utm_content_values) > 1:
        raise ValueError("GA4 landing acquisition content is ambiguous")
    if content_id_values and utm_content_values:
        content_id = ga4_schema.canonical_pilot_dimension(
            content_id_values[0], "acquisition_content_id"
        )
        utm_content = ga4_schema.canonical_pilot_dimension(
            utm_content_values[0], "acquisition_content_id"
        )
        if content_id != utm_content:
            raise ValueError("GA4 landing acquisition values disagree")
    content_values = content_id_values or utm_content_values
    query_content = content_values[0] if content_values else ""
    acquisition = ga4_schema.canonical_pilot_dimension(
        query_content, "acquisition_content_id"
    )
    manual = ga4_schema.canonical_pilot_dimension(
        manual_content, "acquisition_content_id"
    )
    if "utm_content" in query and manual != acquisition:
        raise ValueError("GA4 sessionManualAdContent disagrees with utm_content")
    if "utm_content" not in query and manual not in ("unattributed", acquisition):
        raise ValueError("GA4 sessionManualAdContent has no matching landing value")
    return acquisition


def pull_pilot_sessions(
    context=None, pilot_context=None, output_path=None, *, exit_contract=False
):
    """Materialize exact per-acquisition session operands for the bounded pilot.

    The numerator is GA4's ``sessions`` metric for the exact affiliate event
    identity, never ``eventCount``.  The denominator is ``sessions`` grouped by
    the exact landing page and acquisition content.  Any numerator without a
    matching denominator, or a numerator greater than its denominator, aborts
    the entire bundle instead of producing a plausible ratio.
    """
    pid = _property_id(context)
    if not pid:
        return _blocked_result(
            "GA4_PROPERTY_ID is missing or invalid", exit_contract=exit_contract
        )
    api = _api_client()
    if api is None:
        return _blocked_result(
            "GA4 credentials or client dependency are unavailable",
            exit_contract=exit_contract,
        )
    client, RunReportRequest, DateRange, Dimension, Metric = api
    capture = context or _capture_context()
    frozen = pilot_context or _pilot_capture_context()
    destination = output_path or OUT_PILOT
    try:
        _assert_pilot_context_current(frozen)
        target = frozen.get("target")
        if not isinstance(target, dict):
            raise ValueError("pilot target context is missing")
        hx = _host_exclude()
        dr = [DateRange(start_date=capture["window_start"], end_date=capture["window_end"])]
        prop = "properties/%s" % pid
        query_contract = PILOT_MEASUREMENT_CONTRACT["queries"]
        numerator_dimensions = query_contract["affiliate_click_sessions"]["dimensions"]
        denominator_dimensions = query_contract["qualified_landing_sessions"]["dimensions"]

        numerator_rows, numerator_coverage = _run_paginated_report(
            client, RunReportRequest, {
                "property": prop,
                "date_ranges": dr,
                "dimension_filter": hx,
                "dimensions": [Dimension(name=name) for name in numerator_dimensions],
                "metrics": [Metric(name="sessions")],
                "order_bys": [
                    {"dimension": {"dimension_name": name}}
                    for name in numerator_dimensions
                ],
            }, "pilot affiliate session report")
        clicks = {}
        for row in numerator_rows:
            values = {
                name: _row_dimension(row, index, name)
                for index, name in enumerate(numerator_dimensions)
            }
            if _clean_dimension(values["eventName"], label="eventName") != target["primary_event"]:
                continue
            page = _clean_dimension(
                values["pagePath"], label="pagePath", lowercase=False
            ).rstrip("/") or "/"
            cta_value = values["customEvent:cta_id"].strip().lower()
            if cta_value != target["cta_id"]:
                # An unrelated affiliate CTA is outside this bounded pilot.
                continue
            if page != target["landing_path"].rstrip("/"):
                raise ValueError("bounded pilot CTA event came from a different page")
            observed = {
                "provider": values["customEvent:provider"],
                "cta_id": values["customEvent:cta_id"],
                "position": values["customEvent:position"],
                "content_id": values["customEvent:content_id"],
                "sub_id": values["customEvent:sub_id"],
                "channel": values["customEvent:channel"],
                "campaign": values["customEvent:campaign"],
            }
            for field, raw_value in observed.items():
                value = ga4_schema.canonical_pilot_dimension(raw_value, field)
                if value != target[field]:
                    raise ValueError("bounded pilot event %s drifted" % field)
            landing_acquisition = _landing_acquisition(
                values["landingPagePlusQueryString"],
                values["sessionManualAdContent"],
                target["landing_path"],
            )
            if landing_acquisition is None:
                # The denominator is explicitly sessions whose landing page is
                # the target.  A later navigation to the CTA page is outside
                # that cohort even when the CTA identity is exact.
                continue
            event_acquisition = ga4_schema.canonical_pilot_dimension(
                values["customEvent:acquisition_content_id"],
                "acquisition_content_id",
            )
            if event_acquisition != landing_acquisition:
                raise ValueError(
                    "bounded pilot event acquisition disagrees with session landing"
                )
            acquisition = landing_acquisition
            clicks[acquisition] = clicks.get(acquisition, 0) + _row_count(
                row, label="pilot affiliate sessions"
            )

        denominator_rows, denominator_coverage = _run_paginated_report(
            client, RunReportRequest, {
                "property": prop,
                "date_ranges": dr,
                "dimension_filter": hx,
                "dimensions": [Dimension(name=name) for name in denominator_dimensions],
                "metrics": [Metric(name="sessions")],
                "order_bys": [
                    {"dimension": {"dimension_name": name}}
                    for name in denominator_dimensions
                ],
            }, "pilot qualified landing session report")
        landings = {}
        for row in denominator_rows:
            landing = _row_dimension(row, 0, "landingPagePlusQueryString")
            acquisition = _landing_acquisition(
                landing,
                _row_dimension(row, 1, "sessionManualAdContent"),
                target["landing_path"],
            )
            if acquisition is None:
                continue
            landings[acquisition] = landings.get(acquisition, 0) + _row_count(
                row, label="pilot qualified landing sessions"
            )
        missing_denominators = sorted(set(clicks) - set(landings))
        if missing_denominators:
            raise ValueError("pilot numerator has no matching landing denominator")

        fields = list(ga4_schema.PILOT_MEASUREMENT_FIELDS["field_order"])
        materialized = []
        for acquisition in sorted(landings):
            row = {
                "provider": target["provider"],
                "cta_id": target["cta_id"],
                "position": target["position"],
                "content_id": target["content_id"],
                "acquisition_content_id": acquisition,
                "sub_id": target["sub_id"],
                "channel": target["channel"],
                "campaign": target["campaign"],
                "affiliate_click_sessions": clicks.get(acquisition, 0),
                "qualified_landing_sessions": landings[acquisition],
                "measurement_scope": "session",
            }
            materialized.append(row)
        errors = ga4_schema.pilot_table_errors(materialized, fields)
        if errors:
            raise ValueError("; ".join(errors))
        _atomic_csv(destination, [fields] + [
            [row[field] for field in fields] for row in materialized
        ])
        _log(
            "OK -> ga4-pilot-sessions.csv | rows=%d affiliate_click_sessions=%d qualified_landing_sessions=%d"
            % (len(materialized), sum(clicks.values()), sum(landings.values()))
        )
        return {
            "file": destination,
            "rows": len(materialized),
            "affiliate_click_sessions": sum(clicks.values()),
            "qualified_landing_sessions": sum(landings.values()),
            "query_coverage": {
                "pilot_affiliate_sessions": numerator_coverage,
                "pilot_qualified_landings": denominator_coverage,
            },
        }
    except Exception as e:
        _log("GA4 pilot session pull failed (%s)" % e)
        return _failed_result(
            "GA4 pilot query, validation, or write failed",
            e,
            exit_contract=exit_contract,
        )


def _sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _write_snapshot_metadata(context=None, files=None, output_path=None,
                             query_coverage=None, pilot_context=None):
    capture = context or _capture_context()
    selected_files = files or {
        "metrics": OUT,
        "pages": OUT_PAGES,
        "funnel": OUT_FUNNEL,
        "pilot_sessions": OUT_PILOT,
    }
    if set(selected_files) != {"metrics", "pages", "funnel", "pilot_sessions"}:
        raise ValueError(
            "GA4 snapshot requires metrics, pages, funnel, and pilot session files"
        )
    trust = capture.get("trust")
    if not isinstance(trust, dict) or set(
        ("trusted", "label", "reason", "schema", "expires_at")
    ) - set(trust):
        raise ValueError("GA4 capture trust context is incomplete")
    if trust.get("trusted") is True:
        try:
            trust_expiry = datetime.datetime.fromisoformat(
                str(trust.get("expires_at") or "").replace("Z", "+00:00")
            )
            captured_at = datetime.datetime.fromisoformat(
                str(capture.get("captured_at") or "").replace("Z", "+00:00")
            )
        except (TypeError, ValueError) as exc:
            raise ValueError("GA4 trusted capture expiry is invalid") from exc
        if (
            trust_expiry.tzinfo is None
            or captured_at.tzinfo is None
            or trust_expiry <= captured_at
        ):
            raise ValueError("GA4 trusted capture expiry is not after capture time")
    property_id = _property_id(capture)
    if not property_id:
        raise ValueError("GA4 capture property_id is missing or invalid")
    event_contract = {field: event for event, field in EVENT_FIELDS.items()}
    expected_event_fields = {
        "quiz_start", "affiliate_click", "buy_intent_click", "answer_seen",
        "line_lead_click", "internal_cta_click", "video_start",
    }
    if set(event_contract) != expected_event_fields:
        raise ValueError("GA4 event configuration aliases two decision fields")
    if not isinstance(query_coverage, dict) or set(query_coverage) != set(GA4_QUERY_NAMES):
        raise ValueError("GA4 snapshot query coverage is incomplete")
    frozen_pilot = pilot_context or _pilot_capture_context()
    _assert_pilot_context_current(frozen_pilot)
    pilot_id = frozen_pilot.get("pilot_id")
    if not isinstance(pilot_id, str) or not pilot_id.strip():
        raise ValueError("GA4 pilot id is missing")
    target = frozen_pilot.get("target")
    if not isinstance(target, dict) or target != {
        **PILOT_MEASUREMENT_CONTRACT["target"],
        "landing_path": urlsplit(
            PILOT_MEASUREMENT_CONTRACT["target"]["canonical_url"]
        ).path,
    }:
        raise ValueError("GA4 pilot target binding is invalid")
    payload = {
        "schema_version": 3,
        "captured_at": capture["captured_at"],
        "window_start": capture["window_start"],
        "window_end": capture["window_end"],
        "window_days": capture["window_days"],
        "property_id": property_id,
        "producer_sha256": frozen_pilot["producer_file_sha256"],
        "event_contract": event_contract,
        "pilot_measurement_contract": PILOT_MEASUREMENT_CONTRACT,
        "pilot_schema_contract": ga4_schema.PILOT_MEASUREMENT_FIELDS,
        "pilot_binding": {
            "pilot_id": pilot_id,
            "pilot_contract_sha256": frozen_pilot["pilot_contract_sha256"],
            "pilot_page_sha256": frozen_pilot["pilot_page_sha256"],
            "schema_adapter_sha256": frozen_pilot["schema_adapter_sha256"],
            "producer_file_sha256": frozen_pilot["producer_file_sha256"],
            "producer_contract_sha256": frozen_pilot["producer_contract_sha256"],
            "target": target,
        },
        "query_coverage": query_coverage,
        "ga4_decision_trust": trust["label"],
        "capture_time_trust": dict(trust),
        "files": {name: _sha256(path) for name, path in selected_files.items()},
    }
    snapshot_path = output_path or OUT_SNAPSHOT
    os.makedirs(os.path.dirname(snapshot_path), exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix="ga4-snapshot-", suffix=".json",
                                     dir=os.path.dirname(snapshot_path))
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, snapshot_path)
    except Exception:
        try:
            os.unlink(temporary)
        except OSError:
            pass
        raise
    return payload


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    try:
        capture = _capture_context()
    except Exception as exc:
        _log("GA4 producer failed before trust evaluation (%s)" % exc)
        return 3
    trust = capture.get("trust") if isinstance(capture, dict) else None
    if not isinstance(trust, dict) or trust.get("label") not in {"TRUSTED", "UNTRUSTED"}:
        _log("GA4 producer failed: capture trust contract is invalid")
        return 3
    if trust.get("trusted") is not True or trust.get("label") != "TRUSTED":
        # Fail before making an output directory, loading credentials, or
        # contacting GA4.  An untrusted capture cannot become decision evidence.
        _log("GA4 pull blocked before credentials/network: capture trust is not TRUSTED")
        return 2
    try:
        output_dir = os.path.dirname(OUT_SNAPSHOT)
        os.makedirs(output_dir, exist_ok=True)
        pilot_context = _pilot_capture_context()
        with tempfile.TemporaryDirectory(prefix="ga4-bundle-", dir=output_dir) as stage:
            staged = {
                "metrics": os.path.join(stage, "ga4-metrics.csv"),
                "pages": os.path.join(stage, "ga4-pages.csv"),
                "funnel": os.path.join(stage, "ga4-funnel.csv"),
                "pilot_sessions": os.path.join(stage, "ga4-pilot-sessions.csv"),
            }
            metrics_result = pull(capture, staged["metrics"], exit_contract=True)
            if metrics_result is None:
                raise RuntimeError("metrics pull failed")
            pages_result = pull_pages(capture, staged["pages"], exit_contract=True)
            if pages_result is None:
                raise RuntimeError("pages pull failed")
            funnel_result = pull_funnel(capture, staged["funnel"], exit_contract=True)
            if funnel_result is None:
                raise RuntimeError("funnel pull failed")
            pilot_result = pull_pilot_sessions(
                capture, pilot_context, staged["pilot_sessions"], exit_contract=True
            )
            if pilot_result is None:
                raise RuntimeError("pilot session pull failed")
            query_coverage = {}
            for result in (metrics_result, pages_result, funnel_result, pilot_result):
                coverage = result.get("query_coverage") if isinstance(result, dict) else None
                if not isinstance(coverage, dict):
                    raise RuntimeError("query coverage missing from pull result")
                if set(query_coverage) & set(coverage):
                    raise RuntimeError("duplicate query coverage keys")
                query_coverage.update(coverage)
            staged_snapshot = os.path.join(stage, "ga4-snapshot.json")
            _write_snapshot_metadata(
                capture, staged, staged_snapshot, query_coverage, pilot_context
            )
            # The sidecar is promoted last.  A process interruption can leave
            # CSVs whose hashes differ from the old sidecar, never a false PASS.
            for name, destination in (("metrics", OUT), ("pages", OUT_PAGES),
                                      ("funnel", OUT_FUNNEL),
                                      ("pilot_sessions", OUT_PILOT)):
                os.replace(staged[name], destination)
            _assert_pilot_context_current(pilot_context)
            os.replace(staged_snapshot, OUT_SNAPSHOT)
        return 0
    except ProducerBlocked as exc:
        _log("GA4 observation bundle BLOCKED; metadata not advanced (%s)" % exc)
        return 2
    except ProducerRunnerFailed as exc:
        _log("GA4 observation bundle RUNNER_FAILED; metadata not advanced (%s)" % exc)
        return 3
    except Exception as exc:
        _log("GA4 observation bundle RUNNER_FAILED; metadata not advanced (%s)" % exc)
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
