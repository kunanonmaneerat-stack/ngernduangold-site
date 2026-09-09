#!/usr/bin/env python3
import datetime as dt
import hashlib
import ipaddress
import json
from pathlib import Path
import platform
import tempfile
import unittest

try:
    from . import ga4_readiness_report as report
except ImportError:
    import ga4_readiness_report as report


NOW = dt.datetime(2026, 8, 24, 15, tzinfo=dt.timezone.utc)


def write_json(path: Path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def fixture_json_bytes(payload) -> bytes:
    return (
        json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n"
    ).encode("utf-8")


class Ga4ReadinessReportTests(unittest.TestCase):
    def fixture(self, root: Path, *, covered: bool, attested: bool = True):
        cidr = "203.0.113.17/32" if covered else "198.51.100.8/32"
        block = {
            "filter_state": "Active",
            "filter_operation": "Exclude",
            "ips": [cidr],
            "verified_at": "2026-07-01",
        }
        if attested:
            fingerprint = report.ga4_decision_trust._cidr_set_sha256(
                [ipaddress.ip_network(cidr, strict=False)]
            )
            observed_at = "2026-07-01T00:00:00+07:00"
            observation = {
                "schema_version": 1,
                "mode": "authenticated_browser_read_only",
                "observed_at": observed_at,
                "external_mutations": [],
                "internal_traffic": {
                    "filter_state": "Active",
                    "filter_operation": "Exclude",
                    "exact_normalized_set_match": True,
                    "condition_count": 1,
                    "private_contract_condition_count": 1,
                    "raw_network_values_emitted": False,
                    "cidr_set_sha256": fingerprint,
                },
            }
            evidence_name = "ga4-admin-observation-fixture.json"
            evidence_bytes = fixture_json_bytes(observation)
            evidence_path = root / ".system_control" / evidence_name
            evidence_path.parent.mkdir(parents=True, exist_ok=True)
            evidence_path.write_bytes(evidence_bytes)
            block["coverage_attestation"] = {
                "schema_version": report.ga4_decision_trust.COVERAGE_ATTESTATION_SCHEMA_VERSION,
                "source": report.ga4_decision_trust.COVERAGE_ATTESTATION_SOURCE,
                "verified_at": "2026-07-01",
                "attested_at": observed_at,
                "cidr_set_sha256": fingerprint,
                "admin_observation_contract": {
                    "schema_version": 1,
                    "default": evidence_name,
                    "sha256": hashlib.sha256(evidence_bytes).hexdigest(),
                },
            }
        policy = {
            "ga4": {"internal_traffic": block}
        }
        host = {
            "ip": "203.0.113.17",
            "checked_at": (NOW - dt.timedelta(hours=1)).isoformat(),
            "source": "api.ipify.org",
            "host": platform.node(),
        }
        write_json(root / ".system_control" / "policy.json", policy)
        write_json(root / ".system_control" / "host_ip.json", host)
        log = root / "automation-log"
        log.mkdir()
        for name in ("ga4-metrics.csv", "ga4-pages.csv", "ga4-funnel.csv"):
            (log / name).write_text("legacy\n", encoding="utf-8")
        write_json(log / "ga4-snapshot.json", {
            "schema_version": 1,
            "captured_at": "2026-08-16T05:57:38+00:00",
            "window_start": "2026-07-20",
            "window_end": "2026-08-16",
            "window_days": 28,
            "ga4_decision_trust": "UNTRUSTED",
            "files": {"metrics": "0", "pages": "0", "funnel": "0"},
        })

    def test_legacy_bundle_gets_exact_machine_readable_blockers(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.fixture(root, covered=True)
            result = report.build_report(root, now=NOW)
        codes = {item["code"] for item in result["blockers"]}
        self.assertFalse(result["ready_for_decisions"])
        self.assertTrue(result["ready_to_pull"])
        self.assertEqual(result["decision_state"], "BLOCKED")
        self.assertIn("SNAPSHOT_SCHEMA_NOT_V3", codes)
        self.assertIn("SNAPSHOT_REQUIRED_FIELDS_MISSING", codes)
        self.assertIn("SNAPSHOT_FILE_SET_INCOMPLETE", codes)
        self.assertIn("QUERY_COVERAGE_MISSING", codes)
        self.assertIn("SNAPSHOT_WINDOW_NOT_CURRENT", codes)
        self.assertIn("CAPTURE_TRUST_NOT_TRUSTED", codes)
        self.assertNotIn("COVERAGE_ATTESTATION_NOT_BOUND", codes)
        self.assertEqual(
            result["bundle"]["files"]["missing_declared_keys"],
            ["pilot_sessions"],
        )
        self.assertEqual(
            result["bundle"]["query_coverage"]["missing_keys"],
            sorted(report.ga4_pull.GA4_QUERY_NAMES),
        )

    def test_network_values_are_redacted_and_mismatch_blocks_pull(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.fixture(root, covered=False)
            result = report.build_report(root, now=NOW)
        rendered = json.dumps(result)
        self.assertFalse(result["ready_to_pull"])
        self.assertFalse(result["runtime"]["current_egress_covered"])
        self.assertIn(
            "CURRENT_EGRESS_NOT_COVERED",
            {item["code"] for item in result["blockers"]},
        )
        self.assertNotIn("203.0.113.17", rendered)
        self.assertNotIn("198.51.100.8", rendered)
        self.assertTrue(result["runtime"]["raw_network_values_redacted"])
        self.assertFalse(any(result["safety"].values()))

    def test_missing_attestation_is_an_explicit_runtime_blocker(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.fixture(root, covered=True, attested=False)
            result = report.build_report(root, now=NOW)
        codes = {item["code"] for item in result["blockers"]}
        self.assertFalse(result["ready_to_pull"])
        self.assertFalse(result["ready_for_decisions"])
        self.assertEqual(result["decision_state"], "BLOCKED")
        self.assertFalse(result["runtime"]["coverage_attestation_bound"])
        self.assertFalse(result["runtime"]["full_28_day_coverage"])
        self.assertIn("COVERAGE_ATTESTATION_NOT_BOUND", codes)
        self.assertIn("RUNTIME_TRUST_NOT_TRUSTED", codes)

    def test_naive_evaluation_time_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaisesRegex(ValueError, "timezone-aware"):
                report.build_report(Path(tmp), now=dt.datetime(2026, 8, 24, 15))


if __name__ == "__main__":
    unittest.main(verbosity=2)
