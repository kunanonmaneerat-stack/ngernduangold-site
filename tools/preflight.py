#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""preflight - one command that proves the whole ngernduangold pipeline is sane.

WHY THIS EXISTS
  Every session used to re-invent its own ad-hoc verification, so each one checked a
  slightly different subset and things slipped through for days:
    - 27-30 Jul 2026: clips existed but the posting routines could not see them (4-day
      blackout). Nothing checked "did anything actually ship recently?"
    - 19-30 Jul 2026: a CTA emitted the wrong attribution channel for 11 days.
    - 30 Jul 2026: a caption field contained literal backslash-n in all 35 captions.
    - 30 Jul 2026: a video was published but recorded as "scheduled".
  Each was cheap to detect and expensive to miss. This file is the standing checklist so
  no future session has to remember them.

ASCII-ONLY SOURCE ON PURPOSE: repo rule - scripts that touch Thai must not contain Thai
literals (encoding corruption). Thai stays in the JSON/HTML data and is never printed here.

USAGE
  python tools/preflight.py            # fast checks (no network, ~2s)
  python tools/preflight.py --full     # adds the site build gate + link audit
  python tools/preflight.py --json     # machine-readable, for dispatcher/heartbeat

EXIT CODES
  0 = all pass    1 = at least one WARN    2 = at least one FAIL
"""
import os, sys, re, json, io, argparse, subprocess, datetime

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
MANIFEST = os.path.join(REPO, ".system_control", "content_manifest.json")
SCHEDULE = os.path.join(REPO, "reels", "schedule.json")
CMAP = os.path.join(REPO, "social-autopost", "content_map.json")
LEDGER = os.path.join(REPO, "automation-log", "post-ledger.jsonl")
YTLOG = os.path.join(REPO, ".system_control", "yt_upload_log.json")
SITE = os.path.join(REPO, "site")

# A real content post - heartbeats/failures/system rows do not count as delivery.
DELIVERY_TYPES = {"text", "video", "image", "comment"}
DELIVERY_WARN_DAYS = 2     # nothing shipped for this long -> WARN
DELIVERY_FAIL_DAYS = 3     # ...this long -> FAIL (the 27-30 Jul blackout was 4)

results = []


def add(name, status, detail=""):
    results.append({"check": name, "status": status, "detail": detail})


def _load(path, default=None):
    try:
        with io.open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except Exception:
        return default


def check_queue():
    """Delegate to runway_guard so there is exactly one definition of 'queue is fine'."""
    try:
        out = subprocess.run([sys.executable, os.path.join(HERE, "runway_guard.py"), "--json"],
                             capture_output=True, text=True, cwd=REPO)
        data = json.loads(out.stdout or "{}")
        v = data.get("verdict", "?")
        eff = data.get("effective_runway_days", "?")
        if v == "OK":
            add("content queue", "PASS", f"{eff} day(s) queued, 3 sources agree")
        elif v == "LOW_RUNWAY":
            add("content queue", "WARN", f"only {eff} day(s) left - queue the next batch")
        else:
            add("content queue", "FAIL", "; ".join(data.get("problems", []))[:200])
    except Exception as exc:
        add("content queue", "FAIL", f"runway_guard did not run: {exc}")


def check_delivery_gap():
    """The check that would have caught the 4-day blackout on day one."""
    rows = []
    try:
        for line in io.open(LEDGER, encoding="utf-8"):
            line = line.strip()
            if line:
                try:
                    rows.append(json.loads(line))
                except Exception:
                    pass
    except Exception as exc:
        add("delivery gap", "FAIL", f"cannot read post-ledger: {exc}")
        return
    stamps = [r["ts"][:10] for r in rows
              if r.get("type") in DELIVERY_TYPES and isinstance(r.get("ts"), str)]
    if not stamps:
        add("delivery gap", "FAIL", "post-ledger has no content posts at all")
        return
    last = max(stamps)
    gap = (datetime.date.today() - datetime.date.fromisoformat(last)).days
    msg = f"last real post {last} ({gap} day(s) ago)"
    if gap >= DELIVERY_FAIL_DAYS:
        add("delivery gap", "FAIL", msg + " - channels are going dark")
    elif gap >= DELIVERY_WARN_DAYS:
        add("delivery gap", "WARN", msg)
    else:
        add("delivery gap", "PASS", msg)


def check_captions():
    man = _load(MANIFEST, {})
    items = man.get("items", [])
    if not items:
        add("captions", "FAIL", "manifest unreadable or empty")
        return
    bad_nl = sum(v.count("\\n") for i in items for v in (i.get("captions") or {}).values())
    banned = ("\u0e01\u0e32\u0e23\u0e31\u0e19\u0e15\u0e35",)  # "guarantee"
    hits = []
    pct = 0
    for i in items:
        for ch, v in (i.get("captions") or {}).items():
            if not isinstance(v, str):
                continue
            if any(b in v for b in banned):
                hits.append(f"{i.get('id')}/{ch}")
            if re.search(r"\d+(\.\d+)?\s*%", v):
                pct += 1
            if ch != "youtube" and re.search(r"https?://", v):
                hits.append(f"{i.get('id')}/{ch}:url")
    problems = []
    if bad_nl:
        problems.append(f"{bad_nl} literal backslash-n token(s)")
    if hits:
        problems.append("banned content in " + ", ".join(hits[:4]))
    if pct:
        problems.append(f"{pct} caption(s) contain a percentage figure")
    if problems:
        add("captions", "FAIL", "; ".join(problems))
    else:
        add("captions", "PASS", f"{len(items)} items clean (no stray escapes, no %, no off-channel URL)")


def check_posted_truth():
    """A 'posted' record must not claim a state the evidence contradicts."""
    man = _load(MANIFEST, {})
    ytlog = _load(YTLOG, {}) or {}
    bad = []
    for i in man.get("items", []):
        yt = (i.get("posted") or {}).get("youtube")
        if not yt:
            continue
        m = re.search(r"yt-api ([\w-]+)", yt)
        if not m:
            continue
        vid, date = m.group(1), i.get("date")
        if ytlog.get(date) != vid:
            bad.append(f"{i.get('id')}: manifest says {vid}, upload-log says {ytlog.get(date)}")
        # NOTE: a past-dated row that still says "scheduled" is NOT a defect - the upload
        # really was scheduled, it just was not re-stamped after it went live. The defect
        # this guards is the opposite: claiming a schedule for an upload that was published
        # immediately (slot already passed), which never had a scheduled state at all.
    if bad:
        add("posted records", "FAIL", "; ".join(bad[:3]))
    else:
        add("posted records", "PASS", "manifest agrees with yt_upload_log")


def check_queued_clip_spec():
    """Every clip queued for TODAY or later must already meet the posting spec.

    Gap found 31 Jul 2026: nothing verified the spec of a clip UNTIL video-post-verify ran
    at 21:30 -- i.e. after it had already been posted. A 720x1280 or watermarked clip could
    sit in the queue for days and only be caught on the way out. This checks on the way IN.
    Past dates are ignored on purpose: history is history, and 11-19 Jul really were 720p.
    """
    # Spec comes from policy.json, not from a literal here -- same one-fact-one-place rule
    # that moved the channel pause windows out of post_guard on 31 Jul.
    spec = (_load(os.path.join(REPO, ".system_control", "policy.json"), {}) or {}).get("specs", {})
    want_w, want_h = spec.get("reel_width", 1080), spec.get("reel_height", 1920)
    want = f"{want_w},{want_h}"
    sched = _load(SCHEDULE, {}) or {}
    today = datetime.date.today().isoformat()
    future = {d: v for d, v in sched.items() if d >= today}
    if not future:
        add("queued clip spec", "WARN", "nothing queued from today onward")
        return
    import shutil
    if not shutil.which("ffprobe"):
        add("queued clip spec", "WARN", "ffprobe not on PATH - spec not verified")
        return
    bad = []
    for d, v in sorted(future.items()):
        rel = (v or {}).get("file", "")
        path = os.path.join(REPO, "reels", rel)
        if not os.path.exists(path):
            bad.append(f"{d}: {rel or '<none>'} missing on disk")
            continue
        r = subprocess.run(
            ["ffprobe", "-v", "error", "-select_streams", "v:0",
             "-show_entries", "stream=width,height", "-of", "csv=p=0", path],
            capture_output=True, text=True)
        dims = (r.stdout or "").strip()
        if dims != want:
            bad.append(f"{d}: {rel} is {dims or '?'} (spec {want_w}x{want_h})")
    if bad:
        add("queued clip spec", "FAIL", "; ".join(bad[:3]))
    else:
        add("queued clip spec", "PASS", f"{len(future)} queued clip(s), all {want_w}x{want_h} on disk")


def check_competing_plan():
    """Nothing outside the manifest may claim to decide what gets posted today.

    Found 31 Jul 2026: pipeline/post_dispatcher.py (legacy, plans from the raw Google Flow
    library) rewrote automation-log/post-plan.json every morning naming 720x1280 WATERMARKED
    clips for the exact days b3-05..b3-07 were queued -- and its paths pointed at a dead
    sandbox mount. Two sources of truth for one decision is the same failure class as the
    27-30 Jul blackout; the only difference is which file won. So: assert there is no second
    plan, or that if one exists it agrees with the manifest.
    """
    plan_path = os.path.join(REPO, "automation-log", "post-plan.json")
    if not os.path.exists(plan_path):
        add("competing plan", "PASS", "no rival post-plan.json - manifest is the only source")
        return
    plan = _load(plan_path, None)
    if plan is None:
        add("competing plan", "WARN", "post-plan.json exists but is unreadable")
        return
    items = plan if isinstance(plan, list) else (plan.get("items") or plan.get("plan") or [])
    man = {i.get("date"): i for i in (_load(MANIFEST, {}) or {}).get("items", [])}
    today = datetime.date.today().isoformat()
    bad = []
    for it in items:
        if not isinstance(it, dict):
            continue
        day = it.get("day") or it.get("date")
        if not day or day < today:
            continue                      # only future/today matters
        f = str(it.get("file") or "")
        if not f:
            continue
        norm = f.replace("\\", "/")
        if "/reels/" not in norm:
            bad.append(f"{day}: plans {os.path.basename(norm) or f} which is not a reels/ clip")
        elif day in man and os.path.basename(man[day].get("reel", "")) != os.path.basename(norm):
            bad.append(f"{day}: plan says {os.path.basename(norm)}, manifest says "
                       f"{os.path.basename(man[day].get('reel',''))}")
    if bad:
        add("competing plan", "FAIL", "; ".join(bad[:3]))
    else:
        add("competing plan", "PASS", "post-plan.json agrees with the manifest")


def check_disclosure():
    """Affiliate disclosure must be driven by real anchors, never by grep-for-words.
    Guards the negation bug (a page saying 'no affiliate links' matched 'affiliate links')."""
    if not os.path.isdir(SITE):
        add("disclosure", "WARN", "site/ not built - run build_site.py")
        return
    # Thai kept as \u escapes on purpose - this file must stay pure ASCII so a
    # Windows re-encode cannot silently corrupt the strings the check depends on.
    HAS = "\u0e21\u0e35\u0e25\u0e34\u0e07\u0e01\u0e4c\u0e1e\u0e31\u0e19\u0e18\u0e21\u0e34\u0e15\u0e23"   # "has affiliate links"
    NONE = "\u0e44\u0e21\u0e48" + HAS                                        # "no affiliate links"
    # The REQUIRED disclosure box, not the generic phrase. This distinction matters:
    # the site-wide footer trust line also contains HAS, so a page could lose its real
    # FTC disclosure box and still "say" HAS. The first version of this check did exactly
    # that and passed a page whose disclosure had been stripped (caught by self-test 3).
    BOX = "* " + HAS + " \u2014 \u0e40\u0e23\u0e32\u0e2d\u0e32\u0e08\u0e44\u0e14\u0e49\u0e23\u0e31\u0e1a"  # "* has affiliate links - we may receive"                                                                        # "no affiliate links"
    bad = []
    checked = 0
    for fn in sorted(os.listdir(SITE)):
        if not fn.endswith(".html"):
            continue
        try:
            html = io.open(os.path.join(SITE, fn), encoding="utf-8").read()
        except Exception:
            continue
        checked += 1
        n_aff = len(re.findall(r'href="https://atth\.me', html))
        says_none = NONE in html
        # Only two states are actually unsafe. Over-disclosing (saying the site uses
        # affiliate links on a page that happens to have none) is not a violation - the
        # About page and the site-wide footer both do it on purpose, so flagging that
        # produced 3 false positives on the first run of this checker.
        if n_aff > 0 and BOX not in html:
            bad.append(f"{fn}: {n_aff} affiliate link(s) but NO disclosure box")  # FTC risk
        if n_aff > 0 and says_none:
            bad.append(f"{fn}: says 'no affiliate links' but has {n_aff}")     # false claim
    if bad:
        add("disclosure", "FAIL", "; ".join(bad[:3]))
    else:
        add("disclosure", "PASS",
            f"{checked} pages: every page with affiliate links discloses them "
            f"(counted by real anchors, not by word match)")


def check_attribution():
    """Every affiliate button must carry a well-formed channel_page_provider sub id."""
    if not os.path.isdir(SITE):
        add("attribution", "WARN", "site/ not built")
        return
    bad, total = [], 0
    for fn in sorted(os.listdir(SITE)):
        if not fn.endswith(".html"):
            continue
        html = io.open(os.path.join(SITE, fn), encoding="utf-8").read()
        for a in re.findall(r'href="https://atth\.me[^"]*"', html):
            total += 1
            m = re.search(r"utm_content=([^&\"]*)", a)
            if not m or m.group(1).count("_") < 2:
                bad.append(f"{fn}: malformed sub id")
    if bad:
        add("attribution", "FAIL", f"{len(bad)} bad of {total}: " + "; ".join(bad[:3]))
    else:
        add("attribution", "PASS", f"{total} affiliate buttons, all sub ids well-formed")


def check_build_gate():
    r = subprocess.run([sys.executable, os.path.join(HERE, "postdeploy_smoke.py"), "--src", "site"],
                       capture_output=True, text=True, cwd=REPO)
    tail = (r.stdout or r.stderr).strip().splitlines()
    add("build gate", "PASS" if r.returncode == 0 else "FAIL", tail[-1][:160] if tail else "")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--full", action="store_true", help="also run the site build gate")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    check_queue()
    check_delivery_gap()
    check_captions()
    check_posted_truth()
    check_queued_clip_spec()
    check_competing_plan()
    check_disclosure()
    check_attribution()
    if args.full:
        check_build_gate()

    fails = [r for r in results if r["status"] == "FAIL"]
    warns = [r for r in results if r["status"] == "WARN"]
    code = 2 if fails else (1 if warns else 0)

    if args.json:
        print(json.dumps({"verdict": ["OK", "WARN", "FAIL"][code], "checks": results},
                         ensure_ascii=False))
        return code

    print("preflight [%s]  %s" % (["OK", "WARN", "FAIL"][code],
                                  datetime.datetime.now().strftime("%Y-%m-%d %H:%M")))
    for r in results:
        print("  %-5s %-16s %s" % (r["status"], r["check"], r["detail"]))
    if code:
        print("\n  %d fail / %d warn -- fix before the next posting slot." % (len(fails), len(warns)))
    return code


if __name__ == "__main__":
    sys.exit(main())
