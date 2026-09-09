#!/usr/bin/env python3
"""Prove scheduled generation wrappers cannot reach a network/paid LLM."""

from __future__ import annotations

import ast
import contextlib
import io
from pathlib import Path
import socket
import sys
import tempfile
import unittest
import urllib.request
from unittest import mock


ROOT = Path(__file__).resolve().parent.parent
PIPELINE = ROOT / "pipeline"
if str(PIPELINE) not in sys.path:
    sys.path.insert(0, str(PIPELINE))

import daily_content  # noqa: E402
import dispatcher  # noqa: E402
import free_llm  # noqa: E402


RUN_DAILY = PIPELINE / "run_daily.cmd"
WRAPPERS = (
    PIPELINE / "dispatcher.py",
    PIPELINE / "daily_content.py",
    PIPELINE / "request_retirement.py",
)
FORBIDDEN_IMPORTS = {
    "content_council", "content_creators", "free_llm", "head_content",
    "httpx", "openai", "requests", "urllib",
}


def imported_roots(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    roots = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            roots.update(alias.name.split(".", 1)[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            roots.add(node.module.split(".", 1)[0])
    return roots


def active_lines(path: Path) -> list[str]:
    result = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.casefold().startswith("rem ") or line.startswith("::"):
            continue
        result.append(line)
    return result


class ScheduledLlmSafetyTests(unittest.TestCase):
    def test_free_llm_is_offline_even_when_every_key_exists(self) -> None:
        keys = {
            "QWEN_API_KEY": "fixture",
            "QW_KEY": "fixture",
            "GLM_KEY": "fixture",
            "DEEPSEEK_KEY": "fixture",
        }
        with (
            mock.patch.dict("os.environ", keys, clear=False),
            mock.patch.object(free_llm, "_get_key", side_effect=AssertionError("must not read keys")),
            contextlib.redirect_stdout(io.StringIO()),
        ):
            self.assertEqual(free_llm.generate("fixture", verbose=True), (None, None))

    def test_legacy_provider_call_fails_before_network(self) -> None:
        with mock.patch.object(urllib.request, "urlopen", side_effect=AssertionError("network")) as urlopen:
            with self.assertRaises(free_llm.NetworkGenerationBlocked):
                free_llm._call("https://example.invalid", "paid", "key", "p", "s", 1, 0)
        urlopen.assert_not_called()

    def test_scheduled_wrappers_run_with_network_mocked_to_zero(self) -> None:
        from tools.test_content_novelty_queue import _fixture_registry

        with tempfile.TemporaryDirectory(prefix="scheduled_llm_offline_") as temp:
            root = Path(temp)
            inbox = root / "inbox"
            orders = root / "orders.txt"
            _fixture_registry(orders, active_count=1, historical_count=0)
            with (
                mock.patch.object(dispatcher, "INBOX", str(inbox)),
                mock.patch.object(dispatcher, "ORDERS", str(orders)),
                mock.patch.object(daily_content, "INBOX", str(inbox)),
                mock.patch.object(daily_content, "ORDERS", str(orders)),
                mock.patch.object(urllib.request, "urlopen", side_effect=AssertionError("network")) as urlopen,
                mock.patch.object(socket.socket, "connect", side_effect=AssertionError("network")) as connect,
                contextlib.redirect_stdout(io.StringIO()),
            ):
                dispatcher.bootstrap_novelty_state(
                    dispatcher.ledger_path_for(inbox)
                )
                dispatch = dispatcher.main()
                daily = daily_content.main()
            self.assertFalse(dispatch["generated"])
            self.assertTrue(Path(dispatch["request"]).is_file())
            self.assertTrue(Path(daily).is_file())
        urlopen.assert_not_called()
        connect.assert_not_called()

    def test_scheduled_wrappers_have_no_llm_or_http_import_edge(self) -> None:
        for path in WRAPPERS:
            with self.subTest(path=path.name):
                self.assertEqual(imported_roots(path) & FORBIDDEN_IMPORTS, set())

    def test_batch_propagates_local_only_to_both_generation_steps(self) -> None:
        lines = active_lines(RUN_DAILY)
        for script in ("dispatcher.py", "daily_content.py"):
            matches = [line for line in lines if script in line]
            self.assertEqual(len(matches), 1)
            self.assertIn("--local-only", matches[0])
        active = "\n".join(lines).casefold()
        for forbidden in ("--network", "--paid", "--generate", "free_llm.py"):
            self.assertNotIn(forbidden, active)

    def test_shared_llm_sink_contains_no_http_transport(self) -> None:
        source = (PIPELINE / "free_llm.py").read_text(encoding="utf-8")
        tree = ast.parse(source)
        imported = imported_roots(PIPELINE / "free_llm.py")
        self.assertNotIn("urllib", imported)
        self.assertNotIn("requests", imported)
        calls = {
            node.func.attr
            for node in ast.walk(tree)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
        }
        self.assertNotIn("urlopen", calls)
        self.assertNotIn("post", calls)


if __name__ == "__main__":
    unittest.main(verbosity=2)
