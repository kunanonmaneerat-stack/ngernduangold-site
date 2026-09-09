#!/usr/bin/env python3
"""Fail-closed tests for the unresolved Facebook Story ledger line 39."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
AUTO = ROOT / "automation-log"
sys.path.insert(0, str(AUTO))

import post_ledger as ledger  # noqa: E402
import post_ledger_identity as identity  # noqa: E402


LEDGER = AUTO / "post-ledger.jsonl"
BINDINGS = AUTO / "post-ledger-identity-bindings.jsonl"
MANIFEST = ROOT / ".system_control" / "content_manifest.json"
JULY_LOG = AUTO / "2026-07.jsonl"
RECEIPT = (
    AUTO / "dedup-evidence" /
    "FACEBOOK-STORY-LINE39-RECOVERY-BLOCKER_20260824.json"
)
ARTIFACT_AUDIT = (
    AUTO / "dedup-evidence" /
    "FACEBOOK-STORY-LINE39-LOCAL-ARTIFACT-AUDIT_20260825.json"
)


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest().upper()


def physical_lines(path: Path) -> list[bytes]:
    raw = path.read_bytes()
    if not raw.endswith(b"\n"):
        raise AssertionError(f"{path} must end with a newline")
    return [line.rstrip(b"\r") for line in raw.split(b"\n")[:-1]]


class FacebookStory39RecoveryGuardTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.receipt = json.loads(RECEIPT.read_text(encoding="utf-8"))
        cls.ledger_lines = physical_lines(LEDGER)
        cls.rows = [json.loads(line.decode("utf-8")) for line in cls.ledger_lines]

    def test_receipt_is_hash_bound_to_the_exact_local_evidence(self):
        receipt = self.receipt
        target = receipt["target"]
        self.assertEqual("COMPLETED_BLOCKED", receipt["status"])
        self.assertEqual(39, target["ledger_line"])
        self.assertEqual(target["ledger_sha256"], sha256_file(LEDGER))
        self.assertEqual(
            target["ledger_row_sha256"],
            hashlib.sha256(self.ledger_lines[38]).hexdigest().upper(),
        )
        self.assertEqual("story", self.rows[38]["type"])
        self.assertEqual("facebook", self.rows[38]["channel"])
        self.assertEqual(target["ledger_timestamp"], self.rows[38]["ts"])
        self.assertEqual(
            tuple(receipt["required_recovery_evidence"]),
            identity.FACEBOOK_STORY_REQUIRED_RECOVERY_EVIDENCE,
        )

        manifest = json.loads(MANIFEST.read_text(encoding="utf-8-sig"))
        candidates = {
            item["candidate_id"]: item for item in receipt["candidate_evidence"]
        }
        manifest_candidates = {
            item["content_id"]: item
            for item in receipt["candidate_evidence"]
            if item["candidate_id"].startswith("manifest-reel-")
        }
        self.assertEqual(
            manifest_candidates["2026-07-17_eb02"]["source_sha256"],
            sha256_file(MANIFEST),
        )
        items = {item["id"]: item for item in manifest["items"]}
        for content_id, candidate in manifest_candidates.items():
            self.assertIn(content_id, items)
            self.assertEqual(
                candidate["facebook_schedule_evidence"],
                items[content_id]["posted"]["fb"],
            )
            self.assertEqual(
                candidate["media_sha256"],
                sha256_file(ROOT / candidate["media_path"]),
            )
            self.assertFalse(candidate["one_to_one_story_link"])

        log_candidate = candidates["operational-log-eb03-live-unverified"]
        july_lines = physical_lines(JULY_LOG)
        self.assertEqual(log_candidate["source_sha256"], sha256_file(JULY_LOG))
        self.assertEqual(
            log_candidate["source_row_sha256"],
            hashlib.sha256(july_lines[81]).hexdigest().upper(),
        )
        self.assertNotEqual(
            target["ledger_timestamp"],
            manifest_candidates["2026-07-19_eb03"]["scheduled_timestamp"],
        )

    def test_every_generic_identity_route_rejects_story_line_39(self):
        row = self.rows[38]
        generic_routes = (
            "content_manifest_item",
            "published_media_item",
            "knowledge_markdown_field",
            "markdown_table_text_hash",
            "knowledge_manual_descriptor_join",
            "privacy_sanitized_tool_input_commitment",
            "pantip_public_dom_observation",
            "facebook_group_public_dom_observation",
            "facebook_page_public_dom_and_link_observation",
            "markdown_line_range_text_hash",
            "line_broadcast_local_recovery",
            "content_manifest_hash_join",
            "future_generic_route",
        )
        for evidence_type in generic_routes:
            with self.subTest(evidence_type=evidence_type):
                with self.assertRaisesRegex(
                    identity.IdentityBindingError,
                    "dedicated one-to-one Story archive evidence",
                ):
                    identity._validate_binding_value(
                        row=row,
                        source={},
                        evidence_type=evidence_type,
                        identity={},
                        value={},
                        reuse_policy="PERMANENT_DEDUP",
                        source_raw=b"",
                        target_line=39,
                    )

    def test_no_false_recovery_was_applied(self):
        report = ledger.inspect_ledger(LEDGER)
        coverage = report["identity_coverage"]
        self.assertEqual("PASS", report["identity_binding_report"]["state"])
        self.assertEqual((124, 1), (
            coverage["complete_rows"], coverage["incomplete_rows"]
        ))
        self.assertEqual(
            [39], [item["line"] for item in coverage["legacy_incomplete"]]
        )
        self.assertEqual(
            self.receipt["result"]["identity_bindings_sha256_unchanged"],
            sha256_file(BINDINGS),
        )
        self.assertFalse(self.receipt["scope"]["identity_binding_appended"])
        self.assertFalse(self.receipt["scope"]["content_calendar_changed"])

    def test_local_artifact_audit_corroborates_route_but_not_identity(self):
        audit = json.loads(ARTIFACT_AUDIT.read_text(encoding="utf-8"))
        self.assertEqual("COMPLETED_BLOCKED", audit["status"])
        self.assertEqual(39, audit["target"]["ledger_line"])
        self.assertEqual(sha256_file(LEDGER), audit["target"]["ledger_sha256"])
        self.assertEqual(
            hashlib.sha256(self.ledger_lines[38]).hexdigest().upper(),
            audit["target"]["ledger_row_sha256"],
        )

        result = audit["result"]
        self.assertEqual("UNKNOWN_IDENTITY", result["state"])
        self.assertTrue(result["route_corroborated"])
        self.assertFalse(result["publication_success_verified"])
        self.assertFalse(result["stable_story_identity_verified"])
        self.assertFalse(result["source_reel_identity_verified"])
        self.assertEqual(sha256_file(BINDINGS), result["identity_bindings_sha256_unchanged"])
        self.assertEqual([39], result["remaining_incomplete_lines"])

        observed = audit["browser_history_observation"]["rows"]
        self.assertEqual([12836, 12839, 12840], [row["visit_id"] for row in observed])
        self.assertIn("story_composer", observed[1]["sanitized_url"])
        self.assertNotIn("/stories/", observed[1]["sanitized_url"])
        self.assertIn("[REDACTED]", observed[2]["sanitized_url"])

        required = set(audit["required_owner_collection"]["required_fields"])
        self.assertIn("stable Facebook Story object id", required)
        self.assertIn("canonical Story permalink or archive permalink", required)
        self.assertIn("displayed Story publication timestamp", required)
        self.assertFalse(audit["scope"]["identity_binding_appended"])
        self.assertFalse(audit["scope"]["content_calendar_changed"])


if __name__ == "__main__":
    raise SystemExit(unittest.main(verbosity=2))
