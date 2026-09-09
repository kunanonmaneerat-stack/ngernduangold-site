#!/usr/bin/env python3
from pathlib import Path
import shlex
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
PIPELINE = ROOT / "pipeline"
if str(PIPELINE) not in sys.path:
    sys.path.insert(0, str(PIPELINE))

import task_run_receipt as receipt


class ImprovementLoopWiringTests(unittest.TestCase):
    def _runner_step_commands(self, runner_name):
        text = (PIPELINE / runner_name).read_text(encoding="utf-8")
        lines = text.splitlines()
        observed = []
        for index, raw in enumerate(lines):
            stripped = raw.strip()
            if not stripped.startswith('set "STEP_NAME='):
                continue
            step_id = stripped[len('set "STEP_NAME='):-1]
            for candidate in lines[index + 1:]:
                call = candidate.strip()
                if call.startswith('set "STEP_NAME='):
                    self.fail("step has no bound wrapper call: " + step_id)
                if not call.startswith((
                    "call :required ", "call :novelty_queue ",
                    "call :graded ",
                )):
                    continue
                parts = shlex.split(call, posix=False)
                if "||" in parts:
                    parts = parts[:parts.index("||")]
                wrapper_label = parts[1][1:]
                wrapper = (
                    "required" if wrapper_label == "novelty_queue"
                    else wrapper_label
                )
                command = []
                for token in parts[2:]:
                    if len(token) >= 2 and token[0] == token[-1] == '"':
                        token = token[1:-1]
                    token = token.replace("%PY%", receipt.RUNTIME_LAUNCHER)
                    token = token.replace("%BASE%", str(PIPELINE))
                    command.append(token)
                observed.append((step_id, wrapper, receipt._normalize_command(command)))
                break
        return observed

    def test_daily_runs_after_ga4_and_before_traffic_decisions(self):
        text = (ROOT / "pipeline" / "run_daily.cmd").read_text(encoding="utf-8")
        ga4 = text.index('"%BASE%\\ga4_pull.py"')
        loop = text.index('"%BASE%\\improvement_loop.py" run --cadence daily --mode local-safe')
        analyst = text.index('"%BASE%\\traffic_analyst.py"')
        self.assertLess(ga4, loop)
        self.assertLess(loop, analyst)
        self.assertIn("call :required", text[text.rfind("\n", 0, loop):loop])
        self.assertEqual(
            text.count('"%BASE%\\improvement_loop.py" run --cadence daily --mode local-safe'),
            1,
        )
        self.assertNotIn("--cadence weekly", text)
        self.assertIn("set IMPROVEMENT_RC=!errorlevel!", text)
        ga4_line = next(line.strip() for line in text.splitlines() if "ga4_pull.py" in line and "call :required" in line)
        self.assertNotIn("goto :abort", ga4_line.casefold())
        linkcheck_line = next(
            line.strip()
            for line in text.splitlines()
            if "fb_queue_linkcheck.py" in line and "call :required" in line
        )
        self.assertNotIn("goto :abort", linkcheck_line.casefold())

    def test_weekly_finishes_with_local_safe_loop(self):
        text = (ROOT / "pipeline" / "run_weekly.cmd").read_text(encoding="utf-8")
        gsc = text.index('"%BASE%\\gsc_pull.py"')
        review = text.index('"%BASE%\\weekly_growth_review.py"')
        loop = text.index('"%BASE%\\improvement_loop.py" run --cadence weekly --mode local-safe')
        self.assertLess(gsc, review)
        self.assertLess(review, loop)
        self.assertEqual(
            text.count('"%BASE%\\improvement_loop.py" run --cadence weekly --mode local-safe'),
            1,
        )
        self.assertNotIn("--cadence daily", text)
        self.assertIn("set IMPROVEMENT_RC=!errorlevel!", text)
        ga4_line = next(line.strip() for line in text.splitlines() if "ga4_pull.py" in line and "call :required" in line)
        gsc_line = next(line.strip() for line in text.splitlines() if "gsc_pull.py" in line and "call :required" in line)
        self.assertNotIn("goto :abort", ga4_line.casefold())
        self.assertNotIn("goto :abort", gsc_line.casefold())

    def test_no_external_mode_is_wired(self):
        combined = "\n".join(
            (ROOT / "pipeline" / name).read_text(encoding="utf-8")
            for name in ("run_daily.cmd", "run_weekly.cmd")
        )
        self.assertNotIn("--mode publish", combined)
        self.assertNotIn("--mode deploy", combined)

    def test_each_monitored_step_is_bound_to_the_exact_runner_command(self):
        for task_name, version in receipt.ACTIVE_TASK_CONTRACT_VERSION.items():
            with self.subTest(task=task_name):
                spec = receipt.TASK_STEP_CONTRACT_REGISTRY[(task_name, version)]
                observed = self._runner_step_commands(spec["runner_name"])
                expected_steps = [
                    (step_id, wrapper)
                    for step_id, wrapper, _ in spec["expected_steps"]
                    if wrapper != "internal"
                ]
                self.assertEqual(
                    [(step_id, wrapper) for step_id, wrapper, _ in observed],
                    expected_steps,
                )
                registry = receipt.TASK_STEP_COMMAND_REGISTRY[
                    (task_name, version)
                ]
                for step_id, _, command in observed:
                    self.assertEqual(
                        command,
                        receipt._normalize_command(registry[step_id]),
                        step_id,
                    )


if __name__ == "__main__":
    unittest.main(verbosity=2)
