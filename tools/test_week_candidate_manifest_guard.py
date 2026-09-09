#!/usr/bin/env python3
from copy import deepcopy
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools import week_candidate_manifest_guard as guard


class WeekCandidateManifestGuardTests(unittest.TestCase):
    def test_current_manifest_is_exactly_bound(self):
        result = guard.evaluate()
        self.assertEqual("BLOCKED", result["verdict"], result["findings"])
        self.assertEqual("PASS", result["manifest_integrity_state"])
        self.assertEqual("PASS", result["technical_qa_state"])
        self.assertEqual("BLOCKED", result["final_media_guard_state"])
        self.assertEqual(11, result["checked_assets"])
        self.assertEqual(
            7,
            sum(
                item["state"] == "BLOCKED_HUMAN_AUDIO_REVIEW"
                for item in result["media_guard_results"]
            ),
        )
        self.assertTrue(result["publication_blockers"])
        self.assertFalse(result["publishable"])
        self.assertFalse(result["publication_authority_granted"])
        self.assertEqual(str(guard.MANIFEST.resolve()), result["manifest"])

    def test_stale_receipt_hash_fails_closed(self):
        manifest = guard._load(guard.MANIFEST)
        manifest = deepcopy(manifest)
        manifest["assets"][0]["receipt_sha256"] = "0" * 64
        result = guard.evaluate_document(manifest)
        self.assertEqual("FAIL", result["verdict"])
        self.assertTrue(any("receipt hash is stale" in item for item in result["findings"]))

    def test_incomplete_asset_coverage_fails_closed(self):
        manifest = guard._load(guard.MANIFEST)
        manifest = deepcopy(manifest)
        manifest["assets"].pop()
        result = guard.evaluate_document(manifest)
        self.assertEqual("FAIL", result["verdict"])
        self.assertTrue(any("coverage" in item for item in result["findings"]))


if __name__ == "__main__":
    unittest.main()
