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
import os, sys, re, json, io, argparse, subprocess, datetime, shutil, hashlib, math
from pathlib import Path
import content_source_gate
from private_runtime import SALES_LOG_FILE

# run_daily.cmd sets PYTHONIOENCODING=utf-8, so the DAILY path always printed fine and
# nobody noticed that the INTERACTIVE path did not: a Thai Windows console is cp874, so
# `py tools\preflight.py` typed by hand (which is exactly what the watchdog and the
# agent-auditor prompts tell an agent to do) rendered every Thai detail as mojibake, and
# any character outside cp874 killed the process outright with UnicodeEncodeError.
# Seven other tools in this repo already do this line; these three had been missed.
# The covered path and the uncovered path were different paths - same shape as note 29.
for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
PIPELINE_DIR = os.path.join(REPO, "pipeline")
MANIFEST = os.path.join(REPO, ".system_control", "content_manifest.json")
SCHEDULE = os.path.join(REPO, "reels", "schedule.json")
CMAP = os.path.join(REPO, "social-autopost", "content_map.json")
LEDGER = os.path.join(REPO, "automation-log", "post-ledger.jsonl")
YTLOG = os.path.join(REPO, ".system_control", "yt_upload_log.json")
SITE = os.path.join(REPO, "site")
DASHBOARD = os.path.join(REPO, "automation-log", "dashboard.html")
REVENUE_READER = os.path.join(PIPELINE_DIR, "revenue_ledger.py")
DASHBOARD_REVENUE_READERS = (
    REVENUE_READER,
    os.path.join(HERE, "log_sale.py"),
    os.path.join(HERE, "import_accesstrade_csv.py"),
    os.path.join(HERE, "private_runtime.py"),
)
DASHBOARD_PRODUCER = os.path.join(PIPELINE_DIR, "dashboard_agent.py")
DASHBOARD_ANALYTICS_INPUTS = (
    os.path.join(REPO, "automation-log", "ga4-snapshot.json"),
    os.path.join(REPO, "automation-log", "ga4-metrics.csv"),
    os.path.join(REPO, "automation-log", "ga4-pages.csv"),
    os.path.join(REPO, "automation-log", "ga4-funnel.csv"),
    os.path.join(REPO, "automation-log", "ga4-pilot-sessions.csv"),
    os.path.join(REPO, "automation-log", "gsc-snapshot.json"),
    os.path.join(REPO, "automation-log", "gsc-queries.csv"),
    os.path.join(REPO, "automation-log", "gsc-pages.csv"),
)
DASHBOARD_ANALYTICS_READERS = (
    os.path.join(PIPELINE_DIR, "decision_readiness.py"),
    os.path.join(PIPELINE_DIR, "observation_snapshot.py"),
    os.path.join(PIPELINE_DIR, "ga4_pull.py"),
    os.path.join(PIPELINE_DIR, "gsc_pull.py"),
    os.path.join(PIPELINE_DIR, "ga4_decision_trust.py"),
    os.path.join(PIPELINE_DIR, "ga4_schema.py"),
    os.path.join(HERE, "content_source_gate.py"),
)
DASHBOARD_CONTRACT_VERSION = "11"
DASHBOARD_GA4_METRIC_GRAIN = "ga4-metrics-source-session-total"
DASHBOARD_GSC_METRIC_GRAIN = "gsc-pages-url-total"
DASHBOARD_MAX_AGE_HOURS = 30
# Test seam. Production resolves the strict analytics reader from pipeline/.
DASHBOARD_READINESS_READER = None

# A feed/content publication - replies and first comments are engagement, not a
# substitute for keeping the owned publishing surfaces alive.
DELIVERY_TYPES = {"text", "video", "image"}
DELIVERY_WARN_DAYS = 2     # nothing shipped for this long -> WARN
DELIVERY_FAIL_DAYS = 3     # ...this long -> FAIL (the 27-30 Jul blackout was 4)

# One failure row is noise. The SAME channel failing again inside this window is a
# standing outage that nobody is watching.
REPEAT_FAIL_WINDOW_DAYS = 3
REPEAT_FAIL_WARN = 2
REPEAT_FAIL_FAIL = 3
POLICY = os.path.join(REPO, ".system_control", "policy.json")

# Written daily by tools/uptime_check.py (the only thing that runs from Task Scheduler
# AND has network). check_ga4_internal_ip compares it against the CIDRs pinned in GA4.
HOST_IP_FILE = os.path.join(REPO, ".system_control", "host_ip.json")
HOST_IP_STALE_DAYS = 7
OFFICIAL_NEWS_SNAPSHOT = os.path.join(
    REPO, "automation-log", "knowledge-base", "official-news-snapshot.json")
OFFICIAL_NEWS_STALE_DAYS = 1
MEDIA_PUBLISH_GUARD = os.path.join(HERE, "media_publish_guard.py")
PUBLIC_IDENTITY_GUARD = os.path.join(HERE, "public_identity_guard.py")
PUBLIC_IDENTITY_TIMEOUT_SECONDS = 180
# The calendar guard performs exact-hash media QA for the active placements.  The
# 25 Aug 2026 daily run measured a valid media-heavy guard at about 52 seconds,
# while this consumer still had the old 45-second generic subprocess budget and
# therefore reported a false "guard unavailable".  Keep a fixed per-guard cap:
# 120 seconds is more than twice the measured high-water mark, but can never turn
# into an unbounded wait if media tooling or a child process genuinely stalls.
CONTENT_CALENDAR_GUARD_TIMEOUT_SECONDS = 120
FFPROBE_BIN = shutil.which("ffprobe")
# Test seams: production leaves these as None and executes the real tools.
QUEUED_CLIP_PROBER = None
MEDIA_GUARD_RUNNER = None

# POSTING-POLICY_antispam_20260702.md rule 2: <=2 posts/day/channel and >=3h between
# posts on the same channel (Pinterest gets 5 pins/day). Comments are not posts.
POST_CAP_LOOKBACK_DAYS = 2


def _reject_json_constant(value):
    raise ValueError("non-finite JSON number: %s" % value)


def _reject_json_duplicates(pairs):
    value = {}
    for key, item in pairs:
        if key in value:
            raise ValueError("duplicate JSON key: %s" % key)
        value[key] = item
    return value


def _strict_json_loads(value):
    """Parse evidence/config JSON without Python's duplicate/NaN extensions."""
    document = json.loads(
        value,
        parse_constant=_reject_json_constant,
        object_pairs_hook=_reject_json_duplicates,
    )
    def require_finite(item):
        if isinstance(item, float) and not math.isfinite(item):
            raise ValueError("non-finite JSON number")
        if isinstance(item, dict):
            for nested in item.values():
                require_finite(nested)
        elif isinstance(item, list):
            for nested in item:
                require_finite(nested)
    require_finite(document)
    return document


def _read_strict_json(path):
    """Return one stable, strict UTF-8 JSON snapshot or raise fail-closed."""
    target = Path(path)
    before = target.stat()
    raw = target.read_bytes()
    after = target.stat()
    if (before.st_size != after.st_size or
            before.st_mtime_ns != after.st_mtime_ns or
            len(raw) != after.st_size):
        raise ValueError("JSON file changed while being read")
    return _strict_json_loads(raw.decode("utf-8-sig"))


def _read_strict_jsonl(path):
    """Read an append-only ledger at one stable newline-committed snapshot."""
    target = Path(path)
    before = target.stat()
    raw = target.read_bytes()
    after = target.stat()
    if (before.st_size != after.st_size or
            before.st_mtime_ns != after.st_mtime_ns or
            len(raw) != after.st_size):
        raise ValueError("JSONL file changed while being read")
    if raw and not raw.endswith(b"\n"):
        raise ValueError("final JSONL row lacks newline commit boundary")
    text = raw.decode("utf-8-sig")
    rows = []
    for line_number, source in enumerate(text.splitlines(), 1):
        if not source.strip():
            raise ValueError("blank JSONL row at line %d" % line_number)
        try:
            row = _strict_json_loads(source)
        except (TypeError, ValueError) as exc:
            raise ValueError("malformed JSON at line %d" % line_number) from exc
        if not isinstance(row, dict):
            raise ValueError("JSONL row %d is not an object" % line_number)
        rows.append(row)
    return rows


def _is_positive_finite_number(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return False
    if isinstance(value, float) and not (float("-inf") < value < float("inf")):
        return False
    return value > 0


def _parse_aware_timestamp(value):
    if not isinstance(value, str) or not value.strip():
        raise ValueError("timestamp is missing")
    parsed = datetime.datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("timestamp has no timezone")
    return parsed.astimezone(RUNLOG_TZ)


def _limits():
    """Read the anti-spam numbers from policy.json, falling back to the documented
    values. Fail-safe on purpose: a missing/broken policy must not silently disable
    the cap - it must behave exactly as the written policy says."""
    fallback = {"default": 2, "pinterest": 5}, 3, {"text", "video", "image"}
    try:
        policy = _read_strict_json(POLICY)
        if not isinstance(policy, dict):
            return fallback
        lim = policy.get("limits") or {}
        if not isinstance(lim, dict):
            return fallback
        caps = lim.get("posts_per_day") or {}
        if not isinstance(caps, dict) or "default" not in caps:
            return fallback
        if (not caps or any(
                not isinstance(channel, str) or not channel.strip() or
                channel != channel.strip().casefold() or
                isinstance(cap, bool) or not isinstance(cap, int) or cap <= 0
                for channel, cap in caps.items())):
            return fallback
        gap = lim.get("min_gap_hours")
        types = lim.get("post_types")
        if not _is_positive_finite_number(gap):
            return fallback
        if (not isinstance(types, list) or not types or
                any(not isinstance(item, str) or not item.strip() for item in types) or
                len(set(types)) != len(types) or set(types) != fallback[2]):
            return fallback
        return caps, gap, set(types)
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
        return _read_strict_json(path)
    except Exception:
        return default


def check_queue():
    """Check the video route; text-draft supply is reported separately in detail.

    ``runway_guard`` compares manifest/schedule/content_map, all of which are video
    routing sources.  Calling this the generic "content queue" hid the fact that a
    healthy knowledge-post library can coexist with an empty video schedule.
    """
    try:
        out = subprocess.run([sys.executable, os.path.join(HERE, "runway_guard.py"), "--json"],
                             capture_output=True, text=True, encoding="utf-8",
                             errors="replace", cwd=REPO)
        data = _strict_json_loads(out.stdout or "{}")
        v = data.get("verdict", "?")
        eff = data.get("effective_runway_days", "?")
        probs = "; ".join(data.get("problems", []))[:200]
        policy = _load(POLICY, {}) or {}
        text_until = (((policy.get("content_supply") or {}).get("text") or {})
                      .get("knowledge_posts_until"))
        text_note = (f"; text drafts declared through {text_until}"
                     if isinstance(text_until, str) and text_until else
                     "; text-draft runway not declared")
        if v == "OK":
            add("video queue", "PASS", f"{eff} day(s) queued, 3 sources agree{text_note}")
        elif v == "LOW_RUNWAY":
            add("video queue", "WARN",
                f"only {eff} video day(s) left - queue the next approved batch{text_note}")
        elif v == "PARKED":
            # An approved pause is not a fault, but it must stay VISIBLE - a park
            # that prints nothing is indistinguishable from a healthy queue, which
            # is how a pause quietly becomes a permanent outage.
            park = data.get("park", {})
            add("video queue", "PASS",
                f"queue parked until {park.get('until')} by {park.get('decided_by')} "
                f"- goes loud the day after{text_note}")
        elif v == "PARK_OVERRUN":
            add("video queue", "FAIL",
                probs or "approved pause expired with the queue still empty")
        elif v == "DRIFT":
            add("video queue", "FAIL", probs or "runway sources disagree")
        else:
            # Whoever adds the next verdict to runway_guard must be told that this
            # consumer does not know it yet, instead of getting a blank FAIL.
            # That is exactly what happened when PARKED was added on 7 Aug 2026.
            add("video queue", "FAIL",
                f"runway_guard returned a verdict preflight does not know: {v!r}"
                + (f" ({probs})" if probs else ""))
    except Exception as exc:
        add("video queue", "FAIL", f"runway_guard did not run: {exc}")


RUNLOG_DIR = os.path.join(REPO, "automation-log")
STUCK_RUN_HOURS = 12
RUNLOG_TZ = datetime.timezone(datetime.timedelta(hours=7))


def check_stuck_runs():
    """A routine that wrote `started` and never wrote a result.

    WHY THIS EXISTS (7 Aug 2026). Five task prompts were changed today to write
    evidence BEFORE calling anything that can fail - the fix for the watchdog that
    died silently for 12 days because its only trace came after the Slack call.
    But evidence nobody reads is not evidence. `log_run.py` keeps the LAST row per
    routine, so a round that begins and dies leaves `status: started` sitting there
    forever, looking no different from a healthy table to anyone not diffing it.

    This closes that loop: a `started` row older than STUCK_RUN_HOURS means a round
    began and never finished. That is precisely the failure the ordering change was
    meant to make visible, so it must be surfaced rather than merely recorded.

    Deliberately NOT a FAIL: a long-running routine can legitimately be mid-flight,
    and this check runs at 08:00 alongside tasks that fire at the same hour.
    """
    import glob as _glob
    latest = {}
    try:
        files = sorted(_glob.glob(os.path.join(RUNLOG_DIR, "20??-??.jsonl")))
    except Exception as exc:
        add("stuck runs", "WARN", "cannot list runlogs: %s" % exc)
        return
    if not files:
        add("stuck runs", "WARN", "no runlog files found - proof-of-run may not be wired")
        return
    read_errors = []
    for fn in files:
        try:
            before = os.stat(fn)
            with io.open(fn, "rb") as handle:
                payload = handle.read()
            after = os.stat(fn)
            if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
                raise ValueError("file changed while being read")
            if payload and not payload.endswith(b"\n"):
                raise ValueError("final JSONL row lacks newline commit boundary")
            text = payload.decode("utf-8")
            for line_number, source in enumerate(text.splitlines(), 1):
                if not source.strip():
                    raise ValueError("blank JSONL row at line %d" % line_number)
                try:
                    e = _strict_json_loads(source)
                except Exception as exc:
                    raise ValueError("malformed JSON at line %d" % line_number) from exc
                if not isinstance(e, dict):
                    raise ValueError("JSONL row %d is not an object" % line_number)
                if "routine" not in e:
                    # Keep unrelated historical rows out of the run lifecycle index.
                    continue
                routine = e.get("routine")
                if not isinstance(routine, str) or not routine.strip() or "ts" not in e:
                    raise ValueError("runlog identity is incomplete at line %d" % line_number)
                try:
                    stamp = datetime.datetime.fromisoformat(
                        str(e["ts"]).strip().replace("Z", "+00:00")
                    )
                    if stamp.tzinfo is None or stamp.utcoffset() is None:
                        raise ValueError("timezone missing")
                    stamp = stamp.astimezone(RUNLOG_TZ)
                except (TypeError, ValueError) as exc:
                    raise ValueError("invalid aware timestamp at line %d" % line_number) from exc
                e = dict(e)
                e["_parsed_ts"] = stamp
                latest[routine.strip()] = e          # keep last per routine
        except (OSError, UnicodeError, ValueError) as exc:
            read_errors.append("%s (%s)" % (os.path.basename(fn), exc))

    if read_errors:
        add("stuck runs", "WARN",
            "runlog state UNKNOWN; unreadable/corrupt evidence -> %s"
            % ", ".join(read_errors[:3]))
        return

    now = datetime.datetime.now(RUNLOG_TZ)
    stuck = []
    for routine, e in sorted(latest.items()):
        if str(e.get("status", "")).lower() != "started":
            continue
        ts = e["_parsed_ts"]
        age = (now - ts).total_seconds() / 3600.0
        if age < -0.1:
            stuck.append("%s (timestamp %.1fh in the future)" % (routine, -age))
        elif age >= STUCK_RUN_HOURS:
            stuck.append("%s (%.0fh ago)" % (routine, age))

    if stuck:
        add("stuck runs", "WARN",
            "%d routine(s) wrote 'started' and never a result; reconciliation required "
            "(do not synthesize a terminal row) -> %s"
            % (len(stuck), ", ".join(stuck[:4])))
    else:
        add("stuck runs", "PASS",
            "%d routine(s) tracked, none stuck mid-run" % len(latest))


MIN_DELIVERABLE_BYTES = 10 * 1024


def check_deliverables():
    """Every product a page offers for sale must have something to hand over.

    WHY THIS EXISTS (9 Aug 2026). site/debt-letter-kit.html says "send the slip in
    this chat and get the 10-page PDF back" three separate times. That PDF does not
    exist - not in the repo, not anywhere on the machine. The page has been live and
    promoted for weeks, and the money endpoint was even audited twice and declared
    healthy, because every check in this repo asked whether the OFFER was reachable
    and none asked whether the THING could actually be delivered.

    That is the worst failure mode available here: not "nobody buys" but "somebody
    buys and we cannot ship". It is also the one that would only be discovered by the
    first paying customer, at maximum cost to trust.

    FAIL, not WARN. preflight FAIL writes an alert and does not halt posting, so this
    is loud without being destructive - which is the correct shape for "stop promoting
    this until you can fill the order".
    """
    try:
        pol = _read_strict_json(POLICY)
    except Exception as exc:
        add("deliverables", "FAIL", "cannot read policy.json: %s" % exc)
        return
    items = ((pol.get("products") or {}).get("items")) or []
    if not items:
        add("deliverables", "FAIL",
            "policy.json has no products block - cannot tell what this site sells")
        return

    # A paused badge is not enough: the original incident had a pause marker while
    # visible payment/order controls remained in the same page.  Scan both the source
    # and generated copy for concrete purchase mechanisms.  The Thai literals are
    # escaped to preserve this file's ASCII-only contract.
    paused_purchase_tokens = {
        'data-buy=': 'buy-intent attribute',
        'rel="sponsored': 'sponsored link',
        'atth.me/': 'affiliate endpoint',
        'line.me/': 'LINE order endpoint',
        'gumroad.com/': 'checkout endpoint',
        'promptpay': 'PromptPay instruction',
        '\u0e1e\u0e23\u0e49\u0e2d\u0e21\u0e40\u0e1e\u0e22\u0e4c': 'PromptPay instruction',
        '\u0e2a\u0e48\u0e07\u0e2a\u0e25\u0e34\u0e1b': 'slip-delivery instruction',
        '199\u0e3f': 'paused-product price',
    }

    missing, unverifiable, ready, paused, unsafe_paused = [], [], 0, 0, []
    authorized_unverifiable = []
    promotion_disabled = 0
    policy_errors, unauthorized_promotions = [], []

    # Own-product click intent must carry a stable product id, and every id must
    # be declared in policy.  Free-form data-note used to create an untraceable
    # purchase path that no authorization switch could disable.
    public_intents, unbound_intents = {}, []
    site_root = os.path.join(REPO, "site")
    if os.path.isdir(site_root):
        for filename in sorted(os.listdir(site_root)):
            if not filename.endswith(".html"):
                continue
            full = os.path.join(site_root, filename)
            try:
                with io.open(full, encoding="utf-8") as handle:
                    text = handle.read()
            except Exception as exc:
                policy_errors.append("cannot inspect %s: %s" % (filename, exc))
                continue
            for product_id in re.findall(r'data-buy\s*=\s*["\']([^"\']+)["\']', text, re.I):
                public_intents.setdefault(product_id, []).append(filename)
            if re.search(r'\bdata-note\s*=', text, re.I):
                unbound_intents.append(filename)

    declared_ids = {it.get("id") for it in items if isinstance(it, dict)}
    for product_id, pages in sorted(public_intents.items()):
        if product_id not in declared_ids:
            policy_errors.append(
                "undeclared data-buy %s in %s" % (product_id, ", ".join(pages[:3])))
    if unbound_intents:
        policy_errors.append(
            "unbound data-note purchase intent in %s" % ", ".join(unbound_intents[:3]))

    for it in items:
        if not isinstance(it, dict):
            policy_errors.append("product row is not an object")
            continue
        pid = it.get("id", "?")
        page = it.get("sold_on") or ""
        deliverable = it.get("deliverable")
        authorized = it.get("promotion_authorized")
        if not isinstance(authorized, bool):
            policy_errors.append("%s has no boolean promotion_authorized" % pid)
        elif not authorized and pid in public_intents:
            unauthorized_promotions.append(
                "%s in %s" % (pid, ", ".join(public_intents[pid][:3])))
        elif not authorized:
            promotion_disabled += 1
        # A retired product is out of scope only if no generated page still
        # exposes its purchase intent. A stale sold_on path must not hide an
        # active promise on another page (for example, an old landing page).
        if (page and not os.path.exists(os.path.join(REPO, page))
                and pid not in public_intents):
            continue
        if not deliverable and page:
            candidates = [os.path.join(REPO, page)]
            site_prefix = "site" + os.sep
            if page.replace("/", os.sep).startswith(site_prefix):
                candidates.append(os.path.join(REPO, page.replace("/", os.sep)[len(site_prefix):]))
            inspected, has_pause, risks = 0, False, []
            for candidate in dict.fromkeys(candidates):
                try:
                    with io.open(candidate, encoding="utf-8") as handle:
                        page_text = handle.read()
                except Exception:
                    continue
                inspected += 1
                has_pause = has_pause or 'data-offer-status="paused"' in page_text
                lower = page_text.casefold()
                for token, label in paused_purchase_tokens.items():
                    if token.casefold() in lower:
                        risks.append("%s in %s" % (label, os.path.relpath(candidate, REPO)))
            if has_pause and inspected and not risks:
                paused += 1
                continue
            if has_pause and risks:
                unsafe_paused.append("%s (%s)" % (pid, ", ".join(sorted(set(risks))[:4])))
                continue
        if not deliverable:
            missing.append("%s (%s promises it, nothing to send)" % (pid, page or "?"))
            continue
        if (not isinstance(deliverable, str) or
                deliverable != deliverable.strip() or not deliverable.strip()):
            policy_errors.append("%s has a malformed deliverable path" % pid)
            continue
        if deliverable.startswith(("gumroad:", "http://", "https://")):
            # Hosted elsewhere - disk cannot answer this. Say so rather than assume.
            unverifiable.append(pid)
            if authorized is True:
                authorized_unverifiable.append(pid)
            continue
        root = os.path.realpath(REPO)
        full = os.path.realpath(os.path.join(root, deliverable))
        try:
            bounded = (not os.path.isabs(deliverable) and
                       os.path.commonpath([root, full]) == root)
        except (OSError, ValueError):
            bounded = False
        if not bounded:
            policy_errors.append(
                "%s local deliverable must be project-relative and inside the project" % pid)
            continue
        try:
            if not os.path.isfile(full):
                missing.append("%s (file listed but absent or not a regular file: %s)"
                               % (pid, deliverable))
                continue
            size = os.path.getsize(full)
        except OSError:
            missing.append("%s (local deliverable cannot be inspected)" % pid)
            continue
        if size < MIN_DELIVERABLE_BYTES:
            missing.append("%s (file is only %d bytes - placeholder?)" % (pid, size))
        else:
            ready += 1

    if policy_errors:
        add("deliverables", "FAIL",
            "own-product policy/intents are malformed -> %s"
            % "; ".join(policy_errors[:4]))
    elif unauthorized_promotions:
        add("deliverables", "FAIL",
            "%d product(s) expose purchase intent while promotion_authorized=false -> %s"
            % (len(unauthorized_promotions), "; ".join(unauthorized_promotions[:3])))
    elif unsafe_paused:
        add("deliverables", "FAIL",
            "%d paused product(s) still expose purchase mechanics -> %s"
            % (len(unsafe_paused), "; ".join(unsafe_paused[:3])))
    elif missing:
        add("deliverables", "FAIL",
            "%d product(s) are on sale with nothing to hand over -> %s"
            % (len(missing), "; ".join(missing[:3])))
    else:
        bits = "%d ready" % ready
        if paused:
            bits += ", %d paused before payment" % paused
        if promotion_disabled:
            bits += ", %d promotion-disabled by policy" % promotion_disabled
        if unverifiable:
            bits += ", %d hosted externally (not checkable from disk): %s" % (
                len(unverifiable), ", ".join(unverifiable[:3]))
        if authorized_unverifiable:
            bits += "; authorized hosted fulfillment is UNVERIFIED, not sale-ready"
        add("deliverables", "WARN" if authorized_unverifiable else "PASS", bits)


def check_delivery_gap():
    """The check that would have caught the 4-day blackout on day one."""
    try:
        rows = _read_strict_jsonl(LEDGER)
    except Exception as exc:
        add("delivery gap", "FAIL", f"cannot read post-ledger: {exc}")
        return
    stamps, invalid = [], []
    today = datetime.date.today()
    for row_number, row in enumerate(rows, 1):
        if row.get("type") not in DELIVERY_TYPES:
            continue
        try:
            stamp = _parse_aware_timestamp(row.get("ts"))
            if stamp.date() > today:
                raise ValueError("content timestamp is in the future")
            stamps.append(stamp.date())
        except (TypeError, ValueError, OverflowError):
            invalid.append(row_number)
    if invalid:
        add("delivery gap", "FAIL", "post-ledger has invalid content timestamp row(s): %s"
            % ",".join(str(item) for item in invalid[:8]))
        return
    if not stamps:
        add("delivery gap", "FAIL", "post-ledger has no content posts at all")
        return
    last = max(stamps)
    gap = (today - last).days
    msg = f"last feed/content post {last.isoformat()} ({gap} day(s) ago)"
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


def _queued_clip_dimensions(path):
    if callable(QUEUED_CLIP_PROBER):
        return str(QUEUED_CLIP_PROBER(path)).strip()
    if not FFPROBE_BIN:
        raise RuntimeError("ffprobe not on PATH")
    result = subprocess.run(
        [FFPROBE_BIN, "-v", "error", "-select_streams", "v:0",
         "-show_entries", "stream=width,height", "-of", "csv=p=0", path],
        capture_output=True, text=True, encoding="utf-8", errors="replace")
    if result.returncode != 0:
        raise RuntimeError((result.stderr or "ffprobe failed")[-160:])
    return (result.stdout or "").strip()


def _queued_clip_media_guard(path, report):
    if callable(MEDIA_GUARD_RUNNER):
        return MEDIA_GUARD_RUNNER(path, report)
    result = subprocess.run(
        [sys.executable, MEDIA_PUBLISH_GUARD, path, "--report", report, "--json"],
        capture_output=True, text=True, encoding="utf-8", errors="replace", cwd=REPO)
    return result.returncode, (result.stdout or result.stderr or "").strip()


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
        add("queued clip spec", "FAIL",
            "policy.json is MISSING - queued media cannot be verified")
        return
    want = f"{want_w},{want_h}"
    sched = _load(SCHEDULE, {}) or {}
    today = datetime.date.today().isoformat()
    future = {d: v for d, v in sched.items() if d >= today}
    if not future:
        add("queued clip spec", "WARN", "nothing queued from today onward")
        return
    bad = []
    for d, v in sorted(future.items()):
        rel = (v or {}).get("file", "")
        path = os.path.join(REPO, "reels", rel)
        if not os.path.exists(path):
            bad.append(f"{d}: {rel or '<none>'} missing on disk")
            continue
        qa_rel = (v or {}).get("qa_report", "")
        if not isinstance(qa_rel, str) or not qa_rel.strip():
            bad.append(f"{d}: {rel} has no hash-bound qa_report")
            continue
        report = os.path.join(REPO, qa_rel)
        if not os.path.isfile(report):
            bad.append(f"{d}: QA receipt {qa_rel} missing on disk")
            continue
        try:
            dims = _queued_clip_dimensions(path)
        except Exception as exc:
            bad.append(f"{d}: dimensions unavailable ({str(exc)[:120]})")
            continue
        if dims != want:
            bad.append(f"{d}: {rel} is {dims or '?'} (spec {want_w}x{want_h})")
            continue
        try:
            guard_rc, guard_detail = _queued_clip_media_guard(path, report)
        except Exception as exc:
            bad.append(f"{d}: media publication guard unavailable ({str(exc)[:120]})")
            continue
        if guard_rc != 0:
            bad.append(f"{d}: watermark/hash QA blocked ({guard_detail[:160] or 'no detail'})")
    if bad:
        add("queued clip spec", "FAIL", "; ".join(bad[:3]))
    else:
        add("queued clip spec", "PASS",
            f"{len(future)} queued clip(s), all {want_w}x{want_h} with hash-bound visual and fresh watermark QA")


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
        # Completed/disabled one-shot tasks are historical records, not live orders.
        # Keep the prompt for auditability but do not grade its past dates against the
        # current channel policy. Other prompt checks use the same frontmatter marker.
        if _RETIRED.match(_description_of(text).strip()):
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
                       capture_output=True, text=True, encoding="utf-8",
                       errors="replace", cwd=REPO)
    tail = (r.stdout or r.stderr).strip().splitlines()
    add("build gate", "PASS" if r.returncode == 0 else "FAIL", tail[-1][:160] if tail else "")


def check_live_release_parity():
    """A clean local build is not production-ready until live bytes attest to it."""
    try:
        r = subprocess.run(
            [sys.executable, os.path.join(HERE, "postdeploy_smoke.py"),
             "--live", "--compare-src", "site"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            cwd=REPO,
            timeout=120,
        )
    except Exception as exc:
        add("live release", "FAIL", "release comparison unavailable: %s" % str(exc)[:100])
        return
    lines = [line.strip() for line in (r.stdout or r.stderr).splitlines() if line.strip()]
    detail = lines[0][:200] if lines else "release comparison returned no detail"
    add("live release", "PASS" if r.returncode == 0 else "FAIL", detail)


def check_privacy_guard():
    """A public-repo privacy failure is a publication/deploy stop, not a CI-only note."""
    script = os.path.join(HERE, "privacy_guard.py")
    try:
        r = subprocess.run([sys.executable, script], capture_output=True, text=True,
                           encoding="utf-8", errors="replace", cwd=REPO, timeout=45)
    except Exception as exc:
        add("privacy guard", "FAIL", "scanner unavailable: %s" % str(exc)[:100])
        return
    if r.returncode == 0:
        add("privacy guard", "PASS", "tracked public-repo records contain no protected data")
    else:
        # Do not echo the matched content here.  The scanner intentionally reports only
        # path/line/category, and operators can run it directly for the detailed inventory.
        add("privacy guard", "FAIL",
            "privacy scan exit %d; block commit/push/deploy and run tools/privacy_guard.py"
            % r.returncode)


def check_automation_policy_guard():
    """One executable owner per task is a publication-safety prerequisite."""
    script = os.path.join(HERE, "automation_policy_guard.py")
    try:
        r = subprocess.run(
            [sys.executable, script],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            cwd=REPO,
            timeout=90,
        )
    except Exception as exc:
        add("automation guard", "FAIL", "guard unavailable: %s" % str(exc)[:100])
        return
    lines = [line.strip() for line in (r.stdout or r.stderr).splitlines() if line.strip()]
    if r.returncode == 0:
        add("automation guard", "PASS", lines[-1][:160] if lines else "automation ownership and action boundaries pass")
        return
    failures = sum(1 for line in lines if line.startswith("FAIL "))
    add(
        "automation guard",
        "FAIL",
        "%d finding(s); block unattended mutation and run tools/automation_policy_guard.py"
        % (failures or 1),
    )


def check_public_identity_guard():
    """Every outward surface must speak only as the configured page identity."""
    try:
        r = subprocess.run([sys.executable, PUBLIC_IDENTITY_GUARD, "--json"],
                           capture_output=True, text=True, encoding="utf-8",
                           errors="replace", cwd=REPO,
                           timeout=PUBLIC_IDENTITY_TIMEOUT_SECONDS)
    except Exception as exc:
        add("public identity", "FAIL", "guard unavailable: %s" % str(exc)[:100])
        return
    try:
        data = _strict_json_loads(r.stdout or "{}")
    except ValueError:
        data = {}
    if r.returncode == 0 and data.get("verdict") == "PASS":
        counts = data.get("counts") or {}
        add("public identity", "PASS",
            "%d page(s), %d caption field(s), %d knowledge row(s), %d outward prompt(s) are page-only"
            % (counts.get("pages", 0), counts.get("caption_fields", 0),
               counts.get("knowledge_rows", 0), counts.get("outward_prompts", 0)))
    else:
        # Guard output is already redacted to path/category, but keep preflight compact.
        findings = data.get("findings") or []
        categories = sorted({str(item.get("category", "UNKNOWN"))
                             for item in findings if isinstance(item, dict)})
        detail = ", ".join(categories[:4]) or "guard unavailable or malformed"
        add("public identity", "FAIL",
            "%d finding(s): %s; run tools/public_identity_guard.py"
            % (len(findings), detail))


def check_manifest_contract():
    """Historical evidence drift may never be interpreted as a fresh publish backlog."""
    script = os.path.join(HERE, "manifest_contract.py")
    try:
        r = subprocess.run([sys.executable, script], capture_output=True, text=True,
                           encoding="utf-8", errors="replace", cwd=REPO, timeout=30)
    except Exception as exc:
        add("manifest contract", "FAIL", "guard unavailable: %s" % str(exc)[:100])
        return
    tail = (r.stdout or r.stderr).strip().splitlines()
    detail = tail[-1][:160] if tail else "manifest guard returned no detail"
    add("manifest contract", "PASS" if r.returncode == 0 else "FAIL", detail)


def check_content_calendar_contract():
    """Report calendar structure separately from authority to publish it."""
    script = os.path.join(HERE, "content_calendar_guard.py")
    try:
        r = subprocess.run(
            [sys.executable, script, "--json"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            cwd=REPO,
            timeout=CONTENT_CALENDAR_GUARD_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired:
        add(
            "calendar structure",
            "FAIL",
            "guard timed out after %gs (bounded fail-closed)"
            % CONTENT_CALENDAR_GUARD_TIMEOUT_SECONDS,
        )
        add("publish readiness", "FAIL", "calendar structure is unavailable")
        return
    except Exception as exc:
        add("calendar structure", "FAIL", "guard unavailable: %s" % str(exc)[:100])
        add("publish readiness", "FAIL", "calendar structure is unavailable")
        return
    try:
        data = _strict_json_loads(r.stdout or "{}")
    except ValueError:
        data = {}
    counts = data.get("counts") if isinstance(data.get("counts"), dict) else {}
    process_state = data.get("process_state")
    exit_contract = {
        "PASS": (0, "PASS"),
        "COMPLETED_BLOCKED": (1, "COMPLETED_BLOCKED"),
        "BLOCKED": (2, "FAIL"),
        "STRUCTURAL_FINDINGS": (3, "FAIL"),
        "RUNNER_FAILED": (3, "FAIL"),
    }
    expected = exit_contract.get(process_state)
    process_valid = bool(
        expected is not None
        and r.returncode == expected[0]
        and data.get("verdict") == expected[1]
    )
    findings = data.get("findings") if isinstance(data.get("findings"), list) else []
    structural_findings = [
        item for item in findings
        if not isinstance(item, dict)
        or item.get("classification") not in {"REPORT_ONLY", "PUBLICATION_BLOCKER"}
    ]
    source_values = [
        counts.get("source_content_evaluated"),
        counts.get("source_content_allowed"),
        counts.get("source_content_blocked"),
        counts.get("source_failure_reasons"),
    ]
    source_contract_valid = bool(
        all(isinstance(value, int) and not isinstance(value, bool) and value >= 0
            for value in source_values)
        and source_values[1] + source_values[2] == source_values[0]
    )
    if not source_contract_valid:
        structural_findings.append({"code": "SOURCE_COUNT_CONTRACT"})
    if process_valid and process_state in {"PASS", "COMPLETED_BLOCKED", "BLOCKED"} and not structural_findings:
        add(
            "calendar structure",
            "PASS",
            "%d placement(s), %d content id(s); content-scoped sources %d evaluated/%d blocked; control=%s, structural contract passed"
            % (
                int(counts.get("placements", 0)),
                int(counts.get("content_ids", 0)),
                source_values[0],
                source_values[2],
                process_state,
            ),
        )
        publishable = int(counts.get("publishable", 0))
        publication_findings = [
            item for item in findings
            if isinstance(item, dict)
            and item.get("classification") == "PUBLICATION_BLOCKER"
        ]
        if process_state == "BLOCKED":
            categories = sorted({str(item.get("code") or "UNKNOWN")
                                 for item in publication_findings})
            add(
                "publish readiness",
                "FAIL",
                "0 publishable; valid control detected publication blockers: %s"
                % (", ".join(categories[:6]) or "unspecified blocker"),
            )
            return
        add(
            "publish readiness",
            "PASS" if publishable > 0 else "WARN",
            ("%d placement(s) explicitly publishable" % publishable
             if publishable > 0 else
             "0 publishable; structural PASS does not authorize posting"),
        )
        return
    add(
        "calendar structure",
        "FAIL",
        "%d structural finding(s); control=%s rc=%s; run tools/content_calendar_guard.py --json"
        % (len(structural_findings), process_state or "INVALID", r.returncode),
    )
    add("publish readiness", "FAIL", "calendar structure did not pass")


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
    try:
        rows = _read_strict_jsonl(LEDGER)
    except Exception as exc:
        add("repeat failures", "FAIL", "cannot read post-ledger: %s" % exc)
        return

    cutoff = datetime.date.today() - datetime.timedelta(days=REPEAT_FAIL_WINDOW_DAYS - 1)
    # Newest successful delivery per channel - used to tell "still broken" from "fixed".
    last_ok = {}
    invalid_rows = []
    for row_number, r in enumerate(rows, 1):
        if r.get("type") in DELIVERY_TYPES:
            ch = r.get("channel")
            try:
                if not isinstance(ch, str) or not ch.strip():
                    raise ValueError("channel is missing")
                stamp = _parse_aware_timestamp(r.get("ts"))
            except (TypeError, ValueError, OverflowError):
                invalid_rows.append(row_number)
                continue
            ch = ch.strip()
            if ch not in last_ok or stamp > last_ok[ch]:
                last_ok[ch] = stamp
    recent = {}
    for row_number, r in enumerate(rows, 1):
        if r.get("type") != "failure":
            continue
        try:
            ch = r.get("channel")
            if not isinstance(ch, str) or not ch.strip():
                raise ValueError("channel is missing")
            stamp = _parse_aware_timestamp(r.get("ts"))
        except (TypeError, ValueError, OverflowError):
            invalid_rows.append(row_number)
            continue
        if stamp.date() < cutoff:
            continue
        recent.setdefault(ch.strip(), []).append((stamp, r))

    if invalid_rows:
        add("repeat failures", "FAIL",
            "post-ledger has invalid delivery/failure row(s): %s"
            % ",".join(str(item) for item in sorted(set(invalid_rows))[:8]))
        return

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
        recovered = ch in last_ok and last_ok[ch] > hits[-1][0]
        if recovered:
            notes.append("%s: %d failures since %s, but RECOVERED - delivered again at %s"
                         % (ch, len(hits), hits[0][0].date().isoformat(),
                            last_ok[ch].isoformat(timespec="minutes")))
            continue
        status = "FAIL" if len(hits) >= REPEAT_FAIL_FAIL else "WARN"
        if status == "FAIL" or worst == "PASS":
            worst = status
        why = str(hits[-1][1].get("text_first80", ""))[:70]
        note = "%s: %d failures since %s -> %s" % (
            ch, len(hits), hits[0][0].date().isoformat(), why)
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
    try:
        rows = _read_strict_jsonl(LEDGER)
    except Exception as exc:
        add("posting cap", "FAIL", "cannot read post-ledger: %s" % exc)
        return

    cutoff = datetime.date.today() - datetime.timedelta(days=POST_CAP_LOOKBACK_DAYS - 1)
    buckets = {}
    invalid_rows = []
    for row_number, r in enumerate(rows, 1):
        kind = str(r.get("type") or "").strip().lower()
        # A status row confirms its write-ahead claim; it is not a second post.
        # The claim itself reserves daily capacity before the external mutation,
        # including the new sha256 YouTube publication path.
        is_claim = kind == "claim"
        if kind not in POST_TYPES and not is_claim:
            continue
        channel = str(r.get("channel") or "").strip()
        if not channel:
            invalid_rows.append(row_number)
            continue
        claim_event_day = None
        if is_claim:
            if str(r.get("status") or "").strip().casefold() != "claimed":
                invalid_rows.append(row_number)
                continue
            scheduled_for = r.get("scheduled_for")
            if not isinstance(scheduled_for, str) or len(scheduled_for) < 10:
                invalid_rows.append(row_number)
                continue
            key_day = scheduled_for[:10]
            scheduled_at = r.get("scheduled_at")
            try:
                claim_event = datetime.datetime.fromisoformat(
                    str(scheduled_at or "").strip().replace("Z", "+00:00")
                )
                if claim_event.tzinfo is None or claim_event.utcoffset() is None:
                    raise ValueError("claim time has no timezone")
                claim_event = claim_event.astimezone(RUNLOG_TZ)
            except (TypeError, ValueError):
                invalid_rows.append(row_number)
                continue
            claim_event_day = claim_event.date()
            gap_known = True
            ts = claim_event.isoformat(timespec="seconds")
        else:
            ts = r.get("ts") or r.get("published_at") or r.get("posted_at")
            if not isinstance(ts, str) or len(ts) < 10:
                invalid_rows.append(row_number)
                continue
            try:
                event_time = datetime.datetime.fromisoformat(
                    ts.strip().replace("Z", "+00:00")
                )
                if event_time.tzinfo is None or event_time.utcoffset() is None:
                    raise ValueError("post time has no timezone")
            except (TypeError, ValueError, OverflowError):
                invalid_rows.append(row_number)
                continue
            # A scheduled clip is seen by the audience on publish_at, not when it was
            # uploaded. Counting by upload time made a legitimate multi-day catch-up
            # run look like a same-day spam burst. Date-only schedules still reserve
            # capacity, but cannot prove an exact gap.
            scheduled = isinstance(r.get("publish_at"), str) and len(r["publish_at"]) >= 10
            key_day = r["publish_at"][:10] if scheduled else ts[:10]
            gap_known = not scheduled
            ts = event_time.astimezone(RUNLOG_TZ).isoformat(timespec="seconds")
        try:
            day = datetime.date.fromisoformat(key_day)
        except Exception:
            invalid_rows.append(row_number)
            continue
        if is_claim and claim_event_day != day:
            invalid_rows.append(row_number)
            continue
        if day < cutoff:
            continue
        buckets.setdefault((channel, key_day), []).append((ts, gap_known))

    if invalid_rows:
        add("posting cap", "FAIL", "post-ledger has unclassifiable post/claim row(s): %s"
            % ",".join(str(line) for line in invalid_rows[:8]))
        return

    today = datetime.date.today().isoformat()
    problems, history = [], []
    for (ch, day), entries in sorted(buckets.items()):
        entries.sort()
        stamps = [t for t, _ in entries]
        # spacing only means something between rows that were actually posted live
        live = [t for t, gap_known in entries if gap_known]
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
# "superseded" is a closed state too: the decision was made and then replaced by a later
# one. Leaving it out kept the 1 Aug threads-video gate warning every single day after it
# had been settled twice over - and a gate that warns about a decision already taken is
# how people learn to skim the open-decisions line.
DECISION_DONE = {"done", "decided", "closed", "resolved", "superseded"}


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
# Allow decoration between the bracket and the word: "[\u26d4 PAUSED ...]" is how one
# retired task is labelled, and \u26d4 is not whitespace, so \\[\\s*PAUSED missed it.
_RETIRED = re.compile(r"\[[^\w\u0e00-\u0e7f]{0,4}\s*(?:\u0e1b\u0e34\u0e14|\u0e1e\u0e31\u0e01|PAUSED|DISABLED|DONE|\u0e40\u0e25\u0e34\u0e01\u0e43\u0e0a\u0e49)")


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
    """Every stored prompt from both roots, for content-only safety scans.

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

    Yields (name, root_label, path). A name in both roots is yielded twice on purpose.
    This helper does not establish which copy is executable; that authority comes from
    the two Claude ``scheduled-tasks.json`` registries checked by automation_policy_guard.
    """
    for label, root in (("cc", OWN_TASKS_DIR), ("cowork", SCHEDULED_DIR)):
        if not os.path.isdir(root):
            continue
        for name in sorted(os.listdir(root)):
            path = os.path.join(root, name, "SKILL.md")
            if os.path.isfile(path):
                yield name, label, path


def check_task_mirror():
    """Compare prompt bytes only; do not infer scheduler ownership here.

    Not a style point. On 1 Aug a guard block was written into the Cowork copy of
    `ngernduangold-pantip-monitor` believing it would change behaviour; the CC scheduler
    reads its own copy and never saw it. Whoever reads the wrong file acts on orders that
    are not in force. WARN, not FAIL: divergence is sometimes legitimate (two different
    jobs that happen to share a name), but it must never be invisible.
    """
    if not (os.path.isdir(OWN_TASKS_DIR) and os.path.isdir(SCHEDULED_DIR)):
        add("prompt byte consistency", "WARN", "one of the two prompt roots is not visible here")
        return
    diverged, only_cc, settled = [], [], []
    for name in sorted(os.listdir(OWN_TASKS_DIR)):
        a = os.path.join(OWN_TASKS_DIR, name, "SKILL.md")
        b = os.path.join(SCHEDULED_DIR, name, "SKILL.md")
        if not os.path.isfile(a):
            continue
        if not os.path.isfile(b):
            only_cc.append(name)
            continue
        try:
            ta = io.open(a, encoding="utf-8", errors="replace").read()
            tb = io.open(b, encoding="utf-8", errors="replace").read()
        except OSError:
            continue
        if ta == tb:
            continue
        # A collision that has ALREADY been resolved is not drift.
        # `ngernduangold-weekly-review` is the worked example: one id once meant two
        # unrelated jobs, so one side was replaced by a tombstone that says "this id
        # moved, report and stop". The two files are supposed to differ - flagging it
        # forever trains the reader to skim past this check, which is how the real
        # divergence on `pantip-monitor` went unnoticed for a day.
        # Only ONE side may be retired: if both sides are live and differ, that is the
        # dangerous case and it still warns.
        ra, rb = bool(_RETIRED.match(_description_of(ta).strip())), \
                 bool(_RETIRED.match(_description_of(tb).strip()))
        if ra != rb:
            settled.append(name)
        else:
            diverged.append(name)
    bits = []
    if diverged:
        bits.append("%d id(s) mean different orders in the two roots -> %s"
                    % (len(diverged), ", ".join(diverged[:4])))
    if only_cc:
        bits.append("%d cc-only task(s) absent from the mirror -> %s"
                    % (len(only_cc), ", ".join(only_cc[:4])))
    if bits:
        if settled:
            bits.append("(%d resolved collision(s) ignored: %s)"
                        % (len(settled), ", ".join(settled[:3])))
        add("prompt byte consistency", "WARN", "; ".join(bits))
    elif settled:
        # Still say it out loud. A resolved collision is fine, but it must not
        # become invisible either - if a tombstone is ever overwritten back into a
        # live prompt, the reader needs to have known the tombstone was there.
        add("prompt byte consistency", "PASS",
            "byte check settled; %d id(s) deliberately retired on one side: %s"
            % (len(settled), ", ".join(settled[:3])))
    else:
        add("prompt byte consistency", "PASS",
            "shared prompt bytes agree; scheduler ownership is checked separately")


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
# A line that quotes the stale phrase in order to ban it, or recalls what a file "used to"
# say, is documentation OF the drift, not the drift. Six separate times on 1 Aug 2026 a
# guard flagged the lesson written about the bug it hunts -- including this check flagging
# the sentence that tells people not to do the thing. Same family as _FORBIDDING.
_ABOUT_DRIFT = re.compile(
    r"\u0e2b\u0e49\u0e32\u0e21\u0e40\u0e02\u0e35\u0e22\u0e19|\u0e40\u0e04\u0e22\u0e40\u0e02\u0e35\u0e22\u0e19|\u0e02\u0e2d\u0e07\u0e40\u0e14\u0e34\u0e21|\u0e40\u0e14\u0e34\u0e21\u0e40\u0e02\u0e35\u0e22\u0e19|\u0e15\u0e32\u0e23\u0e32\u0e07\u0e40\u0e14\u0e34\u0e21|"
    r"\u0e40\u0e04\u0e22\u0e1e\u0e25\u0e32\u0e14|\u0e04\u0e49\u0e32\u0e07\u0e2d\u0e22\u0e39\u0e48|\u0e17\u0e35\u0e48\u0e04\u0e49\u0e32\u0e07|used to|previously|no longer")
# Only a CHANNEL-STATE deadline belongs in policy.json. A content-library rotation
# ("use file A until 1 Aug, file B after") is a schedule, not a channel policy, and the
# check has no business owning it.
_CH_STATE = re.compile(
    # BOTH directions: a channel state word can announce the stop or the restart.
    # First version listed only the stop side, so "\u0e1e\u0e31\u0e19\u0e17\u0e34\u0e1b \u0e40\u0e1b\u0e34\u0e14\u0e2d\u0e35\u0e01\u0e04\u0e23\u0e31\u0e49\u0e07 14 \u0e2a.\u0e04." -
    # a real reopen deadline - slipped through and the suite caught it.
    r"\u0e1e\u0e31\u0e01|\u0e1f\u0e23\u0e35\u0e0b|\u0e40\u0e1f\u0e2a|\u0e42\u0e04\u0e27\u0e15\u0e32|\u0e07\u0e14|\u0e2b\u0e22\u0e38\u0e14|"
    r"\u0e40\u0e1b\u0e34\u0e14\u0e2d\u0e35\u0e01\u0e04\u0e23\u0e31\u0e49\u0e07|\u0e01\u0e25\u0e31\u0e1a\u0e21\u0e32|\u0e04\u0e37\u0e19\u0e0a\u0e48\u0e2d\u0e07|\u0e17\u0e1a\u0e17\u0e27\u0e19|FROZEN|"
    r"pause|paused|frozen|freeze|quota|phase|hold|resume|reopen", re.I)


_DEADLINE = re.compile(
    r"ถึง|จนถึง|หมดอายุ|"
    r"ครบกำหนด|สิ้นสุด|"
    r"กลับมา|เปิดอีกครั้ง|"
    # \b on the English words: without it, "until" fires inside `phase_until` -- the very
    # field name a prompt is supposed to point AT. That made two prompts that were doing the
    # right thing look like offenders. Fifth substring bug of 1 Aug 2026, and this one was
    # inside the check written to catch drift.
    r"\buntil\b|\bthrough\b|\bresume\b|\bexpires?\b|\bdeadline\b|\breopen\b", re.I)


def check_policy_dates_in_prompts():
    """A prompt must never carry a channel's own expiry/decision date - it must point at policy.json.

    check_prompt_drift only compares ISO dates, so "Pantip FROZEN ถึง 16 ก.ค." sat in a live
    prompt for two weeks while preflight said PASS. The dangerous reading is not the stale
    date itself, it is the inference: "16 ก.ค. has passed, so the freeze is over."
    The rule is therefore about WHERE the fact lives, not whether the copy is currently right.

    FAIL for prompts this agent owns; WARN with names for the other root, same split as
    check_dead_tooling -- we cannot rewrite Cowork's prompts, but the finding must stay visible.
    """
    own, other, scanned, skipped_retired = [], [], 0, 0
    for name, label, path in task_prompts():
        scanned += 1
        try:
            body = io.open(path, encoding="utf-8", errors="replace").read()
        except OSError:
            continue
        # Same rule as check_dead_tooling: a retired task quoting an expired window is a
        # record of what was true, not an instruction anyone will follow. Without this the
        # warning listed 20 names of which 13 were closed tasks carrying the same 2 Jul
        # boilerplate -- and a warning nobody can act on is one everybody learns to skip.
        if _RETIRED.search(_description_of(body)):
            skipped_retired += 1
            continue
        for line in body.split("\n"):
            probe = _FILENAMEish.sub(" ", line)      # drop filenames before looking for dates
            if not _DATE_ANY.search(probe):
                continue
            if not _DEADLINE.search(probe):           # a record of what happened, not a deadline
                continue
            if _ABOUT_DRIFT.search(probe):            # explaining the bug is not committing it
                continue
            if not _CH_STATE.search(probe):           # a library rotation is not a channel policy
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
    add("policy dates", "PASS",
        "%d prompt(s) (%d retired, skipped): channel dates live in policy.json only"
        % (scanned, skipped_retired))


SALES_LOG = str(SALES_LOG_FILE)


def _affiliate_revenue_summary():
    """Use the same strict schema-4 event reader as every decision report."""
    if PIPELINE_DIR not in sys.path:
        sys.path.insert(0, PIPELINE_DIR)
    try:
        import revenue_ledger
        return revenue_ledger.read_affiliate_revenue(path=SALES_LOG)
    except Exception as exc:
        return {
            "trusted": False,
            "reconciliation_state": "UNRECONCILED",
            "error": "revenue reader unavailable: %s" % type(exc).__name__,
        }


def _sha256(path):
    selected = os.fspath(path)
    if not os.path.isfile(selected):
        return "MISSING"
    digest = hashlib.sha256()
    with open(selected, "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _combined_sha256(paths):
    """Match dashboard_agent's ordered, path-bound input-set fingerprint."""
    digest = hashlib.sha256()
    for path in paths:
        selected = Path(path)
        digest.update(str(selected.resolve()).encode("utf-8"))
        digest.update(b"\0")
        if not selected.is_file():
            digest.update(b"MISSING\0")
            continue
        digest.update(b"FILE\0")
        with selected.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        digest.update(b"\0")
    return digest.hexdigest()


def _dashboard_meta(document, name):
    match = re.search(
        r'<meta\s+name=["\']' + re.escape(name) +
        r'["\']\s+content=["\']([^"\']*)["\']\s*/?>',
        document,
        flags=re.I,
    )
    return match.group(1).strip() if match else None


def _dashboard_metric(document, name):
    match = re.search(
        r'<(?:b|span)\b[^>]*\bdata-dashboard-metric=["\']' +
        re.escape(name) + r'["\'][^>]*>(.*?)</(?:b|span)>',
        document,
        flags=re.I | re.S,
    )
    if not match:
        return None
    return re.sub(r"<[^>]+>", "", match.group(1)).strip()


def _canonical_expiry(value):
    try:
        selected = datetime.datetime.fromisoformat(
            str(value or "").replace("Z", "+00:00")
        )
    except (TypeError, ValueError):
        return None
    if selected.tzinfo is None or selected.utcoffset() is None:
        return None
    return selected.astimezone(datetime.timezone.utc).isoformat(timespec="seconds")


def _strict_dashboard_count(value, label):
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError("%s metric is invalid" % label)
    return value


def _dashboard_analytics_readiness():
    reader = DASHBOARD_READINESS_READER
    if reader is None:
        if PIPELINE_DIR not in sys.path:
            sys.path.insert(0, PIPELINE_DIR)
        import decision_readiness
        current = decision_readiness.read()
        observed = current.observation
        metrics = observed.get("metrics") if isinstance(observed, dict) else None
        ga4_metrics = (
            metrics.get("ga4_observed_not_decisionable_unless_trusted")
            if isinstance(metrics, dict) else None
        )
        gsc_metrics = (
            metrics.get("gsc_observed_not_decisionable_unless_current")
            if isinstance(metrics, dict) else None
        )
        raw = {
            "ga4": {
                "trusted": current.ga4.trusted,
                "state": current.ga4.state,
                "expires_at": current.ga4.expires_at,
                "sessions": (ga4_metrics.get("sessions")
                             if isinstance(ga4_metrics, dict) else None),
            },
            "gsc": {
                "trusted": current.gsc.trusted,
                "state": current.gsc.state,
                "expires_at": current.gsc.expires_at,
                "clicks": (gsc_metrics.get("clicks")
                           if isinstance(gsc_metrics, dict) else None),
                "impressions": (gsc_metrics.get("impressions")
                                if isinstance(gsc_metrics, dict) else None),
            },
        }
    else:
        raw = reader()
    if not isinstance(raw, dict) or set(raw) != {"ga4", "gsc"}:
        raise ValueError("analytics readiness contract is invalid")
    result = {}
    for source in ("ga4", "gsc"):
        item = raw.get(source)
        if not isinstance(item, dict) or not isinstance(item.get("trusted"), bool):
            raise ValueError("%s readiness trust is invalid" % source)
        state = item.get("state")
        if not isinstance(state, str) or not state.strip():
            raise ValueError("%s readiness state is invalid" % source)
        expiry = _canonical_expiry(item.get("expires_at"))
        if item["trusted"] and (
            expiry is None
            or datetime.datetime.fromisoformat(expiry)
            <= datetime.datetime.now(datetime.timezone.utc)
        ):
            raise ValueError("%s readiness expiry is invalid" % source)
        metric_names = (("sessions",) if source == "ga4"
                        else ("clicks", "impressions"))
        metric_values = {}
        for name in metric_names:
            metric_values[name] = (
                _strict_dashboard_count(item.get(name), "%s %s" % (source, name))
                if item["trusted"] else None
            )
        result[source] = {
            "trusted": item["trusted"],
            "state": state.strip(),
            "expires_at": expiry,
            **metric_values,
        }
    return result


def check_dashboard_provenance():
    """Reject a dashboard that outlives the inputs/code behind its trust label."""
    if not os.path.isfile(DASHBOARD):
        add("dashboard proof", "FAIL", "dashboard artifact is missing")
        return
    try:
        with io.open(DASHBOARD, encoding="utf-8") as handle:
            document = handle.read()
        contract = _dashboard_meta(document, "ngernduangold-dashboard-contract")
        generated = _dashboard_meta(document, "ngernduangold-dashboard-generated-at")
        sales_hash = _dashboard_meta(document, "ngernduangold-sales-input-sha256")
        reader_hash = _dashboard_meta(document, "ngernduangold-revenue-reader-sha256")
        producer_hash = _dashboard_meta(document, "ngernduangold-dashboard-producer-sha256")
        analytics_input_hash = _dashboard_meta(
            document, "ngernduangold-analytics-input-sha256")
        analytics_reader_hash = _dashboard_meta(
            document, "ngernduangold-analytics-reader-sha256")
        trusted = _dashboard_meta(document, "ngernduangold-revenue-trusted")
        state = _dashboard_meta(document, "ngernduangold-revenue-state")
        quality_state = _dashboard_meta(
            document, "ngernduangold-revenue-quality-state")
        revenue_expiry = _dashboard_meta(
            document, "ngernduangold-revenue-expires-at")
        paid_net = _dashboard_meta(document, "ngernduangold-revenue-paid-net-thb")
        paid_count = _dashboard_meta(document, "ngernduangold-revenue-paid-count")
        pending_amount = _dashboard_meta(
            document, "ngernduangold-revenue-pending-amount-thb")
        pending_count = _dashboard_meta(
            document, "ngernduangold-revenue-pending-count")
        ga4_trusted = _dashboard_meta(document, "ngernduangold-ga4-trusted")
        ga4_state = _dashboard_meta(document, "ngernduangold-ga4-state")
        ga4_expiry = _dashboard_meta(document, "ngernduangold-ga4-expires-at")
        ga4_metric_grain = _dashboard_meta(
            document, "ngernduangold-ga4-metric-grain")
        gsc_trusted = _dashboard_meta(document, "ngernduangold-gsc-trusted")
        gsc_state = _dashboard_meta(document, "ngernduangold-gsc-state")
        gsc_expiry = _dashboard_meta(document, "ngernduangold-gsc-expires-at")
        gsc_metric_grain = _dashboard_meta(
            document, "ngernduangold-gsc-metric-grain")
        missing = [name for name, value in (
            ("contract", contract), ("generated_at", generated),
            ("sales hash", sales_hash), ("reader hash", reader_hash),
            ("dashboard producer hash", producer_hash),
            ("analytics input hash", analytics_input_hash),
            ("analytics reader hash", analytics_reader_hash),
            ("revenue trust", trusted), ("revenue state", state),
            ("revenue quality state", quality_state),
            ("revenue expiry", revenue_expiry),
            ("paid revenue", paid_net), ("paid count", paid_count),
            ("pending amount", pending_amount), ("pending count", pending_count),
            ("GA4 trust", ga4_trusted), ("GA4 state", ga4_state),
            ("GA4 expiry", ga4_expiry),
            ("GA4 metric grain", ga4_metric_grain),
            ("GSC trust", gsc_trusted), ("GSC state", gsc_state),
            ("GSC expiry", gsc_expiry),
            ("GSC metric grain", gsc_metric_grain),
        ) if value is None]
        if missing:
            add("dashboard proof", "FAIL", "missing provenance: " + ", ".join(missing))
            return
        if contract != DASHBOARD_CONTRACT_VERSION:
            add("dashboard proof", "FAIL", "dashboard contract is stale")
            return
        if (
            ga4_metric_grain != DASHBOARD_GA4_METRIC_GRAIN
            or gsc_metric_grain != DASHBOARD_GSC_METRIC_GRAIN
        ):
            add("dashboard proof", "FAIL", "dashboard analytics metric grain is invalid")
            return
        if (
            "Date.now() >= deadline" not in document
            or "data-dashboard-source=" not in document
            or "STALE_AT_VIEW" not in document
        ):
            add("dashboard proof", "FAIL", "dashboard runtime expiry enforcement is missing")
            return
        if (sales_hash != _sha256(SALES_LOG_FILE)
                or reader_hash != _combined_sha256(DASHBOARD_REVENUE_READERS)):
            add("dashboard proof", "FAIL", "dashboard revenue input/code hash does not match current state")
            return
        if producer_hash != _sha256(DASHBOARD_PRODUCER):
            add("dashboard proof", "FAIL", "dashboard producer hash does not match current state")
            return
        if analytics_input_hash != _combined_sha256(DASHBOARD_ANALYTICS_INPUTS):
            add("dashboard proof", "FAIL", "dashboard analytics input hash does not match current state")
            return
        if analytics_reader_hash != _combined_sha256(DASHBOARD_ANALYTICS_READERS):
            add("dashboard proof", "FAIL", "dashboard analytics reader hash does not match current state")
            return
        revenue = _affiliate_revenue_summary()
        expected_trust = "true" if revenue.get("trusted") else "false"
        expected_state = revenue.get("reconciliation_state") or "UNRECONCILED"
        expected_quality = revenue.get("quality_state") or "UNAVAILABLE"
        if (trusted != expected_trust or state != expected_state
                or quality_state != expected_quality):
            add("dashboard proof", "FAIL", "dashboard revenue trust label disagrees with strict reader")
            return
        expected_revenue_expiry = (
            _canonical_expiry(revenue.get("trust_expires_at"))
            if revenue.get("trusted") else None
        )
        declared_revenue_expiry = (
            _canonical_expiry(revenue_expiry)
            if revenue_expiry != "UNAVAILABLE" else None
        )
        if (
            declared_revenue_expiry != expected_revenue_expiry
            or (revenue.get("trusted") and declared_revenue_expiry is None)
            or (not revenue.get("trusted") and revenue_expiry != "UNAVAILABLE")
        ):
            add("dashboard proof", "FAIL", "dashboard revenue expiry disagrees with strict reader")
            return
        if revenue.get("trusted"):
            expected_revenue = {
                "paid_net": format(float(revenue["net_revenue_thb"]), ".2f"),
                "paid_count": str(revenue["paid_transactions"]),
                "pending_amount": format(float(revenue["pending_amount_thb"]), ".2f"),
                "pending_count": str(revenue["pending_transactions"]),
            }
        else:
            expected_revenue = {
                "paid_net": "UNAVAILABLE", "paid_count": "UNAVAILABLE",
                "pending_amount": "UNAVAILABLE", "pending_count": "UNAVAILABLE",
            }
        declared_revenue = {
            "paid_net": paid_net, "paid_count": paid_count,
            "pending_amount": pending_amount, "pending_count": pending_count,
        }
        if declared_revenue != expected_revenue:
            add("dashboard proof", "FAIL",
                "dashboard paid/pending revenue values disagree with strict reader")
            return
        analytics = _dashboard_analytics_readiness()
        declared_analytics = {
            "ga4": {"trusted": ga4_trusted, "state": ga4_state,
                    "expires_at": ga4_expiry},
            "gsc": {"trusted": gsc_trusted, "state": gsc_state,
                    "expires_at": gsc_expiry},
        }
        for source in ("ga4", "gsc"):
            expected_source_trust = (
                "true" if analytics[source]["trusted"] else "false"
            )
            if (declared_analytics[source]["trusted"] != expected_source_trust or
                    declared_analytics[source]["state"] != analytics[source]["state"]):
                add(
                    "dashboard proof", "FAIL",
                    "dashboard %s trust label disagrees with strict reader" % source,
                )
                return
            expected_expiry = analytics[source]["expires_at"]
            declared_expiry_text = declared_analytics[source]["expires_at"]
            declared_expiry = (
                _canonical_expiry(declared_expiry_text)
                if declared_expiry_text != "UNAVAILABLE" else None
            )
            if (
                declared_expiry != expected_expiry
                or (analytics[source]["trusted"] and declared_expiry is None)
                or (not analytics[source]["trusted"]
                    and declared_expiry_text != "UNAVAILABLE")
            ):
                add(
                    "dashboard proof", "FAIL",
                    "dashboard %s expiry disagrees with strict reader" % source,
                )
                return
        metric_groups = {
            "revenue": (expected_trust == "true", (
                "revenue-28d", "revenue-paid-count",
                "revenue-pending-amount", "revenue-pending-count",
            )),
            "ga4": (analytics["ga4"]["trusted"], ("ga4-sessions",)),
            "gsc": (analytics["gsc"]["trusted"],
                    ("gsc-impressions", "gsc-clicks")),
        }
        for source, (is_trusted, names) in metric_groups.items():
            values = [_dashboard_metric(document, name) for name in names]
            if any(value is None for value in values):
                add("dashboard proof", "FAIL",
                    "dashboard %s visible metric provenance is missing" % source)
                return
            if not is_trusted and any(value != "UNAVAILABLE" for value in values):
                add("dashboard proof", "FAIL",
                    "dashboard %s is unavailable but renders a numeric value" % source)
                return
            if is_trusted and any(value == "UNAVAILABLE" for value in values):
                add("dashboard proof", "FAIL",
                    "dashboard %s is trusted but renders unavailable" % source)
                return
        expected_visible_analytics = {
            "ga4-sessions": (
                str(analytics["ga4"]["sessions"])
                if analytics["ga4"]["trusted"] else "UNAVAILABLE"
            ),
            "gsc-impressions": (
                str(analytics["gsc"]["impressions"])
                if analytics["gsc"]["trusted"] else "UNAVAILABLE"
            ),
            "gsc-clicks": (
                str(analytics["gsc"]["clicks"])
                if analytics["gsc"]["trusted"] else "UNAVAILABLE"
            ),
        }
        if any(
            _dashboard_metric(document, name) != value
            for name, value in expected_visible_analytics.items()
        ):
            add("dashboard proof", "FAIL",
                "dashboard visible GA4/GSC values disagree with strict reader")
            return
        if revenue.get("trusted"):
            expected_visible_revenue = {
                "revenue-28d": format(float(revenue["net_revenue_thb"]), ",.2f") + chr(3647),
                "revenue-paid-count": str(revenue["paid_transactions"]),
                "revenue-pending-amount": (
                    format(float(revenue["pending_amount_thb"]), ",.2f") + chr(3647)
                ),
                "revenue-pending-count": str(revenue["pending_transactions"]),
            }
            if any(
                _dashboard_metric(document, name) != value
                for name, value in expected_visible_revenue.items()
            ):
                add("dashboard proof", "FAIL",
                    "dashboard visible paid/pending values disagree with strict reader")
                return
        captured = datetime.datetime.fromisoformat(generated)
        if captured.tzinfo is None:
            raise ValueError("generated_at has no timezone")
        now = datetime.datetime.now(datetime.timezone.utc)
        age_hours = (now - captured.astimezone(datetime.timezone.utc)).total_seconds() / 3600
        if age_hours < -0.1:
            add("dashboard proof", "FAIL", "dashboard generated_at is in the future")
        elif age_hours > DASHBOARD_MAX_AGE_HOURS:
            add("dashboard proof", "WARN", f"dashboard is {age_hours:.1f}h old")
        else:
            add(
                "dashboard proof",
                "PASS",
                "dashboard artifact is current and faithfully renders each source trust state",
            )
    except Exception as exc:
        add("dashboard proof", "FAIL", f"dashboard provenance unreadable: {exc}")


def check_sales_recorded():
    """Revenue is decision-ready only from a complete reconciled private export."""
    summary = _affiliate_revenue_summary()
    if summary.get("trusted") is not True:
        error = str(summary.get("error") or "private revenue source is not reconciled")
        add("sales recorded", "WARN",
            "revenue ledger UNRECONCILED; paid revenue is unavailable, not zero (%s)"
            % error[:120])
        return
    paid = int(summary.get("paid_transactions") or 0)
    pending = int(summary.get("pending_transactions") or 0)
    approved = int(summary.get("approved_transactions") or 0)
    if paid:
        add(
            "sales recorded",
            "PASS",
            "%d paid affiliate transaction(s), net %.2f THB in the reconciled 28-day window"
            % (paid, float(summary.get("net_revenue_thb") or 0)),
        )
        return
    if pending or approved:
        add(
            "sales recorded",
            "WARN",
            "0 paid transaction(s); %d pending and %d approved still require settlement reconciliation"
            % (pending, approved),
        )
        return
    add("sales recorded", "PASS", "reconciled 28-day ledger: 0 paid transaction(s)")


GA4_METRICS = os.path.join(REPO, "automation-log", "ga4-metrics.csv")
SYNTHETIC_DIRECT_SHARE = 0.50
GA4_TRUST_EVALUATOR = None


def _ga4_rows():
    if not os.path.exists(GA4_METRICS):
        return None
    try:
        import csv
        with io.open(GA4_METRICS, encoding="utf-8", errors="replace") as fh:
            return list(csv.DictReader(fh))
    except (OSError, ValueError):
        return None


def _ga4_trust_result():
    evaluator = GA4_TRUST_EVALUATOR
    if evaluator is None:
        if PIPELINE_DIR not in sys.path:
            sys.path.insert(0, PIPELINE_DIR)
        from ga4_decision_trust import evaluate_ga4_decision_trust
        evaluator = evaluate_ga4_decision_trust
    return evaluator(POLICY, HOST_IP_FILE)


def check_synthetic_traffic():
    """direct ท่วมแต่ไม่มี engagement เลย = น่าจะเป็น automation ของเราเอง ไม่ใช่คน.

    1 ส.ค. 2026: direct = 166 จาก 209 sessions (79%) โดยมี quiz_start 0 และ affiliate_click 2
    ขณะที่ pantip 18 sessions ให้ quiz_start ทั้ง 2 ครั้งของทั้งเดือน คนจริงที่อ่านจนจบมีพฤติกรรม
    ต่างจากตัวเลขก้อนนี้อย่างสิ้นเชิง และเราเพิ่งพบว่า clicktest ยิง hit ถึง GA4 จริงทุกรอบ
    ถ้าปล่อยไว้ ทุก verdict จะถูกคำนวณบนฐานที่มีทราฟฟิกของเราเองปนอยู่โดยไม่มีใครทักท้วง
    """
    try:
        trust = _ga4_trust_result()
    except Exception as exc:
        add("synthetic traffic", "WARN",
            "GA4 trust check unavailable (%s); traffic-shape diagnosis suppressed"
            % type(exc).__name__)
        return
    if not trust.trusted:
        add("synthetic traffic", "WARN",
            "GA4 Decision Trust=UNTRUSTED; traffic-shape diagnosis suppressed until a trusted recapture")
        return
    rows = _ga4_rows()
    if rows is None:
        add("synthetic traffic", "WARN", "ยังไม่มี ga4-metrics.csv - ตรวจไม่ได้ว่ามีทราฟฟิกของเราเองปนไหม")
        return
    total = 0
    direct_sessions = 0
    direct_quiz = 0
    for r in rows:
        try:
            sess = int(r.get("sessions") or 0)
        except ValueError:
            continue
        total += sess
        if (r.get("source") or "").strip().lower() == "direct":
            direct_sessions += sess
            try:
                direct_quiz += int(r.get("quiz_start") or 0)
            except ValueError:
                pass
    if total <= 0:
        add("synthetic traffic", "PASS", "ยังไม่มี sessions ให้ประเมิน")
        return
    share = direct_sessions / float(total)
    if share > SYNTHETIC_DIRECT_SHARE and direct_quiz == 0:
        add("synthetic traffic", "WARN",
            "direct %d sessions (%.0f%%) โดย quiz_start=0 - ไม่มีสัญญาณว่าอ่านจริง น่าจะเป็น automation ของเราเอง ไม่ใช่คน"
            " -> เช็กว่างานอัตโนมัติตัวไหนเปิดหน้าเว็บโดยไม่ตั้ง traffic_type=internal"
            % (direct_sessions, share * 100))
        return
    add("synthetic traffic", "PASS",
        "direct %d/%d sessions (%.0f%%) quiz_start=%d - สัดส่วนกับ engagement ยังสมเหตุผล"
        % (direct_sessions, total, share * 100, direct_quiz))


def check_ga4_internal_ip():
    """Fail closed through the private GA4 state contract without echoing values."""
    try:
        trust = _ga4_trust_result()
    except Exception as exc:
        add("ga4 internal ip", "FAIL",
            "private GA4 trust check could not run (%s); analytics decisions remain UNTRUSTED"
            % type(exc).__name__)
        return
    if not trust.trusted:
        add("ga4 internal ip", "FAIL",
            "GA4 Decision Trust=UNTRUSTED: %s; private values are intentionally not printed"
            % trust.reason)
        return
    add("ga4 internal ip", "PASS",
        "private egress state is covered; filter is Active/Exclude and no network value was logged")


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
        st = str(g.get("status", "")).strip()
        if st.casefold() in DECISION_DONE:
            continue
        what = str(g.get("task", "?"))
        if st:
            # A gate closed with prose ("CLOSED 9 Aug - ran, could not decide") reads
            # EXACTLY like a gate nobody has touched, because the match is exact-set.
            # Done once on 9 Aug 2026, and the only symptom was a stale OVERDUE line that
            # invited someone to re-decide a question that had already been answered.
            # Say which word is missing instead of staying silent about it.
            what += ' [status "%s" is not one of: %s]' % (st, "/".join(sorted(DECISION_DONE)))
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


def check_official_source_freshness():
    """Report the global monitor; exact publication impact belongs to the calendar.

    This check must never make an unrelated global watch item a site-wide
    publication blocker.  The always-wired content-calendar check separately
    proves exact content_id mappings and fails closed for affected claims.
    """
    snap = _load(OFFICIAL_NEWS_SNAPSHOT, None)
    if not isinstance(snap, dict):
        add("official sources", "WARN",
            "global monitor missing/unreadable; affected content remains fail-closed by the content calendar")
        return
    result = content_source_gate.validate_official_snapshot_contract(
        snap,
        now=datetime.datetime.now(datetime.timezone.utc),
        freshness_hours=OFFICIAL_NEWS_STALE_DAYS * 24,
        strict_all_rows=True,
    )
    if not result.allowed:
        detail = "; ".join(str(item) for item in result.failures[:3])
        add(
            "official sources",
            "WARN",
            "global monitor is not clean/strict (%s); matching content IDs remain fail-closed by exact calendar source gates"
            % (detail or "unknown strict-contract failure"),
        )
        return
    add(
        "official sources",
        "PASS",
        "%d strict schema-3 source fingerprint(s), globally current"
        % len(snap.get("sources") or []),
    )


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
    check_deliverables()
    check_stuck_runs()
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
    check_sales_recorded()
    check_dashboard_provenance()
    check_synthetic_traffic()
    check_ga4_internal_ip()
    check_privacy_guard()
    check_automation_policy_guard()
    check_public_identity_guard()
    check_manifest_contract()
    check_content_calendar_contract()
    check_task_mirror()
    check_official_source_freshness()
    check_open_decisions()
    check_content_cliff()
    check_disclosure()
    check_attribution()
    if args.full:
        check_build_gate()
        check_live_release_parity()

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
