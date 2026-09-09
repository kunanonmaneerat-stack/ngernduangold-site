#!/usr/bin/env python3
"""Build the decision-grade revenue snapshot from one frozen local export.

Input is event-only JSONL using the raw-intake row contract.  The live
intake itself is rejected: copy/export it to a frozen file first and record its
SHA-256 plus event-row count independently at freeze time.  Only a fully
validated, hash-bound candidate is atomically installed as schema 5.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
import datetime as dt
from decimal import Decimal
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import tempfile
import time

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
PIPELINE = ROOT / "pipeline"
if str(PIPELINE) not in sys.path:
    sys.path.insert(0, str(PIPELINE))

import log_sale
import import_accesstrade_csv as accesstrade_csv
from private_runtime import SALES_INTAKE_FILE, SALES_LOG_FILE, ensure_private_parent
import revenue_ledger


BANGKOK = dt.timezone(dt.timedelta(hours=7))
SOURCE_SYSTEM_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{2,63}$")
BLOCKED_PRODUCTS = ["letter-kit-199"]


class ReconcileError(ValueError):
    """The frozen export cannot produce a trusted snapshot."""


def _private_reconciled_output(path: str | os.PathLike[str]) -> Path:
    """Resolve an output only inside the private runtime or its configured file."""
    try:
        selected = Path(path).expanduser().resolve()
        private_root = Path(accesstrade_csv.PRIVATE_ROOT).resolve()
        configured = Path(SALES_LOG_FILE).resolve()
    except (OSError, TypeError, ValueError) as exc:
        raise ReconcileError("reconciled output path is invalid") from exc
    if selected != configured:
        try:
            selected.relative_to(private_root)
        except ValueError as exc:
            raise ReconcileError(
                "reconciled output must remain inside the private runtime"
            ) from exc
    return selected


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _date(value: object, label: str) -> dt.date:
    try:
        return dt.date.fromisoformat(str(value))
    except (TypeError, ValueError) as exc:
        raise ReconcileError(label + " must be YYYY-MM-DD") from exc


def _stamp(value: object, label: str) -> dt.datetime:
    try:
        stamp = dt.datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError) as exc:
        raise ReconcileError(label + " must be ISO-8601") from exc
    if stamp.tzinfo is None:
        raise ReconcileError(label + " must include a timezone")
    return stamp


def _coverage_date(value: object, label: str) -> dt.date:
    if isinstance(value, dt.datetime):
        raise ReconcileError(label + " must be a date, not a timestamp")
    return value if isinstance(value, dt.date) else _date(value, label)


def _validate_money(row: dict, line_number: int) -> None:
    try:
        gross = log_sale._money(row.get("gross_amount_thb"), "gross_amount_thb")
        fee = log_sale._money(row.get("fee_thb"), "fee_thb")
        net = log_sale._money(row.get("net_amount_thb"), "net_amount_thb")
    except log_sale.IntakeError as exc:
        raise ReconcileError(
            "invalid money at source line %d: %s" % (line_number, exc)
        ) from exc
    if gross < 0 or fee < 0 or fee > gross:
        raise ReconcileError("invalid amount/fee at source line %d" % line_number)
    status = row["status"]
    if status in {"pending", "approved", "paid"}:
        expected = gross - fee
        if gross <= 0 or net != expected:
            raise ReconcileError("invalid %s money at source line %d" % (status, line_number))
    elif status == "refunded":
        expected = -(gross - fee)
        if gross <= 0 or net != expected:
            raise ReconcileError("invalid refunded money at source line %d" % line_number)
    elif status in {"rejected", "cancelled"}:
        if gross != 0 or fee != 0 or net != 0:
            raise ReconcileError("invalid %s money at source line %d" % (status, line_number))
    else:
        raise ReconcileError("invalid status at source line %d" % line_number)
    fixed = log_sale.PRODUCTS[row["product"]]
    if fixed is not None and status in log_sale.POSITIVE_STATUSES and gross != fixed:
        raise ReconcileError("fixed product price mismatch at source line %d" % line_number)


def _read_frozen_source(
    source: Path,
    *,
    coverage_start: dt.date,
    coverage_end: dt.date,
    extracted_at: dt.datetime,
) -> tuple[list[dict], str]:
    if not source.is_file():
        raise ReconcileError("frozen source export is missing")
    try:
        before = _sha256(source)
        payload = source.read_bytes()
        text = payload.decode("utf-8")
    except (OSError, UnicodeError) as exc:
        raise ReconcileError("frozen source export is unreadable UTF-8") from exc
    payload_hash = hashlib.sha256(payload).hexdigest()
    if before != payload_hash:
        raise ReconcileError("source export changed before it could be read consistently")
    if payload and not payload.endswith(b"\n"):
        raise ReconcileError("frozen source final row lacks newline commit boundary")
    rows: list[dict] = []
    for line_number, raw in enumerate(text.splitlines(), 1):
        if not raw.strip():
            raise ReconcileError("blank JSONL row at source line %d" % line_number)
        try:
            row = json.loads(raw)
        except (TypeError, ValueError) as exc:
            raise ReconcileError("invalid JSON at source line %d" % line_number) from exc
        if not isinstance(row, dict) or set(row) != log_sale.REQUIRED_FIELDS:
            raise ReconcileError("source line %d does not match the transaction contract" % line_number)
        sale_id = row.get("sale_id")
        if not isinstance(sale_id, str) or not log_sale.SALE_ID_RE.fullmatch(sale_id):
            raise ReconcileError("invalid sale_id at source line %d" % line_number)
        event_id = row.get("event_id")
        if not isinstance(event_id, str) or not log_sale.EVENT_ID_RE.fullmatch(event_id):
            raise ReconcileError("invalid event_id at source line %d" % line_number)
        if row.get("product") not in log_sale.PRODUCTS:
            raise ReconcileError("unknown product at source line %d" % line_number)
        if row.get("status") not in log_sale.STATUSES:
            raise ReconcileError("invalid status at source line %d" % line_number)
        if row.get("channel_source") not in log_sale.SOURCES:
            raise ReconcileError("unknown channel_source at source line %d" % line_number)
        if not isinstance(row.get("ref"), str) or not isinstance(row.get("note"), str):
            raise ReconcileError("ref/note must be strings at source line %d" % line_number)
        if log_sale._contains_pii(" ".join((event_id, sale_id, row["ref"], row["note"]))):
            raise ReconcileError("possible PII at source line %d" % line_number)
        transaction_date = _date(row.get("date"), "transaction date")
        if not coverage_start <= transaction_date <= coverage_end:
            raise ReconcileError("transaction outside declared coverage at source line %d" % line_number)
        transaction_stamp = _stamp(row.get("ts"), "transaction ts")
        if transaction_stamp.astimezone(dt.timezone.utc) > extracted_at.astimezone(dt.timezone.utc):
            raise ReconcileError("transaction ts is after the frozen export at source line %d" % line_number)
        if transaction_date > transaction_stamp.astimezone(BANGKOK).date():
            raise ReconcileError("transaction date is after ts at source line %d" % line_number)
        try:
            log_sale.validate_record(row, now=extracted_at)
        except log_sale.IntakeError as exc:
            raise ReconcileError(
                "non-canonical transaction at source line %d: %s"
                % (line_number, exc)
            ) from exc
        _validate_money(row, line_number)
        rows.append(row)
    try:
        log_sale.validate_event_sequence(rows, now=extracted_at)
    except log_sale.IntakeError as exc:
        raise ReconcileError("invalid lifecycle event sequence: %s" % exc) from exc
    try:
        after = _sha256(source)
    except OSError as exc:
        raise ReconcileError("frozen source export became unreadable") from exc
    if payload_hash != after:
        raise ReconcileError("source export changed while it was being read")
    return rows, payload_hash


def _metadata(
    *,
    source_system: str,
    coverage_start: dt.date,
    coverage_end: dt.date,
    extracted_at: dt.datetime,
    reconciled_at: dt.datetime,
    source_hash: str,
    source_row_count: int,
    upstream_evidence: list[dict],
) -> dict:
    products = {
        name: (None if price is None else float(price))
        for name, price in sorted(log_sale.PRODUCTS.items())
    }
    return {
        "_meta": "reconciled frozen local source export",
        "schema_version": revenue_ledger.SCHEMA_VERSION,
        "fields": sorted(revenue_ledger.REQUIRED_SALE_FIELDS),
        "products": products,
        "blocked_products": BLOCKED_PRODUCTS,
        "channel_source_values": sorted(log_sale.SOURCES),
        "created": extracted_at.date().isoformat(),
        "updated": reconciled_at.date().isoformat(),
        "source_system": source_system,
        "coverage_start": coverage_start.isoformat(),
        "coverage_end": coverage_end.isoformat(),
        "extracted_at": extracted_at.isoformat(timespec="seconds"),
        "reconciled_at": reconciled_at.isoformat(timespec="seconds"),
        "source_snapshot_sha256": source_hash,
        "source_row_count": source_row_count,
        "upstream_evidence": upstream_evidence,
        "complete": True,
    }


def _read_upstream_receipt(
    path: str | os.PathLike[str], expected_sha256: str
) -> tuple[dict, str]:
    try:
        selected = accesstrade_csv._private_input(
            path, "upstream AccessTrade evidence receipt"
        )
    except accesstrade_csv.AccessTradeImportError as exc:
        raise ReconcileError(str(exc)) from exc
    expected = str(expected_sha256 or "").strip().lower()
    if not re.fullmatch(r"[0-9a-f]{64}", expected):
        raise ReconcileError("expected upstream evidence SHA-256 is invalid")
    try:
        before = _sha256(selected)
        payload = selected.read_bytes()
        receipt = json.loads(payload.decode("utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ReconcileError("upstream AccessTrade evidence receipt is unreadable") from exc
    actual = hashlib.sha256(payload).hexdigest()
    try:
        after = _sha256(selected)
    except OSError as exc:
        raise ReconcileError("upstream AccessTrade evidence receipt became unreadable") from exc
    if before != actual or actual != expected or after != actual:
        raise ReconcileError("upstream AccessTrade evidence receipt hash does not match")
    try:
        accesstrade_csv.validate_receipt(receipt, require_complete=True)
    except accesstrade_csv.AccessTradeImportError as exc:
        raise ReconcileError("upstream AccessTrade evidence is invalid: " + str(exc)) from exc
    return receipt, actual


@contextmanager
def _output_lock(output: Path, timeout: float = 10.0):
    lock = output.with_name(output.name + ".reconcile.lock")
    deadline = time.monotonic() + timeout
    descriptor = None
    while descriptor is None:
        try:
            descriptor = os.open(str(lock), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        except FileExistsError:
            if time.monotonic() >= deadline:
                raise ReconcileError("reconciliation lock is busy")
            time.sleep(0.02)
    try:
        os.write(descriptor, (str(os.getpid()) + "\n").encode("ascii"))
        os.fsync(descriptor)
        yield
    finally:
        os.close(descriptor)
        try:
            lock.unlink()
        except FileNotFoundError:
            pass


def reconcile(
    source: str | os.PathLike[str],
    output: str | os.PathLike[str] = SALES_LOG_FILE,
    *,
    source_system: str,
    coverage_start: str | dt.date,
    coverage_end: str | dt.date,
    extracted_at: str | dt.datetime,
    expected_sha256: str,
    expected_row_count: int,
    upstream_evidence_path: str | os.PathLike[str] | list[str | os.PathLike[str]],
    expected_upstream_evidence_sha256: str | list[str],
    upstream_raw_csv_path: str | os.PathLike[str] | list[str | os.PathLike[str]],
    upstream_browser_evidence_path: str | os.PathLike[str] | list[str | os.PathLike[str]],
    replace: bool = False,
    now: dt.datetime | None = None,
) -> dict:
    """Validate, strict-read, then atomically install one schema-5 snapshot."""
    try:
        selected_source = accesstrade_csv._private_input(
            source, "frozen sales source"
        )
    except accesstrade_csv.AccessTradeImportError as exc:
        raise ReconcileError(str(exc)) from exc
    selected_output = _private_reconciled_output(output)
    if selected_source == Path(SALES_INTAKE_FILE).resolve():
        raise ReconcileError("live intake is mutable; copy/export it to a frozen file first")
    if selected_source == selected_output:
        raise ReconcileError("source and output must be different files")
    if selected_output == Path(SALES_INTAKE_FILE).resolve():
        raise ReconcileError("reconciled output must not overwrite raw intake")
    source_system = str(source_system or "").strip().lower()
    if not SOURCE_SYSTEM_RE.fullmatch(source_system):
        raise ReconcileError("source-system must be a safe 3-64 character identifier")
    expected_sha256 = str(expected_sha256 or "").strip().lower()
    if not re.fullmatch(r"[0-9a-f]{64}", expected_sha256):
        raise ReconcileError("expected-sha256 must be the checksum recorded when the export was frozen")
    if (
        not isinstance(expected_row_count, int)
        or isinstance(expected_row_count, bool)
        or expected_row_count < 0
    ):
        raise ReconcileError("expected-row-count must be a non-negative integer")
    start = _coverage_date(coverage_start, "coverage-start")
    end = _coverage_date(coverage_end, "coverage-end")
    if end < start:
        raise ReconcileError("coverage-end precedes coverage-start")
    extracted = extracted_at if isinstance(extracted_at, dt.datetime) else _stamp(extracted_at, "extracted-at")
    if extracted.tzinfo is None:
        raise ReconcileError("extracted-at must include a timezone")
    reconciled = now or dt.datetime.now(dt.timezone.utc)
    if reconciled.tzinfo is None:
        raise ReconcileError("now must include a timezone")
    reconciled = reconciled.astimezone(BANGKOK)
    if extracted.astimezone(dt.timezone.utc) > reconciled.astimezone(dt.timezone.utc):
        raise ReconcileError("extracted-at is after reconciliation time")
    if extracted.astimezone(BANGKOK).date() < end:
        raise ReconcileError("extracted-at predates coverage-end")
    if reconciled.astimezone(BANGKOK).date() < end:
        raise ReconcileError("coverage-end is not yet reconcilable")

    rows, source_hash = _read_frozen_source(
        selected_source,
        coverage_start=start,
        coverage_end=end,
        extracted_at=extracted,
    )
    if source_hash != expected_sha256:
        raise ReconcileError("frozen source checksum does not match the recorded checksum")
    if len(rows) != expected_row_count:
        raise ReconcileError("frozen source row count does not match the recorded row count")
    evidence_paths = (
        list(upstream_evidence_path)
        if isinstance(upstream_evidence_path, (list, tuple))
        else [upstream_evidence_path]
    )
    evidence_hashes = (
        list(expected_upstream_evidence_sha256)
        if isinstance(expected_upstream_evidence_sha256, (list, tuple))
        else [expected_upstream_evidence_sha256]
    )
    raw_paths = (
        list(upstream_raw_csv_path)
        if isinstance(upstream_raw_csv_path, (list, tuple))
        else [upstream_raw_csv_path]
    )
    browser_paths = (
        list(upstream_browser_evidence_path)
        if isinstance(upstream_browser_evidence_path, (list, tuple))
        else [upstream_browser_evidence_path]
    )
    if (
        not evidence_paths
        or len(evidence_paths) != len(evidence_hashes)
        or len(evidence_paths) != len(raw_paths)
        or len(evidence_paths) != len(browser_paths)
    ):
        raise ReconcileError(
            "upstream receipt, raw CSV, browser evidence, and hash lists must be non-empty and aligned"
        )
    try:
        evidence_paths = [
            accesstrade_csv._private_input(
                path, "upstream AccessTrade evidence receipt"
            )
            for path in evidence_paths
        ]
        raw_paths = [
            accesstrade_csv._private_input(path, "AccessTrade CSV")
            for path in raw_paths
        ]
        browser_paths = [
            accesstrade_csv._private_input(path, "browser evidence")
            for path in browser_paths
        ]
    except accesstrade_csv.AccessTradeImportError as exc:
        raise ReconcileError(str(exc)) from exc
    resolved_artifacts = [*evidence_paths, *raw_paths, *browser_paths]
    if len(resolved_artifacts) != len(set(resolved_artifacts)):
        raise ReconcileError("upstream artifact paths must be distinct and ordered one-to-one")
    if selected_source in resolved_artifacts or selected_output in resolved_artifacts:
        raise ReconcileError("upstream artifacts must differ from source and output")
    embedded_evidence = []
    receipt_hashes = []
    raw_hashes = []
    browser_hashes = []
    upstream_file_checks: list[tuple[Path, str]] = []
    for evidence_path, evidence_hash, raw_path, browser_path in zip(
        evidence_paths, evidence_hashes, raw_paths, browser_paths
    ):
        receipt, receipt_hash = _read_upstream_receipt(evidence_path, evidence_hash)
        try:
            source_proof = accesstrade_csv.verify_receipt_sources(
                receipt,
                raw_path,
                browser_path,
                require_complete=True,
            )
        except accesstrade_csv.AccessTradeImportError as exc:
            raise ReconcileError(
                "upstream AccessTrade source artifacts are invalid: " + str(exc)
            ) from exc
        receipt_hashes.append(receipt_hash)
        raw_hashes.append(source_proof["raw_file_sha256"])
        browser_hashes.append(source_proof["browser_evidence_sha256"])
        upstream_file_checks.extend((
            (Path(evidence_path).expanduser().resolve(), receipt_hash),
            (Path(raw_path).expanduser().resolve(), source_proof["raw_file_sha256"]),
            (
                Path(browser_path).expanduser().resolve(),
                source_proof["browser_evidence_sha256"],
            ),
        ))
        embedded_evidence.append({
            "receipt_file_sha256": receipt_hash,
            "receipt_sha256": accesstrade_csv.canonical_sha256(receipt),
            "receipt": receipt,
            "canonical_source_sha256": source_hash,
            "canonical_source_row_count": len(rows),
        })
    try:
        accesstrade_csv.validate_embedded_evidence(
            embedded_evidence,
            rows,
            source_sha256=source_hash,
            source_row_count=len(rows),
            coverage_start=start,
            coverage_end=end,
            extracted_at=extracted,
        )
    except accesstrade_csv.AccessTradeImportError as exc:
        raise ReconcileError("upstream evidence does not bind frozen source: " + str(exc)) from exc
    metadata = _metadata(
        source_system=source_system,
        coverage_start=start,
        coverage_end=end,
        extracted_at=extracted,
        reconciled_at=reconciled,
        source_hash=source_hash,
        source_row_count=len(rows),
        upstream_evidence=embedded_evidence,
    )
    selected_output = ensure_private_parent(selected_output)
    with _output_lock(selected_output):
        output_existed = selected_output.exists()
        if output_existed and not replace:
            raise ReconcileError("output exists; pass --replace after verifying the frozen export")
        descriptor, temp_name = tempfile.mkstemp(
            prefix=selected_output.stem + "-candidate-",
            suffix=".jsonl",
            dir=str(selected_output.parent),
        )
        candidate = Path(temp_name)
        rollback: Path | None = None
        installed = False
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
                for row in (metadata, *rows):
                    handle.write(json.dumps(
                        row, ensure_ascii=False, sort_keys=True, allow_nan=False,
                        separators=(",", ":"),
                    ) + "\n")
                handle.flush()
                os.fsync(handle.fileno())
            try:
                candidate_hash = _sha256(candidate)
            except OSError as exc:
                raise ReconcileError(
                    "candidate became unreadable after durable write"
                ) from exc
            days = (end - start).days + 1
            verification = revenue_ledger.read_affiliate_revenue(
                candidate, today=end, days=days
            )
            if verification.get("trusted") is not True:
                raise ReconcileError(
                    "strict reader rejected candidate: "
                    + str(verification.get("error") or "unknown contract error")
                )
            try:
                if _sha256(candidate) != candidate_hash:
                    raise ReconcileError(
                        "candidate changed during strict validation"
                    )
            except OSError as exc:
                raise ReconcileError(
                    "candidate became unreadable during strict validation"
                ) from exc
            expected_transactions = len(
                log_sale.validate_event_sequence(rows, now=extracted)
            )
            if (
                verification.get("source_snapshot_sha256") != source_hash
                or verification.get("source_row_count") != len(rows)
                or verification.get("ledger_event_rows") != len(rows)
                or verification.get("ledger_transaction_rows") != expected_transactions
            ):
                raise ReconcileError(
                    "strict reader provenance does not match the frozen source"
                )
            try:
                if _sha256(selected_source) != source_hash:
                    raise ReconcileError("source export changed before atomic install")
                if any(_sha256(path) != expected for path, expected in upstream_file_checks):
                    raise ReconcileError("upstream evidence changed before atomic install")
            except OSError as exc:
                raise ReconcileError(
                    "source or upstream evidence became unreadable before atomic install"
                ) from exc
            if output_existed:
                rollback_descriptor: int | None = None
                try:
                    before = _sha256(selected_output)
                    previous_payload = selected_output.read_bytes()
                    previous_hash = hashlib.sha256(previous_payload).hexdigest()
                    after = _sha256(selected_output)
                    if before != previous_hash or after != previous_hash:
                        raise ReconcileError(
                            "existing output changed before replacement"
                        )
                    rollback_descriptor, rollback_name = tempfile.mkstemp(
                        prefix=selected_output.stem + "-rollback-",
                        suffix=".jsonl",
                        dir=str(selected_output.parent),
                    )
                    rollback = Path(rollback_name)
                    with os.fdopen(rollback_descriptor, "wb") as handle:
                        rollback_descriptor = None
                        handle.write(previous_payload)
                        handle.flush()
                        os.fsync(handle.fileno())
                    if _sha256(rollback) != previous_hash:
                        raise ReconcileError(
                            "rollback snapshot hash does not match existing output"
                        )
                except OSError as exc:
                    if rollback_descriptor is not None:
                        os.close(rollback_descriptor)
                    raise ReconcileError(
                        "existing output could not be snapshotted safely"
                    ) from exc
            elif selected_output.exists():
                raise ReconcileError("output appeared before atomic install")
            try:
                if _sha256(candidate) != candidate_hash:
                    raise ReconcileError("candidate changed before atomic install")
            except OSError as exc:
                raise ReconcileError(
                    "candidate became unreadable before atomic install"
                ) from exc
            os.replace(candidate, selected_output)
            installed = True
            try:
                if _sha256(selected_output) != candidate_hash:
                    raise ReconcileError("installed output hash does not match candidate")
            except OSError as exc:
                raise ReconcileError(
                    "installed output became unreadable"
                ) from exc
            installed_verification = revenue_ledger.read_affiliate_revenue(
                selected_output, today=end, days=days
            )
            if installed_verification.get("trusted") is not True:
                raise ReconcileError(
                    "strict reader rejected installed output: "
                    + str(
                        installed_verification.get("error")
                        or "unknown contract error"
                    )
                )
            if (
                installed_verification.get("source_snapshot_sha256") != source_hash
                or installed_verification.get("source_row_count") != len(rows)
                or installed_verification.get("ledger_event_rows") != len(rows)
                or installed_verification.get("ledger_transaction_rows")
                != expected_transactions
            ):
                raise ReconcileError(
                    "installed output provenance does not match the frozen source"
                )
            try:
                if _sha256(selected_output) != candidate_hash:
                    raise ReconcileError(
                        "installed output changed during strict validation"
                    )
            except OSError as exc:
                raise ReconcileError(
                    "installed output became unreadable during strict validation"
                ) from exc
            if rollback is not None:
                rollback.unlink()
                rollback = None
        except Exception as exc:
            rollback_error: OSError | None = None
            if installed:
                try:
                    if rollback is not None and rollback.exists():
                        os.replace(rollback, selected_output)
                        rollback = None
                    else:
                        selected_output.unlink(missing_ok=True)
                except OSError as rollback_exc:
                    rollback_error = rollback_exc
            try:
                candidate.unlink()
            except FileNotFoundError:
                pass
            if rollback is not None:
                try:
                    rollback.unlink()
                except FileNotFoundError:
                    pass
            if rollback_error is not None:
                raise ReconcileError(
                    "installed output failed validation and rollback failed"
                ) from rollback_error
            raise
    return {
        "trusted": True,
        "schema_version": revenue_ledger.SCHEMA_VERSION,
        "output": str(selected_output),
        "source_snapshot_sha256": source_hash,
        "source_row_count": len(rows),
        "upstream_evidence_sha256": sorted(receipt_hashes),
        "upstream_raw_file_sha256": sorted(raw_hashes),
        "upstream_browser_evidence_sha256": sorted(browser_hashes),
        "coverage_start": start.isoformat(),
        "coverage_end": end.isoformat(),
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", required=True,
                        help="frozen lifecycle-event UTF-8 JSONL export")
    parser.add_argument("--output", default=str(SALES_LOG_FILE))
    parser.add_argument("--source-system", required=True)
    parser.add_argument("--coverage-start", required=True)
    parser.add_argument("--coverage-end", required=True)
    parser.add_argument("--extracted-at", required=True,
                        help="timezone-aware ISO timestamp from the frozen export")
    parser.add_argument("--expected-sha256", required=True,
                        help="checksum recorded when the source export was frozen")
    parser.add_argument("--expected-row-count", required=True, type=int,
                        help="event row count recorded when the export was frozen")
    parser.add_argument("--upstream-evidence", required=True, action="append",
                        help="private AccessTrade CSV evidence receipt")
    parser.add_argument("--expected-upstream-evidence-sha256", required=True, action="append",
                        help="receipt checksum recorded after private import")
    parser.add_argument("--upstream-raw-csv", required=True, action="append",
                        help="frozen raw AccessTrade CSV for the matching receipt")
    parser.add_argument("--upstream-browser-evidence", required=True, action="append",
                        help="private schema-2 browser evidence for the matching receipt")
    parser.add_argument("--replace", action="store_true",
                        help="atomically replace an existing reconciled snapshot")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _parser()
    args = parser.parse_args(argv)
    try:
        result = reconcile(
            args.source,
            args.output,
            source_system=args.source_system,
            coverage_start=args.coverage_start,
            coverage_end=args.coverage_end,
            extracted_at=args.extracted_at,
            expected_sha256=args.expected_sha256,
            expected_row_count=args.expected_row_count,
            upstream_evidence_path=args.upstream_evidence,
            expected_upstream_evidence_sha256=args.expected_upstream_evidence_sha256,
            upstream_raw_csv_path=args.upstream_raw_csv,
            upstream_browser_evidence_path=args.upstream_browser_evidence,
            replace=args.replace,
        )
    except ReconcileError as exc:
        parser.error("REFUSED: " + str(exc))
    except (OSError, UnicodeError):
        parser.error("REFUSED: private revenue reconciliation I/O failed")
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
