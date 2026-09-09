#!/usr/bin/env python3
"""Page2 AI-disclosure and official-source binding contract."""

import json
from pathlib import Path
import re

from content_source_gate import evaluate_content_source_claim


ROOT = Path(__file__).resolve().parents[1]
LIBRARY = ROOT / "automation-log" / "PAGE2-POSTS-B_20260818-0915.md"
REGISTRY = ROOT / "automation-log" / "knowledge-base" / "page2-source-registry.json"
SNAPSHOT = ROOT / "automation-log" / "knowledge-base" / "official-news-snapshot.json"
EXPECTED_IDS = {"p2-%02d" % value for value in range(9, 17)}


def table_rows():
    rows = {}
    for line in LIBRARY.read_text(encoding="utf-8").splitlines():
        match = re.match(r"^\|\s*\d{4}-\d{2}-\d{2}\s*\|\s*(p2-\d+)\s*\|", line)
        if match:
            rows[match.group(1)] = line
    return rows


def main():
    rows = table_rows()
    registry = json.loads(REGISTRY.read_text(encoding="utf-8"))
    assert set(rows) == EXPECTED_IDS
    assert set(registry["items"]) == EXPECTED_IDS
    assert registry["binding_state"] == "PROVISIONAL_REVIEW_REQUIRED"
    assert registry["last_human_review"] is None
    assert all("ผลิตด้วย AI" in rows[content_id] for content_id in EXPECTED_IDS)

    structural_failures = []
    manual_evidence_ids = {
        content_id for content_id, item in registry["items"].items()
        if item.get("manual_evidence_required")
    }
    observed_manual_blocks = set()
    for content_id, item in registry["items"].items():
        result = evaluate_content_source_claim(
            content_id,
            item["source_ids"],
            REGISTRY,
            SNAPSHOT,
            library_name=registry["library"],
        )
        assert set(result.source_ids) == set(item["source_ids"])
        assert any(
            "require explicit human review" in failure
            for failure in result.failures
        )
        assert any(
            "reviewed binding hash is missing or malformed" in failure
            for failure in result.failures
        )
        structural_failures.extend(
            failure for failure in result.failures
            if failure != "source registry reviewed binding hash is missing or malformed"
            if any(marker in failure for marker in (
                "not monitored", "no source ID mapping", "do not match official_urls",
                "must exactly equal", "missing or malformed", "different library",
            ))
        )
        if any("manual source evidence" in failure for failure in result.failures):
            observed_manual_blocks.add(content_id)
    assert not structural_failures, structural_failures
    assert observed_manual_blocks == manual_evidence_ids
    print("Page2 source contract: 8/8 bindings complete; AI disclosure 8/8; review remains fail-closed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
