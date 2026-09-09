#!/usr/bin/env python3
"""Append a non-PII lifecycle event to the private *raw intake* ledger.

This command deliberately does not write the reconciled ``sales-log.jsonl``
consumed by business decisions. A frozen copy/export of this intake must pass
``reconcile_sales.py`` before the strict revenue reader can trust it.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
import datetime as dt
from decimal import Decimal, InvalidOperation
import ipaddress
import json
import os
from pathlib import Path
import re
import time

from private_runtime import SALES_INTAKE_FILE, ensure_private_parent


LOG = str(SALES_INTAKE_FILE)
BANGKOK = dt.timezone(dt.timedelta(hours=7))
PRODUCTS = {
    "ebook-59": Decimal("59.00"),
    "debt-toolkit-gumroad": Decimal("199.00"),
    "affiliate-commission": None,
}
SOURCES = {
    "line", "gumroad", "fb", "fb-page2", "threads", "ig", "yt",
    "pinterest", "pantip", "direct", "organic", "atth",
}
STATUSES = ("pending", "approved", "paid", "rejected", "refunded", "cancelled")
POSITIVE_STATUSES = {"pending", "approved", "paid", "refunded"}
ZERO_STATUSES = {"rejected", "cancelled"}
INITIAL_STATUSES = {"pending", "approved", "paid", "rejected", "cancelled"}
STATUS_TRANSITIONS = {
    "pending": {"approved", "paid", "refunded", "rejected", "cancelled"},
    "approved": {"paid", "refunded", "rejected", "cancelled"},
    "paid": {"refunded"},
    "refunded": set(),
    "rejected": set(),
    "cancelled": set(),
}
IMMUTABLE_SALE_FIELDS = ("date", "product", "channel_source", "ref")
REQUIRED_FIELDS = {
    "event_id", "sale_id", "date", "product", "status", "gross_amount_thb",
    "fee_thb", "net_amount_thb", "channel_source", "ref", "note", "ts",
}
SALE_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{2,79}$")
EVENT_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{2,95}$")
EMAIL_RE = re.compile(r"(?i)\b[^\s@]+@[^\s@]+\.[^\s@]+\b")
THAI_PHONE_RE = re.compile(r"(?<!\d)0\d{8,9}(?!\d)")
INTL_PHONE_RE = re.compile(r"(?<!\d)(?:\+?66|0066)[\s-]*\d(?:[\s-]*\d){7,9}(?!\d)")
CONTROL_RE = re.compile(r"[\x00-\x1f\x7f]")
MAX_REF_LENGTH = 160
MAX_NOTE_LENGTH = 500


class IntakeError(ValueError):
    """The raw intake cannot be safely appended or interpreted."""


def _money(value: object, label: str) -> Decimal:
    try:
        number = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise IntakeError(label + " must be numeric") from exc
    if not number.is_finite():
        raise IntakeError(label + " must be finite")
    try:
        if number != number.quantize(Decimal("0.01")):
            raise IntakeError(label + " must have at most two decimal places")
    except InvalidOperation as exc:
        raise IntakeError(label + " is outside the supported range") from exc
    return number


def _json_money(number: Decimal) -> int | float:
    integral = number.to_integral_value()
    return int(integral) if number == integral else float(number)


def _contains_pii(value: str) -> bool:
    compact = re.sub(r"[\s().-]", "", value)
    if (
        EMAIL_RE.search(value)
        or THAI_PHONE_RE.search(compact)
        or INTL_PHONE_RE.search(value)
    ):
        return True
    if re.search(r"(?<!\d)(?:\d{1,3}\.){3}\d{1,3}(?!\d)", value):
        return True
    for token in re.split(r"[\s,;()\[\]{}<>]+", value):
        candidate = token.strip("'\"./")
        try:
            ipaddress.ip_address(candidate)
        except ValueError:
            continue
        return True
    return False


def make_record(
    *,
    event_id: str,
    sale_id: str,
    product: str,
    amount: object,
    fee: object,
    status: str,
    source: str,
    ref: str = "",
    note: str = "",
    date: str | None = None,
    now: dt.datetime | None = None,
) -> dict:
    """Validate one raw event and return the canonical intake row."""
    current = now or dt.datetime.now(BANGKOK)
    if current.tzinfo is None:
        raise IntakeError("now must include a timezone")
    current = current.astimezone(BANGKOK)
    event_id = str(event_id or "").strip()
    sale_id = str(sale_id or "").strip()
    product = str(product or "").strip()
    status = str(status or "").strip().lower()
    source = str(source or "").strip().lower()
    ref = str(ref or "")
    note = str(note or "")
    if not EVENT_ID_RE.fullmatch(event_id):
        raise IntakeError("event-id must be 3-96 safe non-PII characters")
    if not SALE_ID_RE.fullmatch(sale_id):
        raise IntakeError("sale-id must be 3-80 safe non-PII characters")
    if product not in PRODUCTS:
        raise IntakeError("product is not in the intake contract")
    if status not in STATUSES:
        raise IntakeError("status must be an explicit lifecycle value")
    if source not in SOURCES:
        raise IntakeError("source is not in the intake contract")
    if len(ref) > MAX_REF_LENGTH or len(note) > MAX_NOTE_LENGTH:
        raise IntakeError("ref/note exceeds the private intake length limit")
    if CONTROL_RE.search(ref) or CONTROL_RE.search(note):
        raise IntakeError("ref/note must not contain control characters")
    if _contains_pii(" ".join((event_id, sale_id, ref, note))):
        raise IntakeError("event-id/sale-id/ref/note appears to contain phone, email, or IP data")

    try:
        event_date = dt.date.fromisoformat(date) if date else current.date()
    except (TypeError, ValueError) as exc:
        raise IntakeError("date must be YYYY-MM-DD") from exc
    if event_date > current.date():
        raise IntakeError("date must not be in the future")

    gross = _money(amount, "amount")
    transaction_fee = _money(fee, "fee")
    if gross < 0 or transaction_fee < 0 or transaction_fee > gross:
        raise IntakeError("amount/fee must be non-negative and fee cannot exceed amount")
    if status in POSITIVE_STATUSES and gross <= 0:
        raise IntakeError(status + " amount must be positive")
    if status in ZERO_STATUSES and (gross != 0 or transaction_fee != 0):
        raise IntakeError(status + " amount and fee must both be zero")
    expected = PRODUCTS[product]
    if expected is not None and status in POSITIVE_STATUSES and gross != expected:
        raise IntakeError("amount does not match the fixed product price")

    net = gross - transaction_fee
    if status == "refunded":
        net = -net
    elif status in ZERO_STATUSES:
        net = Decimal("0")
    return {
        "event_id": event_id,
        "sale_id": sale_id,
        "date": event_date.isoformat(),
        "product": product,
        "status": status,
        "gross_amount_thb": _json_money(gross),
        "fee_thb": _json_money(transaction_fee),
        "net_amount_thb": _json_money(net),
        "channel_source": source,
        "ref": ref,
        "note": note,
        "ts": current.isoformat(timespec="seconds"),
    }


def validate_record(
    record: object,
    *,
    now: dt.datetime | None = None,
) -> dict:
    """Require one fully canonical intake row, including lifecycle math."""
    if not isinstance(record, dict) or set(record) != REQUIRED_FIELDS:
        raise IntakeError("record does not match the raw intake contract")
    try:
        stamp = dt.datetime.fromisoformat(str(record.get("ts", "")).replace("Z", "+00:00"))
    except (TypeError, ValueError) as exc:
        raise IntakeError("ts must be ISO-8601") from exc
    if stamp.tzinfo is None:
        raise IntakeError("ts must include a timezone")
    current = now or dt.datetime.now(dt.timezone.utc)
    if current.tzinfo is None:
        raise IntakeError("validation time must include a timezone")
    if stamp.astimezone(dt.timezone.utc) > current.astimezone(dt.timezone.utc) + dt.timedelta(minutes=5):
        raise IntakeError("ts must not be in the future")
    canonical = make_record(
        event_id=record.get("event_id"),
        sale_id=record.get("sale_id"),
        product=record.get("product"),
        amount=record.get("gross_amount_thb"),
        fee=record.get("fee_thb"),
        status=record.get("status"),
        source=record.get("channel_source"),
        ref=record.get("ref"),
        note=record.get("note"),
        date=record.get("date"),
        now=stamp,
    )
    if canonical != record:
        raise IntakeError("record is not canonical or lifecycle money does not match")
    return canonical


def validate_event_sequence(
    records: list[dict],
    *,
    now: dt.datetime | None = None,
) -> dict[str, dict]:
    """Validate an append-only lifecycle and reduce it to one state per sale.

    Physical order is authoritative.  Event identifiers are globally unique,
    transition timestamps increase strictly for each sale, and identity/money
    fields cannot be rewritten by a later status event.
    """
    latest: dict[str, dict] = {}
    seen_events: dict[str, dict] = {}
    positive_money: dict[str, tuple[object, object]] = {}
    for index, raw in enumerate(records, 1):
        try:
            row = validate_record(raw, now=now)
        except IntakeError as exc:
            raise IntakeError("event row %d is invalid: %s" % (index, exc)) from exc
        event_id = row["event_id"]
        if event_id in seen_events:
            qualifier = "duplicate" if seen_events[event_id] == row else "conflicting"
            raise IntakeError("%s event_id at event row %d" % (qualifier, index))
        seen_events[event_id] = row

        sale_id = row["sale_id"]
        previous = latest.get(sale_id)
        if previous is None:
            if row["status"] not in INITIAL_STATUSES:
                raise IntakeError(
                    "sale_id %s cannot start at status %s"
                    % (sale_id, row["status"])
                )
        else:
            allowed = STATUS_TRANSITIONS[previous["status"]]
            if row["status"] not in allowed:
                raise IntakeError(
                    "invalid lifecycle transition for sale_id %s: %s -> %s"
                    % (sale_id, previous["status"], row["status"])
                )
            previous_stamp = dt.datetime.fromisoformat(previous["ts"])
            event_stamp = dt.datetime.fromisoformat(row["ts"])
            if event_stamp.astimezone(dt.timezone.utc) <= previous_stamp.astimezone(dt.timezone.utc):
                raise IntakeError(
                    "event timestamp must increase strictly for sale_id %s" % sale_id
                )
            for field in IMMUTABLE_SALE_FIELDS:
                if row[field] != previous[field]:
                    raise IntakeError(
                        "%s cannot change across events for sale_id %s"
                        % (field, sale_id)
                    )

        if row["status"] in POSITIVE_STATUSES:
            money = (row["gross_amount_thb"], row["fee_thb"])
            if sale_id in positive_money and money != positive_money[sale_id]:
                raise IntakeError(
                    "gross amount or fee cannot change across events for sale_id %s"
                    % sale_id
                )
            positive_money.setdefault(sale_id, money)
        latest[sale_id] = row
    return latest


def _lock_path(path: str | os.PathLike[str]) -> Path:
    selected = Path(path).resolve()
    return selected.with_name(selected.name + ".lock")


@contextmanager
def _exclusive_lock(path: str | os.PathLike[str], timeout: float = 10.0):
    lock = _lock_path(path)
    deadline = time.monotonic() + timeout
    descriptor = None
    while descriptor is None:
        try:
            descriptor = os.open(str(lock), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        except FileExistsError:
            if time.monotonic() >= deadline:
                raise IntakeError("intake lock is busy; no row was written")
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


def read_intake_events(path: str | os.PathLike[str] | None = None) -> list[dict]:
    """Read and lifecycle-validate intake; corruption blocks future appends."""
    selected = Path(path or LOG)
    if not selected.is_file():
        return []
    try:
        payload = selected.read_bytes()
        if payload and not payload.endswith(b"\n"):
            raise IntakeError("raw intake final row lacks newline commit boundary")
        lines = payload.decode("utf-8").splitlines()
    except (OSError, UnicodeError) as exc:
        raise IntakeError("raw intake is unreadable") from exc
    rows: list[dict] = []
    for line_number, raw in enumerate(lines, 1):
        if not raw.strip():
            raise IntakeError("raw intake has a blank JSONL row at line %d" % line_number)
        try:
            row = json.loads(raw)
        except (TypeError, ValueError) as exc:
            raise IntakeError("raw intake has invalid JSON at line %d" % line_number) from exc
        rows.append(row)
    try:
        validate_event_sequence(rows)
    except IntakeError as exc:
        raise IntakeError("raw intake lifecycle is invalid: %s" % exc) from exc
    return rows


def existing_sale_ids(path: str | os.PathLike[str] | None = None) -> set[str]:
    """Return transaction identifiers after strict event-ledger validation."""
    return {row["sale_id"] for row in read_intake_events(path)}


def _same_idempotent_payload(left: dict, right: dict) -> bool:
    """Compare caller-controlled event content; ``ts`` is assigned locally."""
    return all(left[key] == right[key] for key in REQUIRED_FIELDS - {"ts"})


def append_record(
    record: dict,
    path: str | os.PathLike[str] | None = None,
    *,
    lock_timeout: float = 10.0,
) -> Path:
    """Append one durable event, or no-op an identical idempotent retry."""
    record = validate_record(record)
    selected = ensure_private_parent(path or LOG)
    encoded = json.dumps(
        record, ensure_ascii=False, sort_keys=True, allow_nan=False,
        separators=(",", ":"),
    ) + "\n"
    with _exclusive_lock(selected, timeout=lock_timeout):
        existing = read_intake_events(selected)
        for prior in existing:
            if prior["event_id"] != record["event_id"]:
                continue
            if _same_idempotent_payload(prior, record):
                return selected
            raise IntakeError("event-id already exists with different content; raw intake was not changed")
        validate_event_sequence([*existing, record])
        with selected.open("a", encoding="utf-8", newline="\n") as handle:
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())
    return selected


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--event-id", required=True,
                        help="unique non-PII idempotency key for this lifecycle event")
    parser.add_argument("--sale-id", required=True,
                        help="unique non-PII transaction reference")
    parser.add_argument("--product", required=True, choices=sorted(PRODUCTS))
    parser.add_argument("--amount", required=True)
    parser.add_argument("--fee", default="0")
    parser.add_argument("--status", required=True, choices=STATUSES,
                        help="explicit source lifecycle; there is no paid default")
    parser.add_argument("--source", required=True, choices=sorted(SOURCES))
    parser.add_argument("--ref", default="")
    parser.add_argument("--note", default="")
    parser.add_argument("--date", default=None, help="YYYY-MM-DD (default Bangkok today)")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _parser()
    args = parser.parse_args(argv)
    try:
        record = make_record(
            event_id=args.event_id,
            sale_id=args.sale_id,
            product=args.product,
            amount=args.amount,
            fee=args.fee,
            status=args.status,
            source=args.source,
            ref=args.ref,
            note=args.note,
            date=args.date,
        )
        append_record(record)
    except (IntakeError, OSError, UnicodeError) as exc:
        parser.error("REFUSED: " + str(exc))
    print(
        "intake logged (UNRECONCILED): event_id=%s sale_id=%s product=%s status=%s source=%s"
        % (record["event_id"], record["sale_id"], record["product"],
           record["status"], record["channel_source"])
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
