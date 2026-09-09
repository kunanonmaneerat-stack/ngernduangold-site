#!/usr/bin/env python3
import json
import hashlib
import datetime as dt
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

import improvement_loop as loop


SYNTHETIC_RELEASE_OUTPUT = "synthetic live release parity PASS"
SYNTHETIC_RELEASE_SHA256 = hashlib.sha256(
    SYNTHETIC_RELEASE_OUTPUT.encode("utf-8")
).hexdigest()
SYNTHETIC_RELEASE_PATH = (
    "guard-evidence/subprocess/postdeploy_smoke-synthetic.txt"
)


def valid_receipt_monitoring(instrumentation_started_at, **overrides):
    """Build a complete live-bound monitoring contract for consumer tests."""
    if isinstance(instrumentation_started_at, dt.datetime):
        instrumentation = instrumentation_started_at.isoformat()
    else:
        instrumentation = instrumentation_started_at
    producer_hash = loop._path_sha256(loop.TASK_RECEIPT_TOOL_PATH)
    consumer_hash = loop._path_sha256(Path(loop.__file__).resolve())
    sources_hash = loop._activation_test_sources_hash()
    if not all(isinstance(value, str) for value in (
        producer_hash, consumer_hash, sources_hash,
    )):
        raise AssertionError("live receipt activation hashes are unavailable")
    verification = {
        "verified_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "test_sources_sha256": sources_hash,
        "suite_results": {
            suite: {"tests": 1, "exit_code": 0}
            for suite in (
                "task_receipt_tests", "improvement_loop_tests", "wiring_tests",
                "policy_tests", "batch_exit_tests",
            )
        },
    }
    verification["result_hash"] = loop._canonical_hash(verification)
    monitoring = {
        "schema_version": loop.task_run_receipt.SCHEMA_VERSION,
        "instrumentation_started_at": instrumentation,
        "tasks": list(loop.TASK_RECEIPT_NAMES),
        "contract_revision": "task-version-ordered-command-manifest-v3",
        "finished_requires_complete_manifest": True,
        "legacy_schema_policy": "test-only exact hash-bound migration registry",
        "legacy_receipt_attestations": [],
        "activation_attestation": {
            "activated_at": instrumentation,
            "receipt_producer_sha256": producer_hash,
            "receipt_consumer_sha256": consumer_hash,
            "contract_registry_sha256": (
                loop.task_run_receipt.task_contract_registry_hash()
            ),
            "verification": verification,
        },
        "trusted_receipt_producer_sha256": [producer_hash],
        "stuck_after_hours": loop.TASK_RECEIPT_STUCK_AFTER_HOURS,
        "origin": "RUNNER_INVOCATION_UNVERIFIED",
        "scheduler_launch_proven": False,
        "scheduler_sla_source": "test-only scheduler boundary",
    }
    monitoring.update(overrides)
    return monitoring


def write_synthetic_release_evidence(run_dir):
    path = Path(run_dir) / SYNTHETIC_RELEASE_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(SYNTHETIC_RELEASE_OUTPUT, encoding="utf-8", newline="\n")


def write_task_receipt(root, task_name, run_id, *, started_at, status,
                       finished_at=None, execution_state=None, final_rc=None,
                       terminal_reason=None, terminal_step_id=None, steps=None):
    terminal = status in loop.task_run_receipt.TERMINAL_STATUSES
    if steps is None and status == "FINISHED":
        selected_steps = canonical_receipt_steps(task_name, started_at)
    else:
        selected_steps = list(steps or [])
    selected_reason = terminal_reason or (
        "normal_end" if status == "FINISHED"
        else "unclassified_abort" if status == "ABORTED" else None
    )
    selected_final_rc = final_rc
    if terminal and selected_final_rc is None:
        selected_final_rc = 0 if status == "FINISHED" else 3
    task_spec = loop.task_run_receipt.TASK_STEP_CONTRACTS.get(task_name)
    runner_hash = task_spec["runner_sha256"] if task_spec else "a" * 64
    producer_hash = loop._path_sha256(loop.TASK_RECEIPT_TOOL_PATH)
    if not isinstance(producer_hash, str):
        raise AssertionError("live receipt producer hash is unavailable")
    receipt = {
        "schema_version": loop.task_run_receipt.SCHEMA_VERSION,
        "run_id": run_id,
        "task_name": task_name,
        "origin": "RUNNER_INVOCATION_UNVERIFIED",
        "status": status,
        "terminal_kind": (
            "end" if status == "FINISHED"
            else "abort" if status == "ABORTED" else None
        ),
        "terminal_reason": selected_reason,
        "terminal_step_id": terminal_step_id,
        "started_at": started_at.isoformat(),
        "finished_at": finished_at.isoformat() if finished_at else None,
        "execution_state": execution_state or (
            "RUNNING" if status == "RUNNING" else "PASS"
        ),
        "publication_state": "BLOCKED_LOCAL_ONLY",
        "final_rc": selected_final_rc,
        "runner": {
            "path": str(loop.TASK_RECEIPT_RUNNER_PATHS[task_name]),
            "sha256_start": runner_hash,
            "sha256_end": runner_hash if terminal else None,
            "stable_during_run": True if terminal else None,
        },
        "receipt_tool": {
            "path": str(loop.TASK_RECEIPT_TOOL_PATH),
            "sha256_start": producer_hash,
            "sha256_end": producer_hash if terminal else None,
            "stable_during_run": True if terminal else None,
        },
        "task_contract": loop.task_run_receipt.build_task_contract(
            task_name, runner_hash
        ),
        "log_path": "C:\\repo\\.local-private\\runtime\\runner.log",
        "steps": selected_steps,
        "transition_counter": len(selected_steps) + (1 if terminal else 0),
    }
    path = Path(root) / task_name / (run_id + ".json")
    path.parent.mkdir(parents=True, exist_ok=True)
    loop._atomic(path, loop.task_run_receipt.seal_receipt(receipt))
    return path


def canonical_receipt_steps(task_name, started_at, *, overrides=None):
    selected = []
    overrides = overrides or {}
    spec = loop.task_run_receipt.TASK_STEP_CONTRACTS[task_name]
    task_contract = loop.task_run_receipt.build_task_contract(
        task_name, spec["runner_sha256"]
    )
    cursor = started_at + dt.timedelta(seconds=1)
    for sequence, expected in enumerate(task_contract["expected_steps"], start=1):
        step_id = expected["step_id"]
        wrapper = expected["wrapper"]
        contract = expected["contract"]
        raw_rc = overrides.get(step_id, 0)
        row = receipt_step(
            step_id, cursor, raw_rc=raw_rc,
            contract=contract, wrapper=wrapper,
        )
        row["sequence"] = sequence
        if expected["evidence_mode"] == "exec":
            row.update({
                "executable": expected["executable"],
                "argument_count": expected["argument_count"],
                "command_hash": expected["command_hash"],
            })
        selected.append(row)
        cursor += dt.timedelta(seconds=2)
    return selected


def receipt_step(step_id, started_at, *, raw_rc=2,
                 contract="block-on-2-v1", wrapper="required"):
    finished_at = started_at + dt.timedelta(seconds=1)
    evidence_mode = "record" if wrapper == "internal" else "exec"
    row = {
        "sequence": 1,
        "step_id": step_id,
        "wrapper": wrapper,
        "contract": contract,
        "evidence_mode": evidence_mode,
        "started_at": started_at.isoformat(),
        "finished_at": finished_at.isoformat(),
        "duration_ms": 1000,
        "raw_rc": raw_rc,
        **loop.task_run_receipt.classify_step(wrapper, contract, raw_rc),
    }
    if evidence_mode == "exec":
        command = ["synthetic-child"]
        row.update({
            "executable": command[0],
            "argument_count": 0,
            "command_hash": loop.task_run_receipt._hash_value(command),
        })
    return row


def write_learning_commit(root, run_id, state, *, finished_at,
                          status="COMPLETED_WITH_BLOCKERS"):
    """Write the minimum hash-bound terminal evidence for a learning snapshot."""
    run_dir = Path(root) / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    loop._atomic(run_dir / "error-learning.json", state)
    loop._atomic(run_dir / "validation.json", {"passed": True})
    loop._atomic(run_dir / "run.json", {
        "run_id": run_id,
        "status": status,
        "started_at": (finished_at - dt.timedelta(minutes=1)).isoformat(),
        "finished_at": finished_at.isoformat(),
        "validation_passed": True,
        "error_learning_state_hash": state["state_hash"],
    })
    return run_dir


def observation(*, ga4=True, gsc=True, revenue=0, ledger=True, pending=0,
                 guards=True, failed_guard=None, official_current=True, intent=3):
    now = dt.datetime.now(dt.timezone.utc)
    bangkok = dt.timezone(dt.timedelta(hours=7))
    local_day = now.astimezone(bangkok).date()
    window_start = local_day - dt.timedelta(days=27)
    revenue_expiry = dt.datetime.combine(
        local_day + dt.timedelta(days=1), dt.time.min, tzinfo=bangkok
    ).isoformat(timespec="seconds")
    analytics_expiry = (now + dt.timedelta(hours=1)).isoformat(timespec="seconds")
    guard_rows = {
        name: {"passed": bool(guards and name != failed_guard),
               "exit_code": 0 if guards and name != failed_guard else 1}
        for name in loop.GUARDS
    }
    confirmed = 1 if revenue else 0
    transaction_facts = ([{
        "date": local_day.isoformat(),
        "status": "paid",
        "source": "atth",
        "gross_amount_thb": f"{float(revenue):.2f}",
        "fee_thb": "0.00",
        "net_amount_thb": f"{float(revenue):.2f}",
    }] if confirmed else [])
    revenue_payload = {
        "trusted": ledger,
        "reconciliation_state": "RECONCILED" if ledger else "UNRECONCILED",
        "quality_state": "CURRENT" if ledger else "INVALID_LEDGER",
        "learning_ready": ledger,
        "reconcile_required": not ledger,
        "next_action": "NONE" if ledger else "RECONCILE_REVENUE",
        "error": None if ledger else "missing",
        "window_start": window_start.isoformat(),
        "window_end": local_day.isoformat(),
        "window_days": 28,
        "coverage_start": window_start.isoformat(),
        "coverage_end": local_day.isoformat(),
        "extracted_at": now.isoformat(timespec="seconds"),
        "reconciled_at": now.isoformat(timespec="seconds"),
        "source_snapshot_sha256": "a" * 64,
        "upstream_evidence_bound": ledger,
        "upstream_evidence_count": 1 if ledger else None,
        "upstream_raw_file_sha256": ["b" * 64] if ledger else [],
        "upstream_browser_evidence_sha256": ["c" * 64] if ledger else [],
        "upstream_receipt_file_sha256": ["d" * 64] if ledger else [],
        "upstream_receipt_sha256": ["e" * 64] if ledger else [],
        "upstream_bound_event_rows": confirmed if ledger else None,
        "attribution_state": "UNATTRIBUTED" if ledger else None,
        "attribution_scope": "MERCHANT_TOTAL_ONLY" if ledger else None,
        "sub_id_available": False if ledger else None,
        "page_cta_attribution_ready": False,
        "verified_revenue_statuses": ["paid"],
        "pending_is_verified_revenue": False,
        "trust_expires_at": revenue_expiry,
        "source_row_count": confirmed,
        "ledger_event_rows": confirmed,
        "ledger_transaction_rows": confirmed,
        "affiliate_window_transactions": confirmed,
        "affiliate_window_transaction_facts": transaction_facts,
        "verified_transactions": confirmed,
        "paid_transactions": confirmed,
        "confirmed_transactions": confirmed,
        "pending_transactions": 0,
        "approved_transactions": 0,
        "rejected_transactions": 0,
        "refund_transactions": 0,
        "cancelled_transactions": 0,
        "paid_revenue_thb": float(revenue),
        "verified_revenue_thb": float(revenue),
        "refund_amount_thb": 0.0,
        "pending_amount_thb": 0.0,
        "approved_amount_thb": 0.0,
        "net_revenue_thb": float(revenue),
        "by_source": {"atth": float(revenue)} if revenue else {},
        "pending_by_source": {},
        "approved_by_source": {},
        "lifecycle_counts": {
            "approved": 0, "cancelled": 0, "paid": confirmed,
            "pending": 0, "refunded": 0, "rejected": 0,
        },
        "latest_transaction_date": local_day.isoformat() if confirmed else None,
        "latest_paid_date": local_day.isoformat() if confirmed else None,
    }
    result = {
        "schema_version": 1,
        "observed_at": now.isoformat(timespec="seconds"),
        "window_days": 28,
        "sources": {
            "ga4": {"trust": {"label": "TRUSTED" if ga4 else "UNTRUSTED",
                                "trusted": ga4,
                                "expires_at": analytics_expiry if ga4 else None},
                    "bundle": {"decisionable": ga4,
                               "state": "CURRENT" if ga4 else "UNTRUSTED_NOW",
                               "capture_trust": "TRUSTED" if ga4 else "UNTRUSTED",
                               "current_trust": "TRUSTED" if ga4 else "UNTRUSTED",
                               "expires_at": analytics_expiry if ga4 else None,
                               "capture_time_trust": {
                                   "trusted": ga4,
                                   "label": "TRUSTED" if ga4 else "UNTRUSTED",
                                   "expires_at": analytics_expiry if ga4 else None,
                               }}},
            "gsc": {"bundle": {"decisionable": gsc,
                                  "state": "CURRENT" if gsc else "MISSING_METADATA",
                                  "expires_at": analytics_expiry if gsc else None}},
            "official_sources": {
                "current": official_current,
                "clear_for_publication": bool(official_current and pending == 0),
                "state": ("CURRENT_CLEAN" if official_current and pending == 0
                          else "CURRENT_BLOCKED" if official_current else "MISSING"),
                "errors": 0 if official_current else None,
                "review_required": pending if official_current else None,
            },
            "revenue_ledger": {
                "trusted": ledger,
                "quality_state": revenue_payload["quality_state"],
                "learning_ready": ledger,
                "reconcile_required": not ledger,
                "next_action": revenue_payload["next_action"],
                "error": revenue_payload["error"],
            },
        },
        "metrics": {
            "ga4_observed_not_decisionable_unless_trusted": {
                "affiliate_click": intent,
            },
            "verified_affiliate_revenue": revenue_payload,
        },
        "guards": guard_rows,
    }
    result["learning_readiness"] = loop.observation_snapshot.build_learning_readiness(
        result["sources"]["ga4"]["bundle"],
        result["sources"]["gsc"]["bundle"],
        revenue_payload,
        expected_end=local_day,
        decision_time=now,
    )
    result["decision_readiness"] = loop.evaluate_decision_readiness(
        result,
        {"channels": {"threads": {"publication_authorized": True}}},
        {"passed": True, "exit_code": 0,
         "payload": {"verdict": "PASS", "process_state": "PASS",
                     "counts": {
                         "publishable": 1,
                         "structural_findings": 0,
                         "source_content_evaluated": 0,
                         "source_content_allowed": 0,
                         "source_content_blocked": 0,
                         "source_failure_reasons": 0,
                     }}},
        {
            "passed": True,
            "exit_code": 0,
            "summary": SYNTHETIC_RELEASE_OUTPUT,
            "evidence_sha256": SYNTHETIC_RELEASE_SHA256,
            "evidence_path": SYNTHETIC_RELEASE_PATH,
            "evidence_lines": 1,
        },
        target_channel="threads",
    )
    return result


class ImprovementLoopTests(unittest.TestCase):
    def contract(self):
        return json.loads(loop.CONTRACT.read_text(encoding="utf-8"))

    def write_complete_weekly_bundle(self, root, run_id, *, evaluated_at=None):
        observed = observation(revenue=100)
        evaluated_at = evaluated_at or loop._parse_utc(observed["observed_at"])
        observed["observed_at"] = evaluated_at.isoformat()
        scorecard = loop.build_maturity_scorecard(
            observed, self.contract(), cadence="weekly", now=evaluated_at,
        )
        diagnosis = {"maturity_scorecard": scorecard}
        validation = {
            "schema_version": 2,
            "passed": True,
            "control_state": "READY",
            "errors": [],
            "maturity_score": scorecard["score"],
            "maturity_stage": scorecard["stage"],
        }
        run_dir = Path(root) / run_id
        run_dir.mkdir()
        loop._atomic(run_dir / "observation.json", observed)
        loop._atomic(run_dir / "diagnosis.json", diagnosis)
        loop._atomic(run_dir / "maturity-scorecard.json", scorecard)
        loop._atomic(run_dir / "validation.json", validation)
        run = {
            "schema_version": 2,
            "run_id": run_id,
            "cadence": "weekly",
            "status": "COMPLETED",
            "started_at": (evaluated_at - dt.timedelta(minutes=1)).isoformat(),
            "finished_at": evaluated_at.isoformat(),
            "validation_passed": True,
            "validation_hash": loop._canonical_hash(validation),
            "control_state": validation["control_state"],
            "maturity_score": scorecard["score"],
            "maturity_stage": scorecard["stage"],
            "maturity_scorecard_hash": scorecard["scorecard_hash"],
            "observation_hash": loop._canonical_hash(observed),
            "diagnosis_hash": loop._canonical_hash(diagnosis),
        }
        loop._atomic(run_dir / "run.json", run)
        return run_dir, observed, diagnosis, scorecard, validation, run

    def test_untrusted_data_never_creates_scale_action(self):
        result = loop.diagnose(observation(ga4=False, gsc=False, revenue=0, pending=2), self.contract())
        kinds = [item["type"] for item in result["priorities"]]
        self.assertIn("repair_measurement", kinds)
        self.assertNotIn("design_one_revenue_experiment", kinds)
        self.assertFalse(result["external_mutation_authorized"])
        self.assertTrue(all(item["request_only"] for item in result["owner_actions"]))

    def test_verified_revenue_allows_one_bounded_experiment(self):
        result = loop.diagnose(
            observation(revenue=100), self.contract(), cadence="weekly"
        )
        kinds = [item["type"] for item in result["priorities"]]
        self.assertEqual(kinds, ["design_one_revenue_experiment"])
        self.assertEqual(result["maturity_scorecard"]["score"], 100)
        self.assertEqual(result["maturity_scorecard"]["stage"], "revenue_learning")

    def test_daily_score_is_provisional_and_never_selects_experiment(self):
        result = loop.diagnose(
            observation(revenue=100), self.contract(), cadence="daily"
        )
        self.assertNotIn(
            "design_one_revenue_experiment",
            [item["type"] for item in result["priorities"]],
        )
        self.assertEqual(
            result["maturity_scorecard"]["progression"]["status"],
            "PROVISIONAL_DAILY",
        )
        self.assertFalse(result["maturity_scorecard"]["growth_experiment_eligible"])

    def test_forged_ready_payload_is_hash_and_contract_blocked(self):
        observed = observation(revenue=100)
        observed["decision_readiness"] = {
            "schema_version": 2,
            "status": "READY",
            "growth_ready": True,
            "publication_ready": True,
            "target_channel": "threads",
            "blockers": [],
            "checks": {},
            "evidence_hash": "0" * 64,
        }
        result = loop.diagnose(
            observed, self.contract(), cadence="weekly"
        )
        self.assertNotIn(
            "design_one_revenue_experiment",
            [item["type"] for item in result["priorities"]],
        )
        card = result["maturity_scorecard"]
        self.assertEqual(card["evidence_status"], "INVALID")
        self.assertIn("evidence_current_and_bound", card["hard_blockers"])
        self.assertLessEqual(card["score"], 49)

    def test_publication_authority_requires_an_exact_target_channel(self):
        observed = observation(revenue=100)
        calendar = {
            "passed": True,
            "exit_code": 0,
            "payload": {
                "verdict": "PASS",
                "process_state": "PASS",
                "counts": {
                    "publishable": 1,
                    "structural_findings": 0,
                    "source_content_evaluated": 0,
                    "source_content_allowed": 0,
                    "source_content_blocked": 0,
                    "source_failure_reasons": 0,
                },
            },
        }
        release = {
            "passed": True,
            "exit_code": 0,
            "summary": SYNTHETIC_RELEASE_OUTPUT,
            "evidence_sha256": SYNTHETIC_RELEASE_SHA256,
            "evidence_path": SYNTHETIC_RELEASE_PATH,
            "evidence_lines": 1,
        }

        readiness = loop.evaluate_decision_readiness(
            observed,
            {"channels": {"threads": {"publication_authorized": True}}},
            calendar,
            release,
            target_channel=None,
        )

        authority = readiness["checks"]["publication_authority"]
        self.assertFalse(authority["passed"])
        self.assertIsNone(authority["target_channel"])
        self.assertEqual(authority["authorized_channels"], [])
        self.assertEqual(
            authority["available_authorized_channels"], ["threads"]
        )
        self.assertIn("publication_authority_false", readiness["blockers"])
        self.assertFalse(readiness["publication_ready"])

    def test_readiness_contract_rejects_unscoped_authority_claim(self):
        observed = observation(revenue=100)
        readiness = json.loads(json.dumps(observed["decision_readiness"]))
        authority = readiness["checks"]["publication_authority"]
        authority["target_channel"] = None
        authority["authorized_channels"] = ["threads"]
        authority["available_authorized_channels"] = ["threads"]
        authority["passed"] = True
        readiness["target_channel"] = None
        readiness["evidence_hash"] = loop._readiness_hash(readiness)

        errors = loop.readiness_contract_errors(readiness, observed)

        self.assertIn(
            "publication authority check contradicts its evidence", errors
        )

    def test_contradictory_learning_readiness_marks_evidence_invalid(self):
        observed = observation(revenue=100)
        observed["learning_readiness"]["ready"] = False
        evaluated_at = loop._parse_utc(observed["observed_at"])

        card = loop.build_maturity_scorecard(
            observed,
            self.contract(),
            cadence="weekly",
            now=evaluated_at,
        )

        criterion = next(
            row for row in card["criteria"]
            if row["id"] == "evidence_current_and_bound"
        )
        self.assertFalse(criterion["passed"])
        self.assertIn(
            "learning readiness contradicts recomputed source contracts",
            criterion["evidence"]["learning_readiness_errors"],
        )
        self.assertEqual(card["evidence_status"], "INVALID")
        self.assertEqual(
            card["progression"]["status"],
            "CURRENT_EVIDENCE_INVALID",
        )
        self.assertFalse(card["growth_experiment_eligible"])

    def test_readiness_rejects_tampered_calendar_and_release_evidence(self):
        observed = observation(revenue=100)
        readiness = observed["decision_readiness"]
        self.assertEqual(loop.readiness_contract_errors(readiness, observed), [])

        calendar_tampered = json.loads(json.dumps(readiness))
        calendar_tampered["checks"]["content_calendar"]["payload"][
            "counts"
        ]["publishable"] = 0
        self.assertIn(
            "content calendar payload evidence is missing or mismatched",
            loop.readiness_contract_errors(calendar_tampered, observed),
        )

        release_tampered = json.loads(json.dumps(readiness))
        release_tampered["checks"]["live_release_parity"][
            "summary"
        ] = "forged release result"
        self.assertIn(
            "live release parity evidence hash is mismatched",
            loop.readiness_contract_errors(release_tampered, observed),
        )

        full_output_tampered = json.loads(json.dumps(readiness))
        full_output_tampered["checks"]["live_release_parity"][
            "full_output_sha256"
        ] = "0" * 64
        self.assertIn(
            "live release parity evidence hash is mismatched",
            loop.readiness_contract_errors(full_output_tampered, observed),
        )

    def test_readiness_revalidates_ga4_and_gsc_expiry_at_observation_time(self):
        for source, expiry in (
            ("ga4", None),
            (
                "gsc",
                (dt.datetime.now(dt.timezone.utc) - dt.timedelta(seconds=1))
                .isoformat(timespec="seconds"),
            ),
        ):
            with self.subTest(source=source):
                observed = observation(revenue=100)
                observed["sources"][source]["bundle"]["expires_at"] = expiry
                errors = loop.readiness_contract_errors(
                    observed["decision_readiness"], observed
                )
                self.assertTrue(any("expiry" in error for error in errors), errors)
                evaluated_at = loop._parse_utc(observed["observed_at"])
                card = loop.build_maturity_scorecard(
                    observed, self.contract(), cadence="weekly", now=evaluated_at
                )
                self.assertFalse(card["growth_experiment_eligible"])
                self.assertTrue(card["hard_blockers"])

    def test_source_expiry_between_observation_and_score_is_invalid(self):
        observed = observation(revenue=100)
        observed_at = loop._parse_utc(observed["observed_at"])
        expires_at = (observed_at + dt.timedelta(minutes=30)).isoformat()
        observed["sources"]["ga4"]["trust"]["expires_at"] = expires_at
        observed["sources"]["ga4"]["bundle"]["expires_at"] = expires_at
        observed["decision_readiness"]["checks"]["ga4"][
            "expires_at"
        ] = expires_at
        observed["decision_readiness"]["evidence_hash"] = (
            loop._readiness_hash(observed["decision_readiness"])
        )
        evaluated_at = observed_at + dt.timedelta(hours=1)

        card = loop.build_maturity_scorecard(
            observed,
            self.contract(),
            cadence="weekly",
            now=evaluated_at,
        )

        self.assertEqual(card["evidence_status"], "INVALID")
        self.assertIn("evidence_current_and_bound", card["hard_blockers"])
        self.assertIn("analytics_decisionable", card["hard_blockers"])
        self.assertFalse(card["learning_ready"])
        self.assertFalse(card["growth_experiment_eligible"])

    def test_stale_observation_scores_zero_and_blocks_growth(self):
        observed = observation(revenue=100)
        observed["observed_at"] = (
            dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=3)
        ).isoformat(timespec="seconds")
        result = loop.diagnose(
            observed, self.contract(), cadence="weekly"
        )
        card = result["maturity_scorecard"]
        self.assertEqual(card["evidence_status"], "STALE")
        self.assertEqual(card["score"], 0)
        self.assertFalse(card["growth_experiment_eligible"])
        self.assertNotIn(
            "design_one_revenue_experiment",
            [item["type"] for item in result["priorities"]],
        )

    def test_nan_revenue_is_unavailable_not_zero_or_experiment(self):
        observed = observation(revenue=100)
        observed["metrics"]["verified_affiliate_revenue"][
            "net_revenue_thb"
        ] = float("nan")
        result = loop.diagnose(
            observed, self.contract(), cadence="weekly"
        )
        kinds = [item["type"] for item in result["priorities"]]
        finding_ids = [item["id"] for item in result["findings"]]
        self.assertIn("repair_revenue_ledger", kinds)
        self.assertIn("revenue_ledger_unavailable", finding_ids)
        self.assertNotIn("verified_zero_revenue", finding_ids)
        self.assertNotIn("design_one_revenue_experiment", kinds)
        self.assertFalse(result["learning_ready"])
        self.assertIn(
            "RECONCILE_REVENUE",
            {item["action"] for item in result["next_data_actions"]},
        )

    def test_weekly_progression_requires_real_criterion_transition(self):
        baseline = loop.diagnose(
            observation(revenue=0), self.contract(), cadence="weekly"
        )["maturity_scorecard"]
        improved = loop.diagnose(
            observation(revenue=100), self.contract(), cadence="weekly",
            previous_scorecard=baseline,
        )["maturity_scorecard"]
        self.assertEqual(improved["progression"]["status"], "IMPROVED")
        self.assertEqual(improved["progression"]["delta"], 10)
        self.assertEqual(
            improved["progression"]["newly_passed"],
            ["verified_revenue_learning"],
        )

    def test_regressed_error_learning_blocks_progression_and_growth_eligibility(self):
        contract = self.contract()
        first_observation = observation(revenue=0, pending=1)
        first_at = loop._parse_utc(first_observation["observed_at"])
        first_diagnosis = loop.diagnose(
            first_observation, contract, cadence="weekly", now=first_at,
        )
        first_state = loop.build_error_learning_state(
            loop._empty_error_learning_state(), first_diagnosis,
            run_id="regression-first",
            observed_at=first_observation["observed_at"], now=first_at,
        )

        resolved_observation = observation(revenue=0, pending=0)
        resolved_at = loop._parse_utc(resolved_observation["observed_at"])
        resolved_diagnosis = loop.diagnose(
            resolved_observation, contract, cadence="weekly", now=resolved_at,
        )
        resolved_state = loop.build_error_learning_state(
            first_state, resolved_diagnosis, run_id="regression-resolved",
            observed_at=resolved_observation["observed_at"], now=resolved_at,
        )

        current_observation = observation(revenue=100, pending=1)
        current_at = loop._parse_utc(current_observation["observed_at"])
        baseline = loop.diagnose(
            observation(revenue=0, pending=0), contract,
            cadence="weekly", now=current_at,
        )["maturity_scorecard"]
        diagnosis, error_learning = loop._diagnose_with_error_learning(
            current_observation,
            contract,
            cadence="weekly",
            now=current_at,
            previous_scorecard=baseline,
            previous_learning_state=resolved_state,
            run_id="regression-returned",
        )
        diagnosis["error_learning"] = {
            "state_hash": error_learning["state_hash"],
            **error_learning["summary"],
        }

        card = diagnosis["maturity_scorecard"]
        self.assertEqual(
            card["progression"]["status"], "ERROR_REGRESSION_BLOCKED"
        )
        self.assertFalse(card["progression"]["comparable"])
        self.assertFalse(card["growth_experiment_eligible"])
        self.assertIn(
            "official_source_review",
            error_learning["summary"]["regressed_incidents"],
        )
        self.assertNotIn(
            "design_one_revenue_experiment",
            [item["type"] for item in diagnosis["priorities"]],
        )
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            loop._atomic(run_dir / "observation.json", current_observation)
            loop._atomic(run_dir / "diagnosis.json", diagnosis)
            validated = loop.validate(
                run_dir,
                current_observation,
                diagnosis,
                contract,
                now=current_at,
                learning_state=resolved_state,
                error_learning=error_learning,
                previous_scorecard=baseline,
                run_id="regression-returned",
            )
        self.assertTrue(validated["passed"], validated["errors"])
        self.assertFalse(validated["growth_experiment_eligible"])

    def test_validate_recomputes_error_learning_transition_from_prior_state(self):
        contract = self.contract()
        first_observation = observation(revenue=0, pending=1)
        first_at = loop._parse_utc(first_observation["observed_at"])
        first_diagnosis = loop.diagnose(
            first_observation, contract, cadence="weekly", now=first_at,
        )
        first_state = loop.build_error_learning_state(
            loop._empty_error_learning_state(), first_diagnosis,
            run_id="learning-first",
            observed_at=first_observation["observed_at"], now=first_at,
        )
        resolved_observation = observation(revenue=0, pending=0)
        resolved_at = loop._parse_utc(resolved_observation["observed_at"])
        resolved_diagnosis = loop.diagnose(
            resolved_observation, contract, cadence="weekly", now=resolved_at,
        )
        resolved_state = loop.build_error_learning_state(
            first_state, resolved_diagnosis, run_id="learning-resolved",
            observed_at=resolved_observation["observed_at"], now=resolved_at,
        )

        current_observation = observation(revenue=100, pending=1)
        current_at = loop._parse_utc(current_observation["observed_at"])
        baseline = loop.diagnose(
            observation(revenue=0), contract,
            cadence="weekly", now=current_at,
        )["maturity_scorecard"]
        forged_diagnosis = loop.diagnose(
            current_observation,
            contract,
            cadence="weekly",
            now=current_at,
            previous_scorecard=baseline,
            learning_state=resolved_state,
        )
        forged_learning = loop.build_error_learning_state(
            resolved_state,
            forged_diagnosis,
            run_id="learning-forged",
            observed_at=current_observation["observed_at"],
            now=current_at,
        )
        for incident in forged_learning["incidents"].values():
            if incident.get("status") == "REGRESSED":
                incident["status"] = "OPEN"
        forged_learning["summary"]["regressed_incidents"] = []
        loop._seal_error_learning_state(forged_learning)
        self.assertEqual(
            forged_learning["previous_state_hash"], resolved_state["state_hash"]
        )
        self.assertEqual(
            loop.error_learning_state_errors(
                forged_learning,
                current_findings=forged_diagnosis["findings"],
                not_after=current_at,
            ),
            [],
        )
        forged_diagnosis["error_learning"] = {
            "state_hash": forged_learning["state_hash"],
            **forged_learning["summary"],
        }
        self.assertTrue(
            forged_diagnosis["maturity_scorecard"]["growth_experiment_eligible"]
        )

        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            loop._atomic(run_dir / "observation.json", current_observation)
            loop._atomic(run_dir / "diagnosis.json", forged_diagnosis)
            validated = loop.validate(
                run_dir,
                current_observation,
                forged_diagnosis,
                contract,
                now=current_at,
                learning_state=resolved_state,
                error_learning=forged_learning,
                previous_scorecard=baseline,
                run_id="learning-forged",
            )
        self.assertFalse(validated["passed"])
        self.assertFalse(validated["growth_experiment_eligible"])
        self.assertIn(
            "error-learning state contradicts prior state and current evidence",
            validated["errors"],
        )

    def test_validate_rejects_resealed_forged_progression(self):
        contract = self.contract()
        baseline_observation = observation(revenue=0)
        baseline_at = loop._parse_utc(baseline_observation["observed_at"])
        baseline = loop.diagnose(
            baseline_observation, contract, cadence="weekly", now=baseline_at,
        )["maturity_scorecard"]
        observed = observation(revenue=100)
        evaluated_at = loop._parse_utc(observed["observed_at"])
        diagnosed = loop.diagnose(
            observed,
            contract,
            cadence="weekly",
            now=evaluated_at,
            previous_scorecard=baseline,
        )
        card = diagnosed["maturity_scorecard"]
        card["progression"] = {
            "status": "IMPROVED",
            "comparable": True,
            "delta": 999,
            "newly_passed": ["forged_criterion"],
            "reopened_hard_blockers": [],
            "previous_scorecard_hash": "0" * 64,
        }
        loop._seal_scorecard(card)
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            loop._atomic(run_dir / "observation.json", observed)
            loop._atomic(run_dir / "diagnosis.json", diagnosed)
            validated = loop.validate(
                run_dir, observed, diagnosed, contract,
                now=evaluated_at, previous_scorecard=baseline,
            )
        self.assertFalse(validated["passed"])
        self.assertIn(
            "maturity scorecard contradicts evidence: progression",
            validated["errors"],
        )

    def test_tampered_weekly_baseline_cannot_create_progress(self):
        baseline = loop.diagnose(
            observation(revenue=0), self.contract(), cadence="weekly"
        )["maturity_scorecard"]
        baseline["score"] += 1
        result = loop.diagnose(
            observation(revenue=100), self.contract(), cadence="weekly",
            previous_scorecard=baseline,
        )["maturity_scorecard"]
        self.assertEqual(result["progression"]["status"], "INVALID_BASELINE")
        self.assertIsNone(result["progression"]["delta"])

    def test_guard_failure_caps_score_and_queue_is_acceptance_bound(self):
        result = loop.diagnose(
            observation(revenue=100, failed_guard="daily_media"),
            self.contract(), cadence="weekly",
        )
        self.assertLessEqual(result["maturity_scorecard"]["score"], 49)
        self.assertEqual(result["priorities"][0]["type"], "repair_local_guard")
        self.assertNotIn(
            "design_one_revenue_experiment",
            [item["type"] for item in result["priorities"]],
        )
        self.assertEqual(
            loop.action_queue_errors(result["action_queue"], self.contract()), []
        )
        self.assertTrue(all(
            item["acceptance_criteria"]
            for item in result["action_queue"]["items"]
        ))

    def test_ready_weekly_scorecard_and_queue_validate(self):
        observed = observation(revenue=100)
        diagnosed = loop.diagnose(
            observed, self.contract(), cadence="weekly"
        )
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            (run_dir / "observation.json").write_text("{}", encoding="utf-8")
            (run_dir / "diagnosis.json").write_text("{}", encoding="utf-8")
            validated = loop.validate(
                run_dir, observed, diagnosed, self.contract()
            )
        self.assertTrue(validated["passed"], validated["errors"])
        self.assertTrue(validated["growth_experiment_eligible"])

    def test_persisted_evaluation_time_recomputes_identical_scorecard(self):
        """Sub-second wall time must not change hash-bound evidence on reload."""
        observed = observation(revenue=0)
        observed_at = loop._parse_utc(observed["observed_at"])
        evaluated_at = observed_at + dt.timedelta(
            seconds=196, microseconds=900000
        )
        scorecard = loop.build_maturity_scorecard(
            observed, self.contract(), cadence="daily", now=evaluated_at,
        )
        persisted_time = loop._parse_utc(scorecard["evaluated_at"])
        recomputed = loop.build_maturity_scorecard(
            observed, self.contract(), cadence="daily", now=persisted_time,
        )

        self.assertEqual(scorecard["criteria"], recomputed["criteria"])
        self.assertEqual(scorecard["evidence_hash"], recomputed["evidence_hash"])
        self.assertTrue(loop._scorecard_hash_valid(scorecard))
        self.assertTrue(loop._scorecard_hash_valid(recomputed))

        diagnosed = loop.diagnose(
            observed, self.contract(), cadence="daily", now=evaluated_at,
        )
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            loop._atomic(run_dir / "observation.json", observed)
            loop._atomic(run_dir / "diagnosis.json", diagnosed)
            validated = loop.validate(
                run_dir, observed, diagnosed, self.contract(), now=evaluated_at,
            )
        self.assertTrue(validated["passed"], validated["errors"])
        self.assertFalse(any(
            "maturity scorecard contradicts evidence" in error
            for error in validated["errors"]
        ))

    def test_subsecond_beyond_freshness_sla_is_stale(self):
        observed = observation(revenue=0)
        observed_at = loop._parse_utc(observed["observed_at"])
        evaluated_at = observed_at + dt.timedelta(
            hours=2, microseconds=900000
        )
        card = loop.build_maturity_scorecard(
            observed, self.contract(), cadence="daily", now=evaluated_at,
        )
        freshness = {
            row["id"]: row for row in card["criteria"]
        }["evidence_current_and_bound"]
        self.assertEqual(card["evidence_status"], "STALE")
        self.assertFalse(freshness["passed"])
        self.assertEqual(
            freshness["evidence"]["freshness_error"],
            "observation is outside the cadence evidence window",
        )

    def test_validate_rejects_resealed_schema_and_denominator(self):
        observed = observation(revenue=100)
        evaluated_at = loop._parse_utc(observed["observed_at"])
        diagnosed = loop.diagnose(
            observed, self.contract(), cadence="weekly", now=evaluated_at,
        )
        card = diagnosed["maturity_scorecard"]
        card["schema_version"] = 999
        card["maximum_score"] = 1
        loop._seal_scorecard(card)
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            loop._atomic(run_dir / "observation.json", observed)
            loop._atomic(run_dir / "diagnosis.json", diagnosed)
            validated = loop.validate(
                run_dir, observed, diagnosed, self.contract(), now=evaluated_at,
            )
        self.assertFalse(validated["passed"])
        self.assertIn(
            "maturity scorecard contradicts evidence: schema_version",
            validated["errors"],
        )
        self.assertIn(
            "maturity scorecard contradicts evidence: maximum_score",
            validated["errors"],
        )

    def test_report_never_calls_sources_current_when_learning_not_ready(self):
        observed = observation(revenue=0)
        diagnosed = loop.diagnose(observed, self.contract(), cadence="daily")
        diagnosed["learning_ready"] = False
        diagnosed["learning_blockers"] = ["learning_readiness_evidence_invalid"]
        diagnosed["next_data_actions"] = []
        report = loop.render_report(
            "report-learning-blocked",
            "daily",
            observed,
            diagnosed,
            {
                "passed": True,
                "control_state": "VALID_WITH_BLOCKERS",
                "operational_blockers": ["learning_readiness_evidence_invalid"],
                "growth_experiment_eligible": False,
            },
        )
        self.assertNotIn("All three learning sources are current.", report)
        self.assertIn("Learning sources are BLOCKED/INVALID", report)
        self.assertIn("learning_readiness_evidence_invalid", report)

    def test_report_labels_unavailable_control_rate_instead_of_python_none(self):
        observed = observation(revenue=0)
        diagnosed = loop.diagnose(observed, self.contract(), cadence="daily")
        report = loop.render_report(
            "report-unavailable-control-rate",
            "daily",
            observed,
            diagnosed,
            {
                "passed": True,
                "control_state": "VALID_WITH_BLOCKERS",
                "growth_experiment_eligible": False,
            },
            control_health={
                "kpis": {"terminal_control_run_rate_7d": None},
            },
        )

        self.assertIn(
            "terminal control-run rate (7d): `UNAVAILABLE`", report
        )
        self.assertNotIn("terminal control-run rate (7d): `None`", report)

    def test_injected_growth_action_fails_validation_behind_blocker(self):
        observed = observation(revenue=100, failed_guard="daily_media")
        diagnosed = loop.diagnose(
            observed, self.contract(), cadence="weekly"
        )
        diagnosed["priorities"].append({
            "rank": 4,
            "type": "design_one_revenue_experiment",
            "scope": ["forged"],
            "reason": "forged",
        })
        diagnosed["action_queue"] = loop.build_action_queue(
            diagnosed["priorities"], diagnosed["owner_actions"],
            self.contract(), observed["observed_at"],
        )
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            (run_dir / "observation.json").write_text("{}", encoding="utf-8")
            (run_dir / "diagnosis.json").write_text("{}", encoding="utf-8")
            validated = loop.validate(
                run_dir, observed, diagnosed, self.contract()
            )
        self.assertFalse(validated["passed"])
        self.assertIn("hard blocker", " ".join(validated["errors"]))

    def test_invalid_score_policy_fails_before_creating_run(self):
        with tempfile.TemporaryDirectory() as tmp:
            policy_path = Path(tmp) / "improvement-policy.json"
            invalid = self.contract()
            invalid["maturity_scorecard"]["criteria"][0]["weight"] += 1
            policy_path.write_text(json.dumps(invalid), encoding="utf-8")
            runs = Path(tmp) / "runs"
            with (mock.patch.object(loop, "CONTRACT", policy_path),
                  mock.patch.object(loop, "IMPROVEMENT_RUNS_DIR", runs)):
                with self.assertRaisesRegex(ValueError, "invalid improvement policy"):
                    loop.execute(run_id="invalid-policy")
            self.assertFalse(runs.exists())

    def test_failed_validation_weekly_run_is_not_a_progression_baseline(self):
        """A self-hashed scorecard cannot redeem a failed control run."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_dir = root / "failed-weekly"
            run_dir.mkdir()
            evaluated_at = dt.datetime.now(dt.timezone.utc).replace(
                microsecond=0
            )
            scorecard = loop.build_maturity_scorecard(
                observation(revenue=100), self.contract(), cadence="weekly",
                now=evaluated_at,
            )
            loop._atomic(run_dir / "maturity-scorecard.json", scorecard)
            loop._atomic(run_dir / "validation.json", {"passed": False})
            loop._atomic(run_dir / "run.json", {
                "schema_version": 2,
                "run_id": "failed-weekly",
                "cadence": "weekly",
                "status": "FAILED_VALIDATION",
                "started_at": (
                    evaluated_at - dt.timedelta(minutes=1)
                ).isoformat(),
                "finished_at": evaluated_at.isoformat(),
                "validation_passed": False,
                "maturity_score": scorecard["score"],
                "maturity_stage": scorecard["stage"],
            })

            self.assertIsNone(loop._load_previous_weekly_scorecard(root))

    def test_validated_weekly_run_is_hash_bound_progression_baseline(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_dir, _, _, scorecard, validation, _ = (
                self.write_complete_weekly_bundle(root, "valid-weekly")
            )

            selected = loop._load_previous_weekly_scorecard(root)
            self.assertEqual(selected, scorecard)

            validation["passed"] = False
            loop._atomic(run_dir / "validation.json", validation)
            self.assertIsNone(loop._load_previous_weekly_scorecard(root))

            (run_dir / "validation.json").write_text(
                '{"passed": true, "metric": NaN}', encoding="utf-8"
            )
            self.assertIsNone(loop._load_previous_weekly_scorecard(root))

    def test_previous_weekly_loader_rejects_cross_rehashed_forged_bundle(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_dir, _, diagnosis, scorecard, validation, run = (
                self.write_complete_weekly_bundle(root, "cross-rehashed-forgery")
            )
            for row in scorecard["criteria"]:
                row["passed"] = False
                row["awarded"] = 0
                row["evidence"] = {"forged": True}
                row["evidence_hash"] = loop._canonical_hash(row["evidence"])
            scorecard["raw_score"] = 0
            scorecard["score"] = 0
            scorecard["stage"] = "instrumented"
            scorecard["hard_blockers"] = sorted(
                row["id"] for row in scorecard["criteria"]
                if row["hard_blocker"]
            )
            scorecard["growth_experiment_eligible"] = False
            scorecard["evidence_hash"] = loop._canonical_hash({
                "observed_at": scorecard["observed_at"],
                "policy_hash": scorecard["policy_hash"],
                "criteria": [
                    {
                        "id": row["id"],
                        "passed": row["passed"],
                        "evidence_hash": row["evidence_hash"],
                    }
                    for row in scorecard["criteria"]
                ],
                "score": scorecard["score"],
                "hard_blockers": scorecard["hard_blockers"],
            })
            loop._seal_scorecard(scorecard)
            diagnosis["maturity_scorecard"] = scorecard
            validation["maturity_score"] = scorecard["score"]
            validation["maturity_stage"] = scorecard["stage"]
            run["maturity_score"] = scorecard["score"]
            run["maturity_stage"] = scorecard["stage"]
            run["maturity_scorecard_hash"] = scorecard["scorecard_hash"]
            run["diagnosis_hash"] = loop._canonical_hash(diagnosis)
            run["validation_hash"] = loop._canonical_hash(validation)
            loop._atomic(run_dir / "maturity-scorecard.json", scorecard)
            loop._atomic(run_dir / "diagnosis.json", diagnosis)
            loop._atomic(run_dir / "validation.json", validation)
            loop._atomic(run_dir / "run.json", run)

            self.assertTrue(loop._scorecard_hash_valid(scorecard))
            self.assertFalse(loop._has_complete_evidence_bundle(run_dir, run))
            self.assertIsNone(loop._load_previous_weekly_scorecard(root))

    def test_weekly_baseline_validation_is_bound_to_the_scorecard(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_dir, _, _, _, validation, run = (
                self.write_complete_weekly_bundle(root, "mismatched-validation")
            )
            validation["maturity_score"] += 1
            loop._atomic(run_dir / "validation.json", validation)
            run["validation_hash"] = loop._canonical_hash(validation)
            loop._atomic(run_dir / "run.json", run)

            self.assertIsNone(loop._load_previous_weekly_scorecard(root))

    def test_future_weekly_terminal_cannot_mask_the_latest_valid_baseline(self):
        now = dt.datetime.now(dt.timezone.utc).replace(microsecond=0)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _, _, _, expected, _, _ = self.write_complete_weekly_bundle(
                root, "current-weekly", evaluated_at=now
            )
            self.write_complete_weekly_bundle(
                root, "future-weekly", evaluated_at=now + dt.timedelta(hours=1)
            )

            self.assertEqual(loop._load_previous_weekly_scorecard(root), expected)

    def test_improvement_global_state_has_a_single_writer(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with loop._exclusive_run_lock(root):
                with self.assertRaisesRegex(RuntimeError, "already active"):
                    with loop._exclusive_run_lock(root):
                        self.fail("overlapping run acquired the global-state lock")

            with loop._exclusive_run_lock(root):
                self.assertTrue((root / "_active-run.lock").is_file())

    def test_improvement_global_state_lock_blocks_another_process(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            code = (
                "import pathlib,sys;"
                f"sys.path.insert(0,{str(Path(loop.__file__).parent)!r});"
                "import improvement_loop as loop;"
                f"root=pathlib.Path({str(root)!r});"
                "blocked=False;"
                "\ntry:\n"
                "  with loop._exclusive_run_lock(root): pass\n"
                "except RuntimeError:\n"
                "  blocked=True\n"
                "raise SystemExit(0 if blocked else 1)"
            )
            with loop._exclusive_run_lock(root):
                completed = subprocess.run(
                    [sys.executable, "-c", code],
                    capture_output=True,
                    text=True,
                    timeout=10,
                    check=False,
                )
            self.assertEqual(
                completed.returncode, 0,
                completed.stdout + completed.stderr,
            )

    def test_malformed_numeric_policy_fails_closed_without_type_error(self):
        invalid = self.contract()
        invalid["maturity_scorecard"]["max_score"] = "100"
        invalid["cadence"]["daily"]["max_observation_age_hours"] = "2"
        errors = loop.improvement_contract_errors(invalid)
        self.assertIn("maturity max_score must be a positive integer", errors)
        self.assertTrue(any("cadence evidence age" in item for item in errors))

    def test_task_receipt_activation_attestation_binds_live_contract_code(self):
        contract = loop._load(loop.CONTRACT)
        self.assertEqual(loop.improvement_contract_errors(contract), [])
        mutations = (
            (
                "producer",
                lambda row: row["task_receipt_monitoring"][
                    "activation_attestation"
                ].update(receipt_producer_sha256="0" * 64),
            ),
            (
                "consumer",
                lambda row: row["task_receipt_monitoring"][
                    "activation_attestation"
                ].update(receipt_consumer_sha256="0" * 64),
            ),
            (
                "registry",
                lambda row: row["task_receipt_monitoring"][
                    "activation_attestation"
                ].update(contract_registry_sha256="0" * 64),
            ),
            (
                "activation-time",
                lambda row: row["task_receipt_monitoring"][
                    "activation_attestation"
                ].update(activated_at="2026-08-24T00:00:00+00:00"),
            ),
            (
                "verification-time",
                lambda row: row["task_receipt_monitoring"][
                    "activation_attestation"
                ]["verification"].update(
                    verified_at="2000-01-01T00:00:00+00:00"
                ),
            ),
            (
                "verification-test-sources",
                lambda row: row["task_receipt_monitoring"][
                    "activation_attestation"
                ]["verification"].update(test_sources_sha256="0" * 64),
            ),
            (
                "verification-suite-result",
                lambda row: row["task_receipt_monitoring"][
                    "activation_attestation"
                ]["verification"]["suite_results"][
                    "task_receipt_tests"
                ].update(tests=0),
            ),
            (
                "verification-result-hash",
                lambda row: row["task_receipt_monitoring"][
                    "activation_attestation"
                ]["verification"].update(result_hash="0" * 64),
            ),
        )
        for label, mutate in mutations:
            with self.subTest(label=label):
                forged = json.loads(json.dumps(contract))
                mutate(forged)
                errors = loop.improvement_contract_errors(forged)
                self.assertTrue(
                    any("task receipt activation" in error for error in errors),
                    errors,
                )

    def test_task_receipt_monitoring_contract_rejects_mutated_registries(self):
        contract = loop._load(loop.CONTRACT)
        mutations = (
            (
                "revision",
                lambda row: row["task_receipt_monitoring"].update(
                    contract_revision="forged-revision"
                ),
                "task receipt ordered-step contract revision is invalid",
            ),
            (
                "complete-manifest",
                lambda row: row["task_receipt_monitoring"].update(
                    finished_requires_complete_manifest=False
                ),
                "task receipt complete-manifest requirement is disabled",
            ),
            (
                "producer-duplicate",
                lambda row: row["task_receipt_monitoring"][
                    "trusted_receipt_producer_sha256"
                ].append(
                    row["task_receipt_monitoring"][
                        "trusted_receipt_producer_sha256"
                    ][0]
                ),
                "trusted receipt producer registry is invalid",
            ),
            (
                "legacy-duplicate",
                lambda row: row["task_receipt_monitoring"][
                    "legacy_receipt_attestations"
                ].append(json.loads(json.dumps(
                    row["task_receipt_monitoring"][
                        "legacy_receipt_attestations"
                    ][0]
                ))),
                "legacy receipt attestation is duplicated",
            ),
        )
        for label, mutate, expected in mutations:
            with self.subTest(label=label):
                candidate = json.loads(json.dumps(contract))
                mutate(candidate)
                self.assertIn(expected, loop.improvement_contract_errors(candidate))

    def test_safety_failure_precedes_growth(self):
        result = loop.diagnose(observation(revenue=100, guards=False), self.contract())
        self.assertEqual(result["priorities"][0]["type"], "repair_local_guard")
        self.assertNotIn("design_one_revenue_experiment",
                         [item["type"] for item in result["priorities"]])

    def test_failed_media_guard_is_valid_completed_blocker(self):
        observed = observation(revenue=100, failed_guard="daily_media")
        diagnosed = loop.diagnose(observed, self.contract())
        self.assertNotIn("design_one_revenue_experiment",
                         [item["type"] for item in diagnosed["priorities"]])
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            (run_dir / "observation.json").write_text("{}", encoding="utf-8")
            (run_dir / "diagnosis.json").write_text("{}", encoding="utf-8")
            validated = loop.validate(run_dir, observed, diagnosed, self.contract())
        self.assertTrue(validated["passed"], validated["errors"])
        self.assertEqual(validated["control_state"], "VALID_WITH_BLOCKERS")
        self.assertIn("daily_media", " ".join(validated["operational_blockers"]))

    def test_missing_global_monitor_is_diagnostic_not_a_content_scoped_blocker(self):
        observed = observation(revenue=100, official_current=False)
        diagnosed = loop.diagnose(observed, self.contract())
        self.assertIn("official_source_snapshot_unavailable",
                      [item["id"] for item in diagnosed["findings"]])
        self.assertNotIn("design_one_revenue_experiment",
                         [item["type"] for item in diagnosed["priorities"]])
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            (run_dir / "observation.json").write_text("{}", encoding="utf-8")
            (run_dir / "diagnosis.json").write_text("{}", encoding="utf-8")
            validated = loop.validate(run_dir, observed, diagnosed, self.contract())
        self.assertTrue(validated["passed"], validated["errors"])
        self.assertEqual(validated["control_state"], "READY")
        self.assertNotIn("official_source_snapshot_not_current",
                         validated["operational_blockers"])

    def test_no_intent_does_not_claim_intent_without_revenue(self):
        result = loop.diagnose(observation(revenue=0, intent=0), self.contract())
        self.assertNotIn("audit_offer_and_attribution",
                         [item["type"] for item in result["priorities"]])
        findings = {item["id"]: item for item in result["findings"]}
        self.assertNotIn("verified_zero_revenue", findings)
        self.assertEqual(
            findings["verified_zero_revenue_observed"]["severity"], "INFO"
        )

    def test_untrusted_intent_does_not_create_zero_revenue_incident(self):
        result = loop.diagnose(
            observation(ga4=False, revenue=0, intent=9), self.contract()
        )
        findings = {item["id"]: item for item in result["findings"]}
        self.assertNotIn("verified_zero_revenue", findings)
        observed = findings["verified_zero_revenue_observed"]
        self.assertEqual(observed["severity"], "INFO")
        self.assertFalse(observed["evidence"]["trusted_intent"])
        self.assertNotIn(
            "verified_zero_revenue",
            [item["id"] for item in loop._learnable_findings(result["findings"])],
        )

    def test_untrusted_measurement_suppresses_positive_revenue_experiment(self):
        result = loop.diagnose(observation(ga4=False, revenue=100), self.contract())
        self.assertNotIn("design_one_revenue_experiment",
                         [item["type"] for item in result["priorities"]])

    def test_unrelated_global_review_does_not_suppress_content_scoped_growth(self):
        result = loop.diagnose(
            observation(revenue=100, pending=1), self.contract(), cadence="weekly"
        )
        self.assertIn("design_one_revenue_experiment",
                      [item["type"] for item in result["priorities"]])

    def test_fresh_schema3_official_review_queues_review_not_refresh(self):
        observed = observation(revenue=100, pending=26)
        observed["sources"]["official_sources"].update({
            "state": "FRESH_REVIEW_REQUIRED",
            "current": True,
            "clear_for_publication": False,
            "errors": 0,
            "review_required": 26,
        })
        result = loop.diagnose(observed, self.contract())
        criterion = next(
            row for row in result["maturity_scorecard"]["criteria"]
            if row["id"] == "content_scoped_source_enforcement"
        )
        self.assertTrue(criterion["passed"])
        self.assertEqual(criterion["evidence"], {
            "scope": "CONTENT_ID_EXACT_MAPPING",
            "evaluated": 0,
            "allowed": 0,
            "blocked": 0,
            "failure_reasons": 0,
            "global_monitor_state_diagnostic": "FRESH_REVIEW_REQUIRED",
            "global_pending_diagnostic": 26,
            "global_errors_diagnostic": 0,
        })
        self.assertIn("official_source_review",
                      [item["id"] for item in result["findings"]])
        self.assertNotIn("official_source_snapshot_unavailable",
                         [item["id"] for item in result["findings"]])
        self.assertNotIn("refresh_official_source_snapshot",
                         [item["type"] for item in result["priorities"]])
        queue_kinds = [item["kind"] for item in result["action_queue"]["items"]]
        self.assertIn("review_official_sources", queue_kinds)
        self.assertNotIn("refresh_official_source_snapshot", queue_kinds)

    def test_each_business_readiness_condition_fails_closed(self):
        observed = observation(revenue=100)
        policy = {"channels": {"threads": {
            "state": "active", "publication_authorized": True,
        }}}
        calendar = {
            "passed": True,
            "exit_code": 0,
            "payload": {"verdict": "PASS", "process_state": "PASS",
                        "counts": {
                            "publishable": 1,
                            "structural_findings": 0,
                            "source_content_evaluated": 0,
                            "source_content_allowed": 0,
                            "source_content_blocked": 0,
                            "source_failure_reasons": 0,
                        }},
        }
        release = {
            "passed": True,
            "exit_code": 0,
            "summary": SYNTHETIC_RELEASE_OUTPUT,
            "evidence_sha256": SYNTHETIC_RELEASE_SHA256,
            "evidence_path": SYNTHETIC_RELEASE_PATH,
            "evidence_lines": 1,
        }
        baseline = loop.evaluate_decision_readiness(
            observed, policy, calendar, release, target_channel="threads"
        )
        self.assertTrue(baseline["growth_ready"])

        cases = {
            "publication_authority_false": (
                observed,
                {"channels": {"threads": {
                    "state": "active", "publication_authorized": False,
                }}},
                calendar,
                release,
            ),
            "content_calendar_publishable_zero": (
                observed,
                policy,
                {**calendar, "payload": {"verdict": "PASS", "process_state": "PASS",
                                          "counts": {
                                              **calendar["payload"]["counts"],
                                              "publishable": 0,
                                          }}},
                release,
            ),
            "content_calendar_guard_failed": (
                observed,
                policy,
                {"passed": False, "exit_code": 3,
                 "payload": {"verdict": "FAIL", "process_state": "RUNNER_FAILED",
                             "counts": {
                                 **calendar["payload"]["counts"],
                                 "publishable": 0,
                             }}},
                release,
            ),
            "content_calendar_blocked": (
                observed,
                policy,
                {"passed": False, "exit_code": 2,
                 "payload": {"verdict": "FAIL", "process_state": "BLOCKED",
                             "counts": {
                                 **calendar["payload"]["counts"],
                                 "publishable": 0,
                                 "structural_findings": 1,
                             }}},
                release,
            ),
            "live_release_parity_failed": (
                observed,
                policy,
                calendar,
                {
                    **release,
                    "passed": False,
                    "exit_code": 1,
                    "summary": "synthetic live release parity FAIL",
                },
            ),
            "revenue_ledger_unreconciled": (
                observation(revenue=100, ledger=False),
                policy,
                calendar,
                release,
            ),
            "ga4_trust_or_bundle_failed": (
                observation(ga4=False, revenue=100),
                policy,
                calendar,
                release,
            ),
            "gsc_bundle_failed": (
                observation(gsc=False, revenue=100),
                policy,
                calendar,
                release,
            ),
            "content_scoped_source_enforcement_failed": (
                observed,
                policy,
                {**calendar, "payload": {
                    **calendar["payload"],
                    "counts": {
                        **calendar["payload"]["counts"],
                        "source_content_evaluated": None,
                    },
                }},
                release,
            ),
        }
        for expected, args in cases.items():
            with self.subTest(expected=expected):
                result = loop.evaluate_decision_readiness(
                    *args, target_channel="threads"
                )
                self.assertEqual(result["status"], "BLOCKED")
                self.assertFalse(result["growth_ready"])
                self.assertFalse(result["publication_ready"])
                self.assertIn(expected, result["blockers"])
                gated_observation = json.loads(json.dumps(args[0]))
                gated_observation["decision_readiness"] = result
                diagnosed = loop.diagnose(gated_observation, self.contract())
                self.assertNotIn(
                    "design_one_revenue_experiment",
                    [item["type"] for item in diagnosed["priorities"]],
                )
                with tempfile.TemporaryDirectory() as tmp:
                    run_dir = Path(tmp)
                    (run_dir / "observation.json").write_text("{}", encoding="utf-8")
                    (run_dir / "diagnosis.json").write_text("{}", encoding="utf-8")
                    validated = loop.validate(
                        run_dir, gated_observation, diagnosed, self.contract()
                    )
                self.assertTrue(validated["passed"], validated["errors"])
                self.assertEqual(validated["control_state"], "VALID_WITH_BLOCKERS")
                self.assertFalse(validated["growth_ready"])
                self.assertFalse(validated["publication_ready"])

    def test_missing_readiness_evidence_blocks_growth_and_validation(self):
        observed = observation(revenue=100)
        observed.pop("decision_readiness")
        diagnosed = loop.diagnose(observed, self.contract())
        self.assertNotIn("design_one_revenue_experiment",
                         [item["type"] for item in diagnosed["priorities"]])
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            (run_dir / "observation.json").write_text("{}", encoding="utf-8")
            (run_dir / "diagnosis.json").write_text("{}", encoding="utf-8")
            validated = loop.validate(run_dir, observed, diagnosed, self.contract())
        self.assertFalse(validated["passed"])
        self.assertFalse(validated["growth_ready"])
        self.assertIn("decision readiness evidence invalid",
                      " ".join(validated["errors"]))

    def test_nonpositive_net_revenue_never_scales(self):
        observed = observation(revenue=100)
        observed["metrics"]["verified_affiliate_revenue"]["net_revenue_thb"] = -10
        result = loop.diagnose(observed, self.contract())
        self.assertNotIn("design_one_revenue_experiment",
                         [item["type"] for item in result["priorities"]])

    def test_guardrail_contract_has_complete_executable_mapping(self):
        contract = json.loads(loop.CONTRACT.read_text(encoding="utf-8"))
        self.assertEqual(loop.guardrail_contract_errors(contract), [])
        self.assertEqual(set(contract["guardrails"]), set(loop.GUARDRAIL_EVIDENCE))

    def test_posting_guard_writes_evidence_only_inside_private_run(self):
        public_history = loop.ROOT / "automation-log" / "post-guard" / "history.jsonl"
        before = hashlib.sha256(public_history.read_bytes()).hexdigest()
        private_parent = loop.ROOT / ".local-private" / "runtime"
        private_parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=private_parent) as tmp:
            run_dir = Path(tmp)
            result = loop._run_guard(["@private_posting_plan"], run_dir)
            self.assertIn(result["exit_code"], (0, 2))
            self.assertTrue(
                (run_dir / "guard-evidence" / "post-guard" / "history.jsonl").is_file()
            )
            self.assertTrue(list(
                (run_dir / "guard-evidence" / "post-guard").glob("status-*.md")
            ))
        after = hashlib.sha256(public_history.read_bytes()).hexdigest()
        self.assertEqual(before, after)

    def test_guard_evidence_keeps_header_and_complete_private_output(self):
        output = "\n".join(["HEADER 0/72", *["line-%d" % i for i in range(1, 10)]])
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            result = loop._guard_output_evidence(
                ["tools/postdeploy_smoke.py", "--live"], root, output
            )
            persisted = root / result["evidence_path"]
            self.assertEqual(persisted.read_text(encoding="utf-8"), output)
            readiness = {"checks": {"live_release_parity": {
                "full_output_path": result["evidence_path"],
                "full_output_sha256": result["evidence_sha256"],
                "full_output_lines": result["evidence_lines"],
            }}}
            self.assertEqual(
                loop.readiness_file_evidence_errors(readiness, root), []
            )
            persisted.write_text("tampered", encoding="utf-8")
            self.assertIn(
                "live release parity full output artifact hash is mismatched",
                loop.readiness_file_evidence_errors(readiness, root),
            )
        self.assertTrue(result["summary"].startswith("HEADER 0/72\n"))
        self.assertNotIn("line-1\n", result["summary"])
        self.assertTrue(result["summary"].endswith("line-9"))
        self.assertEqual(result["evidence_lines"], 10)
        self.assertEqual(
            result["evidence_sha256"],
            hashlib.sha256(output.encode("utf-8")).hexdigest(),
        )

    def test_local_safe_readiness_never_runs_live_probe_and_blocks_unknown(self):
        observed = observation(revenue=100)
        calendar = {
            "passed": True,
            "exit_code": 0,
            "payload": {
                "verdict": "PASS",
                "process_state": "PASS",
                "counts": {
                    "publishable": 1,
                    "structural_findings": 0,
                    "source_content_evaluated": 0,
                    "source_content_allowed": 0,
                    "source_content_blocked": 0,
                    "source_failure_reasons": 0,
                },
            },
        }
        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(
            loop.subprocess, "run",
            side_effect=AssertionError("local-safe attempted a subprocess"),
        ):
            run_dir = Path(tmp)
            result = loop.collect_decision_readiness(
                observation=observed,
                policy={
                    "channels": {
                        "threads": {"publication_authorized": True},
                    },
                },
                calendar_result=calendar,
                run_dir=run_dir,
                target_channel="threads",
            )

            release = result["checks"]["live_release_parity"]
            self.assertEqual(result["status"], "BLOCKED")
            self.assertFalse(result["growth_ready"])
            self.assertFalse(result["publication_ready"])
            self.assertIn("live_release_parity_failed", result["blockers"])
            self.assertFalse(release["passed"])
            self.assertEqual(release["exit_code"], 2)
            self.assertIn("BLOCKED/UNKNOWN", release["summary"])
            self.assertIn("No live request was attempted", release["summary"])
            self.assertEqual(
                loop.readiness_contract_errors(result, observed), []
            )
            self.assertEqual(
                loop.readiness_file_evidence_errors(result, run_dir), []
            )
            evidence = run_dir / release["full_output_path"]
            self.assertTrue(evidence.is_file())
            self.assertEqual(
                evidence.read_text(encoding="utf-8"),
                loop.LOCAL_SAFE_LIVE_RELEASE_SUMMARY,
            )

    def test_media_guard_keeps_full_scan_quality_with_bounded_long_timeout(self):
        completed = subprocess_result = mock.Mock()
        subprocess_result.returncode = 0
        subprocess_result.stdout = '{"verdict":"PASS"}'
        subprocess_result.stderr = ""
        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(
            loop.subprocess, "run", return_value=completed
        ) as runner:
            result = loop._run_guard(loop.GUARDS["daily_media"], Path(tmp))
            self.assertTrue((Path(tmp) / result["evidence_path"]).is_file())
        self.assertTrue(result["passed"])
        self.assertEqual(result["process_state"], "PASS")
        self.assertEqual(result["timeout_seconds"], 600)
        self.assertEqual(runner.call_args.kwargs["timeout"], 600)
        launched = runner.call_args.args[0]
        self.assertEqual(
            Path(launched[0]).resolve(),
            (loop.ROOT / "pipeline/python_runtime.cmd").resolve(),
        )
        self.assertEqual(
            Path(launched[1]).resolve(),
            (loop.ROOT / "tools/daily_media_gate.py").resolve(),
        )
        self.assertEqual(loop.GUARDS["daily_media"][2:4], ["3", "--json"])

    def test_guard_timeout_is_runner_failure_not_business_blocker(self):
        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(
            loop.subprocess, "run",
            side_effect=loop.subprocess.TimeoutExpired(["guard"], 180),
        ):
            result = loop._run_guard(
                ["tools/privacy_guard.py"], Path(tmp)
            )
        self.assertEqual(result["exit_code"], 3)
        self.assertEqual(result["process_state"], "RUNNER_FAILED")
        self.assertEqual(result["timeout_seconds"], 180)

    def test_run_writes_terminal_state_and_no_external_authority(self):
        with tempfile.TemporaryDirectory() as tmp:
            observed = observation(ga4=False, gsc=False, pending=2)
            # This test owns terminal-state semantics, not live-worktree race
            # detection.  Pin one valid snapshot so another test process or a
            # developer edit to a runtime dependency cannot turn the fixture
            # into FAILED_VALIDATION between collection and revalidation.  The
            # dedicated runtime-contract tamper test below proves that genuine
            # drift remains fail closed.
            stable_runtime_contract = loop.collect_runtime_contract()

            def fake_observe(run_dir, *, runtime_contract=None):
                self.assertIsInstance(runtime_contract, dict)
                observed["runtime_contract"] = runtime_contract
                write_synthetic_release_evidence(run_dir)
                loop._atomic(run_dir / "observation.json", observed)
                return observed

            with (mock.patch.object(loop, "IMPROVEMENT_RUNS_DIR", Path(tmp)),
                  mock.patch.object(loop, "observe", side_effect=fake_observe),
                  mock.patch.object(
                      loop,
                      "collect_runtime_contract",
                      side_effect=lambda: json.loads(
                          json.dumps(stable_runtime_contract)
                      ),
                  ) as runtime_reader):
                state, run_dir = loop.execute(run_id="test-run")
            persisted_validation = json.loads(
                (run_dir / "validation.json").read_text(encoding="utf-8")
            )
            self.assertGreaterEqual(runtime_reader.call_count, 2)
            self.assertEqual(
                state["status"],
                "COMPLETED_WITH_BLOCKERS",
                "unexpected validation errors: %s"
                % persisted_validation.get("errors"),
            )
            self.assertTrue(state["validation_passed"])
            self.assertEqual(state["control_state"], "VALID_WITH_BLOCKERS")
            self.assertTrue((run_dir / "report.md").is_file())
            self.assertTrue((run_dir / "error-learning.json").is_file())
            self.assertTrue((run_dir / "control-health.json").is_file())
            diagnosis = json.loads((run_dir / "diagnosis.json").read_text(encoding="utf-8"))
            persisted_run = json.loads(
                (run_dir / "run.json").read_text(encoding="utf-8")
            )
            persisted_observation = json.loads(
                (run_dir / "observation.json").read_text(encoding="utf-8")
            )
            self.assertEqual(
                persisted_run["maturity_scorecard_hash"],
                diagnosis["maturity_scorecard"]["scorecard_hash"],
            )
            self.assertEqual(
                persisted_run["validation_hash"],
                loop._canonical_hash(persisted_validation),
            )
            self.assertEqual(
                persisted_run["observation_hash"],
                loop._canonical_hash(persisted_observation),
            )
            self.assertEqual(
                persisted_run["diagnosis_hash"],
                loop._canonical_hash(diagnosis),
            )
            self.assertFalse(diagnosis["external_mutation_authorized"])
            events = (run_dir / "events.jsonl").read_text(encoding="utf-8")
            self.assertIn('"status": "finished"', events)

    def test_global_pointer_failure_preserves_recoverable_terminal_run(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            observed = observation(ga4=False, gsc=False, pending=2)
            original_atomic = loop._atomic

            def fake_observe(run_dir, *, runtime_contract=None):
                observed["runtime_contract"] = runtime_contract
                write_synthetic_release_evidence(run_dir)
                original_atomic(run_dir / "observation.json", observed)
                return observed

            def fail_global_learning_pointer(path, payload):
                if Path(path) == root / loop.ERROR_LEARNING_STATE_FILE:
                    raise OSError("simulated global pointer failure")
                return original_atomic(path, payload)

            with (mock.patch.object(loop, "IMPROVEMENT_RUNS_DIR", root),
                  mock.patch.object(loop, "observe", side_effect=fake_observe),
                  mock.patch.object(
                      loop, "_atomic", side_effect=fail_global_learning_pointer
                  )):
                with self.assertRaisesRegex(OSError, "global pointer failure"):
                    loop.execute(run_id="recoverable-run")

            run_dir = root / "recoverable-run"
            run = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
            self.assertEqual(run["status"], "COMPLETED_WITH_BLOCKERS")
            self.assertTrue(run["validation_passed"])
            self.assertFalse((run_dir / "failure.txt").exists())
            self.assertTrue((run_dir / "recovery-required.txt").is_file())
            recovered = loop._load_error_learning_state(root)
            self.assertEqual(recovered["last_run_id"], "recoverable-run")
            self.assertEqual(recovered["state_hash"], run["error_learning_state_hash"])

    def test_error_learning_tracks_recurrence_resolution_and_regression(self):
        base = (
            dt.datetime.now(dt.timezone.utc).replace(microsecond=0)
            - dt.timedelta(hours=3)
        )
        diagnosed = loop.diagnose(
            observation(ga4=False, revenue=100), self.contract(), now=base
        )
        first = loop.build_error_learning_state(
            loop._empty_error_learning_state(), diagnosed, run_id="run-1",
            observed_at=base.isoformat(),
        )
        self.assertIn("ga4_not_decisionable", first["summary"]["new_incidents"])
        second = loop.build_error_learning_state(
            first, diagnosed, run_id="run-2",
            observed_at=(base + dt.timedelta(hours=1)).isoformat(),
        )
        self.assertIn("ga4_not_decisionable",
                      second["summary"]["recurring_incidents"])
        resolved = loop.build_error_learning_state(
            second, {"findings": [], "priorities": []}, run_id="run-3",
            observed_at=(base + dt.timedelta(hours=2)).isoformat(),
        )
        self.assertIn("ga4_not_decisionable",
                      resolved["summary"]["resolved_incidents"])
        regressed = loop.build_error_learning_state(
            resolved, diagnosed, run_id="run-4",
            observed_at=(base + dt.timedelta(hours=3)).isoformat(),
        )
        self.assertIn("ga4_not_decisionable",
                      regressed["summary"]["regressed_incidents"])
        self.assertEqual(
            loop.error_learning_state_errors(
                regressed, current_findings=diagnosed["findings"]
            ),
            [],
        )

    def test_error_learning_rejects_future_build_and_accepts_history_now(self):
        current = dt.datetime.now(dt.timezone.utc).replace(microsecond=0)
        historical = current - dt.timedelta(minutes=1)
        diagnosed = {
            "findings": [{
                "id": "chronology-fixture",
                "severity": "P1",
                "fact": "bounded chronology fixture",
                "evidence": {"source": "unit-test"},
            }],
            "priorities": [],
        }
        first = loop.build_error_learning_state(
            loop._empty_error_learning_state(), diagnosed,
            run_id="run-history", observed_at=historical.isoformat(),
            now=current,
        )
        latest = loop.build_error_learning_state(
            first, diagnosed, run_id="run-now",
            observed_at=current.isoformat(), now=current,
        )
        self.assertEqual(
            loop.error_learning_state_errors(
                latest, not_before=historical, not_after=current
            ),
            [],
        )
        with self.assertRaisesRegex(ValueError, "cannot be in the future"):
            loop.build_error_learning_state(
                latest, diagnosed, run_id="run-future",
                observed_at=(current + dt.timedelta(seconds=1)).isoformat(),
                now=current,
            )

    def test_error_learning_rejects_sealed_state_after_terminal_finish(self):
        terminal_time = dt.datetime.now(dt.timezone.utc).replace(microsecond=0)
        future = terminal_time + dt.timedelta(days=1)
        diagnosed = {
            "findings": [{
                "id": "future-fixture",
                "severity": "P1",
                "fact": "sealed future chronology fixture",
                "evidence": {"source": "unit-test"},
            }],
            "priorities": [],
        }
        future_state = loop.build_error_learning_state(
            loop._empty_error_learning_state(), diagnosed,
            run_id="run-future", observed_at=future.isoformat(), now=future,
        )
        self.assertEqual(loop.error_learning_state_errors(future_state), [])
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_learning_commit(
                root, "run-future", future_state, finished_at=terminal_time
            )
            loop._atomic(root / loop.ERROR_LEARNING_STATE_FILE, future_state)
            with self.assertRaisesRegex(ValueError, "proven chronology"):
                loop._load_error_learning_state(root)

    def test_error_learning_loader_rejects_fully_shifted_future_terminal(self):
        current = dt.datetime.now(dt.timezone.utc).replace(microsecond=0)
        future = current + dt.timedelta(days=365)
        diagnosed = {
            "findings": [{
                "id": "fully-shifted-future-terminal",
                "severity": "P1",
                "fact": "all terminal chronology was shifted into the future",
                "evidence": {"source": "unit-test"},
            }],
            "priorities": [],
        }
        future_state = loop.build_error_learning_state(
            loop._empty_error_learning_state(), diagnosed,
            run_id="run-future", observed_at=future.isoformat(), now=future,
        )
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_learning_commit(
                root, "run-future", future_state, finished_at=future
            )
            loop._atomic(root / loop.ERROR_LEARNING_STATE_FILE, future_state)
            with self.assertRaisesRegex(ValueError, "proven chronology|future"):
                loop._load_error_learning_state(root, now=current)

    def test_error_learning_historical_recovery_uses_injected_time(self):
        finished = dt.datetime(2026, 1, 2, tzinfo=dt.timezone.utc)
        diagnosed = {
            "findings": [{
                "id": "historical-terminal",
                "severity": "P1",
                "fact": "historical terminal remains recoverable",
                "evidence": {"source": "unit-test"},
            }],
            "priorities": [],
        }
        state = loop.build_error_learning_state(
            loop._empty_error_learning_state(), diagnosed,
            run_id="run-history", observed_at=finished.isoformat(), now=finished,
        )
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_learning_commit(
                root, "run-history", state, finished_at=finished
            )
            recovered = loop._load_error_learning_state(
                root, now=finished + dt.timedelta(seconds=1)
            )
            self.assertEqual(recovered, state)

    def test_error_learning_persistent_state_is_bound_to_last_run_snapshot(self):
        base = dt.datetime.now(dt.timezone.utc).replace(microsecond=0)
        diagnosed = loop.diagnose(
            observation(ga4=False, revenue=100), self.contract(), now=base
        )
        state = loop.build_error_learning_state(
            loop._empty_error_learning_state(), diagnosed, run_id="run-1",
            observed_at=base.isoformat(),
        )
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_learning_commit(root, "run-1", state, finished_at=base)
            loop._atomic(root / loop.ERROR_LEARNING_STATE_FILE, state)
            self.assertEqual(loop._load_error_learning_state(root), state)

            altered = json.loads(json.dumps(state))
            altered["summary"]["new_incidents"] = []
            loop._seal_error_learning_state(altered)
            loop._atomic(root / loop.ERROR_LEARNING_STATE_FILE, altered)
            with self.assertRaisesRegex(ValueError, "last run snapshot"):
                loop._load_error_learning_state(root)

    def test_error_learning_rejects_global_pointer_bound_to_nonterminal_run(self):
        base = dt.datetime.now(dt.timezone.utc).replace(microsecond=0)
        diagnosed = loop.diagnose(
            observation(ga4=False, revenue=100), self.contract(), now=base
        )
        state = loop.build_error_learning_state(
            loop._empty_error_learning_state(), diagnosed, run_id="run-1",
            observed_at=base.isoformat(),
        )
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_dir = write_learning_commit(
                root, "run-1", state, finished_at=base
            )
            run = loop._load(run_dir / "run.json")
            run["status"] = "STARTED"
            run["finished_at"] = None
            loop._atomic(run_dir / "run.json", run)
            loop._atomic(root / loop.ERROR_LEARNING_STATE_FILE, state)
            with self.assertRaisesRegex(ValueError, "validated terminal run"):
                loop._load_error_learning_state(root)

    def test_error_learning_recovers_newer_validated_terminal_snapshot(self):
        base = (
            dt.datetime.now(dt.timezone.utc).replace(microsecond=0)
            - dt.timedelta(minutes=5)
        )
        first_diagnosis = loop.diagnose(
            observation(ga4=False, revenue=100), self.contract(), now=base
        )
        first = loop.build_error_learning_state(
            loop._empty_error_learning_state(), first_diagnosis,
            run_id="run-1", observed_at=base.isoformat(),
        )
        second = loop.build_error_learning_state(
            first, first_diagnosis, run_id="run-2",
            observed_at=(base + dt.timedelta(minutes=5)).isoformat(),
        )
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_learning_commit(root, "run-1", first, finished_at=base)
            write_learning_commit(
                root, "run-2", second,
                finished_at=base + dt.timedelta(minutes=5),
            )
            loop._atomic(root / loop.ERROR_LEARNING_STATE_FILE, first)
            self.assertEqual(loop._load_error_learning_state(root), second)

    def test_error_learning_recovery_skips_unrelated_corrupt_terminal_bundle(self):
        base = dt.datetime.now(dt.timezone.utc).replace(microsecond=0)
        diagnosed = loop.diagnose(
            observation(ga4=False, revenue=100), self.contract(), now=base
        )
        valid = loop.build_error_learning_state(
            loop._empty_error_learning_state(), diagnosed, run_id="run-valid",
            observed_at=base.isoformat(),
        )
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_learning_commit(root, "run-valid", valid, finished_at=base)
            loop._atomic(root / loop.ERROR_LEARNING_STATE_FILE, valid)
            corrupt = root / "run-corrupt"
            corrupt.mkdir()
            loop._atomic(corrupt / "run.json", {
                "run_id": "run-corrupt",
                "status": "COMPLETED_WITH_BLOCKERS",
                "started_at": (base + dt.timedelta(minutes=4)).isoformat(),
                "finished_at": (base + dt.timedelta(minutes=5)).isoformat(),
                "validation_passed": True,
            })

            self.assertEqual(loop._load_error_learning_state(root), valid)

    def test_error_learning_recovers_hash_chain_with_equal_finish_times(self):
        base = dt.datetime.now(dt.timezone.utc).replace(microsecond=0)
        diagnosed = loop.diagnose(
            observation(ga4=False, revenue=100), self.contract(), now=base
        )
        first = loop.build_error_learning_state(
            loop._empty_error_learning_state(), diagnosed, run_id="run-first",
            observed_at=base.isoformat(),
        )
        second = loop.build_error_learning_state(
            first, diagnosed, run_id="run-second",
            observed_at=base.isoformat(),
        )
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_learning_commit(root, "run-first", first, finished_at=base)
            write_learning_commit(root, "run-second", second, finished_at=base)
            loop._atomic(root / loop.ERROR_LEARNING_STATE_FILE, first)

            self.assertEqual(loop._load_error_learning_state(root), second)

    def test_error_learning_recovery_rejects_a_forked_hash_chain(self):
        base = (
            dt.datetime.now(dt.timezone.utc).replace(microsecond=0)
            - dt.timedelta(seconds=1)
        )
        diagnosed = loop.diagnose(
            observation(ga4=False, revenue=100), self.contract(), now=base
        )
        empty = loop._empty_error_learning_state()
        left = loop.build_error_learning_state(
            empty, diagnosed, run_id="run-left", observed_at=base.isoformat()
        )
        right = loop.build_error_learning_state(
            empty, diagnosed, run_id="run-right",
            observed_at=(base + dt.timedelta(seconds=1)).isoformat(),
        )
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_learning_commit(root, "run-left", left, finished_at=base)
            write_learning_commit(
                root, "run-right", right,
                finished_at=base + dt.timedelta(seconds=1),
            )

            with self.assertRaisesRegex(ValueError, "ambiguous recovery chain"):
                loop._load_error_learning_state(root)

    def test_error_learning_summary_and_lifecycle_are_validated(self):
        state = loop._empty_error_learning_state()
        state["summary"]["open_incidents"] = 1
        loop._seal_error_learning_state(state)
        self.assertIn(
            "error-learning open incident count is inconsistent",
            loop.error_learning_state_errors(state),
        )

        base = dt.datetime.now(dt.timezone.utc).replace(microsecond=0)
        valid = loop.build_error_learning_state(
            loop._empty_error_learning_state(), {
                "findings": [
                    {"id": "one", "severity": "P1", "fact": "first", "evidence": {}}
                ],
                "priorities": [],
            }, run_id="run-1", observed_at=base.isoformat(),
        )
        fingerprint = next(iter(valid["incidents"]))
        valid["incidents"][fingerprint]["consecutive_runs"] = "invalid"
        loop._seal_error_learning_state(valid)
        self.assertTrue(
            any("incident count is invalid" in item
                for item in loop.error_learning_state_errors(valid))
        )

    def test_error_learning_fails_closed_when_open_memory_exceeds_bound(self):
        base = dt.datetime.now(dt.timezone.utc).replace(microsecond=0)
        diagnosis = {
            "findings": [
                {"id": "one", "severity": "P1", "fact": "first", "evidence": {}},
                {"id": "two", "severity": "P1", "fact": "second", "evidence": {}},
            ],
            "priorities": [],
        }
        with self.assertRaisesRegex(ValueError, "memory bound"):
            loop.build_error_learning_state(
                loop._empty_error_learning_state(), diagnosis, run_id="run-1",
                observed_at=base.isoformat(), max_incidents=1,
            )

    def test_control_health_counts_recurring_fingerprints_not_finding_ids(self):
        base = (
            dt.datetime.now(dt.timezone.utc).replace(microsecond=0)
            - dt.timedelta(minutes=1)
        )
        diagnosis = {
            "findings": [
                {"id": "shared", "severity": "P1", "fact": "first fact",
                 "evidence": {}},
                {"id": "shared", "severity": "P1", "fact": "second fact",
                 "evidence": {}},
            ],
            "priorities": [],
        }
        first = loop.build_error_learning_state(
            loop._empty_error_learning_state(), diagnosis,
            run_id="run-1", observed_at=base.isoformat(),
        )
        second = loop.build_error_learning_state(
            first, diagnosis, run_id="run-2",
            observed_at=(base + dt.timedelta(minutes=1)).isoformat(),
        )
        with tempfile.TemporaryDirectory() as tmp:
            health = loop.build_control_health(
                Path(tmp), second, now=base + dt.timedelta(minutes=2),
            )
        self.assertEqual(second["summary"]["recurring_incidents"], ["shared"])
        self.assertEqual(health["kpis"]["recurring_open_incidents"], 2)

    def test_error_learning_prioritizes_recurring_action_within_same_rank(self):
        learning = loop._empty_error_learning_state()
        learning["actions"] = {
            "refresh_official_source_snapshot": {
                "kind": "refresh_official_source_snapshot",
                "occurrences": 8,
                "consecutive_runs": 8,
                "regression_count": 1,
                "status": "OPEN",
            },
            "repair_measurement": {
                "kind": "repair_measurement",
                "occurrences": 1,
                "consecutive_runs": 1,
                "regression_count": 0,
                "status": "OPEN",
            },
        }
        loop._seal_error_learning_state(learning)
        result = loop.diagnose(
            observation(ga4=False, revenue=100, official_current=False),
            self.contract(), learning_state=learning,
        )
        self.assertEqual(
            result["priorities"][0]["type"],
            "refresh_official_source_snapshot",
        )

    def test_control_health_keeps_legacy_false_fatals_unproven(self):
        now = dt.datetime.now(dt.timezone.utc).replace(microsecond=0)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            completed = root / "completed"
            completed.mkdir()
            loop._atomic(completed / "run.json", {
                "run_id": "completed", "status": "COMPLETED_WITH_BLOCKERS",
                "started_at": (now - dt.timedelta(hours=3)).isoformat(),
                "finished_at": (now - dt.timedelta(hours=2)).isoformat(),
            })
            started = root / "started"
            started.mkdir()
            loop._atomic(started / "run.json", {
                "run_id": "started", "status": "STARTED",
                "started_at": (now - dt.timedelta(hours=1)).isoformat(),
            })
            legacy = root / "legacy"
            legacy.mkdir()
            loop._atomic(legacy / "run.json", {
                "run_id": "legacy", "status": "FAILED_VALIDATION",
                "started_at": (now - dt.timedelta(hours=5)).isoformat(),
                "finished_at": (now - dt.timedelta(hours=4)).isoformat(),
            })
            loop._atomic(legacy / "validation.json", {
                "errors": [
                    "decision readiness blocked: publication_authority_false",
                    "maturity hard blockers: publication_inputs_ready",
                ]
            })
            health = loop.build_control_health(
                root, loop._empty_error_learning_state(), now=now
            )
        self.assertEqual(health["kpis"]["started_runs_7d"], 0)
        self.assertEqual(health["kpis"]["terminal_runs_7d"], 0)
        self.assertEqual(
            health["kpis"]["task_receipt_coverage_state"], "NO_RECEIPTS"
        )
        self.assertIsNone(health["kpis"]["terminal_control_run_rate_7d"])
        self.assertEqual(health["improvement_bundles"]["started_7d"], 3)
        self.assertEqual(health["improvement_bundles"]["terminal_7d"], 2)
        self.assertAlmostEqual(
            health["improvement_bundles"]["terminal_rate_7d"], 2 / 3
        )
        self.assertIsNone(
            health["kpis"]["publication_blocker_false_fatal_count"]
        )
        self.assertEqual(
            health["kpis"]["observed_publication_blocker_false_fatal_count"],
            0,
        )
        self.assertEqual(
            health["kpis"]["legacy_unproven_false_fatal_signals"], 1
        )

    def test_control_health_failed_run_does_not_refresh_evidence_age(self):
        now = dt.datetime.now(dt.timezone.utc).replace(microsecond=0)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.write_complete_weekly_bundle(
                root, "completed", evaluated_at=now - dt.timedelta(hours=2)
            )
            failed = root / "failed"
            failed.mkdir()
            loop._atomic(failed / "run.json", {
                "run_id": "failed", "status": "FAILED",
                "started_at": (now - dt.timedelta(minutes=40)).isoformat(),
                "finished_at": (now - dt.timedelta(minutes=30)).isoformat(),
            })
            health = loop.build_control_health(
                root, loop._empty_error_learning_state(), now=now
            )
        self.assertEqual(health["improvement_bundles"]["terminal_7d"], 2)
        self.assertEqual(health["kpis"]["terminal_runs_7d"], 0)
        self.assertEqual(health["kpis"]["fresh_evidence_age_hours"], 2.0)

    def test_unbound_legacy_bundle_does_not_refresh_evidence_age(self):
        now = dt.datetime.now(dt.timezone.utc).replace(microsecond=0)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_dir = root / "legacy-unbound"
            run_dir.mkdir()
            for name in (
                "observation.json", "diagnosis.json", "validation.json",
                "maturity-scorecard.json",
            ):
                loop._atomic(run_dir / name, {"parseable": name})
            row = {
                "run_id": "legacy-unbound",
                "status": "COMPLETED_WITH_BLOCKERS",
                "started_at": (now - dt.timedelta(minutes=2)).isoformat(),
                "finished_at": (now - dt.timedelta(minutes=1)).isoformat(),
            }
            loop._atomic(run_dir / "run.json", row)

            self.assertFalse(loop._has_complete_evidence_bundle(run_dir, row))
            health = loop.build_control_health(
                root, loop._empty_error_learning_state(), now=now,
            )

        self.assertIsNone(health["kpis"]["fresh_evidence_age_hours"])

    def test_unpersisted_current_state_does_not_refresh_evidence_age(self):
        now = dt.datetime.now(dt.timezone.utc).replace(microsecond=0)
        current = {
            "schema_version": 2,
            "run_id": "not-persisted",
            "cadence": "daily",
            "status": "COMPLETED",
            "started_at": (now - dt.timedelta(minutes=2)).isoformat(),
            "finished_at": (now - dt.timedelta(minutes=1)).isoformat(),
            "validation_passed": True,
        }
        with tempfile.TemporaryDirectory() as tmp:
            health = loop.build_control_health(
                Path(tmp), loop._empty_error_learning_state(), now=now,
                current_state=current,
            )

        self.assertIsNone(health["kpis"]["fresh_evidence_age_hours"])
        self.assertEqual(health["improvement_bundles"]["terminal_7d"], 1)

    def test_schema2_placeholder_bundle_does_not_refresh_evidence_age(self):
        now = dt.datetime.now(dt.timezone.utc).replace(microsecond=0)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_dir = root / "placeholder"
            run_dir.mkdir()
            for name in (
                "observation.json", "diagnosis.json", "validation.json",
                "maturity-scorecard.json",
            ):
                loop._atomic(run_dir / name, {"placeholder": name})
            loop._atomic(run_dir / "run.json", {
                "schema_version": 2,
                "run_id": "placeholder",
                "cadence": "daily",
                "status": "COMPLETED",
                "started_at": (now - dt.timedelta(minutes=2)).isoformat(),
                "finished_at": (now - dt.timedelta(minutes=1)).isoformat(),
                "validation_passed": True,
            })
            health = loop.build_control_health(
                root, loop._empty_error_learning_state(), now=now,
            )

        self.assertIsNone(health["kpis"]["fresh_evidence_age_hours"])

    def test_complete_schema2_bundle_is_bound_to_observation_and_diagnosis(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_dir, observed, _, _, _, run = (
                self.write_complete_weekly_bundle(root, "bound-bundle")
            )
            self.assertTrue(loop._has_complete_evidence_bundle(run_dir, run))
            observed["tampered_after_validation"] = True
            loop._atomic(run_dir / "observation.json", observed)

            self.assertFalse(loop._has_complete_evidence_bundle(run_dir, run))

    def test_legacy_corrupt_or_nonfinite_artifact_is_not_complete_evidence(self):
        now = dt.datetime.now(dt.timezone.utc).replace(microsecond=0)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_dir = root / "legacy-corrupt"
            run_dir.mkdir()
            row = {
                "run_id": "legacy-corrupt",
                "status": "COMPLETED_WITH_BLOCKERS",
                "started_at": (now - dt.timedelta(minutes=2)).isoformat(),
                "finished_at": (now - dt.timedelta(minutes=1)).isoformat(),
            }
            for name in (
                "observation.json", "diagnosis.json", "validation.json",
                "maturity-scorecard.json",
            ):
                loop._atomic(run_dir / name, {"evidence": name})

            (run_dir / "observation.json").write_text("{", encoding="utf-8")
            self.assertFalse(loop._has_complete_evidence_bundle(run_dir, row))
            (run_dir / "observation.json").write_text(
                '{"metric": NaN}', encoding="utf-8"
            )
            self.assertFalse(loop._has_complete_evidence_bundle(run_dir, row))

    def test_future_terminal_bundle_cannot_report_negative_evidence_age(self):
        now = dt.datetime.now(dt.timezone.utc).replace(microsecond=0)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.write_complete_weekly_bundle(
                root, "current-bundle", evaluated_at=now
            )
            self.write_complete_weekly_bundle(
                root, "future-bundle", evaluated_at=now + dt.timedelta(hours=1)
            )
            health = loop.build_control_health(
                root, loop._empty_error_learning_state(),
                now=now + dt.timedelta(minutes=2),
            )

            self.assertEqual(
                health["kpis"]["fresh_evidence_age_hours"], 0.033
            )

    def test_task_receipt_rate_is_unavailable_during_partial_window(self):
        now = dt.datetime.now(dt.timezone.utc).replace(microsecond=0)
        with tempfile.TemporaryDirectory() as tmp:
            receipt_root = Path(tmp) / "task-runs"
            write_task_receipt(
                receipt_root, "ngernduangold_daily", "daily-current",
                started_at=now - dt.timedelta(hours=2),
                status="FINISHED", finished_at=now - dt.timedelta(hours=1),
                execution_state="PASS", final_rc=0,
            )
            health = loop.build_control_health(
                Path(tmp) / "improvement-runs",
                loop._empty_error_learning_state(), now=now,
                task_runs_root=receipt_root,
                receipt_monitoring=valid_receipt_monitoring(
                    now - dt.timedelta(hours=3)
                ),
            )
        self.assertEqual(
            health["kpis"]["task_receipt_coverage_state"], "PARTIAL_WINDOW"
        )
        self.assertEqual(
            health["kpis"]["observed_terminal_control_run_rate_7d"], 1.0
        )
        self.assertIsNone(health["kpis"]["terminal_control_run_rate_7d"])
        self.assertFalse(health["task_receipts"]["scheduler_launch_proven"])

    def test_task_receipt_consumer_matches_producer_step_shape_contract(self):
        now = dt.datetime.now(dt.timezone.utc).replace(microsecond=0)
        started = now - dt.timedelta(minutes=10)
        steps = canonical_receipt_steps("ngernduangold_daily", started)
        with tempfile.TemporaryDirectory() as tmp:
            path = write_task_receipt(
                Path(tmp), "ngernduangold_daily", "shape-contract",
                started_at=started, status="FINISHED",
                finished_at=now - dt.timedelta(minutes=1),
                execution_state="PASS", final_rc=0, steps=steps,
            )
            original = loop._load(path)

        self.assertEqual(
            loop._task_receipt_contract_errors(
                original, task_name="ngernduangold_daily",
                run_id="shape-contract", current=now,
            ),
            [],
        )
        cases = []

        unsafe_id = json.loads(json.dumps(original))
        unsafe_id["steps"][1]["step_id"] = "../../forged"
        cases.append((
            "unsafe step id", unsafe_id, "receipt step identity is invalid",
        ))

        reversed_step = json.loads(json.dumps(original))
        reversed_step["steps"][1]["started_at"] = started.isoformat()
        reversed_step["steps"][1]["finished_at"] = (
            started + dt.timedelta(milliseconds=500)
        ).isoformat()
        cases.append((
            "reversed chronology", reversed_step,
            "receipt step chronology is invalid",
        ))

        future_step = json.loads(json.dumps(original))
        future_step["steps"][1]["started_at"] = (
            now + dt.timedelta(hours=1)
        ).isoformat()
        future_step["steps"][1]["finished_at"] = (
            now + dt.timedelta(hours=1, seconds=1)
        ).isoformat()
        cases.append((
            "future and post-terminal step", future_step,
            "receipt step time is in the future",
        ))

        bool_sequence = json.loads(json.dumps(original))
        bool_sequence["steps"][0]["sequence"] = True
        cases.append((
            "boolean sequence", bool_sequence,
            "receipt step sequence is invalid",
        ))

        bool_counter = json.loads(json.dumps(original))
        bool_counter["transition_counter"] = True
        cases.append((
            "boolean transition counter", bool_counter,
            "receipt transition count is invalid",
        ))

        malformed_launch_error = json.loads(json.dumps(original))
        malformed_launch_error["steps"][3]["launch_error"] = {}
        cases.append((
            "malformed launch error", malformed_launch_error,
            "receipt step launch error is invalid",
        ))

        mutated_command = json.loads(json.dumps(original))
        mutated_command["steps"][3]["command_hash"] = "c" * 64
        cases.append((
            "mutated command hash", mutated_command,
            "receipt steps are not an exact ordered manifest prefix",
        ))

        mutated_contract_producer = json.loads(json.dumps(original))
        mutated_contract_producer["task_contract"][
            "receipt_producer_sha256"
        ] = "c" * 64
        cases.append((
            "mutated task-contract producer binding", mutated_contract_producer,
            "receipt task contract producer binding is mismatched",
        ))

        for label, candidate, expected_error in cases:
            with self.subTest(label=label):
                sealed = loop.task_run_receipt.seal_receipt(candidate)
                errors = loop._task_receipt_contract_errors(
                    sealed, task_name="ngernduangold_daily",
                    run_id="shape-contract", current=now,
                )
                self.assertIn(expected_error, errors)
                with self.assertRaises(loop.task_run_receipt.ReceiptError):
                    loop.task_run_receipt._validate_receipt_shape(sealed)

    def test_task_receipt_consumer_rejects_unattested_stable_producer(self):
        now = dt.datetime.now(dt.timezone.utc).replace(microsecond=0)
        with tempfile.TemporaryDirectory() as tmp:
            path = write_task_receipt(
                Path(tmp), "ngernduangold_daily", "producer-contract",
                started_at=now - dt.timedelta(minutes=2),
                status="FINISHED", finished_at=now - dt.timedelta(minutes=1),
                execution_state="PASS", final_rc=0,
            )
            candidate = loop._load(path)
        candidate["receipt_tool"]["sha256_start"] = "c" * 64
        candidate["receipt_tool"]["sha256_end"] = "c" * 64
        candidate["task_contract"] = loop.task_run_receipt.build_task_contract(
            "ngernduangold_daily",
            candidate["runner"]["sha256_start"],
            receipt_producer_sha256="c" * 64,
        )
        sealed = loop.task_run_receipt.seal_receipt(candidate)
        errors = loop._task_receipt_contract_errors(
            sealed,
            task_name="ngernduangold_daily",
            run_id="producer-contract",
            current=now,
            trusted_producer_hashes=[
                loop._path_sha256(loop.TASK_RECEIPT_TOOL_PATH)
            ],
        )
        self.assertIn("receipt tool hash is not an attested producer", errors)
        self.assertNotIn(
            "receipt task contract producer binding is mismatched", errors
        )

    def test_empty_resealed_monitored_pass_is_invalid_and_not_counted(self):
        now = dt.datetime.now(dt.timezone.utc).replace(microsecond=0)
        with tempfile.TemporaryDirectory() as tmp:
            receipt_root = Path(tmp) / "task-runs"
            path = write_task_receipt(
                receipt_root, "ngernduangold_daily", "empty-pass",
                started_at=now - dt.timedelta(hours=1), status="RUNNING",
            )
            forged = loop._load(path)
            forged.update({
                "status": "FINISHED",
                "terminal_kind": "end",
                "terminal_reason": "normal_end",
                "terminal_step_id": None,
                "finished_at": (now - dt.timedelta(minutes=30)).isoformat(),
                "execution_state": "PASS",
                "final_rc": 0,
                "transition_counter": 1,
            })
            for binding in ("runner", "receipt_tool"):
                forged[binding]["sha256_end"] = forged[binding]["sha256_start"]
                forged[binding]["stable_during_run"] = True
            loop._atomic(path, loop.task_run_receipt.seal_receipt(forged))
            health = loop.build_control_health(
                Path(tmp) / "improvement-runs",
                loop._empty_error_learning_state(), now=now,
                task_runs_root=receipt_root,
                receipt_monitoring=valid_receipt_monitoring(
                    now - dt.timedelta(hours=2)
                ),
            )
        self.assertEqual(
            health["kpis"]["task_receipt_coverage_state"], "INVALID_RECEIPTS"
        )
        self.assertEqual(health["kpis"]["terminal_runs_7d"], 0)
        self.assertEqual(health["kpis"]["invalid_task_receipts"], 1)
        self.assertIsNone(health["kpis"]["terminal_control_run_rate_7d"])
        self.assertIn(
            "finished receipt did not complete its task manifest",
            health["task_receipts"]["invalid_receipts"][0]["errors"],
        )

    def test_preinstrumentation_schema2_receipt_is_legacy_not_trusted(self):
        now = dt.datetime.now(dt.timezone.utc).replace(microsecond=0)
        instrumentation = now - dt.timedelta(minutes=30)
        with tempfile.TemporaryDirectory() as tmp:
            receipt_root = Path(tmp) / "task-runs"
            path = write_task_receipt(
                receipt_root, "ngernduangold_weekly", "legacy-schema2",
                started_at=now - dt.timedelta(hours=2),
                status="FINISHED",
                finished_at=now - dt.timedelta(hours=1),
                execution_state="PASS", final_rc=0,
            )
            legacy = loop._load(path)
            legacy["schema_version"] = 2
            legacy.pop("task_contract")
            loop._atomic(path, loop.task_run_receipt.seal_receipt(legacy))
            legacy = loop._load(path)
            health = loop.build_control_health(
                Path(tmp) / "improvement-runs",
                loop._empty_error_learning_state(), now=now,
                task_runs_root=receipt_root,
                receipt_monitoring=valid_receipt_monitoring(
                    instrumentation,
                    legacy_receipt_attestations=[{
                        "task_name": "ngernduangold_weekly",
                        "run_id": "legacy-schema2",
                        "receipt_hash": legacy["receipt_hash"],
                        "migration_state": "LEGACY_UNVALIDATED",
                        "errors": [],
                    }],
                ),
            )
        self.assertEqual(
            health["kpis"]["task_receipt_coverage_state"], "NO_RECEIPTS"
        )
        self.assertEqual(health["task_receipts"]["legacy_receipt_count"], 1)
        self.assertEqual(
            health["task_receipts"]["legacy_unvalidated_receipt_count"], 1
        )
        self.assertEqual(health["kpis"]["invalid_task_receipts"], 0)
        self.assertEqual(health["kpis"]["terminal_runs_7d"], 0)
        self.assertIsNone(health["kpis"]["terminal_control_run_rate_7d"])

    def test_preactivation_schema3_receipt_is_diagnostic_only(self):
        now = dt.datetime.now(dt.timezone.utc).replace(microsecond=0)
        instrumentation = now - dt.timedelta(minutes=30)
        with tempfile.TemporaryDirectory() as tmp:
            receipt_root = Path(tmp) / "task-runs"
            write_task_receipt(
                receipt_root, "ngernduangold_weekly", "preactivation-valid",
                started_at=now - dt.timedelta(hours=2),
                status="FINISHED", finished_at=now - dt.timedelta(hours=1),
                execution_state="PASS", final_rc=0,
            )
            write_task_receipt(
                receipt_root, "ngernduangold_daily", "postactivation-valid",
                started_at=now - dt.timedelta(minutes=20),
                status="FINISHED", finished_at=now - dt.timedelta(minutes=10),
                execution_state="PASS", final_rc=0,
            )
            health = loop.build_control_health(
                Path(tmp) / "improvement-runs",
                loop._empty_error_learning_state(), now=now,
                task_runs_root=receipt_root,
                receipt_monitoring=valid_receipt_monitoring(instrumentation),
            )

        receipts = health["task_receipts"]
        self.assertEqual(
            health["kpis"]["task_receipt_coverage_state"], "PARTIAL_WINDOW"
        )
        self.assertEqual(receipts["window_observed"], 1)
        self.assertEqual(receipts["window_terminal"], 1)
        self.assertEqual(receipts["invalid_receipt_count"], 0)
        self.assertEqual(receipts["historical_invalid_receipt_count"], 0)
        self.assertEqual(receipts["pre_activation_receipt_count"], 1)
        self.assertEqual(receipts["pre_activation_valid_receipt_count"], 1)
        self.assertEqual(receipts["pre_activation_invalid_receipt_count"], 0)
        self.assertEqual(
            receipts["pre_activation_receipts"][0]["run_id"],
            "preactivation-valid",
        )
        self.assertEqual(
            receipts["pre_activation_receipts"][0]["classification"],
            "PRE_ACTIVATION_VALID_DIAGNOSTIC_ONLY",
        )
        self.assertEqual(
            receipts["per_task_coverage"]["ngernduangold_weekly"]["state"],
            "MISSING",
        )

    def test_preactivation_invalid_schema3_is_historical_diagnostic(self):
        now = dt.datetime.now(dt.timezone.utc).replace(microsecond=0)
        instrumentation = now - dt.timedelta(minutes=30)
        with tempfile.TemporaryDirectory() as tmp:
            receipt_root = Path(tmp) / "task-runs"
            path = write_task_receipt(
                receipt_root, "ngernduangold_weekly", "preactivation-invalid",
                started_at=now - dt.timedelta(hours=2),
                status="FINISHED", finished_at=now - dt.timedelta(hours=1),
                execution_state="PASS", final_rc=0,
            )
            candidate = loop._load(path)
            candidate["origin"] = "SCHEDULED"
            loop._atomic(path, loop.task_run_receipt.seal_receipt(candidate))
            write_task_receipt(
                receipt_root, "ngernduangold_daily", "postactivation-valid",
                started_at=now - dt.timedelta(minutes=20),
                status="FINISHED", finished_at=now - dt.timedelta(minutes=10),
                execution_state="PASS", final_rc=0,
            )
            health = loop.build_control_health(
                Path(tmp) / "improvement-runs",
                loop._empty_error_learning_state(), now=now,
                task_runs_root=receipt_root,
                receipt_monitoring=valid_receipt_monitoring(instrumentation),
            )

        receipts = health["task_receipts"]
        self.assertEqual(
            health["kpis"]["task_receipt_coverage_state"], "PARTIAL_WINDOW"
        )
        self.assertEqual(health["kpis"]["invalid_task_receipts"], 0)
        self.assertEqual(receipts["historical_invalid_receipt_count"], 1)
        self.assertEqual(receipts["pre_activation_receipt_count"], 1)
        self.assertEqual(receipts["pre_activation_valid_receipt_count"], 0)
        self.assertEqual(receipts["pre_activation_invalid_receipt_count"], 1)
        self.assertEqual(receipts["all_invalid_receipt_count"], 1)
        self.assertEqual(
            receipts["historical_invalid_receipts"][0]["run_id"],
            "preactivation-invalid",
        )
        self.assertEqual(
            receipts["historical_invalid_receipts"][0]["classification"],
            "PRE_ACTIVATION_INVALID",
        )
        self.assertEqual(
            receipts["pre_activation_receipts"][0]["run_id"],
            "preactivation-invalid",
        )
        self.assertIn(
            "receipt origin is unsupported",
            receipts["historical_invalid_receipts"][0]["errors"],
        )

    def test_unreadable_receipt_without_started_at_cannot_claim_preactivation(self):
        now = dt.datetime.now(dt.timezone.utc).replace(microsecond=0)
        instrumentation = now - dt.timedelta(minutes=30)
        with tempfile.TemporaryDirectory() as tmp:
            receipt_root = Path(tmp) / "task-runs"
            path = receipt_root / "ngernduangold_daily" / "unreadable.json"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("{", encoding="utf-8")
            health = loop.build_control_health(
                Path(tmp) / "improvement-runs",
                loop._empty_error_learning_state(), now=now,
                task_runs_root=receipt_root,
                receipt_monitoring=valid_receipt_monitoring(instrumentation),
            )

        receipts = health["task_receipts"]
        self.assertEqual(
            health["kpis"]["task_receipt_coverage_state"], "INVALID_RECEIPTS"
        )
        self.assertEqual(receipts["invalid_receipt_count"], 1)
        self.assertEqual(receipts["historical_invalid_receipt_count"], 0)
        self.assertEqual(receipts["pre_activation_receipt_count"], 0)
        self.assertEqual(receipts["pre_activation_valid_receipt_count"], 0)
        self.assertEqual(receipts["pre_activation_invalid_receipt_count"], 0)
        self.assertIn(
            "receipt is unreadable",
            receipts["invalid_receipts"][0]["errors"][0],
        )

    def test_unbound_schema3_cannot_claim_preactivation_from_old_timestamp(self):
        now = dt.datetime.now(dt.timezone.utc).replace(microsecond=0)
        instrumentation = now - dt.timedelta(minutes=30)
        mutations = {
            "bad-hash": lambda row: row.update(origin="SCHEDULED"),
            "identity-mismatch": lambda row: row.update(
                task_name="ngernduangold_weekly"
            ),
            "naive-start": lambda row: row.update(
                started_at=(now - dt.timedelta(hours=2)).replace(
                    tzinfo=None
                ).isoformat()
            ),
        }
        for label, mutate in mutations.items():
            with self.subTest(case=label), tempfile.TemporaryDirectory() as tmp:
                receipt_root = Path(tmp) / "task-runs"
                path = write_task_receipt(
                    receipt_root, "ngernduangold_daily", "unbound-" + label,
                    started_at=now - dt.timedelta(hours=2),
                    status="FINISHED", finished_at=now - dt.timedelta(hours=1),
                    execution_state="PASS", final_rc=0,
                )
                candidate = loop._load(path)
                mutate(candidate)
                if label != "bad-hash":
                    candidate = loop.task_run_receipt.seal_receipt(candidate)
                loop._atomic(path, candidate)
                health = loop.build_control_health(
                    Path(tmp) / "improvement-runs",
                    loop._empty_error_learning_state(), now=now,
                    task_runs_root=receipt_root,
                    receipt_monitoring=valid_receipt_monitoring(instrumentation),
                )

                receipts = health["task_receipts"]
                self.assertEqual(
                    health["kpis"]["task_receipt_coverage_state"],
                    "INVALID_RECEIPTS",
                )
                self.assertEqual(receipts["invalid_receipt_count"], 1)
                self.assertEqual(receipts["historical_invalid_receipt_count"], 0)
                self.assertEqual(receipts["pre_activation_receipt_count"], 0)
                self.assertEqual(
                    receipts["pre_activation_invalid_receipt_count"], 0
                )

    def test_schema3_started_exactly_at_activation_is_current(self):
        now = dt.datetime.now(dt.timezone.utc).replace(microsecond=0)
        instrumentation = now - dt.timedelta(minutes=30)
        with tempfile.TemporaryDirectory() as tmp:
            receipt_root = Path(tmp) / "task-runs"
            write_task_receipt(
                receipt_root, "ngernduangold_daily", "activation-boundary",
                started_at=instrumentation,
                status="FINISHED",
                finished_at=instrumentation + dt.timedelta(minutes=10),
                execution_state="PASS", final_rc=0,
            )
            health = loop.build_control_health(
                Path(tmp) / "improvement-runs",
                loop._empty_error_learning_state(), now=now,
                task_runs_root=receipt_root,
                receipt_monitoring=valid_receipt_monitoring(instrumentation),
            )

        receipts = health["task_receipts"]
        self.assertEqual(
            health["kpis"]["task_receipt_coverage_state"], "PARTIAL_WINDOW"
        )
        self.assertEqual(receipts["window_observed"], 1)
        self.assertEqual(receipts["window_terminal"], 1)
        self.assertEqual(receipts["pre_activation_receipt_count"], 0)
        self.assertEqual(receipts["invalid_receipt_count"], 0)

    def test_postactivation_invalid_schema3_still_fails_closed(self):
        now = dt.datetime.now(dt.timezone.utc).replace(microsecond=0)
        instrumentation = now - dt.timedelta(minutes=30)
        with tempfile.TemporaryDirectory() as tmp:
            receipt_root = Path(tmp) / "task-runs"
            path = write_task_receipt(
                receipt_root, "ngernduangold_daily", "postactivation-invalid",
                started_at=instrumentation + dt.timedelta(seconds=1),
                status="FINISHED",
                finished_at=instrumentation + dt.timedelta(minutes=10),
                execution_state="PASS", final_rc=0,
            )
            candidate = loop._load(path)
            candidate["origin"] = "SCHEDULED"
            loop._atomic(path, loop.task_run_receipt.seal_receipt(candidate))
            health = loop.build_control_health(
                Path(tmp) / "improvement-runs",
                loop._empty_error_learning_state(), now=now,
                task_runs_root=receipt_root,
                receipt_monitoring=valid_receipt_monitoring(instrumentation),
            )

        receipts = health["task_receipts"]
        self.assertEqual(
            health["kpis"]["task_receipt_coverage_state"], "INVALID_RECEIPTS"
        )
        self.assertEqual(receipts["invalid_receipt_count"], 1)
        self.assertEqual(receipts["historical_invalid_receipt_count"], 0)
        self.assertEqual(receipts["pre_activation_receipt_count"], 0)
        self.assertEqual(receipts["pre_activation_invalid_receipt_count"], 0)

    def test_task_receipt_consumer_binds_exact_runner_and_tool_paths(self):
        now = dt.datetime.now(dt.timezone.utc).replace(microsecond=0)
        with tempfile.TemporaryDirectory() as tmp:
            path = write_task_receipt(
                Path(tmp), "ngernduangold_daily", "path-contract",
                started_at=now - dt.timedelta(minutes=2),
                status="FINISHED", finished_at=now - dt.timedelta(minutes=1),
                execution_state="PASS", final_rc=0,
            )
            original = loop._load(path)

        cases = (
            (
                "runner",
                "receipt runner path is not bound to the monitored task",
            ),
            (
                "receipt_tool",
                "receipt tool path is not bound to the monitored producer",
            ),
        )
        for binding, expected_error in cases:
            with self.subTest(binding=binding):
                candidate = json.loads(json.dumps(original))
                candidate[binding]["path"] = str(loop.ROOT / "README.md")
                sealed = loop.task_run_receipt.seal_receipt(candidate)
                errors = loop._task_receipt_contract_errors(
                    sealed, task_name="ngernduangold_daily",
                    run_id="path-contract", current=now,
                )
                self.assertIn(expected_error, errors)

    def test_task_receipt_consumer_enforces_terminal_hashes_log_and_step_mode(self):
        now = dt.datetime.now(dt.timezone.utc).replace(microsecond=0)
        with tempfile.TemporaryDirectory() as tmp:
            path = write_task_receipt(
                Path(tmp), "ngernduangold_daily", "consumer-parity",
                started_at=now - dt.timedelta(minutes=2),
                status="FINISHED", finished_at=now - dt.timedelta(minutes=1),
                execution_state="PASS", final_rc=0,
            )
            original = loop._load(path)

        cases = []
        runner_drift = json.loads(json.dumps(original))
        runner_drift["runner"]["sha256_end"] = "c" * 64
        cases.append((
            runner_drift, "terminal receipt runner hash stability is invalid"
        ))
        tool_drift = json.loads(json.dumps(original))
        tool_drift["receipt_tool"]["sha256_end"] = "c" * 64
        cases.append((
            tool_drift,
            "terminal receipt receipt-tool hash stability is invalid",
        ))
        missing_log = json.loads(json.dumps(original))
        missing_log["log_path"] = ""
        cases.append((missing_log, "receipt log path is invalid"))
        forged_mode = json.loads(json.dumps(original))
        forged_mode["steps"][3]["evidence_mode"] = "record"
        for field in ("executable", "argument_count", "command_hash"):
            forged_mode["steps"][3].pop(field)
        cases.append((
            forged_mode, "receipt steps are not an exact ordered manifest prefix"
        ))
        for candidate, expected_error in cases:
            with self.subTest(error=expected_error):
                sealed = loop.task_run_receipt.seal_receipt(candidate)
                errors = loop._task_receipt_contract_errors(
                    sealed, task_name="ngernduangold_daily",
                    run_id="consumer-parity", current=now,
                )
                self.assertIn(expected_error, errors)

    def test_malformed_schema3_receipts_fail_closed_without_consumer_crash(self):
        now = dt.datetime.now(dt.timezone.utc).replace(microsecond=0)
        mutations = {
            "runner": lambda row: row.update(runner=[]),
            "receipt_tool": lambda row: row.update(receipt_tool=[]),
            "task_name": lambda row: row.update(task_name=[]),
            "status": lambda row: row.update(status=[]),
            "execution_state": lambda row: row.update(execution_state=[]),
            "execution_valid": lambda row: row["steps"][3].update(
                execution_valid=[]
            ),
        }
        for label, mutate in mutations.items():
            with self.subTest(field=label), tempfile.TemporaryDirectory() as tmp:
                receipt_root = Path(tmp) / "task-runs"
                path = write_task_receipt(
                    receipt_root, "ngernduangold_daily", "malformed-" + label,
                    started_at=now - dt.timedelta(minutes=2),
                    status="FINISHED", finished_at=now - dt.timedelta(minutes=1),
                    execution_state="PASS", final_rc=0,
                )
                candidate = loop._load(path)
                mutate(candidate)
                loop._atomic(path, loop.task_run_receipt.seal_receipt(candidate))
                health = loop.build_control_health(
                    Path(tmp) / "improvement-runs",
                    loop._empty_error_learning_state(), now=now,
                    task_runs_root=receipt_root,
                    receipt_monitoring=valid_receipt_monitoring(
                        now - dt.timedelta(days=1)
                    ),
                )
                self.assertEqual(
                    health["kpis"]["task_receipt_coverage_state"],
                    "INVALID_RECEIPTS",
                )
                self.assertEqual(health["kpis"]["invalid_task_receipts"], 1)
                self.assertEqual(health["kpis"]["terminal_runs_7d"], 0)
                self.assertIsNone(health["kpis"]["terminal_control_run_rate_7d"])

    def test_unknown_or_mutated_legacy_schema_cannot_bypass_validation(self):
        now = dt.datetime.now(dt.timezone.utc).replace(microsecond=0)
        instrumentation = now - dt.timedelta(minutes=30)
        schemas = (2, 4, 999, True)
        for schema in schemas:
            with self.subTest(schema=schema), tempfile.TemporaryDirectory() as tmp:
                receipt_root = Path(tmp) / "task-runs"
                path = write_task_receipt(
                    receipt_root, "ngernduangold_weekly", "legacy-bypass",
                    started_at=now - dt.timedelta(hours=2),
                    status="FINISHED", finished_at=now - dt.timedelta(hours=1),
                    execution_state="PASS", final_rc=0,
                )
                candidate = loop._load(path)
                candidate["schema_version"] = schema
                candidate.pop("task_contract", None)
                loop._atomic(path, loop.task_run_receipt.seal_receipt(candidate))
                health = loop.build_control_health(
                    Path(tmp) / "improvement-runs",
                    loop._empty_error_learning_state(), now=now,
                    task_runs_root=receipt_root,
                    receipt_monitoring=valid_receipt_monitoring(instrumentation),
                )
                self.assertEqual(
                    health["kpis"]["task_receipt_coverage_state"],
                    "INVALID_RECEIPTS",
                )
                self.assertEqual(health["task_receipts"]["legacy_receipt_count"], 0)
                self.assertEqual(health["kpis"]["invalid_task_receipts"], 1)

    def test_attested_legacy_invalid_reason_remains_in_audit_counters(self):
        now = dt.datetime.now(dt.timezone.utc).replace(microsecond=0)
        instrumentation = now - dt.timedelta(minutes=30)
        with tempfile.TemporaryDirectory() as tmp:
            receipt_root = Path(tmp) / "task-runs"
            path = write_task_receipt(
                receipt_root, "ngernduangold_weekly", "known-legacy-invalid",
                started_at=now - dt.timedelta(hours=2),
                status="FINISHED", finished_at=now - dt.timedelta(hours=1),
                execution_state="PASS", final_rc=0,
            )
            candidate = loop._load(path)
            candidate["schema_version"] = 2
            candidate.pop("task_contract")
            loop._atomic(path, loop.task_run_receipt.seal_receipt(candidate))
            candidate = loop._load(path)
            health = loop.build_control_health(
                Path(tmp) / "improvement-runs",
                loop._empty_error_learning_state(), now=now,
                task_runs_root=receipt_root,
                receipt_monitoring=valid_receipt_monitoring(
                    instrumentation,
                    legacy_receipt_attestations=[{
                        "task_name": "ngernduangold_weekly",
                        "run_id": "known-legacy-invalid",
                        "receipt_hash": candidate["receipt_hash"],
                        "migration_state": "LEGACY_INVALID",
                        "errors": ["prior classification mismatch"],
                    }],
                ),
            )
        self.assertEqual(
            health["kpis"]["task_receipt_coverage_state"], "NO_RECEIPTS"
        )
        self.assertEqual(health["task_receipts"]["legacy_invalid_receipt_count"], 1)
        self.assertEqual(health["task_receipts"]["all_invalid_receipt_count"], 1)
        self.assertEqual(
            health["task_receipts"]["legacy_receipts"][0]["errors"],
            ["prior classification mismatch"],
        )

    def test_task_receipt_rate_counts_abort_and_stuck_but_excludes_active(self):
        now = dt.datetime.now(dt.timezone.utc).replace(microsecond=0)
        cutoff = now - dt.timedelta(days=7)
        with tempfile.TemporaryDirectory() as tmp:
            receipt_root = Path(tmp) / "task-runs"
            for task_name in loop.TASK_RECEIPT_NAMES:
                write_task_receipt(
                    receipt_root, task_name, task_name + "-coverage",
                    started_at=cutoff - dt.timedelta(hours=1),
                    status="FINISHED",
                    finished_at=cutoff - dt.timedelta(minutes=30),
                    execution_state="PASS", final_rc=0,
                )
            write_task_receipt(
                receipt_root, "ngernduangold_daily", "daily-pass",
                started_at=now - dt.timedelta(hours=5),
                status="FINISHED", finished_at=now - dt.timedelta(hours=4),
                execution_state="PASS", final_rc=0,
            )
            write_task_receipt(
                receipt_root, "ngernduangold_weekly", "weekly-abort",
                started_at=now - dt.timedelta(hours=4),
                status="ABORTED", finished_at=now - dt.timedelta(hours=3),
                execution_state="RUNNER_FAILED", final_rc=3,
            )
            write_task_receipt(
                receipt_root, "ngernduangold_daily", "daily-active",
                started_at=now - dt.timedelta(hours=1), status="RUNNING",
            )
            write_task_receipt(
                receipt_root, "ngernduangold_weekly", "weekly-stuck",
                started_at=now - dt.timedelta(hours=7), status="RUNNING",
            )
            write_task_receipt(
                receipt_root, "ngernduangold_weekly", "weekly-active-other",
                started_at=now - dt.timedelta(hours=1), status="RUNNING",
            )
            health = loop.build_control_health(
                Path(tmp) / "improvement-runs",
                loop._empty_error_learning_state(), now=now,
                task_runs_root=receipt_root,
                receipt_monitoring=valid_receipt_monitoring(
                    cutoff - dt.timedelta(hours=2)
                ),
                current_task_identity=(
                    "ngernduangold_daily", "daily-active"
                ),
            )
        self.assertEqual(
            health["kpis"]["task_receipt_coverage_state"], "FULL_WINDOW"
        )
        self.assertEqual(health["kpis"]["started_runs_7d"], 4)
        self.assertEqual(health["kpis"]["terminal_runs_7d"], 2)
        self.assertEqual(health["kpis"]["runner_failed_runs_7d"], 1)
        self.assertEqual(health["kpis"]["active_runs_7d"], 1)
        self.assertEqual(health["kpis"]["stuck_runs_7d"], 1)
        self.assertEqual(
            health["task_receipts"]["excluded_current_running_receipt"], 1
        )
        self.assertAlmostEqual(
            health["kpis"]["terminal_control_run_rate_7d"], 2 / 3
        )
        self.assertEqual(health["task_receipts"]["window_rate_denominator"], 3)

    def test_proven_block_abort_is_the_only_official_false_fatal(self):
        now = dt.datetime.now(dt.timezone.utc).replace(microsecond=0)
        cutoff = now - dt.timedelta(days=7)
        with tempfile.TemporaryDirectory() as tmp:
            receipt_root = Path(tmp) / "task-runs"
            started = now - dt.timedelta(hours=1)
            blocked_steps = canonical_receipt_steps(
                "ngernduangold_daily", started,
                overrides={"daily_media_gate": 2},
            )
            media_index = next(
                index for index, step in enumerate(blocked_steps)
                if step["step_id"] == "daily_media_gate"
            )
            blocked_steps = blocked_steps[:media_index + 1]
            write_task_receipt(
                receipt_root, "ngernduangold_daily", "daily-block-abort",
                started_at=started, status="ABORTED",
                finished_at=now - dt.timedelta(minutes=50),
                execution_state="COMPLETED_BLOCKED", final_rc=2,
                terminal_reason="step_nonzero",
                terminal_step_id="daily_media_gate",
                steps=blocked_steps,
            )
            health = loop.build_control_health(
                Path(tmp) / "improvement-runs",
                loop._empty_error_learning_state(), now=now,
                task_runs_root=receipt_root,
                receipt_monitoring=valid_receipt_monitoring(
                    cutoff - dt.timedelta(hours=1)
                ),
            )
        self.assertEqual(
            health["kpis"]["task_receipt_coverage_state"],
            "INCOMPLETE_TASK_COVERAGE",
        )
        self.assertEqual(
            health["task_receipts"]["per_task_coverage"][
                "ngernduangold_daily"
            ]["state"],
            "OBSERVED",
        )
        self.assertEqual(
            health["task_receipts"]["per_task_coverage"][
                "ngernduangold_weekly"
            ]["state"],
            "MISSING",
        )
        self.assertEqual(
            health["task_receipts"]["missing_window_tasks"],
            ["ngernduangold_weekly"],
        )
        self.assertEqual(health["kpis"]["completed_blocked_runs_7d"], 1)
        self.assertIsNone(
            health["kpis"]["publication_blocker_false_fatal_count"]
        )
        self.assertEqual(
            health["kpis"]["observed_publication_blocker_false_fatal_count"],
            1,
        )

    def test_full_window_requires_each_monitored_task_to_be_observed(self):
        now = dt.datetime.now(dt.timezone.utc).replace(microsecond=0)
        cutoff = now - dt.timedelta(days=7)
        cases = (
            ("ngernduangold_daily", "ngernduangold_weekly"),
            ("ngernduangold_weekly", "ngernduangold_daily"),
        )
        for present_task, missing_task in cases:
            with self.subTest(present_task=present_task):
                with tempfile.TemporaryDirectory() as tmp:
                    receipt_root = Path(tmp) / "task-runs"
                    write_task_receipt(
                        receipt_root, present_task, "only-observed",
                        started_at=now - dt.timedelta(hours=2),
                        status="FINISHED",
                        finished_at=now - dt.timedelta(hours=1),
                        execution_state="PASS", final_rc=0,
                    )
                    health = loop.build_control_health(
                        Path(tmp) / "improvement-runs",
                        loop._empty_error_learning_state(), now=now,
                        task_runs_root=receipt_root,
                        receipt_monitoring=valid_receipt_monitoring(
                            cutoff - dt.timedelta(hours=1)
                        ),
                    )
                self.assertEqual(
                    health["kpis"]["task_receipt_coverage_state"],
                    "INCOMPLETE_TASK_COVERAGE",
                )
                per_task = health["task_receipts"]["per_task_coverage"]
                self.assertEqual(per_task[present_task]["state"], "OBSERVED")
                self.assertEqual(per_task[missing_task]["state"], "MISSING")
                self.assertEqual(
                    health["task_receipts"]["missing_window_tasks"],
                    [missing_task],
                )
                self.assertIsNone(
                    health["kpis"]["terminal_control_run_rate_7d"]
                )

    def test_active_only_and_stuck_task_do_not_claim_full_coverage(self):
        now = dt.datetime.now(dt.timezone.utc).replace(microsecond=0)
        cutoff = now - dt.timedelta(days=7)
        cases = (
            ("weekly-active", now - dt.timedelta(hours=1), "ACTIVE_ONLY", True),
            ("weekly-stuck", now - dt.timedelta(hours=7), "STUCK", False),
        )
        for run_id, started, expected_state, current_run in cases:
            with self.subTest(expected_state=expected_state):
                with tempfile.TemporaryDirectory() as tmp:
                    receipt_root = Path(tmp) / "task-runs"
                    write_task_receipt(
                        receipt_root, "ngernduangold_daily", "daily-terminal",
                        started_at=now - dt.timedelta(hours=3),
                        status="FINISHED",
                        finished_at=now - dt.timedelta(hours=2),
                        execution_state="PASS", final_rc=0,
                    )
                    write_task_receipt(
                        receipt_root, "ngernduangold_weekly", run_id,
                        started_at=started, status="RUNNING",
                    )
                    health = loop.build_control_health(
                        Path(tmp) / "improvement-runs",
                        loop._empty_error_learning_state(), now=now,
                        task_runs_root=receipt_root,
                        receipt_monitoring=valid_receipt_monitoring(
                            cutoff - dt.timedelta(hours=1)
                        ),
                        current_task_identity=(
                            ("ngernduangold_weekly", run_id)
                            if current_run else None
                        ),
                    )
                self.assertEqual(
                    health["kpis"]["task_receipt_coverage_state"],
                    "INCOMPLETE_TASK_COVERAGE",
                )
                self.assertEqual(
                    health["task_receipts"]["per_task_coverage"][
                        "ngernduangold_weekly"
                    ]["state"],
                    expected_state,
                )
                self.assertIsNone(
                    health["kpis"]["terminal_control_run_rate_7d"]
                )

    def test_receipt_monitoring_schema_mismatch_is_unavailable(self):
        now = dt.datetime.now(dt.timezone.utc).replace(microsecond=0)
        with tempfile.TemporaryDirectory() as tmp:
            health = loop.build_control_health(
                Path(tmp) / "improvement-runs",
                loop._empty_error_learning_state(), now=now,
                task_runs_root=Path(tmp) / "task-runs",
                receipt_monitoring=valid_receipt_monitoring(
                    now - dt.timedelta(days=8),
                    schema_version=loop.task_run_receipt.SCHEMA_VERSION - 1,
                ),
            )
        self.assertEqual(
            health["kpis"]["task_receipt_coverage_state"],
            "INVALID_MONITORING_CONTRACT",
        )
        self.assertIsNone(
            health["kpis"]["publication_blocker_false_fatal_count"]
        )

    def test_invalid_task_receipt_makes_rate_unavailable(self):
        now = dt.datetime.now(dt.timezone.utc).replace(microsecond=0)
        with tempfile.TemporaryDirectory() as tmp:
            receipt_root = Path(tmp) / "task-runs"
            path = write_task_receipt(
                receipt_root, "ngernduangold_daily", "tampered",
                started_at=now - dt.timedelta(hours=1), status="RUNNING",
            )
            receipt = json.loads(path.read_text(encoding="utf-8"))
            receipt["origin"] = "SCHEDULED"
            loop._atomic(path, receipt)
            health = loop.build_control_health(
                Path(tmp) / "improvement-runs",
                loop._empty_error_learning_state(), now=now,
                task_runs_root=receipt_root,
                receipt_monitoring=valid_receipt_monitoring(
                    now - dt.timedelta(hours=2)
                ),
            )
        self.assertEqual(
            health["kpis"]["task_receipt_coverage_state"], "INVALID_RECEIPTS"
        )
        self.assertEqual(health["kpis"]["invalid_task_receipts"], 1)
        self.assertEqual(
            health["task_receipts"]["historical_invalid_receipt_count"], 0
        )
        self.assertEqual(
            health["task_receipts"]["all_invalid_receipt_count"], 1
        )
        self.assertIsNone(health["kpis"]["terminal_control_run_rate_7d"])

    def test_historical_invalid_receipt_does_not_poison_current_window(self):
        now = dt.datetime.now(dt.timezone.utc).replace(microsecond=0)
        cutoff = now - dt.timedelta(days=7)
        with tempfile.TemporaryDirectory() as tmp:
            receipt_root = Path(tmp) / "task-runs"
            historical = write_task_receipt(
                receipt_root, "ngernduangold_daily", "historical-invalid",
                started_at=cutoff - dt.timedelta(days=1),
                status="FINISHED",
                finished_at=(
                    cutoff - dt.timedelta(days=1) + dt.timedelta(minutes=1)
                ),
                execution_state="PASS", final_rc=0,
            )
            historical_receipt = loop._load(historical)
            historical_receipt["origin"] = "SCHEDULED"
            loop._atomic(
                historical,
                loop.task_run_receipt.seal_receipt(historical_receipt),
            )
            write_task_receipt(
                receipt_root, "ngernduangold_weekly", "current-pass",
                started_at=now - dt.timedelta(hours=2),
                status="FINISHED", finished_at=now - dt.timedelta(hours=1),
                execution_state="PASS", final_rc=0,
            )
            write_task_receipt(
                receipt_root, "ngernduangold_daily", "current-daily-pass",
                started_at=now - dt.timedelta(hours=3),
                status="FINISHED", finished_at=now - dt.timedelta(hours=2),
                execution_state="PASS", final_rc=0,
            )
            health = loop.build_control_health(
                Path(tmp) / "improvement-runs",
                loop._empty_error_learning_state(), now=now,
                task_runs_root=receipt_root,
                receipt_monitoring=valid_receipt_monitoring(
                    cutoff - dt.timedelta(days=2)
                ),
            )

        self.assertEqual(
            health["kpis"]["task_receipt_coverage_state"], "FULL_WINDOW"
        )
        self.assertEqual(health["kpis"]["invalid_task_receipts"], 0)
        self.assertEqual(
            health["task_receipts"]["historical_invalid_receipt_count"], 1
        )
        self.assertEqual(
            health["task_receipts"]["historical_invalid_receipts"][0][
                "run_id"
            ],
            "historical-invalid",
        )
        self.assertEqual(
            health["task_receipts"]["all_invalid_receipt_count"], 1
        )
        self.assertEqual(health["kpis"]["terminal_control_run_rate_7d"], 1.0)

    def test_duplicate_key_task_receipt_is_rejected_by_control_health_consumer(self):
        now = dt.datetime.now(dt.timezone.utc).replace(microsecond=0)
        with tempfile.TemporaryDirectory() as tmp:
            receipt_root = Path(tmp) / "task-runs"
            path = write_task_receipt(
                receipt_root,
                "ngernduangold_daily",
                "duplicate-status",
                started_at=now - dt.timedelta(hours=1),
                status="FINISHED",
                finished_at=now - dt.timedelta(minutes=30),
                execution_state="PASS",
                final_rc=0,
            )
            raw = path.read_text(encoding="utf-8")
            needle = '"status": "FINISHED"'
            self.assertIn(needle, raw)
            path.write_text(
                raw.replace(
                    needle,
                    '"status": "RUNNING", "status": "FINISHED"',
                    1,
                ),
                encoding="utf-8",
            )
            health = loop.build_control_health(
                Path(tmp) / "improvement-runs",
                loop._empty_error_learning_state(),
                now=now,
                task_runs_root=receipt_root,
                receipt_monitoring=valid_receipt_monitoring(
                    now - dt.timedelta(days=8)
                ),
            )
        self.assertEqual(
            health["kpis"]["task_receipt_coverage_state"], "INVALID_RECEIPTS"
        )
        self.assertEqual(health["kpis"]["invalid_task_receipts"], 1)
        self.assertEqual(health["kpis"]["terminal_runs_7d"], 0)
        self.assertIsNone(health["kpis"]["terminal_control_run_rate_7d"])

    def test_deeply_nested_task_receipt_is_rejected_without_consumer_crash(self):
        now = dt.datetime.now(dt.timezone.utc).replace(microsecond=0)
        with tempfile.TemporaryDirectory() as tmp:
            receipt_root = Path(tmp) / "task-runs"
            path = receipt_root / "ngernduangold_daily" / "deep-json.json"
            path.parent.mkdir(parents=True, exist_ok=True)
            depth = 2000
            path.write_text(
                '{"nested":' + ('[' * depth) + '0' + (']' * depth) + '}',
                encoding="utf-8",
            )
            health = loop.build_control_health(
                Path(tmp) / "improvement-runs",
                loop._empty_error_learning_state(),
                now=now,
                task_runs_root=receipt_root,
                receipt_monitoring=valid_receipt_monitoring(
                    now - dt.timedelta(days=8)
                ),
            )
        self.assertEqual(
            health["kpis"]["task_receipt_coverage_state"], "INVALID_RECEIPTS"
        )
        self.assertEqual(health["kpis"]["invalid_task_receipts"], 1)
        self.assertEqual(health["kpis"]["terminal_runs_7d"], 0)
        self.assertIsNone(health["kpis"]["terminal_control_run_rate_7d"])

    def test_revoked_terminal_receipt_is_rejected_by_control_health_consumer(self):
        now = dt.datetime.now(dt.timezone.utc).replace(microsecond=0)
        with tempfile.TemporaryDirectory() as tmp:
            receipt_root = Path(tmp) / "task-runs"
            path = write_task_receipt(
                receipt_root,
                "ngernduangold_daily",
                "revoked-pass",
                started_at=now - dt.timedelta(hours=1),
                status="FINISHED",
                finished_at=now - dt.timedelta(minutes=30),
                execution_state="PASS",
                final_rc=0,
            )
            marker = loop.task_run_receipt.receipt_revocation_path(path)
            marker.write_bytes(b"partial marker is authoritative")
            health = loop.build_control_health(
                Path(tmp) / "improvement-runs",
                loop._empty_error_learning_state(),
                now=now,
                task_runs_root=receipt_root,
                receipt_monitoring=valid_receipt_monitoring(
                    now - dt.timedelta(days=8)
                ),
            )

        self.assertEqual(
            health["kpis"]["task_receipt_coverage_state"], "INVALID_RECEIPTS"
        )
        self.assertEqual(health["kpis"]["invalid_task_receipts"], 1)
        self.assertEqual(health["kpis"]["terminal_runs_7d"], 0)
        self.assertIn(
            "receipt terminal commit is revoked",
            health["task_receipts"]["invalid_receipts"][0]["errors"][0],
        )

    def test_orphan_revocation_marker_is_still_a_consumer_failure(self):
        now = dt.datetime.now(dt.timezone.utc).replace(microsecond=0)
        with tempfile.TemporaryDirectory() as tmp:
            receipt_root = Path(tmp) / "task-runs"
            path = write_task_receipt(
                receipt_root,
                "ngernduangold_daily",
                "orphan-revocation",
                started_at=now - dt.timedelta(hours=1),
                status="FINISHED",
                finished_at=now - dt.timedelta(minutes=30),
                execution_state="PASS",
                final_rc=0,
            )
            marker = loop.task_run_receipt.receipt_revocation_path(path)
            marker.write_bytes(b"revoked")
            path.unlink()
            health = loop.build_control_health(
                Path(tmp) / "improvement-runs",
                loop._empty_error_learning_state(),
                now=now,
                task_runs_root=receipt_root,
                receipt_monitoring=valid_receipt_monitoring(
                    now - dt.timedelta(days=8)
                ),
            )

        self.assertEqual(
            health["kpis"]["task_receipt_coverage_state"], "INVALID_RECEIPTS"
        )
        self.assertEqual(health["kpis"]["invalid_task_receipts"], 1)
        self.assertEqual(
            health["task_receipts"]["invalid_receipts"][0]["run_id"],
            "orphan-revocation",
        )
        self.assertIn(
            "receipt terminal commit is revoked",
            health["task_receipts"]["invalid_receipts"][0]["errors"][0],
        )

    def test_invalid_monitoring_contract_takes_precedence_over_bad_receipt(self):
        now = dt.datetime.now(dt.timezone.utc).replace(microsecond=0)
        with tempfile.TemporaryDirectory() as tmp:
            receipt_root = Path(tmp) / "task-runs"
            path = write_task_receipt(
                receipt_root, "ngernduangold_daily", "tampered",
                started_at=now - dt.timedelta(hours=1), status="RUNNING",
            )
            receipt = json.loads(path.read_text(encoding="utf-8"))
            receipt["origin"] = "SCHEDULED"
            loop._atomic(path, receipt)
            health = loop.build_control_health(
                Path(tmp) / "improvement-runs",
                loop._empty_error_learning_state(), now=now,
                task_runs_root=receipt_root,
                receipt_monitoring=valid_receipt_monitoring(
                    now - dt.timedelta(days=8),
                    schema_version=loop.task_run_receipt.SCHEMA_VERSION - 1,
                ),
            )
        self.assertEqual(
            health["kpis"]["task_receipt_coverage_state"],
            "INVALID_MONITORING_CONTRACT",
        )
        self.assertEqual(health["kpis"]["invalid_task_receipts"], 1)

    def test_runtime_contract_is_hash_bound_and_detects_tampering(self):
        contract = loop.collect_runtime_contract()
        self.assertEqual(loop.runtime_contract_errors(contract), [])
        forged = json.loads(json.dumps(contract))
        forged["files"][0]["sha256"] = "0" * 64
        self.assertIn(
            "runtime contract hash is missing or mismatched",
            loop.runtime_contract_errors(forged),
        )
        representative_paths = {
            "pipeline/observation_snapshot.py",
            "pipeline/official_news_monitor.py",
            "tools/content_source_gate.py",
            "automation-log/knowledge-base/social-source-registry.json",
            "pipeline/task_run_receipt.py",
            ".system_control/generative_media_policy.json",
            "tools/generative_media_origin_gate.py",
            "automation-log/post_ledger_identity.py",
            "automation-log/post_ledger_collision.py",
            "automation-log/post-ledger-identity-bindings.jsonl",
            "automation-log/post-ledger-collision-tombstones.json",
            "automation-log/dedup-evidence/post-ledger-identity-sources-v2.json",
            "automation-log/KNOWLEDGE-POSTS-B_20260802-0815.md",
            "tools/publication_authority.py",
            "automation/ig_publish.py",
            "social-autopost/publish_tiktok.py",
            "tools/yt_upload_batch2.py",
            "tools/week_candidate_manifest_guard.py",
            "automation-log/media-qa/WEEK-TIKTOK-QUOTE-CANDIDATES_MANIFEST_R5_20260823.json",
            "automation-log/WEEK-CONTENT-PACK_20260824-30.json",
            "automation-log/media-qa/wk36-sf01-tiktok-video-r5.json",
            "reels/week-20260824-30-r5/2026-08-24_wk36-sf01.mp4",
        }
        self.assertTrue(
            representative_paths.issubset(
                {row["path"] for row in contract["files"]}
            )
        )
        for path in representative_paths:
            with self.subTest(path=path):
                changed = json.loads(json.dumps(contract))
                row = next(item for item in changed["files"] if item["path"] == path)
                row["sha256"] = "0" * 64
                changed["contract_hash"] = loop._canonical_hash({
                    key: value for key, value in changed.items()
                    if key != "contract_hash"
                })
                self.assertIn(
                    "runtime contract changed during the control run",
                    loop.runtime_contract_errors(changed, verify_current=True),
                )

    def test_runtime_contract_discovers_identity_overlay_dependencies(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            bindings = root / "automation-log/post-ledger-identity-bindings.jsonl"
            bindings.parent.mkdir(parents=True)
            bindings.write_text(json.dumps({
                "record_type": "post_ledger_identity_binding",
                "source": {
                    "path": "automation-log/source.md",
                    "evidence_path": "automation-log/evidence.json",
                },
            }) + "\n", encoding="utf-8")
            with mock.patch.object(loop, "ROOT", root):
                paths = loop._runtime_contract_paths()
            self.assertIn("automation-log/source.md", paths)
            self.assertIn("automation-log/evidence.json", paths)

    def test_runtime_contract_discovers_bounded_media_and_manifest_dependencies(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            media_dir = root / "automation-log/media-qa"
            media_dir.mkdir(parents=True)
            asset = root / "reels/week/clip.mp4"
            asset.parent.mkdir(parents=True)
            asset.write_bytes(b"video")
            receipt = media_dir / "clip.json"
            receipt.write_text("{}", encoding="utf-8")
            pack = root / "automation-log/pack.json"
            pack.write_text("{}", encoding="utf-8")
            summary = media_dir / "summary.md"
            summary.write_text("qa", encoding="utf-8")
            manifest = media_dir / "WEEK-TIKTOK-QUOTE-CANDIDATES_MANIFEST_R1_20260823.json"
            manifest.write_text(json.dumps({
                "pack": {"path": "automation-log/pack.json"},
                "qa_summary": {"path": "automation-log/media-qa/summary.md"},
                "assets": [{
                    "asset": "reels/week/clip.mp4",
                    "receipt": "automation-log/media-qa/clip.json",
                }],
            }), encoding="utf-8")
            with mock.patch.object(loop, "ROOT", root):
                paths = loop._runtime_contract_paths()
            for expected in (
                "reels/week/clip.mp4",
                "automation-log/media-qa/clip.json",
                "automation-log/media-qa/summary.md",
                "automation-log/pack.json",
            ):
                self.assertIn(expected, paths)

    def test_runtime_contract_binds_every_release_contract_input_and_drift(self):
        release_inputs = {
            path.as_posix()
            for path in (
                *loop.release_contract.SOURCE_INPUTS,
                loop.release_contract.PILOT_PATH,
            )
        }
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            with mock.patch.object(loop, "ROOT", root):
                initial_paths = loop._runtime_contract_paths()
                self.assertTrue(release_inputs.issubset(set(initial_paths)))
                self.assertEqual(len(initial_paths), len(set(initial_paths)))
                for relative in initial_paths:
                    path = root / relative
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_bytes(b"fixture\n")
                contract = loop.collect_runtime_contract()
                self.assertEqual(loop.runtime_contract_errors(contract), [])
                for relative in sorted(release_inputs):
                    with self.subTest(path=relative):
                        path = root / relative
                        original = path.read_bytes()
                        path.write_bytes(original + b"changed\n")
                        self.assertIn(
                            "runtime contract changed during the control run",
                            loop.runtime_contract_errors(
                                contract, verify_current=True
                            ),
                        )
                        path.write_bytes(original)

    def test_observe_captures_runtime_contract_before_source_collection(self):
        order = []
        contract = loop.collect_runtime_contract()
        with tempfile.TemporaryDirectory() as tmp, (
            mock.patch.object(
                loop, "collect_runtime_contract",
                side_effect=lambda: order.append("contract") or contract,
            )
        ), mock.patch.object(
            loop.observation_snapshot, "collect",
            side_effect=lambda: order.append("observation") or observation(),
        ), mock.patch.object(loop, "GUARDS", {}), mock.patch.object(
            loop, "collect_decision_readiness", return_value={}
        ):
            observed = loop.observe(Path(tmp))
        self.assertEqual(order[:2], ["contract", "observation"])
        self.assertEqual(observed["runtime_contract"], contract)

    def test_failed_validation_returns_nonzero_cli_status(self):
        state = {"validation_passed": False, "status": "FAILED_VALIDATION",
                 "priority_count": 1, "owner_action_count": 0}
        with (mock.patch.object(loop, "execute", return_value=(state, Path("private-run"))),
              mock.patch.object(loop.sys, "argv", ["improvement_loop.py", "run"])):
            self.assertEqual(loop.main(), 2)

    def test_completed_cli_status_distinguishes_clean_and_blocked_runs(self):
        base = {"validation_passed": True, "priority_count": 1,
                "owner_action_count": 0}
        cases = (("COMPLETED", 0), ("COMPLETED_WITH_BLOCKERS", 2),
                 ("FAILED", 3), ("UNKNOWN", 3))
        for status, expected in cases:
            with self.subTest(status=status):
                state = {**base, "status": status}
                with (
                    mock.patch.object(
                        loop, "execute", return_value=(state, Path("private-run"))
                    ),
                    mock.patch.object(
                        loop.sys, "argv", ["improvement_loop.py", "run"]
                    ),
                ):
                    self.assertEqual(loop.main(), expected)

    def test_cli_runtime_exception_returns_runner_failure_status(self):
        with (mock.patch.object(loop, "execute", side_effect=RuntimeError("boom")),
              mock.patch.object(loop.sys, "argv", ["improvement_loop.py", "run"])):
            self.assertEqual(loop.main(), 3)

    def test_cli_argument_error_returns_runner_failure_status(self):
        with mock.patch.object(
            loop.sys, "argv", ["improvement_loop.py", "invalid"]
        ):
            self.assertEqual(loop.main(), 3)

    def test_invalid_mode_fails_before_creating_run(self):
        with tempfile.TemporaryDirectory() as tmp:
            with mock.patch.object(loop, "IMPROVEMENT_RUNS_DIR", Path(tmp)):
                with self.assertRaises(ValueError):
                    loop.execute(mode="publish")
            self.assertEqual(list(Path(tmp).iterdir()), [])

    def test_run_id_cannot_escape_private_directory(self):
        for unsafe in ("../escape", "..\\escape", "/absolute", "two words"):
            with self.subTest(run_id=unsafe), tempfile.TemporaryDirectory() as tmp:
                with mock.patch.object(loop, "IMPROVEMENT_RUNS_DIR", Path(tmp)):
                    with self.assertRaises(ValueError):
                        loop.execute(run_id=unsafe)
                self.assertEqual(list(Path(tmp).iterdir()), [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
