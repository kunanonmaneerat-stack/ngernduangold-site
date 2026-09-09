#!/usr/bin/env python3
"""Deterministic archive and fail-closed receipt regressions."""

from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import tempfile
import zipfile

import release_candidate
import release_contract


def seed_repo(repo: Path) -> Path:
    pilot = {
        "pilot_id": "fixture-pilot",
        "state": "planned_blocked",
        "external_action_authorized": False,
    }
    for relative in release_contract.SOURCE_INPUTS:
        path = repo / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        if relative == release_contract.PILOT_PATH:
            path.write_text(json.dumps(pilot), encoding="utf-8")
        else:
            path.write_text("fixture:" + relative.as_posix(), encoding="utf-8")
    site = repo / "site"
    site.mkdir()
    (site / "index.html").write_text("one\n", encoding="utf-8")
    (site / "assets").mkdir()
    (site / "assets" / "x.bin").write_bytes(b"two")
    manifest = release_contract.manifest_for(site, repo)
    (site / release_contract.MANIFEST_NAME).write_text(
        json.dumps(manifest, ensure_ascii=False, sort_keys=True,
                   separators=(",", ":")) + "\n",
        encoding="utf-8", newline="\n",
    )
    (repo / "operator-notes.txt").write_text("original\n", encoding="utf-8")
    (repo / ".gitignore").write_text(
        "automation-log/owner-decision/NEXT48-EXACT-READINESS_*.json\n",
        encoding="utf-8",
    )
    subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "fixture@example.invalid"],
                   cwd=repo, check=True)
    subprocess.run(["git", "config", "user.name", "Release Fixture"],
                   cwd=repo, check=True)
    subprocess.run(["git", "add", "."], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-m", "fixture"], cwd=repo, check=True,
                   capture_output=True)
    return site


def expect_fail(action, contains: str) -> None:
    try:
        action()
    except release_candidate.CandidateError as exc:
        assert contains in str(exc), exc
    else:
        raise AssertionError("expected CandidateError containing " + contains)


def rewrite_archive_metadata(
    archive: Path, *, member_updates=None, archive_comment: bytes = b"",
) -> None:
    temporary = archive.with_suffix(".metadata-test.tmp")
    with zipfile.ZipFile(archive, "r") as source:
        members = [(item.filename, source.read(item)) for item in source.infolist()]
    with zipfile.ZipFile(temporary, "w", allowZip64=True) as target:
        target.comment = archive_comment
        for index, (name, content) in enumerate(members):
            info = zipfile.ZipInfo(name, release_candidate.FIXED_ZIP_TIME)
            info.compress_type = zipfile.ZIP_STORED
            info.create_system = release_candidate.ZIP_CREATE_SYSTEM
            info.create_version = release_candidate.ZIP_CREATE_VERSION
            info.extract_version = release_candidate.ZIP_EXTRACT_VERSION
            info.reserved = 0
            info.volume = 0
            info.internal_attr = 0
            info.external_attr = release_candidate.ZIP_EXTERNAL_ATTR
            info.extra = b""
            info.comment = b""
            if index == 0:
                for field, value in (member_updates or {}).items():
                    setattr(info, field, value)
            target.writestr(info, content)
    os.replace(temporary, archive)


def rebind_archive_receipt(archive: Path, receipt: Path, base: dict) -> None:
    payload = json.loads(json.dumps(base))
    digest = release_candidate.sha256_file(archive)
    payload["candidate_id"] = "sha256:" + digest
    payload["archive"]["sha256"] = digest
    payload["archive"]["bytes"] = archive.stat().st_size
    receipt.write_text(json.dumps(payload), encoding="utf-8")


def set_first_member_flags(archive: Path, flags: int) -> None:
    raw = bytearray(archive.read_bytes())
    for signature, offset in ((b"PK\x03\x04", 6), (b"PK\x01\x02", 8)):
        position = raw.find(signature)
        if position < 0:
            raise AssertionError("ZIP header missing from fixture")
        raw[position + offset:position + offset + 2] = int(flags).to_bytes(2, "little")
    archive.write_bytes(raw)


def set_first_member_volume(archive: Path, volume: int) -> None:
    raw = bytearray(archive.read_bytes())
    position = raw.find(b"PK\x01\x02")
    if position < 0:
        raise AssertionError("ZIP central header missing from fixture")
    raw[position + 34:position + 36] = int(volume).to_bytes(2, "little")
    archive.write_bytes(raw)


def run() -> None:
    for raw in (
        '{"schema_version":999,"schema_version":1}',
        '{"schema_version":1,"probe":1e999}',
    ):
        try:
            release_candidate._strict_json_loads(raw)
        except ValueError:
            pass
        else:
            raise AssertionError("ambiguous/non-finite release receipt JSON must fail closed")
    with tempfile.TemporaryDirectory() as td:
        repo = Path(td) / "repo"
        repo.mkdir()
        site = seed_repo(repo)

        # The exemption contract itself is fail-closed: it cannot grow into a
        # wildcard or hide a declared release input.
        canonical_exclusions = release_candidate.SOURCE_REVISION_OUTPUT_EXCLUSIONS
        try:
            release_candidate.SOURCE_REVISION_OUTPUT_EXCLUSIONS = ("release/**",)
            expect_fail(
                lambda: release_candidate._validated_output_exclusions(repo),
                "one exact downstream release path",
            )
            release_candidate.SOURCE_REVISION_OUTPUT_EXCLUSIONS = (
                "release/funnel_pilot.json",
            )
            expect_fail(
                lambda: release_candidate._validated_output_exclusions(repo),
                "one exact downstream release path",
            )
        finally:
            release_candidate.SOURCE_REVISION_OUTPUT_EXCLUSIONS = canonical_exclusions

        out = repo / "release" / "candidates"
        receipt = repo / "release" / "candidate-receipt.json"

        archive, first = release_candidate.pack(site, repo, out, receipt)
        assert first["schema_version"] == 1
        assert first["candidate_id"] == "sha256:" + first["archive"]["sha256"]
        assert first["artifact"]["reproducible_from_archive"] is True
        assert first["deployment"]["authorized"] is False
        assert first["external_action_authorized"] is False
        assert first["rollback"]["ready"] is False
        assert first["postdeploy"]["state"] == "NOT_CREATED"
        assert first["source_revision"]["clean"] is True
        assert len(first["source_revision"]["working_tree_content_sha256"]) == 64
        assert first["source_revision"]["scope"] == (
            "git-worktree-excluding-candidate-and-declared-downstream-outputs-v1"
        )
        assert first["source_revision"]["excluded_generated_outputs"] == [
            "release/PREDEPLOY-ACCEPTANCE.md",
            "release/RELEASE-FUNNEL-READINESS.json",
        ]
        assert release_candidate.verify(site, repo, archive, receipt) == first

        # Next-48 packets are downstream receipts that consume candidate/live
        # evidence.  Writing a timestamped packet must not invalidate the
        # candidate it just inspected, or the two receipts form a permanent
        # self-invalidating cycle.  The ignore is deliberately filename-scoped;
        # unrelated owner-decision inputs remain visible to the source binding.
        decision_root = repo / "automation-log" / "owner-decision"
        decision_root.mkdir(parents=True)
        packet = decision_root / "NEXT48-EXACT-READINESS_20260825T025038+0700.json"
        packet.write_text('{"generated":true}\n', encoding="utf-8")
        assert release_candidate.verify(site, repo, archive, receipt) == first
        packet.unlink()
        assert release_candidate.verify(site, repo, archive, receipt) == first
        neighbouring_decision = decision_root / "OWNER-AUTHORITY.json"
        neighbouring_decision.write_text('{"source_like":true}\n', encoding="utf-8")
        expect_fail(
            lambda: release_candidate.verify(site, repo, archive, receipt),
            "source revision",
        )
        neighbouring_decision.unlink()
        assert release_candidate.verify(site, repo, archive, receipt) == first

        # The predeploy acceptance report is a downstream consumer of this
        # receipt.  Creating or rewriting that exact generated output must not
        # invalidate its own source revision, while a neighbouring untracked
        # file must still fail closed.
        predeploy = repo / "release" / "PREDEPLOY-ACCEPTANCE.md"
        predeploy.write_text("generated-one\n", encoding="utf-8")
        assert release_candidate.verify(site, repo, archive, receipt) == first
        predeploy.write_text("generated-two\n", encoding="utf-8")
        assert release_candidate.verify(site, repo, archive, receipt) == first
        predeploy.unlink()
        assert release_candidate.verify(site, repo, archive, receipt) == first

        funnel_report = repo / "release" / "RELEASE-FUNNEL-READINESS.json"
        funnel_report.write_text('{"generated":1}\n', encoding="utf-8")
        assert release_candidate.verify(site, repo, archive, receipt) == first
        funnel_report.write_text('{"generated":2}\n', encoding="utf-8")
        assert release_candidate.verify(site, repo, archive, receipt) == first
        funnel_report.unlink()
        assert release_candidate.verify(site, repo, archive, receipt) == first

        neighbour = repo / "release" / "PREDEPLOY-INPUT.md"
        neighbour.write_text("source-like\n", encoding="utf-8")
        expect_fail(
            lambda: release_candidate.verify(site, repo, archive, receipt),
            "source revision",
        )
        neighbour.unlink()
        assert release_candidate.verify(site, repo, archive, receipt) == first

        # The same narrow exemption applies if the generated report is tracked;
        # no broad ``release/`` exclusion is allowed.
        predeploy.write_text("tracked-generated\n", encoding="utf-8")
        subprocess.run(["git", "add", predeploy.relative_to(repo).as_posix()],
                       cwd=repo, check=True)
        subprocess.run(["git", "commit", "-m", "track generated report"],
                       cwd=repo, check=True, capture_output=True)
        archive, first = release_candidate.pack(site, repo, out, receipt)
        assert first["source_revision"]["clean"] is True
        predeploy.write_text("tracked-generated-update\n", encoding="utf-8")
        assert release_candidate.verify(site, repo, archive, receipt) == first
        predeploy.write_text("tracked-generated\n", encoding="utf-8")
        assert release_candidate.verify(site, repo, archive, receipt) == first

        # Same bytes must reuse the exact content-addressed archive.
        archive_again, second = release_candidate.pack(site, repo, out, receipt)
        assert archive_again == archive
        assert second["candidate_id"] == first["candidate_id"]
        assert second["archive"] == first["archive"]

        # Python's JSON decoder otherwise accepts the non-standard NaN token;
        # an ignored receipt field must not turn malformed JSON into VERIFIED.
        malformed = dict(second)
        malformed["nonfinite"] = float("nan")
        receipt.write_text(json.dumps(malformed), encoding="utf-8")
        expect_fail(
            lambda: release_candidate.verify(site, repo, archive, receipt),
            "receipt is missing or unreadable",
        )
        receipt.write_text(json.dumps(second), encoding="utf-8")
        assert release_candidate.verify(site, repo, archive, receipt) == second

        # Same-path tracked edits must invalidate the receipt even though the
        # set of dirty path names has not changed.
        notes = repo / "operator-notes.txt"
        notes.write_text("changed\n", encoding="utf-8")
        expect_fail(
            lambda: release_candidate.verify(site, repo, archive, receipt),
            "source revision",
        )
        notes.write_text("original\n", encoding="utf-8")
        assert release_candidate.verify(site, repo, archive, receipt) == second

        # ``git diff --raw`` alone records an all-zero destination object id for
        # an unstaged edit.  Bytes must therefore be bound separately: changing
        # one already-dirty tracked path cannot replay the prior receipt.
        notes.write_text("dirty-one\n", encoding="utf-8")
        archive, second = release_candidate.pack(site, repo, out, receipt)
        notes.write_text("dirty-two\n", encoding="utf-8")
        expect_fail(
            lambda: release_candidate.verify(site, repo, archive, receipt),
            "source revision",
        )
        notes.write_text("dirty-one\n", encoding="utf-8")
        assert release_candidate.verify(site, repo, archive, receipt) == second
        notes.write_text("original\n", encoding="utf-8")

        # Untracked contents are bound too; changing bytes under the same path
        # cannot keep an old receipt valid.
        scratch = repo / "review-note.txt"
        scratch.write_text("one\n", encoding="utf-8")
        archive, second = release_candidate.pack(site, repo, out, receipt)
        scratch.write_text("two\n", encoding="utf-8")
        expect_fail(
            lambda: release_candidate.verify(site, repo, archive, receipt),
            "source revision",
        )
        scratch.write_text("one\n", encoding="utf-8")
        assert release_candidate.verify(site, repo, archive, receipt) == second

        # A changed site cannot keep using the old receipt/archive.
        (site / "index.html").write_text("changed\n", encoding="utf-8")
        expect_fail(
            lambda: release_candidate.verify(site, repo, archive, receipt),
            "release drift",
        )

        # Restore site, then prove receipt authorization/rollback overclaims fail.
        (site / "index.html").write_text("one\n", encoding="utf-8")
        canonical_archive = archive.read_bytes()
        canonical_receipt = json.loads(receipt.read_text(encoding="utf-8"))
        metadata_mutations = (
            {"create_system": 0},
            {"external_attr": 0o100600 << 16},
            {"create_version": release_candidate.ZIP_CREATE_VERSION + 1},
            {"extract_version": release_candidate.ZIP_EXTRACT_VERSION + 1},
            {"internal_attr": 1},
            {"comment": b"member-comment"},
            {"extra": b"\xfe\xca\x00\x00"},
        )
        for updates in metadata_mutations:
            archive.write_bytes(canonical_archive)
            rewrite_archive_metadata(archive, member_updates=updates)
            rebind_archive_receipt(archive, receipt, canonical_receipt)
            expect_fail(
                lambda: release_candidate.verify(site, repo, archive, receipt),
                "metadata is not deterministic",
            )
        archive.write_bytes(canonical_archive)
        set_first_member_flags(archive, release_candidate.ZIP_UTF8_FLAG)
        rebind_archive_receipt(archive, receipt, canonical_receipt)
        expect_fail(
            lambda: release_candidate.verify(site, repo, archive, receipt),
            "metadata is not deterministic",
        )
        archive.write_bytes(canonical_archive)
        set_first_member_volume(archive, 1)
        rebind_archive_receipt(archive, receipt, canonical_receipt)
        expect_fail(
            lambda: release_candidate.verify(site, repo, archive, receipt),
            "metadata is not deterministic",
        )
        archive.write_bytes(canonical_archive)
        rewrite_archive_metadata(archive, archive_comment=b"archive-comment")
        rebind_archive_receipt(archive, receipt, canonical_receipt)
        expect_fail(
            lambda: release_candidate.verify(site, repo, archive, receipt),
            "archive comment is not deterministic",
        )
        archive.write_bytes(canonical_archive)
        receipt.write_text(json.dumps(canonical_receipt), encoding="utf-8")

        payload = json.loads(receipt.read_text(encoding="utf-8"))
        payload["deployment"]["authorized"] = True
        receipt.write_text(json.dumps(payload), encoding="utf-8")
        expect_fail(
            lambda: release_candidate.verify(site, repo, archive, receipt),
            "must not authorize deployment",
        )
        payload["deployment"]["authorized"] = False
        payload["rollback"]["ready"] = True
        receipt.write_text(json.dumps(payload), encoding="utf-8")
        expect_fail(
            lambda: release_candidate.verify(site, repo, archive, receipt),
            "must not overclaim rollback readiness",
        )

        # Corrupt archive bytes are rejected before any external action.
        payload["rollback"]["ready"] = False
        receipt.write_text(json.dumps(payload), encoding="utf-8")
        archive.write_bytes(archive.read_bytes() + b"corrupt")
        expect_fail(
            lambda: release_candidate.verify(site, repo, archive, receipt),
            "content-addressed correctly",
        )
    print("release candidate: tracked/untracked byte binding PASS")


if __name__ == "__main__":
    run()
