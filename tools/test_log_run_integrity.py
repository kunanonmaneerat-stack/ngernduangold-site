#!/usr/bin/env python3
"""Regression checks for durable, local-only proof-of-run writes."""
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import threading


ROOT = Path(__file__).resolve().parents[1]
LOG_DIR = ROOT / "automation-log"
sys.path.insert(0, str(LOG_DIR))
SPEC = importlib.util.spec_from_file_location("automation_log_run", LOG_DIR / "log_run.py")
module = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(module)


def check(label, condition):
    if not condition:
        raise AssertionError(label)
    print("PASS", label)


def main():
    with tempfile.TemporaryDirectory() as raw:
        target = Path(raw) / "automation-log"
        target.mkdir()
        original = module.HERE
        module.HERE = str(target)
        try:
            errors = []

            def write(index):
                try:
                    module.log_run(
                        f"routine-{index:02d}", "ok", "local",
                        {"count": index}, ts=f"2026-08-16T10:{index:02d}:00+07:00",
                    )
                except Exception as exc:  # pragma: no cover - assertion reports it
                    errors.append(exc)

            threads = [threading.Thread(target=write, args=(index,)) for index in range(20)]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join()
            check("concurrent runlog writes complete", errors == [])
            rows = [json.loads(line) for line in
                    (target / "2026-08.jsonl").read_text(encoding="utf-8").splitlines()
                    if line.strip()]
            check("concurrent append preserves every JSON row", len(rows) == 20)
            latest = (target / "latest.md").read_text(encoding="utf-8")
            check("atomic latest rebuild retains every routine",
                  all(f"routine-{index:02d}" in latest for index in range(20)))
            check("temporary latest artifacts are cleaned",
                  not list(target.glob("latest.md.tmp-*")))

            (target / "2026-07.jsonl").write_text("{not-json}\n", encoding="utf-8")
            try:
                module.rebuild_latest()
            except RuntimeError as exc:
                check("malformed historical row fails closed",
                      "2026-07.jsonl:1" in str(exc))
            else:
                raise AssertionError("malformed historical row was ignored")
        finally:
            module.HERE = original
    print("log_run integrity: all checks passed")


if __name__ == "__main__":
    main()
