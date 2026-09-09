#!/usr/bin/env python3
"""Deterministic and fail-closed tests for the predeploy Markdown renderer."""

from __future__ import annotations

import copy
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import tempfile
from unittest import mock

import write_predeploy_acceptance as acceptance


def expect_fail(action, contains: str) -> None:
    try:
        action()
    except acceptance.AcceptanceError as exc:
        assert contains in str(exc), exc
    else:
        raise AssertionError("expected AcceptanceError containing " + contains)


def fixture() -> dict:
    values = {name: "fixture" for name in acceptance.FIELD_ORDER}
    values.update({
        "schema_version": acceptance.SCHEMA_VERSION,
        "report_kind": acceptance.REPORT_KIND,
        "evaluated_at": "2026-08-24T12:00:00+00:00",
        "expires_at": "2026-08-24T14:00:00+00:00",
        "acceptance_contract_schema": 1,
        "acceptance_policy_path": acceptance.POLICY_PATH.as_posix(),
        "acceptance_policy_sha256": "a" * 64,
        "acceptance_max_age_hours": 2,
        "acceptance_max_funnel_report_age_hours": 2,
        "acceptance_future_skew_seconds": 300,
        "acceptance_exclusive_expiry": True,
        "evidence_only": True,
        "external_action_authorized": False,
        "deployment_authorized": False,
        "publication_authority": "NOT_AUTHORIZED",
        "final_verdict": "BLOCKED",
        "candidate_artifact_integrity": "PASS",
        "candidate_archive_member_count": 3,
        "candidate_archive_bytes": 123,
        "candidate_source_revision_clean": False,
        "manifest_schema": 2,
        "manifest_file_count": 2,
        "manifest_source_input_count": 14,
        "official_sources_configured": 31,
        "official_sources_successful": 31,
        "official_source_current_errors": 0,
        "official_source_pending_reviews": 31,
        "owner_review_packet_items": 31,
        "affected_content_items": 16,
        "affected_content_items_allowed": 0,
        "affected_content_items_blocked": 16,
        "calendar_publishable_count": 0,
        "calendar_structural_findings": 0,
        "workspace_clean": False,
        "funnel_score_descriptive": 80,
        "funnel_report_expires_at": "2026-08-24T14:00:00+00:00",
    })
    for name in acceptance.SHA256_FIELDS:
        values[name] = "a" * 64
    return values


def write_policy(root: Path, *, contract_overrides=None, marker=None) -> dict:
    contract = {
        "schema_version": 1,
        "max_age_hours": 2,
        "max_funnel_report_age_hours": 2,
        "future_skew_seconds": 300,
        "exclusive_expiry": True,
    }
    contract.update(contract_overrides or {})
    policy = {
        "release_attestation": {
            "schema_version": 1,
            "predeploy_acceptance": contract,
        }
    }
    if marker is not None:
        policy["test_marker"] = marker
    path = root / acceptance.POLICY_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(policy, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return acceptance._policy_contract(root)


def bound_fixture(root: Path, evaluated_at: datetime) -> dict:
    contract = acceptance._policy_contract(root)
    evaluated_at = evaluated_at.astimezone(timezone.utc).replace(microsecond=0)
    evidence = fixture()
    evidence.update({
        "evaluated_at": evaluated_at.isoformat(timespec="seconds"),
        "expires_at": (
            evaluated_at + timedelta(hours=contract["max_age_hours"])
        ).isoformat(timespec="seconds"),
        "acceptance_contract_schema": contract["schema_version"],
        "acceptance_policy_path": acceptance.POLICY_PATH.as_posix(),
        "acceptance_policy_sha256": contract["policy_sha256"],
        "acceptance_max_age_hours": contract["max_age_hours"],
        "acceptance_max_funnel_report_age_hours": contract[
            "max_funnel_report_age_hours"
        ],
        "acceptance_future_skew_seconds": contract["future_skew_seconds"],
        "acceptance_exclusive_expiry": contract["exclusive_expiry"],
        "funnel_report_evaluated_at": (
            evaluated_at - timedelta(minutes=15)
        ).isoformat(timespec="seconds"),
        "funnel_report_expires_at": (
            evaluated_at + timedelta(hours=1, minutes=45)
        ).isoformat(timespec="seconds"),
    })
    return evidence


def install_report(root: Path, evidence: dict) -> Path:
    path = root / acceptance.REPORT_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        acceptance.render_document(evidence), encoding="utf-8", newline="\n"
    )
    return path


def evidence_collector(recorded: dict, *, drift_field=None):
    recorded_at = acceptance._parse_time(recorded["evaluated_at"])

    def collect(_repo: Path, *, now: datetime) -> dict:
        normalized = now.astimezone(timezone.utc).replace(microsecond=0)
        current = copy.deepcopy(recorded)
        current["evaluated_at"] = normalized.isoformat(timespec="seconds")
        current["expires_at"] = (
            normalized
            + timedelta(hours=current["acceptance_max_age_hours"])
        ).isoformat(timespec="seconds")
        if drift_field and normalized != recorded_at:
            current[drift_field] = "b" * 64
        return current

    return collect


def test_temporal_and_current_contract() -> None:
    evaluated = datetime(2026, 8, 25, 5, 0, tzinfo=timezone.utc)
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        write_policy(root)
        evidence = bound_fixture(root, evaluated)
        report = install_report(root, evidence)
        original = report.read_bytes()
        original_mtime = report.stat().st_mtime_ns
        with mock.patch.object(
            acceptance,
            "collect_evidence",
            side_effect=evidence_collector(evidence),
        ):
            acceptance.check_integrity(root)
            acceptance.check_report(
                root,
                as_of=evaluated + timedelta(hours=2) - timedelta(microseconds=1),
            )
            assert report.read_bytes() == original
            assert report.stat().st_mtime_ns == original_mtime
            expect_fail(
                lambda: acceptance.check_report(
                    root, as_of=evaluated + timedelta(hours=2)
                ),
                "is stale",
            )
            # Historical integrity remains inspectable after decision expiry.
            acceptance.check_integrity(root)
            expect_fail(
                lambda: acceptance.check_report(
                    root, as_of=evaluated - timedelta(seconds=1)
                ),
                "not yet valid",
            )
            expect_fail(
                lambda: acceptance.check_report(
                    root, as_of=evaluated - timedelta(seconds=301)
                ),
                "exceeds future skew",
            )


def test_policy_and_timestamp_adversaries() -> None:
    evaluated = datetime(2026, 8, 25, 5, 0, tzinfo=timezone.utc)
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        write_policy(root)
        evidence = bound_fixture(root, evaluated)
        report = install_report(root, evidence)
        canonical = report.read_text(encoding="utf-8")
        with mock.patch.object(
            acceptance,
            "collect_evidence",
            side_effect=evidence_collector(evidence),
        ):
            report.write_text(
                canonical.replace(
                    evidence["expires_at"],
                    (evaluated + timedelta(hours=1)).isoformat(timespec="seconds"),
                    1,
                ),
                encoding="utf-8",
            )
            expect_fail(
                lambda: acceptance.check_integrity(root),
                "does not match the policy TTL",
            )
            report.write_text(
                canonical.replace(
                    evidence["evaluated_at"], "2026-08-25T05:00:00", 1
                ),
                encoding="utf-8",
            )
            expect_fail(
                lambda: acceptance.check_integrity(root), "must include a UTC offset"
            )
            report.write_text(
                canonical.replace(
                    evidence["expires_at"], "not-a-time", 1
                ),
                encoding="utf-8",
            )
            expect_fail(lambda: acceptance.check_integrity(root), "is invalid")
            report.write_text(canonical, encoding="utf-8")
            write_policy(root, marker="policy-byte-drift")
            expect_fail(
                lambda: acceptance.check_integrity(root),
                "policy binding is stale",
            )

    invalid_contracts = (
        ({"max_age_hours": True}, "non-negative integer"),
        ({"max_age_hours": 0}, "positive integer"),
        ({"exclusive_expiry": False}, "must be exclusive"),
        ({"future_skew_seconds": -1}, "non-negative integer"),
        ({"unexpected": 1}, "contract differs"),
    )
    for override, message in invalid_contracts:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = root / acceptance.POLICY_PATH
            path.parent.mkdir(parents=True, exist_ok=True)
            contract = {
                "schema_version": 1,
                "max_age_hours": 2,
                "max_funnel_report_age_hours": 2,
                "future_skew_seconds": 300,
                "exclusive_expiry": True,
            }
            contract.update(override)
            path.write_text(
                json.dumps({
                    "release_attestation": {
                        "schema_version": 1,
                        "predeploy_acceptance": contract,
                    }
                }),
                encoding="utf-8",
            )
            expect_fail(lambda: acceptance._policy_contract(root), message)


def test_current_evidence_drift_is_field_scoped() -> None:
    evaluated = datetime(2026, 8, 25, 5, 0, tzinfo=timezone.utc)
    drift_fields = (
        "candidate_id",
        "official_snapshot_sha256",
        "official_source_decisions_sha256",
        "calendar_sha256",
        "calendar_decision_sha256",
        "ga4_decision_evidence_sha256",
        "funnel_report_sha256",
    )
    for drift_field in drift_fields:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_policy(root)
            evidence = bound_fixture(root, evaluated)
            install_report(root, evidence)
            with mock.patch.object(
                acceptance,
                "collect_evidence",
                side_effect=evidence_collector(
                    evidence, drift_field=drift_field
                ),
            ):
                expect_fail(
                    lambda: acceptance.check_report(
                        root, as_of=evaluated + timedelta(hours=1)
                    ),
                    drift_field,
                )


def test_funnel_currentness_boundaries() -> None:
    evaluated = datetime(2026, 8, 25, 5, 0, tzinfo=timezone.utc)
    contract = {
        "max_funnel_report_age_hours": 2,
        "future_skew_seconds": 300,
    }
    funnel = {"evaluated_at": evaluated.isoformat(timespec="seconds")}
    acceptance._funnel_currentness(
        funnel,
        now=evaluated + timedelta(hours=2) - timedelta(microseconds=1),
        contract=contract,
    )
    expect_fail(
        lambda: acceptance._funnel_currentness(
            funnel, now=evaluated + timedelta(hours=2), contract=contract
        ),
        "is stale",
    )
    expect_fail(
        lambda: acceptance._funnel_currentness(
            funnel, now=evaluated - timedelta(seconds=1), contract=contract
        ),
        "not yet valid",
    )
    expect_fail(
        lambda: acceptance._funnel_currentness(
            funnel, now=evaluated - timedelta(seconds=301), contract=contract
        ),
        "exceeds future skew",
    )
    expect_fail(
        lambda: acceptance._funnel_currentness(
            {"evaluated_at": "2026-08-25T05:00:00"},
            now=evaluated,
            contract=contract,
        ),
        "must include a UTC offset",
    )


def run() -> None:
    evidence = fixture()
    first = acceptance.render_document(evidence)
    second = acceptance.render_document(copy.deepcopy(evidence))
    assert first == second
    assert first.endswith("\n")
    assert acceptance.field(first, "final_verdict") == "BLOCKED"
    assert "deployment_authorized: `false`" in first

    authorized = copy.deepcopy(evidence)
    authorized["deployment_authorized"] = True
    expect_fail(
        lambda: acceptance.render_document(authorized),
        "overclaims authority",
    )

    unsafe = copy.deepcopy(evidence)
    unsafe["release_id"] = "one\ntwo"
    expect_fail(
        lambda: acceptance.render_document(unsafe),
        "unsafe Markdown",
    )

    incomplete = copy.deepcopy(evidence)
    incomplete.pop("ga4_decision_trust")
    expect_fail(
        lambda: acceptance.render_document(incomplete),
        "fields differ",
    )
    invalid_hash = copy.deepcopy(evidence)
    invalid_hash["calendar_sha256"] = "not-a-hash"
    expect_fail(
        lambda: acceptance.render_document(invalid_hash),
        "invalid SHA-256",
    )
    expect_fail(
        lambda: acceptance._add_hours(
            datetime.max.replace(tzinfo=timezone.utc), 1, "test expiry"
        ),
        "out of range",
    )
    test_temporal_and_current_contract()
    test_policy_and_timestamp_adversaries()
    test_current_evidence_drift_is_field_scoped()
    test_funnel_currentness_boundaries()
    print("predeploy acceptance writer: 5/5 groups PASS")


if __name__ == "__main__":
    run()
