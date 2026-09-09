#!/usr/bin/env python3
"""Regression tests for privacy_guard.py.

The fixtures use synthetic markers.  Tests verify both detection and the more
important output contract: no matched value is ever echoed to stdout.
"""

from __future__ import annotations

from contextlib import redirect_stdout
import io
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest


HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import privacy_guard as guard


class TemporaryGitRepo:
    def __init__(self) -> None:
        self._tmp = tempfile.mkdtemp(prefix="privacy_guard_")
        self.root = Path(self._tmp)
        subprocess.run(
            ["git", "init", "--quiet", str(self.root)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=True,
        )

    def write(self, relative: str, content: str, tracked: bool = True) -> Path:
        path = self.root.joinpath(*Path(relative).parts)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8", newline="\n")
        if tracked:
            subprocess.run(
                ["git", "-C", str(self.root), "add", "--", relative],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=True,
            )
        return path

    def close(self) -> None:
        shutil.rmtree(self._tmp, ignore_errors=True)


class PrivacyGuardTests(unittest.TestCase):
    def setUp(self) -> None:
        self.repo = TemporaryGitRepo()

    def tearDown(self) -> None:
        self.repo.close()

    def test_tracked_and_untracked_scope_detection_and_redaction(self) -> None:
        secret_marker = "synthetic-credential-marker-001"
        email_marker = "synthetic.person@example.invalid"
        phone_marker = "0812345678"
        ip_marker = "203.0.113.42"
        self.repo.write(
            ".system_control/policy.json",
            json.dumps({"access_token": secret_marker, "public_ip": ip_marker}),
        )
        self.repo.write(
            "automation-log/gumroad-sales.csv",
            "purchase_date,product,price_thb,buyer_email,source\n"
            "2026-01-01,fixture,1,%s,test\n" % email_marker,
        )
        self.repo.write(
            "automation-log/knowledge-base/FACTS_current.md",
            "Contact %s or %s\n" % (phone_marker, email_marker),
        )
        self.repo.write(
            ".system_control/untracked.json",
            json.dumps({"access_token": "untracked-marker-should-not-be-seen"}),
            tracked=False,
        )
        self.repo.write(
            "docs/tracked-but-out-of-scope.json",
            json.dumps({"access_token": "out-of-scope-marker-should-not-be-seen"}),
        )

        findings, scanned, operational_error = guard.scan_repository(self.repo.root)
        rendered = guard.render_findings(findings)

        self.assertFalse(operational_error)
        self.assertEqual(scanned, 4)
        self.assertIn("CREDENTIAL_FIELD", rendered)
        self.assertIn("NETWORK_FIELD", rendered)
        self.assertIn("NETWORK_ADDRESS", rendered)
        self.assertIn("EMAIL_ADDRESS", rendered)
        self.assertIn("PHONE_NUMBER", rendered)
        self.assertIn("SALES_RECORD", rendered)
        for marker in (secret_marker, email_marker, phone_marker, ip_marker, "untracked-marker", "out-of-scope-marker"):
            self.assertNotIn(marker, rendered)
        self.assertIn("untracked.json", rendered)
        self.assertNotIn("tracked-but-out-of-scope.json", rendered)

    def test_clean_tracked_files_pass(self) -> None:
        self.repo.write(".system_control/policy.json", '{"state":"active"}\n')
        self.repo.write("automation-log/weekly.log", "routine completed without private data\n")
        findings, scanned, operational_error = guard.scan_repository(self.repo.root)
        self.assertEqual(findings, [])
        self.assertEqual(scanned, 2)
        self.assertFalse(operational_error)

    def test_formatted_thai_phone_variants_and_boundaries(self) -> None:
        variants = (
            "081-234-5678",
            "081 234 5678",
            "081.234.5678",
            "+66 81 234 5678",
            "66-81-234-5678",
            "02-123-4567",
        )
        for value in variants:
            with self.subTest(value=value):
                self.assertIn("PHONE_NUMBER", guard._line_categories("contact " + value))
        for clean in (
            "2026-08-17", "version 0.81.2", "sha256 08123456",
            "body::before{content:''}",
        ):
            with self.subTest(clean=clean):
                self.assertNotIn("PHONE_NUMBER", guard._line_categories(clean))
                if "::before" in clean:
                    self.assertNotIn("NETWORK_ADDRESS", guard._line_categories(clean))

    def test_public_source_and_ignored_generated_site_are_scanned(self) -> None:
        source_phone = "081-234-5678"
        built_phone = "+66 81 234 5678"
        self.repo.write(".gitignore", "site/\n")
        self.repo.write("build_site.py", "CONTACT = %r\n" % source_phone)
        self.repo.write(
            "site/nested/index.html",
            "<html><body>%s</body></html>\n" % built_phone,
            tracked=False,
        )

        findings, scanned, operational_error = guard.scan_repository(self.repo.root)
        rendered = guard.render_findings(findings)

        self.assertFalse(operational_error)
        self.assertEqual(scanned, 2)
        self.assertIn("build_site.py:1 [PHONE_NUMBER]", rendered)
        self.assertIn("site/nested/index.html:1 [PHONE_NUMBER]", rendered)
        self.assertNotIn(source_phone, rendered)
        self.assertNotIn(built_phone, rendered)

    def test_validated_digest_fields_do_not_create_phone_false_positives(self) -> None:
        digest_with_phone_digits = (
            "DC3B34D752AADEBB0D554A18043C426E"
            "F3C03DFE66373D665A310CB001810418"
        )
        fingerprint_with_phone_digits = (
            "2942BA18AA2DC016409560DF55B153F5"
            "5F24DEA2B031172FB9A3E1C69C6A0DFA"
        )
        self.repo.write(
            "automation-log/digest-receipt.json",
            json.dumps(
                {
                    "sha256": digest_with_phone_digits,
                    "corpus_fingerprint": fingerprint_with_phone_digits,
                },
                indent=2,
            ),
        )
        self.repo.write(
            "automation-log/digest-bindings.jsonl",
            json.dumps(
                {
                    "value_sha256": fingerprint_with_phone_digits,
                    "binding_sha256": digest_with_phone_digits,
                },
                separators=(",", ":"),
            ) + "\n",
        )

        findings, scanned, operational_error = guard.scan_repository(self.repo.root)

        self.assertEqual(findings, [])
        self.assertEqual(scanned, 2)
        self.assertFalse(operational_error)

    def test_nested_digest_container_masks_only_valid_leaf_values(self) -> None:
        digest_with_phone_digits = (
            "D459961C4F81BA0C091310793CC0BECBE"
            "11BADD636094E702BD8E049F2B78083"
        )
        second_digest = (
            "DC3B34D752AADEBB0D554A18043C426E"
            "F3C03DFE66373D665A310CB001810418"
        )
        phone_marker = "0812345678"
        relative = "automation-log/nested-digest-receipt.json"
        receipt = self.repo.write(
            relative,
            json.dumps(
                {
                    "scene_evidence_sha256": {
                        "scene-01.png": digest_with_phone_digits,
                        "nested": {
                            "scene-02.png": second_digest,
                            "invalid-leaf": phone_marker,
                        },
                    },
                    # Repeating the exact digest outside an explicit digest
                    # container must remain visible to the phone detector.
                    "unknown_container": {"copy": digest_with_phone_digits},
                    "note": "digest in prose: " + second_digest,
                },
                indent=2,
            ) + "\n",
        )
        lines = receipt.read_text(encoding="utf-8").splitlines()
        expected_lines = {
            index
            for index, line in enumerate(lines, 1)
            if any(token in line for token in ('"invalid-leaf"', '"copy"', '"note"'))
        }

        findings, scanned, operational_error = guard.scan_repository(self.repo.root)
        phone_lines = {
            finding.line
            for finding in findings
            if finding.path == relative and finding.category == "PHONE_NUMBER"
        }

        self.assertFalse(operational_error)
        self.assertEqual(scanned, 1)
        self.assertEqual(phone_lines, expected_lines)
        self.assertEqual(len(phone_lines), 3)

    def test_nested_digest_container_supports_array_leaves(self) -> None:
        digest_with_phone_digits = (
            "2942BA18AA2DC016409560DF55B153F5"
            "5F24DEA2B031172FB9A3E1C69C6A0DFA"
        )
        phone_marker = "0812345678"
        relative = "automation-log/nested-digest-array.jsonl"
        self.repo.write(
            relative,
            json.dumps(
                {
                    "evidence_fingerprint": [
                        digest_with_phone_digits,
                        {"valid": digest_with_phone_digits, "invalid": phone_marker},
                    ]
                },
                separators=(",", ":"),
            ) + "\n",
        )

        findings, scanned, operational_error = guard.scan_repository(self.repo.root)
        phone_findings = [
            finding
            for finding in findings
            if finding.path == relative and finding.category == "PHONE_NUMBER"
        ]

        self.assertFalse(operational_error)
        self.assertEqual(scanned, 1)
        self.assertEqual(phone_findings, [guard.Finding(relative, 1, "PHONE_NUMBER")])

    def test_digest_exclusion_is_field_aware_and_keeps_phone_detection(self) -> None:
        digest_with_phone_digits = (
            "DC3B34D752AADEBB0D554A18043C426E"
            "F3C03DFE66373D665A310CB001810418"
        )
        phone_marker = "0812345678"
        unknown_hex_value = (
            "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
            "AAAAAAAAAAA0812345678AAAAAAAAAAA"
        )
        self.repo.write(
            "automation-log/adversarial.json",
            json.dumps(
                {
                    "sha256": digest_with_phone_digits,
                    "note": "call " + phone_marker,
                    "opaque": unknown_hex_value,
                    # A digest-like key alone is insufficient: the value must
                    # have the algorithm's exact validated length and format.
                    "source_sha256": phone_marker,
                },
                indent=2,
            ) + "\n",
        )
        self.repo.write(
            "automation-log/knowledge-base/FACTS_digest.md",
            "sha256-looking prose still contains %s\n" % phone_marker,
        )

        findings, scanned, operational_error = guard.scan_repository(self.repo.root)
        phone_findings = [
            finding for finding in findings if finding.category == "PHONE_NUMBER"
        ]

        self.assertFalse(operational_error)
        self.assertEqual(scanned, 2)
        self.assertEqual(
            {(finding.path, finding.line) for finding in phone_findings},
            {
                ("automation-log/adversarial.json", 3),
                ("automation-log/adversarial.json", 4),
                ("automation-log/adversarial.json", 5),
                ("automation-log/knowledge-base/FACTS_digest.md", 1),
            },
        )

    def test_validated_affiliate_tracker_does_not_look_like_phone(self) -> None:
        relative = ".system_control/affiliate.json"
        self.repo.write(
            relative,
            json.dumps(
                {
                    "tracking_urls": [
                        "https://atth.me/002114002a0x",
                        "https://atth.me/go/PeCbnOcY",
                    ]
                },
                indent=2,
            ) + "\n",
        )

        findings, scanned, operational_error = guard.scan_repository(self.repo.root)

        self.assertFalse(operational_error)
        self.assertEqual(scanned, 1)
        self.assertEqual(findings, [])

    def test_tracker_mask_is_span_limited_and_real_phone_still_fails(self) -> None:
        relative = "automation-log/affiliate-receipt.json"
        receipt = self.repo.write(
            relative,
            json.dumps(
                {
                    "tracking_url": "https://atth.me/002114002a0x",
                    "contact": "0812345678",
                    "note": (
                        "https://atth.me/002114002a0x call 0898765432"
                    ),
                },
                indent=2,
            ) + "\n",
        )
        lines = receipt.read_text(encoding="utf-8").splitlines()
        expected_lines = {
            index for index, line in enumerate(lines, 1)
            if '"contact"' in line or '"note"' in line
        }

        findings, scanned, operational_error = guard.scan_repository(self.repo.root)
        phone_lines = {
            finding.line for finding in findings
            if finding.path == relative and finding.category == "PHONE_NUMBER"
        }

        self.assertFalse(operational_error)
        self.assertEqual(scanned, 1)
        self.assertEqual(phone_lines, expected_lines)

    def test_tracker_validation_rejects_phone_hiding_variants(self) -> None:
        variants = {
            "insecure": "http://atth.me/002114002a0x",
            "wrong_host": "https://atth.me.evil.invalid/002114002a0x",
            "query_phone": "https://atth.me/002114002a0x?phone=0812345678",
            "fragment_phone": "https://atth.me/002114002a0x#0812345678",
            "path_suffix": "https://atth.me/002114002a0x0812345678",
            "extra_path": "https://atth.me/002114002a0x/0812345678",
        }
        relative = "automation-log/adversarial-affiliate.json"
        receipt = self.repo.write(
            relative,
            json.dumps(variants, indent=2) + "\n",
        )
        expected_lines = {
            index for index, line in enumerate(
                receipt.read_text(encoding="utf-8").splitlines(), 1
            )
            if any(key in line for key in variants)
        }

        findings, scanned, operational_error = guard.scan_repository(self.repo.root)
        phone_lines = {
            finding.line for finding in findings
            if finding.path == relative and finding.category == "PHONE_NUMBER"
        }

        self.assertFalse(operational_error)
        self.assertEqual(scanned, 1)
        self.assertEqual(phone_lines, expected_lines)

    def test_malformed_json_tracker_is_scanned_fail_closed(self) -> None:
        relative = "automation-log/malformed-affiliate.json"
        self.repo.write(
            relative,
            '{"tracking_url":"https://atth.me/002114002a0x"',
        )

        findings, _, operational_error = guard.scan_repository(self.repo.root)
        categories = {finding.category for finding in findings}

        self.assertFalse(operational_error)
        self.assertIn("MALFORMED_JSON", categories)
        self.assertIn("PHONE_NUMBER", categories)

    def test_malformed_json_digest_field_is_scanned_fail_closed(self) -> None:
        phone_marker = "0812345678"
        self.repo.write(
            "automation-log/malformed-digest.json",
            '{"sha256":"%s"' % phone_marker,
        )

        findings, _, operational_error = guard.scan_repository(self.repo.root)
        categories = {finding.category for finding in findings}

        self.assertFalse(operational_error)
        self.assertIn("MALFORMED_JSON", categories)
        self.assertIn("PHONE_NUMBER", categories)

    def test_malformed_json_fails_closed(self) -> None:
        self.repo.write(".system_control/broken.json", '{"state":')
        findings, _, operational_error = guard.scan_repository(self.repo.root)
        self.assertFalse(operational_error)
        self.assertIn("MALFORMED_JSON", {finding.category for finding in findings})

    def test_nonfinite_json_extensions_fail_closed(self) -> None:
        self.repo.write(".system_control/nonfinite.json", '{"score":NaN}')
        self.repo.write(
            "automation-log/nonfinite.jsonl",
            '{"score":Infinity}\n',
        )
        self.repo.write(".system_control/overflow.json", '{"score":1e999}')
        self.repo.write(
            "automation-log/duplicate.jsonl",
            '{"state":"safe","state":"unsafe"}\n',
        )
        findings, _, operational_error = guard.scan_repository(self.repo.root)
        categories = {finding.category for finding in findings}
        paths = {finding.path for finding in findings}
        self.assertFalse(operational_error)
        self.assertIn("MALFORMED_JSON", categories)
        self.assertIn("MALFORMED_JSONL", categories)
        self.assertIn(".system_control/overflow.json", paths)
        self.assertIn("automation-log/duplicate.jsonl", paths)

    def test_missing_tracked_file_fails_closed(self) -> None:
        path = self.repo.write("automation-log/missing.jsonl", '{"state":"ok"}\n')
        path.unlink()
        findings, _, operational_error = guard.scan_repository(self.repo.root)
        self.assertFalse(operational_error)
        self.assertIn("UNREADABLE_TRACKED_FILE", {finding.category for finding in findings})

    def test_non_repository_fails_closed_without_diagnostics_leak(self) -> None:
        empty = Path(tempfile.mkdtemp(prefix="privacy_guard_not_git_"))
        try:
            out = io.StringIO()
            with redirect_stdout(out):
                exit_code = guard.main(["--repo", str(empty)])
            rendered = out.getvalue()
            self.assertEqual(exit_code, 2)
            self.assertIn("GIT_INDEX_UNAVAILABLE", rendered)
            self.assertNotIn(str(empty), rendered)
        finally:
            shutil.rmtree(empty, ignore_errors=True)

    def test_cli_never_echoes_matched_values(self) -> None:
        marker = "synthetic-cli-secret-marker-002"
        self.repo.write(".system_control/private.json", json.dumps({"api_key": marker}))
        out = io.StringIO()
        with redirect_stdout(out):
            exit_code = guard.main(["--repo", str(self.repo.root)])
        rendered = out.getvalue()
        self.assertEqual(exit_code, 1)
        self.assertIn(".system_control/private.json:1 [CREDENTIAL_FIELD]", rendered)
        self.assertNotIn(marker, rendered)


if __name__ == "__main__":
    unittest.main(verbosity=2)
