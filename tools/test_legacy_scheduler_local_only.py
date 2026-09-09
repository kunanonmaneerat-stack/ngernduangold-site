#!/usr/bin/env python3
"""Regression checks for permanently local-only legacy scheduler entrypoints."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
FB_SCRIPT = ROOT / "social-autopost" / "schedule_fb_batch2.py"
POSTIZ_SCRIPT = ROOT / "pipeline" / "postiz_article_scheduler.py"
MANIFEST = ROOT / ".system_control" / "content_manifest.json"


def check(name: str, condition: bool) -> None:
    print(("PASS " if condition else "FAIL ") + name)
    if not condition:
        raise AssertionError(name)


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run(script: Path, *args: str, env: dict[str, str] | None = None):
    child_env = os.environ.copy()
    child_env["PYTHONIOENCODING"] = "utf-8"
    if env:
        child_env.update(env)
    return subprocess.run(
        [sys.executable, str(script), *args],
        cwd=ROOT,
        env=child_env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=30,
        check=False,
    )


def main() -> int:
    fb_source = FB_SCRIPT.read_text(encoding="utf-8")
    postiz_source = POSTIZ_SCRIPT.read_text(encoding="utf-8")
    forbidden_transport = ("urllib.request", "urlopen(", "requests.", "httpx.")
    forbidden_fb_mutation = ("FB_PAGE_TOKEN", "scheduled_publish_time", "/videos")
    forbidden_postiz_mutation = ("POSTIZ_API_KEY", 'api("/posts"', "/integrations")

    check(
        "Facebook compatibility script has no network transport",
        not any(marker in fb_source for marker in forbidden_transport),
    )
    check(
        "Facebook compatibility script has no credential or mutation path",
        not any(marker in fb_source for marker in forbidden_fb_mutation),
    )
    check(
        "Postiz compatibility script has no network transport",
        not any(marker in postiz_source for marker in forbidden_transport),
    )
    check(
        "Postiz compatibility script has no credential or mutation path",
        not any(marker in postiz_source for marker in forbidden_postiz_mutation),
    )

    before = digest(MANIFEST)
    result = run(FB_SCRIPT, "--go", env={"DRY_RUN": "1"})
    check(
        "Facebook --go hard-blocks",
        result.returncode == 2 and "PERMANENTLY LOCAL-ONLY" in result.stdout,
    )
    check("Facebook live rejection does not write manifest", digest(MANIFEST) == before)

    result = run(FB_SCRIPT, env={"DRY_RUN": "0"})
    check(
        "Facebook legacy live environment hard-blocks",
        result.returncode == 2 and "PERMANENTLY LOCAL-ONLY" in result.stdout,
    )

    result = run(POSTIZ_SCRIPT, "--go", "--file", "definitely-missing.json")
    check(
        "Postiz --go blocks before reading the plan",
        result.returncode == 2
        and "PERMANENTLY LOCAL-ONLY" in result.stdout
        and "config" not in result.stdout.lower(),
    )

    with tempfile.TemporaryDirectory(prefix="postiz_local_plan_") as raw:
        plan = Path(raw) / "plan.json"
        plan.write_text(
            json.dumps(
                {
                    "channel": "threads",
                    "per_day": 1,
                    "hour_ict": 19,
                    "posts": [{"topic": "local-only test", "content": "draft"}],
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        result = run(
            POSTIZ_SCRIPT,
            "--file",
            str(plan),
            env={"POSTIZ_API_KEY": "must-have-no-effect"},
        )
    check(
        "Postiz default mode renders a local plan only",
        result.returncode == 0
        and "LOCAL PLAN ONLY" in result.stdout
        and "no external state changed" in result.stdout,
    )

    result = run(FB_SCRIPT, "--plan", env={"DRY_RUN": "1"})
    check(
        "Facebook default mode remains read-only local planning",
        result.returncode in (0, 2)
        and "LOCAL PLAN ONLY" in result.stdout
        and digest(MANIFEST) == before,
    )

    print("10 checks, 0 failed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
