#!/usr/bin/env python3
import csv
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest import mock

import ga4_pull
import gsc_pull


CAPTURE = {
    "captured_at": "2026-08-16T01:02:03+00:00",
    "window_start": "2026-07-20",
    "window_end": "2026-08-16",
    "window_days": 28,
    "property_id": "123",
    "trust": {
        "trusted": False,
        "label": "UNTRUSTED",
        "reason": "fixture trust",
        "schema": "fixture",
        "expires_at": None,
    },
}
TRUSTED_CAPTURE = {
    **CAPTURE,
    "trust": {
        "trusted": True,
        "label": "TRUSTED",
        "reason": "fixture trust",
        "schema": "fixture",
        "expires_at": "2026-08-17T01:02:03+00:00",
    },
}
GSC_CAPTURE = {
    "captured_at": "2026-08-16T01:02:03+00:00",
    "window_start": "2026-07-17",
    "window_end": "2026-08-13",
    "window_days": 28,
    "finalization_lag_days": 3,
    "site_url": "sc-domain:example.test",
}


def ga_row(dimensions, metric):
    return SimpleNamespace(
        dimension_values=[SimpleNamespace(value=value) for value in dimensions],
        metric_values=[SimpleNamespace(value=metric)],
    )


def ga_report(rows, row_count=None):
    rows = list(rows)
    return SimpleNamespace(rows=rows, row_count=len(rows) if row_count is None else row_count)


def query_evidence(rows=0, limit=None):
    limit = limit or ga4_pull.GA4_ROW_LIMIT
    pages = max(1, (rows + limit - 1) // limit)
    page_counts = ([0] if rows == 0 else [
        min(limit, rows - index * limit) for index in range(pages)
    ])
    return {
        "api_row_count": rows,
        "row_limit": limit,
        "rows_fetched": rows,
        "pages_fetched": pages,
        "offsets": [index * limit for index in range(pages)],
        "page_row_counts": page_counts,
        "response_row_counts": [rows] * pages,
        "truncated": False,
        "complete": True,
    }


def all_query_coverage():
    return {name: query_evidence() for name in ga4_pull.GA4_QUERY_NAMES}


def pilot_context():
    target = dict(ga4_pull.PILOT_MEASUREMENT_CONTRACT["target"])
    target["landing_path"] = "/credit-card-salary-30000-2026"
    return {"target": target}


class FakeSearchAnalytics:
    def __init__(self, responses):
        self.responses = iter(responses)
        self.bodies = []

    def query(self, *, siteUrl, body):
        self.bodies.append((siteUrl, dict(body)))
        response = next(self.responses)

        class Request:
            def execute(self_inner):
                if isinstance(response, Exception):
                    raise response
                return response

        return Request()


class FakeGSC:
    def __init__(self, responses):
        self.analytics = FakeSearchAnalytics(responses)

    def searchanalytics(self):
        return self.analytics


class AnalyticsBundleContractTests(unittest.TestCase):
    def setUp(self):
        # Unit-test failure paths must never append synthetic incidents to the
        # workspace's operational ga4_pull.log.
        patcher = mock.patch.object(ga4_pull, "_log")
        patcher.start()
        self.addCleanup(patcher.stop)

    @staticmethod
    def fake_api(client):
        constructor = lambda **kwargs: kwargs
        return client, constructor, constructor, constructor, constructor

    @staticmethod
    def csv_writer(_context, *args, **kwargs):
        path = kwargs.get("output_path") or args[-1]
        Path(path).write_text("fixture\n", encoding="utf-8")
        name = Path(path).name
        if "metrics" in name:
            queries = ("source_sessions", "source_events")
        elif "pages" in name:
            queries = ("page_views", "page_events")
        elif "pilot" in name:
            queries = ("pilot_affiliate_sessions", "pilot_qualified_landings")
        else:
            queries = ("funnel_events",)
        return {"file": path,
                "query_coverage": {key: query_evidence() for key in queries}}

    @staticmethod
    def snapshot_writer(_context, _files, path, _query_coverage, _pilot_context):
        Path(path).write_text("{}\n", encoding="utf-8")

    def test_ga4_cli_keeps_old_bundle_when_later_table_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            outputs = [root / name for name in
                       ("metrics.csv", "pages.csv", "funnel.csv", "pilot.csv",
                        "snapshot.json")]
            for path in outputs:
                path.write_text("old-%s\n" % path.name, encoding="utf-8")
            with (
                mock.patch.object(ga4_pull, "OUT", str(outputs[0])),
                mock.patch.object(ga4_pull, "OUT_PAGES", str(outputs[1])),
                mock.patch.object(ga4_pull, "OUT_FUNNEL", str(outputs[2])),
                mock.patch.object(ga4_pull, "OUT_PILOT", str(outputs[3])),
                mock.patch.object(ga4_pull, "OUT_SNAPSHOT", str(outputs[4])),
                mock.patch.object(ga4_pull, "_capture_context", return_value=TRUSTED_CAPTURE),
                mock.patch.object(ga4_pull, "_pilot_capture_context", return_value={}),
                mock.patch.object(ga4_pull, "_assert_pilot_context_current"),
                mock.patch.object(ga4_pull, "pull", side_effect=self.csv_writer),
                mock.patch.object(ga4_pull, "pull_pages", return_value=None),
                mock.patch.object(ga4_pull, "pull_funnel") as funnel,
                mock.patch.object(ga4_pull, "pull_pilot_sessions") as pilot_pull,
                mock.patch.object(ga4_pull, "_write_snapshot_metadata") as writer,
            ):
                self.assertEqual(ga4_pull.main(), 3)
            funnel.assert_not_called()
            pilot_pull.assert_not_called()
            writer.assert_not_called()
            for path in outputs:
                self.assertEqual(path.read_text(encoding="utf-8"), "old-%s\n" % path.name)

    def test_ga4_cli_promotes_sidecar_only_after_complete_bundle(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            outputs = [root / name for name in
                       ("metrics.csv", "pages.csv", "funnel.csv", "pilot.csv",
                        "snapshot.json")]
            with (
                mock.patch.object(ga4_pull, "OUT", str(outputs[0])),
                mock.patch.object(ga4_pull, "OUT_PAGES", str(outputs[1])),
                mock.patch.object(ga4_pull, "OUT_FUNNEL", str(outputs[2])),
                mock.patch.object(ga4_pull, "OUT_PILOT", str(outputs[3])),
                mock.patch.object(ga4_pull, "OUT_SNAPSHOT", str(outputs[4])),
                mock.patch.object(ga4_pull, "_capture_context", return_value=TRUSTED_CAPTURE),
                mock.patch.object(ga4_pull, "_pilot_capture_context", return_value={}),
                mock.patch.object(ga4_pull, "_assert_pilot_context_current"),
                mock.patch.object(ga4_pull, "pull", side_effect=self.csv_writer),
                mock.patch.object(ga4_pull, "pull_pages", side_effect=self.csv_writer),
                mock.patch.object(ga4_pull, "pull_funnel", side_effect=self.csv_writer),
                mock.patch.object(ga4_pull, "pull_pilot_sessions",
                                  side_effect=self.csv_writer),
                mock.patch.object(ga4_pull, "_write_snapshot_metadata",
                                  side_effect=self.snapshot_writer) as writer,
            ):
                self.assertEqual(ga4_pull.main(), 0)
            self.assertEqual(writer.call_count, 1)
            self.assertEqual(set(writer.call_args.args[3]), set(ga4_pull.GA4_QUERY_NAMES))
            self.assertTrue(all(path.is_file() for path in outputs))
            self.assertEqual(outputs[4].read_text(encoding="utf-8"), "{}\n")

    def test_ga4_cli_blocks_untrusted_before_outputs_credentials_or_network(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            snapshot = root / "not-created" / "snapshot.json"
            with (
                mock.patch.object(ga4_pull, "OUT_SNAPSHOT", str(snapshot)),
                mock.patch.object(ga4_pull, "_capture_context", return_value=CAPTURE),
                mock.patch.object(ga4_pull, "_pilot_capture_context") as pilot_context,
                mock.patch.object(ga4_pull, "pull") as metrics,
                mock.patch.object(ga4_pull, "pull_pages") as pages,
                mock.patch.object(ga4_pull, "pull_funnel") as funnel,
                mock.patch.object(ga4_pull, "pull_pilot_sessions") as pilot,
                mock.patch.object(ga4_pull.os, "makedirs") as make_dirs,
            ):
                self.assertEqual(ga4_pull.main(), 2)
            pilot_context.assert_not_called()
            metrics.assert_not_called()
            pages.assert_not_called()
            funnel.assert_not_called()
            pilot.assert_not_called()
            make_dirs.assert_not_called()
            self.assertFalse(snapshot.exists())

    def test_ga4_cli_uses_blocked_only_for_known_prerequisites(self):
        with tempfile.TemporaryDirectory() as tmp:
            snapshot = Path(tmp) / "ga4-snapshot.json"
            missing_property = {**TRUSTED_CAPTURE, "property_id": ""}
            with (
                mock.patch.object(ga4_pull, "OUT_SNAPSHOT", str(snapshot)),
                mock.patch.object(ga4_pull, "_capture_context", return_value=missing_property),
                mock.patch.object(ga4_pull, "_pilot_capture_context", return_value={}),
                mock.patch.object(ga4_pull, "_api_client") as api_client,
            ):
                self.assertEqual(ga4_pull.main(), 2)
            api_client.assert_not_called()

            with (
                mock.patch.object(ga4_pull, "OUT_SNAPSHOT", str(snapshot)),
                mock.patch.object(ga4_pull, "_capture_context", return_value=TRUSTED_CAPTURE),
                mock.patch.object(ga4_pull, "_pilot_capture_context", return_value={}),
                mock.patch.object(ga4_pull, "_api_client", return_value=None),
            ):
                self.assertEqual(ga4_pull.main(), 2)

    def test_ga4_cli_classifies_invalid_capture_and_api_failure_as_runner_failed(self):
        with mock.patch.object(
            ga4_pull, "_capture_context", side_effect=ValueError("bad capture schema")
        ):
            self.assertEqual(ga4_pull.main(), 3)

        malformed_trust = {**TRUSTED_CAPTURE, "trust": {"trusted": True}}
        with mock.patch.object(
            ga4_pull, "_capture_context", return_value=malformed_trust
        ):
            self.assertEqual(ga4_pull.main(), 3)

        with tempfile.TemporaryDirectory() as tmp:
            snapshot = Path(tmp) / "ga4-snapshot.json"
            with (
                mock.patch.object(ga4_pull, "OUT_SNAPSHOT", str(snapshot)),
                mock.patch.object(ga4_pull, "_capture_context", return_value=TRUSTED_CAPTURE),
                mock.patch.object(ga4_pull, "_pilot_capture_context", return_value={}),
                mock.patch.object(
                    ga4_pull,
                    "pull",
                    side_effect=ga4_pull.ProducerRunnerFailed("API failed"),
                ),
            ):
                self.assertEqual(ga4_pull.main(), 3)

    def test_ga4_metadata_hashes_every_table_and_binds_capture_trust(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            files = {name: root / (name + ".csv")
                     for name in ("metrics", "pages", "funnel", "pilot_sessions")}
            for index, path in enumerate(files.values()):
                path.write_text("value\n%d\n" % index, encoding="utf-8")
            meta = root / "snapshot.json"
            ga4_pull._write_snapshot_metadata(
                CAPTURE, {name: str(path) for name, path in files.items()}, str(meta),
                all_query_coverage(), ga4_pull._pilot_capture_context(),
            )
            payload = json.loads(meta.read_text(encoding="utf-8"))
        self.assertEqual(set(payload["files"]),
                         {"metrics", "pages", "funnel", "pilot_sessions"})
        self.assertEqual(payload["window_days"], 28)
        self.assertEqual(payload["captured_at"], CAPTURE["captured_at"])
        self.assertEqual(payload["capture_time_trust"], CAPTURE["trust"])
        self.assertNotIn("egress_ip", payload["capture_time_trust"])
        self.assertNotIn("cidrs", payload["capture_time_trust"])
        self.assertEqual(payload["property_id"], "123")
        self.assertEqual(payload["schema_version"], 3)
        self.assertEqual(payload["producer_sha256"], ga4_pull._sha256(ga4_pull.__file__))
        self.assertEqual(payload["pilot_binding"]["producer_file_sha256"],
                         payload["producer_sha256"])
        self.assertEqual(payload["event_contract"], {
            field: event for event, field in ga4_pull.EVENT_FIELDS.items()
        })
        self.assertEqual(set(payload["query_coverage"]), set(ga4_pull.GA4_QUERY_NAMES))
        self.assertEqual(payload["pilot_measurement_contract"],
                         ga4_pull.PILOT_MEASUREMENT_CONTRACT)
        self.assertEqual(payload["pilot_schema_contract"],
                         ga4_pull.ga4_schema.PILOT_MEASUREMENT_FIELDS)
        self.assertEqual(payload["pilot_binding"]["pilot_contract_sha256"],
                         ga4_pull._sha256(
                             Path(ga4_pull.ROOT) / "release" / "funnel_pilot.json"
                         ))

    def test_ga4_source_and_medium_are_distinct_attributions(self):
        agg = {}
        details = {}

        def slot(key):
            return agg.setdefault(key, {field: 0 for field in ga4_pull.EVENT_FIELDS.values()})

        def remember(key, attribution):
            details[key] = attribution

        ga4_pull.fold_event_rows([
            ("google", "organic", "affiliate_click", "2"),
            ("google", "cpc", "affiliate_click", "3"),
        ], slot, remember)
        self.assertEqual(set(agg), {"google / organic", "google / cpc"})
        self.assertEqual(agg["google / organic"]["affiliate_click"], 2)
        self.assertEqual(details["google / cpc"]["medium"], "cpc")

    def test_ga4_pull_emits_source_medium_rows_and_requests_medium_for_events(self):
        client = mock.Mock()
        client.run_report.side_effect = [
            ga_report([
                ga_row(["google", "organic"], "10"),
                ga_row(["google", "cpc"], "5"),
            ]),
            ga_report([
                ga_row(["google", "organic", "affiliate_click"], "2"),
                ga_row(["google", "cpc", "affiliate_click"], "3"),
            ]),
        ]
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "metrics.csv"
            with (
                mock.patch.object(ga4_pull, "_get", return_value="123"),
                mock.patch.object(ga4_pull, "_api_client", return_value=self.fake_api(client)),
                mock.patch.object(ga4_pull, "_host_exclude", return_value=object()),
            ):
                result = ga4_pull.pull(CAPTURE, str(output))
            with output.open(encoding="utf-8", newline="") as handle:
                rows = list(csv.DictReader(handle))
        self.assertEqual(result["attributions"], 2)
        self.assertEqual({row["source"] for row in rows},
                         {"google / organic", "google / cpc"})
        self.assertEqual({row["medium"] for row in rows}, {"organic", "cpc"})
        event_request = client.run_report.call_args_list[1].args[0]
        self.assertEqual(event_request["property"], "properties/123")
        self.assertEqual([item["name"] for item in event_request["dimensions"]],
                         ["sessionSource", "sessionMedium", "eventName"])
        self.assertEqual(event_request["limit"], ga4_pull.GA4_ROW_LIMIT)
        self.assertEqual(event_request["offset"], 0)
        self.assertEqual([
            item["dimension"]["dimension_name"] for item in event_request["order_bys"]
        ], ["sessionSource", "sessionMedium", "eventName"])
        self.assertEqual(result["query_coverage"]["source_events"]["rows_fetched"], 2)

    def test_ga4_pilot_materializes_exact_session_operands_and_dimensions(self):
        contract = ga4_pull.PILOT_MEASUREMENT_CONTRACT
        target = contract["target"]
        client = mock.Mock()
        client.run_report.side_effect = [
            ga_report([ga_row([
                "affiliate_click", "/credit-card-salary-30000-2026",
                "/credit-card-salary-30000-2026?utm_content=social_card",
                "social_card",
                target["provider"], target["cta_id"], target["position"],
                target["content_id"], "social_card", target["sub_id"],
                target["channel"], target["campaign"],
            ], "2"), ga_row([
                "affiliate_click", "/credit-card-salary-30000-2026",
                "/another-landing?utm_content=social_card", "social_card",
                target["provider"], target["cta_id"], target["position"],
                target["content_id"], "social_card", target["sub_id"],
                target["channel"], target["campaign"],
            ], "4")]),
            ga_report([
                ga_row([
                    "/credit-card-salary-30000-2026?utm_content=social_card",
                    "social_card",
                ], "5"),
                ga_row([
                    "/credit-card-salary-30000-2026", "(not set)"
                ], "3"),
            ]),
        ]
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "pilot.csv"
            with (
                mock.patch.object(ga4_pull, "_api_client",
                                  return_value=self.fake_api(client)),
                mock.patch.object(ga4_pull, "_host_exclude", return_value=object()),
                mock.patch.object(ga4_pull, "_assert_pilot_context_current"),
            ):
                result = ga4_pull.pull_pilot_sessions(
                    CAPTURE, pilot_context(), str(output)
                )
            with output.open(encoding="utf-8", newline="") as handle:
                rows = list(csv.DictReader(handle))
        self.assertIsNotNone(result)
        self.assertEqual(len(rows), 2)
        social = next(row for row in rows
                      if row["acquisition_content_id"] == "social_card")
        self.assertEqual(social["affiliate_click_sessions"], "2")
        self.assertEqual(social["qualified_landing_sessions"], "5")
        self.assertEqual(social["provider"], "ktccard")
        self.assertEqual(social["cta_id"], "salary30000-ktc-lower")
        self.assertEqual(social["measurement_scope"], "session")
        self.assertEqual(set(result["query_coverage"]), {
            "pilot_affiliate_sessions", "pilot_qualified_landings"
        })
        for call, query_name in zip(
            client.run_report.call_args_list,
            ("affiliate_click_sessions", "qualified_landing_sessions"),
        ):
            request = call.args[0]
            self.assertEqual(request["metrics"], [{"name": "sessions"}])
            self.assertEqual(
                [item["name"] for item in request["dimensions"]],
                contract["queries"][query_name]["dimensions"],
            )
            self.assertEqual(request["limit"], ga4_pull.GA4_ROW_LIMIT)

    def test_ga4_pilot_impossible_ratio_does_not_overwrite_existing_file(self):
        target = ga4_pull.PILOT_MEASUREMENT_CONTRACT["target"]
        client = mock.Mock()
        client.run_report.side_effect = [
            ga_report([ga_row([
                "affiliate_click", "/credit-card-salary-30000-2026",
                "/credit-card-salary-30000-2026?utm_content=social_card",
                "social_card",
                target["provider"], target["cta_id"], target["position"],
                target["content_id"], "social_card", target["sub_id"],
                target["channel"], target["campaign"],
            ], "3")]),
            ga_report([ga_row([
                "/credit-card-salary-30000-2026?utm_content=social_card",
                "social_card",
            ], "2")]),
        ]
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "pilot.csv"
            output.write_text("old\n", encoding="utf-8")
            with (
                mock.patch.object(ga4_pull, "_api_client",
                                  return_value=self.fake_api(client)),
                mock.patch.object(ga4_pull, "_host_exclude", return_value=object()),
                mock.patch.object(ga4_pull, "_assert_pilot_context_current"),
            ):
                result = ga4_pull.pull_pilot_sessions(
                    CAPTURE, pilot_context(), str(output)
                )
            self.assertIsNone(result)
            self.assertEqual(output.read_text(encoding="utf-8"), "old\n")

    def test_ga4_pilot_rejects_conflicting_landing_acquisition_values(self):
        with self.assertRaisesRegex(ValueError, "acquisition values disagree"):
            ga4_pull._landing_acquisition(
                "/credit-card-salary-30000-2026"
                "?content_id=source_a&utm_content=source_b",
                "source_b",
                "/credit-card-salary-30000-2026",
            )

    def test_ga4_pilot_context_binds_exact_audited_cta_bytes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "release").mkdir()
            (root / "site").mkdir()
            source_root = Path(ga4_pull.ROOT)
            pilot_path = root / "release" / "funnel_pilot.json"
            page_path = root / "site" / "credit-card-salary-30000-2026.html"
            pilot_path.write_bytes(
                (source_root / "release" / "funnel_pilot.json").read_bytes()
            )
            page_path.write_bytes(
                (source_root / "site" / page_path.name).read_bytes()
            )
            frozen = ga4_pull._pilot_capture_context(repo=root, site_dir=root / "site")
            self.assertEqual(frozen["target"]["sub_id"],
                             "website_salary30k-lower_ktccard")
            self.assertEqual(frozen["pilot_contract_sha256"],
                             ga4_pull._sha256(pilot_path))
            changed_producer = dict(frozen)
            changed_producer["producer_file_sha256"] = "0" * 64
            with self.assertRaisesRegex(ValueError, "pilot producer changed"):
                ga4_pull._assert_pilot_context_current(changed_producer)
            page_path.write_text(
                page_path.read_text(encoding="utf-8").replace(
                    'data-pos="after-faq"', 'data-pos="drifted"', 1
                ),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "data-pos drifted"):
                ga4_pull._pilot_capture_context(repo=root, site_dir=root / "site")

    def test_ga4_paginates_to_row_count_with_deterministic_offsets(self):
        client = mock.Mock()
        client.run_report.side_effect = [
            ga_report([
                ga_row(["a", "organic"], "1"),
                ga_row(["b", "organic"], "1"),
            ], row_count=3),
            ga_report([ga_row(["c", "organic"], "1")], row_count=3),
            ga_report([], row_count=0),
        ]
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "metrics.csv"
            with (
                mock.patch.object(ga4_pull, "GA4_ROW_LIMIT", 2),
                mock.patch.object(ga4_pull, "_get", return_value="123"),
                mock.patch.object(ga4_pull, "_api_client", return_value=self.fake_api(client)),
                mock.patch.object(ga4_pull, "_host_exclude", return_value=object()),
            ):
                result = ga4_pull.pull(CAPTURE, str(output))
        self.assertIsNotNone(result)
        self.assertEqual(
            [call.args[0]["offset"] for call in client.run_report.call_args_list],
            [0, 2, 0],
        )
        evidence = result["query_coverage"]["source_sessions"]
        self.assertEqual(evidence["api_row_count"], 3)
        self.assertEqual(evidence["page_row_counts"], [2, 1])
        self.assertEqual(evidence["response_row_counts"], [3, 3])
        self.assertTrue(evidence["complete"])
        self.assertFalse(evidence["truncated"])

    def test_ga4_missing_or_changing_row_count_fails_closed(self):
        constructor = lambda **kwargs: kwargs
        request = {"order_bys": [{"dimension": {"dimension_name": "x"}}]}
        missing = mock.Mock()
        missing.run_report.return_value = SimpleNamespace(rows=[])
        with self.assertRaisesRegex(ValueError, "no row_count evidence"):
            ga4_pull._run_paginated_report(missing, constructor, request, "fixture")

        changed = mock.Mock()
        changed.run_report.side_effect = [
            ga_report([ga_row(["a"], "1"), ga_row(["b"], "1")], row_count=3),
            ga_report([ga_row(["c"], "1")], row_count=4),
        ]
        with (mock.patch.object(ga4_pull, "GA4_ROW_LIMIT", 2),
              self.assertRaisesRegex(ValueError, "row_count changed")):
            ga4_pull._run_paginated_report(changed, constructor, request, "fixture")

    def test_ga4_channel_event_subquery_failure_is_not_zero_filled(self):
        client = mock.Mock()
        client.run_report.side_effect = [ga_report([]), RuntimeError("event query failed")]
        with (
            tempfile.TemporaryDirectory() as tmp,
            mock.patch.object(ga4_pull, "_get", return_value="123"),
            mock.patch.object(ga4_pull, "_api_client", return_value=self.fake_api(client)),
            mock.patch.object(ga4_pull, "_host_exclude", return_value=object()),
            mock.patch.object(ga4_pull, "OUT", str(Path(tmp) / "metrics.csv")),
        ):
            self.assertIsNone(ga4_pull.pull(CAPTURE))
            self.assertFalse((Path(tmp) / "metrics.csv").exists())

    def test_ga4_page_event_contract_covers_all_decision_events(self):
        client = mock.Mock()
        client.run_report.side_effect = [
            ga_report([ga_row(["/offer"], "10")]),
            ga_report([
                ga_row(["/offer", "affiliate_click"], "4"),
                ga_row(["/offer", "buy_intent_click"], "3"),
                ga_row(["/offer", "line_lead_click"], "2"),
                ga_row(["/offer", "video_start"], "1"),
            ]),
        ]
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "pages.csv"
            with (
                mock.patch.object(ga4_pull, "_get", return_value="123"),
                mock.patch.object(ga4_pull, "_api_client", return_value=self.fake_api(client)),
                mock.patch.object(ga4_pull, "_host_exclude", return_value=object()),
            ):
                self.assertIsNotNone(ga4_pull.pull_pages(CAPTURE, str(output)))
            with output.open(encoding="utf-8", newline="") as handle:
                rows = list(csv.DictReader(handle))
        self.assertEqual(len(rows), 1)
        for field, expected in (("affiliate_click", "4"), ("buy_intent_click", "3"),
                                ("line_lead_click", "2"), ("video_start", "1")):
            self.assertEqual(rows[0][field], expected)

    def test_ga4_malformed_count_does_not_overwrite_existing_file(self):
        client = mock.Mock()
        client.run_report.side_effect = [
            ga_report([ga_row(["google", "organic"], "not-a-number")]),
        ]
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "metrics.csv"
            output.write_text("old\n", encoding="utf-8")
            with (
                mock.patch.object(ga4_pull, "_get", return_value="123"),
                mock.patch.object(ga4_pull, "_api_client", return_value=self.fake_api(client)),
                mock.patch.object(ga4_pull, "_host_exclude", return_value=object()),
            ):
                self.assertIsNone(ga4_pull.pull(CAPTURE, str(output)))
            self.assertEqual(output.read_text(encoding="utf-8"), "old\n")

    def test_ga4_page_event_subquery_failure_is_not_zero_filled(self):
        client = mock.Mock()
        client.run_report.side_effect = [ga_report([]), RuntimeError("event query failed")]
        with (
            tempfile.TemporaryDirectory() as tmp,
            mock.patch.object(ga4_pull, "_get", return_value="123"),
            mock.patch.object(ga4_pull, "_api_client", return_value=self.fake_api(client)),
            mock.patch.object(ga4_pull, "_host_exclude", return_value=object()),
            mock.patch.object(ga4_pull, "OUT_PAGES", str(Path(tmp) / "pages.csv")),
        ):
            self.assertIsNone(ga4_pull.pull_pages(CAPTURE))
            self.assertFalse((Path(tmp) / "pages.csv").exists())

    def test_gsc_cli_propagates_pull_failure(self):
        with mock.patch.object(gsc_pull, "pull", return_value=None):
            self.assertEqual(gsc_pull.main(), 3)
        with mock.patch.object(gsc_pull, "pull", return_value={}):
            self.assertEqual(gsc_pull.main(), 0)

    def test_gsc_help_and_invalid_arguments_never_pull(self):
        with mock.patch.object(gsc_pull, "pull") as pull:
            with self.assertRaises(SystemExit) as raised:
                gsc_pull.main(["--help"])
            self.assertEqual(raised.exception.code, 0)
            pull.assert_not_called()
        with mock.patch.object(gsc_pull, "pull") as pull:
            with self.assertRaises(SystemExit) as raised:
                gsc_pull.main(["--unexpected"])
            self.assertEqual(raised.exception.code, 2)
            pull.assert_not_called()

    def test_gsc_cli_separates_unavailable_prerequisites_from_runtime_failure(self):
        with mock.patch.object(gsc_pull, "_api_service", return_value=None):
            self.assertEqual(gsc_pull.main(), 2)

        with (
            mock.patch.object(gsc_pull, "_api_service", return_value=object()),
            mock.patch.object(gsc_pull, "_capture_context", return_value=GSC_CAPTURE),
            mock.patch.object(gsc_pull, "_resolve_site", return_value=None),
        ):
            self.assertEqual(gsc_pull.main(), 2)

        with mock.patch.object(
            gsc_pull, "_api_service", side_effect=OSError("client init failed")
        ):
            self.assertEqual(gsc_pull.main(), 3)

        service = mock.Mock()
        service.sites.return_value.list.return_value.execute.side_effect = RuntimeError(
            "sites API failed"
        )
        with self.assertRaises(RuntimeError):
            gsc_pull._resolve_site(service)

    def test_gsc_normalizes_and_aggregates_duplicate_queries(self):
        rows, counts = gsc_pull._aggregate_rows([
            {"keys": ["  บัตร   เครดิต "], "clicks": 1, "impressions": 10,
             "ctr": 0.1, "position": 2},
            {"keys": ["บัตร เครดิต"], "clicks": 2, "impressions": 20,
             "ctr": 0.1, "position": 5},
        ], "query")
        self.assertEqual(rows, [("บัตร เครดิต", 3, 30, 10.0, 4.0)])
        self.assertEqual(counts, {"api_rows": 2, "output_rows": 1,
                                  "duplicate_rows_collapsed": 1})

    def test_gsc_partial_page_failure_does_not_touch_bundle(self):
        service = FakeGSC([
            {"rows": [{"keys": ["loan"], "clicks": 1, "impressions": 10,
                       "ctr": 0.1, "position": 2}]},
            RuntimeError("page query failed"),
        ])
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            outputs = [root / name for name in ("queries.csv", "pages.csv", "snapshot.json")]
            for path in outputs:
                path.write_text("old-%s\n" % path.name, encoding="utf-8")
            with (
                mock.patch.object(gsc_pull, "OUT", str(outputs[0])),
                mock.patch.object(gsc_pull, "OUTP", str(outputs[1])),
                mock.patch.object(gsc_pull, "OUT_SNAPSHOT", str(outputs[2])),
                mock.patch.object(gsc_pull, "_api_service", return_value=service),
                mock.patch.object(gsc_pull, "_resolve_site", return_value="sc-domain:example.test"),
                mock.patch.object(gsc_pull, "_capture_context", return_value=GSC_CAPTURE),
            ):
                self.assertIsNone(gsc_pull.pull())
            for path in outputs:
                self.assertEqual(path.read_text(encoding="utf-8"), "old-%s\n" % path.name)

    def test_gsc_success_writes_normalized_bundle_with_exact_coverage(self):
        service = FakeGSC([
            {"rows": [
                {"keys": [" Loan  Thai "], "clicks": 1, "impressions": 10,
                 "ctr": 0.1, "position": 2},
                {"keys": ["loan thai"], "clicks": 2, "impressions": 20,
                 "ctr": 0.1, "position": 5},
            ]},
            {"rows": [
                {"keys": ["https://example.test/loan"], "clicks": 3,
                 "impressions": 30, "ctr": 0.1, "position": 4},
            ]},
        ])
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            queries, pages, snapshot = (root / "queries.csv", root / "pages.csv",
                                        root / "snapshot.json")
            with (
                mock.patch.object(gsc_pull, "OUT", str(queries)),
                mock.patch.object(gsc_pull, "OUTP", str(pages)),
                mock.patch.object(gsc_pull, "OUT_SNAPSHOT", str(snapshot)),
                mock.patch.object(gsc_pull, "_api_service", return_value=service),
                mock.patch.object(gsc_pull, "_resolve_site", return_value="sc-domain:example.test"),
                mock.patch.object(gsc_pull, "_capture_context", return_value=GSC_CAPTURE),
            ):
                result = gsc_pull.pull()
            with queries.open(encoding="utf-8", newline="") as handle:
                query_rows = list(csv.DictReader(handle))
            metadata = json.loads(snapshot.read_text(encoding="utf-8"))
        self.assertEqual(result["queries"], 1)
        self.assertEqual(query_rows[0], {"query": "loan thai", "clicks": "3",
                                         "impressions": "30", "ctr": "10.0",
                                         "position": "4.0"})
        self.assertEqual(metadata["coverage"]["queries"]["api_rows"], 2)
        self.assertEqual(metadata["coverage"]["queries"]["rows"], 1)
        self.assertEqual(metadata["coverage"]["queries"]["duplicate_rows_collapsed"], 1)
        self.assertEqual(metadata["site_url"], "sc-domain:example.test")
        for _site, body in service.analytics.bodies:
            self.assertEqual((body["startDate"], body["endDate"]),
                             ("2026-07-17", "2026-08-13"))

    def test_gsc_malformed_numeric_fails_closed(self):
        with self.assertRaises(ValueError):
            gsc_pull._aggregate_rows([
                {"keys": ["loan"], "clicks": "bad", "impressions": 10,
                 "ctr": 0.0, "position": 1},
            ], "query")

    def test_gsc_metadata_records_coverage_and_finalization_state(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            files = {name: root / (name + ".csv") for name in ("queries", "pages")}
            for path in files.values():
                path.write_text("key,clicks,impressions,ctr,position\n", encoding="utf-8")
            snapshot = root / "snapshot.json"
            coverage = {
                "queries": {"row_limit": gsc_pull.ROW_LIMIT, "rows": 1,
                            "api_rows": 2, "output_rows": 1,
                            "duplicate_rows_collapsed": 1, "truncated": False},
                "pages": {"row_limit": gsc_pull.ROW_LIMIT, "rows": 0,
                          "api_rows": 0, "output_rows": 0,
                          "duplicate_rows_collapsed": 0, "truncated": False},
            }
            gsc_pull._write_snapshot_metadata(
                coverage=coverage, context=GSC_CAPTURE,
                files={name: str(path) for name, path in files.items()},
                output_path=str(snapshot),
            )
            payload = json.loads(snapshot.read_text(encoding="utf-8"))
        self.assertEqual(payload["coverage"], coverage)
        self.assertEqual(payload["finalization_lag_days"], 3)
        self.assertEqual(payload["window_end"], "2026-08-13")
        self.assertEqual(payload["site_url"], "sc-domain:example.test")
        self.assertEqual(payload["schema_version"], 2)
        self.assertEqual(payload["producer_sha256"], gsc_pull._sha256(gsc_pull.__file__))
        self.assertEqual(gsc_pull.ROW_LIMIT, 25_000)


if __name__ == "__main__":
    unittest.main(verbosity=2)
