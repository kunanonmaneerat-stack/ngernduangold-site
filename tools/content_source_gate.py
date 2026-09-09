#!/usr/bin/env python3
"""Content-scoped publication gate for monitored official sources.

The global monitor intentionally remains strict across every source.  This module
answers the narrower publication question: are the sources mapped to one
``content_id`` fresh and explicitly free of unacknowledged change/error state?
"""
from dataclasses import dataclass
from datetime import date, datetime, timezone
import hashlib
import json
import math
from pathlib import Path
from urllib.parse import urlparse
import xml.etree.ElementTree as ET

try:
    from tools import source_review_receipt
except ImportError:  # Direct import when ``tools`` itself is on sys.path.
    import source_review_receipt


OFFICIAL_SNAPSHOT_SCHEMA = 3
SOURCE_REGISTRY_SCHEMA = 1
QUEUE_ATTESTATION_SCHEMA = 1
QUEUE_ATTESTATION_ALGORITHM = "sha256"
QUEUE_ATTESTATION_GENESIS = "GENESIS"
QUEUE_ATTESTATION_MAX_ENTRIES = 10000
REPO_CONTENT_SOURCE_CONTRACTS = (
    (("kn-",), "content-source-registry.json", "KNOWLEDGE-POSTS-C_20260816-0831.md"),
    (("p2-",), "page2-source-registry.json", "PAGE2-POSTS-B_20260818-0915.md"),
    (("b3-", "b4-", "tt-r14-"), "social-source-registry.json",
     "SOCIAL-CONTENT-BINDINGS_20260823"),
)
_SHA256_HEX = frozenset("0123456789abcdef")
RSS_CONTENT_TYPE_FALLBACK_METHOD = "rss-xml-root-v1"
RSS_CONTENT_TYPE_FALLBACK_ROOTS = frozenset({"rss", "feed"})
RSS_ABSENT_CONTENT_TYPE_PLACEHOLDER = "None"
_SUMMARY_FIELDS = {
    "configured_sources", "checked_sources", "successful_sources",
    "changed_this_run", "current_errors", "pending_owner_reviews",
    "acknowledged_this_run", "network_probe", "freshness_state",
}
_QUEUE_ENTRY_FIELDS = {
    "sequence", "checked_at", "configured_source_ids", "pending_ids",
    "acknowledged_ids", "mode", "previous_hash", "source_state_sha256",
    "entry_hash",
}


@dataclass(frozen=True)
class SourceGateResult:
    allowed: bool
    content_id: str
    source_ids: tuple[str, ...]
    failures: tuple[str, ...]


@dataclass(frozen=True)
class OfficialSnapshotResult:
    """Strict decision result for one exact set of official source IDs."""

    allowed: bool
    source_ids: tuple[str, ...]
    failures: tuple[str, ...]


def _canonical_sha256(value):
    encoded = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _valid_sha256(value):
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(char in _SHA256_HEX for char in value)
    )


def _strict_id_list(value, label, failures, *, allow_empty=True):
    if (
        not isinstance(value, list)
        or (not allow_empty and not value)
        or any(not isinstance(item, str) or not item.strip() for item in value)
    ):
        failures.append("%s is malformed" % label)
        return []
    normalized = [item.strip() for item in value]
    if len(normalized) != len(set(normalized)):
        failures.append("%s contains duplicates" % label)
    return normalized


def _aware_datetime(value, label, failures):
    if not isinstance(value, str) or not value.strip():
        failures.append("%s is unreadable" % label)
        return None
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        failures.append("%s is unreadable" % label)
        return None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        failures.append("%s must include a timezone" % label)
        return None
    return parsed


def _https_host(value):
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = urlparse(value.strip())
    except ValueError:
        return None
    if (
        parsed.scheme.casefold() != "https"
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
    ):
        return None
    return parsed.hostname.casefold()


def _content_type_matches(kind, content_type):
    media_type = str(content_type or "").split(";", 1)[0].strip().casefold()
    if kind == "html":
        return media_type in {"text/html", "application/xhtml+xml"}
    if kind == "pdf":
        return media_type == "application/pdf"
    if kind == "json":
        return media_type == "application/json" or media_type.endswith("+json")
    if kind == "rss":
        return media_type in {
            "application/rss+xml", "application/atom+xml", "application/xml",
            "text/xml",
        }
    return False


def rss_content_type_is_absent(content_type):
    """Recognize only transport values that explicitly mean no media type.

    Google currently returns the literal placeholder ``Content-Type: None``
    for its official Search updates RSS endpoint.  Treat that exact, trimmed
    value like a missing header, while rejecting other invalid or generic media
    types.  The RSS XML-root and raw-body hash checks remain mandatory.
    """
    return (
        content_type is None
        or (
            isinstance(content_type, str)
            and content_type.strip() in {"", RSS_ABSENT_CONTENT_TYPE_PLACEHOLDER}
        )
    )


def strict_rss_xml_root(body):
    """Return a safe RSS/Atom root name or raise ``ValueError``.

    This parser is only a narrow fallback for an absent HTTP Content-Type.  It
    deliberately rejects declarations that can define or expand entities and
    accepts only the document roots used by RSS and Atom feeds.
    """
    if not isinstance(body, (bytes, bytearray)) or not body:
        raise ValueError("RSS fallback body is missing or malformed")
    raw = bytes(body)
    upper = raw.upper()
    if b"<!DOCTYPE" in upper or b"<!ENTITY" in upper:
        raise ValueError("RSS fallback XML declarations are not allowed")
    try:
        root = ET.fromstring(raw)
    except (ET.ParseError, ValueError) as exc:
        raise ValueError("RSS fallback body is not well-formed XML") from exc
    if not isinstance(root.tag, str):
        raise ValueError("RSS fallback XML root is malformed")
    local_name = root.tag.rsplit("}", 1)[-1].rsplit(":", 1)[-1].casefold()
    if local_name not in RSS_CONTENT_TYPE_FALLBACK_ROOTS:
        raise ValueError("RSS fallback XML root is not rss or feed")
    return local_name


def build_rss_content_type_fallback_evidence(body):
    """Build persisted proof that an absent Content-Type body parsed as a feed."""
    raw = bytes(body) if isinstance(body, (bytes, bytearray)) else body
    root = strict_rss_xml_root(raw)
    return {
        "content_type_validation": RSS_CONTENT_TYPE_FALLBACK_METHOD,
        "rss_xml_root": root,
        "rss_xml_raw_sha256": hashlib.sha256(raw).hexdigest(),
    }


def rss_content_type_fallback_matches(
        row, *, expected_url=None, body=None, max_bytes=None):
    """Validate the narrow, hash-bound fallback for a missing RSS media type."""
    if not isinstance(row, dict) or row.get("kind") != "rss":
        return False
    if not rss_content_type_is_absent(row.get("content_type")):
        return False
    configured_url = expected_url if expected_url is not None else row.get("url")
    if (
        not isinstance(configured_url, str)
        or row.get("url") != configured_url
        or row.get("final_url") != configured_url
    ):
        return False
    configured_host = _https_host(configured_url)
    if configured_host is None or _https_host(row.get("final_url")) != configured_host:
        return False
    size = row.get("bytes")
    if not isinstance(size, int) or isinstance(size, bool) or size <= 0:
        return False
    if max_bytes is not None and (
        not isinstance(max_bytes, int) or isinstance(max_bytes, bool)
        or max_bytes <= 0 or size > max_bytes
    ):
        return False
    raw_sha256 = row.get("raw_sha256")
    if not _valid_sha256(raw_sha256):
        return False
    if (
        row.get("content_type_validation") != RSS_CONTENT_TYPE_FALLBACK_METHOD
        or row.get("rss_xml_root") not in RSS_CONTENT_TYPE_FALLBACK_ROOTS
        or row.get("rss_xml_raw_sha256") != raw_sha256
    ):
        return False
    if body is not None:
        if not isinstance(body, (bytes, bytearray)):
            return False
        raw = bytes(body)
        if len(raw) != size or hashlib.sha256(raw).hexdigest() != raw_sha256:
            return False
        try:
            root = strict_rss_xml_root(raw)
        except ValueError:
            return False
        if root != row.get("rss_xml_root"):
            return False
    return True


def _queue_entry_hash(entry):
    body = {key: value for key, value in entry.items() if key != "entry_hash"}
    return _canonical_sha256(body)


def build_queue_attestation(
        previous_attestation, *, configured_source_ids, pending_ids,
        acknowledged_ids, checked_at, sources, bootstrap=False):
    """Append one locally verifiable queue-state transition.

    This is an integrity chain, not human identity proof.  Its purpose is to make
    deleting a durable pending item from the snapshot fail closed on the next run.
    A separate owner-controlled acknowledgement still remains mandatory.
    """
    configured = sorted(set(configured_source_ids))
    pending = sorted(set(pending_ids))
    acknowledged = sorted(set(acknowledged_ids))
    if acknowledged:
        raise ValueError(
            "pending source removal requires an external owner-controlled receipt"
        )
    history = []
    if not bootstrap and isinstance(previous_attestation, dict):
        candidate = previous_attestation.get("history")
        if isinstance(candidate, list):
            history = [dict(item) for item in candidate if isinstance(item, dict)]
    if not history:
        bootstrap = True
    if bootstrap:
        history = []
        pending = list(configured)
    previous_hash = history[-1]["entry_hash"] if history else QUEUE_ATTESTATION_GENESIS
    entry = {
        "sequence": (history[-1]["sequence"] + 1) if history else 1,
        "checked_at": checked_at,
        "configured_source_ids": configured,
        "pending_ids": pending,
        "acknowledged_ids": acknowledged,
        "mode": "BOOTSTRAP_FAIL_CLOSED" if bootstrap else "NORMAL",
        "previous_hash": previous_hash,
        "source_state_sha256": _canonical_sha256(sources),
    }
    entry["entry_hash"] = _queue_entry_hash(entry)
    history.append(entry)
    return {
        "schema": QUEUE_ATTESTATION_SCHEMA,
        "algorithm": QUEUE_ATTESTATION_ALGORITHM,
        "history": history,
    }


def validate_queue_attestation(snapshot):
    """Validate the complete local queue hash-chain against this snapshot."""
    failures = []
    attestation = snapshot.get("queue_attestation") if isinstance(snapshot, dict) else None
    if not isinstance(attestation, dict):
        return (), ("official source queue attestation is missing",)
    if set(attestation) != {"schema", "algorithm", "history"}:
        failures.append("official source queue attestation fields are malformed")
    if attestation.get("schema") != QUEUE_ATTESTATION_SCHEMA:
        failures.append("official source queue attestation schema is unsupported")
    if attestation.get("algorithm") != QUEUE_ATTESTATION_ALGORITHM:
        failures.append("official source queue attestation algorithm is unsupported")
    history = attestation.get("history")
    if (
        not isinstance(history, list) or not history
        or len(history) > QUEUE_ATTESTATION_MAX_ENTRIES
    ):
        failures.append("official source queue attestation history is malformed")
        return (), tuple(dict.fromkeys(failures))

    prior = None
    for index, entry in enumerate(history):
        label = "official source queue attestation entry %d" % (index + 1)
        if not isinstance(entry, dict) or set(entry) != _QUEUE_ENTRY_FIELDS:
            failures.append(label + " fields are malformed")
            prior = entry if isinstance(entry, dict) else {}
            continue
        sequence = entry.get("sequence")
        if not isinstance(sequence, int) or isinstance(sequence, bool) or sequence != index + 1:
            failures.append(label + " sequence is malformed")
        _aware_datetime(entry.get("checked_at"), label + " checked_at", failures)
        configured = _strict_id_list(
            entry.get("configured_source_ids"), label + " configured_source_ids",
            failures, allow_empty=False,
        )
        pending = _strict_id_list(
            entry.get("pending_ids"), label + " pending_ids", failures
        )
        acknowledged = _strict_id_list(
            entry.get("acknowledged_ids"), label + " acknowledged_ids", failures
        )
        if not set(pending).issubset(configured):
            failures.append(label + " pending_ids are not configured")
        if acknowledged:
            failures.append(
                label + " contains an acknowledgement without external owner proof"
            )
        mode = entry.get("mode")
        if index == 0:
            if (
                mode != "BOOTSTRAP_FAIL_CLOSED"
                or entry.get("previous_hash") != QUEUE_ATTESTATION_GENESIS
                or set(pending) != set(configured)
                or acknowledged
            ):
                failures.append(label + " is not a fail-closed genesis")
        else:
            if mode != "NORMAL" or entry.get("previous_hash") != prior.get("entry_hash"):
                failures.append(label + " chain link is invalid")
            prior_pending = set(prior.get("pending_ids", []))
            prior_configured = set(prior.get("configured_source_ids", []))
            configured_set = set(configured)
            removed = prior_pending - set(pending)
            # A co-located SHA chain proves internal consistency only.  It cannot
            # authenticate the owner.  Human acknowledgement and source
            # decommissioning therefore stay blocked until a separately
            # controlled, signed/private receipt verifier exists.
            permitted_removed = set()
            if not removed.issubset(permitted_removed):
                failures.append(label + " removed pending sources without external owner proof")
            if prior_configured - configured_set:
                failures.append(label + " removed configured sources without external owner proof")
            if not (configured_set - prior_configured).issubset(set(pending)):
                failures.append(label + " new configured sources are not pending")
        if not _valid_sha256(entry.get("source_state_sha256")):
            failures.append(label + " source_state_sha256 is malformed")
        if not _valid_sha256(entry.get("entry_hash")) or entry.get("entry_hash") != _queue_entry_hash(entry):
            failures.append(label + " hash is invalid")
        prior = entry

    tail = history[-1] if isinstance(history[-1], dict) else {}
    rows = snapshot.get("sources") if isinstance(snapshot, dict) else None
    current_ids = sorted(
        row.get("id", "").strip()
        for row in rows or []
        if isinstance(row, dict) and isinstance(row.get("id"), str) and row["id"].strip()
    )
    review_ids = snapshot.get("review_required") if isinstance(snapshot, dict) else None
    if tail.get("checked_at") != snapshot.get("checked_at"):
        failures.append("official source queue attestation timestamp does not match snapshot")
    if tail.get("configured_source_ids") != current_ids:
        failures.append("official source queue attestation source set does not match snapshot")
    if tail.get("pending_ids") != review_ids:
        failures.append("official source queue attestation pending set does not match snapshot")
    if tail.get("source_state_sha256") != _canonical_sha256(rows):
        failures.append("official source queue attestation does not bind source rows")
    return tuple(tail.get("pending_ids") or ()), tuple(dict.fromkeys(failures))


def _validate_source_row(row, source_id, expected_url, checked_at, failures):
    label = "official source %s" % source_id
    if not isinstance(row, dict):
        failures.append(label + " row is missing or malformed")
        return
    url = row.get("url")
    initial_host = _https_host(url)
    if initial_host is None:
        failures.append(label + " URL is not provenance-safe HTTPS")
    if expected_url is not None and url != expected_url:
        failures.append(label + " URL does not match the exact source registry")
    kind = row.get("kind")
    if kind not in {"html", "pdf", "json", "rss"}:
        failures.append(label + " kind is unsupported")
    if row.get("checked_at") != checked_at:
        failures.append(label + " checked_at does not match the snapshot")
    change = row.get("change")
    if change not in {"new", "changed", "unchanged", "error"}:
        failures.append(label + " change state is unsupported")
        return
    if change == "error" or row.get("error"):
        if not isinstance(row.get("error"), str) or not row["error"].strip():
            failures.append(label + " error evidence is malformed")
        return
    status = row.get("http_status")
    if not isinstance(status, int) or isinstance(status, bool) or not 200 <= status < 300:
        failures.append(label + " HTTP status is not successful")
    final_url = row.get("final_url")
    final_host = _https_host(final_url)
    if final_host is None or initial_host is None or final_host != initial_host:
        failures.append(label + " final URL leaves the configured official host")
    if (
        not _content_type_matches(kind, row.get("content_type"))
        and not rss_content_type_fallback_matches(
            row, expected_url=expected_url if expected_url is not None else url
        )
    ):
        failures.append(label + " content type does not match its configured kind")
    size = row.get("bytes")
    if not isinstance(size, int) or isinstance(size, bool) or size <= 0:
        failures.append(label + " byte count is malformed")
    method = row.get("fingerprint_method")
    if method not in {"raw-v1", "visible-text-v1"}:
        failures.append(label + " fingerprint method is unsupported")
    if not _valid_sha256(row.get("raw_sha256")) or not _valid_sha256(row.get("sha256")):
        failures.append(label + " fingerprints are malformed")
    elif method == "raw-v1" and row.get("raw_sha256") != row.get("sha256"):
        failures.append(label + " raw fingerprint does not bind the fetched bytes")


def validate_official_snapshot_contract(
        snapshot, *, required_source_ids=None, expected_urls=None, now=None,
        freshness_hours=24, strict_all_rows=False):
    """Validate schema-3 evidence and only apply source state to an exact scope.

    Envelope and queue-chain integrity are global because they establish that the
    artifact is trustworthy.  ``new``/``changed``/``error``/pending decisions and
    full row checks are limited to ``required_source_ids`` unless
    ``strict_all_rows`` is requested by a global observation consumer.
    """
    failures = []
    if not isinstance(snapshot, dict):
        return OfficialSnapshotResult(
            False, (), ("official source snapshot must be a JSON object",)
        )
    if snapshot.get("schema") != OFFICIAL_SNAPSHOT_SCHEMA:
        failures.append("official source snapshot schema must be 3")
    if snapshot.get("purpose") != "change detection only; review official source before publishing":
        failures.append("official source snapshot purpose is missing or unsupported")

    changed = _strict_id_list(
        snapshot.get("changed"), "official source snapshot changed", failures
    )
    errors = _strict_id_list(
        snapshot.get("errors"), "official source snapshot errors", failures
    )
    pending = _strict_id_list(
        snapshot.get("review_required"),
        "official source snapshot review_required", failures,
    )
    acknowledged = _strict_id_list(
        snapshot.get("acknowledged_this_run"),
        "official source snapshot acknowledged_this_run", failures,
    )
    rows = snapshot.get("sources")
    by_id = {}
    by_url = {}
    if not isinstance(rows, list) or not rows:
        failures.append("official source snapshot sources is malformed")
        rows = []
    else:
        for row in rows:
            if not isinstance(row, dict):
                failures.append("official source snapshot source row is malformed")
                continue
            source_id = row.get("id")
            url = row.get("url")
            if not isinstance(source_id, str) or not source_id.strip():
                failures.append("official source snapshot source row has no source id")
                continue
            source_id = source_id.strip()
            if source_id in by_id:
                failures.append("official source snapshot has duplicate source IDs")
                continue
            by_id[source_id] = row
            if isinstance(url, str):
                if url in by_url:
                    failures.append("official source snapshot has duplicate source URLs")
                else:
                    by_url[url] = source_id

    configured_ids = set(by_id)
    for label, values in (
        ("changed", changed), ("errors", errors),
        ("review_required", pending), ("acknowledged_this_run", acknowledged),
    ):
        unknown = set(values) - configured_ids
        if unknown:
            failures.append(
                "official source snapshot %s contains unconfigured IDs: %s" %
                (label, ", ".join(sorted(unknown)[:3]))
            )
    if not set(changed).issubset(pending):
        failures.append("official source snapshot changed IDs are not durably pending")
    if not set(errors).issubset(pending):
        failures.append("official source snapshot error IDs are not durably pending")
    if set(changed) & set(errors):
        failures.append("official source snapshot changed and error IDs overlap")
    if set(acknowledged) & set(pending):
        failures.append("official source snapshot acknowledged IDs remain pending")

    checked = _aware_datetime(
        snapshot.get("checked_at"), "official source snapshot checked_at", failures
    )
    current = now or datetime.now(timezone.utc)
    if not isinstance(current, datetime) or current.tzinfo is None or current.utcoffset() is None:
        failures.append("official source decision time must include a timezone")
        current = None
    if (
        not isinstance(freshness_hours, (int, float))
        or isinstance(freshness_hours, bool)
        or not math.isfinite(float(freshness_hours))
        or float(freshness_hours) <= 0
    ):
        failures.append("official source freshness_hours must be a positive finite number")
    elif checked is not None and current is not None:
        age_hours = (
            current.astimezone(timezone.utc) - checked.astimezone(timezone.utc)
        ).total_seconds() / 3600
        if age_hours < 0:
            failures.append("official source snapshot timestamp is in the future")
        elif age_hours > float(freshness_hours):
            failures.append("official source snapshot is stale")

    summary = snapshot.get("summary")
    review_queue = snapshot.get("review_queue")
    acknowledgement_log = snapshot.get("acknowledgement_log")
    if not isinstance(summary, dict) or set(summary) != _SUMMARY_FIELDS:
        failures.append("official source snapshot summary is malformed")
    else:
        count_fields = _SUMMARY_FIELDS - {"network_probe", "freshness_state"}
        if any(
            not isinstance(summary.get(key), int)
            or isinstance(summary.get(key), bool)
            or summary[key] < 0
            for key in count_fields
        ):
            failures.append("official source snapshot summary counts are malformed")
        expected_state = (
            "ERROR" if errors else "FRESH_REVIEW_REQUIRED" if pending else "CURRENT"
        )
        expected_summary = {
            "configured_sources": len(by_id),
            "checked_sources": len(rows),
            "successful_sources": len(rows) - len(errors),
            "changed_this_run": len(changed),
            "current_errors": len(errors),
            "pending_owner_reviews": len(pending),
            "acknowledged_this_run": len(acknowledged),
            "network_probe": "PARTIAL" if errors else "COMPLETE",
            "freshness_state": expected_state,
        }
        if summary != expected_summary:
            failures.append("official source snapshot summary contradicts its evidence")
    queue_ids = []
    if not isinstance(review_queue, list):
        failures.append("official source snapshot review_queue is malformed")
    else:
        for item in review_queue:
            required = {
                "source_id", "trigger", "pending_since", "last_checked_at",
                "current_state", "acknowledgement_status",
            }
            if (
                not isinstance(item, dict) or not required.issubset(item)
                or any(not isinstance(item.get(key), str) or not item[key].strip()
                       for key in required)
                or item.get("acknowledgement_status") != "PENDING_OWNER_REVIEW"
            ):
                failures.append("official source snapshot review_queue row is malformed")
                continue
            queue_ids.append(item["source_id"])
        if queue_ids != pending:
            failures.append("official source snapshot review_queue does not match pending IDs")
    if not isinstance(acknowledgement_log, list) or any(
        not isinstance(item, dict)
        or not isinstance(item.get("source_id"), str) or not item["source_id"].strip()
        or not isinstance(item.get("acknowledged_by"), str) or not item["acknowledged_by"].strip()
        or _aware_datetime(
            item.get("acknowledged_at"), "official source acknowledgement timestamp", []
        ) is None
        for item in (acknowledgement_log if isinstance(acknowledgement_log, list) else [])
    ):
        failures.append("official source snapshot acknowledgement_log is malformed")

    attested_pending, attestation_failures = validate_queue_attestation(snapshot)
    failures.extend(attestation_failures)
    if not attestation_failures:
        history = snapshot["queue_attestation"]["history"]
        if set(history[-1].get("acknowledged_ids", [])) != set(acknowledged):
            failures.append("official source queue attestation does not bind acknowledgements")
        if tuple(pending) != attested_pending:
            failures.append("official source queue attestation pending order is inconsistent")

    if required_source_ids is None:
        required = set(configured_ids) if strict_all_rows else set()
    elif (
        not isinstance(required_source_ids, (list, tuple, set, frozenset))
        or not required_source_ids
        or any(not isinstance(item, str) or not item.strip()
               for item in required_source_ids)
    ):
        failures.append("required official source IDs are missing or malformed")
        required = set()
    else:
        normalized_required = [item.strip() for item in required_source_ids]
        if len(normalized_required) != len(set(normalized_required)):
            failures.append("required official source IDs contain duplicates")
        required = set(normalized_required)
    expected_urls = expected_urls if isinstance(expected_urls, dict) else {}
    for source_id in sorted(required):
        row = by_id.get(source_id)
        if row is None:
            failures.append("required official source is not monitored: %s" % source_id)
            continue
        row_change = row.get("change")
        row_changed = row_change in {"new", "changed"}
        row_error = row_change == "error" or bool(row.get("error"))
        if row_changed != (source_id in changed):
            failures.append(
                "official source %s row change contradicts changed IDs" % source_id
            )
        if row_error != (source_id in errors):
            failures.append(
                "official source %s row error contradicts error IDs" % source_id
            )
        _validate_source_row(
            row, source_id, expected_urls.get(source_id),
            snapshot.get("checked_at"), failures,
        )
    relevant_changed = sorted(required & set(changed))
    relevant_errors = sorted(required & set(errors))
    relevant_pending = sorted(required & set(pending))
    if relevant_changed:
        failures.append("relevant official source changed: %s" % ", ".join(relevant_changed))
    if relevant_errors:
        failures.append("relevant official source error: %s" % ", ".join(relevant_errors))
    if relevant_pending:
        failures.append(
            "relevant official source review is pending: %s" %
            ", ".join(relevant_pending)
        )
    return OfficialSnapshotResult(
        not failures, tuple(sorted(required)), tuple(dict.fromkeys(failures))
    )


def evaluate_official_snapshot_sources(
        source_ids, snapshot_path, *, expected_urls=None, now=None,
        freshness_hours=24):
    """Public strict helper for consumers that know an exact source-ID set."""
    snapshot, error = _load_object(snapshot_path, "official source snapshot")
    if error:
        return OfficialSnapshotResult(False, (), (error,))
    return validate_official_snapshot_contract(
        snapshot,
        required_source_ids=source_ids,
        expected_urls=expected_urls,
        now=now,
        freshness_hours=freshness_hours,
    )


def source_registry_binding_sha256(registry):
    """Checksum binding fields; this is never proof of owner review authority."""
    if not isinstance(registry, dict):
        return ""
    return _canonical_sha256({
        "schema_version": registry.get("schema_version"),
        "library": registry.get("library"),
        "freshness_hours": registry.get("freshness_hours"),
        "items": registry.get("items"),
    })


def _load_object(path, label):
    def reject_constant(token):
        raise ValueError("non-finite JSON constant: " + token)

    def reject_duplicate_keys(pairs):
        value = {}
        for key, item in pairs:
            if key in value:
                raise ValueError("duplicate JSON key")
            value[key] = item
        return value

    def require_finite(item):
        if isinstance(item, float) and not math.isfinite(item):
            raise ValueError("non-finite JSON number")
        if isinstance(item, dict):
            for child in item.values():
                require_finite(child)
        elif isinstance(item, list):
            for child in item:
                require_finite(child)

    try:
        payload = json.loads(
            Path(path).read_text(encoding="utf-8"),
            parse_constant=reject_constant,
            object_pairs_hook=reject_duplicate_keys,
        )
        require_finite(payload)
    except Exception as exc:
        return None, "%s missing/unreadable: %s" % (label, type(exc).__name__)
    if not isinstance(payload, dict):
        return None, "%s must be a JSON object" % label
    return payload, None


def _id_list(payload, field, failures):
    value = payload.get(field)
    if not isinstance(value, list) or any(
            not isinstance(item, str) or not item.strip() for item in value):
        failures.append("official source snapshot %s is malformed" % field)
        return set()
    return {item.strip() for item in value}


def evaluate_content_source_gate(content_id, registry_path, snapshot_path,
                                 *, library_name=None, now=None,
                                 _registry_document=None,
                                 _snapshot_document=None,
                                 _review_receipt_repo=None):
    """Return a fail-closed, content-scoped official-source decision.

    ``review_required`` remains the durable global human-acknowledgement queue.
    An exact owner-signed ``UNCHANGED`` receipt can clear only the local review
    blockers for this content ID and its exact pending IDs; it never edits or
    acknowledges that global queue. Pending state for unrelated IDs is not a
    publication failure here and remains visible to global consumers.
    """
    normalized_id = content_id.strip() if isinstance(content_id, str) else ""
    if not normalized_id:
        return SourceGateResult(False, "", (), ("content_id missing",))

    if (_registry_document is None) != (_snapshot_document is None):
        return SourceGateResult(
            False,
            normalized_id,
            (),
            ("bound source documents must be supplied as an exact pair",),
        )
    if _registry_document is not None:
        registry = _registry_document
        snapshot = _snapshot_document
        registry_error = (
            None if isinstance(registry, dict)
            else "source registry must be a JSON object"
        )
        snapshot_error = (
            None if isinstance(snapshot, dict)
            else "official source snapshot must be a JSON object"
        )
    else:
        registry, registry_error = _load_object(registry_path, "source registry")
        snapshot, snapshot_error = _load_object(snapshot_path, "official source snapshot")
    load_failures = tuple(
        issue for issue in (registry_error, snapshot_error) if issue is not None)
    if load_failures:
        return SourceGateResult(False, normalized_id, (), load_failures)

    failures = []
    current = now or datetime.now(timezone.utc)
    if not isinstance(current, datetime) or current.tzinfo is None or current.utcoffset() is None:
        failures.append("source registry decision time must include a timezone")

    if registry.get("schema_version") != SOURCE_REGISTRY_SCHEMA:
        failures.append("source registry schema_version must be 1")
    if library_name is not None and registry.get("library") != library_name:
        failures.append("source registry is bound to a different library")
    freshness = registry.get("freshness_hours")
    if (
        not isinstance(freshness, (int, float)) or isinstance(freshness, bool)
        or not math.isfinite(float(freshness)) or float(freshness) <= 0
    ):
        failures.append("source registry freshness_hours must be a positive finite number")

    local_review_failures = []
    binding_state = registry.get("binding_state")
    if binding_state != "HUMAN_REVIEWED":
        local_review_failures.append(
            "source registry bindings still require explicit human review"
        )
    reviewed_at = registry.get("last_human_review")
    review_day = None
    if isinstance(reviewed_at, str) and reviewed_at.strip():
        try:
            review_day = date.fromisoformat(reviewed_at.strip())
        except ValueError:
            review_failures = []
            reviewed_stamp = _aware_datetime(
                reviewed_at, "source registry last_human_review", review_failures
            )
            if reviewed_stamp is not None:
                review_day = reviewed_stamp.astimezone(timezone.utc).date()
            else:
                local_review_failures.extend(review_failures)
    else:
        local_review_failures.append("source registry human review evidence is missing")
    if review_day is not None and isinstance(current, datetime) and current.tzinfo is not None:
        if review_day > current.astimezone(timezone.utc).date():
            local_review_failures.append(
                "source registry human review evidence is in the future"
            )
    binding_hash = registry.get("reviewed_binding_sha256")
    if not _valid_sha256(binding_hash):
        local_review_failures.append(
            "source registry reviewed binding hash is missing or malformed"
        )
    elif binding_hash != source_registry_binding_sha256(registry):
        local_review_failures.append(
            "source registry changed after its recorded human review"
        )
    # All project files are writable by the internal operator.  A status string
    # and a checksum stored beside the registry cannot authenticate the owner.
    # Keep factual content blocked until a separately controlled signed/private
    # receipt can be verified; do not invent authority from local metadata.
    local_review_failures.append(
        "source registry owner review receipt is unavailable; local binding checksum is not authority"
    )

    item_failures = []
    items = registry.get("items")
    if not isinstance(items, dict):
        item_failures.append("source registry items is malformed")
        item = None
    else:
        item = items.get(normalized_id)
        if not isinstance(item, dict):
            item_failures.append("%s: no source-registry entry" % normalized_id)

    urls = []
    ids = []
    expected_urls = {}
    if isinstance(item, dict):
        claim_scope = item.get("claim_scope")
        if not isinstance(claim_scope, str) or not claim_scope.strip():
            item_failures.append("%s: claim_scope is missing" % normalized_id)
        raw_urls = item.get("official_urls")
        if (
            not isinstance(raw_urls, list) or not raw_urls
            or any(_https_host(url) is None for url in raw_urls)
        ):
            item_failures.append(
                "%s: official_urls missing or not provenance-safe HTTPS" % normalized_id
            )
        else:
            urls = list(raw_urls)
            if len(urls) != len(set(urls)):
                item_failures.append(
                    "%s: official_urls contain duplicates" % normalized_id
                )
        raw_ids = item.get("source_ids")
        if (
            not isinstance(raw_ids, list) or not raw_ids
            or any(not isinstance(source_id, str) or not source_id.strip()
                   for source_id in raw_ids)
        ):
            item_failures.append(
                "%s: source_ids is missing or malformed" % normalized_id
            )
        else:
            ids = [source_id.strip() for source_id in raw_ids]
            if len(ids) != len(set(ids)):
                item_failures.append(
                    "%s: source_ids contain duplicates" % normalized_id
                )
        if urls and ids:
            if len(urls) != len(ids):
                item_failures.append(
                    "%s: source_ids do not exactly map official_urls" % normalized_id
                )
            else:
                expected_urls = dict(zip(ids, urls))
        manual_evidence = item.get("manual_evidence_required")
        if isinstance(manual_evidence, str) and manual_evidence.strip():
            item_failures.append(
                "%s: manual source evidence is still required: %s" %
                (normalized_id, manual_evidence.strip())
            )

    snapshot_result = validate_official_snapshot_contract(
        snapshot,
        required_source_ids=ids,
        expected_urls=expected_urls,
        now=current,
        freshness_hours=freshness,
    )
    if _review_receipt_repo is not None:
        receipt_repo = Path(_review_receipt_repo)
    else:
        registry_location = Path(registry_path)
        if (
            registry_location.parent.name == "knowledge-base"
            and registry_location.parent.parent.name == "automation-log"
        ):
            receipt_repo = registry_location.parent.parent.parent
        else:
            receipt_repo = registry_location.parent
    receipt_result = source_review_receipt.verify_content_source_review_receipt(
        repo=receipt_repo,
        content_id=normalized_id,
        registry_binding_sha256=source_registry_binding_sha256(registry),
        source_ids=sorted(set(ids)),
        source_rows=snapshot.get("sources"),
        now=current,
    )

    if not receipt_result.accepted:
        failures.extend(local_review_failures)
    failures.extend(item_failures)
    snapshot_failures = list(snapshot_result.failures)
    if receipt_result.accepted:
        exact_pending_failure = (
            "relevant official source review is pending: "
            + ", ".join(sorted(set(ids)))
        )
        snapshot_failures = [
            issue for issue in snapshot_failures if issue != exact_pending_failure
        ]
    failures.extend(snapshot_failures)
    if receipt_result.found and not receipt_result.accepted:
        failures.extend(
            "source-review receipt invalid: " + issue
            for issue in receipt_result.failures
        )
    unique_failures = tuple(dict.fromkeys(failures))
    return SourceGateResult(
        not unique_failures, normalized_id, tuple(sorted(set(ids))), unique_failures
    )


def evaluate_content_source_claim(content_id, declared_source_ids, registry_path,
                                  snapshot_path, *, library_name=None, now=None):
    """Validate a placement claim against the complete content-scoped mapping.

    The official source decision is derived only from ``content_id`` and therefore
    cannot vary by platform. ``declared_source_ids`` is evidence carried by a
    calendar/manifest placement; it must equal the registry mapping exactly. A
    subset is not sufficient because it can hide a changed required source.
    """
    result = evaluate_content_source_gate(
        content_id,
        registry_path,
        snapshot_path,
        library_name=library_name,
        now=now,
    )
    failures = list(result.failures)
    if (not isinstance(declared_source_ids, (list, tuple))
            or not declared_source_ids
            or any(not isinstance(value, str) or not value.strip()
                   for value in declared_source_ids)):
        failures.append("%s: declared source_ids are missing or malformed" % result.content_id)
    else:
        normalized = [value.strip() for value in declared_source_ids]
        if len(normalized) != len(set(normalized)):
            failures.append("%s: declared source_ids contain duplicates" % result.content_id)
        declared = set(normalized)
        required = set(result.source_ids)
        if declared != required:
            missing = sorted(required - declared)
            extra = sorted(declared - required)
            detail = []
            if missing:
                detail.append("missing=" + ",".join(missing))
            if extra:
                detail.append("extra=" + ",".join(extra))
            failures.append(
                "%s: declared source_ids must exactly equal the content registry%s" % (
                    result.content_id,
                    (" (" + "; ".join(detail) + ")") if detail else "",
                )
            )
    unique_failures = tuple(dict.fromkeys(failures))
    return SourceGateResult(
        not unique_failures,
        result.content_id,
        result.source_ids,
        unique_failures,
    )


def repo_content_source_contract(content_id, repo):
    """Resolve one repository content ID to its single canonical registry."""
    normalized = content_id.strip() if isinstance(content_id, str) else ""
    for prefixes, filename, library in REPO_CONTENT_SOURCE_CONTRACTS:
        if normalized.startswith(prefixes):
            root = Path(repo)
            knowledge = root / "automation-log" / "knowledge-base"
            return knowledge / filename, library
    return None, None


def evaluate_repo_content_source_gate(
        content_id, repo, *, now=None, snapshot_path=None):
    """Evaluate source truth for one project content ID without a placement claim."""
    registry, library = repo_content_source_contract(content_id, repo)
    normalized = content_id.strip() if isinstance(content_id, str) else ""
    if registry is None:
        return SourceGateResult(
            False,
            normalized,
            (),
            ((normalized or "content") + ": factual content has no canonical source registry",),
        )
    selected_snapshot = (
        Path(snapshot_path)
        if snapshot_path is not None
        else Path(repo) / "automation-log" / "knowledge-base" / "official-news-snapshot.json"
    )
    return evaluate_content_source_gate(
        normalized,
        registry,
        selected_snapshot,
        library_name=library,
        now=now,
        _review_receipt_repo=repo,
    )


def evaluate_repo_content_source_claim(
        content_id, declared_source_ids, repo, *, now=None):
    """Shared repository-specific exact per-piece source evaluator."""
    result = evaluate_repo_content_source_gate(content_id, repo, now=now)
    failures = list(result.failures)
    if (
        not isinstance(declared_source_ids, (list, tuple))
        or not declared_source_ids
        or any(
            not isinstance(value, str) or not value.strip()
            for value in declared_source_ids
        )
    ):
        failures.append(
            "%s: declared source_ids are missing or malformed" % result.content_id
        )
    else:
        normalized = [value.strip() for value in declared_source_ids]
        if len(normalized) != len(set(normalized)):
            failures.append(
                "%s: declared source_ids contain duplicates" % result.content_id
            )
        declared = set(normalized)
        required = set(result.source_ids)
        if declared != required:
            failures.append(
                "%s: declared source_ids must exactly equal the content registry"
                % result.content_id
            )
    unique_failures = tuple(dict.fromkeys(failures))
    return SourceGateResult(
        not unique_failures,
        result.content_id,
        result.source_ids,
        unique_failures,
    )
