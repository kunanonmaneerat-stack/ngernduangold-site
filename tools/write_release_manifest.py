#!/usr/bin/env python3
"""Write deterministic site, source, gate, and bounded-pilot provenance."""
import argparse
import json
from pathlib import Path

from release_contract import MANIFEST_NAME, manifest_for


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", required=True)
    ap.add_argument("--repo", default=str(Path(__file__).resolve().parents[1]))
    args = ap.parse_args()
    src = Path(args.src).resolve()
    if not src.is_dir():
        raise SystemExit("site directory not found: " + str(src))
    payload = json.dumps(manifest_for(src, args.repo), ensure_ascii=False, sort_keys=True,
                         separators=(",", ":")) + "\n"
    (src / MANIFEST_NAME).write_text(payload, encoding="utf-8", newline="\n")
    print("release manifest: %d files" % json.loads(payload)["file_count"])


if __name__ == "__main__":
    main()
