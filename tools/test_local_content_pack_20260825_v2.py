"""Read-only exact/near/topic and copy-safety audit for the 2026-08-25 V2 pack."""

from __future__ import annotations

import json
from pathlib import Path
import re
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
PIPELINE = ROOT / "pipeline"
if str(PIPELINE) not in sys.path:
    sys.path.insert(0, str(PIPELINE))

import comply_gate  # noqa: E402
import dispatcher  # noqa: E402
from tools import week_content_r5_novelty_guard as novelty  # noqa: E402


V1 = ROOT / "automation-log" / "cc-outbox" / "LOCAL-CONTENT-PACK_20260825.md"
V2 = ROOT / "automation-log" / "cc-outbox" / "LOCAL-CONTENT-PACK_20260825_V2.md"
ORDERS = ROOT / "automation-log" / "orders.txt"
CALENDAR = ROOT / ".system_control" / "content_calendar.json"
MANIFEST = ROOT / ".system_control" / "content_manifest.json"
LEDGER = ROOT / "automation-log" / "post-ledger.jsonl"
PACKAGES = ROOT / "automation-log" / "content-packages"
LEGACY_CORPUS_RECEIPT = (
    ROOT / "automation-log" / "dedup-evidence"
    / "LOCAL-CONTENT-PACK_20260825_V2-CORPUS-REVIEW.json"
)
CURRENT_CORPUS_RECEIPT = (
    ROOT / "automation-log" / "dedup-evidence"
    / "LOCAL-CONTENT-PACK_20260825_V2-CORPUS-REVIEW-V2.json"
)
FULFILMENT_RECEIPT = (
    ROOT / "automation-log" / "dedup-evidence"
    / "LOCAL-CONTENT-PACK_20260825_V2-DRAFT-FULFILMENT.json"
)
STRICT_RECEIPT = (
    ROOT / "automation-log" / "dedup-evidence"
    / "LOCAL-CONTENT-PACK_20260825_V2-STRICT-REVALIDATION.json"
)
EXPECTED_FAMILIES = (
    "payroll-net-pay-reconciliation",
    "annual-expense-sinking-funds",
    "recurring-charge-renewal-audit",
    "household-bill-ownership-map",
    "refund-dispute-evidence-timeline",
    "beneficiary-emergency-access-review",
    "employee-benefit-inventory",
)


def _topic_blocks():
    text = V2.read_text(encoding="utf-8")
    matches = list(re.finditer(r"(?m)^## ([1-7])\. .+$", text))
    out = []
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else text.index(
            "\n## Release block", match.end()
        )
        block = text[match.start():end]
        family = re.search(r"(?m)^- `family_id`: `([^`]+)`$", block)
        if family is None:
            raise AssertionError("topic block has no family_id")
        copies = {}
        for channel in ("Threads", "Facebook", "TikTok"):
            copy = re.search(
                r"(?ms)^### " + channel + r"\n\n(.*?)(?=^### |^---\s*$|\Z)",
                block,
            )
            if copy is None:
                raise AssertionError(f"{family.group(1)} has no {channel} copy")
            copies[channel.casefold()] = copy.group(1).strip()
        out.append((family.group(1), block, copies))
    return out


def _candidate_variants():
    rows = []
    for family, _block, copies in _topic_blocks():
        for channel, copy in copies.items():
            rows.append(novelty.TextRecord(
                source=V2.relative_to(ROOT).as_posix(),
                field=f"{family}.{channel}", scope="candidate", text=copy,
                norm=novelty.normalize_text(copy), candidate_id=family,
                channel=channel,
            ))
    return rows


def _walk_topics(value, key=""):
    if isinstance(value, dict):
        for child_key, child in value.items():
            yield from _walk_topics(child, str(child_key))
    elif isinstance(value, list):
        for child in value:
            yield from _walk_topics(child, key)
    elif isinstance(value, str) and key in {"topic", "topic_th", "title", "angle"}:
        if len(novelty.normalize_text(value)) >= 8:
            yield value


def _historical_topics():
    values = []
    values.extend(_walk_topics(json.loads(MANIFEST.read_text(encoding="utf-8"))))
    values.extend(_walk_topics(json.loads(CALENDAR.read_text(encoding="utf-8"))))
    for line in LEDGER.read_text(encoding="utf-8").splitlines():
        row = json.loads(line)
        for key in ("topic", "text_first80"):
            value = row.get(key)
            if isinstance(value, str) and len(novelty.normalize_text(value)) >= 8:
                values.append(value)
    for path in sorted(PACKAGES.glob("*.md")):
        first = path.read_text(encoding="utf-8-sig", errors="strict").splitlines()[0]
        values.append(re.sub(r"^#\s*Content Package\s*-\s*", "", first).strip())
    for heading in re.findall(r"(?m)^## \d+\.\s*(.+)$", V1.read_text(encoding="utf-8")):
        values.append(heading.strip())
    return sorted({value for value in values if novelty.normalize_text(value)})


class LocalContentPackV2Tests(unittest.TestCase):
    def test_v1_is_withdrawn_and_v2_is_the_only_current_draft(self):
        v1 = V1.read_text(encoding="utf-8")
        v2 = V2.read_text(encoding="utf-8")
        self.assertTrue(v1.startswith("# WITHDRAWN_TOPIC_OVERLAP — DO NOT USE\n"))
        self.assertIn("DO_NOT_USE_DO_NOT_PUBLISH_DO_NOT_SCHEDULE", v1[:700])
        self.assertIn("LOCAL-CONTENT-PACK_20260825_V2.md", v1[:700])
        self.assertIn("`status`: `DRAFT_ONLY_BLOCKED_SOURCE_REVIEW`", v2[:700])
        self.assertIn("`publication_authority`: `NONE`", v2[:700])
        self.assertIn("`semantic_universality_claimed`: `FALSE`", v2[:1200])
        self.assertIn("ไม่พิสูจน์ความใหม่ระดับความหมาย", v2[:1600])

    def test_registry_and_pack_have_seven_matching_new_families(self):
        active, historical = dispatcher.load_order_registry(ORDERS)
        self.assertEqual(EXPECTED_FAMILIES, tuple(row["family_id"] for row in active))
        self.assertEqual(7, len(historical))
        blocks = _topic_blocks()
        self.assertEqual(EXPECTED_FAMILIES, tuple(row[0] for row in blocks))
        self.assertEqual(21, sum(len(row[2]) for row in blocks))
        self.assertTrue(all(
            "`status`: `DRAFT_ONLY_BLOCKED_SOURCE_REVIEW`" in row[1]
            and "`source_gate`: `BLOCKED_" in row[1]
            for row in blocks
        ))

    def test_separate_review_and_fulfilment_receipts_bind_exact_v2_without_authority(self):
        corpus = json.loads(CURRENT_CORPUS_RECEIPT.read_text(encoding="utf-8"))
        fulfilment = json.loads(FULFILMENT_RECEIPT.read_text(encoding="utf-8"))
        strict = json.loads(STRICT_RECEIPT.read_text(encoding="utf-8"))
        active, _historical = dispatcher.load_order_registry(ORDERS)
        self.assertEqual(dispatcher.CORPUS_REVIEW_SCHEMA_VERSION, corpus["schema_version"])
        self.assertEqual(dispatcher.CORPUS_REVIEW_RECEIPT_TYPE, corpus["receipt_type"])
        self.assertEqual(dispatcher.CORPUS_REVIEW_PRODUCER, corpus["producer"])
        self.assertEqual(dispatcher.CORPUS_REVIEW_METHOD, corpus["method"])
        self.assertNotIn("pack", corpus)
        self.assertFalse(corpus["semantic_universality_claimed"])
        self.assertEqual("NONE", corpus["publication_authority"])
        self.assertEqual(dispatcher.FULFILMENT_RECEIPT_TYPE, fulfilment["receipt_type"])
        self.assertEqual("DRAFT_FULFILLED_BLOCKED", fulfilment["fulfilment_state"])
        self.assertEqual("NONE", fulfilment["publication_authority"])
        self.assertEqual(
            LEGACY_CORPUS_RECEIPT.relative_to(ROOT).as_posix(),
            fulfilment["corpus_review"]["path"],
        )
        self.assertEqual(
            dispatcher._sha256_file(LEGACY_CORPUS_RECEIPT),
            fulfilment["corpus_review"]["sha256"],
        )
        self.assertEqual(
            dispatcher._sha256_file(V2), fulfilment["pack"]["sha256"]
        )
        self.assertEqual(
            {row["family_id"]: row["topic_sha256"] for row in active},
            {
                row["family_id"]: row["topic_sha256"]
                for row in fulfilment["families"]
            },
        )
        self.assertTrue(all(
            row["corpus_review_receipt"]
            == CURRENT_CORPUS_RECEIPT.relative_to(ROOT).as_posix()
            and row["corpus_review_sha256"]
            == dispatcher._sha256_file(CURRENT_CORPUS_RECEIPT)
            for row in active
        ))
        self.assertEqual(
            {
                "path": CURRENT_CORPUS_RECEIPT.relative_to(ROOT).as_posix(),
                "sha256": dispatcher._sha256_file(CURRENT_CORPUS_RECEIPT),
            },
            strict["strict_corpus_review"],
        )
        self.assertEqual(
            {
                "path": FULFILMENT_RECEIPT.relative_to(ROOT).as_posix(),
                "sha256": dispatcher._sha256_file(FULFILMENT_RECEIPT),
            },
            strict["legacy_fulfilment"],
        )
        self.assertEqual(V2.relative_to(ROOT).as_posix(), strict["pack"]["path"])
        self.assertEqual(dispatcher._sha256_file(V2), strict["pack"]["sha256"])
        self.assertEqual(
            "DRAFT_ONLY_BLOCKED_SOURCE_REVIEW", strict["pack"]["status"]
        )

    def test_actual_post_copy_has_page_only_and_no_unsafe_dependency(self):
        full = V2.read_text(encoding="utf-8")
        self.assertIsNone(re.search(r"https?://|www\.", full, flags=re.I))
        self.assertIsNone(re.search(r"\baffiliate\b|พันธมิตร", full, flags=re.I))
        for record in _candidate_variants():
            copy = record.text
            for term in ("ผม", "ฉัน", "ดิฉัน", "ข้าพเจ้า", "พวกเรา", "เรา"):
                self.assertNotIn(term, copy, record.field)
            self.assertIsNone(re.search(
                r"https?://|www\.|\butm_|\baffiliate\b|พันธมิตร",
                copy, flags=re.I,
            ), record.field)
            self.assertIsNone(re.search(
                r"ลิงก์|คลิก|ไบโอ|\bbio\b|\bdm\b|ทัก|โปรไฟล์|\bline\b",
                copy, flags=re.I,
            ), record.field)
            self.assertIsNone(re.search(
                r"การันตี|รับรองผล|ผ่านแน่นอน|ชัวร์|ไร้ความเสี่ยง|ได้ผลแน่นอน",
                copy, flags=re.I,
            ), record.field)
            self.assertIn(
                "เงินเดือนสมองทอง · ข้อมูลเพื่อการศึกษา · ร่างข้อความผลิตด้วย AI",
                copy,
            )
            ok, issues = comply_gate.check(copy)
            self.assertTrue(ok, f"{record.field}: {issues}")

    def test_all_platform_copy_has_no_exact_or_near_historical_collision(self):
        manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
        evidence = novelty._load_json(novelty.IDENTITY_EVIDENCE)
        ledger_rows = [json.loads(line) for line in LEDGER.read_text(
            encoding="utf-8"
        ).splitlines()]
        ledger_module = novelty._import_post_ledger()
        integrity = ledger_module.inspect_ledger(LEDGER)
        corpus, _files = novelty.build_text_corpus(
            ledger_rows, evidence, manifest,
            integrity.get("identity_bindings") or {},
        )
        calendar = json.loads(CALENDAR.read_text(encoding="utf-8"))
        for index, text in enumerate(_walk_topics(calendar)):
            corpus.append(novelty.TextRecord(
                source=CALENDAR.relative_to(ROOT).as_posix(),
                field=f"topic[{index}]", scope="content_calendar", text=text,
                norm=novelty.normalize_text(text),
            ))
        audit = novelty.audit_text(_candidate_variants(), corpus)
        self.assertEqual([], audit["historical_exact_collisions"])
        self.assertEqual([], audit["historical_near_collisions"])
        self.assertEqual([], audit["cross_candidate_exact_collisions"])
        self.assertEqual([], audit["cross_candidate_near_collisions"])

    def test_topic_angles_have_no_exact_or_near_baseline_match(self):
        active, _historical = dispatcher.load_order_registry(ORDERS)
        baseline = _historical_topics()
        self.assertGreaterEqual(len(baseline), 100)
        collisions = []
        for candidate in active:
            for prior in baseline:
                score = novelty.text_similarity(candidate["topic"], prior)
                if score["exact"] or score["near"]:
                    collisions.append({
                        "family_id": candidate["family_id"], "prior": prior,
                        "score": score,
                    })
        self.assertEqual([], collisions)


if __name__ == "__main__":
    unittest.main(verbosity=2)
