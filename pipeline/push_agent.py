"""Build and verify a release without mutating Git or remote state.

Default invocation is local-only::

    py pipeline/push_agent.py

This process cannot authenticate that a CLI ``--actor owner`` string came from
the human owner.  Consequently it exposes no commit or push mode.  The owner
may perform those actions manually outside this agent-facing program after
reviewing the local verification evidence.
"""

from __future__ import annotations

import argparse
import ast
import subprocess
import sys
from pathlib import Path


try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

ROOT_PATH = Path(__file__).resolve().parents[1]
ROOT = str(ROOT_PATH)
BSP = ROOT_PATH / "build_site.py"
SITE = ROOT_PATH / "site"
TAIL_MARK = 'print("url-consistency: hrefs normalized + per-page 301s written")'


def _run(cmd, cwd=ROOT):
    process = subprocess.run(
        cmd, cwd=cwd, capture_output=True, text=True, shell=False
    )
    return process.returncode, (process.stdout or "") + (process.stderr or "")


def guard_truncation():
    """Reject a truncated or unparsable generator before building anything."""
    src = BSP.read_text(encoding="utf-8")
    lines = [line for line in src.splitlines() if line.strip()]
    problems = []
    if not lines or lines[-1].strip() != TAIL_MARK:
        found = lines[-1][:40] if lines else "empty"
        problems.append("build_site.py tail marker is missing (found %r)" % found)
    if len(lines) < 1000:
        problems.append("build_site.py is unexpectedly short (%d lines)" % len(lines))
    try:
        ast.parse(src)
    except SyntaxError as exc:
        problems.append(
            "build_site.py parse failed at line %s: %s" % (exc.lineno, exc.msg)
        )
    return problems


def verify_build():
    htmls = [path.name for path in SITE.glob("*.html")] if SITE.is_dir() else []
    issues = []
    if len(htmls) < 30:
        issues.append("too few HTML pages (%d)" % len(htmls))
    for required in (
        "index.html", "quiz.html", "links.html", "debt-consolidation-2026.html"
    ):
        if required not in htmls:
            issues.append("missing " + required)
    affiliate_page = SITE / "credit-card-krungsri-2026.html"
    if affiliate_page.exists() and "atth.me" not in affiliate_page.read_text(encoding="utf-8"):
        issues.append("affiliate placement is missing")
    return len(htmls), issues


def execute(*, actor=None, do_commit=False, do_push=False, paths=(), role_path=None,
            runner=None):
    del actor, paths, role_path
    if do_commit or do_push:
        print("BLOCKED: this agent-facing program is permanently local-only; "
              "the human owner must perform Git and deployment actions manually")
        return 2
    run = runner or _run

    print("=== push_agent: local build + verification ===")
    truncation = guard_truncation()
    if truncation:
        print("FAIL truncation guard:")
        for issue in truncation:
            print(" -", issue)
        return 3

    rc, out = run([sys.executable, "build_site.py"])
    if rc != 0 or "quiz.html written" not in out:
        print("FAIL build:\n", out[-400:])
        return 4
    page_count, issues = verify_build()
    if issues:
        print("FAIL verification:", "; ".join(issues))
        return 5
    print("PASS local build + verification (%d pages)" % page_count)
    print("LOCAL-ONLY: no files staged, committed, pushed, or deployed")
    return 0


def parse_args(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--commit", action="store_true",
                        help="legacy flag; always blocked")
    parser.add_argument("--push", action="store_true",
                        help="legacy flag; always blocked")
    parser.add_argument("--actor",
                        help="actor key from .system_control/role_capabilities.json")
    parser.add_argument("--path", action="append", default=[],
                        help="literal repo-relative file to stage; repeat per file")
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    return execute(
        actor=args.actor,
        do_commit=args.commit,
        do_push=args.push,
        paths=args.path,
    )


if __name__ == "__main__":
    raise SystemExit(main())
