#!/usr/bin/env python3

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from tools import live_domain_observation as observer


class LiveDomainObservationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.repo = Path(self.temp.name)
        for relative, raw in (
            ("site/index.html", b"root"),
            ("site/sitemap.xml", b"<loc>x</loc><lastmod>2026-08-25</lastmod>"),
            ("site/release-manifest.json", b"manifest"),
            ("release/candidate-receipt.json", b"receipt"),
            ("tools/live_domain_observation.py", b"producer"),
        ):
            path = self.repo / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(raw)
        policy = self.repo / ".system_control/policy.json"
        policy.parent.mkdir(parents=True, exist_ok=True)
        policy.write_text(
            json.dumps(
                {
                    "release_attestation": {
                        "live_domain_observation": {
                            "schema_version": 1,
                            "max_age_hours": 6,
                            "max_capture_duration_seconds": 120,
                            "future_skew_seconds": 300,
                            "exclusive_expiry": True,
                        }
                    }
                }
            ),
            encoding="utf-8",
        )

    def tearDown(self):
        self.temp.cleanup()

    @staticmethod
    def response(url, raw, status=200):
        return ({
            "url": url,
            "http_status": status,
            "content_length": len(raw),
            "body_sha256": hashlib.sha256(raw).hexdigest().upper(),
            "etag": None,
            "request_id": None,
            "content_type": "application/octet-stream",
        }, raw)

    def metadata(self):
        return json.dumps({
            "id": "site-id",
            "name": "site",
            "custom_domain": "example.com",
            "published_deploy": {"id": "deploy-id", "state": "ready"},
            "build_settings": {},
        }).encode()

    def capture(self, manifest_status=200):
        answers = [
            self.response("https://example.com/", b"root"),
            self.response(
                "https://example.com/sitemap.xml",
                b"<loc>x</loc><lastmod>2026-08-25</lastmod>",
            ),
            self.response(
                "https://example.com/release-manifest.json",
                b"manifest" if manifest_status == 200 else b"missing",
                manifest_status,
            ),
            self.response("https://alias.example/", b"root"),
            self.response("https://api.netlify.com/api/v1/sites/site", self.metadata()),
        ]
        with mock.patch.object(observer, "_http_get", side_effect=answers), mock.patch.object(
            observer, "_client_addresses", return_value=["203.0.113.10"]
        ), mock.patch.object(
            observer, "_authoritative_addresses", return_value=["203.0.113.10"]
        ):
            return observer.build_observation(
                self.repo,
                domain="example.com",
                alias_domain="alias.example",
                netlify_site="site",
                authoritative_server="dns.example",
                authoritative_server_ip="203.0.113.53",
                timeout=1,
                now=datetime(2026, 8, 25, tzinfo=timezone.utc),
            )

    def validate(self, value, *, as_of=None):
        return observer.validate_observation(
            self.repo,
            value,
            as_of=value.get("observed_at") if as_of is None else as_of,
        )

    @staticmethod
    def reseal(value):
        value["observation_payload_sha256"] = observer._canonical_hash(
            {k: v for k, v in value.items() if k != "observation_payload_sha256"}
        )

    def test_exact_hash_parity_passes(self):
        value = self.capture()
        self.assertEqual(value["conclusion"]["live_local_release_parity"], "PASS")
        self.assertEqual(value["conclusion"]["release_attestation_state"], "PASS")
        self.assertEqual(self.validate(value), [])

    def test_missing_live_manifest_fails_closed(self):
        value = self.capture(manifest_status=404)
        self.assertEqual(value["conclusion"]["live_local_release_parity"], "FAILED")
        self.assertIn(
            "the branded release-manifest endpoint returns 404",
            value["conclusion"]["reasons"],
        )

    def test_tampered_payload_hash_is_rejected(self):
        value = self.capture()
        value["conclusion"]["live_local_release_parity"] = "FAILED"
        self.assertIn("observation payload hash mismatch", self.validate(value))

    def test_stale_producer_binding_is_rejected(self):
        value = self.capture()
        (self.repo / "tools/live_domain_observation.py").write_bytes(b"changed")
        self.assertIn(
            "observation producer binding is invalid or stale",
            self.validate(value),
        )

    def test_changed_local_binding_is_rejected(self):
        value = self.capture()
        (self.repo / "site/index.html").write_bytes(b"changed")
        self.assertIn(
            "local binding changed: site/index.html",
            self.validate(value),
        )

    def test_expiry_is_exclusive(self):
        value = self.capture()
        expires = datetime.fromisoformat(value["expires_at"])
        self.assertEqual(self.validate(value, as_of=expires - timedelta(microseconds=1)), [])
        self.assertIn(
            "observation is stale at the decision time",
            self.validate(value, as_of=expires),
        )

    def test_future_observation_is_not_yet_valid(self):
        value = self.capture()
        observed = datetime.fromisoformat(value["observed_at"])
        self.assertIn(
            "observation is not yet valid",
            self.validate(value, as_of=observed - timedelta(seconds=1)),
        )
        errors = self.validate(value, as_of=observed - timedelta(seconds=301))
        self.assertIn("observation time exceeds allowed future skew", errors)

    def test_naive_payload_times_are_rejected_even_when_resealed(self):
        value = self.capture()
        value["observed_at"] = "2026-08-25T00:00:00"
        self.reseal(value)
        self.assertIn("observed_at must be timezone-aware", self.validate(value))

    def test_altered_expiry_is_rejected_even_when_resealed(self):
        value = self.capture()
        value["expires_at"] = "2026-08-26T00:00:00+00:00"
        self.reseal(value)
        self.assertIn(
            "observation expiry does not match policy",
            self.validate(value),
        )

    def test_policy_drift_invalidates_observation(self):
        value = self.capture()
        policy_path = self.repo / ".system_control/policy.json"
        document = json.loads(policy_path.read_text(encoding="utf-8"))
        document["release_attestation"]["live_domain_observation"]["max_age_hours"] = 7
        policy_path.write_text(json.dumps(document), encoding="utf-8")
        self.assertIn(
            "observation validity contract is invalid or stale",
            self.validate(value),
        )

    def test_capture_duration_over_policy_is_rejected_when_resealed(self):
        value = self.capture()
        observed = datetime.fromisoformat(value["observed_at"])
        value["observation_window"]["start"] = (
            observed - timedelta(seconds=121)
        ).isoformat(timespec="seconds")
        self.reseal(value)
        self.assertIn(
            "observation capture duration exceeds policy",
            self.validate(value),
        )

    def test_legacy_schema_is_blocked(self):
        value = self.capture()
        value["schema_version"] = 1
        self.reseal(value)
        self.assertIn("observation schema is unsupported", self.validate(value))

    def test_boundary_never_claims_mutation_or_authority(self):
        value = self.capture()
        self.assertEqual(
            value["boundary"],
            {
                "scope": "READ_ONLY_EXTERNAL_OBSERVATION_PLUS_LOCAL_FILE_BINDINGS",
                "repairs_dns": False,
                "deploys_site": False,
                "grants_publication_authority": False,
                "follows_affiliate_redirects": False,
            },
        )

    def test_naive_time_is_rejected(self):
        with self.assertRaises(observer.ObservationError):
            observer._aware("2026-08-25T07:00:00")


if __name__ == "__main__":
    unittest.main()
