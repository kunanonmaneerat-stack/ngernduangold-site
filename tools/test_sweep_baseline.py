"""Reverse test for test_sweep's baseline comparison.

"Nothing moved" already proved it can stay quiet. A guard that can only stay
quiet is not a guard, so this proves both directions on the real baseline file,
then puts it back and verifies the restore byte-for-byte.
"""
import io, json, shutil, subprocess, sys, os, hashlib

B = ".system_control/test_baseline.json"
BAK = B + ".rtbak"
GREEN = "tools/test_channel_readiness.py"      # green today
# Pick the red suite from the baseline itself. 13 Sep 2026: the hard-coded
# pantip suite had been fixed, so this test's own fixture went green and the
# BROKE case reported "nothing moved" - a reverse test that silently stops
# testing when the world improves is the exact failure it exists to catch.
_base = json.load(io.open(B, encoding="utf-8"))
_reds = sorted(k for k, v in _base["known_red"].items() if v.get("state") == "fail")
assert _reds, "no baselined red suite to borrow - baseline is fully green, rewrite this test"
RED = _reds[0]


def sweep(only):
    r = subprocess.run([sys.executable, "-X", "utf8", "-B", "tools/test_sweep.py",
                        "--only", only, "--timeout", "120"],
                       capture_output=True, text=True, encoding="utf-8",
                       errors="replace")
    return r.returncode, (r.stdout or "")


before = open(B, "rb").read()
shutil.copy2(B, BAK)
results = []
try:
    base = json.loads(before.decode("utf-8"))

    # FIXED: claim a green suite is known-red. The sweep must complain, because
    # an excuse list that never shrinks is how known-broken becomes permanent.
    d = json.loads(before.decode("utf-8"))
    d["known_red"][GREEN] = {"state": "fail", "note": "injected by reverse test"}
    io.open(B, "w", encoding="utf-8", newline="\n").write(
        json.dumps(d, ensure_ascii=False, indent=2) + "\n")
    rc, out = sweep("test_channel_readiness")
    results.append(("green suite listed as known-red -> FIXED, exit 1",
                    rc == 1 and "FIXED" in out, rc, out.strip().splitlines()[-1][:70]))

    # BROKE: drop a genuinely red suite from the baseline. The sweep must alarm.
    d = json.loads(before.decode("utf-8"))
    d["known_red"].pop(RED, None)
    io.open(B, "w", encoding="utf-8", newline="\n").write(
        json.dumps(d, ensure_ascii=False, indent=2) + "\n")
    rc, out = sweep(os.path.basename(RED)[:-3])
    results.append(("red suite missing from baseline -> BROKE, exit 1",
                    rc == 1 and "BROKE" in out, rc, out.strip().splitlines()[-1][:70]))

    # QUIET: untouched baseline, same red suite -> no alarm.
    shutil.copy2(BAK, B)
    rc, out = sweep(os.path.basename(RED)[:-3])
    results.append(("baselined red suite -> quiet, exit 0",
                    rc == 0 and "nothing moved" in out, rc,
                    out.strip().splitlines()[-1][:70]))
finally:
    shutil.copy2(BAK, B)
    os.remove(BAK)
    after = open(B, "rb").read()
    same = hashlib.sha256(before).hexdigest() == hashlib.sha256(after).hexdigest()
    print("baseline restored byte-for-byte:", same)

fails = 0
for name, ok, rc, tail in results:
    fails += 0 if ok else 1
    print("%-4s %-48s exit=%s  %s" % ("PASS" if ok else "FAIL", name, rc, tail))
print("\n%d case(s), %d failed" % (len(results), fails))
sys.exit(1 if fails else 0)
