#!/usr/bin/env python3
"""Monitor authoritative policy and Search sources without an API key.

The snapshot is a change detector, not a fact extractor.  A changed fingerprint
means a human or research agent must review the official page before site copy is
updated.  Affiliate redirects are intentionally excluded.
"""
import argparse
import datetime
import hashlib
from html.parser import HTMLParser
import json
import math
import os
from pathlib import Path
import sys
import tempfile
import urllib.request
from urllib.parse import urlparse


ROOT_PATH = Path(__file__).resolve().parents[1]
TOOLS_PATH = ROOT_PATH / "tools"
if str(TOOLS_PATH) not in sys.path:
    sys.path.insert(0, str(TOOLS_PATH))

from action_authority import ActionBlocked
from content_source_gate import (
    build_rss_content_type_fallback_evidence,
    build_queue_attestation,
    rss_content_type_is_absent,
    rss_content_type_fallback_matches,
    validate_official_snapshot_contract,
    validate_queue_attestation,
)


HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DEFAULT_OUT = os.path.join(
    ROOT, "automation-log", "knowledge-base", "official-news-snapshot.json")
DEFAULT_ALERT = os.path.join(
    ROOT, "automation-log", "cowork-inbox", "OFFICIAL-NEWS-REVIEW.md")
DEFAULT_SOURCE_REGISTRY = os.path.join(
    ROOT, "automation-log", "knowledge-base", "content-source-registry.json")
DEFAULT_SOURCE_REGISTRIES = (
    DEFAULT_SOURCE_REGISTRY,
    os.path.join(
        ROOT, "automation-log", "knowledge-base", "page2-source-registry.json"
    ),
    os.path.join(
        ROOT, "automation-log", "knowledge-base", "social-source-registry.json"
    ),
)
MAX_BYTES = 4 * 1024 * 1024
SOURCE_ID_ALIASES = {
    # The former URL returned 404 and was replaced with current first-party
    # PDPC guidance.  Preserve the pending-review state under the new id.
    "pdpa-act-2019": "pdpc-privacy-minimization",
}
TIME_SENSITIVE_SOURCE_IDS = {
    "bot-card-minimum-2026",
    "bot-clear-debt-news",
    "bot-economy-q2-2026",
    "bot-loan-survey-q2-2026",
    "bot-ltv-2026-extension",
    "bot-mobile-app-launch",
    "bot-utility-data",
    "bot-your-data-criteria",
    "bot-your-data-rules",
    "bot-youth-transfer-controls",
}
GLOBAL_MONITOR_SCOPE = "global_monitor_only"
SOURCE_IDENTITY_FIELDS = (
    "id", "url", "kind", "scope", "fingerprint", "max_bytes",
)

SOURCES = [
    {
        "id": "google-search-incidents",
        "url": "https://status.search.google.com/incidents.json",
        "kind": "json",
        "scope": GLOBAL_MONITOR_SCOPE,
    },
    {
        "id": "google-search-doc-updates",
        "url": "https://developers.google.com/search/updates/search_docs_updates.rss",
        "kind": "rss",
        "scope": GLOBAL_MONITOR_SCOPE,
    },
    {
        "id": "bot-news",
        "url": "https://www.bot.or.th/th/news-and-media/news.html",
        "kind": "html",
        "scope": GLOBAL_MONITOR_SCOPE,
    },
    {
        "id": "bot-clear-debt",
        "url": "https://www.bot.or.th/th/cleardebt.html",
        "kind": "html",
    },
    {
        "id": "bot-responsible-lending",
        "url": "https://app.bot.or.th/FIPCS/Thai/PFIPCS_summary.aspx?packId=25680030",
        "kind": "html",
        "scope": GLOBAL_MONITOR_SCOPE,
    },
    {
        "id": "bot-ltv-2026-extension",
        "url": "https://www.bot.or.th/th/news-and-media/news/news-20260514.html",
        "kind": "html",
    },
    {
        "id": "bot-youth-transfer-controls",
        "url": "https://www.bot.or.th/th/news-and-media/news/news-20260731-2.html",
        "kind": "html",
    },
    {
        "id": "bot-your-data-criteria",
        "url": "https://www.bot.or.th/content/dam/bot/documents/th/news-and-media/news/2025/news-20251110.pdf",
        "kind": "pdf",
    },
    {
        "id": "bot-credit-card-guidance",
        "url": "https://www.bot.or.th/th/satang-story/digital-fin-lit/creditcard.html",
        "kind": "html",
    },
    {
        "id": "bot-mobile-app",
        "url": "https://www.bot.or.th/th/bot-mobile-app.html",
        "kind": "html",
    },
    {
        "id": "bot-mobile-app-launch",
        "url": "https://www.bot.or.th/th/research-and-publications/articles-and-publications/articles/article-20260804.html",
        "kind": "html",
    },
    {
        "id": "bot-loan-survey-q2-2026",
        "url": "https://www.bot.or.th/content/dam/bot/documents/th/thai-economy/econ-publication/credit-conditions-report/LoanSurvey-TH-2569-Q2.pdf",
        "kind": "pdf",
    },
    {
        "id": "bot-economy-q2-2026",
        "url": "https://www.bot.or.th/th/news-and-media/news/news-20260731.html",
        "kind": "html",
    },
    {
        "id": "bot-card-minimum-2026",
        "url": "https://www.bot.or.th/content/dam/bot/fipcs/documents/FPG/2568/ThaiPDF/25680245.pdf",
        "kind": "pdf",
    },
    {
        "id": "bot-happy-debtor",
        "url": "https://www.bot.or.th/th/research-and-publications/articles-and-publications/bot-magazine-issues/Phrasiam-67-2/256702-FinWis-HappyDebtor.html",
        "kind": "html",
    },
    {
        "id": "bot-before-loan",
        "url": "https://www.bot.or.th/th/satang-story/managing-debt/before-loan.html",
        "kind": "html",
    },
    {
        "id": "bot-responsible-lending-pdf",
        "url": "https://www.bot.or.th/content/dam/bot/fipcs/documents/FPG/2568/ThaiPDF/25680030.pdf",
        "kind": "pdf",
        "max_bytes": 6 * 1024 * 1024,
    },
    {
        "id": "bot-consumer-loan-restructuring",
        "url": "https://www.bot.or.th/th/satang-story/managing-debt/consumer-loan-restructuring.html",
        "kind": "html",
    },
    {
        "id": "bot-clear-debt-news",
        "url": "https://www.bot.or.th/th/news-and-media/news/news-20260105.html",
        "kind": "html",
    },
    {
        "id": "bot-license-loan",
        "url": "https://www.bot.or.th/th/license-loan.html",
        "kind": "html",
    },
    {
        "id": "bot-license-check",
        "url": "https://app.bot.or.th/BOTLicenseCheck",
        "kind": "html",
        "fingerprint": "visible-text-v1",
    },
    {
        "id": "bot-utility-data",
        "url": "https://www.bot.or.th/th/financial-innovation/digital-finance/open-data/Your_Data_Project/utility-data.html",
        "kind": "html",
    },
    {
        "id": "bot-your-data-rules",
        "url": "https://www.bot.or.th/content/dam/bot/fipcs/documents/FPG/2568/ThaiPDF/25680226.pdf",
        "kind": "pdf",
    },
    {
        "id": "sec-license-check",
        "url": "https://market.sec.or.th/LicenseCheck/Search?language=th",
        "kind": "html",
        "fingerprint": "visible-text-v1",
    },
    {
        "id": "sec-investor-safety-guide",
        "url": "https://www.sec.or.th/TH/Documents/SEC-E-Book-01.pdf",
        "kind": "pdf",
        "max_bytes": 20 * 1024 * 1024,
    },
    {
        "id": "pdpc-privacy-minimization",
        "url": "https://gppc.pdpc.or.th/privacy-policy/",
        "kind": "html",
    },
    {
        "id": "google-helpful-content",
        "url": "https://developers.google.com/search/docs/fundamentals/creating-helpful-content",
        "kind": "html",
        "fingerprint": "visible-text-v1",
    },
    {
        "id": "bot-debt-management-basics",
        "url": "https://www.bot.or.th/th/satang-story/managing-debt/indebtedness.html",
        "kind": "html",
    },
    {
        "id": "bot-auto-loan-restructuring",
        "url": "https://www.bot.or.th/th/satang-story/managing-debt/auto-loan-restructuring.html",
        "kind": "html",
    },
    {
        "id": "bot-secured-loan",
        "url": "https://www.bot.or.th/th/satang-story/managing-debt/secured-loan.html",
        "kind": "html",
    },
    {
        "id": "bot-hire-purchase-leasing",
        "url": "https://www.bot.or.th/th/research-and-publications/articles-and-publications/bot-magazine-issues/phrasiam-68-3/hire-purchase-leasing.html",
        "kind": "html",
    },
]
GLOBAL_MONITOR_SOURCE_IDS = frozenset(
    source["id"] for source in SOURCES
    if source.get("scope") == GLOBAL_MONITOR_SCOPE
)
MIN_VISIBLE_TEXT_BYTES = 32


class _VisibleText(HTMLParser):
    """Extract reviewable page text while ignoring volatile scripts and tokens."""

    IGNORED = {"script", "style", "noscript", "template", "svg"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self._ignored_depth = 0
        self.parts = []

    def handle_starttag(self, tag, attrs):
        if tag.lower() in self.IGNORED:
            self._ignored_depth += 1

    def handle_endtag(self, tag):
        if tag.lower() in self.IGNORED and self._ignored_depth:
            self._ignored_depth -= 1

    def handle_data(self, data):
        if not self._ignored_depth:
            self.parts.append(data)


def fingerprint_body(source, body):
    method = source.get(
        "fingerprint", "visible-text-v1" if source.get("kind") == "html" else "raw-v1")
    if method == "raw-v1":
        normalized = body
    elif method == "visible-text-v1":
        parser = _VisibleText()
        parser.feed(body.decode("utf-8", "replace"))
        normalized = " ".join(" ".join(parser.parts).split()).encode("utf-8")
        # A JS shell or script-only response has no reviewable visible claim.
        # Hashing the empty/near-empty string would turn every raw change into
        # the same false CURRENT fingerprint.  Fall back to the fetched bytes;
        # extra reviews are safer than silently missing a rendered claim drift.
        if len(normalized) < MIN_VISIBLE_TEXT_BYTES:
            method = "raw-v1"
            normalized = body
    else:
        raise ValueError("unknown fingerprint method: %s" % method)
    return method, hashlib.sha256(normalized).hexdigest()


def _https_host(value):
    try:
        parsed = urlparse(value)
    except (TypeError, ValueError):
        return None
    if (
        parsed.scheme.casefold() != "https" or not parsed.hostname
        or parsed.username is not None or parsed.password is not None
    ):
        return None
    return parsed.hostname.casefold()


def _url_identity(value):
    try:
        parsed = urlparse(value)
    except (TypeError, ValueError):
        return None
    host = _https_host(value)
    if host is None:
        return None
    port = parsed.port
    authority = host if port in (None, 443) else "%s:%s" % (host, port)
    # Several official applications select the document by query parameter
    # (for example ``?packId=...``).  Dropping that component lets a redirect to
    # a different official document look unchanged when the body hash happens
    # to match.  Fragments remain excluded because they are not sent to HTTP.
    return ("https", authority, parsed.path or "/", parsed.query)


def _media_type(value):
    return str(value or "").split(";", 1)[0].strip().casefold()


def _content_type_matches(kind, content_type):
    media_type = _media_type(content_type)
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


def validate_fetched_metadata(source, fetched, body=None):
    """Reject redirects or response shapes that no longer prove official provenance."""
    if not isinstance(fetched, dict):
        raise ValueError("fetch result is not an object")
    initial_host = _https_host(source.get("url"))
    final_host = _https_host(fetched.get("final_url"))
    if initial_host is None or final_host != initial_host:
        raise ValueError("final URL leaves the configured official host")
    status = fetched.get("http_status")
    if not isinstance(status, int) or isinstance(status, bool) or not 200 <= status < 300:
        raise ValueError("official source returned a non-success HTTP status")
    size = fetched.get("bytes")
    if not isinstance(size, int) or isinstance(size, bool) or size <= 0:
        raise ValueError("official source returned an empty or malformed body")
    max_bytes = source.get("max_bytes", MAX_BYTES)
    if (
        not isinstance(max_bytes, int) or isinstance(max_bytes, bool)
        or max_bytes <= 0 or size > max_bytes
    ):
        raise ValueError("official source body exceeds its configured byte limit")
    for field in ("raw_sha256", "sha256"):
        value = fetched.get(field)
        if (
            not isinstance(value, str) or len(value) != 64
            or any(char not in "0123456789abcdef" for char in value)
        ):
            raise ValueError("official source %s is malformed" % field)
    method = fetched.get("fingerprint_method")
    if method not in {"raw-v1", "visible-text-v1"}:
        raise ValueError("official source fingerprint method is unsupported")
    if method == "raw-v1" and fetched["raw_sha256"] != fetched["sha256"]:
        raise ValueError("raw fingerprint does not bind the fetched bytes")
    if body is not None:
        if not isinstance(body, (bytes, bytearray)):
            raise ValueError("official source body evidence is malformed")
        raw = bytes(body)
        if len(raw) != size or hashlib.sha256(raw).hexdigest() != fetched["raw_sha256"]:
            raise ValueError("official source body evidence does not match metadata")
    if not _content_type_matches(source.get("kind"), fetched.get("content_type")):
        evidence = dict(fetched)
        evidence.update({"kind": source.get("kind"), "url": source.get("url")})
        if not rss_content_type_fallback_matches(
            evidence,
            expected_url=source.get("url"),
            body=body,
            max_bytes=max_bytes,
        ):
            raise ValueError("official source content type does not match configured kind")


def classify_change(before, row):
    for field in SOURCE_IDENTITY_FIELDS:
        if field in before and before.get(field) != row.get(field):
            return "changed"
    if "final_url" in before and _url_identity(before.get("final_url")) != _url_identity(
            row.get("final_url")):
        return "changed"
    if "content_type" in before and _media_type(before.get("content_type")) != _media_type(
            row.get("content_type")):
        return "changed"
    old_hash = before.get("sha256")
    if not old_hash:
        return "new"
    old_method = before.get("fingerprint_method", "raw-v1")
    new_method = row.get("fingerprint_method", "raw-v1")
    if old_method == new_method:
        if old_hash != row["sha256"]:
            return "changed"
        # A stable visible-text fingerprint is useful for review, but it must
        # never hide a claim that moved into script/JSON-LD or another ignored
        # HTML region.  Treat any bound raw-byte drift as reviewable as well.
        # This can create conservative extra reviews on volatile pages, which
        # is preferable to silently classifying an embedded claim as current.
        old_raw_hash = before.get("raw_sha256")
        new_raw_hash = row.get("raw_sha256")
        if old_raw_hash and new_raw_hash and old_raw_hash != new_raw_hash:
            return "changed"
        return "unchanged"
    # A one-time raw -> visible-text migration is not a content change when the
    # newly fetched raw bytes still match the previous raw fingerprint.
    if old_method == "raw-v1" and old_hash == row.get("raw_sha256"):
        return "unchanged"
    return "changed"


def _strict_json_file(path):
    selected = Path(path)
    if selected.is_symlink():
        raise ValueError("JSON evidence must not be a symlink")
    before = selected.stat()
    raw = selected.read_bytes()
    after = selected.stat()
    if (
        before.st_size != after.st_size
        or before.st_mtime_ns != after.st_mtime_ns
        or len(raw) != after.st_size
    ):
        raise ValueError("JSON evidence changed while being read")

    def reject_constant(token):
        raise ValueError("non-finite JSON constant: " + token)

    def reject_duplicates(pairs):
        value = {}
        for key, item in pairs:
            if key in value:
                raise ValueError("duplicate JSON key: " + key)
            value[key] = item
        return value

    payload = json.loads(
        raw.decode("utf-8"),
        parse_constant=reject_constant,
        object_pairs_hook=reject_duplicates,
    )

    def require_finite(item):
        if isinstance(item, float) and not math.isfinite(item):
            raise ValueError("non-finite JSON number")
        if isinstance(item, dict):
            for child in item.values():
                require_finite(child)
        elif isinstance(item, list):
            for child in item:
                require_finite(child)

    require_finite(payload)
    return payload


def read_previous(path):
    try:
        return _strict_json_file(path)
    except Exception:
        return {"sources": []}


def load_review_impacts(path=DEFAULT_SOURCE_REGISTRIES):
    """Map an official URL to the content claims an owner must re-check."""
    impacts = {}
    selected_paths = (
        [path] if isinstance(path, (str, os.PathLike)) else list(path or [])
    )
    for selected in selected_paths:
        try:
            payload = _strict_json_file(selected)
        except Exception:
            continue
        items = payload.get("items") if isinstance(payload, dict) else None
        if not isinstance(items, dict):
            continue
        for content_id, item in items.items():
            if not isinstance(item, dict):
                continue
            scope = item.get("claim_scope")
            urls = item.get("official_urls")
            if (
                not isinstance(scope, str) or not scope.strip()
                or not isinstance(urls, list)
            ):
                continue
            impact = {
                "content_id": str(content_id),
                "claim_scope": scope.strip(),
            }
            for url in urls:
                if (
                    isinstance(url, str) and url.startswith("https://")
                    and impact not in impacts.setdefault(url, [])
                ):
                    impacts[url].append(impact)
    return impacts


def review_priority(source_id, impacts):
    if source_id in TIME_SENSITIVE_SOURCE_IDS:
        return "P0"
    return "P1" if impacts else "P2"


def fetch(source, timeout):
    max_bytes = source.get("max_bytes", MAX_BYTES)
    req = urllib.request.Request(
        source["url"],
        headers={
            "User-Agent": "ngernduangold-official-news-monitor/1.0",
            "Accept": "application/json, application/rss+xml, text/html;q=0.9, */*;q=0.5",
        },
    )
    with urllib.request.urlopen(req, timeout=timeout) as response:
        body = response.read(max_bytes + 1)
        if len(body) > max_bytes:
            raise ValueError("response exceeds %d bytes" % max_bytes)
        method, fingerprint = fingerprint_body(source, body)
        fetched = {
            "http_status": response.getcode(),
            "final_url": response.geturl(),
            "content_type": response.headers.get("Content-Type", ""),
            "etag": response.headers.get("ETag", ""),
            "last_modified": response.headers.get("Last-Modified", ""),
            "bytes": len(body),
            "raw_sha256": hashlib.sha256(body).hexdigest(),
            "sha256": fingerprint,
            "fingerprint_method": method,
        }
        if (
            source.get("kind") == "rss"
            and rss_content_type_is_absent(fetched["content_type"])
        ):
            fetched.update(build_rss_content_type_fallback_evidence(body))
        validate_fetched_metadata(source, fetched, body=body)
        return fetched


def atomic_json(path, payload):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    fd, temp_path = tempfile.mkstemp(prefix="newswatch-", suffix=".json",
                                     dir=os.path.dirname(path))
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
        os.replace(temp_path, path)
    except Exception:
        try:
            os.unlink(temp_path)
        except OSError:
            pass
        raise


def authorize_acknowledgements(previous, acknowledged, actor, role_path=None):
    """Reject programmatic acknowledgements: a CLI actor string is not identity proof."""
    del previous, actor, role_path
    requested = {
        SOURCE_ID_ALIASES.get(source_id.strip(), source_id.strip())
        for source_id in acknowledged
        if isinstance(source_id, str) and source_id.strip()
    }
    if not requested:
        return [], None
    raise ActionBlocked(
        "programmatic source acknowledgement is disabled because --actor cannot "
        "authenticate the human owner; review must be recorded through a separate "
        "owner-controlled process"
    )


def confined_cli_path(path, allowed_root, suffix):
    """Resolve a CLI write target beneath one explicit repository output root."""
    resolved = Path(path).resolve()
    root = Path(allowed_root).resolve()
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise ActionBlocked("output path is outside its approved directory") from exc
    if resolved == root or resolved.suffix.casefold() != suffix.casefold():
        raise ActionBlocked("output path must name a %s file" % suffix)
    return str(resolved)


def run(output, timeout, write=True, acknowledged=(), acknowledged_by=None,
        role_path=None):
    previous = read_previous(output)
    approved_acknowledgements, acknowledgement_actor = authorize_acknowledgements(
        previous, acknowledged, acknowledged_by, role_path=role_path
    )
    previous_rows = previous.get("sources")
    previous_rows = previous_rows if isinstance(previous_rows, list) else []
    attested_pending, previous_attestation_failures = validate_queue_attestation(previous)
    queue_bootstrap = bool(previous_attestation_failures)
    old = {
        item.get("id"): item for item in previous_rows
        if isinstance(item, dict) and isinstance(item.get("id"), str)
    }
    checked_at = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")
    rows = []
    changed = []
    errors = []
    for source in SOURCES:
        before = old.get(source["id"], {})
        try:
            row = dict(source)
            fetched = fetch(source, timeout)
            validate_fetched_metadata(source, fetched)
            row.update(fetched)
            row["checked_at"] = checked_at
            row["change"] = classify_change(before, row)
            if row["change"] in ("new", "changed"):
                changed.append(source["id"])
        except Exception as exc:
            row = dict(source)
            row.update({
                "checked_at": checked_at,
                "change": "error",
                "error": "%s: %s" % (type(exc).__name__, str(exc)[:240]),
            })
            for key in ("sha256", "raw_sha256", "fingerprint_method",
                        "etag", "last_modified", "final_url",
                        "content_type", "bytes", "http_status"):
                if key in before:
                    row["previous_" + key] = before[key]
            errors.append(source["id"])
        rows.append(row)

    # Removing a monitored source can erase a still-pending claim as effectively
    # as acknowledging it.  Preserve a durable error tombstone until a separate
    # owner-controlled decommission receipt can be verified.
    current_source_ids = {source["id"] for source in SOURCES}
    for removed_id in sorted(set(old) - current_source_ids):
        before = old[removed_id]
        tombstone = {
            key: before[key]
            for key in ("id", "url", "kind", "scope", "fingerprint", "max_bytes")
            if key in before
        }
        tombstone.update({
            "checked_at": checked_at,
            "change": "error",
            "error": "configured source removal requires external owner proof",
        })
        rows.append(tombstone)
        errors.append(removed_id)

    configured_ids = {
        row["id"] for row in rows
        if isinstance(row, dict) and isinstance(row.get("id"), str)
    }
    if queue_bootstrap:
        pending = set(configured_ids)
    else:
        pending = {
            SOURCE_ID_ALIASES.get(source_id, source_id)
            for source_id in attested_pending
        }
        pending.intersection_update(configured_ids)
    pending.difference_update(approved_acknowledgements)
    pending.update(changed)
    pending.update(errors)
    acknowledgement_log = [
        item for item in previous.get("acknowledgement_log", [])
        if isinstance(item, dict)
    ][-500:]
    acknowledgement_log.extend({
        "source_id": source_id,
        "acknowledged_by": acknowledgement_actor,
        "acknowledged_at": checked_at,
    } for source_id in approved_acknowledgements)
    previous_queue = {
        item.get("source_id"): item
        for item in previous.get("review_queue", [])
        if isinstance(item, dict) and isinstance(item.get("source_id"), str)
    }
    by_id = {row.get("id"): row for row in rows}
    review_queue = []
    for source_id in sorted(pending):
        row = by_id.get(source_id, {})
        prior = previous_queue.get(source_id, {})
        if source_id in errors:
            trigger = "current_fetch_error"
        elif source_id in changed:
            trigger = row.get("change", "changed")
        elif queue_bootstrap:
            trigger = "queue_integrity_fail_closed"
        else:
            trigger = prior.get("trigger", "carried_forward_unreviewed")
        item = {
            "source_id": source_id,
            "trigger": trigger,
            "pending_since": (
                checked_at if queue_bootstrap else prior.get(
                    "pending_since",
                    previous.get("checked_at")
                    if isinstance(previous.get("checked_at"), str)
                    and previous.get("checked_at").strip()
                    else checked_at,
                )
            ),
            "last_checked_at": checked_at,
            "current_state": row.get("change", "unknown"),
            "acknowledgement_status": "PENDING_OWNER_REVIEW",
        }
        if source_id in errors:
            item["current_error"] = row.get("error", "unknown")
        review_queue.append(item)
    freshness_state = (
        "ERROR" if errors else "FRESH_REVIEW_REQUIRED" if pending else "CURRENT"
    )
    queue_attestation = build_queue_attestation(
        previous.get("queue_attestation") if not queue_bootstrap else None,
        configured_source_ids=configured_ids,
        pending_ids=pending,
        acknowledged_ids=approved_acknowledgements,
        checked_at=checked_at,
        sources=rows,
        bootstrap=queue_bootstrap,
    )
    payload = {
        "schema": 3,
        "checked_at": checked_at,
        "purpose": "change detection only; review official source before publishing",
        "summary": {
            "configured_sources": len(rows),
            "checked_sources": len(rows),
            "successful_sources": len(rows) - len(errors),
            "changed_this_run": len(changed),
            "current_errors": len(errors),
            "pending_owner_reviews": len(pending),
            "acknowledged_this_run": len(approved_acknowledgements),
            "network_probe": "COMPLETE" if not errors else "PARTIAL",
            "freshness_state": freshness_state,
        },
        "changed": changed,
        "errors": errors,
        "review_required": sorted(pending),
        "review_queue": review_queue,
        "acknowledged_this_run": approved_acknowledgements,
        "acknowledgement_log": acknowledgement_log,
        "queue_integrity": {
            "state": "BOOTSTRAPPED_FAIL_CLOSED" if queue_bootstrap else "VALID",
            "previous_attestation_failures": list(previous_attestation_failures),
        },
        "queue_attestation": queue_attestation,
        "sources": rows,
    }
    if write:
        atomic_json(output, payload)
    return payload


def write_review_alert(path, payload, registry_path=DEFAULT_SOURCE_REGISTRIES):
    """Write an actionable packet without acknowledging any source on the owner's behalf."""
    pending = payload.get("review_required", [])
    if not pending:
        try:
            os.unlink(path)
        except FileNotFoundError:
            pass
        return
    by_id = {row.get("id"): row for row in payload.get("sources", [])}
    queue = {
        item.get("source_id"): item
        for item in payload.get("review_queue", [])
        if isinstance(item, dict)
    }
    impact_map = load_review_impacts(registry_path)
    summary = payload.get("summary") if isinstance(payload.get("summary"), dict) else {}
    review_rows = []
    for source_id in pending:
        row = by_id.get(source_id, {})
        impacts = impact_map.get(row.get("url"), [])
        review_rows.append((review_priority(source_id, impacts), source_id, row, impacts))
    review_rows.sort(key=lambda item: (item[0], item[1]))
    lines = [
        "# Owner review packet — official sources",
        "",
        "> สถานะ: **BLOCKED — OWNER REVIEW REQUIRED**",
        "> เอกสารนี้เป็นรายการตรวจ ไม่ใช่ acknowledgement และไม่ให้อำนาจเผยแพร่หรือ deploy",
        "",
        "ตรวจเมื่อ: `%s`" % payload.get("checked_at", "unknown"),
        "ตรวจเครือข่าย: `%s` · สำเร็จ `%s/%s` · current errors `%s` · changed รอบนี้ `%s` · pending `%s`" % (
            summary.get("network_probe", "UNKNOWN"),
            summary.get("successful_sources", "?"),
            summary.get("configured_sources", "?"),
            summary.get("current_errors", len(payload.get("errors", []))),
            summary.get("changed_this_run", len(payload.get("changed", []))),
            summary.get("pending_owner_reviews", len(pending)),
        ),
        "acknowledged_this_run: `%s`" % len(payload.get("acknowledged_this_run", [])),
        "",
        "## วิธีตัดสินแต่ละรายการ",
        "",
        "1. เปิด URL ทางการโดยตรงและเทียบเฉพาะ claim scope ที่ระบุ",
        "2. เลือก verdict หนึ่งค่า: `UNCHANGED`, `UPDATE_REQUIRED`, หรือ `BLOCK`",
        "3. บันทึกหลักฐาน/วันที่ผ่านกระบวนการ owner-controlled แยกต่างหาก; CLI นี้ห้าม ack",
        "4. หากเป็น `UPDATE_REQUIRED` หรือ `BLOCK` ให้คง publication block จนแก้เนื้อหาและ rebuild ใหม่",
        "",
    ]
    current_priority = None
    for priority, source_id, row, impacts in review_rows:
        if priority != current_priority:
            lines.extend(["## %s" % priority, ""])
            current_priority = priority
        meta = queue.get(source_id, {})
        state = (
            "error: %s" % row.get("error", "unknown")
            if source_id in payload.get("errors", [])
            else row.get("change", "pending")
        )
        lines.extend([
            "- [ ] `%s` — current `%s`; trigger `%s`; pending since `%s`" % (
                source_id,
                state,
                meta.get("trigger", "unknown"),
                meta.get("pending_since", "unknown"),
            ),
            "  - Official source: %s" % row.get("url", "URL unavailable"),
        ])
        if impacts:
            for impact in impacts:
                lines.append("  - Impact: `%s` — %s" % (
                    impact["content_id"], impact["claim_scope"]
                ))
        elif source_id in GLOBAL_MONITOR_SOURCE_IDS:
            lines.append(
                "  - Impact: `GLOBAL_MONITOR_ONLY` — เฝ้าระวังภาพรวม ไม่ผูกกับ "
                "content_id/claim และไม่บล็อกคอนเทนต์ที่ไม่เกี่ยวข้อง"
            )
        else:
            lines.append(
                "  - Impact: `UNMAPPED` — ต้องระบุเนื้อหาที่ได้รับผลก่อน owner acknowledgement"
            )
        lines.extend([
            "  - Owner verdict: [ ] `UNCHANGED`  [ ] `UPDATE_REQUIRED`  [ ] `BLOCK`",
            "  - Evidence/date: ______________________________",
            "",
        ])
    lines.extend([
        "## Exit criteria",
        "",
        "- [ ] ทั้ง %d รายการมี owner verdict และหลักฐาน" % len(pending),
        "- [ ] รายการ `UPDATE_REQUIRED` ถูกแก้และผ่าน source/content gates ใหม่",
        "- [ ] snapshot ใหม่มี current errors = 0 และ review_required = 0",
        "- [ ] release ถูก rebuild หลังการแก้ claim ใด ๆ",
        "",
        "ไฟล์นี้จะคงอยู่จนกระบวนการที่เจ้าของควบคุมบันทึกการทบทวนครบ",
        "",
    ])
    os.makedirs(os.path.dirname(path), exist_ok=True)
    fd, temp_path = tempfile.mkstemp(prefix="newsreview-", suffix=".md",
                                     dir=os.path.dirname(path))
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            handle.write("\n".join(lines))
        os.replace(temp_path, path)
    except Exception:
        try:
            os.unlink(temp_path)
        except OSError:
            pass
        raise


def strict_exit_code(payload):
    """Separate an observed source block from an invalid monitor result.

    Exit 1 is pending owner review, exit 2 is a current source fetch/parse
    blocker, and exit 3 means the snapshot itself violates the monitor contract.
    """
    contract = validate_official_snapshot_contract(
        payload, freshness_hours=24, strict_all_rows=True
    )
    state_only_prefixes = (
        "relevant official source changed:",
        "relevant official source error:",
        "relevant official source review is pending:",
    )
    if any(not issue.startswith(state_only_prefixes) for issue in contract.failures):
        return 3
    if payload.get("errors"):
        return 2
    if payload.get("review_required"):
        return 1
    return 0


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default=DEFAULT_OUT)
    parser.add_argument("--timeout", type=int, default=25)
    parser.add_argument("--stdout", action="store_true", help="do not write snapshot")
    parser.add_argument("--strict", action="store_true",
                        help="fail on source errors or any unacknowledged review item")
    parser.add_argument("--alert", default=DEFAULT_ALERT,
                        help="durable review-request file")
    parser.add_argument("--ack", action="append", default=[], metavar="SOURCE_ID",
                        help="legacy flag; programmatic acknowledgement is disabled")
    parser.add_argument("--actor",
                        help="legacy audit label; not accepted as owner identity proof")
    args = parser.parse_args()
    try:
        output = confined_cli_path(
            args.output, ROOT_PATH / "automation-log" / "knowledge-base", ".json")
        alert = confined_cli_path(
            args.alert, ROOT_PATH / "automation-log" / "cowork-inbox", ".md")
        payload = run(output, args.timeout, write=not args.stdout,
                      acknowledged=args.ack, acknowledged_by=args.actor)
    except ActionBlocked as exc:
        parser.error(str(exc))
    if not args.stdout:
        write_review_alert(alert, payload)
    print(json.dumps({
        "checked_at": payload["checked_at"],
        "sources": len(payload["sources"]),
        "summary": payload.get("summary", {}),
        "changed": payload["changed"],
        "errors": payload["errors"],
        "review_required": payload["review_required"],
        "output": None if args.stdout else output,
    }, ensure_ascii=False))
    return strict_exit_code(payload) if args.strict else 0


if __name__ == "__main__":
    try:
        _exit_code = main()
    except SystemExit as exc:
        _raw_code = exc.code if isinstance(exc.code, int) else 1
        _exit_code = 0 if _raw_code == 0 else 3
    except Exception as exc:
        print("official news monitor RUNNER_FAILED: %s" % str(exc)[:240], file=sys.stderr)
        _exit_code = 3
    raise SystemExit(_exit_code)
