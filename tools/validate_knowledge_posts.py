#!/usr/bin/env python3
"""Fail-closed validator for KNOWLEDGE-POSTS markdown libraries."""
from datetime import date, datetime, timedelta, timezone
from html import unescape
from pathlib import Path
import argparse
import difflib
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "pipeline"))
sys.path.insert(0, str(ROOT / "automation-log"))

import comply_gate  # noqa: E402
import post_ledger  # noqa: E402
from content_source_gate import evaluate_content_source_gate  # noqa: E402

FOOTER = "\u0e02\u0e49\u0e2d\u0e21\u0e39\u0e25\u0e40\u0e1e\u0e37\u0e48\u0e2d\u0e01\u0e32\u0e23\u0e28\u0e36\u0e01\u0e29\u0e32 \u00b7 \u0e1c\u0e25\u0e34\u0e15\u0e14\u0e49\u0e27\u0e22 AI"
BAD_MARKERS = ("\ufffd", "\u00e0\u00b8", "\u00e0\u00b9", "\x00")
REGISTRY_FILE = "content-source-registry.json"
SNAPSHOT_FILE = "official-news-snapshot.json"


def parse_rows(path):
    rows = []
    for line_no, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not re.match(r"^\|\s*20\d{2}-\d{2}-\d{2}\s*\|", raw):
            continue
        parts = [part.strip() for part in raw.split("|")[1:-1]]
        if len(parts) != 5:
            raise ValueError("line %d has %d columns, expected 5" % (line_no, len(parts)))
        rows.append({
            "line": line_no,
            "date": parts[0],
            "id": parts[1],
            "topic": parts[2],
            "threads": parts[3],
            "facebook": parts[4],
        })
    return rows


def plain(value):
    return unescape(value.replace("<br>", "\n")).strip()


def prior_topics(current):
    topics = set()
    for path in current.parent.glob("KNOWLEDGE-POSTS*.md"):
        if path.resolve() == current.resolve():
            continue
        try:
            topics.update(row["topic"].casefold() for row in parse_rows(path))
        except Exception:
            continue
    return topics


def validate_same_channel_uniqueness(rows):
    """Reject exact/cosmetic/near duplicate bodies inside one content library.

    Cross-channel reuse remains allowed: a Threads post and its Facebook adaptation
    are different publication lanes, while two Threads rows at >= the canonical
    ledger threshold are a duplicate campaign and must be rewritten.
    """
    failures = []
    prior_bodies = {"threads": [], "facebook": []}
    for row in rows:
        for channel in prior_bodies:
            norm = post_ledger.normalize_text(plain(row[channel]))
            for prior_id, prior_norm in prior_bodies[channel]:
                if not norm or not prior_norm:
                    continue
                similarity = difflib.SequenceMatcher(None, norm, prior_norm).ratio()
                if similarity >= post_ledger.TEXT_SIM_THRESHOLD:
                    failures.append(
                        "%s line %d %s: %.0f%% near-duplicate of %s in the same channel" %
                        (row["id"], row["line"], channel,
                         similarity * 100, prior_id))
                    break
            prior_bodies[channel].append((row["id"], norm))
    return failures


def validate_source_contract(path, rows, content_id=None, now=None):
    """Fail closed on the official sources relevant to one publication item."""
    if not isinstance(content_id, str) or not content_id.strip():
        return ["content_id missing for official-source publication gate"]
    content_id = content_id.strip()
    if content_id not in {row.get("id") for row in rows}:
        return [content_id + ": content_id is not present in the library"]
    kb = path.parent / "knowledge-base"
    result = evaluate_content_source_gate(
        content_id,
        kb / REGISTRY_FILE,
        kb / SNAPSHOT_FILE,
        library_name=path.name,
        now=now,
    )
    return list(result.failures)


def validate(path, content_id=None):
    failures = []
    rows = parse_rows(path)
    seen_ids = set()
    seen_topics = prior_topics(path)
    parsed_dates = []

    if not rows:
        failures.append("no content rows")

    for row in rows:
        prefix = "%s line %d" % (row["id"], row["line"])
        try:
            parsed_dates.append(date.fromisoformat(row["date"]))
        except ValueError:
            failures.append(prefix + ": invalid date")

        if row["id"] in seen_ids:
            failures.append(prefix + ": duplicate id")
        seen_ids.add(row["id"])

        topic_key = row["topic"].casefold()
        if topic_key in seen_topics:
            failures.append(prefix + ": duplicate topic")
        seen_topics.add(topic_key)

        for channel in ("threads", "facebook"):
            body = plain(row[channel])
            label = prefix + " " + channel
            if not body.endswith(FOOTER):
                failures.append(label + ": missing exact disclosure footer")
            if re.search(r"https?://|www\.", body, flags=re.IGNORECASE):
                failures.append(label + ": URL in post body")
            if re.search(r"(?:^|\D)199(?:\D|$)", body):
                failures.append(label + ": blocked product price")
            if any(marker in body for marker in BAD_MARKERS):
                failures.append(label + ": encoding corruption marker")
            ok, issues = comply_gate.check_post(body, channel=channel)
            if not ok:
                failures.append(label + ": comply gate: " + "; ".join(issues))

    if len(parsed_dates) == len(rows):
        expected = [parsed_dates[0] + timedelta(days=i) for i in range(len(rows))]
        if parsed_dates != expected:
            failures.append("dates are not continuous and ordered")

    id_numbers = []
    for row in rows:
        match = re.fullmatch(r"kn-(\d+)", row["id"])
        if not match:
            failures.append(row["id"] + ": invalid id format")
        else:
            id_numbers.append(int(match.group(1)))
    if id_numbers and id_numbers != list(range(id_numbers[0], id_numbers[0] + len(id_numbers))):
        failures.append("ids are not continuous and ordered")

    failures.extend(validate_same_channel_uniqueness(rows))
    failures.extend(validate_source_contract(path, rows, content_id=content_id))

    return rows, failures


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("path", type=Path)
    parser.add_argument("--content-id",
                        help="required publication item id (for example kn-29)")
    args = parser.parse_args()
    rows, failures = validate(args.path, content_id=args.content_id)
    if failures:
        for issue in failures:
            print("FAIL " + issue)
        print("%d rows, %d failures" % (len(rows), len(failures)))
        return 1
    print("PASS %d rows; dates, ids, topics, same-channel near-duplicates, recent ledger, encoding, disclosure, URL, product, and compliance checks" % len(rows))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
