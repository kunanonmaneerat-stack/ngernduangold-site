#!/usr/bin/env python3
import datetime as dt
import hashlib
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest import mock

try:
    from . import observation_snapshot as obs
except ImportError:  # Direct ``python pipeline/test_observation_snapshot.py`` execution.
    import observation_snapshot as obs

try:
    from tools.content_source_gate import build_queue_attestation
except ImportError:  # Direct execution adds ``tools`` through observation_snapshot.
    from content_source_gate import build_queue_attestation


class ObservationBundleTests(unittest.TestCase):
    def ga4_coverage(self, rows=0):
        limit = obs.ga4_pull.GA4_ROW_LIMIT
        pages = max(1, (rows + limit - 1) // limit)
        page_counts = ([0] if rows == 0 else [
            min(limit, rows - index * limit) for index in range(pages)
        ])
        item = {
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
        return {name: dict(item) for name in obs.ga4_pull.GA4_QUERY_NAMES}

    def metadata(self, now, files, *, start="2026-07-20", end="2026-08-16",
                 extra=None):
        payload = {
            "schema_version": 2,
            "captured_at": now.isoformat(),
            "window_start": start,
            "window_end": end,
            "window_days": 28,
            "files": {name: obs.sha256_file(path) for name, path in files.items()},
            "query_coverage": self.ga4_coverage(),
        }
        payload.update(extra or {})
        return payload

    def test_current_bundle_requires_exact_hashes_and_28_dates(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            a = root / "a.csv"
            b = root / "b.csv"
            a.write_text("x\n1\n", encoding="utf-8")
            b.write_text("y\n2\n", encoding="utf-8")
            now = dt.datetime(2026, 8, 16, 4, tzinfo=dt.timezone.utc)
            meta = root / "meta.json"
            meta.write_text(json.dumps({
                "schema_version": 2,
                "captured_at": now.isoformat(),
                "window_start": "2026-07-20",
                "window_end": "2026-08-16",
                "window_days": 28,
                "files": {"a": obs.sha256_file(a), "b": obs.sha256_file(b)},
            }), encoding="utf-8")
            result = obs.validate_bundle(meta, {"a": a, "b": b}, now=now)
            self.assertTrue(result["decisionable"])
            self.assertTrue(result["metadata_valid"])
            self.assertTrue(result["freshness_current"])
            self.assertEqual(result["expires_at"], "2026-08-16T17:00:00+00:00")
            expired = obs.validate_bundle(
                meta, {"a": a, "b": b},
                now=dt.datetime(2026, 8, 16, 17, tzinfo=dt.timezone.utc),
            )
            self.assertEqual(expired["state"], "STALE_WINDOW")
            self.assertFalse(expired["decisionable"])
            a.write_text("x\nchanged\n", encoding="utf-8")
            result = obs.validate_bundle(meta, {"a": a, "b": b}, now=now)
            self.assertFalse(result["decisionable"])
            self.assertEqual(result["state"], "HASH_MISMATCH")

    def test_metadata_json_rejects_duplicate_keys_and_nonfinite_numbers(self):
        now = dt.datetime(2026, 8, 16, 4, tzinfo=dt.timezone.utc)
        prefix = (
            '{"schema_version":2,"captured_at":'
            '"2026-08-16T04:00:00+00:00","window_start":"2026-07-20",'
            '"window_end":"2026-08-16","window_days":28,"files":{}'
        )
        with tempfile.TemporaryDirectory() as tmp:
            meta = Path(tmp) / "meta.json"
            for raw in (
                prefix.replace(
                    '"schema_version":2',
                    '"schema_version":999,"schema_version":2',
                ) + "}",
                prefix + ',"unexpected":NaN}',
                prefix + ',"unexpected":Infinity}',
                prefix + ',"unexpected":1e999}',
            ):
                meta.write_text(raw, encoding="utf-8")
                result = obs.validate_bundle(meta, {}, now=now)
                self.assertFalse(result["decisionable"])
                self.assertEqual(result["state"], "MISSING_METADATA")

    def test_bundle_integer_contract_rejects_bool_and_equal_float(self):
        now = dt.datetime(2026, 8, 16, 4, tzinfo=dt.timezone.utc)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            data = root / "data.csv"
            data.write_text("x\n1\n", encoding="utf-8")
            meta = root / "meta.json"
            baseline = self.metadata(now, {"data": data})

            for field, invalid in (
                ("schema_version", 2.0),
                ("schema_version", True),
                ("window_days", 28.0),
                ("window_days", True),
            ):
                payload = dict(baseline)
                payload[field] = invalid
                meta.write_text(json.dumps(payload), encoding="utf-8")
                result = obs.validate_bundle(meta, {"data": data}, now=now)
                self.assertFalse(result["decisionable"], (field, invalid))
                self.assertEqual(result["state"], "INVALID_METADATA")

            meta.write_text(json.dumps(baseline), encoding="utf-8")
            for invalid_expected in (2.0, True):
                result = obs.validate_bundle(
                    meta,
                    {"data": data},
                    now=now,
                    expected_schema_version=invalid_expected,
                )
                self.assertFalse(result["decisionable"])
                self.assertEqual(result["state"], "INVALID_METADATA")

            for invalid_days in (28.0, True):
                result = obs.validate_bundle(
                    meta,
                    {"data": data},
                    now=now,
                    expected_days=invalid_days,
                )
                self.assertFalse(result["decisionable"])
                self.assertEqual(result["state"], "INVALID_METADATA")

    def test_nonfinite_or_overflowing_max_age_fails_closed_without_raising(self):
        now = dt.datetime(2026, 8, 16, 4, tzinfo=dt.timezone.utc)
        with tempfile.TemporaryDirectory() as tmp:
            meta = Path(tmp) / "meta.json"
            meta.write_text(json.dumps({
                "schema_version": 2,
                "captured_at": now.isoformat(),
                "window_start": "2026-07-20",
                "window_end": "2026-08-16",
                "window_days": 28,
                "files": {},
            }), encoding="utf-8")
            for value in (float("nan"), float("inf"), 1e308, 10 ** 1000):
                result = obs.validate_bundle(
                    meta, {}, now=now, max_age_hours=value
                )
                self.assertFalse(result["decisionable"])
                self.assertEqual(result["state"], "INVALID_METADATA")

    def test_bundle_is_bound_to_the_current_producer_code(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            data = root / "data.csv"
            producer = root / "producer.py"
            data.write_text("x\n1\n", encoding="utf-8")
            producer.write_text("# producer v1\n", encoding="utf-8")
            now = dt.datetime(2026, 8, 16, 4, tzinfo=dt.timezone.utc)
            meta = root / "meta.json"
            payload = self.metadata(now, {"data": data}, extra={
                "producer_sha256": obs.sha256_file(producer),
            })
            meta.write_text(json.dumps(payload), encoding="utf-8")
            current = obs.validate_bundle(
                meta, {"data": data}, now=now, producer_path=producer
            )
            self.assertTrue(current["decisionable"])
            producer.write_text("# producer v2\n", encoding="utf-8")
            changed = obs.validate_bundle(
                meta, {"data": data}, now=now, producer_path=producer
            )
            self.assertFalse(changed["decisionable"])
            self.assertEqual(changed["state"], "PRODUCER_MISMATCH")

    def test_missing_stale_and_wrong_window_fail_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            data = root / "data.csv"
            data.write_text("x\n", encoding="utf-8")
            now = dt.datetime(2026, 8, 16, 4, tzinfo=dt.timezone.utc)
            self.assertEqual(
                obs.validate_bundle(root / "missing", {"data": data}, now=now)["state"],
                "MISSING_METADATA",
            )
            meta = root / "meta.json"
            meta.write_text(json.dumps({
                "schema_version": 2,
                "captured_at": (now - dt.timedelta(hours=40)).isoformat(),
                "window_start": "2026-07-20",
                "window_end": "2026-08-16",
                "window_days": 28,
                "files": {"data": hashlib.sha256(data.read_bytes()).hexdigest()},
            }), encoding="utf-8")
            stale = obs.validate_bundle(meta, {"data": data}, now=now)
            self.assertEqual(stale["state"], "STALE_CAPTURE")
            self.assertTrue(stale["metadata_valid"])
            self.assertFalse(stale["freshness_current"])
            payload = json.loads(meta.read_text(encoding="utf-8"))
            payload["captured_at"] = now.isoformat()
            payload["window_start"] = "2026-07-19"
            meta.write_text(json.dumps(payload), encoding="utf-8")
            self.assertEqual(obs.validate_bundle(meta, {"data": data}, now=now)["state"], "INVALID_METADATA")

            self.assertEqual(
                obs.validate_bundle(
                    meta, {"data": data},
                    now=dt.datetime(2026, 8, 16, 4),
                )["state"],
                "INVALID_EVALUATION_TIME",
            )

    def test_fresh_but_historical_28_day_window_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            data = root / "data.csv"
            data.write_text("x\n1\n", encoding="utf-8")
            now = dt.datetime(2026, 8, 16, 4, tzinfo=dt.timezone.utc)
            meta = root / "meta.json"
            meta.write_text(json.dumps(self.metadata(
                now, {"data": data}, start="2020-01-01", end="2020-01-28"
            )), encoding="utf-8")
            result = obs.validate_bundle(meta, {"data": data}, now=now)
        self.assertFalse(result["decisionable"])
        self.assertEqual(result["state"], "STALE_WINDOW")
        self.assertTrue(result["metadata_valid"])

    def test_gsc_bundle_requires_exact_d3_finalization_contract(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            data = root / "data.csv"
            data.write_text("x\n1\n", encoding="utf-8")
            now = dt.datetime(2026, 8, 16, 4, tzinfo=dt.timezone.utc)
            meta = root / "meta.json"
            payload = self.metadata(
                now, {"data": data}, start="2026-07-17", end="2026-08-13",
                extra={"finalization_lag_days": 3},
            )
            meta.write_text(json.dumps(payload), encoding="utf-8")
            current = obs.validate_bundle(
                meta, {"data": data}, now=now, expected_lag_days=3
            )
            self.assertTrue(current["decisionable"])

            payload["finalization_lag_days"] = 2
            meta.write_text(json.dumps(payload), encoding="utf-8")
            self.assertEqual(obs.validate_bundle(
                meta, {"data": data}, now=now, expected_lag_days=3
            )["state"], "INVALID_METADATA")

            for invalid_lag in (3.0, True):
                payload["finalization_lag_days"] = invalid_lag
                meta.write_text(json.dumps(payload), encoding="utf-8")
                self.assertEqual(obs.validate_bundle(
                    meta, {"data": data}, now=now, expected_lag_days=3
                )["state"], "INVALID_METADATA")

            payload["finalization_lag_days"] = 3
            payload["window_end"] = "2026-08-16"
            payload["window_start"] = "2026-07-20"
            meta.write_text(json.dumps(payload), encoding="utf-8")
            self.assertEqual(obs.validate_bundle(
                meta, {"data": data}, now=now, expected_lag_days=3
            )["state"], "FUTURE_WINDOW")

    def test_csv_schema_and_numeric_domain_are_required(self):
        contract = {
            "required": {"name", "count"},
            "nonempty": {"name"},
            "nonnegative_int": {"count"},
        }
        now = dt.datetime(2026, 8, 16, 4, tzinfo=dt.timezone.utc)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            data = root / "data.csv"
            meta = root / "meta.json"
            data.write_text("name,count\nvalid,1\n", encoding="utf-8")
            meta.write_text(json.dumps(self.metadata(now, {"data": data})), encoding="utf-8")
            valid = obs.validate_bundle(
                meta, {"data": data}, now=now, csv_contracts={"data": contract}
            )
            self.assertTrue(valid["decisionable"])

            data.write_text("name,count\nvalid,-1\n", encoding="utf-8")
            meta.write_text(json.dumps(self.metadata(now, {"data": data})), encoding="utf-8")
            negative = obs.validate_bundle(
                meta, {"data": data}, now=now, csv_contracts={"data": contract}
            )
            self.assertEqual(negative["state"], "INVALID_DATA")

            data.write_text("name,wrong\nvalid,1\n", encoding="utf-8")
            meta.write_text(json.dumps(self.metadata(now, {"data": data})), encoding="utf-8")
            wrong_schema = obs.validate_bundle(
                meta, {"data": data}, now=now, csv_contracts={"data": contract}
            )
            self.assertEqual(wrong_schema["state"], "INVALID_DATA")

    def test_gsc_cross_field_math_and_exact_schema_are_required(self):
        contract = obs.GSC_CSV_CONTRACTS["queries"]
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "queries.csv"
            path.write_text(
                "query,clicks,impressions,ctr,position\nloan,1,10,10.0,2.0\n",
                encoding="utf-8",
            )
            self.assertEqual(obs.validate_csv(path, contract), (None, 1))
            path.write_text(
                "query,clicks,impressions,ctr,position\nloan,11,10,100,2.0\n",
                encoding="utf-8",
            )
            self.assertIn("clicks greater", obs.validate_csv(path, contract)[0])
            path.write_text(
                "query,clicks,impressions,ctr,position\nloan,1,10,99,2.0\n",
                encoding="utf-8",
            )
            self.assertIn("CTR inconsistent", obs.validate_csv(path, contract)[0])
            path.write_text(
                "query,clicks,impressions,ctr,position,extra\nloan,1,10,10,2,x\n",
                encoding="utf-8",
            )
            self.assertIn("canonical field order", obs.validate_csv(path, contract)[0])
            path.write_text(
                "query,clicks,impressions,ctr,position\n Loan ,1,10,10,2\n",
                encoding="utf-8",
            )
            self.assertIn("non-canonical query", obs.validate_csv(path, contract)[0])

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "metrics.csv"
            path.write_text(
                "source,raw_source,medium,channel,sessions,quiz_start,affiliate_click,buy_intent_click,answer_seen,line_lead_click,internal_cta_click,video_start\n"
                "google / organic,google,cpc,google,1,0,0,0,0,0,0,0\n",
                encoding="utf-8",
            )
            self.assertIn(
                "inconsistent source/medium",
                obs.validate_csv(path, obs.GA4_CSV_CONTRACTS["metrics"])[0],
            )
            path.write_text(
                "source,raw_source,medium,channel,sessions,quiz_start,affiliate_click,buy_intent_click,answer_seen,line_lead_click,internal_cta_click,video_start\n"
                "google / organic,google,organic,fb,1,0,0,0,0,0,0,0\n",
                encoding="utf-8",
            )
            self.assertIn(
                "inconsistent canonical channel",
                obs.validate_csv(path, obs.GA4_CSV_CONTRACTS["metrics"])[0],
            )

    def test_analytics_source_identity_is_mandatory_and_target_bound(self):
        base = {"decisionable": True, "state": "CURRENT", "metadata": {}}
        self.assertEqual(
            obs.require_source_identity(
                base, "ga4", expected_ga4_property="123456"
            )["state"],
            "SOURCE_IDENTITY_MISSING",
        )
        self.assertTrue(obs.require_source_identity({
            **base, "metadata": {
                "property_id": "123456",
                "event_contract": {
                    field: event for event, field in obs.ga4_pull.EVENT_FIELDS.items()
                },
            }
        }, "ga4", expected_ga4_property="123456")["decisionable"])
        self.assertEqual(obs.require_source_identity({
            **base, "metadata": {"property_id": "123456"}
        }, "ga4", expected_ga4_property="123456")["state"],
            "EVENT_CONTRACT_MISSING")
        self.assertEqual(obs.require_source_identity({
            **base, "metadata": {"property_id": "999999"}
        }, "ga4", expected_ga4_property="123456")["state"],
            "WRONG_SOURCE_IDENTITY")
        self.assertEqual(obs.require_source_identity({
            **base, "metadata": {"site_url": "sc-domain:example.test"}
        }, "gsc")["state"], "WRONG_SOURCE_IDENTITY")
        self.assertTrue(obs.require_source_identity({
            **base, "metadata": {"site_url": "sc-domain:ngernduangold.com"}
        }, "gsc")["decisionable"])

    def test_ga4_cross_file_event_totals_must_agree(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            files = {
                "metrics": root / "metrics.csv",
                "pages": root / "pages.csv",
                "funnel": root / "funnel.csv",
                "pilot_sessions": root / "pilot.csv",
            }
            files["metrics"].write_text(
                "source,quiz_start,affiliate_click,buy_intent_click,answer_seen,line_lead_click,internal_cta_click,video_start\n"
                "direct,1,2,1,0,0,0,0\n", encoding="utf-8"
            )
            files["pages"].write_text(
                "page,affiliate_click,buy_intent_click,answer_seen,line_lead_click,internal_cta_click,video_start\n"
                "/offer,2,1,0,0,0,0\n", encoding="utf-8"
            )
            files["funnel"].write_text(
                "stage,count\nquiz_start,1\naffiliate_click,2\n",
                encoding="utf-8",
            )
            files["pilot_sessions"].write_text(
                "provider,cta_id,position,content_id,acquisition_content_id,sub_id,channel,campaign,affiliate_click_sessions,qualified_landing_sessions,measurement_scope\n"
                "ktccard,salary30000-ktc-lower,after-faq,salary30k-2026,unattributed,website_salary30k-lower_ktccard,website,ktccard,1,2,session\n",
                encoding="utf-8",
            )
            base = {"decisionable": True, "state": "CURRENT"}
            self.assertTrue(
                obs.require_ga4_cross_file_consistency(base, files)["decisionable"]
            )
            files["pages"].write_text(
                "page,affiliate_click,buy_intent_click,answer_seen,line_lead_click,internal_cta_click,video_start\n"
                "/offer,1,1,0,0,0,0\n", encoding="utf-8"
            )
            mismatch = obs.require_ga4_cross_file_consistency(base, files)
            self.assertFalse(mismatch["decisionable"])
            self.assertEqual(mismatch["state"], "CROSS_FILE_MISMATCH")

            frozen = {
                name: obs._rows(path)
                for name, path in files.items()
            }
            files["pages"].write_text(
                "page,affiliate_click,buy_intent_click,answer_seen,line_lead_click,internal_cta_click,video_start\n"
                "/offer,2,1,0,0,0,0\n", encoding="utf-8"
            )
            self.assertTrue(
                obs.require_ga4_cross_file_consistency(base, files)["decisionable"]
            )
            frozen_result = obs.require_ga4_cross_file_consistency(
                base, tables=frozen
            )
            self.assertFalse(frozen_result["decisionable"])
            self.assertEqual(frozen_result["state"], "CROSS_FILE_MISMATCH")

    def test_integer_reader_preserves_values_above_float_precision(self):
        self.assertEqual(
            obs._int({"count": "9007199254740993"}, "count"),
            9007199254740993,
        )
        self.assertEqual(obs._int({"count": "1.5"}, "count"), 0)

    def test_ga4_pilot_provenance_is_hash_bound_and_fails_closed(self):
        frozen = obs.ga4_pull._pilot_capture_context()
        binding = {
            "pilot_id": frozen["pilot_id"],
            "pilot_contract_sha256": frozen["pilot_contract_sha256"],
            "pilot_page_sha256": frozen["pilot_page_sha256"],
            "schema_adapter_sha256": frozen["schema_adapter_sha256"],
            "producer_file_sha256": frozen["producer_file_sha256"],
            "producer_contract_sha256": frozen["producer_contract_sha256"],
            "target": frozen["target"],
        }
        base = {
            "decisionable": True,
            "state": "CURRENT",
            "metadata": {
                "pilot_measurement_contract": obs.ga4_pull.PILOT_MEASUREMENT_CONTRACT,
                "pilot_schema_contract": obs.ga4_schema.PILOT_MEASUREMENT_FIELDS,
                "pilot_binding": binding,
            },
        }
        self.assertTrue(obs.require_ga4_pilot_provenance(base)["decisionable"])
        drifted = json.loads(json.dumps(base))
        drifted["metadata"]["pilot_binding"]["pilot_page_sha256"] = "0" * 64
        self.assertEqual(
            obs.require_ga4_pilot_provenance(drifted)["state"],
            "PILOT_BINDING_MISMATCH",
        )
        missing = json.loads(json.dumps(base))
        del missing["metadata"]["pilot_binding"]["schema_adapter_sha256"]
        self.assertEqual(
            obs.require_ga4_pilot_provenance(missing)["state"],
            "PILOT_BINDING_MISSING",
        )

    def test_ga4_coverage_missing_truncated_and_mismatch_fail_closed(self):
        base = {"decisionable": True, "state": "CURRENT", "metadata": {}}
        self.assertEqual(obs.require_ga4_coverage(base)["state"], "COVERAGE_MISSING")
        coverage = self.ga4_coverage(rows=1)
        valid = obs.require_ga4_coverage({
            **base, "metadata": {"query_coverage": coverage}
        })
        self.assertTrue(valid["decisionable"])

        truncated = json.loads(json.dumps(coverage))
        truncated["page_views"]["truncated"] = True
        self.assertEqual(obs.require_ga4_coverage({
            **base, "metadata": {"query_coverage": truncated}
        })["state"], "TRUNCATED")

        mismatch = json.loads(json.dumps(coverage))
        mismatch["source_sessions"]["rows_fetched"] = 0
        result = obs.require_ga4_coverage({
            **base, "metadata": {"query_coverage": mismatch}
        })
        self.assertEqual(result["state"], "COVERAGE_ROW_MISMATCH")

    def test_gsc_coverage_requires_nontruncated_exact_row_counts(self):
        base = {
            "decisionable": True,
            "state": "CURRENT",
            "row_counts": {"queries": 2, "pages": 1},
            "metadata": {},
        }
        self.assertEqual(obs.require_gsc_coverage(base)["state"], "TRUNCATION_UNKNOWN")
        coverage = {
            "queries": {"row_limit": 25000, "rows": 2, "api_rows": 3,
                        "output_rows": 2, "duplicate_rows_collapsed": 1,
                        "truncated": False},
            "pages": {"row_limit": 25000, "rows": 1, "api_rows": 1,
                      "output_rows": 1, "duplicate_rows_collapsed": 0,
                      "truncated": False},
        }
        valid = obs.require_gsc_coverage({
            **base, "metadata": {"coverage": coverage}
        })
        self.assertTrue(valid["decisionable"])
        truncated = json.loads(json.dumps(coverage))
        truncated["pages"]["truncated"] = True
        truncated["pages"]["api_rows"] = 25000
        truncated["pages"]["duplicate_rows_collapsed"] = 24999
        self.assertEqual(obs.require_gsc_coverage({
            **base, "metadata": {"coverage": truncated}
        })["state"], "TRUNCATED")
        mismatch = json.loads(json.dumps(coverage))
        mismatch["queries"]["rows"] = 3
        self.assertEqual(obs.require_gsc_coverage({
            **base, "metadata": {"coverage": mismatch}
        })["state"], "COVERAGE_ROW_MISMATCH")

    def test_materialized_rows_remain_bound_to_accepted_hash_and_count(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "data.csv"
            path.write_text("name,count\na,1\n", encoding="utf-8")
            rows, fields = obs._rows(path)
            bundle = {
                "decisionable": True,
                "state": "CURRENT",
                "metadata": {"files": {"metrics": obs.sha256_file(path)}},
                "row_counts": {"metrics": 1},
            }
            self.assertTrue(obs.require_materialized_table(
                bundle, "metrics", path, rows, fields
            )["decisionable"])

            mismatch = obs.require_materialized_table(
                bundle, "metrics", path, [], fields
            )
            self.assertEqual(mismatch["state"], "MATERIALIZATION_ROW_MISMATCH")

            path.write_text("name,count\nb,2\n", encoding="utf-8")
            changed = obs.require_materialized_table(
                bundle, "metrics", path, rows, fields
            )
            self.assertEqual(changed["state"], "HASH_CHANGED_DURING_READ")

    def test_bundle_materialization_freezes_and_rechecks_every_table(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            metrics = root / "metrics.csv"
            pages = root / "pages.csv"
            metrics.write_text("name,count\na,1\n", encoding="utf-8")
            pages.write_text("name,count\nb,2\n", encoding="utf-8")
            files = {"metrics": metrics, "pages": pages}
            bundle = {
                "decisionable": True,
                "state": "CURRENT",
                "metadata": {
                    "files": {
                        name: obs.sha256_file(path)
                        for name, path in files.items()
                    }
                },
                "row_counts": {"metrics": 1, "pages": 1},
            }

            current, tables = obs.materialize_bundle_tables(bundle, files)
            self.assertTrue(current["decisionable"])
            self.assertEqual(set(tables), {"metrics", "pages"})
            self.assertEqual(tables["pages"][0][0]["count"], "2")

            pages.write_text("name,count\nb,3\n", encoding="utf-8")
            changed, frozen = obs.materialize_bundle_tables(bundle, files)
            self.assertEqual(changed["state"], "HASH_CHANGED_DURING_READ")
            self.assertEqual(changed["materialized_table"], "pages")
            self.assertEqual(frozen["pages"][0][0]["count"], "3")

    def test_learning_readiness_names_exact_repull_and_reconcile_actions(self):
        expected_end = dt.date(2026, 8, 16)
        decision_time = dt.datetime(2026, 8, 16, 12, tzinfo=obs.BANGKOK)
        expiry = (decision_time + dt.timedelta(hours=1)).isoformat()
        with mock.patch.object(
            obs.revenue_ledger, "learning_contract_errors", return_value=[]
        ) as revenue_check:
            ready = obs.build_learning_readiness(
                {
                    "decisionable": True,
                    "state": "CURRENT",
                    "capture_trust": "TRUSTED",
                    "current_trust": "TRUSTED",
                    "expires_at": expiry,
                },
                {"decisionable": True, "state": "CURRENT", "expires_at": expiry},
                {"quality_state": "CURRENT"},
                expected_end=expected_end,
                decision_time=decision_time,
            )
        revenue_check.assert_called_once_with(
            {"quality_state": "CURRENT"}, expected_end=expected_end,
            observed_at=decision_time,
        )
        self.assertTrue(ready["ready"])
        self.assertEqual(ready["score"], {"passed": 3, "total": 3})
        self.assertEqual(ready["actions"], [])
        self.assertEqual(ready["sources"]["ga4"]["action"], "NONE")

        with mock.patch.object(
            obs.revenue_ledger, "learning_contract_errors",
            return_value=["invalid revenue metric"],
        ):
            blocked = obs.build_learning_readiness(
                {"decisionable": False, "state": "UNTRUSTED_NOW"},
                {"decisionable": False, "state": "STALE"},
                {"quality_state": "INVALID_LEDGER"},
                expected_end=expected_end,
                decision_time=decision_time,
            )
        self.assertFalse(blocked["ready"])
        self.assertEqual(blocked["score"], {"passed": 0, "total": 3})
        self.assertEqual(
            {item["action"] for item in blocked["actions"]},
            {"REPAIR_GA4_TRUST_THEN_REPULL", "REPULL_GSC", "RECONCILE_REVENUE"},
        )
        self.assertEqual(blocked["sources"]["revenue"]["errors"],
                         ["invalid revenue metric"])

    def test_learning_readiness_repairs_ga4_trust_before_metadata_repull(self):
        expected_end = dt.date(2026, 8, 16)
        decision_time = dt.datetime(2026, 8, 16, 12, tzinfo=obs.BANGKOK)
        expiry = (decision_time + dt.timedelta(hours=1)).isoformat()
        with mock.patch.object(
            obs.revenue_ledger, "learning_contract_errors", return_value=[]
        ):
            current_untrusted = obs.build_learning_readiness(
                {
                    "decisionable": False,
                    "state": "INVALID_METADATA",
                    "capture_trust": "TRUSTED",
                    "current_trust": "UNTRUSTED",
                    "expires_at": expiry,
                },
                {"decisionable": True, "state": "CURRENT", "expires_at": expiry},
                {"quality_state": "CURRENT"},
                expected_end=expected_end,
                decision_time=decision_time,
            )
            current_trusted_capture_untrusted = obs.build_learning_readiness(
                {
                    "decisionable": False,
                    "state": "INVALID_METADATA",
                    "capture_trust": "UNTRUSTED",
                    "current_trust": "TRUSTED",
                    "expires_at": expiry,
                },
                {"decisionable": True, "state": "CURRENT", "expires_at": expiry},
                {"quality_state": "CURRENT"},
                expected_end=expected_end,
                decision_time=decision_time,
            )
            both_trusted_invalid_bundle = obs.build_learning_readiness(
                {
                    "decisionable": False,
                    "state": "INVALID_METADATA",
                    "capture_trust": "TRUSTED",
                    "current_trust": "TRUSTED",
                    "expires_at": expiry,
                },
                {"decisionable": True, "state": "CURRENT", "expires_at": expiry},
                {"quality_state": "CURRENT"},
                expected_end=expected_end,
                decision_time=decision_time,
            )

        self.assertEqual(
            current_untrusted["sources"]["ga4"]["action"],
            "REPAIR_GA4_TRUST_THEN_REPULL",
        )
        self.assertEqual(
            current_untrusted["actions"][0],
            {
                "source": "ga4",
                "action": "REPAIR_GA4_TRUST_THEN_REPULL",
                "reason_code": "INVALID_METADATA",
            },
        )
        self.assertEqual(
            current_untrusted["sources"]["ga4"]["errors"],
            ["GA4 capture/current trust is missing or untrusted"],
        )
        self.assertEqual(
            current_trusted_capture_untrusted["sources"]["ga4"]["action"],
            "REPULL_GA4",
        )
        self.assertEqual(
            both_trusted_invalid_bundle["sources"]["ga4"]["action"],
            "REPULL_GA4",
        )

    def test_official_snapshot_missing_stale_invalid_and_pending_block(self):
        now = dt.datetime(2026, 8, 16, 4, tzinfo=dt.timezone.utc)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = root / "official.json"
            self.assertEqual(obs.validate_official_snapshot(path, now=now)["state"], "MISSING")
            path.write_text("{}", encoding="utf-8")
            self.assertEqual(obs.validate_official_snapshot(path, now=now)["state"], "INVALID")
            payload = {
                "schema": 2,
                "checked_at": (now - dt.timedelta(days=9)).isoformat(),
                "changed": [], "errors": [], "review_required": [],
                "sources": [{"id": "official-1"}],
            }
            path.write_text(json.dumps(payload), encoding="utf-8")
            self.assertEqual(obs.validate_official_snapshot(path, now=now)["state"], "INVALID")
            payload["checked_at"] = now.isoformat()
            payload["changed"] = ["official-1"]
            path.write_text(json.dumps(payload), encoding="utf-8")
            self.assertEqual(obs.validate_official_snapshot(path, now=now)["state"], "INVALID")
            payload["changed"] = []
            payload["review_required"] = ["official-1"]
            path.write_text(json.dumps(payload), encoding="utf-8")
            pending = obs.validate_official_snapshot(path, now=now)
            self.assertEqual(pending["state"], "INVALID")
            self.assertFalse(pending["current"])
            payload["review_required"] = []
            path.write_text(json.dumps(payload), encoding="utf-8")
            clean = obs.validate_official_snapshot(path, now=now)
            self.assertEqual(clean["state"], "INVALID")
            self.assertFalse(clean["clear_for_publication"])

    def test_official_snapshot_schema3_preserves_fresh_pending_review_state(self):
        now = dt.datetime(2026, 8, 16, 15, tzinfo=dt.timezone.utc)
        checked_at = (now - dt.timedelta(minutes=10)).isoformat(timespec="seconds")
        def source_row(source_id):
            url = "https://official.example/%s" % source_id
            digest = hashlib.sha256(source_id.encode("utf-8")).hexdigest()
            return {
                "id": source_id,
                "url": url,
                "kind": "html",
                "http_status": 200,
                "final_url": url,
                "content_type": "text/html",
                "etag": "",
                "last_modified": "",
                "bytes": 10,
                "raw_sha256": digest,
                "sha256": digest,
                "fingerprint_method": "visible-text-v1",
                "checked_at": checked_at,
                "change": "unchanged",
            }
        rows = [source_row("official-1"), source_row("official-2")]
        pending_ids = ["official-1", "official-2"]
        payload = {
            "schema": 3,
            "checked_at": checked_at,
            "purpose": "change detection only; review official source before publishing",
            "summary": {
                "configured_sources": 2,
                "checked_sources": 2,
                "successful_sources": 2,
                "changed_this_run": 0,
                "current_errors": 0,
                "pending_owner_reviews": 2,
                "acknowledged_this_run": 0,
                "network_probe": "COMPLETE",
                "freshness_state": "FRESH_REVIEW_REQUIRED",
            },
            "changed": [],
            "errors": [],
            "review_required": pending_ids,
            "review_queue": [{
                "source_id": source_id,
                "trigger": "carried_forward_unreviewed",
                "pending_since": checked_at,
                "last_checked_at": checked_at,
                "current_state": "unchanged",
                "acknowledgement_status": "PENDING_OWNER_REVIEW",
            } for source_id in pending_ids],
            "acknowledged_this_run": [],
            "acknowledgement_log": [],
            "sources": rows,
        }
        payload["queue_attestation"] = build_queue_attestation(
            None,
            configured_source_ids=pending_ids,
            pending_ids=pending_ids,
            acknowledged_ids=[],
            checked_at=checked_at,
            sources=rows,
            bootstrap=True,
        )
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "official.json"
            path.write_text(json.dumps(payload), encoding="utf-8")
            pending = obs.validate_official_snapshot(path, now=now)
            self.assertEqual(pending["state"], "FRESH_REVIEW_REQUIRED")
            self.assertTrue(pending["current"])
            self.assertFalse(pending["clear_for_publication"])
            self.assertEqual(pending["errors"], 0)
            self.assertEqual(pending["review_required"], 2)
            self.assertEqual(
                pending["expires_at"],
                (dt.datetime.fromisoformat(checked_at) + dt.timedelta(hours=24))
                .isoformat(timespec="seconds"),
            )

            at_boundary = obs.validate_official_snapshot(
                path,
                now=dt.datetime.fromisoformat(checked_at) + dt.timedelta(hours=24),
            )
            self.assertEqual(at_boundary["state"], "FRESH_REVIEW_REQUIRED")
            self.assertTrue(at_boundary["current"])

            stale = obs.validate_official_snapshot(
                path,
                now=dt.datetime.fromisoformat(checked_at) + dt.timedelta(hours=25),
            )
            self.assertEqual(stale["state"], "STALE")
            self.assertFalse(stale["current"])
            self.assertFalse(stale["clear_for_publication"])
            self.assertEqual(stale["checked_at"], checked_at)
            self.assertEqual(stale["age_hours"], 25.0)
            self.assertEqual(
                stale["expires_at"],
                (dt.datetime.fromisoformat(checked_at) + dt.timedelta(hours=24))
                .isoformat(timespec="seconds"),
            )
            self.assertEqual(
                stale["contract_errors"],
                ["official source snapshot is stale"],
            )
            self.assertEqual(stale["changed"], 0)
            self.assertEqual(stale["errors"], 0)
            self.assertEqual(stale["review_required"], 2)

            drifted = json.loads(json.dumps(payload))
            drifted["summary"]["pending_owner_reviews"] = 0
            path.write_text(json.dumps(drifted), encoding="utf-8")
            self.assertEqual(
                obs.validate_official_snapshot(path, now=now)["state"], "INVALID"
            )

            forged_clean = json.loads(json.dumps(payload))
            forged_clean["review_required"] = []
            forged_clean["review_queue"] = []
            forged_clean["summary"]["pending_owner_reviews"] = 0
            forged_clean["summary"]["freshness_state"] = "CURRENT"
            path.write_text(json.dumps(forged_clean), encoding="utf-8")
            clean = obs.validate_official_snapshot(path, now=now)
            self.assertEqual(clean["state"], "INVALID")
            self.assertFalse(clean["clear_for_publication"])

    def test_ga4_requires_trusted_capture_and_current_trust(self):
        now = dt.datetime(2026, 8, 16, 4, tzinfo=dt.timezone.utc)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            ga4_files = {
                "metrics": root / "metrics.csv",
                "pages": root / "pages.csv",
                "funnel": root / "funnel.csv",
                "pilot_sessions": root / "pilot.csv",
            }
            ga4_files["metrics"].write_text(
                "source,raw_source,medium,channel,sessions,quiz_start,affiliate_click,buy_intent_click,answer_seen,line_lead_click,internal_cta_click,video_start\n"
                "(direct) / (none),(direct),(none),direct,1,0,0,0,0,0,0,0\n",
                encoding="utf-8"
            )
            ga4_files["pages"].write_text(
                "page,views,affiliate_click,buy_intent_click,answer_seen,line_lead_click,internal_cta_click,video_start\n"
                "/,1,0,0,0,0,0,0\n", encoding="utf-8"
            )
            ga4_files["funnel"].write_text(
                "stage,count,step_conv_pct,measurement_scope\n"
                "quiz_start,0,,independent_event_total_not_sequence\n"
                "quiz_complete,0,,independent_event_total_not_sequence\n"
                "recommendation_view,0,,independent_event_total_not_sequence\n"
                "affiliate_click,0,,independent_event_total_not_sequence\n", encoding="utf-8"
            )
            ga4_files["pilot_sessions"].write_text(
                "provider,cta_id,position,content_id,acquisition_content_id,sub_id,channel,campaign,affiliate_click_sessions,qualified_landing_sessions,measurement_scope\n",
                encoding="utf-8",
            )
            pilot_context = obs.ga4_pull._pilot_capture_context()
            pilot_binding = {
                "pilot_id": pilot_context["pilot_id"],
                "pilot_contract_sha256": pilot_context["pilot_contract_sha256"],
                "pilot_page_sha256": pilot_context["pilot_page_sha256"],
                "schema_adapter_sha256": pilot_context["schema_adapter_sha256"],
                "producer_file_sha256": pilot_context["producer_file_sha256"],
                "producer_contract_sha256": pilot_context["producer_contract_sha256"],
                "target": pilot_context["target"],
            }
            ga4_meta = root / "ga4.json"
            ga4_meta.write_text(json.dumps(self.metadata(
                now, ga4_files, extra={
                    "schema_version": 3,
                    "property_id": "123456",
                    "producer_sha256": obs.sha256_file(obs.GA4_PRODUCER),
                    "event_contract": {
                        field: event for event, field in obs.ga4_pull.EVENT_FIELDS.items()
                    },
                    "ga4_decision_trust": "UNTRUSTED",
                    "capture_time_trust": {
                        "trusted": False, "label": "UNTRUSTED",
                        "reason": "fixture capture not trusted", "schema": "test",
                        "expires_at": None,
                    },
                    "pilot_measurement_contract": obs.ga4_pull.PILOT_MEASUREMENT_CONTRACT,
                    "pilot_schema_contract": obs.ga4_schema.PILOT_MEASUREMENT_FIELDS,
                    "pilot_binding": pilot_binding,
                }
            )), encoding="utf-8")
            official = root / "official.json"
            official.write_text(json.dumps({
                "schema": 2, "checked_at": now.isoformat(), "changed": [],
                "errors": [], "review_required": [], "sources": [{"id": "one"}],
            }), encoding="utf-8")
            trusted = SimpleNamespace(
                label="TRUSTED", trusted=True, reason="ok", schema="test",
                expires_at=(now + dt.timedelta(days=1)).isoformat(),
            )
            with (mock.patch.object(obs, "GA4_FILES", ga4_files),
                  mock.patch.object(obs, "GA4_META", ga4_meta),
                  mock.patch.object(obs, "GSC_META", root / "missing-gsc.json"),
                  mock.patch.object(obs, "OFFICIAL", official),
                  mock.patch.object(obs.ga4_decision_trust, "evaluate_ga4_decision_trust",
                                    return_value=trusted),
                  mock.patch.object(obs, "_configured_ga4_property_id",
                                    return_value="123456"),
                  mock.patch.object(obs.revenue_ledger, "read_affiliate_revenue",
                                    return_value={"trusted": True, "error": None,
                                                  "confirmed_transactions": 0,
                                                  "net_revenue_thb": 0}) as revenue_reader):
                captured_untrusted = obs.collect(now=now)
            revenue_reader.assert_called_once_with(
                mock.ANY, today=dt.date(2026, 8, 16), days=28, now=now
            )
            self.assertEqual(captured_untrusted["sources"]["ga4"]["bundle"]["state"],
                             "UNTRUSTED_AT_CAPTURE")
            self.assertFalse(captured_untrusted["sources"]["ga4"]["bundle"]["decisionable"])

            payload = json.loads(ga4_meta.read_text(encoding="utf-8"))
            payload["ga4_decision_trust"] = "TRUSTED"
            payload["capture_time_trust"] = {
                "trusted": True, "label": "TRUSTED", "reason": "ok", "schema": "test",
                "expires_at": (now + dt.timedelta(days=1)).isoformat(),
            }
            ga4_meta.write_text(json.dumps(payload), encoding="utf-8")
            untrusted_now = SimpleNamespace(label="UNTRUSTED", trusted=False,
                                            reason="not covered", schema="test",
                                            expires_at=None)
            with (mock.patch.object(obs, "GA4_FILES", ga4_files),
                  mock.patch.object(obs, "GA4_META", ga4_meta),
                  mock.patch.object(obs, "GSC_META", root / "missing-gsc.json"),
                  mock.patch.object(obs, "OFFICIAL", official),
                  mock.patch.object(obs.ga4_decision_trust, "evaluate_ga4_decision_trust",
                                    return_value=untrusted_now),
                  mock.patch.object(obs, "_configured_ga4_property_id",
                                    return_value="123456"),
                  mock.patch.object(obs.revenue_ledger, "read_affiliate_revenue",
                                    return_value={"trusted": True, "error": None,
                                                  "confirmed_transactions": 0,
                                                  "net_revenue_thb": 0})):
                current_untrusted = obs.collect(now=now)
            self.assertEqual(current_untrusted["sources"]["ga4"]["bundle"]["state"],
                             "UNTRUSTED_NOW")


if __name__ == "__main__":
    unittest.main(verbosity=2)
