#!/usr/bin/env python3
"""Fail-closed novelty audit for WEEK-CONTENT-PACK_20260824-30 r5.

The audit is deliberately read-only.  It compares the exact public copy and
candidate media against the append-only publication identity overlay, the
content manifest/library, and historical media.  It never records a claim or
infers that a draft was published.  The optional ``--write-receipt`` export is
limited to an explicitly named local novelty-receipt JSON and replaces it
atomically; it never mutates publication history.

"Near duplicate" is a reproducible structural signal, not a claim of universal
semantic originality.  Thai copy uses normalized character trigrams plus
SequenceMatcher.  Images/video frames use a strict DCT perceptual hash and
aligned low-resolution pixel error.  Incomplete publication identity remains a
hard blocker even when no candidate collision is detected.
"""

from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
from difflib import SequenceMatcher
import hashlib
import html
import importlib.util
import json
import math
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import unicodedata
from typing import Iterable

import numpy as np
from PIL import Image


ROOT = Path(__file__).resolve().parents[1]
PACK = ROOT / "automation-log" / "WEEK-CONTENT-PACK_20260824-30.json"
LEDGER = ROOT / "automation-log" / "post-ledger.jsonl"
BINDINGS = ROOT / "automation-log" / "post-ledger-identity-bindings.jsonl"
IDENTITY_EVIDENCE = (
    ROOT / "automation-log" / "dedup-evidence"
    / "post-ledger-identity-sources-v1.json"
)
IDENTITY_EVIDENCE_V2 = (
    ROOT / "automation-log" / "dedup-evidence"
    / "post-ledger-identity-sources-v2.json"
)
COLLISION_TOMBSTONES = (
    ROOT / "automation-log" / "post-ledger-collision-tombstones.json"
)
MANIFEST = ROOT / ".system_control" / "content_manifest.json"
PUBLISHED_MEDIA = ROOT / "automation-log" / "media-qa" / "published-media.json"
POLICY = ROOT / ".system_control" / "policy.json"
NOVELTY_RECEIPT_DIR = ROOT / "automation-log" / "dedup-evidence"
NOVELTY_RECEIPT_NAME_RE = re.compile(
    r"^WEEK-CONTENT-R5-NOVELTY-RECEIPT_\d{8}\.json$"
)

EXPECTED_PACK_ID = "week-content-20260824-30-r5"
EXPECTED_IDS = (
    "wk36-sf01", "wk36-sf02", "qt-12", "wk36-sf03", "wk36-sf04",
    "qt-13", "wk36-sf05",
)
MEDIA_SUFFIXES = {".mp4", ".mov", ".m4v", ".jpg", ".jpeg", ".png", ".webp"}
VIDEO_SUFFIXES = {".mp4", ".mov", ".m4v"}
IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp"}
SHA256_RE = re.compile(r"^[0-9A-F]{64}$")
THAI_RE = re.compile(r"[\u0e00-\u0e7f]")
URL_RE = re.compile(r"https?://\S+|www\.\S+|atth\.me/\S+", re.I)
TAG_RE = re.compile(r"<[^>]+>")
BOILERPLATE = (
    "ข้อมูลเพื่อการศึกษา",
    "ภาพประกอบผลิตด้วย AI",
    "ผลิตด้วย AI",
    "ไม่ใช่คำแนะนำทางการเงิน",
    "ไม่ใช่คำแนะนำการลงทุน",
    "มีลิงก์พันธมิตร",
)
SKIP_JSON_KEY_HINTS = {
    "id", "path", "asset", "sha256", "hash", "receipt", "status", "url",
    "slug", "source", "reviewer", "evidence", "codec", "format", "voice",
    "engine", "language", "campaign", "utm", "post_id", "dedup_key",
}


@dataclass(frozen=True)
class TextRecord:
    source: str
    field: str
    scope: str
    text: str
    norm: str
    candidate_id: str = ""
    channel: str = ""
    published: bool = False


@dataclass(frozen=True)
class MediaRecord:
    source: str
    path: str
    sha256: str
    scope: str
    candidate_id: str = ""
    channel: str = ""
    published: bool = False
    available: bool = False


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest().upper()


def _canonical_json_sha(value) -> str:
    raw = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(raw).hexdigest().upper()


def _load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def _relative(path: Path) -> str:
    return path.resolve().relative_to(ROOT.resolve()).as_posix()


def _resolve_receipt_output(value: str) -> Path:
    raw = Path(value)
    output = (raw if raw.is_absolute() else ROOT / raw).resolve()
    receipt_dir = NOVELTY_RECEIPT_DIR.resolve()
    if output.parent != receipt_dir:
        raise ValueError(
            "receipt output must be directly inside automation-log/dedup-evidence"
        )
    if not NOVELTY_RECEIPT_NAME_RE.fullmatch(output.name):
        raise ValueError(
            "receipt output must match WEEK-CONTENT-R5-NOVELTY-RECEIPT_YYYYMMDD.json"
        )
    if not receipt_dir.is_dir():
        raise ValueError("receipt output directory does not exist")
    return output


def _write_receipt_atomic(path: Path, result: dict) -> None:
    payload = (
        json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    ).encode("utf-8")
    temporary: Path | None = None
    try:
        descriptor, name = tempfile.mkstemp(
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
        )
        temporary = Path(name)
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        temporary = None
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()


def _clean_visible(text: str) -> str:
    value = html.unescape(str(text or "")).replace("<br>", "\n")
    value = URL_RE.sub(" ", value)
    value = TAG_RE.sub(" ", value)
    value = re.sub(r"#[^\s#]+", " ", value)
    for phrase in BOILERPLATE:
        value = value.replace(phrase, " ")
    return re.sub(r"\s+", " ", value).strip()


def normalize_text(text: str) -> str:
    value = unicodedata.normalize("NFKC", _clean_visible(text)).casefold()
    return "".join(ch for ch in value if ch.isalnum())


def _trigrams(value: str) -> set[str]:
    if len(value) < 3:
        return {value} if value else set()
    return {value[index:index + 3] for index in range(len(value) - 2)}


def text_similarity(left: str, right: str, *, normalized: bool = False) -> dict:
    a = str(left) if normalized else normalize_text(left)
    b = str(right) if normalized else normalize_text(right)
    if not a or not b:
        return {"exact": False, "ratio": 0.0, "jaccard": 0.0,
                "containment": 0.0, "near": False}
    exact = a == b
    ga, gb = _trigrams(a), _trigrams(b)
    intersection = len(ga & gb)
    union = len(ga | gb)
    jaccard = intersection / union if union else 0.0
    containment = intersection / min(len(ga), len(gb)) if ga and gb else 0.0
    # Every near rule below requires far more trigram overlap than this prefilter.
    # Avoid quadratic SequenceMatcher work on long, clearly unrelated documents.
    ratio = (
        SequenceMatcher(None, a, b, autojunk=False).ratio()
        if exact or jaccard >= 0.20 or containment >= 0.50
        else 0.0
    )
    near = (
        not exact
        and min(len(a), len(b)) >= 24
        and (
            (ratio >= 0.88 and jaccard >= 0.70)
            or (containment >= 0.90 and ratio >= 0.72)
        )
    )
    return {
        "exact": exact,
        "ratio": round(ratio, 6),
        "jaccard": round(jaccard, 6),
        "containment": round(containment, 6),
        "near": near,
    }


def _public_variants(pack: dict) -> list[TextRecord]:
    variants = []
    for day in pack.get("days") or []:
        candidate_id = str(day.get("candidate_id") or "")
        for field, channel in (("threads_text", "threads"),
                               ("facebook_text", "facebook")):
            text = day.get(field)
            if isinstance(text, str) and normalize_text(text):
                variants.append(TextRecord(
                    source=_relative(PACK), field=f"{candidate_id}.{field}",
                    scope="candidate", text=text, norm=normalize_text(text),
                    candidate_id=candidate_id, channel=channel,
                ))
        tiktok = day.get("tiktok_draft") or {}
        parts = [tiktok.get("hook"), tiktok.get("voiceover")]
        parts.extend(tiktok.get("onscreen_text") or [])
        parts.append(tiktok.get("end_card"))
        text = "\n".join(str(value) for value in parts if isinstance(value, str))
        variants.append(TextRecord(
            source=_relative(PACK), field=f"{candidate_id}.tiktok",
            scope="candidate", text=text, norm=normalize_text(text),
            candidate_id=candidate_id, channel="tiktok",
        ))
        image_spec = day.get("image_spec") or {}
        overlay = image_spec.get("exact_overlay_text")
        if isinstance(overlay, str) and normalize_text(overlay):
            variants.append(TextRecord(
                source=_relative(PACK), field=f"{candidate_id}.image_overlay",
                scope="candidate", text=overlay, norm=normalize_text(overlay),
                candidate_id=candidate_id, channel="quote_image",
            ))
    return variants


def _iter_json_strings(value, selector: str = "$", key: str = ""):
    if isinstance(value, dict):
        for name, child in value.items():
            yield from _iter_json_strings(child, f"{selector}.{name}", str(name))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            yield from _iter_json_strings(child, f"{selector}[{index}]", key)
    elif isinstance(value, str):
        low = key.casefold()
        if any(hint in low for hint in SKIP_JSON_KEY_HINTS):
            return
        if THAI_RE.search(value) and len(normalize_text(value)) >= 20:
            yield selector, value


def _markdown_segments(path: Path) -> Iterable[tuple[str, str]]:
    text = path.read_text(encoding="utf-8", errors="strict")
    for index, block in enumerate(re.split(r"\n\s*\n", text), 1):
        value = block.strip()
        if not value or value.startswith("```"):
            continue
        if THAI_RE.search(value) and len(normalize_text(value)) >= 24:
            yield f"block[{index}]", value


def _knowledge_records(path: Path) -> list[TextRecord]:
    records = []
    rel = _relative(path)
    for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not re.match(r"^\|\s*20\d\d-\d\d-\d\d\s*\|", line):
            continue
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if len(cells) < 5:
            continue
        candidate_id = cells[1]
        for index, channel in ((3, "threads"), (4, "facebook")):
            value = cells[index].replace("<br>", "\n")
            if len(normalize_text(value)) < 20:
                continue
            records.append(TextRecord(
                source=rel, field=f"line[{line_no}].{channel}",
                scope="knowledge_library", text=value, norm=normalize_text(value),
                candidate_id=candidate_id, channel=channel,
            ))
    return records


def _import_post_ledger():
    path = ROOT / "automation-log" / "post_ledger.py"
    module_dir = str(path.parent)
    if module_dir not in sys.path:
        sys.path.insert(0, module_dir)
    spec = importlib.util.spec_from_file_location("week_r5_post_ledger", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("post ledger module cannot be loaded")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _ledger_text_records(rows: list[dict], identity_evidence: dict,
                         virtual_bindings=None) -> list[TextRecord]:
    records = []
    rel = _relative(LEDGER)
    for line_no, row in enumerate(rows, 1):
        if not isinstance(row, dict):
            continue
        text_norm = str(row.get("text_norm") or "").strip()
        if text_norm:
            records.append(TextRecord(
                source=rel, field=f"line[{line_no}].text_norm",
                scope="ledger_native", text=text_norm, norm=text_norm,
                channel=str(row.get("channel") or ""), published=True,
            ))
    for record in identity_evidence.get("records") or []:
        value = record.get("value") if isinstance(record, dict) else None
        if not isinstance(value, dict) or not isinstance(value.get("exact_text"), str):
            continue
        text = value["exact_text"]
        records.append(TextRecord(
            source=_relative(IDENTITY_EVIDENCE),
            field=f"records[{record.get('evidence_id')}].value.exact_text",
            scope="ledger_identity_overlay", text=text, norm=normalize_text(text),
            candidate_id=str(value.get("id") or ""),
            channel=str(value.get("channel") or ""), published=True,
        ))
    for line_no, binding in sorted((virtual_bindings or {}).items()):
        if not isinstance(binding, dict) or binding.get("kind") != "text_hash":
            continue
        if not 1 <= int(line_no) <= len(rows) or rows[int(line_no) - 1].get("text_norm"):
            continue
        text_norm = str(binding.get("text_norm") or "")
        if not text_norm:
            continue
        row = rows[int(line_no) - 1]
        records.append(TextRecord(
            source=str(binding.get("source_path") or _relative(BINDINGS)),
            field=str(binding.get("source_field") or f"line[{line_no}].binding"),
            scope="ledger_identity_overlay", text=text_norm, norm=text_norm,
            channel=str(row.get("channel") or ""), published=True,
        ))
    return records


def _manifest_text_records(manifest: dict) -> list[TextRecord]:
    records = []
    rel = _relative(MANIFEST)
    for index, item in enumerate(manifest.get("items") or []):
        if not isinstance(item, dict):
            continue
        candidate_id = str(item.get("id") or "")
        posted = item.get("posted") if isinstance(item.get("posted"), dict) else {}
        values = []
        if isinstance(item.get("topic_th"), str):
            values.append(("topic_th", "topic", item["topic_th"]))
        captions = item.get("captions")
        if isinstance(captions, dict):
            values.extend((f"captions.{channel}", str(channel), text)
                          for channel, text in captions.items()
                          if isinstance(text, str))
        for field, channel, text in values:
            if len(normalize_text(text)) < 20:
                continue
            records.append(TextRecord(
                source=rel, field=f"items[{index}].{field}",
                scope="content_manifest", text=text, norm=normalize_text(text),
                candidate_id=candidate_id, channel=channel,
                published=bool(posted.get(channel)) if channel in posted else any(
                    bool(value) for value in posted.values()
                ),
            ))
    return records


def _receipt_copy_records() -> list[TextRecord]:
    records = []
    for path in sorted((ROOT / "automation-log" / "media-qa").glob("*.json")):
        if path.name.endswith("-r5.json") or path.name.startswith(
            "WEEK-TIKTOK-QUOTE-CANDIDATES_MANIFEST_R5"
        ):
            continue
        try:
            payload = _load_json(path)
        except (OSError, UnicodeError, json.JSONDecodeError):
            continue
        source = payload.get("source_binding") if isinstance(payload, dict) else None
        if not isinstance(source, dict):
            continue
        candidate_id = str(source.get("candidate_id") or "")
        copies = source.get("exact_visible_copy")
        if not isinstance(copies, list):
            continue
        text = "\n".join(str(value) for value in copies if isinstance(value, str))
        if len(normalize_text(text)) < 20:
            continue
        records.append(TextRecord(
            source=_relative(path), field="source_binding.exact_visible_copy",
            scope="superseded_receipt", text=text, norm=normalize_text(text),
            candidate_id=candidate_id, channel="media_visible_copy",
        ))
    return records


def build_text_corpus(rows: list[dict], evidence: dict, manifest: dict,
                      virtual_bindings=None):
    records = []
    records.extend(_ledger_text_records(rows, evidence, virtual_bindings))
    records.extend(_manifest_text_records(manifest))
    records.extend(_receipt_copy_records())

    for path in sorted((ROOT / "automation-log").glob("KNOWLEDGE-POSTS*.md")):
        records.extend(_knowledge_records(path))

    markdown_globs = (
        "automation-log/content-packages/*.md",
        "automation-log/_social-stage/*.md",
        "automation-log/social-queue/**/*.md",
        "automation-log/post-ready/**/*.txt",
    )
    corpus_files = {LEDGER, IDENTITY_EVIDENCE, MANIFEST}
    for pattern in markdown_globs:
        for path in sorted(ROOT.glob(pattern)):
            corpus_files.add(path)
            try:
                segments = _markdown_segments(path)
                for field, text in segments:
                    records.append(TextRecord(
                        source=_relative(path), field=field,
                        scope="historical_library", text=text,
                        norm=normalize_text(text),
                    ))
            except (OSError, UnicodeError):
                continue

    json_paths = [
        ROOT / "social-autopost" / "content_map.json",
        ROOT / "social-autopost" / "feed_content_map.json",
        ROOT / "reels" / "schedule.json",
        ROOT / "tiktok-pipeline" / "clip_registry.json",
        ROOT / "tiktok-pipeline" / "ready-for-cowork" / "production-manifest.json",
    ]
    json_paths.extend(sorted((ROOT / "tiktok-pipeline" / "drafts").glob("**/*.json")))
    for path in json_paths:
        if not path.is_file():
            continue
        corpus_files.add(path)
        try:
            payload = _load_json(path)
        except (OSError, UnicodeError, json.JSONDecodeError):
            continue
        for field, text in _iter_json_strings(payload):
            records.append(TextRecord(
                source=_relative(path), field=field, scope="structured_library",
                text=text, norm=normalize_text(text),
            ))
    for path in sorted((ROOT / "tiktok-pipeline" / "captions").glob("*.txt")):
        corpus_files.add(path)
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeError):
            continue
        if len(normalize_text(text)) >= 20:
            records.append(TextRecord(
                source=_relative(path), field="document",
                scope="structured_library", text=text, norm=normalize_text(text),
            ))

    # Identical library fragments are represented once per provenance location.
    unique = {}
    for record in records:
        if not record.norm:
            continue
        unique[(record.source, record.field, record.norm)] = record
    return list(unique.values()), sorted(corpus_files)


def _text_match_record(candidate: TextRecord, historical: TextRecord, score: dict):
    return {
        "candidate_id": candidate.candidate_id,
        "channel": candidate.channel,
        "candidate_field": candidate.field,
        "source": historical.source,
        "source_field": historical.field,
        "source_scope": historical.scope,
        "source_candidate_id": historical.candidate_id,
        "source_published": historical.published,
        "ratio": score["ratio"],
        "jaccard": score["jaccard"],
        "containment": score["containment"],
    }


def audit_text(variants: list[TextRecord], corpus: list[TextRecord]) -> dict:
    historical_exact = []
    historical_near = []
    expected_lineage = []
    best = []
    for candidate in variants:
        best_item = None
        best_score = -1.0
        for historical in corpus:
            score = text_similarity(candidate.norm, historical.norm, normalized=True)
            ranking = max(score["ratio"], score["containment"])
            if ranking > best_score:
                best_score = ranking
                best_item = _text_match_record(candidate, historical, score)
            if not (score["exact"] or score["near"]):
                continue
            item = _text_match_record(candidate, historical, score)
            item["match"] = "EXACT" if score["exact"] else "NEAR"
            if (
                historical.scope == "superseded_receipt"
                and historical.candidate_id == candidate.candidate_id
            ):
                item["classification"] = "EXPECTED_SAME_CANDIDATE_SUPERSEDED_LINEAGE"
                expected_lineage.append(item)
            elif score["exact"]:
                item["classification"] = "BLOCKING_HISTORICAL_EXACT_COLLISION"
                historical_exact.append(item)
            else:
                item["classification"] = "BLOCKING_HISTORICAL_NEAR_COLLISION"
                historical_near.append(item)
        if best_item:
            best.append(best_item)

    cross_exact = []
    cross_near = []
    expected_adaptations = []
    for index, left in enumerate(variants):
        for right in variants[index + 1:]:
            score = text_similarity(left.norm, right.norm, normalized=True)
            if not (score["exact"] or score["near"]):
                continue
            item = {
                "left": left.field, "left_channel": left.channel,
                "right": right.field, "right_channel": right.channel,
                "ratio": score["ratio"], "jaccard": score["jaccard"],
                "containment": score["containment"],
                "match": "EXACT" if score["exact"] else "NEAR",
            }
            if left.candidate_id == right.candidate_id:
                item["classification"] = "EXPECTED_SAME_CANDIDATE_CHANNEL_ADAPTATION"
                expected_adaptations.append(item)
            elif score["exact"]:
                item["classification"] = "BLOCKING_CROSS_CANDIDATE_EXACT_COLLISION"
                cross_exact.append(item)
            else:
                item["classification"] = "BLOCKING_CROSS_CANDIDATE_NEAR_COLLISION"
                cross_near.append(item)
    return {
        "candidate_variants": len(variants),
        "historical_records": len(corpus),
        "unique_historical_normal_forms": len({record.norm for record in corpus}),
        "historical_exact_collisions": historical_exact,
        "historical_near_collisions": historical_near,
        "cross_candidate_exact_collisions": cross_exact,
        "cross_candidate_near_collisions": cross_near,
        "expected_same_candidate_adaptations": expected_adaptations,
        "expected_same_candidate_superseded_lineage": expected_lineage,
        "best_historical_match_per_variant": best,
        "threshold": {
            "minimum_normalized_characters": 24,
            "near_rule": "ratio>=0.88 and trigram_jaccard>=0.70, or trigram_containment>=0.90 and ratio>=0.72",
            "boilerplate_removed": list(BOILERPLATE),
        },
    }


def _current_media(pack: dict) -> list[MediaRecord]:
    records = []
    for day in pack.get("days") or []:
        candidate_id = str(day.get("candidate_id") or "")
        tiktok = (day.get("tiktok_draft") or {}).get("candidate_asset") or {}
        records.append(MediaRecord(
            source=_relative(PACK), path=str(tiktok.get("path") or ""),
            sha256=str(tiktok.get("sha256") or "").upper(), scope="candidate",
            candidate_id=candidate_id, channel="tiktok", available=True,
        ))
        assets = (day.get("image_spec") or {}).get("candidate_assets") or {}
        for key, channel in (("facebook_instagram", "facebook_instagram"),
                             ("pinterest", "pinterest")):
            value = assets.get(key)
            if not isinstance(value, dict):
                continue
            records.append(MediaRecord(
                source=_relative(PACK), path=str(value.get("path") or ""),
                sha256=str(value.get("sha256") or "").upper(), scope="candidate",
                candidate_id=candidate_id, channel=channel, available=True,
            ))
    return records


def _candidate_from_path(path: str) -> str:
    low = path.casefold()
    for candidate_id in EXPECTED_IDS:
        if candidate_id.casefold() in low:
            return candidate_id
    return ""


def _add_media_record(index: dict[str, dict], record: MediaRecord):
    key = record.path.replace("\\", "/")
    if not key or "/week-20260824-30-r5/" in "/" + key:
        return
    existing = index.get(key)
    priority = {"published_registry": 5, "content_manifest": 4,
                "qa_receipt": 3, "canonical_history": 2}
    if existing is None or priority.get(record.scope, 0) > priority.get(existing.scope, 0):
        index[key] = record


def build_media_corpus(manifest: dict, published_media: dict):
    index = {}
    reference_errors = []
    source_files = {MANIFEST, PUBLISHED_MEDIA}
    for item in published_media.get("items") or []:
        if not isinstance(item, dict):
            continue
        path = str(item.get("asset") or "").replace("\\", "/")
        sha = str(item.get("sha256") or "").upper()
        full = ROOT / path
        status = str(item.get("status") or "")
        _add_media_record(index, MediaRecord(
            source=_relative(PUBLISHED_MEDIA), path=path, sha256=sha,
            scope="published_registry", candidate_id=str(item.get("content_id") or ""),
            published="published" in status, available=full.is_file(),
        ))
    for item in manifest.get("items") or []:
        if not isinstance(item, dict) or not isinstance(item.get("reel"), str):
            continue
        path = item["reel"].replace("\\", "/")
        full = ROOT / path
        sha = _sha256(full) if full.is_file() else ""
        posted = item.get("posted") if isinstance(item.get("posted"), dict) else {}
        _add_media_record(index, MediaRecord(
            source=_relative(MANIFEST), path=path, sha256=sha,
            scope="content_manifest", candidate_id=str(item.get("id") or ""),
            published=any(bool(value) for value in posted.values()),
            available=full.is_file(),
        ))
    for receipt in sorted((ROOT / "automation-log" / "media-qa").glob("*.json")):
        if receipt.name.endswith("-r5.json") or receipt.name.startswith(
            "WEEK-TIKTOK-QUOTE-CANDIDATES_MANIFEST_R5"
        ) or receipt.name == "published-media.json":
            continue
        try:
            payload = _load_json(receipt)
        except (OSError, UnicodeError, json.JSONDecodeError):
            continue
        if not isinstance(payload, dict) or not isinstance(payload.get("asset"), str):
            continue
        source_files.add(receipt)
        path = payload["asset"].replace("\\", "/")
        full = ROOT / path
        source = payload.get("source_binding") if isinstance(payload.get("source_binding"), dict) else {}
        novelty = payload.get("novelty_review") if isinstance(payload.get("novelty_review"), dict) else {}
        candidate_id = str(source.get("candidate_id") or novelty.get("content_id") or _candidate_from_path(path))
        _add_media_record(index, MediaRecord(
            source=_relative(receipt), path=path,
            sha256=str(payload.get("sha256") or "").upper(), scope="qa_receipt",
            candidate_id=candidate_id, available=full.is_file(),
        ))

    canonical_patterns = (
        "reels/**/*", "media/quotes/**/*", "media/pins/**/*", "_vidout/clean/**/*",
    )
    for pattern in canonical_patterns:
        for full in sorted(ROOT.glob(pattern)):
            if not full.is_file() or full.suffix.casefold() not in MEDIA_SUFFIXES:
                continue
            path = _relative(full)
            if path in index:
                continue
            _add_media_record(index, MediaRecord(
                source=path, path=path, sha256=_sha256(full),
                scope="canonical_history", candidate_id=_candidate_from_path(path),
                available=True,
            ))
    records = []
    for path, record in sorted(index.items()):
        full = ROOT / path
        actual = (
            record.sha256
            if record.scope in {"canonical_history", "content_manifest"}
            else (_sha256(full) if full.is_file() else "")
        )
        if record.sha256 and actual and record.sha256 != actual:
            reference_errors.append({
                "path": path, "source": record.source,
                "category": "HISTORICAL_MEDIA_REFERENCE_HASH_MISMATCH",
            })
        records.append(record)
    return records, reference_errors, sorted(source_files)


_DCT_MATRIX = None


def _dct_matrix(size: int = 32):
    global _DCT_MATRIX
    if _DCT_MATRIX is None:
        rows = []
        for k in range(size):
            alpha = math.sqrt(1 / size) if k == 0 else math.sqrt(2 / size)
            rows.append([
                alpha * math.cos(math.pi * (2 * n + 1) * k / (2 * size))
                for n in range(size)
            ])
        _DCT_MATRIX = np.asarray(rows, dtype=np.float64)
    return _DCT_MATRIX


def _phash(array: np.ndarray) -> int:
    data = np.asarray(array, dtype=np.float64).reshape(32, 32)
    matrix = _dct_matrix()
    low = (matrix @ data @ matrix.T)[:8, :8]
    values = low.flatten()
    median = float(np.median(values[1:]))
    bits = values > median
    result = 0
    for bit in bits:
        result = (result << 1) | int(bool(bit))
    return result


def _image_frame(path: Path) -> np.ndarray:
    with Image.open(path) as image:
        canvas = image.convert("L")
        canvas.thumbnail((32, 32), Image.Resampling.LANCZOS)
        framed = Image.new("L", (32, 32), 0)
        framed.paste(canvas, ((32 - canvas.width) // 2, (32 - canvas.height) // 2))
        return np.asarray(framed, dtype=np.uint8)


def _video_duration(path: Path) -> float:
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True,
    )
    return float(result.stdout.decode("utf-8", errors="strict").strip())


def _video_frames(path: Path, count: int = 5) -> list[np.ndarray]:
    duration = _video_duration(path)
    rate = max(count / max(duration, 0.001), 0.01)
    vf = (
        f"fps={rate:.9f},"
        "scale=32:32:force_original_aspect_ratio=decrease,"
        "pad=32:32:(ow-iw)/2:(oh-ih)/2:color=black,format=gray"
    )
    result = subprocess.run(
        ["ffmpeg", "-v", "error", "-i", str(path), "-vf", vf,
         "-frames:v", str(count), "-f", "rawvideo", "-pix_fmt", "gray", "-"],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True,
    )
    size = 32 * 32
    raw = result.stdout
    if len(raw) < size or len(raw) % size:
        raise RuntimeError(f"invalid raw frame payload for {path}")
    return [
        np.frombuffer(raw[offset:offset + size], dtype=np.uint8).reshape(32, 32).copy()
        for offset in range(0, len(raw), size)
    ]


def _fingerprint(path: Path):
    suffix = path.suffix.casefold()
    frames = _image_frame(path) if suffix in IMAGE_SUFFIXES else _video_frames(path)
    if isinstance(frames, np.ndarray):
        frames = [frames]
    return [{"hash": _phash(frame), "frame": frame} for frame in frames]


def _hamming(left: int, right: int) -> int:
    return (left ^ right).bit_count()


def perceptual_similarity(left, right, left_type: str, right_type: str) -> dict:
    best_rows = []
    for first in left:
        candidates = []
        for second in right:
            hamming = _hamming(first["hash"], second["hash"])
            mae = float(np.mean(np.abs(
                first["frame"].astype(np.int16) - second["frame"].astype(np.int16)
            )))
            candidates.append((hamming, mae))
        best_rows.append(min(candidates))
    hammings = [row[0] for row in best_rows]
    maes = [row[1] for row in best_rows]
    median_hamming = float(np.median(hammings))
    median_mae = float(np.median(maes))
    if left_type == right_type == "video":
        strong = sum(1 for hamming, mae in best_rows if hamming <= 6 and mae <= 18.0)
        near = median_hamming <= 3.0 and strong >= math.ceil(len(best_rows) * 0.6)
    elif left_type == right_type == "image":
        strong = int(hammings[0] <= 5 and maes[0] <= 18.0)
        near = bool(strong)
    else:
        strong = sum(1 for hamming, mae in best_rows if hamming <= 4 and mae <= 15.0)
        near = strong >= 1 and min(hammings) <= 4 and min(maes) <= 15.0
    return {
        "near": near,
        "median_phash_hamming": round(median_hamming, 3),
        "median_gray_mae": round(median_mae, 3),
        "minimum_phash_hamming": min(hammings),
        "minimum_gray_mae": round(min(maes), 3),
        "strong_frame_matches": strong,
        "left_frames": len(left),
        "right_frames": len(right),
    }


def _media_type(path: str) -> str:
    suffix = Path(path).suffix.casefold()
    return "video" if suffix in VIDEO_SUFFIXES else "image"


def _media_match(left: MediaRecord, right: MediaRecord, score=None):
    item = {
        "candidate_id": left.candidate_id, "candidate_channel": left.channel,
        "candidate_asset": left.path, "source_asset": right.path,
        "source_scope": right.scope, "source_candidate_id": right.candidate_id,
        "source_published": right.published,
    }
    if score:
        item.update(score)
    return item


def audit_media(current: list[MediaRecord], historical: list[MediaRecord], *, perceptual=True):
    exact = []
    expected_exact_lineage = []
    current_cross_exact = []
    for index, left in enumerate(current):
        for right in current[index + 1:]:
            if left.sha256 == right.sha256:
                current_cross_exact.append(_media_match(left, right))
        for right in historical:
            if left.sha256 and left.sha256 == right.sha256:
                item = _media_match(left, right)
                if right.candidate_id == left.candidate_id and right.candidate_id:
                    item["classification"] = "EXPECTED_SAME_CANDIDATE_SUPERSEDED_LINEAGE"
                    expected_exact_lineage.append(item)
                else:
                    item["classification"] = "BLOCKING_HISTORICAL_EXACT_COLLISION"
                    exact.append(item)

    cross_near = []
    historical_near = []
    expected_near_lineage = []
    fingerprint_errors = []
    fingerprint_count = 0
    if perceptual:
        cache = {}

        def get(record):
            nonlocal fingerprint_count
            if record.path not in cache:
                try:
                    cache[record.path] = _fingerprint(ROOT / record.path)
                    fingerprint_count += 1
                except (OSError, ValueError, subprocess.SubprocessError, RuntimeError) as exc:
                    cache[record.path] = None
                    fingerprint_errors.append({
                        "path": record.path, "category": "FINGERPRINT_UNAVAILABLE",
                        "error_type": type(exc).__name__,
                    })
            return cache[record.path]

        for index, left in enumerate(current):
            left_fp = get(left)
            if left_fp is None:
                continue
            for right in current[index + 1:]:
                right_fp = get(right)
                if right_fp is None:
                    continue
                score = perceptual_similarity(
                    left_fp, right_fp, _media_type(left.path), _media_type(right.path)
                )
                if score["near"]:
                    item = _media_match(left, right, score)
                    if left.candidate_id == right.candidate_id:
                        item["classification"] = "EXPECTED_SAME_CANDIDATE_CHANNEL_ADAPTATION"
                        expected_near_lineage.append(item)
                    else:
                        item["classification"] = "BLOCKING_CROSS_CANDIDATE_NEAR_COLLISION"
                        cross_near.append(item)
            for right in historical:
                if not right.available or left.sha256 == right.sha256:
                    continue
                right_fp = get(right)
                if right_fp is None:
                    continue
                score = perceptual_similarity(
                    left_fp, right_fp, _media_type(left.path), _media_type(right.path)
                )
                if not score["near"]:
                    continue
                item = _media_match(left, right, score)
                if right.candidate_id == left.candidate_id and right.candidate_id:
                    item["classification"] = "EXPECTED_SAME_CANDIDATE_SUPERSEDED_LINEAGE"
                    expected_near_lineage.append(item)
                else:
                    item["classification"] = "BLOCKING_HISTORICAL_NEAR_COLLISION"
                    historical_near.append(item)
    return {
        "candidate_assets": len(current),
        "historical_assets": len(historical),
        "historical_assets_available_for_perceptual_review": sum(
            1 for record in historical if record.available
        ),
        "fingerprinted_assets": fingerprint_count,
        "historical_exact_collisions": exact,
        "historical_near_collisions": historical_near,
        "cross_candidate_exact_collisions": current_cross_exact,
        "cross_candidate_near_collisions": cross_near,
        "expected_same_candidate_exact_lineage": expected_exact_lineage,
        "expected_same_candidate_near_lineage": expected_near_lineage,
        "fingerprint_errors": fingerprint_errors,
        "perceptual_threshold": {
            "video": "median pHash hamming <=3 and >=60% frames pHash<=6 plus gray MAE<=18",
            "image": "pHash hamming<=5 and gray MAE<=18",
            "cross_media": "at least one frame pHash hamming<=4 and gray MAE<=15",
            "samples_per_video": 5,
        },
    }


def _corpus_fingerprint(paths: Iterable[Path]) -> dict:
    digest = hashlib.sha256()
    count = 0
    size = 0
    for path in sorted({Path(value).resolve() for value in paths}):
        if not path.is_file():
            continue
        rel = _relative(path)
        raw = path.read_bytes()
        digest.update(rel.encode("utf-8"))
        digest.update(b"\0")
        digest.update(raw)
        digest.update(b"\0")
        count += 1
        size += len(raw)
    return {"sha256": digest.hexdigest().upper(), "file_count": count,
            "bytes": size}


def _identity_audit(pack: dict, variants: list[TextRecord], policy: dict) -> dict:
    identity = policy.get("public_identity") if isinstance(policy, dict) else None
    findings = []
    if not isinstance(identity, dict):
        return {"status": "FAIL", "fields_checked": 0,
                "findings": ["PUBLIC_IDENTITY_POLICY_MISSING"]}
    if pack.get("public_identity") != identity.get("canonical_name"):
        findings.append("PACK_PUBLIC_IDENTITY_MISMATCH")
    if identity.get("page_only") is not True or identity.get("entity_type") != "Organization":
        findings.append("PAGE_ONLY_ORGANIZATION_POLICY_INVALID")
    patterns = []
    for value in identity.get("forbidden_personal_claim_patterns") or []:
        try:
            patterns.append(re.compile(str(value), re.I))
        except re.error:
            findings.append("IDENTITY_PATTERN_INVALID")
    speakers = [str(value).casefold() for value in identity.get("forbidden_public_speakers") or []]
    for record in variants:
        if any(pattern.search(record.text) for pattern in patterns):
            findings.append(f"PERSONAL_PUBLIC_VOICE:{record.field}")
        low = record.text.casefold()
        if any(re.search(r"(?<![a-z0-9_])" + re.escape(name) + r"(?![a-z0-9_])", low)
               for name in speakers):
            findings.append(f"AGENT_AS_PUBLIC_SPEAKER:{record.field}")
    return {
        "status": "PASS" if not findings else "FAIL",
        "fields_checked": len(variants), "findings": sorted(set(findings)),
        "canonical_binding_sha256": _canonical_json_sha({
            "pack_public_identity": pack.get("public_identity"),
            "policy_public_identity": identity,
        }),
    }


def run_audit(*, perceptual=True) -> dict:
    pack = _load_json(PACK)
    manifest = _load_json(MANIFEST)
    published_media = _load_json(PUBLISHED_MEDIA)
    policy = _load_json(POLICY)
    evidence = _load_json(IDENTITY_EVIDENCE)
    ledger_rows = [json.loads(line) for line in LEDGER.read_text(encoding="utf-8").splitlines()]

    blockers = []
    findings = []
    ids = tuple(str(day.get("candidate_id") or "") for day in pack.get("days") or [])
    if pack.get("pack_id") != EXPECTED_PACK_ID or ids != EXPECTED_IDS:
        blockers.append("PACK_ID_OR_CANDIDATE_SET_CHANGED")
    if pack.get("state") != "DRAFT_ONLY":
        blockers.append("PACK_NOT_DRAFT_ONLY")

    variants = _public_variants(pack)
    identity_audit = _identity_audit(pack, variants, policy)
    if identity_audit["status"] != "PASS":
        blockers.append("PUBLIC_IDENTITY_OVERLAY_FAIL")

    ledger_module = _import_post_ledger()
    completeness = ledger_module.permanent_dedup_completeness(LEDGER)
    ledger_integrity = ledger_module.inspect_ledger(LEDGER)
    titleloan = [
        group for group in completeness.get("duplicate_identities") or []
        if group.get("channel") == "tiktok" and group.get("identity") == "titleloan"
    ]
    if completeness.get("identity_coverage_state") != "COMPLETE":
        blockers.append("LEDGER_IDENTITY_COVERAGE_INCOMPLETE")
    if titleloan:
        blockers.append("PERMANENT_DEDUP_DUPLICATE_TIKTOK_TITLELOAN")
    if completeness.get("identity_binding_state") != "PASS":
        blockers.append("IDENTITY_BINDING_OVERLAY_INVALID")
    if completeness.get("collision_tombstone_state") == "INVALID":
        blockers.append("COLLISION_TOMBSTONE_REGISTRY_INVALID")

    text_corpus, text_files = build_text_corpus(
        ledger_rows, evidence, manifest,
        ledger_integrity.get("identity_bindings") or {},
    )
    text_audit = audit_text(variants, text_corpus)
    text_collision_count = sum(len(text_audit[key]) for key in (
        "historical_exact_collisions", "historical_near_collisions",
        "cross_candidate_exact_collisions", "cross_candidate_near_collisions",
    ))
    if text_collision_count:
        blockers.append("R5_TEXT_EXACT_OR_NEAR_DUPLICATE_COLLISION")

    current_media = _current_media(pack)
    for record in current_media:
        full = ROOT / record.path
        if not full.is_file() or _sha256(full) != record.sha256:
            blockers.append("R5_MEDIA_ASSET_OR_HASH_MISMATCH")
            break
    historical_media, reference_errors, media_files = build_media_corpus(
        manifest, published_media
    )
    if reference_errors:
        findings.append("HISTORICAL_MEDIA_REFERENCE_ERRORS_PRESENT")
    media_audit = audit_media(current_media, historical_media, perceptual=perceptual)
    media_audit["historical_reference_errors"] = reference_errors
    media_collision_count = sum(len(media_audit[key]) for key in (
        "historical_exact_collisions", "historical_near_collisions",
        "cross_candidate_exact_collisions", "cross_candidate_near_collisions",
    ))
    if media_collision_count:
        blockers.append("R5_MEDIA_EXACT_OR_NEAR_DUPLICATE_COLLISION")
    if media_audit["fingerprint_errors"]:
        blockers.append("MEDIA_PERCEPTUAL_FINGERPRINT_INCOMPLETE")

    permanent_index = ledger_module.load_index(LEDGER)
    permanent_clip_identities = {
        identity for (_channel, identity) in permanent_index.get("all_by_clip", {})
    }
    candidate_identity_collisions = sorted(set(ids) & permanent_clip_identities)
    if candidate_identity_collisions:
        blockers.append("R5_CANDIDATE_ID_COLLIDES_WITH_PERMANENT_CLIP_IDENTITY")

    key_inputs = [PACK, LEDGER, BINDINGS, IDENTITY_EVIDENCE,
                  IDENTITY_EVIDENCE_V2, COLLISION_TOMBSTONES, MANIFEST,
                  PUBLISHED_MEDIA, POLICY]
    inputs = {
        _relative(path): _sha256(path) if path.is_file() else "MISSING"
        for path in key_inputs
    }
    blockers = sorted(set(blockers))
    r5_collision_count = text_collision_count + media_collision_count + len(
        candidate_identity_collisions
    )
    if r5_collision_count:
        verdict = "BLOCKED_R5_COLLISION_DETECTED"
    elif blockers:
        verdict = "BLOCKED_SYSTEM_HISTORY_NO_R5_COLLISION_DETECTED"
    else:
        verdict = "PASS_SCOPED_DETERMINISTIC_NOVELTY"
    return {
        "schema_version": 1,
        "audit_kind": "LOCAL_ONLY_R5_NOVELTY_GUARD",
        "verdict": verdict,
        "pack": {
            "path": _relative(PACK), "id": pack.get("pack_id"),
            "sha256": _sha256(PACK), "state": pack.get("state"),
            "candidate_ids": list(ids),
        },
        "scope": {
            "candidate_count": len(ids), "public_channel_variants": len(variants),
            "candidate_media_assets": len(current_media),
            "no_publication_status_inferred": True,
            "append_only_history_mutated": False,
            "semantic_universality_claimed": False,
        },
        "identity": identity_audit,
        "permanent_dedup": {
            "state": completeness.get("state"),
            "integrity_state": completeness.get("integrity_state"),
            "identity_coverage_state": completeness.get("identity_coverage_state"),
            "complete_rows": completeness.get("complete_rows"),
            "incomplete_rows": completeness.get("incomplete_rows"),
            "identity_rows": completeness.get("identity_rows"),
            "coverage_percent": completeness.get("coverage_percent"),
            "identity_binding_state": completeness.get("identity_binding_state"),
            "applied_identity_bindings": completeness.get("applied_identity_bindings"),
            "collision_tombstone_state": completeness.get("collision_tombstone_state"),
            "collision_tombstone_count": completeness.get("collision_tombstone_count"),
            "collision_tombstoned_non_reusable": completeness.get(
                "collision_tombstoned_non_reusable"
            ),
            "duplicate_identity_groups": completeness.get("duplicate_identity_groups"),
            "titleloan_tiktok_duplicate": titleloan,
            "candidate_identity_collisions": candidate_identity_collisions,
        },
        "text_novelty": text_audit,
        "media_novelty": media_audit,
        "counts": {
            "r5_text_exact_collisions": len(text_audit["historical_exact_collisions"])
                + len(text_audit["cross_candidate_exact_collisions"]),
            "r5_text_near_collisions": len(text_audit["historical_near_collisions"])
                + len(text_audit["cross_candidate_near_collisions"]),
            "r5_media_exact_collisions": len(media_audit["historical_exact_collisions"])
                + len(media_audit["cross_candidate_exact_collisions"]),
            "r5_media_near_collisions": len(media_audit["historical_near_collisions"])
                + len(media_audit["cross_candidate_near_collisions"]),
            "expected_text_adaptations": len(text_audit["expected_same_candidate_adaptations"]),
            "expected_text_superseded_lineage": len(text_audit["expected_same_candidate_superseded_lineage"]),
            "expected_media_exact_lineage": len(media_audit["expected_same_candidate_exact_lineage"]),
            "expected_media_near_lineage": len(media_audit["expected_same_candidate_near_lineage"]),
            "r5_collision_total": r5_collision_count,
            "system_blockers": len(blockers),
        },
        "corpus": {
            "text": _corpus_fingerprint(text_files),
            "extracted_text_inventory_sha256": _canonical_json_sha([
                {
                    "source": record.source, "field": record.field,
                    "scope": record.scope, "candidate_id": record.candidate_id,
                    "channel": record.channel, "published": record.published,
                    "normalized_text_sha256": hashlib.sha256(
                        record.norm.encode("utf-8")
                    ).hexdigest().upper(),
                }
                for record in sorted(
                    text_corpus,
                    key=lambda value: (value.source, value.field, value.norm),
                )
            ]),
            "media_sources": _corpus_fingerprint(media_files),
            "historical_media_hash_inventory_sha256": _canonical_json_sha([
                asdict(record) for record in sorted(
                    historical_media, key=lambda value: (value.path, value.sha256)
                )
            ]),
            "candidate_text_inventory_sha256": _canonical_json_sha([
                {
                    "candidate_id": record.candidate_id,
                    "channel": record.channel,
                    "normalized_text_sha256": hashlib.sha256(
                        record.norm.encode("utf-8")
                    ).hexdigest().upper(),
                }
                for record in variants
            ]),
            "candidate_media_hash_inventory_sha256": _canonical_json_sha([
                asdict(record) for record in current_media
            ]),
            "key_inputs": inputs,
        },
        "findings": sorted(set(findings)),
        "blockers": blockers,
        "limitations": [
            f"{completeness.get('incomplete_rows')} legacy publication rows lack complete permanent-dedup identity at this snapshot; absence of an r5 match cannot prove universal historical novelty.",
            "Near-copy detection is deterministic structural similarity, not semantic equivalence or a universal originality claim.",
            "No human audio listening and no external platform inspection were performed.",
            "Draft, library, scheduled, and published evidence are kept distinct; this receipt does not claim any r5 candidate was posted.",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true")
    parser.add_argument(
        "--write-receipt",
        metavar="PATH",
        help=(
            "atomically replace one local "
            "WEEK-CONTENT-R5-NOVELTY-RECEIPT_YYYYMMDD.json"
        ),
    )
    parser.add_argument("--no-perceptual", action="store_true",
                        help="skip perceptual media comparison (fail closed in final use)")
    args = parser.parse_args()
    if args.write_receipt and args.no_perceptual:
        parser.error("--write-receipt requires the full perceptual audit")
    receipt_output = None
    if args.write_receipt:
        try:
            receipt_output = _resolve_receipt_output(args.write_receipt)
        except ValueError as exc:
            parser.error(str(exc))
    result = run_audit(perceptual=not args.no_perceptual)
    if receipt_output is not None:
        try:
            _write_receipt_atomic(receipt_output, result)
        except OSError as exc:
            parser.error(f"cannot write receipt atomically: {exc}")
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        counts = result["counts"]
        print(
            f"{result['verdict']}: r5 exact text/media="
            f"{counts['r5_text_exact_collisions']}/{counts['r5_media_exact_collisions']}, "
            f"near text/media={counts['r5_text_near_collisions']}/{counts['r5_media_near_collisions']}, "
            f"blockers={counts['system_blockers']}"
        )
        for blocker in result["blockers"]:
            print("BLOCKER", blocker)
    return 0 if result["verdict"].startswith("PASS") else 2


if __name__ == "__main__":
    raise SystemExit(main())
