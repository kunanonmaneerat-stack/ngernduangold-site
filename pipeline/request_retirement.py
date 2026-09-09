"""Fail-closed retirement for local generation-request inbox artifacts.

Only the root of ``automation-log/cowork-inbox`` is scanned, and only the
three request/reference filename families named in ``REQUEST_PATTERNS``.
Retirement never deletes evidence: exact original bytes are copied to a
content-addressed archive outside the active inbox, a hash-bound manifest is
written, and the original active path becomes an explicit non-actionable
tombstone.

This module has no network, model, notification, publication, deployment, or
scheduler mutation path.
"""

from __future__ import annotations

from collections import defaultdict
from pathlib import Path
import re


ROOT = Path(__file__).resolve().parent.parent
DEFAULT_INBOX = ROOT / "automation-log" / "cowork-inbox"
DEFAULT_ARCHIVE = ROOT / "automation-log" / "_retired-generation"
MANIFEST_NAME = "manifest.json"
MANIFEST_TYPE = "GENERATION_REQUEST_RETIREMENT_MANIFEST"
TOMBSTONE_STATE = "DRAFTED_BLOCKED_DO_NOT_GENERATE"
LEGACY_TOMBSTONE_STATE = "FULFILLED_OR_HISTORICAL_DO_NOT_GENERATE"
REQUEST_PATTERNS = (
    "generation-request*.md",
    "generation-reference*.md",
    "daily-generation-request*.md",
    "daily-reference*.md",
)
CURRENT_REQUEST_RE = re.compile(
    r"^(generation-request|daily-generation-request)-(\d{4}-\d{2}-\d{2})"
    r"-novelty-v3\.md$"
)
CURRENT_REFERENCE_RE = re.compile(
    r"^daily-reference-(\d{4}-\d{2}-\d{2})-novelty-v3\.md$"
)
CURRENT_GENERATION_REFERENCE_RE = re.compile(
    r"^generation-reference-(\d{4}-\d{2}-\d{2})-novelty-v3\.md$"
)
TOMBSTONE_PREFIX = ("# " + TOMBSTONE_STATE + "\n").encode("utf-8")
LEGACY_TOMBSTONE_PREFIX = (
    "# " + LEGACY_TOMBSTONE_STATE + "\n"
).encode("utf-8")
RECORD_KEYS = {
    "original_path", "archive_path", "sha256", "size", "state", "reason",
    "ledger_head", "ledger_sha256", "topic_sha256s", "request_id",
}
MANIFEST_KEYS = {
    "schema_version", "manifest_type", "records", "self_sha256",
}
RETIREMENT_STATES = {
    "DRAFTED_BLOCKED_DO_NOT_GENERATE",
    # Read-only compatibility for manifests created before the safe lifecycle
    # cutover.  No code path in this module creates this state any longer.
    "FULFILLED_DO_NOT_GENERATE",
    "HISTORICAL_CONSUMED_DO_NOT_GENERATE",
}


class RequestRetirementError(RuntimeError):
    """An inbox request cannot be proven active or safely retired."""


def _relative(path: Path, root: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError as exc:
        raise RequestRetirementError("request-retirement path escapes repository") from exc


def _manifest_bytes(records: list[dict], engine) -> bytes:
    body = {
        "schema_version": 1,
        "manifest_type": MANIFEST_TYPE,
        "records": sorted(records, key=lambda row: row["original_path"]),
    }
    payload = dict(
        body,
        self_sha256=engine._sha256_bytes(
            engine._canonical_json(body).encode("utf-8")
        ),
    )
    return (engine._canonical_json(payload) + "\n").encode("utf-8")


def _validate_record_shape(record: dict, engine) -> None:
    if not isinstance(record, dict) or set(record) != RECORD_KEYS:
        raise RequestRetirementError("retirement manifest record schema is invalid")
    if (
        not isinstance(record["original_path"], str)
        or not isinstance(record["archive_path"], str)
        or not engine.SHA256_RE.fullmatch(str(record["sha256"]))
        or not isinstance(record["size"], int)
        or record["size"] < 1
        or record["state"] not in RETIREMENT_STATES
        or not isinstance(record["reason"], str)
        or not record["reason"]
        or not engine.SHA256_RE.fullmatch(str(record["ledger_head"]))
        or not engine.SHA256_RE.fullmatch(str(record["ledger_sha256"]))
        or not isinstance(record["topic_sha256s"], list)
        or not all(engine.SHA256_RE.fullmatch(str(item)) for item in record["topic_sha256s"])
        or record["topic_sha256s"] != sorted(set(record["topic_sha256s"]))
        or not isinstance(record["request_id"], str)
    ):
        raise RequestRetirementError("retirement manifest record values are invalid")


def _load_manifest(archive: Path, engine) -> list[dict]:
    path = archive / MANIFEST_NAME
    if not path.exists():
        return []
    try:
        payload = engine._load_json(path)
    except Exception as exc:
        raise RequestRetirementError("retirement manifest is unreadable") from exc
    if set(payload) != MANIFEST_KEYS:
        raise RequestRetirementError("retirement manifest top-level schema is invalid")
    body = {key: payload[key] for key in payload if key != "self_sha256"}
    expected = engine._sha256_bytes(
        engine._canonical_json(body).encode("utf-8")
    )
    if (
        payload.get("schema_version") != 1
        or payload.get("manifest_type") != MANIFEST_TYPE
        or payload.get("self_sha256") != expected
        or not isinstance(payload.get("records"), list)
    ):
        raise RequestRetirementError("retirement manifest hash or identity is invalid")
    records = payload["records"]
    paths = set()
    for record in records:
        _validate_record_shape(record, engine)
        if record["original_path"] in paths:
            raise RequestRetirementError("retirement manifest repeats an active path")
        paths.add(record["original_path"])
    if records != sorted(records, key=lambda row: row["original_path"]):
        raise RequestRetirementError("retirement manifest records are not canonical")
    if path.read_bytes() != _manifest_bytes(records, engine):
        raise RequestRetirementError("retirement manifest bytes are non-canonical")
    return records


def _scan(inbox: Path) -> list[Path]:
    paths = set()
    for pattern in REQUEST_PATTERNS:
        paths.update(path for path in inbox.glob(pattern) if path.is_file())
    return sorted(paths, key=lambda path: path.name.casefold())


def _ledger_view(rows: list[dict], engine) -> dict:
    reserved, consumed, outstanding = engine._lifecycle(rows)
    drafted = engine._drafted_map(rows)
    by_request = defaultdict(list)
    # One family can gain REVIEW_REFRESHED records.  Request identity and
    # retirement must bind the latest outstanding/reserved lifecycle row, not
    # the superseded original review hash.
    for row in reserved.values():
        by_request[row["request_id"]].append(row)
    return {
        "reserved": reserved,
        "drafted": drafted,
        "consumed": consumed,
        "outstanding": outstanding,
        "by_request": by_request,
        "historical_by_topic": {
            row["topic_sha256"]: row
            for row in rows if row["historical"] and row["event"] == "CONSUMED"
        },
    }


def _all_request_rows_consumed(request_rows: list[dict], view: dict) -> bool:
    return bool(request_rows) and all(
        row["family_id"] in view["consumed"] for row in request_rows
    )


def _all_request_rows_drafted(request_rows: list[dict], view: dict) -> bool:
    """Return true only when every reserved family is effectively draft-blocked.

    ``engine._drafted_map`` includes both native ``DRAFTED_BLOCKED`` rows and
    legacy mechanical ``CONSUMED`` rows that have an append-only
    ``LEGACY_CONSUMPTION_RECLASSIFIED`` correction.  Neither case represents
    semantic approval or a permanent consumed decision.
    """
    return bool(request_rows) and all(
        row["family_id"] in view["drafted"] for row in request_rows
    )


def _all_request_rows_reclassified(request_rows: list[dict], view: dict) -> bool:
    """Recognize only the exact append-only correction of legacy consumption."""
    return bool(request_rows) and all(
        row["family_id"] in view["drafted"]
        and view["drafted"][row["family_id"]]["event"]
        == "LEGACY_CONSUMPTION_RECLASSIFIED"
        for row in request_rows
    )


def _drafted_reason(request_rows: list[dict], view: dict, *, reference: bool) -> str:
    reclassified = any(
        view["drafted"][row["family_id"]]["event"]
        == "LEGACY_CONSUMPTION_RECLASSIFIED"
        for row in request_rows
    )
    subject = "referenced request" if reference else "request"
    correction = (
        "; legacy mechanical consumption is append-only reclassified"
        if reclassified else ""
    )
    return (
        f"all {subject} families have terminal DRAFTED_BLOCKED lifecycle "
        "evidence and no outstanding reservation; generation is retired "
        "without semantic approval or CONSUMED status" + correction
    )


def _legacy_topics(payload: bytes) -> list[str] | None:
    try:
        text = payload.decode("utf-8-sig")
    except UnicodeError as exc:
        raise RequestRetirementError("legacy generation request is not valid UTF-8") from exc
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    if text.startswith("# DAILY LOCAL GENERATION REQUEST — "):
        matches = re.findall(r"(?m)^- topic: (.+)$", text)
        return matches if len(matches) == 1 else None
    if text.startswith("# LOCAL GENERATION REQUEST — ") and "\n## Topics\n" in text:
        section = text.split("\n## Topics\n", 1)[1]
        topics = re.findall(r"(?m)^- (.+)$", section)
        return topics or None
    return None


def _reference_request_id(payload: bytes) -> str:
    try:
        text = payload.decode("utf-8")
    except UnicodeError as exc:
        raise RequestRetirementError("daily reference is not valid UTF-8") from exc
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    match = re.search(r"(?m)^- referenced_request_id: (dispatcher|daily):(\d{4}-\d{2}-\d{2})$", text)
    return match.group(1) + ":" + match.group(2) if match else ""


def _classify_actionable(
    path: Path, payload: bytes, view: dict, inbox: Path, engine,
) -> dict:
    """Return ACTIVE or RETIRE classification, otherwise fail closed."""
    request_match = CURRENT_REQUEST_RE.fullmatch(path.name)
    if request_match:
        prefix, date = request_match.groups()
        request_id = ("dispatcher:" if prefix == "generation-request" else "daily:") + date
        request_rows = sorted(
            view["by_request"].get(request_id, []), key=lambda row: row["sequence"]
        )
        outstanding = [
            row for row in request_rows
            if row["family_id"] in view["outstanding"]
        ]
        if outstanding:
            title = (
                "LOCAL NOVELTY-GATED GENERATION REQUEST"
                if prefix == "generation-request"
                else "DAILY LOCAL NOVELTY-GATED GENERATION REQUEST"
            )
            expected = engine._request_bytes(
                date=date, request_id=request_id, rows=outstanding, title=title
            )
            if payload != expected:
                raise RequestRetirementError(
                    "active request bytes do not bind outstanding ledger records"
                )
            return {
                "action": "ACTIVE", "kind": "REQUEST", "request_id": request_id,
                "topic_sha256s": sorted(row["topic_sha256"] for row in outstanding),
            }
        if _all_request_rows_drafted(request_rows, view):
            return {
                "action": "RETIRE",
                "state": "DRAFTED_BLOCKED_DO_NOT_GENERATE",
                "reason": _drafted_reason(request_rows, view, reference=False),
                "request_id": request_id,
                "topic_sha256s": sorted(row["topic_sha256"] for row in request_rows),
            }
        if _all_request_rows_consumed(request_rows, view):
            raise RequestRetirementError(
                "current request has unreclassified CONSUMED lifecycle; "
                "DRAFTED_BLOCKED cutover evidence is required before retirement"
            )
        raise RequestRetirementError(
            "current actionable request has no matching outstanding or "
            "DRAFTED_BLOCKED lifecycle"
        )

    daily_reference_match = CURRENT_REFERENCE_RE.fullmatch(path.name)
    generation_reference_match = CURRENT_GENERATION_REFERENCE_RE.fullmatch(path.name)
    reference_match = daily_reference_match or generation_reference_match
    if reference_match:
        date = reference_match.group(1)
        referenced_id = _reference_request_id(payload)
        request_rows = sorted(
            view["by_request"].get(referenced_id, []), key=lambda row: row["sequence"]
        )
        outstanding = [
            row for row in request_rows
            if row["family_id"] in view["outstanding"]
        ]
        if outstanding:
            if daily_reference_match:
                own_request_id = "daily:" + date
                title = "DAILY LOCAL NOVELTY REFERENCE"
            else:
                own_request_id = "dispatcher:" + date
                title = "LOCAL NOVELTY OUTSTANDING REFERENCE"
            expected = engine._reference_bytes(
                date=date,
                request_id=own_request_id,
                rows=outstanding,
                referenced_path=engine._origin_request_path(outstanding, inbox),
                title=title,
            )
            if payload != expected:
                raise RequestRetirementError(
                    "reference bytes do not bind outstanding ledger records"
                )
            return {
                "action": "ACTIVE", "kind": "REFERENCE",
                "request_id": referenced_id,
                "topic_sha256s": sorted(row["topic_sha256"] for row in outstanding),
            }
        if _all_request_rows_drafted(request_rows, view):
            return {
                "action": "RETIRE",
                "state": "DRAFTED_BLOCKED_DO_NOT_GENERATE",
                "reason": _drafted_reason(request_rows, view, reference=True),
                "request_id": referenced_id,
                "topic_sha256s": sorted(row["topic_sha256"] for row in request_rows),
            }
        if _all_request_rows_consumed(request_rows, view):
            raise RequestRetirementError(
                "referenced request has unreclassified CONSUMED lifecycle; "
                "DRAFTED_BLOCKED cutover evidence is required before retirement"
            )
        raise RequestRetirementError(
            "reference has no matching outstanding or DRAFTED_BLOCKED lifecycle"
        )

    topics = _legacy_topics(payload)
    if topics is None:
        raise RequestRetirementError("unrecognized actionable generation artifact")
    topic_hashes = sorted({engine.topic_sha256(topic) for topic in topics})
    if len(topic_hashes) != len(topics):
        raise RequestRetirementError("legacy generation artifact repeats a normalized topic")
    if not all(value in view["historical_by_topic"] for value in topic_hashes):
        raise RequestRetirementError(
            "legacy generation artifact includes a topic not bound as historical CONSUMED"
        )
    return {
        "action": "RETIRE", "state": "HISTORICAL_CONSUMED_DO_NOT_GENERATE",
        "reason": "all topic hashes are bound to historical CONSUMED lifecycle rows",
        "request_id": "",
        "topic_sha256s": topic_hashes,
    }


def _archive_path(archive: Path, digest: str) -> Path:
    return archive / (digest + ".original")


def _make_record(
    path: Path, payload: bytes, classification: dict, *, archive: Path,
    ledger_path: Path, rows: list[dict], root: Path, engine,
) -> dict:
    digest = engine._sha256_bytes(payload)
    target = _archive_path(archive, digest)
    if target.exists():
        if target.read_bytes() != payload:
            raise RequestRetirementError("content-addressed retirement archive is mismatched")
    else:
        engine._atomic_write(target, payload)
    return {
        "original_path": _relative(path, root),
        "archive_path": _relative(target, root),
        "sha256": digest,
        "size": len(payload),
        "state": classification["state"],
        "reason": classification["reason"],
        "ledger_head": rows[-1]["record_hash"] if rows else engine.GENESIS_HASH,
        "ledger_sha256": engine._sha256_file(ledger_path),
        "topic_sha256s": classification["topic_sha256s"],
        "request_id": classification["request_id"],
    }


def _tombstone_bytes(record: dict, *, legacy_header: bool = False) -> bytes:
    tombstone_state = (
        LEGACY_TOMBSTONE_STATE if legacy_header else record["state"]
    )
    lines = [
        "# " + tombstone_state,
        "",
        "- state: " + tombstone_state,
        "- actionable: FALSE",
        "- instruction: DO_NOT_GENERATE_DO_NOT_QUEUE_DO_NOT_REFERENCE",
        "- retirement_state: " + record["state"],
        "- original_path: " + record["original_path"],
        "- original_sha256: " + record["sha256"],
        "- archive_path: " + record["archive_path"],
        "- request_id: " + (record["request_id"] or "NONE"),
        "- reason: " + record["reason"],
        "- ledger_head: " + record["ledger_head"],
        "- evidence_manifest: automation-log/_retired-generation/manifest.json",
        "- publication_authority: NONE",
        "",
        "This path is an evidence tombstone, not a generation request.",
    ]
    return ("\n".join(lines) + "\n").encode("utf-8")


def _looks_like_tombstone(payload: bytes) -> bool:
    prefixes = {
        ("# " + state + "\n").encode("utf-8")
        for state in RETIREMENT_STATES
    }
    prefixes.add(LEGACY_TOMBSTONE_PREFIX)
    return any(payload.startswith(prefix) for prefix in prefixes)


def _tombstone_matches_record(payload: bytes, record: dict) -> bool:
    if payload == _tombstone_bytes(record):
        return True
    # Compatibility is limited to pre-cutover records.  A drafted-blocked
    # record must always carry its explicit safe-lifecycle state in the title.
    return (
        record["state"] != "DRAFTED_BLOCKED_DO_NOT_GENERATE"
        and payload == _tombstone_bytes(record, legacy_header=True)
    )


def _validate_archive_record(
    record: dict, *, archive: Path, inbox: Path, view: dict, root: Path, engine,
) -> None:
    _validate_record_shape(record, engine)
    original = (root / record["original_path"]).resolve()
    archive_path = (root / record["archive_path"]).resolve()
    try:
        original.relative_to(inbox.resolve())
        archive_path.relative_to(archive.resolve())
    except ValueError as exc:
        raise RequestRetirementError("retirement record path is outside its allowed root") from exc
    if original.parent != inbox.resolve():
        raise RequestRetirementError("retirement record original path is not inbox-root scoped")
    if (
        not archive_path.is_file()
        or archive_path.name != record["sha256"] + ".original"
        or engine._sha256_file(archive_path) != record["sha256"]
        or archive_path.stat().st_size != record["size"]
    ):
        raise RequestRetirementError("retirement archive bytes do not match manifest")
    if record["state"] == "HISTORICAL_CONSUMED_DO_NOT_GENERATE":
        if not record["topic_sha256s"] or not all(
            value in view["historical_by_topic"] for value in record["topic_sha256s"]
        ):
            raise RequestRetirementError("retired legacy topics lack historical CONSUMED evidence")
    elif record["state"] == "DRAFTED_BLOCKED_DO_NOT_GENERATE":
        request_rows = view["by_request"].get(record["request_id"], [])
        if (
            not _all_request_rows_drafted(request_rows, view)
            or sorted(row["topic_sha256"] for row in request_rows)
            != record["topic_sha256s"]
        ):
            raise RequestRetirementError(
                "retired current request lacks terminal DRAFTED_BLOCKED evidence"
            )
    else:
        # Legacy manifest compatibility is deliberately validation-only.  A
        # newly observed raw CONSUMED lifecycle is not retired by this module.
        # After the append-only safe-lifecycle cutover, the old record remains
        # readable only when every one of its families has the exact legacy
        # reclassification event; native drafts cannot inherit an old
        # FULFILLED label.
        request_rows = view["by_request"].get(record["request_id"], [])
        if (
            not (
                _all_request_rows_consumed(request_rows, view)
                or _all_request_rows_reclassified(request_rows, view)
            )
            or sorted(row["topic_sha256"] for row in request_rows)
            != record["topic_sha256s"]
        ):
            raise RequestRetirementError(
                "retired legacy current request lacks terminal CONSUMED or "
                "exact reclassification evidence"
            )


def _validate_locked(
    rows: list[dict], *, ledger_path: Path, inbox: Path, archive: Path,
    records: list[dict], root: Path, engine,
) -> dict:
    view = _ledger_view(rows, engine)
    record_by_path = {row["original_path"]: row for row in records}
    for record in records:
        _validate_archive_record(
            record, archive=archive, inbox=inbox, view=view, root=root,
            engine=engine,
        )

    active_requests, active_references, tombstones = [], [], []
    present = set()
    for path in _scan(inbox):
        relative = _relative(path, root)
        present.add(relative)
        payload = path.read_bytes()
        if _looks_like_tombstone(payload):
            record = record_by_path.get(relative)
            if record is None or not _tombstone_matches_record(payload, record):
                raise RequestRetirementError("inbox retirement tombstone is unbound or tampered")
            tombstones.append(relative)
            continue
        if relative in record_by_path:
            raise RequestRetirementError("retired active path was overwritten with actionable bytes")
        classification = _classify_actionable(path, payload, view, inbox, engine)
        if classification["action"] != "ACTIVE":
            raise RequestRetirementError(
                "actionable request coexists with a terminal generation lifecycle state"
            )
        target = active_requests if classification["kind"] == "REQUEST" else active_references
        target.append({
            "path": relative,
            "sha256": engine._sha256_bytes(payload),
            "request_id": classification["request_id"],
        })

    missing_tombstones = sorted(set(record_by_path) - present)
    if missing_tombstones:
        raise RequestRetirementError("retired active-path tombstone is missing")
    outstanding_ids = {
        row["request_id"] for row in view["outstanding"].values()
    }
    active_ids = {row["request_id"] for row in active_requests}
    if active_ids != outstanding_ids:
        raise RequestRetirementError(
            "active request inventory does not exactly match outstanding ledger requests"
        )
    if not outstanding_ids and (active_requests or active_references):
        raise RequestRetirementError(
            "actionable request/reference exists while outstanding ledger count is zero"
        )
    return {
        "state": "PASS_ACTIVE" if outstanding_ids else "PASS_EMPTY",
        "outstanding": len(view["outstanding"]),
        "drafted_blocked": len(view["drafted"]),
        "active_requests": active_requests,
        "active_references": active_references,
        "tombstones": sorted(tombstones),
        "retired": len(records),
        "manifest": str(archive / MANIFEST_NAME),
        "manifest_sha256": engine._sha256_file(archive / MANIFEST_NAME),
        "ledger_sha256": engine._sha256_file(ledger_path),
        "ledger_head": rows[-1]["record_hash"] if rows else engine.GENESIS_HASH,
    }


def _retire_and_validate_locked(
    *, ledger: Path, inbox_path: Path, archive_path: Path, scope_root: Path,
    rows: list[dict], engine,
) -> dict:
    """Implementation for callers already holding ``engine._claim_lock``."""
    view = _ledger_view(rows, engine)
    records = _load_manifest(archive_path, engine)
    record_by_path = {row["original_path"]: row for row in records}
    replacements = []
    added = []

    for path in _scan(inbox_path):
        relative = _relative(path, scope_root)
        payload = path.read_bytes()
        if _looks_like_tombstone(payload):
            record = record_by_path.get(relative)
            if record is None or not _tombstone_matches_record(payload, record):
                raise RequestRetirementError(
                    "inbox retirement tombstone is unbound or tampered"
                )
            continue
        classification = _classify_actionable(
            path, payload, view, inbox_path, engine
        )
        if classification["action"] == "ACTIVE":
            if relative in record_by_path:
                raise RequestRetirementError(
                    "retired active path was reused for an actionable request"
                )
            continue
        existing = record_by_path.get(relative)
        digest = engine._sha256_bytes(payload)
        if existing is not None:
            if existing["sha256"] != digest:
                raise RequestRetirementError(
                    "retired active path was overwritten with different actionable bytes"
                )
            record = existing
        else:
            record = _make_record(
                path, payload, classification, archive=archive_path,
                ledger_path=ledger, rows=rows, root=scope_root,
                engine=engine,
            )
            records.append(record)
            record_by_path[relative] = record
            added.append(relative)
        replacements.append((path, record))

    manifest = archive_path / MANIFEST_NAME
    expected_manifest = _manifest_bytes(records, engine)
    if not manifest.exists() or manifest.read_bytes() != expected_manifest:
        engine._atomic_write(manifest, expected_manifest)
    for path, record in replacements:
        expected = _tombstone_bytes(record)
        if path.read_bytes() != expected:
            engine._atomic_write(path, expected)

    result = _validate_locked(
        rows, ledger_path=ledger, inbox=inbox_path,
        archive=archive_path, records=_load_manifest(archive_path, engine),
        root=scope_root, engine=engine,
    )
    result["newly_retired"] = sorted(added)
    return result


def retire_and_validate(
    ledger_path: str | Path,
    inbox: str | Path | None = None,
    archive: str | Path | None = None,
    root: str | Path | None = None,
    *,
    engine,
) -> dict:
    """Retire proven terminal generation artifacts, then validate inventory.

    Current requests retire at ``DRAFTED_BLOCKED_DO_NOT_GENERATE``.  This
    prevents duplicate generation while preserving that no semantic approval,
    owner decision, or permanent ``CONSUMED`` transition has occurred.
    """
    ledger = Path(ledger_path)
    scope_root = Path(root or ROOT).resolve()
    inbox_path = Path(inbox or DEFAULT_INBOX).resolve()
    archive_path = Path(archive or DEFAULT_ARCHIVE).resolve()
    for scoped in (inbox_path, archive_path):
        try:
            scoped.relative_to(scope_root)
        except ValueError as exc:
            raise RequestRetirementError(
                "request-retirement root does not contain inbox/archive"
            ) from exc
    inbox_path.mkdir(parents=True, exist_ok=True)
    archive_path.mkdir(parents=True, exist_ok=True)
    with engine._claim_lock(ledger):
        rows = engine.read_consumed_ledger(ledger)
        return _retire_and_validate_locked(
            ledger=ledger, inbox_path=inbox_path, archive_path=archive_path,
            scope_root=scope_root, rows=rows, engine=engine,
        )


def validate_inventory(
    ledger_path: str | Path,
    inbox: str | Path | None = None,
    archive: str | Path | None = None,
    root: str | Path | None = None,
    *,
    engine,
) -> dict:
    """Read-only validation; never creates archives, manifests, or tombstones."""
    ledger = Path(ledger_path)
    scope_root = Path(root or ROOT).resolve()
    inbox_path = Path(inbox or DEFAULT_INBOX).resolve()
    archive_path = Path(archive or DEFAULT_ARCHIVE).resolve()
    for scoped in (inbox_path, archive_path):
        try:
            scoped.relative_to(scope_root)
        except ValueError as exc:
            raise RequestRetirementError(
                "request-retirement root does not contain inbox/archive"
            ) from exc
    with engine._claim_lock(ledger):
        rows = engine.read_consumed_ledger(ledger)
        records = _load_manifest(archive_path, engine)
        if not (archive_path / MANIFEST_NAME).is_file():
            raise RequestRetirementError("request-retirement manifest is missing")
        return _validate_locked(
            rows, ledger_path=ledger, inbox=inbox_path,
            archive=archive_path, records=records, root=scope_root,
            engine=engine,
        )
