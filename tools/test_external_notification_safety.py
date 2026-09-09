#!/usr/bin/env python3
"""Focused regression tests for scheduled local-only notification safety.

The suite never executes a batch runner and never opens a network connection.
It combines behavioral tests for default callers with static source-order guards
for the Windows Task Scheduler entry points.
"""

from __future__ import annotations

import ast
import contextlib
import importlib.util
import io
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parent.parent
PIPELINE = ROOT / "pipeline"
if str(PIPELINE) not in sys.path:
    sys.path.insert(0, str(PIPELINE))

import cc_bridge  # noqa: E402
import cc_monitor  # noqa: E402
import dispatcher  # noqa: E402
import hermes_digest  # noqa: E402


DAILY = PIPELINE / "run_daily.cmd"
WEEKLY = PIPELINE / "run_weekly.cmd"
SOCIAL_DAILY = ROOT / "social-autopost" / "run_daily.py"
TIKTOK_PUBLISHER = ROOT / "social-autopost" / "publish_tiktok.py"
DAILY_REMINDER = PIPELINE / "daily_post_reminder.py"
SCHEDULED_COMPONENTS = (
    PIPELINE / "cc_bridge.py",
    PIPELINE / "cc_monitor.py",
    PIPELINE / "dispatcher.py",
    PIPELINE / "request_retirement.py",
    PIPELINE / "hermes_digest.py",
    PIPELINE / "weekly_growth_review.py",
)
EXTERNAL_IMPORTS = {
    "playwright", "requests", "selenium", "smtplib", "subprocess",
    "urllib", "webbrowser",
}


def active_lines(path: Path) -> list[str]:
    result = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        stripped = raw.strip()
        if not stripped or stripped.casefold().startswith("rem ") or stripped.startswith("::"):
            continue
        result.append(stripped)
    return result


def imported_roots(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    roots = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            roots.update(alias.name.split(".", 1)[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            roots.add(node.module.split(".", 1)[0])
    return roots


def load_social_daily():
    spec = importlib.util.spec_from_file_location("social_autopost_daily_fixture", SOCIAL_DAILY)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def load_daily_reminder():
    spec = importlib.util.spec_from_file_location(
        "daily_post_reminder_local_fixture", DAILY_REMINDER
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class LocalNotificationBehaviorTests(unittest.TestCase):
    def test_bridge_ping_and_send_are_local_only(self) -> None:
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertFalse(cc_bridge.ping("fixture notification"))
        with tempfile.TemporaryDirectory(prefix="cc_bridge_local_") as temp:
            with mock.patch.object(cc_bridge, "INBOX", temp):
                with contextlib.redirect_stdout(io.StringIO()):
                    path = Path(cc_bridge.send("fixture", "local body"))
            self.assertEqual(path.read_text(encoding="utf-8"), "local body")

    def test_dispatcher_default_only_queues_local_content(self) -> None:
        from tools.test_content_novelty_queue import _fixture_registry

        with tempfile.TemporaryDirectory(prefix="dispatcher_local_") as temp:
            root = Path(temp)
            inbox = root / "inbox"
            orders = root / "orders.txt"
            _fixture_registry(orders, active_count=1, historical_count=0)
            with (
                mock.patch.object(dispatcher, "INBOX", str(inbox)),
                mock.patch.object(dispatcher, "ORDERS", str(orders)),
                contextlib.redirect_stdout(io.StringIO()),
            ):
                dispatcher.bootstrap_novelty_state(
                    dispatcher.ledger_path_for(inbox)
                )
                result = dispatcher.main()
            self.assertTrue(Path(result["request"]).is_file())
        self.assertEqual(result["queued"], 0)
        self.assertFalse(result["generated"])
        self.assertFalse(result["notified"])

    def test_hermes_digest_default_writes_local_artifacts_only(self) -> None:
        card = types.ModuleType("summary_card")
        card.build = lambda: "C:/fixture/summary.png"
        with tempfile.TemporaryDirectory(prefix="digest_local_") as temp:
            with (
                mock.patch.object(hermes_digest, "INBOX", temp),
                mock.patch.object(hermes_digest, "build", return_value="fixture digest"),
                mock.patch.dict(sys.modules, {"summary_card": card}),
                contextlib.redirect_stdout(io.StringIO()),
            ):
                message, sent = hermes_digest.run()
            reports = list(Path(temp).glob("digest-*.md"))
        self.assertEqual(message, "fixture digest")
        self.assertFalse(sent)
        self.assertEqual(len(reports), 1)

    def test_cc_monitor_default_writes_local_status_only(self) -> None:
        with tempfile.TemporaryDirectory(prefix="cc_monitor_local_") as temp:
            root = Path(temp)
            paths = {name: root / name for name in ("in", "out", "arch", "cowork")}
            for path in paths.values():
                path.mkdir()
            with (
                mock.patch.object(cc_monitor, "INBOX", str(paths["in"])),
                mock.patch.object(cc_monitor, "OUTBOX", str(paths["out"])),
                mock.patch.object(cc_monitor, "ARCH", str(paths["arch"])),
                mock.patch.object(cc_monitor, "COWORK_IN", str(paths["cowork"])),
                contextlib.redirect_stdout(io.StringIO()),
            ):
                report = Path(cc_monitor.main())
            self.assertTrue(report.is_file())

    def test_daily_post_reminder_writes_local_card_without_transport(self) -> None:
        module = load_daily_reminder()
        today = module.datetime.date.today().isoformat()
        plan = [{
            "day": today,
            "file": "fixture.mp4",
            "topic": "fixture",
            "label": "local-only",
            "caption": "fixture caption",
            "hashtags": "#fixture",
        }]
        with tempfile.TemporaryDirectory(prefix="daily_reminder_local_") as temp:
            with (
                mock.patch.object(module, "INBOX", temp),
                mock.patch.object(module, "_plan", return_value=plan),
                mock.patch.object(module, "BATCH_WEEKDAY", -1),
                contextlib.redirect_stdout(io.StringIO()),
            ):
                messages = module.run()
            cards = list(Path(temp).glob("today-post-*.md"))
            self.assertEqual(len(cards), 1)
            self.assertEqual(cards[0].read_text(encoding="utf-8"), messages[0])
        self.assertFalse(hasattr(module, "hermes_send"))


class ScheduledSourceSafetyTests(unittest.TestCase):
    def test_scheduled_components_have_no_external_transport_import(self) -> None:
        for path in SCHEDULED_COMPONENTS:
            with self.subTest(path=path.name):
                self.assertEqual(imported_roots(path) & EXTERNAL_IMPORTS, set())

    def test_runners_force_local_only_and_never_opt_in_to_notification(self) -> None:
        daily = active_lines(DAILY)
        weekly = active_lines(WEEKLY)
        for script in ("dispatcher.py", "hermes_digest.py", "cc_monitor.py"):
            matches = [line for line in daily if script in line]
            self.assertEqual(len(matches), 1)
            self.assertIn("--local-only", matches[0])
        weekly_review = [line for line in weekly if "weekly_growth_review.py" in line]
        self.assertEqual(len(weekly_review), 1)
        self.assertIn("--local-only", weekly_review[0])
        active = "\n".join(daily + weekly).casefold()
        for forbidden in (
            "--notify", "telegram_notify.py", "daily_post_reminder.py",
            "playwright", "webbrowser", "slack webhook", "smtp",
        ):
            self.assertNotIn(forbidden, active)

    def test_daily_authority_guards_precede_local_scheduled_consumers(self) -> None:
        lines = active_lines(DAILY)
        guard_positions = []
        for guard in (
            "automation_policy_guard.py", "privacy_guard.py", "public_identity_guard.py",
        ):
            guard_positions.append(next(i for i, line in enumerate(lines) if guard in line))
        consumer_positions = []
        for script in ("dispatcher.py", "hermes_digest.py", "cc_monitor.py"):
            consumer_positions.append(next(i for i, line in enumerate(lines) if script in line))
        self.assertLess(max(guard_positions), min(consumer_positions))

    def test_weekly_review_source_has_no_notification_call(self) -> None:
        source = (PIPELINE / "weekly_growth_review.py").read_text(encoding="utf-8")
        self.assertNotIn("cc_bridge", source)
        self.assertNotIn("hermes_cli", source)
        self.assertNotIn("telegram_notify", source)

    def test_daily_post_reminder_has_no_external_transport(self) -> None:
        source = DAILY_REMINDER.read_text(encoding="utf-8")
        self.assertEqual(imported_roots(DAILY_REMINDER) & EXTERNAL_IMPORTS, set())
        for forbidden in (
            "hermes_cli", "telegram_home_channel", "hermes_send(", "--notify",
        ):
            self.assertNotIn(forbidden, source.casefold())

    def test_legacy_social_daily_is_plan_only_and_rejects_live(self) -> None:
        module = load_social_daily()
        commands = []

        def runner(command, check=False):
            commands.append(command)
            return types.SimpleNamespace(returncode=0)

        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(module.main(["--date", "2026-08-16"], runner=runner), 0)
        self.assertEqual(len(commands), 1)
        self.assertIn("--plan", commands[0])
        self.assertNotIn("--live", commands[0])
        commands.clear()
        with (
            self.assertRaises(SystemExit),
            contextlib.redirect_stderr(io.StringIO()),
        ):
            module.main(["--live"], runner=runner)
        self.assertEqual(commands, [], "invalid live flag must fail before subprocess/browser")

    def test_live_browser_authority_gate_remains_before_launch(self) -> None:
        source = TIKTOK_PUBLISHER.read_text(encoding="utf-8")
        start = source.index("def mode_post(")
        end = source.index("\ndef mode_plan(", start)
        body = source[start:end]
        self.assertLess(body.index("authorize_live_publication("), body.index("ctx = launch("))

    def test_plan_mode_short_circuits_before_playwright_import(self) -> None:
        source = TIKTOK_PUBLISHER.read_text(encoding="utf-8")
        main_start = source.index("def main(")
        main_body = source[main_start:]
        self.assertNotIn("from playwright", main_body)
        self.assertLess(main_body.index("if not a.live:"), main_body.index("return mode_post("))
        post_start = source.index("def mode_post(")
        post_end = source.index("\ndef mode_plan(", post_start)
        post_body = source[post_start:post_end]
        self.assertLess(post_body.index("if not live:"), post_body.index("from playwright.sync_api"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
