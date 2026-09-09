#!/usr/bin/env python3
"""Regression tests for the read-only content manifest contract."""

from __future__ import annotations

import datetime as dt
import io
import json
import sys
import tempfile
from contextlib import redirect_stdout
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import manifest_contract as guard  # noqa: E402


TODAY = dt.date(2026, 8, 16)
PLATFORMS = ("tiktok", "ig", "fb", "youtube", "threads")
checks = 0


def check(name: str, condition: bool) -> None:
    global checks
    checks += 1
    print(("PASS " if condition else "FAIL ") + name)
    if not condition:
        raise AssertionError(name)


def blank_evidence() -> dict[str, None]:
    return {platform: None for platform in PLATFORMS}


def item(item_id: str, date: str, status: str, posted=None) -> dict:
    return {
        "id": item_id,
        "date": date,
        "status": status,
        "posted": blank_evidence() if posted is None else posted,
    }


def errors_for(items) -> list[str]:
    return guard.validate_document({"items": items}, TODAY)


def has_code(errors: list[str], code: str) -> bool:
    return any(error.startswith(code + ":") for error in errors)


def main() -> int:
    future = item("future-1", "2026-08-17", "Scheduled")
    check("future Scheduled row may await evidence", errors_for([future]) == [])

    backlog = item("backlog-1", "2026-01-01", "Backlog")
    check("past Backlog is not inferred to be a publication candidate", errors_for([backlog]) == [])

    legacy = item("legacy-unknown", "2026-01-02", "LegacyUnknown")
    check("LegacyUnknown remains reconciliation-only", errors_for([legacy]) == [])

    duplicate_id = [
        item("same-id", "2026-08-17", "Rendered"),
        item("same-id", "2026-08-18", "Rendered"),
    ]
    check("duplicate id fails", has_code(errors_for(duplicate_id), "DUPLICATE_ID"))

    duplicate_date = [
        item("one", "2026-08-17", "Rendered"),
        item("two", "2026-08-17", "Rendered"),
    ]
    check("duplicate date fails", has_code(errors_for(duplicate_date), "DUPLICATE_DATE"))

    posted_empty = item("posted-empty", "2026-08-15", "Posted")
    check(
        "global Posted without posted.* evidence fails",
        has_code(errors_for([posted_empty]), "POSTED_WITHOUT_EVIDENCE"),
    )

    posted_scheduled_only = item("posted-scheduled", "2026-08-15", "Posted")
    posted_scheduled_only["posted"]["youtube"] = "scheduled (yt-api abc)"
    check(
        "global Posted is not proven by schedule-only evidence",
        has_code(errors_for([posted_scheduled_only]), "POSTED_WITHOUT_EVIDENCE"),
    )

    posted_proven = item("posted-proven", "2026-08-15", "Posted")
    posted_proven["posted"]["youtube"] = "published (yt-api abc)"
    check("global Posted with publication evidence passes", errors_for([posted_proven]) == [])

    for bad_value in ("not posted", "failed: not published", "cancelled after posted", "unscheduled draft"):
        negative = item("negative-" + bad_value.split()[0], "2026-08-15", "Posted")
        negative["posted"]["youtube"] = bad_value
        check(
            f"negative evidence cannot prove Posted: {bad_value}",
            has_code(errors_for([negative]), "POSTED_WITHOUT_EVIDENCE"),
        )

    extra_key = item("extra-evidence-key", "2026-08-15", "Posted")
    extra_key["posted"]["audit_note"] = "published someday"
    check(
        "non-platform key is rejected and cannot prove publication",
        has_code(errors_for([extra_key]), "UNKNOWN_PLATFORM")
        and has_code(errors_for([extra_key]), "POSTED_WITHOUT_EVIDENCE"),
    )

    past_scheduled = item("past-scheduled", "2026-08-15", "Scheduled")
    check(
        "past Scheduled without scheduler/platform evidence fails",
        has_code(errors_for([past_scheduled]), "PAST_SCHEDULED_WITHOUT_EVIDENCE"),
    )

    past_proven = item("past-proven", "2026-08-15", "Scheduled")
    past_proven["posted"]["tiktok"] = "scheduled-ui 19:00 (owner-studio)"
    check("past Scheduled with scheduler evidence passes", errors_for([past_proven]) == [])

    same_day = item("same-day", TODAY.isoformat(), "Scheduled")
    check("same-day Scheduled row may await evidence", errors_for([same_day]) == [])

    for field in guard.REQUIRED_FIELDS:
        missing = item("missing-" + field, "2026-08-17", "Rendered")
        del missing[field]
        check(
            "missing required field fails: " + field,
            has_code(errors_for([missing]), "MISSING_FIELD"),
        )

    check(
        "non-object root fails closed",
        has_code(guard.validate_document([], TODAY), "ROOT_NOT_OBJECT"),
    )
    check(
        "missing items list fails closed",
        has_code(guard.validate_document({}, TODAY), "MISSING_ITEMS"),
    )
    check(
        "non-list items fails closed",
        has_code(guard.validate_document({"items": {}}, TODAY), "INVALID_ITEMS"),
    )
    check(
        "non-object item fails closed",
        has_code(guard.validate_document({"items": [None]}, TODAY), "ITEM_NOT_OBJECT"),
    )

    malformed_date = item("bad-date", "2026-02-30", "Rendered")
    check("impossible ISO date fails", has_code(errors_for([malformed_date]), "INVALID_DATE"))

    unknown_status = item("bad-status", "2026-08-17", "posting-soon")
    check("unknown status fails", has_code(errors_for([unknown_status]), "INVALID_STATUS"))

    malformed_posted = item("bad-posted", "2026-08-17", "Rendered")
    malformed_posted["posted"] = []
    check("non-object posted fails", has_code(errors_for([malformed_posted]), "INVALID_POSTED"))

    missing_platform = item("missing-platform", "2026-08-17", "Rendered")
    del missing_platform["posted"]["threads"]
    check("missing posted platform fails", has_code(errors_for([missing_platform]), "MISSING_PLATFORM"))

    invalid_evidence = item("bad-evidence", "2026-08-17", "Rendered")
    invalid_evidence["posted"]["fb"] = "  "
    check("blank evidence string fails", has_code(errors_for([invalid_evidence]), "INVALID_EVIDENCE"))

    with tempfile.TemporaryDirectory(prefix="manifest_contract_") as tmp:
        tmp_path = Path(tmp)
        malformed = tmp_path / "malformed.json"
        malformed.write_text("{not-json", encoding="utf-8")
        errors, count = guard.validate_path(malformed, TODAY)
        check("malformed JSON fails closed", count == 0 and has_code(errors, "MALFORMED_JSON"))

        missing = tmp_path / "missing.json"
        errors, count = guard.validate_path(missing, TODAY)
        check("missing manifest file fails closed", count == 0 and has_code(errors, "MISSING_FILE"))

        valid = tmp_path / "valid.json"
        valid.write_text(json.dumps({"items": [future]}), encoding="utf-8")
        output = io.StringIO()
        with redirect_stdout(output):
            exit_code = guard.main([str(valid), "--today", TODAY.isoformat()])
        check("CLI returns zero for a valid fixture", exit_code == 0 and "PASS" in output.getvalue())

        invalid = tmp_path / "invalid.json"
        invalid.write_text(json.dumps({"items": [posted_empty]}), encoding="utf-8")
        output = io.StringIO()
        with redirect_stdout(output):
            exit_code = guard.main([str(invalid), "--today", TODAY.isoformat()])
        check("CLI returns nonzero for an invalid fixture", exit_code == 1 and "FAIL" in output.getvalue())

    print(f"manifest contract: {checks} checks, 0 failed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
