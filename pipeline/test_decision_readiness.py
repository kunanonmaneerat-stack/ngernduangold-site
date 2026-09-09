#!/usr/bin/env python3
import datetime as dt
from types import SimpleNamespace
import unittest
from unittest import mock

try:
    import decision_readiness as readiness
except ImportError:  # package import path
    from pipeline import decision_readiness as readiness

NOW = dt.datetime(2026, 8, 16, 4, tzinfo=dt.timezone.utc)


def observation(
    ga4_state="CURRENT",
    ga4_ready=True,
    gsc_state="CURRENT",
    gsc_ready=True,
    revenue_state="CURRENT",
    revenue_ready=True,
):
    return {
        "observed_at": NOW.isoformat(),
        "sources": {
            "ga4": {"bundle": {
                "decisionable": ga4_ready, "state": ga4_state,
                "capture_trust": "TRUSTED" if ga4_ready else "UNTRUSTED",
                "current_trust": "TRUSTED" if ga4_ready else "UNTRUSTED",
                "expires_at": (NOW + dt.timedelta(hours=1)).isoformat(),
            }},
            "gsc": {"bundle": {
                "decisionable": gsc_ready, "state": gsc_state,
                "expires_at": (NOW + dt.timedelta(hours=1)).isoformat(),
            }},
            "revenue_ledger": {
                "trusted": revenue_ready,
                "learning_ready": revenue_ready,
                "quality_state": revenue_state,
                "reconcile_required": not revenue_ready,
            },
        },
        "learning_readiness": {"sources": {"revenue": {
            "ready": revenue_ready,
            "state": revenue_state,
        }}},
        "metrics": {"verified_affiliate_revenue": {
            "trust_expires_at": (NOW + dt.timedelta(hours=1)).isoformat(),
        }},
    }


class DecisionReadinessTests(unittest.TestCase):
    def test_current_bundles_are_decisionable(self):
        with mock.patch.object(readiness.observation_snapshot, "collect",
                               return_value=observation()):
            result = readiness.read()
        self.assertTrue(result.ga4.trusted)
        self.assertTrue(result.gsc.trusted)
        self.assertTrue(result.revenue.trusted)

    def test_capture_or_coverage_failure_is_not_decisionable(self):
        with mock.patch.object(
            readiness.observation_snapshot, "collect",
            return_value=observation("UNTRUSTED_AT_CAPTURE", False, "TRUNCATED", False),
        ):
            result = readiness.read()
        self.assertFalse(result.ga4.trusted)
        self.assertFalse(result.gsc.trusted)
        self.assertTrue(result.revenue.trusted)
        self.assertIn("UNTRUSTED_AT_CAPTURE", result.ga4.reason)
        self.assertIn("TRUNCATED", result.gsc.reason)

    def test_observation_failure_is_fail_closed(self):
        with mock.patch.object(readiness.observation_snapshot, "collect",
                               side_effect=ValueError("bad")):
            result = readiness.read()
        self.assertFalse(result.ga4.trusted)
        self.assertFalse(result.gsc.trusted)
        self.assertFalse(result.revenue.trusted)
        self.assertEqual(result.ga4.state, "UNAVAILABLE")

    def test_truthy_non_boolean_and_missing_expiry_never_fail_open(self):
        malformed = observation()
        malformed["sources"]["ga4"]["bundle"]["decisionable"] = "true"
        malformed["sources"]["gsc"]["bundle"].pop("expires_at")
        with mock.patch.object(
            readiness.observation_snapshot, "collect", return_value=malformed
        ):
            result = readiness.read()
        self.assertFalse(result.ga4.trusted)
        self.assertFalse(result.gsc.trusted)
        self.assertEqual(result.gsc.state, "INVALID_EXPIRY")

    def test_revenue_missing_or_expired_boundary_never_fails_open(self):
        missing = observation()
        missing["metrics"]["verified_affiliate_revenue"].pop(
            "trust_expires_at"
        )
        with mock.patch.object(
            readiness.observation_snapshot, "collect", return_value=missing
        ):
            result = readiness.read(now=NOW)
        self.assertFalse(result.revenue.trusted)
        self.assertEqual(result.revenue.state, "INVALID_EXPIRY")
        self.assertIsNone(result.revenue.expires_at)

        boundary = observation()
        boundary["metrics"]["verified_affiliate_revenue"][
            "trust_expires_at"
        ] = NOW.isoformat()
        with mock.patch.object(
            readiness.observation_snapshot, "collect", return_value=boundary
        ):
            result = readiness.read(now=NOW)
        self.assertFalse(result.revenue.trusted)
        self.assertEqual(result.revenue.state, "INVALID_EXPIRY")


if __name__ == "__main__":
    unittest.main(verbosity=2)
