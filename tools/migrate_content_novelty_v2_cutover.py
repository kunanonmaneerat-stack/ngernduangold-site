"""One-shot local migration for the 2026-08-25 blocked V2 draft evidence.

The command verifies immutable pre-cutover anchors, recomputes the corpus twice,
runs the exact migration first in a temporary clone, then applies the same
review/order/strict-receipt bytes to production.  It never grants publication
authority and has no network, scheduler, post, deploy, or notification path.
"""

from __future__ import annotations

import argparse
import contextlib
import datetime
import hashlib
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile


ROOT = Path(__file__).resolve().parents[1]
PIPELINE = ROOT / "pipeline"
if str(PIPELINE) not in sys.path:
    sys.path.insert(0, str(PIPELINE))

import dispatcher  # noqa: E402


EXPECTED_HASHES = {
    "pipeline/content_pack_audit.py": "1BF3036D108F25769C25DD2BBF1BF674DC6973FCB19287980C6CBD5A9BAAB6DE",
    "pipeline/dispatcher.py": "0A21F2A7A4DAA7FAF75DF3DFFED8E192AB9861C2F59D03D4EDB3FF8B5EFF68FB",
    "pipeline/daily_content.py": "7CC08AFAEE8EE0379B566295BCADAD816EBCF68BEB128F7088EC632E1D9E1B2E",
    "pipeline/request_retirement.py": "277BD2D335A31ABB20EB0CEA2CEEFE81430039F21B3F14A15D2A505370C6623E",
    "automation-log/orders.txt": "508B1F3C7A2E8042571A40CE74BCFD2895F6B1CF497CAB9A23AE17E7D9FA3093",
    "automation-log/dedup-evidence/LOCAL-CONTENT-PACK_20260825_V2-CORPUS-REVIEW.json": "A3760DEA1AB1C8BDE867279073D38CE2D18AF0F8895E430EBF2DA35962EA7CD3",
    "automation-log/dedup-evidence/LOCAL-CONTENT-PACK_20260825_V2-DRAFT-FULFILMENT.json": "40BA011556AFE9B67310709037427840C33C54F2835DC4EA7324F5CF9968E9CD",
    "automation-log/cc-outbox/LOCAL-CONTENT-PACK_20260825_V2.md": "B871E8BA08BD5BD5A5CB64F0E3ABBD95D888AF86BE1B78E0E944AFC58951DE85",
    "automation-log/_retired-generation/manifest.json": "0D3BDB7914BD1B0F8D39E71DF8754306E3DE284F48E2467DC0954A3FA8773DFC",
    ".local-private/runtime/content-novelty/topic-lifecycle-ledger.jsonl": "71DA76225908A9FC924D503E2464FC0A4BE38790D385D1AFE9EDF69DF415B6E0",
    ".local-private/runtime/content-novelty/topic-lifecycle-ledger.jsonl.activated.json": "23B0265516E108F4EF122ABD0593F4D0DE6642F1F3D658727B9BE2B1D251BCA1",
    ".local-private/runtime/content-novelty/topic-lifecycle-ledger.jsonl.checkpoint.json": "17084083694ADF81B6008AE71CAB029B290FCA6F5A57C8186B5B0C517ACB85C7",
}
EXPECTED_HEAD = "9ED077BDE6BBA7FE66E550EAD89D476E74654C914216BA5BC7553F5DCA6E0A4D"
REVIEW_RELATIVE = (
    "automation-log/dedup-evidence/"
    "LOCAL-CONTENT-PACK_20260825_V2-CORPUS-REVIEW-V2.json"
)
CANDIDATE_RELATIVE = "automation-log/cc-outbox/LOCAL-CONTENT-PACK_20260825_V2.md"
OLD_REVIEW_RELATIVE = (
    "automation-log/dedup-evidence/"
    "LOCAL-CONTENT-PACK_20260825_V2-CORPUS-REVIEW.json"
)
FULFILMENT_SHA = "40BA011556AFE9B67310709037427840C33C54F2835DC4EA7324F5CF9968E9CD"


def _sha_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest().upper()


def _sha_file(path: Path) -> str:
    return _sha_bytes(path.read_bytes())


def _json_bytes(payload: dict) -> bytes:
    return (
        json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
    ).encode("utf-8")


@contextlib.contextmanager
def _dispatcher_root(root: Path):
    names = ("ROOT", "DEFAULT_ORDERS", "DEFAULT_INBOX", "DEFAULT_LEDGER")
    saved = {name: getattr(dispatcher, name) for name in names}
    dispatcher.ROOT = root
    dispatcher.DEFAULT_ORDERS = root / "automation-log" / "orders.txt"
    dispatcher.DEFAULT_INBOX = root / "automation-log" / "cowork-inbox"
    dispatcher.DEFAULT_LEDGER = (
        root / ".local-private" / "runtime" / "content-novelty"
        / "topic-lifecycle-ledger.jsonl"
    )
    try:
        yield
    finally:
        for name, value in saved.items():
            setattr(dispatcher, name, value)


def _assert_preflight(root: Path, *, hashes: bool) -> None:
    if hashes:
        for relative, expected in EXPECTED_HASHES.items():
            path = root / relative
            if not path.is_file() or _sha_file(path) != expected:
                raise dispatcher.NoveltyIntegrityError(
                    "pre-cutover anchor drift: " + relative
                )
    ledger = (
        root / ".local-private" / "runtime" / "content-novelty"
        / "topic-lifecycle-ledger.jsonl"
    )
    journal = dispatcher._append_journal_path(ledger)
    if journal.exists():
        raise dispatcher.NoveltyIntegrityError("pre-cutover append journal exists")
    if (root / REVIEW_RELATIVE).exists() or (
        root / dispatcher.STRICT_REVALIDATION_RELATIVE
    ).exists():
        raise dispatcher.NoveltyIntegrityError("pre-cutover v2 evidence already exists")
    if (root / dispatcher._snapshot_relative(FULFILMENT_SHA)).exists():
        raise dispatcher.NoveltyIntegrityError("pre-cutover evidence snapshot already exists")
    with _dispatcher_root(root):
        with dispatcher._claim_lock(ledger):
            rows = dispatcher.read_consumed_ledger(ledger)
            if len(rows) != 21 or rows[-1]["record_hash"] != EXPECTED_HEAD:
                raise dispatcher.NoveltyIntegrityError(
                    "pre-cutover ledger sequence/head drifted"
                )
            if [
                row["sequence"] for row in rows
                if row["event"] == "CONSUMED" and not row["historical"]
            ] != list(range(15, 22)):
                raise dispatcher.NoveltyIntegrityError(
                    "pre-cutover legacy consumed set drifted"
                )


def _active_rows_from_orders(payload: bytes) -> list[dict]:
    rows = []
    for line_number, raw in enumerate(payload.decode("utf-8-sig").splitlines(), 1):
        stripped = raw.strip()
        if stripped and not stripped.startswith("#"):
            rows.append(
                dispatcher._parse_order_line(stripped, line_number, historical=False)
            )
    if len(rows) != 7:
        raise dispatcher.NoveltyIntegrityError("expected exactly seven active orders")
    return rows


def _orders_v2_bytes(original: bytes, review_sha: str) -> bytes:
    text = original.decode("utf-8")
    lines = text.splitlines(keepends=True)
    changed = 0
    out = []
    for raw in lines:
        ending = "\r\n" if raw.endswith("\r\n") else "\n" if raw.endswith("\n") else ""
        body = raw[:-len(ending)] if ending else raw
        stripped = body.strip()
        if stripped and not stripped.startswith("#"):
            fields = body.split("\t")
            if len(fields) != 4:
                raise dispatcher.NoveltyIntegrityError("active order field count drifted")
            body = "\t".join((fields[0], fields[1], REVIEW_RELATIVE, review_sha))
            changed += 1
        out.append(body + ending)
    if changed != 7:
        raise dispatcher.NoveltyIntegrityError("did not update exactly seven active rows")
    return "".join(out).encode("utf-8")


def _build_review_bytes(created_at: str) -> tuple[bytes, bytes]:
    orders_path = ROOT / "automation-log" / "orders.txt"
    original_orders = orders_path.read_bytes()
    families = _active_rows_from_orders(original_orders)
    with _dispatcher_root(ROOT):
        runs = []
        for _index in range(2):
            runtime = dispatcher._load_bound_audit_engine(
                label="migration corpus audit engine"
            )
            corpus, inputs = dispatcher._capture_corpus_bytes(CANDIDATE_RELATIVE)
            module = runtime["module"]
            try:
                audit = module.audit_topics(
                    ROOT, CANDIDATE_RELATIVE, families, corpus
                )
            except module.ContentPackAuditError as exc:
                raise dispatcher.NoveltyIntegrityError(
                    "migration corpus audit failed: " + str(exc)
                ) from exc
            dispatcher._recheck_bound_audit_engine(
                runtime, label="migration corpus audit engine"
            )
            runs.append((corpus, inputs, audit))
        if runs[0] != runs[1]:
            raise dispatcher.NoveltyIntegrityError(
                "two current corpus recomputations are not byte-identical"
            )
    audit_keys = (
        "topic_candidates", "topic_baseline_records",
        "historical_exact_collisions", "historical_near_collisions",
        "cross_family_exact_collisions", "cross_family_near_collisions",
    )
    audit = {key: runs[0][2][key] for key in audit_keys}
    if audit["topic_candidates"] != 7 or any(
        audit[key] != 0 for key in audit_keys[2:]
    ):
        raise dispatcher.NoveltyIntegrityError("current corpus review is not clean")
    review = {
        "schema_version": dispatcher.CORPUS_REVIEW_SCHEMA_VERSION,
        "receipt_type": dispatcher.CORPUS_REVIEW_RECEIPT_TYPE,
        "producer": dispatcher.CORPUS_REVIEW_PRODUCER,
        "method": dispatcher.CORPUS_REVIEW_METHOD,
        "review_state": "PROVISIONAL_LOCAL_REVIEW",
        "semantic_universality_claimed": False,
        "publication_authority": "NONE",
        "created_at": created_at,
        "method_limit": (
            "Local deterministic exact/near checks do not prove universal "
            "semantic novelty."
        ),
        "candidate_path": CANDIDATE_RELATIVE,
        "families": [{
            "family_id": row["family_id"], "topic": row["topic"],
            "topic_sha256": row["topic_sha256"],
        } for row in families],
        "corpus_inputs": runs[0][1],
        "corpus_audit": audit,
        "explicit_non_authority": (
            "Provisional local corpus review only; no source, claim, media, "
            "schedule, release, or publication authority."
        ),
    }
    review_bytes = _json_bytes(review)
    return review_bytes, _orders_v2_bytes(original_orders, _sha_bytes(review_bytes))


def _inventory(root: Path) -> dict[str, str]:
    roots = (
        root / "automation-log" / "cowork-inbox",
        root / "automation-log" / "_retired-generation",
    )
    result = {}
    for base in roots:
        if base.is_dir():
            for path in sorted(item for item in base.rglob("*") if item.is_file()):
                result[path.relative_to(root).as_posix()] = _sha_file(path)
    return result


def _apply(
    root: Path, review_bytes: bytes, orders_bytes: bytes,
    *, expected_strict_bytes: bytes | None,
) -> tuple[dict, bytes]:
    with _dispatcher_root(root):
        review_path = root / REVIEW_RELATIVE
        orders_path = root / "automation-log" / "orders.txt"
        dispatcher._atomic_write(review_path, review_bytes)
        dispatcher._atomic_write(orders_path, orders_bytes)
        active, historical = dispatcher.load_order_registry(orders_path)
        if len(active) != 7 or len(historical) != 7:
            raise dispatcher.NoveltyIntegrityError("migrated registry count is invalid")
        dispatcher._validate_review_receipt(active, recompute_current_audit=True)
        ledger = dispatcher.DEFAULT_LEDGER
        # The public builder intentionally remains non-mutating but does not yet
        # compare arbitrary caller-supplied row dictionaries with the ledger.
        # Release therefore derives and proves the exact full seq15-21 rows
        # inside the same lifecycle lock used by the internal builder.
        with dispatcher._claim_lock(ledger):
            rows = dispatcher.read_consumed_ledger(ledger)
            consumed = [
                row for row in rows
                if row["event"] == "CONSUMED" and not row["historical"]
            ]
            if (
                [row["sequence"] for row in consumed] != list(range(15, 22))
                or consumed != rows[14:21]
                or any(
                    row["record_hash"] != rows[row["sequence"] - 1]["record_hash"]
                    or row != rows[row["sequence"] - 1]
                    for row in consumed
                )
            ):
                raise dispatcher.NoveltyIntegrityError(
                    "strict cutover exact source rows drifted"
                )
            strict_payload = dispatcher._strict_revalidation_payload_locked(
                consumed, ledger_path=ledger,
                strict_corpus_review_path=REVIEW_RELATIVE,
                strict_corpus_review_sha256=_sha_bytes(review_bytes),
            )
        strict_bytes = _json_bytes(strict_payload)
        if expected_strict_bytes is not None and strict_bytes != expected_strict_bytes:
            raise dispatcher.NoveltyIntegrityError(
                "production strict receipt differs from exact dry-run bytes"
            )
        strict_path = root / dispatcher.STRICT_REVALIDATION_RELATIVE
        dispatcher._atomic_write(strict_path, strict_bytes)
        anchors = dispatcher.record_strict_revalidation(
            receipt_path=dispatcher.STRICT_REVALIDATION_RELATIVE,
            receipt_sha256=_sha_bytes(strict_bytes), ledger_path=ledger,
        )
        if len(anchors) != 7 or any(
            row["event"] != "LEGACY_CONSUMPTION_RECLASSIFIED" for row in anchors
        ):
            raise dispatcher.NoveltyIntegrityError("cutover did not append seven anchors")
        rows = dispatcher.read_consumed_ledger(ledger)
        if len(rows) != 28 or [row["sequence"] for row in anchors] != list(range(22, 29)):
            raise dispatcher.NoveltyIntegrityError("post-cutover ledger sequence is invalid")
        evidence = dispatcher.validate_consumed_evidence(ledger)
        expected_evidence = {
            "state": "PASS", "consumed": 0, "drafted_blocked": 7,
            "legacy_reclassified": 7,
        }
        if evidence != expected_evidence:
            raise dispatcher.NoveltyIntegrityError(
                "post-cutover evidence summary differs: " + repr(evidence)
            )
        before_retirement = _inventory(root)
        first = dispatcher.retire_request_inventory(ledger, dispatcher.DEFAULT_INBOX)
        after_first = _inventory(root)
        second = dispatcher.retire_request_inventory(ledger, dispatcher.DEFAULT_INBOX)
        after_second = _inventory(root)
        if (
            first.get("state") not in {"PASS", "PASS_EMPTY"}
            or second != first
            or after_first != after_second
            or before_retirement != after_first
        ):
            raise dispatcher.NoveltyIntegrityError(
                "retirement inventory/tombstones are not byte-idempotent"
            )
        return {
            "review_sha256": _sha_bytes(review_bytes),
            "orders_sha256": _sha_bytes(orders_bytes),
            "strict_sha256": _sha_bytes(strict_bytes),
            "ledger_sha256": _sha_file(ledger),
            "ledger_head": rows[-1]["record_hash"],
            "snapshot_manifest_sha256": _sha_file(
                root / dispatcher._snapshot_relative(FULFILMENT_SHA)
            ),
            "strict_snapshot_sha256": _sha_file(
                dispatcher._strict_receipt_snapshot_path(_sha_bytes(strict_bytes))
            ),
            "evidence": evidence,
            "retirement": first,
        }, strict_bytes


def _copy_dry_root(target: Path) -> None:
    file_paths = (
        ".system_control/content_manifest.json",
        ".system_control/content_calendar.json",
        "automation-log/post-ledger.jsonl",
        "automation-log/orders.txt",
        "pipeline/content_pack_audit.py",
    )
    dir_paths = (
        "automation-log/content-packages",
        "automation-log/cc-outbox",
        "automation-log/dedup-evidence",
        "automation-log/cowork-inbox",
        "automation-log/_retired-generation",
        ".local-private/runtime/content-novelty",
    )
    for relative in file_paths:
        destination = target / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / relative, destination)
    for relative in dir_paths:
        shutil.copytree(ROOT / relative, target / relative)
    # Activation/checkpoint state_id intentionally binds the absolute ledger
    # path.  Rebase only those two temp-clone identities; ledger bytes/head stay
    # exact so the dry strict receipt remains production-comparable.
    with _dispatcher_root(target):
        ledger = dispatcher.DEFAULT_LEDGER
        sentinel_path, checkpoint_path = dispatcher._state_paths(ledger)
        state_id = dispatcher._state_id(ledger)
        sentinel = json.loads(sentinel_path.read_text(encoding="utf-8"))
        checkpoint = json.loads(checkpoint_path.read_text(encoding="utf-8"))
        sentinel["state_id"] = state_id
        checkpoint["state_id"] = state_id
        dispatcher._atomic_write(
            sentinel_path,
            (dispatcher._canonical_json(sentinel) + "\n").encode("utf-8"),
        )
        dispatcher._atomic_write(
            checkpoint_path,
            (dispatcher._canonical_json(checkpoint) + "\n").encode("utf-8"),
        )


def _safe_rollback(original_orders: bytes, strict_sha: str | None) -> None:
    ledger = dispatcher.DEFAULT_LEDGER
    try:
        rows = dispatcher.read_consumed_ledger(ledger)
    except dispatcher.NoveltyError:
        return
    if len(rows) != 21 or rows[-1]["record_hash"] != EXPECTED_HEAD:
        return
    dispatcher._atomic_write(ROOT / "automation-log/orders.txt", original_orders)
    exact_files = (ROOT / REVIEW_RELATIVE, ROOT / dispatcher.STRICT_REVALIDATION_RELATIVE)
    strict_path = ROOT / dispatcher.STRICT_REVALIDATION_RELATIVE
    if strict_sha is None and strict_path.is_file():
        strict_sha = _sha_file(strict_path)
    for path in exact_files:
        if path.is_file():
            path.unlink()
    evidence_dir = (ROOT / dispatcher._snapshot_relative(FULFILMENT_SHA)).parent
    if evidence_dir.is_dir():
        evidence_dir.resolve().relative_to(ROOT.resolve())
        shutil.rmtree(evidence_dir)
    if strict_sha:
        strict_dir = dispatcher._strict_receipt_snapshot_path(strict_sha).parent
        if strict_dir.is_dir():
            strict_dir.resolve().relative_to(ROOT.resolve())
            shutil.rmtree(strict_dir)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    _assert_preflight(ROOT, hashes=True)
    created_at = datetime.datetime.now(
        datetime.timezone(datetime.timedelta(hours=7))
    ).replace(microsecond=0).isoformat()
    review_bytes, orders_bytes = _build_review_bytes(created_at)
    with tempfile.TemporaryDirectory(prefix="ngernduangold-v2-cutover-") as raw:
        dry_root = Path(raw)
        _copy_dry_root(dry_root)
        _assert_preflight(dry_root, hashes=False)
        dry_result, strict_bytes = _apply(
            dry_root, review_bytes, orders_bytes, expected_strict_bytes=None
        )
    print("DRY_RUN_PASS=" + json.dumps(dry_result, ensure_ascii=False, sort_keys=True))
    if not args.execute:
        print("PRODUCTION_NOT_MUTATED=1")
        return 0
    original_orders = (ROOT / "automation-log/orders.txt").read_bytes()
    strict_sha = None
    try:
        _assert_preflight(ROOT, hashes=True)
        result, production_strict = _apply(
            ROOT, review_bytes, orders_bytes, expected_strict_bytes=strict_bytes
        )
        strict_sha = _sha_bytes(production_strict)
    except Exception:
        _safe_rollback(original_orders, strict_sha)
        raise
    print("PRODUCTION_MIGRATION_PASS=" + json.dumps(
        result, ensure_ascii=False, sort_keys=True
    ))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
