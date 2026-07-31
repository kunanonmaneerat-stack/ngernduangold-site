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

# One failure row is noise. The SAME channel failing again inside this window is a
# standing outage that nobody is watching.
REPEAT_FAIL_WINDOW_DAYS = 3
REPEAT_FAIL_WARN = 2
REPEAT_FAIL_FAIL = 3
POLICY = os.path.join(REPO, ".system_control", "policy.json")

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
    pol_path = os.path.join(REPO, ".system_control", "policy.json")
    spec = (_load(pol_path, {}) or {}).get("specs", {})
    want_w, want_h = spec.get("reel_width", 1080), spec.get("reel_height", 1920)
    if not os.path.exists(pol_path):
        add("queued clip spec", "WARN",
            "policy.json is MISSING - falling back to %dx%d; restore it before trusting this"
            % (want_w, want_h))
        return
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


SCHEDULED_DIR = os.path.join(os.path.expanduser("~"), "Claude", "Scheduled")


def check_prompt_drift():
    """Scheduled-task prompts may quote a policy date, but it must still be the real one.

    Twice on 31 Jul the same fact lived in a prompt AND in policy/code, and the copies
    disagreed: TikTok was dropped but two prompts still asked for it, and the clip spec was
    written in both policy.json and preflight. Banning dates in prompts would be useless --
    context helps. So the rule is narrower and checkable: IF a prompt names a date that
    policy.json also owns for that channel, the two must match. A prompt quoting a date
    policy no longer holds is drift, and drift is what goes unnoticed for days.

    Skips silently when the Scheduled directory is not visible (e.g. the Linux sandbox);
    the Windows-side runs are the ones that matter.
    """
    if not os.path.isdir(SCHEDULED_DIR):
        add("prompt drift", "WARN", "Scheduled dir not visible here - run this check on the Windows host")
        return
    pol_path = os.path.join(REPO, ".system_control", "policy.json")
    if not os.path.exists(pol_path):
        # Distinguish "policy has no dates" from "policy is gone". The first is fine; the
        # second means this check has no input and would otherwise PASS while blind --
        # exactly the failure mode this repo keeps writing rules about.
        add("prompt drift", "WARN", "policy.json is MISSING - this check has nothing to compare against")
        return
    pol = _load(pol_path, {}) or {}
    channels = pol.get("channels", {})
    # channel -> the ONE date policy currently owns for it
    owned = {ch: v["until"] for ch, v in channels.items() if v.get("until")}
    if not owned:
        add("prompt drift", "PASS", "policy owns no channel dates to drift from")
        return
    alias = {"instagram": ("instagram", "ig"), "tiktok": ("tiktok",),
             "pinterest": ("pinterest",), "threads": ("threads",),
             "youtube": ("youtube", "yt"), "facebook": ("facebook", "fb")}
    stale, checked = [], 0
    for name in sorted(os.listdir(SCHEDULED_DIR)):
        skill = os.path.join(SCHEDULED_DIR, name, "SKILL.md")
        if not os.path.isfile(skill):
            continue
        try:
            text = io.open(skill, encoding="utf-8", errors="ignore").read()
        except Exception:
            continue
        checked += 1
        low = text.lower()
        for ch, good in owned.items():
            if not any(a in low for a in alias.get(ch, (ch,))):
                continue
            # every ISO date this prompt mentions for a month policy also talks about
            for found in set(re.findall(r"20\d\d-\d\d-\d\d", text)):
                if found[:7] == good[:7] and found != good:
                    stale.append(f"{name}: says {found} for {ch}, policy says {good}")
    if stale:
        add("prompt drift", "FAIL", "; ".join(sorted(set(stale))[:3]))
    else:
        add("prompt drift", "PASS", f"{checked} task prompt(s) agree with policy.json")


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


def check_repeat_failures():
    """Catch a channel that fails every day for one root cause.

    Blind spot this closes (found 31 Jul 2026): Facebook's web session expired on
    30 Jul. THREE automated legs failed across two days - knowledge-post-noon FB text
    (30 Jul 21:31, 31 Jul 12:50) and fb-comment-daily (30 Jul 22:05) - and no guard
    said a word, because policy.json marks facebook state=manual/auto=false, so every
    report classified it as MANUAL-ONLY = expected, not broken.
    "This channel is meant to be manual" and "automation is trying and failing on this
    channel" are different facts. Only the first one was ever checked.
    """
    rows = []
    try:
        for line in io.open(LEDGER, encoding="utf-8"):
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except Exception:
                pass
    except Exception as exc:
        add("repeat failures", "FAIL", "cannot read post-ledger: %s" % exc)
        return

    cutoff = datetime.date.today() - datetime.timedelta(days=REPEAT_FAIL_WINDOW_DAYS - 1)
    recent = {}
    for r in rows:
        if r.get("type") != "failure":
            continue
        ts = r.get("ts")
        if not isinstance(ts, str):
            continue
        try:
            day = datetime.date.fromisoformat(ts[:10])
        except Exception:
            continue
        if day < cutoff:
            continue
        recent.setdefault(str(r.get("channel", "?")), []).append((ts, r))

    policy = _load(POLICY, {}) or {}
    channels = policy.get("channels", {}) if isinstance(policy, dict) else {}

    worst, notes = "PASS", []
    for ch in sorted(recent):
        hits = sorted(recent[ch])
        if len(hits) < REPEAT_FAIL_WARN:
            continue
        status = "FAIL" if len(hits) >= REPEAT_FAIL_FAIL else "WARN"
        if status == "FAIL" or worst == "PASS":
            worst = status
        why = str(hits[-1][1].get("text_first80", ""))[:70]
        note = "%s: %d failures since %s -> %s" % (ch, len(hits), hits[0][0][:10], why)
        # The drift that kept this invisible: policy says nothing automates this
        # channel, yet automation is writing failure rows for it. One of them is wrong.
        cfg = channels.get(ch)
        if isinstance(cfg, dict) and cfg.get("auto") is False and not cfg.get("auto_legs"):
            # policy claims nobody automates this channel, yet automation is writing
            # failure rows for it. One of the two is wrong - do not just report it green.
            # (If the channel is only partly manual, declare which legs are automated in
            #  policy.json -> channels.<ch>.auto_legs, and this stops being drift.)
            note += (" [DRIFT: policy has auto=false/%s and declares no auto_legs, so guards"
                     " call it expected - but automation IS posting to it]" % cfg.get("state", "?"))
        elif isinstance(cfg, dict) and cfg.get("auto_legs"):
            note += " [automated legs: %s]" % ",".join(cfg["auto_legs"])
        notes.append(note)

    if not notes:
        add("repeat failures", "PASS",
            "no channel failed twice in the last %d days" % REPEAT_FAIL_WINDOW_DAYS)
        return
    add("repeat failures", worst, " | ".join(notes))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--full", action="store_true", help="also run the site build gate")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    check_queue()
    check_delivery_gap()
    check_repeat_failures()
    check_captions()
    check_posted_truth()
    check_queued_clip_spec()
    check_competing_plan()
    check_prompt_drift()
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
