#!/usr/bin/env python3
"""Report reconciled affiliate revenue for Monday through the selected day."""
from __future__ import annotations

import argparse
import datetime as dt
import math
from pathlib import Path
import re
import sys

HERE = Path(__file__).resolve().parent
PIPELINE = HERE.parent / "pipeline"
if str(PIPELINE) not in sys.path:
    sys.path.insert(0, str(PIPELINE))

from private_runtime import SALES_LOG_FILE
from log_sale import SOURCES
import revenue_ledger


BANGKOK = dt.timezone(dt.timedelta(hours=7))
LOG = str(SALES_LOG_FILE)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "date",
        nargs="?",
        help="week-to-date endpoint in YYYY-MM-DD (default Bangkok today)",
    )
    return parser


def _selected_date(value: str | None) -> dt.date:
    if value is None:
        return dt.datetime.now(BANGKOK).date()
    try:
        return dt.date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError("date must be YYYY-MM-DD") from exc


def _money(value: object) -> str:
    number = float(value)
    if not math.isfinite(number):
        raise ValueError("money is not finite")
    return f"{number:,.2f}"


def _count(value: object) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise ValueError("count is not a non-negative integer")
    return value


def main(argv: list[str] | None = None) -> int:
    parser = _parser()
    args = parser.parse_args(argv)
    try:
        end = _selected_date(args.date)
    except ValueError as exc:
        parser.error(str(exc))
    start = end - dt.timedelta(days=end.weekday())
    days = (end - start).days + 1
    result = revenue_ledger.read_affiliate_revenue(
        LOG,
        today=end,
        days=days,
    )
    if not isinstance(result, dict) or result.get("trusted") is not True:
        reason = str(
            result.get("error") if isinstance(result, dict)
            else "strict reader returned an invalid payload"
        )
        if not reason or reason == "None":
            reason = "strict revenue contract failed"
        reason = " ".join(reason.split())[:240]
        print(
            f"WEEK {start}..{end} — revenue=UNRECONCILED "
            f"(unavailable, not zero): {reason}"
        )
        return 2

    try:
        headline = (
            f"WEEK {start}..{end} — paid={_count(result['paid_transactions'])} "
            f"refunds={_count(result['refund_transactions'])} "
            f"net_revenue={_money(result['net_revenue_thb'])} THB"
        )
        pipeline = (
            "pipeline: "
            f"pending={_count(result['pending_transactions'])} "
            f"({_money(result['pending_amount_thb'])} THB), "
            f"approved={_count(result['approved_transactions'])} "
            f"({_money(result['approved_amount_thb'])} THB)"
        )
        lifecycle = result["lifecycle_counts"]
        by_source = result["by_source"]
        if not isinstance(lifecycle, dict) or not isinstance(by_source, dict):
            raise TypeError("breakdown is not an object")
        source_rows = _count(result["source_row_count"])
        event_rows = _count(result["ledger_event_rows"])
        transaction_rows = _count(result["ledger_transaction_rows"])
        source_hash = result["source_snapshot_sha256"]
        if (
            result.get("reconciliation_state") != "RECONCILED"
            or source_rows != event_rows
            or transaction_rows > event_rows
            or not isinstance(source_hash, str)
            or not re.fullmatch(r"[0-9a-f]{64}", source_hash)
        ):
            raise ValueError("reconciliation provenance is incomplete")
        if set(lifecycle) != revenue_ledger.ALLOWED_STATUS:
            raise ValueError("lifecycle vocabulary drift")
        if any(key not in SOURCES for key in by_source):
            raise ValueError("source vocabulary drift")
        lifecycle_line = {key: _count(lifecycle[key]) for key in sorted(lifecycle)}
        source_line = {key: _money(by_source[key]) for key in sorted(by_source)}
        provenance = (
            f"reconciled events={event_rows} transactions={transaction_rows} "
            f"source_sha256={source_hash[:12]}..."
        )
    except (KeyError, TypeError, ValueError, OverflowError):
        print(
            f"WEEK {start}..{end} — revenue=UNRECONCILED "
            "(unavailable, not zero): strict reader trusted payload is incomplete"
        )
        return 2
    print(headline)
    print(pipeline)
    print("lifecycle:", lifecycle_line)
    print("paid net by source:", source_line)
    print(provenance)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
