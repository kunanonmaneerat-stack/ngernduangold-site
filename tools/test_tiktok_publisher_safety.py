#!/usr/bin/env python3
"""Adversarial regression tests for the retired TikTok Studio publisher.

These tests never open a browser, upload a file, or make a network request.  They
exercise the public CLI dispatcher and each local live gate with Playwright imports
and browser launch replaced by tripwires.
"""

from __future__ import annotations

import builtins
import contextlib
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
PUBLISHER = ROOT / "social-autopost" / "publish_tiktok.py"
KNOWN_PLAN_DATE = "2026-07-11"
KNOWN_CLIP = ROOT / "reels" / "2026-08-16_b4-p01.mp4"
KNOWN_RECEIPT = "automation-log/media-qa/b4-p01-video.json"


def load_publisher():
    spec = importlib.util.spec_from_file_location("tiktok_publisher_safety_fixture", PUBLISHER)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class SafetyBlocked(RuntimeError):
    pass


class TikTokPublisherSafetyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.publisher = load_publisher()

    def block_playwright_import(self):
        real_import = builtins.__import__

        def guarded(name, *args, **kwargs):
            if name == "playwright" or name.startswith("playwright."):
                raise AssertionError("Playwright import crossed a local-only boundary")
            return real_import(name, *args, **kwargs)

        return mock.patch("builtins.__import__", side_effect=guarded)

    def test_default_plan_is_read_only_and_never_launches_or_uploads(self) -> None:
        launch = mock.Mock(side_effect=AssertionError("browser launch attempted"))
        with (
            mock.patch.object(self.publisher, "launch", launch),
            self.block_playwright_import(),
            contextlib.redirect_stdout(io.StringIO()),
        ):
            self.assertEqual(
                self.publisher.main(["--date", KNOWN_PLAN_DATE]), 0
            )
            self.assertEqual(
                self.publisher.main(["--plan", "--date", KNOWN_PLAN_DATE]), 0
            )
            # A direct legacy call with live=False must also short-circuit to plan.
            self.assertEqual(
                self.publisher.mode_post(object(), KNOWN_PLAN_DATE, False), 0
            )
        launch.assert_not_called()

    def test_legacy_login_and_check_flags_fail_without_browser(self) -> None:
        launch = mock.Mock(side_effect=AssertionError("browser launch attempted"))
        with (
            mock.patch.object(self.publisher, "launch", launch),
            self.block_playwright_import(),
            contextlib.redirect_stdout(io.StringIO()),
        ):
            self.assertEqual(self.publisher.main(["--login"]), 2)
            self.assertEqual(self.publisher.main(["--check"]), 2)
        launch.assert_not_called()

    def test_missing_plan_is_a_nonzero_failure_without_browser(self) -> None:
        launch = mock.Mock(side_effect=AssertionError("browser launch attempted"))
        with (
            mock.patch.object(self.publisher, "launch", launch),
            self.block_playwright_import(),
            contextlib.redirect_stdout(io.StringIO()),
        ):
            self.assertEqual(
                self.publisher.main(["--date", "2099-01-01"]), 2
            )
            self.assertEqual(
                self.publisher.main(["--plan", "--date", "2099-01-01"]), 2
            )
        launch.assert_not_called()

    def live_fixture(self, temp: str):
        digest = hashlib.sha256(KNOWN_CLIP.read_bytes()).hexdigest().upper()
        today = self.publisher.now_th().date().isoformat()
        entry = {
            "clipFile": KNOWN_CLIP.name,
            "contentId": "b4-p01",
            "placementId": "b4-p01__tiktok_main",
            "scheduledSlot": self.publisher.now_th().replace(
                hour=20, minute=0, second=0, microsecond=0
            ).isoformat(),
            "mediaReceipt": KNOWN_RECEIPT,
            "tiktokCaption": (
                "ข้อความทดสอบที่ไม่เผยแพร่\n"
                "ข้อมูลเพื่อการศึกษา ไม่ใช่คำแนะนำทางการเงิน · ผลิตด้วย AI"
            ),
            "affiliate": False,
            "approval": {
                "publication": "approved",
                "privacy_gate": "pass",
                "public_identity": "pass",
                "source_gate": "pass",
                "dedup": "pass",
                "qa": "pass",
            },
        }
        content_map = Path(temp) / "content-map.json"
        content_map.write_text(
            json.dumps({today: entry}, ensure_ascii=False), encoding="utf-8"
        )
        return today, content_map, digest

    @staticmethod
    def raise_blocked(message, *args, **kwargs):
        raise SafetyBlocked(message)

    def live_common_patches(self, temp: str, content_map: Path):
        return (
            mock.patch.object(self.publisher, "CONTENT_MAP", str(content_map)),
            mock.patch.object(self.publisher, "LOGS", str(Path(temp) / "logs")),
            mock.patch.object(self.publisher, "PUBLISHED", str(Path(temp) / "published.json")),
            mock.patch.object(self.publisher, "ALERT", str(Path(temp) / "alert.md")),
            mock.patch.object(self.publisher, "fail", side_effect=self.raise_blocked),
        )

    def test_authority_failure_stops_before_playwright_and_upload(self) -> None:
        with tempfile.TemporaryDirectory(prefix="tiktok_authority_") as temp:
            today, content_map, _ = self.live_fixture(temp)
            launch = mock.Mock(side_effect=AssertionError("browser launch attempted"))
            patches = self.live_common_patches(temp, content_map)
            with contextlib.ExitStack() as stack:
                for patcher in patches:
                    stack.enter_context(patcher)
                stack.enter_context(mock.patch.object(
                    self.publisher,
                    "authorize_live_publication",
                    side_effect=self.publisher.PublicationBlocked("fixture authority block"),
                ))
                stack.enter_context(mock.patch.object(
                    self.publisher.media_publish_guard,
                    "evaluate",
                    return_value={"verdict": "PASS", "findings": [], "sha256": "a" * 64},
                ))
                stack.enter_context(mock.patch.object(
                    self.publisher.post_ledger,
                    "is_duplicate_text",
                    return_value=(False, "", None),
                ))
                stack.enter_context(mock.patch.object(self.publisher, "launch", launch))
                stack.enter_context(self.block_playwright_import())
                with self.assertRaisesRegex(SafetyBlocked, "authority"):
                    self.publisher.mode_post(
                        None, today, True, "owner", "@fixture",
                        account_reader=lambda _page: "@fixture",
                        submission_reader=lambda *_args: {},
                    )
            launch.assert_not_called()

    def test_live_without_reviewed_account_reader_blocks_before_authority(self) -> None:
        with tempfile.TemporaryDirectory(prefix="tiktok_account_reader_") as temp:
            today, content_map, _ = self.live_fixture(temp)
            launch = mock.Mock(side_effect=AssertionError("browser launch attempted"))
            authority = mock.Mock(side_effect=AssertionError("authority receipt consumed"))
            patches = self.live_common_patches(temp, content_map)
            with contextlib.ExitStack() as stack:
                for patcher in patches:
                    stack.enter_context(patcher)
                stack.enter_context(mock.patch.object(
                    self.publisher, "authorize_live_publication", authority
                ))
                stack.enter_context(mock.patch.object(self.publisher, "launch", launch))
                stack.enter_context(self.block_playwright_import())
                with self.assertRaisesRegex(SafetyBlocked, "account verifier"):
                    self.publisher.mode_post(
                        None, today, True, "owner", "@fixture"
                    )
            authority.assert_not_called()
            launch.assert_not_called()

    def test_live_without_action_bound_submission_reader_blocks_before_authority(self) -> None:
        with tempfile.TemporaryDirectory(prefix="tiktok_submission_reader_") as temp:
            today, content_map, _ = self.live_fixture(temp)
            launch = mock.Mock(side_effect=AssertionError("browser launch attempted"))
            authority = mock.Mock(side_effect=AssertionError("authority receipt consumed"))
            patches = self.live_common_patches(temp, content_map)
            with contextlib.ExitStack() as stack:
                for patcher in patches:
                    stack.enter_context(patcher)
                stack.enter_context(mock.patch.object(
                    self.publisher, "authorize_live_publication", authority
                ))
                stack.enter_context(mock.patch.object(self.publisher, "launch", launch))
                stack.enter_context(self.block_playwright_import())
                with self.assertRaisesRegex(SafetyBlocked, "action-bound TikTok submission"):
                    self.publisher.mode_post(
                        None, today, True, "owner", "@fixture",
                        account_reader=lambda _page: "@fixture",
                    )
            authority.assert_not_called()
            launch.assert_not_called()

    def test_media_or_hash_failure_stops_before_dedup_claim_and_browser(self) -> None:
        with tempfile.TemporaryDirectory(prefix="tiktok_media_") as temp:
            today, content_map, digest = self.live_fixture(temp)
            launch = mock.Mock(side_effect=AssertionError("browser launch attempted"))
            claim = mock.Mock(side_effect=AssertionError("dedup claim attempted"))
            patches = self.live_common_patches(temp, content_map)
            with contextlib.ExitStack() as stack:
                for patcher in patches:
                    stack.enter_context(patcher)
                stack.enter_context(mock.patch.object(self.publisher, "authorize_live_publication"))
                stack.enter_context(mock.patch.object(
                    self.publisher.media_publish_guard,
                    "evaluate",
                    return_value={"verdict": "FAIL", "findings": ["watermark"], "sha256": digest},
                ))
                stack.enter_context(mock.patch.object(self.publisher.post_ledger, "claim", claim))
                stack.enter_context(mock.patch.object(self.publisher, "launch", launch))
                stack.enter_context(self.block_playwright_import())
                with self.assertRaisesRegex(SafetyBlocked, "media publication guard"):
                    self.publisher.mode_post(
                        None, today, True, "owner", "@fixture",
                        account_reader=lambda _page: "@fixture",
                        submission_reader=lambda *_args: {},
                    )
            claim.assert_not_called()
            launch.assert_not_called()

        with tempfile.TemporaryDirectory(prefix="tiktok_hash_") as temp:
            today, content_map, digest = self.live_fixture(temp)
            launch = mock.Mock(side_effect=AssertionError("browser launch attempted"))
            claim = mock.Mock(side_effect=AssertionError("dedup claim attempted"))
            patches = self.live_common_patches(temp, content_map)
            with contextlib.ExitStack() as stack:
                for patcher in patches:
                    stack.enter_context(patcher)
                stack.enter_context(mock.patch.object(
                    self.publisher.post_ledger,
                    "is_duplicate_text",
                    return_value=(False, "", None),
                ))
                def reject_receipt(**kwargs):
                    self.assertEqual(kwargs["asset_sha256"], digest)
                    raise self.publisher.PublicationBlocked(
                        "private publication receipt asset binding does not match"
                    )

                stack.enter_context(mock.patch.object(
                    self.publisher,
                    "authorize_live_publication",
                    side_effect=reject_receipt,
                ))
                stack.enter_context(mock.patch.object(
                    self.publisher.media_publish_guard,
                    "evaluate",
                    return_value={"verdict": "PASS", "findings": [], "sha256": digest},
                ))
                stack.enter_context(mock.patch.object(self.publisher.post_ledger, "claim", claim))
                stack.enter_context(mock.patch.object(self.publisher, "launch", launch))
                stack.enter_context(self.block_playwright_import())
                with self.assertRaisesRegex(SafetyBlocked, "asset binding"):
                    self.publisher.mode_post(
                        None, today, True, "owner", "@fixture",
                        account_reader=lambda _page: "@fixture",
                        submission_reader=lambda *_args: {},
                    )
            claim.assert_not_called()
            launch.assert_not_called()

    def test_duplicate_claim_failure_stops_before_playwright_and_upload(self) -> None:
        with tempfile.TemporaryDirectory(prefix="tiktok_dedup_") as temp:
            today, content_map, digest = self.live_fixture(temp)
            launch = mock.Mock(side_effect=AssertionError("browser launch attempted"))
            patches = self.live_common_patches(temp, content_map)
            with contextlib.ExitStack() as stack:
                for patcher in patches:
                    stack.enter_context(patcher)
                stack.enter_context(mock.patch.object(self.publisher, "authorize_live_publication"))
                stack.enter_context(mock.patch.object(
                    self.publisher.media_publish_guard,
                    "evaluate",
                    return_value={"verdict": "PASS", "findings": [], "sha256": digest},
                ))
                stack.enter_context(mock.patch.object(
                    self.publisher.post_ledger,
                    "is_duplicate_text",
                    return_value=(False, "", None),
                ))
                stack.enter_context(mock.patch.object(
                    self.publisher.post_ledger,
                    "claim",
                    return_value=(False, "", "TWIN: already used"),
                ))
                stack.enter_context(mock.patch.object(self.publisher, "launch", launch))
                stack.enter_context(self.block_playwright_import())
                with self.assertRaisesRegex(SafetyBlocked, "dedup blocked"):
                    self.publisher.mode_post(
                        None, today, True, "owner", "@fixture",
                        account_reader=lambda _page: "@fixture",
                        submission_reader=lambda *_args: {},
                    )
            launch.assert_not_called()

    def test_source_order_keeps_all_local_gates_before_browser_boundary(self) -> None:
        source = PUBLISHER.read_text(encoding="utf-8")
        start = source.index("def mode_post(")
        end = source.index("\ndef mode_plan(", start)
        body = source[start:end]
        self.assertLess(body.index("_require_account_reader("), body.index("ctx = launch("))
        self.assertLess(body.index("_require_submission_reader("), body.index("ctx = launch("))
        for marker in (
            "authorize_live_publication(",
            "media_publish_guard.evaluate(",
            "post_ledger.is_duplicate_text(",
            "post_ledger.claim(",
        ):
            self.assertLess(body.index(marker), body.index("ctx = launch("))
        self.assertLess(body.index("media_publish_guard.evaluate("),
                        body.index("authorize_live_publication("))
        self.assertLess(body.index("post_ledger.is_duplicate_text("),
                        body.index("authorize_live_publication("))
        self.assertLess(body.index("authorize_live_publication("),
                        body.index("post_ledger.claim("))
        self.assertNotIn("from playwright", source[:start])

    def test_exact_account_verifier_fails_closed_with_fake_page(self) -> None:
        page = object()
        reader = mock.Mock(return_value="@NgernDuanGold")
        self.assertEqual(
            self.publisher._verify_authenticated_account(
                page, "@ngernduangold", reader
            ),
            "@ngernduangold",
        )
        reader.assert_called_once_with(page)

        with self.assertRaisesRegex(
            self.publisher.PublicationBlocked, "does not match"
        ):
            self.publisher._verify_authenticated_account(
                page, "@ngernduangold", lambda _page: "@other"
            )
        with self.assertRaisesRegex(
            self.publisher.PublicationBlocked, "unreadable"
        ):
            self.publisher._verify_authenticated_account(
                page, "@ngernduangold", lambda _page: None
            )
        with self.assertRaisesRegex(
            self.publisher.PublicationBlocked, "unavailable"
        ):
            self.publisher._verify_authenticated_account(
                page, "@ngernduangold", None
            )

    def test_exact_caption_readback_fails_closed_with_fake_editor(self) -> None:
        class Editor:
            def __init__(self, value=None, error=None):
                self.value = value
                self.error = error

            def evaluate(self, expression):
                self.test_expression = expression
                if self.error is not None:
                    raise self.error
                return self.value

        caption = "ข้อความตรงกัน\nข้อมูลเพื่อการศึกษา · ผลิตด้วย AI"
        editor = Editor(caption)
        self.assertEqual(
            self.publisher._assert_exact_caption(editor, caption), caption
        )
        self.assertEqual(editor.test_expression, "element => element.innerText")
        with self.assertRaisesRegex(
            self.publisher.PublicationBlocked, "does not match"
        ):
            self.publisher._assert_exact_caption(Editor(caption[:-1]), caption)
        with self.assertRaisesRegex(
            self.publisher.PublicationBlocked, "unreadable"
        ):
            self.publisher._assert_exact_caption(Editor(None), caption)
        with self.assertRaisesRegex(
            self.publisher.PublicationBlocked, "unavailable"
        ):
            self.publisher._assert_exact_caption(
                Editor(error=RuntimeError("fixture")), caption
            )

    def test_action_bound_submission_evidence_fails_closed_with_fake_page(self) -> None:
        page = object()
        button = object()
        action = {
            "content_id": "b4-p01",
            "placement_id": "b4-p01__tiktok_main",
            "target_identity": "ngernduangold",
            "caption_sha256": "a" * 64,
            "asset_sha256": "b" * 64,
        }
        evidence = {
            "source": "platform-post-response-v1",
            "platform_request_id": "request-7555555555555555555",
            **action,
            "permalink": (
                "https://www.tiktok.com/@ngernduangold/"
                "video/7555555555555555555?lang=th"
            ),
            "video_id": "7555555555555555555",
        }
        reader = mock.Mock(return_value=evidence)
        self.assertEqual(
            self.publisher._submit_with_action_bound_evidence(
                page, button, action, reader
            ),
            {
                "platform_request_id": "request-7555555555555555555",
                "permalink": (
                    "https://www.tiktok.com/@ngernduangold/"
                    "video/7555555555555555555"
                ),
                "video_id": "7555555555555555555",
            },
        )
        reader.assert_called_once_with(page, button, action)

        with self.assertRaisesRegex(
            self.publisher.PublicationBlocked, "verifier is unavailable"
        ):
            self.publisher._submit_with_action_bound_evidence(
                page, button, action, None
            )
        with self.assertRaisesRegex(
            self.publisher.PublicationBlocked, "source is not action-bound"
        ):
            self.publisher._submit_with_action_bound_evidence(
                page, button, action,
                lambda *_args: dict(evidence, source="account-page-scan"),
            )
        with self.assertRaisesRegex(
            self.publisher.PublicationBlocked, "authorized content_id"
        ):
            self.publisher._submit_with_action_bound_evidence(
                page, button, action,
                lambda *_args: dict(evidence, content_id="other"),
            )
        with self.assertRaisesRegex(
            self.publisher.PublicationBlocked, "account-bound video result"
        ):
            self.publisher._submit_with_action_bound_evidence(
                page, button, action,
                lambda *_args: dict(evidence, video_id="7111111111111111111"),
            )

    def test_account_and_caption_are_rechecked_before_post_click(self) -> None:
        source = PUBLISHER.read_text(encoding="utf-8")
        start = source.index("def mode_post(")
        end = source.index("\ndef mode_plan(", start)
        body = source[start:end]
        upload = body.index("page.set_input_files(")
        post = body.index("_submit_with_action_bound_evidence(")
        upload_corpus_claim = body.index(
            "with media_publish_guard.publication_corpus_claim("
        )
        post_corpus_claim = body.index(
            "with media_publish_guard.publication_corpus_claim(",
            upload_corpus_claim + 1,
        )
        first_account = body.index("_verify_authenticated_account(")
        second_account = body.index("_verify_authenticated_account(", first_account + 1)
        first_caption = body.index("_assert_exact_caption(")
        second_caption = body.index("_assert_exact_caption(", first_caption + 1)
        self.assertLess(first_account, upload)
        self.assertLess(upload_corpus_claim, upload)
        self.assertLess(upload, post_corpus_claim)
        self.assertLess(post_corpus_claim, post)
        self.assertGreater(second_account, upload)
        self.assertLess(second_account, post)
        self.assertLess(first_caption, post)
        self.assertGreater(second_caption, upload)
        self.assertLess(second_caption, post)
        self.assertEqual(body.count("_verify_authenticated_account("), 2)
        self.assertEqual(body.count("_assert_exact_caption("), 2)
        self.assertEqual(
            body.count("with media_publish_guard.publication_corpus_claim("), 2
        )
        self.assertNotIn('page.locator(SEL["post_button"]).first.click()', body)

    def test_fresh_boundary_guard_rehashes_exact_bytes_and_rejects_drift(self) -> None:
        with tempfile.TemporaryDirectory(prefix="tiktok_boundary_hash_") as temp:
            asset = Path(temp) / "clip.mp4"
            receipt = Path(temp) / "receipt.json"
            asset.write_bytes(b"exact-video-v1")
            receipt.write_text("{}", encoding="utf-8")
            expected = hashlib.sha256(asset.read_bytes()).hexdigest().upper()
            evaluate = mock.Mock(return_value={
                "verdict": "PASS", "findings": [], "sha256": expected,
            })
            with mock.patch.object(
                self.publisher.media_publish_guard, "evaluate", evaluate
            ):
                self.assertEqual(
                    self.publisher._fresh_media_boundary_hash(asset, receipt, expected),
                    expected,
                )
            args, kwargs = evaluate.call_args
            self.assertEqual(args[0], asset.resolve())
            self.assertEqual(args[1], receipt)
            self.assertEqual(kwargs["repo"], ROOT)

            asset.write_bytes(b"exact-video-v2")
            changed = hashlib.sha256(asset.read_bytes()).hexdigest().upper()
            with mock.patch.object(
                self.publisher.media_publish_guard,
                "evaluate",
                return_value={"verdict": "PASS", "findings": [], "sha256": changed},
            ), self.assertRaisesRegex(
                self.publisher.PublicationBlocked, "changed after authority"
            ):
                self.publisher._fresh_media_boundary_hash(asset, receipt, expected)

    def test_fresh_boundary_rejects_guard_hash_that_is_not_exact_asset(self) -> None:
        with tempfile.TemporaryDirectory(prefix="tiktok_guard_hash_") as temp:
            asset = Path(temp) / "clip.mp4"
            receipt = Path(temp) / "receipt.json"
            asset.write_bytes(b"exact-video")
            receipt.write_text("{}", encoding="utf-8")
            expected = hashlib.sha256(asset.read_bytes()).hexdigest().upper()
            with mock.patch.object(
                self.publisher.media_publish_guard,
                "evaluate",
                return_value={"verdict": "PASS", "findings": [], "sha256": "A" * 64},
            ), self.assertRaisesRegex(
                self.publisher.PublicationBlocked, "does not match exact asset"
            ):
                self.publisher._fresh_media_boundary_hash(asset, receipt, expected)

    def test_upload_payload_is_the_exact_hash_bound_immutable_bytes(self) -> None:
        with tempfile.TemporaryDirectory(prefix="tiktok_upload_payload_") as temp:
            asset = Path(temp) / "clip.mp4"
            receipt = Path(temp) / "receipt.json"
            payload_bytes = b"exact-upload-video"
            asset.write_bytes(payload_bytes)
            receipt.write_text("{}", encoding="utf-8")
            expected = hashlib.sha256(payload_bytes).hexdigest().upper()
            with mock.patch.object(
                self.publisher.media_publish_guard,
                "evaluate",
                return_value={"verdict": "PASS", "findings": [], "sha256": expected},
            ):
                payload, actual = self.publisher._verified_upload_payload(
                    asset, receipt, expected
                )
            self.assertEqual(actual, expected)
            self.assertEqual(payload["name"], "clip.mp4")
            self.assertEqual(payload["mimeType"], "video/mp4")
            self.assertEqual(payload["buffer"], payload_bytes)

            def mutate_after_guard(*_args, **_kwargs):
                asset.write_bytes(b"replaced-after-guard")
                return {"verdict": "PASS", "findings": [], "sha256": expected}

            with mock.patch.object(
                self.publisher.media_publish_guard,
                "evaluate",
                side_effect=mutate_after_guard,
            ), self.assertRaisesRegex(
                self.publisher.PublicationBlocked, "immutable upload bytes"
            ):
                self.publisher._verified_upload_payload(asset, receipt, expected)

    def test_tiktok_claim_uses_authorized_exact_slot_and_gap(self) -> None:
        source = PUBLISHER.read_text(encoding="utf-8")
        start = source.index("def mode_post(")
        end = source.index("\ndef mode_plan(", start)
        body = source[start:end]
        claim = body.index("post_ledger.claim(")
        attempt = body.index("_begin_attempt(")
        self.assertIn(
            '"sha256:" + str(action.get("asset_sha256") or "")',
            body[claim:attempt],
        )
        self.assertIn('action.get("scheduled_slot")', body[claim:attempt])
        self.assertIn("enforce_gap=True", body[claim:attempt])
        self.assertLess(claim, attempt)
        finish = body.index("_finish_attempt(")
        confirm = body.index("post_ledger.confirm(")
        registry = body.index("_atomic_json_write(PUBLISHED")
        self.assertLess(finish, confirm)
        self.assertLess(confirm, registry)
        self.assertIn("if terminal_written:", body)
        self.assertIn("remote publication is terminal POSTED", body)

    def test_source_order_refreshes_media_immediately_at_upload_and_post(self) -> None:
        source = PUBLISHER.read_text(encoding="utf-8")
        start = source.index("def mode_post(")
        end = source.index("\ndef mode_plan(", start)
        body = source[start:end]
        upload = body.index("page.set_input_files(")
        post = body.index("_submit_with_action_bound_evidence(")
        first_fresh = body.rfind("upload_payload, actual_hash = _verified_upload_payload(", 0, upload)
        first_verify = body.rfind("verify_execution_authorization(", 0, upload)
        second_fresh = body.rfind("actual_hash = _fresh_media_boundary_hash(", upload, post)
        second_verify = body.rfind("verify_execution_authorization(", upload, post)
        self.assertGreater(first_fresh, body.index("ctx = launch("))
        self.assertLess(first_fresh, first_verify)
        self.assertLess(first_verify, upload)
        self.assertGreater(second_fresh, upload)
        self.assertLess(second_fresh, second_verify)
        self.assertLess(second_verify, post)
        self.assertEqual(body.count("upload_payload, actual_hash = _verified_upload_payload("), 1)
        self.assertEqual(body.count("actual_hash = _fresh_media_boundary_hash("), 1)
        self.assertIn('page.set_input_files(SEL["file_input"], upload_payload)', body)


if __name__ == "__main__":
    unittest.main(verbosity=2)
