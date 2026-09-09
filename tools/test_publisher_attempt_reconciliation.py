#!/usr/bin/env python3
"""No-network tests for crash-safe direct publisher attempt receipts."""

from concurrent.futures import ThreadPoolExecutor
import ast
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
PUBLISHERS = {
    "instagram": ROOT / "automation/ig_publish.py",
    "facebook": ROOT / "social-autopost/publish_fb.py",
    "tiktok": ROOT / "social-autopost/publish_tiktok.py",
    "youtube": ROOT / "tools/yt_upload_batch2.py",
}


def load_module(channel, path):
    spec = importlib.util.spec_from_file_location(
        "attempt_reconciliation_%s" % channel, path
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def action(channel, placement="content-1__main"):
    target = {
        "instagram": "17890000000000000",
        "facebook": "583765282304956",
        "tiktok": "ngernduangold",
        "youtube": "youtube-channel-123",
    }[channel]
    return {
        "content_id": "content-1",
        "placement_id": placement,
        "channel": channel,
        "target_identity": target,
        "caption_sha256": "a" * 64,
        "asset_sha256": None if channel == "facebook" else "b" * 64,
        "scheduled_slot": "2026-08-16T20:00:00+07:00",
        "nonce": "receipt-" + "x" * 40,
        "consumed": True,
    }


class AttemptReceiptTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.modules = {
            channel: load_module(channel, path)
            for channel, path in PUBLISHERS.items()
        }

    def valid_terminal(self, channel, module, value):
        if channel == "instagram":
            module._finish_attempt(
                value, "POSTED", remote_platform_id="17890000000000001",
                details={"creation_id": "17890000000000002"},
            )
        elif channel == "facebook":
            module._finish_attempt(
                value, "POSTED", remote_platform_id="583765282304956_999999999999999",
                details={"comment_id": "583765282304956_999999999999999_888888888888888"},
            )
        elif channel == "tiktok":
            module._finish_attempt(
                value, "POSTED", remote_platform_id="7555555555555555555",
                permalink="https://www.tiktok.com/@ngernduangold/video/7555555555555555555",
            )
        else:
            module._finish_attempt(
                value, "POSTED", remote_platform_id="AbCdEf12345"
            )

    def invalid_posted(self, channel, module, value):
        if channel == "facebook":
            module._finish_attempt(
                value, "POSTED", remote_platform_id="not-an-id",
                details={"comment_id": "also-bad"},
            )
        elif channel == "tiktok":
            module._finish_attempt(
                value, "POSTED", remote_platform_id="7555555555555555555",
                permalink="",
            )
        else:
            module._finish_attempt(value, "POSTED", remote_platform_id="bad id!")

    def test_pending_and_terminal_receipts_are_durable_and_replay_blocking(self):
        for channel, module in self.modules.items():
            with self.subTest(channel=channel), tempfile.TemporaryDirectory() as raw:
                module.ATTEMPT_ROOT = Path(raw) / "private-attempts"
                value = action(channel)
                module._assert_reconciliation_clear(value["placement_id"])
                module._begin_attempt(value)
                pending, terminal = module._attempt_paths(value["placement_id"])
                pending_value = json.loads(pending.read_text(encoding="utf-8"))
                self.assertEqual(pending_value["status"], "PENDING_REMOTE")
                self.assertEqual(pending_value["action"], value)
                with self.assertRaisesRegex(Exception, "reconciliation-only"):
                    module._assert_reconciliation_clear(value["placement_id"])
                with self.assertRaisesRegex(Exception, "automatic retry"):
                    module._begin_attempt(value)
                with self.assertRaises(Exception):
                    self.invalid_posted(channel, module, value)
                self.assertFalse(terminal.exists())
                self.valid_terminal(channel, module, value)
                terminal_value = json.loads(terminal.read_text(encoding="utf-8"))
                self.assertEqual(terminal_value["status"], "POSTED")
                self.assertTrue(terminal_value["remote_platform_id"])
                with self.assertRaisesRegex(Exception, "automatic retry"):
                    self.valid_terminal(channel, module, value)

    def test_unknown_is_terminal_and_has_no_success_evidence(self):
        for channel, module in self.modules.items():
            with self.subTest(channel=channel), tempfile.TemporaryDirectory() as raw:
                module.ATTEMPT_ROOT = Path(raw) / "private-attempts"
                value = action(channel, "content-unknown__main")
                module._begin_attempt(value)
                module._finish_attempt(value, "UNKNOWN", reason="connection reset")
                _pending, terminal = module._attempt_paths(value["placement_id"])
                receipt = json.loads(terminal.read_text(encoding="utf-8"))
                self.assertEqual(receipt["status"], "UNKNOWN")
                self.assertIsNone(receipt["remote_platform_id"])
                self.assertIsNone(receipt["permalink"])
                with self.assertRaisesRegex(Exception, "reconciliation-only"):
                    module._assert_reconciliation_clear(value["placement_id"])

    def test_concurrent_begin_has_exactly_one_winner(self):
        module = self.modules["instagram"]
        with tempfile.TemporaryDirectory() as raw:
            module.ATTEMPT_ROOT = Path(raw) / "private-attempts"
            value = action("instagram", "content-race__instagram")

            def begin(_index):
                try:
                    module._begin_attempt(value)
                    return "allowed"
                except Exception:
                    return "blocked"

            with ThreadPoolExecutor(max_workers=2) as pool:
                outcomes = list(pool.map(begin, range(2)))
            self.assertEqual(sorted(outcomes), ["allowed", "blocked"])

    def test_tiktok_submission_evidence_must_be_action_and_account_bound(self):
        module = self.modules["tiktok"]
        good = "https://www.tiktok.com/@ngernduangold/video/7555555555555555555?lang=th"
        self.assertEqual(
            module._validated_permalink(good, "@ngernduangold"),
            (
                "https://www.tiktok.com/@ngernduangold/video/7555555555555555555",
                "7555555555555555555",
            ),
        )
        for invalid in (
            "https://evil.example/@ngernduangold/video/7555555555555555555",
            "https://www.tiktok.com/@other/video/7555555555555555555",
            "https://www.tiktok.com/@ngernduangold",
            "https://www.tiktok.com/@ngernduangold/video/not-a-number",
        ):
            self.assertEqual(module._validated_permalink(invalid, "ngernduangold"), ("", ""))

        value = action("tiktok")
        evidence = {
            "source": "platform-post-response-v1",
            "platform_request_id": "request-7555555555555555555",
            "content_id": value["content_id"],
            "placement_id": value["placement_id"],
            "target_identity": value["target_identity"],
            "caption_sha256": value["caption_sha256"],
            "asset_sha256": value["asset_sha256"],
            "permalink": good,
            "video_id": "7555555555555555555",
        }
        page = object()
        button = object()
        reader = mock.Mock(return_value=evidence)
        self.assertEqual(
            module._submit_with_action_bound_evidence(page, button, value, reader),
            {
                "platform_request_id": "request-7555555555555555555",
                "permalink": (
                    "https://www.tiktok.com/@ngernduangold/"
                    "video/7555555555555555555"
                ),
                "video_id": "7555555555555555555",
            },
        )
        reader.assert_called_once_with(page, button, value)

        mismatched = dict(evidence, content_id="different-content")
        with self.assertRaisesRegex(Exception, "authorized content_id"):
            module._submit_with_action_bound_evidence(
                page, button, value, lambda *_args: mismatched
            )
        with self.assertRaisesRegex(Exception, "source is not action-bound"):
            module._submit_with_action_bound_evidence(
                page, button, value, lambda *_args: dict(evidence, source="dom-scan")
            )

    def test_publishers_wire_attempt_before_remote_and_terminal_before_success_registry(self):
        boundaries = {
            "instagram": 'result = api("/%s/media"',
            "facebook": 'result = api("/%s/feed"',
            "tiktok": "ctx = launch(",
            "youtube": "request = service.videos().insert(",
        }
        function_names = {
            "instagram": "main",
            "facebook": "main",
            "tiktok": "mode_post",
            "youtube": "run_live",
        }
        for channel, path in PUBLISHERS.items():
            with self.subTest(channel=channel):
                source = path.read_text(encoding="utf-8")
                tree = ast.parse(source, filename=str(path))
                node = next(
                    item for item in tree.body
                    if isinstance(item, ast.FunctionDef)
                    and item.name == function_names[channel]
                )
                lines = source.splitlines()
                body = "\n".join(lines[node.lineno - 1:node.end_lineno])
                if channel == "youtube":
                    validate_node = next(
                        item for item in tree.body
                        if isinstance(item, ast.FunctionDef)
                        and item.name == "validate_live_upload"
                    )
                    validate_body = "\n".join(
                        lines[validate_node.lineno - 1:validate_node.end_lineno]
                    )
                    self.assertLess(
                        validate_body.index("_assert_reconciliation_clear("),
                        validate_body.index("authorize_live_publication("),
                    )
                    self.assertLess(
                        body.index("validate_live_upload("),
                        body.index("get_credentials(interactive=True)"),
                    )
                else:
                    self.assertLess(body.index("_assert_reconciliation_clear("),
                                    body.index("authorize_live_publication("))
                self.assertLess(body.index("_begin_attempt("), body.index(boundaries[channel]))
                success_registry = (
                    "write_json(UPLOAD_LOG_PATH" if channel == "youtube"
                    else "_atomic_json_write("
                )
                self.assertLess(body.index("_finish_attempt("),
                                body.index(success_registry))
                self.assertNotIn("submitted_unverified", body)

    def test_facebook_revalidates_immediately_before_comment_mutation(self):
        source = PUBLISHERS["facebook"].read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(PUBLISHERS["facebook"]))
        node = next(
            item for item in tree.body
            if isinstance(item, ast.FunctionDef) and item.name == "main"
        )
        lines = source.splitlines()
        body = "\n".join(lines[node.lineno - 1:node.end_lineno])
        feed_mutation = body.index('result = api("/%s/feed"')
        comment_mutation = body.index('result = api("/%s/comments"')
        comment_recheck = body.index(
            "verify_execution_authorization(", feed_mutation
        )
        self.assertLess(feed_mutation, comment_recheck)
        self.assertLess(comment_recheck, comment_mutation)

    def test_facebook_atomic_text_claim_precedes_attempt_and_mutations(self):
        source = PUBLISHERS["facebook"].read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(PUBLISHERS["facebook"]))
        node = next(
            item for item in tree.body
            if isinstance(item, ast.FunctionDef) and item.name == "main"
        )
        lines = source.splitlines()
        body = "\n".join(lines[node.lineno - 1:node.end_lineno])
        claim = body.index("post_ledger.claim_text_publication(")
        attempt = body.index("_begin_attempt(")
        feed = body.index('result = api("/%s/feed"')
        comment = body.index('result = api("/%s/comments"')
        finish = body.index("_finish_attempt(")
        confirm = body.index("post_ledger.confirm(")
        registry = body.index("_atomic_json_write(PUBLISHED")
        self.assertLess(claim, attempt)
        self.assertLess(attempt, feed)
        self.assertLess(feed, comment)
        self.assertLess(comment, finish)
        self.assertLess(finish, confirm)
        self.assertLess(confirm, registry)
        self.assertIn("if attempt_started and not terminal_written:", body)
        self.assertIn("if terminal_written:", body)
        self.assertIn("remote publication is terminal POSTED", body)
        claim_body = body[claim:attempt]
        self.assertIn('"facebook",\n            text,', claim_body)
        self.assertNotIn("canonical_text_payload(", claim_body)

    def test_facebook_claim_failure_blocks_before_attempt_and_api(self):
        module = self.modules["facebook"]
        value = action("facebook", "content-1__facebook-feed")
        date = "2026-08-25"
        entry = {
            "fbText": "เนื้อหาใหม่ ข้อมูลเพื่อการศึกษา มีลิงก์พันธมิตร",
            "firstComment": "อ่านรายละเอียดที่ https://ngernduangold.com/example",
            "affiliate": True,
            "content_id": value["content_id"],
            "placement_id": value["placement_id"],
            "scheduled_slot": value["scheduled_slot"],
            "approval": {},
        }
        with tempfile.TemporaryDirectory(prefix="facebook-claim-boundary-") as raw:
            directory = Path(raw)
            content_map = directory / "feed_content_map.json"
            content_map.write_text(
                json.dumps({date: entry}, ensure_ascii=False), encoding="utf-8"
            )
            api = mock.Mock(side_effect=AssertionError("remote API crossed claim gate"))
            begin = mock.Mock(side_effect=AssertionError("attempt began before claim"))
            with (
                mock.patch.dict(module.os.environ, {"OVERRIDE_DATE": date}),
                mock.patch.object(module, "CONTENT_MAP", str(content_map)),
                mock.patch.object(module, "LOG_DIR", str(directory / "logs")),
                mock.patch.object(module, "PUBLISHED", str(directory / "published.json")),
                mock.patch.object(module, "INBOX", str(directory / "inbox")),
                mock.patch.object(module, "DRY_RUN", False),
                mock.patch.object(module, "PAGE_ID", value["target_identity"]),
                mock.patch.object(module, "TOKEN", "fixture-token"),
                mock.patch.object(module, "_assert_reconciliation_clear"),
                mock.patch.object(module, "authorize_live_publication", return_value=value),
                mock.patch.object(
                    module.post_ledger, "claim_text_publication",
                    return_value=(False, "", "GAP: fixture"),
                ),
                mock.patch.object(module, "_begin_attempt", begin),
                mock.patch.object(module, "api", api),
            ):
                with self.assertRaises(SystemExit):
                    module.main()
            begin.assert_not_called()
            api.assert_not_called()


if __name__ == "__main__":
    unittest.main(verbosity=2)
