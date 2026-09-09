"""Build one provenance-aware observation for the local improvement loop.

CSV values are never decisionable merely because a file exists.  A sidecar
must declare the exact 28-day window and hashes of every file in that bundle.
This prevents a partial API run from mixing new and stale tables.
"""
from __future__ import annotations

import csv
import datetime as dt
from decimal import Decimal, InvalidOperation
import hashlib
import io
import json
import math
import os
from pathlib import Path
import re
import sys
import tempfile
import unicodedata


ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))
from private_runtime import SALES_LOG_FILE  # noqa: E402
from content_source_gate import validate_official_snapshot_contract  # noqa: E402

try:  # Script execution puts ``pipeline`` on sys.path.
    import ga4_decision_trust  # noqa: E402
    import ga4_pull  # noqa: E402
    import ga4_schema  # noqa: E402
    import gsc_pull  # noqa: E402
    import revenue_ledger  # noqa: E402
except ImportError:  # Package imports (``import pipeline.observation_snapshot``).
    from pipeline import ga4_decision_trust, ga4_pull, ga4_schema, gsc_pull, revenue_ledger  # noqa: E402


LOG = ROOT / "automation-log"
GA4_FILES = {
    "metrics": LOG / "ga4-metrics.csv",
    "pages": LOG / "ga4-pages.csv",
    "funnel": LOG / "ga4-funnel.csv",
    "pilot_sessions": LOG / "ga4-pilot-sessions.csv",
}
GSC_FILES = {
    "queries": LOG / "gsc-queries.csv",
    "pages": LOG / "gsc-pages.csv",
}
GA4_META = LOG / "ga4-snapshot.json"
GSC_META = LOG / "gsc-snapshot.json"
GA4_PRODUCER = Path(ga4_pull.__file__).resolve()
GSC_PRODUCER = Path(gsc_pull.__file__).resolve()
OFFICIAL = LOG / "knowledge-base" / "official-news-snapshot.json"
POLICY = ROOT / ".system_control" / "policy.json"
HOST = ROOT / ".system_control" / "host_ip.json"
BANGKOK = dt.timezone(dt.timedelta(hours=7))
OFFICIAL_MAX_AGE_HOURS = 24
GSC_TARGET_PROPERTIES = {
    "https://ngernduangold.com/",
    "sc-domain:ngernduangold.com",
    "https://www.ngernduangold.com/",
}

GA4_CSV_CONTRACTS = {
    "metrics": {
        "exact_fields": [
            "source", "raw_source", "medium", "channel", "sessions",
            "quiz_start", "affiliate_click", "buy_intent_click", "answer_seen",
            "line_lead_click", "internal_cta_click", "video_start",
        ],
        "required": {"source", "sessions", "quiz_start", "affiliate_click",
                     "buy_intent_click", "answer_seen", "line_lead_click",
                     "internal_cta_click", "video_start", "raw_source", "medium",
                     "channel"},
        "nonempty": {"source", "raw_source", "medium", "channel"},
        "unique_key": "source",
        "nonnegative_int": {"sessions", "quiz_start", "affiliate_click",
                            "buy_intent_click", "answer_seen", "line_lead_click",
                            "internal_cta_click", "video_start"},
        "ga4_attribution_consistency": True,
    },
    "pages": {
        "exact_fields": [
            "page", "views", "affiliate_click", "buy_intent_click", "answer_seen",
            "line_lead_click", "internal_cta_click", "video_start",
        ],
        "required": {"page", "views", "affiliate_click", "answer_seen",
                     "buy_intent_click", "line_lead_click", "internal_cta_click",
                     "video_start"},
        "nonempty": {"page"},
        "unique_key": "page",
        "nonnegative_int": {"views", "affiliate_click", "buy_intent_click",
                            "answer_seen", "line_lead_click", "internal_cta_click",
                            "video_start"},
    },
    "funnel": {
        "exact_fields": ["stage", "count", "step_conv_pct", "measurement_scope"],
        "required": {"stage", "count", "step_conv_pct", "measurement_scope"},
        "nonempty": {"stage", "measurement_scope"},
        "unique_key": "stage",
        "required_key_values": {
            "quiz_start", "quiz_complete", "recommendation_view", "affiliate_click"
        },
        "nonnegative_int": {"count"},
        "exact": {
            "step_conv_pct": "",
            "measurement_scope": "independent_event_total_not_sequence",
        },
    },
    "pilot_sessions": {
        "exact_fields": ga4_schema.PILOT_MEASUREMENT_FIELDS["field_order"],
        "required": set(ga4_schema.PILOT_MEASUREMENT_FIELDS["field_order"]),
        "nonempty": set(ga4_schema.PILOT_MEASUREMENT_FIELDS["dimensions"])
                    | {"measurement_scope"},
        "nonnegative_int": set(ga4_schema.PILOT_MEASUREMENT_FIELDS["fields"]),
        "exact": {"measurement_scope": "session"},
        "ga4_pilot_contract": True,
    },
}
GSC_CSV_CONTRACTS = {
    "queries": {
        "exact_fields": ["query", "clicks", "impressions", "ctr", "position"],
        "required": {"query", "clicks", "impressions", "ctr", "position"},
        "nonempty": {"query"},
        "unique_key": "query",
        "nonnegative_int": {"clicks", "impressions"},
        "number_ranges": {"ctr": (0, 100), "position": (0, None)},
        "gsc_metric_consistency": True,
        "canonical_key": "gsc_query",
    },
    "pages": {
        "exact_fields": ["page", "clicks", "impressions", "ctr", "position"],
        "required": {"page", "clicks", "impressions", "ctr", "position"},
        "nonempty": {"page"},
        "unique_key": "page",
        "nonnegative_int": {"clicks", "impressions"},
        "number_ranges": {"ctr": (0, 100), "position": (0, None)},
        "gsc_metric_consistency": True,
        "canonical_key": "gsc_page",
    },
}


def sha256_file(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def atomic_json(path, payload):
    selected = Path(path)
    selected.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=selected.stem + "-", suffix=".tmp",
                                     dir=str(selected.parent))
    try:
        with open(fd, "w", encoding="utf-8", newline="\n", closefd=True) as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2, sort_keys=True)
            handle.write("\n")
        Path(temp_name).replace(selected)
    except Exception:
        Path(temp_name).unlink(missing_ok=True)
        raise


def _strict_json_loads(text):
    def reject_constant(value):
        raise ValueError("non-finite JSON constant: " + str(value))

    def finite_float(value):
        parsed = float(value)
        if not math.isfinite(parsed):
            raise ValueError("non-finite JSON number")
        return parsed

    def unique_object(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("duplicate JSON object key")
            result[key] = value
        return result

    return json.loads(
        text,
        parse_constant=reject_constant,
        parse_float=finite_float,
        object_pairs_hook=unique_object,
    )


def _json(path, default=None):
    try:
        value = _strict_json_loads(Path(path).read_text(encoding="utf-8"))
        return value
    except Exception:
        return default


def _positive_finite_number(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return False
    try:
        return value > 0 and math.isfinite(value)
    except (OverflowError, TypeError, ValueError):
        return False


def _exact_int(value, expected=None):
    """Accept JSON integers only; bool and numerically-equal floats fail closed."""
    if not isinstance(value, int) or isinstance(value, bool):
        return False
    return expected is None or value == expected


def _rows(path):
    selected = Path(path)
    if not selected.is_file():
        return [], None
    try:
        with selected.open(encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle, strict=True)
            fields = list(reader.fieldnames or [])
            return list(reader), fields
    except (OSError, UnicodeError, csv.Error):
        return [], None


def _frozen_rows(path):
    """Read, hash, and parse one immutable in-memory CSV observation."""
    selected = Path(path)
    try:
        payload = selected.read_bytes()
        text = payload.decode("utf-8-sig")
        reader = csv.DictReader(io.StringIO(text, newline=""), strict=True)
        fields = list(reader.fieldnames or [])
        return list(reader), fields, hashlib.sha256(payload).hexdigest()
    except (OSError, UnicodeError, csv.Error):
        return [], None, None


def _int(row, key):
    try:
        number = _decimal(row.get(key, 0) or 0)
        if number != number.to_integral_value():
            return 0
        return int(number)
    except (TypeError, ValueError):
        return 0


def _decimal(value):
    try:
        number = Decimal(str(value).strip())
    except (InvalidOperation, ValueError, AttributeError) as exc:
        raise ValueError("not numeric") from exc
    if not number.is_finite():
        raise ValueError("not finite")
    return number


def validate_csv(path, contract):
    """Validate header and value domains; return a reason and data-row count."""
    rows, fields = _rows(path)
    if fields is None:
        return "CSV is missing or unreadable", 0
    if len(fields) != len(set(fields)) or any(not field for field in fields):
        return "CSV header contains a duplicate or blank field", len(rows)
    exact_fields = contract.get("exact_fields")
    if exact_fields is not None and fields != list(exact_fields):
        return "CSV header does not match the canonical field order", len(rows)
    required = set(contract.get("required", ()))
    missing = sorted(required - set(fields))
    if missing:
        return "CSV header is missing: " + ", ".join(missing), len(rows)
    unique_key = contract.get("unique_key")
    seen_values = set()
    for index, row in enumerate(rows, 2):
        if None in row:
            return "CSV row %d has more values than its header" % index, len(rows)
        for key in contract.get("nonempty", ()):
            if not str(row.get(key, "") or "").strip():
                return "CSV row %d has blank %s" % (index, key), len(rows)
        if unique_key:
            selected = str(row.get(unique_key, "") or "")
            canonical_key = contract.get("canonical_key")
            if canonical_key == "gsc_query":
                canonical = " ".join(
                    unicodedata.normalize("NFKC", selected).strip().split()
                ).casefold()
            elif canonical_key == "gsc_page":
                canonical = unicodedata.normalize("NFC", selected).strip()
            else:
                canonical = selected
            if selected != canonical:
                return "CSV row %d has non-canonical %s" % (index, unique_key), len(rows)
            if selected in seen_values:
                return "CSV row %d duplicates %s" % (index, unique_key), len(rows)
            seen_values.add(selected)
        for key in contract.get("nonnegative_int", ()):
            try:
                number = _decimal(row.get(key, ""))
            except ValueError:
                return "CSV row %d has invalid %s" % (index, key), len(rows)
            if number < 0 or number != number.to_integral_value():
                return "CSV row %d has invalid %s" % (index, key), len(rows)
        for key, bounds in contract.get("number_ranges", {}).items():
            try:
                number = _decimal(row.get(key, ""))
            except ValueError:
                return "CSV row %d has invalid %s" % (index, key), len(rows)
            minimum, maximum = bounds
            if (minimum is not None and number < minimum) or (
                maximum is not None and number > maximum
            ):
                return "CSV row %d has out-of-range %s" % (index, key), len(rows)
        for key, expected in contract.get("exact", {}).items():
            if str(row.get(key, "") or "") != expected:
                return "CSV row %d has invalid %s semantics" % (index, key), len(rows)
        if contract.get("ga4_attribution_consistency"):
            for key in ("raw_source", "medium"):
                selected = str(row.get(key, "") or "")
                canonical = " ".join(selected.strip().split()).lower()
                if selected != canonical:
                    return "CSV row %d has non-canonical %s" % (index, key), len(rows)
            expected_source = "%s / %s" % (row.get("raw_source"), row.get("medium"))
            if row.get("source") != expected_source:
                return "CSV row %d has inconsistent source/medium identity" % index, len(rows)
            expected_channel = ga4_pull._norm(row.get("raw_source"), row.get("medium"))
            if row.get("channel") != expected_channel:
                return "CSV row %d has inconsistent canonical channel" % index, len(rows)
        if contract.get("gsc_metric_consistency"):
            try:
                clicks = _decimal(row.get("clicks", ""))
                impressions = _decimal(row.get("impressions", ""))
                ctr = _decimal(row.get("ctr", ""))
                position = _decimal(row.get("position", ""))
            except ValueError:
                return "CSV row %d has invalid GSC metric semantics" % index, len(rows)
            if clicks > impressions:
                return "CSV row %d has clicks greater than impressions" % index, len(rows)
            if impressions == 0:
                if clicks != 0 or ctr != 0 or position != 0:
                    return "CSV row %d has inconsistent zero-impression metrics" % index, len(rows)
            else:
                expected_ctr = clicks / impressions * Decimal("100")
                # Producers round percentages to two decimal places.  A tolerance
                # just over half one output unit accepts that representation while
                # still rejecting semantically unrelated percentages.
                if abs(ctr - expected_ctr) > Decimal("0.0051"):
                    return "CSV row %d has CTR inconsistent with clicks/impressions" % index, len(rows)
                if position <= 0:
                    return "CSV row %d has non-positive position with impressions" % index, len(rows)
    if contract.get("ga4_pilot_contract"):
        pilot_errors = ga4_schema.pilot_table_errors(rows, fields)
        if pilot_errors:
            return "pilot session contract: " + "; ".join(pilot_errors), len(rows)
    required_values = set(contract.get("required_key_values", ()))
    if required_values and seen_values != required_values:
        return "CSV %s values do not match the required set" % unique_key, len(rows)
    return None, len(rows)


def _configured_ga4_property_id():
    value = os.environ.get("GA4_PROPERTY_ID", "").strip()
    if value:
        return value
    try:
        import winreg
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment")
        try:
            value, _kind = winreg.QueryValueEx(key, "GA4_PROPERTY_ID")
        finally:
            winreg.CloseKey(key)
        return str(value or "").strip()
    except Exception:
        return ""


def require_source_identity(bundle, source, *, expected_ga4_property=None,
                            expected_ga4_event_contract=None):
    """Require a producer-bound analytics source before data can be decisionable."""
    if not bundle.get("decisionable"):
        return bundle
    meta = bundle.get("metadata")
    if not isinstance(meta, dict):
        return {**bundle, "decisionable": False, "state": "SOURCE_IDENTITY_MISSING"}
    if source == "ga4":
        property_id = meta.get("property_id")
        if (not isinstance(property_id, str) or not property_id.isdigit()
                or not property_id.strip()):
            return {**bundle, "decisionable": False,
                    "state": "SOURCE_IDENTITY_MISSING"}
        expected = (str(expected_ga4_property).strip()
                    if expected_ga4_property is not None
                    else _configured_ga4_property_id())
        if not expected or not expected.isdigit():
            return {**bundle, "decisionable": False,
                    "state": "SOURCE_IDENTITY_UNVERIFIED"}
        if property_id != expected:
            return {**bundle, "decisionable": False,
                    "state": "WRONG_SOURCE_IDENTITY"}
        declared_contract = meta.get("event_contract")
        expected_contract = (
            dict(expected_ga4_event_contract)
            if expected_ga4_event_contract is not None
            else {field: event for event, field in ga4_pull.EVENT_FIELDS.items()}
        )
        if not isinstance(declared_contract, dict):
            return {**bundle, "decisionable": False,
                    "state": "EVENT_CONTRACT_MISSING"}
        if declared_contract != expected_contract:
            return {**bundle, "decisionable": False,
                    "state": "EVENT_CONTRACT_MISMATCH"}
    elif source == "gsc":
        site_url = meta.get("site_url")
        if not isinstance(site_url, str) or not site_url.strip():
            return {**bundle, "decisionable": False,
                    "state": "SOURCE_IDENTITY_MISSING"}
        if site_url not in GSC_TARGET_PROPERTIES:
            return {**bundle, "decisionable": False,
                    "state": "WRONG_SOURCE_IDENTITY"}
    else:
        raise ValueError("unsupported analytics source identity")
    return bundle


def require_ga4_pilot_provenance(bundle, *, repo=ROOT, site_dir=None):
    """Bind the pilot table to current producer/schema/pilot/page bytes."""
    if not bundle.get("decisionable"):
        return bundle
    meta = bundle.get("metadata")
    if not isinstance(meta, dict):
        return {**bundle, "decisionable": False, "state": "PILOT_BINDING_MISSING"}
    if (
        meta.get("pilot_measurement_contract") != ga4_pull.PILOT_MEASUREMENT_CONTRACT
        or meta.get("pilot_schema_contract") != ga4_schema.PILOT_MEASUREMENT_FIELDS
    ):
        return {**bundle, "decisionable": False,
                "state": "PILOT_CONTRACT_MISMATCH"}
    binding = meta.get("pilot_binding")
    required = {
        "pilot_id", "pilot_contract_sha256", "pilot_page_sha256",
        "schema_adapter_sha256", "producer_file_sha256",
        "producer_contract_sha256", "target",
    }
    if not isinstance(binding, dict) or set(binding) != required:
        return {**bundle, "decisionable": False, "state": "PILOT_BINDING_MISSING"}
    try:
        current = ga4_pull._pilot_capture_context(repo=repo, site_dir=site_dir)
    except Exception:
        return {**bundle, "decisionable": False,
                "state": "PILOT_BINDING_UNAVAILABLE"}
    expected = {
        "pilot_id": current.get("pilot_id"),
        "pilot_contract_sha256": current.get("pilot_contract_sha256"),
        "pilot_page_sha256": current.get("pilot_page_sha256"),
        "schema_adapter_sha256": current.get("schema_adapter_sha256"),
        "producer_file_sha256": current.get("producer_file_sha256"),
        "producer_contract_sha256": current.get("producer_contract_sha256"),
        "target": current.get("target"),
    }
    if binding != expected:
        return {**bundle, "decisionable": False,
                "state": "PILOT_BINDING_MISMATCH"}
    return bundle


def require_ga4_cross_file_consistency(bundle, files=None, *, tables=None):
    """Reject a bundle whose independently queried event totals disagree."""
    if not bundle.get("decisionable"):
        return bundle
    required = ("metrics", "pages", "funnel", "pilot_sessions")
    if tables is not None:
        if (
            not isinstance(tables, dict)
            or any(
                name not in tables
                or not isinstance(tables[name], tuple)
                or len(tables[name]) != 2
                or not isinstance(tables[name][0], list)
                for name in required
            )
        ):
            return {**bundle, "decisionable": False,
                    "state": "MATERIALIZATION_PROVENANCE_MISSING"}
        metrics = tables["metrics"][0]
        pages = tables["pages"][0]
        funnel = tables["funnel"][0]
        pilot = tables["pilot_sessions"][0]
    else:
        selected = files or GA4_FILES
        metrics, _ = _rows(selected["metrics"])
        pages, _ = _rows(selected["pages"])
        funnel, _ = _rows(selected["funnel"])
        pilot, _ = _rows(selected["pilot_sessions"])

    def total(rows, field):
        return sum(int(_decimal(row.get(field, ""))) for row in rows)

    funnel_counts = {str(row.get("stage") or ""): int(_decimal(row.get("count", "")))
                     for row in funnel}
    comparisons = {
        "quiz_start metrics/funnel": (
            total(metrics, "quiz_start"), funnel_counts.get("quiz_start")
        ),
        "affiliate_click metrics/pages": (
            total(metrics, "affiliate_click"), total(pages, "affiliate_click")
        ),
        "affiliate_click metrics/funnel": (
            total(metrics, "affiliate_click"), funnel_counts.get("affiliate_click")
        ),
    }
    for field in ("buy_intent_click", "answer_seen", "line_lead_click",
                  "internal_cta_click", "video_start"):
        comparisons[field + " metrics/pages"] = (
            total(metrics, field), total(pages, field)
        )
    if any(left != right for left, right in comparisons.values()):
        failed = sorted(name for name, values in comparisons.items()
                        if values[0] != values[1])
        return {**bundle, "decisionable": False, "state": "CROSS_FILE_MISMATCH",
                "consistency_errors": failed}
    pilot_sessions = sum(
        int(_decimal(row.get("affiliate_click_sessions", ""))) for row in pilot
    )
    if pilot_sessions > total(metrics, "affiliate_click"):
        return {**bundle, "decisionable": False, "state": "CROSS_FILE_MISMATCH",
                "consistency_errors": [
                    "pilot affiliate sessions exceed affiliate click events"
                ]}
    return bundle


def require_ga4_coverage(bundle):
    """Require complete, internally consistent pagination evidence per GA4 query."""
    if not bundle.get("decisionable"):
        return bundle
    meta = bundle.get("metadata")
    coverage = meta.get("query_coverage") if isinstance(meta, dict) else None
    if not isinstance(coverage, dict) or set(coverage) != set(ga4_pull.GA4_QUERY_NAMES):
        return {**bundle, "decisionable": False, "state": "COVERAGE_MISSING"}
    required = {
        "api_row_count", "row_limit", "rows_fetched", "pages_fetched",
        "offsets", "page_row_counts", "response_row_counts", "truncated",
        "complete",
    }
    for name in ga4_pull.GA4_QUERY_NAMES:
        item = coverage.get(name)
        if not isinstance(item, dict) or set(item) != required:
            return {**bundle, "decisionable": False, "state": "INVALID_COVERAGE"}
        api_rows = item.get("api_row_count")
        limit = item.get("row_limit")
        fetched = item.get("rows_fetched")
        pages = item.get("pages_fetched")
        offsets = item.get("offsets")
        page_counts = item.get("page_row_counts")
        response_counts = item.get("response_row_counts")
        truncated = item.get("truncated")
        complete = item.get("complete")
        integers = (api_rows, limit, fetched, pages)
        if (any(not isinstance(value, int) or isinstance(value, bool) for value in integers)
                or api_rows < 0 or fetched < 0 or pages < 1
                or limit != ga4_pull.GA4_ROW_LIMIT
                or not isinstance(offsets, list)
                or not isinstance(page_counts, list)
                or not isinstance(response_counts, list)
                or not isinstance(truncated, bool) or not isinstance(complete, bool)
                or any(not isinstance(value, int) or isinstance(value, bool) or value < 0
                       for values in (offsets, page_counts, response_counts)
                       for value in values)):
            return {**bundle, "decisionable": False, "state": "INVALID_COVERAGE"}
        if truncated:
            return {**bundle, "decisionable": False, "state": "TRUNCATED"}
        if not complete:
            return {**bundle, "decisionable": False, "state": "INCOMPLETE_COVERAGE"}
        expected_pages = max(1, (api_rows + limit - 1) // limit)
        if (fetched != api_rows or pages != expected_pages
                or len(offsets) != pages or len(page_counts) != pages
                or len(response_counts) != pages
                or any(offset != index * limit
                       for index, offset in enumerate(offsets))
                or any(count != (0 if api_rows == 0 else
                                 min(limit, api_rows - index * limit))
                       for index, count in enumerate(page_counts))
                or any(count != api_rows for count in response_counts)
                or sum(page_counts) != fetched):
            return {**bundle, "decisionable": False,
                    "state": "COVERAGE_ROW_MISMATCH", "coverage_query": name}
    return bundle


def validate_bundle(meta_path, files, *, expected_days=28, expected_lag_days=0,
                    max_age_hours=36, now=None, csv_contracts=None,
                    expected_schema_version=2, producer_path=None):
    """Validate sidecar schema, exact file hashes, window and freshness."""
    current = now or dt.datetime.now(dt.timezone.utc)
    meta = _json(meta_path)
    result = {
        "decisionable": False,
        "state": "MISSING_METADATA",
        "metadata": meta,
        "metadata_valid": False,
        "freshness_current": False,
        "expires_at": None,
    }
    if (
        not isinstance(current, dt.datetime)
        or current.tzinfo is None
        or current.utcoffset() is None
    ):
        return {**result, "state": "INVALID_EVALUATION_TIME"}
    if not isinstance(meta, dict):
        return result
    if (not _exact_int(expected_schema_version)
            or not _exact_int(expected_days)
            or not _exact_int(meta.get("schema_version"), expected_schema_version)
            or not _exact_int(meta.get("window_days"), expected_days)
            or not isinstance(expected_lag_days, int) or isinstance(expected_lag_days, bool)
            or expected_lag_days < 0
            or not _positive_finite_number(max_age_hours)):
        return {**result, "state": "INVALID_METADATA"}
    try:
        captured = dt.datetime.fromisoformat(str(meta["captured_at"]).replace("Z", "+00:00"))
        start = dt.date.fromisoformat(str(meta["window_start"]))
        end = dt.date.fromisoformat(str(meta["window_end"]))
        if (
            captured.tzinfo is None
            or captured.utcoffset() is None
            or (end - start).days + 1 != expected_days
        ):
            raise ValueError("invalid window")
        if expected_lag_days and not _exact_int(
            meta.get("finalization_lag_days"), expected_lag_days
        ):
            raise ValueError("invalid finalization lag")
    except (KeyError, TypeError, ValueError):
        return {**result, "state": "INVALID_METADATA"}
    expected_end = (current.astimezone(BANGKOK).date()
                    - dt.timedelta(days=expected_lag_days))
    try:
        capture_expiry = captured.astimezone(dt.timezone.utc) + dt.timedelta(
            hours=max_age_hours
        )
        window_expiry = dt.datetime.combine(
            end + dt.timedelta(days=expected_lag_days + 1),
            dt.time.min,
            tzinfo=BANGKOK,
        )
    except (OverflowError, TypeError, ValueError):
        return {**result, "state": "INVALID_METADATA"}
    expires_at = min(
        capture_expiry,
        window_expiry.astimezone(dt.timezone.utc),
    ).isoformat(timespec="seconds")
    valid_metadata = {
        **result,
        "metadata_valid": True,
        "expires_at": expires_at,
    }
    if end < expected_end:
        return {**valid_metadata, "state": "STALE_WINDOW"}
    if end > expected_end:
        return {**valid_metadata, "state": "FUTURE_WINDOW"}
    age = (current.astimezone(dt.timezone.utc) - captured.astimezone(dt.timezone.utc)).total_seconds() / 3600
    if age < 0:
        return {**valid_metadata, "state": "FUTURE_CAPTURE",
                "age_hours": round(age, 2)}
    if age >= max_age_hours:
        return {**valid_metadata, "state": "STALE_CAPTURE",
                "age_hours": round(age, 2)}
    if producer_path is not None:
        try:
            current_producer_hash = sha256_file(producer_path)
        except (OSError, UnicodeError):
            return {**valid_metadata, "state": "PRODUCER_UNAVAILABLE",
                    "age_hours": round(age, 2)}
        if meta.get("producer_sha256") != current_producer_hash:
            return {**valid_metadata, "state": "PRODUCER_MISMATCH",
                    "age_hours": round(age, 2)}
    declared = meta.get("files")
    if not isinstance(declared, dict) or set(declared) != set(files):
        return {**valid_metadata, "state": "FILE_SET_MISMATCH", "age_hours": round(age, 2)}
    for name, path in files.items():
        if not Path(path).is_file() or declared.get(name) != sha256_file(path):
            return {**valid_metadata, "state": "HASH_MISMATCH", "age_hours": round(age, 2)}
    row_counts = {}
    if csv_contracts is not None:
        if set(csv_contracts) != set(files):
            return {**valid_metadata, "state": "INVALID_DATA_CONTRACT", "age_hours": round(age, 2)}
        for name, path in files.items():
            error, row_count = validate_csv(path, csv_contracts[name])
            row_counts[name] = row_count
            if error:
                return {**valid_metadata, "state": "INVALID_DATA", "data_error": "%s: %s" % (name, error),
                        "row_counts": row_counts, "age_hours": round(age, 2)}
    return {**valid_metadata, "decisionable": True, "state": "CURRENT",
            "freshness_current": True,
            "row_counts": row_counts, "age_hours": round(age, 2)}


def require_materialized_table(
    bundle, name, path, rows, fields, *, observed_hash=None
):
    """Bind materialized rows to the already accepted hash and row count."""
    if not bundle.get("decisionable"):
        return bundle
    if fields is None:
        return {**bundle, "decisionable": False,
                "state": "MATERIALIZATION_FAILED", "materialized_table": name}
    metadata = bundle.get("metadata")
    declared = metadata.get("files") if isinstance(metadata, dict) else None
    row_counts = bundle.get("row_counts")
    if (not isinstance(declared, dict) or not isinstance(row_counts, dict)
            or name not in declared or name not in row_counts):
        return {**bundle, "decisionable": False,
                "state": "MATERIALIZATION_PROVENANCE_MISSING",
                "materialized_table": name}
    if observed_hash is None:
        try:
            current_hash = sha256_file(path)
        except (OSError, UnicodeError):
            return {**bundle, "decisionable": False,
                    "state": "MATERIALIZATION_FAILED", "materialized_table": name}
    else:
        current_hash = observed_hash
    if current_hash != declared[name]:
        return {**bundle, "decisionable": False,
                "state": "HASH_CHANGED_DURING_READ", "materialized_table": name}
    if len(rows) != row_counts[name]:
        return {**bundle, "decisionable": False,
                "state": "MATERIALIZATION_ROW_MISMATCH",
                "materialized_table": name}
    return bundle


def materialize_bundle_tables(bundle, files):
    """Freeze and provenance-check every declared table used by a consumer.

    Parsing and hashing use the same byte string, so the returned rows cannot
    describe different file contents from the hash that made them eligible.
    All files are frozen even after an earlier gate blocks the bundle, allowing
    callers to report raw observations without treating them as decisionable.
    """
    tables = {}
    for name, path in files.items():
        rows, fields, observed_hash = _frozen_rows(path)
        tables[name] = (rows, fields)
        bundle = require_materialized_table(
            bundle, name, path, rows, fields, observed_hash=observed_hash
        )
    return bundle, tables


def decision_expiry_error(bundle, decision_time, source):
    """Return a fail-closed reason when an analytics bundle has no live expiry."""
    if not isinstance(decision_time, dt.datetime) or decision_time.tzinfo is None:
        return "%s decision time is invalid" % source
    if not isinstance(bundle, dict):
        return "%s bundle is not an object" % source
    raw = bundle.get("expires_at")
    if not isinstance(raw, str) or not raw.strip():
        return "%s bundle expiry is missing" % source
    try:
        expiry = dt.datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return "%s bundle expiry is invalid" % source
    if expiry.tzinfo is None or expiry.utcoffset() is None:
        return "%s bundle expiry is timezone-naive" % source
    if expiry <= decision_time:
        return "%s bundle expiry is not after the decision time" % source
    return None


def build_learning_readiness(
    ga4_bundle, gsc_bundle, revenue, *, expected_end, decision_time
):
    """Return canonical readiness and the exact safe data-refresh actions."""
    ga4_bundle = ga4_bundle if isinstance(ga4_bundle, dict) else {}
    gsc_bundle = gsc_bundle if isinstance(gsc_bundle, dict) else {}
    revenue = revenue if isinstance(revenue, dict) else {}
    ga4_state = str(ga4_bundle.get("state") or "UNAVAILABLE")
    gsc_state = str(gsc_bundle.get("state") or "UNAVAILABLE")
    ga4_capture_trust = ga4_bundle.get("capture_trust")
    ga4_current_trust = ga4_bundle.get("current_trust")
    ga4_expiry_error = decision_expiry_error(
        ga4_bundle, decision_time, "GA4"
    )
    gsc_expiry_error = decision_expiry_error(
        gsc_bundle, decision_time, "GSC"
    )
    ga4_current_trust_ready = ga4_current_trust == "TRUSTED"
    ga4_trust_ready = (
        ga4_capture_trust == "TRUSTED" and ga4_current_trust_ready
    )
    ga4_ready = (
        ga4_bundle.get("decisionable") is True
        and ga4_state == "CURRENT"
        and ga4_trust_ready
        and ga4_expiry_error is None
    )
    gsc_ready = (
        gsc_bundle.get("decisionable") is True
        and gsc_state == "CURRENT"
        and gsc_expiry_error is None
    )
    revenue_errors = revenue_ledger.learning_contract_errors(
        revenue, expected_end=expected_end, observed_at=decision_time
    )
    revenue_ready = not revenue_errors

    ga4_action = (
        "NONE" if ga4_ready
        else "REPAIR_GA4_TRUST_THEN_REPULL" if not ga4_current_trust_ready
        else "REPULL_GA4"
    )
    gsc_action = "NONE" if gsc_ready else "REPULL_GSC"
    revenue_action = "NONE" if revenue_ready else "RECONCILE_REVENUE"
    sources = {
        "ga4": {
            "ready": ga4_ready,
            "state": ga4_state,
            "action": ga4_action,
            "capture_trust": ga4_capture_trust,
            "current_trust": ga4_current_trust,
            "errors": (
                ([] if ga4_trust_ready else
                 ["GA4 capture/current trust is missing or untrusted"])
                + ([ga4_expiry_error] if ga4_expiry_error else [])
            ),
        },
        "gsc": {"ready": gsc_ready, "state": gsc_state,
                "action": gsc_action,
                "errors": ([gsc_expiry_error] if gsc_expiry_error else [])},
        "revenue": {
            "ready": revenue_ready,
            "state": str(revenue.get("quality_state") or "UNAVAILABLE"),
            "action": revenue_action,
            "errors": revenue_errors,
        },
    }
    blockers = [name + "_not_ready" for name, item in sources.items()
                if not item["ready"]]
    actions = [
        {"source": name, "action": item["action"], "reason_code": item["state"]}
        for name, item in sources.items() if not item["ready"]
    ]
    passed = sum(1 for item in sources.values() if item["ready"])
    return {
        "schema_version": 1,
        "status": "READY" if not blockers else "BLOCKED",
        "ready": not blockers,
        "score": {"passed": passed, "total": len(sources)},
        "blockers": blockers,
        "actions": actions,
        "sources": sources,
    }


def require_gsc_coverage(bundle):
    """Require producer-declared non-truncation and exact CSV row counts."""
    if not bundle.get("decisionable"):
        return bundle
    meta = bundle.get("metadata")
    coverage = meta.get("coverage") if isinstance(meta, dict) else None
    if not isinstance(coverage, dict) or set(coverage) != set(GSC_FILES):
        return {**bundle, "decisionable": False, "state": "TRUNCATION_UNKNOWN"}
    actual_rows = bundle.get("row_counts", {})
    for name in GSC_FILES:
        item = coverage.get(name)
        if not isinstance(item, dict):
            return {**bundle, "decisionable": False, "state": "TRUNCATION_UNKNOWN"}
        row_limit = item.get("row_limit")
        rows = item.get("rows")
        api_rows = item.get("api_rows")
        output_rows = item.get("output_rows")
        collapsed = item.get("duplicate_rows_collapsed")
        truncated = item.get("truncated")
        if (not isinstance(row_limit, int) or isinstance(row_limit, bool) or row_limit < 1
                or not isinstance(rows, int) or isinstance(rows, bool) or rows < 0
                or not isinstance(api_rows, int) or isinstance(api_rows, bool) or api_rows < 0
                or not isinstance(output_rows, int) or isinstance(output_rows, bool)
                or output_rows < 0
                or not isinstance(collapsed, int) or isinstance(collapsed, bool) or collapsed < 0
                or not isinstance(truncated, bool)):
            return {**bundle, "decisionable": False, "state": "INVALID_COVERAGE"}
        if (rows != actual_rows.get(name) or output_rows != rows
                or api_rows < output_rows or collapsed != api_rows - output_rows):
            return {**bundle, "decisionable": False, "state": "COVERAGE_ROW_MISMATCH"}
        if truncated != (api_rows >= row_limit):
            return {**bundle, "decisionable": False, "state": "INVALID_COVERAGE"}
        if truncated:
            return {**bundle, "decisionable": False, "state": "TRUNCATED"}
    return bundle


def validate_official_snapshot(path=OFFICIAL, *, now=None,
                               max_age_hours=OFFICIAL_MAX_AGE_HOURS):
    """Return fail-closed freshness and review state for official-source evidence."""
    current = now or dt.datetime.now(dt.timezone.utc)
    payload = _json(path)
    base = {"current": False, "clear_for_publication": False,
            "state": "MISSING", "checked_at": None,
            "changed": None, "errors": None, "review_required": None}
    if not isinstance(payload, dict):
        return base
    result = validate_official_snapshot_contract(
        payload,
        now=current,
        freshness_hours=max_age_hours,
        strict_all_rows=True,
    )
    changed_ids = payload.get("changed") if isinstance(payload.get("changed"), list) else []
    error_ids = payload.get("errors") if isinstance(payload.get("errors"), list) else []
    review_ids = (
        payload.get("review_required")
        if isinstance(payload.get("review_required"), list) else []
    )
    state_only_prefixes = (
        "relevant official source changed:",
        "relevant official source error:",
        "relevant official source review is pending:",
    )
    contract_errors = [
        issue for issue in result.failures
        if not issue.startswith(state_only_prefixes)
    ]
    counts = {
        "changed": len(changed_ids),
        "errors": len(error_ids),
        "review_required": len(review_ids),
    }
    if contract_errors:
        # Structural/schema failures outrank age.  A schema-2 or malformed
        # artifact that also happens to be old is INVALID, not a merely stale
        # schema-3 observation that could be refreshed safely.
        stale = bool(contract_errors) and all(
            issue == "official source snapshot is stale"
            for issue in contract_errors
        )
        if stale:
            checked = dt.datetime.fromisoformat(
                payload["checked_at"].replace("Z", "+00:00")
            )
            age = (
                current.astimezone(dt.timezone.utc)
                - checked.astimezone(dt.timezone.utc)
            ).total_seconds() / 3600
            expires_at = checked + dt.timedelta(hours=max_age_hours)
            return {
                **base,
                **counts,
                "state": "STALE",
                "checked_at": checked.isoformat(timespec="seconds"),
                "age_hours": round(age, 2),
                "expires_at": expires_at.isoformat(timespec="seconds"),
                "contract_errors": contract_errors,
            }
        return {
            **base,
            **counts,
            "state": "INVALID",
            "contract_errors": contract_errors,
        }
    checked = dt.datetime.fromisoformat(
        payload["checked_at"].replace("Z", "+00:00")
    )
    age = (
        current.astimezone(dt.timezone.utc) - checked.astimezone(dt.timezone.utc)
    ).total_seconds() / 3600
    counts = {
        "checked_at": checked.isoformat(timespec="seconds"),
        **counts,
        "age_hours": round(age, 2),
        "expires_at": (
            checked + dt.timedelta(hours=max_age_hours)
        ).isoformat(timespec="seconds"),
    }
    clear = not changed_ids and not error_ids and not review_ids
    state = "ERROR" if error_ids else "FRESH_REVIEW_REQUIRED" if review_ids else "CURRENT"
    if state == "ERROR":
        return {**base, **counts, "state": state}
    return {**base, **counts, "current": True,
            "clear_for_publication": clear, "state": state}


def _normalize_url(value):
    text = str(value or "").split("?", 1)[0].rstrip("/")
    return text[:-5] if text.endswith(".html") else text


def _monetized_urls(site=None):
    base = Path(site or ROOT / "site")
    urls = set()
    for path in base.glob("*.html"):
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeError):
            continue
        if "atth.me" not in text:
            continue
        match = re.search(r'<link[^>]+rel="canonical"[^>]+href="([^"]+)"', text, re.I)
        if not match:
            match = re.search(r'<link[^>]+href="([^"]+)"[^>]+rel="canonical"', text, re.I)
        if match:
            urls.add(_normalize_url(match.group(1)))
    return urls


def collect(*, now=None, today=None, sales_path=SALES_LOG_FILE):
    current = now or dt.datetime.now(dt.timezone.utc)
    if not isinstance(current, dt.datetime) or current.tzinfo is None:
        raise ValueError("now must be a timezone-aware datetime")
    local_day = today or current.astimezone(dt.timezone(dt.timedelta(hours=7))).date()
    try:
        trust = ga4_decision_trust.evaluate_ga4_decision_trust(
            POLICY, HOST, now=current
        )
        trust_label = str(trust.label)
        trust_boolean = trust.trusted is True and trust_label == "TRUSTED"
        ga4_trust = {"label": trust_label if trust_boolean else "UNTRUSTED",
                     "trusted": trust_boolean,
                     "reason": str(trust.reason), "schema": str(trust.schema),
                     "expires_at": getattr(trust, "expires_at", None)}
    except Exception as exc:
        ga4_trust = {"label": "UNTRUSTED", "trusted": False,
                     "reason": "GA4 trust evaluation failed (%s)" % type(exc).__name__,
                     "schema": "error", "expires_at": None}
    runtime_expiry = None
    if ga4_trust["trusted"]:
        try:
            runtime_expiry = dt.datetime.fromisoformat(
                str(ga4_trust.get("expires_at") or "").replace("Z", "+00:00")
            )
            if runtime_expiry.tzinfo is None or runtime_expiry <= current:
                raise ValueError("runtime trust has expired")
        except (TypeError, ValueError):
            ga4_trust = {
                "label": "UNTRUSTED",
                "trusted": False,
                "reason": "GA4 runtime trust expiry is missing, invalid, or expired",
                "schema": ga4_trust.get("schema", "unknown"),
                "expires_at": None,
            }
            runtime_expiry = None
    ga4_bundle = require_ga4_pilot_provenance(
        require_source_identity(require_ga4_coverage(validate_bundle(
            GA4_META, GA4_FILES, now=current, csv_contracts=GA4_CSV_CONTRACTS,
            producer_path=GA4_PRODUCER, expected_schema_version=3,
        )), "ga4"))
    gsc_bundle = require_source_identity(require_gsc_coverage(validate_bundle(
        GSC_META, GSC_FILES, now=current, expected_lag_days=3,
        csv_contracts=GSC_CSV_CONTRACTS, producer_path=GSC_PRODUCER,
    )), "gsc")
    capture_metadata = ga4_bundle.get("metadata")
    capture_trust = (capture_metadata.get("ga4_decision_trust")
                     if isinstance(capture_metadata, dict) else None)
    capture_evidence = (capture_metadata.get("capture_time_trust")
                        if isinstance(capture_metadata, dict) else None)
    ga4_bundle["capture_trust"] = capture_trust
    ga4_bundle["capture_time_trust"] = capture_evidence
    ga4_bundle["current_trust"] = ga4_trust["label"]
    capture_evidence_valid = (
        isinstance(capture_evidence, dict)
        and isinstance(capture_evidence.get("trusted"), bool)
        and capture_evidence.get("label") in ("TRUSTED", "UNTRUSTED")
        and isinstance(capture_evidence.get("reason"), str)
        and bool(capture_evidence["reason"].strip())
        and isinstance(capture_evidence.get("schema"), str)
        and bool(capture_evidence["schema"].strip())
        and capture_evidence["trusted"] == (capture_evidence["label"] == "TRUSTED")
        and capture_trust == capture_evidence["label"]
    )
    if capture_evidence_valid and capture_evidence.get("trusted") is True:
        try:
            capture_expiry = dt.datetime.fromisoformat(
                str(capture_evidence.get("expires_at") or "").replace("Z", "+00:00")
            )
            captured_at = dt.datetime.fromisoformat(
                str(capture_metadata.get("captured_at") or "").replace("Z", "+00:00")
            )
            capture_evidence_valid = (
                capture_expiry.tzinfo is not None
                and captured_at.tzinfo is not None
                and capture_expiry > captured_at
            )
        except (TypeError, ValueError):
            capture_evidence_valid = False
    if ga4_bundle.get("decisionable") and not capture_evidence_valid:
        ga4_bundle["decisionable"] = False
        ga4_bundle["state"] = "INVALID_CAPTURE_TRUST"
    if ga4_bundle.get("decisionable") and capture_trust != "TRUSTED":
        ga4_bundle["decisionable"] = False
        ga4_bundle["state"] = "UNTRUSTED_AT_CAPTURE"
    if ga4_bundle.get("decisionable") and not ga4_trust["trusted"]:
        ga4_bundle["decisionable"] = False
        ga4_bundle["state"] = "UNTRUSTED_NOW"
    if ga4_bundle.get("decisionable"):
        try:
            bundle_expiry = dt.datetime.fromisoformat(
                str(ga4_bundle.get("expires_at") or "").replace("Z", "+00:00")
            )
            if bundle_expiry.tzinfo is None or runtime_expiry is None:
                raise ValueError("GA4 expiry is incomplete")
            combined_expiry = min(
                bundle_expiry.astimezone(dt.timezone.utc),
                runtime_expiry.astimezone(dt.timezone.utc),
            )
            if combined_expiry <= current.astimezone(dt.timezone.utc):
                raise ValueError("GA4 expiry has passed")
            ga4_bundle["expires_at"] = combined_expiry.isoformat(timespec="seconds")
            ga4_bundle["runtime_trust_expires_at"] = (
                runtime_expiry.astimezone(dt.timezone.utc).isoformat(timespec="seconds")
            )
        except (TypeError, ValueError):
            ga4_bundle["decisionable"] = False
            ga4_bundle["state"] = "INVALID_RUNTIME_EXPIRY"

    ga4_bundle, ga4_tables = materialize_bundle_tables(ga4_bundle, GA4_FILES)
    gsc_bundle, gsc_tables = materialize_bundle_tables(gsc_bundle, GSC_FILES)
    ga4_bundle = require_ga4_cross_file_consistency(
        ga4_bundle, tables=ga4_tables
    )
    ga4_rows, ga4_fields = ga4_tables["metrics"]
    pilot_rows, pilot_fields = ga4_tables["pilot_sessions"]
    gsc_rows, gsc_fields = gsc_tables["pages"]

    ga4_totals = {
        "sessions": sum(_int(row, "sessions") for row in ga4_rows),
        "quiz_start": sum(_int(row, "quiz_start") for row in ga4_rows),
        "affiliate_click": sum(_int(row, "affiliate_click") or _int(row, "conversion") for row in ga4_rows),
        "buy_intent_click": sum(_int(row, "buy_intent_click") for row in ga4_rows),
        "answer_seen": sum(_int(row, "answer_seen") for row in ga4_rows),
        "line_lead_click": sum(_int(row, "line_lead_click") for row in ga4_rows),
        "internal_cta_click": sum(_int(row, "internal_cta_click") for row in ga4_rows),
        "pilot_affiliate_click_sessions": sum(
            _int(row, "affiliate_click_sessions") for row in pilot_rows
        ),
        "pilot_qualified_landing_sessions": sum(
            _int(row, "qualified_landing_sessions") for row in pilot_rows
        ),
    }
    monetized = _monetized_urls()
    gsc_totals = {
        "clicks": sum(_int(row, "clicks") for row in gsc_rows),
        "impressions": sum(_int(row, "impressions") for row in gsc_rows),
        "monetized_clicks": sum(_int(row, "clicks") for row in gsc_rows
                                 if _normalize_url(row.get("page")) in monetized),
        "monetized_impressions": sum(_int(row, "impressions") for row in gsc_rows
                                      if _normalize_url(row.get("page")) in monetized),
    }
    source_state = validate_official_snapshot(OFFICIAL, now=current)
    revenue = revenue_ledger.read_affiliate_revenue(
        sales_path, today=local_day, days=28, now=current
    )
    learning_readiness = build_learning_readiness(
        ga4_bundle, gsc_bundle, revenue, expected_end=local_day,
        decision_time=current,
    )
    return {
        "schema_version": 1,
        "observed_at": current.isoformat(timespec="seconds"),
        "window_days": 28,
        "sources": {
            "ga4": {"trust": ga4_trust, "bundle": ga4_bundle,
                    "rows": len(ga4_rows), "fields": ga4_fields,
                    "pilot_rows": len(pilot_rows),
                    "pilot_fields": pilot_fields},
            "gsc": {"bundle": gsc_bundle, "rows": len(gsc_rows), "fields": gsc_fields},
            "revenue_ledger": {
                "trusted": revenue.get("trusted") is True,
                "quality_state": revenue.get("quality_state", "UNAVAILABLE"),
                "learning_ready": revenue.get("learning_ready") is True,
                "reconcile_required": revenue.get("reconcile_required") is not False,
                "next_action": revenue.get("next_action", "RECONCILE_REVENUE"),
                "error": revenue.get("error"),
            },
            "official_sources": source_state,
        },
        "metrics": {
            "ga4_observed_not_decisionable_unless_trusted": ga4_totals,
            "gsc_observed_not_decisionable_unless_current": gsc_totals,
            "verified_affiliate_revenue": revenue,
        },
        "learning_readiness": learning_readiness,
    }


if __name__ == "__main__":
    print(json.dumps(collect(), ensure_ascii=False, indent=2))
