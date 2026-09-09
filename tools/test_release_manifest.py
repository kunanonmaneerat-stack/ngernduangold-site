#!/usr/bin/env python3
"""Release-manifest contract tests."""
import json
import tempfile
from pathlib import Path
from unittest import mock

import release_contract
import write_release_manifest as release


def seed_repo(root):
    pilot = {
        "pilot_id": "fixture-pilot",
        "state": "planned_blocked",
        "external_action_authorized": False,
    }
    for relative in release_contract.SOURCE_INPUTS:
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        if relative == release_contract.PILOT_PATH:
            path.write_text(json.dumps(pilot), encoding="utf-8")
        else:
            path.write_text("fixture:" + relative.as_posix(), encoding="utf-8")


def run():
    with tempfile.TemporaryDirectory() as td:
        repo = Path(td) / "repo"
        site = Path(td) / "site"
        seed_repo(repo)
        site.mkdir()
        (site / "index.html").write_text("one", encoding="utf-8")
        (site / "assets").mkdir()
        (site / "assets" / "x.bin").write_bytes(b"two")
        first = release.manifest_for(site, repo)
        assert first["schema_version"] == 2
        assert first["algorithm"] == "sha256-tree-v1"
        assert first["file_count"] == 2
        assert len(first["tree_sha256"]) == 64
        assert first["contracts"] == release_contract.CONTRACT_VERSIONS
        assert set(first["source_sha256"]) == {
            path.as_posix() for path in release_contract.SOURCE_INPUTS
        }
        assert ".system_control/content_manifest.json" in first["source_sha256"]
        assert "tools/comply_gate_stitch.py" in first["source_sha256"]
        assert first["pilot"]["external_action_authorized"] is False

        pilot_path = repo / release_contract.PILOT_PATH
        pilot_raw = pilot_path.read_bytes()
        original_stable_read = release_contract._stable_file_bytes
        pilot_reads = 0

        def changing_second_pilot_read(path, label):
            nonlocal pilot_reads
            if Path(path).resolve() == pilot_path.resolve():
                pilot_reads += 1
                if pilot_reads > 1:
                    return pilot_raw.replace(b"fixture-pilot", b"changed-pilot")
            return original_stable_read(path, label)

        with mock.patch.object(
            release_contract,
            "_stable_file_bytes",
            side_effect=changing_second_pilot_read,
        ):
            coherent = release.manifest_for(site, repo)
        assert pilot_reads == 1
        assert (
            coherent["source_sha256"][release_contract.PILOT_PATH.as_posix()]
            == coherent["pilot"]["contract_sha256"]
            == release_contract.sha256_bytes(pilot_raw)
        )

        # The manifest never hashes itself, so repeated generation is stable.
        (site / release.MANIFEST_NAME).write_text(json.dumps(first), encoding="utf-8")
        assert release.manifest_for(site, repo) == first

        (site / "index.html").write_text("changed", encoding="utf-8")
        second = release.manifest_for(site, repo)
        assert second["tree_sha256"] != first["tree_sha256"]
        assert second["file_count"] == first["file_count"]

        gate = repo / "tools" / "merchant_offer_gate.py"
        gate.write_text("changed gate", encoding="utf-8")
        third = release.manifest_for(site, repo)
        assert third["tree_sha256"] == second["tree_sha256"]
        assert third["source_sha256"] != second["source_sha256"]

        pilot = json.loads(pilot_path.read_text(encoding="utf-8"))
        pilot_path.write_text(
            '{"pilot_id":"fixture-pilot","state":"planned_blocked",'
            '"external_action_authorized":false,"score":NaN}',
            encoding="utf-8",
        )
        try:
            release.manifest_for(site, repo)
        except ValueError:
            pass
        else:
            raise AssertionError("non-finite pilot JSON must fail closed")
        pilot_path.write_text(json.dumps(pilot), encoding="utf-8")

        for malformed in (
            '{"pilot_id":"fixture-pilot","state":"planned_blocked",'
            '"external_action_authorized":true,"external_action_authorized":false}',
            '{"pilot_id":"fixture-pilot","state":"planned_blocked",'
            '"external_action_authorized":false,"score":1e999}',
        ):
            pilot_path.write_text(malformed, encoding="utf-8")
            try:
                release.manifest_for(site, repo)
            except ValueError:
                pass
            else:
                raise AssertionError("ambiguous/non-finite pilot JSON must fail closed")
        pilot_path.write_text(json.dumps(pilot), encoding="utf-8")

        original_is_symlink = Path.is_symlink
        with mock.patch.object(
            Path,
            "is_symlink",
            autospec=True,
            side_effect=lambda value: (
                value.name == "x.bin" or original_is_symlink(value)
            ),
        ):
            try:
                release_contract.file_hashes(site)
            except ValueError:
                pass
            else:
                raise AssertionError("symlinked release artifacts must fail closed")

        pilot["external_action_authorized"] = True
        pilot_path.write_text(json.dumps(pilot), encoding="utf-8")
        try:
            release.manifest_for(site, repo)
        except ValueError:
            pass
        else:
            raise AssertionError("authorizing pilot must not produce a release manifest")
    print("release manifest: hash, JSON, and symlink contract PASS")


if __name__ == "__main__":
    run()
