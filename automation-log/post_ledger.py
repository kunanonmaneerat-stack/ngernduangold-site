#!/usr/bin/env python3
"""post_ledger — unified, interrupt-safe dedup ledger for ngernduangold posting.

WHY THIS EXISTS
  ngernduangold posts to Postiz via TWO paths that were blind to each other:
    1) SCHEDULED LOOP   queue-keeper (cron Mon+Thu) + weekly engine -> future-dated posts
    2) AD-HOC INSERT    owner says "post X now" -> integrationSchedulePostTool(type=now)
  The only prior dedup was content_queue.json's BINARY `used` flag (no channel, no
  date, no count) + a "skip days with 2 posts" volume check read from the unreliable
  ask_postiz. An ad-hoc post wrote NEITHER, so the same clip could be posted twice to
  the same channel within a day -- and because Postiz has NO delete/update for a
  scheduled post, a duplicate that slips through WILL fire and is irrecoverable except
  by a human deleting it in the Postiz web UI.

WHAT THIS GIVES (verified by a 3-reviewer adversarial audit, 2026-06-15)
  A single append-only JSONL at a FIXED path that ALL Claude Code posting paths read
  BEFORE the (irrevocable) schedule call and append to immediately after. Dedup decision
  is moved to BEFORE the post -- the only sound response to "no delete".
    - dedup_key = sha1(channel | clip_key | local-date)  -> "this clip, this channel, this day"
    - is_twin() blocks the same canonical clip identity on the same channel forever;
      the rolling window remains available for time-bounded checks around a candidate.
    - per-channel rows: a 4-channel multicast writes 4 rows (record_multicast) so a later
      ad-hoc to ONE of those channels is detected.
    - clip_key resolver: maps mp4 filename / Postiz library id / topic slug -> canonical
      content_queue key, so the ad-hoc path (which only knows a library URL like
      1tBSoLqqVS.mp4) keys the SAME as the engine (which knows 'titleloan').
    - write-ahead claim(): append a 'claimed' row + take a lockfile BEFORE posting; flip
      to 'confirmed' after. A crash leaves a claim that BLOCKS the twin instead of an
      orphan post that invites one.
    - --check is FAIL-CLOSED (exit 2 on twin / unknown clip) so an unattended cron that
      can't prove a candidate is twin-free REFUSES to schedule rather than posting blind.

HONEST LIMITS (do not overclaim -- see POST-PROTOCOL.md "Residual gaps")
  * The ledger only knows posts WE recorded. Posts created out-of-band (Cowork hand-adds
    in the Postiz web UI; a record interrupted between post & append) are invisible until
    a reconcile back-fills them. The ONLY reliable live-queue read is a MANUAL Chrome
    list-view. So:
      - AD-HOC (interactive, human present)  -> live Chrome list-view read is MANDATORY
        before posting; this genuinely closes the owner's "insert -> repost" fear.
      - CRON (unattended)                    -> fail-closed; dedup of out-of-band posts is
        best-effort only until ask_postiz reliability is resolved or a scriptable queue
        read exists.
  * The weekly engine schedules via Chrome (no post_id) -> it records via a post-run
    reconcile, not an MCP-return hook.

stdlib only. PUBLIC repo -> rows carry NO revenue/PII, only channel/clip/date/postId.
"""
import os, sys, json, time, re, hashlib, argparse, datetime, difflib, math
from public_log_sanitize import sanitize_public_record
import post_ledger_identity
import post_ledger_collision

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
LEDGER = os.path.join(HERE, "post-ledger.jsonl")
LOCK = os.path.join(HERE, ".post-ledger.lock")
POLICY = os.path.join(ROOT, ".system_control", "policy.json")
TZ = datetime.timezone(datetime.timedelta(hours=7))          # Asia/Bangkok (no DST)

# Legacy rolling window MUST be >= the furthest forward any path schedules
# (queue-keeper 7-14d, engine up to ~14d). Exact content identity is permanent;
# this window remains for bounded/near checks shared by every writer and checker.
WINDOW_DAYS = 16
SUCCESS_CONFIRM_STATUSES = {
    "posted", "scheduled", "published_confirmed", "delivered_confirmed",
}

# Postiz integrationId -> short channel name (keep in sync with postiz-setup.md)
INTEGRATION_TO_CHANNEL = {
    "cmqcb7csd03u9pm0ysg8l9n4p": "tiktok",
    "cmqdl4omw00mgo80yvlde46ik": "yt",
    "cmqdc6bqm00qkpm0y9tjn0yzv": "ig",
    "cmqdc5wrr051mo80y2fch5qif": "fb",
    "cmqdiamz700b8pm0y9dzztalg": "threads",
}
# Postiz library asset id (the <id> in uploads.postiz.com/<id>.mp4) -> canonical clip_key.
# Seeded with what is known; extend as more library ids are mapped (the ad-hoc path only
# knows the library url, so without this map it would key differently than the engine).
ASSET_TO_KEY = {
    "1tBSoLqqVS": "titleloan",
}
# post_dispatcher.py EXPECTED slug (often the parent dir of the mp4, e.g.
# video-out/debt-consolidate/01.mp4) -> canonical content_queue clip_key. The basename
# is just a scene number ("01") so without this the dispatcher slug resolves to None.
SLUG_TO_KEY = {
    "debt-consolidate": "debt", "credit-score": "score", "save-paycheck": "save",
    "title-loan": "titleloan", "emergency-fund": "em",
}
# valid clip_keys come from content_queue.json; this static fallback lets --check work even
# when the AppData session copy isn't reachable. Keep aligned with content_queue.json.
KNOWN_CLIP_KEYS = {
    "invest", "save", "credit", "books", "em", "debt", "score", "tax", "side", "index",
    "insure", "retire", "track", "compound", "salary15k", "freelance", "easyapprove",
    "install0", "docs", "titleloan",
}
BATCH_CLIP_KEY = re.compile(r"^b\d+-(?:p)?\d+$", re.IGNORECASE)
HASH_CLIP_KEY = re.compile(r"^sha256:[0-9a-f]{64}$", re.IGNORECASE)

CHANNEL_ALIASES = {
    "youtube": "yt", "instagram": "ig", "facebook": "fb", "facebook_feed": "fb_feed",
    "fbfeed": "fb_feed", "tt": "tiktok",
}


def now_local():
    return datetime.datetime.now(TZ)


def norm_channel(ch):
    ch = (ch or "").strip().lower()
    ch = INTEGRATION_TO_CHANNEL.get(ch, ch)        # accept a raw integrationId too
    return CHANNEL_ALIASES.get(ch, ch)


def resolve_clip_key(x):
    """Map whatever a caller has (clip_key | mp4 filename | postiz library id/url | topic)
    to the canonical content_queue clip_key. Returns None if it can't be resolved -- callers
    must treat None as fail-closed (do NOT post a clip you can't identify)."""
    if not x:
        return None
    s = str(x).strip()
    if HASH_CLIP_KEY.fullmatch(s):
        return s.casefold()
    if s in KNOWN_CLIP_KEYS:
        return s
    base = s.rsplit("/", 1)[-1]                     # strip url path
    base = base.split("?", 1)[0]                    # strip query
    stem = base[:-4] if base.lower().endswith(".mp4") else base
    dated_stem = re.sub(r"^\d{4}-\d{2}-\d{2}_", "", stem).lower()
    if BATCH_CLIP_KEY.fullmatch(dated_stem):
        return dated_stem
    if stem in ASSET_TO_KEY:                        # postiz library id
        return ASSET_TO_KEY[stem]
    if stem.startswith("vid_") and stem[4:] in KNOWN_CLIP_KEYS:   # vid_titleloan.mp4
        return stem[4:]
    if stem in KNOWN_CLIP_KEYS:
        return stem
    # dispatcher slug: check the input, the stem, and every path component (the slug is
    # usually the parent dir, e.g. .../video-out/debt-consolidate/01.mp4 -> "debt").
    for cand in [s, stem] + s.replace("\\", "/").split("/"):
        if cand in SLUG_TO_KEY:
            return SLUG_TO_KEY[cand]
    # topic slug variants e.g. "title-loan" -> "titleloan"
    flat = stem.replace("-", "").replace("_", "")
    for k in KNOWN_CLIP_KEYS:
        if flat == k.replace("-", "").replace("_", ""):
            return k
    return None


def make_dedup_key(channel, clip_key, when):
    """THE one definition of identity. `when` may be a date, datetime, or ISO string."""
    ch = norm_channel(channel)
    ck = (clip_key or "").strip()
    if isinstance(when, str):
        d = when[:10]
    elif isinstance(when, (datetime.datetime,)):
        d = when.astimezone(TZ).strftime("%Y%m%d") if when.tzinfo else when.strftime("%Y%m%d")
        return hashlib.sha1(f"{ch}|{ck}|{d}".encode("utf-8")).hexdigest()
    elif isinstance(when, datetime.date):
        d = when.strftime("%Y-%m-%d")
    else:
        d = str(when)[:10]
    d = d.replace("-", "")[:8]
    return hashlib.sha1(f"{ch}|{ck}|{d}".encode("utf-8")).hexdigest()


def make_text_dedup_key(channel, normalized_hash):
    """Permanent same-channel identity for a write-ahead text claim."""
    ch = norm_channel(channel)
    identity = str(normalized_hash or "").strip().casefold()
    if re.fullmatch(r"[0-9a-f]{40}", identity) is None:
        raise ValueError("text identity hash must be exact SHA-1")
    return hashlib.sha1(f"text|{ch}|{identity}".encode("utf-8")).hexdigest()


def _date_of(when):
    if isinstance(when, datetime.datetime):
        return (when.astimezone(TZ) if when.tzinfo else when).date()
    if isinstance(when, datetime.date):
        return when
    return datetime.date.fromisoformat(str(when)[:10])


def _exact_timestamp(value):
    """Return an exact aware timestamp, or ``None`` for date-only/invalid input."""
    if isinstance(value, datetime.datetime):
        stamp = value
    else:
        raw = str(value or "").strip()
        if len(raw) <= 10:
            return None
        try:
            stamp = datetime.datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except ValueError:
            return None
    if stamp.tzinfo is None or stamp.utcoffset() is None:
        return None
    return stamp.astimezone(TZ)


def _text_timestamp(value):
    """Return a canonical timezone-aware publication timestamp."""
    try:
        stamp = datetime.datetime.fromisoformat(str(value).strip().replace("Z", "+00:00"))
    except (TypeError, ValueError) as exc:
        raise ValueError("text publication timestamp must be ISO-8601") from exc
    if stamp.tzinfo is None:
        raise ValueError("text publication timestamp must include a timezone")
    return stamp.astimezone(TZ).isoformat(timespec="seconds")


class LedgerIntegrityError(RuntimeError):
    """Raised when a complete, stable JSONL snapshot cannot be proven readable."""

    def __init__(self, state, path, reason, line=None):
        self.state = state
        self.path = path
        self.reason = reason
        self.line = line
        where = f" line {line}" if line is not None else ""
        super().__init__(f"ledger {state}{where}: {reason}")

    def as_dict(self):
        return {"state": self.state, "path": self.path,
                "line": self.line, "reason": self.reason}


_TEXT_IDENTITY_TYPES = {"text", "comment", "story", "broadcast-scheduled"}
_CLIP_IDENTITY_TYPES = {"claim", "now", "schedule", "manual", "video", "image"}
_NON_IDENTITY_TYPES = {
    "attempt", "failure", "skipped", "heartbeat", "verify", "join", "incident",
    "page-setup", "product-update", "richmenu-updated", "funnel-fix", "status",
}


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


def _stable_file_bytes(path):
    """Read one regular, direct file snapshot or fail closed on concurrent drift."""
    target = os.fspath(path)
    is_junction = getattr(os.path, "isjunction", lambda _path: False)
    if os.path.islink(target) or is_junction(target):
        raise ValueError("policy file must not be a symlink or junction")
    before = os.stat(target)
    with open(target, "rb") as handle:
        raw = handle.read()
    after = os.stat(target)
    before_identity = (
        before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns,
    )
    after_identity = (
        after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns,
    )
    if before_identity != after_identity or len(raw) != after.st_size:
        raise ValueError("policy file changed while it was being read")
    return raw


_NEGATIVE_IDENTITY_STATUSES = {
    "aborted", "cancelled", "canceled", "failed", "failure", "rejected", "skipped",
}


def _row_clip_identity(row, binding=None):
    for field in ("clip_key", "clip_id", "slug", "video"):
        value = row.get(field)
        resolved = resolve_clip_key(value) if value else None
        if resolved:
            return resolved
    if isinstance(binding, dict) and binding.get("kind") == "clip":
        value = str(binding.get("value") or "").strip()
        if value:
            return value
    return None


def _row_text_identity(row, binding=None):
    text_hash_value = str(row.get("text_hash") or "").strip().casefold()
    if text_hash_value:
        return text_hash_value
    text_norm_value = str(row.get("text_norm") or "").strip()
    if text_norm_value:
        return hashlib.sha1(text_norm_value.encode("utf-8")).hexdigest()
    if isinstance(binding, dict) and binding.get("kind") == "text_hash":
        value = str(binding.get("value") or "").strip().casefold()
        if value:
            return value
    return None


def _row_publication_date(row):
    kind = str(row.get("type") or "").strip().lower()
    status = str(row.get("status") or "").strip().lower()
    if kind in {"claim", "schedule", "now", "manual"}:
        fields = ("scheduled_for", "published_at", "posted_at", "ts",
                  "schedule_date", "slot")
    elif kind == "text" and status == "claimed":
        # ``posted_at`` is the local write-ahead time, not the audience day.
        # Counting it would move a future reservation into today's quota bucket.
        fields = ("scheduled_at", "published_at", "ts", "scheduled_for")
    else:
        # Legacy publication rows often carry an old editorial slot as well as the
        # actual platform timestamp. Count the real publication day when available.
        fields = ("published_at", "posted_at", "ts", "scheduled_for",
                  "schedule_date", "slot")
    for field in fields:
        value = row.get(field)
        if value:
            try:
                return _date_of(value)
            except (TypeError, ValueError):
                continue
    return None


def _row_publication_timestamp(row):
    """Return the exact event time; never substitute a local claim/write time.

    Scheduled and claimed rows need ``scheduled_at`` (or another explicit event
    timestamp). Their ``posted_at`` value is commonly just the ledger-write time
    and cannot prove the anti-blast gap.
    """
    kind = str(row.get("type") or "").strip().lower()
    status = str(row.get("status") or "").strip().lower()
    if kind in {"claim", "schedule"} or (kind == "text" and status == "claimed"):
        fields = ("scheduled_at", "published_at", "ts", "scheduled_for")
    else:
        fields = ("published_at", "posted_at", "ts", "scheduled_at", "scheduled_for")
    for field in fields:
        stamp = _exact_timestamp(row.get(field))
        if stamp is not None:
            return stamp
    return None


def _policy_posting_limits(path=None):
    """Read the current cap/gap contract; malformed or unreadable policy fails closed."""
    selected = path or POLICY
    try:
        policy = _strict_json_loads(_stable_file_bytes(selected).decode("utf-8"))
    except (OSError, UnicodeError, ValueError):
        return None, None
    limits = policy.get("limits") if isinstance(policy, dict) else None
    posts = limits.get("posts_per_day") if isinstance(limits, dict) else None
    default = posts.get("default") if isinstance(posts, dict) else None
    gap = limits.get("min_gap_hours") if isinstance(limits, dict) else None
    if (
        not isinstance(default, int) or isinstance(default, bool) or default <= 0
        or not isinstance(gap, (int, float)) or isinstance(gap, bool) or gap <= 0
    ):
        return None, None
    caps = {"default": default}
    for channel, value in posts.items():
        if channel == "default":
            continue
        if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
            return None, None
        caps[norm_channel(channel)] = value
    return caps, float(gap)


def _identity_coverage(numbered_rows, bindings=None, binding_report=None):
    """Describe legacy rows that cannot provide a complete dedup identity.

    Legacy JSON objects remain readable and available to existing consumers.  Coverage
    is reported separately so a caller never mistakes a syntactically healthy ledger
    for complete historical identity coverage.
    """
    bindings = bindings or {}
    complete = 0
    incomplete = []
    ignored = 0
    for line_no, row in numbered_rows:
        binding = bindings.get(line_no)
        kind = str(row.get("type") or "").strip().lower()
        if kind in _NON_IDENTITY_TYPES:
            ignored += 1
            continue
        reason = None
        if kind in _TEXT_IDENTITY_TYPES:
            has_exact_text = bool(_row_text_identity(row, binding))
            if not str(row.get("channel") or "").strip():
                reason = "channel missing"
            elif not has_exact_text:
                reason = "full text hash/normal form missing; prefix-only identity"
            elif not (row.get("published_at") or row.get("posted_at") or row.get("ts")):
                reason = "publication timestamp missing"
            else:
                try:
                    _text_timestamp(
                        row.get("published_at") or row.get("posted_at") or row.get("ts")
                    )
                except ValueError:
                    reason = "publication timestamp invalid or timezone missing"
        elif kind in _CLIP_IDENTITY_TYPES:
            if not str(row.get("channel") or "").strip():
                reason = "channel missing"
            elif not _row_clip_identity(row, binding):
                reason = "canonical clip identity missing or unresolved"
            elif _row_publication_date(row) is None:
                reason = "publication/schedule date missing or invalid"
        else:
            # Unknown historical event types are preserved, but are not silently
            # represented as publication identities.
            ignored += 1
            continue
        if reason:
            incomplete.append({"line": line_no, "type": kind or "unknown",
                               "channel": str(row.get("channel") or ""),
                               "reason": reason})
        else:
            complete += 1
    binding_invalid = (binding_report or {}).get("state") == "INVALID"
    return {
        "state": "UNKNOWN" if binding_invalid else (
            "INCOMPLETE" if incomplete else "COMPLETE"
        ),
        "complete_rows": complete,
        "incomplete_rows": len(incomplete),
        "legacy_incomplete": incomplete,
        "ignored_non_identity_rows": ignored,
        "binding_state": (binding_report or {}).get("state", "NOT_PRESENT"),
        "applied_binding_rows": len(bindings),
    }


def _identity_coverage_for_channel(rows, channel, bindings=None,
                                   binding_report=None):
    """Return coverage only for identities comparable on one channel.

    Exact dedup identity is ``(channel, identity)``.  Missing legacy text on an
    unrelated channel cannot make a duplicate on the requested channel, while
    any incomplete row on the requested channel must still block fail-closed.
    Global completeness remains available for audit and is not weakened.
    """
    selected = norm_channel(channel)
    numbered = [
        (line_no, row)
        for line_no, row in enumerate(rows, 1)
        if (
            str(row.get("type") or "").strip().lower()
            in _TEXT_IDENTITY_TYPES | _CLIP_IDENTITY_TYPES
            and norm_channel(row.get("channel")) == selected
        )
    ]
    return _identity_coverage(numbered, bindings, binding_report)


def _identity_coverage_by_channel(rows, bindings=None, binding_report=None):
    channels = {
        norm_channel(row.get("channel"))
        for row in rows
        if (
            str(row.get("type") or "").strip().lower()
            in _TEXT_IDENTITY_TYPES | _CLIP_IDENTITY_TYPES
            and norm_channel(row.get("channel"))
        )
    }
    return {
        channel: _identity_coverage_for_channel(
            rows, channel, bindings, binding_report
        )
        for channel in sorted(channels)
    }


def _permanent_identity_collisions(rows, bindings=None):
    """Return exact same-channel identities recorded more than once.

    Coverage and collision safety are separate properties: a ledger can have a
    complete identity on every row and still prove that one canonical item was
    published/scheduled twice.  Negative terminal statuses are excluded to avoid
    turning an explicitly cancelled attempt into a false permanent duplicate.
    """
    latest_status = {}
    for row in rows:
        if not isinstance(row, dict) or str(row.get("type") or "").strip().lower() != "status":
            continue
        dedup_key = str(row.get("dedup_key") or "").strip()
        if dedup_key:
            latest_status[dedup_key] = str(row.get("status") or "").strip().lower()

    bindings = bindings or {}
    identities = {}
    for line_no, row in enumerate(rows, 1):
        if not isinstance(row, dict):
            continue
        kind = str(row.get("type") or "").strip().lower()
        if kind not in _TEXT_IDENTITY_TYPES | _CLIP_IDENTITY_TYPES:
            continue
        dedup_key = str(row.get("dedup_key") or "").strip()
        status = latest_status.get(
            dedup_key,
            str(row.get("status") or "").strip().lower(),
        )
        if status in _NEGATIVE_IDENTITY_STATUSES:
            continue
        channel = norm_channel(row.get("channel"))
        identity_type = None
        identity = None
        binding = bindings.get(line_no)
        if kind in _TEXT_IDENTITY_TYPES:
            text_identity = _row_text_identity(row, binding)
            if text_identity:
                identity_type, identity = "text_hash", text_identity
        else:
            clip_identity = _row_clip_identity(row, binding)
            if clip_identity:
                identity_type, identity = "clip", clip_identity
        if not channel or not identity_type or not identity:
            continue
        published = _row_publication_date(row)
        identities.setdefault((identity_type, channel, identity), []).append({
            "line": line_no,
            "date": published.isoformat() if published else None,
            "type": kind,
        })

    collisions = []
    for (identity_type, channel, identity), occurrences in sorted(identities.items()):
        if len(occurrences) < 2:
            continue
        collisions.append({
            "identity_type": identity_type,
            "channel": channel,
            "identity": identity,
            "occurrences": occurrences,
        })
    return collisions


def _error_report(path, state, reason, line=None):
    return {
        "state": state,
        "path": os.path.abspath(path),
        "line": line,
        "reason": reason,
        "row_count": 0,
        "identity_coverage": {
            "state": "UNKNOWN", "complete_rows": 0, "incomplete_rows": 0,
            "legacy_incomplete": [], "ignored_non_identity_rows": 0,
            "binding_state": "UNKNOWN", "applied_binding_rows": 0,
        },
        "identity_binding_report": {
            "state": "UNKNOWN", "binding_count": 0, "applied_lines": [],
            "quarantined_non_reusable": [], "errors": [reason],
        },
        "identity_bindings": {},
        "collision_tombstone_report": {
            "state": "UNKNOWN", "tombstone_count": 0,
            "non_reusable_identities": [], "errors": [reason],
        },
        "collision_tombstones": set(),
        "pending_claims": [],
    }


def _read_ledger_snapshot(path=None):
    """Return ``(rows, report)`` only after validating the whole stable snapshot."""
    target = os.path.abspath(path or LEDGER)
    try:
        before = os.stat(target)
        with open(target, "rb") as handle:
            raw = handle.read()
        after = os.stat(target)
    except FileNotFoundError:
        # Preserve the historical first-write contract: a path that has never existed
        # is a new empty ledger, not a damaged prior history.  An adjacent identity
        # overlay proves prior history did exist, so a missing target in that case is
        # deletion/tampering and must fail closed.
        binding_path = os.path.join(
            os.path.dirname(target), "post-ledger-identity-bindings.jsonl"
        )
        tombstone_path = os.path.join(
            os.path.dirname(target), "post-ledger-collision-tombstones.json"
        )
        if os.path.exists(binding_path) or os.path.exists(tombstone_path):
            return [], _error_report(
                target, "UNKNOWN",
                "ledger is missing while a dedup identity overlay still exists (binding or collision tombstone)",
            )
        # Once bytes exist, every malformed/incomplete state below is fail-closed.
        return [], {
            "state": "OK", "path": target, "line": None,
            "reason": "ledger not yet created (empty initialization)", "row_count": 0,
            "history_state": "NOT_CREATED",
            "identity_coverage": {
                "state": "COMPLETE", "complete_rows": 0, "incomplete_rows": 0,
                "legacy_incomplete": [], "ignored_non_identity_rows": 0,
                "binding_state": "NOT_PRESENT", "applied_binding_rows": 0,
            },
            "identity_binding_report": {
                "state": "NOT_PRESENT", "binding_count": 0, "applied_lines": [],
                "quarantined_non_reusable": [], "errors": [],
            },
            "identity_bindings": {},
            "collision_tombstone_report": {
                "state": "NOT_PRESENT", "tombstone_count": 0,
                "non_reusable_identities": [], "errors": [],
            },
            "collision_tombstones": set(),
            "pending_claims": [],
        }
    except OSError as exc:
        return [], _error_report(target, "UNKNOWN", f"ledger is unreadable: {exc}")
    if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
        return [], _error_report(target, "UNKNOWN", "ledger changed while it was being read")
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        return [], _error_report(target, "CORRUPT", f"invalid UTF-8: {exc}")

    numbered_rows = []
    for line_no, source in enumerate(text.splitlines(), 1):
        if not source.strip():
            # JSONL has one JSON object per physical line.  Treat a whitespace-only
            # physical row as malformed instead of silently collapsing history.
            return [], _error_report(target, "CORRUPT", "blank JSONL row", line_no)
        try:
            row = _strict_json_loads(source)
        except (json.JSONDecodeError, ValueError) as exc:
            detail = getattr(exc, "msg", str(exc))
            column = getattr(exc, "colno", None)
            return [], _error_report(
                target, "CORRUPT",
                "malformed JSON (%s%s)" % (
                    detail, " at column %s" % column if column is not None else ""
                ),
                line_no,
            )
        if not isinstance(row, dict):
            return [], _error_report(target, "CORRUPT", "JSONL row is not an object", line_no)
        numbered_rows.append((line_no, row))

    # Every successful append writes a newline.  A syntactically complete final object
    # without that commit boundary is crash-like and must remain UNKNOWN.
    if raw and not raw.endswith(b"\n"):
        return [], _error_report(target, "UNKNOWN", "final JSON row lacks newline commit boundary",
                                 numbered_rows[-1][0] if numbered_rows else 1)

    base_keys = {}
    status_rows = []
    claims = {}
    for line_no, row in numbered_rows:
        kind = str(row.get("type") or "").strip().lower()
        dedup_key = str(row.get("dedup_key") or "").strip()
        if kind == "claim":
            required = (dedup_key, str(row.get("channel") or "").strip(),
                        str(row.get("clip_key") or "").strip(),
                        str(row.get("scheduled_for") or "").strip())
            if not all(required):
                return [], _error_report(target, "UNKNOWN",
                                         "incomplete write-ahead claim identity", line_no)
            try:
                claim_date = _date_of(row["scheduled_for"])
            except (TypeError, ValueError):
                return [], _error_report(target, "UNKNOWN",
                                         "write-ahead claim date is invalid", line_no)
            expected = make_dedup_key(row["channel"], row["clip_key"], claim_date)
            if dedup_key != expected:
                return [], _error_report(target, "UNKNOWN",
                                         "write-ahead claim dedup_key does not match its identity", line_no)
            if dedup_key in claims:
                return [], _error_report(target, "UNKNOWN",
                                         "duplicate write-ahead claim for one dedup_key", line_no)
            claims[dedup_key] = {"line": line_no, "channel": norm_channel(row["channel"]),
                                 "clip_key": row["clip_key"],
                                 "scheduled_for": claim_date.isoformat()}
        if kind == "text" and str(row.get("status") or "").strip().lower() == "claimed":
            channel = norm_channel(row.get("channel"))
            text_hash_value = str(row.get("text_hash") or "").strip().casefold()
            text_norm_value = str(row.get("text_norm") or "").strip()
            content_id = str(row.get("content_id") or "").strip()
            placement_id = str(row.get("placement_id") or "").strip()
            required = (
                dedup_key, channel, text_hash_value, text_norm_value,
                content_id, placement_id, str(row.get("ts") or "").strip(),
            )
            if not all(required):
                return [], _error_report(
                    target, "UNKNOWN", "incomplete write-ahead text claim identity", line_no
                )
            if placement_id.startswith(content_id + "__") is False:
                return [], _error_report(
                    target, "UNKNOWN", "text claim placement/content binding is invalid", line_no
                )
            if hashlib.sha1(text_norm_value.encode("utf-8")).hexdigest() != text_hash_value:
                return [], _error_report(
                    target, "UNKNOWN", "text claim hash does not match normalized text", line_no
                )
            try:
                _text_timestamp(row.get("ts"))
                expected = make_text_dedup_key(channel, text_hash_value)
            except ValueError:
                return [], _error_report(
                    target, "UNKNOWN", "write-ahead text claim timestamp/hash is invalid", line_no
                )
            if dedup_key != expected:
                return [], _error_report(
                    target, "UNKNOWN", "write-ahead text claim dedup_key does not match", line_no
                )
            if dedup_key in claims:
                return [], _error_report(
                    target, "UNKNOWN", "duplicate write-ahead claim for one dedup_key", line_no
                )
            claims[dedup_key] = {
                "line": line_no,
                "channel": channel,
                "text_hash": text_hash_value,
                "content_id": content_id,
                "placement_id": placement_id,
                "scheduled_for": str(row.get("ts")),
            }
        if kind == "status":
            if not dedup_key or not str(row.get("status") or "").strip():
                return [], _error_report(target, "UNKNOWN", "incomplete status identity", line_no)
            status_rows.append((line_no, dedup_key, row))
        elif dedup_key:
            if dedup_key in base_keys:
                return [], _error_report(
                    target,
                    "UNKNOWN",
                    "multiple base identity rows share one dedup_key; status target is ambiguous",
                    line_no,
                )
            base_keys[dedup_key] = line_no

    latest_status = {}
    for line_no, dedup_key, row in status_rows:
        base_line = base_keys.get(dedup_key)
        if base_line is None or base_line >= line_no:
            return [], _error_report(target, "UNKNOWN",
                                     "orphan/out-of-order status without a prior identity row", line_no)
        latest_status[dedup_key] = row.get("status")

    pending = []
    for dedup_key, claim in claims.items():
        if dedup_key not in latest_status:
            pending.append(dict({"dedup_key": dedup_key}, **claim))
    physical_rows = raw.split(b"\n")[:-1] if raw else []
    row_hashes = {}
    for line_no, payload in enumerate(physical_rows, 1):
        if payload.endswith(b"\r"):
            payload = payload[:-1]
        row_hashes[line_no] = hashlib.sha256(payload).hexdigest().upper()
    bindings, binding_report = post_ledger_identity.load_identity_bindings(
        ledger_path=target,
        rows=[row for _, row in numbered_rows],
        row_sha256=row_hashes,
    )
    collision_tombstones, collision_report = (
        post_ledger_collision.load_collision_tombstones(
            ledger_path=target,
            rows=[row for _, row in numbered_rows],
            row_sha256=row_hashes,
            bindings=bindings if binding_report.get("state") != "INVALID" else {},
            collision_groups=_permanent_identity_collisions(
                [row for _, row in numbered_rows],
                bindings if binding_report.get("state") != "INVALID" else {},
            ),
        )
    )
    coverage = _identity_coverage(numbered_rows, bindings, binding_report)
    report = {
        "state": "OK",
        "path": target,
        "line": None,
        "reason": "",
        "row_count": len(numbered_rows),
        "history_state": "PRESENT",
        "identity_coverage": coverage,
        "identity_binding_report": binding_report,
        "identity_bindings": bindings,
        "collision_tombstone_report": collision_report,
        "collision_tombstones": collision_tombstones,
        "pending_claims": pending,
    }
    return [row for _, row in numbered_rows], report


def inspect_ledger(path=None):
    """Return explicit integrity, identity-coverage, and pending-claim health."""
    _rows, report = _read_ledger_snapshot(path)
    return report


ledger_health = inspect_ledger


def permanent_dedup_completeness(path=None):
    """Return a measurable, fail-closed permanent-dedup coverage decision.

    Integrity and identity completeness are intentionally separate: syntactically
    valid legacy rows can still be unusable for permanent exact dedup.  This helper
    never edits or backfills the append-only ledger.
    """
    rows, report = _read_ledger_snapshot(path)
    coverage = report.get("identity_coverage") or {}
    complete = int(coverage.get("complete_rows") or 0)
    incomplete = int(coverage.get("incomplete_rows") or 0)
    total = complete + incomplete
    ratio = (complete / total) if total else 1.0
    failures = []
    if report.get("state") != "OK":
        failures.append(_integrity_block_reason(report))
    if coverage.get("state") != "COMPLETE":
        failures.append(
            "permanent dedup identity coverage is %s (%d complete, %d incomplete)"
            % (coverage.get("state") or "UNKNOWN", complete, incomplete)
        )
    bindings = report.get("identity_bindings") or {}
    binding_report = report.get("identity_binding_report") or {}
    if binding_report.get("state") == "INVALID":
        failures.append(
            "identity binding overlay is INVALID: %s"
            % "; ".join(binding_report.get("errors") or ["unknown binding failure"])
        )
    collision_report = report.get("collision_tombstone_report") or {}
    if collision_report.get("state") == "INVALID":
        failures.append(
            "collision tombstone registry is INVALID: %s"
            % "; ".join(collision_report.get("errors") or ["unknown tombstone failure"])
        )
    # Even a broken overlay must not hide duplicate identities already native to the
    # base ledger.  Invalid bindings are ignored atomically, while native collisions
    # remain visible alongside the overlay failure.
    all_collisions = (
        _permanent_identity_collisions(
            rows, bindings if binding_report.get("state") != "INVALID" else {}
        )
        if report.get("state") == "OK" else []
    )
    tombstoned_keys = (
        set(report.get("collision_tombstones") or set())
        if collision_report.get("state") == "PASS" else set()
    )
    tombstoned_collisions = []
    collisions = []
    for collision in all_collisions:
        key = (
            collision.get("identity_type"),
            collision.get("channel"),
            collision.get("identity"),
        )
        if key in tombstoned_keys:
            tombstoned_collisions.append(collision)
        else:
            collisions.append(collision)
    if collisions:
        failures.append(
            "permanent dedup history contains %d unresolved duplicate canonical identity group(s)"
            % len(collisions)
        )
    return {
        "state": "PASS" if not failures else "BLOCKED",
        "integrity_state": report.get("state") or "UNKNOWN",
        "identity_coverage_state": coverage.get("state") or "UNKNOWN",
        "complete_rows": complete,
        "incomplete_rows": incomplete,
        "identity_rows": total,
        "coverage_ratio": ratio,
        "coverage_percent": round(ratio * 100.0, 1),
        "duplicate_identity_groups": len(collisions),
        "duplicate_identity_rows": sum(len(item["occurrences"]) for item in collisions),
        "duplicate_identities": collisions,
        "historical_duplicate_identity_groups": len(all_collisions),
        "tombstoned_duplicate_identity_groups": len(tombstoned_collisions),
        "tombstoned_duplicate_identity_rows": sum(
            len(item["occurrences"]) for item in tombstoned_collisions
        ),
        "tombstoned_duplicate_identities": tombstoned_collisions,
        "identity_binding_state": binding_report.get("state") or "UNKNOWN",
        "applied_identity_bindings": int(binding_report.get("binding_count") or 0),
        "quarantined_non_reusable": list(
            binding_report.get("quarantined_non_reusable") or []
        ),
        "collision_tombstone_state": collision_report.get("state") or "UNKNOWN",
        "collision_tombstone_count": int(collision_report.get("tombstone_count") or 0),
        "collision_tombstoned_non_reusable": list(
            collision_report.get("non_reusable_identities") or []
        ),
        "failures": failures,
    }


def permanent_dedup_gate(path=None):
    """Return ``(allowed, reason, metric)`` for publication gate integration."""
    metric = permanent_dedup_completeness(path)
    allowed = metric["state"] == "PASS"
    reason = ("permanent dedup history is complete"
              if allowed else "; ".join(metric["failures"]))
    return allowed, reason, metric


def permanent_dedup_channel_completeness(channel, path=None):
    """Return fail-closed permanent-dedup health for one channel identity space.

    This does not replace the global audit metric.  It is the action-scoped
    decision used by a single-channel publication candidate because the ledger
    contract explicitly permits cross-channel adaptation.
    """
    selected = norm_channel(channel)
    if not selected:
        return {
            "state": "BLOCKED", "channel": "", "integrity_state": "UNKNOWN",
            "identity_coverage_state": "UNKNOWN", "complete_rows": 0,
            "incomplete_rows": 0, "identity_rows": 0, "coverage_ratio": 0.0,
            "coverage_percent": 0.0, "duplicate_identity_groups": 0,
            "duplicate_identity_rows": 0, "duplicate_identities": [],
            "identity_binding_state": "UNKNOWN", "applied_identity_bindings": 0,
            "collision_tombstone_state": "UNKNOWN", "failures": [
                "permanent dedup channel is missing"
            ],
        }
    rows, report = _read_ledger_snapshot(path)
    bindings = report.get("identity_bindings") or {}
    binding_report = report.get("identity_binding_report") or {}
    coverage = _identity_coverage_for_channel(
        rows, selected, bindings, binding_report
    )
    complete = int(coverage.get("complete_rows") or 0)
    incomplete = int(coverage.get("incomplete_rows") or 0)
    total = complete + incomplete
    ratio = (complete / total) if total else 1.0
    failures = []
    if report.get("state") != "OK":
        failures.append(_integrity_block_reason(report))
    if coverage.get("state") != "COMPLETE":
        failures.append(
            "permanent dedup identity coverage for channel %s is %s "
            "(%d complete, %d incomplete)" % (
                selected, coverage.get("state") or "UNKNOWN", complete, incomplete
            )
        )
    if binding_report.get("state") == "INVALID":
        failures.append(
            "identity binding overlay is INVALID: %s"
            % "; ".join(binding_report.get("errors") or ["unknown binding failure"])
        )
    collision_report = report.get("collision_tombstone_report") or {}
    if collision_report.get("state") == "INVALID":
        failures.append(
            "collision tombstone registry is INVALID: %s"
            % "; ".join(collision_report.get("errors") or ["unknown tombstone failure"])
        )
    collisions = [
        item for item in (
            _permanent_identity_collisions(
                rows, bindings if binding_report.get("state") != "INVALID" else {}
            ) if report.get("state") == "OK" else []
        )
        if item.get("channel") == selected
    ]
    tombstoned = set(report.get("collision_tombstones") or set())
    unresolved = [
        item for item in collisions
        if not (
            (
                item.get("identity_type"),
                item.get("channel"),
                item.get("identity"),
            ) in tombstoned
            and collision_report.get("state") == "PASS"
        )
    ]
    if unresolved:
        failures.append(
            "permanent dedup channel %s contains %d unresolved duplicate "
            "canonical identity group(s)" % (selected, len(unresolved))
        )
    return {
        "state": "PASS" if not failures else "BLOCKED",
        "channel": selected,
        "integrity_state": report.get("state") or "UNKNOWN",
        "identity_coverage_state": coverage.get("state") or "UNKNOWN",
        "complete_rows": complete,
        "incomplete_rows": incomplete,
        "identity_rows": total,
        "coverage_ratio": ratio,
        "coverage_percent": round(ratio * 100.0, 1),
        "duplicate_identity_groups": len(unresolved),
        "duplicate_identity_rows": sum(
            len(item.get("occurrences") or []) for item in unresolved
        ),
        "duplicate_identities": unresolved,
        "identity_binding_state": binding_report.get("state") or "UNKNOWN",
        "applied_identity_bindings": int(binding_report.get("binding_count") or 0),
        "collision_tombstone_state": collision_report.get("state") or "UNKNOWN",
        "failures": failures,
    }


def permanent_dedup_channel_gate(channel, path=None):
    metric = permanent_dedup_channel_completeness(channel, path)
    allowed = metric["state"] == "PASS"
    reason = (
        "permanent dedup channel history is complete"
        if allowed else "; ".join(metric["failures"])
    )
    return allowed, reason, metric


def _integrity_block_reason(report):
    state = str((report or {}).get("state") or "UNKNOWN")
    reason = str((report or {}).get("reason") or "ledger integrity is unproven")
    line = (report or {}).get("line")
    location = f" line {line}" if line is not None else ""
    return f"ledger integrity {state}{location}: {reason} -> fail-closed"


def iter_ledger(path=None):
    """Yield rows only after the complete JSONL snapshot proves healthy.

    Malformed middle rows, truncated final rows, unreadable existing files, and unstable
    reads raise ``LedgerIntegrityError``.  A never-created path retains the historical
    empty-ledger initialization contract. No consumer can return early from an apparently
    valid prefix and accidentally hide corruption later in the ledger.
    """
    rows, report = _read_ledger_snapshot(path)
    if report["state"] != "OK":
        raise LedgerIntegrityError(report["state"], report["path"], report["reason"],
                                   report.get("line"))
    yield from rows


def load_index(path=None, since_days=None):
    """Build dedup structures. Resolves status rows (latest wins per dedup_key)."""
    cutoff = None
    if since_days is not None:
        cutoff = now_local().date() - datetime.timedelta(days=since_days)
    path = path or LEDGER
    keys, by_clip, all_by_clip, by_day, status = set(), {}, {}, {}, {}
    by_channel_time, unknown_time_dates = {}, set()
    rows, integrity = _read_ledger_snapshot(path)
    bindings = integrity.get("identity_bindings") or {}
    coverage_by_channel = _identity_coverage_by_channel(
        rows, bindings, integrity.get("identity_binding_report") or {}
    )
    quarantined = set(
        (integrity.get("identity_binding_report") or {}).get(
            "quarantined_non_reusable", []
        )
    )
    collision_tombstones = {
        (channel, identity)
        for identity_type, channel, identity in set(
            integrity.get("collision_tombstones") or set()
        )
        if identity_type == "clip"
    }
    collision_report = integrity.get("collision_tombstone_report") or {}
    if integrity["state"] != "OK":
        return {"keys": keys, "by_clip": by_clip, "all_by_clip": all_by_clip,
                "by_day": by_day, "status": status, "integrity": integrity,
                "by_channel_time": by_channel_time,
                "unknown_time_dates": unknown_time_dates,
                "identity_coverage": integrity["identity_coverage"],
                "identity_coverage_by_channel": coverage_by_channel,
                "pending_claims": integrity["pending_claims"],
                "quarantined_clip_identities": quarantined,
                "collision_tombstone_report": collision_report,
                "collision_tombstoned_clip_identities": collision_tombstones}
    for line_no, r in enumerate(rows, 1):
        kind = str(r.get("type") or "").strip().lower()
        if kind == "status":
            status[r.get("dedup_key")] = r.get("status")
            continue
        d = _row_publication_date(r)
        ch = norm_channel(r.get("channel"))
        binding = bindings.get(line_no)
        is_clip = kind in _CLIP_IDENTITY_TYPES
        is_text = kind in _TEXT_IDENTITY_TYPES
        identity = (
            _row_clip_identity(r, binding) if is_clip
            else _row_text_identity(r, binding) if is_text
            else None
        )
        if d is None or not ch or not identity:
            continue
        if is_clip:
            # Permanent exact-identity index. Build this before applying the rolling
            # cutoff so an old canonical clip can never be reposted on the same channel.
            all_by_clip.setdefault((ch, identity), []).append(d)
        if cutoff and d < cutoff:
            continue
        if is_clip:
            dk = r.get("dedup_key") or make_dedup_key(ch, identity, d)
            keys.add(dk)
            by_clip.setdefault((ch, identity), []).append(d)
        by_day.setdefault((ch, d), 0)
        by_day[(ch, d)] += 1
        stamp = _row_publication_timestamp(r)
        if stamp is None:
            unknown_time_dates.add((ch, d))
        else:
            by_channel_time.setdefault(ch, []).append(stamp)
    return {"keys": keys, "by_clip": by_clip, "all_by_clip": all_by_clip,
            "by_day": by_day, "status": status, "integrity": integrity,
            "by_channel_time": by_channel_time,
            "unknown_time_dates": unknown_time_dates,
            "identity_coverage": integrity["identity_coverage"],
            "identity_coverage_by_channel": coverage_by_channel,
            "pending_claims": integrity["pending_claims"],
            "quarantined_clip_identities": quarantined,
            "collision_tombstone_report": collision_report,
            "collision_tombstoned_clip_identities": collision_tombstones}


def is_twin(index, channel, clip_key, when, window_days=WINDOW_DAYS):
    """Return whether a canonical content identity collides on this channel.

    Same-day dedup keys retain their original diagnostic. The same canonical clip on
    the same channel is otherwise a permanent collision, regardless of age. Cross-
    channel reuse remains allowed because channel is part of the identity.
    """
    integrity = index.get("integrity") or {"state": "UNKNOWN",
                                            "reason": "index has no integrity result"}
    if integrity.get("state") != "OK":
        state = integrity.get("state") or "UNKNOWN"
        reason = integrity.get("reason") or "ledger integrity is unproven"
        line = integrity.get("line")
        location = f" line {line}" if line is not None else ""
        return True, f"ledger integrity {state}{location}: {reason} -> fail-closed", [state]
    collision_report = index.get("collision_tombstone_report") or {}
    if collision_report.get("state") == "INVALID":
        errors = "; ".join(collision_report.get("errors") or ["unknown tombstone failure"])
        return True, f"collision tombstone registry INVALID: {errors} -> fail-closed", ["COLLISION_TOMBSTONE_INVALID"]
    ch = norm_channel(channel)
    if (ch, clip_key) in set(index.get("collision_tombstoned_clip_identities") or set()):
        return (
            True,
            f"content identity {clip_key} has a historical canonical collision on channel={ch} and is permanently non-reusable",
            ["HISTORICAL_CANONICAL_COLLISION_NON_REUSABLE"],
        )
    coverage = (
        index.get("identity_coverage_by_channel") or {}
    ).get(ch, {"state": "COMPLETE", "complete_rows": 0, "incomplete_rows": 0})
    if coverage.get("state") != "COMPLETE":
        complete = int(coverage.get("complete_rows") or 0)
        incomplete = int(coverage.get("incomplete_rows") or 0)
        return (
            True,
            "permanent dedup identity coverage is %s (%d complete, %d incomplete) "
            "-> fail-closed" % (
                coverage.get("state") or "UNKNOWN", complete, incomplete),
            ["IDENTITY_COVERAGE_%s" % (coverage.get("state") or "UNKNOWN")],
        )
    if clip_key in set(index.get("quarantined_clip_identities") or []):
        return (
            True,
            f"content identity {clip_key} is quarantined and non-reusable",
            ["QUARANTINED_NON_REUSABLE"],
        )
    d = _date_of(when)
    dk = make_dedup_key(ch, clip_key, d)
    if dk in index["keys"]:
        return True, "exact dedup_key already in ledger (same clip/channel/day)", [dk]
    permanent_hits = index.get("all_by_clip", {}).get((ch, clip_key), [])
    if permanent_hits:
        hits = sorted({dd.isoformat() for dd in permanent_hits})
        return True, (f"exact content identity already used on channel={ch} "
                      f"for clip={clip_key}: {hits}"), hits
    hits = []
    for dd in index["by_clip"].get((ch, clip_key), []):
        if abs((dd - d).days) <= window_days:
            hits.append(dd.isoformat())
    if hits:
        return True, f"(channel={ch}, clip={clip_key}) within +/-{window_days}d of {d}: {hits}", hits
    return False, "", []


def day_capacity(index, channel, when):
    """Remaining policy slots, counting every exact text/clip identity atomically."""
    if (index.get("integrity") or {}).get("state") != "OK":
        return 0
    ch = norm_channel(channel)
    coverage = (index.get("identity_coverage_by_channel") or {}).get(
        ch, {"state": "COMPLETE"}
    )
    if coverage.get("state") != "COMPLETE":
        return 0
    caps, _gap = _policy_posting_limits()
    if caps is None:
        return 0
    d = _date_of(when)
    used = index["by_day"].get((ch, d), 0)
    return max(0, caps.get(ch, caps["default"]) - used)


def minimum_gap(index, channel, when, min_gap_hours=None):
    """Return ``(allowed, reason)`` for the exact atomic anti-blast gap.

    A date-only historical row near the candidate cannot prove spacing and blocks.
    """
    if (index.get("integrity") or {}).get("state") != "OK":
        return False, "ledger integrity is unproven -> gap fail-closed"
    ch = norm_channel(channel)
    coverage = (index.get("identity_coverage_by_channel") or {}).get(
        ch, {"state": "COMPLETE"}
    )
    if coverage.get("state") != "COMPLETE":
        return False, "ledger identity coverage is incomplete -> gap fail-closed"
    _caps, policy_gap = _policy_posting_limits()
    gap = policy_gap if min_gap_hours is None else min_gap_hours
    if (
        not isinstance(gap, (int, float)) or isinstance(gap, bool) or gap <= 0
    ):
        return False, "minimum-gap policy is missing/invalid -> fail-closed"
    candidate = _exact_timestamp(when)
    if candidate is None:
        return False, "candidate publication time is not exact/timezone-aware -> gap fail-closed"
    horizon = datetime.timedelta(hours=float(gap))
    relevant_days = max(1, int((float(gap) + 23) // 24))
    for unknown_channel, unknown_day in index.get("unknown_time_dates", set()):
        if unknown_channel == ch and abs((unknown_day - candidate.date()).days) <= relevant_days:
            return False, (
                f"channel {ch} has date-only publication evidence near {candidate.isoformat()} "
                "-> exact gap cannot be proven"
            )
    for prior in index.get("by_channel_time", {}).get(ch, []):
        delta = abs(candidate - prior)
        if delta < horizon:
            return False, (
                f"channel {ch} publication gap is {delta.total_seconds() / 3600:.2f}h; "
                f"requires >= {float(gap):g}h"
            )
    return True, "gap passed"


# ---- lock (serialize read-check-post-record across concurrent actors in this env) ----
def _lock_path(path=None):
    """Return a ledger-adjacent lock path; keeps temp-ledger tests out of the repo."""
    target = os.path.abspath(path or LEDGER)
    name = os.path.basename(target)
    if name.lower().endswith(".jsonl"):
        name = name[:-6]
    return os.path.join(os.path.dirname(target), "." + name + ".lock")


def acquire_lock(timeout=20, stale=120, path=None):
    lock_path = _lock_path(path)
    start = time.time()
    while True:
        try:
            fd = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except (FileExistsError, PermissionError):
            # Windows may surface a concurrently-created/deleted lock as EACCES
            # instead of EEXIST. Treat both as contention and retry fail-closed.
            try:
                if time.time() - os.path.getmtime(lock_path) > stale:
                    os.remove(lock_path); continue       # break a stale lock
            except OSError:
                pass
            if time.time() - start > timeout:
                return False
            time.sleep(0.3)
            continue
        try:
            payload = str(os.getpid()).encode()
            if os.write(fd, payload) != len(payload):
                raise OSError("short write while creating ledger lock")
            os.fsync(fd)
        except OSError:
            # An uncommitted lock cannot authorize a writer. Close it, remove the
            # exact lock we just created, and fail closed without entering the ledger.
            try:
                os.close(fd)
            finally:
                try:
                    os.remove(lock_path)
                except OSError:
                    pass
            return False
        else:
            os.close(fd)
            return True


def release_lock(path=None):
    try:
        os.remove(_lock_path(path))
    except OSError:
        pass


def _append(row, path=None):
    row = sanitize_public_record(row)
    with open(path or LEDGER, "a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")
        # The caller still holds the ledger-adjacent lock.  Make the append durable
        # before returning so its finally/release path can never unlock first.
        f.flush()
        os.fsync(f.fileno())


_BANNED = {"revenue", "payout", "income", "commission", "earnings", "phone", "email",
           "ip", "ipaddr", "token", "secret", "password", "ssn"}


def _public_safe(row):
    """Reject obvious revenue/PII field names. Token-boundary match so legitimate keys
    like 'clip_key' (which merely *contains* 'ip') are not false-positives."""
    for k in row:
        tokens = set(re.split(r"[^a-z0-9]+", k.lower()))
        bad = tokens & _BANNED
        if bad:
            raise ValueError(f"refusing PUBLIC-unsafe field '{k}' (token {bad})")


def record_post(channel, clip_key, when, post_id="", video="", topic="",
                ptype="schedule", source="queue-keeper", status="scheduled",
                window_days=WINDOW_DAYS, note="", fmt=""):
    """Append ONE per-channel row. Idempotent: refuse if dedup_key already present."""
    ptype = str(ptype or "").strip()
    if not ptype or ptype.lower() in {"claim", "status"}:
        raise ValueError("record_post cannot mint claim/status transaction rows")
    ck = resolve_clip_key(clip_key) or clip_key
    if (
        ck not in KNOWN_CLIP_KEYS
        and not BATCH_CLIP_KEY.fullmatch(ck)
        and not HASH_CLIP_KEY.fullmatch(ck)
    ):
        raise ValueError(f"unknown clip_key '{clip_key}' (resolve to a content_queue key first)")
    ch = norm_channel(channel)
    d = _date_of(when)
    dk = make_dedup_key(ch, ck, d)
    if not acquire_lock(path=LEDGER):
        return {"dedup_key": dk, "appended": False,
                "reason": "could not acquire ledger lock -> fail-closed"}
    try:
        index = load_index()
        if index["integrity"]["state"] != "OK":
            return {"dedup_key": dk, "appended": False,
                    "reason": "INTEGRITY_BLOCK: " + _integrity_block_reason(index["integrity"])}
        twin, reason, _ = is_twin(index, ch, ck, d, window_days)
        if twin:
            # Preserve the historical idempotent response for a same-day retry while
            # making older exact content identities an explicit permanent duplicate.
            if dk in index["keys"]:
                why = "already recorded"
            elif "dedup identity coverage" in reason:
                why = "DEDUP_COMPLETENESS_BLOCK: " + reason
            else:
                why = "DUPLICATE: " + reason
            return {"dedup_key": dk, "appended": False, "reason": why}
        row = {"dedup_key": dk, "channel": ch, "clip_key": ck, "video": video, "topic": topic,
               "post_id": post_id, "scheduled_for": d.isoformat(),
               "posted_at": now_local().isoformat(timespec="seconds"),
               "type": ptype, "source": source, "status": status, "window_days": window_days}
        if note:
            row["note"] = note
        if fmt:
            row["fmt"] = fmt          # 7-format rotation log (number-shock/compare/myth-bust/pov/checklist/trend-jack/reply-comment)
        _public_safe(row)
        _append(row)
        return {"dedup_key": dk, "appended": True, "row": row}
    finally:
        release_lock(path=LEDGER)


def record_multicast(channels, clip_key, when, post_id="", video="", topic="",
                     ptype="schedule", source="queue-keeper", window_days=WINDOW_DAYS, fmt=""):
    """A multicast MUST write one row per target channel (else a per-channel twin reopens)."""
    out = [record_post(c, clip_key, when, post_id, video, topic, ptype, source,
                       "scheduled", window_days, fmt=fmt) for c in channels]
    assert len([o for o in out if o.get("appended") or o.get("reason") == "already recorded"
                or str(o.get("reason", "")).startswith("DUPLICATE:")]) == len(channels)
    return out


def recent_formats(path=None, n=3):
    """Last n posted content formats (chronological, most-recent-last) for no-repeat rotation.
    Reads `fmt` from post rows (skips status rows). Engine picks a clip whose content_queue
    `format` is NOT in this list -> enforces 'no same format in last 3 posts'."""
    fmts = [r.get("fmt") for r in iter_ledger(path or LEDGER)
            if r.get("type") != "status" and r.get("fmt")]
    return fmts[-n:]


# ---- text-post dedup (POSTING-POLICY_antispam_20260702: no duplicate text per channel) ----
TEXT_DUP_DAYS = 30
TEXT_SIM_THRESHOLD = 0.9

def normalize_text(text):
    """Normalize before hashing/compare: drop URLs, then keep only letters+digits (casefolded).
    isalnum() keeps Thai; spaces/emoji/punctuation vanish so cosmetic edits don't dodge dedup."""
    t = re.sub(r"https?://\S+|www\.\S+|atth\.me/\S+", "", str(text or ""))
    return "".join(ch for ch in t.casefold() if ch.isalnum())


def text_hash(text):
    return hashlib.sha1(normalize_text(text).encode("utf-8")).hexdigest()


def iter_all_text_rows(path=None):
    """Yield text-post rows of every age for permanent exact dedup.

    Legacy prefix-only rows remain intentionally unmatchable: reconstructing an exact
    identity from ``text_first80`` could falsely block distinct full captions.
    """
    for r in iter_ledger(path or LEDGER):
        if str(r.get("type") or "").strip().lower() in _TEXT_IDENTITY_TYPES:
            yield r


def iter_text_rows(days=TEXT_DUP_DAYS, path=None):
    cutoff = now_local() - datetime.timedelta(days=days)
    for r in iter_all_text_rows(path):
        try:
            ts = datetime.datetime.fromisoformat(str(r.get("ts")))
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=TZ)
        except Exception:
            continue
        if ts >= cutoff:
            yield r


def is_duplicate_text(channel, text, days=TEXT_DUP_DAYS, path=None):
    """Return whether text is a duplicate on the same channel.

    Exact normalized hashes are permanent across the complete ledger. Near matches
    retain the existing rolling `days` window. Cross-channel adaptations are allowed.
    """
    rows, integrity = _read_ledger_snapshot(path or LEDGER)
    if integrity["state"] != "OK":
        finding = {"type": "ledger_integrity", "state": integrity["state"],
                   "line": integrity.get("line"), "reason": integrity["reason"]}
        return True, _integrity_block_reason(integrity), finding
    ch = norm_channel(channel)
    coverage = _identity_coverage_for_channel(
        rows,
        ch,
        integrity.get("identity_bindings") or {},
        integrity.get("identity_binding_report") or {},
    )
    if coverage.get("state") != "COMPLETE":
        complete = int(coverage.get("complete_rows") or 0)
        incomplete = int(coverage.get("incomplete_rows") or 0)
        finding = {
            "type": "dedup_completeness",
            "state": coverage.get("state") or "UNKNOWN",
            "complete_rows": complete,
            "incomplete_rows": incomplete,
        }
        return (
            True,
            "permanent dedup identity coverage is %s (%d complete, %d incomplete) "
            "-> fail-closed" % (finding["state"], complete, incomplete),
            finding,
        )
    norm = normalize_text(text)
    if not norm:
        finding = {"type": "text_identity", "state": "UNKNOWN",
                   "reason": "normalized publication text is empty"}
        return True, "text identity UNKNOWN: normalized publication text is empty -> fail-closed", finding
    bindings = integrity.get("identity_bindings") or {}
    text_rows = [
        (line_no, row) for line_no, row in enumerate(rows, 1)
        if str(row.get("type") or "").strip().lower() in _TEXT_IDENTITY_TYPES
    ]
    h = hashlib.sha1(norm.encode("utf-8")).hexdigest()
    for line_no, r in text_rows:
        if norm_channel(r.get("channel")) != ch:
            continue
        prior_hash = _row_text_identity(r, bindings.get(line_no))
        if prior_hash == h:
            return True, "exact duplicate (permanent) of %s post @%s: %s" % (
                ch, r.get("ts"), r.get("text_first80", "")), r
    cutoff = now_local() - datetime.timedelta(days=days)
    for line_no, r in text_rows:
        if norm_channel(r.get("channel")) != ch:
            continue
        try:
            ts = datetime.datetime.fromisoformat(str(r.get("ts")))
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=TZ)
        except (TypeError, ValueError):
            continue
        if ts < cutoff:
            continue
        prior = r.get("text_norm") or str(
            (bindings.get(line_no) or {}).get("text_norm") or ""
        )
        if prior:
            sim = difflib.SequenceMatcher(None, norm, prior).ratio()
            if sim >= TEXT_SIM_THRESHOLD:
                return True, "%.0f%% similar to %s post @%s: %s" % (sim * 100, ch, r.get("ts"), r.get("text_first80", "")), r
    return False, "", None


def record_text_post(channel, text, when="", source="manual", note=""):
    """Atomically check and append one full text-post row; fail closed on duplicates."""
    timestamp = _text_timestamp(when or now_local().isoformat(timespec="seconds"))
    if not acquire_lock(path=LEDGER):
        return {"appended": False, "reason": "could not acquire ledger lock -> fail-closed"}
    try:
        dup, reason, finding = is_duplicate_text(channel, text)
        if dup:
            finding_type = finding.get("type") if isinstance(finding, dict) else None
            prefix = (
                "INTEGRITY_BLOCK: "
                if finding_type in {"ledger_integrity", "text_identity"}
                else "DEDUP_COMPLETENESS_BLOCK: "
                if finding_type == "dedup_completeness"
                else "DUPLICATE: "
            )
            return {"appended": False, "reason": prefix + reason}
        norm = normalize_text(text)
        row = {"type": "text", "channel": norm_channel(channel),
               "text_hash": hashlib.sha1(norm.encode("utf-8")).hexdigest(),
               "text_norm": norm, "text_first80": str(text).replace("\n", " ")[:80],
               "ts": timestamp, "source": source}
        if note:
            row["note"] = note
        _public_safe(row)
        _append(row)
        return {"appended": True, "text_hash": row["text_hash"]}
    finally:
        release_lock(path=LEDGER)


def record_text_publication(channel, text, *, content_id, placement_id,
                            published_at, post_id, platform_evidence,
                            source="manual-reconcile", note=""):
    """Append an evidence-bound text publication receipt.

    ``record_text_post`` remains the lightweight writer used by legacy posting
    paths.  Reconciliation needs stronger identity: an immutable content id, an
    exact account placement id, the platform's publication time/object id, and
    live verification evidence.  This writer keeps the same permanent text
    dedup and append lock while failing closed on incomplete receipts.
    """
    identifier = re.compile(r"^[a-z0-9][a-z0-9._-]*$", re.IGNORECASE)
    content_id = str(content_id or "").strip()
    placement_id = str(placement_id or "").strip()
    post_id = str(post_id or "").strip()
    if not identifier.fullmatch(content_id):
        raise ValueError("content_id is missing or non-canonical")
    if not identifier.fullmatch(placement_id):
        raise ValueError("placement_id is missing or non-canonical")
    if not placement_id.startswith(content_id + "__"):
        raise ValueError("placement_id must be namespaced by content_id")
    if not post_id:
        raise ValueError("platform post_id is required")
    try:
        published = datetime.datetime.fromisoformat(
            str(published_at).strip().replace("Z", "+00:00")
        )
    except (TypeError, ValueError) as exc:
        raise ValueError("published_at must be an ISO-8601 timestamp") from exc
    if published.tzinfo is None:
        raise ValueError("published_at must include a timezone")
    published = published.astimezone(TZ).isoformat(timespec="seconds")
    if not isinstance(platform_evidence, dict):
        raise ValueError("platform_evidence must be an object")
    permalink = platform_evidence.get("permalink")
    if not isinstance(permalink, str) or not permalink.startswith("https://"):
        raise ValueError("platform_evidence.permalink must be HTTPS")
    if not str(text or "").strip():
        raise ValueError("publication text is empty")

    if not acquire_lock(path=LEDGER):
        return {"appended": False, "reason": "could not acquire ledger lock -> fail-closed"}
    try:
        dup, reason, finding = is_duplicate_text(channel, text)
        if dup:
            finding_type = finding.get("type") if isinstance(finding, dict) else None
            prefix = (
                "INTEGRITY_BLOCK: "
                if finding_type in {"ledger_integrity", "text_identity"}
                else "DEDUP_COMPLETENESS_BLOCK: "
                if finding_type == "dedup_completeness"
                else "DUPLICATE: "
            )
            return {"appended": False, "reason": prefix + reason}
        norm = normalize_text(text)
        row = {
            "type": "text",
            "channel": norm_channel(channel),
            "content_id": content_id,
            "placement_id": placement_id,
            "text_hash": hashlib.sha1(norm.encode("utf-8")).hexdigest(),
            "text_norm": norm,
            "text_first80": str(text).replace("\n", " ")[:80],
            "ts": published,
            "posted_at": published,
            "published_at": published,
            "post_id": post_id,
            "status": "published_confirmed",
            "platform_evidence": platform_evidence,
            "source": source,
        }
        if note:
            row["note"] = note
        _public_safe(row)
        _append(row)
        return {
            "appended": True,
            "content_id": content_id,
            "placement_id": placement_id,
            "text_hash": row["text_hash"],
        }
    finally:
        release_lock(path=LEDGER)


def claim_text_publication(channel, text, when, *, content_id, placement_id,
                           source="adhoc", enforce_gap=True):
    """Atomically reserve exact text, daily capacity, and the policy gap.

    This is write-ahead evidence only. The caller must perform no external
    mutation unless this returns ``True`` and must call :func:`confirm` only
    after durable platform success evidence exists.
    """
    if enforce_gap is not True:
        return False, "", "minimum-gap enforcement cannot be disabled -> fail-closed"
    identifier = re.compile(r"^[a-z0-9][a-z0-9._-]*$", re.IGNORECASE)
    content_id = str(content_id or "").strip()
    placement_id = str(placement_id or "").strip()
    if not identifier.fullmatch(content_id):
        return False, "", "content_id is missing or non-canonical -> fail-closed"
    if (
        not identifier.fullmatch(placement_id)
        or not placement_id.startswith(content_id + "__")
    ):
        return False, "", "placement/content binding is invalid -> fail-closed"
    try:
        scheduled_at = _text_timestamp(when)
    except ValueError as exc:
        return False, "", str(exc) + " -> fail-closed"
    norm = normalize_text(text)
    if not norm:
        return False, "", "text identity is empty -> fail-closed"
    text_hash_value = hashlib.sha1(norm.encode("utf-8")).hexdigest()
    dedup_key = make_text_dedup_key(channel, text_hash_value)
    if not acquire_lock(path=LEDGER):
        return False, "", "could not acquire ledger lock -> fail-closed"
    try:
        duplicate, reason, _finding = is_duplicate_text(channel, text)
        if duplicate:
            return False, "", "DUPLICATE_OR_UNKNOWN: " + reason
        index = load_index(since_days=WINDOW_DAYS)
        if index["integrity"]["state"] != "OK":
            return False, "", "INTEGRITY_BLOCK: " + _integrity_block_reason(
                index["integrity"]
            )
        if day_capacity(index, channel, scheduled_at) <= 0:
            return False, "", (
                f"channel {norm_channel(channel)} at daily cap for "
                f"{_date_of(scheduled_at)}"
            )
        gap_allowed, gap_reason = minimum_gap(index, channel, scheduled_at)
        if not gap_allowed:
            return False, "", "GAP: " + gap_reason
        row = {
            "dedup_key": dedup_key,
            "type": "text",
            "status": "claimed",
            "channel": norm_channel(channel),
            "content_id": content_id,
            "placement_id": placement_id,
            "text_hash": text_hash_value,
            "text_norm": norm,
            "text_first80": str(text).replace("\n", " ")[:80],
            "ts": scheduled_at,
            "scheduled_at": scheduled_at,
            "scheduled_for": scheduled_at[:10],
            "posted_at": now_local().isoformat(timespec="seconds"),
            "source": source,
        }
        _public_safe(row)
        _append(row)
        return True, dedup_key, "claimed"
    finally:
        release_lock(path=LEDGER)


def claim(channel, clip_key, when, source="adhoc", window_days=WINDOW_DAYS,
          enforce_gap=True):
    """Write-ahead: take lock, twin-check, append a 'claimed' row BEFORE posting.
    Returns (ok, dedup_key, reason). Caller posts only if ok, then confirm()."""
    if enforce_gap is not True:
        return False, "", "minimum-gap enforcement cannot be disabled -> fail-closed"
    ck = resolve_clip_key(clip_key)
    if not ck:
        return False, "", f"unknown clip '{clip_key}' -> fail-closed (do not post)"
    if not acquire_lock(path=LEDGER):
        return False, "", "could not acquire ledger lock -> fail-closed"
    try:
        idx = load_index(since_days=window_days)
        if idx["integrity"]["state"] != "OK":
            return False, "", "INTEGRITY_BLOCK: " + _integrity_block_reason(idx["integrity"])
        twin, reason, _ = is_twin(idx, channel, ck, when, window_days)
        if twin:
            return False, "", f"TWIN: {reason}"
        if day_capacity(idx, channel, when) <= 0:
            return False, "", f"channel {norm_channel(channel)} at daily cap for {_date_of(when)}"
        gap_allowed, gap_reason = minimum_gap(idx, channel, when)
        if not gap_allowed:
            return False, "", "GAP: " + gap_reason
        dk = make_dedup_key(channel, ck, when)
        row = {"dedup_key": dk, "channel": norm_channel(channel), "clip_key": ck,
               "scheduled_for": _date_of(when).isoformat(),
               "posted_at": now_local().isoformat(timespec="seconds"),
               "type": "claim", "source": source, "status": "claimed",
               "window_days": window_days}
        exact = _exact_timestamp(when)
        if exact is not None:
            row["scheduled_at"] = exact.isoformat(timespec="seconds")
        _append(row)
        return True, dk, "claimed"
    finally:
        release_lock(path=LEDGER)


def confirm(dedup_key, post_id="", status="scheduled"):
    """After a successful post, append a status row (append-only; never edit the claim)."""
    dedup_key = str(dedup_key or "").strip()
    post_id = str(post_id or "").strip()
    status = str(status or "").strip()
    normalized_status = status.casefold()
    if normalized_status not in SUCCESS_CONFIRM_STATUSES:
        raise RuntimeError(
            "UNKNOWN/non-success status cannot confirm a publication claim -> fail-closed"
        )
    if not post_id:
        raise RuntimeError(
            "UNKNOWN platform post_id is required to confirm publication success -> fail-closed"
        )
    if not acquire_lock(path=LEDGER):
        raise RuntimeError("could not acquire ledger lock -> status append failed closed")
    try:
        rows, integrity = _read_ledger_snapshot()
        if integrity["state"] != "OK":
            raise RuntimeError("INTEGRITY_BLOCK: " + _integrity_block_reason(integrity))
        claims = [
            row for row in rows
            if str(row.get("dedup_key") or "").strip() == dedup_key
            and (
                str(row.get("type") or "").strip().lower() == "claim"
                or (
                    str(row.get("type") or "").strip().lower() == "text"
                    and str(row.get("status") or "").strip().lower() == "claimed"
                )
            )
        ]
        if not dedup_key or len(claims) != 1:
            raise RuntimeError("UNKNOWN dedup_key has no exact prior claim -> fail-closed")
        existing = [
            row for row in rows
            if str(row.get("type") or "").strip().lower() == "status"
            and str(row.get("dedup_key") or "").strip() == dedup_key
        ]
        if existing:
            latest = existing[-1]
            if (
                str(latest.get("status") or "").strip().casefold() == normalized_status
                and str(latest.get("post_id") or "").strip() == post_id
            ):
                return
            raise RuntimeError("publication claim already has terminal evidence -> fail-closed")
        _append({"dedup_key": dedup_key, "type": "status", "status": status,
                 "post_id": post_id, "posted_at": now_local().isoformat(timespec="seconds")})
    finally:
        release_lock(path=LEDGER)


def reconcile_status(channel, clip_key, when, status="delivered_confirmed", post_id=""):
    ck = resolve_clip_key(clip_key) or clip_key
    confirm(make_dedup_key(channel, ck, when), post_id, status)


# ---------------------------------- CLI ----------------------------------
def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description="ngernduangold post-ledger / dedup gate")
    sub = ap.add_subparsers(dest="cmd")

    c = sub.add_parser("check", help="FAIL-CLOSED twin/capacity check (exit 2 = collision/unknown)")
    c.add_argument("--channel", required=True)
    c.add_argument("--clip", required=True, help="clip_key | mp4 | postiz id | topic")
    c.add_argument("--date", default=now_local().date().isoformat())
    c.add_argument("--window", type=int, default=WINDOW_DAYS)

    r = sub.add_parser("record", help="append a post row")
    for a in ("channel", "clip"):
        r.add_argument("--" + a, required=True)
    r.add_argument("--date", default=now_local().date().isoformat())
    r.add_argument("--post-id", default="")
    r.add_argument("--video", default="")
    r.add_argument("--topic", default="")
    r.add_argument("--type", default="schedule")
    r.add_argument("--source", default="queue-keeper")
    r.add_argument("--note", default="")
    r.add_argument("--format", default="", help="7-format tag (number-shock/compare/myth-bust/pov/checklist/trend-jack/reply-comment)")

    sub.add_parser("list", help="dump current dedup index summary")

    rf = sub.add_parser("recent-formats", help="last N posted formats (for no-repeat rotation)")
    rf.add_argument("-n", type=int, default=3)

    a = ap.parse_args()
    if a.cmd == "check":
        idx = load_index(since_days=a.window)
        ck = resolve_clip_key(a.clip)
        if not ck:
            print(f"UNKNOWN clip '{a.clip}' -> FAIL-CLOSED (resolve to a content_queue key)")
            sys.exit(2)
        twin, reason, conf = is_twin(idx, a.channel, ck, a.date, a.window)
        cap = day_capacity(idx, a.channel, a.date)
        if twin:
            print(f"COLLISION ({norm_channel(a.channel)}/{ck}/{a.date}): {reason}")
            sys.exit(2)
        if cap <= 0:
            print(f"AT CAP ({norm_channel(a.channel)} on {a.date}) -> do not add")
            sys.exit(2)
        coverage = idx["identity_coverage"]
        if coverage["state"] != "COMPLETE":
            print("NOTICE identity coverage INCOMPLETE: %d legacy publication row(s) "
                  "lack a complete canonical identity" % coverage["incomplete_rows"])
        print(f"CLEAR: {norm_channel(a.channel)}/{ck}/{a.date} no twin in +/-{a.window}d, {cap} slot(s) left")
        sys.exit(0)
    elif a.cmd == "record":
        print(json.dumps(record_post(a.channel, a.clip, a.date, a.post_id, a.video,
                                      a.topic, a.type, a.source, note=a.note, fmt=a.format),
                         ensure_ascii=False))
    elif a.cmd == "recent-formats":
        rf = recent_formats(n=a.n)
        print("recent formats (last %d, oldest->newest): %s" % (a.n, rf))
        print("AVOID for next post:", sorted(set(rf)) or "none yet")
    elif a.cmd == "list":
        idx = load_index()
        print(f"ledger: {LEDGER}")
        print("integrity: %s%s" % (
            idx["integrity"]["state"],
            (" — " + idx["integrity"]["reason"]) if idx["integrity"]["reason"] else "",
        ))
        completeness = permanent_dedup_completeness()
        print("identity_coverage: %s (%d complete, %d incomplete legacy rows, %.1f%%)" % (
            completeness["identity_coverage_state"],
            completeness["complete_rows"],
            completeness["incomplete_rows"],
            completeness["coverage_percent"],
        ))
        print("pending_claims: %d" % len(idx["pending_claims"]))
        print(f"dedup_keys: {len(idx['keys'])}")
        for (ch, ck), days in sorted(idx["by_clip"].items()):
            print(f"  {ch:8} {ck:12} -> {sorted(d.isoformat() for d in days)}")
    else:
        ap.print_help()


if __name__ == "__main__":
    main()
