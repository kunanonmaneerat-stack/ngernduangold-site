#!/usr/bin/env python3
"""Regression tests for the retired post-plan producer/consumer boundary."""

from contextlib import redirect_stderr, redirect_stdout
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "pipeline"))

import posting_kit  # noqa: E402


def _valid_document():
    return {
        "plan": [
            {
                "day": "2026-08-24",
                "topic": "fixture",
                "label": "local only",
                "file": "reels/fixture.mp4",
                "tiktok": 19,
                "ig": 20,
                "yt": 18,
                "caption": "fixture caption",
                "hashtags": "#fixture",
            }
        ]
    }


class PostingKitContractTests(unittest.TestCase):
    def _run(self, *args):
        stdout = io.StringIO()
        stderr = io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            exit_code = posting_kit.main(list(args))
        return exit_code, stdout.getvalue(), stderr.getvalue()

    def test_missing_legacy_input_with_no_output_is_an_explicit_noop(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            output = base / "posting-kit.html"

            exit_code, stdout, stderr = self._run(
                "--plan",
                str(base / "post-plan.json"),
                "--output",
                str(output),
                "--allow-missing-legacy-plan",
            )

            self.assertEqual(exit_code, posting_kit.EXIT_OK)
            self.assertIn("SKIP", stdout)
            self.assertEqual(stderr, "")
            self.assertFalse(output.exists())

    def test_missing_legacy_input_marks_preserved_output_for_review(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            output = base / "posting-kit.html"
            output.write_text("owner-created sentinel", encoding="utf-8")

            exit_code, stdout, stderr = self._run(
                "--plan",
                str(base / "post-plan.json"),
                "--output",
                str(output),
                "--allow-missing-legacy-plan",
            )

            self.assertEqual(exit_code, posting_kit.EXIT_REVIEW_REQUIRED)
            self.assertEqual(stdout, "")
            self.assertIn("REVIEW_REQUIRED", stderr)
            self.assertIn("may be stale", stderr)
            self.assertEqual(output.read_text(encoding="utf-8"), "owner-created sentinel")

    def test_missing_input_without_runner_opt_in_is_a_true_failure(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            output = base / "posting-kit.html"
            exit_code, _stdout, stderr = self._run(
                "--plan",
                str(base / "post-plan.json"),
                "--output",
                str(output),
            )

            self.assertEqual(exit_code, posting_kit.EXIT_RUNNER_FAILED)
            self.assertIn("RUNNER_FAILED", stderr)
            self.assertFalse(output.exists())

    def test_malformed_existing_plan_requires_review_without_rewriting_output(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            plan = base / "post-plan.json"
            output = base / "posting-kit.html"
            plan.write_text("{not-json", encoding="utf-8")
            output.write_text("known-good sentinel", encoding="utf-8")

            exit_code, _stdout, stderr = self._run(
                "--plan",
                str(plan),
                "--output",
                str(output),
                "--allow-missing-legacy-plan",
            )

            self.assertEqual(exit_code, posting_kit.EXIT_REVIEW_REQUIRED)
            self.assertIn("REVIEW_REQUIRED", stderr)
            self.assertEqual(output.read_text(encoding="utf-8"), "known-good sentinel")

    def test_valid_plan_builds_only_the_requested_local_output(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            plan = base / "post-plan.json"
            output = base / "posting-kit.html"
            plan.write_text(json.dumps(_valid_document()), encoding="utf-8")

            exit_code, stdout, stderr = self._run(
                "--plan",
                str(plan),
                "--output",
                str(output),
            )

            self.assertEqual(exit_code, posting_kit.EXIT_OK)
            self.assertIn("(1 คลิป)", stdout)
            self.assertEqual(stderr, "")
            rendered = output.read_text(encoding="utf-8")
            self.assertIn("1 คลิป", rendered)
            self.assertNotIn("36 คลิป", rendered)
            self.assertIn("fixture caption", rendered)

    def test_output_io_failure_is_not_downgraded_to_review_required(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            plan = base / "post-plan.json"
            plan.write_text(json.dumps(_valid_document()), encoding="utf-8")

            exit_code, _stdout, stderr = self._run(
                "--plan",
                str(plan),
                "--output",
                str(base / "missing-parent" / "posting-kit.html"),
            )

            self.assertEqual(exit_code, posting_kit.EXIT_RUNNER_FAILED)
            self.assertIn("RUNNER_FAILED", stderr)


if __name__ == "__main__":
    unittest.main(verbosity=2)
