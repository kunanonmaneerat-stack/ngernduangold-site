"""Regression tests for the fail-closed local novelty lifecycle."""

from __future__ import annotations

import concurrent.futures
import contextlib
import datetime
import hashlib
import json
import multiprocessing
from pathlib import Path
import sys
import tempfile
import time
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
PIPELINE = ROOT / "pipeline"
if str(PIPELINE) not in sys.path:
    sys.path.insert(0, str(PIPELINE))

import daily_content  # noqa: E402
import dispatcher  # noqa: E402


def _sha(path: Path):
    return hashlib.sha256(path.read_bytes()).hexdigest().upper() if path.exists() else None


def _write_json(path: Path, value: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def _prepare_fixture_root(root: Path):
    (root / "pipeline").mkdir(parents=True, exist_ok=True)
    (root / "pipeline" / "content_pack_audit.py").write_bytes(
        (PIPELINE / "content_pack_audit.py").read_bytes()
    )
    (root / ".system_control").mkdir(parents=True, exist_ok=True)
    (root / "automation-log" / "content-packages").mkdir(parents=True, exist_ok=True)
    (root / "automation-log" / "cc-outbox").mkdir(parents=True, exist_ok=True)
    (root / "automation-log" / "dedup-evidence").mkdir(parents=True, exist_ok=True)
    _write_json(root / ".system_control" / "content_manifest.json", {
        "items": [{
            "topic_th": "Historical fixture baseline about reviewing a documented monthly budget",
            "captions": {
                "threads": (
                    "Historical reference copy explains a monthly budget checkpoint "
                    "using a dated source document and a separate verification record."
                )
            },
        }],
    })
    _write_json(root / ".system_control" / "content_calendar.json", {
        "items": [{
            "title": "Historical fixture calendar angle for a documented budget review",
            "copy": (
                "Historical calendar reference asks readers to compare an original "
                "statement with an independent dated note before making a decision."
            ),
        }],
    })
    (root / "automation-log" / "post-ledger.jsonl").write_text(
        json.dumps({
            "topic": "Historical ledger topic about a weekly expense checklist",
            "text_first80": (
                "Historical ledger copy records a weekly checklist with evidence, "
                "ownership, and a review date for later verification."
            ),
        }, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def _fixture_registry(path: Path, active_count=3, historical_count=1, topics=None):
    root = dispatcher.ROOT.resolve()
    _prepare_fixture_root(root)
    topic_pool = [
        "Documented payroll variance reconciliation using dated source fields",
        "Annual maintenance reserve calendar separated from emergency cash",
        "Household responsibility map with evidence and accountable checkpoints",
        "Refund case timeline that distinguishes promises from settled funds",
        "Employer benefit inventory before purchasing overlapping protection",
    ]
    active_topics = topics or topic_pool[:active_count]
    families = [
        {
            "family_id": "family-%d" % index,
            "topic": topic,
            "topic_sha256": dispatcher.topic_sha256(topic),
        }
        for index, topic in enumerate(active_topics, 1)
    ]
    receipt_relative = "automation-log/dedup-evidence/corpus-review.json"
    receipt = root / receipt_relative
    candidate_path = "automation-log/cc-outbox/LOCAL-CONTENT-PACK_FIXTURE.md"
    topic_audit = dispatcher.content_pack_audit.audit_topics(
        root, candidate_path, families
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
        "candidate_path": candidate_path,
        "families": [
            {
                "family_id": row["family_id"],
                "topic": row["topic"],
                "topic_sha256": row["topic_sha256"],
            }
            for row in families
        ],
        "corpus_inputs": dispatcher.current_corpus_inputs(candidate_path),
        "corpus_audit": {
            key: topic_audit[key] for key in (
                "topic_candidates", "topic_baseline_records",
                "historical_exact_collisions", "historical_near_collisions",
                "cross_family_exact_collisions", "cross_family_near_collisions",
            )
        },
        "explicit_non_authority": "No source, claim, media, scheduling, publication, or release authority.",
    })
    receipt_hash = _sha(receipt)
    lines = ["# fixture registry"]
    lines.extend(
        "\t".join((row["family_id"], row["topic"], receipt_relative, receipt_hash))
        for row in families
    )
    lines.extend(
        "# HISTORICAL_CONSUMED\told-family-%d\tOld consumed topic %d" % (i, i)
        for i in range(1, historical_count + 1)
    )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return families, receipt_relative, receipt_hash


def _fixture_fulfilment(
    base: Path, families, corpus: str, corpus_hash: str,
    request_id: str = "dispatcher:2026-08-25",
    candidate_relative: str = "automation-log/cc-outbox/LOCAL-CONTENT-PACK_FIXTURE.md",
    receipt_relative: str = "automation-log/dedup-evidence/draft-fulfilment.json",
):
    pack = base / candidate_relative
    pack.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# blocked local draft",
        "",
        "- `request_id`: `" + request_id + "`",
        "- `status`: `DRAFT_ONLY_BLOCKED_SOURCE_REVIEW`",
        "- `publication_authority`: `NONE`",
        "- `novelty_review_state`: `PROVISIONAL_LOCAL_REVIEW`",
        "- `semantic_universality_claimed`: `FALSE`",
    ]
    vocabulary = (
        "amber bicycle cedar delta ember forest garden harbor island jasmine kernel lantern",
        "meadow notebook orchid pebble quartz river saffron timber upland velvet willow xenon",
        "acorn breeze copper dahlia elm feather granite horizon indigo juniper kettle lagoon",
        "maple nectar olive prism quill ribbon spruce topaz umber violet walnut zephyr",
    )
    for index, row in enumerate(families):
        lines.extend(["", "## %d. Fixture topic" % (index + 1)])
        lines.extend([
            "", "- `family_id`: `" + row["family_id"] + "`",
        ])
        for channel_index, channel in enumerate(("Threads", "Facebook", "TikTok")):
            words = vocabulary[(index + channel_index) % len(vocabulary)]
            body = (
                "The reserved topic is " + row["topic"] + ". "
                "This blocked educational fixture uses " + words
                + ". It asks the page to compare a dated source, record an accountable "
                "reviewer, preserve a separate checkpoint, and stop before any release. "
                + "Family " + str(index + 1) + " channel " + channel + " remains local."
            )
            lines.extend(["", "### " + channel, "", body, "", dispatcher.content_pack_audit.DISCLOSURE])
    pack.write_text("\n".join(lines) + "\n", encoding="utf-8")
    pack_audit = dispatcher.content_pack_audit.audit_pack(
        base, candidate_relative, families, pack
    )
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
        "corpus_review": {"path": corpus, "sha256": corpus_hash},
        "pack": {
            "path": candidate_relative, "sha256": _sha(pack),
            "status": "DRAFT_ONLY_BLOCKED_SOURCE_REVIEW",
            "platform_variants": len(families) * 3,
            "semantic_family_ids": [row["family_id"] for row in families],
            "request_id": request_id,
        },
        "families": [
            {"family_id": row["family_id"], "topic_sha256": row["topic_sha256"]}
            for row in families
        ],
        "safety_audit": pack_audit["safety_audit"],
        "copy_corpus_audit": pack_audit["copy_corpus_audit"],
        "relevance_audit": pack_audit["relevance_audit"],
        "explicit_non_authority": "Exact blocked draft bytes only; no publication authority.",
    })
    return receipt_relative, _sha(receipt)


def _hold_process_lock(ledger: str, ready: str):
    with dispatcher._claim_lock(Path(ledger)):
        Path(ready).write_text("ready", encoding="ascii")
        while True:
            time.sleep(0.05)


class ContentNoveltyQueueTests(unittest.TestCase):
    def setUp(self):
        self.production_paths = (
            dispatcher.DEFAULT_LEDGER,
            *dispatcher._state_paths(dispatcher.DEFAULT_LEDGER),
        )
        self.production_before = {
            str(path): _sha(path) for path in self.production_paths
        }

    def tearDown(self):
        self.assertEqual(
            self.production_before,
            {str(path): _sha(path) for path in self.production_paths},
            "tests must never create or mutate production novelty state",
        )

    @contextlib.contextmanager
    def _runtime(self, root: Path, active=3, historical=1):
        orders = root / "automation-log" / "orders.txt"
        inbox = root / "automation-log" / "cowork-inbox"
        with contextlib.ExitStack() as stack:
            stack.enter_context(mock.patch.object(dispatcher, "ROOT", root))
            _prepare_fixture_root(root)
            inbox.mkdir(parents=True)
            families, corpus, corpus_hash = _fixture_registry(
                orders, active_count=active, historical_count=historical
            )
            stack.enter_context(mock.patch.object(dispatcher, "ORDERS", str(orders)))
            stack.enter_context(mock.patch.object(dispatcher, "INBOX", str(inbox)))
            stack.enter_context(mock.patch.object(daily_content, "ORDERS", str(orders)))
            stack.enter_context(mock.patch.object(daily_content, "INBOX", str(inbox)))
            ledger = dispatcher.ledger_path_for(inbox)
            dispatcher.bootstrap_novelty_state(ledger)
            yield orders, inbox, ledger, families, corpus, corpus_hash

    def test_source_has_no_replacement_character_or_invalid_backtick_escape(self):
        source = Path(dispatcher.__file__).read_bytes()
        self.assertNotIn(bytes.fromhex("EFBFBD"), source)
        self.assertNotIn(b"\\x5c\\x60", source)

    def test_thai_marks_remain_part_of_topic_identity(self):
        self.assertNotEqual(dispatcher.normalize_topic("หนี้"), dispatcher.normalize_topic("หนี"))
        self.assertNotEqual(dispatcher.topic_sha256("หนี้"), dispatcher.topic_sha256("หนี"))
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            path = base / "automation-log" / "orders.txt"
            with mock.patch.object(dispatcher, "ROOT", base):
                _fixture_registry(
                    path, active_count=2, historical_count=0, topics=["หนี้", "หนี"]
                )
                active, _historical = dispatcher.load_order_registry(path)
                self.assertEqual(2, len(active))

    def test_registry_rejects_duplicate_family_and_normalized_topic(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            path = base / "automation-log" / "orders.txt"
            with mock.patch.object(dispatcher, "ROOT", base):
                _families, receipt, receipt_hash = _fixture_registry(
                    path, active_count=2, historical_count=0
                )
                path.write_text(
                    "same-family\tFirst topic\t%s\t%s\n"
                    "same-family\tSecond topic\t%s\t%s\n"
                    % (receipt, receipt_hash, receipt, receipt_hash),
                    encoding="utf-8",
                )
                with self.assertRaisesRegex(dispatcher.NoveltyIntegrityError, "semantic family"):
                    dispatcher.load_order_registry(path)
                path.write_text(
                    "family-one\tAlpha topic!\t%s\t%s\n"
                    "family-two\talpha-topic\t%s\t%s\n"
                    % (receipt, receipt_hash, receipt, receipt_hash),
                    encoding="utf-8",
                )
                with self.assertRaisesRegex(dispatcher.NoveltyIntegrityError, "normalized topic"):
                    dispatcher.load_order_registry(path)

    def test_missing_activation_and_checkpoint_mismatch_fail_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            orders = base / "automation-log" / "orders.txt"
            with mock.patch.object(dispatcher, "ROOT", base):
                _fixture_registry(orders, active_count=1, historical_count=0)
                active, historical = dispatcher.load_order_registry(orders)
                ledger = base / "ledger.jsonl"
                with self.assertRaises(dispatcher.NoveltyStateUninitialized):
                    dispatcher.claim_novel_orders(
                        active, historical, consumer="test",
                        request_id="dispatcher:2026-08-25", ledger_path=ledger,
                    )
                dispatcher.bootstrap_novelty_state(ledger)
                checkpoint = dispatcher._state_paths(ledger)[1]
                checkpoint.write_text("{}\n", encoding="utf-8")
                with self.assertRaises(dispatcher.NoveltyIntegrityError):
                    dispatcher.read_consumed_ledger(ledger)

    def test_dispatcher_then_daily_is_reference_only_and_idempotent(self):
        with tempfile.TemporaryDirectory() as directory:
            with self._runtime(Path(directory)) as (
                _orders, _inbox, ledger, _families, _corpus, _corpus_hash
            ):
                first_dispatch = dispatcher.main()
                dispatch_path = Path(first_dispatch["request"])
                daily = daily_content.run()
                daily_path = Path(daily["request"])
                ledger_before = ledger.read_bytes()
                dispatch_before = dispatch_path.read_bytes()
                daily_before = daily_path.read_bytes()
                rows = dispatcher.read_consumed_ledger(ledger)
                reservations = [
                    row for row in rows if row["event"] == "RESERVED"
                ]
                self.assertEqual(3, len(reservations))
                self.assertEqual("REFERENCE_DO_NOT_GENERATE_DUPLICATE", daily["state"])
                self.assertIn(b"REFERENCE_DO_NOT_GENERATE_DUPLICATE", daily_before)
                self.assertIn(reservations[-1]["record_hash"].encode(), dispatch_before)
                self.assertEqual([], [
                    row for row in rows
                    if row["request_id"].startswith("daily:")
                ])

                second_dispatch = dispatcher.main()
                second_daily = daily_content.run()
                self.assertEqual(first_dispatch["families"], second_dispatch["families"])
                self.assertEqual("REFERENCE_DO_NOT_GENERATE_DUPLICATE", second_daily["state"])
                self.assertEqual(ledger_before, ledger.read_bytes())
                self.assertEqual(dispatch_before, dispatch_path.read_bytes())
                self.assertEqual(daily_before, Path(second_daily["request"]).read_bytes())

    def test_standalone_daily_reserves_one_and_repeats_same_bytes(self):
        with tempfile.TemporaryDirectory() as directory:
            with self._runtime(Path(directory)) as (
                _orders, _inbox, ledger, _families, _corpus, _corpus_hash
            ):
                first = daily_content.run()
                before_request = Path(first["request"]).read_bytes()
                before_ledger = ledger.read_bytes()
                second = daily_content.run()
                self.assertEqual("QUEUED_NOVEL", first["state"])
                self.assertEqual(before_request, Path(second["request"]).read_bytes())
                self.assertEqual(before_ledger, ledger.read_bytes())
                reservations = [
                    row for row in dispatcher.read_consumed_ledger(ledger)
                    if row["event"] == "RESERVED"
                ]
                self.assertEqual(["family-1"], [row["family_id"] for row in reservations])

    def test_daily_dispatcher_interleaving_has_no_double_reservation(self):
        with tempfile.TemporaryDirectory() as directory:
            with self._runtime(Path(directory)) as (
                orders, _inbox, ledger, _families, _corpus, _corpus_hash
            ):
                active, historical = dispatcher.load_order_registry(orders)
                date = datetime.date.today().isoformat()
                with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
                    dispatch_future = pool.submit(
                        dispatcher.claim_novel_orders,
                        active, historical,
                        consumer="dispatcher-local-request",
                        request_id="dispatcher:" + date,
                        ledger_path=ledger,
                    )
                    daily_future = pool.submit(
                        dispatcher.select_daily_order_atomic,
                        active, historical,
                        request_id="daily:" + date,
                        ledger_path=ledger,
                    )
                    dispatch_rows = dispatch_future.result()
                    daily_mode, daily_rows = daily_future.result()
                rows = dispatcher.read_consumed_ledger(ledger)
                reservations = [row for row in rows if row["event"] == "RESERVED"]
                self.assertEqual(
                    len(reservations),
                    len({row["family_id"] for row in reservations}),
                )
                self.assertEqual("family-1", daily_rows[0]["family_id"])
                self.assertIn(
                    daily_mode,
                    {"DAILY_RESERVED", "DISPATCHER_REFERENCE", "OUTSTANDING_REFERENCE"},
                )
                self.assertTrue(dispatch_rows)

    def test_os_lock_contention_and_process_crash_release(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            ledger = base / "ledger.jsonl"
            dispatcher.bootstrap_novelty_state(ledger)
            with dispatcher._claim_lock(ledger):
                with mock.patch.object(dispatcher, "LOCK_TIMEOUT_SECONDS", 0.03):
                    with self.assertRaises(dispatcher.NoveltyLockError):
                        with dispatcher._claim_lock(ledger):
                            pass

            ready = base / "ready"
            process = multiprocessing.get_context("spawn").Process(
                target=_hold_process_lock, args=(str(ledger), str(ready))
            )
            process.start()
            deadline = time.monotonic() + 5
            while not ready.exists() and time.monotonic() < deadline:
                time.sleep(0.02)
            self.assertTrue(ready.exists())
            process.terminate()
            process.join(5)
            self.assertFalse(process.is_alive())
            with dispatcher._claim_lock(ledger):
                self.assertTrue(
                    ledger.with_suffix(ledger.suffix + ".lock").exists()
                )

    def test_crash_after_reservation_is_rebuilt_and_tamper_is_blocked(self):
        with tempfile.TemporaryDirectory() as directory:
            with self._runtime(Path(directory)) as (
                orders, inbox, ledger, _families, _corpus, _corpus_hash
            ):
                active, historical = dispatcher.load_order_registry(orders)
                reserved = dispatcher.claim_novel_orders(
                    active, historical, consumer="dispatcher-local-request",
                    request_id="dispatcher:2000-01-01", ledger_path=ledger,
                    max_count=1,
                )
                request = dispatcher.request_path(
                    "generation-request", "2000-01-01", inbox=inbox
                )
                self.assertFalse(request.exists())
                recovered = dispatcher.reconcile_requests(ledger, inbox)
                self.assertEqual([str(request)], recovered)
                copy = request.read_bytes()
                self.assertIn(reserved[0]["record_hash"].encode(), copy)
                request.write_bytes(copy + b"tamper")
                with self.assertRaisesRegex(
                    dispatcher.NoveltyIntegrityError, "request bytes"
                ):
                    dispatcher.reconcile_requests(ledger, inbox)

    def test_reserved_becomes_drafted_blocked_after_exact_draft_receipt(self):
        with tempfile.TemporaryDirectory() as directory:
            with self._runtime(Path(directory), active=1, historical=0) as (
                orders, inbox, ledger, families, corpus, corpus_hash
            ):
                active, historical = dispatcher.load_order_registry(orders)
                reserved = dispatcher.claim_novel_orders(
                    active, historical, consumer="test",
                    request_id="dispatcher:2026-08-25", ledger_path=ledger,
                )
                self.assertEqual("RESERVED", reserved[0]["event"])
                request = dispatcher.request_path(
                    "generation-request", "2026-08-25", inbox=inbox
                )
                self.assertEqual(
                    [str(request)], dispatcher.reconcile_requests(ledger, inbox)
                )
                receipt, receipt_hash = _fixture_fulfilment(
                    Path(directory), families, corpus, corpus_hash
                )
                drafted = dispatcher.fulfil_reservations(
                    ["family-1"], receipt_path=str(receipt),
                    receipt_sha256=receipt_hash, ledger_path=ledger,
                )
                self.assertEqual("DRAFTED_BLOCKED", drafted[0]["event"])
                self.assertFalse(any(
                    row["event"] == "CONSUMED" and not row["historical"]
                    for row in dispatcher.read_consumed_ledger(ledger)
                ))
                self.assertEqual(
                    drafted,
                    dispatcher.fulfil_reservations(
                        ["family-1"], receipt_path=str(receipt),
                        receipt_sha256=receipt_hash, ledger_path=ledger,
                    ),
                )
                exhausted = dispatcher.claim_novel_orders(
                    active, historical, consumer="test",
                    request_id="dispatcher:2026-08-26", ledger_path=ledger,
                )
                self.assertEqual([], exhausted)
                request.unlink()
                self.assertEqual([], dispatcher.reconcile_requests(ledger, inbox))
                self.assertFalse(request.exists())

    def test_cli_splits_valid_exhaustion_rc10_from_integrity_block_rc20(self):
        with tempfile.TemporaryDirectory() as directory:
            with self._runtime(Path(directory), active=1, historical=0) as (
                orders, _inbox, ledger, families, corpus, corpus_hash
            ):
                active, historical = dispatcher.load_order_registry(orders)
                dispatcher.claim_novel_orders(
                    active, historical, consumer="test",
                    request_id="dispatcher:" + datetime.date.today().isoformat(),
                    ledger_path=ledger,
                )
                receipt, receipt_hash = _fixture_fulfilment(
                    Path(directory), families, corpus, corpus_hash
                )
                dispatcher.fulfil_reservations(
                    ["family-1"], receipt_path=str(receipt),
                    receipt_sha256=receipt_hash, ledger_path=ledger,
                )
                self.assertEqual(10, dispatcher.cli_main())
                self.assertEqual(10, daily_content.cli_main())
                Path(orders).unlink()
                self.assertEqual(20, dispatcher.cli_main())
                self.assertEqual(20, daily_content.cli_main())
                Path(orders).write_text(
                    "malformed-family-without-required-fields\n", encoding="utf-8"
                )
                self.assertEqual(20, dispatcher.cli_main())
                self.assertEqual(20, daily_content.cli_main())
                with mock.patch.object(
                    dispatcher, "main", side_effect=RuntimeError("unexpected crash")
                ):
                    with self.assertRaisesRegex(RuntimeError, "unexpected crash"):
                        dispatcher.cli_main()
                with mock.patch.object(
                    daily_content, "run", side_effect=RuntimeError("unexpected crash")
                ):
                    with self.assertRaisesRegex(RuntimeError, "unexpected crash"):
                        daily_content.cli_main()

    def test_supplied_topic_hash_and_request_id_are_recomputed_before_commit(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            orders = base / "automation-log" / "orders.txt"
            with mock.patch.object(dispatcher, "ROOT", base):
                _fixture_registry(orders, active_count=1, historical_count=0)
                active, historical = dispatcher.load_order_registry(orders)
                ledger = base / "ledger.jsonl"
                dispatcher.bootstrap_novelty_state(ledger)
                tampered = [dict(active[0], topic_sha256="0" * 64)]
                with self.assertRaisesRegex(dispatcher.NoveltyIntegrityError, "topic hash"):
                    dispatcher.claim_novel_orders(
                        tampered, historical, consumer="test",
                        request_id="dispatcher:2026-08-25", ledger_path=ledger,
                    )
                with self.assertRaisesRegex(dispatcher.NoveltyIntegrityError, "request_id"):
                    dispatcher.claim_novel_orders(
                        active, historical, consumer="test",
                        request_id="request-1", ledger_path=ledger,
                    )
                self.assertEqual([], dispatcher.read_consumed_ledger(ledger))

    def test_ledger_checkpoint_interrupted_commit_recovers_idempotently(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            orders = base / "automation-log" / "orders.txt"
            with mock.patch.object(dispatcher, "ROOT", base):
                _fixture_registry(orders, active_count=1, historical_count=0)
                active, historical = dispatcher.load_order_registry(orders)
                ledger = base / "ledger.jsonl"
                dispatcher.bootstrap_novelty_state(ledger)
                checkpoint = dispatcher._state_paths(ledger)[1]
                real_atomic = dispatcher._atomic_write

                def fail_checkpoint(path, payload):
                    if Path(path) == checkpoint:
                        raise OSError("simulated checkpoint crash")
                    return real_atomic(path, payload)

                with mock.patch.object(dispatcher, "_atomic_write", side_effect=fail_checkpoint):
                    with self.assertRaises(OSError):
                        dispatcher.claim_novel_orders(
                            active, historical, consumer="test",
                            request_id="dispatcher:2026-08-25", ledger_path=ledger,
                        )
                with self.assertRaisesRegex(dispatcher.NoveltyIntegrityError, "checkpoint"):
                    dispatcher.read_consumed_ledger(ledger)
                recovered = dispatcher.claim_novel_orders(
                    active, historical, consumer="test",
                    request_id="dispatcher:2026-08-25", ledger_path=ledger,
                )
                self.assertEqual("RESERVED", recovered[0]["event"])
                stable = {
                    path: path.read_bytes() for path in (
                        ledger, checkpoint, dispatcher._append_journal_path(ledger)
                    )
                }
                repeated = dispatcher.claim_novel_orders(
                    active, historical, consumer="test",
                    request_id="dispatcher:2026-08-25", ledger_path=ledger,
                )
                self.assertEqual(recovered, repeated)
                self.assertEqual(
                    stable,
                    {path: path.read_bytes() for path in stable},
                )


if __name__ == "__main__":
    unittest.main(verbosity=2)
