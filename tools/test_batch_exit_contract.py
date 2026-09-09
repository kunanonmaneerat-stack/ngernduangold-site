#!/usr/bin/env python3
"""Static/read-only contract tests for the daily and weekly Windows batch runners.

The test reads source text only. It never executes either ``.cmd`` file and never
creates, deletes, or modifies an alert.
"""

from __future__ import annotations

import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
DAILY = ROOT / "pipeline" / "run_daily.cmd"
WEEKLY = ROOT / "pipeline" / "run_weekly.cmd"

EXPECTED_STEPS = {
    DAILY: {
        "required": {
            "comply_gate_stitch.py",
            "automation_policy_guard.py",
            "privacy_guard.py",
            "public_identity_guard.py",
            "manifest_contract.py",
            "dispatcher.py",
            "daily_content.py",
            "ga4_pull.py",
            "improvement_loop.py",
            "fb_queue_linkcheck.py",
            "daily_media_gate.py",
            "traffic_analyst.py",
            "post_agent.py",
            "credit_tracker.py",
            "dashboard_agent.py",
            "hermes_digest.py",
            "cc_monitor.py",
            "test_preflight_checks.py",
        },
        "graded": {
            "uptime_check.py",
            "agent_gap_check.py",
            "content_calendar_guard.py",
            "posting_kit.py",
            "preflight.py",
        },
    },
    WEEKLY: {
        "required": {
            "comply_gate_stitch.py",
            "ga4_pull.py",
            "gsc_pull.py",
            "weekly_growth_review.py",
            "improvement_loop.py",
        },
        "graded": {"official_news_monitor.py", "content_calendar_guard.py"},
    },
}


def source(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def active_lines(text: str) -> list[str]:
    lines = []
    for raw in text.splitlines():
        stripped = raw.strip()
        lowered = stripped.casefold()
        if not stripped or lowered.startswith("rem ") or stripped.startswith("::"):
            continue
        lines.append(stripped)
    return lines


def normalized(line: str) -> str:
    return re.sub(r"\s+", " ", line.strip()).casefold()


def label_body(lines: list[str], label: str) -> list[str]:
    wanted = ":" + label.casefold()
    start = next(i for i, line in enumerate(lines) if line.casefold() == wanted)
    body = []
    for line in lines[start + 1 :]:
        if line.startswith(":"):
            break
        body.append(line)
    return body


def step_lines(lines: list[str], mode: str) -> list[str]:
    prefixes = ["call :" + mode.casefold() + " "]
    if mode.casefold() == "required":
        prefixes.append("call :novelty_queue ")
    return [
        line for line in lines
        if normalized(line).startswith(tuple(prefixes))
    ]


class BatchExitContractTests(unittest.TestCase):
    def test_windows_runners_use_crlf_only(self) -> None:
        for path in (DAILY, WEEKLY):
            with self.subTest(path=path.name):
                raw = path.read_bytes()
                bare_lf = [
                    index for index, byte in enumerate(raw)
                    if byte == 0x0A and (index == 0 or raw[index - 1] != 0x0D)
                ]
                self.assertEqual(bare_lf, [], "cmd.exe may misparse mixed/LF-only runners")

    def test_runners_enable_delayed_expansion_and_initialize_accumulator(self) -> None:
        for path in (DAILY, WEEKLY):
            with self.subTest(path=path.name):
                lines = active_lines(source(path))
                lowered = [normalized(line) for line in lines]
                self.assertIn("setlocal enableextensions enabledelayedexpansion", lowered)
                self.assertIn("set run_exit=0", lowered)

    def test_required_and_graded_labels_preserve_exit_contract(self) -> None:
        for path in (DAILY, WEEKLY):
            with self.subTest(path=path.name):
                lines = active_lines(source(path))
                required = [normalized(line) for line in label_body(lines, "required")]
                graded = [normalized(line) for line in label_body(lines, "graded")]

                self.assertIn("set step_rc=!errorlevel!", required)
                self.assertIn("if !step_rc! geq 3 set run_exit=3", required)
                self.assertIn(
                    "if !step_rc! equ 2 if !run_exit! lss 2 set run_exit=2",
                    required,
                )
                self.assertIn(
                    "if !step_rc! equ 1 if !run_exit! lss 2 set run_exit=2",
                    required,
                )
                self.assertIn("exit /b !step_rc!", required)

                self.assertIn("set step_rc=!errorlevel!", graded)
                self.assertIn("if !step_rc! geq 3 set run_exit=3", graded)
                self.assertIn(
                    "if !step_rc! equ 2 if !run_exit! lss 2 set run_exit=2",
                    graded,
                )
                self.assertIn(
                    "if !step_rc! equ 1 if !run_exit! lss 1 set run_exit=1",
                    graded,
                )
                self.assertIn("exit /b !step_rc!", graded)

    def test_every_active_python_invocation_is_routed_through_a_contract_label(self) -> None:
        for path in (DAILY, WEEKLY):
            with self.subTest(path=path.name):
                lines = active_lines(source(path))
                main = lines[: next(i for i, line in enumerate(lines) if line.casefold() == ":required")]
                python_steps = [line for line in main if re.search(r"\.py(?:\"|\s|$)", line, re.I)]
                self.assertTrue(python_steps, "runner has no active Python steps")
                violations = [
                    line
                    for line in python_steps
                    if not normalized(line).startswith((
                        "call :required ", "call :novelty_queue ",
                        "call :graded ",
                    ))
                ]
                self.assertEqual(violations, [], "unrouted critical invocation(s)")

    def test_expected_critical_steps_keep_their_required_or_graded_route(self) -> None:
        for path, expected in EXPECTED_STEPS.items():
            with self.subTest(path=path.name):
                lines = active_lines(source(path))
                for mode in ("required", "graded"):
                    routed = step_lines(lines, mode)
                    for script in expected[mode]:
                        matches = [line for line in routed if script.casefold() in line.casefold()]
                        self.assertEqual(
                            len(matches),
                            1,
                            f"{script} must appear exactly once through :{mode}",
                        )

    def test_agent_gap_alert_writer_is_explicit_only_in_scheduled_runner(self) -> None:
        lines = active_lines(source(DAILY))
        invocations = [
            normalized(line) for line in lines
            if line.startswith("call :graded ") and "agent_gap_check.py" in line
        ]
        self.assertEqual(len(invocations), 1)
        self.assertIn("--update-agent-silent-alert-file", invocations[0])

    def test_main_flow_returns_accumulated_exit_code(self) -> None:
        for path in (DAILY, WEEKLY):
            with self.subTest(path=path.name):
                lines = active_lines(source(path))
                label_index = next(i for i, line in enumerate(lines) if line.casefold() == ":abort")
                main = [normalized(line) for line in lines[:label_index]]
                self.assertEqual(main[-1], "exit /b !run_exit!")
                self.assertEqual(main.count("exit /b !run_exit!"), 1)

    def test_sealed_terminal_classification_overrides_batch_accumulator(self) -> None:
        for path in (DAILY, WEEKLY):
            with self.subTest(path=path.name):
                lines = [normalized(line) for line in active_lines(source(path))]
                for label in ("end", "abort"):
                    close = next(
                        index for index, line in enumerate(lines)
                        if line.startswith('call :close_receipt "%s"' % label)
                    )
                    tail = lines[close + 1:close + 8]
                    self.assertEqual(tail[0], "set close_rc=!errorlevel!")
                    self.assertIn(
                        "if !close_rc! equ 2 if !run_exit! lss 2 set run_exit=2",
                        tail,
                    )
                    self.assertIn(
                        "if !close_rc! neq 0 if !close_rc! neq 2 (", tail
                    )
                    self.assertIn("set run_exit=3", tail)

    def test_required_failures_abort_before_downstream_consumers(self) -> None:
        for path in (DAILY, WEEKLY):
            with self.subTest(path=path.name):
                lines = active_lines(source(path))
                abort_index = next(i for i, line in enumerate(lines) if line.casefold() == ":abort")
                main = lines[:abort_index]
                ordinary = [
                    normalized(line)
                    for line in main
                    if normalized(line).startswith("call :required ")
                    and "daily_media_gate.py" not in line.casefold()
                    and "test_preflight_checks.py" not in line.casefold()
                    and "post_agent.py" not in line.casefold()
                    and "automation_policy_guard.py" not in line.casefold()
                    and "improvement_loop.py" not in line.casefold()
                    and "ga4_pull.py" not in line.casefold()
                    and "gsc_pull.py" not in line.casefold()
                    and "fb_queue_linkcheck.py" not in line.casefold()
                    and "dispatcher.py" not in line.casefold()
                    and "daily_content.py" not in line.casefold()
                ]
                self.assertTrue(ordinary)
                self.assertTrue(all(line.endswith("|| goto :abort") for line in ordinary))

                abort_body = [normalized(line) for line in label_body(lines, "abort")]
                self.assertIn("if !run_exit! lss 2 set run_exit=2", abort_body)
                self.assertIn("exit /b !run_exit!", abort_body)

    def test_novelty_skip_and_unknown_block_have_distinct_exit_contracts(self) -> None:
        lines = [normalized(line) for line in active_lines(source(DAILY))]
        for script, rc_var in (
            ("dispatcher.py", "dispatcher_rc"),
            ("daily_content.py", "daily_content_rc"),
        ):
            index = next(
                i for i, line in enumerate(lines)
                if line.startswith("call :novelty_queue ") and script in line
            )
            self.assertEqual(
                lines[index - 1], 'set "step_contract=novelty-queue-v1"'
            )
            self.assertFalse(lines[index].endswith("|| goto :abort"))
            self.assertEqual(lines[index + 1], f"set {rc_var}=!errorlevel!")
            self.assertIn(f"if !{rc_var}! equ 10", lines[index + 2])
            self.assertIn("novelty_exhausted - skip", lines[index + 2])
            self.assertIn(f"if !{rc_var}! equ 20", lines[index + 3])
            self.assertIn("blocked_unknown", lines[index + 3])
            self.assertEqual(
                lines[index + 4],
                f"if !{rc_var}! neq 0 if !{rc_var}! neq 10 "
                f"if !{rc_var}! neq 20 goto :abort",
            )

        wrapper = [normalized(line) for line in label_body(
            active_lines(source(DAILY)), "novelty_queue"
        )]
        self.assertTrue(any(
            "--wrapper required --contract" in line for line in wrapper
        ))
        self.assertIn("if !step_rc! equ 10 exit /b 10", wrapper)
        self.assertIn("if !step_rc! equ 20 (", wrapper)
        self.assertIn(
            "if !run_exit! lss 2 set run_exit=2", wrapper
        )
        self.assertIn("exit /b 20", wrapper)
        self.assertIn("if !step_rc! neq 0 (", wrapper)
        self.assertIn("set run_exit=3", wrapper)
        self.assertIn('set "abort_reason=step_unclassified"', wrapper)
        self.assertIn("exit /b !step_rc!", wrapper)

    def test_blocked_post_queue_keeps_read_only_monitoring_tail_alive(self) -> None:
        lines = active_lines(source(DAILY))
        normalized_lines = [normalized(line) for line in lines]
        queue_index = next(
            i for i, line in enumerate(normalized_lines)
            if line.startswith("call :required ") and "post_agent.py" in line
        )
        self.assertFalse(normalized_lines[queue_index].endswith("|| goto :abort"))
        self.assertEqual(normalized_lines[queue_index + 1], "set post_queue_rc=!errorlevel!")
        self.assertIn("completed_blocked", normalized_lines[queue_index + 2])
        for script in (
            "credit_tracker.py", "dashboard_agent.py", "posting_kit.py",
            "hermes_digest.py", "cc_monitor.py", "test_preflight_checks.py",
            "preflight.py",
        ):
            monitor_index = next(
                i for i, line in enumerate(normalized_lines)
                if script in line and line.startswith(("call :required ", "call :graded "))
            )
            self.assertGreater(monitor_index, queue_index, script)

    def test_expected_safety_and_decision_blocks_keep_diagnostics_alive(self) -> None:
        lines = active_lines(source(DAILY))
        normalized_lines = [normalized(line) for line in lines]
        for script, rc_var, marker in (
            ("automation_policy_guard.py", "automation_policy_rc", "completed_blocked"),
            ("improvement_loop.py", "improvement_rc", "completed_blocked"),
        ):
            index = next(
                i for i, line in enumerate(normalized_lines)
                if line.startswith("call :required ") and script in line
            )
            self.assertFalse(normalized_lines[index].endswith("|| goto :abort"))
            self.assertEqual(normalized_lines[index + 1], f"set {rc_var}=!errorlevel!")
            self.assertIn(marker, normalized_lines[index + 2])
            self.assertIn("continues", normalized_lines[index + 2])
        preflight_index = next(
            i for i, line in enumerate(normalized_lines)
            if line.startswith("call :graded ") and "preflight.py" in line
        )
        self.assertGreater(
            preflight_index,
            next(i for i, line in enumerate(normalized_lines)
                 if line.startswith("call :required ") and "improvement_loop.py" in line),
        )
        weekly_lines = [normalized(line) for line in active_lines(source(WEEKLY))]
        weekly_index = next(
            i for i, line in enumerate(weekly_lines)
            if line.startswith("call :required ") and "improvement_loop.py" in line
        )
        self.assertFalse(weekly_lines[weekly_index].endswith("|| goto :abort"))
        self.assertEqual(weekly_lines[weekly_index + 1], "set improvement_rc=!errorlevel!")
        self.assertIn("completed_blocked", weekly_lines[weekly_index + 2])
        close_index = next(
            i for i, line in enumerate(weekly_lines)
            if line.startswith('call :close_receipt "end"')
        )
        exit_index = next(
            i for i, line in enumerate(weekly_lines[close_index:], close_index)
            if line == "exit /b !run_exit!"
        )
        self.assertGreater(close_index, weekly_index + 2)
        self.assertGreater(exit_index, close_index)

    def test_measurement_failures_do_not_blind_independent_safety_and_repair_steps(self) -> None:
        daily = [normalized(line) for line in active_lines(source(DAILY))]
        daily_ga4 = next(
            i for i, line in enumerate(daily)
            if line.startswith("call :required ") and "ga4_pull.py" in line
        )
        self.assertFalse(daily[daily_ga4].endswith("|| goto :abort"))
        self.assertEqual(daily[daily_ga4 + 1], "set ga4_pull_rc=!errorlevel!")
        self.assertIn("completed_blocked", daily[daily_ga4 + 2])
        self.assertIn("continues", daily[daily_ga4 + 2])
        for script in (
            "fb_queue_linkcheck.py", "daily_media_gate.py", "improvement_loop.py", "dashboard_agent.py",
            "test_preflight_checks.py", "preflight.py",
        ):
            index = next(
                i for i, line in enumerate(daily)
                if script in line and line.startswith(("call :required ", "call :graded "))
            )
            self.assertGreater(index, daily_ga4, script)

        linkcheck = next(
            i for i, line in enumerate(daily)
            if line.startswith("call :required ") and "fb_queue_linkcheck.py" in line
        )
        self.assertFalse(daily[linkcheck].endswith("|| goto :abort"))
        self.assertEqual(daily[linkcheck + 1], "set fb_linkcheck_rc=!errorlevel!")
        self.assertIn("completed_blocked", daily[linkcheck + 2])
        self.assertIn("continues", daily[linkcheck + 2])
        media = next(
            i for i, line in enumerate(daily)
            if line.startswith("call :required ") and "daily_media_gate.py" in line
        )
        self.assertGreater(media, linkcheck)

        weekly = [normalized(line) for line in active_lines(source(WEEKLY))]
        weekly_ga4 = next(
            i for i, line in enumerate(weekly)
            if line.startswith("call :required ") and "ga4_pull.py" in line
        )
        weekly_gsc = next(
            i for i, line in enumerate(weekly)
            if line.startswith("call :required ") and "gsc_pull.py" in line
        )
        self.assertFalse(weekly[weekly_ga4].endswith("|| goto :abort"))
        self.assertEqual(weekly[weekly_ga4 + 1], "set ga4_pull_rc=!errorlevel!")
        self.assertIn("independent gsc refresh continues", weekly[weekly_ga4 + 2])
        self.assertGreater(weekly_gsc, weekly_ga4)
        self.assertFalse(weekly[weekly_gsc].endswith("|| goto :abort"))
        self.assertEqual(weekly[weekly_gsc + 1], "set gsc_pull_rc=!errorlevel!")
        self.assertIn("diagnostics continue", weekly[weekly_gsc + 2])
        loop = next(i for i, line in enumerate(weekly) if "improvement_loop.py" in line)
        self.assertGreater(loop, weekly_gsc)

    def test_media_qa_alert_is_written_on_failure_and_removed_only_on_pass(self) -> None:
        lines = active_lines(source(DAILY))
        normalized_lines = [normalized(line) for line in lines]
        qa_index = next(
            i
            for i, line in enumerate(normalized_lines)
            if line.startswith("call :required ") and "daily_media_gate.py" in line
        )
        self.assertEqual(normalized_lines[qa_index + 1], "set watermark_rc=!errorlevel!")

        alert_lines = [
            line
            for line in normalized_lines
            if "watermark-alert.md" in line
        ]
        failure_writes = [
            line
            for line in alert_lines
            if "if !watermark_rc! geq 1" in line and ">" in line and " del " not in line
        ]
        pass_deletes = [
            line
            for line in alert_lines
            if "if !watermark_rc! equ 0" in line and " if exist " in line and " del " in line
        ]
        unsafe_deletes = [line for line in alert_lines if " del " in line and line not in pass_deletes]

        self.assertEqual(len(failure_writes), 1, "failure must create/preserve the alert")
        self.assertEqual(len(pass_deletes), 1, "only a clean pass may remove the alert")
        self.assertEqual(unsafe_deletes, [], "failure/unknown state must never delete the alert")
        self.assertLess(
            normalized_lines.index(failure_writes[0]),
            normalized_lines.index(pass_deletes[0]),
        )

    def test_verified_media_block_keeps_independent_evidence_tail_alive(self) -> None:
        lines = [normalized(line) for line in active_lines(source(DAILY))]
        media = next(
            i for i, line in enumerate(lines)
            if line.startswith("call :required ") and "daily_media_gate.py" in line
        )
        self.assertEqual(lines[media - 1], 'set "step_contract=block-on-2-v1"')
        conditional_abort = next(
            line for line in lines[media + 1:media + 12]
            if "watermark_rc" in line and "goto :abort" in line
        )
        self.assertIn("neq 0", conditional_abort)
        self.assertIn("neq 2", conditional_abort)
        for script in (
            "improvement_loop.py", "dashboard_agent.py",
            "test_preflight_checks.py", "preflight.py",
        ):
            tail = next(
                i for i, line in enumerate(lines)
                if line.startswith(("call :required ", "call :graded "))
                and script in line
            )
            self.assertGreater(tail, media, script)

    def test_daily_media_gate_replaces_the_two_narrow_staging_globs(self) -> None:
        lines = active_lines(source(DAILY))
        active = "\n".join(normalized(line) for line in lines)
        self.assertNotIn(r"_vidout\clean\*.mp4", active)
        self.assertNotIn(r"_social-stage\_final_*.mp4", active)
        self.assertIn("daily_media_gate.py", active)

    def test_calendar_guard_runs_before_generation_or_metric_consumers(self) -> None:
        daily = [normalized(line) for line in active_lines(source(DAILY))]
        weekly = [normalized(line) for line in active_lines(source(WEEKLY))]

        daily_calendar = next(i for i, line in enumerate(daily) if "content_calendar_guard.py" in line)
        daily_generation = next(i for i, line in enumerate(daily) if "dispatcher.py" in line)
        self.assertLess(daily_calendar, daily_generation)

        weekly_calendar = next(i for i, line in enumerate(weekly) if "content_calendar_guard.py" in line)
        weekly_metrics = next(i for i, line in enumerate(weekly) if "ga4_pull.py" in line)
        self.assertLess(weekly_calendar, weekly_metrics)

    def test_calendar_blocked_states_continue_but_runner_failure_aborts(self) -> None:
        for path, downstream_script in ((DAILY, "dispatcher.py"), (WEEKLY, "ga4_pull.py")):
            with self.subTest(path=path.name):
                lines = [normalized(line) for line in active_lines(source(path))]
                calendar = next(
                    i for i, line in enumerate(lines)
                    if line.startswith("call :graded ") and "content_calendar_guard.py" in line
                )
                self.assertEqual(lines[calendar + 1], "set calendar_rc=!errorlevel!")
                self.assertIn("if !calendar_rc! equ 1", lines[calendar + 2])
                self.assertIn("completed_blocked", lines[calendar + 2])
                self.assertIn("monitoring continues", lines[calendar + 2])
                self.assertIn("if !calendar_rc! equ 2", lines[calendar + 3])
                self.assertIn("content calendar blocked", lines[calendar + 3])
                self.assertIn("monitoring continues", lines[calendar + 3])
                self.assertIn("if !calendar_rc! geq 3", lines[calendar + 4])
                self.assertIn("runner_failed", lines[calendar + 4])
                self.assertEqual(lines[calendar + 5], "if !calendar_rc! geq 3 goto :abort")
                downstream = next(
                    i for i, line in enumerate(lines)
                    if downstream_script in line
                    and line.startswith((
                        "call :required ", "call :novelty_queue ",
                        "call :graded ",
                    ))
                )
                self.assertGreater(downstream, calendar + 5)

    def test_posting_kit_contract_skips_missing_legacy_plan_without_hiding_true_errors(self) -> None:
        lines = [normalized(line) for line in active_lines(source(DAILY))]
        posting_kit = next(
            i for i, line in enumerate(lines)
            if line.startswith("call :graded ") and "posting_kit.py" in line
        )
        self.assertIn("--allow-missing-legacy-plan", lines[posting_kit])
        self.assertEqual(lines[posting_kit + 1], "set posting_kit_rc=!errorlevel!")
        self.assertIn("if !posting_kit_rc! equ 1", lines[posting_kit + 2])
        self.assertIn("review_required", lines[posting_kit + 2])
        self.assertIn("monitoring continues", lines[posting_kit + 2])
        self.assertEqual(lines[posting_kit + 3], "if !posting_kit_rc! geq 2 goto :abort")
        digest = next(i for i, line in enumerate(lines) if "hermes_digest.py" in line)
        self.assertGreater(digest, posting_kit + 3)

    def test_official_news_exit_one_is_review_required_not_error(self) -> None:
        lines = [normalized(line) for line in active_lines(source(WEEKLY))]
        monitor = next(
            i for i, line in enumerate(lines)
            if line.startswith("call :graded ") and "official_news_monitor.py" in line
        )
        self.assertEqual(lines[monitor + 1], "set official_news_rc=!errorlevel!")
        self.assertIn("if !official_news_rc! equ 1", lines[monitor + 2])
        self.assertIn("review_required", lines[monitor + 2])
        self.assertNotIn(" error ", " " + lines[monitor + 2] + " ")
        self.assertIn("if !official_news_rc! equ 2", lines[monitor + 3])
        self.assertIn("blocked", lines[monitor + 3])
        self.assertIn("if !official_news_rc! geq 3", lines[monitor + 4])
        self.assertIn("runner_failed", lines[monitor + 4])


if __name__ == "__main__":
    unittest.main(verbosity=2)
