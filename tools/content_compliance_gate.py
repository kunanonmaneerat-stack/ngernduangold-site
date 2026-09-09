#!/usr/bin/env python3
"""Reusable fail-closed compliance gate for calendar-backed content libraries."""

from __future__ import annotations

import argparse
from collections import defaultdict
import json
import math
from pathlib import Path
import re
import sys


ROOT = Path(__file__).resolve().parents[1]
PIPELINE = ROOT / "pipeline"
if str(PIPELINE) not in sys.path:
    sys.path.insert(0, str(PIPELINE))

import comply_gate  # noqa: E402


SECTION_HEADINGS = {
    "youtube_package": "## YouTube package",
    "social_caption": "## Social caption",
}
WEEKLY_REPLACEMENT_PACK = "WEEK-CONTENT-PACK_20260824-30.json"


def _reject_json_constant(token: str) -> None:
    raise ValueError("non-finite JSON constant: " + token)


def _reject_duplicate_json_keys(pairs: list[tuple[str, object]]) -> dict:
    value: dict[str, object] = {}
    for key, item in pairs:
        if key in value:
            raise ValueError("duplicate JSON key: " + key)
        value[key] = item
    return value


def _weekly_pack_rows(path: Path) -> dict[str, dict]:
    document = json.loads(
        path.read_text(encoding="utf-8"),
        parse_constant=_reject_json_constant,
        object_pairs_hook=_reject_duplicate_json_keys,
    )
    if (
        not isinstance(document, dict)
        or document.get("schema_version") != 1
        or document.get("state") != "DRAFT_ONLY"
        or document.get("calendar_action")
        != "REPLACEMENT_CANDIDATES_ONLY_DO_NOT_ADD_OR_REPLACE_AUTOMATICALLY"
    ):
        raise ValueError("weekly replacement pack contract is invalid")
    days = document.get("days")
    if not isinstance(days, list):
        raise ValueError("weekly replacement pack days are malformed")
    rows: dict[str, dict] = {}
    for day in days:
        if not isinstance(day, dict):
            raise ValueError("weekly replacement candidate is malformed")
        candidate_id = str(day.get("candidate_id") or "").strip()
        if not candidate_id or candidate_id in rows:
            raise ValueError("weekly replacement candidate identity is invalid")
        rows[candidate_id] = day
    return rows


def _safe_path(repo: Path, value: object) -> Path | None:
    if not isinstance(value, str) or not value.strip():
        return None
    candidate = (repo / value).resolve()
    try:
        candidate.relative_to(repo.resolve())
    except ValueError:
        return None
    return candidate


def _table_rows(path: Path) -> dict[str, dict[str, str]]:
    rows: dict[str, dict[str, str]] = {}
    header: list[str] | None = None
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        if not raw_line.lstrip().startswith("|"):
            continue
        cells = [cell.strip() for cell in raw_line.strip().strip("|").split("|")]
        lowered = [cell.casefold() for cell in cells]
        if "id" in lowered:
            header = lowered
            continue
        if header is None or len(cells) != len(header):
            continue
        if all(re.fullmatch(r"[-: ]+", cell or "-") for cell in cells):
            continue
        row = dict(zip(header, cells))
        content_id = row.get("id", "").strip()
        if content_id:
            if content_id in rows:
                raise ValueError("duplicate library content id: " + content_id)
            rows[content_id] = row
    return rows


def _section(path: Path, field: str) -> str:
    heading = SECTION_HEADINGS.get(field)
    if not heading:
        return ""
    text = path.read_text(encoding="utf-8")
    if heading not in text:
        return ""
    tail = text.split(heading, 1)[1]
    return tail.split("\n## ", 1)[0].strip()


def load_source_copy(placement: object, repo: Path = ROOT) -> tuple[str, str | None]:
    """Return the exact source copy referenced by one calendar placement."""
    if not isinstance(placement, dict):
        return "", "calendar placement is not an object"
    source = placement.get("source")
    if not isinstance(source, dict):
        return "", "placement source is missing"
    path = _safe_path(repo, source.get("file"))
    if path is None or not path.is_file():
        return "", "source file is missing or outside the repository"
    field = str(source.get("field") or "").strip().casefold()
    row_id = str(source.get("row_id") or "").strip()
    if not field or not row_id:
        return "", "source row_id/field is missing"
    try:
        if path.name == WEEKLY_REPLACEMENT_PACK:
            row = _weekly_pack_rows(path).get(row_id)
            text = row.get(field, "") if row else ""
        elif field in SECTION_HEADINGS:
            text = _section(path, field)
        else:
            row = _table_rows(path).get(row_id)
            text = row.get(field, "") if row else ""
    except (OSError, UnicodeError, ValueError) as exc:
        return "", "source library is unreadable: %s" % str(exc)
    text = re.sub(r"<br\s*/?>", "\n", text, flags=re.IGNORECASE).strip()
    if not text:
        return "", "referenced source copy is missing"
    return text, None


def evaluate_calendar_compliance_document(calendar: object, *, repo: Path = ROOT) -> dict:
    """Evaluate every distinct source copy in one in-memory calendar document."""
    placements = calendar.get("placements") if isinstance(calendar, dict) else None
    if not isinstance(placements, list):
        return {
            "state": "BLOCKED",
            "placements_scanned": 0,
            "source_copies_scanned": 0,
            "findings": [{"issues": ["calendar placements is malformed"]}],
            "warnings": [],
        }

    grouped: dict[tuple[str, str, str], list[dict]] = defaultdict(list)
    malformed: list[dict] = []
    for placement in placements:
        if not isinstance(placement, dict) or not isinstance(placement.get("source"), dict):
            malformed.append({
                "placement_ids": [str((placement or {}).get("placement_id") or "")]
                if isinstance(placement, dict) else [],
                "issues": ["placement source is missing or malformed"],
            })
            continue
        source = placement["source"]
        key = (
            str(source.get("file") or ""),
            str(source.get("row_id") or ""),
            str(source.get("field") or ""),
        )
        grouped[key].append(placement)

    findings = list(malformed)
    warnings = []
    for (source_file, row_id, field), copies in sorted(grouped.items()):
        text, error = load_source_copy(copies[0], repo=repo)
        placement_ids = [str(item.get("placement_id") or "") for item in copies]
        content_ids = sorted({str(item.get("content_id") or "") for item in copies})
        evidence = {
            "content_ids": content_ids,
            "placement_ids": placement_ids,
            "source": {"file": source_file, "row_id": row_id, "field": field},
        }
        if error:
            findings.append(dict(evidence, issues=[error]))
            continue
        ok, issues = comply_gate.check(text)
        blocking = [issue for issue in issues if not issue.startswith("WARN ")]
        advisory = [issue for issue in issues if issue.startswith("WARN ")]
        if not ok or blocking:
            findings.append(dict(evidence, issues=blocking or issues))
        if advisory:
            warnings.append(dict(evidence, issues=advisory))

    return {
        "state": "PASS" if not findings else "BLOCKED",
        "placements_scanned": len(placements),
        "source_copies_scanned": len(grouped),
        "findings": findings,
        "warnings": warnings,
    }


def evaluate_calendar_compliance(calendar_path: Path | str, *, repo: Path = ROOT) -> dict:
    """Load a calendar and evaluate every distinct referenced source copy."""
    def reject_constant(token: str) -> None:
        raise ValueError("non-finite JSON constant: " + token)

    def reject_duplicates(pairs: list[tuple[str, object]]) -> dict:
        value: dict[str, object] = {}
        for key, item in pairs:
            if key in value:
                raise ValueError("duplicate JSON key: " + key)
            value[key] = item
        return value

    def require_finite(item: object) -> None:
        if isinstance(item, float) and not math.isfinite(item):
            raise ValueError("non-finite JSON number")
        if isinstance(item, dict):
            for child in item.values():
                require_finite(child)
        elif isinstance(item, list):
            for child in item:
                require_finite(child)

    try:
        path = Path(calendar_path)
        if path.is_symlink():
            raise ValueError("calendar must not be a symlink")
        before = path.stat()
        raw = path.read_bytes()
        after = path.stat()
        if (
            before.st_size != after.st_size
            or before.st_mtime_ns != after.st_mtime_ns
            or len(raw) != after.st_size
        ):
            raise ValueError("calendar changed while being read")
        calendar = json.loads(
            raw.decode("utf-8"),
            parse_constant=reject_constant,
            object_pairs_hook=reject_duplicates,
        )
        require_finite(calendar)
    except Exception as exc:
        return {
            "state": "BLOCKED",
            "placements_scanned": 0,
            "source_copies_scanned": 0,
            "findings": [{"issues": ["calendar missing/unreadable: %s" % type(exc).__name__]}],
            "warnings": [],
        }
    return evaluate_calendar_compliance_document(calendar, repo=repo)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--calendar",
        default=str(ROOT / ".system_control" / "content_calendar.json"),
    )
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    result = evaluate_calendar_compliance(args.calendar)
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(
            "content compliance %s: %d placements, %d source copies, %d blockers, %d warnings"
            % (
                result["state"],
                result["placements_scanned"],
                result["source_copies_scanned"],
                len(result["findings"]),
                len(result["warnings"]),
            )
        )
        for finding in result["findings"]:
            print("BLOCKED %s: %s" % (
                ",".join(finding.get("placement_ids") or ["calendar"]),
                "; ".join(finding["issues"]),
            ))
    return 0 if result["state"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
