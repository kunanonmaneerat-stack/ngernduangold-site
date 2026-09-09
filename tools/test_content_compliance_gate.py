#!/usr/bin/env python3
"""Regression tests for calendar-wide reusable content compliance."""

import json
from pathlib import Path
import tempfile

from content_compliance_gate import evaluate_calendar_compliance


ROOT = Path(__file__).resolve().parents[1]


def check(name, condition):
    print(("PASS " if condition else "FAIL ") + name)
    if not condition:
        raise AssertionError(name)


def fixture(root: Path, copy: str):
    library = root / "library.md"
    library.write_text(
        "| date | id | fb_text |\n"
        "|---|---|---|\n"
        "| 2026-08-24 | item-1 | %s |\n" % copy,
        encoding="utf-8",
    )
    calendar = root / "calendar.json"
    calendar.write_text(json.dumps({"placements": [{
        "placement_id": "item-1__facebook_main",
        "content_id": "item-1",
        "source": {"file": "library.md", "row_id": "item-1", "field": "fb_text"},
    }]}), encoding="utf-8")
    return calendar


def main():
    with tempfile.TemporaryDirectory(prefix="content_compliance_") as raw:
        root = Path(raw)
        calendar = fixture(root, "เปรียบเทียบสินเชื่อก่อนตัดสินใจ")
        result = evaluate_calendar_compliance(calendar, repo=root)
        check(
            "lending library copy without the standard warning blocks",
            result["state"] == "BLOCKED"
            and result["findings"][0]["issues"] == ["missing Responsible Lending warning"],
        )

        calendar = fixture(
            root,
            "เปรียบเทียบสินเชื่อก่อนตัดสินใจ<br>กู้เท่าที่จำเป็นและชำระคืนไหว",
        )
        result = evaluate_calendar_compliance(calendar, repo=root)
        check("standard warning passes", result["state"] == "PASS")

        missing = json.loads(calendar.read_text(encoding="utf-8"))
        missing["placements"][0]["source"]["field"] = "missing_field"
        calendar.write_text(json.dumps(missing), encoding="utf-8")
        result = evaluate_calendar_compliance(calendar, repo=root)
        check("missing library field fails closed", result["state"] == "BLOCKED")

        for label, malformed in (
            ("duplicate calendar keys fail reusable compliance closed",
             '{"placements":[],"placements":[]}'),
            ("overflow calendar numbers fail reusable compliance closed",
             '{"placements":[],"probe":1e999}'),
        ):
            calendar.write_text(malformed, encoding="utf-8")
            result = evaluate_calendar_compliance(calendar, repo=root)
            check(label, result["state"] == "BLOCKED")

        pack_path = root / "WEEK-CONTENT-PACK_20260824-30.json"
        pack_path.write_text(json.dumps({
            "schema_version": 1,
            "state": "DRAFT_ONLY",
            "calendar_action": "REPLACEMENT_CANDIDATES_ONLY_DO_NOT_ADD_OR_REPLACE_AUTOMATICALLY",
            "days": [{
                "date": "2026-08-25",
                "candidate_id": "wk36-sf02",
                "threads_text": "Keep one exact evergreen decision pause.",
            }],
        }), encoding="utf-8")
        calendar.write_text(json.dumps({"placements": [{
            "placement_id": "wk36-sf02__threads_main",
            "content_id": "wk36-sf02",
            "source": {
                "file": pack_path.name,
                "row_id": "wk36-sf02",
                "field": "threads_text",
            },
        }]}), encoding="utf-8")
        result = evaluate_calendar_compliance(calendar, repo=root)
        check("exact weekly replacement JSON copy is compliance-scanned", result["state"] == "PASS")

        pack = json.loads(pack_path.read_text(encoding="utf-8"))
        pack["state"] = "READY"
        pack_path.write_text(json.dumps(pack), encoding="utf-8")
        result = evaluate_calendar_compliance(calendar, repo=root)
        check("weekly replacement pack state drift fails compliance closed", result["state"] == "BLOCKED")

    current = evaluate_calendar_compliance(
        ROOT / ".system_control" / "content_calendar.json", repo=ROOT
    )
    check(
        "all current calendar library copies pass reusable compliance",
        current["state"] == "PASS" and current["placements_scanned"] == 65,
    )
    print("content compliance gate: 8/8 PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
