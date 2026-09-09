"""Deterministic, local-only audits for blocked Markdown content packs.

The functions in this module recompute evidence from candidate bytes and the
allowlisted local corpus.  A receipt is never treated as proof of its own
counters.  The near-duplicate heuristic is intentionally conservative and is
only a provisional local signal; it is not a universal semantic-newness claim.
"""

from __future__ import annotations

from difflib import SequenceMatcher
import hashlib
import json
from pathlib import Path
import re
import unicodedata

AUDIT_ENGINE_VERSION = "content-pack-audit-v2"
# Capture the exact source bytes observed by this module at import time.  Live
# admission code compares this identity with the hash-bound receipt and a fresh
# disk read so a long-running process cannot execute one engine while archiving
# different bytes as its evidence.
AUDIT_ENGINE_SOURCE_SHA256 = hashlib.sha256(
    Path(__file__).read_bytes()
).hexdigest().upper()

CHANNELS = ("Threads", "Facebook", "TikTok")
DISCLOSURE = "เงินเดือนสมองทอง · ข้อมูลเพื่อการศึกษา · ร่างข้อความผลิตด้วย AI"
MIN_SUBSTANTIVE_NORMALIZED_CHARS = 80
MIN_SUBSTANTIVE_UNIQUE_CHARS = 15
MIN_TOPIC_PLATFORM_TRIGRAM_COVERAGE = 0.12
MIN_TOPIC_COMBINED_TRIGRAM_COVERAGE = 0.30

URL_RE = re.compile(
    r"https?://\S+|www\.\S+|(?:atth\.me|bit\.ly|tinyurl\.com)/\S+", re.I
)
COMMERCIAL_RE = re.compile(
    r"\baffiliate\b|\butm_[a-z]+\b|[?&](?:ref|aff|affiliate|tracking)="
    r"|ลิงก์พันธมิตร|ค่าคอมมิชชั่น|ติดตามการขาย",
    re.I,
)
GUARANTEE_RE = re.compile(
    r"การันตี|รับรองผล|ผ่านแน่นอน|ชัวร์|ไร้ความเสี่ยง|ได้ผลแน่นอน"
    r"|กำไรแน่นอน|รวยแน่นอน|\b100\s*%\b",
    re.I,
)
LIVE_LINK_RE = re.compile(
    r"ลิงก์|คลิก|ไบโอ|โปรไฟล์|ทัก|\bbio\b|\bdm\b|\bline\b",
    re.I,
)
FIRST_PERSON_TERMS = ("ผม", "ฉัน", "ดิฉัน", "ข้าพเจ้า", "พวกเรา", "ของเรา", "เรา")
COMPLY_TRIGGERS = (
    "ฟรีไม่มี", "ฟรี 100", "ผ่านแน่นอน", "อนุมัติแน่นอน", "การันตี",
    "รับรองผล", "รวยเร็ว", "รวยไว", "ได้เงินชัวร์", "ปิดหนี้ได้ 100",
    "ไร้ความเสี่ยง", "คลิกเลย", "กู้ผ่านทุก", "ผ่านทุกราย", "ดอกถูกที่สุด",
    "ดีที่สุดในไทย",
)
COMPLY_CAVEAT_HINTS = (
    "เช็ก", "เช็ค", "สอบถาม", "ขึ้นกับ", "แล้วแต่", "อีกที", "ตรวจสอบ",
    "ประมาณ", "ราว",
)
COMPLY_RESPONSIBLE_LINE = "กู้เท่าที่จำเป็นและชำระคืนไหว"
COMPLY_LENDING_TERMS = ("กู้", "สินเชื่อ", "บัตรเครดิต")
COMPLY_BANNED_LENDING_PATTERNS = (
    r"ใคร\s*[ๆ]?\s*ก็?กู้ได้",
    r"ไม่ดู\s*เครดิต",
    r"ไม่เช[็็]ค\s*(?:เครดิต\s*)?บูโร",
    r"ไม่เช[็็]ค.{0,20}(?:กู้|สินเชื่อ)",
    r"ติดบูโร\s*ก็?\s*กู้ได้",
    r"กู้\s*(?:เงิน)?\s*(?:เรื่อง)?\s*ง่าย",
    r"อนุมัติ\s*ง่าย",
    r"แค่\s*(?:มีรถ|ถือเล่มทะเบียน).{0,40}กู้ได้",
    r"รับเงินสดได้ทันที",
    r"ของมันต้องมี",
    r"อยากได้ต้องได้",
    r"ไฮโซก่อน.{0,20}ค่อยผ่อนทีหลัง",
)
COMPLY_NEGATABLE = {"การันตี", "รับรองผล"}
COMPLY_NEGATION_CUES = ("ไม่", "ปฏิเสธ")
COMPLY_SENTENCE_END = ".!?\n"
SKIP_JSON_KEY_HINTS = {
    "id", "path", "asset", "sha256", "hash", "receipt", "status", "url",
    "slug", "source", "reviewer", "evidence", "codec", "format", "voice",
    "engine", "language", "campaign", "utm", "post_id", "dedup_key",
}


class ContentPackAuditError(RuntimeError):
    """Candidate or corpus bytes cannot support a deterministic local audit."""


def _comply_negated(text: str, position: int) -> bool:
    left = text[max(0, position - 20):position]
    cue = max((left.rfind(value) for value in COMPLY_NEGATION_CUES), default=-1)
    return cue >= 0 and not any(char in COMPLY_SENTENCE_END for char in left[cue:])


def _comply_check(text: str) -> bool:
    """Self-contained blocking subset of the page compliance check.

    Audit admission never imports the broader comply_gate module: its optional
    generation and post-ledger paths are outside this deterministic proof.
    """
    for trigger in COMPLY_TRIGGERS:
        if trigger not in text:
            continue
        if trigger in COMPLY_NEGATABLE:
            position = 0
            blocked = False
            while True:
                hit = text.find(trigger, position)
                if hit < 0:
                    break
                if not _comply_negated(text, hit):
                    blocked = True
                    break
                position = hit + len(trigger)
            if not blocked:
                continue
        return False
    if any(
        re.search(pattern, text, flags=re.IGNORECASE)
        for pattern in COMPLY_BANNED_LENDING_PATTERNS
    ):
        return False
    if re.search(r"\d+\s*%", text) and not any(
        hint in text for hint in COMPLY_CAVEAT_HINTS
    ):
        return False
    if re.search(r"\b0\s*%", text):
        return False
    if any(term in text for term in COMPLY_LENDING_TERMS) and (
        COMPLY_RESPONSIBLE_LINE not in text
    ):
        return False
    return True


def normalize_text(text: str) -> str:
    value = unicodedata.normalize("NFKC", str(text or "")).casefold()
    return "".join(
        char for char in value
        if char.isalnum() or unicodedata.category(char).startswith("M")
    )


def _trigrams(value: str) -> set[str]:
    if len(value) < 3:
        return {value} if value else set()
    return {value[index:index + 3] for index in range(len(value) - 2)}


def text_similarity(left: str, right: str) -> dict:
    a = normalize_text(left)
    b = normalize_text(right)
    if not a or not b:
        return {
            "exact": False, "ratio": 0.0, "jaccard": 0.0,
            "containment": 0.0, "near": False,
        }
    exact = a == b
    ga, gb = _trigrams(a), _trigrams(b)
    common = len(ga & gb)
    union = len(ga | gb)
    jaccard = common / union if union else 0.0
    containment = common / min(len(ga), len(gb)) if ga and gb else 0.0
    ratio = (
        SequenceMatcher(None, a, b, autojunk=False).ratio()
        if exact or jaccard >= 0.20 or containment >= 0.50 else 0.0
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


def _load_json(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ContentPackAuditError("corpus JSON is unreadable: " + str(path)) from exc


def _load_json_content(payload: bytes, label: str):
    try:
        return json.loads(payload.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise ContentPackAuditError("corpus JSON is unreadable: " + label) from exc


def _walk_topic_strings(value, key: str = ""):
    if isinstance(value, dict):
        for child_key, child in value.items():
            yield from _walk_topic_strings(child, str(child_key))
    elif isinstance(value, list):
        for child in value:
            yield from _walk_topic_strings(child, key)
    elif isinstance(value, str) and key.casefold() in {
        "topic", "topic_th", "title", "angle", "novel_angle",
    }:
        if len(normalize_text(value)) >= 8:
            yield value


def _walk_copy_strings(value, key: str = ""):
    if isinstance(value, dict):
        for child_key, child in value.items():
            yield from _walk_copy_strings(child, str(child_key))
    elif isinstance(value, list):
        for child in value:
            yield from _walk_copy_strings(child, key)
    elif isinstance(value, str):
        low = key.casefold()
        if any(hint in low for hint in SKIP_JSON_KEY_HINTS):
            return
        if len(normalize_text(value)) >= 24:
            yield value


def _markdown_segments(path: Path):
    try:
        text = path.read_text(encoding="utf-8-sig", errors="strict")
    except (OSError, UnicodeError) as exc:
        raise ContentPackAuditError("corpus Markdown is unreadable: " + str(path)) from exc
    for block in re.split(r"\n\s*\n", text):
        block = block.strip()
        if block and not block.startswith("```") and len(normalize_text(block)) >= 24:
            yield block


def _corpus_markdown_paths(root: Path, candidate_path: str) -> list[Path]:
    paths = list((root / "automation-log" / "content-packages").glob("*.md"))
    paths.extend(
        (root / "automation-log" / "cc-outbox").glob("LOCAL-CONTENT-PACK_*.md")
    )
    candidate = (root / candidate_path).resolve()
    return sorted(
        {
            path.resolve() for path in paths
            if path.is_file() and path.resolve() != candidate
        },
        key=lambda path: path.relative_to(root.resolve()).as_posix().casefold(),
    )


def build_topic_baseline(
    root: Path, candidate_path: str, corpus_bytes: dict[str, bytes] | None = None,
) -> list[str]:
    root = root.resolve()
    values: list[str] = []
    for relative in (
        ".system_control/content_manifest.json",
        ".system_control/content_calendar.json",
    ):
        if corpus_bytes is not None:
            if relative not in corpus_bytes:
                raise ContentPackAuditError("required topic snapshot is missing: " + relative)
            payload = _load_json_content(corpus_bytes[relative], relative)
        else:
            path = root / relative
            if not path.is_file():
                raise ContentPackAuditError("required topic corpus is missing: " + relative)
            payload = _load_json(path)
        values.extend(_walk_topic_strings(payload))
    ledger = root / "automation-log" / "post-ledger.jsonl"
    ledger_relative = "automation-log/post-ledger.jsonl"
    if corpus_bytes is not None:
        if ledger_relative not in corpus_bytes:
            raise ContentPackAuditError("required topic snapshot is missing: " + ledger_relative)
        try:
            ledger_text = corpus_bytes[ledger_relative].decode("utf-8")
        except UnicodeError as exc:
            raise ContentPackAuditError("post ledger snapshot is unreadable") from exc
    else:
        if not ledger.is_file():
            raise ContentPackAuditError("required topic corpus is missing: automation-log/post-ledger.jsonl")
        try:
            ledger_text = ledger.read_text(encoding="utf-8")
        except (OSError, UnicodeError) as exc:
            raise ContentPackAuditError("post ledger is unreadable") from exc
    try:
        for line_number, line in enumerate(ledger_text.splitlines(), 1):
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ContentPackAuditError(
                    "post ledger JSON is invalid at line %d" % line_number
                ) from exc
            values.extend(_walk_topic_strings(row))
            if isinstance(row, dict):
                for key in ("text_first80", "text_norm"):
                    text = row.get(key)
                    if isinstance(text, str) and len(normalize_text(text)) >= 8:
                        values.append(text)
    except UnicodeError as exc:
        raise ContentPackAuditError("post ledger is unreadable") from exc
    if corpus_bytes is None:
        markdown_items = [
            (path.relative_to(root).as_posix(), path.read_bytes())
            for path in _corpus_markdown_paths(root, candidate_path)
        ]
    else:
        markdown_items = sorted(
            (relative, payload) for relative, payload in corpus_bytes.items()
            if relative != candidate_path and (
                (relative.startswith("automation-log/content-packages/") and relative.endswith(".md"))
                or (
                    relative.startswith("automation-log/cc-outbox/LOCAL-CONTENT-PACK_")
                    and relative.endswith(".md")
                )
            )
        )
    for relative, raw in markdown_items:
        try:
            text = raw.decode("utf-8-sig")
        except UnicodeError as exc:
            raise ContentPackAuditError("corpus Markdown is unreadable: " + relative) from exc
        first = next((line for line in text.splitlines() if line.strip()), "")
        if len(normalize_text(first)) >= 8:
            values.append(re.sub(r"^#\s*", "", first).strip())
        values.extend(
            match.strip()
            for match in re.findall(r"(?m)^##\s+\d+\.\s*(.+)$", text)
            if len(normalize_text(match)) >= 8
        )
    unique = {normalize_text(value): value for value in values if normalize_text(value)}
    return [unique[key] for key in sorted(unique)]


def build_copy_baseline(
    root: Path, candidate_path: str, corpus_bytes: dict[str, bytes] | None = None,
) -> list[str]:
    root = root.resolve()
    values: list[str] = []
    for relative in (
        ".system_control/content_manifest.json",
        ".system_control/content_calendar.json",
    ):
        if corpus_bytes is not None:
            if relative not in corpus_bytes:
                raise ContentPackAuditError("required copy snapshot is missing: " + relative)
            payload = _load_json_content(corpus_bytes[relative], relative)
        else:
            path = root / relative
            if not path.is_file():
                raise ContentPackAuditError("required copy corpus is missing: " + relative)
            payload = _load_json(path)
        values.extend(_walk_copy_strings(payload))
    ledger = root / "automation-log" / "post-ledger.jsonl"
    ledger_relative = "automation-log/post-ledger.jsonl"
    if corpus_bytes is not None:
        if ledger_relative not in corpus_bytes:
            raise ContentPackAuditError("required copy snapshot is missing: " + ledger_relative)
        try:
            ledger_text = corpus_bytes[ledger_relative].decode("utf-8")
        except UnicodeError as exc:
            raise ContentPackAuditError("post ledger snapshot is unreadable") from exc
    else:
        if not ledger.is_file():
            raise ContentPackAuditError("required copy corpus is missing: automation-log/post-ledger.jsonl")
        try:
            ledger_text = ledger.read_text(encoding="utf-8")
        except (OSError, UnicodeError) as exc:
            raise ContentPackAuditError("post ledger is unreadable") from exc
    try:
        for line_number, line in enumerate(ledger_text.splitlines(), 1):
            if not line.strip():
                continue
            try:
                values.extend(_walk_copy_strings(json.loads(line)))
            except json.JSONDecodeError as exc:
                raise ContentPackAuditError(
                    "post ledger JSON is invalid at line %d" % line_number
                ) from exc
    except UnicodeError as exc:
        raise ContentPackAuditError("post ledger is unreadable") from exc
    if corpus_bytes is None:
        for path in _corpus_markdown_paths(root, candidate_path):
            values.extend(_markdown_segments(path))
    else:
        for relative, raw in sorted(corpus_bytes.items()):
            if relative == candidate_path or not (
                (relative.startswith("automation-log/content-packages/") and relative.endswith(".md"))
                or (
                    relative.startswith("automation-log/cc-outbox/LOCAL-CONTENT-PACK_")
                    and relative.endswith(".md")
                )
            ):
                continue
            try:
                text = raw.decode("utf-8-sig")
            except UnicodeError as exc:
                raise ContentPackAuditError("corpus Markdown is unreadable: " + relative) from exc
            for block in re.split(r"\n\s*\n", text):
                block = block.strip()
                if block and not block.startswith("```") and len(normalize_text(block)) >= 24:
                    values.append(block)
    unique = {normalize_text(value): value for value in values if normalize_text(value)}
    return [unique[key] for key in sorted(unique)]


def _collision_counts(candidates: list[tuple[str, str]], baseline: list[str]) -> dict:
    exact = []
    near = []
    for candidate_id, candidate in candidates:
        for prior in baseline:
            score = text_similarity(candidate, prior)
            if score["exact"]:
                exact.append((candidate_id, normalize_text(prior)[:80]))
            elif score["near"]:
                near.append((candidate_id, normalize_text(prior)[:80]))
    cross_exact = []
    cross_near = []
    for left_index, (left_id, left) in enumerate(candidates):
        for right_id, right in candidates[left_index + 1:]:
            if left_id == right_id:
                continue
            score = text_similarity(left, right)
            if score["exact"]:
                cross_exact.append((left_id, right_id))
            elif score["near"]:
                cross_near.append((left_id, right_id))
    return {
        "historical_exact_collisions": len(exact),
        "historical_near_collisions": len(near),
        "cross_family_exact_collisions": len(cross_exact),
        "cross_family_near_collisions": len(cross_near),
        "collision_examples": {
            "historical_exact": exact[:3], "historical_near": near[:3],
            "cross_exact": cross_exact[:3], "cross_near": cross_near[:3],
        },
    }


def audit_topics(
    root: Path, candidate_path: str, families: list[dict],
    corpus_bytes: dict[str, bytes] | None = None,
) -> dict:
    baseline = build_topic_baseline(root, candidate_path, corpus_bytes)
    candidates = [(str(row["family_id"]), str(row["topic"])) for row in families]
    counts = _collision_counts(candidates, baseline)
    return {
        "topic_candidates": len(candidates),
        "topic_baseline_records": len(baseline),
        "historical_exact_collisions": counts["historical_exact_collisions"],
        "historical_near_collisions": counts["historical_near_collisions"],
        "cross_family_exact_collisions": counts["cross_family_exact_collisions"],
        "cross_family_near_collisions": counts["cross_family_near_collisions"],
        "collision_examples": counts["collision_examples"],
    }


def parse_pack_text(text: str, expected_family_ids: list[str]) -> list[dict]:
    text = str(text).replace("\r\n", "\n").replace("\r", "\n")
    matches = list(re.finditer(r"(?m)^##\s+(\d+)\.\s+.+$", text))
    blocks = []
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        block = text[match.start():end]
        family = re.search(r"(?m)^- `family_id`: `([^`]+)`$", block)
        if family is None:
            raise ContentPackAuditError("candidate topic block has no exact family_id")
        copies = {}
        for channel in CHANNELS:
            copy = re.search(
                r"(?ms)^### " + re.escape(channel)
                + r"\n\n(.*?)(?=^### |^---\s*$|\Z)",
                block,
            )
            if copy is None:
                raise ContentPackAuditError(
                    family.group(1) + " has no exact " + channel + " section"
                )
            copies[channel.casefold()] = copy.group(1).strip()
        blocks.append({"family_id": family.group(1), "copies": copies})
    actual_ids = [block["family_id"] for block in blocks]
    if actual_ids != list(expected_family_ids) or len(set(actual_ids)) != len(actual_ids):
        raise ContentPackAuditError("candidate pack family order/set is not exact")
    variants = []
    for block in blocks:
        for channel in ("threads", "facebook", "tiktok"):
            copy = block["copies"][channel]
            normalized = normalize_text(copy)
            unique_chars = {char for char in normalized if char.isalnum()}
            if (
                len(normalized) < MIN_SUBSTANTIVE_NORMALIZED_CHARS
                or len(unique_chars) < MIN_SUBSTANTIVE_UNIQUE_CHARS
                or DISCLOSURE not in copy
            ):
                raise ContentPackAuditError(
                    block["family_id"] + "." + channel
                    + " is not substantive page-only copy"
                )
            variants.append({
                "family_id": block["family_id"], "channel": channel,
                "copy": copy, "norm": normalized,
            })
    if len({item["norm"] for item in variants}) != len(variants):
        raise ContentPackAuditError("candidate platform copy is not distinct")
    return variants


def parse_pack(pack_path: Path, expected_family_ids: list[str]) -> list[dict]:
    try:
        text = pack_path.read_text(encoding="utf-8", errors="strict")
    except (OSError, UnicodeError) as exc:
        raise ContentPackAuditError("candidate pack is unreadable") from exc
    return parse_pack_text(text, expected_family_ids)


def _count_terms(text: str, terms: tuple[str, ...]) -> int:
    return sum(text.count(term) for term in terms)


def audit_pack(
    root: Path, candidate_path: str, families: list[dict], pack_path: Path,
) -> dict:
    try:
        pack_text = pack_path.read_text(encoding="utf-8", errors="strict")
    except (OSError, UnicodeError) as exc:
        raise ContentPackAuditError("candidate pack is unreadable") from exc
    return audit_pack_text(root, candidate_path, families, pack_text)


def audit_pack_text(
    root: Path, candidate_path: str, families: list[dict], pack_text: str,
    corpus_bytes: dict[str, bytes] | None = None,
) -> dict:
    family_ids = [str(row["family_id"]) for row in families]
    variants = parse_pack_text(pack_text, family_ids)
    safety = {
        "first_person_hits": 0,
        "url_hits": 0,
        "commercial_or_tracking_hits": 0,
        "guarantee_hits": 0,
        "live_link_dependency_hits": 0,
        "comply_gate_failures": 0,
    }
    for item in variants:
        copy = item["copy"]
        safety["first_person_hits"] += _count_terms(copy, FIRST_PERSON_TERMS)
        safety["url_hits"] += len(URL_RE.findall(copy))
        safety["commercial_or_tracking_hits"] += len(COMMERCIAL_RE.findall(copy))
        safety["guarantee_hits"] += len(GUARANTEE_RE.findall(copy))
        safety["live_link_dependency_hits"] += len(LIVE_LINK_RE.findall(copy))
        if not _comply_check(copy):
            safety["comply_gate_failures"] += 1
    baseline = build_copy_baseline(root, candidate_path, corpus_bytes)
    candidates = [(item["family_id"], item["copy"]) for item in variants]
    counts = _collision_counts(candidates, baseline)
    copy_audit = {
        "candidate_variants": len(variants),
        "historical_records": len(baseline),
        "unique_historical_normal_forms": len({normalize_text(item) for item in baseline}),
        "historical_exact_collisions": counts["historical_exact_collisions"],
        "historical_near_collisions": counts["historical_near_collisions"],
        "cross_family_exact_collisions": counts["cross_family_exact_collisions"],
        "cross_family_near_collisions": counts["cross_family_near_collisions"],
    }
    relevance_rows = []
    below_threshold = 0
    by_family = {
        family_id: [item for item in variants if item["family_id"] == family_id]
        for family_id in family_ids
    }
    expected_topics = {str(row["family_id"]): row for row in families}
    for family_id in family_ids:
        topic_norm = normalize_text(expected_topics[family_id]["topic"])
        topic_grams = _trigrams(topic_norm)
        platform_coverages = []
        for item in by_family[family_id]:
            copy_grams = _trigrams(item["norm"])
            coverage = len(topic_grams & copy_grams) / len(topic_grams) if topic_grams else 0.0
            platform_coverages.append(round(coverage, 6))
        combined_norm = "".join(item["norm"] for item in by_family[family_id])
        combined_grams = _trigrams(combined_norm)
        combined = len(topic_grams & combined_grams) / len(topic_grams) if topic_grams else 0.0
        minimum = min(platform_coverages) if platform_coverages else 0.0
        passed = (
            minimum >= MIN_TOPIC_PLATFORM_TRIGRAM_COVERAGE
            and combined >= MIN_TOPIC_COMBINED_TRIGRAM_COVERAGE
        )
        if not passed:
            below_threshold += 1
        relevance_rows.append({
            "family_id": family_id,
            "topic_sha256": str(expected_topics[family_id]["topic_sha256"]),
            "minimum_platform_coverage": round(minimum, 6),
            "combined_coverage": round(combined, 6),
            "passed": passed,
        })
    relevance_audit = {
        "method": "normalized-topic-character-trigram-containment-v1",
        "mechanical_relevance_only": True,
        "minimum_platform_coverage_required": MIN_TOPIC_PLATFORM_TRIGRAM_COVERAGE,
        "minimum_combined_coverage_required": MIN_TOPIC_COMBINED_TRIGRAM_COVERAGE,
        "family_count": len(family_ids),
        "candidate_variants": len(variants),
        "families_below_threshold": below_threshold,
        "families": relevance_rows,
    }
    return {
        "safety_audit": safety,
        "copy_corpus_audit": copy_audit,
        "relevance_audit": relevance_audit,
        "collision_examples": counts["collision_examples"],
    }
