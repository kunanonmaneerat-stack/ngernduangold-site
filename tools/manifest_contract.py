#!/usr/bin/env python3
"""Read-only structural and evidence contract for content_manifest.json.

This guard deliberately does not decide whether Backlog, Idea, Draft, Approved,
or Rendered rows should be published.  Publication evidence rules apply only to
an explicit global ``Posted`` claim and to an explicit, past ``Scheduled`` row.

Exit codes:
  0 - manifest satisfies the contract
  1 - unreadable, malformed, or contract violations found
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import re
from pathlib import Path
from typing import Any, Sequence


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MANIFEST = ROOT / ".system_control" / "content_manifest.json"
REQUIRED_FIELDS = ("id", "date", "status", "posted")
PLATFORMS = ("tiktok", "ig", "fb", "youtube", "threads")
KNOWN_STATUSES = {
    "Backlog",
    "Idea",
    "Draft",
    "Approved",
    "Rendered",
    "Scheduled",
    "Posted",
    "LegacyUnknown",
}
NEGATIVE_EVIDENCE = re.compile(
    r"(?:\bnot\s+(?:posted|published|scheduled)\b|\bnever\s+(?:posted|published|scheduled)\b|"
    r"\b(?:failed|failure|cancelled|canceled|unscheduled)\b|ไม่(?:ได้)?(?:โพสต์|เผยแพร่|ตั้งเวลา))",
    re.IGNORECASE,
)
PUBLICATION_EVIDENCE = re.compile(
    r"^\s*(?:posted(?:-offset)?|published)(?:\b|\s|\()", re.IGNORECASE
)
SCHEDULER_EVIDENCE = re.compile(
    r"^\s*scheduled(?:-ui)?(?:\b|\s|\()", re.IGNORECASE
)


def bangkok_today() -> dt.date:
    return dt.datetime.now(dt.timezone(dt.timedelta(hours=7))).date()


def _valid_date(value: Any) -> dt.date | None:
    if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        return None
    try:
        parsed = dt.date.fromisoformat(value)
    except ValueError:
        return None
    return parsed if parsed.isoformat() == value else None


def evidence_kind(value: Any) -> str | None:
    """Classify explicit, positive platform evidence only.

    Substring matching is unsafe here: ``not posted`` and ``unscheduled`` are
    negative claims.  Evidence must start with the canonical action token.
    """
    if not isinstance(value, str) or not value.strip() or NEGATIVE_EVIDENCE.search(value):
        return None
    if PUBLICATION_EVIDENCE.search(value):
        return "posted"
    if SCHEDULER_EVIDENCE.search(value):
        return "scheduled"
    return None


def _has_evidence(posted: dict[str, Any], accepted: set[str]) -> bool:
    return any(evidence_kind(posted.get(platform)) in accepted for platform in PLATFORMS)


def validate_document(document: Any, today: dt.date | None = None) -> list[str]:
    """Return deterministic contract errors; an empty list means PASS."""
    checked_date = today or bangkok_today()
    errors: list[str] = []

    if not isinstance(document, dict):
        return ["ROOT_NOT_OBJECT: top level must be an object containing an items list"]
    if "items" not in document:
        return ["MISSING_ITEMS: top level is missing required field 'items'"]
    items = document.get("items")
    if not isinstance(items, list):
        return ["INVALID_ITEMS: top-level 'items' must be a list"]

    seen_ids: dict[str, int] = {}
    seen_dates: dict[str, int] = {}

    for index, item in enumerate(items):
        label = f"items[{index}]"
        if not isinstance(item, dict):
            errors.append(f"ITEM_NOT_OBJECT: {label} must be an object")
            continue

        for field in REQUIRED_FIELDS:
            if field not in item:
                errors.append(f"MISSING_FIELD: {label} is missing '{field}'")

        item_id = item.get("id")
        if not isinstance(item_id, str) or not item_id.strip() or item_id != item_id.strip():
            errors.append(f"INVALID_ID: {label}.id must be a non-empty trimmed string")
            normalized_id = None
        else:
            normalized_id = item_id
            if item_id in seen_ids:
                errors.append(
                    f"DUPLICATE_ID: {label}.id {item_id!r} duplicates items[{seen_ids[item_id]}]"
                )
            else:
                seen_ids[item_id] = index

        raw_date = item.get("date")
        item_date = _valid_date(raw_date)
        if item_date is None:
            errors.append(f"INVALID_DATE: {label}.date must be a real YYYY-MM-DD date")
        else:
            if raw_date in seen_dates:
                errors.append(
                    f"DUPLICATE_DATE: {label}.date {raw_date!r} duplicates items[{seen_dates[raw_date]}]"
                )
            else:
                seen_dates[raw_date] = index

        status = item.get("status")
        if not isinstance(status, str) or status not in KNOWN_STATUSES:
            errors.append(
                f"INVALID_STATUS: {label}.status must be one of {', '.join(sorted(KNOWN_STATUSES))}"
            )

        posted = item.get("posted")
        if not isinstance(posted, dict):
            errors.append(f"INVALID_POSTED: {label}.posted must be an object")
            continue

        for platform in PLATFORMS:
            if platform not in posted:
                errors.append(f"MISSING_PLATFORM: {label}.posted is missing '{platform}'")
                continue
            value = posted.get(platform)
            if value is not None and (not isinstance(value, str) or not value.strip()):
                errors.append(
                    f"INVALID_EVIDENCE: {label}.posted.{platform} must be null or a non-empty string"
                )

        for platform in sorted(set(posted) - set(PLATFORMS)):
            errors.append(
                f"UNKNOWN_PLATFORM: {label}.posted contains unsupported key '{platform}'"
            )

        evidence_label = normalized_id or label
        if status == "Posted" and not _has_evidence(posted, {"posted"}):
            errors.append(
                f"POSTED_WITHOUT_EVIDENCE: {evidence_label} claims Posted but posted.* "
                "contains no posted/published evidence"
            )
        if (
            status == "Scheduled"
            and item_date is not None
            and item_date < checked_date
            and not _has_evidence(posted, {"scheduled", "posted"})
        ):
            errors.append(
                f"PAST_SCHEDULED_WITHOUT_EVIDENCE: {evidence_label} is Scheduled for "
                f"{item_date.isoformat()} but posted.* contains no scheduler/platform evidence"
            )

    return errors


def validate_path(path: Path, today: dt.date | None = None) -> tuple[list[str], int]:
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return [f"MISSING_FILE: manifest not found: {path}"], 0
    except OSError as exc:
        return [f"READ_ERROR: cannot read manifest {path}: {exc}"], 0
    except json.JSONDecodeError as exc:
        return [f"MALFORMED_JSON: {path}:{exc.lineno}:{exc.colno}: {exc.msg}"], 0

    item_count = len(document.get("items", [])) if isinstance(document, dict) and isinstance(document.get("items"), list) else 0
    return validate_document(document, today), item_count


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate the read-only content manifest contract.")
    parser.add_argument("manifest", nargs="?", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--today", type=dt.date.fromisoformat, default=None)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    errors, item_count = validate_path(args.manifest, args.today)
    if errors:
        for error in errors:
            print("ERROR " + error)
        print(f"manifest contract: FAIL ({item_count} items, {len(errors)} error(s))")
        return 1
    print(f"manifest contract: PASS ({item_count} items, 0 errors)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
