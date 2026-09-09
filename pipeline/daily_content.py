"""Reserve one local draft or reference dispatcher's outstanding reservation.

The selection and reservation decision is one lock transaction. When
dispatcher already owns the date's batch, this wrapper writes only a
REFERENCE_DO_NOT_GENERATE_DUPLICATE artifact.
"""

from __future__ import annotations

import argparse
import datetime as _datetime
from pathlib import Path

try:
    import sys as _sys
    _sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    _sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

import dispatcher


ROOT = Path(__file__).resolve().parent.parent
ORDERS = str(ROOT / "automation-log" / "orders.txt")
INBOX = str(ROOT / "automation-log" / "cowork-inbox")


def topics() -> list[dict]:
    """Return active families; retained as a compatibility entrypoint."""
    return dispatcher.load_order_registry(ORDERS)[0]


def run():
    active, historical = dispatcher.load_order_registry(ORDERS)
    date = _datetime.date.today().isoformat()
    request_id = "daily:" + date
    ledger_path = dispatcher.ledger_path_for(INBOX)
    reconciled = dispatcher.reconcile_requests(ledger_path, INBOX)
    mode, rows = dispatcher.select_daily_order_atomic(
        active, historical, request_id=request_id, ledger_path=ledger_path
    )
    if mode in {
        "DISPATCHER_REFERENCE", "OUTSTANDING_REFERENCE",
        "REVIEW_REFRESHED_REFERENCE",
    }:
        state = "REFERENCE_DO_NOT_GENERATE_DUPLICATE"
        path = dispatcher.request_path("daily-reference", date, inbox=INBOX)
        dispatcher.write_reference(
            path,
            date=date,
            request_id=request_id,
            rows=rows,
            referenced_path=dispatcher._origin_request_path(rows, INBOX),
            title="DAILY LOCAL NOVELTY REFERENCE",
        )
    elif rows:
        state = "QUEUED_NOVEL"
        path = dispatcher.request_path(
            "daily-generation-request", date, inbox=INBOX
        )
        dispatcher.write_request(
            path,
            date=date,
            request_id=request_id,
            rows=rows,
            title="DAILY LOCAL NOVELTY-GATED GENERATION REQUEST",
        )
    elif mode == "ALREADY_TERMINAL_FOR_DATE":
        state = "NOVELTY_EXHAUSTED"
        path = dispatcher.request_path(
            "daily-generation-request", date, inbox=INBOX
        )
    else:
        state = "NOVELTY_EXHAUSTED"
        path = dispatcher.request_path("daily-status", date, inbox=INBOX)
        dispatcher.write_request(
            path,
            date=date,
            request_id=request_id,
            rows=[],
            title="DAILY LOCAL NOVELTY-GATED STATUS",
        )
    for recovered_path in dispatcher.reconcile_requests(ledger_path, INBOX):
        if recovered_path not in reconciled:
            reconciled.append(recovered_path)
    retirement = dispatcher.retire_request_inventory(ledger_path, INBOX)
    if state == "QUEUED_NOVEL":
        row = rows[0]
        print(
            "[daily_content] QUEUED_NOVEL " + row["family_id"] + ": "
            + row["topic"][:80]
        )
    elif state == "REFERENCE_DO_NOT_GENERATE_DUPLICATE":
        print(
            "[daily_content] REFERENCE_DO_NOT_GENERATE_DUPLICATE -> "
            + rows[0]["request_id"]
        )
    else:
        print(
            "[daily_content] NOVELTY_EXHAUSTED — do not generate and do not cycle"
        )
    print(
        "[daily_content] local request -> " + str(path)
        + " (no network LLM/paid API)"
    )
    return {
        "state": state,
        "request": str(path),
        "families": [row["family_id"] for row in rows],
        "ledger": str(ledger_path),
        "reconciled_requests": reconciled,
        "request_retirement": retirement,
    }


def main():
    """Compatibility entrypoint returning the local artifact path."""
    return run()["request"]


def cli_main() -> int:
    try:
        result = run()
    except dispatcher.NoveltyError as exc:
        print("[daily_content] BLOCKED_UNKNOWN: " + str(exc))
        return 20
    return 10 if result["state"] == "NOVELTY_EXHAUSTED" else 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--local-only", action="store_true",
        help="document the immutable local-only generation posture",
    )
    parser.parse_args()
    raise SystemExit(cli_main())
