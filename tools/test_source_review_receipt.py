#!/usr/bin/env python3
"""Adversarial tests for the verifier-only source-review receipt contract."""

from copy import deepcopy
from datetime import datetime, timedelta, timezone
import base64
import hashlib
import json
import os
from pathlib import Path
import stat
import tempfile
from types import SimpleNamespace
import unittest
from unittest import mock

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

import source_review_receipt as receipt


class SourceReviewReceiptTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.repo = Path(self.temporary.name)
        self.now = datetime(2026, 8, 25, 12, 0, tzinfo=timezone.utc)
        self.private_key = Ed25519PrivateKey.generate()
        self.public_key_raw = self.private_key.public_key().public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw,
        )
        self.environ = {
            receipt.PUBLIC_KEY_ENV: base64.b64encode(self.public_key_raw).decode("ascii")
        }
        self.content_id = "kn-1"
        self.registry_hash = "a" * 64
        self.source_ids = ["source-a"]
        digest = hashlib.sha256(b"source-a").hexdigest()
        self.rows = [{
            "id": "source-a",
            "url": "https://official.example/a",
            "final_url": "https://official.example/a",
            "kind": "html",
            "http_status": 200,
            "content_type": "text/html",
            "bytes": 100,
            "fingerprint_method": "visible-text-v1",
            "raw_sha256": digest,
            "sha256": digest,
            "checked_at": self.now.isoformat(),
            "change": "unchanged",
        }]

    def _unsigned(self, **updates):
        source_hash = receipt.source_state_sha256(self.rows, self.source_ids)
        value = {
            "schema_version": 1,
            "receipt_kind": "OWNER_CONTENT_SOURCE_REVIEW",
            "content_id": self.content_id,
            "verdict": "UNCHANGED",
            "reviewed_at": (self.now - timedelta(minutes=1)).isoformat(),
            "registry_binding_sha256": self.registry_hash,
            "source_ids": list(self.source_ids),
            "source_state_sha256": source_hash,
            "nonce": "A" * 32,
            "owner_key_sha256": hashlib.sha256(self.public_key_raw).hexdigest(),
            "signature_algorithm": "ed25519",
        }
        value.update(updates)
        return value

    def _signed(self, private_key=None, **updates):
        value = self._unsigned(**updates)
        signing_key = private_key or self.private_key
        value["signature_b64"] = base64.b64encode(
            signing_key.sign(receipt.canonical_signed_payload(value))
        ).decode("ascii")
        return value

    def _path(self):
        source_hash = receipt.source_state_sha256(self.rows, self.source_ids)
        return receipt.expected_receipt_path(
            self.repo, self.content_id, self.registry_hash, source_hash
        )

    def _write_json(self, value):
        path = self._path()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(
                value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
            ),
            encoding="utf-8",
        )
        return path

    def _verify(self, **overrides):
        arguments = {
            "repo": self.repo,
            "content_id": self.content_id,
            "registry_binding_sha256": self.registry_hash,
            "source_ids": self.source_ids,
            "source_rows": self.rows,
            "now": self.now,
            "environ": self.environ,
        }
        arguments.update(overrides)
        return receipt.verify_content_source_review_receipt(**arguments)

    def test_valid_exact_receipt_is_accepted(self):
        self._write_json(self._signed())
        result = self._verify()
        self.assertTrue(result.accepted)
        self.assertTrue(result.found)
        self.assertEqual(result.receipt_id, "A" * 32)
        self.assertRegex(result.receipt_sha256 or "", r"^[0-9a-f]{64}$")

    def test_missing_receipt_fails_closed_without_claiming_it_was_found(self):
        result = self._verify()
        self.assertFalse(result.accepted)
        self.assertFalse(result.found)
        self.assertIn("missing", result.failures[0])

    def test_stable_hash_excludes_fetch_time_and_transient_change(self):
        changed = deepcopy(self.rows)
        changed[0]["checked_at"] = (self.now + timedelta(hours=1)).isoformat()
        changed[0]["change"] = "changed"
        self.assertEqual(
            receipt.source_state_sha256(self.rows, self.source_ids),
            receipt.source_state_sha256(changed, self.source_ids),
        )

    def test_stable_hash_binds_visible_and_raw_fingerprints(self):
        changed = deepcopy(self.rows)
        changed[0]["raw_sha256"] = "b" * 64
        changed[0]["sha256"] = "b" * 64
        self.assertNotEqual(
            receipt.source_state_sha256(self.rows, self.source_ids),
            receipt.source_state_sha256(changed, self.source_ids),
        )

    def test_source_ids_must_match_exactly(self):
        self._write_json(self._signed(source_ids=["source-b"]))
        result = self._verify()
        self.assertFalse(result.accepted)
        self.assertTrue(result.found)
        self.assertIn("exactly match", result.failures[0])

    def test_duplicate_source_ids_are_rejected(self):
        self._write_json(self._signed(source_ids=["source-a", "source-a"]))
        result = self._verify()
        self.assertFalse(result.accepted)
        self.assertIn("duplicates", result.failures[0])

    def test_extra_receipt_field_is_rejected(self):
        value = self._signed()
        value["unexpected"] = "local-authority-escalation"
        self._write_json(value)
        result = self._verify()
        self.assertFalse(result.accepted)
        self.assertIn("fields are not exact", result.failures[0])

    def test_boolean_schema_version_is_not_integer_one(self):
        self._write_json(self._signed(schema_version=True))
        result = self._verify()
        self.assertFalse(result.accepted)
        self.assertIn("schema_version", result.failures[0])

    def test_duplicate_json_key_is_rejected_before_signature(self):
        path = self._path()
        path.parent.mkdir(parents=True, exist_ok=True)
        raw = json.dumps(self._signed(), separators=(",", ":"))
        path.write_text('{"schema_version":1,' + raw[1:], encoding="utf-8")
        result = self._verify()
        self.assertFalse(result.accepted)
        self.assertIn("invalid JSON", result.failures[0])

    def test_nonfinite_json_is_rejected(self):
        path = self._path()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text('{"probe":NaN}', encoding="utf-8")
        result = self._verify()
        self.assertFalse(result.accepted)
        self.assertIn("invalid JSON", result.failures[0])

    def test_missing_public_key_blocks_an_existing_receipt(self):
        self._write_json(self._signed())
        result = self._verify(environ={})
        self.assertFalse(result.accepted)
        self.assertTrue(result.found)
        self.assertIn("public key", result.failures[0])

    def test_noncanonical_base64_is_rejected(self):
        value = self._signed()
        encoded = value["signature_b64"]
        alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/"
        last_index = alphabet.index(encoded[-3])
        alternate_index = (last_index & 0x30) | ((last_index + 1) & 0x0F)
        if alternate_index == last_index:
            alternate_index = (last_index & 0x30) | ((last_index - 1) & 0x0F)
        value["signature_b64"] = encoded[:-3] + alphabet[alternate_index] + encoded[-2:]
        self._write_json(value)
        result = self._verify()
        self.assertFalse(result.accepted)
        self.assertIn("canonical base64", result.failures[0])

    def test_oversized_receipt_is_rejected_before_json_parsing(self):
        path = self._path()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b" " * (receipt.MAX_RECEIPT_BYTES + 1))
        result = self._verify()
        self.assertFalse(result.accepted)
        self.assertTrue(result.found)
        self.assertIn("maximum size", result.failures[0])

    def test_wrong_owner_key_cannot_verify_a_resigned_payload(self):
        wrong_private = Ed25519PrivateKey.generate()
        wrong_public = wrong_private.public_key().public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw,
        )
        value = self._unsigned(
            owner_key_sha256=hashlib.sha256(wrong_public).hexdigest()
        )
        value["signature_b64"] = base64.b64encode(
            self.private_key.sign(receipt.canonical_signed_payload(value))
        ).decode("ascii")
        self._write_json(value)
        result = self._verify(environ={
            receipt.PUBLIC_KEY_ENV: base64.b64encode(wrong_public).decode("ascii")
        })
        self.assertFalse(result.accepted)
        self.assertIn("signature is invalid", result.failures[0])

    def test_future_review_timestamp_is_rejected(self):
        value = self._signed(
            reviewed_at=(self.now + timedelta(seconds=1)).isoformat()
        )
        self._write_json(value)
        result = self._verify()
        self.assertFalse(result.accepted)
        self.assertIn("future", result.failures[0])

    def test_non_accepting_signed_verdict_stays_blocked(self):
        self._write_json(self._signed(verdict="BLOCK"))
        result = self._verify()
        self.assertFalse(result.accepted)
        self.assertIn("requires owner update", result.failures[0])

    def test_registry_binding_mismatch_is_rejected(self):
        self._write_json(self._signed(registry_binding_sha256="b" * 64))
        result = self._verify()
        self.assertFalse(result.accepted)
        self.assertIn("registry binding", result.failures[0])

    def test_source_state_mismatch_is_rejected(self):
        self._write_json(self._signed(source_state_sha256="b" * 64))
        result = self._verify()
        self.assertFalse(result.accepted)
        self.assertIn("source state", result.failures[0])

    def test_symlink_receipt_is_rejected(self):
        path = self._path()
        path.parent.mkdir(parents=True, exist_ok=True)
        target = self.repo / "attacker-controlled.json"
        target.write_text(json.dumps(self._signed()), encoding="utf-8")
        try:
            os.symlink(target, path)
        except (OSError, NotImplementedError):
            self.skipTest("symlink creation is unavailable on this host")
        result = self._verify()
        self.assertFalse(result.accepted)
        self.assertTrue(result.found)
        self.assertIn("symlink", result.failures[0])

    def test_windows_reparse_component_is_treated_as_a_symlink(self):
        path = self._path()
        path.parent.mkdir(parents=True, exist_ok=True)
        real_lstat = Path.lstat
        reparse_component = path.parent

        def fake_lstat(candidate):
            if candidate == reparse_component:
                return SimpleNamespace(
                    st_mode=stat.S_IFDIR,
                    st_file_attributes=getattr(
                        stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400
                    ),
                )
            return real_lstat(candidate)

        with mock.patch.object(Path, "lstat", new=fake_lstat):
            with self.assertRaisesRegex(receipt.ReceiptBlocked, "symlinks"):
                receipt._existing_components_have_no_symlink(self.repo, path)

    def test_second_read_detects_toctou_replacement(self):
        path = self._write_json(self._signed())
        raw = path.read_bytes()
        stable_stamp = (1, 2, len(raw), 3)
        with mock.patch.object(
            receipt,
            "_read_stable_regular_file",
            side_effect=[(raw, stable_stamp), (raw + b" ", stable_stamp)],
        ):
            result = self._verify()
        self.assertFalse(result.accepted)
        self.assertIn("changed during verification", result.failures[0])


if __name__ == "__main__":
    unittest.main(verbosity=2)
