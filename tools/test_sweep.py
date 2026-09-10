#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""test_sweep - run every test file in this repo and say what CHANGED.

WHY THIS EXISTS: 10 Sep 2026. tools/test_content_calendar_guard.py was found at
88/102 - thirteen tests had been failing for weeks and nothing said so. The cron
layer (pipeline/run_daily.cmd) runs exactly one of this repo's 116 test files:
test_preflight_checks.py. The other 115 have no scheduled runner at all, so the
guards that protect this repo can rot without a single line of output changing.

WHY A BASELINE, AND WHY IT CUTS BOTH WAYS: a sweep that prints "13 failing" every
morning teaches the reader to skim it, and the day it prints 14 nobody notices -
the same way check_task_mirror warned daily about a deliberate tombstone until it
stopped being read. So this compares against a recorded baseline and is quiet
when nothing moved. It is NOT quiet when a baselined suite starts passing: an
excuse list that only ever grows is how known-broken becomes permanent. Fixing
something must force the list to shrink.

  BROKE   was green, now red        -> exit 1. This is the alarm.
  FIXED   was baselined, now green  -> exit 1. Remove it from the baseline.
  KNOWN   red and expected          -> quiet, but counted and dated
  PASS    green                     -> quiet

USAGE
  python tools/test_sweep.py                    # sweep, compare to baseline
  python tools/test_sweep.py --write-baseline   # record today's reality
  python tools/test_sweep.py --only calendar    # substring filter
  python tools/test_sweep.py --timeout 120

EXIT CODES
  0 = nothing moved   1 = something moved (either direction)   2 = could not sweep
"""
import os, sys, io, json, glob, time, argparse, subprocess

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BASELINE = os.path.join(REPO, ".system_control", "test_baseline.json")
SELF = os.path.basename(__file__)

# Suites this sweep must not run.
#   test_sweep itself - it would call itself forever.
SKIP = {SELF}


def discover():
    out = []
    for pat in ("tools/test_*.py", "pipeline/test_*.py"):
        for p in glob.glob(os.path.join(REPO, pat)):
            if os.path.basename(p) in SKIP:
                continue
            out.append(os.path.relpath(p, REPO).replace("\\", "/"))
    return sorted(out)


def run_one(rel, timeout):
    """-> (state, rc, seconds, note). state in {pass, fail, timeout, error}."""
    started = time.time()
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1", PYTHONIOENCODING="utf-8")
    try:
        r = subprocess.run([sys.executable, "-X", "utf8", "-B", rel],
                           cwd=REPO, capture_output=True, timeout=timeout, env=env)
    except subprocess.TimeoutExpired:
        return "timeout", None, time.time() - started, "exceeded %ss" % timeout
    except Exception as exc:
        return "error", None, time.time() - started, type(exc).__name__
    took = time.time() - started
    if r.returncode == 0:
        return "pass", 0, took, ""
    out = (r.stdout or b"").decode("utf-8", "replace")
    err = (r.stderr or b"").decode("utf-8", "replace")
    # "the test ran and the assertion failed" and "the test could never start"
    # are different facts. Filing both as fail is the same collapse that made
    # RUNNER_FAILED useless in content_calendar_guard: a suite that cannot import
    # is protecting nothing, and calling it a failing test hides that it is not
    # a test at all right now.
    blob = err + out
    if ("ModuleNotFoundError" in blob or "ImportError" in blob
            or "cannot import name" in blob):
        line = next((l.strip() for l in reversed(blob.splitlines())
                     if "Error" in l and ("import" in l.lower() or "module" in l.lower())),
                    "import failed")
        return "cannot_run", r.returncode, took, line[:110]
    tail = out.strip().splitlines()
    note = tail[-1][:110] if tail else err[-110:]
    return "fail", r.returncode, took, note.strip()


def load_baseline():
    try:
        return json.loads(io.open(BASELINE, encoding="utf-8").read())
    except FileNotFoundError:
        return None
    except Exception as exc:
        print("baseline unreadable (%s) - refusing to guess what was known-red" % exc)
        raise SystemExit(2)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--timeout", type=int, default=180)
    ap.add_argument("--only")
    ap.add_argument("--write-baseline", action="store_true")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()

    suites = [s for s in discover() if not a.only or a.only in s]
    if not suites:
        print("test_sweep: no test files found - that is itself the finding")
        return 2

    base = load_baseline()
    known = set((base or {}).get("known_red", {}))

    results, moved = {}, []
    # Progress is printed and flushed per suite on purpose. A sweep of a hundred
    # suites that prints nothing until it finishes cannot be told apart from a
    # sweep that hung, which is the same "I could not look" problem this repo
    # keeps paying for - just applied to the tool doing the looking.
    for n, rel in enumerate(suites, 1):
        if not a.json:
            print("[%3d/%d] %s" % (n, len(suites), rel), flush=True)
        state, rc, took, note = run_one(rel, a.timeout)
        if not a.json and state != "pass":
            print("         -> %s %s" % (state, note[:80]), flush=True)
        results[rel] = {"state": state, "rc": rc, "seconds": round(took, 1),
                        "note": note}
        if base is None:
            continue
        green = state == "pass"
        if green and rel in known:
            moved.append(("FIXED", rel, "was baselined red, now green - remove it "
                                        "from the baseline"))
        elif not green and rel not in known:
            moved.append(("BROKE", rel, "%s %s" % (state, note)))

    if a.write_baseline:
        red = {rel: {"state": r["state"], "note": r["note"]}
               for rel, r in results.items() if r["state"] != "pass"}
        payload = {
            "_what_this_is": "Suites known to be red on the date below. This is a "
                             "debt list, not permission. A suite listed here still "
                             "protects nothing.",
            "_rule": "Adding an entry needs a reason. Removing one happens the "
                     "moment it goes green - test_sweep fails until you do, so the "
                     "list cannot quietly grow into an excuse.",
            "recorded_on": time.strftime("%Y-%m-%d"),
            "suites_total": len(results),
            "known_red": red,
        }
        io.open(BASELINE, "w", encoding="utf-8", newline="\n").write(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
        print("baseline written: %d suite(s), %d red" % (len(results), len(red)))
        return 0

    if a.json:
        print(json.dumps({"results": results, "moved": moved}, ensure_ascii=False,
                         indent=2))
        return 1 if moved else 0

    n_pass = sum(1 for r in results.values() if r["state"] == "pass")
    n_red = len(results) - n_pass
    print("test_sweep: %d suite(s), %d green, %d red" % (len(results), n_pass, n_red))

    if base is None:
        print("\nNO BASELINE YET - cannot tell new breakage from old.")
        print("Red right now:")
        for rel, r in sorted(results.items()):
            if r["state"] != "pass":
                print("  %-52s %-8s %s" % (rel, r["state"], r["note"][:60]))
        print("\nRun: python tools/test_sweep.py --write-baseline")
        return 1

    if not moved:
        print("nothing moved since %s (%d known red)"
              % (base.get("recorded_on", "?"), len(known)))
        return 0

    print("")
    for kind, rel, why in moved:
        print("  %-6s %-52s %s" % (kind, rel, why))
    print("\n%d suite(s) moved - baseline is out of date" % len(moved))
    return 1


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    sys.exit(main())
