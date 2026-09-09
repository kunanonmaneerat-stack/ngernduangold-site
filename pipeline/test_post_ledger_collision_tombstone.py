#!/usr/bin/env python3
"""Adversarial tests for historical canonical-collision tombstones."""

from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
AUTO = ROOT / "automation-log"
sys.path.insert(0, str(AUTO))
import post_ledger as ledger  # noqa: E402
import post_ledger_collision as collision  # noqa: E402


LEDGER = AUTO / "post-ledger.jsonl"
TOMBSTONE = AUTO / "post-ledger-collision-tombstones.json"
RECEIPT = (
    AUTO / "dedup-evidence" /
    "POST-LEDGER-TEXT-COLLISION-TOMBSTONES_20260824.json"
)


def snapshot(path: Path):
    physical = path.read_bytes().split(b"\n")[:-1]
    return (
        [json.loads(line.decode("utf-8")) for line in physical],
        {number: hashlib.sha256(line).hexdigest().upper()
         for number, line in enumerate(physical, 1)},
    )


def reseal(payload: dict) -> None:
    payload["self_sha256"] = collision.payload_sha256(payload)


class CollisionTombstoneTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="collision-tombstone-")
        self.root = Path(self.temp.name)
        self.ledger = LEDGER
        self.tombstone = self.root / TOMBSTONE.name
        shutil.copyfile(TOMBSTONE, self.tombstone)

    def tearDown(self):
        self.temp.cleanup()

    def load(self):
        rows, hashes = snapshot(self.ledger)
        # The production reader proves that every tombstone binds the complete
        # current collision occurrence set.  Exercise that same contract here;
        # omitting the groups only tests the validator's intentional fail-closed
        # response to incomplete caller evidence.
        binding_report = ledger.inspect_ledger(self.ledger)
        bindings = binding_report["identity_bindings"]
        collision_groups = ledger._permanent_identity_collisions(rows, bindings)
        return collision.load_collision_tombstones(
            ledger_path=self.ledger, rows=rows, row_sha256=hashes,
            bindings=bindings,
            collision_groups=collision_groups,
            tombstone_path=self.tombstone,
        )

    def save(self, payload):
        self.tombstone.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

    def test_01_production_tombstone_is_hash_bound_and_unknown_delivery(self):
        identities, report = self.load()
        self.assertEqual("PASS", report["state"])
        self.assertEqual({
            ("clip", "tiktok", "titleloan"),
            (
                "text_hash", "ig",
                "aed0406157eb7257c3bf86c7906a6822f8b86e79",
            ),
            (
                "text_hash", "yt",
                "90e43a4ddc4d3da3f72e17d10fd38f153e0741bc",
            ),
        }, identities)
        payload = json.loads(self.tombstone.read_text(encoding="utf-8"))
        self.assertTrue(all(
            item["external_delivery_resolution"] == "UNKNOWN_NO_INFERENCE"
            for item in payload["tombstones"]
        ))
        self.assertEqual([1, 19], [
            item["line"] for item in payload["tombstones"][0]["occurrences"]
        ])
        self.assertEqual([63, 89], [
            item["line"] for item in payload["tombstones"][1]["occurrences"]
        ])
        self.assertEqual(
            [31, 47, 55, 62, 70, 78, 87, 94, 103, 113, 120, 129, 137, 155],
            [item["line"] for item in payload["tombstones"][2]["occurrences"]],
        )

    def test_02_payload_tampering_is_rejected(self):
        payload = json.loads(self.tombstone.read_text(encoding="utf-8"))
        payload["tombstones"][0]["identity"] = "save"
        self.save(payload)
        identities, report = self.load()
        self.assertEqual(set(), identities)
        self.assertEqual("INVALID", report["state"])

    def test_03_delivery_resolution_cannot_be_inferred_even_after_reseal(self):
        payload = json.loads(self.tombstone.read_text(encoding="utf-8"))
        payload["tombstones"][0]["external_delivery_resolution"] = "LINE_19_DELIVERED"
        reseal(payload)
        self.save(payload)
        identities, report = self.load()
        self.assertEqual(set(), identities)
        self.assertEqual("INVALID", report["state"])
        self.assertIn("remain unknown", report["errors"][0])

    def test_04_occurrence_row_hash_mismatch_is_rejected_after_reseal(self):
        payload = json.loads(self.tombstone.read_text(encoding="utf-8"))
        payload["tombstones"][0]["occurrences"][0]["row_sha256"] = "A" * 64
        reseal(payload)
        self.save(payload)
        identities, report = self.load()
        self.assertEqual(set(), identities)
        self.assertEqual("INVALID", report["state"])
        self.assertIn("row hash mismatch", report["errors"][0])

    def test_05_duplicate_tombstone_identity_is_rejected(self):
        payload = json.loads(self.tombstone.read_text(encoding="utf-8"))
        duplicate = copy.deepcopy(payload["tombstones"][0])
        duplicate["tombstone_id"] += "-duplicate"
        payload["tombstones"].append(duplicate)
        reseal(payload)
        self.save(payload)
        identities, report = self.load()
        self.assertEqual(set(), identities)
        self.assertEqual("INVALID", report["state"])

    def test_06_titleloan_is_specifically_non_reusable_before_global_coverage(self):
        index = ledger.load_index(self.ledger)
        blocked, reason, finding = ledger.is_twin(
            index, "tiktok", "titleloan", "2027-01-01"
        )
        self.assertTrue(blocked)
        self.assertIn("historical canonical collision", reason)
        self.assertEqual(["HISTORICAL_CANONICAL_COLLISION_NON_REUSABLE"], finding)

    def test_07_duplicate_key_in_sealed_nested_object_is_rejected(self):
        raw = self.tombstone.read_text(encoding="utf-8")
        ambiguous = raw.replace(
            '"tombstone_id":',
            '"channel": "shadow-channel",\n      "tombstone_id":',
            1,
        )
        self.assertNotEqual(raw, ambiguous)
        self.tombstone.write_text(ambiguous, encoding="utf-8")
        identities, report = self.load()
        self.assertEqual(set(), identities)
        self.assertEqual("INVALID", report["state"])

    def test_08_nested_overflow_number_is_rejected_by_strict_parser(self):
        with self.assertRaisesRegex(ValueError, "non-finite JSON number"):
            collision._strict_json_loads('{"nested":[{"value":1e999}]}')

    def test_09_text_hash_tombstone_requires_the_complete_occurrence_set(self):
        payload = json.loads(self.tombstone.read_text(encoding="utf-8"))
        payload["tombstones"][2]["occurrences"].pop()
        reseal(payload)
        self.save(payload)
        identities, report = self.load()
        self.assertEqual(set(), identities)
        self.assertEqual("INVALID", report["state"])
        self.assertIn("occurrence set mismatch", report["errors"][0])

    def test_10_remediation_receipt_is_hash_bound_and_keeps_line39_blocked(self):
        receipt = json.loads(RECEIPT.read_text(encoding="utf-8"))
        self.assertEqual(receipt["self_sha256"], collision.payload_sha256(receipt))
        for path_key, hash_key in (
            ("ledger_path", "ledger_sha256"),
            ("identity_bindings_path", "identity_bindings_sha256"),
            ("private_commitments_path", "private_commitments_sha256"),
            ("private_identity_evidence_path", "private_identity_evidence_sha256"),
        ):
            path = ROOT / receipt["inputs"][path_key]
            self.assertEqual(
                receipt["inputs"][hash_key],
                hashlib.sha256(path.read_bytes()).hexdigest().upper(),
            )
        for path_key, hash_key in (
            ("registry_path", "registry_sha256"),
            ("validator_path", "validator_sha256"),
            ("consumer_path", "consumer_sha256"),
        ):
            path = ROOT / receipt["remediation"][path_key]
            self.assertEqual(
                receipt["remediation"][hash_key],
                hashlib.sha256(path.read_bytes()).hexdigest().upper(),
            )
        metric = ledger.permanent_dedup_completeness(LEDGER)
        self.assertEqual(0, metric["duplicate_identity_groups"])
        self.assertEqual(3, metric["tombstoned_duplicate_identity_groups"])
        self.assertEqual((124, 1), (
            metric["complete_rows"], metric["incomplete_rows"]
        ))
        self.assertEqual(39, receipt["remaining_blocker"]["ledger_line"])
        self.assertEqual("UNKNOWN_IDENTITY", receipt["remaining_blocker"]["state"])


if __name__ == "__main__":
    raise SystemExit(unittest.main(verbosity=2))
