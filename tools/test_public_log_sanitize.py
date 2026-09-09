#!/usr/bin/env python3
"""Focused tests for the public-log write boundary."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path


LOG_DIR = Path(__file__).resolve().parents[1] / "automation-log"
sys.path.insert(0, str(LOG_DIR))
from public_log_sanitize import sanitize_public_record, sanitize_text  # noqa: E402


class PublicLogSanitizeTests(unittest.TestCase):
    def test_text_values_are_redacted_without_dropping_summary(self) -> None:
        text = (
            "email person@example.com; Telegram home=123456789; "
            "network 203.0.113.17"
        )
        clean = sanitize_text(text)
        self.assertIn("email", clean)
        self.assertNotIn("person@example.com", clean)
        self.assertNotIn("123456789", clean)
        self.assertNotIn("203.0.113.17", clean)

    def test_private_fields_are_removed_recursively(self) -> None:
        clean = sanitize_public_record({
            "summary": "safe aggregate",
            "metrics": {"revenue_thb": 0, "count": 3},
            "email": "person@example.com",
        })
        self.assertEqual(clean["summary"], "safe aggregate")
        self.assertEqual(clean["metrics"], {"count": 3})
        self.assertNotIn("email", clean)
        self.assertEqual(
            clean["redacted_private_fields"], ["email", "revenue_thb"]
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
