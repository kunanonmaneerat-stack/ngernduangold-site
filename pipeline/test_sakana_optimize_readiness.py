#!/usr/bin/env python3
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

import sakana_optimize as sakana


def readiness(*blockers):
    ready = not blockers
    return {
        "schema_version": 1,
        "status": "READY" if ready else "BLOCKED",
        "growth_ready": ready,
        "publication_ready": ready,
        "target_channel": "threads",
        "blockers": list(blockers),
        "checks": {},
    }


class SakanaReadinessTests(unittest.TestCase):
    def test_every_required_blocker_stops_before_key_csv_or_api(self):
        blockers = (
            "publication_authority_false",
            "content_calendar_publishable_zero",
            "content_calendar_guard_failed",
            "live_release_parity_failed",
            "revenue_ledger_unreconciled",
            "ga4_trust_or_bundle_failed",
            "gsc_bundle_failed",
            "content_scoped_source_enforcement_failed",
        )
        for blocker in blockers:
            with self.subTest(blocker=blocker):
                with (
                    mock.patch.object(
                        sakana.improvement_loop,
                        "collect_decision_readiness",
                        return_value=readiness(blocker),
                    ),
                    mock.patch.object(sakana, "get_key") as get_key,
                    mock.patch.object(sakana, "fugu") as fugu,
                    mock.patch.object(sakana.os.path, "exists") as exists,
                ):
                    result = sakana.main([])
                self.assertEqual(result, 2)
                get_key.assert_not_called()
                exists.assert_not_called()
                fugu.assert_not_called()

    def test_readiness_collection_error_fails_closed_before_api(self):
        with (
            mock.patch.object(
                sakana.improvement_loop,
                "collect_decision_readiness",
                side_effect=ValueError("bad evidence"),
            ),
            mock.patch.object(sakana, "fugu") as fugu,
        ):
            self.assertEqual(sakana.main([]), 2)
        fugu.assert_not_called()

    def test_ready_evidence_is_embedded_in_generated_draft(self):
        with tempfile.TemporaryDirectory() as tmp:
            pages = Path(tmp) / "ga4-pages.csv"
            output = Path(tmp) / "drafts.json"
            pages.write_text(
                "page,affiliate_click\n/credit-card-salary-30000,2\n",
                encoding="utf-8",
            )
            with (
                mock.patch.object(sakana, "PAGES", str(pages)),
                mock.patch.object(sakana, "OUT", str(output)),
                mock.patch.object(sakana, "get_key", return_value="test-key"),
                mock.patch.object(sakana.improvement_loop,
                                  "collect_decision_readiness",
                                  return_value=readiness()),
                mock.patch.object(sakana, "fugu",
                                  return_value='["draft one"]') as fugu,
                mock.patch.object(sakana.time, "sleep"),
            ):
                result = sakana.main(["--topn", "1", "--variants", "1"])
            self.assertEqual(result, 0)
            fugu.assert_called_once()
            payload = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(payload["decision_readiness"]["status"], "READY")
            self.assertEqual(payload["decision_readiness"]["target_channel"], "threads")
            self.assertEqual(len(payload["posts"]), 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
