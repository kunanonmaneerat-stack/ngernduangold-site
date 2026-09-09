#!/usr/bin/env python3
"""Ensure held quote cards preserve exact media/caption evidence and authority gates."""

import json
import hashlib
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CALENDAR = ROOT / ".system_control" / "content_calendar.json"
QUOTE_IDS = {"qt-12", "qt-13", "qt-14"}
BOUND_IDS = {"qt-12", "qt-13", "qt-14"}
PACK = "automation-log/WEEK-CONTENT-PACK_20260824-30.json"
EXACT_FIELDS = {
    "facebook_main": "facebook_text",
    "instagram_main": "threads_text",
    "pinterest_main": "threads_text",
}


def main():
    calendar = json.loads(CALENDAR.read_text(encoding="utf-8"))
    placements = [
        placement for placement in calendar["placements"]
        if placement.get("content_id") in QUOTE_IDS
        and placement.get("account") in EXACT_FIELDS
    ]
    assert len(placements) == 9
    assert {placement["content_id"] for placement in placements} == QUOTE_IDS
    for placement in placements:
        assert placement["status"] == "PLANNED_BLOCKED"
        assert placement["slot_state"] == "RESERVED_BLOCKED"
        assert placement["gates"]["publication_authority"] == "BLOCKED"
        assert placement["gates"]["dedup"] == "REQUIRED"
        assert "publication_authority" in placement["blockers"]
        if placement["content_id"] in BOUND_IDS:
            assert placement.get("media")
            assert placement.get("media_receipt")
            assert placement.get("media_content_id")
            assert placement["gates"]["media"] == "PASS"
            if placement["content_id"] in {"qt-12", "qt-13"}:
                assert placement["source"]["file"] == PACK
                assert placement["source"]["field"] == EXACT_FIELDS[placement["account"]]
            else:
                assert placement["source"]["file"] == "automation-log/QUOTE-CARDS_20260723-0822.md"
                assert placement["source"]["field"] == "caption"
                assert placement["media_binding_receipt"] == "automation-log/QT14-MEDIA-BINDING-RECEIPT_20260830.json"
            assert "caption_adaptation" not in placement["blockers"]
            assert "missing_media" not in placement["blockers"]
            assert "visual_qa" not in placement["blockers"]
    binding_path = ROOT / "automation-log/QT14-MEDIA-BINDING-RECEIPT_20260830.json"
    binding = json.loads(binding_path.read_text(encoding="utf-8"))
    canonical = lambda value: hashlib.sha256(
        json.dumps(
            value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
    ).hexdigest().upper()
    calendar_sha = hashlib.sha256(CALENDAR.read_bytes()).hexdigest().upper()
    assert binding["calendar"]["file_sha256"] == calendar_sha
    assert binding["calendar"]["canonical_sha256"] == canonical(calendar)
    by_id = {placement["placement_id"]: placement for placement in placements}
    for placement_id, evidence in binding["placement_bindings"].items():
        assert evidence["placement_canonical_sha256"] == canonical(by_id[placement_id])
        asset = binding["assets"][evidence["asset_key"]]
        asset_path = ROOT / asset["path"]
        receipt_path = ROOT / asset["qa_receipt"]
        assert hashlib.sha256(asset_path.read_bytes()).hexdigest().upper() == asset["sha256"]
        assert hashlib.sha256(receipt_path.read_bytes()).hexdigest().upper() == asset["qa_receipt_sha256"]
    print("quote readiness contract: all 9 placements are exact-media-bound and remain fail-closed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
