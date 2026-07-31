#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Keep post-ledger.jsonl bounded without losing what it proves.

WHY
  The ledger is append-only and EVERY guard reads it whole on every run - and so do
  the agents, which pay for it in context. On 31 Jul 2026 it was 114 rows but already
  77 KB, because the useful rows carry long forensic notes (the same notes that make
  incidents diagnosable months later). Left alone it grows without bound, and the file
  that is supposed to make the system legible becomes the thing nobody can read.

  So: keep RECENT rows byte-for-byte (that is the working window every guard queries),
  and fold OLDER rows into one compact summary row per month+channel+type. Counts stay
  intact, the raw rows are still on disk in archive/, and the hot file stays small.

SAFETY
  - dry-run by default; --apply is required to write anything
  - never edits in place: writes a .bak, then a fresh file, then verifies the rewrite
    reproduces the same per-channel counts before replacing the original
  - refuses to run if the working window would end up empty

USAGE
  py tools\\ledger_archive.py                 # show what WOULD happen
  py tools\\ledger_archive.py --apply         # do it
  py tools\\ledger_archive.py --keep-days 90  # widen the hot window

ASCII-ONLY SOURCE: repo rule for scripts that touch Thai (see OPERATING-NOTES 19).
"""
import io, os, sys, json, shutil, argparse, datetime, collections

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
LEDGER = os.path.join(REPO, "automation-log", "post-ledger.jsonl")
ARCHIVE_DIR = os.path.join(REPO, "automation-log", "archive")

# The widest window any guard actually queries is a few days; 60 is a large margin.
DEFAULT_KEEP_DAYS = 60
SUMMARY_TYPE = "archived_summary"


def load(path):
    rows, bad = [], 0
    with io.open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except Exception:
                bad += 1
    return rows, bad


def day_of(row):
    ts = row.get("ts")
    if not isinstance(ts, str) or len(ts) < 10:
        return None
    try:
        return datetime.date.fromisoformat(ts[:10])
    except Exception:
        return None


def counts(rows):
    """What the file asserts, reduced to something a rewrite must preserve."""
    c = collections.Counter()
    for r in rows:
        if r.get("type") == SUMMARY_TYPE:
            for k, n in (r.get("counts") or {}).items():
                c[k] += n
        else:
            c["%s/%s" % (r.get("channel", "?"), r.get("type", "?"))] += 1
    return c


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--keep-days", type=int, default=DEFAULT_KEEP_DAYS)
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--ledger", default=LEDGER)
    args = ap.parse_args()

    if not os.path.exists(args.ledger):
        print("no ledger at %s" % args.ledger)
        return 1

    rows, bad = load(args.ledger)
    cutoff = datetime.date.today() - datetime.timedelta(days=args.keep_days)
    old, hot, undated = [], [], []
    for r in rows:
        d = day_of(r)
        if d is None:
            undated.append(r)          # keep anything we cannot date - never guess
        elif d < cutoff:
            old.append(r)
        else:
            hot.append(r)

    size = os.path.getsize(args.ledger)
    print("ledger      : %d rows, %.1f KB%s" % (len(rows), size / 1024.0,
                                                (" (%d unparseable)" % bad) if bad else ""))
    print("keep window : last %d days (from %s)" % (args.keep_days, cutoff))
    print("  keep as-is: %d row(s)%s" % (len(hot),
          (" + %d undated kept" % len(undated)) if undated else ""))
    print("  archivable: %d row(s)" % len(old))

    if not old:
        print("\nnothing old enough to archive - the hot file is already the whole story.")
        return 0
    if not hot:
        print("\nREFUSING: every row is older than the window; that would empty the file.")
        return 2

    # one summary row per month+channel+type
    buckets = collections.Counter()
    for r in old:
        d = day_of(r)
        buckets["%s|%s|%s" % (d.strftime("%Y-%m"), r.get("channel", "?"), r.get("type", "?"))] += 1
    per_month = collections.defaultdict(dict)
    for key, n in buckets.items():
        month, ch, ty = key.split("|")
        per_month[month]["%s/%s" % (ch, ty)] = n

    summaries = []
    for month in sorted(per_month):
        summaries.append({
            "type": SUMMARY_TYPE,
            "channel": "system",
            "ts": "%s-01T00:00:00+07:00" % month,
            "month": month,
            "counts": per_month[month],
            "rows_folded": sum(per_month[month].values()),
            "raw": "automation-log/archive/post-ledger-%s.jsonl" % month,
            "note": ("Rows for %s were folded here by tools/ledger_archive.py to keep the "
                     "working ledger small. Nothing was deleted - the originals are in the "
                     "raw file named above." % month),
        })
        print("  %s -> %s" % (month, json.dumps(per_month[month], ensure_ascii=False)))

    new_rows = summaries + undated + sorted(hot, key=lambda r: str(r.get("ts", "")))

    before, after = counts(rows), counts(new_rows)
    if before != after:
        print("\nREFUSING: the rewrite would change what the ledger asserts.")
        for k in sorted(set(before) | set(after)):
            if before.get(k, 0) != after.get(k, 0):
                print("   %-24s %s -> %s" % (k, before.get(k, 0), after.get(k, 0)))
        return 2
    print("\ncount check : identical across %d channel/type pairs" % len(before))

    if not args.apply:
        print("\nDRY RUN - nothing written. Re-run with --apply to do it.")
        return 0

    if not os.path.isdir(ARCHIVE_DIR):
        os.makedirs(ARCHIVE_DIR)
    by_month = collections.defaultdict(list)
    for r in old:
        by_month[day_of(r).strftime("%Y-%m")].append(r)
    for month, rs in by_month.items():
        path = os.path.join(ARCHIVE_DIR, "post-ledger-%s.jsonl" % month)
        with io.open(path, "a", encoding="utf-8", newline="\n") as fh:
            for r in sorted(rs, key=lambda x: str(x.get("ts", ""))):
                fh.write(json.dumps(r, ensure_ascii=False) + "\n")
        print("archived    : %s (%d rows)" % (path, len(rs)))

    shutil.copy2(args.ledger, args.ledger + ".bak")
    with io.open(args.ledger, "w", encoding="utf-8", newline="\n") as fh:
        for r in new_rows:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")

    back, _ = load(args.ledger)
    if counts(back) != before:
        shutil.copy2(args.ledger + ".bak", args.ledger)
        print("VERIFY FAILED after write - restored from .bak, nothing changed.")
        return 2
    print("rewrote     : %d rows, %.1f KB (was %.1f KB) - .bak kept alongside"
          % (len(back), os.path.getsize(args.ledger) / 1024.0, size / 1024.0))
    return 0


if __name__ == "__main__":
    sys.exit(main())
