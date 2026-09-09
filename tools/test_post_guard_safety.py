#!/usr/bin/env python3
"""Regression tests for post_guard's mutation and policy safety boundaries."""

from __future__ import annotations

import argparse
import contextlib
import io
import json
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
import post_guard as PG  # noqa: E402
import yt_upload_batch2 as YT  # noqa: E402


TARGET = date(2026, 8, 16)
CHECKED_AT = PG.datetime(2026, 8, 16, 9, 0, tzinfo=PG.BANGKOK)
CHANNEL_ID = "youtube-channel-test-fixture"
RECEIPT_NONCE = "receipt-" + "x" * 40


def youtube_policy(*, state="active", publication_authorized=True):
    return {
        "state": state,
        "publication_authorized": publication_authorized,
        "channel_id": CHANNEL_ID,
    }


@contextlib.contextmanager
def authorized_repair_fixture():
    """Create one exact, locally approved schedule row; no external calls."""
    with tempfile.TemporaryDirectory(prefix="_post_guard_test_", dir=PG.REELS_DIR) as tmp:
        directory = Path(tmp)
        asset = directory / "clip.mp4"
        asset.write_bytes(b"local-test-asset")
        relative_asset = f"{directory.name}/clip.mp4"
        item = {
            "id": "approved-content-id",
            "date": TARGET.isoformat(),
            "reel": f"reels/{relative_asset}",
            "captions": {},
        }
        schedule = {
            TARGET.isoformat(): {
                "file": relative_asset,
                "content_id": item["id"],
                "approval": {
                    "qa": "PASS",
                    "publication": "APPROVED",
                    "privacy_gate": "PASS",
                    "publication_gate": "PASS",
                    "approved_by": "unit-test-owner",
                    "approved_at": "2026-08-16T08:00:00+07:00",
                },
            }
        }
        yield item, schedule


class CliSafetyTests(unittest.TestCase):
    def test_repair_requires_explicit_date(self) -> None:
        with mock.patch.object(sys, "argv", ["post_guard.py", "--repair-youtube"]):
            with contextlib.redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit) as raised:
                    PG.parse_args()
        self.assertEqual(raised.exception.code, 2)

    def test_repair_requires_private_receipt_nonce(self) -> None:
        with mock.patch.object(
            sys,
            "argv",
            [
                "post_guard.py",
                "--repair-youtube",
                "--date",
                TARGET.isoformat(),
                "--actor",
                "owner",
            ],
        ):
            with contextlib.redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit) as raised:
                    PG.parse_args()
        self.assertEqual(raised.exception.code, 2)

    def test_json_default_never_calls_live_repair(self) -> None:
        args = argparse.Namespace(
            date=TARGET.isoformat(),
            target_date=TARGET,
            check_tomorrow=False,
            json=True,
            repair_youtube=False,
            actor=None,
            receipt_nonce=None,
        )
        item = {"date": TARGET.isoformat(), "captions": {}}
        safe = PG.result("TEST", "OK", "local fixture")
        with (
            mock.patch.object(PG, "parse_args", return_value=args),
            mock.patch.object(PG, "load_channel_policy", return_value={"state": "retired"}),
            mock.patch.object(PG, "load_manifest", return_value=[item]),
            mock.patch.object(PG, "load_upload_log", return_value={}),
            mock.patch.object(
                PG,
                "run_youtube_recovery",
                side_effect=AssertionError("default mode attempted a live repair"),
            ) as repair,
            mock.patch.object(PG, "check_youtube", return_value=safe),
            mock.patch.object(PG, "check_instagram", return_value=safe),
            mock.patch.object(PG, "check_facebook", return_value=safe),
            mock.patch.object(PG, "check_facebook_comment", return_value=safe),
            mock.patch.object(PG, "check_tiktok", return_value=safe),
            mock.patch.object(PG, "check_threads", return_value=safe),
            mock.patch.object(PG, "write_outputs", return_value=PG.ROOT / "status-test.md"),
            contextlib.redirect_stdout(io.StringIO()),
        ):
            self.assertEqual(PG.main(), 0)
        repair.assert_not_called()


class PublicationRecommendationTests(unittest.TestCase):
    @mock.patch.object(PG.content_source_gate, "evaluate_repo_content_source_gate")
    def test_authority_gate_fails_closed_for_role_privacy_and_source(
        self, canonical_source_gate
    ) -> None:
        canonical_source_gate.return_value = PG.content_source_gate.SourceGateResult(
            True, "kn-test", ("official-fixture",), ()
        )
        with tempfile.TemporaryDirectory(prefix="_publication_gate_", dir=PG.ROOT) as tmp:
            directory = Path(tmp)
            roles_path = directory / "roles.json"
            source_path = directory / "sources.json"
            roles = {
                "actors": {
                    "cowork": {"social_publish": False},
                    "owner": {"social_publish": True},
                }
            }
            clean_source = {
                "checked_at": CHECKED_AT.isoformat(),
                "errors": [],
                "changed": [],
                "review_required": [],
                "sources": [{"id": "official-fixture"}],
            }
            authorized_channel = {
                "state": "active",
                "publication_authorized": True,
            }
            roles_path.write_text(json.dumps(roles), encoding="utf-8")
            source_path.write_text(json.dumps(clean_source), encoding="utf-8")

            privacy = mock.Mock(return_value=0)
            allowed, reason = PG.evaluate_publication_authority(
                CHECKED_AT,
                "cowork",
                channel="facebook",
                content_id="kn-test",
                channel_policy=authorized_channel,
                role_path=roles_path,
                source_path=source_path,
                privacy_check=privacy,
                content_source_check=lambda *_: (True, "exact source passed"),
            )
            self.assertFalse(allowed)
            self.assertIn("social_publish", reason)
            privacy.assert_not_called()

            allowed, reason = PG.evaluate_publication_authority(
                CHECKED_AT,
                "owner",
                channel="facebook",
                content_id="kn-test",
                channel_policy=authorized_channel,
                role_path=roles_path,
                source_path=source_path,
                privacy_check=lambda: 1,
                content_source_check=lambda *_: (True, "exact source passed"),
            )
            self.assertFalse(allowed)
            self.assertIn("privacy", reason)

            pending_source = {**clean_source, "review_required": ["pending-source"]}
            source_path.write_text(json.dumps(pending_source), encoding="utf-8")
            allowed, reason = PG.evaluate_publication_authority(
                CHECKED_AT,
                "owner",
                channel="facebook",
                content_id="kn-test",
                channel_policy=authorized_channel,
                role_path=roles_path,
                source_path=source_path,
                privacy_check=lambda: 0,
                content_source_check=lambda *_: (True, "exact source passed"),
            )
            self.assertTrue(allowed, reason)

            source_path.write_text(json.dumps(clean_source), encoding="utf-8")
            allowed, reason = PG.evaluate_publication_authority(
                CHECKED_AT.replace(tzinfo=None),
                "owner",
                channel="facebook",
                content_id="kn-test",
                channel_policy=authorized_channel,
                role_path=roles_path,
                source_path=source_path,
                privacy_check=lambda: 0,
                content_source_check=lambda *_: (True, "exact source passed"),
            )
            self.assertFalse(allowed)
            self.assertIn("timezone", reason)

            allowed, reason = PG.evaluate_publication_authority(
                CHECKED_AT,
                "owner",
                channel="facebook",
                content_id="kn-test",
                channel_policy=authorized_channel,
                role_path=roles_path,
                source_path=source_path,
                privacy_check=lambda: 0,
                content_source_check=lambda *_: (
                    False, "kn-test: relevant official source review is pending"
                ),
            )
            self.assertFalse(allowed)
            self.assertIn("relevant", reason)

            allowed, reason = PG.evaluate_publication_authority(
                CHECKED_AT,
                "owner",
                channel="facebook",
                content_id=None,
                channel_policy=authorized_channel,
                role_path=roles_path,
                source_path=source_path,
                privacy_check=lambda: 0,
                content_source_check=lambda *_: (True, "exact source passed"),
            )
            self.assertFalse(allowed)
            self.assertIn("content_id", reason)

            for blocked_policy, expected in (
                ({"state": "active", "publication_authorized": False}, "publication_authorized"),
                ({"state": "paused", "publication_authorized": True}, "paused"),
            ):
                with self.subTest(policy=blocked_policy):
                    privacy = mock.Mock(return_value=0)
                    allowed, reason = PG.evaluate_publication_authority(
                        CHECKED_AT,
                        "owner",
                        channel="facebook",
                        content_id="kn-test",
                        channel_policy=blocked_policy,
                        role_path=roles_path,
                        source_path=source_path,
                        privacy_check=privacy,
                        content_source_check=lambda *_: (True, "exact source passed"),
                    )
                    self.assertFalse(allowed)
                    self.assertIn(expected, reason)
                    privacy.assert_not_called()

    def test_facebook_and_threads_never_recommend_mutation_when_blocked(self) -> None:
        blocked_gates = (
            (False, "actor cowork has no current social_publish authority"),
            (False, "privacy gate is blocked"),
            (False, "official-source review is pending"),
        )
        for gate in blocked_gates:
            with self.subTest(reason=gate[1]):
                with (
                    mock.patch.object(PG, "fb_log_candidates", return_value=[]),
                    mock.patch.object(PG, "ledger_evidence", return_value=("failed", {"note": "old failure"})),
                    mock.patch.object(PG, "public_profile_page") as fetch,
                ):
                    facebook = PG.check_facebook(TARGET, None, gate)
                    threads = PG.check_threads(TARGET, None, gate)
                for verdict in (facebook, threads):
                    self.assertEqual(verdict["status"], "PUBLICATION-BLOCKED")
                    self.assertEqual(verdict["action"], PG.PUBLICATION_BLOCKED_ACTION)
                    self.assertTrue(verdict["action"].startswith("Report the delivery gap only"))
                fetch.assert_not_called()


class YoutubeRepairTests(unittest.TestCase):
    def test_repair_passes_one_exact_target_to_live_helper(self) -> None:
        completed = SimpleNamespace(returncode=0, stdout="", stderr="")
        with authorized_repair_fixture() as (item, schedule):
            with (
                mock.patch.object(PG, "quota_likely_available", return_value=True),
                mock.patch.object(PG, "upload_token_is_safe_to_use", return_value=True),
                mock.patch.object(
                    PG,
                    "evaluate_publication_authority",
                    return_value=(True, "authorized fixture"),
                ),
                mock.patch.object(PG.shutil, "which", return_value="python.exe"),
                mock.patch.object(PG.subprocess, "run", return_value=completed) as run,
            ):
                message = PG.run_youtube_recovery(
                    TARGET,
                    CHECKED_AT,
                    item=item,
                    youtube_policy=youtube_policy(),
                    schedule=schedule,
                    actor="owner",
                    receipt_nonce=RECEIPT_NONCE,
                )

        command = run.call_args.args[0]
        self.assertEqual(command[0], "python.exe")
        self.assertEqual(command[1], str(PG.ROOT / "tools" / "yt_upload_batch2.py"))
        parsed = YT.parse_args(command[2:])
        self.assertTrue(parsed.live)
        self.assertEqual(parsed.target_channel_id, CHANNEL_ID)
        self.assertEqual(parsed.dates, TARGET.isoformat())
        self.assertEqual(
            parsed.receipt_nonces, {TARGET.isoformat(): RECEIPT_NONCE}
        )
        self.assertIn(TARGET.isoformat(), message)

    def test_repair_nonzero_exit_fails_closed(self) -> None:
        completed = SimpleNamespace(returncode=7, stdout="", stderr="upload failed")
        with authorized_repair_fixture() as (item, schedule):
            with (
                mock.patch.object(PG, "quota_likely_available", return_value=True),
                mock.patch.object(PG, "upload_token_is_safe_to_use", return_value=True),
                mock.patch.object(
                    PG,
                    "evaluate_publication_authority",
                    return_value=(True, "authorized fixture"),
                ),
                mock.patch.object(PG.shutil, "which", return_value="python.exe"),
                mock.patch.object(PG.subprocess, "run", return_value=completed),
            ):
                with self.assertRaises(PG.YouTubeRepairError):
                    PG.run_youtube_recovery(
                        TARGET,
                        CHECKED_AT,
                        item=item,
                        youtube_policy=youtube_policy(),
                        schedule=schedule,
                        actor="owner",
                        receipt_nonce=RECEIPT_NONCE,
                    )

    def test_repair_global_authority_blocks_before_token_or_subprocess(self) -> None:
        with authorized_repair_fixture() as (item, schedule):
            with (
                mock.patch.object(
                    PG,
                    "evaluate_publication_authority",
                    return_value=(False, "privacy gate is blocked"),
                ),
                mock.patch.object(PG, "quota_likely_available") as quota,
                mock.patch.object(PG, "upload_token_is_safe_to_use") as token,
                mock.patch.object(PG.subprocess, "run") as run,
            ):
                with self.assertRaisesRegex(PG.YouTubeRepairError, "privacy gate"):
                    PG.run_youtube_recovery(
                        TARGET,
                        CHECKED_AT,
                        item=item,
                        youtube_policy=youtube_policy(),
                        schedule=schedule,
                        actor="owner",
                        receipt_nonce=RECEIPT_NONCE,
                    )
            quota.assert_not_called()
            token.assert_not_called()
            run.assert_not_called()

    def test_repair_authorization_gates_run_before_subprocess(self) -> None:
        with authorized_repair_fixture() as (item, schedule):
            cases = []
            cases.append(
                (
                    "inactive policy",
                    item,
                    schedule,
                    youtube_policy(state="paused"),
                    CHECKED_AT,
                )
            )
            cases.append(
                (
                    "publication not authorized",
                    item,
                    schedule,
                    youtube_policy(publication_authorized=False),
                    CHECKED_AT,
                )
            )
            missing_id = {
                TARGET.isoformat(): {**schedule[TARGET.isoformat()], "content_id": None}
            }
            cases.append(
                (
                    "missing exact content_id",
                    item,
                    missing_id,
                    youtube_policy(),
                    CHECKED_AT,
                )
            )
            missing_asset = {**item, "reel": "reels/does-not-exist.mp4"}
            cases.append(
                (
                    "missing manifest asset",
                    missing_asset,
                    schedule,
                    youtube_policy(),
                    CHECKED_AT,
                )
            )
            no_approval = {
                TARGET.isoformat(): {
                    key: value
                    for key, value in schedule[TARGET.isoformat()].items()
                    if key != "approval"
                }
            }
            cases.append(
                (
                    "missing approval record",
                    item,
                    no_approval,
                    youtube_policy(),
                    CHECKED_AT,
                )
            )
            cases.append(
                (
                    "historical target",
                    item,
                    schedule,
                    youtube_policy(),
                    PG.datetime(2026, 8, 17, 9, 0, tzinfo=PG.BANGKOK),
                )
            )
            for name, case_item, case_schedule, policy, checked_at in cases:
                with self.subTest(name=name):
                    with mock.patch.object(PG.subprocess, "run") as run:
                        with self.assertRaises(PG.YouTubeRepairError):
                            PG.run_youtube_recovery(
                                TARGET,
                                checked_at,
                                item=case_item,
                                youtube_policy=policy,
                                schedule=case_schedule,
                                actor="owner",
                                receipt_nonce=RECEIPT_NONCE,
                            )
                    run.assert_not_called()

    def test_each_approval_and_publication_gate_is_explicit(self) -> None:
        with authorized_repair_fixture() as (item, schedule):
            good_row = schedule[TARGET.isoformat()]
            for field in ("qa", "publication", "privacy_gate", "publication_gate"):
                with self.subTest(field=field):
                    bad_approval = {**good_row["approval"], field: "BLOCKED"}
                    bad_schedule = {
                        TARGET.isoformat(): {**good_row, "approval": bad_approval}
                    }
                    with mock.patch.object(PG.subprocess, "run") as run:
                        with self.assertRaisesRegex(PG.YouTubeRepairError, field):
                            PG.run_youtube_recovery(
                                TARGET,
                                CHECKED_AT,
                                item=item,
                                youtube_policy=youtube_policy(),
                                schedule=bad_schedule,
                                actor="owner",
                                receipt_nonce=RECEIPT_NONCE,
                            )
                    run.assert_not_called()

    def test_success_without_exact_upload_log_entry_fails_closed(self) -> None:
        args = argparse.Namespace(
            date=TARGET.isoformat(),
            target_date=TARGET,
            check_tomorrow=False,
            json=True,
            repair_youtube=True,
            actor="owner",
            receipt_nonce=RECEIPT_NONCE,
        )
        item = {"date": TARGET.isoformat(), "captions": {}}
        def channel_policy(channel: str):
            return {"state": "active" if channel == "youtube" else "retired"}

        with (
            mock.patch.object(PG, "parse_args", return_value=args),
            mock.patch.object(PG, "load_channel_policy", side_effect=channel_policy),
            mock.patch.object(PG, "load_manifest", return_value=[item]),
            mock.patch.object(PG, "load_upload_log", side_effect=[{}, {}]),
            mock.patch.object(PG, "load_reel_schedule", return_value={}),
            mock.patch.object(PG, "run_youtube_recovery", return_value="exit 0"),
            contextlib.redirect_stderr(io.StringIO()),
        ):
            self.assertEqual(PG.main(), 2)


class InstagramPolicyTests(unittest.TestCase):
    def test_paused_stays_paused_after_review_date_without_external_check(self) -> None:
        with (
            mock.patch.object(PG, "ig_artifact_matches") as artifacts,
            mock.patch.object(PG, "ig_workflow_configured") as workflow,
        ):
            verdict = PG.check_instagram(
                date(2026, 8, 26),
                None,
                {"state": "paused", "until": "2026-08-25"},
            )
        self.assertEqual(verdict["status"], "PAUSED")
        self.assertIn("never reactivates", verdict["evidence"])
        artifacts.assert_not_called()
        workflow.assert_not_called()

    def test_missing_or_unknown_policy_fails_closed_without_external_check(self) -> None:
        with (
            mock.patch.object(
                PG,
                "load_channel_policy",
                side_effect=PG.GuardSetupError("missing policy"),
            ),
            mock.patch.object(PG, "ig_artifact_matches") as artifacts,
        ):
            missing = PG.check_instagram(TARGET, None)
        self.assertEqual(missing["status"], "FAIL")
        artifacts.assert_not_called()

        with mock.patch.object(PG, "ig_artifact_matches") as artifacts:
            unknown = PG.check_instagram(TARGET, None, {"state": "mystery"})
        self.assertEqual(unknown["status"], "FAIL")
        artifacts.assert_not_called()


class TiktokPolicyTests(unittest.TestCase):
    def test_retired_is_permanent_and_does_not_fetch(self) -> None:
        with mock.patch.object(PG, "public_profile_page") as fetch:
            verdict = PG.check_tiktok(
                date(2030, 1, 1),
                None,
                CHECKED_AT,
                {"state": "retired", "until": "2026-08-06"},
            )
        self.assertEqual(verdict["status"], "RETIRED")
        self.assertEqual(verdict["action"], "-")
        fetch.assert_not_called()

    def test_testing_blocked_is_local_plan_only_and_does_not_fetch(self) -> None:
        with mock.patch.object(PG, "public_profile_page") as fetch:
            verdict = PG.check_tiktok(
                TARGET,
                None,
                CHECKED_AT,
                {
                    "state": "testing_blocked",
                    "auto": False,
                    "automation_capable": False,
                    "publication_authorized": False,
                },
            )
        self.assertEqual(verdict["status"], "TESTING-BLOCKED")
        self.assertIn("do not schedule or publish", verdict["action"])
        fetch.assert_not_called()

    def test_unknown_state_fails_closed_without_fetch(self) -> None:
        with mock.patch.object(PG, "public_profile_page") as fetch:
            verdict = PG.check_tiktok(TARGET, None, CHECKED_AT, {"state": "mystery"})
        self.assertEqual(verdict["status"], "FAIL")
        self.assertIn(verdict["status"], PG.ACTION_REQUIRED)
        fetch.assert_not_called()

    def test_missing_and_malformed_policy_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory(prefix="post_guard_policy_", dir=PG.ROOT) as tmp:
            missing = Path(tmp) / "missing.json"
            with mock.patch.object(PG, "POLICY_PATH", missing):
                with self.assertRaises(PG.GuardSetupError):
                    PG.load_channel_policy("tiktok")

            malformed = Path(tmp) / "policy.json"
            malformed.write_text("{not-json", encoding="utf-8")
            with mock.patch.object(PG, "POLICY_PATH", malformed):
                with self.assertRaises(PG.GuardSetupError):
                    PG.load_channel_policy("tiktok")

            malformed.write_text(
                '{"channels":{"tiktok":{"state":"mystery"}}}',
                encoding="utf-8",
            )
            with mock.patch.object(PG, "POLICY_PATH", malformed):
                with self.assertRaises(PG.GuardSetupError):
                    PG.load_channel_policy("tiktok")

    def test_main_policy_failure_stops_before_all_checks_and_repairs(self) -> None:
        args = argparse.Namespace(
            date=TARGET.isoformat(),
            target_date=TARGET,
            check_tomorrow=False,
            json=True,
            repair_youtube=True,
            actor="owner",
            receipt_nonce=RECEIPT_NONCE,
        )
        with (
            mock.patch.object(PG, "parse_args", return_value=args),
            mock.patch.object(
                PG,
                "load_channel_policy",
                side_effect=PG.GuardSetupError("Policy not found"),
            ),
            mock.patch.object(PG, "load_manifest") as manifest,
            mock.patch.object(PG, "run_youtube_recovery") as repair,
            contextlib.redirect_stderr(io.StringIO()),
        ):
            self.assertEqual(PG.main(), 2)
        manifest.assert_not_called()
        repair.assert_not_called()


if __name__ == "__main__":
    unittest.main(verbosity=2)
