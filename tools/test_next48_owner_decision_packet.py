import copy
from datetime import datetime, timedelta
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools import next48_owner_decision_packet as packet


# Current-repository integration anchor. Historical receipt behavior is tested
# separately against the immutable hash-bound fixture.
AS_OF = datetime.fromisoformat("2026-08-31T00:29:39+07:00")


class WindowSelectionTests(unittest.TestCase):
    def test_window_inventory_is_data_driven_and_empty_fails_closed(self):
        anchor = datetime.fromisoformat("2026-08-30T22:45:00+07:00")
        rows = [
            {
                "placement_id": "one__threads_main",
                "date": "2026-08-31",
                "time": "12:40",
            },
            {
                "placement_id": "two__facebook_main",
                "date": "2026-09-01",
                "time": "13:10",
            },
            {
                "placement_id": "outside__facebook_main",
                "date": "2026-09-02",
                "time": "23:00",
            },
        ]
        selected = packet._select_window_placements(
            rows, anchor, anchor + timedelta(hours=48)
        )
        self.assertEqual(
            [row["placement_id"] for row in selected],
            ["one__threads_main", "two__facebook_main"],
        )
        with self.assertRaisesRegex(
            packet.PacketError,
            "exact 48-hour window has no calendar placements",
        ):
            packet._select_window_placements(
                rows,
                datetime.fromisoformat("2026-09-10T00:00:00+07:00"),
                datetime.fromisoformat("2026-09-12T00:00:00+07:00"),
            )

    def test_markdown_section_caption_is_identity_bound(self):
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory)
            source = repo / "package.md"
            source.write_text(
                "# Pilot\n\n- **Asset ID:** `b4-p01`\n\n"
                "## Social caption\n\nExact social copy\n\n## Measurement\n\nNo copy\n",
                encoding="utf-8",
            )
            placement = {
                "source": {
                    "file": "package.md",
                    "row_id": "b4-p01",
                    "field": "social_caption",
                }
            }
            value, binding = packet._caption(repo, placement, {})
            self.assertEqual(value, "Exact social copy")
            self.assertEqual(binding["row_id"], "b4-p01")
            changed = copy.deepcopy(placement)
            changed["source"]["row_id"] = "another-id"
            with self.assertRaisesRegex(packet.PacketError, "caption field is missing"):
                packet._caption(repo, changed, {})

            source.write_text(
                "# Multi\n\n- **Asset ID:** `b4-p01`\n"
                "- **Asset ID:** `another-id`\n\n"
                "## Social caption\n\nAmbiguous copy\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(packet.PacketError, "caption field is missing"):
                packet._caption(repo, placement, {})

            source.write_text(
                "# Duplicate heading\n\n- **Asset ID:** `b4-p01`\n\n"
                "## Social caption\n\nFirst\n\n"
                "## Social caption\n\nSecond\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(packet.PacketError, "caption field is missing"):
                packet._caption(repo, placement, {})


class Next48OwnerDecisionPacketTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.value = packet.build_packet(ROOT, AS_OF, 48)

    def test_exact_current_inventory_is_five_and_hash_bound(self):
        self.assertEqual(self.value["summary"]["placement_count"], 5)
        self.assertEqual(
            [row["placement_id"] for row in self.value["placements"]],
            [
                "kn-44__threads_main",
                "kn-44__facebook_main",
                "b4-p01__facebook_main",
                "qt-13__instagram_main",
                "p2-13__facebook_page2",
            ],
        )
        for row in self.value["placements"]:
            self.assertRegex(row["caption_binding"]["caption_sha256"], r"^[0-9A-F]{64}$")
            self.assertRegex(row["calendar_state"]["placement_canonical_sha256"], r"^[0-9A-F]{64}$")

    def test_never_promotes_calendar_or_authority(self):
        self.assertEqual(self.value["summary"]["publishable"], 0)
        self.assertEqual(self.value["summary"]["ready_all_gates"], 0)
        self.assertFalse(self.value["boundary"]["is_approval_receipt"])
        self.assertFalse(self.value["boundary"]["grants_publication_authority"])
        for row in self.value["placements"]:
            self.assertEqual(row["calendar_state"]["status"], "PLANNED_BLOCKED")
            self.assertEqual(row["publication_state"], "BLOCKED")
            self.assertFalse(row["authority"]["exact_private_owner_receipt_present"])

    def test_closest_piece_is_blocked_by_live_release_parity(self):
        summary = self.value["summary"]
        self.assertEqual(summary["closest_placement_id"], "kn-44__threads_main")
        self.assertEqual(
            summary["closest_decision_state"],
            "BLOCKED_NOT_READY_FOR_OWNER_DECISION",
        )
        self.assertIn("publication_authority", summary["closest_owner_blockers"])
        self.assertIn(
            "live_branded_release_parity_failed_or_unknown",
            summary["closest_non_owner_blockers"],
        )
        self.assertEqual(summary["ready_for_owner_decision"], 0)

    def test_unrelated_facebook_gap_remains_audit_only_for_threads(self):
        row = self.value["placements"][0]
        self.assertEqual(row["target"]["channel"], "threads")
        self.assertEqual(row["dedup"]["global_state"], "BLOCKED")
        self.assertEqual(row["dedup"]["channel_state"], "PASS")
        self.assertEqual(
            row["dedup"]["decision_scope"], "CHANNEL_AND_EXACT_CANDIDATE"
        )
        self.assertEqual(
            row["dedup"]["global_state_role"], "AUDIT_ONLY_NOT_ACTION_GATE"
        )
        self.assertNotIn(
            "global_permanent_dedup_incomplete", row["non_owner_blockers"]
        )

    def test_live_observation_is_hash_bound_and_profile_cta_fails_closed(self):
        row = self.value["placements"][0]
        self.assertTrue(row["live_domain"]["depends_on_branded_site"])
        self.assertEqual(row["live_domain"]["observation_state"], "BLOCKED")
        binding = self.value["bound_inputs"]["live_domain_observation"]
        self.assertRegex(binding["sha256"], r"^[0-9A-F]{64}$")
        self.assertTrue(binding["path"].endswith(".json"))

    def test_current_media_states_preserve_real_human_blocker(self):
        video = next(
            item for item in self.value["placements"]
            if item["placement_id"] == "b4-p01__facebook_main"
        )
        image = next(
            item for item in self.value["placements"]
            if item["placement_id"] == "qt-13__instagram_main"
        )
        self.assertEqual(video["media"]["state"], "BLOCKED_HUMAN_LISTENING")
        self.assertIn("human_listening_not_run", video["owner_blockers"])
        self.assertEqual(image["media"]["state"], "PASS")

    def test_quota_and_gap_are_explicit_action_gates(self):
        row = self.value["placements"][0]
        self.assertEqual(row["quota_gap"]["state"], "PASS")
        self.assertGreater(
            row["quota_gap"]["remaining_capacity_before_claim"], 0
        )
        self.assertTrue(row["quota_gap"]["gap_allowed"])

    def test_incomplete_channel_does_not_duplicate_derived_quota_blockers(self):
        row = next(
            item for item in self.value["placements"]
            if item["placement_id"] == "kn-44__facebook_main"
        )
        self.assertIn(
            "channel_permanent_dedup_incomplete", row["non_owner_blockers"]
        )
        self.assertNotIn(
            "daily_quota_exhausted_or_unknown", row["non_owner_blockers"]
        )
        self.assertNotIn(
            "minimum_gap_failed_or_unknown", row["non_owner_blockers"]
        )

    def test_page2_uses_its_own_account_identity_space(self):
        row = next(
            item for item in self.value["placements"]
            if item["placement_id"] == "p2-13__facebook_page2"
        )
        self.assertEqual(row["target"]["channel"], "fb")
        self.assertEqual(row["target"]["dedup_channel"], "facebook-page2")
        self.assertEqual(row["dedup"]["channel_state"], "PASS")
        self.assertEqual(
            row["dedup"]["channel_coverage"]["channel"], "facebook-page2"
        )
        self.assertNotIn(
            "channel_permanent_dedup_incomplete", row["non_owner_blockers"]
        )

    def test_packet_contains_hashes_not_raw_caption_copy(self):
        rendered = json.dumps(self.value, ensure_ascii=False)
        calendar = packet._load_object(ROOT / packet.CALENDAR)
        by_id = {
            row["placement_id"]: row for row in calendar["placements"]
        }
        for row in self.value["placements"]:
            copy_text, _binding = packet._caption(
                ROOT, by_id[row["placement_id"]], {}
            )
            self.assertNotIn(copy_text, rendered)

    def test_deterministic_validator_accepts_exact_packet(self):
        self.assertEqual(packet.validate_packet(self.value, ROOT), [])

    def test_validator_rejects_tampered_caption_hash(self):
        changed = copy.deepcopy(self.value)
        changed["placements"][0]["caption_binding"]["caption_sha256"] = "0" * 64
        failures = packet.validate_packet(changed, ROOT)
        self.assertIn("packet payload SHA-256 mismatch", failures)
        self.assertIn("packet does not equal deterministic recomputation", failures)

    def test_validator_rejects_resigned_live_observation_binding(self):
        changed = copy.deepcopy(self.value)
        changed["bound_inputs"]["live_domain_observation"]["sha256"] = "0" * 64
        changed["packet_payload_sha256"] = packet._canonical_sha256({
            key: value for key, value in changed.items()
            if key != "packet_payload_sha256"
        })
        failures = packet.validate_packet(changed, ROOT)
        self.assertNotIn("packet payload SHA-256 mismatch", failures)
        self.assertIn("packet does not equal deterministic recomputation", failures)

    def test_stale_live_observation_never_becomes_pass(self):
        latest = packet._latest_live_domain_observation(ROOT)
        payload = json.loads(latest.read_text(encoding="utf-8"))
        observed_at = datetime.fromisoformat(payload["observed_at"])
        contract = payload.get("validity_contract")
        max_age_hours = (
            contract.get("max_age_hours") if isinstance(contract, dict) else 6
        )
        state, _path = packet._live_domain_state(
            ROOT,
            observed_at + timedelta(hours=max_age_hours, seconds=1),
        )
        self.assertEqual(state["state"], "BLOCKED")
        if payload.get("schema_version") == 2:
            self.assertIn(
                "live-domain observation: observation is stale at the decision time",
                state["failures"],
            )
        else:
            self.assertIn(
                "live-domain observation: observation schema is unsupported",
                state["failures"],
            )

    def test_http_status_without_exact_body_hashes_cannot_prove_parity(self):
        state, _path = packet._live_domain_state(
            ROOT, datetime.fromisoformat("2026-08-25T02:09:20+07:00")
        )
        self.assertEqual(state["state"], "BLOCKED")
        self.assertIn(
            "live response body hashes do not match the local candidate",
            state["failures"],
        )


if __name__ == "__main__":
    unittest.main()
