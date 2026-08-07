#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""encoding_probe - find Thai text that has already been corrupted, anywhere.

WHY THIS EXISTS: this repo writes Thai into task prompts, JSON policy and markdown
logs from a Windows box whose console is cp874. Every few days some file comes back
with U+FFFD in it, and the damage is silent - a prompt with a mangled word still
runs, it just quietly means something else. Until now the check was "remember to
grep for the replacement character after every write", which is exactly the kind of
rule that gets skipped on the day it matters.

It also catches the two lookalike faults that are NOT corruption, because calling
them corruption sends the next reader chasing nothing:
  - a UTF-8 BOM (the bytes are fine, some readers choke)
  - cp874/tis-620 bytes that never were UTF-8 (recoverable - do not "fix" by
    re-saving, that destroys the original)

USAGE
  python tools/encoding_probe.py                     # scan the default set
  python tools/encoding_probe.py <path> [<path>...]  # scan specific files or dirs

EXIT CODES
  0 = clean    1 = something needs a human    2 = could not scan anything
"""
import os, sys, io, glob

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HOME = os.path.expanduser("~")

DEFAULT_TARGETS = [
    os.path.join(HOME, "Claude", "Scheduled"),
    os.path.join(HOME, ".claude", "scheduled-tasks"),
    os.path.join(REPO, ".system_control"),
    os.path.join(REPO, "automation-log"),
    os.path.join(REPO, "OPERATING-NOTES.md"),
]
TEXT_EXT = {".md", ".json", ".jsonl", ".csv", ".txt", ".py"}
REPLACEMENT = "�"
SKIP_DIRS = {".git", "node_modules", "_raw", "_rejected", ".tiktok-profile",
             "Code Cache", "Service Worker", "_social-stage"}


def files_under(target):
    if os.path.isfile(target):
        yield target
        return
    for root, dirs, names in os.walk(target):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        for n in names:
            if os.path.splitext(n)[1].lower() in TEXT_EXT:
                yield os.path.join(root, n)


def probe(path):
    """-> (verdict, note). verdict in {ok, corrupt, bom, legacy, unreadable}."""
    try:
        raw = open(path, "rb").read()
    except Exception as exc:
        return "unreadable", str(exc)
    if not raw:
        return "ok", ""

    bom = raw[:3] == b"\xef\xbb\xbf"
    body = raw[3:] if bom else raw

    try:
        text = body.decode("utf-8")
    except UnicodeDecodeError:
        # Not UTF-8 at all. If it decodes as cp874 AND contains Thai, it is a
        # legacy file, not damage - the bytes still hold the original characters.
        try:
            legacy = body.decode("cp874")
        except Exception:
            return "corrupt", "not valid UTF-8 and not cp874 either"
        thai = sum(1 for c in legacy if "฀" <= c <= "๿")
        if thai:
            return "legacy", "cp874/tis-620 with %d Thai char(s) - convert, do not re-save blind" % thai
        return "corrupt", "not valid UTF-8"

    n = text.count(REPLACEMENT)
    if n:
        i = text.find(REPLACEMENT)
        line = text[:i].count("\n") + 1
        ctx = text[max(0, i - 30):i + 30].replace("\n", " ")
        return "corrupt", "%d replacement char(s), first at line %d: ...%s..." % (n, line, ctx)
    if bom:
        return "bom", "UTF-8 BOM present - content is intact"
    return "ok", ""


def main():
    targets = sys.argv[1:] or DEFAULT_TARGETS
    seen, buckets = 0, {"corrupt": [], "legacy": [], "bom": [], "unreadable": []}
    for t in targets:
        if not os.path.exists(t):
            continue
        for f in files_under(t):
            seen += 1
            v, note = probe(f)
            if v != "ok":
                buckets[v].append((f, note))

    if not seen:
        print("encoding_probe: nothing to scan - none of the targets exist")
        return 2

    for kind, label in (("corrupt", "ALREADY DAMAGED - the original characters are gone"),
                        ("legacy", "not UTF-8 but recoverable"),
                        ("unreadable", "could not be read"),
                        ("bom", "BOM only - content intact, safe to ignore")):
        rows = buckets[kind]
        if not rows:
            continue
        print("\n%s (%d)" % (label, len(rows)))
        for f, note in rows:
            print("  %s\n      %s" % (os.path.relpath(f, HOME), note))

    bad = len(buckets["corrupt"]) + len(buckets["legacy"]) + len(buckets["unreadable"])
    print("\nencoding_probe: %d file(s) scanned, %d need a human, %d BOM-only"
          % (seen, bad, len(buckets["bom"])))
    return 1 if bad else 0


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    sys.exit(main())
