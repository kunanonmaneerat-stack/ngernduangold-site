import datetime as dt
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest import mock


HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
SCRIPT = HERE / "task_run_receipt.py"
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import task_run_receipt as receipt


class ReceiptTestCase(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.receipt_root = self.base / "receipts"
        self.runner = self.base / "runner.cmd"
        self.runner.write_text("@echo off\r\nexit /b 0\r\n", encoding="utf-8")
        self.log = self.base / "runner.log"
        self.task = "receipt_test"

    def start(self, run_id="test-run"):
        path, document = receipt.start_receipt(
            root=self.receipt_root,
            task_name=self.task,
            runner_path=self.runner,
            log_path=self.log,
            run_id=run_id,
        )
        self.assertTrue(receipt.verify_receipt(document))
        return path, document

    def load(self, path):
        return json.loads(path.read_text(encoding="utf-8"))

    def cli(self, *args):
        return subprocess.run(
            [sys.executable, str(SCRIPT), *map(str, args)],
            text=True,
            capture_output=True,
            check=False,
        )

    def test_cli_start_exec_finish_is_atomic_and_hash_bound(self):
        start = self.cli(
            "start",
            "--root", self.receipt_root,
            "--task", self.task,
            "--runner", self.runner,
            "--log", self.log,
            "--run-id", "cli-run",
        )
        self.assertEqual(start.returncode, 0, start.stderr)
        self.assertEqual(start.stdout.strip(), "cli-run")

        execute = self.cli(
            "exec",
            "--root", self.receipt_root,
            "--task", self.task,
            "--run-id", "cli-run",
            "--step", "child_ok",
            "--wrapper", "required",
            "--contract", "generic",
            "--",
            sys.executable,
            "-c",
            "raise SystemExit(0)",
        )
        self.assertEqual(execute.returncode, 0, execute.stderr)

        finish = self.cli(
            "finish",
            "--root", self.receipt_root,
            "--task", self.task,
            "--run-id", "cli-run",
            "--terminal", "end",
            "--terminal-reason", "normal_end",
            "--publication-state", "BLOCKED_LOCAL_ONLY",
            "--final-rc", "0",
        )
        self.assertEqual(finish.returncode, 0, finish.stderr)
        path = receipt.receipt_path(self.receipt_root, self.task, "cli-run")
        document = self.load(path)
        self.assertTrue(receipt.verify_receipt(document))
        self.assertEqual(document["status"], "FINISHED")
        self.assertEqual(document["execution_state"], "PASS")
        self.assertEqual(document["publication_state"], "BLOCKED_LOCAL_ONLY")
        self.assertEqual(document["steps"][0]["raw_rc"], 0)
        inspected = receipt.inspect_receipt_file(path)
        self.assertTrue(inspected["trusted_for_completion"])
        self.assertFalse(inspected["trusted_for_scheduler_launch"])
        self.assertFalse(list(path.parent.glob("*.tmp")))
        self.assertFalse(receipt.receipt_revocation_path(path).exists())

    def start_monitored(self, task_name, run_id):
        spec = receipt.TASK_STEP_CONTRACTS[task_name]
        runner = HERE / spec["runner_name"]
        return receipt.start_receipt(
            root=self.receipt_root,
            task_name=task_name,
            runner_path=runner,
            log_path=self.log,
            run_id=run_id,
        )

    def test_read_only_inspection_validates_schema3_without_private_details(self):
        path, document = self.start("inspect-current")
        summary = receipt.inspect_receipt_file(path)
        rendered = json.dumps(summary, sort_keys=True)

        self.assertEqual(summary["evidence_status"], "VALID_SCHEMA3_TASK_CONTRACT")
        self.assertEqual(summary["receipt_schema_version"], receipt.SCHEMA_VERSION)
        self.assertEqual(summary["execution_state"], "RUNNING")
        self.assertTrue(summary["trusted_for_execution"])
        self.assertFalse(summary["trusted_for_completion"])
        self.assertFalse(summary["trusted_for_scheduler_launch"])
        self.assertEqual(summary["task_contract_version"], "unmonitored-v1")
        self.assertNotIn(document["run_id"], rendered)
        self.assertNotIn(document["runner"]["path"], rendered)
        self.assertNotIn(document["log_path"], rendered)
        self.assertNotIn(document["receipt_hash"], rendered)
        self.assertNotIn("steps", summary)
        cli_inspection = self.cli("inspect", "--path", path)
        self.assertEqual(cli_inspection.returncode, 0, cli_inspection.stderr)
        self.assertEqual(
            json.loads(cli_inspection.stdout)["evidence_status"],
            "VALID_SCHEMA3_TASK_CONTRACT",
        )

    def test_read_only_inspection_marks_schema2_as_legacy_not_completion(self):
        path, _ = self.start("inspect-legacy")
        receipt.execute_step(
            root=self.receipt_root,
            task_name=self.task,
            run_id="inspect-legacy",
            step_id="legacy_child",
            wrapper="required",
            contract="generic",
            command=[sys.executable, "-c", "raise SystemExit(0)"],
        )
        current = self.load(path)
        legacy = json.loads(json.dumps(current))
        legacy["schema_version"] = receipt.LEGACY_RECEIPT_SCHEMA_VERSION
        legacy.pop("task_contract")
        for step in legacy["steps"]:
            step.pop("evidence_mode")
        legacy = receipt.seal_receipt(legacy)
        path.write_text(
            json.dumps(legacy, sort_keys=True, indent=2) + "\n",
            encoding="utf-8",
        )

        summary = receipt.inspect_receipt_file(path)

        self.assertEqual(
            summary["evidence_status"],
            "LEGACY_SCHEMA2_HASH_VALID_UNVERIFIED",
        )
        self.assertIsNone(summary["execution_state"])
        self.assertEqual(summary["claimed_execution_state"], "RUNNING")
        self.assertFalse(summary["trusted_for_execution"])
        self.assertFalse(summary["trusted_for_completion"])
        self.assertFalse(summary["trusted_for_scheduler_launch"])
        self.assertIsNone(summary["task_contract_version"])
        cli_inspection = self.cli("inspect", "--path", path)
        self.assertEqual(
            cli_inspection.returncode,
            receipt.CLI_LEGACY_UNVERIFIED,
            cli_inspection.stderr,
        )
        self.assertEqual(
            json.loads(cli_inspection.stdout)["evidence_status"],
            "LEGACY_SCHEMA2_HASH_VALID_UNVERIFIED",
        )

    def test_read_only_inspection_rejects_tampered_legacy_hash(self):
        path, current = self.start("inspect-legacy-tampered")
        legacy = json.loads(json.dumps(current))
        legacy["schema_version"] = receipt.LEGACY_RECEIPT_SCHEMA_VERSION
        legacy.pop("task_contract")
        legacy = receipt.seal_receipt(legacy)
        legacy["publication_state"] = "NOT_ATTEMPTED"
        path.write_text(json.dumps(legacy), encoding="utf-8")

        with self.assertRaisesRegex(receipt.ReceiptError, "hash mismatch"):
            receipt.inspect_receipt_file(path)

    def test_schema3_without_task_contract_cannot_fall_back_to_legacy(self):
        path, current = self.start("inspect-schema3-missing-contract")
        forged = json.loads(json.dumps(current))
        forged.pop("task_contract")
        path.write_text(
            json.dumps(receipt.seal_receipt(forged)), encoding="utf-8"
        )

        with self.assertRaisesRegex(
            receipt.ReceiptError, "missing required fields"
        ):
            receipt.inspect_receipt_file(path)

    def record_full_manifest(self, task_name, run_id, raw_rc_by_step=None):
        raw_rc_by_step = dict(raw_rc_by_step or {})
        contract = receipt.TASK_STEP_CONTRACTS[task_name]
        commands = receipt.TASK_STEP_COMMAND_REGISTRY[
            (task_name, contract["version"])
        ]
        for step_id, wrapper, step_contract in contract["expected_steps"]:
            raw_rc = raw_rc_by_step.get(step_id, 0)
            if wrapper == "internal":
                receipt.record_step(
                    root=self.receipt_root,
                    task_name=task_name,
                    run_id=run_id,
                    step_id=step_id,
                    wrapper=wrapper,
                    contract=step_contract,
                    raw_rc=raw_rc,
                )
            else:
                command = list(commands[step_id])
                with mock.patch.object(
                    receipt.subprocess, "run",
                    return_value=subprocess.CompletedProcess(command, raw_rc),
                ) as child:
                    receipt.execute_step(
                        root=self.receipt_root,
                        task_name=task_name,
                        run_id=run_id,
                        step_id=step_id,
                        wrapper=wrapper,
                        contract=step_contract,
                        command=command,
                    )
                    child.assert_called_once()
                    self.assertEqual(child.call_args.args[0], command)

    def test_monitored_normal_end_requires_the_complete_ordered_manifest(self):
        task_name = "ngernduangold_daily"
        path, started = self.start_monitored(task_name, "empty-finish")
        with self.assertRaisesRegex(
            receipt.ReceiptError, "missing required task-contract steps"
        ):
            receipt.finish_receipt(
                root=self.receipt_root,
                task_name=task_name,
                run_id="empty-finish",
                terminal_kind="end",
                terminal_reason="normal_end",
                terminal_step_id=None,
                publication_state="BLOCKED_LOCAL_ONLY",
                final_rc=0,
            )
        persisted = self.load(path)
        self.assertEqual(persisted, started)
        self.assertEqual(persisted["status"], "RUNNING")
        self.assertEqual(persisted["steps"], [])

        path, _ = self.start_monitored(task_name, "full-finish")
        self.record_full_manifest(task_name, "full-finish")
        final = receipt.finish_receipt(
            root=self.receipt_root,
            task_name=task_name,
            run_id="full-finish",
            terminal_kind="end",
            terminal_reason="normal_end",
            terminal_step_id=None,
            publication_state="BLOCKED_LOCAL_ONLY",
            final_rc=0,
        )
        self.assertEqual(final["status"], "FINISHED")
        self.assertEqual(final["execution_state"], "PASS")
        self.assertEqual(
            len(final["steps"]),
            len(final["task_contract"]["expected_steps"]),
        )
        self.assertEqual(self.load(path), final)

    def test_monitored_step_tuple_is_checked_before_any_child_execution(self):
        task_name = "ngernduangold_daily"
        bad_tuples = (
            ("runner.log_directory", "internal", "internal-v1"),
            ("runner.chdir", "graded", "internal-v1"),
            ("runner.chdir", "internal", "generic"),
        )
        for index, (step_id, wrapper, step_contract) in enumerate(bad_tuples):
            run_id = f"bad-next-{index}"
            self.start_monitored(task_name, run_id)
            with mock.patch.object(receipt.subprocess, "run") as child:
                with self.assertRaisesRegex(
                    receipt.ReceiptError,
                    "step does not match the next task-contract entry",
                ):
                    receipt.execute_step(
                        root=self.receipt_root,
                        task_name=task_name,
                        run_id=run_id,
                        step_id=step_id,
                        wrapper=wrapper,
                        contract=step_contract,
                        command=["child"],
                    )
                child.assert_not_called()

    def test_monitored_command_is_checked_before_any_child_execution(self):
        task_name = "ngernduangold_daily"
        run_id = "wrong-command"
        self.start_monitored(task_name, run_id)
        for step_id in (
            "runner.chdir", "runner.log_directory", "runner.log_prepare"
        ):
            receipt.record_step(
                root=self.receipt_root,
                task_name=task_name,
                run_id=run_id,
                step_id=step_id,
                wrapper="internal",
                contract="internal-v1",
                raw_rc=0,
            )
        path = receipt.receipt_path(self.receipt_root, task_name, run_id)
        before = self.load(path)
        with mock.patch.object(receipt.subprocess, "run") as child:
            with self.assertRaisesRegex(
                receipt.ReceiptError,
                "step does not match the next task-contract entry",
            ):
                receipt.execute_step(
                    root=self.receipt_root,
                    task_name=task_name,
                    run_id=run_id,
                    step_id="comply_gate_stitch",
                    wrapper="required",
                    contract="scan-on-1-v1",
                    command=[sys.executable, "-c", "raise SystemExit(0)"],
                )
            child.assert_not_called()
        self.assertEqual(self.load(path), before)

    def test_monitored_record_and_exec_modes_cannot_be_substituted(self):
        task_name = "ngernduangold_daily"
        self.start_monitored(task_name, "record-for-exec")
        for step_id in (
            "runner.chdir", "runner.log_directory", "runner.log_prepare"
        ):
            receipt.record_step(
                root=self.receipt_root,
                task_name=task_name,
                run_id="record-for-exec",
                step_id=step_id,
                wrapper="internal",
                contract="internal-v1",
                raw_rc=0,
            )
        with self.assertRaisesRegex(
            receipt.ReceiptError, "next task-contract entry"
        ):
            receipt.record_step(
                root=self.receipt_root,
                task_name=task_name,
                run_id="record-for-exec",
                step_id="comply_gate_stitch",
                wrapper="required",
                contract="scan-on-1-v1",
                raw_rc=0,
            )

        self.start_monitored(task_name, "exec-for-record")
        with mock.patch.object(receipt.subprocess, "run") as child:
            with self.assertRaisesRegex(
                receipt.ReceiptError, "next task-contract entry"
            ):
                receipt.execute_step(
                    root=self.receipt_root,
                    task_name=task_name,
                    run_id="exec-for-record",
                    step_id="runner.chdir",
                    wrapper="internal",
                    contract="internal-v1",
                    command=["synthetic-child"],
                )
            child.assert_not_called()

    def test_unscoped_unsafe_or_empty_step_request_never_launches_child(self):
        path, started = self.start("unsafe-request")
        cases = (
            {"step_id": "../unsafe", "contract": "generic"},
            {"step_id": "safe", "contract": ""},
        )
        for case in cases:
            with self.subTest(case=case):
                with mock.patch.object(receipt.subprocess, "run") as child:
                    with self.assertRaises(receipt.ReceiptError):
                        receipt.execute_step(
                            root=self.receipt_root,
                            task_name=self.task,
                            run_id="unsafe-request",
                            wrapper="required",
                            command=["synthetic-child"],
                            **case,
                        )
                    child.assert_not_called()
                self.assertEqual(self.load(path), started)

    def test_historical_contract_survives_active_version_change(self):
        task_name = "ngernduangold_daily"
        _, historical = self.start_monitored(task_name, "historical-v3")
        current_version = receipt.ACTIVE_TASK_CONTRACT_VERSION[task_name]
        current_spec = receipt.TASK_STEP_CONTRACT_REGISTRY[
            (task_name, current_version)
        ]
        next_spec = json.loads(json.dumps(current_spec))
        next_spec["expected_steps"] = tuple(
            tuple(row) for row in next_spec["expected_steps"]
        )
        next_spec["version"] = "daily-runner-v4-test"
        current_commands = receipt.TASK_STEP_COMMAND_REGISTRY[
            (task_name, current_version)
        ]
        next_commands = {
            step_id: tuple(command)
            for step_id, command in current_commands.items()
        }
        with mock.patch.dict(
            receipt.TASK_STEP_CONTRACT_REGISTRY,
            {(task_name, next_spec["version"]): next_spec},
            clear=False,
        ), mock.patch.dict(
            receipt.TASK_STEP_COMMAND_REGISTRY,
            {(task_name, next_spec["version"]): next_commands},
            clear=False,
        ), mock.patch.dict(
            receipt.ACTIVE_TASK_CONTRACT_VERSION,
            {task_name: next_spec["version"]},
            clear=False,
        ):
            receipt._validate_receipt_shape(historical)
            _, fresh = receipt.start_receipt(
                root=self.receipt_root,
                task_name=task_name,
                runner_path=HERE / current_spec["runner_name"],
                log_path=self.log,
                run_id="active-v4",
            )
            self.assertEqual(
                fresh["task_contract"]["version"], "daily-runner-v4-test"
            )

    def test_classifier_mapping_change_without_version_invalidates_binding(self):
        task_name = "ngernduangold_daily"
        _, historical = self.start_monitored(task_name, "classifier-drift")
        classifier_version = historical["task_contract"]["classifier_version"]
        exit_map = receipt.STEP_CLASSIFIER_REGISTRY[classifier_version][
            "contract_exit_maps"
        ]["internal-v1"]
        with mock.patch.dict(exit_map, {"0": "BLOCKED"}, clear=True):
            with self.assertRaisesRegex(
                receipt.ReceiptError, "classifier hash is invalid"
            ):
                receipt._validate_receipt_shape(historical)

    def test_classifier_versions_preserve_historical_receipt_contracts(self):
        self.assertEqual(
            receipt._classifier_hash(1),
            "4bcac846cef25d2892105df14ad564399ef111d7769d65473ac5f51db92d6673",
        )
        self.assertEqual(
            receipt._classifier_hash(2),
            "719faa22cd322c0c886ddeeff1f99f8889772a8cc3a17feb00ff3fb76f2e6bb4",
        )
        self.assertEqual(receipt.STEP_CLASSIFIER_VERSION, 2)
        self.assertEqual(
            receipt.TASK_STEP_CONTRACT_REGISTRY[
                ("ngernduangold_weekly", "weekly-runner-v4")
            ]["classifier_version"],
            1,
        )
        self.assertEqual(
            receipt.TASK_STEP_CONTRACT_REGISTRY[
                ("ngernduangold_daily", "daily-runner-v5")
            ]["classifier_version"],
            1,
        )
        self.assertEqual(
            receipt.TASK_STEP_CONTRACT_REGISTRY[
                ("ngernduangold_daily", "daily-runner-v6")
            ]["classifier_version"],
            2,
        )

    def test_monitored_abort_accepts_only_an_exact_manifest_prefix(self):
        task_name = "ngernduangold_weekly"
        path, _ = self.start_monitored(task_name, "prefix-abort")
        first = receipt.TASK_STEP_CONTRACTS[task_name]["expected_steps"][0]
        receipt.record_step(
            root=self.receipt_root,
            task_name=task_name,
            run_id="prefix-abort",
            step_id=first[0],
            wrapper=first[1],
            contract=first[2],
            raw_rc=0,
        )
        final = receipt.finish_receipt(
            root=self.receipt_root,
            task_name=task_name,
            run_id="prefix-abort",
            terminal_kind="abort",
            terminal_reason="working_directory_failed",
            terminal_step_id=None,
            publication_state="BLOCKED_LOCAL_ONLY",
            final_rc=3,
        )
        self.assertEqual(final["status"], "ABORTED")
        self.assertEqual(final["execution_state"], "RUNNER_FAILED")
        self.assertEqual(len(final["steps"]), 1)
        self.assertEqual(self.load(path), final)

    def test_resealed_forged_task_contract_and_extra_step_fail_closed(self):
        task_name = "ngernduangold_daily"
        _, document = self.start_monitored(task_name, "forged-contract")
        forged = json.loads(json.dumps(document))
        forged["task_contract"]["expected_steps"].pop()
        forged["task_contract"]["manifest_hash"] = receipt._hash_value(
            receipt._task_contract_unsigned(forged["task_contract"])
        )
        with self.assertRaisesRegex(
            receipt.ReceiptError, "task contract is not canonical"
        ):
            receipt._validate_receipt_shape(receipt.seal_receipt(forged))

        self.start_monitored(task_name, "extra-step")
        self.record_full_manifest(task_name, "extra-step")
        with self.assertRaisesRegex(
            receipt.ReceiptError, "task contract has no remaining step"
        ):
            receipt.record_step(
                root=self.receipt_root,
                task_name=task_name,
                run_id="extra-step",
                step_id="unexpected_tail",
                wrapper="required",
                contract="generic",
                raw_rc=0,
            )

    def test_monitored_start_rejects_unregistered_runner_hash(self):
        task_name = "ngernduangold_daily"
        runner = HERE / receipt.TASK_STEP_CONTRACTS[task_name]["runner_name"]
        tool_hash = receipt._file_hash(SCRIPT)
        with mock.patch.object(
            receipt, "_file_hash", side_effect=["0" * 64, tool_hash]
        ):
            with self.assertRaisesRegex(
                receipt.ReceiptError, "runner hash is not registered"
            ):
                receipt.start_receipt(
                    root=self.receipt_root,
                    task_name=task_name,
                    runner_path=runner,
                    log_path=self.log,
                    run_id="unknown-runner",
                )

    def test_cli_finish_propagates_sealed_terminal_classification(self):
        cases = (
            ("blocked", 2, "COMPLETED_BLOCKED", receipt.CLI_COMPLETED_BLOCKED),
            ("runner-failed", 1, "RUNNER_FAILED", receipt.CLI_RUNNER_FAILED),
        )
        for run_id, child_rc, expected_state, expected_process_rc in cases:
            with self.subTest(run_id=run_id):
                self.start(run_id)
                execute = self.cli(
                    "exec",
                    "--root", self.receipt_root,
                    "--task", self.task,
                    "--run-id", run_id,
                    "--step", "media_gate",
                    "--wrapper", "required",
                    "--contract", "block-on-2-v1",
                    "--",
                    sys.executable,
                    "-c",
                    "raise SystemExit(%d)" % child_rc,
                )
                self.assertEqual(execute.returncode, child_rc, execute.stderr)
                finish = self.cli(
                    "finish",
                    "--root", self.receipt_root,
                    "--task", self.task,
                    "--run-id", run_id,
                    "--terminal", "abort",
                    "--terminal-reason", "step_nonzero",
                    "--terminal-step", "media_gate",
                    "--publication-state", "BLOCKED_LOCAL_ONLY",
                    "--final-rc", "2",
                )
                self.assertEqual(finish.returncode, expected_process_rc, finish.stderr)
                path = receipt.receipt_path(self.receipt_root, self.task, run_id)
                document = self.load(path)
                self.assertTrue(receipt.verify_receipt(document))
                self.assertEqual(document["execution_state"], expected_state)

    def test_child_receives_exact_private_runner_identity(self):
        self.start("identity-run")
        completed = subprocess.CompletedProcess(["child"], 0)
        with mock.patch.object(
            receipt.subprocess, "run", return_value=completed
        ) as runner:
            result = receipt.execute_step(
                root=self.receipt_root,
                task_name=self.task,
                run_id="identity-run",
                step_id="identity_child",
                wrapper="required",
                contract="generic",
                command=["child"],
            )
        self.assertEqual(result, 0)
        environment = runner.call_args.kwargs["env"]
        self.assertEqual(environment["NGERNDUANGOLD_TASK_NAME"], self.task)
        self.assertEqual(
            environment["NGERNDUANGOLD_TASK_RUN_ID"], "identity-run"
        )

    def test_atomic_replace_failure_preserves_prior_receipt(self):
        path, document = self.start()
        before = path.read_bytes()
        changed = receipt.seal_receipt({**document, "status": "BROKEN"})
        with mock.patch.object(receipt.os, "replace", side_effect=OSError("blocked")):
            with self.assertRaises(OSError):
                receipt._atomic_write(path, changed)
        self.assertEqual(path.read_bytes(), before)
        self.assertFalse(list(path.parent.glob(f".{path.name}.*.tmp")))

    def test_terminal_receipt_rejects_duplicate_finish_and_new_step(self):
        path, _ = self.start()
        receipt.record_step(
            root=self.receipt_root,
            task_name=self.task,
            run_id="test-run",
            step_id="first",
            wrapper="required",
            contract="generic",
            raw_rc=0,
        )
        receipt.finish_receipt(
            root=self.receipt_root,
            task_name=self.task,
            run_id="test-run",
            terminal_kind="end",
            terminal_reason="normal_end",
            terminal_step_id=None,
            publication_state="BLOCKED_LOCAL_ONLY",
            final_rc=0,
        )
        terminal_bytes = path.read_bytes()
        duplicate = self.cli(
            "finish",
            "--root", self.receipt_root,
            "--task", self.task,
            "--run-id", "test-run",
            "--terminal", "end",
            "--terminal-reason", "normal_end",
            "--publication-state", "BLOCKED_LOCAL_ONLY",
            "--final-rc", "0",
        )
        self.assertEqual(duplicate.returncode, receipt.CLI_EVIDENCE_ERROR)
        append = self.cli(
            "record",
            "--root", self.receipt_root,
            "--task", self.task,
            "--run-id", "test-run",
            "--step", "late",
            "--raw-rc", "0",
        )
        self.assertEqual(append.returncode, receipt.CLI_EVIDENCE_ERROR)
        self.assertEqual(path.read_bytes(), terminal_bytes)

    def test_hash_tampering_blocks_transition(self):
        path, document = self.start()
        document["status"] = "FORGED"
        path.write_text(json.dumps(document), encoding="utf-8")
        result = self.cli(
            "record",
            "--root", self.receipt_root,
            "--task", self.task,
            "--run-id", "test-run",
            "--step", "forbidden",
            "--raw-rc", "0",
        )
        self.assertEqual(result.returncode, receipt.CLI_EVIDENCE_ERROR)
        self.assertIn("hash mismatch", result.stderr)

    def test_self_consistent_malformed_receipt_fails_cli_closed(self):
        path, document = self.start("malformed-shape")
        document.pop("runner")
        path.write_text(
            json.dumps(receipt.seal_receipt(document)), encoding="utf-8"
        )
        result = self.cli(
            "finish",
            "--root", self.receipt_root,
            "--task", self.task,
            "--run-id", "malformed-shape",
            "--terminal", "end",
            "--terminal-reason", "normal_end",
            "--publication-state", "BLOCKED_LOCAL_ONLY",
            "--final-rc", "0",
        )
        self.assertEqual(result.returncode, receipt.CLI_EVIDENCE_ERROR)
        self.assertIn("schema is missing", result.stderr)

    def test_self_consistent_forged_step_classification_fails_closed(self):
        path, document = self.start("forged-step")
        now = receipt._utc_now()
        document["steps"] = [{
            "sequence": 1,
            "step_id": "forged_failure",
            "wrapper": "required",
            "contract": "zero-only-v1",
            "evidence_mode": "record",
            "started_at": now,
            "finished_at": now,
            "duration_ms": 0,
            "raw_rc": 3,
            "semantic_state": "PASS",
            "execution_valid": True,
            "classification_basis": "zero-only-v1",
        }]
        document["transition_counter"] = 1
        path.write_text(
            json.dumps(receipt.seal_receipt(document)), encoding="utf-8"
        )
        result = self.cli(
            "finish",
            "--root", self.receipt_root,
            "--task", self.task,
            "--run-id", "forged-step",
            "--terminal", "end",
            "--terminal-reason", "normal_end",
            "--publication-state", "BLOCKED_LOCAL_ONLY",
            "--final-rc", "0",
        )
        self.assertEqual(result.returncode, receipt.CLI_EVIDENCE_ERROR)
        self.assertIn("classification is inconsistent", result.stderr)

    def test_self_consistent_invalid_chronology_fails_closed(self):
        mutations = (
            ("malformed-start", lambda document: document.update(started_at="not-a-time")),
            (
                "future-start",
                lambda document: document.update(
                    started_at=(
                        dt.datetime.now(dt.timezone.utc) + dt.timedelta(hours=1)
                    ).isoformat()
                ),
            ),
        )
        for run_id, mutate in mutations:
            with self.subTest(run_id=run_id):
                path, document = self.start(run_id)
                mutate(document)
                path.write_text(
                    json.dumps(receipt.seal_receipt(document)), encoding="utf-8"
                )
                result = self.cli(
                    "finish",
                    "--root", self.receipt_root,
                    "--task", self.task,
                    "--run-id", run_id,
                    "--terminal", "end",
                    "--terminal-reason", "normal_end",
                    "--publication-state", "BLOCKED_LOCAL_ONLY",
                    "--final-rc", "0",
                )
                self.assertEqual(result.returncode, receipt.CLI_EVIDENCE_ERROR)

    def test_finish_revalidates_the_new_terminal_chronology(self):
        path, document = self.start("near-future-start")
        document["started_at"] = (
            dt.datetime.now(dt.timezone.utc) + dt.timedelta(minutes=4)
        ).isoformat()
        path.write_text(
            json.dumps(receipt.seal_receipt(document)), encoding="utf-8"
        )
        result = self.cli(
            "finish",
            "--root", self.receipt_root,
            "--task", self.task,
            "--run-id", "near-future-start",
            "--terminal", "end",
            "--terminal-reason", "normal_end",
            "--publication-state", "BLOCKED_LOCAL_ONLY",
            "--final-rc", "0",
        )
        self.assertEqual(result.returncode, receipt.CLI_EVIDENCE_ERROR)
        persisted = self.load(path)
        self.assertEqual(persisted["status"], "RUNNING")
        self.assertIsNone(persisted["finished_at"])

    def test_duplicate_and_nonfinite_receipt_json_fail_closed(self):
        cases = (
            (
                "duplicate-json",
                lambda value: value.replace(
                    f'"schema_version": {receipt.SCHEMA_VERSION},',
                    (
                        f'"schema_version": {receipt.SCHEMA_VERSION}, '
                        f'"schema_version": {receipt.SCHEMA_VERSION},'
                    ),
                    1,
                ),
            ),
            (
                "nonfinite-json",
                lambda value: value.replace(
                    '"transition_counter": 0', '"transition_counter": NaN', 1
                ),
            ),
        )
        for run_id, mutate in cases:
            with self.subTest(run_id=run_id):
                path, _ = self.start(run_id)
                path.write_text(mutate(path.read_text(encoding="utf-8")), encoding="utf-8")
                result = self.cli(
                    "record",
                    "--root", self.receipt_root,
                    "--task", self.task,
                    "--run-id", run_id,
                    "--step", "must_not_append",
                    "--raw-rc", "0",
                )
                self.assertEqual(result.returncode, receipt.CLI_EVIDENCE_ERROR)

    def test_self_hashed_overflow_number_in_extra_field_fails_closed(self):
        path, document = self.start("overflow-extra")
        document["extra_evidence"] = {"nested": [float("inf")]}
        sealed = receipt.seal_receipt(document)
        encoded = json.dumps(sealed, ensure_ascii=False, sort_keys=True)
        encoded = encoded.replace("Infinity", "1e999")
        path.write_text(encoded, encoding="utf-8")

        permissive = json.loads(encoded)
        self.assertTrue(receipt.verify_receipt(permissive))
        result = receipt.main([
            "record", "--root", str(self.receipt_root),
            "--task", self.task,
            "--run-id", "overflow-extra",
            "--step", "must_not_append",
            "--raw-rc", "0",
        ])
        self.assertEqual(result, receipt.CLI_EVIDENCE_ERROR)
        self.assertEqual(self.load(path)["status"], "RUNNING")

    def test_inflight_step_cannot_overwrite_a_finished_receipt(self):
        path, _ = self.start("transition-race")
        original_atomic = receipt._atomic_write
        staged = threading.Event()
        release = threading.Event()
        append_errors = []

        def pause_step_commit(selected_path, value):
            if (
                value.get("status") == "RUNNING"
                and len(value.get("steps", [])) == 1
                and not staged.is_set()
            ):
                staged.set()
                release.wait(5)
            return original_atomic(selected_path, value)

        def append_step():
            try:
                receipt.record_step(
                    root=self.receipt_root,
                    task_name=self.task,
                    run_id="transition-race",
                    step_id="inflight",
                    wrapper="required",
                    contract="generic",
                    raw_rc=0,
                )
            except Exception as exc:  # pragma: no cover - asserted below
                append_errors.append(exc)

        with mock.patch.object(
            receipt, "_atomic_write", side_effect=pause_step_commit
        ):
            worker = threading.Thread(target=append_step)
            worker.start()
            self.assertTrue(staged.wait(5))
            try:
                close_rc = receipt.main([
                    "finish", "--root", str(self.receipt_root),
                    "--task", self.task,
                    "--run-id", "transition-race",
                    "--terminal", "end",
                    "--terminal-reason", "normal_end",
                    "--publication-state", "BLOCKED_LOCAL_ONLY",
                    "--final-rc", "0",
                ])
            finally:
                release.set()
                worker.join(5)

        persisted = self.load(path)
        self.assertEqual(close_rc, receipt.CLI_EVIDENCE_ERROR)
        self.assertFalse(append_errors)
        self.assertFalse(worker.is_alive())
        self.assertEqual(persisted["status"], "RUNNING")
        self.assertEqual([row["step_id"] for row in persisted["steps"]], ["inflight"])

        final = receipt.finish_receipt(
            root=self.receipt_root,
            task_name=self.task,
            run_id="transition-race",
            terminal_kind="end",
            terminal_reason="normal_end",
            terminal_step_id=None,
            publication_state="BLOCKED_LOCAL_ONLY",
            final_rc=0,
        )
        self.assertEqual(final["execution_state"], "PASS")
        self.assertEqual(self.load(path), final)

    def test_transition_lease_blocks_a_second_process(self):
        path, _ = self.start("cross-process-lease")
        holder_code = (
            "from pathlib import Path\n"
            "import sys\n"
            "from pipeline import task_run_receipt as receipt\n"
            "with receipt._receipt_transition_lease(Path(sys.argv[1])):\n"
            "    print('READY', flush=True)\n"
            "    sys.stdin.readline()\n"
        )
        holder = subprocess.Popen(
            [sys.executable, "-c", holder_code, str(path)],
            cwd=str(ROOT),
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )

        def cleanup_holder():
            if holder.poll() is None:
                holder.kill()
                holder.wait(timeout=5)
            for stream in (holder.stdin, holder.stdout, holder.stderr):
                if stream is not None and not stream.closed:
                    stream.close()

        self.addCleanup(cleanup_holder)
        self.assertEqual(holder.stdout.readline().strip(), "READY")
        blocked = self.cli(
            "record",
            "--root", self.receipt_root,
            "--task", self.task,
            "--run-id", "cross-process-lease",
            "--step", "must_not_append",
            "--raw-rc", "0",
        )
        self.assertEqual(blocked.returncode, receipt.CLI_EVIDENCE_ERROR)
        self.assertIn("transition lease is unavailable", blocked.stderr)
        self.assertEqual(self.load(path)["steps"], [])

        holder.stdin.write("\n")
        holder.stdin.flush()
        holder.wait(timeout=5)
        self.assertEqual(holder.returncode, 0, holder.stderr.read())
        receipt.record_step(
            root=self.receipt_root,
            task_name=self.task,
            run_id="cross-process-lease",
            step_id="after_release",
            wrapper="required",
            contract="generic",
            raw_rc=0,
        )
        self.assertEqual(self.load(path)["steps"][0]["step_id"], "after_release")

    def test_transition_lease_retries_a_transient_os_lock_failure(self):
        path, _ = self.start("transient-transition-lock")
        original_acquire = receipt._acquire_transition_byte_lock
        attempts = 0

        def fail_once(handle):
            nonlocal attempts
            attempts += 1
            if attempts == 1:
                raise OSError("synthetic transient lock hand-off")
            return original_acquire(handle)

        with mock.patch.object(
            receipt, "_acquire_transition_byte_lock", side_effect=fail_once
        ):
            receipt.record_step(
                root=self.receipt_root,
                task_name=self.task,
                run_id="transient-transition-lock",
                step_id="after_transient_lock",
                wrapper="required",
                contract="generic",
                raw_rc=0,
            )

        self.assertEqual(attempts, 2)
        persisted = self.load(path)
        self.assertEqual(persisted["transition_counter"], 1)
        self.assertEqual(
            [step["step_id"] for step in persisted["steps"]],
            ["after_transient_lock"],
        )

    def test_transition_lease_serializes_duplicate_start_identity(self):
        original_atomic = receipt._atomic_write
        staged = threading.Event()
        release = threading.Event()
        start_errors = []

        def pause_initial_commit(selected_path, value):
            if value.get("run_id") == "duplicate-start" and not staged.is_set():
                staged.set()
                release.wait(5)
            return original_atomic(selected_path, value)

        def first_start():
            try:
                receipt.start_receipt(
                    root=self.receipt_root,
                    task_name=self.task,
                    runner_path=self.runner,
                    log_path=self.log,
                    run_id="duplicate-start",
                )
            except Exception as exc:  # pragma: no cover - asserted below
                start_errors.append(exc)

        with mock.patch.object(
            receipt, "_atomic_write", side_effect=pause_initial_commit
        ):
            worker = threading.Thread(target=first_start)
            worker.start()
            self.assertTrue(staged.wait(5))
            try:
                with self.assertRaisesRegex(
                    receipt.ReceiptError, "transition is already active"
                ):
                    receipt.start_receipt(
                        root=self.receipt_root,
                        task_name=self.task,
                        runner_path=self.runner,
                        log_path=self.log,
                        run_id="duplicate-start",
                    )
            finally:
                release.set()
                worker.join(5)

        path = receipt.receipt_path(
            self.receipt_root, self.task, "duplicate-start"
        )
        self.assertFalse(start_errors)
        self.assertFalse(worker.is_alive())
        self.assertEqual(self.load(path)["status"], "RUNNING")

    def test_cli_argument_error_uses_reserved_evidence_failure_code(self):
        result = self.cli("record", "--task", self.task)
        self.assertEqual(result.returncode, receipt.CLI_EVIDENCE_ERROR)
        self.assertIn("invalid CLI arguments", result.stderr)

    def test_calendar_block_is_execution_valid_but_not_pass(self):
        path, _ = self.start()
        receipt.record_step(
            root=self.receipt_root,
            task_name=self.task,
            run_id="test-run",
            step_id="calendar",
            wrapper="graded",
            contract="calendar-v1",
            raw_rc=2,
        )
        final = receipt.finish_receipt(
            root=self.receipt_root,
            task_name=self.task,
            run_id="test-run",
            terminal_kind="end",
            terminal_reason="normal_end",
            terminal_step_id=None,
            publication_state="BLOCKED_LOCAL_ONLY",
            final_rc=2,
        )
        self.assertEqual(final["execution_state"], "COMPLETED_WITH_BLOCKERS")
        self.assertEqual(final["steps"][0]["semantic_state"], "BLOCKED")
        self.assertIs(final["steps"][0]["execution_valid"], True)
        self.assertEqual(self.load(path)["final_rc"], 2)

    def test_queue_agent_block_is_explicit_and_not_a_publish_contract(self):
        classified = receipt.classify_step(
            "required", "queue-agent-v1", 2
        )
        self.assertEqual(classified["semantic_state"], "BLOCKED")
        self.assertIs(classified["execution_valid"], True)

    def test_novelty_queue_contract_distinguishes_skip_block_and_failures(self):
        cases = (
            (0, "PASS", True),
            (10, "SKIP", True),
            (20, "BLOCKED", True),
            (1, "RUNNER_FAILED", False),
            (2, "RUNNER_FAILED", False),
            (3, "RUNNER_FAILED", False),
        )
        for raw_rc, state, valid in cases:
            with self.subTest(raw_rc=raw_rc):
                classified = receipt.classify_step(
                    "required", "novelty-queue-v1", raw_rc
                )
                self.assertEqual(classified["semantic_state"], state)
                self.assertIs(classified["execution_valid"], valid)

    def test_schema3_novelty_skip_is_pass_but_unknown_is_a_blocker(self):
        task_name = "ngernduangold_daily"
        path, _ = self.start_monitored(task_name, "novelty-skip")
        self.record_full_manifest(
            task_name,
            "novelty-skip",
            {"dispatcher": 10, "daily_content": 10},
        )
        skipped = receipt.finish_receipt(
            root=self.receipt_root,
            task_name=task_name,
            run_id="novelty-skip",
            terminal_kind="end",
            terminal_reason="normal_end",
            terminal_step_id=None,
            publication_state="BLOCKED_LOCAL_ONLY",
            final_rc=0,
        )
        novelty_steps = {
            step["step_id"]: step for step in skipped["steps"]
            if step["step_id"] in {"dispatcher", "daily_content"}
        }
        self.assertEqual(skipped["execution_state"], "PASS")
        self.assertEqual(
            {step["semantic_state"] for step in novelty_steps.values()},
            {"SKIP"},
        )
        self.assertTrue(receipt.verify_receipt(self.load(path)))

        path, _ = self.start_monitored(task_name, "novelty-blocked")
        self.record_full_manifest(
            task_name,
            "novelty-blocked",
            {"dispatcher": 20, "daily_content": 10},
        )
        blocked = receipt.finish_receipt(
            root=self.receipt_root,
            task_name=task_name,
            run_id="novelty-blocked",
            terminal_kind="end",
            terminal_reason="normal_end",
            terminal_step_id=None,
            publication_state="BLOCKED_LOCAL_ONLY",
            final_rc=2,
        )
        self.assertEqual(blocked["execution_state"], "COMPLETED_WITH_BLOCKERS")
        self.assertEqual(
            next(
                step for step in blocked["steps"]
                if step["step_id"] == "dispatcher"
            )["semantic_state"],
            "BLOCKED",
        )
        self.assertTrue(receipt.verify_receipt(self.load(path)))

    def test_improvement_loop_contract_separates_block_from_runner_failure(self):
        blocked = receipt.classify_step(
            "required", "improvement-loop-v1", 2
        )
        failed = receipt.classify_step(
            "required", "improvement-loop-v1", 3
        )
        self.assertEqual(blocked["semantic_state"], "BLOCKED")
        self.assertIs(blocked["execution_valid"], True)
        self.assertEqual(failed["semantic_state"], "RUNNER_FAILED")
        self.assertIs(failed["execution_valid"], False)

    def test_named_runner_contracts_classify_expected_nonzero_states(self):
        cases = (
            ("scan-on-1-v1", 0, "PASS_OR_SKIP", True),
            ("scan-on-1-v1", 1, "BLOCKED", True),
            ("scan-on-1-v1", 3, "RUNNER_FAILED", False),
            ("validation-on-1-v1", 1, "BLOCKED", True),
            ("privacy-guard-v1", 1, "BLOCKED", True),
            ("privacy-guard-v1", 2, "RUNNER_FAILED", False),
            ("review-or-block-v1", 1, "REVIEW_REQUIRED", True),
            ("review-or-block-v1", 2, "BLOCKED", True),
            ("official-news-v1", 1, "REVIEW_REQUIRED", True),
            ("official-news-v1", 2, "BLOCKED", True),
            ("official-news-v1", 3, "RUNNER_FAILED", False),
            ("block-on-2-v1", 2, "BLOCKED", True),
            ("block-on-2-v1", 3, "RUNNER_FAILED", False),
            ("zero-only-v1", 1, "RUNNER_FAILED", False),
        )
        for contract, raw_rc, state, valid in cases:
            with self.subTest(contract=contract, raw_rc=raw_rc):
                classified = receipt.classify_step("required", contract, raw_rc)
                self.assertEqual(classified["semantic_state"], state)
                self.assertIs(classified["execution_valid"], valid)

    def test_unclassified_nonzero_never_becomes_success(self):
        _, _ = self.start()
        receipt.record_step(
            root=self.receipt_root,
            task_name=self.task,
            run_id="test-run",
            step_id="ambiguous",
            wrapper="required",
            contract="generic",
            raw_rc=2,
        )
        final = receipt.finish_receipt(
            root=self.receipt_root,
            task_name=self.task,
            run_id="test-run",
            terminal_kind="end",
            terminal_reason="normal_end",
            terminal_step_id=None,
            publication_state="BLOCKED_LOCAL_ONLY",
            final_rc=2,
        )
        self.assertEqual(final["execution_state"], "UNVERIFIED_NONZERO")
        self.assertEqual(final["steps"][0]["semantic_state"], "NONZERO_UNCLASSIFIED")
        self.assertIsNone(final["steps"][0]["execution_valid"])

    def test_abort_is_runner_failed_even_when_last_step_passed(self):
        self.start()
        receipt.record_step(
            root=self.receipt_root,
            task_name=self.task,
            run_id="test-run",
            step_id="before_abort",
            wrapper="required",
            contract="generic",
            raw_rc=0,
        )
        final = receipt.finish_receipt(
            root=self.receipt_root,
            task_name=self.task,
            run_id="test-run",
            terminal_kind="abort",
            terminal_reason="unclassified_abort",
            terminal_step_id=None,
            publication_state="BLOCKED_LOCAL_ONLY",
            final_rc=2,
        )
        self.assertEqual(final["status"], "ABORTED")
        self.assertEqual(final["execution_state"], "RUNNER_FAILED")

    def test_abort_bound_to_verified_block_is_completed_blocked(self):
        self.start()
        receipt.record_step(
            root=self.receipt_root,
            task_name=self.task,
            run_id="test-run",
            step_id="media_gate",
            wrapper="required",
            contract="block-on-2-v1",
            raw_rc=2,
        )
        final = receipt.finish_receipt(
            root=self.receipt_root,
            task_name=self.task,
            run_id="test-run",
            terminal_kind="abort",
            terminal_reason="step_nonzero",
            terminal_step_id="media_gate",
            publication_state="BLOCKED_LOCAL_ONLY",
            final_rc=2,
        )
        self.assertEqual(final["status"], "ABORTED")
        self.assertEqual(final["execution_state"], "COMPLETED_BLOCKED")

    def test_runner_failure_accumulator_dominates_verified_block(self):
        cases = (
            ("end", 3),
            ("end", 90),
            ("end", -1),
            ("abort", 3),
            ("abort", 90),
            ("abort", -1),
        )
        for index, (terminal_kind, final_rc) in enumerate(cases):
            run_id = "dominates-%d" % index
            with self.subTest(terminal_kind=terminal_kind, final_rc=final_rc):
                self.start(run_id)
                receipt.record_step(
                    root=self.receipt_root,
                    task_name=self.task,
                    run_id=run_id,
                    step_id="media_gate",
                    wrapper="required",
                    contract="block-on-2-v1",
                    raw_rc=2,
                )
                final = receipt.finish_receipt(
                    root=self.receipt_root,
                    task_name=self.task,
                    run_id=run_id,
                    terminal_kind=terminal_kind,
                    terminal_reason=(
                        "normal_end" if terminal_kind == "end" else "step_nonzero"
                    ),
                    terminal_step_id=(
                        None if terminal_kind == "end" else "media_gate"
                    ),
                    publication_state="BLOCKED_LOCAL_ONLY",
                    final_rc=final_rc,
                )
                self.assertEqual(final["execution_state"], "RUNNER_FAILED")
                self.assertEqual(
                    receipt.terminal_process_code(final), receipt.CLI_RUNNER_FAILED
                )

    def test_zero_accumulator_cannot_hide_a_verified_block(self):
        self.start("zero-blocker")
        receipt.record_step(
            root=self.receipt_root,
            task_name=self.task,
            run_id="zero-blocker",
            step_id="media_gate",
            wrapper="required",
            contract="block-on-2-v1",
            raw_rc=2,
        )
        final = receipt.finish_receipt(
            root=self.receipt_root,
            task_name=self.task,
            run_id="zero-blocker",
            terminal_kind="end",
            terminal_reason="normal_end",
            terminal_step_id=None,
            publication_state="BLOCKED_LOCAL_ONLY",
            final_rc=0,
        )
        self.assertEqual(final["execution_state"], "RUNNER_FAILED")
        self.assertEqual(receipt.terminal_process_code(final), receipt.CLI_RUNNER_FAILED)

    def test_abort_bound_to_unclassified_nonzero_remains_unverified(self):
        self.start()
        receipt.record_step(
            root=self.receipt_root,
            task_name=self.task,
            run_id="test-run",
            step_id="unknown_contract",
            wrapper="required",
            contract="generic",
            raw_rc=2,
        )
        final = receipt.finish_receipt(
            root=self.receipt_root,
            task_name=self.task,
            run_id="test-run",
            terminal_kind="abort",
            terminal_reason="step_nonzero",
            terminal_step_id="unknown_contract",
            publication_state="BLOCKED_LOCAL_ONLY",
            final_rc=2,
        )
        self.assertEqual(final["execution_state"], "UNVERIFIED_NONZERO")

    def test_step_abort_must_name_the_exact_last_step(self):
        self.start()
        receipt.record_step(
            root=self.receipt_root,
            task_name=self.task,
            run_id="test-run",
            step_id="media_gate",
            wrapper="required",
            contract="block-on-2-v1",
            raw_rc=2,
        )
        with self.assertRaises(receipt.ReceiptError):
            receipt.finish_receipt(
                root=self.receipt_root,
                task_name=self.task,
                run_id="test-run",
                terminal_kind="abort",
                terminal_reason="step_nonzero",
                terminal_step_id="different_step",
                publication_state="BLOCKED_LOCAL_ONLY",
                final_rc=2,
            )

    def test_runner_hash_change_during_run_fails_closed(self):
        self.start()
        receipt.record_step(
            root=self.receipt_root,
            task_name=self.task,
            run_id="test-run",
            step_id="before_change",
            wrapper="required",
            contract="generic",
            raw_rc=0,
        )
        self.runner.write_text("@echo off\r\nexit /b 2\r\n", encoding="utf-8")
        final = receipt.finish_receipt(
            root=self.receipt_root,
            task_name=self.task,
            run_id="test-run",
            terminal_kind="end",
            terminal_reason="normal_end",
            terminal_step_id=None,
            publication_state="BLOCKED_LOCAL_ONLY",
            final_rc=0,
        )
        self.assertIs(final["runner"]["stable_during_run"], False)
        self.assertEqual(final["execution_state"], "RUNNER_FAILED")

    def test_receipt_tool_hash_change_during_run_fails_closed(self):
        self.start()
        receipt.record_step(
            root=self.receipt_root,
            task_name=self.task,
            run_id="test-run",
            step_id="before_change",
            wrapper="required",
            contract="generic",
            raw_rc=0,
        )
        original_hash = receipt._file_hash

        def changed_tool_hash(path):
            if Path(path).resolve(strict=False) == Path(receipt.__file__).resolve():
                return "0" * 64
            return original_hash(path)

        with mock.patch.object(receipt, "_file_hash", side_effect=changed_tool_hash):
            final = receipt.finish_receipt(
                root=self.receipt_root,
                task_name=self.task,
                run_id="test-run",
                terminal_kind="end",
                terminal_reason="normal_end",
                terminal_step_id=None,
                publication_state="BLOCKED_LOCAL_ONLY",
                final_rc=0,
            )
        self.assertIs(final["receipt_tool"]["stable_during_run"], False)
        self.assertEqual(final["execution_state"], "RUNNER_FAILED")

    def test_finish_rechecks_runner_hash_at_commit_boundary(self):
        self.start("commit-drift")
        original_hash = receipt._file_hash
        first_runner_end = True

        def drift_after_first_runner_end(path):
            nonlocal first_runner_end
            value = original_hash(path)
            if Path(path).resolve() == self.runner.resolve() and first_runner_end:
                first_runner_end = False
                self.runner.write_text(
                    "@echo off\r\nexit /b 3\r\n", encoding="utf-8"
                )
            return value

        with mock.patch.object(
            receipt, "_file_hash", side_effect=drift_after_first_runner_end
        ):
            final = receipt.finish_receipt(
                root=self.receipt_root,
                task_name=self.task,
                run_id="commit-drift",
                terminal_kind="end",
                terminal_reason="normal_end",
                terminal_step_id=None,
                publication_state="BLOCKED_LOCAL_ONLY",
                final_rc=0,
            )
        self.assertEqual(final["execution_state"], "RUNNER_FAILED")
        self.assertIs(final["runner"]["stable_during_run"], False)
        self.assertEqual(final["runner"]["sha256_end"], original_hash(self.runner))
        self.assertEqual(receipt.terminal_process_code(final), receipt.CLI_RUNNER_FAILED)

    def test_finish_rechecks_runner_hash_after_atomic_commit(self):
        self.start("post-commit-drift")
        original_atomic = receipt._atomic_write
        terminal_writes = 0

        def mutate_after_terminal_write(path, value):
            nonlocal terminal_writes
            original_atomic(path, value)
            if value.get("status") in receipt.TERMINAL_STATUSES:
                terminal_writes += 1
                if terminal_writes == 1:
                    self.runner.write_text(
                        "@echo off\r\nexit /b 3\r\n", encoding="utf-8"
                    )

        with mock.patch.object(
            receipt, "_atomic_write", side_effect=mutate_after_terminal_write
        ):
            final = receipt.finish_receipt(
                root=self.receipt_root,
                task_name=self.task,
                run_id="post-commit-drift",
                terminal_kind="end",
                terminal_reason="normal_end",
                terminal_step_id=None,
                publication_state="BLOCKED_LOCAL_ONLY",
                final_rc=0,
            )
        self.assertEqual(terminal_writes, 2)
        self.assertEqual(final["execution_state"], "RUNNER_FAILED")
        self.assertIs(final["runner"]["stable_during_run"], False)
        self.assertEqual(receipt.terminal_process_code(final), receipt.CLI_RUNNER_FAILED)

    def test_post_commit_drift_repair_failure_invalidates_prior_pass(self):
        path, _ = self.start("post-commit-repair-failure")
        original_atomic = receipt._atomic_write
        terminal_writes = 0

        def fail_corrective_write(selected_path, value):
            nonlocal terminal_writes
            if value.get("status") in receipt.TERMINAL_STATUSES:
                terminal_writes += 1
                if terminal_writes == 1:
                    original_atomic(selected_path, value)
                    self.runner.write_text(
                        "@echo off\r\nexit /b 3\r\n", encoding="utf-8"
                    )
                    return
                raise OSError("simulated corrective write failure")
            original_atomic(selected_path, value)

        with mock.patch.object(
            receipt, "_atomic_write", side_effect=fail_corrective_write
        ):
            result = receipt.main([
                "finish", "--root", str(self.receipt_root),
                "--task", self.task,
                "--run-id", "post-commit-repair-failure",
                "--terminal", "end",
                "--terminal-reason", "normal_end",
                "--publication-state", "BLOCKED_LOCAL_ONLY",
                "--final-rc", "0",
            ])

        self.assertEqual(result, receipt.CLI_EVIDENCE_ERROR)
        self.assertEqual(terminal_writes, 2)
        if path.exists():
            with self.assertRaises((json.JSONDecodeError, UnicodeError)):
                self.load(path)

    def test_post_commit_repair_exception_after_replace_preserves_runner_failure(self):
        path, _ = self.start("post-commit-repair-after-replace")
        original_atomic = receipt._atomic_write
        terminal_writes = 0

        def raise_after_corrective_replace(selected_path, value):
            nonlocal terminal_writes
            if value.get("status") in receipt.TERMINAL_STATUSES:
                terminal_writes += 1
            original_atomic(selected_path, value)
            if terminal_writes == 1:
                self.runner.write_text(
                    "@echo off\r\nexit /b 3\r\n", encoding="utf-8"
                )
            elif terminal_writes == 2:
                raise OSError("ambiguous post-replace failure")

        with mock.patch.object(
            receipt, "_atomic_write", side_effect=raise_after_corrective_replace
        ):
            final = receipt.finish_receipt(
                root=self.receipt_root,
                task_name=self.task,
                run_id="post-commit-repair-after-replace",
                terminal_kind="end",
                terminal_reason="normal_end",
                terminal_step_id=None,
                publication_state="BLOCKED_LOCAL_ONLY",
                final_rc=0,
            )

        persisted = self.load(path)
        self.assertEqual(terminal_writes, 2)
        self.assertEqual(final, persisted)
        self.assertEqual(final["execution_state"], "RUNNER_FAILED")
        self.assertEqual(receipt.terminal_process_code(final), receipt.CLI_RUNNER_FAILED)

    def test_repair_failure_invalidates_runner_failure_with_stale_stability_claim(self):
        path, _ = self.start("post-commit-stale-runner-failure")
        original_atomic = receipt._atomic_write
        terminal_writes = 0

        def fail_corrective_write(selected_path, value):
            nonlocal terminal_writes
            if value.get("status") in receipt.TERMINAL_STATUSES:
                terminal_writes += 1
                if terminal_writes == 1:
                    self.assertEqual(value["execution_state"], "RUNNER_FAILED")
                    self.assertIs(value["runner"]["stable_during_run"], True)
                    original_atomic(selected_path, value)
                    self.runner.write_text(
                        "@echo off\r\nexit /b 3\r\n", encoding="utf-8"
                    )
                    return
                raise OSError("simulated corrective write failure")
            original_atomic(selected_path, value)

        with mock.patch.object(
            receipt, "_atomic_write", side_effect=fail_corrective_write
        ):
            result = receipt.main([
                "finish", "--root", str(self.receipt_root),
                "--task", self.task,
                "--run-id", "post-commit-stale-runner-failure",
                "--terminal", "end",
                "--terminal-reason", "normal_end",
                "--publication-state", "BLOCKED_LOCAL_ONLY",
                "--final-rc", "3",
            ])

        self.assertEqual(result, receipt.CLI_EVIDENCE_ERROR)
        if path.exists():
            with self.assertRaises((json.JSONDecodeError, UnicodeError)):
                self.load(path)

    def test_post_commit_drift_uses_quarantine_when_poison_is_unavailable(self):
        path, _ = self.start("post-commit-quarantine")
        original_atomic = receipt._atomic_write
        original_open = Path.open
        terminal_writes = 0

        def fail_corrective_write(selected_path, value):
            nonlocal terminal_writes
            if value.get("status") in receipt.TERMINAL_STATUSES:
                terminal_writes += 1
                if terminal_writes == 1:
                    original_atomic(selected_path, value)
                    self.runner.write_text(
                        "@echo off\r\nexit /b 3\r\n", encoding="utf-8"
                    )
                    return
                raise OSError("simulated corrective write failure")
            original_atomic(selected_path, value)

        def reject_poison(selected_path, *args, **kwargs):
            mode = args[0] if args else kwargs.get("mode", "r")
            if Path(selected_path) == path and mode == "r+b":
                raise OSError("simulated canonical write denial")
            return original_open(selected_path, *args, **kwargs)

        with mock.patch.object(
            receipt, "_atomic_write", side_effect=fail_corrective_write
        ), mock.patch.object(Path, "open", new=reject_poison):
            result = receipt.main([
                "finish", "--root", str(self.receipt_root),
                "--task", self.task,
                "--run-id", "post-commit-quarantine",
                "--terminal", "end",
                "--terminal-reason", "normal_end",
                "--publication-state", "BLOCKED_LOCAL_ONLY",
                "--final-rc", "0",
            ])

        self.assertEqual(result, receipt.CLI_EVIDENCE_ERROR)
        self.assertFalse(path.exists())
        quarantined = list(path.parent.glob(f".{path.name}.*.untrusted"))
        self.assertEqual(len(quarantined), 1)
        stale = self.load(quarantined[0])
        self.assertEqual(stale["execution_state"], "PASS")

    def test_post_commit_drift_removes_canonical_when_other_revocation_fails(self):
        path, _ = self.start("post-commit-remove")
        original_atomic = receipt._atomic_write
        original_open = Path.open
        original_replace = receipt.os.replace
        terminal_writes = 0

        def fail_corrective_write(selected_path, value):
            nonlocal terminal_writes
            if value.get("status") in receipt.TERMINAL_STATUSES:
                terminal_writes += 1
                if terminal_writes == 1:
                    original_atomic(selected_path, value)
                    self.runner.write_text(
                        "@echo off\r\nexit /b 3\r\n", encoding="utf-8"
                    )
                    return
                raise OSError("simulated corrective write failure")
            original_atomic(selected_path, value)

        def reject_poison(selected_path, *args, **kwargs):
            mode = args[0] if args else kwargs.get("mode", "r")
            if Path(selected_path) == path and mode == "r+b":
                raise OSError("simulated canonical write denial")
            return original_open(selected_path, *args, **kwargs)

        def reject_quarantine(source, target):
            if str(target).endswith(".untrusted"):
                raise OSError("simulated quarantine denial")
            return original_replace(source, target)

        with mock.patch.object(
            receipt, "_atomic_write", side_effect=fail_corrective_write
        ), mock.patch.object(
            Path, "open", new=reject_poison
        ), mock.patch.object(
            receipt.os, "replace", side_effect=reject_quarantine
        ):
            result = receipt.main([
                "finish", "--root", str(self.receipt_root),
                "--task", self.task,
                "--run-id", "post-commit-remove",
                "--terminal", "end",
                "--terminal-reason", "normal_end",
                "--publication-state", "BLOCKED_LOCAL_ONLY",
                "--final-rc", "0",
            ])

        self.assertEqual(result, receipt.CLI_EVIDENCE_ERROR)
        self.assertFalse(path.exists())
        self.assertFalse(list(path.parent.glob(f".{path.name}.*.untrusted")))

    def test_durable_revocation_blocks_stale_pass_when_all_file_repairs_fail(self):
        path, _ = self.start("post-commit-durable-revocation")
        marker = receipt.receipt_revocation_path(path)
        original_atomic = receipt._atomic_write
        original_open = Path.open
        original_replace = receipt.os.replace
        original_unlink = Path.unlink
        terminal_writes = 0

        def fail_corrective_write(selected_path, value):
            nonlocal terminal_writes
            if value.get("status") in receipt.TERMINAL_STATUSES:
                terminal_writes += 1
                if terminal_writes == 1:
                    original_atomic(selected_path, value)
                    self.runner.write_text(
                        "@echo off\r\nexit /b 3\r\n", encoding="utf-8"
                    )
                    return
                raise OSError("simulated corrective write failure")
            original_atomic(selected_path, value)

        def reject_poison(selected_path, *args, **kwargs):
            mode = args[0] if args else kwargs.get("mode", "r")
            if Path(selected_path) == path and mode == "r+b":
                raise OSError("simulated canonical write denial")
            return original_open(selected_path, *args, **kwargs)

        def reject_quarantine(source, target):
            if str(target).endswith(".untrusted"):
                raise OSError("simulated quarantine denial")
            return original_replace(source, target)

        def reject_canonical_unlink(selected_path, *args, **kwargs):
            if Path(selected_path) == path:
                raise OSError("simulated canonical unlink denial")
            return original_unlink(selected_path, *args, **kwargs)

        with mock.patch.object(
            receipt, "_atomic_write", side_effect=fail_corrective_write
        ), mock.patch.object(
            Path, "open", new=reject_poison
        ), mock.patch.object(
            receipt.os, "replace", side_effect=reject_quarantine
        ), mock.patch.object(
            Path, "unlink", new=reject_canonical_unlink
        ):
            result = receipt.main([
                "finish", "--root", str(self.receipt_root),
                "--task", self.task,
                "--run-id", "post-commit-durable-revocation",
                "--terminal", "end",
                "--terminal-reason", "normal_end",
                "--publication-state", "BLOCKED_LOCAL_ONLY",
                "--final-rc", "0",
            ])

        stale = self.load(path)
        self.assertEqual(result, receipt.CLI_EVIDENCE_ERROR)
        self.assertEqual(stale["execution_state"], "PASS")
        self.assertTrue(receipt.verify_receipt(stale))
        self.assertTrue(marker.exists())
        with self.assertRaisesRegex(receipt.ReceiptError, "commit is revoked"):
            receipt._load_receipt(
                self.receipt_root,
                self.task,
                "post-commit-durable-revocation",
            )

    def test_stale_revocation_marker_prevents_run_identity_reuse(self):
        path = receipt.receipt_path(self.receipt_root, self.task, "revoked-id")
        marker = receipt.receipt_revocation_path(path)
        marker.parent.mkdir(parents=True, exist_ok=True)
        marker.write_bytes(b"partial")
        with self.assertRaisesRegex(receipt.ReceiptError, "commit is revoked"):
            receipt.start_receipt(
                root=self.receipt_root,
                task_name=self.task,
                runner_path=self.runner,
                log_path=self.log,
                run_id="revoked-id",
            )

    def test_revocation_clear_exception_after_unlink_keeps_process_consistent(self):
        path, _ = self.start("ambiguous-revocation-clear")
        marker = receipt.receipt_revocation_path(path)
        original_unlink = Path.unlink

        def unlink_then_raise(selected_path, *args, **kwargs):
            result = original_unlink(selected_path, *args, **kwargs)
            if Path(selected_path) == marker:
                raise OSError("ambiguous post-unlink failure")
            return result

        with mock.patch.object(Path, "unlink", new=unlink_then_raise):
            final = receipt.finish_receipt(
                root=self.receipt_root,
                task_name=self.task,
                run_id="ambiguous-revocation-clear",
                terminal_kind="end",
                terminal_reason="normal_end",
                terminal_step_id=None,
                publication_state="BLOCKED_LOCAL_ONLY",
                final_rc=0,
            )

        self.assertFalse(marker.exists())
        self.assertEqual(final, self.load(path))
        self.assertEqual(final["execution_state"], "PASS")
        self.assertEqual(receipt.terminal_process_code(final), 0)

    def test_log_rotation_is_bounded(self):
        self.log.write_bytes(b"a" * 12)
        Path(f"{self.log}.1").write_bytes(b"older")
        state = receipt.rotate_log(self.log, max_bytes=10, keep=2)
        self.assertEqual(state, "ROTATED")
        self.assertFalse(self.log.exists())
        self.assertEqual(Path(f"{self.log}.1").read_bytes(), b"a" * 12)
        self.assertEqual(Path(f"{self.log}.2").read_bytes(), b"older")

    def test_log_rotation_drops_stale_oldest_generation_across_a_gap(self):
        self.log.write_bytes(b"current payload")
        Path(f"{self.log}.2").write_bytes(b"stale oldest")
        state = receipt.rotate_log(self.log, max_bytes=10, keep=2)
        self.assertEqual(state, "ROTATED")
        self.assertEqual(Path(f"{self.log}.1").read_bytes(), b"current payload")
        self.assertFalse(Path(f"{self.log}.2").exists())

    @unittest.skipUnless(sys.platform == "win32", "batch quoting is Windows-specific")
    def test_batch_for_f_captures_start_run_id(self):
        batch = self.base / "capture.cmd"
        batch.write_text(
            "\r\n".join(
                [
                    "@echo off",
                    "setlocal EnableExtensions EnableDelayedExpansion",
                    f'set "PY={sys.executable}"',
                    f'set "TOOL={SCRIPT}"',
                    f'set "ROOT={self.receipt_root}"',
                    f'set "RUNNER={self.runner}"',
                    f'set "LOG={self.log}"',
                    'set "RID="',
                    'for /f "usebackq delims=" %%R in (`^"^"%PY%" "%TOOL%" start --root "%ROOT%" --task batch_test --runner "%RUNNER%" --log "%LOG%" --run-id batch-run^"`) do if not defined RID set "RID=%%R"',
                    'if not defined RID exit /b 3',
                    'echo !RID!',
                    'exit /b 0',
                    "",
                ]
            ),
            encoding="utf-8",
        )
        result = subprocess.run(
            ["cmd.exe", "/d", "/c", str(batch)],
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), "batch-run")
        self.assertTrue(
            receipt.receipt_path(self.receipt_root, "batch_test", "batch-run").is_file()
        )

    @unittest.skipUnless(sys.platform == "win32", "batch exit propagation is Windows-specific")
    def test_batch_process_exit_matches_sealed_runner_failure(self):
        batch = self.base / "sealed-failure.cmd"
        batch.write_text(
            "\r\n".join(
                [
                    "@echo off",
                    "setlocal EnableExtensions EnableDelayedExpansion",
                    f'set "PY={sys.executable}"',
                    f'set "TOOL={SCRIPT}"',
                    f'set "ROOT={self.receipt_root}"',
                    f'set "LOG={self.log}"',
                    'set "RID=sealed-failure"',
                    'set "RUN_EXIT=0"',
                    '"%PY%" "%TOOL%" start --root "%ROOT%" --task batch_failure --runner "%~f0" --log "%LOG%" --run-id "%RID%" >NUL',
                    'if !errorlevel! NEQ 0 exit /b 3',
                    '"%PY%" "%TOOL%" exec --root "%ROOT%" --task batch_failure --run-id "%RID%" --step media_gate --wrapper required --contract block-on-2-v1 -- "%PY%" -c "raise SystemExit(1)"',
                    'set "STEP_RC=!errorlevel!"',
                    'if !STEP_RC! GEQ 3 set RUN_EXIT=3',
                    'if !STEP_RC! EQU 1 if !RUN_EXIT! LSS 2 set RUN_EXIT=2',
                    '"%PY%" "%TOOL%" finish --root "%ROOT%" --task batch_failure --run-id "%RID%" --terminal abort --terminal-reason step_nonzero --terminal-step media_gate --publication-state BLOCKED_LOCAL_ONLY --final-rc !RUN_EXIT!',
                    'set "CLOSE_RC=!errorlevel!"',
                    'if !CLOSE_RC! EQU 2 if !RUN_EXIT! LSS 2 set RUN_EXIT=2',
                    'if !CLOSE_RC! GEQ 3 set RUN_EXIT=3',
                    'exit /b !RUN_EXIT!',
                    "",
                ]
            ),
            encoding="utf-8",
        )
        result = subprocess.run(
            ["cmd.exe", "/d", "/c", str(batch)],
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(result.returncode, receipt.CLI_RUNNER_FAILED, result.stderr)
        path = receipt.receipt_path(
            self.receipt_root, "batch_failure", "sealed-failure"
        )
        document = self.load(path)
        self.assertTrue(receipt.verify_receipt(document))
        self.assertEqual(document["steps"][-1]["raw_rc"], 1)
        self.assertIs(document["steps"][-1]["execution_valid"], False)
        self.assertEqual(document["execution_state"], "RUNNER_FAILED")


class RunnerWiringTestCase(unittest.TestCase):
    @staticmethod
    def parsed_manifest(name):
        lines = (HERE / name).read_text(encoding="utf-8").splitlines()
        main_lines = lines[:lines.index(":abort")]
        parsed = []
        for index, line in enumerate(main_lines):
            stripped = line.strip()
            match = receipt.re.fullmatch(
                r'call :record_internal "([A-Za-z0-9_.-]+)" .+', stripped
            )
            if match:
                parsed.append((match.group(1), "internal", "internal-v1"))
                continue
            prefix = 'set "STEP_NAME='
            if not stripped.startswith(prefix) or not stripped.endswith('"'):
                continue
            step_id = stripped[len(prefix):-1]
            contract_line = main_lines[index + 1].strip()
            contract_prefix = 'set "STEP_CONTRACT='
            if not (
                contract_line.startswith(contract_prefix)
                and contract_line.endswith('"')
            ):
                raise AssertionError(f"missing contract after {step_id}")
            step_contract = contract_line[len(contract_prefix):-1]
            wrapper = None
            for following in main_lines[index + 2:]:
                candidate = following.strip()
                if candidate.startswith('set "STEP_NAME='):
                    break
                if candidate.startswith(("call :required ", "call :novelty_queue ")):
                    wrapper = "required"
                    break
                if candidate.startswith("call :graded "):
                    wrapper = "graded"
                    break
            if wrapper is None:
                raise AssertionError(f"missing wrapper call for {step_id}")
            parsed.append((step_id, wrapper, step_contract))
        return tuple(parsed)

    @staticmethod
    def parsed_commands(name):
        lines = (HERE / name).read_text(encoding="utf-8").splitlines()
        main_lines = lines[:lines.index(":abort")]
        variables = {}
        for line in main_lines:
            match = receipt.re.fullmatch(
                r'\s*set "([A-Za-z0-9_]+)=(.*)"\s*', line
            )
            if match:
                variables[match.group(1)] = match.group(2)

        def expand(value):
            expanded = value
            for _ in range(len(variables) + 1):
                prior = expanded
                for key, replacement in variables.items():
                    expanded = expanded.replace(f"%{key}%", replacement)
                if expanded == prior:
                    break
            return expanded

        parsed = {}
        for index, line in enumerate(main_lines):
            stripped = line.strip()
            prefix = 'set "STEP_NAME='
            if not stripped.startswith(prefix) or not stripped.endswith('"'):
                continue
            step_id = stripped[len(prefix):-1]
            command_line = None
            for following in main_lines[index + 1:]:
                candidate = following.strip()
                if candidate.startswith('set "STEP_NAME='):
                    break
                if candidate.startswith((
                    "call :required ", "call :novelty_queue ", "call :graded ",
                )):
                    command_line = candidate.split("||", 1)[0].strip()
                    break
            if command_line is None:
                raise AssertionError(f"missing command after {step_id}")
            match = receipt.re.fullmatch(
                r"call :(?:required|novelty_queue|graded)\s+(.+)", command_line
            )
            if not match:
                raise AssertionError(f"malformed command after {step_id}")
            tokens = []
            for token in receipt.re.finditer(r'"([^"]*)"|(\S+)', match.group(1)):
                tokens.append(expand(
                    token.group(1) if token.group(1) is not None else token.group(2)
                ))
            parsed[step_id] = tokens
        return parsed

    def test_registered_runner_hash_and_ordered_manifest_match_the_batch_files(self):
        mapping = {
            "ngernduangold_daily": "run_daily.cmd",
            "ngernduangold_weekly": "run_weekly.cmd",
        }
        for task_name, name in mapping.items():
            with self.subTest(task=task_name):
                spec = receipt.TASK_STEP_CONTRACTS[task_name]
                runner_bytes = (HERE / name).read_bytes()
                self.assertEqual(spec["runner_name"], name)
                self.assertEqual(
                    spec["runner_sha256"],
                    hashlib.sha256(runner_bytes).hexdigest(),
                )
                self.assertEqual(
                    tuple(spec["expected_steps"]), self.parsed_manifest(name)
                )
                parsed_commands = self.parsed_commands(name)
                registered_commands = receipt.TASK_STEP_COMMAND_REGISTRY[
                    (task_name, spec["version"])
                ]
                self.assertEqual(set(parsed_commands), set(registered_commands))
                for step_id, command in registered_commands.items():
                    self.assertEqual(
                        receipt._normalize_command(parsed_commands[step_id]),
                        receipt._normalize_command(command),
                        step_id,
                    )

    def test_runner_receipt_wiring_precedes_first_guard_and_covers_wrappers(self):
        for name in ("run_daily.cmd", "run_weekly.cmd"):
            with self.subTest(runner=name):
                text = (HERE / name).read_text(encoding="utf-8")
                lines = text.splitlines()
                start_index = next(
                    index for index, line in enumerate(lines)
                    if "task_run_receipt.py" not in line
                    and " start --root " in line
                )
                chdir_index = next(
                    index for index, line in enumerate(lines)
                    if line.strip() == 'cd /d "%REPO_ROOT%"'
                )
                first_guard = next(
                    index for index, line in enumerate(lines)
                    if line.strip().startswith("call :required")
                )
                self.assertLess(start_index, chdir_index)
                self.assertLess(chdir_index, first_guard)
                self.assertIn("rotate-log --path", text)
                self.assertEqual(text.count('call :close_receipt "'), 2)
                self.assertIn("--terminal \"%~1\"", text)
                self.assertIn("--terminal-reason \"%~3\"", text)
                self.assertIn("--terminal-step \"%~4\"", text)
                self.assertIn("--final-rc \"%~2\"", text)
                self.assertIn("--publication-state \"%PUBLICATION_STATE%\"", text)
                self.assertIn("--step \"%STEP_NAME%\"", text)
                self.assertIn("--contract \"%STEP_CONTRACT%\"", text)
                self.assertIn('set "ABORT_REASON=step_nonzero"', text)
                self.assertIn('set "ABORT_STEP=!STEP_NAME!"', text)
                self.assertIn(
                    'call :close_receipt "end" !RUN_EXIT! "normal_end"', text
                )

                for index, line in enumerate(lines[: lines.index(":required")]):
                    stripped = line.strip()
                    if not stripped.startswith(("call :required ", "call :graded ")):
                        continue
                    context = "\n".join(lines[max(0, index - 3):index])
                    self.assertIn('set "STEP_NAME=', context, stripped)
                    self.assertIn('set "STEP_CONTRACT=', context, stripped)

                improvement_index = next(
                    index for index, line in enumerate(lines)
                    if line.strip().startswith("call :required ")
                    and "improvement_loop.py" in line
                )
                improvement_context = "\n".join(
                    lines[max(0, improvement_index - 3):improvement_index]
                )
                self.assertIn(
                    'set "STEP_CONTRACT=improvement-loop-v1"',
                    improvement_context,
                )

    def test_runner_declares_the_proven_nonzero_contracts(self):
        expectations = {
            "run_daily.cmd": {
                "comply_gate_stitch": "scan-on-1-v1",
                "uptime_check": "review-or-block-v1",
                "agent_gap_check": "review-or-block-v1",
                "automation_policy_guard": "block-on-2-v1",
                "privacy_guard": "privacy-guard-v1",
                "public_identity_guard": "block-on-2-v1",
                "manifest_contract": "validation-on-1-v1",
                "ga4_pull": "block-on-2-v1",
                "fb_queue_linkcheck": "validation-on-1-v1",
                "preflight_self_test": "zero-only-v1",
                "preflight": "review-or-block-v1",
            },
            "run_weekly.cmd": {
                "comply_gate_stitch": "scan-on-1-v1",
                "official_news_monitor": "official-news-v1",
                "ga4_pull": "block-on-2-v1",
                "gsc_pull": "block-on-2-v1",
                "weekly_growth_review": "zero-only-v1",
            },
        }
        for name, step_contracts in expectations.items():
            with self.subTest(runner=name):
                lines = (HERE / name).read_text(encoding="utf-8").splitlines()
                for step, contract in step_contracts.items():
                    step_index = lines.index(f'set "STEP_NAME={step}"')
                    self.assertEqual(
                        lines[step_index + 1],
                        f'set "STEP_CONTRACT={contract}"',
                    )

    def test_runner_does_not_change_windows_task_or_publish(self):
        for name in ("run_daily.cmd", "run_weekly.cmd"):
            text = (HERE / name).read_text(encoding="utf-8").casefold()
            self.assertNotIn("register-scheduledtask", text)
            self.assertNotIn("set-scheduledtask", text)
            self.assertNotIn("schtasks /change", text)
            self.assertNotIn("git push", text)
            self.assertNotIn("netlify deploy", text)


if __name__ == "__main__":
    unittest.main()
