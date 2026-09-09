#!/usr/bin/env python3
"""No-network regressions for Instagram hosted-media publication boundaries."""

from __future__ import annotations

import base64
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import unittest
import urllib.request
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
PUBLISHER = ROOT / "automation" / "ig_publish.py"


def load_publisher():
    spec = importlib.util.spec_from_file_location(
        "instagram_publisher_safety_fixture", PUBLISHER
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class FakeResponse:
    def __init__(self, body, url, *, status=200, headers=None):
        self._body = io.BytesIO(body)
        self._url = url
        self.status = status
        self.headers = headers or {}

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self, size=-1):
        return self._body.read(size)

    def geturl(self):
        return self._url


class FakeOpener:
    def __init__(self, response):
        self.response = response
        self.calls = []

    def open(self, request, timeout=None):
        self.calls.append((request, timeout))
        return self.response


class InstagramPublisherSafetyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.publisher = load_publisher()

    def test_only_exact_canonical_https_origin_and_safe_mp4_are_allowed(self):
        expected = "https://ngernduangold.com/reels/clip-01.mp4"
        self.assertEqual(
                    self.publisher._canonical_video_url(
                "clip-01.mp4", "https://ngernduangold.com"
            ),
            expected,
        )
        self.assertEqual(
            self.publisher._canonical_video_url(
                "clip-01.mp4", "https://NGERNDUANGOLD.COM/"
            ),
            expected,
        )
        invalid_bases = (
            "http://ngernduangold.com",
            "https://www.ngernduangold.com",
            "https://ngernduangold.com:443",
            "https://user@ngernduangold.com",
            "https://ngernduangold.com/media",
            "https://ngernduangold.com?next=https://evil.example",
            "https://ngernduangold.com#fragment",
            "https://evil.example",
        )
        for value in invalid_bases:
            with self.subTest(base=value), self.assertRaisesRegex(
                self.publisher.PublicationBlocked, "canonical HTTPS"
            ):
                self.publisher._canonical_video_url("clip-01.mp4", value)
        for value in ("../clip.mp4", "folder/clip.mp4", "clip.mov", "", "clip.mp4?x=1"):
            with self.subTest(file=value), self.assertRaisesRegex(
                self.publisher.PublicationBlocked, "safe MP4"
            ):
                self.publisher._canonical_video_url(
                    value, "https://ngernduangold.com"
                )

    def test_redirect_handler_never_creates_a_followup_request(self):
        handler = self.publisher._NoRedirectHandler()
        request = urllib.request.Request("https://ngernduangold.com/reels/clip.mp4")
        self.assertIsNone(
            handler.redirect_request(
                request, None, 302, "Found", {},
                "https://cdn.example/clip.mp4",
            )
        )

    def hosted_fixture(self, body, *, remote_body=None, final_url=None, headers=None):
        temp = tempfile.TemporaryDirectory(prefix="ig_hosted_media_")
        asset = Path(temp.name) / "clip.mp4"
        asset.write_bytes(body)
        expected_hash = hashlib.sha256(body).hexdigest()
        contract = {
            "schema_version": 1,
            "kind": self.publisher.IMMUTABLE_REMOTE_KIND,
            "sha256": expected_hash,
            "url": "https://ngernduangold.com/reels/sha256/%s.mp4" % expected_hash,
        }
        url = contract["url"]
        request = urllib.request.Request(url, method="GET")
        response_headers = {
            "Content-Type": "video/mp4",
            "Content-Length": str(len(body)),
            "Content-Encoding": "identity",
            "Cache-Control": "public, max-age=31536000, immutable",
            "Content-Digest": "sha-256=:%s:" % base64.b64encode(
                bytes.fromhex(expected_hash)
            ).decode("ascii"),
        }
        if headers:
            response_headers.update(headers)
        opener = FakeOpener(FakeResponse(
            body if remote_body is None else remote_body,
            url if final_url is None else final_url,
            headers=response_headers,
        ))
        return temp, asset, request, opener, expected_hash, contract

    def test_gets_bounded_exact_bytes_without_redirect_and_returns_evidence_hash(self):
        body = (b"local-video-bytes" * 257) + b"end"
        temp, asset, request, opener, expected_hash, contract = self.hosted_fixture(body)
        with temp:
            evidence = self.publisher._verify_hosted_video(
                request, asset, expected_hash, contract, opener=opener
            )
        self.assertEqual(len(opener.calls), 1)
        sent_request, timeout = opener.calls[0]
        self.assertEqual(sent_request.get_method(), "GET")
        self.assertEqual(timeout, 30)
        self.assertFalse(evidence["redirects_allowed"])
        self.assertEqual(evidence["byte_length"], len(body))
        self.assertEqual(evidence["local_sha256"], expected_hash)
        self.assertEqual(evidence["remote_sha256"], expected_hash)
        self.assertEqual(evidence["remote_asset_contract"], contract)
        claimed_hash = evidence.pop("evidence_sha256")
        self.assertEqual(
            claimed_hash,
            hashlib.sha256(
                json.dumps(evidence, ensure_ascii=False, sort_keys=True,
                           separators=(",", ":")).encode("utf-8")
            ).hexdigest(),
        )

    def test_redirect_byte_drift_and_oversize_are_fail_closed(self):
        body = b"exact-video"
        cases = (
            {
                "label": "redirect",
                "remote": body,
                "url": "https://cdn.example/clip.mp4",
                "headers": {},
                "reason": "direct canonical",
            },
            {
                "label": "same-size drift",
                "remote": b"other-video",
                "url": None,
                "headers": {},
                "reason": "exactly match",
            },
            {
                "label": "extra byte",
                "remote": body + b"x",
                "url": None,
                "headers": {"Content-Length": ""},
                "reason": "bounded byte length",
            },
        )
        for case in cases:
            with self.subTest(case["label"]):
                temp, asset, request, opener, expected_hash, contract = self.hosted_fixture(
                    body,
                    remote_body=case["remote"],
                    final_url=case["url"],
                    headers=case["headers"],
                )
                with temp, self.assertRaisesRegex(
                    self.publisher.PublicationBlocked, case["reason"]
                ):
                    self.publisher._verify_hosted_video(
                        request, asset, expected_hash, contract, opener=opener
                    )

    def test_local_change_after_media_guard_is_blocked_before_get(self):
        body = b"first"
        temp, asset, request, opener, expected_hash, contract = self.hosted_fixture(body)
        with temp:
            asset.write_bytes(b"second")
            with self.assertRaisesRegex(
                self.publisher.PublicationBlocked, "changed after"
            ):
                self.publisher._verify_hosted_video(
                    request, asset, expected_hash, contract, opener=opener
                )
        self.assertEqual(opener.calls, [])

    def test_mutable_or_unbound_remote_asset_contract_is_fail_closed(self):
        body = b"exact-video"
        expected_hash = hashlib.sha256(body).hexdigest()
        valid = {
            "schema_version": 1,
            "kind": self.publisher.IMMUTABLE_REMOTE_KIND,
            "sha256": expected_hash,
            "url": "https://ngernduangold.com/reels/sha256/%s.mp4" % expected_hash,
        }
        self.assertEqual(
            self.publisher._immutable_remote_asset_contract(
                {"remote_asset": valid}, expected_hash
            ),
            valid,
        )
        for contract in (
            None,
            {**valid, "kind": "mutable-url"},
            {**valid, "sha256": "0" * 64},
            {**valid, "url": "https://ngernduangold.com/reels/clip.mp4"},
            {**valid, "url": "https://evil.example/reels/sha256/%s.mp4" % expected_hash},
        ):
            with self.subTest(contract=contract), self.assertRaises(
                self.publisher.PublicationBlocked
            ):
                self.publisher._immutable_remote_asset_contract(
                    {"remote_asset": contract} if contract is not None else {},
                    expected_hash,
                )

        temp, asset, request, opener, expected_hash, contract = self.hosted_fixture(
            body, headers={"Cache-Control": "public, max-age=60"}
        )
        with temp, self.assertRaisesRegex(
            self.publisher.PublicationBlocked, "immutable cache contract"
        ):
            self.publisher._verify_hosted_video(
                request, asset, expected_hash, contract, opener=opener
            )

    def test_hosted_evidence_is_durable_and_bound_to_pending_action(self):
        with tempfile.TemporaryDirectory(prefix="ig_attempt_evidence_") as temp:
            self.publisher.ATTEMPT_ROOT = Path(temp) / "attempts"
            action = {"placement_id": "content-1__instagram", "nonce": "fixture"}
            evidence = {
                "evidence_sha256": "a" * 64,
                "remote_sha256": "b" * 64,
                "byte_length": 123,
            }
            self.publisher._begin_attempt(action)
            self.publisher._record_hosted_media_evidence(action, evidence)
            path = self.publisher._attempt_evidence_path(action["placement_id"])
            stored = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(stored["status"], "REMOTE_MEDIA_VERIFIED")
            self.assertEqual(stored["hosted_media"], evidence)
            self.assertEqual(
                stored["action_sha256"],
                hashlib.sha256(
                    json.dumps(action, ensure_ascii=False, sort_keys=True,
                               separators=(",", ":")).encode("utf-8")
                ).hexdigest(),
            )

    def test_source_order_revalidates_at_both_instagram_mutations(self):
        source = PUBLISHER.read_text(encoding="utf-8")
        start = source.index("def main():")
        body = source[start:]
        begin = body.index("_begin_attempt(action)")
        hosted = body.index("hosted_evidence = _verify_hosted_video(")
        evidence = body.index("_record_hosted_media_evidence(", hosted)
        claim = body.index("post_ledger.claim(", evidence)
        create = body.index('result = api("/%s/media"')
        publish = body.index('"/%s/media_publish"', create)
        first_corpus_claim = body.index(
            "with media_publish_guard.publication_corpus_claim(", claim
        )
        second_corpus_claim = body.index(
            "with media_publish_guard.publication_corpus_claim(", create
        )
        first_verify = body.index("verify_execution_authorization(", evidence)
        second_verify = body.index("verify_execution_authorization(", create)
        self.assertLess(begin, hosted)
        self.assertLess(hosted, evidence)
        self.assertLess(evidence, claim)
        self.assertLess(claim, first_corpus_claim)
        self.assertLess(first_corpus_claim, first_verify)
        self.assertLess(first_verify, create)
        self.assertLess(create, second_corpus_claim)
        self.assertLess(second_corpus_claim, second_verify)
        self.assertLess(second_verify, publish)
        self.assertEqual(
            body.count("with media_publish_guard.publication_corpus_claim("), 2
        )
        self.assertIn('method="GET"', body[begin:create])
        self.assertNotIn('method="HEAD"', body)
        finish = body.index("_finish_attempt(", publish)
        confirm = body.index("post_ledger.confirm(", finish)
        registry = body.index("_atomic_json_write(PUBLISHED", confirm)
        self.assertLess(finish, confirm)
        self.assertLess(confirm, registry)

    def test_atomic_claim_failure_blocks_before_container_mutation(self):
        date = "2026-08-25"
        with tempfile.TemporaryDirectory(prefix="ig-claim-boundary-") as raw:
            repo = Path(raw)
            asset = repo / "reels" / "clip.mp4"
            asset.parent.mkdir(parents=True)
            asset.write_bytes(b"instagram-fixture-video")
            digest = hashlib.sha256(asset.read_bytes()).hexdigest()
            contract = {
                "schema_version": 1,
                "kind": self.publisher.IMMUTABLE_REMOTE_KIND,
                "sha256": digest,
                "url": "https://ngernduangold.com/reels/sha256/%s.mp4" % digest,
            }
            entry = {
                "file": asset.name,
                "caption": "เนื้อหาทดสอบ ข้อมูลเพื่อการศึกษา · ผลิตด้วย AI",
                "content_id": "content-ig-1",
                "placement_id": "content-ig-1__instagram",
                "scheduled_slot": "2026-08-25T20:00:00+07:00",
                "qa_report": "receipt.json",
                "remote_asset": contract,
                "approval": {},
            }
            schedule = repo / "schedule.json"
            schedule.write_text(
                json.dumps({date: entry}, ensure_ascii=False), encoding="utf-8"
            )
            action = {
                "content_id": entry["content_id"],
                "placement_id": entry["placement_id"],
                "channel": "instagram",
                "target_identity": "17890000000000000",
                "caption_sha256": "a" * 64,
                "asset_sha256": digest,
                "scheduled_slot": entry["scheduled_slot"],
                "consumed": True,
            }
            api = mock.Mock(side_effect=AssertionError("container API crossed claim gate"))
            with (
                mock.patch.dict(self.publisher.os.environ, {"OVERRIDE_DATE": date}),
                mock.patch.object(self.publisher, "ROOT", str(repo)),
                mock.patch.object(self.publisher, "SCHEDULE", str(schedule)),
                mock.patch.object(self.publisher, "LOG_DIR", str(repo / "logs")),
                mock.patch.object(self.publisher, "PUBLISHED", str(repo / "published.json")),
                mock.patch.object(self.publisher, "ALERT", str(repo / "alert.md")),
                mock.patch.object(self.publisher, "DRY_RUN", False),
                mock.patch.object(self.publisher, "TOKEN", "fixture-token"),
                mock.patch.object(self.publisher, "IG_USER", action["target_identity"]),
                mock.patch.object(
                    self.publisher.media_publish_guard, "evaluate",
                    return_value={"verdict": "PASS", "findings": [], "sha256": digest},
                ),
                mock.patch.object(self.publisher, "_assert_reconciliation_clear"),
                mock.patch.object(
                    self.publisher, "authorize_live_publication", return_value=action
                ),
                mock.patch.object(self.publisher, "_begin_attempt"),
                mock.patch.object(
                    self.publisher, "_verify_hosted_video",
                    return_value={
                        "evidence_sha256": "b" * 64,
                        "remote_sha256": digest,
                        "byte_length": asset.stat().st_size,
                    },
                ),
                mock.patch.object(self.publisher, "_record_hosted_media_evidence"),
                mock.patch.object(
                    self.publisher.post_ledger, "claim",
                    return_value=(False, "", "GAP: fixture"),
                ),
                mock.patch.object(self.publisher, "_finish_attempt"),
                mock.patch.object(self.publisher, "api", api),
            ):
                with self.assertRaises(SystemExit):
                    self.publisher.main()
            api.assert_not_called()


if __name__ == "__main__":
    unittest.main(verbosity=2)
