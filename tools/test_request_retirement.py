"""Adversarial tests for hash-bound generation-request retirement."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
PIPELINE = ROOT / "pipeline"
if str(PIPELINE) not in sys.path:
    sys.path.insert(0, str(PIPELINE))

import dispatcher  # noqa: E402
import daily_content  # noqa: E402
import request_retirement as retirement  # noqa: E402


def _sha(path: Path) -> str | None:
    return hashlib.sha256(path.read_bytes()).hexdigest().upper() if path.is_file() else None


def _write_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def _historical(topic: str, index: int) -> dict:
    return {
        "family_id": "old-family-%d" % index,
        "topic": topic,
        "topic_sha256": dispatcher.topic_sha256(topic),
        "line_number": index,
        "historical": True,
        "explicit_family": True,
        "corpus_review_receipt": "",
        "corpus_review_sha256": "",
    }


def _prepare_root(base: Path) -> None:
    (base / "pipeline").mkdir(parents=True, exist_ok=True)
    (base / "pipeline" / "content_pack_audit.py").write_bytes(
        (PIPELINE / "content_pack_audit.py").read_bytes()
    )
    (base / ".system_control").mkdir(parents=True, exist_ok=True)
    (base / "automation-log" / "content-packages").mkdir(parents=True, exist_ok=True)
    (base / "automation-log" / "cc-outbox").mkdir(parents=True, exist_ok=True)
    (base / "automation-log" / "dedup-evidence").mkdir(parents=True, exist_ok=True)
    _write_json(base / ".system_control" / "content_manifest.json", {
        "items": [{
            "topic_th": "Historical baseline for a documented household budget review",
            "captions": {"threads": (
                "Historical reference copy checks an original statement, a dated note, "
                "and an accountable reviewer before any decision is made."
            )},
        }],
    })
    _write_json(base / ".system_control" / "content_calendar.json", {
        "items": [{
            "title": "Historical calendar topic for a weekly expense checklist",
            "copy": (
                "Historical calendar copy preserves evidence, ownership, and a review "
                "date so the result can be verified independently."
            ),
        }],
    })
    (base / "automation-log" / "post-ledger.jsonl").write_text(
        json.dumps({
            "topic": "Historical ledger topic about a monthly statement checkpoint",
            "text_first80": (
                "Historical ledger copy records a separate source, date, accountable "
                "owner, and verification note for later review."
            ),
        }) + "\n",
        encoding="utf-8",
    )


def _active(base: Path, topic: str = "A genuinely new fixture angle") -> tuple[dict, str, str]:
    _prepare_root(base)
    row = {
        "family_id": "active-family-one",
        "topic": topic,
        "topic_sha256": dispatcher.topic_sha256(topic),
        "line_number": 1,
        "historical": False,
        "explicit_family": True,
    }
    receipt_relative = "automation-log/dedup-evidence/corpus-review.json"
    receipt = base / receipt_relative
    topic_audit = dispatcher.content_pack_audit.audit_topics(
        base,
        "automation-log/cc-outbox/LOCAL-CONTENT-PACK_FIXTURE.md",
        [row],
    )
    with mock.patch.object(dispatcher, "ROOT", base):
        corpus_inputs = dispatcher.current_corpus_inputs(
            "automation-log/cc-outbox/LOCAL-CONTENT-PACK_FIXTURE.md"
        )
    _write_json(receipt, {
        "schema_version": dispatcher.CORPUS_REVIEW_SCHEMA_VERSION,
        "receipt_type": dispatcher.CORPUS_REVIEW_RECEIPT_TYPE,
        "producer": dispatcher.CORPUS_REVIEW_PRODUCER,
        "method": dispatcher.CORPUS_REVIEW_METHOD,
        "review_state": "PROVISIONAL_LOCAL_REVIEW",
        "semantic_universality_claimed": False,
        "publication_authority": "NONE",
        "created_at": "2026-08-25T00:00:00+07:00",
        "method_limit": "Local deterministic checks do not prove universal semantic novelty.",
        "candidate_path": "automation-log/cc-outbox/LOCAL-CONTENT-PACK_FIXTURE.md",
        "families": [{
            "family_id": row["family_id"], "topic": row["topic"],
            "topic_sha256": row["topic_sha256"],
        }],
        "corpus_inputs": corpus_inputs,
        "corpus_audit": {
            key: topic_audit[key] for key in (
                "topic_candidates", "topic_baseline_records",
                "historical_exact_collisions", "historical_near_collisions",
                "cross_family_exact_collisions", "cross_family_near_collisions",
            )
        },
        "explicit_non_authority": "No source, claim, media, schedule, release, or publication authority.",
    })
    receipt_hash = _sha(receipt)
    row["corpus_review_receipt"] = receipt_relative
    row["corpus_review_sha256"] = receipt_hash
    return row, receipt_relative, receipt_hash


def _fulfilment(
    base: Path, row: dict, corpus: str, corpus_hash: str,
    request_id: str = "dispatcher:2026-08-25",
) -> tuple[str, str]:
    candidate_relative = "automation-log/cc-outbox/LOCAL-CONTENT-PACK_FIXTURE.md"
    pack = base / candidate_relative
    lines = [
        "# blocked local draft", "",
        "- `request_id`: `" + request_id + "`",
        "- `status`: `DRAFT_ONLY_BLOCKED_SOURCE_REVIEW`",
        "- `publication_authority`: `NONE`",
        "- `novelty_review_state`: `PROVISIONAL_LOCAL_REVIEW`",
        "- `semantic_universality_claimed`: `FALSE`", "",
        "## 1. Fixture topic", "",
        "- `family_id`: `" + row["family_id"] + "`",
    ]
    vocabularies = (
        "amber bicycle cedar delta ember forest garden harbor island jasmine kernel lantern",
        "meadow notebook orchid pebble quartz river saffron timber upland velvet willow xenon",
        "acorn breeze copper dahlia elm feather granite horizon indigo juniper kettle lagoon",
    )
    for channel, words in zip(("Threads", "Facebook", "TikTok"), vocabularies):
        lines.extend([
            "", "### " + channel, "",
            (
                "The reserved topic is " + row["topic"] + ". "
                "This blocked educational fixture uses " + words
                + ". It compares a dated source, an accountable reviewer, an independent "
                "checkpoint, and a preserved decision record before any release."
            ),
            "", dispatcher.content_pack_audit.DISCLOSURE,
        ])
    pack.write_text("\n".join(lines) + "\n", encoding="utf-8")
    pack_audit = dispatcher.content_pack_audit.audit_pack(
        base, candidate_relative, [row], pack
    )
    receipt_relative = "automation-log/dedup-evidence/fulfilment.json"
    receipt = base / receipt_relative
    _write_json(receipt, {
        "schema_version": dispatcher.FULFILMENT_SCHEMA_VERSION,
        "receipt_type": dispatcher.FULFILMENT_RECEIPT_TYPE,
        "producer": dispatcher.FULFILMENT_PRODUCER,
        "fulfilment_state": "DRAFT_FULFILLED_BLOCKED",
        "semantic_universality_claimed": False,
        "publication_authority": "NONE",
        "release_state": "DRAFT_ONLY_BLOCKED_SOURCE_REVIEW",
        "request_id": request_id,
        "created_at": "2026-08-25T00:00:00+07:00",
        "audit_engine": {
            "path": "pipeline/content_pack_audit.py",
            "sha256": _sha(dispatcher.ROOT / "pipeline" / "content_pack_audit.py"),
        },
        "corpus_review": {"path": str(corpus), "sha256": corpus_hash},
        "pack": {
            "path": candidate_relative, "sha256": _sha(pack),
            "status": "DRAFT_ONLY_BLOCKED_SOURCE_REVIEW",
            "platform_variants": 3,
            "semantic_family_ids": [row["family_id"]],
            "request_id": request_id,
        },
        "families": [{
            "family_id": row["family_id"], "topic_sha256": row["topic_sha256"],
        }],
        "safety_audit": pack_audit["safety_audit"],
        "copy_corpus_audit": pack_audit["copy_corpus_audit"],
        "relevance_audit": pack_audit["relevance_audit"],
        "explicit_non_authority": "Exact blocked local draft bytes only; no publication authority.",
    })
    return receipt_relative, _sha(receipt)


def _tree_snapshot(paths: list[Path]) -> dict:
    result = {}
    for root in paths:
        if root.is_file():
            result[str(root)] = _sha(root)
        elif root.is_dir():
            for path in sorted(item for item in root.rglob("*") if item.is_file()):
                result[str(path)] = _sha(path)
    return result


class RequestRetirementTests(unittest.TestCase):
    def setUp(self):
        self.production_before = _tree_snapshot([
            dispatcher.DEFAULT_LEDGER,
            *dispatcher._state_paths(dispatcher.DEFAULT_LEDGER),
            dispatcher._append_journal_path(dispatcher.DEFAULT_LEDGER),
            retirement.DEFAULT_ARCHIVE,
            retirement.DEFAULT_INBOX,
        ])

    def tearDown(self):
        self.assertEqual(
            self.production_before,
            _tree_snapshot([
                dispatcher.DEFAULT_LEDGER,
                *dispatcher._state_paths(dispatcher.DEFAULT_LEDGER),
                dispatcher._append_journal_path(dispatcher.DEFAULT_LEDGER),
                retirement.DEFAULT_ARCHIVE,
                retirement.DEFAULT_INBOX,
            ]),
            "tests must not mutate production ledger/inbox/retirement evidence",
        )

    def _runtime(self, base: Path):
        inbox = base / "cowork-inbox"
        archive = base / "_retired-generation"
        ledger = base / "novelty-ledger.jsonl"
        inbox.mkdir()
        dispatcher.bootstrap_novelty_state(ledger)
        return inbox, archive, ledger

    def test_legacy_files_retire_only_when_every_topic_is_historical_consumed(self):
        with tempfile.TemporaryDirectory() as raw:
            base = Path(raw)
            inbox, archive, ledger = self._runtime(base)
            topics = ["Historical topic alpha", "Historical topic beta"]
            history = [_historical(topic, index) for index, topic in enumerate(topics, 1)]
            dispatcher.claim_novel_orders(
                [], history, consumer="test", request_id="dispatcher:2026-08-25",
                ledger_path=ledger,
            )
            generation = inbox / "generation-request-2026-08-16.md"
            generation.write_text(
                "# LOCAL GENERATION REQUEST — 2026-08-16\n\n## Topics\n"
                + "\n".join("- " + topic for topic in topics) + "\n",
                encoding="utf-8",
            )
            daily = inbox / "daily-generation-request-2026-08-16.md"
            daily.write_text(
                "# DAILY LOCAL GENERATION REQUEST — 2026-08-16\n\n"
                "- topic: " + topics[0] + "\n",
                encoding="utf-8",
            )
            originals = {path.name: path.read_bytes() for path in (generation, daily)}

            result = retirement.retire_and_validate(
                ledger, inbox=inbox, archive=archive, root=base, engine=dispatcher
            )
            self.assertEqual("PASS_EMPTY", result["state"])
            self.assertEqual(2, result["retired"])
            self.assertEqual(2, len(result["newly_retired"]))
            manifest = json.loads((archive / "manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(2, len(manifest["records"]))
            for record in manifest["records"]:
                self.assertEqual(
                    originals[Path(record["original_path"]).name],
                    (base / record["archive_path"]).read_bytes(),
                )
                tombstone = (base / record["original_path"]).read_bytes()
                self.assertTrue(retirement._looks_like_tombstone(tombstone))
                self.assertTrue(tombstone.startswith(
                    b"# HISTORICAL_CONSUMED_DO_NOT_GENERATE\n"
                ))

    def test_unknown_legacy_topic_blocks_without_overwriting_original(self):
        with tempfile.TemporaryDirectory() as raw:
            base = Path(raw)
            inbox, archive, ledger = self._runtime(base)
            history = [_historical("Known historical topic", 1)]
            dispatcher.claim_novel_orders(
                [], history, consumer="test", request_id="dispatcher:2026-08-25",
                ledger_path=ledger,
            )
            path = inbox / "daily-generation-request-2026-08-17.md"
            path.write_text(
                "# DAILY LOCAL GENERATION REQUEST — 2026-08-17\n\n"
                "- topic: Unknown topic must not be retired silently\n",
                encoding="utf-8",
            )
            before = path.read_bytes()
            with self.assertRaisesRegex(
                retirement.RequestRetirementError, "not bound as historical"
            ):
                retirement.retire_and_validate(
                    ledger, inbox=inbox, archive=archive, root=base, engine=dispatcher
                )
            self.assertEqual(before, path.read_bytes())
            self.assertFalse((archive / "manifest.json").exists())

    def test_drafted_blocked_request_and_reference_retire_without_consumption(self):
        with tempfile.TemporaryDirectory() as raw:
            base = Path(raw)
            inbox, archive, ledger = self._runtime(base)
            row, corpus, corpus_hash = _active(base)
            with mock.patch.object(dispatcher, "ROOT", base):
                reserved = dispatcher.claim_novel_orders(
                    [row], [], consumer="test", request_id="dispatcher:2026-08-25",
                    ledger_path=ledger,
                )
            request = dispatcher.request_path(
                "generation-request", "2026-08-25", inbox=inbox
            )
            dispatcher.write_request(
                request, date="2026-08-25", request_id="dispatcher:2026-08-25",
                rows=reserved, title="LOCAL NOVELTY-GATED GENERATION REQUEST",
            )
            reference = dispatcher.request_path(
                "daily-reference", "2026-08-25", inbox=inbox
            )
            dispatcher.write_reference(
                reference, date="2026-08-25", request_id="daily:2026-08-25",
                rows=reserved, referenced_path=request,
                title="DAILY LOCAL NOVELTY REFERENCE",
            )
            originals = {path.name: path.read_bytes() for path in (request, reference)}
            receipt, receipt_hash = _fulfilment(base, row, corpus, corpus_hash)
            with mock.patch.object(dispatcher, "ROOT", base):
                dispatcher.fulfil_reservations(
                    [row["family_id"]], receipt_path=str(receipt),
                    receipt_sha256=receipt_hash, ledger_path=ledger,
                )

            rows = dispatcher.read_consumed_ledger(ledger)
            self.assertEqual("DRAFTED_BLOCKED", rows[-1]["event"])
            _reserved, consumed, outstanding = dispatcher._lifecycle(rows)
            self.assertEqual({}, consumed)
            self.assertEqual({}, outstanding)
            self.assertEqual(
                [row["family_id"]], sorted(dispatcher._drafted_map(rows))
            )

            first = retirement.retire_and_validate(
                ledger, inbox=inbox, archive=archive, root=base, engine=dispatcher
            )
            snapshot = _tree_snapshot([
                inbox, archive, ledger, *dispatcher._state_paths(ledger),
                dispatcher._append_journal_path(ledger),
            ])
            second = retirement.retire_and_validate(
                ledger, inbox=inbox, archive=archive, root=base, engine=dispatcher
            )
            self.assertEqual("PASS_EMPTY", first["state"])
            self.assertEqual(1, first["drafted_blocked"])
            self.assertEqual(2, first["retired"])
            self.assertEqual([], second["newly_retired"])
            self.assertEqual(
                snapshot,
                _tree_snapshot([
                    inbox, archive, ledger, *dispatcher._state_paths(ledger),
                    dispatcher._append_journal_path(ledger),
                ]),
            )
            manifest = json.loads((archive / "manifest.json").read_text(encoding="utf-8"))
            for record in manifest["records"]:
                self.assertEqual(
                    "DRAFTED_BLOCKED_DO_NOT_GENERATE", record["state"]
                )
                self.assertIn("without semantic approval", record["reason"])
                self.assertEqual(
                    originals[Path(record["original_path"]).name],
                    (base / record["archive_path"]).read_bytes(),
                )
                tombstone = (base / record["original_path"]).read_text(
                    encoding="utf-8"
                )
                self.assertIn(
                    "- retirement_state: DRAFTED_BLOCKED_DO_NOT_GENERATE",
                    tombstone,
                )
                self.assertIn("- publication_authority: NONE", tombstone)

    def test_validator_blocks_actionable_bytes_when_outstanding_is_zero(self):
        with tempfile.TemporaryDirectory() as raw:
            base = Path(raw)
            inbox, archive, ledger = self._runtime(base)
            row, corpus, corpus_hash = _active(base)
            with mock.patch.object(dispatcher, "ROOT", base):
                reserved = dispatcher.claim_novel_orders(
                    [row], [], consumer="test", request_id="dispatcher:2026-08-25",
                    ledger_path=ledger,
                )
            request = dispatcher.request_path(
                "generation-request", "2026-08-25", inbox=inbox
            )
            dispatcher.write_request(
                request, date="2026-08-25", request_id="dispatcher:2026-08-25",
                rows=reserved, title="LOCAL NOVELTY-GATED GENERATION REQUEST",
            )
            original = request.read_bytes()
            receipt, receipt_hash = _fulfilment(base, row, corpus, corpus_hash)
            with mock.patch.object(dispatcher, "ROOT", base):
                dispatcher.fulfil_reservations(
                    [row["family_id"]], receipt_path=str(receipt),
                    receipt_sha256=receipt_hash, ledger_path=ledger,
                )
            retirement.retire_and_validate(
                ledger, inbox=inbox, archive=archive, root=base, engine=dispatcher
            )
            request.write_bytes(original)
            with self.assertRaisesRegex(
                retirement.RequestRetirementError, "overwritten with actionable"
            ):
                retirement.validate_inventory(
                    ledger, inbox=inbox, archive=archive, root=base, engine=dispatcher
                )

    def test_unreclassified_current_consumed_cannot_authorize_retirement(self):
        """A raw legacy CONSUMED row must first receive its blocked correction."""
        with tempfile.TemporaryDirectory() as raw:
            base = Path(raw)
            inbox, archive, ledger = self._runtime(base)
            row, _corpus, _corpus_hash = _active(base)
            with mock.patch.object(dispatcher, "ROOT", base):
                reserved = dispatcher.claim_novel_orders(
                    [row], [], consumer="test",
                    request_id="dispatcher:2026-08-25", ledger_path=ledger,
                )
            request = dispatcher.request_path(
                "generation-request", "2026-08-25", inbox=inbox
            )
            dispatcher.write_request(
                request, date="2026-08-25",
                request_id="dispatcher:2026-08-25", rows=reserved,
                title="LOCAL NOVELTY-GATED GENERATION REQUEST",
            )
            original = request.read_bytes()
            with dispatcher._claim_lock(ledger):
                rows = dispatcher.read_consumed_ledger(ledger)
                dispatcher._append_events_atomic(ledger, rows, [dict(
                    reserved[0],
                    event="CONSUMED",
                    consumer="legacy-mechanical-fixture",
                    fulfilment_receipt="automation-log/dedup-evidence/legacy.json",
                    fulfilment_sha256="A" * 64,
                )])

            with self.assertRaisesRegex(
                retirement.RequestRetirementError,
                "unreclassified CONSUMED lifecycle",
            ):
                retirement.retire_and_validate(
                    ledger, inbox=inbox, archive=archive, root=base,
                    engine=dispatcher,
                )
            self.assertEqual(original, request.read_bytes())
            self.assertFalse((archive / "manifest.json").exists())

    def test_old_fulfilled_manifest_remains_readable_after_exact_reclassification(self):
        """Cutover is append-only; it must not require rewriting old evidence."""
        with tempfile.TemporaryDirectory() as raw:
            base = Path(raw)
            inbox, archive, ledger = self._runtime(base)
            row, _corpus, _corpus_hash = _active(base)
            with mock.patch.object(dispatcher, "ROOT", base):
                reserved = dispatcher.claim_novel_orders(
                    [row], [], consumer="test",
                    request_id="dispatcher:2026-08-25", ledger_path=ledger,
                )
            request = dispatcher.request_path(
                "generation-request", "2026-08-25", inbox=inbox
            )
            dispatcher.write_request(
                request, date="2026-08-25",
                request_id="dispatcher:2026-08-25", rows=reserved,
                title="LOCAL NOVELTY-GATED GENERATION REQUEST",
            )
            original = request.read_bytes()
            with dispatcher._claim_lock(ledger):
                rows = dispatcher.read_consumed_ledger(ledger)
                rows = dispatcher._append_events_atomic(ledger, rows, [dict(
                    reserved[0],
                    event="CONSUMED",
                    consumer="legacy-mechanical-fixture",
                    fulfilment_receipt="automation-log/dedup-evidence/legacy.json",
                    fulfilment_sha256="A" * 64,
                )])

            classification = {
                "state": "FULFILLED_DO_NOT_GENERATE",
                "reason": "pre-cutover mechanical terminal record",
                "request_id": "dispatcher:2026-08-25",
                "topic_sha256s": [row["topic_sha256"]],
            }
            record = retirement._make_record(
                request, original, classification, archive=archive,
                ledger_path=ledger, rows=rows, root=base, engine=dispatcher,
            )
            dispatcher._atomic_write(
                archive / "manifest.json",
                retirement._manifest_bytes([record], dispatcher),
            )
            dispatcher._atomic_write(
                request,
                retirement._tombstone_bytes(record, legacy_header=True),
            )

            with dispatcher._claim_lock(ledger):
                rows = dispatcher.read_consumed_ledger(ledger)
                prior = rows[-1]
                dispatcher._append_events_atomic(ledger, rows, [dict(
                    prior,
                    event="LEGACY_CONSUMPTION_RECLASSIFIED",
                    consumer="strict-legacy-reclassification",
                    revalidation_receipt=dispatcher.STRICT_REVALIDATION_RELATIVE,
                    revalidation_sha256="B" * 64,
                    snapshot_manifest_sha256="C" * 64,
                )])

            state_paths = [
                inbox, archive, ledger, *dispatcher._state_paths(ledger),
                dispatcher._append_journal_path(ledger),
            ]
            before = _tree_snapshot(state_paths)
            result = retirement.validate_inventory(
                ledger, inbox=inbox, archive=archive, root=base,
                engine=dispatcher,
            )
            self.assertEqual("PASS_EMPTY", result["state"])
            self.assertEqual(1, result["drafted_blocked"])
            self.assertEqual(before, _tree_snapshot(state_paths))

    def test_archive_tombstone_and_manifest_tamper_each_fail_closed(self):
        for target in ("archive", "tombstone", "manifest"):
            with self.subTest(target=target), tempfile.TemporaryDirectory() as raw:
                base = Path(raw)
                inbox, archive, ledger = self._runtime(base)
                topic = "Historical evidence topic"
                dispatcher.claim_novel_orders(
                    [], [_historical(topic, 1)], consumer="test",
                    request_id="dispatcher:2026-08-25", ledger_path=ledger,
                )
                request = inbox / "daily-generation-request-2026-08-16.md"
                request.write_text(
                    "# DAILY LOCAL GENERATION REQUEST — 2026-08-16\n\n"
                    "- topic: " + topic + "\n",
                    encoding="utf-8",
                )
                retirement.retire_and_validate(
                    ledger, inbox=inbox, archive=archive, root=base, engine=dispatcher
                )
                manifest_path = archive / "manifest.json"
                manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
                if target == "archive":
                    (base / manifest["records"][0]["archive_path"]).write_bytes(b"tamper")
                elif target == "tombstone":
                    request.write_bytes(request.read_bytes() + b"tamper")
                else:
                    manifest_path.write_bytes(manifest_path.read_bytes() + b"tamper")
                with self.assertRaises(retirement.RequestRetirementError):
                    retirement.validate_inventory(
                        ledger, inbox=inbox, archive=archive, root=base, engine=dispatcher
                    )

    def test_exact_outstanding_request_is_the_only_actionable_state_allowed(self):
        with tempfile.TemporaryDirectory() as raw:
            base = Path(raw)
            inbox, archive, ledger = self._runtime(base)
            row, _corpus, _corpus_hash = _active(base)
            with mock.patch.object(dispatcher, "ROOT", base):
                reserved = dispatcher.claim_novel_orders(
                    [row], [], consumer="test", request_id="dispatcher:2026-08-25",
                    ledger_path=ledger,
                )
            request = dispatcher.request_path(
                "generation-request", "2026-08-25", inbox=inbox
            )
            dispatcher.write_request(
                request, date="2026-08-25", request_id="dispatcher:2026-08-25",
                rows=reserved, title="LOCAL NOVELTY-GATED GENERATION REQUEST",
            )
            result = retirement.retire_and_validate(
                ledger, inbox=inbox, archive=archive, root=base, engine=dispatcher
            )
            self.assertEqual("PASS_ACTIVE", result["state"])
            self.assertEqual(1, result["outstanding"])
            self.assertEqual(1, len(result["active_requests"]))
            self.assertFalse(request.read_bytes().startswith(retirement.TOMBSTONE_PREFIX))
            self.assertEqual(
                "PASS_ACTIVE",
                retirement.validate_inventory(
                    ledger, inbox=inbox, archive=archive, root=base, engine=dispatcher
                )["state"],
            )

    def test_scan_is_root_only(self):
        with tempfile.TemporaryDirectory() as raw:
            base = Path(raw)
            inbox, archive, ledger = self._runtime(base)
            nested = inbox / "nested"
            nested.mkdir()
            ignored = nested / "generation-request-unknown.md"
            ignored.write_text("actionable-looking nested evidence\n", encoding="utf-8")
            result = retirement.retire_and_validate(
                ledger, inbox=inbox, archive=archive, root=base, engine=dispatcher
            )
            self.assertEqual("PASS_EMPTY", result["state"])
            self.assertEqual("actionable-looking nested evidence\n", ignored.read_text())

    def test_daily_first_reference_retires_at_drafted_blocked_not_consumed(self):
        with tempfile.TemporaryDirectory() as raw:
            base = Path(raw)
            inbox = base / "cowork-inbox"
            archive = base / "_retired-generation"
            inbox.mkdir()
            ledger = dispatcher.ledger_path_for(inbox)
            dispatcher.bootstrap_novelty_state(ledger)
            row, corpus, corpus_hash = _active(base)
            orders = base / "orders.txt"
            orders.write_text(
                "\t".join((
                    row["family_id"], row["topic"],
                    row["corpus_review_receipt"], row["corpus_review_sha256"],
                )) + "\n",
                encoding="utf-8",
            )
            with (
                mock.patch.object(dispatcher, "ROOT", base),
                mock.patch.object(dispatcher, "ORDERS", str(orders)),
                mock.patch.object(dispatcher, "INBOX", str(inbox)),
                mock.patch.object(daily_content, "ORDERS", str(orders)),
                mock.patch.object(daily_content, "INBOX", str(inbox)),
            ):
                daily_result = daily_content.run()
                dispatch_result = dispatcher.main()
                self.assertEqual("QUEUED_NOVEL", daily_result["state"])
                self.assertEqual(
                    "REFERENCE_OUTSTANDING_RESERVED", dispatch_result["state"]
                )
                reference = Path(dispatch_result["request"])
                self.assertTrue(reference.name.startswith("generation-reference-"))
                active = retirement.validate_inventory(
                    ledger, inbox=inbox, archive=archive, root=base,
                    engine=dispatcher,
                )
                self.assertEqual("PASS_ACTIVE", active["state"])
                self.assertEqual(1, len(active["active_references"]))

                receipt, receipt_hash = _fulfilment(
                    base, row, corpus, corpus_hash,
                    request_id="daily:2026-08-25",
                )
                dispatcher.fulfil_reservations(
                    [row["family_id"]], receipt_path=str(receipt),
                    receipt_sha256=receipt_hash, ledger_path=ledger,
                )
                ledger_rows = dispatcher.read_consumed_ledger(ledger)
                self.assertEqual("DRAFTED_BLOCKED", ledger_rows[-1]["event"])
                self.assertEqual({}, dispatcher._lifecycle(ledger_rows)[1])
                retired = dispatcher.retire_request_inventory(ledger, inbox)
                self.assertEqual("PASS_EMPTY", retired["state"])
                self.assertEqual(1, retired["drafted_blocked"])
                self.assertTrue(
                    reference.read_bytes().startswith(retirement.TOMBSTONE_PREFIX)
                )
                self.assertTrue(
                    Path(daily_result["request"]).read_bytes().startswith(
                        retirement.TOMBSTONE_PREFIX
                    )
                )
                manifest = json.loads(
                    (archive / "manifest.json").read_text(encoding="utf-8")
                )
                self.assertEqual(
                    {"DRAFTED_BLOCKED_DO_NOT_GENERATE"},
                    {record["state"] for record in manifest["records"]},
                )

    def test_script_cli_converts_retirement_error_to_rc20_without_traceback(self):
        with tempfile.TemporaryDirectory() as raw:
            base = Path(raw)
            pipeline = base / "pipeline"
            inbox = base / "automation-log" / "cowork-inbox"
            pipeline.mkdir()
            inbox.mkdir(parents=True)
            (base / "automation-log" / "orders.txt").write_text(
                "# empty fixture registry\n", encoding="utf-8"
            )
            for name in (
                "dispatcher.py", "request_retirement.py", "content_pack_audit.py",
                "comply_gate.py",
            ):
                shutil.copyfile(PIPELINE / name, pipeline / name)
            command = [sys.executable, str(pipeline / "dispatcher.py")]
            bootstrap = subprocess.run(
                command + ["--bootstrap-novelty-state"], cwd=base,
                text=True, encoding="utf-8", capture_output=True, check=False,
            )
            self.assertEqual(0, bootstrap.returncode, bootstrap.stdout + bootstrap.stderr)
            first = subprocess.run(
                command + ["--retire-consumed-requests"], cwd=base,
                text=True, encoding="utf-8", capture_output=True, check=False,
            )
            self.assertEqual(0, first.returncode, first.stdout + first.stderr)
            manifest = base / "automation-log" / "_retired-generation" / "manifest.json"
            manifest.write_bytes(manifest.read_bytes() + b"{}")
            blocked = subprocess.run(
                command + ["--retire-consumed-requests"], cwd=base,
                text=True, encoding="utf-8", capture_output=True, check=False,
            )
            output = blocked.stdout + blocked.stderr
            self.assertEqual(20, blocked.returncode, output)
            self.assertIn("BLOCKED_UNKNOWN:", output)
            self.assertNotIn("Traceback", output)


if __name__ == "__main__":
    unittest.main(verbosity=2)
