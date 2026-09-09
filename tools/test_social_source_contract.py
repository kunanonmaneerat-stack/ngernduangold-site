#!/usr/bin/env python3
"""Exact source-binding contract for held Batch3/4 and TikTok content."""

from datetime import datetime
import json
from pathlib import Path

from content_source_gate import evaluate_content_source_claim


ROOT = Path(__file__).resolve().parents[1]
CALENDAR = ROOT / ".system_control" / "content_calendar.json"
REGISTRY = ROOT / "automation-log" / "knowledge-base" / "social-source-registry.json"
SNAPSHOT = ROOT / "automation-log" / "knowledge-base" / "official-news-snapshot.json"
LIBRARY_NAME = "SOCIAL-CONTENT-BINDINGS_20260823"
HISTORICAL_REGISTRY_IDS = {
    "b4-p01",
    "b3-01", "b3-02", "b3-03", "b3-04", "b3-05", "b3-06",
    "tt-r14-08", "tt-r14-09", "tt-r14-10", "tt-r14-11",
    "tt-r14-12", "tt-r14-13", "tt-r14-14",
}
CURRENT_FACTUAL_PLACEMENT_IDS = {
    "b4-p01",
    "b3-01", "b3-02", "b3-03", "b3-04", "b3-05", "b3-06",
}
TIKTOK_WEEK_REPLACEMENTS = {
    "tt-r14-08": "wk36-sf01",
    "tt-r14-09": "wk36-sf02",
    "tt-r14-10": "qt-12",
    "tt-r14-11": "wk36-sf03",
    "tt-r14-12": "wk36-sf04",
    "tt-r14-13": "qt-13",
    "tt-r14-14": "wk36-sf05",
}
TIKTOK_REPLACEMENT_RECEIPT = (
    "automation-log/TIKTOK-WEEK-REPLACEMENT-RECEIPT_20260824_R5.json"
)
TIKTOK_REPLACEMENT_BLOCKERS = {
    "publication_authority",
    "channel_review",
    "per_piece_owner_confirmation",
    "official_source_review",
    "live_tiktok_history_dedup",
    "live_landing_parity",
    "bio_route_parity",
    "human_listening_not_run",
}
MANUAL_EVIDENCE_IDS = {"b3-01", "b3-02", "b3-03", "b3-04", "b3-05"}


def main():
    calendar = json.loads(CALENDAR.read_text(encoding="utf-8"))
    registry = json.loads(REGISTRY.read_text(encoding="utf-8"))
    snapshot = json.loads(SNAPSHOT.read_text(encoding="utf-8"))
    checked_at = datetime.fromisoformat(
        str(snapshot["checked_at"]).replace("Z", "+00:00")
    )

    assert registry["library"] == LIBRARY_NAME
    assert registry["binding_state"] == "PROVISIONAL_REVIEW_REQUIRED"
    assert registry["last_human_review"] is None
    # Superseded creative briefs remain historical source evidence.  Replacing
    # their calendar reservations must never delete or rewrite those bindings.
    assert set(registry["items"]) == HISTORICAL_REGISTRY_IDS
    assert {
        content_id for content_id, item in registry["items"].items()
        if item.get("manual_evidence_required")
    } == MANUAL_EVIDENCE_IDS

    source_libraries = set(registry["source_libraries"])
    snapshot_map = {
        row["id"]: row["url"] for row in snapshot["sources"]
        if isinstance(row, dict) and row.get("id") and row.get("url")
    }
    structural_failures = []
    for content_id, item in registry["items"].items():
        source_file = item["source_file"]
        assert source_file in source_libraries
        source_text = (ROOT / source_file).read_text(encoding="utf-8")
        assert content_id in source_text
        assert len(item["source_ids"]) == len(set(item["source_ids"]))
        assert [snapshot_map[source_id] for source_id in item["source_ids"]] == item["official_urls"]

        result = evaluate_content_source_claim(
            content_id,
            item["source_ids"],
            REGISTRY,
            SNAPSHOT,
            library_name=LIBRARY_NAME,
            now=checked_at,
        )
        assert set(result.source_ids) == set(item["source_ids"])
        assert not result.allowed
        assert any("require explicit human review" in issue for issue in result.failures)
        assert any(
            "reviewed binding hash is missing or malformed" in issue
            for issue in result.failures
        )
        structural_failures.extend(
            issue for issue in result.failures
            if issue != "source registry reviewed binding hash is missing or malformed"
            if any(marker in issue for marker in (
                "not monitored", "no source ID mapping", "do not match official_urls",
                "must exactly equal", "missing or malformed", "different library",
            ))
        )
    assert not structural_failures, structural_failures

    factual_placements = [
        placement for placement in calendar["placements"]
        if placement.get("content_id") in CURRENT_FACTUAL_PLACEMENT_IDS
    ]
    assert len(factual_placements) == 11
    assert {
        placement["content_id"] for placement in factual_placements
    } == CURRENT_FACTUAL_PLACEMENT_IDS
    by_content = {}
    for placement in factual_placements:
        content_id = placement["content_id"]
        expected = registry["items"][content_id]["source_ids"]
        assert placement["source_ids"] == expected
        assert placement["status"] == "PLANNED_BLOCKED"
        assert placement["slot_state"] == "RESERVED_BLOCKED"
        assert placement["gates"]["source_review"] == "BLOCKED"
        assert placement["gates"]["publication_authority"] == "BLOCKED"
        assert "official_source_review" in placement["blockers"]
        by_content.setdefault(content_id, set()).add(tuple(placement["source_ids"]))
    assert all(len(source_sets) == 1 for source_sets in by_content.values())

    # The seven unproduced tt-r14 briefs were replaced one-for-one.  Restoring
    # them beside the replacements would duplicate the same seven TikTok dates.
    old_tiktok_ids = set(TIKTOK_WEEK_REPLACEMENTS)
    old_placement_ids = {
        f"{content_id}__tiktok_main" for content_id in old_tiktok_ids
    }
    assert not any(
        placement.get("content_id") in old_tiktok_ids
        or placement.get("placement_id") in old_placement_ids
        for placement in calendar["placements"]
    )

    replacement_spec = calendar["content_sets"]["tiktok_week_replacements"]
    assert replacement_spec["ids"] == list(TIKTOK_WEEK_REPLACEMENTS.values())
    assert replacement_spec["supersedes"] == TIKTOK_WEEK_REPLACEMENTS
    assert replacement_spec["selection_mode"] == "OWNER_AUTHORIZED_LOCAL_PLAN_REPLACEMENT"
    assert replacement_spec["reservation_only"] is True
    assert replacement_spec["change_receipt"] == TIKTOK_REPLACEMENT_RECEIPT

    replacement_ids = set(TIKTOK_WEEK_REPLACEMENTS.values())
    replacement_placements = [
        placement for placement in calendar["placements"]
        if placement.get("account") == "tiktok_main"
        and placement.get("content_id") in replacement_ids
    ]
    assert len(replacement_placements) == 7
    assert {
        placement["placement_id"] for placement in replacement_placements
    } == {f"{content_id}__tiktok_main" for content_id in replacement_ids}
    replacements_by_id = {
        placement["placement_id"]: placement
        for placement in replacement_placements
    }
    for old_id, replacement_id in TIKTOK_WEEK_REPLACEMENTS.items():
        placement_id = f"{replacement_id}__tiktok_main"
        placement = replacements_by_id[placement_id]
        assert placement["content_id"] == replacement_id
        assert placement["source_ids"] == []
        assert placement["source"]["row_id"] == replacement_id
        assert placement["source"]["field"] == "threads_text"
        assert placement["status"] == "PLANNED_BLOCKED"
        assert placement["slot_state"] == "RESERVED_BLOCKED"
        assert set(placement["blockers"]) == TIKTOK_REPLACEMENT_BLOCKERS
        assert placement["gates"] == {
            "publication_authority": "BLOCKED",
            "source_review": "BLOCKED",
            "media": "BLOCKED",
            "dedup": "REQUIRED",
            "page_identity": "PASS",
            "owner_confirmation": "BLOCKED",
            "live_history_dedup": "BLOCKED",
            "landing_parity": "BLOCKED",
        }
        assert placement["replacement_provenance"] == {
            "supersedes_placement_id": f"{old_id}__tiktok_main",
            "supersedes_content_id": old_id,
            "candidate_id": replacement_id,
            "change_receipt": TIKTOK_REPLACEMENT_RECEIPT,
        }

    print(
        "social source contract: 14/14 historical bindings, 11/11 factual "
        "placements, and 7/7 exact TikTok replacements; all remain "
        "review/authority blocked"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
