"""Targeted P1 regressions for strict novelty admission and terminal evidence."""

from __future__ import annotations

import contextlib
import hashlib
import json
import multiprocessing
import os
from pathlib import Path
import subprocess
import tempfile
import time
import unittest
from unittest import mock

from tools.test_content_novelty_queue import (
    PIPELINE,
    _fixture_fulfilment,
    _fixture_registry,
    _hold_process_lock,
    _prepare_fixture_root,
    _sha,
    _write_json,
)

import sys

if str(PIPELINE) not in sys.path:
    sys.path.insert(0, str(PIPELINE))

import daily_content  # noqa: E402
import dispatcher  # noqa: E402


def _snapshot_tree(*roots: Path) -> dict[str, str]:
    out = {}
    for root in roots:
        if root.is_file():
            out[str(root)] = hashlib.sha256(root.read_bytes()).hexdigest().upper()
        elif root.is_dir():
            for path in sorted(item for item in root.rglob("*") if item.is_file()):
                out[str(path)] = hashlib.sha256(path.read_bytes()).hexdigest().upper()
    return out


def _write_review(
    base: Path, row: dict, *, name: str, candidate: str,
) -> tuple[str, str]:
    relative = "automation-log/dedup-evidence/" + name
    path = base / relative
    topic_audit = dispatcher.content_pack_audit.audit_topics(
        base, candidate, [row]
    )
    _write_json(path, {
        "schema_version": dispatcher.CORPUS_REVIEW_SCHEMA_VERSION,
        "receipt_type": dispatcher.CORPUS_REVIEW_RECEIPT_TYPE,
        "producer": dispatcher.CORPUS_REVIEW_PRODUCER,
        "method": dispatcher.CORPUS_REVIEW_METHOD,
        "review_state": "PROVISIONAL_LOCAL_REVIEW",
        "semantic_universality_claimed": False,
        "publication_authority": "NONE",
        "created_at": "2026-08-25T00:00:00+07:00",
        "method_limit": "Local deterministic checks do not prove universal semantic novelty.",
        "candidate_path": candidate,
        "families": [{
            "family_id": row["family_id"], "topic": row["topic"],
            "topic_sha256": row["topic_sha256"],
        }],
        "corpus_inputs": dispatcher.current_corpus_inputs(candidate),
        "corpus_audit": {
            key: topic_audit[key] for key in (
                "topic_candidates", "topic_baseline_records",
                "historical_exact_collisions", "historical_near_collisions",
                "cross_family_exact_collisions", "cross_family_near_collisions",
            )
        },
        "explicit_non_authority": "Local provisional review only; no publication authority.",
    })
    return relative, _sha(path)


class ContentNoveltyP1Tests(unittest.TestCase):
    @contextlib.contextmanager
    def _runtime(self, base: Path, active_count: int = 3):
        with contextlib.ExitStack() as stack:
            stack.enter_context(mock.patch.object(dispatcher, "ROOT", base))
            _prepare_fixture_root(base)
            orders = base / "automation-log" / "orders.txt"
            inbox = base / "automation-log" / "cowork-inbox"
            inbox.mkdir(parents=True)
            families, corpus, corpus_hash = _fixture_registry(
                orders, active_count=active_count, historical_count=0
            )
            stack.enter_context(mock.patch.object(dispatcher, "ORDERS", str(orders)))
            stack.enter_context(mock.patch.object(dispatcher, "INBOX", str(inbox)))
            stack.enter_context(mock.patch.object(daily_content, "ORDERS", str(orders)))
            stack.enter_context(mock.patch.object(daily_content, "INBOX", str(inbox)))
            ledger = dispatcher.ledger_path_for(inbox)
            dispatcher.bootstrap_novelty_state(ledger)
            yield orders, inbox, ledger, families, corpus, corpus_hash

    def test_shared_three_family_review_can_fulfil_daily_subset_without_false_consumption(self):
        with tempfile.TemporaryDirectory() as raw:
            base = Path(raw)
            with self._runtime(base, active_count=3) as (
                orders, _inbox, ledger, families, corpus, corpus_hash
            ):
                active, historical = dispatcher.load_order_registry(orders)
                mode, reserved = dispatcher.select_daily_order_atomic(
                    active, historical, request_id="daily:2026-08-25",
                    ledger_path=ledger,
                )
                self.assertEqual("DAILY_RESERVED", mode)
                self.assertEqual([families[0]["family_id"]], [row["family_id"] for row in reserved])
                receipt, receipt_hash = _fixture_fulfilment(
                    base, families[:1], corpus, corpus_hash,
                    request_id="daily:2026-08-25",
                )
                drafted = dispatcher.fulfil_outstanding_from_receipt(
                    receipt_path=receipt, receipt_sha256=receipt_hash,
                    ledger_path=ledger,
                )
                self.assertEqual(1, len(drafted))
                rows = dispatcher.read_consumed_ledger(ledger)
                _reserved, consumed, outstanding = dispatcher._lifecycle(rows)
                self.assertEqual({}, outstanding)
                self.assertEqual({}, consumed)
                self.assertEqual(
                    {families[0]["family_id"]},
                    set(dispatcher._drafted_map(rows)),
                )
                self.assertFalse(any(
                    row["family_id"] in {families[1]["family_id"], families[2]["family_id"]}
                    for row in rows
                ))
                next_rows = dispatcher.claim_novel_orders(
                    active, historical, consumer="test",
                    request_id="dispatcher:2026-08-26", ledger_path=ledger,
                )
                self.assertEqual(
                    [families[1]["family_id"], families[2]["family_id"]],
                    [row["family_id"] for row in next_rows],
                )

    def test_reconcile_evidence_and_retirement_use_one_coherent_lock_view(self):
        with tempfile.TemporaryDirectory() as raw:
            base = Path(raw)
            with self._runtime(base, active_count=1) as (
                orders, inbox, ledger, _families, _corpus, _corpus_hash
            ):
                active, historical = dispatcher.load_order_registry(orders)
                dispatcher.claim_novel_orders(
                    active, historical, consumer="test",
                    request_id="dispatcher:2026-08-25", ledger_path=ledger,
                )
                dispatcher.reconcile_requests(ledger, inbox)
                before = _snapshot_tree(
                    ledger, *dispatcher._state_paths(ledger),
                    dispatcher._append_journal_path(ledger), inbox,
                )
                ready = base / "lock-ready"
                process = multiprocessing.get_context("spawn").Process(
                    target=_hold_process_lock, args=(str(ledger), str(ready))
                )
                process.start()
                deadline = time.monotonic() + 5
                while not ready.exists() and time.monotonic() < deadline:
                    time.sleep(0.02)
                self.assertTrue(ready.exists())
                try:
                    with mock.patch.object(dispatcher, "LOCK_TIMEOUT_SECONDS", 0.03):
                        for operation in (
                            lambda: dispatcher.reconcile_requests(ledger, inbox),
                            lambda: dispatcher.validate_consumed_evidence(ledger),
                            lambda: dispatcher.retire_request_inventory(ledger, inbox),
                        ):
                            with self.subTest(operation=operation):
                                with self.assertRaises(dispatcher.NoveltyLockError):
                                    operation()
                    self.assertEqual(
                        before,
                        _snapshot_tree(
                            ledger, *dispatcher._state_paths(ledger),
                            dispatcher._append_journal_path(ledger), inbox,
                        ),
                    )
                finally:
                    process.terminate()
                    process.join(5)
                self.assertEqual([], dispatcher.reconcile_requests(ledger, inbox))
                self.assertEqual(
                    "PASS_EMPTY", dispatcher.validate_consumed_evidence(ledger)["state"]
                )
                self.assertEqual(
                    "PASS_ACTIVE", dispatcher.retire_request_inventory(ledger, inbox)["state"]
                )

    def test_two_review_groups_are_never_combined_in_one_request(self):
        with tempfile.TemporaryDirectory() as raw:
            base = Path(raw)
            with self._runtime(base, active_count=2) as (
                orders, _inbox, ledger, families, _corpus, _corpus_hash
            ):
                bindings = []
                for index, row in enumerate(families, 1):
                    candidate = (
                        "automation-log/cc-outbox/LOCAL-CONTENT-PACK_GROUP%d.md" % index
                    )
                    bindings.append(_write_review(
                        base, row, name="group%d-review.json" % index,
                        candidate=candidate,
                    ))
                orders.write_text("\n".join(
                    "\t".join((
                        row["family_id"], row["topic"], binding[0], binding[1],
                    ))
                    for row, binding in zip(families, bindings)
                ) + "\n", encoding="utf-8")
                active, historical = dispatcher.load_order_registry(orders)
                first = dispatcher.claim_novel_orders(
                    active, historical, consumer="test",
                    request_id="dispatcher:2026-08-25", ledger_path=ledger,
                )
                self.assertEqual([families[0]["family_id"]], [row["family_id"] for row in first])
                receipt, receipt_hash = _fixture_fulfilment(
                    base, families[:1], bindings[0][0], bindings[0][1],
                    candidate_relative="automation-log/cc-outbox/LOCAL-CONTENT-PACK_GROUP1.md",
                    receipt_relative="automation-log/dedup-evidence/group1-fulfilment.json",
                )
                dispatcher.fulfil_outstanding_from_receipt(
                    receipt_path=receipt, receipt_sha256=receipt_hash,
                    ledger_path=ledger,
                )
                # The first fulfilled pack has now become part of the canonical
                # prior-pack inventory.  The second review was deliberately
                # issued before that corpus transition, so admission must fail
                # closed rather than leaving an outstanding reservation.
                with self.assertRaises(dispatcher.NoveltyIntegrityError):
                    dispatcher.claim_novel_orders(
                        active, historical, consumer="test",
                        request_id="dispatcher:2026-08-26", ledger_path=ledger,
                    )
                _reserved, _terminal, outstanding = dispatcher._lifecycle(
                    dispatcher.read_consumed_ledger(ledger)
                )
                self.assertEqual({}, outstanding)

                refreshed = _write_review(
                    base, families[1], name="group2-review-refreshed.json",
                    candidate="automation-log/cc-outbox/LOCAL-CONTENT-PACK_GROUP2.md",
                )
                orders.write_text("\n".join((
                    "\t".join((
                        families[0]["family_id"], families[0]["topic"],
                        bindings[0][0], bindings[0][1],
                    )),
                    "\t".join((
                        families[1]["family_id"], families[1]["topic"],
                        refreshed[0], refreshed[1],
                    )),
                )) + "\n", encoding="utf-8")
                active, historical = dispatcher.load_order_registry(orders)
                second = dispatcher.claim_novel_orders(
                    active, historical, consumer="test",
                    request_id="dispatcher:2026-08-26", ledger_path=ledger,
                )
                self.assertEqual([families[1]["family_id"]], [row["family_id"] for row in second])

    def test_fabricated_zero_audits_minimal_copy_and_wrong_candidate_all_block(self):
        for target in (
            "zero_audit", "minimal_pack", "wrong_candidate",
            "nested_pack", "audit_engine",
        ):
            with self.subTest(target=target), tempfile.TemporaryDirectory() as raw:
                base = Path(raw)
                with self._runtime(base, active_count=1) as (
                    orders, _inbox, ledger, families, corpus, corpus_hash
                ):
                    active, historical = dispatcher.load_order_registry(orders)
                    reserved = dispatcher.claim_novel_orders(
                        active, historical, consumer="test",
                        request_id="dispatcher:2026-08-25", ledger_path=ledger,
                    )
                    receipt, _receipt_hash = _fixture_fulfilment(
                        base, families, corpus, corpus_hash
                    )
                    receipt_path = base / receipt
                    payload = json.loads(receipt_path.read_text(encoding="utf-8"))
                    if target == "zero_audit":
                        # A self-asserted clean result must be compared with the
                        # deterministic audit, not trusted merely because every
                        # declared failure counter is zero.
                        payload["relevance_audit"]["method"] = "fabricated-zero-claim"
                    elif target in {"minimal_pack", "wrong_candidate"}:
                        original_pack = base / payload["pack"]["path"]
                        if target == "minimal_pack":
                            original_pack.write_text(
                                "# blocked\n\n- `request_id`: `dispatcher:2026-08-25`\n"
                                "- `status`: `DRAFT_ONLY_BLOCKED_SOURCE_REVIEW`\n"
                                "- `publication_authority`: `NONE`\n"
                                "- `novelty_review_state`: `PROVISIONAL_LOCAL_REVIEW`\n"
                                "- `semantic_universality_claimed`: `FALSE`\n\n"
                                "## 1. unrelated\n\n- `family_id`: `" + families[0]["family_id"] + "`\n\n"
                                "### Threads\n\n" + ("x" * 450) + "\n\n"
                                "### Facebook\n\n" + ("y" * 450) + "\n\n"
                                "### TikTok\n\n" + ("z" * 450) + "\n",
                                encoding="utf-8",
                            )
                        else:
                            wrong = base / "automation-log/cc-outbox/LOCAL-CONTENT-PACK_WRONG.md"
                            wrong.write_bytes(original_pack.read_bytes())
                            payload["pack"]["path"] = wrong.relative_to(base).as_posix()
                            original_pack = wrong
                        payload["pack"]["sha256"] = _sha(original_pack)
                    elif target == "nested_pack":
                        payload["pack"]["unexpected"] = "fabricated"
                    else:
                        payload["audit_engine"]["sha256"] = "0" * 64
                    _write_json(receipt_path, payload)
                    bad_hash = _sha(receipt_path)
                    with self.assertRaises(dispatcher.NoveltyIntegrityError):
                        dispatcher.fulfil_reservations(
                            [reserved[0]["family_id"]], receipt_path=receipt,
                            receipt_sha256=bad_hash, ledger_path=ledger,
                        )
                    self.assertEqual(0, len([
                        row for row in dispatcher.read_consumed_ledger(ledger)
                        if row["event"] == "CONSUMED" and not row["historical"]
                    ]))

    def test_snapshot_survives_live_swap_but_missing_blob_blocks_terminal_validation(self):
        with tempfile.TemporaryDirectory() as raw:
            base = Path(raw)
            with self._runtime(base, active_count=1) as (
                orders, _inbox, ledger, families, corpus, corpus_hash
            ):
                active, historical = dispatcher.load_order_registry(orders)
                dispatcher.claim_novel_orders(
                    active, historical, consumer="test",
                    request_id="dispatcher:2026-08-25", ledger_path=ledger,
                )
                receipt, receipt_hash = _fixture_fulfilment(
                    base, families, corpus, corpus_hash
                )
                pack = base / "automation-log/cc-outbox/LOCAL-CONTENT-PACK_FIXTURE.md"
                original = pack.read_bytes()
                real_snapshot = dispatcher._write_consumption_snapshot

                def snapshot_then_swap(*args, **kwargs):
                    result = real_snapshot(*args, **kwargs)
                    pack.write_bytes(b"swapped live bytes after immutable snapshot")
                    return result

                with mock.patch.object(
                    dispatcher, "_write_consumption_snapshot",
                    side_effect=snapshot_then_swap,
                ):
                    dispatcher.fulfil_outstanding_from_receipt(
                        receipt_path=receipt, receipt_sha256=receipt_hash,
                        ledger_path=ledger,
                    )
                self.assertNotEqual(original, pack.read_bytes())
                self.assertEqual("PASS", dispatcher.validate_consumed_evidence(ledger)["state"])
                live_engine = base / "pipeline/content_pack_audit.py"
                live_engine_bytes = live_engine.read_bytes()
                live_engine.write_bytes(
                    live_engine_bytes + b"\n# compatible future audit engine\n"
                )
                self.assertEqual(
                    "PASS", dispatcher.validate_consumed_evidence(ledger)["state"]
                )
                live_engine.write_bytes(live_engine_bytes)
                manifest, _payloads = dispatcher._load_consumption_snapshot(receipt_hash)
                pack_record = next(
                    item for item in manifest["artifacts"] if item["role"] == "candidate_pack"
                )
                blob = (
                    base / dispatcher._snapshot_relative(receipt_hash)
                ).parent / pack_record["blob"]
                blob.unlink()
                with self.assertRaises(dispatcher.NoveltyIntegrityError):
                    dispatcher.validate_consumed_evidence(ledger)

    def test_snapshot_manifest_drop_add_or_role_rewrite_blocks_after_valid_rehash(self):
        for target in ("drop", "add", "role_rewrite"):
            with self.subTest(target=target), tempfile.TemporaryDirectory() as raw:
                base = Path(raw)
                with self._runtime(base, active_count=1) as (
                    orders, _inbox, ledger, families, corpus, corpus_hash
                ):
                    active, historical = dispatcher.load_order_registry(orders)
                    dispatcher.claim_novel_orders(
                        active, historical, consumer="test",
                        request_id="dispatcher:2026-08-25", ledger_path=ledger,
                    )
                    receipt, receipt_hash = _fixture_fulfilment(
                        base, families, corpus, corpus_hash
                    )
                    dispatcher.fulfil_outstanding_from_receipt(
                        receipt_path=receipt, receipt_sha256=receipt_hash,
                        ledger_path=ledger,
                    )
                    manifest_path = base / dispatcher._snapshot_relative(receipt_hash)
                    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
                    records = payload["artifacts"]
                    if target == "drop":
                        records.pop(next(
                            index for index, item in enumerate(records)
                            if item["role"] == "corpus_input"
                        ))
                    elif target == "add":
                        data = b"unbound-extra-artifact"
                        digest = hashlib.sha256(data).hexdigest().upper()
                        blob = manifest_path.parent / "blobs" / (digest + ".bin")
                        blob.write_bytes(data)
                        records.append({
                            "role": "corpus_input",
                            "path": "automation-log/content-packages/EXTRA.md",
                            "sha256": digest,
                            "blob": "blobs/" + digest + ".bin",
                        })
                    else:
                        candidate = next(
                            item for item in records if item["role"] == "candidate_pack"
                        )
                        candidate["role"] = "corpus_input"
                    records.sort(key=lambda item: (item["role"], item["path"]))
                    payload["bundle_sha256"] = dispatcher._sha256_bytes(
                        dispatcher._canonical_json(records).encode("utf-8")
                    )
                    manifest_path.write_bytes(
                        (dispatcher._canonical_json(payload) + "\n").encode("utf-8")
                    )
                    with self.assertRaises(dispatcher.NoveltyIntegrityError):
                        dispatcher.validate_consumed_evidence(ledger)

    def test_same_day_terminal_reruns_are_byte_idempotent(self):
        with tempfile.TemporaryDirectory() as raw:
            base = Path(raw)
            with self._runtime(base, active_count=1) as (
                _orders, inbox, ledger, families, corpus, corpus_hash
            ):
                first = dispatcher.main()
                receipt, receipt_hash = _fixture_fulfilment(
                    base, families, corpus, corpus_hash
                )
                dispatcher.fulfil_outstanding_from_receipt(
                    receipt_path=receipt, receipt_sha256=receipt_hash,
                    ledger_path=ledger,
                )
                dispatcher.retire_request_inventory(ledger, inbox)
                roots = [
                    ledger, *dispatcher._state_paths(ledger), inbox,
                    inbox.parent / "_retired-generation",
                    base / ".local-private/runtime/content-novelty/evidence",
                ]
                before = _snapshot_tree(*roots)
                again = dispatcher.main()
                twice = dispatcher.main()
                self.assertEqual("NOVELTY_EXHAUSTED", again["state"])
                self.assertEqual("NOVELTY_EXHAUSTED", twice["state"])
                self.assertEqual(before, _snapshot_tree(*roots))
                self.assertTrue(
                    Path(first["request"]).read_bytes().startswith(
                        b"# DRAFTED_BLOCKED_DO_NOT_GENERATE"
                    )
                )

    @unittest.skipUnless(os.name == "nt", "Windows junction regression")
    def test_allowed_evidence_candidate_and_snapshot_root_junctions_fail_closed(self):
        for kind in ("dedup-evidence", "cc-outbox", "evidence"):
            with self.subTest(kind=kind), tempfile.TemporaryDirectory() as raw:
                base = Path(raw) / "repo"
                outside = Path(raw) / "outside"
                outside.mkdir()
                if kind == "evidence":
                    parent = base / ".local-private/runtime/content-novelty"
                else:
                    parent = base / "automation-log"
                parent.mkdir(parents=True)
                link = parent / kind
                created = subprocess.run(
                    ["cmd", "/c", "mklink", "/J", str(link), str(outside)],
                    text=True, capture_output=True, check=False,
                )
                if created.returncode != 0:
                    self.skipTest("junction creation unavailable: " + created.stderr)
                with mock.patch.object(dispatcher, "ROOT", base):
                    if kind == "dedup-evidence":
                        with self.assertRaises(dispatcher.NoveltyIntegrityError):
                            dispatcher._resolve_repo_evidence_path(
                                "automation-log/dedup-evidence/test.json"
                            )
                    elif kind == "cc-outbox":
                        with self.assertRaises(dispatcher.NoveltyIntegrityError):
                            dispatcher._resolve_repo_candidate_path(
                                "automation-log/cc-outbox/LOCAL-CONTENT-PACK_TEST.md"
                            )
                    else:
                        with self.assertRaises(dispatcher.NoveltyIntegrityError):
                            dispatcher._write_consumption_snapshot(
                                "A" * 64,
                                [{"role": "test", "path": "test", "bytes": b"test"}],
                            )

    def test_crlf_pack_has_same_deterministic_audit_as_lf(self):
        with tempfile.TemporaryDirectory() as raw:
            base = Path(raw)
            with self._runtime(base, active_count=1) as (
                _orders, _inbox, _ledger, families, corpus, corpus_hash
            ):
                receipt, _receipt_hash = _fixture_fulfilment(
                    base, families, corpus, corpus_hash
                )
                fulfilment = json.loads((base / receipt).read_text(encoding="utf-8"))
                pack = base / fulfilment["pack"]["path"]
                lf = pack.read_bytes().replace(b"\r\n", b"\n")
                crlf = lf.replace(b"\n", b"\r\n")
                corpus_bytes, _inputs = dispatcher._capture_corpus_bytes(
                    fulfilment["pack"]["path"]
                )
                left = dispatcher.content_pack_audit.audit_pack_text(
                    base, fulfilment["pack"]["path"], families,
                    lf.decode("utf-8"), corpus_bytes,
                )
                right = dispatcher.content_pack_audit.audit_pack_text(
                    base, fulfilment["pack"]["path"], families,
                    crlf.decode("utf-8"), corpus_bytes,
                )
                self.assertEqual(left, right)

    def test_review_refresh_recovers_old_request_bytes_and_drafts_latest_binding(self):
        with tempfile.TemporaryDirectory() as raw:
            base = Path(raw)
            with self._runtime(base, active_count=1) as (
                orders, inbox, ledger, families, _corpus, _corpus_hash
            ):
                active, historical = dispatcher.load_order_registry(orders)
                reserved = dispatcher.claim_novel_orders(
                    active, historical, consumer="test",
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
                old_request_bytes = request.read_bytes()
                reference = dispatcher.request_path(
                    "daily-reference", "2026-08-25", inbox=inbox
                )
                dispatcher.write_reference(
                    reference, date="2026-08-25",
                    request_id="daily:2026-08-25", rows=reserved,
                    referenced_path=request,
                    title="DAILY LOCAL NOVELTY REFERENCE",
                )
                old_reference_bytes = reference.read_bytes()

                calendar = base / ".system_control/content_calendar.json"
                calendar_payload = json.loads(calendar.read_text(encoding="utf-8"))
                calendar_payload["items"].append({
                    "title": "Later unrelated calendar evidence transition",
                    "copy": "A later corpus entry documents a separate source and reviewer.",
                })
                _write_json(calendar, calendar_payload)
                refreshed = _write_review(
                    base, families[0], name="refreshed-review.json",
                    candidate="automation-log/cc-outbox/LOCAL-CONTENT-PACK_FIXTURE.md",
                )
                orders.write_text("\t".join((
                    families[0]["family_id"], families[0]["topic"],
                    refreshed[0], refreshed[1],
                )) + "\n", encoding="utf-8")
                active, historical = dispatcher.load_order_registry(orders)
                refreshed_rows, mode = dispatcher.claim_novel_orders(
                    active, historical, consumer="test-refresh",
                    request_id="dispatcher:2026-08-25", ledger_path=ledger,
                    return_mode=True,
                )
                self.assertEqual("REVIEW_REFRESHED", mode)
                self.assertEqual("REVIEW_REFRESHED", refreshed_rows[0]["event"])
                self.assertEqual(old_request_bytes, request.read_bytes())
                self.assertEqual(old_reference_bytes, reference.read_bytes())
                recovered = dispatcher.reconcile_requests(ledger, inbox)
                self.assertEqual({str(request), str(reference)}, set(recovered))
                self.assertNotEqual(old_request_bytes, request.read_bytes())
                self.assertNotEqual(old_reference_bytes, reference.read_bytes())

                receipt, receipt_hash = _fixture_fulfilment(
                    base, families, refreshed[0], refreshed[1]
                )
                drafted = dispatcher.fulfil_outstanding_from_receipt(
                    receipt_path=receipt, receipt_sha256=receipt_hash,
                    ledger_path=ledger,
                )
                self.assertEqual(refreshed[0], drafted[0]["corpus_review_receipt"])
                self.assertEqual(refreshed[1], drafted[0]["corpus_review_sha256"])
                retired = dispatcher.retire_request_inventory(ledger, inbox)
                self.assertEqual("PASS_EMPTY", retired["state"])
                self.assertEqual({}, dispatcher._lifecycle(
                    dispatcher.read_consumed_ledger(ledger)
                )[2])

    def test_stale_or_fabricated_corpus_review_never_reserves(self):
        for target in ("stale_input", "fabricated_producer", "fabricated_audit"):
            with self.subTest(target=target), tempfile.TemporaryDirectory() as raw:
                base = Path(raw)
                with self._runtime(base, active_count=1) as (
                    orders, _inbox, ledger, _families, corpus, _corpus_hash
                ):
                    active, historical = dispatcher.load_order_registry(orders)
                    receipt_path = base / corpus
                    if target == "stale_input":
                        manifest = base / ".system_control/content_manifest.json"
                        manifest.write_bytes(manifest.read_bytes() + b"\n")
                    else:
                        payload = json.loads(receipt_path.read_text(encoding="utf-8"))
                        if target == "fabricated_producer":
                            payload["producer"] = "fabricated-review-producer"
                        else:
                            payload["corpus_audit"]["topic_baseline_records"] += 1
                        _write_json(receipt_path, payload)
                        new_hash = _sha(receipt_path)
                        raw_orders = orders.read_text(encoding="utf-8")
                        orders.write_text(
                            raw_orders.replace(active[0]["corpus_review_sha256"], new_hash),
                            encoding="utf-8",
                        )
                        if target == "fabricated_producer":
                            with self.assertRaises(dispatcher.NoveltyIntegrityError):
                                dispatcher.load_order_registry(orders)
                            self.assertEqual([], dispatcher.read_consumed_ledger(ledger))
                            continue
                        active, historical = dispatcher.load_order_registry(orders)
                    with self.assertRaises(dispatcher.NoveltyIntegrityError):
                        dispatcher.claim_novel_orders(
                            active, historical, consumer="test",
                            request_id="dispatcher:2026-08-25", ledger_path=ledger,
                        )
                    self.assertEqual([], dispatcher.read_consumed_ledger(ledger))

    def test_v3_near_copy_of_prior_v2_is_detected_and_cannot_be_consumed(self):
        with tempfile.TemporaryDirectory() as raw:
            base = Path(raw)
            with self._runtime(base, active_count=1) as (
                orders, _inbox, ledger, families, corpus, corpus_hash
            ):
                _fixture_fulfilment(base, families, corpus, corpus_hash)
                fixture = base / "automation-log/cc-outbox/LOCAL-CONTENT-PACK_FIXTURE.md"
                v2 = base / "automation-log/cc-outbox/LOCAL-CONTENT-PACK_V2.md"
                v2.write_bytes(fixture.read_bytes())
                fixture.unlink()

                candidate = "automation-log/cc-outbox/LOCAL-CONTENT-PACK_V3.md"
                review = _write_review(
                    base, families[0], name="v3-review.json", candidate=candidate,
                )
                orders.write_text("\t".join((
                    families[0]["family_id"], families[0]["topic"],
                    review[0], review[1],
                )) + "\n", encoding="utf-8")
                active, historical = dispatcher.load_order_registry(orders)
                reserved = dispatcher.claim_novel_orders(
                    active, historical, consumer="test",
                    request_id="dispatcher:2026-08-25", ledger_path=ledger,
                )
                fulfilment, _old_hash = _fixture_fulfilment(
                    base, families, review[0], review[1],
                    candidate_relative=candidate,
                    receipt_relative="automation-log/dedup-evidence/v3-fulfilment.json",
                )
                candidate_path = base / candidate
                candidate_path.write_text(
                    candidate_path.read_text(encoding="utf-8").replace(
                        "This blocked educational fixture uses",
                        "This blocked educational revised fixture uses",
                    ),
                    encoding="utf-8",
                )
                audit = dispatcher.content_pack_audit.audit_pack(
                    base, candidate, families, candidate_path,
                )
                self.assertEqual(0, audit["copy_corpus_audit"]["historical_exact_collisions"])
                self.assertGreater(
                    audit["copy_corpus_audit"]["historical_near_collisions"], 0
                )
                fulfilment_path = base / fulfilment
                payload = json.loads(fulfilment_path.read_text(encoding="utf-8"))
                payload["pack"]["sha256"] = _sha(candidate_path)
                payload["safety_audit"] = audit["safety_audit"]
                payload["copy_corpus_audit"] = audit["copy_corpus_audit"]
                payload["relevance_audit"] = audit["relevance_audit"]
                _write_json(fulfilment_path, payload)
                with self.assertRaises(dispatcher.NoveltyIntegrityError):
                    dispatcher.fulfil_reservations(
                        [reserved[0]["family_id"]], receipt_path=fulfilment,
                        receipt_sha256=_sha(fulfilment_path), ledger_path=ledger,
                    )
                self.assertEqual(1, len(dispatcher.read_consumed_ledger(ledger)))

    def test_exact_source_audit_engine_blocks_mid_audit_disk_swap(self):
        with tempfile.TemporaryDirectory() as raw:
            base = Path(raw)
            with self._runtime(base, active_count=1) as (
                _orders, _inbox, ledger, families, corpus, corpus_hash
            ):
                active, historical = dispatcher.load_order_registry(
                    base / "automation-log/orders.txt"
                )
                reserved = dispatcher.claim_novel_orders(
                    active, historical, consumer="test",
                    request_id="dispatcher:2026-08-25", ledger_path=ledger,
                )
                receipt, receipt_hash = _fixture_fulfilment(
                    base, families, corpus, corpus_hash,
                )
                engine = base / dispatcher.AUDIT_ENGINE_RELATIVE
                engine_bytes = engine.read_bytes()
                self.assertEqual(
                    dispatcher.content_pack_audit.AUDIT_ENGINE_SOURCE_SHA256,
                    hashlib.sha256(engine_bytes).hexdigest().upper(),
                )
                state_paths = (
                    ledger, *dispatcher._state_paths(ledger),
                    dispatcher._append_journal_path(ledger),
                )
                before = {
                    path: path.read_bytes() for path in state_paths if path.exists()
                }
                bound = dispatcher._load_bound_audit_engine()
                self.assertNotIn("comply_gate", bound["module"].__dict__)
                real_loader = dispatcher._load_bound_audit_engine

                def loader_with_mid_audit_swap(*args, **kwargs):
                    runtime = real_loader(*args, **kwargs)
                    bound_module = runtime["module"]
                    real_audit = bound_module.audit_pack_text

                    def swap_engine_after_audit(*audit_args, **audit_kwargs):
                        result = real_audit(*audit_args, **audit_kwargs)
                        engine.write_bytes(
                            b"not valid Python and not the bound audit engine\n"
                        )
                        return result

                    bound_module.audit_pack_text = swap_engine_after_audit
                    return runtime

                with mock.patch.object(
                    dispatcher, "_load_bound_audit_engine",
                    side_effect=loader_with_mid_audit_swap,
                ):
                    with self.assertRaises(dispatcher.NoveltyIntegrityError):
                        dispatcher.fulfil_reservations(
                            [reserved[0]["family_id"]], receipt_path=receipt,
                            receipt_sha256=receipt_hash, ledger_path=ledger,
                        )
                self.assertEqual(
                    before, {path: path.read_bytes() for path in before}
                )
                self.assertFalse(
                    (base / dispatcher._snapshot_relative(receipt_hash)).exists()
                )

                engine.write_bytes(engine_bytes)
                drafted = dispatcher.fulfil_reservations(
                    [reserved[0]["family_id"]], receipt_path=receipt,
                    receipt_sha256=receipt_hash, ledger_path=ledger,
                )
                self.assertEqual(["DRAFTED_BLOCKED"], [row["event"] for row in drafted])
                _manifest, snapshot = dispatcher._load_consumption_snapshot(receipt_hash)
                self.assertEqual(engine_bytes, snapshot[dispatcher.AUDIT_ENGINE_RELATIVE])
                engine.write_bytes(b"still not Python after terminal snapshot\n")
                self.assertEqual(
                    "PASS", dispatcher.validate_consumed_evidence(ledger)["state"]
                )
                engine.write_bytes(engine_bytes)

    def test_stale_timestamp_pyc_cannot_replace_exact_source_execution(self):
        with tempfile.TemporaryDirectory() as raw:
            base = Path(raw)
            pipeline = base / "pipeline"
            pipeline.mkdir()
            for name in ("content_pack_audit.py", "dispatcher.py"):
                (pipeline / name).write_bytes((PIPELINE / name).read_bytes())
            environment = dict(os.environ)
            environment["PYTHONPATH"] = str(pipeline)
            first = subprocess.run(
                [
                    sys.executable, "-c",
                    (
                        "import content_pack_audit as c; "
                        "print(c.MIN_SUBSTANTIVE_NORMALIZED_CHARS); "
                        "print(c.__cached__)"
                    ),
                ],
                cwd=base, env=environment, text=True,
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=30,
            )
            self.assertEqual(0, first.returncode, first.stderr)
            self.assertTrue((pipeline / "__pycache__").is_dir())

            source = pipeline / "content_pack_audit.py"
            before = source.read_bytes()
            stat = source.stat()
            old = b"MIN_SUBSTANTIVE_NORMALIZED_CHARS = 80"
            new = b"MIN_SUBSTANTIVE_NORMALIZED_CHARS = 81"
            self.assertEqual(len(old), len(new))
            self.assertEqual(1, before.count(old))
            source.write_bytes(before.replace(old, new))
            os.utime(source, ns=(stat.st_atime_ns, stat.st_mtime_ns))
            self.assertEqual(len(before), source.stat().st_size)

            second = subprocess.run(
                [
                    sys.executable, "-c",
                    (
                        "import dispatcher; "
                        "print('IMPORTED=' + str("
                        "dispatcher.content_pack_audit.MIN_SUBSTANTIVE_NORMALIZED_CHARS)); "
                        "bound=dispatcher._load_bound_audit_engine(); "
                        "print('BOUND=' + str("
                        "bound['module'].MIN_SUBSTANTIVE_NORMALIZED_CHARS)); "
                        "print('SELF_CONTAINED=' + str("
                        "'comply_gate' not in bound['module'].__dict__))"
                    ),
                ],
                cwd=base, env=environment, text=True,
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=30,
            )
            self.assertEqual(0, second.returncode, second.stderr)
            self.assertIn("IMPORTED=80", second.stdout)
            self.assertIn("BOUND=81", second.stdout)
            self.assertIn("SELF_CONTAINED=True", second.stdout)

    def test_fulfilment_reuses_one_engine_across_timed_a_b_a_swap(self):
        with tempfile.TemporaryDirectory() as raw:
            base = Path(raw)
            with self._runtime(base, active_count=1) as (
                _orders, _inbox, ledger, families, corpus, corpus_hash
            ):
                active, historical = dispatcher.load_order_registry(
                    base / "automation-log/orders.txt"
                )
                reserved = dispatcher.claim_novel_orders(
                    active, historical, consumer="test",
                    request_id="dispatcher:2026-08-25", ledger_path=ledger,
                )
                receipt, receipt_hash = _fixture_fulfilment(
                    base, families, corpus, corpus_hash,
                )
                engine = base / dispatcher.AUDIT_ENGINE_RELATIVE
                source_a = engine.read_bytes()
                source_b = source_a.replace(
                    b"MIN_SUBSTANTIVE_NORMALIZED_CHARS = 80",
                    b"MIN_SUBSTANTIVE_NORMALIZED_CHARS = 81",
                )
                self.assertEqual(len(source_a), len(source_b))
                real_loader = dispatcher._load_bound_audit_engine
                runtime_a = real_loader()
                engine.write_bytes(source_b)
                runtime_b = real_loader()
                engine.write_bytes(source_a)
                self.assertNotEqual(runtime_a["sha256"], runtime_b["sha256"])
                load_count = 0

                def sequence_loader(*args, **kwargs):
                    nonlocal load_count
                    load_count += 1
                    return runtime_a if load_count == 1 else runtime_b

                real_review = dispatcher._validate_review_receipt

                def review_after_timed_a_b_a(*args, **kwargs):
                    engine.write_bytes(source_b)
                    time.sleep(0.01)
                    engine.write_bytes(source_a)
                    return real_review(*args, **kwargs)

                with mock.patch.object(
                    dispatcher, "_load_bound_audit_engine",
                    side_effect=sequence_loader,
                ), mock.patch.object(
                    dispatcher, "_validate_review_receipt",
                    side_effect=review_after_timed_a_b_a,
                ):
                    drafted = dispatcher.fulfil_reservations(
                        [reserved[0]["family_id"]], receipt_path=receipt,
                        receipt_sha256=receipt_hash, ledger_path=ledger,
                    )
                self.assertEqual(1, load_count)
                self.assertEqual(["DRAFTED_BLOCKED"], [row["event"] for row in drafted])
                _manifest, snapshot = dispatcher._load_consumption_snapshot(receipt_hash)
                self.assertEqual(source_a, snapshot[dispatcher.AUDIT_ENGINE_RELATIVE])

    def test_legacy_snapshot_is_append_safe_but_prefix_and_snapshot_tamper_block(self):
        with tempfile.TemporaryDirectory() as raw:
            base = Path(raw)
            with self._runtime(base, active_count=1) as (
                _orders, inbox, ledger, families, corpus, corpus_hash
            ):
                active, historical = dispatcher.load_order_registry(
                    base / "automation-log/orders.txt"
                )
                reserved = dispatcher.claim_novel_orders(
                    active, historical, consumer="test",
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
                legacy_receipt, _v2_hash = _fixture_fulfilment(
                    base, families, corpus, corpus_hash,
                    receipt_relative="automation-log/dedup-evidence/legacy-fulfilment.json",
                )
                legacy_path = base / legacy_receipt
                legacy_payload = json.loads(legacy_path.read_text(encoding="utf-8"))
                legacy_payload["schema_version"] = 1
                _write_json(legacy_path, legacy_payload)
                legacy_hash = _sha(legacy_path)
                with dispatcher._claim_lock(ledger):
                    rows = dispatcher.read_consumed_ledger(ledger)
                    committed = dispatcher._append_events_atomic(
                        ledger, rows, [dict(
                            reserved[0], event="CONSUMED",
                            consumer="legacy-local-draft-fulfilment",
                            fulfilment_receipt=legacy_receipt,
                            fulfilment_sha256=legacy_hash,
                        )],
                    )
                consumed = [
                    row for row in committed
                    if row["event"] == "CONSUMED" and not row["historical"]
                ]
                live_engine = base / dispatcher.AUDIT_ENGINE_RELATIVE
                live_engine_bytes = live_engine.read_bytes()
                real_loader = dispatcher._load_bound_audit_engine
                pre_builder_state = {
                    path: path.read_bytes()
                    for path in (ledger, *dispatcher._state_paths(ledger))
                    if path.exists()
                }
                strict_loader_count = 0

                def loader_with_strict_builder_swap(*args, **kwargs):
                    nonlocal strict_loader_count
                    strict_loader_count += 1
                    runtime = real_loader(*args, **kwargs)
                    bound_module = runtime["module"]
                    real_pack_audit = bound_module.audit_pack_text

                    def swap_engine_during_strict_builder(
                        *audit_args, **audit_kwargs
                    ):
                        result = real_pack_audit(*audit_args, **audit_kwargs)
                        live_engine.write_bytes(
                            b"not Python during strict cutover build\n"
                        )
                        return result

                    bound_module.audit_pack_text = swap_engine_during_strict_builder
                    return runtime

                with mock.patch.object(
                    dispatcher, "_load_bound_audit_engine",
                    side_effect=loader_with_strict_builder_swap,
                ):
                    with self.assertRaises(dispatcher.NoveltyIntegrityError):
                        dispatcher.strict_revalidation_payload(
                            consumed, ledger_path=ledger,
                            strict_corpus_review_path=corpus,
                            strict_corpus_review_sha256=corpus_hash,
                        )
                self.assertEqual(1, strict_loader_count)
                self.assertEqual(
                    pre_builder_state,
                    {path: path.read_bytes() for path in pre_builder_state},
                )
                self.assertFalse(
                    (base / dispatcher._snapshot_relative(legacy_hash)).exists()
                )
                live_engine.write_bytes(live_engine_bytes)
                strict = dispatcher.strict_revalidation_payload(
                    consumed, ledger_path=ledger,
                    strict_corpus_review_path=corpus,
                    strict_corpus_review_sha256=corpus_hash,
                )
                strict_path = base / dispatcher.STRICT_REVALIDATION_RELATIVE
                _write_json(strict_path, strict)
                strict_bytes = strict_path.read_bytes()
                state_paths = (
                    ledger, *dispatcher._state_paths(ledger),
                    dispatcher._append_journal_path(ledger),
                )
                before_failed_cutover = {
                    path: path.read_bytes() for path in state_paths if path.exists()
                }
                real_validate = dispatcher._validate_legacy_strict_revalidation

                def swap_after_validation(*args, **kwargs):
                    value = real_validate(*args, **kwargs)
                    strict_path.write_bytes(strict_bytes + b"\n")
                    return value

                with mock.patch.object(
                    dispatcher, "_validate_legacy_strict_revalidation",
                    side_effect=swap_after_validation,
                ):
                    with self.assertRaises(dispatcher.NoveltyIntegrityError):
                        dispatcher.record_strict_revalidation(
                            receipt_path=dispatcher.STRICT_REVALIDATION_RELATIVE,
                            receipt_sha256=_sha(strict_path), ledger_path=ledger,
                        )
                self.assertEqual(
                    before_failed_cutover,
                    {path: path.read_bytes() for path in before_failed_cutover},
                )
                strict_path.write_bytes(strict_bytes)
                anchors = dispatcher.record_strict_revalidation(
                    receipt_path=dispatcher.STRICT_REVALIDATION_RELATIVE,
                    receipt_sha256=_sha(strict_path), ledger_path=ledger,
                )
                self.assertEqual(
                    ["LEGACY_CONSUMPTION_RECLASSIFIED"],
                    [row["event"] for row in anchors],
                )
                anchored_ledger = ledger.read_bytes()
                repeated = dispatcher.record_strict_revalidation(
                    receipt_path=dispatcher.STRICT_REVALIDATION_RELATIVE,
                    receipt_sha256=_sha(strict_path), ledger_path=ledger,
                )
                self.assertEqual(
                    ["LEGACY_CONSUMPTION_RECLASSIFIED"],
                    [row["event"] for row in repeated],
                )
                self.assertEqual(anchored_ledger, ledger.read_bytes())
                first_retirement = dispatcher.retire_request_inventory(ledger, inbox)
                self.assertEqual("PASS_EMPTY", first_retirement["state"])

                # Mutable live corpus can advance and the ledger can be extended;
                # terminal proof remains tied to its immutable snapshot and prefix.
                manifest = base / ".system_control/content_manifest.json"
                manifest.write_bytes(manifest.read_bytes() + b"\n")
                with dispatcher._claim_lock(ledger):
                    rows = dispatcher.read_consumed_ledger(ledger)
                    dispatcher._append_events_atomic(ledger, rows, [{
                        "event": "CONSUMED",
                        "family_id": "historical-extension",
                        "topic": "Later historical ledger extension",
                        "topic_sha256": dispatcher.topic_sha256(
                            "Later historical ledger extension"
                        ),
                        "consumer": "test-historical-extension",
                        "request_id": dispatcher.HISTORICAL_REQUEST_ID,
                        "line_number": 99,
                        "historical": True,
                        "corpus_review_receipt": "",
                        "corpus_review_sha256": "",
                        "fulfilment_receipt": "",
                        "fulfilment_sha256": "",
                    }])
                self.assertEqual(
                    "PASS", dispatcher.validate_consumed_evidence(ledger)["state"]
                )
                self.assertEqual(
                    "PASS_EMPTY", dispatcher.retire_request_inventory(ledger, inbox)["state"]
                )

                # Historical verification resolves the hash-anchored strict
                # receipt snapshot.  Live receipt/engine upgrades are inert,
                # while any archived byte drift is fail closed.
                strict_bytes = strict_path.read_bytes()
                strict_hash = _sha(strict_path)
                strict_snapshot = dispatcher._strict_receipt_snapshot_path(strict_hash)
                archived_bytes = strict_snapshot.read_bytes()
                for target in ("nested_pack", "audit_engine"):
                    with self.subTest(strict_tamper=target):
                        broken = json.loads(archived_bytes.decode("utf-8"))
                        if target == "nested_pack":
                            broken["pack"]["unexpected"] = "fabricated"
                        else:
                            broken["audit_engine"]["sha256"] = "0" * 64
                        _write_json(strict_snapshot, broken)
                        with self.assertRaises(dispatcher.NoveltyIntegrityError):
                            dispatcher.validate_consumed_evidence(ledger)
                        strict_snapshot.write_bytes(archived_bytes)

                broken = json.loads(archived_bytes.decode("utf-8"))
                broken["ledger"]["prefix_head"] = "0" * 64
                _write_json(strict_snapshot, broken)
                with self.assertRaises(dispatcher.NoveltyIntegrityError):
                    dispatcher.validate_consumed_evidence(ledger)
                strict_snapshot.write_bytes(archived_bytes)

                broken_live = json.loads(strict_bytes.decode("utf-8"))
                broken_live["pack"]["unexpected"] = "live-file-is-not-history"
                _write_json(strict_path, broken_live)
                self.assertEqual(
                    "PASS", dispatcher.validate_consumed_evidence(ledger)["state"]
                )
                strict_path.write_bytes(strict_bytes)
                live_engine = base / "pipeline/content_pack_audit.py"
                live_engine_bytes = live_engine.read_bytes()
                live_engine.write_bytes(live_engine_bytes + b"\n# harmless future engine\n")
                self.assertEqual(
                    "PASS", dispatcher.validate_consumed_evidence(ledger)["state"]
                )
                live_engine.write_bytes(live_engine_bytes)

                snapshot_manifest, _payloads = dispatcher._load_consumption_snapshot(
                    legacy_hash
                )
                snapshot_dir = (
                    base / dispatcher._snapshot_relative(legacy_hash)
                ).parent
                for role in ("fulfilment_receipt", "candidate_pack"):
                    with self.subTest(snapshot_role=role):
                        record = next(
                            item for item in snapshot_manifest["artifacts"]
                            if item["role"] == role
                        )
                        blob = snapshot_dir / record["blob"]
                        original = blob.read_bytes()
                        blob.write_bytes(original + b"tamper")
                        with self.assertRaises(dispatcher.NoveltyIntegrityError):
                            dispatcher.validate_consumed_evidence(ledger)
                        blob.write_bytes(original)
                self.assertEqual(
                    "PASS", dispatcher.validate_consumed_evidence(ledger)["state"]
                )


if __name__ == "__main__":
    unittest.main(verbosity=2)
