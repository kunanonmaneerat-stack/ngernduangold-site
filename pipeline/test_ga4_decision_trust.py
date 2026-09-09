#!/usr/bin/env python3
"""Regression tests for fail-closed GA4 decision trust; local fixtures only."""

from __future__ import annotations

import datetime
import copy
import hashlib
import ipaddress
import json
import platform
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ga4_decision_trust as TRUST  # noqa: E402
import weekly_growth_review as REVIEW  # noqa: E402


def _fixture_json_bytes(value) -> bytes:
    return (
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n"
    ).encode("utf-8")


def write_json(path: Path, value) -> None:
    payload = copy.deepcopy(value)

    def materialize(item) -> None:
        if isinstance(item, dict):
            attestation = item.get("coverage_attestation")
            if isinstance(attestation, dict):
                observation = attestation.pop(
                    "_admin_observation_fixture", None
                )
                if observation is not None:
                    contract = attestation["admin_observation_contract"]
                    evidence_path = path.parent / contract["default"]
                    evidence_path.write_bytes(_fixture_json_bytes(observation))
            for child in item.values():
                materialize(child)
        elif isinstance(item, list):
            for child in item:
                materialize(child)

    materialize(payload)
    path.write_text(json.dumps(payload), encoding="utf-8")


def current_policy(cidr: str) -> dict:
    verified_at = (
        datetime.date.today() - datetime.timedelta(days=35)
    ).isoformat()
    policy = {
        "ga4": {
            "internal_traffic": {
                "filter_state": "Active",
                "filter_operation": "Exclude",
                "ips": [cidr],
                "verified_at": verified_at,
            }
        }
    }
    bind_coverage_attestation(policy["ga4"]["internal_traffic"])
    return policy


def bind_coverage_attestation(block: dict) -> None:
    raw_cidrs = block.get("ips", block.get("cidrs", []))
    if isinstance(raw_cidrs, str):
        raw_cidrs = [raw_cidrs]
    try:
        networks = [
            ipaddress.ip_network(str(value).strip(), strict=False)
            for value in raw_cidrs
        ]
        fingerprint = TRUST._cidr_set_sha256(networks)
    except ValueError:
        # Invalid-CIDR fixtures must reach the production parser; the binding
        # itself is intentionally unusable and cannot turn that case trusted.
        fingerprint = "0" * 64
    verified_at = block["verified_at"]
    verified_day, error = TRUST._verified_business_date(block)
    if error or verified_day is None:
        raise ValueError(error or "invalid verified_at fixture")
    block["coverage_attestation"] = {
        "schema_version": TRUST.COVERAGE_ATTESTATION_SCHEMA_VERSION,
        "source": TRUST.COVERAGE_ATTESTATION_SOURCE,
        "verified_at": verified_at,
        "attested_at": verified_day.isoformat() + "T00:00:00+07:00",
        "cidr_set_sha256": fingerprint,
    }
    attestation = block["coverage_attestation"]
    raw_cidrs = block.get("ips", block.get("cidrs", []))
    if isinstance(raw_cidrs, str):
        raw_cidrs = [raw_cidrs]
    observation = {
        "schema_version": 1,
        "mode": "authenticated_browser_read_only",
        "observed_at": attestation["attested_at"],
        "external_mutations": [],
        "internal_traffic": {
            "filter_state": "Active",
            "filter_operation": "Exclude",
            "exact_normalized_set_match": True,
            "condition_count": len(set(raw_cidrs)),
            "private_contract_condition_count": len(set(raw_cidrs)),
            "raw_network_values_emitted": False,
            "cidr_set_sha256": fingerprint,
        },
    }
    evidence_name = "ga4-admin-observation-fixture.json"
    attestation["admin_observation_contract"] = {
        "schema_version": 1,
        "default": evidence_name,
        "sha256": hashlib.sha256(_fixture_json_bytes(observation)).hexdigest(),
    }
    attestation["_admin_observation_fixture"] = observation


def current_host(address: str, key: str = "ip") -> dict:
    return {
        key: address,
        "checked_at": datetime.datetime.now(
            datetime.timezone.utc
        ).isoformat(timespec="seconds"),
        "source": "api.ipify.org",
        "host": platform.node(),
    }


class TrustHelperTests(unittest.TestCase):
    def test_private_contract_loads_and_fails_closed_when_missing(self) -> None:
        with tempfile.TemporaryDirectory(prefix="ga4_private_contract_") as tmp:
            root = Path(tmp)
            control = root / ".system_control"
            private = root / ".local-private" / "runtime"
            control.mkdir()
            private.mkdir(parents=True)
            policy = control / "policy.json"
            host_contract = control / "host.json"
            private_policy = private / "ga4-policy-private.json"
            private_host = private / "host-state.json"
            write_json(
                policy,
                {"ga4": {"internal_traffic": {"private_config_contract": {
                    "schema_version": 1,
                    "default": ".local-private/runtime/ga4-policy-private.json"
                }}}},
            )
            write_json(
                host_contract,
                {"private_state_contract": {
                    "default": ".local-private/runtime/host-state.json"
                }},
            )
            write_json(
                private_policy,
                {"schema_version": 1, **current_policy("203.0.113.0/24")},
            )
            write_json(private_host, current_host("203.0.113.17"))

            trusted = TRUST.evaluate_ga4_decision_trust(policy, host_contract)
            self.assertTrue(trusted.trusted)
            self.assertIn("private", trusted.schema)
            self.assertNotIn("203.0.113", trusted.reason)

            private_policy.unlink()
            missing = TRUST.evaluate_ga4_decision_trust(policy, host_contract)
            self.assertFalse(missing.trusted)
            self.assertEqual(missing.label, "UNTRUSTED")

    def test_private_contract_and_document_schema_are_exact_integers(self) -> None:
        with tempfile.TemporaryDirectory(prefix="ga4_private_schema_") as tmp:
            root = Path(tmp)
            control = root / ".system_control"
            private = root / ".local-private" / "runtime"
            control.mkdir()
            private.mkdir(parents=True)
            policy = control / "policy.json"
            host_contract = control / "host.json"
            private_policy = private / "ga4-policy-private.json"
            private_host = private / "host-state.json"
            write_json(
                host_contract,
                {"private_state_contract": {
                    "default": ".local-private/runtime/host-state.json"
                }},
            )
            write_json(private_host, current_host("203.0.113.17"))

            for contract_schema, document_schema in (
                (None, 1),
                (True, 1),
                (1, None),
                (1, True),
                (1, 2),
            ):
                contract = {
                    "default": ".local-private/runtime/ga4-policy-private.json"
                }
                if contract_schema is not None:
                    contract["schema_version"] = contract_schema
                write_json(
                    policy,
                    {"ga4": {"internal_traffic": {
                        "private_config_contract": contract
                    }}},
                )
                document = current_policy("203.0.113.0/24")
                if document_schema is not None:
                    document = {"schema_version": document_schema, **document}
                write_json(private_policy, document)

                result = TRUST.evaluate_ga4_decision_trust(
                    policy, host_contract
                )
                self.assertFalse(result.trusted)
                self.assertEqual(result.label, "UNTRUSTED")
                self.assertIn("schema_version", result.reason)
                self.assertNotIn("203.0.113", result.reason)

    def test_matching_current_schema_is_trusted(self) -> None:
        with tempfile.TemporaryDirectory(prefix="ga4_trust_") as tmp:
            root = Path(tmp)
            policy = root / "policy.json"
            host = root / "host.json"
            write_json(policy, current_policy("203.0.113.0/24"))
            write_json(host, current_host("203.0.113.17"))
            result = TRUST.evaluate_ga4_decision_trust(policy, host)
        self.assertTrue(result.trusted)
        self.assertEqual(result.label, "TRUSTED")
        self.assertIsNotNone(result.expires_at)

    def test_cidr_change_cannot_reuse_old_coverage_attestation(self) -> None:
        with tempfile.TemporaryDirectory(prefix="ga4_trust_binding_") as tmp:
            root = Path(tmp)
            policy = root / "policy.json"
            host = root / "host.json"
            config = current_policy("203.0.113.0/24")
            config["ga4"]["internal_traffic"]["ips"].append(
                "198.51.100.0/24"
            )
            write_json(policy, config)
            write_json(host, current_host("203.0.113.17"))
            result = TRUST.evaluate_ga4_decision_trust(policy, host)
        self.assertFalse(result.trusted)
        self.assertIn("does not match the configured CIDR set", result.reason)
        self.assertNotIn("203.0.113", result.reason)
        self.assertNotIn("198.51.100", result.reason)

    def test_admin_observation_file_is_hash_bound(self) -> None:
        with tempfile.TemporaryDirectory(prefix="ga4_trust_admin_hash_") as tmp:
            root = Path(tmp)
            policy = root / "policy.json"
            host = root / "host.json"
            write_json(policy, current_policy("203.0.113.0/24"))
            write_json(host, current_host("203.0.113.17"))
            evidence = root / "ga4-admin-observation-fixture.json"
            evidence.write_text("{}\n", encoding="utf-8")
            result = TRUST.evaluate_ga4_decision_trust(policy, host)
        self.assertFalse(result.trusted)
        self.assertIn("SHA-256 does not match", result.reason)
        self.assertNotIn("203.0.113", result.reason)

    def test_rehashed_admin_observation_must_match_cidr_semantics(self) -> None:
        with tempfile.TemporaryDirectory(prefix="ga4_trust_admin_semantics_") as tmp:
            root = Path(tmp)
            policy = root / "policy.json"
            host = root / "host.json"
            config = current_policy("203.0.113.0/24")
            attestation = config["ga4"]["internal_traffic"][
                "coverage_attestation"
            ]
            observation = attestation["_admin_observation_fixture"]
            observation["internal_traffic"]["cidr_set_sha256"] = "0" * 64
            attestation["admin_observation_contract"]["sha256"] = (
                hashlib.sha256(_fixture_json_bytes(observation)).hexdigest()
            )
            write_json(policy, config)
            write_json(host, current_host("203.0.113.17"))
            result = TRUST.evaluate_ga4_decision_trust(policy, host)
        self.assertFalse(result.trusted)
        self.assertIn("observation CIDR-set fingerprint", result.reason)
        self.assertNotIn("203.0.113", result.reason)

    def test_missing_or_retrodated_attestation_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory(prefix="ga4_trust_attestation_") as tmp:
            root = Path(tmp)
            policy = root / "policy.json"
            host = root / "host.json"
            config = current_policy("203.0.113.0/24")
            block = config["ga4"]["internal_traffic"]
            write_json(host, current_host("203.0.113.17"))

            block.pop("coverage_attestation")
            write_json(policy, config)
            missing = TRUST.evaluate_ga4_decision_trust(policy, host)
            self.assertFalse(missing.trusted)
            self.assertIn("attestation is missing", missing.reason)

            bind_coverage_attestation(block)
            block["coverage_attestation"]["attested_at"] = (
                datetime.date.today().isoformat() + "T00:00:00+07:00"
            )
            write_json(policy, config)
            retrodated = TRUST.evaluate_ga4_decision_trust(policy, host)
        self.assertFalse(retrodated.trusted)
        self.assertIn("clean-window start date", retrodated.reason)

    def test_trust_json_rejects_duplicate_keys_and_nonfinite_numbers(self) -> None:
        now = datetime.datetime(2026, 8, 24, 12, tzinfo=datetime.timezone.utc)
        config = current_policy("203.0.113.0/24")
        config["ga4"]["internal_traffic"]["verified_at"] = "2026-07-01"
        with tempfile.TemporaryDirectory(prefix="ga4_trust_strict_json_") as tmp:
            root = Path(tmp)
            policy = root / "policy.json"
            host = root / "host.json"
            write_json(policy, config)
            suffix = (
                ',"checked_at":"2026-08-24T11:00:00+00:00",'
                '"source":"api.ipify.org","host":%s}' % json.dumps(platform.node())
            )
            for raw in (
                '{"ip":"198.51.100.9","ip":"203.0.113.17"' + suffix,
                '{"ip":"203.0.113.17","unexpected":NaN' + suffix,
                '{"ip":"203.0.113.17","unexpected":Infinity' + suffix,
                '{"ip":"203.0.113.17","unexpected":1e999' + suffix,
            ):
                host.write_text(raw, encoding="utf-8")
                result = TRUST.evaluate_ga4_decision_trust(
                    policy, host, now=now
                )
                self.assertFalse(result.trusted)
                self.assertEqual(result.label, "UNTRUSTED")
                self.assertIn("invalid JSON", result.reason)

    def test_runtime_trust_has_one_exclusive_host_freshness_boundary(self) -> None:
        with tempfile.TemporaryDirectory(prefix="ga4_trust_expiry_") as tmp:
            root = Path(tmp)
            policy = root / "policy.json"
            host = root / "host.json"
            now = datetime.datetime(2026, 8, 16, 4, tzinfo=datetime.timezone.utc)
            checked = now - datetime.timedelta(days=6)
            config = current_policy("203.0.113.0/24")
            config["ga4"]["internal_traffic"]["verified_at"] = "2026-07-01"
            bind_coverage_attestation(config["ga4"]["internal_traffic"])
            state = current_host("203.0.113.17")
            state["checked_at"] = checked.isoformat()
            write_json(policy, config)
            write_json(host, state)

            current = TRUST.evaluate_ga4_decision_trust(policy, host, now=now)
            at_boundary = TRUST.evaluate_ga4_decision_trust(
                policy, host,
                now=checked + datetime.timedelta(days=TRUST.HOST_STATE_MAX_AGE_DAYS),
            )

        self.assertTrue(current.trusted)
        self.assertEqual(
            current.expires_at,
            (checked + datetime.timedelta(days=7)).isoformat(timespec="seconds"),
        )
        self.assertFalse(at_boundary.trusted)
        self.assertIn("stale", at_boundary.reason)

    def test_legacy_schema_is_supported(self) -> None:
        with tempfile.TemporaryDirectory(prefix="ga4_trust_legacy_") as tmp:
            root = Path(tmp)
            policy = root / "policy.json"
            host = root / "host.json"
            block = {
                "state": "active", "cidrs": "198.51.100.0/24",
                "operation": "exclude",
                "verified_at": (
                    datetime.date.today() - datetime.timedelta(days=35)
                ).isoformat(),
            }
            bind_coverage_attestation(block)
            write_json(policy, {"ga4_internal_traffic": block})
            write_json(host, current_host("198.51.100.42", "egress_ip"))
            result = TRUST.evaluate_ga4_decision_trust(policy, host)
        self.assertTrue(result.trusted)
        self.assertIn("legacy", result.schema)

    def test_mismatch_and_unreadable_config_are_untrusted(self) -> None:
        with tempfile.TemporaryDirectory(prefix="ga4_trust_bad_") as tmp:
            root = Path(tmp)
            policy = root / "policy.json"
            host = root / "host.json"
            write_json(policy, current_policy("203.0.113.0/24"))
            write_json(host, current_host("198.51.100.9"))
            mismatch = TRUST.evaluate_ga4_decision_trust(policy, host)
            self.assertFalse(mismatch.trusted)
            self.assertEqual(mismatch.label, "UNTRUSTED")
            self.assertIn("outside configured", mismatch.reason)

            policy.write_text("{not-json", encoding="utf-8")
            unreadable = TRUST.evaluate_ga4_decision_trust(policy, host)
            self.assertFalse(unreadable.trusted)
            self.assertEqual(unreadable.label, "UNTRUSTED")

    def test_inactive_filter_and_invalid_cidr_are_untrusted(self) -> None:
        with tempfile.TemporaryDirectory(prefix="ga4_trust_gate_") as tmp:
            root = Path(tmp)
            policy = root / "policy.json"
            host = root / "host.json"
            write_json(host, current_host("203.0.113.5"))
            inactive = current_policy("203.0.113.0/24")
            inactive["ga4"]["internal_traffic"]["filter_state"] = "Testing"
            write_json(policy, inactive)
            self.assertFalse(TRUST.evaluate_ga4_decision_trust(policy, host).trusted)

            write_json(policy, current_policy("not-a-cidr"))
            self.assertFalse(TRUST.evaluate_ga4_decision_trust(policy, host).trusted)

    def test_catch_all_network_cannot_make_every_egress_trusted(self) -> None:
        with tempfile.TemporaryDirectory(prefix="ga4_trust_catch_all_") as tmp:
            root = Path(tmp)
            policy = root / "policy.json"
            host = root / "host.json"
            write_json(policy, current_policy("0.0.0.0/0"))
            write_json(host, current_host("198.51.100.9"))
            result = TRUST.evaluate_ga4_decision_trust(policy, host)
        self.assertFalse(result.trusted)
        self.assertIn("broader", result.reason)
        self.assertNotIn("198.51.100", result.reason)

    def test_conflicting_aliases_cannot_select_the_first_convenient_value(self) -> None:
        with tempfile.TemporaryDirectory(prefix="ga4_trust_aliases_") as tmp:
            root = Path(tmp)
            policy = root / "policy.json"
            host = root / "host.json"
            config = current_policy("203.0.113.0/24")
            config["ga4"]["internal_traffic"]["cidrs"] = ["198.51.100.0/24"]
            write_json(policy, config)
            state = current_host("203.0.113.17")
            state["egress_ip"] = "198.51.100.17"
            write_json(host, state)
            policy_result = TRUST.evaluate_ga4_decision_trust(policy, host)
            self.assertFalse(policy_result.trusted)
            self.assertIn("ambiguous aliases", policy_result.reason)

            config["ga4"]["internal_traffic"].pop("cidrs")
            write_json(policy, config)
            host_result = TRUST.evaluate_ga4_decision_trust(policy, host)
        self.assertFalse(host_result.trusted)
        self.assertIn("ambiguous aliases", host_result.reason)

    def test_missing_or_non_exclude_operation_is_untrusted(self) -> None:
        with tempfile.TemporaryDirectory(prefix="ga4_trust_operation_") as tmp:
            root = Path(tmp)
            policy = root / "policy.json"
            host = root / "host.json"
            write_json(host, current_host("203.0.113.5"))

            missing = current_policy("203.0.113.0/24")
            missing["ga4"]["internal_traffic"].pop("filter_operation")
            write_json(policy, missing)
            missing_result = TRUST.evaluate_ga4_decision_trust(policy, host)
            self.assertFalse(missing_result.trusted)
            self.assertIn("operation is missing", missing_result.reason)

            included = current_policy("203.0.113.0/24")
            included["ga4"]["internal_traffic"]["filter_operation"] = "Include"
            write_json(policy, included)
            included_result = TRUST.evaluate_ga4_decision_trust(policy, host)
            self.assertFalse(included_result.trusted)
            self.assertIn("not Exclude", included_result.reason)

    def test_enabled_boolean_cannot_replace_active_filter_state(self) -> None:
        with tempfile.TemporaryDirectory(prefix="ga4_trust_state_") as tmp:
            root = Path(tmp)
            policy = root / "policy.json"
            host = root / "host.json"
            write_json(host, current_host("203.0.113.5"))
            missing_state = current_policy("203.0.113.0/24")
            block = missing_state["ga4"]["internal_traffic"]
            block.pop("filter_state")
            block["enabled"] = True
            write_json(policy, missing_state)
            result = TRUST.evaluate_ga4_decision_trust(policy, host)
        self.assertFalse(result.trusted)
        self.assertIn("filter is not active", result.reason)

    def test_recent_filter_coverage_cannot_clear_a_historical_window(self) -> None:
        with tempfile.TemporaryDirectory(prefix="ga4_trust_recent_") as tmp:
            root = Path(tmp)
            policy = root / "policy.json"
            host = root / "host.json"
            recent = current_policy("203.0.113.0/24")
            recent["ga4"]["internal_traffic"]["verified_at"] = datetime.date.today().isoformat()
            write_json(policy, recent)
            write_json(host, current_host("203.0.113.17"))
            result = TRUST.evaluate_ga4_decision_trust(policy, host)
        self.assertFalse(result.trusted)
        self.assertIn("full 28-day", result.reason)

    def test_coverage_timestamp_uses_bangkok_business_date(self) -> None:
        today = datetime.date(2026, 8, 23)
        shifted_into_next_bangkok_day = TRUST._coverage_window_error(
            {"verified_at": "2026-07-27T23:30:00-04:00"}, today=today
        )
        exact_bangkok_boundary = TRUST._coverage_window_error(
            {"verified_at": "2026-07-26T17:00:00Z"}, today=today
        )
        naive_timestamp = TRUST._coverage_window_error(
            {"verified_at": "2026-07-27T00:00:00"}, today=today
        )

        self.assertIn("full 28-day", shifted_into_next_bangkok_day)
        self.assertIsNone(exact_bangkok_boundary)
        self.assertIn("invalid", naive_timestamp)

    def test_recent_filter_also_reports_uncovered_egress_immediately(self) -> None:
        with tempfile.TemporaryDirectory(prefix="ga4_trust_two_blockers_") as tmp:
            root = Path(tmp)
            policy = root / "policy.json"
            host = root / "host.json"
            recent = current_policy("203.0.113.0/24")
            recent["ga4"]["internal_traffic"]["verified_at"] = datetime.date.today().isoformat()
            write_json(policy, recent)
            write_json(host, current_host("198.51.100.17"))
            result = TRUST.evaluate_ga4_decision_trust(policy, host)
        self.assertFalse(result.trusted)
        self.assertIn("outside configured", result.reason)
        self.assertIn("full 28-day", result.reason)
        self.assertNotIn("198.51.100", result.reason)

    def test_host_and_source_provenance_fail_closed_without_leaking_values(self) -> None:
        with tempfile.TemporaryDirectory(prefix="ga4_trust_origin_") as tmp:
            root = Path(tmp)
            policy = root / "policy.json"
            host = root / "host.json"
            write_json(policy, current_policy("203.0.113.0/24"))

            wrong_host = current_host("203.0.113.17")
            wrong_host["host"] = "different-fixture-host"
            write_json(host, wrong_host)
            mismatch = TRUST.evaluate_ga4_decision_trust(policy, host)
            self.assertFalse(mismatch.trusted)
            self.assertIn("different host", mismatch.reason)
            self.assertNotIn(wrong_host["host"], mismatch.reason)
            self.assertNotIn("203.0.113", repr(mismatch))

            no_source = current_host("203.0.113.17")
            no_source.pop("source")
            write_json(host, no_source)
            unsupported = TRUST.evaluate_ga4_decision_trust(policy, host)
            self.assertFalse(unsupported.trusted)
            self.assertIn("source is missing or unsupported", unsupported.reason)
            self.assertNotIn("203.0.113", repr(unsupported))


class WeeklyReportTests(unittest.TestCase):
    def _run_report(self, root: Path, policy: dict, host: dict, legacy_csv: bool = False):
        log = root / "automation-log"
        inbox = log / "cowork-inbox"
        log.mkdir()
        policy_path = root / "policy.json"
        host_path = root / "host.json"
        write_json(policy_path, policy)
        write_json(host_path, host)
        if legacy_csv:
            (log / "ga4-metrics.csv").write_text(
                "source,sessions,conversion,quiz_start\nfacebook,20,3,1\n",
                encoding="utf-8",
            )
            (log / "ga4-pages.csv").write_text(
                "page,views,conversion\n/clicked-page,12,2\n/leak-page,8,0\n",
                encoding="utf-8",
            )
        else:
            (log / "ga4-metrics.csv").write_text(
                "source,sessions,affiliate_click,quiz_start\nfacebook,20,3,1\n",
                encoding="utf-8",
            )
            (log / "ga4-pages.csv").write_text(
                "page,views,affiliate_click\n/clicked-page,12,2\n/leak-page,8,0\n",
                encoding="utf-8",
            )

        gsc_pull = types.ModuleType("gsc_pull")
        gsc_pull.pull = lambda: None
        messages = []
        cc_bridge = types.ModuleType("cc_bridge")
        cc_bridge.ping = messages.append
        current_trust = TRUST.evaluate_ga4_decision_trust(policy_path, host_path)
        bundle_readiness = types.SimpleNamespace(
            ga4=types.SimpleNamespace(
                trusted=current_trust.trusted,
                label=current_trust.label,
                reason=current_trust.reason,
                schema=current_trust.schema,
                state="CURRENT" if current_trust.trusted else "UNTRUSTED",
                expires_at=current_trust.expires_at,
            ),
            gsc=types.SimpleNamespace(
                trusted=False, label="UNTRUSTED", reason="fixture has no GSC bundle",
                schema="fixture", state="MISSING_METADATA",
            ),
            revenue=types.SimpleNamespace(
                trusted=False,
                label="UNTRUSTED",
                reason="fixture has no reconciled affiliate revenue bundle",
                schema="fixture",
                state="UNAVAILABLE",
            ),
        )
        with (
            mock.patch.dict(sys.modules, {"gsc_pull": gsc_pull, "cc_bridge": cc_bridge}),
            mock.patch.object(REVIEW, "LOG", str(log)),
            mock.patch.object(REVIEW, "INBOX", str(inbox)),
            mock.patch.object(REVIEW, "GA4", str(log / "ga4-metrics.csv")),
            mock.patch.object(REVIEW, "PAGES", str(log / "ga4-pages.csv")),
            mock.patch.object(REVIEW, "GSC", str(log / "gsc-queries.csv")),
            mock.patch.object(REVIEW, "GSCP", str(log / "gsc-pages.csv")),
            mock.patch.object(REVIEW, "POLICY", str(policy_path)),
            mock.patch.object(REVIEW, "HOST_IP", str(host_path)),
            mock.patch.object(REVIEW, "_decision_readiness", return_value=bundle_readiness),
        ):
            out = Path(REVIEW.main())
        return out.read_text(encoding="utf-8"), messages

    def test_untrusted_report_blocks_ga4_decisions(self) -> None:
        with tempfile.TemporaryDirectory(prefix="weekly_untrusted_") as tmp:
            report, messages = self._run_report(
                Path(tmp),
                current_policy("203.0.113.0/24"),
                current_host("198.51.100.8"),
            )
        self.assertIn("GA4 Decision Trust — UNTRUSTED", report)
        self.assertIn("การตัดสินใจ: BLOCKED", report)
        self.assertNotIn("แปลงดีสุด", report)
        self.assertNotIn("เพิ่มความถี่/คอนเทนต์ช่องนี้ก่อน", report)
        self.assertNotIn("เขียนบทความใกล้เคียง winner", report)
        self.assertNotIn("ทำต่อ: หน้าเหล่านี้มีคนอ่านแต่ไม่คลิก", report)
        self.assertIn("canonical evidence states are bound above", report)
        self.assertEqual(messages, [], "weekly local report must not notify externally")

    def test_trusted_report_keeps_legacy_schema_but_does_not_scale_clicks(self) -> None:
        with tempfile.TemporaryDirectory(prefix="weekly_trusted_") as tmp:
            report, messages = self._run_report(
                Path(tmp),
                current_policy("203.0.113.0/24"),
                current_host("203.0.113.8"),
                legacy_csv=True,
            )
        self.assertIn("GA4 Decision Trust — TRUSTED", report)
        self.assertIn("affiliate_click(intent events)=3", report)
        self.assertIn("affiliate_click events/100 sessions=15.0", report)
        self.assertIn("| affiliate_click events | events/100 sessions |", report)
        self.assertNotIn("click-rate", report)
        self.assertIn("intent signal ไม่ใช่รายได้", report)
        self.assertIn("paid affiliate commission", report)
        self.assertNotIn("เพิ่มความถี่/คอนเทนต์ช่องนี้ก่อน", report)
        self.assertNotIn("เขียนบทความใกล้เคียง winner", report)
        self.assertNotIn("double-down", report)
        self.assertIn("canonical evidence states are bound above", report)
        self.assertNotIn("GSC=MISSING_METADATA · verified affiliate revenue", report)
        self.assertEqual(messages, [], "trusted analytics still must not notify externally")


if __name__ == "__main__":
    unittest.main(verbosity=2)
