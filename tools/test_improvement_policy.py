#!/usr/bin/env python3
import json
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class ImprovementPolicyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.policy = json.loads((ROOT / ".system_control" / "policy.json").read_text(encoding="utf-8"))
        cls.roles = json.loads((ROOT / ".system_control" / "role_capabilities.json").read_text(encoding="utf-8"))
        cls.loop = json.loads((ROOT / ".system_control" / "improvement_policy.json").read_text(encoding="utf-8"))

    def test_policy_points_to_one_loop_contract(self):
        pointer = self.policy["continuous_improvement"]
        self.assertEqual(pointer["contract"], ".system_control/improvement_policy.json")
        self.assertEqual(pointer["operator"], "codex")
        self.assertTrue(pointer["local_safe_mode_authorized"])
        self.assertFalse(pointer["unattended_external_mutation"])

    def test_operator_is_internal_and_page_is_public_speaker(self):
        self.assertEqual(self.roles["delegations"]["codex"]["role"], "internal_page_operator")
        self.assertFalse(self.roles["delegations"]["codex"]["public_speaker"])
        self.assertEqual(self.loop["operator"]["public_identity"],
                         self.policy["public_identity"]["canonical_name"])
        self.assertFalse(self.loop["operator"]["public_speaker"])

    def test_external_actions_remain_denied_to_codex(self):
        caps = self.roles["actors"]["codex"]
        for action in ("social_publish", "source_acknowledge", "git_commit",
                       "git_push", "deploy", "financial_transaction",
                       "external_notify", "external_storage_write",
                       "package_install", "scheduler_mutation"):
            self.assertFalse(caps[action], action)
            self.assertIn(action, self.loop["external_actions_requiring_owner_action"])

    def test_metric_semantics_do_not_call_click_revenue(self):
        driver = next(item for item in self.loop["drivers"]
                      if item["id"] == "trusted_affiliate_clicks_28d")
        self.assertIn("never revenue or conversion", driver["meaning"])
        ids = {item["id"] for item in self.loop["primary_kpis"]}
        self.assertEqual(ids, {"paid_affiliate_revenue_thb_28d",
                               "paid_affiliate_transactions_28d"})

    def test_scorecard_is_bounded_and_acceptance_based(self):
        self.assertEqual(self.loop["schema_version"], 2)
        scorecard = self.loop["maturity_scorecard"]
        criteria = scorecard["criteria"]
        self.assertEqual(sum(item["weight"] for item in criteria),
                         scorecard["max_score"])
        self.assertEqual(len({item["id"] for item in criteria}), len(criteria))
        self.assertTrue(all(item["acceptance"].strip() for item in criteria))
        self.assertTrue(all(isinstance(item["hard_blocker"], bool)
                            for item in criteria))
        self.assertLess(scorecard["hard_blocker_score_cap"],
                        scorecard["minimum_growth_experiment_score"])

    def test_daily_is_provisional_and_weekly_owns_experiment_selection(self):
        daily = self.loop["cadence"]["daily"]
        weekly = self.loop["cadence"]["weekly"]
        self.assertEqual(daily["score_progression"], "provisional")
        self.assertFalse(daily["growth_experiment_selection"])
        self.assertEqual(weekly["score_progression"], "ratified")
        self.assertTrue(weekly["growth_experiment_selection"])
        for row in (daily, weekly):
            self.assertGreater(row["review_due_hours"],
                               row["max_observation_age_hours"])

    def test_every_action_has_owner_and_acceptance_criteria(self):
        catalog = self.loop["action_catalog"]
        expected = {
            "repair_local_guard", "repair_measurement", "refresh_gsc_bundle",
            "refresh_official_source_snapshot", "repair_revenue_ledger",
            "audit_offer_and_attribution", "design_one_revenue_experiment",
            "verify_ga4_internal_network", "review_official_sources",
        }
        self.assertEqual(set(catalog), expected)
        for kind, row in catalog.items():
            with self.subTest(kind=kind):
                self.assertIn(row["owner"], {"codex", "owner"})
                self.assertTrue(row["acceptance_criteria"])
                self.assertTrue(all(item.strip()
                                    for item in row["acceptance_criteria"]))

    def test_progression_contract_forbids_stale_or_blocker_gaming(self):
        rules = " ".join(self.loop["feedback_cadence"]["progression_rules"])
        self.assertIn("failed-to-passed criterion transition", rules)
        self.assertIn("reopened hard blocker", rules)
        self.assertIn("missing, stale, malformed, or hash-mismatched", rules)
        self.assertIn("cannot appear before or beside", rules)

    def test_task_receipts_do_not_overclaim_scheduler_origin(self):
        monitoring = self.loop["task_receipt_monitoring"]
        self.assertEqual(monitoring["schema_version"], 3)
        self.assertEqual(
            monitoring["tasks"],
            ["ngernduangold_daily", "ngernduangold_weekly"],
        )
        self.assertEqual(monitoring["origin"], "RUNNER_INVOCATION_UNVERIFIED")
        self.assertFalse(monitoring["scheduler_launch_proven"])
        self.assertEqual(monitoring["stuck_after_hours"], 2)
        self.assertEqual(
            monitoring["contract_revision"],
            "task-version-ordered-command-manifest-v3",
        )
        self.assertTrue(monitoring["finished_requires_complete_manifest"])
        attestations = monitoring["legacy_receipt_attestations"]
        self.assertEqual(len(attestations), 8)
        self.assertEqual(
            sum(row["migration_state"] == "LEGACY_INVALID" for row in attestations),
            1,
        )
        activation = monitoring["activation_attestation"]
        self.assertEqual(
            activation["activated_at"], monitoring["instrumentation_started_at"]
        )
        self.assertEqual(
            activation["receipt_producer_sha256"],
            monitoring["trusted_receipt_producer_sha256"][0],
        )
        verification = activation["verification"]
        self.assertEqual(
            verification["suite_results"],
            {
                "task_receipt_tests": {"tests": 65, "exit_code": 0},
                "improvement_loop_tests": {"tests": 117, "exit_code": 0},
                "wiring_tests": {"tests": 4, "exit_code": 0},
                "policy_tests": {"tests": 9, "exit_code": 0},
                "batch_exit_tests": {"tests": 20, "exit_code": 0},
            },
        )
        self.assertRegex(verification["test_sources_sha256"], r"^[0-9a-f]{64}$")
        self.assertRegex(verification["result_hash"], r"^[0-9a-f]{64}$")
        terminal = next(
            row for row in self.loop["control_health_kpis"]
            if row["id"] == "terminal_control_run_rate_7d"
        )
        self.assertIn(
            "Receipts do not prove a parent process or Windows-scheduled launch",
            terminal["definition"],
        )
        self.assertIn("excluded from the rate", terminal["definition"])
        self.assertIn("stuck RUNNING receipts enter the denominator", terminal["definition"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
