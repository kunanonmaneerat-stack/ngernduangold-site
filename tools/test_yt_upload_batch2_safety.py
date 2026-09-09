#!/usr/bin/env python3
"""Focused regression tests for the fail-closed YouTube live-upload gate."""

from __future__ import annotations

import copy
import hashlib
import io
import json
import tempfile
import unittest
from contextlib import nullcontext, redirect_stderr, redirect_stdout
from datetime import datetime, timedelta, timezone
from pathlib import Path
import sys
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools import yt_upload_batch2 as uploader
from tools.publication_authority import (
    content_source_sha256,
    media_qa_evidence_sha256,
)


BANGKOK = timezone(timedelta(hours=7))
CHECKED_AT = datetime(2026, 8, 16, 10, 0, tzinfo=BANGKOK)


def file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest().upper()


class LiveUploadGateTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory(prefix="yt_live_gate_")
        self.repo = Path(self.tmp.name)
        self.asset = self.repo / "reels" / "clip.mp4"
        self.asset.parent.mkdir(parents=True)
        self.asset.write_bytes(b"exact-approved-video-bytes")
        self.content_id = "content-20260816"
        self.placement_id = self.content_id + "__youtube_main"
        self.channel_id = "authorized-channel-fixture"
        self.nonce_counter = 0
        self.original_attempt_root = uploader.ATTEMPT_ROOT
        uploader.ATTEMPT_ROOT = (
            self.repo / ".local-private" / "runtime" / "publication-attempts"
        )
        self.ledger_claim_patcher = mock.patch.object(
            uploader.post_ledger,
            "claim",
            return_value=(True, "f" * 40, "claimed"),
        )
        self.ledger_confirm_patcher = mock.patch.object(
            uploader.post_ledger, "confirm"
        )
        self.ledger_claim = self.ledger_claim_patcher.start()
        self.ledger_confirm = self.ledger_confirm_patcher.start()
        self.receipt = self.repo / "automation-log" / "media-qa" / "clip.json"
        self.receipt.parent.mkdir(parents=True)
        self.receipt.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "asset": "reels/clip.mp4",
                    "sha256": file_hash(self.asset),
                    "media_type": "video",
                    "reviewed_at": "2026-08-16T09:00:00+07:00",
                    "media_origin": {
                        "generator_origin": "LOCAL_HTML_SVG_FFMPEG_WINDOWS_TTS",
                        "contains_flow_pixels": False,
                        "contains_flow_audio": False,
                        "synthid_expected": False,
                    },
                    "novelty_review": {
                        "status": "PASS",
                        "content_id": self.content_id,
                        "reviewer": "fixture-reviewer",
                    },
                    "human_audio_review": {
                        "status": "PASS",
                        "reviewer_is_human": True,
                        "reviewer_type": "OWNER",
                        "reviewer": "fixture-owner",
                        "asset_sha256": file_hash(self.asset),
                        "reviewed_at": "2026-08-16T09:00:00+07:00",
                    },
                    "watermark": {
                        "visual_review": {
                            "status": "PASS",
                            "reviewer": "fixture-human-reviewer",
                            "evidence": ["reels/clip.mp4"],
                            "evidence_sha256": {
                                "reels/clip.mp4": file_hash(self.asset),
                            },
                        },
                        "automated_scan": {"status": "PASS", "fps": 3.0},
                    },
                }
            ),
            encoding="utf-8",
        )
        self.plan = uploader.UploadPlan(
            date="2026-08-16",
            item={
                "id": self.content_id,
                "date": "2026-08-16",
                "status": "Scheduled",
                "publication_eligibility": "READY",
                "reel": "reels/clip.mp4",
                "captions": {"youtube": "Safe title\nSafe description"},
                "posted": {},
            },
            video_path=self.asset,
            relative_video_path="reels/clip.mp4",
            title="Safe title #Shorts",
            description="Safe title\nSafe description",
            publish_at="2026-08-16T12:00:00Z",
        )
        approved_hash = file_hash(self.asset)
        self.schedule = {
            self.plan.date: {
                "file": "clip.mp4",
                "content_id": self.content_id,
                "placement_id": self.placement_id,
                "qa_report": "automation-log/media-qa/clip.json",
                "approval": {
                    "qa": "PASS",
                    "publication": "APPROVED",
                    "privacy_gate": "PASS",
                    "publication_gate": "PASS",
                    "public_identity": "PASS",
                    "source_gate": "PASS",
                    "dedup": "PASS",
                    "approved_by": "owner",
                    "approved_at": "2026-08-16T09:00:00+07:00",
                    "source_checked_at": "2026-08-16T09:00:00+07:00",
                    "asset_sha256": approved_hash,
                },
            }
        }
        self.policy = {
            "publication_control": {"default_publication_authorized": False},
            "channels": {
                "youtube": {
                    "state": "active",
                    "publication_authorized": True,
                    "channel_id": self.channel_id,
                }
            },
        }
        self.roles = {
            "default": "deny",
            "actors": {
                "owner": {"social_publish": True},
                "cowork": {"social_publish": False},
            },
        }
        self.sources = {
            "checked_at": "2026-08-16T02:00:00+00:00",
            "errors": [],
            "changed": [],
            "review_required": [],
            "sources": [{"id": "official-source"}],
        }
        self.source_decision = {
            "allowed": True,
            "failures": [],
            "source_ids": ["official-source"],
            "registry_sha256": "",
        }
        for path, value in (
            (self.repo / ".system_control" / "policy.json", self.policy),
            (self.repo / ".system_control" / "role_capabilities.json", self.roles),
            (
                self.repo / ".system_control" / "generative_media_policy.json",
                {
                    "schema_version": 1,
                    "strict_no_watermark": True,
                    "google_flow": {
                        "role": "IDEATION_STORYBOARD_ONLY",
                        "final_pixels_allowed": False,
                        "final_audio_allowed": False,
                    },
                    "final_asset_required_fields": [
                        "generator_origin",
                        "contains_flow_pixels",
                        "contains_flow_audio",
                        "synthid_expected",
                    ],
                    "allowed_final_origins": [
                        "LOCAL_HTML_SVG_FFMPEG_WINDOWS_TTS"
                    ],
                },
            ),
        ):
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(value), encoding="utf-8")
        self.snapshot_path = (
            self.repo
            / "automation-log/knowledge-base/official-news-snapshot.json"
        )
        self.snapshot_path.parent.mkdir(parents=True, exist_ok=True)
        self.snapshot_path.write_text(json.dumps(self.sources), encoding="utf-8")
        self.registry_path = (
            self.repo / "automation-log/knowledge-base/social-source-registry.json"
        )
        self.registry_path.write_text(
            json.dumps({"fixture": "canonical-registry-bytes"}), encoding="utf-8"
        )
        self.source_decision["registry_sha256"] = hashlib.sha256(
            self.registry_path.read_bytes()
        ).hexdigest()
        self.sync_calendar([self.plan], self.schedule)

    def tearDown(self) -> None:
        self.ledger_confirm_patcher.stop()
        self.ledger_claim_patcher.stop()
        uploader.ATTEMPT_ROOT = self.original_attempt_root
        self.tmp.cleanup()

    def sync_calendar(self, plans, schedule) -> None:
        placements = []
        for selected in plans:
            row = schedule.get(selected.date, {}) if isinstance(schedule, dict) else {}
            slot = datetime.strptime(
                selected.publish_at, "%Y-%m-%dT%H:%M:%SZ"
            ).replace(tzinfo=timezone.utc).astimezone(BANGKOK)
            placements.append(
                {
                    "placement_id": row.get("placement_id") or self.placement_id,
                    "content_id": selected.item.get("id"),
                    "account": "youtube_main",
                    "date": slot.date().isoformat(),
                    "time": slot.strftime("%H:%M"),
                    "publication_authorized": True,
                }
            )
        path = self.repo / ".system_control" / "content_calendar.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(
                {
                    "schema_version": 2,
                    "timezone": "Asia/Bangkok",
                    "accounts": {
                        "youtube_main": {
                            "channel": "youtube",
                            "policy_channel": "youtube",
                        }
                    },
                    "placements": placements,
                }
            ),
            encoding="utf-8",
        )

    def mint_receipt(
        self,
        plan=None,
        *,
        placement_id=None,
        schedule_row=None,
        source_document=None,
        **overrides,
    ) -> str:
        selected = plan or self.plan
        selected_schedule = schedule_row or self.schedule[selected.date]
        selected_sources = source_document or self.sources
        selected_placement = placement_id or self.placement_id
        self.nonce_counter += 1
        nonce = f"yt-receipt-{self.nonce_counter:04d}-" + "x" * 48
        value = {
            "schema_version": 2,
            "content_id": selected.item["id"],
            "placement_id": selected_placement,
            "channel": "youtube",
            "target_identity": self.channel_id,
            "caption_sha256": hashlib.sha256(
                selected.description.encode("utf-8")
            ).hexdigest(),
            "asset_sha256": file_hash(selected.video_path),
            "scheduled_slot": selected.publish_at,
            "expires_at": "2026-08-17T00:00:00+00:00",
            "nonce": nonce,
            "policy_sha256": hashlib.sha256(
                (self.repo / ".system_control/policy.json").read_bytes()
            ).hexdigest(),
            "role_capabilities_sha256": hashlib.sha256(
                (self.repo / ".system_control/role_capabilities.json").read_bytes()
            ).hexdigest(),
            "content_calendar_sha256": hashlib.sha256(
                (self.repo / ".system_control/content_calendar.json").read_bytes()
            ).hexdigest(),
            "content_source_sha256": content_source_sha256(
                {
                    "manifest_item": selected.item,
                    "official_source_snapshot": selected_sources,
                    "source_ids": self.source_decision["source_ids"],
                    "source_registry_sha256": self.source_decision[
                        "registry_sha256"
                    ],
                    "source_file_sha256": {
                        "automation-log/knowledge-base/official-news-snapshot.json":
                            hashlib.sha256(self.snapshot_path.read_bytes()).hexdigest(),
                        "automation-log/knowledge-base/social-source-registry.json":
                            hashlib.sha256(self.registry_path.read_bytes()).hexdigest(),
                    },
                    "schedule_row": selected_schedule,
                    "source_files": [
                        ".system_control/content_manifest.json",
                        "automation-log/knowledge-base/official-news-snapshot.json",
                        "reels/schedule.json",
                    ],
                },
                selected_schedule.get("approval"),
            ),
            "media_qa_sha256": media_qa_evidence_sha256(
                self.receipt.read_bytes(),
                (
                    self.repo
                    / ".system_control/generative_media_policy.json"
                ).read_bytes(),
            ),
        }
        value.update(overrides)
        path = (
            self.repo
            / ".local-private/runtime/publication-receipts/pending"
            / f"{nonce}.json"
        )
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value), encoding="utf-8")
        return nonce

    def authorized_action(self, *, placement_id=None) -> dict:
        return {
            "content_id": self.content_id,
            "placement_id": placement_id or self.placement_id,
            "channel": "youtube",
            "target_identity": self.channel_id,
            "caption_sha256": hashlib.sha256(
                self.plan.description.encode("utf-8")
            ).hexdigest(),
            "asset_sha256": file_hash(self.asset),
            "scheduled_slot": self.plan.publish_at,
            "nonce": "consumed-" + "x" * 40,
            "consumed": True,
        }

    def gate(self, **overrides):
        plans = overrides.get("plans", [self.plan])
        schedule = overrides.get("schedule_document", self.schedule)
        sources = overrides.get("source_document", self.sources)
        self.snapshot_path.write_text(json.dumps(sources), encoding="utf-8")
        self.sync_calendar(plans, schedule)
        receipt_nonces = overrides.get("receipt_nonces")
        if receipt_nonces is None:
            receipt_nonces = {}
            for plan in plans:
                row = schedule.get(plan.date, {}) if isinstance(schedule, dict) else {}
                placement_id = row.get("placement_id") or self.placement_id
                receipt_nonces[plan.date] = self.mint_receipt(
                    plan,
                    placement_id=placement_id,
                    schedule_row=row,
                    source_document=sources,
                )
        values = {
            "plans": plans,
            "explicit_dates": True,
            "actor": "owner",
            "target_channel_id": self.channel_id,
            "receipt_nonces": receipt_nonces,
            "checked_at": CHECKED_AT,
            "repo": self.repo,
            "schedule_document": self.schedule,
            "policy_document": self.policy,
            "role_document": self.roles,
            "source_document": self.sources,
            "content_source_check": lambda *_args: copy.deepcopy(
                self.source_decision
            ),
            "privacy_check": lambda: 0,
            "media_guard": lambda _asset, _report, _repo: {
                "verdict": "PASS",
                "sha256": file_hash(self.asset),
                "findings": [],
            },
            "authority_guard_runner": lambda _relative: 0,
        }
        values.update(overrides)
        canonical_result = uploader.content_source_gate.SourceGateResult(
            True,
            self.content_id,
            tuple(self.source_decision["source_ids"]),
            (),
        )
        with (
            mock.patch.object(
                uploader.content_source_gate,
                "repo_content_source_contract",
                return_value=(self.registry_path, "fixture-library"),
            ),
            mock.patch.object(
                uploader.content_source_gate,
                "evaluate_content_source_gate",
                return_value=canonical_result,
            ),
        ):
            return uploader.validate_live_upload(**values)

    def test_exact_authorized_plan_passes_and_returns_bound_hash(self) -> None:
        result = self.gate()
        self.assertTrue(result[self.plan.date]["consumed"])
        self.assertEqual(
            result[self.plan.date]["asset_sha256"].upper(), file_hash(self.asset)
        )

    def test_live_requires_explicit_dates_and_actor(self) -> None:
        with self.assertRaisesRegex(uploader.SetupError, "explicit --dates"):
            self.gate(explicit_dates=False)
        with self.assertRaisesRegex(uploader.SetupError, "explicit actor"):
            self.gate(actor=None)

    def test_arg_parser_rejects_default_or_range_live_selection(self) -> None:
        for argv in (
            ["--live", "--actor", "owner"],
            ["--live", "--actor", "owner", "--from", "2026-08-16", "--to", "2026-08-17"],
            ["--live", "--actor", "owner", "--dates", "2026-08-16"],
            [
                "--live", "--actor", "owner", "--dates", "2026-08-16",
                "--target-channel-id", self.channel_id,
            ],
        ):
            with self.subTest(argv=argv), redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit) as raised:
                    uploader.parse_args(argv)
                self.assertEqual(raised.exception.code, 2)
        parsed = uploader.parse_args(
            [
                "--live", "--actor", "owner", "--dates", "2026-08-16",
                "--target-channel-id", self.channel_id,
                "--receipt-nonce", "2026-08-16=" + "x" * 40,
            ]
        )
        self.assertTrue(parsed.live)
        self.assertEqual(parsed.receipt_nonces, {"2026-08-16": "x" * 40})

    def test_local_target_identity_is_required_exact_and_redacted(self) -> None:
        for label, target, policy_mutator in (
            ("missing request", None, None),
            ("mismatch", "wrong-channel-fixture", None),
            ("missing policy", self.channel_id, "remove"),
        ):
            policy = copy.deepcopy(self.policy)
            if policy_mutator == "remove":
                policy["channels"]["youtube"].pop("channel_id")
            with self.subTest(label=label), self.assertRaises(uploader.SetupError) as raised:
                self.gate(target_channel_id=target, policy_document=policy)
            message = str(raised.exception)
            self.assertNotIn(self.channel_id, message)
            self.assertNotIn("wrong-channel-fixture", message)

    def test_authenticated_channel_identity_passes_only_one_exact_match(self) -> None:
        service = mock.Mock()
        request = service.channels.return_value.list.return_value
        request.execute.return_value = {"items": [{"id": self.channel_id}]}
        uploader.verify_authenticated_youtube_channel(service, self.channel_id)
        service.channels.return_value.list.assert_called_once_with(
            part="id", mine=True, maxResults=2
        )

        for label, response in (
            ("missing", {"items": []}),
            ("ambiguous", {"items": [{"id": self.channel_id}, {"id": "second"}]}),
            ("mismatch", {"items": [{"id": "wrong-channel-fixture"}]}),
            ("malformed", {"items": [{}]}),
        ):
            service = mock.Mock()
            service.channels.return_value.list.return_value.execute.return_value = response
            with self.subTest(label=label), self.assertRaises(uploader.SetupError) as raised:
                uploader.verify_authenticated_youtube_channel(service, self.channel_id)
            message = str(raised.exception)
            self.assertNotIn(self.channel_id, message)
            self.assertNotIn("wrong-channel-fixture", message)

    def test_authenticated_channel_lookup_failure_is_redacted(self) -> None:
        service = mock.Mock()
        service.channels.return_value.list.return_value.execute.side_effect = RuntimeError(
            "provider detail contains wrong-channel-fixture"
        )
        with self.assertRaises(uploader.SetupError) as raised:
            uploader.verify_authenticated_youtube_channel(service, self.channel_id)
        message = str(raised.exception)
        self.assertNotIn(self.channel_id, message)
        self.assertNotIn("wrong-channel-fixture", message)

    def test_historical_target_and_non_scheduled_status_are_blocked(self) -> None:
        old = copy.deepcopy(self.plan)
        object.__setattr__(old, "date", "2026-08-15")
        old.item["date"] = old.date
        old_schedule = {old.date: copy.deepcopy(self.schedule[self.plan.date])}
        with self.assertRaisesRegex(uploader.SetupError, "historical"):
            self.gate(plans=[old], schedule_document=old_schedule)

        for status in ("Backlog", "LegacyUnknown", "Posted", "Approved", "scheduled"):
            item = copy.deepcopy(self.plan.item)
            item["status"] = status
            plan = uploader.UploadPlan(**{**self.plan.__dict__, "item": item})
            with self.subTest(status=status), self.assertRaisesRegex(
                uploader.SetupError, "exactly Scheduled"
            ):
                self.gate(plans=[plan])

    def test_passed_or_too_close_slot_never_becomes_public(self) -> None:
        for publish_at in (
            "2026-08-16T02:59:00Z",
            "2026-08-16T03:10:00Z",
        ):
            plan = uploader.UploadPlan(
                **{**self.plan.__dict__, "publish_at": publish_at}
            )
            with self.subTest(publish_at=publish_at), self.assertRaisesRegex(
                uploader.SetupError, "fresh owner-approved slot"
            ):
                self.gate(plans=[plan])
            with mock.patch.object(uploader, "datetime") as clock:
                clock.now.return_value = CHECKED_AT.astimezone(timezone.utc)
                clock.strptime.side_effect = datetime.strptime
                with self.assertRaisesRegex(uploader.SetupError, "immediate public fallback"):
                    uploader.upload_body(plan)

        mismatched_title = uploader.UploadPlan(
            **{**self.plan.__dict__, "title": "Different outward title #Shorts"}
        )
        with self.assertRaisesRegex(uploader.SetupError, "title.*captions.youtube"):
            self.gate(plans=[mismatched_title])

    def test_publication_eligibility_is_explicit_and_duplicate_blocks(self) -> None:
        for eligibility in (None, "", "BLOCKED_DUPLICATE", "BLOCKED_POLICY", "RETIRED"):
            item = copy.deepcopy(self.plan.item)
            if eligibility is None:
                item.pop("publication_eligibility", None)
            else:
                item["publication_eligibility"] = eligibility
            plan = uploader.UploadPlan(**{**self.plan.__dict__, "item": item})
            with self.subTest(eligibility=eligibility), self.assertRaisesRegex(
                uploader.SetupError, "publication_eligibility"
            ):
                self.gate(plans=[plan])

        for eligibility in ("ALLOWED", "READY", " ready "):
            item = copy.deepcopy(self.plan.item)
            item["publication_eligibility"] = eligibility
            plan = uploader.UploadPlan(**{**self.plan.__dict__, "item": item})
            with self.subTest(eligibility=eligibility):
                action = self.gate(plans=[plan])[plan.date]
                self.assertEqual(action["asset_sha256"].upper(), file_hash(self.asset))

    def test_exact_schedule_content_and_asset_are_required(self) -> None:
        wrong_id = copy.deepcopy(self.schedule)
        wrong_id[self.plan.date]["content_id"] = "another-content"
        with self.assertRaisesRegex(uploader.SetupError, "content_id"):
            self.gate(schedule_document=wrong_id)

        wrong_asset = copy.deepcopy(self.schedule)
        wrong_asset[self.plan.date]["file"] = "other.mp4"
        with self.assertRaisesRegex(uploader.SetupError, "schedule asset"):
            self.gate(schedule_document=wrong_asset)

        with self.assertRaisesRegex(uploader.SetupError, "exact schedule row"):
            self.gate(schedule_document={})

        missing_placement = copy.deepcopy(self.schedule)
        missing_placement[self.plan.date].pop("placement_id")
        with self.assertRaisesRegex(uploader.SetupError, "placement_id"):
            self.gate(schedule_document=missing_placement)

    def test_policy_role_privacy_and_source_fail_closed(self) -> None:
        policy = copy.deepcopy(self.policy)
        policy["channels"]["youtube"]["publication_authorized"] = False
        with self.assertRaisesRegex(uploader.SetupError, "publication_authorized"):
            self.gate(policy_document=policy)

        with self.assertRaisesRegex(uploader.SetupError, "social_publish"):
            self.gate(actor="cowork")

        with self.assertRaisesRegex(uploader.SetupError, "Privacy gate"):
            self.gate(privacy_check=lambda: 2)

        unrelated_pending = copy.deepcopy(self.sources)
        unrelated_pending["review_required"] = ["unrelated-source"]
        self.assertIn(
            self.plan.date,
            self.gate(source_document=unrelated_pending),
        )

        relevant = copy.deepcopy(self.source_decision)
        relevant["allowed"] = False
        relevant["failures"] = [
            "relevant official source review is pending: official-source"
        ]
        with self.assertRaisesRegex(
            uploader.SetupError, "relevant official source review is pending"
        ):
            self.gate(content_source_check=lambda *_args: relevant)

        malformed = copy.deepcopy(self.source_decision)
        malformed["source_ids"] = []
        with self.assertRaisesRegex(uploader.SetupError, "source IDs"):
            self.gate(content_source_check=lambda *_args: malformed)

        forged = copy.deepcopy(self.source_decision)
        forged["source_ids"] = ["not-in-canonical-registry"]
        forged["registry_sha256"] = "b" * 64
        with self.assertRaisesRegex(uploader.SetupError, "exactly match canonical"):
            self.gate(content_source_check=lambda *_args: forged)

    def test_source_snapshot_drift_blocks_pre_mutation_execution(self) -> None:
        action = self.gate()[self.plan.date]
        empty_binding = copy.deepcopy(action)
        empty_binding["content_source_file_sha256"] = {}
        with self.assertRaisesRegex(
            uploader.PublicationBlocked, "file bindings are missing"
        ):
            uploader.verify_execution_authorization(
                repo=self.repo,
                action=empty_binding,
                caption=self.plan.description,
                asset_sha256=file_hash(self.asset),
                media_qa_path=action["media_qa_path"],
                now=CHECKED_AT,
            )

        unrelated_binding = copy.deepcopy(action)
        unrelated_binding["content_source_file_sha256"] = {
            ".system_control/policy.json": hashlib.sha256(
                (self.repo / ".system_control/policy.json").read_bytes()
            ).hexdigest()
        }
        with self.assertRaisesRegex(
            uploader.PublicationBlocked, "consumed authorization"
        ):
            uploader.verify_execution_authorization(
                repo=self.repo,
                action=unrelated_binding,
                caption=self.plan.description,
                asset_sha256=file_hash(self.asset),
                media_qa_path=action["media_qa_path"],
                now=CHECKED_AT,
            )

        self.snapshot_path.write_text(
            json.dumps({**self.sources, "changed": ["post-authorization-drift"]}),
            encoding="utf-8",
        )
        with self.assertRaisesRegex(
            uploader.PublicationBlocked, "content-source evidence file hash"
        ):
            uploader.verify_execution_authorization(
                repo=self.repo,
                action=action,
                caption=self.plan.description,
                asset_sha256=file_hash(self.asset),
                media_qa_path=action["media_qa_path"],
                now=CHECKED_AT,
            )

    def test_every_piece_approval_field_and_owner_are_required(self) -> None:
        for field in (
            "qa",
            "publication",
            "privacy_gate",
            "publication_gate",
            "public_identity",
            "source_gate",
            "dedup",
        ):
            schedule = copy.deepcopy(self.schedule)
            schedule[self.plan.date]["approval"][field] = "BLOCKED"
            with self.subTest(field=field), self.assertRaisesRegex(
                uploader.SetupError, r"approval\." + field
            ):
                self.gate(schedule_document=schedule)

        not_owner = copy.deepcopy(self.schedule)
        not_owner[self.plan.date]["approval"]["approved_by"] = "cowork"
        with self.assertRaisesRegex(uploader.SetupError, "approved_by"):
            self.gate(schedule_document=not_owner)

        no_source_time = copy.deepcopy(self.schedule)
        no_source_time[self.plan.date]["approval"].pop("source_checked_at")
        with self.assertRaisesRegex(uploader.SetupError, "source_checked_at"):
            self.gate(schedule_document=no_source_time)

    def test_private_receipt_is_required_replay_safe_and_exactly_bound(self) -> None:
        with self.assertRaisesRegex(uploader.SetupError, "private receipt"):
            self.gate(receipt_nonces={})

        nonce = self.mint_receipt()
        action = self.gate(receipt_nonces={self.plan.date: nonce})[self.plan.date]
        self.assertTrue(action["consumed"])
        with self.assertRaisesRegex(uploader.SetupError, "replay"):
            self.gate(receipt_nonces={self.plan.date: nonce})

        mismatch_cases = (
            ("channel", {"channel": "facebook"}),
            ("target", {"target_identity": "wrong-channel-fixture"}),
            ("content", {"content_id": "other-content"}),
            ("placement", {"placement_id": "other__youtube_main"}),
            ("caption", {"caption_sha256": "0" * 64}),
            ("asset", {"asset_sha256": "1" * 64}),
            ("slot", {"scheduled_slot": "2026-08-16T12:01:00Z"}),
            ("nonce", {"nonce": "different-" + "z" * 40}),
        )
        for label, mutation in mismatch_cases:
            with self.subTest(label=label):
                bad_nonce = self.mint_receipt(**mutation)
                with self.assertRaisesRegex(uploader.SetupError, "binding|receipt"):
                    self.gate(receipt_nonces={self.plan.date: bad_nonce})

    def test_hash_media_receipt_and_content_id_are_exact(self) -> None:
        wrong_hash = copy.deepcopy(self.schedule)
        wrong_hash[self.plan.date]["approval"]["asset_sha256"] = "0" * 64
        with self.assertRaisesRegex(uploader.SetupError, "asset_sha256"):
            self.gate(schedule_document=wrong_hash)

        with self.assertRaisesRegex(uploader.SetupError, "media_publish_guard blocked"):
            self.gate(media_guard=lambda *_args: {
                "verdict": "FAIL", "sha256": file_hash(self.asset), "findings": ["watermark"]
            })

        forged_hash = "A" * 64
        forged_approval = copy.deepcopy(self.schedule)
        forged_approval[self.plan.date]["approval"]["asset_sha256"] = forged_hash
        with self.assertRaisesRegex(uploader.SetupError, "does not match asset bytes"):
            self.gate(
                schedule_document=forged_approval,
                media_guard=lambda *_args: {
                    "verdict": "PASS", "sha256": forged_hash, "findings": []
                },
            )

        self.receipt.write_text(
            json.dumps({"novelty_review": {"content_id": "wrong-content"}}),
            encoding="utf-8",
        )
        with self.assertRaisesRegex(uploader.SetupError, "receipt content_id"):
            self.gate()

    def test_default_media_publish_guard_is_called_with_exact_asset_and_receipt(self) -> None:
        result = {
            "verdict": "PASS",
            "sha256": file_hash(self.asset),
            "findings": [],
        }
        with mock.patch.object(
            uploader, "_run_media_publish_guard", return_value=result
        ) as media_guard:
            self.assertEqual(
                self.gate(media_guard=None)[self.plan.date]["asset_sha256"].upper(),
                file_hash(self.asset),
            )
        media_guard.assert_called_once_with(
            self.asset, self.receipt.resolve(), self.repo.resolve()
        )

    def test_gate_failure_precedes_upload_log_credentials_and_network(self) -> None:
        with (
            mock.patch.object(
                uploader,
                "validate_live_upload",
                side_effect=uploader.SetupError("blocked fixture"),
            ),
            mock.patch.object(uploader, "load_upload_log", return_value={}) as upload_log,
            mock.patch.object(uploader, "get_credentials") as credentials,
            redirect_stdout(io.StringIO()),
        ):
            code = uploader.run_live(
                {"items": [self.plan.item]},
                [self.plan],
                1,
                explicit_dates=True,
                actor="owner",
                target_channel_id=self.channel_id,
                receipt_nonces={self.plan.date: "x" * 40},
                checked_at=CHECKED_AT,
            )
        self.assertEqual(code, 1)
        upload_log.assert_called_once_with()
        credentials.assert_not_called()

    def test_remote_identity_mismatch_precedes_media_upload(self) -> None:
        service = mock.Mock()
        service.channels.return_value.list.return_value.execute.return_value = {
            "items": [{"id": "wrong-channel-fixture"}]
        }
        build = mock.Mock(return_value=service)
        media_upload = mock.Mock()
        libraries = (mock.Mock(), mock.Mock(), mock.Mock(), build, Exception, media_upload)
        with (
            mock.patch.object(
                uploader,
                "validate_live_upload",
                return_value={
                    self.plan.date: {
                        "asset_sha256": file_hash(self.asset),
                        "placement_id": self.placement_id,
                        "consumed": True,
                    }
                },
            ),
            mock.patch.object(uploader, "load_upload_log", return_value={}),
            mock.patch.object(uploader, "get_credentials", return_value=(object(), libraries)),
            redirect_stdout(io.StringIO()) as output,
        ):
            code = uploader.run_live(
                {"items": [self.plan.item]},
                [self.plan],
                1,
                explicit_dates=True,
                actor="owner",
                target_channel_id=self.channel_id,
                receipt_nonces={self.plan.date: "x" * 40},
                checked_at=CHECKED_AT,
            )
        self.assertEqual(code, 1)
        media_upload.assert_not_called()
        service.videos.assert_not_called()
        self.assertNotIn(self.channel_id, output.getvalue())
        self.assertNotIn("wrong-channel-fixture", output.getvalue())

    def test_remote_success_is_terminal_before_legacy_log_crash(self) -> None:
        class FakeHttpError(Exception):
            pass

        service = mock.Mock()
        build = mock.Mock(return_value=service)
        libraries = (
            mock.Mock(), mock.Mock(), mock.Mock(), build, FakeHttpError, mock.Mock()
        )
        action = self.authorized_action()
        with (
            mock.patch.object(
                uploader,
                "validate_live_upload",
                return_value={self.plan.date: action},
            ),
            mock.patch.object(uploader, "load_upload_log", return_value={}),
            mock.patch.object(uploader, "get_credentials", return_value=(object(), libraries)),
            mock.patch.object(uploader, "verify_authenticated_youtube_channel"),
            mock.patch.object(
                uploader,
                "verify_execution_authorization",
                return_value={"verified": True},
            ),
            mock.patch.object(
                uploader.media_publish_guard,
                "publication_corpus_claim",
                side_effect=lambda *_args, **_kwargs: nullcontext(),
            ),
            mock.patch.object(uploader, "publishes_in_the_past", return_value=False),
            mock.patch.object(
                uploader, "resumable_upload", return_value={"id": "AbCdEf12345"}
            ) as remote_upload,
            mock.patch.object(
                uploader, "write_json", side_effect=OSError("simulated disk crash")
            ),
            redirect_stdout(io.StringIO()),
        ):
            code = uploader.run_live(
                {"items": [self.plan.item]},
                [self.plan],
                1,
                explicit_dates=True,
                actor="owner",
                target_channel_id=self.channel_id,
                receipt_nonces={self.plan.date: "x" * 40},
                checked_at=CHECKED_AT,
            )
        self.assertEqual(code, 1)
        remote_upload.assert_called_once()
        _pending, terminal = uploader._attempt_paths(self.placement_id)
        terminal_value = json.loads(terminal.read_text(encoding="utf-8"))
        self.assertEqual(terminal_value["status"], "POSTED")
        self.assertEqual(terminal_value["remote_platform_id"], "AbCdEf12345")
        self.ledger_confirm.assert_called_once_with(
            "f" * 40, post_id="AbCdEf12345", status="POSTED"
        )
        with self.assertRaisesRegex(Exception, "reconciliation-only"):
            uploader._assert_reconciliation_clear(self.placement_id)

    def test_remote_ambiguity_becomes_unknown_and_blocks_retry(self) -> None:
        class FakeHttpError(Exception):
            pass

        service = mock.Mock()
        libraries = (
            mock.Mock(), mock.Mock(), mock.Mock(), mock.Mock(return_value=service),
            FakeHttpError, mock.Mock(),
        )
        action = self.authorized_action()
        with (
            mock.patch.object(
                uploader,
                "validate_live_upload",
                return_value={self.plan.date: action},
            ),
            mock.patch.object(uploader, "load_upload_log", return_value={}),
            mock.patch.object(uploader, "get_credentials", return_value=(object(), libraries)),
            mock.patch.object(uploader, "verify_authenticated_youtube_channel"),
            mock.patch.object(
                uploader,
                "verify_execution_authorization",
                return_value={"verified": True},
            ),
            mock.patch.object(
                uploader.media_publish_guard,
                "publication_corpus_claim",
                side_effect=lambda *_args, **_kwargs: nullcontext(),
            ),
            mock.patch.object(uploader, "publishes_in_the_past", return_value=False),
            mock.patch.object(
                uploader,
                "resumable_upload",
                side_effect=ConnectionResetError("ambiguous connection reset"),
            ) as remote_upload,
            redirect_stdout(io.StringIO()),
        ):
            code = uploader.run_live(
                {"items": [self.plan.item]},
                [self.plan],
                1,
                explicit_dates=True,
                actor="owner",
                target_channel_id=self.channel_id,
                receipt_nonces={self.plan.date: "x" * 40},
                checked_at=CHECKED_AT,
            )
        self.assertEqual(code, 1)
        remote_upload.assert_called_once()
        _pending, terminal = uploader._attempt_paths(self.placement_id)
        terminal_value = json.loads(terminal.read_text(encoding="utf-8"))
        self.assertEqual(terminal_value["status"], "UNKNOWN")
        self.assertIsNone(terminal_value["remote_platform_id"])
        with self.assertRaisesRegex(Exception, "reconciliation-only"):
            uploader._assert_reconciliation_clear(self.placement_id)

    def test_dry_plan_keeps_historical_non_scheduled_compatibility(self) -> None:
        item = copy.deepcopy(self.plan.item)
        item["status"] = "Backlog"
        old_targets = uploader.TARGET_DATES
        uploader.TARGET_DATES = (self.plan.date,)
        try:
            with mock.patch.object(uploader, "ROOT", self.repo):
                plans = uploader.build_plans([item])
        finally:
            uploader.TARGET_DATES = old_targets
        self.assertEqual(len(plans), 1)
        self.assertEqual(plans[0].item["status"], "Backlog")

    def test_immutable_upload_buffer_is_hash_bound_and_source_independent(self) -> None:
        original = self.asset.read_bytes()
        expected = file_hash(self.asset)
        stream, actual = uploader._hash_bound_upload_buffer(self.asset, expected)
        try:
            self.assertEqual(actual, expected)
            self.asset.write_bytes(b"replacement-after-snapshot")
            self.assertEqual(stream.read(), original)
        finally:
            stream.close()
        self.assertTrue(stream.closed)
        with self.assertRaisesRegex(
            uploader.PublicationBlocked, "do not match authority"
        ):
            uploader._hash_bound_upload_buffer(self.asset, expected)

    def test_atomic_claim_failure_precedes_attempt_media_and_upload(self) -> None:
        class FakeHttpError(Exception):
            pass

        service = mock.Mock()
        build = mock.Mock(return_value=service)
        media_upload = mock.Mock()
        libraries = (
            mock.Mock(), mock.Mock(), mock.Mock(), build, FakeHttpError, media_upload
        )
        action = self.authorized_action()
        remote_upload = mock.Mock(side_effect=AssertionError("upload crossed claim gate"))
        with (
            mock.patch.object(
                uploader, "validate_live_upload",
                return_value={self.plan.date: action},
            ),
            mock.patch.object(uploader, "load_upload_log", return_value={}),
            mock.patch.object(uploader, "get_credentials", return_value=(object(), libraries)),
            mock.patch.object(uploader, "verify_authenticated_youtube_channel"),
            mock.patch.object(
                uploader, "verify_execution_authorization",
                return_value={"verified": True},
            ),
            mock.patch.object(
                uploader.post_ledger, "claim",
                return_value=(False, "", "GAP: fixture"),
            ),
            mock.patch.object(uploader, "resumable_upload", remote_upload),
            redirect_stdout(io.StringIO()),
        ):
            code = uploader.run_live(
                {"items": [self.plan.item]}, [self.plan], 1,
                explicit_dates=True, actor="owner",
                target_channel_id=self.channel_id,
                receipt_nonces={self.plan.date: "x" * 40},
                checked_at=CHECKED_AT,
            )
        self.assertEqual(code, 1)
        media_upload.assert_not_called()
        remote_upload.assert_not_called()
        pending, terminal = uploader._attempt_paths(self.placement_id)
        self.assertFalse(pending.exists())
        self.assertFalse(terminal.exists())

    def test_source_order_uses_buffer_claim_and_confirm_boundaries(self) -> None:
        source = (ROOT / "tools" / "yt_upload_batch2.py").read_text(encoding="utf-8")
        start = source.index("def run_live(")
        end = source.index("\ndef main()", start)
        body = source[start:end]
        snapshot = body.index("_hash_bound_upload_buffer(")
        claim = body.index("post_ledger.claim(", snapshot)
        begin = body.index("_begin_attempt(", claim)
        media = body.index("media = MediaFileUpload(", begin)
        request = body.index("request = service.videos().insert(", media)
        corpus_claim = body.index(
            "with media_publish_guard.publication_corpus_claim(", request
        )
        upload = body.index("response = resumable_upload(", request)
        finish = body.index("_finish_attempt(", upload)
        confirm = body.index("post_ledger.confirm(", finish)
        registry = body.index("write_json(UPLOAD_LOG_PATH", confirm)
        self.assertLess(snapshot, claim)
        self.assertLess(claim, begin)
        self.assertLess(begin, media)
        self.assertLess(media, request)
        self.assertLess(request, corpus_claim)
        self.assertLess(corpus_claim, upload)
        self.assertLess(upload, finish)
        self.assertLess(finish, confirm)
        self.assertLess(confirm, registry)
        self.assertIn("upload_buffer, mimetype=", body[media:request])
        self.assertNotIn("MediaFileUpload(\n                str(plan.video_path)", body)
        self.assertIn("upload_buffer.close()", body)


if __name__ == "__main__":
    unittest.main(verbosity=2)
