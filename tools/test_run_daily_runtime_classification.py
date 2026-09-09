#!/usr/bin/env python3
"""Regression checks for exact Windows runner alert classification."""

from __future__ import annotations

from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[1]
RUNNER = ROOT / "pipeline/run_daily.cmd"


def normalized_active_lines() -> list[str]:
    lines = []
    for raw in RUNNER.read_text(encoding="utf-8").splitlines():
        line = re.sub(r"\s+", " ", raw.strip()).casefold()
        if line and not line.startswith("rem ") and not line.startswith("::"):
            lines.append(line)
    return lines


class RunDailyRuntimeClassificationTests(unittest.TestCase):
    def test_alerts_require_exact_verified_block_not_runner_failure(self) -> None:
        lines = normalized_active_lines()
        for script, alert_marker in (
            ("uptime_check.py", "site down"),
            ("agent_gap_check.py", "agent layer silent"),
        ):
            with self.subTest(script=script):
                call_index = next(
                    index for index, line in enumerate(lines)
                    if line.startswith("call :graded ") and script in line
                )
                alert_line = lines[call_index + 1]
                self.assertTrue(alert_line.startswith("if !step_rc! equ 2 echo "))
                self.assertIn(alert_marker, alert_line)
                self.assertNotIn("if errorlevel 2", alert_line)

    def test_novelty_skip_and_unknown_block_use_exact_reserved_codes(self) -> None:
        lines = normalized_active_lines()
        for script, rc_var in (
            ("dispatcher.py", "dispatcher_rc"),
            ("daily_content.py", "daily_content_rc"),
        ):
            with self.subTest(script=script):
                call_index = next(
                    index for index, line in enumerate(lines)
                    if line.startswith("call :novelty_queue ") and script in line
                )
                self.assertEqual(
                    lines[call_index - 1],
                    'set "step_contract=novelty-queue-v1"',
                )
                self.assertEqual(
                    lines[call_index + 1], f"set {rc_var}=!errorlevel!"
                )
                self.assertTrue(lines[call_index + 2].startswith(
                    f"if !{rc_var}! equ 10 echo "
                ))
                self.assertIn("novelty_exhausted - skip", lines[call_index + 2])
                self.assertTrue(lines[call_index + 3].startswith(
                    f"if !{rc_var}! equ 20 echo "
                ))
                self.assertIn("blocked_unknown", lines[call_index + 3])
                self.assertNotIn("if errorlevel", " ".join(
                    lines[call_index + 1:call_index + 5]
                ))


if __name__ == "__main__":
    unittest.main(verbosity=2)
