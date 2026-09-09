#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Focused tests for fail-closed JSONL integrity and durable ledger commits."""
from contextlib import contextmanager
from pathlib import Path
import json
import os
import sys
import tempfile


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "automation-log"))
import post_ledger as PL  # noqa: E402


def encoded(row):
    return json.dumps(row, ensure_ascii=False).encode("utf-8")


def post_row(channel="threads", clip="save", when="2026-08-16"):
    return {
        "dedup_key": PL.make_dedup_key(channel, clip, when),
        "channel": channel,
        "clip_key": clip,
        "scheduled_for": when,
        "posted_at": "2026-08-16T10:00:00+07:00",
        "type": "schedule",
        "source": "integrity-test",
        "status": "scheduled",
    }


def text_row(text, channel="threads"):
    norm = PL.normalize_text(text)
    return {
        "type": "text",
        "channel": channel,
        "text_hash": PL.text_hash(text),
        "text_norm": norm,
        "text_first80": text[:80],
        "ts": "2026-08-16T10:00:00+07:00",
        "source": "integrity-test",
    }


@contextmanager
def ledger(initial=b"", create=True):
    with tempfile.TemporaryDirectory(prefix="post-ledger-integrity-") as raw:
        path = Path(raw) / "post-ledger.jsonl"
        if create:
            path.write_bytes(initial)
        previous = PL.LEDGER
        PL.LEDGER = str(path)
        try:
            yield path
        finally:
            PL.LEDGER = previous
            lock = Path(PL._lock_path(str(path)))
            if lock.exists():
                lock.unlink()


def assert_index_blocks(path, expected_state):
    index = PL.load_index(path)
    assert index["integrity"]["state"] == expected_state, index["integrity"]
    twin, reason, _ = PL.is_twin(index, "threads", "debt", "2026-08-17")
    assert twin and expected_state in reason, reason
    assert PL.day_capacity(index, "threads", "2026-08-17") == 0


def assert_durable_before_unlock(call):
    events = []
    original_fsync = PL.os.fsync
    original_release = PL.release_lock

    def tracked_fsync(fd):
        events.append(("fsync", Path(PL._lock_path(PL.LEDGER)).exists()))
        return original_fsync(fd)

    def tracked_release(path=None):
        events.append(("release", Path(PL._lock_path(path or PL.LEDGER)).exists()))
        return original_release(path)

    PL.os.fsync = tracked_fsync
    PL.release_lock = tracked_release
    try:
        result = call()
    finally:
        PL.os.fsync = original_fsync
        PL.release_lock = original_release
    releases = [index for index, event in enumerate(events) if event[0] == "release"]
    fsyncs = [index for index, event in enumerate(events) if event[0] == "fsync"]
    assert len(releases) == 1 and len(fsyncs) >= 2, events  # lock fd + ledger fd
    assert max(fsyncs) < releases[0], events
    assert all(event[1] for event in events), events
    assert not Path(PL._lock_path(PL.LEDGER)).exists(), events
    return result


def main():
    # 1) A malformed middle row invalidates the entire snapshot and every writer.
    middle = encoded(post_row()) + b"\n{broken json\n" + encoded(post_row("fb", "debt")) + b"\n"
    with ledger(middle) as path:
        health = PL.inspect_ledger(path)
        assert health["state"] == "CORRUPT" and health["line"] == 2, health
        assert_index_blocks(path, "CORRUPT")
        try:
            list(PL.iter_ledger(path))
            raise AssertionError("iter_ledger must not hide a corrupt middle row")
        except PL.LedgerIntegrityError as exc:
            assert exc.state == "CORRUPT" and exc.line == 2
        result = PL.record_post("threads", "debt", "2026-08-17")
        assert not result["appended"] and "CORRUPT" in result["reason"], result

    blank_middle = encoded(post_row()) + b"\n \t\n" + encoded(post_row("fb", "debt")) + b"\n"
    with ledger(blank_middle) as path:
        health = PL.inspect_ledger(path)
        assert health["state"] == "CORRUPT" and health["line"] == 2, health
        assert "blank JSONL row" in health["reason"], health
        assert_index_blocks(path, "CORRUPT")

    # JSON duplicate keys and every non-finite representation are ambiguous
    # evidence, even when the unsafe value sits in an otherwise unused field.
    strict_failures = (
        b'{"type":"comment","type":"text","channel":"threads",'
        b'"ts":"2026-08-16T10:00:00+07:00"}\n',
        b'{"type":"comment","channel":"threads","unused":NaN,'
        b'"ts":"2026-08-16T10:00:00+07:00"}\n',
        b'{"type":"comment","channel":"threads","unused":1e999,'
        b'"ts":"2026-08-16T10:00:00+07:00"}\n',
    )
    for payload in strict_failures:
        with ledger(payload) as path:
            health = PL.inspect_ledger(path)
            assert health["state"] == "CORRUPT" and health["line"] == 1, health
            assert_index_blocks(path, "CORRUPT")

    # 2) A truncated final row is CORRUPT even when an earlier row already matches.
    text = "ข้อความเดียวกันต้องไม่ทำให้ระบบมองข้ามแถวท้ายที่เสีย"
    truncated = encoded(text_row(text)) + b"\n" + b'{"type":"text"'
    with ledger(truncated) as path:
        health = PL.inspect_ledger(path)
        assert health["state"] == "CORRUPT" and health["line"] == 2, health
        duplicate, reason, finding = PL.is_duplicate_text("threads", text, path=path)
        assert duplicate and "CORRUPT" in reason, reason
        assert finding["type"] == "ledger_integrity", finding
        claimed, _, reason = PL.claim("threads", "debt", "2026-08-17")
        assert not claimed and "CORRUPT" in reason, reason

    # 3) Syntactically complete JSON without the append newline is crash-like UNKNOWN.
    with ledger(encoded(post_row())) as path:
        health = PL.inspect_ledger(path)
        assert health["state"] == "UNKNOWN" and "newline" in health["reason"], health
        assert_index_blocks(path, "UNKNOWN")
        result = PL.record_text_post("threads", "ข้อความใหม่ที่ต้องถูกบล็อก")
        assert not result["appended"] and "UNKNOWN" in result["reason"], result

    # 4) A valid-JSON but incomplete transactional claim is UNKNOWN, never skipped.
    incomplete = encoded({"type": "claim", "channel": "threads"}) + b"\n"
    with ledger(incomplete) as path:
        health = PL.inspect_ledger(path)
        assert health["state"] == "UNKNOWN" and "incomplete" in health["reason"], health
        assert_index_blocks(path, "UNKNOWN")
        try:
            PL.confirm("not-a-real-key", status="POSTED")
            raise AssertionError("confirm must fail closed on an incomplete ledger")
        except RuntimeError as exc:
            assert "UNKNOWN" in str(exc), exc
        assert not Path(PL._lock_path(str(path))).exists()

    # 5) A complete but unconfirmed claim is healthy, visible, and blocks its twin.
    with ledger() as path:
        claimed, dedup_key, reason = PL.claim(
            "threads", "save", "2026-08-16T10:00:00+07:00"
        )
        assert claimed and reason == "claimed", reason
        health = PL.inspect_ledger(path)
        assert health["state"] == "OK" and len(health["pending_claims"]) == 1, health
        retry, _, retry_reason = PL.claim(
            "threads", "save", "2026-09-16T10:00:00+07:00"
        )
        assert not retry and "TWIN" in retry_reason, retry_reason
        PL.confirm(dedup_key, post_id="platform-1", status="POSTED")
        health = PL.inspect_ledger(path)
        assert health["state"] == "OK" and not health["pending_claims"], health
        assert PL.load_index(path)["status"][dedup_key] == "POSTED"

    # 6) Valid legacy rows remain readable while incomplete identity coverage is explicit.
    legacy_rows = [
        {"type": "text", "channel": "threads", "text_first80": "legacy prefix only",
         "ts": "2026-07-01T10:00:00+07:00", "source": "legacy"},
        {"type": "video", "channel": "facebook", "video": "unmapped-legacy.mp4",
         "ts": "2026-07-01T11:00:00+07:00", "source": "legacy"},
        {"type": "video", "channel": "facebook", "clip_id": "b3-02",
         "schedule_date": "2026-07-28", "ts": "2026-08-14T17:22:00+07:00",
         "source": "legacy"},
        {"type": "attempt", "channel": "facebook",
         "ts": "2026-07-01T10:59:00+07:00", "source": "legacy"},
    ]
    with ledger(b"".join(encoded(row) + b"\n" for row in legacy_rows)) as path:
        health = PL.inspect_ledger(path)
        coverage = health["identity_coverage"]
        assert health["state"] == "OK", health
        assert coverage["state"] == "INCOMPLETE" and coverage["incomplete_rows"] == 2, coverage
        assert coverage["complete_rows"] == 1, coverage
        assert len(list(PL.iter_ledger(path))) == 4, "legacy rows must be preserved"
        index = PL.load_index(path)
        published_day = PL.datetime.date(2026, 8, 14)
        assert index["all_by_clip"][("fb", "b3-02")] == [published_day], index
        assert index["by_day"][("fb", published_day)] == 1, index
        allowed, reason, metric = PL.permanent_dedup_gate(path)
        assert not allowed and metric["coverage_percent"] == 33.3, metric
        assert "2 incomplete" in reason, reason
        result = PL.record_post("threads", "debt", "2026-08-17")
        assert not result["appended"], result
        assert result["reason"].startswith("DEDUP_COMPLETENESS_BLOCK:"), result

    # 7) record, claim, and confirm all fsync the ledger while the lock still exists.
    with ledger():
        recorded = assert_durable_before_unlock(
            lambda: PL.record_post("threads", "save", "2026-08-16"))
        assert recorded["appended"], recorded
        claimed = assert_durable_before_unlock(
            lambda: PL.claim("facebook", "debt", "2026-08-17T10:00:00+07:00"))
        assert claimed[0], claimed
        assert_durable_before_unlock(
            lambda: PL.confirm(claimed[1], post_id="platform-2", status="POSTED"))
        original_fsync = PL.os.fsync
        def fail_fsync(_fd):
            raise OSError("simulated lock fsync failure")
        PL.os.fsync = fail_fsync
        try:
            assert not PL.acquire_lock(path=PL.LEDGER), "an uncommitted lock must fail closed"
        finally:
            PL.os.fsync = original_fsync
        assert not Path(PL._lock_path(PL.LEDGER)).exists(), "failed lock commit must clean up"

    # 8) A status without a preceding claim/post is crash-like UNKNOWN and cannot confirm.
    orphan = encoded({"type": "status", "dedup_key": "orphan-key", "status": "POSTED"}) + b"\n"
    with ledger(orphan) as path:
        health = PL.inspect_ledger(path)
        assert health["state"] == "UNKNOWN" and "orphan" in health["reason"], health
        assert_index_blocks(path, "UNKNOWN")
        result = PL.record_post("threads", "save", "2026-08-16")
        assert not result["appended"] and "UNKNOWN" in result["reason"], result

    # 9) Text receipts need an unambiguous timezone; a naive/invalid timestamp
    # cannot be used to evade the rolling near-duplicate window.
    with ledger() as path:
        for invalid in ("2026-08-16T10:00:00", "not-a-time"):
            try:
                PL.record_text_post("threads", "ข้อความเวลาไม่ชัด " + invalid, when=invalid)
                raise AssertionError("invalid text timestamp must fail closed")
            except ValueError as exc:
                assert "timestamp" in str(exc), exc
        assert path.read_bytes() == b"", "invalid receipts must not touch the ledger"

    print("test_post_ledger_integrity: all PASS")
    return 0


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    raise SystemExit(main())
