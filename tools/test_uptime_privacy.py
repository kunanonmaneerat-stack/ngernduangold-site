#!/usr/bin/env python3
"""Privacy and provenance regressions for uptime-owned egress evidence."""

from __future__ import annotations

import contextlib
import datetime
import io
import json
import platform
import re
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
import uptime_check as UPTIME  # noqa: E402


class UptimePrivacyTests(unittest.TestCase):
    @staticmethod
    def _secret_fixture() -> str:
        # Build the documentation-only value at runtime so test output cannot
        # accidentally normalize into an operational-looking address literal.
        return ".".join(("203", "0", "113", "17"))

    def test_json_and_human_output_suppress_recorded_address(self) -> None:
        secret = self._secret_fixture()
        output = io.StringIO()
        with (
            mock.patch.object(sys, "argv", ["uptime_check.py", "--json"]),
            mock.patch.object(UPTIME, "fetch", return_value=(200, "fixture", None)),
            mock.patch.object(UPTIME, "judge", return_value=("up", "fixture healthy")),
            mock.patch.object(UPTIME, "clear_alert", return_value=False),
            mock.patch.object(UPTIME, "record_host_ip", return_value=secret),
            contextlib.redirect_stdout(output),
        ):
            self.assertEqual(UPTIME.main(), 0)

        rendered = output.getvalue()
        self.assertNotIn(secret, rendered)
        self.assertIn("value suppressed", rendered)
        payload = json.loads(rendered.strip().splitlines()[-1])
        self.assertTrue(payload["host_ip_recorded"])
        self.assertNotIn("host_ip", payload)

    def test_selftest_never_echoes_address_or_cidr_values(self) -> None:
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            self.assertEqual(UPTIME.selftest(), 0)
        rendered = output.getvalue()
        self.assertIsNone(re.search(r"\b(?:\d{1,3}\.){3}\d{1,3}(?:/\d{1,3})?\b", rendered))

    def test_recorder_binds_private_evidence_to_machine_source_and_aware_time(self) -> None:
        secret = self._secret_fixture()
        response = SimpleNamespace(read=lambda: json.dumps({"ip": secret}).encode("utf-8"))
        with tempfile.TemporaryDirectory(prefix="uptime_private_state_") as tmp:
            target = Path(tmp) / "host-state.json"
            with (
                mock.patch.object(UPTIME, "HOST_IP_FILE", str(target)),
                mock.patch.object(UPTIME, "urlopen", return_value=response),
                mock.patch.object(platform, "node", return_value="fixture-host"),
            ):
                self.assertEqual(UPTIME.record_host_ip(), secret)
            payload = json.loads(target.read_text(encoding="utf-8"))

        self.assertEqual(payload["host"], "fixture-host")
        self.assertEqual(payload["source"], "api.ipify.org")
        stamp = datetime.datetime.fromisoformat(payload["checked_at"])
        self.assertIsNotNone(stamp.tzinfo)
        self.assertEqual(payload["ip"], secret)

    def test_recorder_refuses_unbound_machine_identity(self) -> None:
        secret = self._secret_fixture()
        response = SimpleNamespace(read=lambda: json.dumps({"ip": secret}).encode("utf-8"))
        with tempfile.TemporaryDirectory(prefix="uptime_no_host_") as tmp:
            target = Path(tmp) / "host-state.json"
            with (
                mock.patch.object(UPTIME, "HOST_IP_FILE", str(target)),
                mock.patch.object(UPTIME, "urlopen", return_value=response),
                mock.patch.object(platform, "node", return_value=""),
            ):
                self.assertIsNone(UPTIME.record_host_ip())
            self.assertFalse(target.exists())


if __name__ == "__main__":
    unittest.main(verbosity=2)
