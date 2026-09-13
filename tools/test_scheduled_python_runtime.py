#!/usr/bin/env python3
"""Local regression tests for the scheduled Python dependency launcher."""

from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
PIPELINE = ROOT / "pipeline"
LAUNCHER = PIPELINE / "python_runtime.cmd"
PROJECT_RUNTIME = ROOT / ".venv" / "Scripts" / "python.exe"


class ScheduledPythonRuntimeTests(unittest.TestCase):
    def _run_strict(
        self, cv2_body: str, *args: str, cryptography_body: str | None = None
    ) -> subprocess.CompletedProcess:
        with tempfile.TemporaryDirectory() as raw_tmp:
            fake_module = Path(raw_tmp) / "cv2.py"
            fake_module.write_text(cv2_body, encoding="ascii")
            if cryptography_body is not None:
                (Path(raw_tmp) / "cryptography.py").write_text(
                    cryptography_body, encoding="ascii"
                )
            env = os.environ.copy()
            env["NGERNDUANGOLD_PYTHON"] = str(
                PROJECT_RUNTIME if PROJECT_RUNTIME.is_file() else Path(sys.executable)
            )
            env["NGERNDUANGOLD_PYTHON_STRICT"] = "1"
            env["PYTHONPATH"] = raw_tmp
            return subprocess.run(
                ["cmd.exe", "/d", "/c", str(LAUNCHER), *args],
                cwd=ROOT,
                env=env,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
            )

    def test_valid_configured_runtime_is_used_after_import_probe(self) -> None:
        result = self._run_strict(
            "__version__ = 'test-double'\n",
            "-c", "print('FAKE_RUNTIME_OK')",
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("FAKE_RUNTIME_OK", result.stdout)

    def test_missing_imports_fail_before_target_command(self) -> None:
        result = self._run_strict(
            "raise ImportError('blocked by test')\n",
            "-c", "print('SHOULD_NOT_RUN')",
        )
        self.assertEqual(result.returncode, 86)
        self.assertIn("RUNNER_FAILED", result.stdout + result.stderr)
        self.assertNotIn("SHOULD_NOT_RUN", result.stdout + result.stderr)

    def test_missing_ed25519_dependency_fails_before_target_command(self) -> None:
        result = self._run_strict(
            "__version__ = 'test-double'\n",
            "-c", "print('SHOULD_NOT_RUN')",
            cryptography_body="raise ImportError('blocked by test')\n",
        )
        self.assertEqual(result.returncode, 86)
        self.assertIn("RUNNER_FAILED", result.stdout + result.stderr)
        self.assertNotIn("SHOULD_NOT_RUN", result.stdout + result.stderr)

    def test_live_project_runtime_imports_required_dependencies(self) -> None:
        result = subprocess.run(
            [
                "cmd.exe", "/d", "/c", str(LAUNCHER), "-c",
                "import numpy,cv2,PIL,cryptography; print('REQUIRED_RUNTIME_OK')",
            ],
            cwd=ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("REQUIRED_RUNTIME_OK", result.stdout)

    def test_runtime_lockfile_pins_ed25519_verifier_dependency(self) -> None:
        requirements = (PIPELINE / "requirements-runtime.txt").read_text(
            encoding="utf-8"
        ).splitlines()
        self.assertIn("cryptography==48.0.1", requirements)

    def test_runners_and_contract_use_hash_bound_launcher(self) -> None:
        sys.path.insert(0, str(PIPELINE))
        try:
            import task_run_receipt as receipt
            import improvement_loop as loop
        finally:
            sys.path.pop(0)

        for runner_name in ("run_daily.cmd", "run_weekly.cmd"):
            runner = (PIPELINE / runner_name).read_text(encoding="utf-8")
            self.assertIn(
                'set "PY=%REPO_ROOT%\\pipeline\\python_runtime.cmd"', runner
            )
            self.assertNotIn("pythoncore-3.14-64\\python.exe", runner)

        self.assertEqual(
            receipt.ACTIVE_TASK_CONTRACT_VERSION["ngernduangold_daily"],
            "daily-runner-v6",
        )
        self.assertEqual(
            receipt.ACTIVE_TASK_CONTRACT_VERSION["ngernduangold_weekly"],
            "weekly-runner-v5",
        )
        for task_name, version in receipt.ACTIVE_TASK_CONTRACT_VERSION.items():
            commands = receipt.TASK_STEP_COMMAND_REGISTRY[(task_name, version)]
            self.assertTrue(commands)
            self.assertTrue(all(command[0] == str(LAUNCHER) for command in commands.values()))

        self.assertIn("pipeline/python_runtime.cmd", loop.RUNTIME_CONTRACT_PATHS)
        self.assertIn("pipeline/requirements-runtime.txt", loop.RUNTIME_CONTRACT_PATHS)

    def test_batch_runners_call_the_cmd_launcher_before_returning(self) -> None:
        """A .cmd-to-.cmd invocation must use CALL or it abandons the runner."""
        for runner_name in ("run_daily.cmd", "run_weekly.cmd"):
            runner = (PIPELINE / runner_name).read_text(encoding="utf-8")
            active = [
                line.strip()
                for line in runner.splitlines()
                if line.strip()
                and not line.lstrip().casefold().startswith(("rem ", "::"))
            ]
            direct = [
                line for line in active
                if line.startswith('"%PY%"')
            ]
            self.assertEqual(
                direct,
                [],
                f"{runner_name} invokes python_runtime.cmd without CALL",
            )
            self.assertIn(
                'call "%PY%" "%RECEIPT_TOOL%" record ',
                runner,
            )
            self.assertIn(
                'call "%PY%" "%RECEIPT_TOOL%" finish ',
                runner,
            )

    def test_receipt_subprocess_can_execute_the_cmd_launcher(self) -> None:
        sys.path.insert(0, str(PIPELINE))
        try:
            import task_run_receipt as receipt
        finally:
            sys.path.pop(0)

        with tempfile.TemporaryDirectory() as raw_tmp:
            tmp = Path(raw_tmp)
            runner = tmp / "synthetic-runner.cmd"
            runner.write_text("@exit /b 0\r\n", encoding="ascii")
            receipt_root = tmp / "receipts"
            run_id = "runtime-launcher-smoke"
            receipt.start_receipt(
                root=receipt_root,
                task_name="runtime-launcher-smoke",
                runner_path=runner,
                log_path=tmp / "runner.log",
                run_id=run_id,
            )
            raw_rc = receipt.execute_step(
                root=receipt_root,
                task_name="runtime-launcher-smoke",
                run_id=run_id,
                step_id="media_imports",
                wrapper="required",
                contract="zero-only-v1",
                command=[
                    str(LAUNCHER), "-c",
                    "import numpy,cv2,PIL,cryptography; raise SystemExit(0)",
                ],
            )
            self.assertEqual(raw_rc, 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
