"""Strict reader for the private revenue ledger used by the improvement loop.

``affiliate_click`` is not revenue.  This module reduces validated lifecycle
events to the latest state of each ``affiliate-commission`` sale.  One malformed
event or invalid transition
makes the window unavailable for decisions instead of silently turning bad
data into zero revenue.
"""
from __future__ import annotations

import datetime as dt
from decimal import Decimal, InvalidOperation
import json
import math
from pathlib import Path
import re
import sys


ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))
from private_runtime import SALES_LOG_FILE  # noqa: E402
import log_sale  # noqa: E402
import import_accesstrade_csv as accesstrade_csv  # noqa: E402


ALLOWED_STATUS = {
    "pending", "approved", "paid", "rejected", "refunded", "cancelled",
}
SCHEMA_VERSION = 5
BANGKOK = log_sale.BANGKOK
FUTURE_TOLERANCE = dt.timedelta(minutes=5)
POSITIVE_AMOUNT_STATUS = {"pending", "approved", "paid"}
ZERO_AMOUNT_STATUS = {"rejected", "cancelled"}
NORTH_STAR_STATUS = {"paid"}
VERIFIED_REVENUE_STATUSES = ("paid",)
AFFILIATE_TRANSACTION_FACT_FIELDS = (
    "date",
    "status",
    "source",
    "gross_amount_thb",
    "fee_thb",
    "net_amount_thb",
)
METADATA_KEYS = {
    "_meta", "schema_version", "fields", "products", "blocked_products",
    "channel_source_values", "created", "updated", "source_system",
    "coverage_start", "coverage_end", "extracted_at", "reconciled_at",
    "source_snapshot_sha256", "source_row_count", "upstream_evidence",
    "complete",
}
REQUIRED_SALE_FIELDS = {
    "event_id", "sale_id", "date", "product", "status", "gross_amount_thb",
    "fee_thb", "net_amount_thb", "channel_source", "ref", "note", "ts",
}


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


def _money(value, label):
    try:
        if isinstance(value, bool):
            raise InvalidOperation
        number = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ValueError(label + " is not numeric") from exc
    if not number.is_finite():
        raise ValueError(label + " is not finite")
    try:
        if number != number.quantize(Decimal("0.01")):
            raise ValueError(label + " has more than two decimal places")
    except InvalidOperation as exc:
        raise ValueError(label + " is outside the supported money range") from exc
    return number


def _canonical_money(value: Decimal) -> str:
    """Serialize one already-validated THB value without float ambiguity."""
    return format(value.quantize(Decimal("0.01")), ".2f")


def _affiliate_transaction_fact(row: dict) -> dict:
    """Return the privacy-safe decision grain for one latest-state sale.

    Sale/event IDs, references, notes, and timestamps are deliberately omitted.
    Duplicate economic facts remain duplicate list rows, preserving counts while
    preventing downstream consumers from silently rewriting a paid window to
    zero and still passing the learning contract.
    """
    return {
        "date": row["date"].isoformat(),
        "status": row["status"],
        "source": row["source"],
        "gross_amount_thb": _canonical_money(row["gross"]),
        "fee_thb": _canonical_money(row["fee"]),
        "net_amount_thb": _canonical_money(row["net"]),
    }


def _fact_sort_key(fact: dict) -> tuple[str, ...]:
    return tuple(str(fact[field]) for field in AFFILIATE_TRANSACTION_FACT_FIELDS)


def _validate_amount_contract(row, status, line_number):
    """Return exact THB decimals after enforcing lifecycle-specific math."""
    gross = _money(row.get("gross_amount_thb"), "gross_amount_thb")
    fee = _money(row.get("fee_thb"), "fee_thb")
    net = _money(row.get("net_amount_thb"), "net_amount_thb")
    if gross < 0 or fee < 0 or fee > gross:
        raise ValueError("invalid gross amount or fee at line %d" % line_number)

    if status in POSITIVE_AMOUNT_STATUS:
        expected = gross - fee
        if net < 0 or net != expected:
            raise ValueError(
                "%s net amount does not match gross minus fee at line %d"
                % (status, line_number)
            )
    elif status == "refunded":
        expected = -(gross - fee)
        if net > 0 or net != expected:
            raise ValueError(
                "refunded net amount must reverse gross minus fee at line %d"
                % line_number
            )
    elif status in ZERO_AMOUNT_STATUS:
        if gross != 0 or fee != 0 or net != 0:
            raise ValueError(
                "%s amounts must all be zero at line %d" % (status, line_number)
            )
    else:  # defensive: callers must validate the enum first
        raise ValueError("invalid status at line %d" % line_number)
    return gross, fee, net


def _unique_strings(value, *, allow_empty=False):
    return (
        isinstance(value, list)
        and (allow_empty or bool(value))
        and all(isinstance(item, str) and item.strip() for item in value)
        and len(value) == len(set(value))
    )


def _validate_metadata(row, line_number):
    """Accept only a complete, reconciled source-export envelope."""
    if set(row) != METADATA_KEYS:
        raise ValueError("invalid metadata envelope at line %d" % line_number)
    fields = row.get("fields")
    sources = row.get("channel_source_values")
    blocked_products = row.get("blocked_products")
    source_row_count = row.get("source_row_count")
    if (row.get("schema_version") != SCHEMA_VERSION
            or not isinstance(row.get("_meta"), str)
            or not row["_meta"].strip()
            or not _unique_strings(fields)
            or set(fields) != REQUIRED_SALE_FIELDS
            or not isinstance(row.get("products"), dict)
            or "affiliate-commission" not in row["products"]
            or any(not isinstance(key, str) or not key.strip()
                   for key in row["products"])
            or not _unique_strings(blocked_products, allow_empty=True)
            or not _unique_strings(sources)
            or not isinstance(row.get("source_system"), str)
            or not row["source_system"].strip()
            or not isinstance(row.get("upstream_evidence"), list)
            or not row["upstream_evidence"]
            or row.get("complete") is not True
            or not isinstance(source_row_count, int)
            or isinstance(source_row_count, bool)
            or source_row_count < 0
            or not re.fullmatch(r"[0-9a-f]{64}", str(row.get("source_snapshot_sha256", "")))):
        raise ValueError("invalid metadata contract at line %d" % line_number)
    try:
        created = dt.date.fromisoformat(str(row.get("created", "")))
        updated = dt.date.fromisoformat(str(row.get("updated", "")))
    except (TypeError, ValueError) as exc:
        raise ValueError("invalid metadata date at line %d" % line_number) from exc
    if updated < created:
        raise ValueError("metadata updated date precedes created date at line %d" % line_number)
    try:
        coverage_start = dt.date.fromisoformat(str(row.get("coverage_start", "")))
        coverage_end = dt.date.fromisoformat(str(row.get("coverage_end", "")))
        extracted_at = dt.datetime.fromisoformat(str(row.get("extracted_at", "")))
        reconciled_at = dt.datetime.fromisoformat(str(row.get("reconciled_at", "")))
    except (TypeError, ValueError) as exc:
        raise ValueError("invalid reconciliation timestamp at line %d" % line_number) from exc
    if coverage_end < coverage_start:
        raise ValueError("metadata coverage end precedes start at line %d" % line_number)
    if (
        extracted_at.tzinfo is None
        or extracted_at.utcoffset() is None
        or reconciled_at.tzinfo is None
        or reconciled_at.utcoffset() is None
    ):
        raise ValueError("reconciliation timestamps must be timezone-aware at line %d" % line_number)
    if reconciled_at < extracted_at:
        raise ValueError("reconciled_at precedes extracted_at at line %d" % line_number)
    if reconciled_at.astimezone(BANGKOK).date() < coverage_end:
        raise ValueError("reconciliation predates coverage end at line %d" % line_number)
    return (
        coverage_start,
        coverage_end,
        source_row_count,
        extracted_at,
        reconciled_at,
        row["source_snapshot_sha256"],
        row["upstream_evidence"],
    )


def read_affiliate_revenue(path=SALES_LOG_FILE, *, today=None, days=28, now=None):
    """Return a fail-closed rolling affiliate revenue summary."""
    if not isinstance(days, int) or isinstance(days, bool) or days < 1:
        raise ValueError("days must be a positive integer")
    end = today or dt.date.today()
    if isinstance(end, dt.datetime) or not isinstance(end, dt.date):
        raise ValueError("today must be a date")
    if now is None:
        evaluation_time = dt.datetime.now(dt.timezone.utc)
    else:
        if (
            not isinstance(now, dt.datetime)
            or now.tzinfo is None
            or now.utcoffset() is None
        ):
            raise ValueError("now must be a timezone-aware datetime")
        evaluation_time = now
        if end > evaluation_time.astimezone(BANGKOK).date():
            raise ValueError("today cannot be after the evaluation date")
    start = end - dt.timedelta(days=days - 1)
    selected = Path(path)
    base = {
        "trusted": False,
        "window_start": start.isoformat(),
        "window_end": end.isoformat(),
        "window_days": days,
        "reconciliation_state": "UNRECONCILED",
        "quality_state": "UNAVAILABLE",
        "learning_ready": False,
        "reconcile_required": True,
        "next_action": "RECONCILE_REVENUE",
        "coverage_start": None,
        "coverage_end": None,
        "extracted_at": None,
        "reconciled_at": None,
        "source_row_count": None,
        "source_snapshot_sha256": None,
        "upstream_evidence_bound": False,
        "upstream_evidence_count": None,
        "upstream_raw_file_sha256": [],
        "upstream_browser_evidence_sha256": [],
        "upstream_receipt_file_sha256": [],
        "upstream_receipt_sha256": [],
        "upstream_bound_event_rows": None,
        "attribution_state": None,
        "attribution_scope": None,
        "sub_id_available": None,
        "page_cta_attribution_ready": False,
        "verified_revenue_statuses": list(VERIFIED_REVENUE_STATUSES),
        "pending_is_verified_revenue": False,
        "trust_expires_at": None,
        "ledger_event_rows": None,
        "ledger_transaction_rows": None,
        "affiliate_window_transactions": None,
        "affiliate_window_transaction_facts": None,
        "verified_transactions": None,
        "paid_transactions": None,
        "confirmed_transactions": None,
        "pending_transactions": None,
        "approved_transactions": None,
        "rejected_transactions": None,
        "refund_transactions": None,
        "refund_amount_thb": None,
        "cancelled_transactions": None,
        "paid_revenue_thb": None,
        "verified_revenue_thb": None,
        "pending_amount_thb": None,
        "approved_amount_thb": None,
        "net_revenue_thb": None,
        "by_source": {},
        "pending_by_source": {},
        "approved_by_source": {},
        "lifecycle_counts": {},
        "latest_transaction_date": None,
        "latest_paid_date": None,
    }
    if not selected.is_file():
        return {**base, "quality_state": "MISSING_LEDGER",
                "error": "private sales ledger is missing"}

    raw_events = []
    records = []
    metadata_seen = False
    metadata_coverage = None
    metadata_source_row_count = None
    metadata_source_hash = None
    metadata_extracted_at = None
    metadata_reconciled_at = None
    metadata_upstream_evidence = None
    metadata_sources = set()
    metadata_products = set()
    try:
        payload = selected.read_bytes()
        if payload and not payload.endswith(b"\n"):
            raise ValueError("final JSONL row lacks newline commit boundary")
        text = payload.decode("utf-8")
        for line_number, raw in enumerate(text.splitlines(), 1):
            if not raw.strip():
                raise ValueError("blank JSONL row at line %d" % line_number)
            try:
                row = _strict_json_loads(raw)
            except (TypeError, ValueError) as exc:
                raise ValueError("invalid JSON at line %d" % line_number) from exc
            if not isinstance(row, dict):
                raise ValueError("row %d is not an object" % line_number)
            sale_id = str(row.get("sale_id", "")).strip()
            if not sale_id:
                if "_meta" in row or "schema_version" in row:
                    if metadata_seen or raw_events or line_number != 1:
                        raise ValueError("metadata envelope must be the first and only metadata row")
                    (coverage_start, coverage_end, metadata_source_row_count,
                     metadata_extracted_at, metadata_reconciled_at,
                     metadata_source_hash, metadata_upstream_evidence) = _validate_metadata(
                         row, line_number
                     )
                    metadata_coverage = (coverage_start, coverage_end)
                    metadata_sources = set(row["channel_source_values"])
                    metadata_products = set(row["products"])
                    metadata_seen = True
                    continue
                raise ValueError("sale_id missing at line %d" % line_number)
            if not metadata_seen:
                raise ValueError("reconciled metadata envelope is required before events")
            if set(row) != REQUIRED_SALE_FIELDS:
                raise ValueError("event fields do not match contract at line %d" % line_number)
            try:
                date = dt.date.fromisoformat(str(row.get("date", "")))
            except ValueError as exc:
                raise ValueError("invalid date at line %d" % line_number) from exc
            status = str(row.get("status", "")).strip().lower()
            if status not in ALLOWED_STATUS:
                raise ValueError("invalid status at line %d" % line_number)
            _validate_amount_contract(row, status, line_number)
            product = str(row.get("product", "")).strip()
            source = str(row.get("channel_source", "")).strip()
            if product not in metadata_products:
                raise ValueError("unknown product at line %d" % line_number)
            if source not in metadata_sources:
                raise ValueError("unknown channel_source at line %d" % line_number)
            if not (metadata_coverage[0] <= date <= metadata_coverage[1]):
                raise ValueError("transaction falls outside reconciled coverage")
            try:
                log_sale.validate_record(row, now=metadata_extracted_at)
            except log_sale.IntakeError as exc:
                raise ValueError(
                    "event is not canonical at line %d: %s" % (line_number, exc)
                ) from exc
            transaction_stamp = dt.datetime.fromisoformat(
                str(row.get("ts", "")).replace("Z", "+00:00")
            )
            if transaction_stamp.astimezone(dt.timezone.utc) > metadata_extracted_at.astimezone(dt.timezone.utc):
                raise ValueError("transaction timestamp is after source extraction at line %d" % line_number)
            raw_events.append(row)
        if not metadata_seen or metadata_coverage is None:
            return {**base, "quality_state": "MISSING_METADATA",
                    "error": "reconciled metadata envelope is missing"}
        try:
            latest_by_sale = log_sale.validate_event_sequence(
                raw_events, now=metadata_extracted_at
            )
        except log_sale.IntakeError as exc:
            raise ValueError("invalid lifecycle event sequence: %s" % exc) from exc
        try:
            evidence_summary = accesstrade_csv.validate_embedded_evidence(
                metadata_upstream_evidence,
                raw_events,
                source_sha256=metadata_source_hash,
                source_row_count=metadata_source_row_count,
                coverage_start=metadata_coverage[0],
                coverage_end=metadata_coverage[1],
                extracted_at=metadata_extracted_at,
            )
        except accesstrade_csv.AccessTradeImportError as exc:
            raise ValueError("invalid upstream AccessTrade evidence: %s" % exc) from exc
        event_lines = {
            event["event_id"]: index + 2
            for index, event in enumerate(raw_events)
        }
        for row in latest_by_sale.values():
            gross, fee, net = _validate_amount_contract(
                row, row["status"], event_lines[row["event_id"]]
            )
            records.append({
                "event_id": row["event_id"],
                "sale_id": row["sale_id"],
                "date": dt.date.fromisoformat(row["date"]),
                "status": row["status"],
                "product": row["product"],
                "source": row["channel_source"],
                "gross": gross,
                "fee": fee,
                "net": net,
            })
    except (OSError, UnicodeError, ValueError) as exc:
        return {**base, "quality_state": "INVALID_LEDGER", "error": str(exc)}

    if not metadata_seen or metadata_coverage is None:
        return {**base, "quality_state": "MISSING_METADATA",
                "error": "reconciled metadata envelope is missing"}
    provenance = {
        "source_row_count": metadata_source_row_count,
        "source_snapshot_sha256": metadata_source_hash,
        "ledger_event_rows": len(raw_events),
        "ledger_transaction_rows": len(records),
        "coverage_start": metadata_coverage[0].isoformat(),
        "coverage_end": metadata_coverage[1].isoformat(),
        "extracted_at": metadata_extracted_at.isoformat(timespec="seconds"),
        "reconciled_at": metadata_reconciled_at.isoformat(timespec="seconds"),
        "upstream_evidence_bound": True,
        **evidence_summary,
    }
    if metadata_source_row_count != len(raw_events):
        return {
            **base,
            **provenance,
            "quality_state": "ROW_COUNT_MISMATCH",
            "error": "source_row_count does not match ledger event rows",
        }
    if metadata_extracted_at.astimezone(dt.timezone.utc) > (
        evaluation_time.astimezone(dt.timezone.utc) + FUTURE_TOLERANCE
    ) or metadata_reconciled_at.astimezone(dt.timezone.utc) > (
        evaluation_time.astimezone(dt.timezone.utc) + FUTURE_TOLERANCE
    ):
        return {
            **base,
            **provenance,
            "quality_state": "FUTURE_RECONCILIATION",
            "error": "reconciliation timestamps are after the evaluation time",
        }
    if metadata_coverage[0] > start:
        return {**base, **provenance, "quality_state": "INCOMPLETE_COVERAGE",
                "error": "reconciled source coverage starts after the requested window"}
    if metadata_coverage[1] < end:
        return {**base, **provenance, "quality_state": "STALE_COVERAGE",
                "error": "reconciled source coverage is stale for the requested window"}
    if metadata_coverage[1] > end:
        return {**base, **provenance, "quality_state": "FUTURE_COVERAGE",
                "error": "reconciled source coverage extends beyond the requested window"}

    window = [row for row in records
              if start <= row["date"] <= end and row["product"] == "affiliate-commission"]
    paid = [row for row in window if row["status"] == "paid"]
    pending = [row for row in window if row["status"] == "pending"]
    approved = [row for row in window if row["status"] == "approved"]
    rejected = [row for row in window if row["status"] == "rejected"]
    refunds = [row for row in window if row["status"] == "refunded"]
    cancelled = [row for row in window if row["status"] == "cancelled"]
    by_source = {}
    pending_by_source = {}
    approved_by_source = {}
    for row in window:
        if row["status"] not in NORTH_STAR_STATUS:
            continue
        by_source[row["source"]] = (
            by_source.get(row["source"], Decimal("0")) + row["net"]
        )
    for row in pending:
        pending_by_source[row["source"]] = (
            pending_by_source.get(row["source"], Decimal("0")) + row["net"]
        )
    for row in approved:
        approved_by_source[row["source"]] = (
            approved_by_source.get(row["source"], Decimal("0")) + row["net"]
        )
    lifecycle_counts = {
        status: sum(1 for row in window if row["status"] == status)
        for status in sorted(ALLOWED_STATUS)
    }
    paid_revenue = sum((row["net"] for row in paid), Decimal("0"))
    refund_amount = sum((-row["net"] for row in refunds), Decimal("0"))
    transaction_facts = sorted(
        (_affiliate_transaction_fact(row) for row in window),
        key=_fact_sort_key,
    )
    trust_expires_at = dt.datetime.combine(
        end + dt.timedelta(days=1), dt.time.min, tzinfo=BANGKOK
    ).isoformat(timespec="seconds")
    return {
        **base,
        "trusted": True,
        "reconciliation_state": "RECONCILED",
        "quality_state": "CURRENT",
        "learning_ready": True,
        "reconcile_required": False,
        "next_action": "NONE",
        "error": None,
        **provenance,
        # Independent decision-scope denominator.  Learning consumers reconcile
        # every lifecycle bucket against this value so a non-zero affiliate
        # window cannot be silently rewritten into an all-zero outcome.
        "affiliate_window_transactions": len(window),
        "affiliate_window_transaction_facts": transaction_facts,
        "verified_transactions": len(paid),
        "paid_transactions": len(paid),
        # Compatibility for current consumers: "confirmed" means paid payout only.
        "confirmed_transactions": len(paid),
        "pending_transactions": len(pending),
        "approved_transactions": len(approved),
        "rejected_transactions": len(rejected),
        "refund_transactions": len(refunds),
        "refund_amount_thb": float(refund_amount),
        "cancelled_transactions": len(cancelled),
        "paid_revenue_thb": float(paid_revenue),
        "verified_revenue_thb": float(paid_revenue),
        "pending_amount_thb": float(sum(
            (row["net"] for row in pending), Decimal("0")
        )),
        "approved_amount_thb": float(sum(
            (row["net"] for row in approved), Decimal("0")
        )),
        # Latest-state accounting: a refunded sale contributes zero, not a
        # second negative transaction after its superseded paid state.
        "net_revenue_thb": float(paid_revenue),
        "trust_expires_at": trust_expires_at,
        "by_source": {
            key: float(value) for key, value in sorted(by_source.items())
        },
        "pending_by_source": {
            key: float(value) for key, value in sorted(pending_by_source.items())
        },
        "approved_by_source": {
            key: float(value) for key, value in sorted(approved_by_source.items())
        },
        "lifecycle_counts": lifecycle_counts,
        "latest_transaction_date": max((row["date"].isoformat() for row in window), default=None),
        "latest_paid_date": max((row["date"].isoformat() for row in paid), default=None),
    }


def _transaction_fact_summary(facts, *, window_start, window_end):
    """Validate canonical anonymized facts and recompute every decision metric."""
    errors = []
    if not isinstance(facts, list):
        return None, ["affiliate window transaction facts are not a list"]

    normalized = []
    parsed = []
    required = set(AFFILIATE_TRANSACTION_FACT_FIELDS)
    for index, fact in enumerate(facts):
        label = "affiliate transaction fact %d" % (index + 1)
        if not isinstance(fact, dict) or set(fact) != required:
            errors.append(label + " fields do not match the privacy-safe contract")
            continue
        try:
            fact_date = dt.date.fromisoformat(str(fact["date"]))
            status = str(fact["status"])
            source = str(fact["source"])
            if fact["date"] != fact_date.isoformat():
                raise ValueError("date is not canonical")
            if status not in ALLOWED_STATUS or fact["status"] != status:
                raise ValueError("status is invalid")
            if source != "atth" or fact["source"] != source:
                raise ValueError("source is not merchant-total AccessTrade")
            if not (window_start <= fact_date <= window_end):
                raise ValueError("date is outside the requested window")
            gross, fee, net = _validate_amount_contract(fact, status, index + 1)
            canonical = {
                "date": fact_date.isoformat(),
                "status": status,
                "source": source,
                "gross_amount_thb": _canonical_money(gross),
                "fee_thb": _canonical_money(fee),
                "net_amount_thb": _canonical_money(net),
            }
            if fact != canonical:
                raise ValueError("money or text values are not canonical")
        except (KeyError, TypeError, ValueError) as exc:
            errors.append(label + " is invalid: " + str(exc))
            continue
        normalized.append(canonical)
        parsed.append({
            "date": fact_date,
            "status": status,
            "source": source,
            "gross": gross,
            "fee": fee,
            "net": net,
        })

    if len(parsed) != len(facts):
        return None, errors
    canonical_order = sorted(normalized, key=_fact_sort_key)
    if facts != canonical_order:
        errors.append("affiliate window transaction facts are not in canonical order")

    lifecycle = {
        status: sum(1 for row in parsed if row["status"] == status)
        for status in sorted(ALLOWED_STATUS)
    }
    paid = [row for row in parsed if row["status"] == "paid"]
    pending = [row for row in parsed if row["status"] == "pending"]
    approved = [row for row in parsed if row["status"] == "approved"]
    refunds = [row for row in parsed if row["status"] == "refunded"]

    def by_source(rows):
        values = {}
        for row in rows:
            values[row["source"]] = values.get(row["source"], Decimal("0")) + row["net"]
        return values

    paid_revenue = sum((row["net"] for row in paid), Decimal("0"))
    return {
        "affiliate_window_transactions": len(parsed),
        "verified_transactions": len(paid),
        "paid_transactions": len(paid),
        "confirmed_transactions": len(paid),
        "pending_transactions": len(pending),
        "approved_transactions": len(approved),
        "rejected_transactions": lifecycle["rejected"],
        "refund_transactions": len(refunds),
        "cancelled_transactions": lifecycle["cancelled"],
        "paid_revenue_thb": paid_revenue,
        "verified_revenue_thb": paid_revenue,
        "pending_amount_thb": sum(
            (row["net"] for row in pending), Decimal("0")
        ),
        "approved_amount_thb": sum(
            (row["net"] for row in approved), Decimal("0")
        ),
        "refund_amount_thb": sum(
            (-row["net"] for row in refunds), Decimal("0")
        ),
        "net_revenue_thb": paid_revenue,
        "by_source": by_source(paid),
        "pending_by_source": by_source(pending),
        "approved_by_source": by_source(approved),
        "lifecycle_counts": lifecycle,
        "latest_transaction_date": max(
            (row["date"].isoformat() for row in parsed), default=None
        ),
        "latest_paid_date": max(
            (row["date"].isoformat() for row in paid), default=None
        ),
    }, errors


def learning_contract_errors(payload, *, expected_end=None, observed_at=None):
    """Return reasons a revenue summary is unsafe for learning decisions."""
    if not isinstance(payload, dict):
        return ["revenue payload is not an object"]
    errors = []
    if (
        payload.get("trusted") is not True
        or payload.get("reconciliation_state") != "RECONCILED"
        or payload.get("quality_state") != "CURRENT"
        or payload.get("learning_ready") is not True
        or payload.get("reconcile_required") is not False
        or payload.get("next_action") != "NONE"
        or payload.get("error") is not None
        or payload.get("upstream_evidence_bound") is not True
    ):
        errors.append("revenue trust or reconciliation state is not current")
    if (
        payload.get("attribution_state") != accesstrade_csv.ATTRIBUTION_STATE
        or payload.get("attribution_scope") != accesstrade_csv.ATTRIBUTION_SCOPE
        or payload.get("sub_id_available") is not False
        or payload.get("page_cta_attribution_ready") is not False
    ):
        errors.append(
            "revenue attribution must remain merchant-total-only until a deterministic sub-id exists"
        )
    if (
        payload.get("verified_revenue_statuses") != list(VERIFIED_REVENUE_STATUSES)
        or payload.get("pending_is_verified_revenue") is not False
    ):
        errors.append("verified revenue must include paid status only; pending is excluded")

    count_keys = (
        "source_row_count", "ledger_event_rows", "ledger_transaction_rows",
        "affiliate_window_transactions",
        "verified_transactions",
        "paid_transactions", "confirmed_transactions", "pending_transactions",
        "approved_transactions", "rejected_transactions", "refund_transactions",
        "cancelled_transactions",
    )
    counts = {}
    for key in count_keys:
        value = payload.get(key)
        if not isinstance(value, int) or isinstance(value, bool) or value < 0:
            errors.append(key + " is not a non-negative integer")
        else:
            counts[key] = value
    if len(counts) == len(count_keys):
        if counts["source_row_count"] != counts["ledger_event_rows"]:
            errors.append("source row count does not equal event rows")
        if counts["ledger_transaction_rows"] > counts["ledger_event_rows"]:
            errors.append("transaction rows exceed event rows")
        if counts["confirmed_transactions"] != counts["paid_transactions"]:
            errors.append("confirmed transactions do not equal paid transactions")
        if counts["verified_transactions"] != counts["paid_transactions"]:
            errors.append("verified transactions do not equal paid transactions")
        if (
            counts["affiliate_window_transactions"]
            > counts["ledger_transaction_rows"]
        ):
            errors.append("affiliate window transactions exceed ledger transaction rows")

    source_hash = payload.get("source_snapshot_sha256")
    if not isinstance(source_hash, str) or not re.fullmatch(r"[0-9a-f]{64}", source_hash):
        errors.append("source snapshot hash is invalid")
    evidence_count = payload.get("upstream_evidence_count")
    bound_rows = payload.get("upstream_bound_event_rows")
    raw_hashes = payload.get("upstream_raw_file_sha256")
    browser_hashes = payload.get("upstream_browser_evidence_sha256")
    receipt_file_hashes = payload.get("upstream_receipt_file_sha256")
    receipt_hashes = payload.get("upstream_receipt_sha256")
    if (
        not isinstance(evidence_count, int) or isinstance(evidence_count, bool)
        or evidence_count < 1
    ):
        errors.append("upstream evidence count is invalid")
    if (
        not isinstance(bound_rows, int) or isinstance(bound_rows, bool)
        or bound_rows < 0
    ):
        errors.append("upstream bound event row count is invalid")
    elif "ledger_event_rows" in counts and bound_rows != counts["ledger_event_rows"]:
        errors.append("upstream bound event rows do not equal ledger event rows")
    if (
        not isinstance(raw_hashes, list) or len(raw_hashes) != evidence_count
        or any(not isinstance(value, str) or not re.fullmatch(r"[0-9a-f]{64}", value)
               for value in raw_hashes)
    ):
        errors.append("upstream raw file hashes are invalid")
    for label, hashes in (
        ("browser evidence", browser_hashes),
        ("receipt file", receipt_file_hashes),
        ("receipt canonical", receipt_hashes),
    ):
        if (
            not isinstance(hashes, list) or len(hashes) != evidence_count
            or any(
                not isinstance(value, str) or not re.fullmatch(r"[0-9a-f]{64}", value)
                for value in hashes
            )
        ):
            errors.append("upstream %s hashes are invalid" % label)

    window_start = None
    window_end = None
    coverage_start = None
    coverage_end = None
    trust_expiry = None
    try:
        window_start = dt.date.fromisoformat(str(payload.get("window_start", "")))
        window_end = dt.date.fromisoformat(str(payload.get("window_end", "")))
        coverage_start = dt.date.fromisoformat(str(payload.get("coverage_start", "")))
        coverage_end = dt.date.fromisoformat(str(payload.get("coverage_end", "")))
        days = payload.get("window_days")
        if not isinstance(days, int) or isinstance(days, bool) or days < 1:
            raise ValueError("invalid window days")
        if (window_end - window_start).days + 1 != days:
            errors.append("revenue window length is inconsistent")
        if coverage_start > window_start or coverage_end != window_end:
            errors.append("revenue coverage does not exactly close the requested window")
        if expected_end is not None:
            if isinstance(expected_end, dt.datetime) or not isinstance(expected_end, dt.date):
                errors.append("expected revenue end is invalid")
            elif window_end != expected_end:
                errors.append("revenue window end does not match the observation date")
        trust_expiry = dt.datetime.fromisoformat(
            str(payload.get("trust_expires_at") or "").replace("Z", "+00:00")
        )
        expected_expiry = dt.datetime.combine(
            coverage_end + dt.timedelta(days=1), dt.time.min, tzinfo=BANGKOK
        )
        if trust_expiry.tzinfo is None or trust_expiry != expected_expiry:
            errors.append("revenue trust expiry does not match the coverage boundary")
    except (TypeError, ValueError):
        errors.append("revenue window or coverage dates are invalid")

    extracted_at = None
    reconciled_at = None
    try:
        raw_extracted = payload.get("extracted_at")
        raw_reconciled = payload.get("reconciled_at")
        if not isinstance(raw_extracted, str) or not isinstance(raw_reconciled, str):
            raise ValueError("timestamps must be strings")
        extracted_at = dt.datetime.fromisoformat(raw_extracted)
        reconciled_at = dt.datetime.fromisoformat(raw_reconciled)
        if (
            extracted_at.tzinfo is None or extracted_at.utcoffset() is None
            or reconciled_at.tzinfo is None or reconciled_at.utcoffset() is None
        ):
            raise ValueError("timestamps must include a timezone")
        if (
            raw_extracted != extracted_at.isoformat(timespec="seconds")
            or raw_reconciled != reconciled_at.isoformat(timespec="seconds")
        ):
            raise ValueError("timestamps are not canonical")
        if reconciled_at < extracted_at:
            errors.append("revenue reconciliation timestamp precedes extraction")
        if (
            coverage_end is not None
            and reconciled_at.astimezone(BANGKOK).date() < coverage_end
        ):
            errors.append("revenue reconciliation timestamp precedes coverage end")
        if observed_at is not None:
            if (
                not isinstance(observed_at, dt.datetime)
                or observed_at.tzinfo is None
                or observed_at.utcoffset() is None
            ):
                errors.append("revenue observation timestamp is invalid")
            else:
                decision_time = observed_at.astimezone(dt.timezone.utc)
                if extracted_at.astimezone(dt.timezone.utc) > decision_time:
                    errors.append("revenue extraction timestamp is after the observation")
                if reconciled_at.astimezone(dt.timezone.utc) > decision_time:
                    errors.append("revenue reconciliation timestamp is after the observation")
                if (
                    expected_end is not None
                    and isinstance(expected_end, dt.date)
                    and not isinstance(expected_end, dt.datetime)
                    and observed_at.astimezone(BANGKOK).date() != expected_end
                ):
                    errors.append("revenue observation date does not match the expected window end")
                if (
                    trust_expiry is not None
                    and trust_expiry.tzinfo is not None
                    and decision_time >= trust_expiry.astimezone(dt.timezone.utc)
                ):
                    errors.append("revenue trust has expired at the observation time")
        if trust_expiry is not None and trust_expiry.tzinfo is not None:
            boundary = trust_expiry.astimezone(dt.timezone.utc)
            if extracted_at.astimezone(dt.timezone.utc) >= boundary:
                errors.append("revenue extraction timestamp is outside the trust window")
            if reconciled_at.astimezone(dt.timezone.utc) >= boundary:
                errors.append("revenue reconciliation timestamp is outside the trust window")
    except (TypeError, ValueError):
        errors.append("revenue extraction or reconciliation timestamp is invalid")

    money_keys = (
        "paid_revenue_thb", "verified_revenue_thb", "refund_amount_thb", "pending_amount_thb",
        "approved_amount_thb", "net_revenue_thb",
    )
    money = {}
    for key in money_keys:
        try:
            value = _money(payload.get(key), key)
        except ValueError:
            errors.append(key + " is not finite canonical money")
            continue
        if value < 0:
            errors.append(key + " must not be negative")
        money[key] = value
    if len(money) == len(money_keys):
        if money["paid_revenue_thb"] != money["net_revenue_thb"]:
            errors.append("latest-state net revenue does not equal paid revenue")
        if money["verified_revenue_thb"] != money["paid_revenue_thb"]:
            errors.append("verified revenue does not equal paid revenue")

    lifecycle = payload.get("lifecycle_counts")
    if not isinstance(lifecycle, dict) or set(lifecycle) != ALLOWED_STATUS:
        errors.append("lifecycle counts do not match the canonical status set")
    else:
        mapping = {
            "paid": "paid_transactions", "pending": "pending_transactions",
            "approved": "approved_transactions", "rejected": "rejected_transactions",
            "refunded": "refund_transactions", "cancelled": "cancelled_transactions",
        }
        for status, count_key in mapping.items():
            value = lifecycle.get(status)
            if (not isinstance(value, int) or isinstance(value, bool) or value < 0
                    or count_key in counts and value != counts[count_key]):
                errors.append("lifecycle count is inconsistent for " + status)
        if (
            "affiliate_window_transactions" in counts
            and all(
                isinstance(lifecycle.get(status), int)
                and not isinstance(lifecycle.get(status), bool)
                and lifecycle.get(status) >= 0
                for status in ALLOWED_STATUS
            )
            and sum(lifecycle.values()) != counts["affiliate_window_transactions"]
        ):
            errors.append(
                "affiliate window transactions do not reconcile to lifecycle counts"
            )

    by_source = payload.get("by_source")
    if not isinstance(by_source, dict):
        errors.append("paid revenue by source is not an object")
    else:
        try:
            source_total = sum((_money(value, "by_source") for value in by_source.values()),
                               Decimal("0"))
            if any(not isinstance(key, str) or not key.strip() for key in by_source):
                raise ValueError("invalid source key")
            if any(key != "atth" for key in by_source):
                raise ValueError("unattributed revenue cannot name a page or channel")
            if any(_money(value, "by_source") < 0 for value in by_source.values()):
                raise ValueError("negative source money")
            if "paid_revenue_thb" in money and source_total != money["paid_revenue_thb"]:
                errors.append("paid revenue by source does not reconcile")
        except ValueError:
            errors.append("paid revenue by source is invalid")
    for map_key, money_key in (
        ("pending_by_source", "pending_amount_thb"),
        ("approved_by_source", "approved_amount_thb"),
    ):
        source_map = payload.get(map_key)
        if not isinstance(source_map, dict):
            errors.append(map_key + " is not an object")
            continue
        try:
            if any(
                not isinstance(key, str) or key != "atth"
                for key in source_map
            ):
                raise ValueError("unattributed revenue cannot name a page or channel")
            values = [_money(value, map_key) for value in source_map.values()]
            if any(value < 0 for value in values):
                raise ValueError("negative source money")
            if money_key in money and sum(values, Decimal("0")) != money[money_key]:
                errors.append(map_key + " does not reconcile")
        except ValueError:
            errors.append(map_key + " is invalid")

    if window_start is not None and window_end is not None:
        fact_summary, fact_errors = _transaction_fact_summary(
            payload.get("affiliate_window_transaction_facts"),
            window_start=window_start,
            window_end=window_end,
        )
        errors.extend(fact_errors)
        if fact_summary is not None:
            for key in (
                "affiliate_window_transactions",
                "verified_transactions",
                "paid_transactions",
                "confirmed_transactions",
                "pending_transactions",
                "approved_transactions",
                "rejected_transactions",
                "refund_transactions",
                "cancelled_transactions",
            ):
                if key in counts and counts[key] != fact_summary[key]:
                    errors.append(key + " does not reconcile to transaction facts")
            for key in money_keys:
                if key in money and money[key] != fact_summary[key]:
                    errors.append(key + " does not reconcile to transaction facts")
            if lifecycle != fact_summary["lifecycle_counts"]:
                errors.append("lifecycle counts do not reconcile to transaction facts")
            for key in ("latest_transaction_date", "latest_paid_date"):
                if payload.get(key) != fact_summary[key]:
                    errors.append(key + " does not reconcile to transaction facts")

            for map_key in ("by_source", "pending_by_source", "approved_by_source"):
                raw_map = payload.get(map_key)
                try:
                    normalized_map = {
                        key: _money(value, map_key)
                        for key, value in raw_map.items()
                    }
                except (AttributeError, ValueError):
                    continue
                if normalized_map != fact_summary[map_key]:
                    errors.append(map_key + " does not reconcile to transaction facts")
    return errors


if __name__ == "__main__":
    print(json.dumps(read_affiliate_revenue(), ensure_ascii=False, indent=2))
