import contextlib
import datetime
import io
import json
import os
import sys
import tempfile
import types
import unittest
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PIPELINE = os.path.join(ROOT, "pipeline")
TOOLS = os.path.join(ROOT, "tools")
for selected in (PIPELINE, TOOLS):
    if selected not in sys.path:
        sys.path.insert(0, selected)

import content_council
import content_creators
import content_review
import credit_tracker
import diag_keys
import free_llm
import ga4_today
import run_batch


class _FakeGA4Client:
    def __init__(self, results):
        self.results = results
        self.requests = []

    def run_report(self, request):
        self.requests.append(request)
        dimensions = tuple(item.name for item in request.dimensions)
        metrics = tuple(item.name for item in request.metrics)
        rows = []
        for dim_values, metric_values in self.results.get((dimensions, metrics), []):
            rows.append(types.SimpleNamespace(
                dimension_values=[types.SimpleNamespace(value=value) for value in dim_values],
                metric_values=[types.SimpleNamespace(value=value) for value in metric_values],
            ))
        return types.SimpleNamespace(rows=rows)


def _constructor(**kwargs):
    return types.SimpleNamespace(**kwargs)


class GA4TodayFailClosedTests(unittest.TestCase):
    def _api(self, client):
        return client, _constructor, _constructor, _constructor, _constructor

    def test_collect_uses_explicit_property_and_unambiguous_totals(self):
        client = _FakeGA4Client({
            (("hour",), ("sessions", "totalUsers")): [(["09"], ["3", "2"])],
            ((), ("sessions", "totalUsers", "eventCount")): [([], ["8", "5", "21"])],
            (("sessionDefaultChannelGroup",), ("sessions",)): [(["Organic Search"], ["4"])],
            (("date",), ("sessions",)): [(["20260824"], ["8"])],
        })
        with mock.patch.object(ga4_today.G, "_property_id", return_value="12345"):
            report = ga4_today.collect("2026-08-24", api=self._api(client))
        rendered = ga4_today.build_report(report)
        self.assertIn("DIAGNOSTIC ONLY", rendered)
        self.assertIn("TOTAL sessions=8 users=5 events=21", rendered)
        self.assertIn("7 DAYS THROUGH 2026-08-24", rendered)
        self.assertTrue(all(request.property == "properties/12345" for request in client.requests))
        last_request = client.requests[-1]
        self.assertEqual(last_request.date_ranges[0].start_date, "2026-08-18")
        self.assertEqual(last_request.date_ranges[0].end_date, "2026-08-24")

    def test_missing_client_returns_nonzero_without_overwriting_report(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = os.path.join(tmp, "report.txt")
            with open(output, "w", encoding="utf-8") as handle:
                handle.write("trusted previous report")
            with mock.patch.object(ga4_today.G, "_property_id", return_value="12345"), \
                    mock.patch.object(ga4_today.G, "_api_client", return_value=None), \
                    contextlib.redirect_stderr(io.StringIO()):
                code = ga4_today.main(["2026-08-24"], output_path=output)
            self.assertEqual(code, 2)
            with open(output, encoding="utf-8") as handle:
                self.assertEqual(handle.read(), "trusted previous report")

    def test_invalid_day_is_unavailable(self):
        with tempfile.TemporaryDirectory() as tmp, contextlib.redirect_stderr(io.StringIO()):
            output = os.path.join(tmp, "report.txt")
            code = ga4_today.main(["24-08-2026"], api=(), output_path=output)
            self.assertEqual(code, 2)
            self.assertFalse(os.path.exists(output))


class ProviderDiagnosticTests(unittest.TestCase):
    POOL = [("provider", "https://invalid.example", "model", "KEY")]

    def test_policy_block_is_failure_not_success(self):
        def blocked(*_args):
            raise free_llm.NetworkGenerationBlocked("disabled")

        with contextlib.redirect_stdout(io.StringIO()):
            result = diag_keys.diagnose(self.POOL, lambda _env: "secret", blocked)
        self.assertEqual(result, {"configured": 1, "verified": 0, "failed": 1})

    def test_empty_provider_response_is_failure(self):
        with contextlib.redirect_stdout(io.StringIO()):
            result = diag_keys.diagnose(self.POOL, lambda _env: "secret", lambda *_args: " ")
        self.assertEqual(result["failed"], 1)
        self.assertEqual(result["verified"], 0)

    def test_verified_provider_passes_and_missing_provider_is_skip(self):
        pool = self.POOL + [("optional", "https://invalid.example", "model", "MISSING")]
        with contextlib.redirect_stdout(io.StringIO()):
            result = diag_keys.diagnose(
                pool,
                lambda env: "secret" if env == "KEY" else "",
                lambda *_args: "OK",
            )
        self.assertEqual(result, {"configured": 1, "verified": 1, "failed": 0})

    def test_main_returns_nonzero_for_failed_or_unavailable_diagnostic(self):
        with mock.patch.object(diag_keys, "diagnose", return_value={"configured": 1, "verified": 0, "failed": 1}), \
                contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(diag_keys.main(), 1)
        with mock.patch.object(diag_keys, "diagnose", return_value={"configured": 0, "verified": 0, "failed": 0}), \
                contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(diag_keys.main(), 2)


class DraftClassificationTests(unittest.TestCase):
    def test_content_creator_never_marks_empty_generation_passed(self):
        with mock.patch.object(content_creators.free_llm, "generate", return_value=(None, None)):
            result = content_creators.create("fb", "topic")
        self.assertFalse(result["ok"])
        self.assertEqual(result["content"], "")
        self.assertIn("generation unavailable or empty", result["issues"])

    def test_council_empty_stage_blocks_before_queue_write(self):
        with mock.patch.object(content_council.free_llm, "generate", return_value=(None, None)), \
                mock.patch.object(content_council, "_write_queue") as write_queue, \
                contextlib.redirect_stderr(io.StringIO()):
            code = content_council.main(["topic"])
        self.assertEqual(code, 2)
        write_queue.assert_not_called()

    def test_review_flags_blank_and_embedded_empty_placeholder(self):
        self.assertTrue(content_review.review_text("   "))
        self.assertTrue(content_review.review_text("## Facebook\n\n(ว่าง)\n"))
        self.assertTrue(content_review.review_text("## TikTok\n\n(ว่าง — ลองรันใหม่)\n"))

    def test_batch_continues_but_returns_blocked_on_runner_failures(self):
        called = []

        def runner(topic):
            called.append(topic)
            raise RuntimeError("forced")

        with contextlib.redirect_stdout(io.StringIO()):
            code = run_batch.main(["one", "two"], runner=runner)
        self.assertEqual(code, 1)
        self.assertEqual(called, ["one", "two"])

    def test_batch_rejects_empty_platform_output(self):
        incomplete = ("package", "note", [{"ok": True, "content": ""}])
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(run_batch.main(["one"], runner=lambda _topic: incomplete), 1)

    def test_batch_succeeds_only_for_nonempty_passed_outputs(self):
        complete = ("package", "note", [{"ok": True, "content": "draft"}])
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(run_batch.main(["one"], runner=lambda _topic: complete), 0)


class CreditTrackerFailClosedTests(unittest.TestCase):
    def _paths(self, tmp):
        return mock.patch.multiple(
            credit_tracker,
            AL=tmp,
            INBOX=os.path.join(tmp, "inbox"),
            STATE=os.path.join(tmp, "flow-credits.json"),
        )

    def test_existing_malformed_state_does_not_reset_to_full_quota(self):
        with tempfile.TemporaryDirectory() as tmp, self._paths(tmp):
            with open(credit_tracker.STATE, "w", encoding="utf-8") as handle:
                handle.write("{bad")
            with self.assertRaises(credit_tracker.CreditStateError):
                credit_tracker._load()
            with open(credit_tracker.STATE, encoding="utf-8") as handle:
                self.assertEqual(handle.read(), "{bad")

    def test_invalid_structure_and_explicit_empty_state_fail_closed(self):
        with tempfile.TemporaryDirectory() as tmp, self._paths(tmp):
            with open(credit_tracker.STATE, "w", encoding="utf-8") as handle:
                json.dump({"month": "2026-08", "quota": 1000, "used": "0", "log": []}, handle)
            with self.assertRaises(credit_tracker.CreditStateError):
                credit_tracker._load()
            with self.assertRaises(credit_tracker.CreditStateError):
                credit_tracker.remaining({})

    def test_missing_state_initializes_only_in_memory_and_atomic_save_round_trips(self):
        with tempfile.TemporaryDirectory() as tmp, self._paths(tmp), \
                mock.patch.object(credit_tracker, "_month", return_value="2026-08"):
            state = credit_tracker._load()
            self.assertEqual(state["used"], 0)
            self.assertFalse(os.path.exists(credit_tracker.STATE))
            state["used"] = 15
            credit_tracker._save(state)
            self.assertEqual(credit_tracker._load()["used"], 15)
            leftovers = [name for name in os.listdir(tmp) if name.endswith(".tmp")]
            self.assertEqual(leftovers, [])


if __name__ == "__main__":
    unittest.main()
