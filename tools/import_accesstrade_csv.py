#!/usr/bin/env python3
"""Create a private, hash-bound evidence receipt from an AccessTrade CSV.

The AccessTrade file does not contain the dashboard filter window.  Coverage,
date basis, status filter, and extraction time are therefore explicit browser
assertions and are never inferred from the CSV rows.  Multi-row exports require
an exact, hash-bound row-binding specification so ledger identities cannot be
paired by amount, status, or file order alone.  This importer writes only an
ignored private receipt; it never edits the intake or reconciled ledger.
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
from decimal import Decimal
import hashlib
import io
import json
import os
from pathlib import Path
import re
import tempfile
from typing import Any

import log_sale
from private_runtime import PRIVATE_ROOT


RECEIPT_SCHEMA_VERSION = 1
BROWSER_EVIDENCE_SCHEMA_VERSION = 2
ROW_BINDING_SPEC_SCHEMA_VERSION = 1
FORMAT_ID = "accesstrade-th-conversion-23-v1"
VERIFICATION_MODE = "authenticated_browser_read_only"
DATE_BASIS = "effect_date"
ATTRIBUTION_STATE = "UNATTRIBUTED"
ATTRIBUTION_SCOPE = "MERCHANT_TOTAL_ONLY"
REPORT_URL = (
    "https://publisher.accesstrade.in.th/"
    "#/dashboard/sites/reports/conversion"
)
LEDGER_REF_RE = re.compile(
    r"^accesstrade-dashboard-"
    r"(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[0-9]{4}$"
)
STATUS_MAP = {
    "PENDING": "pending",
    "APPROVED": "approved",
    "PAID": "paid",
    "REJECTED": "rejected",
    "REFUNDED": "refunded",
    "CANCELLED": "cancelled",
}
STATUS_FILTERS = ("ALL", *STATUS_MAP)
MONEY_RE = re.compile(r"^(?:0|[1-9][0-9]*)\.[0-9]{2}$")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


def _exact_schema_version(value: object, expected: int) -> bool:
    """Return true only for the exact JSON integer required by a contract."""
    return type(value) is int and value == expected

# Exact export order supplied by the authenticated AccessTrade dashboard.
# Unicode escapes keep this operational script safe on legacy Windows editors.
CSV_HEADERS = (
    "\u0e40\u0e27\u0e25\u0e32\u0e04\u0e25\u0e34\u0e01",
    "\u0e40\u0e27\u0e25\u0e32\u0e17\u0e35\u0e48\u0e40\u0e01\u0e34\u0e14\u0e1c\u0e25",
    "\u0e44\u0e0b\u0e15\u0e4c",
    "\u0e44\u0e2d\u0e14\u0e35\u0e41\u0e04\u0e21\u0e40\u0e1b\u0e0d",
    "Conversion ID",
    "\u0e44\u0e2d\u0e14\u0e35\u0e02\u0e2d\u0e07\u0e2b\u0e21\u0e27\u0e14\u0e2b\u0e21\u0e39\u0e48",
    "\u0e44\u0e2d\u0e14\u0e35\u0e02\u0e2d\u0e07\u0e1c\u0e25\u0e34\u0e15\u0e20\u0e31\u0e13\u0e11\u0e4c",
    "\u0e23\u0e32\u0e04\u0e32\u0e15\u0e48\u0e2d\u0e2b\u0e19\u0e48\u0e27\u0e22",
    "\u0e1b\u0e23\u0e34\u0e21\u0e32\u0e13",
    "\u0e23\u0e32\u0e04\u0e32\u0e2a\u0e38\u0e17\u0e18\u0e34",
    "\u0e1c\u0e25\u0e15\u0e2d\u0e1a\u0e41\u0e17\u0e19",
    "\u0e0a\u0e37\u0e48\u0e2d\u0e1c\u0e25\u0e34\u0e15\u0e20\u0e31\u0e13\u0e11\u0e4c",
    "\u0e2b\u0e21\u0e27\u0e14\u0e2b\u0e21\u0e39\u0e48\u0e1c\u0e25\u0e34\u0e15\u0e20\u0e31\u0e13\u0e11\u0e4c\u0e23\u0e30\u0e14\u0e31\u0e1a 1",
    "\u0e2b\u0e21\u0e27\u0e14\u0e2b\u0e21\u0e39\u0e48\u0e1c\u0e25\u0e34\u0e15\u0e20\u0e31\u0e13\u0e11\u0e4c\u0e23\u0e30\u0e14\u0e31\u0e1a 2",
    "\u0e2b\u0e21\u0e27\u0e14\u0e2b\u0e21\u0e39\u0e48\u0e1c\u0e25\u0e34\u0e15\u0e20\u0e31\u0e13\u0e11\u0e4c\u0e23\u0e30\u0e14\u0e31\u0e1a 3",
    "\u0e0a\u0e37\u0e48\u0e2d\u0e41\u0e1a\u0e23\u0e19\u0e14\u0e4c",
    "\u0e0a\u0e37\u0e48\u0e2d\u0e23\u0e49\u0e32\u0e19\u0e04\u0e49\u0e32",
    "URL \u0e1c\u0e25\u0e34\u0e15\u0e20\u0e31\u0e13\u0e11\u0e4c",
    "\u0e0a\u0e37\u0e48\u0e2d\u0e41\u0e04\u0e21\u0e40\u0e1b\u0e0d",
    "Transaction ID",
    "\u0e1b\u0e23\u0e30\u0e40\u0e20\u0e17\u0e25\u0e39\u0e01\u0e04\u0e49\u0e32",
    "\u0e2a\u0e16\u0e32\u0e19\u0e30",
    "\u0e20\u0e32\u0e29\u0e32",
)
CLICK_AT = CSV_HEADERS[0]
CONVERSION_AT = CSV_HEADERS[1]
CAMPAIGN_ID = CSV_HEADERS[3]
REWARD = CSV_HEADERS[10]
STATUS = CSV_HEADERS[21]

EVIDENCE_KEYS = {
    "schema_version", "provider", "format", "verification_mode",
    "raw_file_sha256", "raw_file_row_count", "header_sha256",
    "browser_evidence_sha256", "filter_assertion", "extracted_at", "importer_sha256",
    "sub_id_available", "attribution_state", "bindings",
}
FILTER_KEYS = {
    "coverage_start", "coverage_end", "date_basis", "status_filter",
    "campaign_filter", "asserted_conversion_count", "asserted_reward_thb",
    "currency", "timezone", "asserted_from",
}
BINDING_KEYS = {
    "provider_identity_sha256", "provider_conversion_id_hash",
    "transaction_id_hash", "campaign_id_hash", "source_row_sha256",
    "event_id", "sale_id", "date", "status", "gross_amount_thb",
    "fee_thb", "net_amount_thb", "channel_source", "ref",
}
EMBEDDED_KEYS = {
    "receipt_file_sha256", "receipt_sha256", "receipt", "canonical_source_sha256",
    "canonical_source_row_count",
}
BROWSER_EVIDENCE_KEYS = {
    "schema_version", "provider", "verified_at", "verification_mode",
    "report_url", "filters", "observed", "ledger_bindings",
    "external_mutation", "financial_action", "note",
}
BROWSER_FILTER_KEYS = {
    "period_start", "period_end", "date_basis", "status", "campaign",
}
BROWSER_OBSERVED_KEYS = {
    "campaign", "conversion_count", "total_reward_thb", "currency",
    "provider_conversion_id_available", "transaction_id_available",
    "sub_id_available",
}
BROWSER_LEDGER_BINDING_KEYS = {
    "event_id", "sale_id", "status", "amount_thb",
}
ROW_BINDING_SPEC_KEYS = {"schema_version", "raw_file_sha256", "bindings"}
ROW_BINDING_INPUT_KEYS = {
    "source_row_sha256", "event_id", "sale_id", "ledger_ref", "fee",
}
BROWSER_STATUS_TO_FILTER = {
    "all": "ALL",
    "pending_approval": "PENDING",
    "approved": "APPROVED",
    "paid": "PAID",
    "rejected": "REJECTED",
    "refunded": "REFUNDED",
    "cancelled": "CANCELLED",
}


class AccessTradeImportError(ValueError):
    """The raw export or its browser assertions are not decision-grade."""


def _canonical_bytes(value: object) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, allow_nan=False,
        separators=(",", ":"),
    ).encode("utf-8")


def canonical_sha256(value: object) -> str:
    return hashlib.sha256(_canonical_bytes(value)).hexdigest()


def file_sha256(path: str | os.PathLike[str]) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _importer_sha256() -> str:
    return file_sha256(__file__)


def _header_sha256() -> str:
    return canonical_sha256(list(CSV_HEADERS))


def _parse_date(value: object, label: str) -> dt.date:
    try:
        return dt.date.fromisoformat(str(value))
    except (TypeError, ValueError) as exc:
        raise AccessTradeImportError(label + " must be YYYY-MM-DD") from exc


def _parse_stamp(value: object, label: str) -> dt.datetime:
    try:
        stamp = dt.datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError) as exc:
        raise AccessTradeImportError(label + " must be ISO-8601") from exc
    if stamp.tzinfo is None:
        raise AccessTradeImportError(label + " must include a timezone")
    return stamp


def _parse_conversion_stamp(value: str) -> dt.datetime:
    if value != value.strip():
        raise AccessTradeImportError("conversion time has surrounding whitespace")
    try:
        stamp = dt.datetime.strptime(value, "%Y-%m-%d %H:%M:%S")
    except ValueError as exc:
        raise AccessTradeImportError(
            "conversion time must be YYYY-MM-DD HH:MM:SS"
        ) from exc
    return stamp.replace(tzinfo=log_sale.BANGKOK)


def _hash_identifier(label: str, value: str) -> str | None:
    if not value:
        return None
    if value != value.strip() or log_sale.CONTROL_RE.search(value):
        raise AccessTradeImportError(label + " is malformed")
    domains = {
        "conversion_id": "accesstrade-th/conversion-id/v1\0",
        "transaction_id": "accesstrade-th/transaction-id/v1\0",
        "campaign_id": "accesstrade-th/campaign-id/v1\0",
    }
    return hashlib.sha256((domains[label] + value).encode("utf-8")).hexdigest()


def _private_output(path: str | os.PathLike[str]) -> Path:
    try:
        selected = Path(path).expanduser().resolve()
        private = Path(PRIVATE_ROOT).resolve()
    except (OSError, TypeError, ValueError) as exc:
        raise AccessTradeImportError("receipt output path is invalid") from exc
    try:
        selected.relative_to(private)
    except ValueError as exc:
        raise AccessTradeImportError("receipt output must remain inside the private runtime") from exc
    try:
        selected.parent.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise AccessTradeImportError("private receipt directory is unavailable") from exc
    return selected


def _private_input(path: str | os.PathLike[str], label: str) -> Path:
    try:
        selected = Path(path).expanduser().resolve()
        private = Path(PRIVATE_ROOT).resolve()
    except (OSError, TypeError, ValueError) as exc:
        raise AccessTradeImportError(label + " path is invalid") from exc
    try:
        selected.relative_to(private)
    except ValueError as exc:
        raise AccessTradeImportError(label + " must remain inside the private runtime") from exc
    try:
        is_file = selected.is_file()
    except OSError as exc:
        raise AccessTradeImportError(label + " is unavailable") from exc
    if not is_file:
        raise AccessTradeImportError(label + " is missing")
    return selected


def _reject_duplicate_json_keys(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise AccessTradeImportError("browser evidence contains duplicate JSON keys")
        result[key] = value
    return result


def _read_browser_evidence(
    path: str | os.PathLike[str], *, expected_sha256: str,
) -> tuple[dict[str, Any], str]:
    selected = _private_input(path, "browser evidence")
    expected = str(expected_sha256 or "").strip().lower()
    if not SHA256_RE.fullmatch(expected):
        raise AccessTradeImportError("browser evidence SHA-256 is invalid")
    try:
        before = file_sha256(selected)
        payload = selected.read_bytes()
        evidence = json.loads(
            payload.decode("utf-8"), object_pairs_hook=_reject_duplicate_json_keys,
        )
    except AccessTradeImportError:
        raise
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise AccessTradeImportError("browser evidence must be readable UTF-8 JSON") from exc
    actual = hashlib.sha256(payload).hexdigest()
    try:
        after = file_sha256(selected)
    except OSError as exc:
        raise AccessTradeImportError("browser evidence became unreadable") from exc
    if before != actual or actual != expected or after != actual:
        raise AccessTradeImportError("browser evidence hash does not match frozen evidence")
    if not isinstance(evidence, dict):
        raise AccessTradeImportError("browser evidence must be a JSON object")
    return evidence, actual


def _read_row_binding_spec(
    path: str | os.PathLike[str],
    *,
    expected_sha256: str,
    expected_raw_sha256: str,
) -> list[dict[str, str]]:
    """Read one frozen private binding specification without trusting its path."""
    selected = _private_input(path, "row-binding specification")
    expected = str(expected_sha256 or "").strip().lower()
    raw_hash = str(expected_raw_sha256 or "").strip().lower()
    if not SHA256_RE.fullmatch(expected):
        raise AccessTradeImportError("row-binding specification SHA-256 is invalid")
    if not SHA256_RE.fullmatch(raw_hash):
        raise AccessTradeImportError("expected raw SHA-256 is invalid")
    try:
        before = file_sha256(selected)
        raw = selected.read_bytes()
        payload = json.loads(
            raw.decode("utf-8"), object_pairs_hook=_reject_duplicate_json_keys
        )
    except AccessTradeImportError:
        raise
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise AccessTradeImportError(
            "row-binding specification must be readable UTF-8 JSON"
        ) from exc
    actual = hashlib.sha256(raw).hexdigest()
    try:
        after = file_sha256(selected)
    except OSError as exc:
        raise AccessTradeImportError(
            "row-binding specification became unreadable"
        ) from exc
    if before != actual or actual != expected or after != actual:
        raise AccessTradeImportError(
            "row-binding specification hash does not match frozen input"
        )
    if not isinstance(payload, dict) or set(payload) != ROW_BINDING_SPEC_KEYS:
        raise AccessTradeImportError("row-binding specification fields are invalid")
    if (
        not _exact_schema_version(
            payload.get("schema_version"), ROW_BINDING_SPEC_SCHEMA_VERSION
        )
        or payload.get("raw_file_sha256") != raw_hash
        or not isinstance(payload.get("bindings"), list)
    ):
        raise AccessTradeImportError(
            "row-binding specification does not bind the exact raw CSV"
        )
    return payload["bindings"]


def _read_rows(
    source: Path, *, expected_raw_sha256: str, expected_row_count: int
) -> tuple[list[dict[str, str]], str]:
    if not source.is_file():
        raise AccessTradeImportError("AccessTrade CSV is missing")
    expected_hash = str(expected_raw_sha256 or "").strip().lower()
    if not SHA256_RE.fullmatch(expected_hash):
        raise AccessTradeImportError("expected raw SHA-256 is invalid")
    if (
        not isinstance(expected_row_count, int)
        or isinstance(expected_row_count, bool)
        or expected_row_count < 0
    ):
        raise AccessTradeImportError("expected row count must be a non-negative integer")
    try:
        before = file_sha256(source)
        payload = source.read_bytes()
        text = payload.decode("utf-8-sig")
    except (OSError, UnicodeError) as exc:
        raise AccessTradeImportError("AccessTrade CSV must be readable UTF-8") from exc
    raw_hash = hashlib.sha256(payload).hexdigest()
    if before != raw_hash or raw_hash != expected_hash:
        raise AccessTradeImportError("AccessTrade CSV hash does not match frozen evidence")
    try:
        parsed = list(csv.reader(io.StringIO(text, newline=""), strict=True))
    except csv.Error as exc:
        raise AccessTradeImportError("AccessTrade CSV is malformed") from exc
    if not parsed:
        raise AccessTradeImportError("AccessTrade CSV has no header")
    if tuple(parsed[0]) != CSV_HEADERS:
        raise AccessTradeImportError("AccessTrade CSV header/order does not match the exact contract")
    rows: list[dict[str, str]] = []
    for line_number, values in enumerate(parsed[1:], 2):
        if not values or all(value == "" for value in values):
            raise AccessTradeImportError("blank CSV row at source line %d" % line_number)
        if len(values) != len(CSV_HEADERS):
            raise AccessTradeImportError("CSV field count drift at source line %d" % line_number)
        if any(value != value.strip() for value in values):
            raise AccessTradeImportError("CSV value has surrounding whitespace at source line %d" % line_number)
        rows.append(dict(zip(CSV_HEADERS, values)))
    if len(rows) != expected_row_count:
        raise AccessTradeImportError("AccessTrade CSV row count does not match frozen evidence")
    try:
        after = file_sha256(source)
    except OSError as exc:
        raise AccessTradeImportError("AccessTrade CSV became unreadable") from exc
    if after != raw_hash:
        raise AccessTradeImportError("AccessTrade CSV changed while it was being read")
    return rows, raw_hash


def _source_row_sha256(row: dict[str, str]) -> str:
    return canonical_sha256([row[name] for name in CSV_HEADERS])


def _row_binding_map(
    entries: object, rows: list[dict[str, str]]
) -> dict[str, dict[str, str]]:
    """Validate exact row coverage and return bindings keyed by source-row hash."""
    if not isinstance(entries, list):
        raise AccessTradeImportError("row bindings must be a JSON list")
    actual_hashes = [_source_row_sha256(row) for row in rows]
    if len(actual_hashes) != len(set(actual_hashes)):
        raise AccessTradeImportError(
            "raw CSV contains duplicate source rows; deterministic binding is impossible"
        )
    if len(entries) != len(rows):
        raise AccessTradeImportError(
            "row bindings do not exactly cover parsed CSV rows"
        )
    by_hash: dict[str, dict[str, str]] = {}
    event_ids: set[str] = set()
    sale_ids: set[str] = set()
    for index, entry in enumerate(entries, 1):
        if not isinstance(entry, dict) or set(entry) != ROW_BINDING_INPUT_KEYS:
            raise AccessTradeImportError(
                "row binding %d fields are invalid" % index
            )
        if any(not isinstance(entry.get(key), str) for key in ROW_BINDING_INPUT_KEYS):
            raise AccessTradeImportError(
                "row binding %d values must be strings" % index
            )
        row_hash = entry["source_row_sha256"]
        event_id = entry["event_id"]
        sale_id = entry["sale_id"]
        ledger_ref = entry["ledger_ref"]
        fee = entry["fee"]
        if not SHA256_RE.fullmatch(row_hash):
            raise AccessTradeImportError("row binding source hash is invalid")
        if not event_id or not sale_id:
            raise AccessTradeImportError("row binding ledger identity is missing")
        if not LEDGER_REF_RE.fullmatch(ledger_ref):
            raise AccessTradeImportError(
                "row binding ledger ref must be provider-dashboard evidence"
            )
        if not MONEY_RE.fullmatch(fee):
            raise AccessTradeImportError(
                "row binding fee must be canonical THB with exactly two decimals"
            )
        if row_hash in by_hash or event_id in event_ids or sale_id in sale_ids:
            raise AccessTradeImportError("row bindings contain duplicate identities")
        by_hash[row_hash] = entry
        event_ids.add(event_id)
        sale_ids.add(sale_id)
    if set(by_hash) != set(actual_hashes):
        raise AccessTradeImportError(
            "row bindings do not exactly cover parsed CSV row hashes"
        )
    return by_hash


def _binding_for_row(
    row: dict[str, str], *, sale_id: str, event_id: str, channel_source: str,
    ledger_ref: str, fee: str, coverage_start: dt.date,
    coverage_end: dt.date, extracted_at: dt.datetime,
) -> dict[str, Any]:
    raw_status = row[STATUS]
    if raw_status not in STATUS_MAP:
        raise AccessTradeImportError("AccessTrade status is not in the exact lifecycle map")
    status = STATUS_MAP[raw_status]
    conversion_stamp = _parse_conversion_stamp(row[CONVERSION_AT])
    conversion_date = conversion_stamp.date()
    if not coverage_start <= conversion_date <= coverage_end:
        raise AccessTradeImportError("conversion time is outside asserted browser coverage")
    if conversion_stamp.astimezone(dt.timezone.utc) > extracted_at.astimezone(dt.timezone.utc):
        raise AccessTradeImportError("conversion time is after authenticated extraction")
    raw_reward = row[REWARD]
    if not MONEY_RE.fullmatch(raw_reward):
        raise AccessTradeImportError("reward must be canonical THB with exactly two decimals")
    amount = Decimal(raw_reward)
    conversion_hash = _hash_identifier("conversion_id", row["Conversion ID"])
    transaction_hash = _hash_identifier("transaction_id", row["Transaction ID"])
    campaign_hash = _hash_identifier("campaign_id", row[CAMPAIGN_ID])
    if conversion_hash is None and transaction_hash is None:
        raise AccessTradeImportError("provider conversion/transaction identity is missing")
    if campaign_hash is None:
        raise AccessTradeImportError("campaign identity is missing")
    identity_hash = canonical_sha256({
        "conversion_id_hash": conversion_hash,
        "transaction_id_hash": transaction_hash,
        "campaign_id_hash": campaign_hash,
        "conversion_at": conversion_stamp.isoformat(timespec="seconds"),
    })
    try:
        canonical = log_sale.make_record(
            event_id=event_id,
            sale_id=sale_id,
            product="affiliate-commission",
            amount=amount,
            fee=fee,
            status=status,
            source=channel_source,
            ref=ledger_ref,
            note="",
            date=conversion_date.isoformat(),
            now=conversion_stamp,
        )
    except log_sale.IntakeError as exc:
        raise AccessTradeImportError("ledger binding is invalid: " + str(exc)) from exc
    return {
        "provider_identity_sha256": identity_hash,
        "provider_conversion_id_hash": conversion_hash,
        "transaction_id_hash": transaction_hash,
        "campaign_id_hash": campaign_hash,
        "source_row_sha256": _source_row_sha256(row),
        "event_id": canonical["event_id"],
        "sale_id": canonical["sale_id"],
        "date": canonical["date"],
        "status": canonical["status"],
        "gross_amount_thb": canonical["gross_amount_thb"],
        "fee_thb": canonical["fee_thb"],
        "net_amount_thb": canonical["net_amount_thb"],
        "channel_source": canonical["channel_source"],
        "ref": canonical["ref"],
    }


def validate_receipt(receipt: object, *, require_complete: bool) -> dict[str, Any]:
    """Validate an importer receipt and return its canonical evidence payload."""
    if not isinstance(receipt, dict) or set(receipt) != {"_meta", "evidence", "evidence_sha256"}:
        raise AccessTradeImportError("upstream receipt envelope is invalid")
    evidence = receipt.get("evidence")
    if not isinstance(evidence, dict) or set(evidence) != EVIDENCE_KEYS:
        raise AccessTradeImportError("upstream evidence fields are invalid")
    if receipt.get("_meta") != "private AccessTrade CSV evidence receipt":
        raise AccessTradeImportError("upstream receipt type is invalid")
    if receipt.get("evidence_sha256") != canonical_sha256(evidence):
        raise AccessTradeImportError("upstream evidence canonical hash does not match")
    if (
        not _exact_schema_version(
            evidence.get("schema_version"), RECEIPT_SCHEMA_VERSION
        )
        or evidence.get("provider") != "accesstrade"
        or evidence.get("format") != FORMAT_ID
        or evidence.get("verification_mode") != VERIFICATION_MODE
        or evidence.get("header_sha256") != _header_sha256()
        or evidence.get("importer_sha256") != _importer_sha256()
        or evidence.get("sub_id_available") is not False
        or evidence.get("attribution_state") != ATTRIBUTION_STATE
        or not SHA256_RE.fullmatch(str(evidence.get("raw_file_sha256", "")))
        or not SHA256_RE.fullmatch(str(evidence.get("browser_evidence_sha256", "")))
    ):
        raise AccessTradeImportError("upstream evidence contract is invalid or stale")
    count = evidence.get("raw_file_row_count")
    bindings = evidence.get("bindings")
    if (
        not isinstance(count, int) or isinstance(count, bool) or count < 0
        or not isinstance(bindings, list) or len(bindings) != count
    ):
        raise AccessTradeImportError("upstream evidence row count is invalid")
    assertion = evidence.get("filter_assertion")
    if not isinstance(assertion, dict) or set(assertion) != FILTER_KEYS:
        raise AccessTradeImportError("browser filter assertion is invalid")
    start = _parse_date(assertion.get("coverage_start"), "coverage start")
    end = _parse_date(assertion.get("coverage_end"), "coverage end")
    extracted = _parse_stamp(evidence.get("extracted_at"), "extracted_at")
    if end < start or extracted.astimezone(log_sale.BANGKOK).date() < end:
        raise AccessTradeImportError("browser coverage dates are inconsistent")
    if (
        assertion.get("date_basis") != DATE_BASIS
        or assertion.get("asserted_from") != "authenticated_browser_filter_not_csv"
        or assertion.get("status_filter") not in STATUS_FILTERS
        or assertion.get("campaign_filter") != "ALL"
        or assertion.get("currency") != "THB"
        or assertion.get("timezone") != "Asia/Bangkok"
    ):
        raise AccessTradeImportError("browser filter assertion vocabulary is invalid")
    asserted_count = assertion.get("asserted_conversion_count")
    asserted_reward = assertion.get("asserted_reward_thb")
    if (
        not isinstance(asserted_count, int) or isinstance(asserted_count, bool)
        or asserted_count < 0 or asserted_count != count
        or not isinstance(asserted_reward, str)
        or not MONEY_RE.fullmatch(asserted_reward)
    ):
        raise AccessTradeImportError("browser summary assertion is invalid")
    if require_complete and assertion["status_filter"] != "ALL":
        raise AccessTradeImportError("partial AccessTrade status filter cannot prove complete revenue")

    event_ids: set[str] = set()
    sale_ids: set[str] = set()
    identities: set[str] = set()
    for index, binding in enumerate(bindings, 1):
        if not isinstance(binding, dict) or set(binding) != BINDING_KEYS:
            raise AccessTradeImportError("upstream binding %d fields are invalid" % index)
        hashes = (
            binding.get("provider_identity_sha256"), binding.get("campaign_id_hash"),
            binding.get("source_row_sha256"),
        )
        if any(not isinstance(value, str) or not SHA256_RE.fullmatch(value) for value in hashes):
            raise AccessTradeImportError("upstream binding hashes are invalid")
        optional_ids = (
            binding.get("provider_conversion_id_hash"), binding.get("transaction_id_hash")
        )
        if all(value is None for value in optional_ids) or any(
            value is not None and (not isinstance(value, str) or not SHA256_RE.fullmatch(value))
            for value in optional_ids
        ):
            raise AccessTradeImportError("provider identity hashes are invalid")
        if binding.get("channel_source") != "atth":
            raise AccessTradeImportError("unattributed AccessTrade evidence must use source atth")
        try:
            canonical = log_sale.make_record(
                event_id=binding.get("event_id"), sale_id=binding.get("sale_id"),
                product="affiliate-commission", amount=binding.get("gross_amount_thb"),
                fee=binding.get("fee_thb"), status=binding.get("status"),
                source=binding.get("channel_source"), ref=binding.get("ref"), note="",
                date=binding.get("date"),
                now=dt.datetime.combine(
                    _parse_date(binding.get("date"), "binding date"),
                    dt.time(12), tzinfo=log_sale.BANGKOK,
                ),
            )
        except log_sale.IntakeError as exc:
            raise AccessTradeImportError("upstream ledger binding is invalid") from exc
        for key in (
            "event_id", "sale_id", "date", "status", "gross_amount_thb",
            "fee_thb", "net_amount_thb", "channel_source", "ref",
        ):
            if binding.get(key) != canonical.get(key):
                raise AccessTradeImportError("upstream ledger binding is non-canonical")
        if not start <= _parse_date(binding["date"], "binding date") <= end:
            raise AccessTradeImportError("upstream binding is outside asserted coverage")
        if assertion["status_filter"] != "ALL" and binding["status"] != STATUS_MAP[assertion["status_filter"]]:
            raise AccessTradeImportError("binding status contradicts browser status filter")
        if binding["event_id"] in event_ids or binding["sale_id"] in sale_ids or binding["provider_identity_sha256"] in identities:
            raise AccessTradeImportError("upstream evidence contains duplicate identities")
        event_ids.add(binding["event_id"])
        sale_ids.add(binding["sale_id"])
        identities.add(binding["provider_identity_sha256"])
    expected_reward = sum(
        (Decimal(str(binding["gross_amount_thb"])) for binding in bindings),
        Decimal("0.00"),
    )
    if Decimal(asserted_reward) != expected_reward:
        raise AccessTradeImportError("browser reward summary does not match bound CSV rows")
    return evidence


def _browser_money(value: object, label: str) -> Decimal:
    try:
        if isinstance(value, bool):
            raise ValueError
        amount = Decimal(str(value))
        if not amount.is_finite() or amount < 0:
            raise ValueError
        if amount != amount.quantize(Decimal("0.01")):
            raise ValueError
    except Exception as exc:
        raise AccessTradeImportError(label + " must be non-negative canonical THB") from exc
    return amount


def validate_browser_evidence(
    payload: object, receipt_evidence: dict[str, Any],
) -> dict[str, Any]:
    """Validate private browser proof against the receipt assertions and bindings."""
    if not isinstance(payload, dict) or set(payload) != BROWSER_EVIDENCE_KEYS:
        raise AccessTradeImportError("browser evidence envelope is invalid")
    if (
        not _exact_schema_version(
            payload.get("schema_version"), BROWSER_EVIDENCE_SCHEMA_VERSION
        )
        or payload.get("provider") != "AccessTrade"
        or payload.get("verification_mode") != VERIFICATION_MODE
        or payload.get("external_mutation") is not False
        or payload.get("financial_action") is not False
        or payload.get("report_url") != REPORT_URL
        or not isinstance(payload.get("note"), str)
    ):
        raise AccessTradeImportError("browser evidence safety contract is invalid")
    verified_at = _parse_stamp(payload.get("verified_at"), "browser verified_at")
    receipt_extracted = _parse_stamp(receipt_evidence.get("extracted_at"), "receipt extracted_at")
    if verified_at.astimezone(dt.timezone.utc) != receipt_extracted.astimezone(dt.timezone.utc):
        raise AccessTradeImportError("browser verified_at does not match receipt extraction time")

    filters = payload.get("filters")
    assertion = receipt_evidence["filter_assertion"]
    if not isinstance(filters, dict) or set(filters) != BROWSER_FILTER_KEYS:
        raise AccessTradeImportError("browser evidence filters are invalid")
    browser_status = filters.get("status")
    if (
        filters.get("period_start") != assertion["coverage_start"]
        or filters.get("period_end") != assertion["coverage_end"]
        or filters.get("date_basis") != assertion["date_basis"]
        or BROWSER_STATUS_TO_FILTER.get(browser_status) != assertion["status_filter"]
        or filters.get("campaign") != "all"
        or assertion.get("campaign_filter") != "ALL"
    ):
        raise AccessTradeImportError("browser evidence filters do not match receipt assertions")

    observed = payload.get("observed")
    if not isinstance(observed, dict) or set(observed) != BROWSER_OBSERVED_KEYS:
        raise AccessTradeImportError("browser evidence summary is invalid")
    count = observed.get("conversion_count")
    if (
        not isinstance(count, int) or isinstance(count, bool) or count < 0
        or count != assertion["asserted_conversion_count"]
        or count != receipt_evidence["raw_file_row_count"]
        or observed.get("currency") != "THB"
        or observed.get("sub_id_available") is not False
        or not isinstance(observed.get("campaign"), str)
        or not observed["campaign"].strip()
    ):
        raise AccessTradeImportError("browser evidence summary does not match receipt")
    if _browser_money(observed.get("total_reward_thb"), "browser reward") != Decimal(
        assertion["asserted_reward_thb"]
    ):
        raise AccessTradeImportError("browser reward does not match receipt assertion")
    bindings = receipt_evidence["bindings"]
    if (
        not isinstance(observed.get("provider_conversion_id_available"), bool)
        or not isinstance(observed.get("transaction_id_available"), bool)
    ):
        raise AccessTradeImportError("browser identifier availability flags are invalid")

    browser_bindings = payload.get("ledger_bindings")
    if not isinstance(browser_bindings, list) or len(browser_bindings) != len(bindings):
        raise AccessTradeImportError("browser ledger bindings do not match receipt")
    expected_by_event = {binding["event_id"]: binding for binding in bindings}
    seen: set[str] = set()
    for binding in browser_bindings:
        if not isinstance(binding, dict) or set(binding) != BROWSER_LEDGER_BINDING_KEYS:
            raise AccessTradeImportError("browser ledger binding fields are invalid")
        event_id = binding.get("event_id")
        expected = expected_by_event.get(event_id)
        if expected is None or event_id in seen:
            raise AccessTradeImportError("browser ledger binding identity is invalid")
        seen.add(event_id)
        if (
            binding.get("sale_id") != expected["sale_id"]
            or binding.get("status") != expected["status"]
            or _browser_money(binding.get("amount_thb"), "browser binding amount")
            != Decimal(str(expected["gross_amount_thb"]))
        ):
            raise AccessTradeImportError("browser ledger binding does not match receipt")
    return payload


def verify_receipt_sources(
    receipt: object,
    raw_csv_path: str | os.PathLike[str],
    browser_evidence_path: str | os.PathLike[str],
    *,
    require_complete: bool,
) -> dict[str, Any]:
    """Re-open and semantically verify both upstream artifacts for one receipt."""
    evidence = validate_receipt(receipt, require_complete=require_complete)
    raw_path = _private_input(raw_csv_path, "AccessTrade CSV")
    rows, raw_hash = _read_rows(
        raw_path,
        expected_raw_sha256=evidence["raw_file_sha256"],
        expected_row_count=evidence["raw_file_row_count"],
    )
    assertion = evidence["filter_assertion"]
    start = _parse_date(assertion["coverage_start"], "coverage start")
    end = _parse_date(assertion["coverage_end"], "coverage end")
    extracted = _parse_stamp(evidence["extracted_at"], "extracted_at")
    expected_by_identity = {
        binding["provider_identity_sha256"]: binding for binding in evidence["bindings"]
    }
    seen: set[str] = set()
    for row in rows:
        conversion_stamp = _parse_conversion_stamp(row[CONVERSION_AT])
        identity = canonical_sha256({
            "conversion_id_hash": _hash_identifier("conversion_id", row["Conversion ID"]),
            "transaction_id_hash": _hash_identifier("transaction_id", row["Transaction ID"]),
            "campaign_id_hash": _hash_identifier("campaign_id", row[CAMPAIGN_ID]),
            "conversion_at": conversion_stamp.isoformat(timespec="seconds"),
        })
        binding = expected_by_identity.get(identity)
        if binding is None or identity in seen:
            raise AccessTradeImportError("raw CSV identity does not match receipt binding")
        seen.add(identity)
        recomputed = _binding_for_row(
            row,
            sale_id=binding["sale_id"],
            event_id=binding["event_id"],
            channel_source=binding["channel_source"],
            ledger_ref=binding["ref"],
            fee=str(binding["fee_thb"]),
            coverage_start=start,
            coverage_end=end,
            extracted_at=extracted,
        )
        if recomputed != binding:
            raise AccessTradeImportError("raw CSV row does not match receipt binding")
    if seen != set(expected_by_identity):
        raise AccessTradeImportError("raw CSV does not exactly cover receipt bindings")

    browser_payload, browser_hash = _read_browser_evidence(
        browser_evidence_path,
        expected_sha256=evidence["browser_evidence_sha256"],
    )
    validate_browser_evidence(browser_payload, evidence)
    return {
        "raw_file_sha256": raw_hash,
        "browser_evidence_sha256": browser_hash,
        "raw_file_row_count": len(rows),
    }


def validate_embedded_evidence(
    bundles: object,
    events: list[dict],
    *,
    source_sha256: str,
    source_row_count: int,
    coverage_start: dt.date,
    coverage_end: dt.date,
    extracted_at: dt.datetime,
) -> dict[str, Any]:
    """Verify the raw-CSV receipt chain against every affiliate event."""
    if not isinstance(bundles, list) or not bundles:
        raise AccessTradeImportError("upstream AccessTrade evidence is missing")
    if not SHA256_RE.fullmatch(str(source_sha256 or "")):
        raise AccessTradeImportError("canonical source hash is invalid")
    if (
        not isinstance(source_row_count, int)
        or isinstance(source_row_count, bool)
        or source_row_count < 0
    ):
        raise AccessTradeImportError("canonical source row count is invalid")
    receipt_hashes: set[tuple[str, str]] = set()
    bindings: dict[str, dict] = {}
    current_binding_ids: set[str] = set()
    raw_hashes: list[str] = []
    browser_hashes: list[str] = []
    receipt_file_hashes: list[str] = []
    receipt_hash_values: list[str] = []
    provider_by_sale: dict[str, tuple[object, ...]] = {}
    sale_by_provider: dict[str, str] = {}
    for index, bundle in enumerate(bundles, 1):
        if not isinstance(bundle, dict) or set(bundle) != EMBEDDED_KEYS:
            raise AccessTradeImportError("embedded evidence %d fields are invalid" % index)
        receipt_file_hash = bundle.get("receipt_file_sha256")
        receipt_hash = bundle.get("receipt_sha256")
        if (
            not isinstance(receipt_file_hash, str)
            or not SHA256_RE.fullmatch(receipt_file_hash)
            or not isinstance(receipt_hash, str)
            or not SHA256_RE.fullmatch(receipt_hash)
            or receipt_hash != canonical_sha256(bundle.get("receipt"))
        ):
            raise AccessTradeImportError("embedded receipt hash is invalid")
        identity = (receipt_file_hash, receipt_hash)
        if identity in receipt_hashes:
            raise AccessTradeImportError("duplicate embedded receipt hash")
        receipt_hashes.add(identity)
        receipt_file_hashes.append(receipt_file_hash)
        receipt_hash_values.append(receipt_hash)
        if (
            bundle.get("canonical_source_sha256") != source_sha256
            or bundle.get("canonical_source_row_count") != source_row_count
        ):
            raise AccessTradeImportError("embedded evidence does not bind the canonical source")
        evidence = validate_receipt(bundle.get("receipt"), require_complete=True)
        assertion = evidence["filter_assertion"]
        evidence_start = _parse_date(assertion["coverage_start"], "evidence coverage start")
        evidence_end = _parse_date(assertion["coverage_end"], "evidence coverage end")
        if evidence_start < coverage_start or evidence_end > coverage_end:
            raise AccessTradeImportError("browser filter coverage escapes ledger coverage")
        is_current = evidence_start == coverage_start and evidence_end == coverage_end
        evidence_extracted = _parse_stamp(evidence["extracted_at"], "evidence extracted_at")
        if evidence_extracted.astimezone(dt.timezone.utc) > extracted_at.astimezone(dt.timezone.utc):
            raise AccessTradeImportError("upstream evidence was extracted after the canonical source")
        raw_hashes.append(evidence["raw_file_sha256"])
        browser_hashes.append(evidence["browser_evidence_sha256"])
        for binding in evidence["bindings"]:
            event_id = binding["event_id"]
            if event_id in bindings:
                raise AccessTradeImportError("one event is bound by multiple upstream receipts")
            bindings[event_id] = binding
            provider_key = (
                binding["provider_identity_sha256"],
                binding["provider_conversion_id_hash"],
                binding["transaction_id_hash"],
                binding["campaign_id_hash"],
            )
            sale_id = binding["sale_id"]
            if sale_id in provider_by_sale and provider_by_sale[sale_id] != provider_key:
                raise AccessTradeImportError(
                    "provider identity changed across lifecycle receipts"
                )
            prior_sale = sale_by_provider.get(binding["provider_identity_sha256"])
            if prior_sale is not None and prior_sale != sale_id:
                raise AccessTradeImportError(
                    "one provider identity is bound to multiple sales"
                )
            provider_by_sale[sale_id] = provider_key
            sale_by_provider[binding["provider_identity_sha256"]] = sale_id
            if is_current:
                current_binding_ids.add(event_id)

    affiliate_events = {
        row["event_id"]: row for row in events
        if row.get("product") == "affiliate-commission"
    }
    if set(bindings) != set(affiliate_events):
        raise AccessTradeImportError(
            "upstream bindings do not exactly cover canonical affiliate events"
        )
    latest_affiliate_ids = {
        row["event_id"] for row in log_sale.validate_event_sequence(events).values()
        if row.get("product") == "affiliate-commission"
    }
    if not latest_affiliate_ids.issubset(current_binding_ids):
        raise AccessTradeImportError(
            "latest affiliate states are not covered by a current browser export"
        )
    for event_id, row in affiliate_events.items():
        binding = bindings[event_id]
        for event_key, binding_key in (
            ("event_id", "event_id"), ("sale_id", "sale_id"),
            ("date", "date"), ("status", "status"),
            ("gross_amount_thb", "gross_amount_thb"),
            ("fee_thb", "fee_thb"), ("net_amount_thb", "net_amount_thb"),
            ("channel_source", "channel_source"), ("ref", "ref"),
        ):
            if row.get(event_key) != binding.get(binding_key):
                raise AccessTradeImportError(
                    "upstream binding does not match canonical event field " + event_key
                )
    return {
        "upstream_evidence_count": len(bundles),
        "upstream_raw_file_sha256": sorted(raw_hashes),
        "upstream_browser_evidence_sha256": sorted(browser_hashes),
        "upstream_receipt_file_sha256": sorted(receipt_file_hashes),
        "upstream_receipt_sha256": sorted(receipt_hash_values),
        "upstream_bound_event_rows": len(bindings),
        "attribution_state": ATTRIBUTION_STATE,
        "attribution_scope": ATTRIBUTION_SCOPE,
        "sub_id_available": False,
        "page_cta_attribution_ready": False,
    }


def import_csv(
    source: str | os.PathLike[str],
    output: str | os.PathLike[str],
    *,
    expected_raw_sha256: str,
    expected_row_count: int,
    browser_evidence_path: str | os.PathLike[str],
    browser_evidence_sha256: str,
    coverage_start: str,
    coverage_end: str,
    extracted_at: str,
    verification_mode: str,
    date_basis: str,
    status_filter: str,
    campaign_filter: str,
    asserted_conversion_count: int,
    asserted_reward_thb: str,
    sale_id: str | None = None,
    event_id: str | None = None,
    row_bindings: list[dict[str, str]] | None = None,
    ledger_ref: str = "",
    channel_source: str = "atth",
    fee: str = "0.00",
    replace: bool = False,
) -> dict[str, Any]:
    """Validate one exact export and atomically write one private receipt."""
    if verification_mode != VERIFICATION_MODE:
        raise AccessTradeImportError("verification mode must be authenticated browser read-only")
    if date_basis != DATE_BASIS:
        raise AccessTradeImportError("date basis must explicitly be conversion occurred time")
    if status_filter not in STATUS_FILTERS:
        raise AccessTradeImportError("status filter is not in the exact contract")
    if campaign_filter != "ALL":
        raise AccessTradeImportError("campaign filter must explicitly cover all campaigns")
    browser_hash = str(browser_evidence_sha256 or "").strip().lower()
    if not SHA256_RE.fullmatch(browser_hash):
        raise AccessTradeImportError("browser evidence SHA-256 is invalid")
    if (
        not isinstance(asserted_conversion_count, int)
        or isinstance(asserted_conversion_count, bool)
        or asserted_conversion_count < 0
        or not isinstance(asserted_reward_thb, str)
        or not MONEY_RE.fullmatch(asserted_reward_thb)
    ):
        raise AccessTradeImportError("browser summary assertion is invalid")
    start = _parse_date(coverage_start, "coverage start")
    end = _parse_date(coverage_end, "coverage end")
    extracted = _parse_stamp(extracted_at, "extracted_at")
    if end < start or extracted.astimezone(log_sale.BANGKOK).date() < end:
        raise AccessTradeImportError("browser coverage dates are inconsistent")
    source_path = _private_input(source, "AccessTrade CSV")
    browser_path = _private_input(browser_evidence_path, "browser evidence")
    output_path = _private_output(output)
    if source_path == output_path or browser_path == output_path or source_path == browser_path:
        raise AccessTradeImportError("CSV, browser evidence, and receipt paths must differ")
    rows, raw_hash = _read_rows(
        source_path,
        expected_raw_sha256=expected_raw_sha256,
        expected_row_count=expected_row_count,
    )
    bindings: list[dict[str, Any]] = []
    if row_bindings is not None:
        if any(value for value in (sale_id, event_id, ledger_ref)) or fee != "0.00":
            raise AccessTradeImportError(
                "row-binding specification cannot be mixed with legacy ledger arguments"
            )
        mapping = _row_binding_map(row_bindings, rows)
        for row in sorted(rows, key=_source_row_sha256):
            spec = mapping[_source_row_sha256(row)]
            binding = _binding_for_row(
                row,
                sale_id=spec["sale_id"],
                event_id=spec["event_id"],
                channel_source=channel_source,
                ledger_ref=spec["ledger_ref"],
                fee=spec["fee"],
                coverage_start=start,
                coverage_end=end,
                extracted_at=extracted,
            )
            if status_filter != "ALL" and binding["status"] != STATUS_MAP[status_filter]:
                raise AccessTradeImportError(
                    "row status contradicts authenticated status filter"
                )
            bindings.append(binding)
    elif len(rows) > 1:
        raise AccessTradeImportError(
            "multi-row export requires an exact hash-bound row-binding specification"
        )
    elif rows:
        if not all(isinstance(value, str) and value for value in (sale_id, event_id)):
            raise AccessTradeImportError("one-row export requires existing sale-id and event-id binding")
        if not isinstance(ledger_ref, str) or not LEDGER_REF_RE.fullmatch(ledger_ref):
            raise AccessTradeImportError(
                "ledger ref must be a provider-dashboard evidence reference, not page attribution"
            )
        binding = _binding_for_row(
            rows[0], sale_id=str(sale_id), event_id=str(event_id),
            channel_source=channel_source, ledger_ref=ledger_ref, fee=fee,
            coverage_start=start, coverage_end=end, extracted_at=extracted,
        )
        if status_filter != "ALL" and binding["status"] != STATUS_MAP[status_filter]:
            raise AccessTradeImportError("row status contradicts authenticated status filter")
        bindings.append(binding)
    elif any(value for value in (sale_id, event_id, ledger_ref)):
        raise AccessTradeImportError("empty export cannot carry a ledger row binding")
    if asserted_conversion_count != len(rows):
        raise AccessTradeImportError("browser conversion count does not match parsed CSV rows")
    csv_reward = sum((Decimal(row[REWARD]) for row in rows), Decimal("0.00"))
    if Decimal(asserted_reward_thb) != csv_reward:
        raise AccessTradeImportError("browser reward summary does not match parsed CSV rows")

    evidence = {
        "schema_version": RECEIPT_SCHEMA_VERSION,
        "provider": "accesstrade",
        "format": FORMAT_ID,
        "verification_mode": verification_mode,
        "raw_file_sha256": raw_hash,
        "browser_evidence_sha256": browser_hash,
        "raw_file_row_count": len(rows),
        "header_sha256": _header_sha256(),
        "filter_assertion": {
            "coverage_start": start.isoformat(),
            "coverage_end": end.isoformat(),
            "date_basis": date_basis,
            "status_filter": status_filter,
            "campaign_filter": campaign_filter,
            "asserted_conversion_count": asserted_conversion_count,
            "asserted_reward_thb": asserted_reward_thb,
            "currency": "THB",
            "timezone": "Asia/Bangkok",
            "asserted_from": "authenticated_browser_filter_not_csv",
        },
        "extracted_at": extracted.isoformat(timespec="seconds"),
        "importer_sha256": _importer_sha256(),
        "sub_id_available": False,
        "attribution_state": ATTRIBUTION_STATE,
        "bindings": bindings,
    }
    receipt = {
        "_meta": "private AccessTrade CSV evidence receipt",
        "evidence": evidence,
        "evidence_sha256": canonical_sha256(evidence),
    }
    validate_receipt(receipt, require_complete=False)
    verify_receipt_sources(
        receipt,
        source_path,
        browser_path,
        require_complete=False,
    )
    if output_path.exists() and not replace:
        raise AccessTradeImportError("receipt output exists; pass --replace after re-verifying evidence")
    descriptor, temp_name = tempfile.mkstemp(
        prefix=output_path.stem + "-candidate-", suffix=".json",
        dir=str(output_path.parent),
    )
    candidate = Path(temp_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
            json.dump(receipt, handle, ensure_ascii=False, sort_keys=True,
                      allow_nan=False, separators=(",", ":"))
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(candidate, output_path)
    except Exception:
        try:
            candidate.unlink()
        except FileNotFoundError:
            pass
        raise
    return {
        "trusted": True,
        "output": str(output_path),
        "receipt_sha256": file_sha256(output_path),
        "raw_file_sha256": raw_hash,
        "raw_file_row_count": len(rows),
        "evidence_sha256": receipt["evidence_sha256"],
        "status_filter": status_filter,
        "complete_status_coverage": status_filter == "ALL",
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", required=True)
    parser.add_argument("--output", required=True,
                        help="receipt path inside ignored private runtime")
    parser.add_argument("--expected-raw-sha256", required=True)
    parser.add_argument("--expected-row-count", required=True, type=int)
    parser.add_argument("--browser-evidence", required=True,
                        help="private schema-2 authenticated-browser evidence JSON")
    parser.add_argument("--browser-evidence-sha256", required=True)
    parser.add_argument("--coverage-start", required=True)
    parser.add_argument("--coverage-end", required=True)
    parser.add_argument("--extracted-at", required=True)
    parser.add_argument("--verification-mode", required=True,
                        choices=(VERIFICATION_MODE,))
    parser.add_argument("--date-basis", required=True, choices=(DATE_BASIS,))
    parser.add_argument("--status-filter", required=True, choices=STATUS_FILTERS)
    parser.add_argument("--campaign-filter", required=True, choices=("ALL",))
    parser.add_argument("--asserted-conversion-count", required=True, type=int)
    parser.add_argument("--asserted-reward-thb", required=True)
    parser.add_argument("--sale-id")
    parser.add_argument("--event-id")
    parser.add_argument("--row-bindings",
                        help="private exact row-binding specification JSON")
    parser.add_argument("--row-bindings-sha256")
    parser.add_argument("--ledger-ref", default="")
    parser.add_argument("--channel-source", default="atth", choices=("atth",))
    parser.add_argument("--fee", default="0.00")
    parser.add_argument("--replace", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _parser()
    args = parser.parse_args(argv)
    try:
        if bool(args.row_bindings) != bool(args.row_bindings_sha256):
            raise AccessTradeImportError(
                "row-binding path and SHA-256 must be provided together"
            )
        row_bindings = None
        if args.row_bindings:
            row_bindings = _read_row_binding_spec(
                args.row_bindings,
                expected_sha256=args.row_bindings_sha256,
                expected_raw_sha256=args.expected_raw_sha256,
            )
        result = import_csv(
            args.source, args.output,
            expected_raw_sha256=args.expected_raw_sha256,
            expected_row_count=args.expected_row_count,
            browser_evidence_path=args.browser_evidence,
            browser_evidence_sha256=args.browser_evidence_sha256,
            coverage_start=args.coverage_start,
            coverage_end=args.coverage_end,
            extracted_at=args.extracted_at,
            verification_mode=args.verification_mode,
            date_basis=args.date_basis,
            status_filter=args.status_filter,
            campaign_filter=args.campaign_filter,
            asserted_conversion_count=args.asserted_conversion_count,
            asserted_reward_thb=args.asserted_reward_thb,
            sale_id=args.sale_id,
            event_id=args.event_id,
            row_bindings=row_bindings,
            ledger_ref=args.ledger_ref,
            channel_source=args.channel_source,
            fee=args.fee,
            replace=args.replace,
        )
    except AccessTradeImportError as exc:
        parser.error("REFUSED: " + str(exc))
    except (OSError, UnicodeError):
        parser.error("REFUSED: private evidence import I/O failed")
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
