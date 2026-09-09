#!/usr/bin/env python3
"""The legacy scheduler helper must never overwrite the hardened task."""

from __future__ import annotations

import importlib.util
from pathlib import Path
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "scheduler_agent", ROOT / "pipeline" / "scheduler_agent.py"
)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(MODULE)


class SchedulerAgentSafetyTests(unittest.TestCase):
    def test_install_is_refused_without_invoking_schtasks(self) -> None:
        with mock.patch.object(MODULE, "_sch") as sch:
            self.assertEqual(MODULE.main(["install"]), 2)
        sch.assert_not_called()

    def test_status_propagates_missing_task(self) -> None:
        with mock.patch.object(MODULE, "status", return_value={"exists": False}):
            self.assertEqual(MODULE.main(["status"]), 1)

    def test_status_propagates_success(self) -> None:
        with mock.patch.object(MODULE, "status", return_value={"exists": True}):
            self.assertEqual(MODULE.main([]), 0)

    def test_unknown_command_fails(self) -> None:
        with mock.patch.object(MODULE, "_sch") as sch:
            self.assertEqual(MODULE.main(["mutate"]), 2)
        sch.assert_not_called()


if __name__ == "__main__":
    unittest.main(verbosity=2)
