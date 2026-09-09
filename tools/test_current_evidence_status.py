"""Saved evidence must survive both elapsed time and live input changes."""
import datetime as dt
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

PIPELINE = Path(__file__).resolve().parents[1] / "pipeline"
sys.path.insert(0, str(PIPELINE))
import improvement_loop as loop
import test_improvement_loop as fixtures


class CurrentEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.now = dt.datetime.now(dt.timezone.utc).replace(microsecond=0)
        self.contract = loop._load(loop.CONTRACT)
        self.addCleanup(mock.patch.stopall)
        mock.patch.object(loop, "ROOT", self.root).start()
        mock.patch.object(loop, "_runtime_contract_paths", return_value=("control.json",)).start()
        (self.root / "control.json").write_text('{"version":1}', encoding="utf-8")
        writer = fixtures.ImprovementLoopTests()
        self.run_dir, self.observation, _, _, _, self.row = writer.write_complete_weekly_bundle(
            self.root, "test-current-evidence", evaluated_at=self.now
        )
        self.observation["runtime_contract"] = loop.collect_runtime_contract()
        fixtures.write_synthetic_release_evidence(self.run_dir)
        for name, guard in self.observation["guards"].items():
            relative = "guard-evidence/%s.txt" % name
            data = ("synthetic test output " + name).encode()
            (self.run_dir / relative).write_bytes(data)
            guard.update(evidence_path=relative, evidence_sha256=hashlib.sha256(data).hexdigest())
        self.reseal()

    def reseal(self, *, assert_complete=True):
        score = loop.build_maturity_scorecard(
            self.observation, self.contract, cadence="weekly", now=self.now
        )
        diagnosis = {"maturity_scorecard": score}
        validation = {
            "schema_version": 2, "passed": True, "control_state": "READY",
            "errors": [], "operational_blockers": [],
            "maturity_score": score["score"], "maturity_stage": score["stage"],
        }
        self.row.update(
            observation_hash=loop._canonical_hash(self.observation),
            diagnosis_hash=loop._canonical_hash(diagnosis),
            validation_hash=loop._canonical_hash(validation),
            maturity_score=score["score"], maturity_stage=score["stage"],
            maturity_scorecard_hash=score["scorecard_hash"],
        )
        for name, value in (("observation", self.observation), ("diagnosis", diagnosis),
                            ("validation", validation), ("maturity-scorecard", score),
                            ("run", self.row)):
            loop._atomic(self.run_dir / (name + ".json"), value)
        if assert_complete:
            self.assertTrue(loop._has_complete_evidence_bundle(
                self.run_dir, self.row, self.contract
            ))

    def assess(self, **kwargs):
        return loop.assess_current_evidence(
            self.run_dir, self.row, now=kwargs.get("now", self.now), contract=self.contract
        )

    def test_current_bound_evidence_has_current_score(self):
        result = self.assess()
        self.assertEqual(result["state"], "CURRENT")
        self.assertEqual(result["current_score"], result["historical_score"])

    def test_changed_input_invalidates_score_without_rewriting_bundle(self):
        before = (self.run_dir / "run.json").read_bytes()
        (self.root / "control.json").write_text('{"version":2}', encoding="utf-8")
        result = self.assess()
        self.assertEqual(result["state"], "INPUT_DRIFT")
        self.assertEqual(result["changed_inputs"], ["control.json"])
        self.assertIsNone(result["current_score"])
        self.assertEqual((self.run_dir / "run.json").read_bytes(), before)

    def test_threads_editorial_dependencies_are_in_production_contract(self):
        for relative in (
            "tools/editorial_draft_gate.py",
            "tools/week_content_freshness_guard.py",
        ):
            with self.subTest(path=relative):
                self.assertIn(relative, loop.RUNTIME_CONTRACT_PATHS)

    def test_editorial_dependency_byte_drift_invalidates_saved_score(self):
        dependencies = (
            "tools/editorial_draft_gate.py",
            "tools/week_content_freshness_guard.py",
        )
        # Select from the real production registry. Injecting the desired paths
        # here would make this test pass even if production forgot to bind them.
        selected = ("control.json",) + tuple(
            relative for relative in dependencies
            if relative in loop.RUNTIME_CONTRACT_PATHS
        )
        for relative in dependencies:
            path = self.root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b"lint-a\n")
        with mock.patch.object(loop, "_runtime_contract_paths", return_value=selected):
            for relative in dependencies:
                with self.subTest(path=relative):
                    self.observation["runtime_contract"] = loop.collect_runtime_contract()
                    self.reseal()
                    before = (self.run_dir / "run.json").read_bytes()
                    (self.root / relative).write_bytes(b"lint-b\n")
                    result = self.assess()
                    self.assertEqual("INPUT_DRIFT", result["state"])
                    self.assertEqual("BLOCKED", result["decision_state"])
                    self.assertEqual([relative], result["changed_inputs"])
                    self.assertIsNone(result["current_score"])
                    self.assertEqual((self.run_dir / "run.json").read_bytes(), before)

    def test_manual_calendar_absence_is_bound_and_appearance_is_drift(self):
        relative = ".local-private/runtime/manual-publication-calendar.json"
        self.assertIn(relative, loop.RUNTIME_CONTRACT_PATHS)
        with mock.patch.object(loop, "_runtime_contract_paths", return_value=("control.json", relative)):
            self.observation["runtime_contract"] = loop.collect_runtime_contract()
            self.assertEqual("ABSENT", self.observation["runtime_contract"]["files"][-1]["state"])
            self.reseal()
            self.assertEqual("CURRENT", self.assess()["state"])
            before = (self.run_dir / "run.json").read_bytes()
            path = self.root / relative
            path.parent.mkdir(parents=True)
            path.write_text('{"test_only":true}', encoding="utf-8")
            result = self.assess()
            self.assertEqual("INPUT_DRIFT", result["state"])
            self.assertEqual([relative], result["changed_inputs"])
            self.assertIsNone(result["current_score"])
            self.assertEqual(before, (self.run_dir / "run.json").read_bytes())

    def test_manual_calendar_removal_and_byte_drift_invalidate_score(self):
        relative = ".local-private/runtime/manual-publication-calendar.json"
        path = self.root / relative
        path.parent.mkdir(parents=True)
        path.write_bytes(b"calendar-a")
        with mock.patch.object(loop, "_runtime_contract_paths", return_value=("control.json", relative)):
            self.observation["runtime_contract"] = loop.collect_runtime_contract()
            self.reseal()
            self.assertEqual("CURRENT", self.assess()["state"])
            path.write_bytes(b"calendar-b")
            self.assertEqual("INPUT_DRIFT", self.assess()["state"])
            path.unlink()
            result = self.assess()
            self.assertEqual("INPUT_DRIFT", result["state"])
            self.assertEqual([relative], result["changed_inputs"])
            self.assertIsNone(result["current_score"])

    def test_optional_absence_cannot_hide_nonfile_or_unrelated_missing_input(self):
        relative = ".local-private/runtime/manual-publication-calendar.json"
        path = self.root / relative
        path.mkdir(parents=True)
        with mock.patch.object(loop, "_runtime_contract_paths", return_value=("control.json", relative)):
            contract = loop.collect_runtime_contract()
            self.assertTrue(loop.runtime_contract_errors(contract))
            row = contract["files"][-1]
            row.update(state="ABSENT", size_bytes=1, sha256="a" * 64)
            contract["contract_hash"] = loop._canonical_hash({key: value for key, value in contract.items() if key != "contract_hash"})
            self.assertTrue(loop.runtime_contract_errors(contract))
        with mock.patch.object(loop, "_runtime_contract_paths", return_value=("missing-control.json",)):
            contract = loop.collect_runtime_contract()
            contract["files"][0]["state"] = "ABSENT"
            contract["contract_hash"] = loop._canonical_hash({key: value for key, value in contract.items() if key != "contract_hash"})
            self.assertTrue(loop.runtime_contract_errors(contract))

    def test_freshness_uses_observation_not_later_completion(self):
        self.row["finished_at"] = (self.now + dt.timedelta(hours=2)).isoformat()
        result = self.assess(now=self.now + dt.timedelta(hours=2, seconds=1))
        self.assertEqual(result["state"], "STALE")
        self.assertIsNone(result["current_score"])

    def test_missing_runtime_evidence_is_unknown(self):
        self.observation.pop("runtime_contract")
        self.reseal()
        self.assertEqual(self.assess()["state"], "UNKNOWN")

    def test_tampered_guard_output_is_unknown(self):
        name = next(iter(self.observation["guards"]))
        path = self.run_dir / self.observation["guards"][name]["evidence_path"]
        path.write_text("tampered", encoding="utf-8")
        result = self.assess()
        self.assertEqual(result["state"], "UNKNOWN")
        self.assertIsNone(result["current_score"])

    def test_future_completion_cannot_be_current(self):
        self.row["finished_at"] = (self.now + dt.timedelta(minutes=1)).isoformat()
        self.assertEqual(self.assess()["state"], "UNKNOWN")

    def test_missing_bundle_is_unknown(self):
        result = loop.assess_current_evidence(None, None, now=self.now, contract=self.contract)
        self.assertEqual(result["state"], "UNKNOWN")
        self.assertIsNone(result["current_score"])

    def test_failed_validation_bundle_cannot_become_ready(self):
        validation = loop._load(self.run_dir / "validation.json")
        validation.update({
            "passed": False,
            "control_state": "INVALID",
            "errors": ["action queue is invalid"],
        })
        self.row.update({
            "status": "FAILED_VALIDATION",
            "validation_passed": False,
            "control_state": "INVALID",
            "validation_hash": loop._canonical_hash(validation),
        })
        loop._atomic(self.run_dir / "validation.json", validation)
        loop._atomic(self.run_dir / "run.json", self.row)

        result = self.assess()
        self.assertNotEqual(
            result["decision_state"], "READY_FOR_OWNER_APPROVAL"
        )
        self.assertNotEqual(result["state"], "CURRENT")
        self.assertIsNone(result["current_score"])

    def test_saved_valid_with_blockers_cannot_become_ready(self):
        validation = loop._load(self.run_dir / "validation.json")
        validation.update({
            "passed": True,
            "control_state": "VALID_WITH_BLOCKERS",
            "operational_blockers": ["error_regression:synthetic"],
        })
        self.row.update({
            "status": "COMPLETED_WITH_BLOCKERS",
            "validation_passed": True,
            "control_state": "VALID_WITH_BLOCKERS",
            "validation_hash": loop._canonical_hash(validation),
        })
        loop._atomic(self.run_dir / "validation.json", validation)
        loop._atomic(self.run_dir / "run.json", self.row)
        self.assertTrue(loop._has_complete_evidence_bundle(
            self.run_dir, self.row, self.contract
        ))

        result = self.assess()
        self.assertEqual("BLOCKED", result["decision_state"])
        self.assertNotEqual(
            "READY_FOR_OWNER_APPROVAL", result["decision_state"]
        )

    def test_missing_saved_operational_blockers_cannot_become_ready(self):
        validation = loop._load(self.run_dir / "validation.json")
        validation.pop("operational_blockers")
        self.row["validation_hash"] = loop._canonical_hash(validation)
        loop._atomic(self.run_dir / "validation.json", validation)
        loop._atomic(self.run_dir / "run.json", self.row)
        self.assertTrue(loop._has_complete_evidence_bundle(
            self.run_dir, self.row, self.contract
        ))

        result = self.assess()
        self.assertEqual("BLOCKED", result["decision_state"])

    def test_child_evidence_expiry_suppresses_current_score(self):
        # Synthetic GA4/GSC/revenue evidence expires after one hour while the
        # weekly outer observation SLA remains open.  INVALID child evidence
        # must not be labelled CURRENT or retain a decision-facing score.
        result = self.assess(now=self.now + dt.timedelta(hours=2))
        self.assertNotEqual(result["state"], "CURRENT")
        self.assertEqual(result["decision_state"], "BLOCKED")
        self.assertIsNone(result["current_score"])

    def test_external_run_directory_junction_is_excluded(self):
        runs_root = self.root / "scan-root"
        runs_root.mkdir()
        linked = runs_root / self.run_dir.name
        if os.name == "nt":
            made = subprocess.run(
                ["cmd", "/c", "mklink", "/J", str(linked), str(self.run_dir)],
                capture_output=True, text=True, check=False,
            )
            self.assertEqual(0, made.returncode, made.stderr or made.stdout)
            self.addCleanup(
                lambda: os.rmdir(linked) if linked.exists() else None
            )
        else:
            os.symlink(self.run_dir, linked, target_is_directory=True)

        health = loop.build_control_health(
            runs_root,
            loop._empty_error_learning_state(),
            now=self.now,
            task_runs_root=self.root / "task-runs",
            receipt_monitoring=self.contract["task_receipt_monitoring"],
        )
        self.assertIsNone(health["current_evidence"]["run_id"])
        self.assertEqual("UNKNOWN", health["current_evidence"]["state"])
        self.assertEqual(0, health["improvement_bundles"]["started_7d"])

    def test_health_evidence_age_uses_observation_not_finish(self):
        # A slow bundle completed 20 minutes after observation and is checked
        # 10 minutes later. Evidence age is 30 minutes, not completion age.
        self.row["finished_at"] = (
            self.now + dt.timedelta(minutes=20)
        ).isoformat()
        loop._atomic(self.run_dir / "run.json", self.row)
        health = loop.build_control_health(
            self.root,
            loop._empty_error_learning_state(),
            now=self.now + dt.timedelta(minutes=30),
            task_runs_root=self.root / "task-runs",
            receipt_monitoring=self.contract["task_receipt_monitoring"],
        )
        self.assertEqual(
            health["current_evidence"]["observation_age_hours"],
            health["kpis"]["fresh_evidence_age_hours"],
        )
        self.assertEqual(0.5, health["kpis"]["fresh_evidence_age_hours"])

    def test_malformed_guard_map_returns_structured_unknown(self):
        self.observation["guards"] = []
        self.reseal(assert_complete=False)
        result = self.assess()
        self.assertEqual("UNKNOWN", result["state"])
        self.assertIsNone(result["current_score"])
        self.assertTrue(result["errors"])

    def test_status_cli_never_dispatches_run_or_writes_state(self):
        health = {"current_evidence": {"state": "STALE", "decision_state": "BLOCKED"}}
        with mock.patch.object(sys, "argv", ["improvement_loop.py", "status", "--json"]), \
             mock.patch.object(loop, "execute", side_effect=AssertionError("run called")), \
             mock.patch.object(loop, "_atomic", side_effect=AssertionError("write called")), \
             mock.patch.object(loop, "_load_error_learning_state", return_value={}), \
             mock.patch.object(loop, "build_control_health", return_value=health), \
             mock.patch("sys.stdout", new_callable=io.StringIO) as output:
            self.assertEqual(loop.main(), 2)
            self.assertEqual(json.loads(output.getvalue()), health)


if __name__ == "__main__":
    unittest.main()
