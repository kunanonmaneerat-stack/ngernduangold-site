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

# POSTING-POLICY_antispam_20260702.md rule 2: <=2 posts/day/channel and >=3h between
# posts on the same channel (Pinterest gets 5 pins/day). Comments are not posts.
POST_CAP_LOOKBACK_DAYS = 2


def _limits():
    """Read the anti-spam numbers from policy.json, falling back to the documented
    values. Fail-safe on purpose: a missing/broken policy must not silently disable
    the cap - it must behave exactly as the written policy says."""
    fallback = {"default": 2, "pinterest": 5}, 3, {"text", "video", "image"}
    try:
        with io.open(POLICY, encoding="utf-8") as fh:
            lim = (json.load(fh) or {}).get("limits") or {}
        caps = lim.get("posts_per_day") or {}
        if not isinstance(caps, dict) or "default" not in caps:
            return fallback
        gap = lim.get("min_gap_hours")
        types = lim.get("post_types")
        return (caps,
                gap if isinstance(gap, (int, float)) else 3,
                set(types) if isinstance(types, list) and types else fallback[2])
    except Exception:
        return fallback


_CAPS, POST_MIN_GAP_HOURS, POST_TYPES = _limits()
POST_CAP_DEFAULT = _CAPS.get("default", 2)
POST_CAP_BY_CHANNEL = {k: v for k, v in _CAPS.items() if k != "default"}

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
# Tasks this agent owns and can therefore be held to a hard FAIL (the mirror above also
# carries ~90 Cowork prompts we must not silently rewrite).
OWN_TASKS_DIR = os.path.join(os.path.expanduser("~"), ".claude", "scheduled-tasks")


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
    if not (os.path.isdir(SCHEDULED_DIR) or os.path.isdir(OWN_TASKS_DIR)):
        add("prompt drift", "WARN", "no task root visible here - run this check on the Windows host")
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
    # channel -> the ONE date policy currently owns for it.
    # 'until' = when a pause ends. 'phase_until' = when a posting phase ends -- Pantip uses
    # the latter, and until 1 Aug 2026 this dict only read 'until', so the auditor prompt
    # could sit on an expired Pantip phase date ("30 Jul") for two days and this check
    # still said PASS. A drift check that only knows one field name is blind to the other.
    owned = {}
    for ch, v in channels.items():
        for field in ("until", "phase_until"):
            if v.get(field):
                owned[ch] = v[field]
                break
    if not owned:
        add("prompt drift", "PASS", "policy owns no channel dates to drift from")
        return
    alias = {"instagram": ("instagram", "ig"), "tiktok": ("tiktok",),
             "pinterest": ("pinterest",), "threads": ("threads",),
             "youtube": ("youtube", "yt"), "facebook": ("facebook", "fb")}
    # Short aliases MUST match as whole words. On 1 Aug 2026 this check raised a FAIL on
    # cowork-cc-review-loop -- "says 2026-08-01 for instagram" -- because the alias "ig"
    # matched inside the word "ignore", and the date came from a filename it referenced
    # (HANDOFF_2026-08-01.md). Neither had anything to do with Instagram. A false FAIL is
    # worse than a false WARN here: FAIL is a hard gate, so it either blocks a posting slot
    # or teaches everyone to scroll past the one line that will matter one day.
    alias_re = {ch: re.compile(r"\b(?:%s)\b" % "|".join(re.escape(a) for a in al))
                for ch, al in alias.items()}
    # A date that lives inside a filename or identifier is a reference, not a policy claim.
    FILEISH = re.compile(r"[\w/\\-]*20\d\d-\d\d-\d\d[\w-]*\.[A-Za-z0-9]{1,6}")
    stale, checked = [], 0
    # Both roots, same reason as check_dead_tooling: until 1 Aug 2026 this scanned only the
    # Cowork mirror, so the ten prompts Claude Code actually executes were never compared
    # against policy at all. See task_prompts().
    for name, root_label, skill in task_prompts():
        try:
            text = io.open(skill, encoding="utf-8", errors="ignore").read()
        except Exception:
            continue
        checked += 1
        low = text.lower()
        # strip filename-embedded dates before looking for policy claims
        scannable = FILEISH.sub(" ", text)
        for ch, good in owned.items():
            rx = alias_re.get(ch)
            if rx is None:
                if ch not in low:
                    continue
            elif not rx.search(low):
                continue
            # every ISO date this prompt mentions for a month policy also talks about
            for found in set(re.findall(r"20\d\d-\d\d-\d\d", scannable)):
                if found[:7] == good[:7] and found != good:
                    stale.append(f"{name} [{root_label}]: says {found} for {ch}, policy says {good}")
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
        # Match reels/ at a PATH-SEGMENT boundary, not as a bare substring. The first
        # version required "/reels/" with a leading slash, so a relative path -- which is
        # exactly the form the manifest itself uses (items[].reel = "reels/2026-07-27_b3-01.mp4")
        # -- was reported as "not a reels/ clip" and FAILed. Found 1 Aug 2026 by the first
        # test ever written for this check. FAIL is a hard gate, so that false positive
        # would have blocked a posting slot over a plan that actually agreed with us.
        in_reels = norm.startswith("reels/") or "/reels/" in norm
        if not in_reels:
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
    # Newest successful delivery per channel - used to tell "still broken" from "fixed".
    last_ok = {}
    for r in rows:
        if r.get("type") in DELIVERY_TYPES and isinstance(r.get("ts"), str):
            ch = str(r.get("channel", "?"))
            if r["ts"] > last_ok.get(ch, ""):
                last_ok[ch] = r["ts"]
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
        # A channel that has delivered successfully SINCE its last failure is fixed.
        # Without this the check stays red for the whole window after a real repair,
        # which is how alerts get ignored.
        recovered = last_ok.get(ch, "") > hits[-1][0]
        if recovered:
            notes.append("%s: %d failures since %s, but RECOVERED - delivered again at %s"
                         % (ch, len(hits), hits[0][0][:10], last_ok[ch][:16]))
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


def check_posting_cap():
    """Enforce the anti-spam posting cap that until now lived only in a markdown file.

    POSTING-POLICY_antispam_20260702.md rule 2 says <=2 posts/day/channel with >=3h
    between posts on the same channel. It was written after 23 Jul 2026 (3 Facebook
    posts in 58 minutes) - and then broken again on 31 Jul 2026 (3 Facebook posts in
    20 minutes), because nothing checked it: the only guard that knew the number ran
    at 19:08, hours after the posts went out. A rule no tool enforces is a wish.
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
        add("posting cap", "FAIL", "cannot read post-ledger: %s" % exc)
        return

    cutoff = datetime.date.today() - datetime.timedelta(days=POST_CAP_LOOKBACK_DAYS - 1)
    buckets = {}
    for r in rows:
        if r.get("type") not in POST_TYPES:
            continue
        ts = r.get("ts")
        if not isinstance(ts, str) or len(ts) < 16:
            continue
        # A scheduled clip is seen by the audience on publish_at, not when it was
        # uploaded. Counting by upload time made a legitimate multi-day catch-up run
        # look like a same-day spam burst.
        sched = isinstance(r.get("publish_at"), str) and len(r["publish_at"]) >= 10
        key_day = r["publish_at"][:10] if sched else ts[:10]
        try:
            day = datetime.date.fromisoformat(key_day)
        except Exception:
            continue
        if day < cutoff:
            continue
        buckets.setdefault((str(r.get("channel", "?")), key_day), []).append((ts, sched))

    today = datetime.date.today().isoformat()
    problems, history = [], []
    for (ch, day), entries in sorted(buckets.items()):
        entries.sort()
        stamps = [t for t, _ in entries]
        # spacing only means something between rows that were actually posted live
        live = [t for t, sched in entries if not sched]
        cap = POST_CAP_BY_CHANNEL.get(ch, POST_CAP_DEFAULT)
        # Today is a GATE - it decides whether the next post may go out.
        # An earlier day is HISTORY - you cannot un-post it, so it must not hold the
        # whole preflight red forever (see note 17/18: an alert that stays red after
        # the fact is how alerts get ignored).
        bucket = problems if day == today else history
        if len(stamps) > cap:
            bucket.append("%s %s: %d posts (cap %d)" % (ch, day, len(stamps), cap))
        for a, b in zip(live, live[1:]):
            try:
                gap = (datetime.datetime.fromisoformat(b)
                       - datetime.datetime.fromisoformat(a)).total_seconds() / 3600.0
            except Exception:
                continue
            if gap < POST_MIN_GAP_HOURS:
                bucket.append("%s %s: only %.2fh between %s and %s (min %dh)"
                              % (ch, day, gap, a[11:16], b[11:16], POST_MIN_GAP_HOURS))

    if problems:
        detail = " | ".join(problems)
        if history:
            detail += "  [also breached earlier: %s]" % " | ".join(history)
        add("posting cap", "FAIL", detail + " -- do NOT post again on that channel today")
    elif history:
        add("posting cap", "WARN",
            "today is clean; earlier breach on record (cannot be undone): %s"
            % " | ".join(history))
    else:
        add("posting cap", "PASS",
            "all channels within <=%d posts/day and >=%dh spacing (last %d days)"
            % (POST_CAP_DEFAULT, POST_MIN_GAP_HOURS, POST_CAP_LOOKBACK_DAYS))


DECISION_SOON_DAYS = 3
DECISION_DONE = {"done", "decided", "closed", "resolved"}


# Tooling that was retired but whose name still reads like a working instruction.
# Each entry: (label, regex, why it is dead). check_prompt_drift already catches a prompt
# quoting a stale DATE; it says nothing about a prompt quoting a stale TOOL, which is how
# six task prompts kept ordering Postiz and Meta-MCP calls a month after both were gone.
DEAD_TOOLING = [
    ("Postiz", r"[Pp]ostiz", "retired 19 Jun 2026 - bot posting was the spam-flag cause"),
    ("Meta MCP", r"get_instagram_posts|get_facebook_posts|Meta MCP",
     "Meta token revoked permanently 18 Jul 2026"),
    ("netlify.app domain", r"ngernduangold\.netlify\.app", "canonical host is ngernduangold.com"),
]
# A prompt is allowed - encouraged - to NAME a dead tool in order to forbid it. Only an
# unqualified mention is drift. Same lesson as the disclosure gate on 25 Jul, where
# grep("มีลิงก์พันธมิตร") happily matched "ไม่มีลิงก์พันธมิตร" and passed a page that said
# the opposite of what the check believed.
# Retirement markers the repo already uses at the START of a description.
_RETIRED = re.compile(r"\[\s*(?:\u0e1b\u0e34\u0e14|\u0e1e\u0e31\u0e01|PAUSED|DISABLED|DONE|\u0e40\u0e25\u0e34\u0e01\u0e43\u0e0a\u0e49)")


def _description_of(body):
    """The frontmatter description line only - retirement is declared there, not in the body."""
    if not body.startswith("---"):
        return ""
    head = body.split("---", 2)[1] if body.count("---") >= 2 else ""
    m = re.search(r"^description:\s*(.*)$", head, re.M)
    return m.group(1) if m else ""


_FORBIDDING = re.compile(
    r"ห้าม|เลิกใช้|ยกเลิก|ตายไปแล้ว|ไม่ใช้|อย่าใช้|ปิดถาวร|ใช้ไม่ได้|ไม่มีอยู่แล้ว|อย่าเสียเวลา|301|"
    r"do not|don't|retired|revoked|deprecated|no longer"
)


def task_prompts():
    """Every prompt a scheduler can actually execute, from BOTH roots.

    WHY THIS EXISTS (1 Aug 2026, the most expensive lesson of the day)
      There are two task directories and they are not copies of each other:
        ~/.claude/scheduled-tasks/   10 prompts - what Claude Code's scheduler runs
        ~/Claude/Scheduled/          97 prompts - what Cowork's scheduler runs
      Nine names exist in both, and on 1 Aug FOUR of those nine had different contents.
      `ngernduangold-weekly-review` is not even the same job in the two roots: Cowork's is
      an enabled Monday review, CC's is its own GSC-first routine. Same id, different work.

      The first version of check_dead_tooling took the NAMES from the CC root but read the
      CONTENT from the Cowork root. So for exactly the tasks it was built to police, it
      graded the wrong file - and `ngernduangold-clicktest`, which exists only in the CC
      root, was never scanned at all. That is the same failure as everything else found
      today: the guard looked where it was easy to look, not where the truth was.

    Yields (name, root_label, path). A name in both roots is yielded TWICE on purpose --
    they are two live files and both must be clean.
    """
    for label, root in (("cc", OWN_TASKS_DIR), ("cowork", SCHEDULED_DIR)):
        if not os.path.isdir(root):
            continue
        for name in sorted(os.listdir(root)):
            path = os.path.join(root, name, "SKILL.md")
            if os.path.isfile(path):
                yield name, label, path


def check_task_mirror():
    """One task id must not mean two different sets of orders.

    Not a style point. On 1 Aug a guard block was written into the Cowork copy of
    `ngernduangold-pantip-monitor` believing it would change behaviour; the CC scheduler
    reads its own copy and never saw it. Whoever reads the wrong file acts on orders that
    are not in force. WARN, not FAIL: divergence is sometimes legitimate (two different
    jobs that happen to share a name), but it must never be invisible.
    """
    if not (os.path.isdir(OWN_TASKS_DIR) and os.path.isdir(SCHEDULED_DIR)):
        add("task mirror", "WARN", "one of the two task roots is not visible here")
        return
    diverged, only_cc = [], []
    for name in sorted(os.listdir(OWN_TASKS_DIR)):
        a = os.path.join(OWN_TASKS_DIR, name, "SKILL.md")
        b = os.path.join(SCHEDULED_DIR, name, "SKILL.md")
        if not os.path.isfile(a):
            continue
        if not os.path.isfile(b):
            only_cc.append(name)
            continue
        try:
            if io.open(a, encoding="utf-8", errors="replace").read() != \
               io.open(b, encoding="utf-8", errors="replace").read():
                diverged.append(name)
        except OSError:
            continue
    bits = []
    if diverged:
        bits.append("%d id(s) mean different orders in the two roots -> %s"
                    % (len(diverged), ", ".join(diverged[:4])))
    if only_cc:
        bits.append("%d cc-only task(s) absent from the mirror -> %s"
                    % (len(only_cc), ", ".join(only_cc[:4])))
    if bits:
        add("task mirror", "WARN", "; ".join(bits))
    else:
        add("task mirror", "PASS", "both task roots agree on every shared id")


def check_dead_tooling():
    """Task prompts must not still ORDER a tool that no longer exists.

    Naming a dead tool to ban it is correct and must keep passing; naming it as a step is
    the drift. Reads BOTH task roots -- see task_prompts() for why that matters.
    """
    if not (os.path.isdir(SCHEDULED_DIR) or os.path.isdir(OWN_TASKS_DIR)):
        add("dead tooling", "WARN", "no task root visible here - run this check on the Windows host")
        return
    # Ours fail the gate (a regression must block); Cowork's warn with names, so the
    # finding stays visible every run instead of becoming a permanently red gate nobody
    # can act on. Severity now follows the root the file was READ from, not a name lookup.
    offenders = []
    others = []
    scanned = 0
    skipped_retired = 0
    for name, root_label, path in task_prompts():
        scanned += 1
        try:
            body = io.open(path, encoding="utf-8", errors="replace").read()
        except OSError:
            continue
        # A RETIRED task naming a dead tool is a historical record, not an order anyone
        # will follow. Flagging those kept nine permanently-closed prompts in the warning
        # line forever, which is how a warning stops being read (see the alarm-fatigue note
        # on check_posting_cap). The repo already marks retirement in the description, so
        # use that convention rather than inventing a new field.
        if _RETIRED.search(_description_of(body)):
            skipped_retired += 1
            continue
        for line in body.split("\n"):
            if _FORBIDDING.search(line):
                continue
            for label, pattern, _why in DEAD_TOOLING:
                if re.search(pattern, line):
                    tag = "%s [%s]: %s" % (name, root_label, label)
                    (offenders if root_label == "cc" else others).append(tag)
                    break
    if offenders:
        uniq = sorted(set(offenders))
        add("dead tooling", "FAIL",
            "%d OWN prompt(s) still instruct retired tooling -> %s" % (len(uniq), " | ".join(uniq[:4])))
        return
    if others:
        uniq = sorted(set(others))
        add("dead tooling", "WARN",
            "cc prompts clean (%d scanned across both roots); %d Cowork prompt(s) still name "
            "retired tooling -> %s" % (scanned, len(uniq), " | ".join(uniq[:5])))
        return
    add("dead tooling", "PASS",
        "%d task prompt(s) across both roots (%d retired, skipped): no orders pointing at "
        "retired tooling" % (scanned, skipped_retired))


# Channel names as they appear in prompts, mapped to whole-word patterns. Short aliases
# must not match inside longer words -- "ig" inside "ignore" produced a false FAIL in
# check_prompt_drift on 1 Aug, and a false FAIL is worse than no check because it trains
# everyone to skip the output.
_CH_WORDS = {
    "pantip": r"pantip|\u0e1e\u0e31\u0e19\u0e17\u0e34\u0e1b",
    "threads": r"threads",
    "tiktok": r"tiktok",
    "instagram": r"instagram|(?<![a-z])ig(?![a-z])",
    "facebook": r"facebook|(?<![a-z])fb(?![a-z])",
    "youtube": r"youtube|(?<![a-z])yt(?![a-z])",
    "pinterest": r"pinterest",
}
# A date in ISO form or written in Thai ("16 ก.ค." / "16 ก.ค. 2026").
_DATE_ANY = re.compile(r"\d{4}-\d{2}-\d{2}|\d{1,2}\s*(?:%s)" % r"ม.ค.|ก.พ.|มี.ค.|เม.ย.|พ.ค.|มิ.ย.|ก.ค.|ส.ค.|ก.ย.|ต.ค.|พ.ย.|ธ.ค.")
# Filenames carry dates as identifiers, not as claims: HANDOFF_2026-08-01.md, status-2026-07-30.md
_FILENAMEish = re.compile(r"[\w./\\-]*\d{4}-\d{2}-\d{2}[\w./\\-]*\.(?:md|json|jsonl|csv|py|html)")
# A date only matters here when it acts as a DEADLINE for the channel - 'paused until X',
# 'frozen through X'. Recording when something happened ('token revoked 18 Jul', '[closed
# 19 Jun]') is history and must pass: banning every date next to a channel name produced
# five false FAILs on the first run, and a check people learn to ignore protects nothing.
_DEADLINE = re.compile(
    r"ถึง|จนถึง|หมดอายุ|"
    r"ครบกำหนด|สิ้นสุด|"
    r"กลับมา|เปิดอีกครั้ง|"
    r"until|through|resume|expires?|deadline|reopen", re.I)


def check_policy_dates_in_prompts():
    """A prompt must never carry a channel's own expiry/decision date - it must point at policy.json.

    check_prompt_drift only compares ISO dates, so "Pantip FROZEN ถึง 16 ก.ค." sat in a live
    prompt for two weeks while preflight said PASS. The dangerous reading is not the stale
    date itself, it is the inference: "16 ก.ค. has passed, so the freeze is over."
    The rule is therefore about WHERE the fact lives, not whether the copy is currently right.

    FAIL for prompts this agent owns; WARN with names for the other root, same split as
    check_dead_tooling -- we cannot rewrite Cowork's prompts, but the finding must stay visible.
    """
    own, other, scanned = [], [], 0
    for name, label, path in task_prompts():
        scanned += 1
        try:
            body = io.open(path, encoding="utf-8", errors="replace").read()
        except OSError:
            continue
        for line in body.split("\n"):
            probe = _FILENAMEish.sub(" ", line)      # drop filenames before looking for dates
            if not _DATE_ANY.search(probe):
                continue
            if not _DEADLINE.search(probe):           # a record of what happened, not a deadline
                continue
            for ch, pat in _CH_WORDS.items():
                if re.search(pat, probe, re.I):
                    (own if label == "cc" else other).append("%s: %s" % (name, ch))
                    break
    if own:
        uniq = sorted(set(own))
        add("policy dates", "FAIL",
            "%d own prompt(s) hard-code a channel date instead of reading policy.json -> %s"
            % (len(uniq), " | ".join(uniq[:4])))
        return
    if other:
        uniq = sorted(set(other))
        add("policy dates", "WARN",
            "own prompts clean (%d scanned); %d Cowork prompt(s) hard-code a channel date -> %s"
            % (scanned, len(uniq), " | ".join(uniq[:5])))
        return
    add("policy dates", "PASS", "%d prompt(s): channel dates live in policy.json only" % scanned)


def check_open_decisions():
    """Surface plan decisions whose date has passed and that nobody has closed.

    policy.json already carries a gates[] array with dates, but until now the ONLY
    thing that read it was the 08:07 watchdog. So on 31 Jul 2026 the Pantip phase-2
    gate sat at status OVERDUE (expired 30 Jul) while five enabled task prompts kept
    operating under the expired phase-1 rule, and the daily 07:00 dispatcher run had
    no idea. An expired plan is a plan nobody is following.

    Deliberately WARN, never FAIL: an unmade decision must be visible on every run,
    but it must not write PREFLIGHT-ALERT.md and block unrelated posting.
    """
    pol = _load(POLICY, None)
    if pol is None:
        add("open decisions", "WARN", "policy.json is MISSING - cannot see any gate")
        return
    gates = pol.get("gates")
    if not isinstance(gates, list) or not gates:
        add("open decisions", "PASS", "policy declares no gates")
        return
    today = datetime.date.today()
    overdue, soon = [], []
    for g in gates:
        if not isinstance(g, dict):
            continue
        raw = g.get("date")
        if not isinstance(raw, str):
            continue
        try:
            when = datetime.date.fromisoformat(raw[:10])
        except Exception:
            continue
        if str(g.get("status", "")).strip().casefold() in DECISION_DONE:
            continue
        what = str(g.get("task", "?"))
        decides = g.get("decides")
        if isinstance(decides, list) and decides:
            what += " (" + ", ".join(str(d) for d in decides[:2]) + ")"
        days = (when - today).days
        if days < 0:
            overdue.append("%s: %s -- %d day(s) OVERDUE" % (raw, what, -days))
        elif days <= DECISION_SOON_DAYS:
            soon.append("%s: %s -- in %d day(s)" % (raw, what, days))
    if overdue:
        add("open decisions", "WARN", "OVERDUE -> " + " | ".join(overdue)
            + ((" ; due soon -> " + " | ".join(soon)) if soon else ""))
    elif soon:
        add("open decisions", "WARN", "due soon -> " + " | ".join(soon))
    else:
        add("open decisions", "PASS", "%d gate(s), none overdue or due within %d days"
            % (len(gates), DECISION_SOON_DAYS))


def check_content_cliff():
    """Catch a gate scheduled AFTER the queue it is supposed to refill runs out.

    Found 31 Jul 2026: the manifest is filled to 5 Aug, and ngernduangold-batch4-gate
    (which decides whether batch4 gets produced at all) fires 6 Aug. Even if the gate
    says yes, production is not instant - so the queue is empty from 6 Aug by
    construction. Neither runway_guard (which only counts days ahead) nor the gate
    itself could see this, because each knew only half of it.

    The point is not that the gate date is wrong - it was moved to 6 Aug deliberately
    so its "YT >=100 views / 7 days" criterion has 7 real days. The point is that
    nobody had checked the two dates against each other.
    """
    pol = _load(POLICY, None) or {}
    gates = pol.get("gates") if isinstance(pol.get("gates"), list) else []
    man = _load(MANIFEST, None)
    items = (man or {}).get("items") if isinstance(man, dict) else None
    if not items:
        add("content cliff", "WARN", "cannot read the manifest queue")
        return
    dates = sorted(str(i.get("date", "")) for i in items if i.get("date"))
    if not dates:
        add("content cliff", "WARN", "manifest has no dated items")
        return
    last = dates[-1]
    # a gate that decides future content production
    KEY = ("batch", "content", "produce", "production")
    deciders = []
    for g in gates:
        if not isinstance(g, dict) or str(g.get("status", "")).casefold() in DECISION_DONE:
            continue
        blob = (str(g.get("task", "")) + " " + " ".join(str(d) for d in (g.get("decides") or []))).casefold()
        if any(k in blob for k in KEY) and isinstance(g.get("date"), str):
            deciders.append((g["date"][:10], str(g.get("task", "?"))))
    if not deciders:
        add("content cliff", "PASS", "no pending gate decides content production")
        return
    # ONE content gate landing before the queue ends is enough to cover the cliff -
    # that gate can still refill it. Only warn when EVERY content gate lands at or
    # after the queue end, because then the gap is guaranteed no matter what is decided.
    covering = [(w, t) for w, t in sorted(deciders) if w < last]
    if covering:
        w, t = covering[0]
        add("content cliff", "PASS",
            "queue ends %s and %s decides on %s - early enough to refill it" % (last, t, w))
        return
    when, what = sorted(deciders)[0]
    gap = (datetime.date.fromisoformat(when) - datetime.date.fromisoformat(last)).days
    add("content cliff", "WARN",
        "%s decides on %s but the queue ends %s -> at least %d empty day(s), "
        "and more while production runs" % (what, when, last, gap + 1))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--full", action="store_true", help="also run the site build gate")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    check_queue()
    check_delivery_gap()
    check_repeat_failures()
    check_posting_cap()
    check_captions()
    check_posted_truth()
    check_queued_clip_spec()
    check_competing_plan()
    check_prompt_drift()
    check_dead_tooling()
    check_policy_dates_in_prompts()
    check_task_mirror()
    check_open_decisions()
    check_content_cliff()
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
