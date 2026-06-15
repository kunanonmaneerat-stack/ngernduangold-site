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
    - is_twin() also scans +/- WINDOW_DAYS so the same clip can't hit the same channel
      anywhere in the rolling horizon (covers the local-midnight bucket edge).
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
import os, sys, json, time, re, hashlib, argparse, datetime

HERE = os.path.dirname(os.path.abspath(__file__))
LEDGER = os.path.join(HERE, "post-ledger.jsonl")
LOCK = os.path.join(HERE, ".post-ledger.lock")
TZ = datetime.timezone(datetime.timedelta(hours=7))          # Asia/Bangkok (no DST)

# twin window MUST be >= the furthest forward any path schedules (queue-keeper 7-14d,
# engine up to ~14d). One global constant shared by every writer and checker.
WINDOW_DAYS = 16
CAPS = {"tiktok": 4, "yt": 3, "ig": 2, "fb": 2, "fb_feed": 1}

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
# valid clip_keys come from content_queue.json; this static fallback lets --check work even
# when the AppData session copy isn't reachable. Keep aligned with content_queue.json.
KNOWN_CLIP_KEYS = {
    "invest", "save", "credit", "books", "em", "debt", "score", "tax", "side", "index",
    "insure", "retire", "track", "compound", "salary15k", "freelance", "easyapprove",
    "install0", "docs", "titleloan",
}

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
    if s in KNOWN_CLIP_KEYS:
        return s
    base = s.rsplit("/", 1)[-1]                     # strip url path
    base = base.split("?", 1)[0]                    # strip query
    stem = base[:-4] if base.lower().endswith(".mp4") else base
    if stem in ASSET_TO_KEY:                        # postiz library id
        return ASSET_TO_KEY[stem]
    if stem.startswith("vid_") and stem[4:] in KNOWN_CLIP_KEYS:   # vid_titleloan.mp4
        return stem[4:]
    if stem in KNOWN_CLIP_KEYS:
        return stem
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


def _date_of(when):
    if isinstance(when, datetime.datetime):
        return (when.astimezone(TZ) if when.tzinfo else when).date()
    if isinstance(when, datetime.date):
        return when
    return datetime.date.fromisoformat(str(when)[:10])


def iter_ledger(path=LEDGER):
    """Yield one dict per line; silently skip blank or truncated final lines
    (interrupt-safe READS). Missing file => empty."""
    if not os.path.exists(path):
        return
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError:
                continue                            # half-written final line -> skip


def load_index(path=LEDGER, since_days=None):
    """Build dedup structures. Resolves status rows (latest wins per dedup_key)."""
    cutoff = None
    if since_days is not None:
        cutoff = now_local().date() - datetime.timedelta(days=since_days)
    keys, by_clip, by_day, status = set(), {}, {}, {}
    for r in iter_ledger(path):
        if r.get("type") == "status":
            status[r.get("dedup_key")] = r.get("status")
            continue
        sf = r.get("scheduled_for")
        try:
            d = _date_of(sf)
        except Exception:
            continue
        if cutoff and d < cutoff:
            continue
        dk = r.get("dedup_key") or make_dedup_key(r.get("channel"), r.get("clip_key"), d)
        keys.add(dk)
        ch = norm_channel(r.get("channel"))
        by_clip.setdefault((ch, r.get("clip_key")), []).append(d)
        by_day.setdefault((ch, d), 0)
        by_day[(ch, d)] += 1
    return {"keys": keys, "by_clip": by_clip, "by_day": by_day, "status": status}


def is_twin(index, channel, clip_key, when, window_days=WINDOW_DAYS):
    """(collision, reason, conflicts). Exact dedup_key OR (channel,clip) within +/- window."""
    ch = norm_channel(channel)
    d = _date_of(when)
    dk = make_dedup_key(ch, clip_key, d)
    if dk in index["keys"]:
        return True, "exact dedup_key already in ledger (same clip/channel/day)", [dk]
    hits = []
    for dd in index["by_clip"].get((ch, clip_key), []):
        if abs((dd - d).days) <= window_days:
            hits.append(dd.isoformat())
    if hits:
        return True, f"(channel={ch}, clip={clip_key}) within +/-{window_days}d of {d}: {hits}", hits
    return False, "", []


def day_capacity(index, channel, when):
    """Remaining slots for channel/day per CAPS, counting only what WE recorded.
    (Cross-check live Chrome list-view for out-of-band posts.)"""
    ch = norm_channel(channel)
    d = _date_of(when)
    used = index["by_day"].get((ch, d), 0)
    return max(0, CAPS.get(ch, 99) - used)


# ---- lock (serialize read-check-post-record across concurrent actors in this env) ----
def acquire_lock(timeout=20, stale=120):
    start = time.time()
    while True:
        try:
            fd = os.open(LOCK, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.write(fd, str(os.getpid()).encode()); os.close(fd)
            return True
        except FileExistsError:
            try:
                if time.time() - os.path.getmtime(LOCK) > stale:
                    os.remove(LOCK); continue       # break a stale lock
            except OSError:
                pass
            if time.time() - start > timeout:
                return False
            time.sleep(0.3)


def release_lock():
    try:
        os.remove(LOCK)
    except OSError:
        pass


def _append(row):
    with open(LEDGER, "a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")


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
                window_days=WINDOW_DAYS, note=""):
    """Append ONE per-channel row. Idempotent: refuse if dedup_key already present."""
    ck = resolve_clip_key(clip_key) or clip_key
    if ck not in KNOWN_CLIP_KEYS:
        raise ValueError(f"unknown clip_key '{clip_key}' (resolve to a content_queue key first)")
    ch = norm_channel(channel)
    d = _date_of(when)
    dk = make_dedup_key(ch, ck, d)
    if dk in load_index()["keys"]:
        return {"dedup_key": dk, "appended": False, "reason": "already recorded"}
    row = {"dedup_key": dk, "channel": ch, "clip_key": ck, "video": video, "topic": topic,
           "post_id": post_id, "scheduled_for": d.isoformat(),
           "posted_at": now_local().isoformat(timespec="seconds"),
           "type": ptype, "source": source, "status": status, "window_days": window_days}
    if note:
        row["note"] = note
    _public_safe(row)
    _append(row)
    return {"dedup_key": dk, "appended": True, "row": row}


def record_multicast(channels, clip_key, when, post_id="", video="", topic="",
                     ptype="schedule", source="queue-keeper", window_days=WINDOW_DAYS):
    """A multicast MUST write one row per target channel (else a per-channel twin reopens)."""
    out = [record_post(c, clip_key, when, post_id, video, topic, ptype, source,
                       "scheduled", window_days) for c in channels]
    assert len([o for o in out if o.get("appended") or o.get("reason") == "already recorded"]) == len(channels)
    return out


def claim(channel, clip_key, when, source="adhoc", window_days=WINDOW_DAYS):
    """Write-ahead: take lock, twin-check, append a 'claimed' row BEFORE posting.
    Returns (ok, dedup_key, reason). Caller posts only if ok, then confirm()."""
    ck = resolve_clip_key(clip_key)
    if not ck:
        return False, "", f"unknown clip '{clip_key}' -> fail-closed (do not post)"
    if not acquire_lock():
        return False, "", "could not acquire ledger lock -> fail-closed"
    try:
        idx = load_index(since_days=window_days)
        twin, reason, _ = is_twin(idx, channel, ck, when, window_days)
        if twin:
            return False, "", f"TWIN: {reason}"
        if day_capacity(idx, channel, when) <= 0:
            return False, "", f"channel {norm_channel(channel)} at daily cap for {_date_of(when)}"
        dk = make_dedup_key(channel, ck, when)
        _append({"dedup_key": dk, "channel": norm_channel(channel), "clip_key": ck,
                 "scheduled_for": _date_of(when).isoformat(),
                 "posted_at": now_local().isoformat(timespec="seconds"),
                 "type": "claim", "source": source, "status": "claimed",
                 "window_days": window_days})
        return True, dk, "claimed"
    finally:
        release_lock()


def confirm(dedup_key, post_id="", status="scheduled"):
    """After a successful post, append a status row (append-only; never edit the claim)."""
    _append({"dedup_key": dedup_key, "type": "status", "status": status,
             "post_id": post_id, "posted_at": now_local().isoformat(timespec="seconds")})


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

    sub.add_parser("list", help="dump current dedup index summary")

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
        print(f"CLEAR: {norm_channel(a.channel)}/{ck}/{a.date} no twin in +/-{a.window}d, {cap} slot(s) left")
        sys.exit(0)
    elif a.cmd == "record":
        print(json.dumps(record_post(a.channel, a.clip, a.date, a.post_id, a.video,
                                      a.topic, a.type, a.source, note=a.note),
                         ensure_ascii=False))
    elif a.cmd == "list":
        idx = load_index()
        print(f"ledger: {LEDGER}")
        print(f"dedup_keys: {len(idx['keys'])}")
        for (ch, ck), days in sorted(idx["by_clip"].items()):
            print(f"  {ch:8} {ck:12} -> {sorted(d.isoformat() for d in days)}")
    else:
        ap.print_help()


if __name__ == "__main__":
    main()
