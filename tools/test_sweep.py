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
  python tools/test_sweep.py --total-timeout 840  # whole sweep, including probes

EXIT CODES
  0 = nothing moved   1 = something moved (either direction)   2 = could not sweep
"""
import os, sys, io, json, glob, time, argparse, subprocess

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BASELINE = os.path.join(REPO, ".system_control", "test_baseline.json")
SELF = os.path.basename(__file__)

# Suites this sweep must not run.
#   test_sweep itself          - it would call itself forever.
#   test_sweep_baseline        - it proves the baseline comparison fires in both
#                                directions by temporarily editing the real
#                                baseline file. Safe on its own, but running it
#                                from inside a sweep means two processes writing
#                                the same file. Run it directly instead.
SKIP = {SELF, "test_sweep_baseline.py"}


def discover():
    out = []
    for pat in ("tools/test_*.py", "pipeline/test_*.py"):
        for p in glob.glob(os.path.join(REPO, pat)):
            if os.path.basename(p) in SKIP:
                continue
            out.append(os.path.relpath(p, REPO).replace("\\", "/"))
    return sorted(out)


# Files no test may change. 10 Sep 2026: a sweep gutted the live content
# calendar (65 placements -> 0), the manifest and the post ledger (177 rows ->
# 2), and the next sweep then read those ruins and reported nine healthy suites
# BROKE. Some test writes fixtures to dispatcher.ROOT without patching it. Every
# suite is now fenced: bytes before, bytes after, and a suite that touches any of
# these is reported as MUTATED (never pass), and the file is put back from git.
PROTECTED = (
    ".system_control/policy.json",
    ".system_control/content_calendar.json",
    ".system_control/content_manifest.json",
    ".system_control/role_capabilities.json",
    "automation-log/post-ledger.jsonl",
)
# Directories where a test must not ADD files either. Same day: a test dropped
# a PROVISIONAL corpus-review.json into automation-log/dedup-evidence/, where
# other suites read it as real evidence. A new file is a mutation too.
PROTECTED_DIRS = (
    ".system_control",
    "automation-log/dedup-evidence",
    "automation-log/media-qa",
)


def _snapshot():
    out = {}
    for rel in PROTECTED:
        p = os.path.join(REPO, rel)
        try:
            out[rel] = open(p, "rb").read()
        except OSError:
            out[rel] = None
    for d in PROTECTED_DIRS:
        p = os.path.join(REPO, d)
        try:
            names = sorted(os.listdir(p))
        except OSError:
            names = None
        out["dir:" + d] = names
    return out


def _new_files(before, after):
    added = []
    for k, was in before.items():
        if not k.startswith("dir:") or was is None:
            continue
        now = after.get(k) or []
        for n in now:
            if n not in was:
                added.append(os.path.join(k[4:], n))
    return added


def _restore(changed):
    """Put protected files back EXACTLY as they were before the suite ran.

    Exact bytes, from memory - never `git checkout`. This repo has
    core.autocrlf=true, so a checkout rewrites LF files as CRLF on disk. Several
    receipts bind the calendar by sha256 of its bytes; on 10 Sep 2026 a manual
    `git checkout` restore after the gutting silently turned seven green suites
    red through that hash alone. If you ever must restore from git, write the
    bytes of `git show HEAD:<path>` directly.
    """
    for rel, before in changed:
        p = os.path.join(REPO, rel)
        if before is None:
            continue
        with open(p, "wb") as fh:
            fh.write(before)


def run_one(rel, timeout):
    """-> (state, rc, seconds, note).
    state in {pass, fail, cannot_run, mutated, timeout, error}."""
    before = _snapshot()
    state, rc, took, note = _run_one_unfenced(rel, timeout)
    after = _snapshot()
    changed = [(k, before[k]) for k in PROTECTED if before[k] != after[k]]
    added = _new_files(before, after)
    if changed or added:
        _restore(changed)
        for a in added:
            try:
                os.remove(os.path.join(REPO, a))
            except OSError:
                pass
        names = ", ".join([k for k, _ in changed] + ["+" + a for a in added])
        return "mutated", rc, took, ("wrote to protected repo file(s): %s - restored; "
                                     "this suite must be fixed before it can count" % names)
    return state, rc, took, note


def _probe_python(path, timeout=60):
    """True when this interpreter can import what the scheduled guards need -
    the same bar pipeline/python_runtime.cmd applies."""
    if not path or not os.path.isfile(path):
        return False
    try:
        r = subprocess.run([path, "-c", "import numpy, cv2, PIL, cryptography"],
                           capture_output=True, timeout=timeout)
        return r.returncode == 0
    except Exception:
        return False


def resolve_python(deadline=None):
    """Pick the interpreter the cron layer would pick, in its order.

    10 Sep 2026: `python` on this machine's PATH is hermes-agent's venv. Every
    ad-hoc test run that day used it without noticing, which is why `tools`
    resolved to the wrong package and why numpy looked missing. The scheduled
    layer never had that problem because python_runtime.cmd probes for a runtime
    that actually imports numpy/cv2/PIL/cryptography. Mirror that here so the
    sweep judges suites on the interpreter that will really run them.
    """
    home = os.path.expanduser("~")
    local = os.environ.get("LOCALAPPDATA", "")
    candidates = [
        os.environ.get("NGERNDUANGOLD_PYTHON"),
        os.path.join(REPO, ".venv", "Scripts", "python.exe"),
        os.path.join(REPO, "venv", "Scripts", "python.exe"),
        os.environ.get("CODEX_WORKSPACE_PYTHON"),
        os.path.join(home, ".cache", "codex-runtimes", "codex-primary-runtime",
                     "dependencies", "python", "python.exe"),
        os.path.join(local, "Python", "pythoncore-3.14-64", "python.exe"),
    ]
    if local:
        candidates.extend(sorted(glob.glob(os.path.join(local, "Python", "*", "python.exe"))))
    for c in candidates:
        remaining = 60 if deadline is None else deadline - time.monotonic()
        if remaining <= 0:
            break
        if _probe_python(c, timeout=min(60, remaining)):
            return c, "cron-equivalent"
    return sys.executable, "FALLBACK sys.executable - cron runtime not found, results may not match the scheduled layer"


PYTHON, PYTHON_NOTE = None, None


def _run_one_unfenced(rel, timeout):
    started = time.time()
    # This repo's tests use TWO import conventions and neither runner mode alone
    # satisfies both:
    #   `import release_candidate`        needs tools/ on sys.path  (run by path)
    #   `from tools import x`             needs the repo root       (run with -m)
    # By path alone, `tools` resolved to hermes-agent's installed package and 7
    # healthy suites read as cannot_run. With -m alone, 40+ suites lost their
    # bare imports and read as BROKE. Run by path AND put the repo root on
    # PYTHONPATH: script dir first (bare imports), repo root second (`tools.*`),
    # site-packages last - so the foreign `tools` never wins. Verified 10 Sep on
    # one suite of each convention.
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1", PYTHONIOENCODING="utf-8",
               PYTHONPATH=REPO + (os.pathsep + os.environ["PYTHONPATH"]
                                  if os.environ.get("PYTHONPATH") else ""))
    try:
        r = subprocess.run([PYTHON, "-X", "utf8", "-B", rel],
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
    ap.add_argument("--total-timeout", type=int, default=840,
                    help="whole-sweep budget in seconds, including interpreter probes (1..900)")
    ap.add_argument("--only")
    ap.add_argument("--write-baseline", action="store_true")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    if a.timeout <= 0 or not 1 <= a.total_timeout <= 900:
        ap.error("timeouts must be positive and total-timeout must be <= 900")
    deadline = time.monotonic() + a.total_timeout

    suites = [s for s in discover() if not a.only or a.only in s]
    if not suites:
        print("test_sweep: no test files found - that is itself the finding")
        return 2

    global PYTHON, PYTHON_NOTE
    PYTHON, PYTHON_NOTE = resolve_python(deadline=deadline)
    if not a.json:
        print("interpreter: %s (%s)" % (PYTHON, PYTHON_NOTE), flush=True)

    base = load_baseline()
    known = set((base or {}).get("known_red", {}))

    results, moved = {}, []
    incomplete = False
    # Progress is printed and flushed per suite on purpose. A sweep of a hundred
    # suites that prints nothing until it finishes cannot be told apart from a
    # sweep that hung, which is the same "I could not look" problem this repo
    # keeps paying for - just applied to the tool doing the looking.
    for n, rel in enumerate(suites, 1):
        if not a.json:
            print("[%3d/%d] %s" % (n, len(suites), rel), flush=True)
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            incomplete = True
            break
        state, rc, took, note = run_one(rel, min(a.timeout, remaining))
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

    # Never certify a partial run or overwrite the baseline with partial data.
    # run_one finishes its mutation fence before this check, even on timeout.
    incomplete = incomplete or time.monotonic() >= deadline
    if incomplete:
        pending = [rel for rel in suites if rel not in results]
        if a.json:
            print(json.dumps({"results": results, "moved": moved,
                              "complete": False, "pending": pending,
                              "reason": "total_timeout"}, ensure_ascii=False, indent=2))
        else:
            print("test_sweep: BLOCKED - whole-sweep timeout; %d/%d suites measured"
                  % (len(results), len(suites)))
        return 2

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
