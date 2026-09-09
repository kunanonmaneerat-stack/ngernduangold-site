#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""agent_gap_check - did the AGENT layer do anything today, or has it been dead?

WHY THIS FILE EXISTS (7 ส.ค. 2026)
  This system has two layers and only one of them can die quietly:

    layer 1 - Windows Task Scheduler -> pipeline/run_daily.cmd
              runs whether or not anything else is open. Never missed a day.
    layer 2 - Cowork scheduled tasks (the LLM agents)
              **only fire while the desktop app is open.**

  On 2-6 Aug 2026 the owner was away working on another project. Layer 1 ran all
  six days: council + traffic-monitor files exist for every date. Layer 2 did
  nothing at all for THREE DAYS - 0 posts, 0 post-guard rows, 0 Slack messages,
  0 routine events on 3, 4 and 5 Aug. Nobody found out until the owner came back
  and asked. By then the batch3 gate had already fired on a measurement window
  with 3 of its 7 days blank, so its verdict was "cannot be measured" - the test
  was never run, and a week of content production was spent to learn nothing.

  The ops Slack channel has a charter, written after the identical 27-30 Jul
  blackout, that says in as many words:

      "ทุกเช้าต้องมีข้อความลงห้องนี้ · ไม่มีข้อความ = ระบบตาย"

  It was never implemented. It could not be: **Slack is written only by agents.**
  There is no Slack credential anywhere in the repo or the pipeline - grep for
  SLACK_ returns nothing - so when the agent layer dies, the very channel that is
  supposed to notice goes quiet with it. A dead man's switch wired to the dead
  man's own hand.

  This script is the switch, placed on the layer that does not die. It never
  talks to Slack. Ordinary audits are read-only; only the explicitly flagged
  Windows-runner invocation updates the file that the next agent reports.

WHAT COUNTS AS "THE AGENT LAYER DID SOMETHING"
  Three independent traces, so one broken writer cannot fake life or fake death:
    - automation-log/post-ledger.jsonl        real posts that went out
    - automation-log/post-guard/history.jsonl the daily guard actually ran
    - automation-log/<YYYY-MM>.jsonl          CC-side routine events
  The newest timestamp across all three is the last sign of life.

THREE AXES, JUDGED SEPARATELY
  activity  : ok / silent / unknown     did anything happen at all?
  reporting : ok / reporting-dark / unknown / n-a    did anyone get told?
  scheduler : ok / missed-or-stuck / runner-failed / stuck /
              completed-blocked / unknown             did enabled project jobs
              reach and prove their latest due slot?

  Each axis keeps the three-way shape on purpose (same rule as uptime_check):
  "I could not look" must never be published as "it is dead", or the alert
  becomes noise and gets ignored on the morning it is real.

WHY REPORTING NEEDED ITS OWN AXIS
  The activity check alone would have said OK all week while nothing reached a
  human. On 6 Aug 2026 four reporting tasks had a lastRunAt on that date and
  content posted, yet Slack's last message was 4 days old and no watchdog log
  had been written. Digging further: **the last watchdog log written at its
  scheduled 08:07 slot is dated 26 Jul.** Every later log file was written
  mid-day, i.e. by a manual or in-session run. The task was switched off with
  15 others on 26 Jul and re-enabled on 31 Jul, and since re-enabling not one
  scheduled run has completed - twelve days of a dead daily guard whose
  lastRunAt advanced every single morning.

  **lastRunAt proves a task STARTED, not that it FINISHED.** It is stamped by a
  run that pauses on a permission prompt or loses a connector mid-way. Editing a
  task's prompt can invalidate its stored tool approvals, so the very act of
  fixing a task can silently stop it - and the only field anyone checks will
  keep saying it is fine.

EXIT CODES
  0 = ok
  1 = unknown (could not tell - deliberately not treated as failure)
  2 = silent, reporting-dark, or scheduler blocking state (alert changes only
      when --update-agent-silent-alert-file was explicitly supplied)
  3 = unexpected local runner failure (sanitised exception class only)

USAGE
  py tools\\agent_gap_check.py
  py tools\\agent_gap_check.py --json
  py tools\\agent_gap_check.py --update-agent-silent-alert-file  # scheduled writer
  py tools\\agent_gap_check.py --selftest     # proves it can fire AND stay quiet
"""
import io, os, re, sys, json, glob, argparse, datetime, hashlib, contextlib, tempfile
from pathlib import Path
from zoneinfo import ZoneInfo

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
INBOX = os.path.join(REPO, "automation-log", "cowork-inbox")
ALERT = os.path.join(INBOX, "AGENT-SILENT-ALERT.md")

# Alert mutation is intentionally opt-in at the command line.  This audit is
# also called by evidence/release tooling, where an ordinary diagnostic read
# must never change the source snapshot it is measuring.
ALERT_MUTATION_FLAG = "--update-agent-silent-alert-file"

# Where the reporting layer leaves its receipts. Separate from the activity traces on
# purpose - see REPORTING-DARK below. Outside the repo, so this only works on the
# Windows host, which is exactly where run_daily.cmd fires it from.
REPORT_DIRS = [os.path.join(os.path.expanduser("~"), "Claude", "watchdog-logs")]
REPORT_STALE_HOURS = 48

# 26h, not 24h: the agent tasks are jittered by several minutes and the owner's
# machine is not switched on at a fixed hour. 24h would cry wolf on a late start;
# 26h still catches a genuine missed day the very next morning.
WARN_HOURS = 26
# Two full days with nothing at all is the 27-30 Jul / 3-5 Aug shape. By this
# point content has already been missed and a measurement window is already dirty.
LOUD_HOURS = 48

# Claude schedules are interpreted in the owner's local timezone.  The latest
# observed registry slots prove that e.g. ``30 12 * * *`` is stored as 05:30Z,
# which is 12:30 Asia/Bangkok.  Keep this explicit rather than trusting the
# Windows process timezone silently.
LOCAL_TZ = ZoneInfo("Asia/Bangkok")
SCHEDULE_GRACE_MINUTES = 20
SCHEDULE_LOOKBACK_DAYS = 35
# Disabled history is a transition-warning window, not a second backlog.  A
# week is long enough for the rolling control-tower comparison while keeping
# intentionally retired campaign jobs out of today's active health counts.
DISABLED_HISTORY_LOOKBACK_DAYS = 7
# Existing project sessions normally settle within minutes.  This is a bound
# for an in-flight state, not permission to infer success or STUCK from age.
COMPLETION_SLA_MINUTES = 120
CLOCK_TOLERANCE_MINUTES = 5
DISPATCH_SLOT_TOLERANCE_SECONDS = 59
SESSION_MATCH_TOLERANCE_SECONDS = 5
SESSION_SCAN_MAX_FILES = 512
SESSION_SCAN_MAX_BYTES = 256 * 1024 * 1024

# Claude/Cowork's registry and session metadata prove dispatch, not terminal
# completion.  A future scheduled task can close that evidence gap by writing
# one immutable, task-bound receipt here.  This monitor only reads receipts; it
# never creates them or mutates the scheduler.  Missing/invalid receipts remain
# UNKNOWN and can never upgrade a slot to PASS.
SCHEDULER_RECEIPT_ROOT = os.path.join(
    REPO, ".local-private", "runtime", "scheduler-task-receipts")
SCHEDULER_RECEIPT_SCHEMA_VERSION = 1
SCHEDULER_RECEIPT_MAX_BYTES = 256 * 1024
SCHEDULER_RECEIPT_MAX_DELIVERABLES = 32
_RECEIPT_IDENTIFIER = re.compile(r"\A[A-Za-z0-9][A-Za-z0-9._-]{0,95}\Z")
_SHA256 = re.compile(r"\A[0-9a-f]{64}\Z")
_TERMINAL_RECEIPT_STATUSES = {
    "COMPLETED", "COMPLETED_BLOCKED", "RUNNER_FAILED",
}

# This repository must not grade unrelated personal schedules such as tax or
# trading reminders.  These explicit legacy ids are project control tasks
# despite not carrying the normal prefix.
PROJECT_TASK_PREFIX = "ngernduangold-"
PROJECT_CONTROL_TASK_IDS = {
    "cowork-task-watchdog",
    "daily-social-post-reminder",
    "daily-pantip-threads-engine",
    "ig-weekly-pulse",
}


def _traces():
    """[(label, path)] - the three independent signs of life. Kept as a function
    so the selftest can point them at fixtures without touching the real repo."""
    return [
        ("post-ledger", os.path.join(REPO, "automation-log", "post-ledger.jsonl")),
        ("post-guard", os.path.join(REPO, "automation-log", "post-guard", "history.jsonl")),
        ("routine-log", os.path.join(REPO, "automation-log",
                                     datetime.datetime.now().strftime("%Y-%m") + ".jsonl")),
    ]


def _ts_of(row):
    """Pull a timestamp out of a log row whatever the writer chose to call it.

    Every one of these field names is in live use somewhere in this repo. Guessing
    one and silently returning None for the others would turn a working trace into
    a dead one - and this script's whole job is telling those two apart.
    """
    for k in ("ts", "checked_at", "timestamp", "time", "at"):
        v = row.get(k)
        if isinstance(v, str) and len(v) >= 10:
            return v
    return None


def last_seen(path):
    """-> (datetime or None, rows_read). Reads the tail; these files are appended."""
    if not os.path.isfile(path):
        return None, 0
    newest, rows = None, 0
    try:
        with io.open(path, encoding="utf-8", errors="replace") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    row = json.loads(line)
                except Exception:
                    continue
                if not isinstance(row, dict):
                    continue
                rows += 1
                ts = _ts_of(row)
                if not ts:
                    continue
                try:
                    dt = datetime.datetime.strptime(ts[:19], "%Y-%m-%dT%H:%M:%S")
                except ValueError:
                    try:
                        dt = datetime.datetime.strptime(ts[:10], "%Y-%m-%d")
                    except ValueError:
                        continue
                if newest is None or dt > newest:
                    newest = dt
    except Exception:
        return None, 0
    return newest, rows


def newest_report(dirs=None):
    """-> (datetime or None, path). Newest dated file the reporting layer produced.

    Only files named YYYY-MM-DD.* count. The directory also holds scratch files like
    moji_out.txt whose mtime moves for unrelated reasons; trusting mtime there would
    make a dead reporting layer look alive, which is the failure being detected.
    """
    best, where = None, None
    for d in (dirs if dirs is not None else REPORT_DIRS):
        if not os.path.isdir(d):
            continue
        for fn in os.listdir(d):
            m = re.match(r"^(\d{4})-(\d{2})-(\d{2})\b", fn)
            if not m:
                continue
            try:
                dt = datetime.datetime(int(m.group(1)), int(m.group(2)), int(m.group(3)))
            except ValueError:
                continue
            if best is None or dt > best:
                best, where = dt, os.path.join(d, fn)
    return best, where


def judge_reporting(now, activity_hours, report_dt):
    """-> (verdict, detail). verdict in {ok, reporting-dark, unknown, n/a}.

    REPORTING-DARK is its own failure mode and it is the sneakiest of the three.
    On 6 Aug 2026 cowork-task-watchdog, daily-social-post-reminder, post-guard-daily and
    channel-heartbeat all have a lastRunAt on that date - they started. Content posted
    that day too, so every activity trace is fresh and the plain silence check says OK.
    Yet nothing reached Slack (last message 2 Aug) and no watchdog log was written (last
    file 1 Aug). The tasks began, did partial work, and never reached their report step.

    **lastRunAt proves a task STARTED, not that it FINISHED.** A run that stalls on a
    permission prompt or loses a connector mid-way still stamps it. So "the agents are
    running" and "anyone is being told anything" are two different questions, and until
    now only the first one was ever asked.
    """
    if activity_hours is None or activity_hours >= WARN_HOURS:
        return "n/a", "ชั้น agent เงียบอยู่แล้ว - ไม่ต้องแยกเคสนี้"
    if report_dt is None:
        return "unknown", "ไม่พบไฟล์รายงานลงวันที่เลย - ตรวจไม่ได้"
    if report_dt > now + datetime.timedelta(minutes=CLOCK_TOLERANCE_MINUTES):
        return "unknown", "ไฟล์รายงานอยู่ในอนาคต - นาฬิกาหรือชื่อไฟล์ผิด"
    hours = (now - report_dt).total_seconds() / 3600.0
    if hours >= REPORT_STALE_HOURS:
        return "reporting-dark", (
            "งานยังเดินอยู่ (ร่องรอยล่าสุด %.1f ชม.) แต่รายงานล่าสุดคือ %s (%.0f วันก่อน)"
            % (activity_hours, report_dt.strftime("%Y-%m-%d"), hours / 24.0))
    return "ok", "รายงานล่าสุด %s" % report_dt.strftime("%Y-%m-%d")


def judge(now, seen):
    """(verdict, hours, detail). `seen` = [(label, datetime|None, rows)].

    Pure, so the selftest can drive it with synthetic clocks and no files.
    """
    alive = [(lab, dt) for lab, dt, _ in seen if dt is not None]
    if not alive:
        readable = sum(1 for _, _, rows in seen if rows)
        if readable == 0:
            return "unknown", None, "อ่านร่องรอยไม่ได้เลยสักตัว (ไฟล์หาย/ว่าง/พัง) - ไม่ใช่หลักฐานว่าเงียบ"
        return "unknown", None, "มีข้อมูลในไฟล์แต่ไม่มีแถวไหนมีเวลา - ตรวจไม่ได้"
    lab, newest = max(alive, key=lambda x: x[1])
    hours = (now - newest).total_seconds() / 3600.0
    if hours < 0:
        return "unknown", hours, "ร่องรอยล่าสุดอยู่ในอนาคต (%s) - นาฬิกาเพี้ยน ไม่สรุป" % newest
    if hours >= WARN_HOURS:
        return "silent", hours, "ร่องรอยล่าสุดคือ %s เมื่อ %s (%.1f ชม.ที่แล้ว)" % (
            lab, newest.strftime("%Y-%m-%d %H:%M"), hours)
    return "ok", hours, "ร่องรอยล่าสุดคือ %s เมื่อ %s (%.1f ชม.ที่แล้ว)" % (
        lab, newest.strftime("%Y-%m-%d %H:%M"), hours)


def _project_task(task_id, row=None):
    """Project ownership by id or an exact repository folder binding."""
    if not isinstance(task_id, str):
        return False
    row = row if isinstance(row, dict) else {}
    folders = row.get("userSelectedFolders")
    if folders is None:
        candidates = []
    elif isinstance(folders, (list, tuple)) and all(
            isinstance(item, str) for item in folders):
        candidates = list(folders)
    else:
        raise ValueError("task ownership folders are malformed")
    cwd = row.get("cwd")
    if cwd is not None and not isinstance(cwd, str):
        raise ValueError("task ownership cwd is malformed")
    if isinstance(cwd, str):
        candidates.append(cwd)
    # Validate registry-owned path fields before accepting even an explicit
    # project id.  Otherwise a prefixed task with a malformed ownership field
    # bypasses the fail-closed registry boundary and looks trustworthy merely
    # because its id starts with the expected string.
    if (task_id.startswith(PROJECT_TASK_PREFIX) or
            task_id in PROJECT_CONTROL_TASK_IDS):
        return True
    repo_key = os.path.normcase(os.path.abspath(REPO))
    for candidate in candidates:
        try:
            if os.path.normcase(os.path.abspath(candidate)) == repo_key:
                return True
        except (OSError, TypeError, ValueError) as exc:
            raise ValueError("task ownership path is malformed") from exc
    return False


def _aware_datetime(value):
    """Parse an ISO registry timestamp and return an aware local datetime."""
    if not isinstance(value, str) or not value.strip():
        return None
    raw = value.strip()
    if raw.endswith("Z"):
        raw = raw[:-1] + "+00:00"
    try:
        parsed = datetime.datetime.fromisoformat(raw)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return None
    return parsed.astimezone(LOCAL_TZ)


def _cron_values(token, minimum, maximum, sunday=False):
    """Expand one conservative five-field cron token.

    Invalid or unsupported syntax raises ValueError.  A monitor must report
    UNKNOWN for a schedule it cannot parse; silently guessing would be a false
    PASS.  Current Claude project schedules use only ``*``, lists, numbers and
    steps, but ranges are supported because they are ordinary cron syntax.
    """
    if not isinstance(token, str) or not token:
        raise ValueError("empty cron field")
    values = set()
    for item in token.split(","):
        if not item:
            raise ValueError("empty cron item")
        if "/" in item:
            base, step_text = item.split("/", 1)
            try:
                step = int(step_text)
            except ValueError as exc:
                raise ValueError("invalid cron step") from exc
            if step <= 0:
                raise ValueError("invalid cron step")
        else:
            base, step = item, 1
        if base == "*":
            start, end = minimum, maximum
        elif "-" in base:
            parts = base.split("-", 1)
            try:
                start, end = int(parts[0]), int(parts[1])
            except ValueError as exc:
                raise ValueError("invalid cron range") from exc
        else:
            try:
                start = end = int(base)
            except ValueError as exc:
                raise ValueError("invalid cron value") from exc
        # 7 is a Sunday alias only as a single value.  Normalising an endpoint
        # before expanding a range turns 0-7 into Sunday-only, a dangerous
        # silent schedule change.  Reject that ambiguous form fail-closed.
        if sunday and "-" in base and (start == 7 or end == 7):
            raise ValueError("Sunday alias 7 is unsupported in cron ranges")
        if sunday and start == 7:
            start = end = 0
        if start < minimum or start > maximum or end < minimum or end > maximum:
            raise ValueError("cron value out of range")
        if start > end:
            raise ValueError("wrapping cron ranges are unsupported")
        values.update(range(start, end + 1, step))
    return values


def _cron_match(expression, local_dt):
    fields = expression.split() if isinstance(expression, str) else []
    if len(fields) != 5:
        raise ValueError("cron must have five fields")
    minute_f, hour_f, dom_f, month_f, dow_f = fields
    minutes = _cron_values(minute_f, 0, 59)
    hours = _cron_values(hour_f, 0, 23)
    doms = _cron_values(dom_f, 1, 31)
    months = _cron_values(month_f, 1, 12)
    dows = _cron_values(dow_f, 0, 7, sunday=True)
    if (local_dt.minute not in minutes or local_dt.hour not in hours or
            local_dt.month not in months):
        return False
    dom_match = local_dt.day in doms
    cron_dow = (local_dt.weekday() + 1) % 7  # Python Mon=0; cron Sun=0.
    dow_match = cron_dow in dows
    dom_any, dow_any = dom_f == "*", dow_f == "*"
    if dom_any and dow_any:
        return True
    if dom_any:
        return dow_match
    if dow_any:
        return dom_match
    # Traditional cron uses OR when both day fields are restricted.
    return dom_match or dow_match


def latest_cron_due(expression, now, lookback_days=SCHEDULE_LOOKBACK_DAYS):
    """Return the latest local due minute at or before ``now``."""
    if now.tzinfo is None:
        raise ValueError("scheduler clock must be timezone-aware")
    cursor = now.replace(second=0, microsecond=0)
    limit = cursor - datetime.timedelta(days=lookback_days)
    while cursor >= limit:
        if _cron_match(expression, cursor):
            return cursor
        cursor -= datetime.timedelta(minutes=1)
    return None


def _stable_raw_registry(source):
    """Re-read the guard-validated registry without losing schedule fields."""
    try:
        path = Path(source["registry_path"])
        before = path.stat()
        raw = path.read_bytes()
        after = path.stat()
    except (KeyError, OSError, TypeError) as exc:
        return None, "registry unreadable (%s)" % type(exc).__name__
    if (before.st_size != after.st_size or before.st_mtime_ns != after.st_mtime_ns or
            len(raw) != after.st_size):
        return None, "registry changed while being read"
    if hashlib.sha256(raw).hexdigest() != source.get("sha256"):
        return None, "registry changed after policy validation"
    try:
        document = json.loads(raw.decode("utf-8-sig"))
    except (UnicodeError, ValueError):
        return None, "registry is not valid UTF-8 JSON"
    rows = document.get("scheduledTasks") if isinstance(document, dict) else None
    if not isinstance(rows, list):
        return None, "registry scheduledTasks is not a list"

    # Cross-check the identity/state snapshot returned by automation_policy_guard.
    expected = {row.get("id"): row for row in source.get("records", [])
                if isinstance(row, dict)}
    found, records = set(), []
    for row in rows:
        if not isinstance(row, dict):
            return None, "registry contains a malformed record"
        task_id = row.get("id")
        if task_id not in expected:
            return None, "registry identity changed after policy validation"
        found.add(task_id)
        if (row.get("enabled") is not expected[task_id].get("enabled") or
                row.get("filePath") != expected[task_id].get("file_path")):
            return None, "registry state changed after policy validation"
        try:
            project_owned = _project_task(task_id, row)
        except ValueError:
            return None, "registry task ownership fields are malformed"
        # Keep disabled project records too.  Dropping them here made a bulk
        # disable look exactly like a recovery: RUNNER_FAILED/UNKNOWN rows
        # disappeared from the next audit even though no terminal receipt had
        # been produced.  ``scheduler_records`` bounds disabled history to the
        # normal lookback and removes superseded mirrors before session scans.
        if project_owned:
            item = dict(row)
            item["source"] = source.get("name")
            item["_registry_path"] = source.get("registry_path")
            item["_registry_sha256"] = source.get("sha256")
            # Bind receipts to this exact task record, not merely the whole
            # registry.  The whole registry can change when an unrelated task
            # runs; the task-record hash identifies the current dispatch facts
            # (including lastScheduledFor/lastRunAt) without that ambiguity.
            item["_task_record_sha256"] = hashlib.sha256(json.dumps(
                row, ensure_ascii=False, sort_keys=True,
                separators=(",", ":")).encode("utf-8")).hexdigest()
            records.append(item)
    if found != set(expected):
        return None, "registry identities changed after policy validation"
    return records, None


def _strict_json_loads(value):
    def pairs_hook(pairs):
        result = {}
        for key, item in pairs:
            if key in result:
                raise ValueError("duplicate JSON key")
            result[key] = item
        return result

    def reject_constant(_value):
        raise ValueError("non-finite JSON number")

    return json.loads(value, object_pairs_hook=pairs_hook,
                      parse_constant=reject_constant)


def _epoch_ms_datetime(value):
    if not isinstance(value, int) or isinstance(value, bool):
        return None
    try:
        return datetime.datetime.fromtimestamp(
            value / 1000.0, tz=datetime.timezone.utc).astimezone(LOCAL_TZ)
    except (OverflowError, OSError, ValueError):
        return None


def _session_error_class(value):
    lowered = value.casefold()
    if "weekly limit" in lowered:
        return "WEEKLY_LIMIT"
    if "session limit" in lowered:
        return "SESSION_LIMIT"
    if "rate limit" in lowered or "too many requests" in lowered:
        return "RATE_LIMIT"
    if "permission" in lowered or "not allowed" in lowered:
        return "PERMISSION"
    if "authentication" in lowered or "sign in" in lowered or "login" in lowered:
        return "AUTHENTICATION"
    return "OTHER"


def _attach_session_evidence(source, records):
    """Bind the exact app-owned session that produced each registry lastRunAt.

    Only a strict metadata whitelist leaves this function.  Prompts, account
    names, email addresses, MCP configuration and raw error text are never
    copied into public JSON/alerts.
    """
    targets = {}
    for row in records:
        last_run = _aware_datetime(row.get("lastRunAt"))
        if last_run is not None:
            targets[row.get("id")] = last_run
    if not targets:
        return records, None
    try:
        session_dir = Path(source["registry_path"]).parent
        candidates = []
        lower = min(targets.values()) - datetime.timedelta(days=1)
        upper = max(targets.values()) + datetime.timedelta(days=1)
        for path in session_dir.glob("local_*.json"):
            stat = path.stat()
            modified = datetime.datetime.fromtimestamp(
                stat.st_mtime, tz=datetime.timezone.utc).astimezone(LOCAL_TZ)
            if lower <= modified <= upper:
                candidates.append((path, stat))
    except (KeyError, OSError, TypeError) as exc:
        return None, "session inventory unreadable (%s)" % type(exc).__name__
    total_bytes = sum(stat.st_size for _path, stat in candidates)
    if len(candidates) > SESSION_SCAN_MAX_FILES:
        return None, "session scan file cap exceeded"
    if total_bytes > SESSION_SCAN_MAX_BYTES:
        return None, "session scan byte cap exceeded"

    matches = {task_id: [] for task_id in targets}
    for path, listed_stat in sorted(candidates,
                                    key=lambda item: item[1].st_mtime_ns,
                                    reverse=True):
        try:
            before = path.stat()
            raw = path.read_bytes()
            after = path.stat()
        except OSError as exc:
            return None, "session file unreadable (%s)" % type(exc).__name__
        if (before.st_size != listed_stat.st_size or
                before.st_mtime_ns != listed_stat.st_mtime_ns or
                before.st_size != after.st_size or
                before.st_mtime_ns != after.st_mtime_ns or
                len(raw) != after.st_size):
            return None, "session inventory changed while being read"
        try:
            document = _strict_json_loads(raw.decode("utf-8-sig"))
        except (UnicodeError, ValueError):
            return None, "session inventory contains invalid UTF-8 JSON"
        if not isinstance(document, dict):
            return None, "session inventory contains a malformed document"
        task_id = document.get("scheduledTaskId")
        if task_id not in targets:
            continue
        session_id = document.get("sessionId")
        created = _epoch_ms_datetime(document.get("createdAt"))
        activity = _epoch_ms_datetime(document.get("lastActivityAt"))
        if (not isinstance(session_id, str) or not session_id or
                path.name != session_id + ".json" or created is None or
                activity is None or activity < created):
            return None, "matching session identity/timestamps are malformed"
        if abs((created - targets[task_id]).total_seconds()) > SESSION_MATCH_TOLERANCE_SECONDS:
            continue
        error_value, error_at_value = document.get("error"), document.get("errorAt")
        evidence = {
            "session_id": session_id,
            "created_at": created.isoformat(),
            "last_activity_at": activity.isoformat(),
            "session_sha256": hashlib.sha256(raw).hexdigest(),
            # The full app-owned session file may gain archival metadata after
            # a run. Receipts bind this stable identity subset instead.
            "binding_sha256": hashlib.sha256(json.dumps({
                "scheduled_task_id": task_id,
                "session_id": session_id,
                "created_at": created.isoformat(),
            }, ensure_ascii=False, sort_keys=True,
                separators=(",", ":")).encode("utf-8")).hexdigest(),
            "error_class": None,
            "error_sha256": None,
            "error_at": None,
        }
        if error_value is None and error_at_value is None:
            pass
        elif isinstance(error_value, str) and error_value.strip():
            error_at = _epoch_ms_datetime(error_at_value)
            if (error_at is None or error_at < created or
                    error_at > activity + datetime.timedelta(seconds=5)):
                return None, "matching session error pair is malformed"
            evidence.update({
                "error_class": _session_error_class(error_value),
                "error_sha256": hashlib.sha256(
                    error_value.encode("utf-8")).hexdigest(),
                "error_at": error_at.isoformat(),
            })
        else:
            return None, "matching session error pair is malformed"
        matches[task_id].append(evidence)

    enriched = []
    for row in records:
        item = dict(row)
        task_matches = matches.get(row.get("id"), [])
        if len(task_matches) > 1:
            item["session_evidence_error"] = "multiple sessions match registry lastRunAt"
        elif len(task_matches) == 1:
            item["session_evidence"] = task_matches[0]
        enriched.append(item)
    return enriched, None


def scheduler_records():
    """Return a hash-stable, policy-validated read-only scheduler snapshot."""
    try:
        import automation_policy_guard
        inventory = automation_policy_guard.query_claude_scheduler_registries()
    except Exception as exc:
        return None, "scheduler inventory failed (%s)" % type(exc).__name__
    if not isinstance(inventory, dict) or inventory.get("status") != "OK":
        reason = inventory.get("reason") if isinstance(inventory, dict) else None
        return None, "scheduler inventory UNKNOWN: %s" % (reason or "invalid result")
    combined = []
    snapshot_now = datetime.datetime.now(LOCAL_TZ)
    history_floor = snapshot_now - datetime.timedelta(
        days=DISABLED_HISTORY_LOOKBACK_DAYS)
    for source in inventory.get("sources", []):
        rows, error = _stable_raw_registry(source)
        if error:
            return None, "%s: %s" % (source.get("name", "unknown"), error)
        relevant = []
        for row in rows:
            if row.get("enabled") is not False:
                relevant.append(row)
                continue
            raw_values = [row.get("lastScheduledFor"), row.get("lastRunAt")]
            parsed = [_aware_datetime(value) for value in raw_values
                      if value is not None]
            # A malformed timestamp must remain observable.  Otherwise retain
            # only recent disabled history so long-retired one-shot jobs do not
            # flood the live control-tower result.
            malformed = any(value is not None and _aware_datetime(value) is None
                            for value in raw_values)
            if malformed or (parsed and max(parsed) >= history_floor):
                relevant.append(row)
        rows = relevant
        rows, error = _attach_session_evidence(source, rows)
        if error:
            return None, "%s: %s" % (source.get("name", "unknown"), error)
        combined.extend(rows)
    if not combined:
        return None, "no current or recent project schedules were found"
    owners = {}
    for row in combined:
        if row.get("enabled") is False:
            continue
        owners.setdefault(row.get("id"), set()).add(row.get("source"))
    duplicate_ids = sorted(task_id for task_id, sources in owners.items()
                           if len(sources) > 1)
    if duplicate_ids:
        return None, "duplicate enabled scheduler ownership: %s" % ", ".join(duplicate_ids)

    # A disabled mirror must not compete with a current enabled owner.  If no
    # owner remains, retain exactly the most recently active disabled copy;
    # scheduler policy guarantees there was at most one live owner, and this
    # avoids double-counting an older mirror as another failed job.
    live_ids = {row.get("id") for row in combined
                if row.get("enabled") is not False}
    active = [row for row in combined if row.get("enabled") is not False]
    disabled = {}
    for row in combined:
        task_id = row.get("id")
        if row.get("enabled") is not False or task_id in live_ids:
            continue
        disabled.setdefault(task_id, []).append(row)

    def activity_key(row):
        values = [_aware_datetime(row.get("lastScheduledFor")),
                  _aware_datetime(row.get("lastRunAt"))]
        values = [value for value in values if value is not None]
        newest = max(values) if values else datetime.datetime.min.replace(
            tzinfo=LOCAL_TZ)
        return newest, str(row.get("source") or "")

    for task_id in sorted(disabled):
        choices = disabled[task_id]
        chosen = max(choices, key=activity_key)
        chosen = dict(chosen)
        chosen["disabled_registry_copy_count"] = len(choices)
        active.append(chosen)
    return active, None


def _receipt_slot_token(due):
    """Filesystem-safe identity for one exact due slot (always UTC)."""
    return due.astimezone(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _stable_receipt_bytes(path):
    """Read one bounded receipt without accepting a changing file."""
    try:
        before = path.stat()
        if before.st_size > SCHEDULER_RECEIPT_MAX_BYTES:
            return None, "receipt exceeds byte cap"
        raw = path.read_bytes()
        after = path.stat()
    except OSError as exc:
        return None, "receipt unreadable (%s)" % type(exc).__name__
    if (before.st_size != after.st_size or
            before.st_mtime_ns != after.st_mtime_ns or
            len(raw) != after.st_size):
        return None, "receipt changed while being read"
    return raw, None


def _stable_deliverable_hash(path):
    """Return (size, sha256) only when a local deliverable is read-stable."""
    try:
        before = path.stat()
        if not path.is_file():
            return None, None, "deliverable is not a regular file"
        digest = hashlib.sha256()
        size = 0
        with path.open("rb") as handle:
            while True:
                block = handle.read(1024 * 1024)
                if not block:
                    break
                size += len(block)
                digest.update(block)
        after = path.stat()
    except OSError as exc:
        return None, None, "deliverable unreadable (%s)" % type(exc).__name__
    if (before.st_size != after.st_size or
            before.st_mtime_ns != after.st_mtime_ns or
            size != after.st_size):
        return None, None, "deliverable changed while being read"
    return size, digest.hexdigest(), None


def _scheduler_receipt_evidence(row, due, last_scheduled, last_run,
                                session, now, receipt_root=None,
                                completion_sla_minutes=COMPLETION_SLA_MINUTES):
    """Validate an exact local terminal receipt and all named deliverables.

    The receipt is a proof-of-run contract, not proof that a remote post or
    financial outcome occurred.  External claims remain governed by their own
    ledgers/gates.  This function never writes the receipt root.
    """
    source, task_id = row.get("source"), row.get("id")
    token = _receipt_slot_token(due)
    evidence = {
        "state": "MISSING",
        "expected_key": None,
        "terminal_status": None,
        "deliverable_count": 0,
        "errors": [],
    }
    if (not isinstance(source, str) or
            not _RECEIPT_IDENTIFIER.fullmatch(source) or
            not isinstance(task_id, str) or
            not _RECEIPT_IDENTIFIER.fullmatch(task_id)):
        evidence.update({
            "state": "INVALID",
            "errors": ["receipt identity is not path-safe"],
        })
        return evidence

    expected_key = "%s/%s/%s.json" % (source, task_id, token)
    evidence["expected_key"] = expected_key
    root = Path(SCHEDULER_RECEIPT_ROOT if receipt_root is None else receipt_root)
    try:
        root = root.resolve()
        path = (root / source / task_id / (token + ".json")).resolve()
        path.relative_to(root)
    except (OSError, ValueError):
        evidence.update({
            "state": "INVALID",
            "errors": ["receipt path escapes configured root"],
        })
        return evidence
    if not path.exists():
        return evidence

    raw, read_error = _stable_receipt_bytes(path)
    if read_error:
        evidence.update({"state": "INVALID", "errors": [read_error]})
        return evidence
    try:
        document = _strict_json_loads(raw.decode("utf-8-sig"))
    except (UnicodeError, ValueError):
        evidence.update({
            "state": "INVALID",
            "errors": ["receipt is not strict UTF-8 JSON"],
        })
        return evidence

    errors = []
    required_top = {
        "schema_version", "source", "task_id", "due_at", "registry",
        "session", "terminal", "deliverables",
    }
    if not isinstance(document, dict) or set(document) != required_top:
        errors.append("receipt top-level contract is malformed")
        document = document if isinstance(document, dict) else {}
    schema = document.get("schema_version")
    if (not isinstance(schema, int) or isinstance(schema, bool) or
            schema != SCHEDULER_RECEIPT_SCHEMA_VERSION):
        errors.append("receipt schema version is unsupported")
    if document.get("source") != source or document.get("task_id") != task_id:
        errors.append("receipt task identity does not match registry")
    receipt_due = _aware_datetime(document.get("due_at"))
    if receipt_due is None or receipt_due != due:
        errors.append("receipt due slot does not match scheduler slot")

    registry = document.get("registry")
    registry_keys = {
        "task_record_sha256", "last_scheduled_for", "last_run_at",
    }
    if not isinstance(registry, dict) or set(registry) != registry_keys:
        errors.append("receipt registry binding is malformed")
        registry = registry if isinstance(registry, dict) else {}
    task_record_sha = row.get("_task_record_sha256")
    if (not isinstance(task_record_sha, str) or
            not _SHA256.fullmatch(task_record_sha) or
            registry.get("task_record_sha256") != task_record_sha):
        errors.append("receipt task-record hash does not match registry")
    receipt_last_scheduled = _aware_datetime(
        registry.get("last_scheduled_for"))
    receipt_last_run = _aware_datetime(registry.get("last_run_at"))
    if (last_scheduled is None or receipt_last_scheduled != last_scheduled or
            last_run is None or receipt_last_run != last_run):
        errors.append("receipt dispatch timestamps do not match registry")

    session_doc = document.get("session")
    if (not isinstance(session_doc, dict) or
            set(session_doc) != {"binding_sha256", "created_at"}):
        errors.append("receipt session binding is malformed")
        session_doc = session_doc if isinstance(session_doc, dict) else {}
    session_sha = (session.get("binding_sha256")
                   if isinstance(session, dict) else None)
    session_created = (_aware_datetime(session.get("created_at"))
                       if isinstance(session, dict) else None)
    receipt_session_created = _aware_datetime(session_doc.get("created_at"))
    if (not isinstance(session_sha, str) or not _SHA256.fullmatch(session_sha) or
            session_doc.get("binding_sha256") != session_sha or
            session_created is None or
            receipt_session_created != session_created):
        errors.append("receipt session identity does not match exact dispatch")

    terminal = document.get("terminal")
    terminal_keys = {"status", "completed_at", "result_sha256", "blockers"}
    if not isinstance(terminal, dict) or set(terminal) != terminal_keys:
        errors.append("receipt terminal contract is malformed")
        terminal = terminal if isinstance(terminal, dict) else {}
    terminal_status = terminal.get("status")
    completed_at = _aware_datetime(terminal.get("completed_at"))
    if terminal_status not in _TERMINAL_RECEIPT_STATUSES:
        errors.append("receipt terminal status is unsupported")
    result_sha = terminal.get("result_sha256")
    if not isinstance(result_sha, str) or not _SHA256.fullmatch(result_sha):
        errors.append("receipt result hash is malformed")
    blockers = terminal.get("blockers")
    if (not isinstance(blockers, list) or len(blockers) > 32 or
            any(not isinstance(item, str) or not item or len(item) > 96
                for item in blockers)):
        errors.append("receipt blockers are malformed")
        blockers = []
    if terminal_status == "COMPLETED_BLOCKED" and not blockers:
        errors.append("completed-blocked receipt has no blocker identity")
    if terminal_status == "COMPLETED" and blockers:
        errors.append("completed receipt unexpectedly declares blockers")
    session_activity = (_aware_datetime(session.get("last_activity_at"))
                        if isinstance(session, dict) else None)
    if (completed_at is None or last_run is None or
            completed_at < last_run - datetime.timedelta(
                seconds=SESSION_MATCH_TOLERANCE_SECONDS) or
            completed_at > last_run + datetime.timedelta(
                minutes=completion_sla_minutes) or
            completed_at > now + datetime.timedelta(
                minutes=CLOCK_TOLERANCE_MINUTES) or
            (session_activity is not None and
             completed_at < session_activity - datetime.timedelta(seconds=5))):
        errors.append("receipt completion timestamp is outside the bound run")

    deliverables = document.get("deliverables")
    if (not isinstance(deliverables, list) or
            len(deliverables) > SCHEDULER_RECEIPT_MAX_DELIVERABLES):
        errors.append("receipt deliverable manifest is malformed")
        deliverables = []
    if terminal_status in {"COMPLETED", "COMPLETED_BLOCKED"} and not deliverables:
        errors.append("terminal receipt has no hash-bound local deliverable")
    repo_root = Path(REPO).resolve()
    seen_paths = set()
    for item in deliverables:
        if not isinstance(item, dict) or set(item) != {"path", "size", "sha256"}:
            errors.append("receipt deliverable entry is malformed")
            continue
        rel = item.get("path")
        size_claim, sha_claim = item.get("size"), item.get("sha256")
        if (not isinstance(rel, str) or not rel or len(rel) > 240 or
                "\\" in rel or rel.startswith("/") or
                any(part in {"", ".", ".."} for part in rel.split("/"))):
            errors.append("receipt deliverable path is unsafe")
            continue
        if rel in seen_paths:
            errors.append("receipt deliverable path is duplicated")
            continue
        seen_paths.add(rel)
        try:
            deliverable_path = (repo_root / Path(*rel.split("/"))).resolve()
            deliverable_path.relative_to(repo_root)
        except (OSError, ValueError):
            errors.append("receipt deliverable path escapes repository")
            continue
        actual_size, actual_sha, artifact_error = _stable_deliverable_hash(
            deliverable_path)
        if artifact_error:
            errors.append(artifact_error)
            continue
        if (not isinstance(size_claim, int) or isinstance(size_claim, bool) or
                size_claim < 0 or size_claim != actual_size or
                not isinstance(sha_claim, str) or
                not _SHA256.fullmatch(sha_claim) or sha_claim != actual_sha):
            errors.append("receipt deliverable hash or size does not match")

    evidence.update({
        "state": "INVALID" if errors else "VALID",
        "terminal_status": (terminal_status
                            if terminal_status in _TERMINAL_RECEIPT_STATUSES
                            else None),
        "deliverable_count": len(deliverables),
        "errors": errors,
    })
    return evidence


def _scheduler_evidence_chain(*, due_state="CALCULATED", dispatch="MISSING",
                              session="MISSING", receipt="NOT_CHECKED",
                              deliverables="NOT_CHECKED"):
    """Small public-safe state map; no paths, hashes or session ids."""
    return {
        "due": due_state,
        "dispatch": dispatch,
        "session": session,
        "terminal_receipt": receipt,
        "deliverables": deliverables,
    }


def _disabled_history_result(now, row, grace_minutes, completion_sla_minutes,
                             receipt_root):
    """Grade the final recorded slot of a recently disabled project task.

    Disabled tasks are no longer due, so comparing them with today's cron slot
    would manufacture a miss.  Conversely, simply filtering them out makes a
    disable look like recovery.  Freeze the final registry ``lastScheduledFor``
    as a one-time historical slot, reuse the exact dispatch/session/receipt
    chain, then expose unresolved history as UNKNOWN with an explicit disabled
    lifecycle.  Only a valid COMPLETED receipt can make that history resolved.
    """
    source = row.get("source", "unknown")
    task_id = row.get("id")
    grace = datetime.timedelta(minutes=grace_minutes)
    last_scheduled = _aware_datetime(row.get("lastScheduledFor"))
    last_run = _aware_datetime(row.get("lastRunAt"))
    malformed = (
        (row.get("lastScheduledFor") is not None and last_scheduled is None) or
        (row.get("lastRunAt") is not None and last_run is None)
    )

    base = {
        "source": source,
        "id": task_id,
        "enabled": False,
        "lifecycle_state": "DISABLED",
        "disabled_registry_copy_count": row.get(
            "disabled_registry_copy_count", 1),
        "disabled_unresolved": True,
        "last_scheduled_for": (last_scheduled.isoformat()
                               if last_scheduled else row.get("lastScheduledFor")),
        "last_run_at": (last_run.isoformat()
                        if last_run else row.get("lastRunAt")),
    }
    if (malformed or (last_scheduled and last_scheduled > now + grace) or
            (last_run and last_run > now + grace)):
        base.update({
            "status": "UNKNOWN",
            "historical_status": "UNKNOWN",
            "reason": "disabled task has malformed or future history timestamps",
            "due_at": last_scheduled.isoformat() if last_scheduled else None,
            "evidence_chain": _scheduler_evidence_chain(
                due_state="INVALID", dispatch="INVALID"),
        })
        return base
    if last_scheduled is None:
        base.update({
            "status": "UNKNOWN",
            "historical_status": "UNKNOWN",
            "reason": "disabled task has recent execution history but no due-slot identity",
            "due_at": None,
            "evidence_chain": _scheduler_evidence_chain(due_state="MISSING"),
        })
        return base

    # Prove that the registry's final scheduled timestamp is actually a slot
    # from the configured schedule before treating it as historical identity.
    slot_tolerance = datetime.timedelta(
        seconds=DISPATCH_SLOT_TOLERANCE_SECONDS)
    cron, fire_at = row.get("cronExpression"), row.get("fireAt")
    try:
        if isinstance(cron, str) and cron.strip():
            configured_due = latest_cron_due(
                cron.strip(), last_scheduled + slot_tolerance)
        elif isinstance(fire_at, (int, float)) and not isinstance(fire_at, bool):
            configured_due = datetime.datetime.fromtimestamp(
                fire_at / 1000.0, tz=datetime.timezone.utc).astimezone(LOCAL_TZ)
        else:
            raise ValueError("missing supported schedule")
        if (configured_due is None or
                abs(configured_due - last_scheduled) > slot_tolerance):
            raise ValueError("lastScheduledFor does not match configured schedule")
    except (OverflowError, OSError, ValueError) as exc:
        base.update({
            "status": "UNKNOWN",
            "historical_status": "UNKNOWN",
            "reason": "disabled task history cannot bind its configured slot: %s" % exc,
            "due_at": last_scheduled.isoformat(),
            "evidence_chain": _scheduler_evidence_chain(due_state="INVALID"),
        })
        return base

    # Reuse the normal evidence grader but prevent a later cron occurrence from
    # replacing the task's final recorded slot after disablement.
    shadow = dict(row)
    shadow["enabled"] = True
    shadow["cronExpression"] = None
    shadow["fireAt"] = int(last_scheduled.timestamp() * 1000)
    _verdict, _detail, graded = judge_scheduler(
        now, [shadow], grace_minutes=grace_minutes,
        completion_sla_minutes=completion_sla_minutes,
        receipt_root=receipt_root)
    if len(graded) != 1:
        base.update({
            "status": "UNKNOWN",
            "historical_status": "UNKNOWN",
            "reason": "disabled task final slot could not be graded uniquely",
            "due_at": last_scheduled.isoformat(),
            "evidence_chain": _scheduler_evidence_chain(due_state="INVALID"),
        })
        return base

    historical = dict(graded[0])
    historical_status = historical.get("status", "UNKNOWN")
    historical.update(base)
    historical["historical_status"] = historical_status
    if historical_status == "COMPLETED":
        historical.update({
            "status": "SKIP",
            "disabled_unresolved": False,
            "reason": ("disabled task retained for history; final recorded slot "
                       "has a valid completion receipt"),
        })
    else:
        historical.update({
            "status": "UNKNOWN",
            "disabled_unresolved": True,
            "reason": ("disabled task retained for history; final recorded slot "
                       "was %s and disabling is not recovery" % historical_status),
        })
    return historical


def _scheduler_state_counts(results):
    """Keep current-slot state separate from the latest recorded attempt.

    A task can miss today's due slot while its latest older session also proves
    an explicit runner failure. Those are facts about different slots and must
    not overwrite or double-count one another.
    """
    rows = results if isinstance(results, list) else []
    return {
        "missed_or_stuck": sum(
            1 for row in rows if row.get("status") == "MISSED_OR_STUCK"),
        "current_runner_failed": sum(
            1 for row in rows if row.get("status") == "RUNNER_FAILED"),
        "last_attempt_runner_failed": sum(
            1 for row in rows
            if row.get("lifecycle_state") != "DISABLED" and
            row.get("last_attempt_status") == "RUNNER_FAILED"),
        "stuck": sum(1 for row in rows if row.get("status") == "STUCK"),
        "completed_blocked": sum(
            1 for row in rows if row.get("status") == "COMPLETED_BLOCKED"),
        "unknown": sum(
            1 for row in rows
            if row.get("lifecycle_state") != "DISABLED" and
            row.get("status") == "UNKNOWN"),
        "started_unverified": sum(
            1 for row in rows if row.get("status") == "STARTED_UNVERIFIED"),
        "disabled_unresolved": sum(
            1 for row in rows if row.get("disabled_unresolved") is True),
        "disabled_resolved": sum(
            1 for row in rows
            if row.get("lifecycle_state") == "DISABLED" and
            row.get("disabled_unresolved") is False),
        "disabled_historical_runner_failed": sum(
            1 for row in rows
            if row.get("disabled_unresolved") is True and
            row.get("historical_status") == "RUNNER_FAILED"),
        "disabled_historical_missed_or_stuck": sum(
            1 for row in rows
            if row.get("disabled_unresolved") is True and
            row.get("historical_status") == "MISSED_OR_STUCK"),
        "disabled_historical_unknown": sum(
            1 for row in rows
            if row.get("disabled_unresolved") is True and
            row.get("historical_status") in {
                "UNKNOWN", "STARTED_UNVERIFIED", "SKIP"}),
        "disabled_last_attempt_runner_failed": sum(
            1 for row in rows
            if row.get("disabled_unresolved") is True and
            row.get("last_attempt_status") == "RUNNER_FAILED"),
        "receipt_valid": sum(
            1 for row in rows
            if isinstance(row.get("receipt_evidence"), dict) and
            row["receipt_evidence"].get("state") == "VALID"),
        "receipt_invalid": sum(
            1 for row in rows
            if isinstance(row.get("receipt_evidence"), dict) and
            row["receipt_evidence"].get("state") == "INVALID"),
        "receipt_missing": sum(
            1 for row in rows
            if isinstance(row.get("receipt_evidence"), dict) and
            row["receipt_evidence"].get("state") == "MISSING"),
    }


def judge_scheduler(now, records, grace_minutes=SCHEDULE_GRACE_MINUTES,
                    completion_sla_minutes=COMPLETION_SLA_MINUTES,
                    receipt_root=None):
    """Classify due project jobs without mutating or launching any scheduler.

    ``lastScheduledFor``/``lastRunAt`` prove dispatch only, not completion.  The
    result therefore says STARTED_UNVERIFIED rather than PASS when a due slot is
    present.  Missing dispatch after grace is MISSED_OR_STUCK.
    """
    if now.tzinfo is None:
        return "unknown", "scheduler clock has no timezone", []
    results, unknown = [], False
    grace = datetime.timedelta(minutes=grace_minutes)
    mature_clock = now - grace
    for row in records:
        task_id = row.get("id")
        source = row.get("source", "unknown")
        if row.get("enabled") is False:
            result = _disabled_history_result(
                now, row, grace_minutes, completion_sla_minutes, receipt_root)
            results.append(result)
            if result.get("status") == "UNKNOWN":
                unknown = True
            continue
        cron = row.get("cronExpression")
        fire_at = row.get("fireAt")
        due, raw_due, schedule_kind = None, None, None
        try:
            if isinstance(cron, str) and cron.strip():
                raw_due = latest_cron_due(cron.strip(), now)
                due = latest_cron_due(cron.strip(), mature_clock)
                schedule_kind = "cron"
                if raw_due is None or due is None:
                    raise ValueError("no cron slot in bounded lookback")
            elif isinstance(fire_at, (int, float)) and not isinstance(fire_at, bool):
                due = datetime.datetime.fromtimestamp(fire_at / 1000.0,
                                                      tz=datetime.timezone.utc).astimezone(LOCAL_TZ)
                raw_due = due
                schedule_kind = "one-time"
            else:
                raise ValueError("missing supported schedule")
        except (OverflowError, OSError, ValueError) as exc:
            results.append({"source": source, "id": task_id, "status": "UNKNOWN",
                            "reason": str(exc), "due_at": None,
                            "last_scheduled_for": row.get("lastScheduledFor"),
                            "last_run_at": row.get("lastRunAt"),
                            "evidence_chain": _scheduler_evidence_chain(
                                due_state="INVALID")})
            unknown = True
            continue

        last_scheduled = _aware_datetime(row.get("lastScheduledFor"))
        last_run = _aware_datetime(row.get("lastRunAt"))
        malformed_time = ((row.get("lastScheduledFor") is not None and last_scheduled is None) or
                          (row.get("lastRunAt") is not None and last_run is None))
        if malformed_time or (last_scheduled and last_scheduled > now + grace) or (last_run and last_run > now + grace):
            results.append({"source": source, "id": task_id, "status": "UNKNOWN",
                            "reason": "malformed or future execution timestamp",
                            "due_at": due.isoformat(),
                            "last_scheduled_for": row.get("lastScheduledFor"),
                            "last_run_at": row.get("lastRunAt"),
                            "evidence_chain": _scheduler_evidence_chain(
                                dispatch="INVALID")})
            unknown = True
            continue
        slot_tolerance = datetime.timedelta(
            seconds=DISPATCH_SLOT_TOLERANCE_SECONDS)

        # Registries expose only the latest execution stamps.  If a cron slot
        # inside grace has already replaced those stamps, grade that explicit
        # current attempt.  Otherwise grade the newest mature slot.  This avoids
        # both hiding yesterday's miss and falsely comparing today's run to
        # yesterday's due time.
        current_inside_grace = False
        if (schedule_kind == "cron" and raw_due != due and
                last_scheduled is not None and
                abs(last_scheduled - raw_due) <= slot_tolerance):
            due = raw_due
            current_inside_grace = True
        elif schedule_kind == "one-time":
            if due > now:
                results.append({"source": source, "id": task_id,
                                "status": "SKIP", "reason": "future slot",
                                "due_at": due.isoformat(),
                                "last_scheduled_for": (last_scheduled.isoformat()
                                                       if last_scheduled else None),
                                "last_run_at": last_run.isoformat()
                                if last_run else None,
                                "evidence_chain": _scheduler_evidence_chain(
                                    due_state="FUTURE")})
                continue
            current_inside_grace = now - due < grace

        scheduled_matches = (last_scheduled is not None and
                             abs(last_scheduled - due) <= slot_tolerance)
        run_matches = (last_run is not None and
                       due - datetime.timedelta(seconds=SESSION_MATCH_TOLERANCE_SECONDS)
                       <= last_run <= due + grace)
        session = row.get("session_evidence")
        if not scheduled_matches or not run_matches:
            if current_inside_grace:
                # No exact failed attempt exists yet and the previous mature
                # slot can no longer be inferred from a latest-only registry.
                results.append({"source": source, "id": task_id,
                                "status": "SKIP",
                                "reason": "current slot is inside grace window",
                                "due_at": due.isoformat(),
                                "last_scheduled_for": (last_scheduled.isoformat()
                                                       if last_scheduled else None),
                                "last_run_at": last_run.isoformat()
                                if last_run else None,
                                "evidence_chain": _scheduler_evidence_chain(
                                    dispatch="INSIDE_GRACE")})
                continue
            result = {"source": source, "id": task_id,
                      "status": "MISSED_OR_STUCK",
                      "reason": "%s slot has no exact dispatch within SLA" % schedule_kind,
                      "due_at": due.isoformat(),
                      "last_scheduled_for": (last_scheduled.isoformat()
                                             if last_scheduled else None),
                      "last_run_at": last_run.isoformat() if last_run else None,
                      "evidence_chain": _scheduler_evidence_chain(
                          dispatch="MISSING_OR_STALE",
                          session=("LAST_ATTEMPT_BOUND"
                                   if isinstance(session, dict) else "MISSING"),
                          receipt="NOT_CHECKED_WITHOUT_EXACT_DISPATCH",
                          deliverables="NOT_CHECKED_WITHOUT_EXACT_DISPATCH")}
            if isinstance(session, dict):
                result["last_attempt_status"] = (
                    "RUNNER_FAILED" if session.get("error_class")
                    else "COMPLETION_UNVERIFIED")
                result["last_attempt_session"] = session
            results.append(result)
            continue

        if row.get("session_evidence_error"):
            results.append({"source": source, "id": task_id, "status": "UNKNOWN",
                            "reason": row["session_evidence_error"],
                            "due_at": due.isoformat(),
                            "last_scheduled_for": last_scheduled.isoformat(),
                            "last_run_at": last_run.isoformat(),
                            "evidence_chain": _scheduler_evidence_chain(
                                dispatch="EXACT", session="AMBIGUOUS")})
            unknown = True
            continue
        if not isinstance(session, dict):
            results.append({"source": source, "id": task_id, "status": "UNKNOWN",
                            "reason": "exact dispatch has no uniquely bound session evidence",
                            "due_at": due.isoformat(),
                            "last_scheduled_for": last_scheduled.isoformat(),
                            "last_run_at": last_run.isoformat(),
                            "evidence_chain": _scheduler_evidence_chain(
                                dispatch="EXACT", session="MISSING")})
            unknown = True
            continue
        if session.get("error_class"):
            results.append({"source": source, "id": task_id,
                            "status": "RUNNER_FAILED",
                            "reason": "bound scheduler session ended with %s" %
                                      session["error_class"],
                            "due_at": due.isoformat(),
                            "last_scheduled_for": last_scheduled.isoformat(),
                            "last_run_at": last_run.isoformat(),
                            "session_evidence": session,
                            "evidence_chain": _scheduler_evidence_chain(
                                dispatch="EXACT", session="EXACT_ERROR",
                                receipt="NOT_REQUIRED_SESSION_ERROR",
                                deliverables="NOT_REQUIRED_RUNNER_FAILED")})
            continue

        completion_deadline = last_run + datetime.timedelta(
            minutes=completion_sla_minutes)
        receipt = _scheduler_receipt_evidence(
            row, due, last_scheduled, last_run, session, now,
            receipt_root=receipt_root,
            completion_sla_minutes=completion_sla_minutes)
        if receipt["state"] == "VALID":
            terminal_status = receipt["terminal_status"]
            if terminal_status == "COMPLETED":
                reason = "exact dispatch has a valid terminal receipt and deliverables"
            elif terminal_status == "COMPLETED_BLOCKED":
                reason = "exact dispatch completed locally with recorded blockers"
            else:
                reason = "exact dispatch wrote a valid runner-failure receipt"
            results.append({
                "source": source,
                "id": task_id,
                "status": terminal_status,
                "reason": reason,
                "due_at": due.isoformat(),
                "last_scheduled_for": last_scheduled.isoformat(),
                "last_run_at": last_run.isoformat(),
                "completion_deadline": completion_deadline.isoformat(),
                "session_evidence": session,
                "receipt_evidence": receipt,
                "evidence_chain": _scheduler_evidence_chain(
                    dispatch="EXACT", session="EXACT",
                    receipt="VALID",
                    deliverables=(
                        "VALID" if receipt["deliverable_count"]
                        else "NOT_REQUIRED_RUNNER_FAILED")),
            })
            continue

        receipt_state = receipt["state"]
        deliverable_state = ("MISSING" if receipt_state == "MISSING"
                             else "INVALID")
        if now < completion_deadline and receipt_state == "MISSING":
            results.append({"source": source, "id": task_id,
                            "status": "STARTED_UNVERIFIED",
                            "reason": "inside completion SLA; no bound terminal receipt",
                            "due_at": due.isoformat(),
                            "last_scheduled_for": last_scheduled.isoformat(),
                            "last_run_at": last_run.isoformat(),
                            "completion_deadline": completion_deadline.isoformat(),
                            "session_evidence": session,
                            "receipt_evidence": receipt,
                            "evidence_chain": _scheduler_evidence_chain(
                                dispatch="EXACT", session="EXACT",
                                receipt="MISSING",
                                deliverables="MISSING")})
        else:
            # This session schema has no trustworthy terminal marker.  Age plus
            # absence of a receipt cannot distinguish silent success from a
            # stall, so fail closed as UNKNOWN rather than fabricating STUCK.
            if receipt_state == "INVALID":
                reason = "task-bound terminal receipt is invalid"
            else:
                reason = "session has no error but no task-bound terminal receipt"
            results.append({"source": source, "id": task_id,
                            "status": "UNKNOWN",
                            "reason": reason,
                            "due_at": due.isoformat(),
                            "last_scheduled_for": last_scheduled.isoformat(),
                            "last_run_at": last_run.isoformat(),
                            "completion_deadline": completion_deadline.isoformat(),
                            "session_evidence": session,
                            "receipt_evidence": receipt,
                            "evidence_chain": _scheduler_evidence_chain(
                                dispatch="EXACT", session="EXACT",
                                receipt=receipt_state,
                                deliverables=deliverable_state)})
        unknown = True

    blocked = [row for row in results if row["status"] in {
        "MISSED_OR_STUCK", "RUNNER_FAILED", "STUCK", "COMPLETED_BLOCKED"} or
        row.get("disabled_unresolved") is True]
    if blocked:
        counts = _scheduler_state_counts(results)
        state_counts = [
            ("missed-or-stuck", counts["missed_or_stuck"]),
            ("runner-failed", counts["current_runner_failed"]),
            ("stuck", counts["stuck"]),
            ("completed-blocked", counts["completed_blocked"]),
            ("disabled-unresolved", counts["disabled_unresolved"]),
        ]
        aggregate = "+".join(name for name, count in state_counts if count)
        return (aggregate,
                ("%d missed-or-stuck, %d current runner-failed, "
                 "%d last-attempt runner-failed, %d stuck and "
                 "%d completed-blocked; "
                 "%d unknown, %d started-unverified and "
                 "%d disabled-unresolved (%d latest-slot runner-failed, "
                 "%d latest-slot missed-or-stuck, %d latest-slot unknown; "
                 "%d late-attempt runner-failed)") %
                (counts["missed_or_stuck"],
                 counts["current_runner_failed"],
                 counts["last_attempt_runner_failed"], counts["stuck"],
                 counts["completed_blocked"], counts["unknown"],
                 counts["started_unverified"],
                 counts["disabled_unresolved"],
                 counts["disabled_historical_runner_failed"],
                 counts["disabled_historical_missed_or_stuck"],
                 counts["disabled_historical_unknown"],
                 counts["disabled_last_attempt_runner_failed"]),
                results)
    if unknown:
        return "unknown", "one or more schedules could not be graded", results
    completed = sum(1 for row in results if row["status"] == "COMPLETED")
    return "ok", "%d due slot(s) have bound completion receipts" % completed, results


def _public_scheduler_tasks(tasks):
    """Return the minimum scheduler evidence safe for JSON/user surfaces."""
    row_keys = {
        "source", "id", "status", "reason", "due_at",
        "last_scheduled_for", "last_run_at", "completion_deadline",
        "last_attempt_status", "evidence_chain", "enabled",
        "lifecycle_state", "historical_status", "disabled_unresolved",
        "disabled_registry_copy_count",
    }
    session_keys = {
        "created_at", "last_activity_at", "error_class", "error_at",
    }
    public = []
    for row in tasks:
        item = {key: row.get(key) for key in row_keys if key in row}
        for evidence_key in ("session_evidence", "last_attempt_session"):
            evidence = row.get(evidence_key)
            if isinstance(evidence, dict):
                item[evidence_key] = {
                    key: evidence.get(key) for key in session_keys
                    if key in evidence
                }
        receipt = row.get("receipt_evidence")
        if isinstance(receipt, dict):
            item["receipt_evidence"] = {
                "state": receipt.get("state"),
                "expected_key": receipt.get("expected_key"),
                "terminal_status": receipt.get("terminal_status"),
                "deliverable_count": receipt.get("deliverable_count"),
                "errors": [
                    _safe_alert_text(value, limit=160)
                    for value in receipt.get("errors", [])
                    if isinstance(value, str)
                ][:16],
            }
        public.append(item)
    return public


_SAFE_ALERT_IDENTIFIER = re.compile(r"\A[A-Za-z0-9][A-Za-z0-9._-]{0,95}\Z")
_ALERT_EMAIL = re.compile(
    r"(?i)(?<![\w.+-])[\w.+-]+@[A-Z0-9.-]+\.[A-Z]{2,}(?![\w.-])")
_ALERT_WINDOWS_PATH = re.compile(
    r"(?i)(?:[A-Z]:\\|\\\\)[^\s`<>|\"']+")
_ALERT_URL_SECRET = re.compile(r"(?i)https?://[^\s`<>]+")


def _safe_alert_identifier(value):
    """Return only a bounded, non-account-like scheduler label."""
    if isinstance(value, str) and _SAFE_ALERT_IDENTIFIER.fullmatch(value):
        return value
    return "REDACTED_INVALID_IDENTIFIER"


def _safe_alert_timestamp(value):
    """Alerts need slot time, never an arbitrary registry string."""
    parsed = _aware_datetime(value)
    return parsed.isoformat() if parsed is not None else "unknown"


def _safe_alert_text(value, limit=400):
    """Make a single-line local alert field safe for a human handoff.

    Raw session errors never reach this function.  This second boundary also
    strips common account/path/URL material should an upstream reason regress.
    """
    if not isinstance(value, str):
        return "unknown"
    cleaned = " ".join(value.split())
    cleaned = _ALERT_EMAIL.sub("[redacted-email]", cleaned)
    cleaned = _ALERT_WINDOWS_PATH.sub("[redacted-path]", cleaned)
    cleaned = _ALERT_URL_SECRET.sub("[redacted-url]", cleaned)
    cleaned = "".join(ch for ch in cleaned if ch >= " " and ch != "\x7f")
    return (cleaned[:limit] if cleaned else "unknown")


def _atomic_write_alert(text, alert_path=None):
    """Atomically replace the one local alert with owner-only permissions.

    A temp file is created beside the destination, flushed, and replaced.  If
    any step fails, the prior alert remains byte-for-byte intact and the error
    reaches the guarded entry point as RUNNER_FAILED.
    """
    path = Path(ALERT if alert_path is None else alert_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = text.encode("utf-8")
    fd, temp_name = tempfile.mkstemp(
        prefix=".%s." % path.name, suffix=".tmp", dir=str(path.parent))
    temp_path = Path(temp_name)
    try:
        try:
            os.chmod(temp_path, 0o600)
        except OSError:
            # Windows ACLs are inherited from the private local workspace; the
            # atomicity guarantee must not be weakened by a chmod limitation.
            if os.name != "nt":
                raise
        with os.fdopen(fd, "wb") as handle:
            fd = None
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(str(temp_path), str(path))
    except Exception:
        if fd is not None:
            os.close(fd)
        try:
            temp_path.unlink()
        except FileNotFoundError:
            pass
        raise


def write_scheduler_alert(detail, tasks):
    """Write a local handoff only.  Never opens Claude or launches backlog."""
    missed = [row for row in tasks if row.get("status") in {
        "MISSED_OR_STUCK", "RUNNER_FAILED", "STUCK", "COMPLETED_BLOCKED"}]
    uncertain = [row for row in tasks
                 if row.get("status") in {
                     "UNKNOWN", "STARTED_UNVERIFIED", "COMPLETED_UNVERIFIED"}]
    counts = _scheduler_state_counts(tasks)
    lines = [
        "# 🔴 Claude scheduler มีงานพลาด/ล้มเหลว/ค้าง",
        "",
        "เขียนโดย `tools/agent_gap_check.py` จาก Claude scheduler registries เมื่อ %s Asia/Bangkok"
        % datetime.datetime.now(LOCAL_TZ).strftime("%Y-%m-%d %H:%M"),
        "",
        "- %s" % _safe_alert_text(detail),
        ("- current `RUNNER_FAILED`: `%d`; latest older attempt "
         "`RUNNER_FAILED`: `%d`") %
        (counts["current_runner_failed"],
         counts["last_attempt_runner_failed"]),
        ("- disabled-but-unresolved: `%d` (latest slot runner-failed `%d`; "
         "missed-or-stuck `%d`) — disable ไม่ใช่หลักฐาน recovery") %
        (counts["disabled_unresolved"],
         counts["disabled_historical_runner_failed"],
         counts["disabled_historical_missed_or_stuck"]),
        "- ตรวจแบบ read-only จาก registry จริง; ไม่ได้เปิด Claude, Run now หรือแก้ schedule",
        "",
        "## งานที่บล็อก",
    ]
    for row in missed:
        line = ("- `%s/%s` — %s; due `%s`; lastScheduledFor `%s`; lastRunAt `%s`" % (
            _safe_alert_identifier(row.get("source")),
            _safe_alert_identifier(row.get("id")),
            _safe_alert_identifier(row.get("status")),
            _safe_alert_timestamp(row.get("due_at")),
            _safe_alert_timestamp(row.get("last_scheduled_for")),
            _safe_alert_timestamp(row.get("last_run_at"))))
        session = row.get("session_evidence") or row.get("last_attempt_session")
        if isinstance(session, dict):
            line += "; session `%s`" % (
                _safe_alert_identifier(
                    session.get("error_class") or "NO_EXPLICIT_ERROR"))
        if row.get("last_attempt_status"):
            line += "; last_attempt `%s`" % _safe_alert_identifier(
                row["last_attempt_status"])
        lines.append(line)
    if uncertain:
        lines += ["", "## งานที่ยังห้ามสรุปว่า PASS"]
        for row in uncertain:
            lines.append("- `%s/%s` — %s; หลักฐานยังไม่พอสำหรับ PASS" % (
                _safe_alert_identifier(row.get("source")),
                _safe_alert_identifier(row.get("id")),
                _safe_alert_identifier(row.get("status"))))
    lines += [
        "",
        "## ขอบเขตความจริง",
        "`lastRunAt` พิสูจน์ได้เพียงเริ่มงาน ไม่ใช่เสร็จงาน; งานที่เริ่มแล้วจึงเป็น",
        "`STARTED_UNVERIFIED` จนกว่าจะมี deliverable/receipt ของงานนั้น",
        "",
        "## การกู้ระบบอย่างปลอดภัย",
        "1. ตรวจ backlog และแยกงาน read-only ออกจากงานที่โพสต์/ตอบ/เขียนภายนอกก่อน",
        "2. ให้ owner เปิด Claude Desktop และยืนยัน account/plan พร้อมแล้วเท่านั้น",
        "3. ห้าม Run now เหมารวม เพราะ enabled backlog บางงานมี external side effects",
        "4. หลัง cron ถัดไป ตรวจ registry + deliverable ใหม่; ห้ามถือว่าเปิดแอปแล้วเท่ากับสำเร็จ",
        "",
        "_ไฟล์นี้จะถูกลบเมื่อ scheduler ไม่มี due slot ที่พลาดและแกนอื่นไม่พบ regression_",
    ]
    _atomic_write_alert("\n".join(lines) + "\n")


def write_alert(hours, detail, seen, reporting=None):
    days = hours / 24.0
    loud = hours >= LOUD_HOURS
    if reporting:
        L = [
            "# 🔴 งานเดินอยู่ แต่ไม่มีรายงานออกมาเลย",
            "",
            "เขียนโดย `tools/agent_gap_check.py` จาก **ชั้น cron** เมื่อ %s"
            % datetime.datetime.now().strftime("%Y-%m-%d %H:%M"),
            "",
            "- %s" % _safe_alert_text(reporting),
            "",
            "## ทำไมเคสนี้ถึงอันตรายกว่า 'เงียบสนิท'",
            "**`lastRunAt` พิสูจน์แค่ว่างาน *เริ่ม* ไม่ได้พิสูจน์ว่ามัน *จบ*** — งานที่ค้างรอ permission",
            "หรือหลุด connector กลางทาง ก็ยังประทับ `lastRunAt` เหมือนกัน",
            "",
            "เคสจริง 6 ส.ค. 2026: `cowork-task-watchdog` · `daily-social-post-reminder` ·",
            "`post-guard-daily` · `channel-heartbeat` **มี lastRunAt วันนั้นครบทั้งสี่ตัว** และมีคอนเทนต์",
            "ขึ้นจริงด้วย → ร่องรอยกิจกรรมสดหมด ตัวตรวจ 'เงียบ' จึงบอกว่า OK",
            "แต่ **ไม่มีข้อความเข้า Slack เลย** (ล่าสุด 2 ส.ค.) และ **ไม่มีไฟล์ watchdog log** (ล่าสุด 1 ส.ค.)",
            "งานเริ่ม ทำได้บางส่วน แล้วไปไม่ถึงขั้นตอนรายงาน",
            "",
            "> **'agent ยังทำงานอยู่' กับ 'มีใครได้รับรู้อะไรบ้าง' เป็นคนละคำถาม**",
            "> ที่ผ่านมาเราถามแค่ข้อแรก",
            "",
            "## ตรวจอะไรก่อน",
            "1. เปิด task ที่ควรรายงาน แล้วดูว่ามันค้างที่ permission prompt หรือเปล่า (approval-trap)",
            "2. เช็กว่า Slack MCP ต่ออยู่จริงในรอบนั้น",
            "3. ถ้าเจอสาเหตุแล้ว ให้รายงานเข้า Slack ครั้งเดียวว่าเงียบไปกี่วันและพลาดอะไร แล้วลบไฟล์นี้",
            "",
            "_ไฟล์นี้จะถูกลบอัตโนมัติเมื่อมีรายงานใหม่ออกมา_",
        ]
        _atomic_write_alert("\n".join(L) + "\n")
        return

    L = [
        "# %s ชั้น agent เงียบมา %.1f ชม. (%.1f วัน)" % ("🔴" if loud else "⚠️", hours, days),
        "",
        "เขียนโดย `tools/agent_gap_check.py` จาก **ชั้น cron** (run_daily.cmd) เมื่อ %s"
        % datetime.datetime.now().strftime("%Y-%m-%d %H:%M"),
        "ชั้นนี้รันจาก Windows Task Scheduler จึงไม่ตายพร้อมกับ agent — เป็นตัวเดียวที่พูดได้ตอนนี้",
        "",
        "- %s" % _safe_alert_text(detail),
        "",
        "## ร่องรอยที่ตรวจ",
    ]
    for lab, dt, rows in seen:
        L.append("- `%s` — %s (%d แถว)" % (
            _safe_alert_identifier(lab),
            dt.strftime("%Y-%m-%d %H:%M") if dt else "ไม่มีเวลาที่อ่านได้", rows))
    L += [
        "",
        "## ทำไมเรื่องนี้ถึงสำคัญกว่าที่เห็น",
        "งาน Cowork ทั้งหมด **ยิงเฉพาะตอนแอปเปิดอยู่** ปิดแอป = ทุก agent หยุดเงียบ",
        "โดยไม่มี error ไม่มี log ไม่มีใครรู้ ขณะที่ชั้น cron ยังเดินปกติทุกวัน",
        "**ระบบที่กำลังทำงานกับระบบที่ตายไปแล้วจึงหน้าตาเหมือนกันเป๊ะจากฝั่งไฟล์**",
        "",
        "เกิดมาแล้ว 2 ครั้ง: 27–30 ก.ค. (4 วัน) และ 3–5 ส.ค. (3 วัน)",
        "ครั้งหลังทำให้ gate batch3 ตัดสินไม่ได้ เพราะ 3 ใน 7 วันของหน้าต่างวัดผลว่างเปล่า",
        "— ผลิตคอนเทนต์ไปทั้งสัปดาห์แล้วไม่ได้คำตอบอะไรกลับมาเลย",
        "",
        "## สิ่งที่ควรทำทันทีเมื่อเห็นไฟล์นี้",
        "1. เช็กว่ามีอะไรที่ **ควรจะโพสต์แล้วไม่ได้โพสต์** ในช่วงที่เงียบ (post-ledger เทียบ manifest)",
        "2. เช็กว่ามี **gate/เส้นตายไหนตกอยู่ในช่วงเงียบ** — ถ้ามี ผลของ gate นั้นเชื่อไม่ได้ ต้องเลื่อน ไม่ใช่ตัดสิน",
        "3. รายงานเข้า Slack **ครั้งเดียว** ว่าเงียบไปกี่วันและพลาดอะไร แล้วลบไฟล์นี้",
        "",
        "_ไฟล์นี้จะถูกลบอัตโนมัติในรอบถัดไปที่ชั้น agent กลับมาทำงาน_",
    ]
    _atomic_write_alert("\n".join(L) + "\n")


def clear_alert():
    if os.path.lexists(ALERT):
        os.remove(ALERT)
        return True
    return False


def _guarded_entrypoint(entrypoint=None):
    """Map unexpected local exceptions to the reserved runner-failure exit.

    Python's default uncaught-exception code is 1, but this tool deliberately
    uses 1 for an evidence-UNKNOWN result. Leaking a crash through code 1 would
    let the receipt contract misclassify it as REVIEW_REQUIRED. Emit only the
    exception class so private paths or values in the message cannot escape.
    """
    target = main if entrypoint is None else entrypoint
    try:
        return target()
    except Exception as exc:
        print("agent-gap RUNNER_FAILED unexpected %s" %
              type(exc).__name__, file=sys.stderr)
        return 3


def selftest():
    """Prove the judge can BOTH fire and stay quiet. A gap detector that has only
    ever returned ok is indistinguishable from one that is not wired up - which is
    exactly what the Slack charter turned out to be."""
    now = datetime.datetime(2026, 8, 7, 9, 0, 0)

    def at(h):
        return now - datetime.timedelta(hours=h)

    cases = [
        ("all three fresh",              [("a", at(2), 5), ("b", at(3), 5), ("c", at(1), 5)], "ok"),
        ("one fresh, two stale",         [("a", at(2), 5), ("b", at(90), 5), ("c", at(70), 5)], "ok"),
        ("25h - inside the window",      [("a", at(25), 5), ("b", None, 0), ("c", None, 0)], "ok"),
        ("26h - exactly at threshold",   [("a", at(26), 5), ("b", None, 0), ("c", None, 0)], "silent"),
        ("the real 3-5 Aug gap (72h)",   [("a", at(72), 9), ("b", at(74), 9), ("c", at(80), 9)], "silent"),
        ("no rows anywhere",             [("a", None, 0), ("b", None, 0), ("c", None, 0)], "unknown"),
        ("rows exist but no timestamps", [("a", None, 4), ("b", None, 2), ("c", None, 0)], "unknown"),
        ("timestamp in the future",      [("a", at(-5), 5), ("b", None, 0), ("c", None, 0)], "unknown"),
    ]
    bad = 0
    for label, seen, want in cases:
        got, hours, why = judge(now, seen)
        ok = got == want
        bad += 0 if ok else 1
        print("  %-32s %-8s (want %-8s) %s" % (label, got, want, "OK" if ok else "*** FAIL"))
        if not ok:
            print("      %s" % why)

    # _ts_of must accept every field name this repo actually writes, or a live
    # trace silently reads as dead. That misclassification is the whole failure.
    print("\n  _ts_of field names")
    fields = [
        ({"ts": "2026-08-06T21:31:52+07:00"}, "2026-08-06T21:31:52+07:00"),
        ({"checked_at": "2026-08-06T08:30:07"}, "2026-08-06T08:30:07"),
        ({"timestamp": "2026-08-06T07:00:00"}, "2026-08-06T07:00:00"),
        ({"at": "2026-08-06T07:00:00"}, "2026-08-06T07:00:00"),
        ({"when": "2026-08-06T07:00:00"}, None),
        ({"ts": 1754000000}, None),
        ({"ts": "short"}, None),
        ({}, None),
    ]
    for row, want in fields:
        got = _ts_of(row)
        ok = got == want
        bad += 0 if ok else 1
        print("    %-40s %-28s %s" % (str(row)[:40], str(got)[:28], "OK" if ok else "*** FAIL"))

    # ชั้นที่สอง ต้องพิสูจน์ว่ามันทั้งดังได้และเงียบได้ เหมือนกันทุกประการ
    print("\n  judge_reporting (งานเดิน แต่รายงานไม่ออก)")
    def d(days_ago):
        return (now - datetime.timedelta(days=days_ago)).replace(hour=0, minute=0, second=0)
    rep_cases = [
        ("activity 2h + report today",     2.0,  d(0),  "ok"),
        ("activity 2h + report 1 day old", 2.0,  d(1),  "ok"),
        ("THE REAL 6 Aug CASE: work fresh, report 6 days old", 2.0, d(6), "reporting-dark"),
        ("exactly 48h old report",         2.0,  d(2),  "reporting-dark"),
        ("47h is still inside the window", 2.0,  now - datetime.timedelta(hours=47), "ok"),
        ("no report file at all",          2.0,  None,  "unknown"),
        ("agent already silent -> skip",   99.0, d(9),  "n/a"),
        ("activity unknown -> skip",       None, d(9),  "n/a"),
        ("report dated in the future",     2.0,  now + datetime.timedelta(days=1), "unknown"),
    ]
    for label, ah, rd, want in rep_cases:
        got, why = judge_reporting(now, ah, rd)
        ok = got == want
        bad += 0 if ok else 1
        print("    %-52s %-15s (want %-15s) %s" % (label, got, want, "OK" if ok else "*** FAIL"))
        if not ok:
            print("        %s" % why)

    # newest_report ต้องไม่หลงไฟล์ที่ไม่ได้ลงวันที่ (เช่น moji_out.txt ที่อยู่ในโฟลเดอร์เดียวกันจริง)
    print("\n  newest_report (ห้ามหลงไฟล์ scratch)")
    import tempfile
    td = tempfile.mkdtemp(prefix="agr_")
    for fn in ("2026-08-01.md", "2026-07-30.md", "moji_out.txt", "notes.md", "2026-13-99.md"):
        io.open(os.path.join(td, fn), "w", encoding="utf-8").write("x")
    got, where = newest_report([td])
    want = datetime.datetime(2026, 8, 1)
    ok = got == want
    bad += 0 if ok else 1
    print("    %-52s %-15s (want %-15s) %s" % ("picks newest dated file, ignores scratch",
          got.strftime("%Y-%m-%d") if got else None, "2026-08-01", "OK" if ok else "*** FAIL"))
    got2, _ = newest_report([os.path.join(td, "nope")])
    ok2 = got2 is None
    bad += 0 if ok2 else 1
    print("    %-52s %-15s (want %-15s) %s" % ("missing directory -> None, not a crash",
          got2, "None", "OK" if ok2 else "*** FAIL"))
    import shutil; shutil.rmtree(td, ignore_errors=True)

    print("\n  scheduler registry grading (read-only pure cases)")
    sched_now = datetime.datetime(2026, 8, 24, 10, 0, tzinfo=LOCAL_TZ)
    cron_cases = [
        ("daily latest slot", "0 8 * * *", "2026-08-24T08:00:00+07:00"),
        ("weekday list latest slot", "10 8 * * 1,3,5", "2026-08-24T08:10:00+07:00"),
        ("Sunday weekly latest slot", "22 9 * * 0", "2026-08-23T09:22:00+07:00"),
        ("hour step latest slot", "0 */12 * * *", "2026-08-24T00:00:00+07:00"),
    ]
    scheduler_case_count = 0
    for label, expression, want in cron_cases:
        scheduler_case_count += 1
        got = latest_cron_due(expression, sched_now).isoformat()
        ok = got == want
        bad += 0 if ok else 1
        print("    %-38s %-25s (want %-25s) %s" % (
            label, got, want, "OK" if ok else "*** FAIL"))

    filter_cases = [
        ("shared Pantip id is monitored", "daily-pantip-threads-engine", True),
        ("IG project control id is monitored", "ig-weekly-pulse", True),
        ("unrelated IG id is ignored", "ig-personal-reminder", False),
        ("unrelated personal task is ignored", "airbnb-tax-pnd90-annual", False),
    ]
    for label, task_id, want in filter_cases:
        scheduler_case_count += 1
        got = _project_task(task_id)
        ok = got is want
        bad += 0 if ok else 1
        print("    %-46s %-5s (want %-5s) %s" % (
            label, got, want, "OK" if ok else "*** FAIL"))
    scheduler_case_count += 1
    got = _project_task("ig-weekly-pulse", {
        "userSelectedFolders": [REPO],
    })
    ok = got is True
    bad += 0 if ok else 1
    print("    %-46s %-5s (want %-5s) %s" % (
        "exact repo folder binding is monitored", got, True,
        "OK" if ok else "*** FAIL"))

    # Exact-id ownership must survive the registry discovery boundary even if
    # older app data has no userSelectedFolders/cwd metadata.  A neighbouring
    # generic ``ig-*`` schedule must not be pulled into this project's health
    # result merely because its name shares the channel prefix.
    scheduler_case_count += 1
    with tempfile.TemporaryDirectory(prefix="agrig_") as ig_td:
        ig_path = Path(ig_td) / "scheduled-tasks.json"
        ig_rows = [{
            "id": "ig-weekly-pulse",
            "enabled": True,
            "filePath": "IG-PROJECT",
            "cronExpression": "0 9 * * 1",
            "lastScheduledFor": "2026-08-17T02:00:00Z",
            "lastRunAt": "2026-08-17T02:01:00Z",
        }, {
            "id": "ig-personal-reminder",
            "enabled": True,
            "filePath": "IG-UNRELATED",
            "cronExpression": "0 9 * * 1",
            "lastScheduledFor": "2026-08-17T02:00:00Z",
            "lastRunAt": "2026-08-17T02:01:00Z",
        }]
        ig_raw = json.dumps(
            {"scheduledTasks": ig_rows}, sort_keys=True).encode("utf-8")
        ig_path.write_bytes(ig_raw)
        discovered, discovery_error = _stable_raw_registry({
            "name": "cowork",
            "registry_path": str(ig_path),
            "sha256": hashlib.sha256(ig_raw).hexdigest(),
            "records": [{
                "id": row["id"],
                "enabled": row["enabled"],
                "file_path": row["filePath"],
            } for row in ig_rows],
        })
    discovered_ids = ([row.get("id") for row in discovered]
                      if isinstance(discovered, list) else [])
    if discovery_error is None and len(discovered_ids) == 1:
        ig_verdict, _ig_detail, ig_graded = judge_scheduler(
            sched_now, discovered)
        ig_status = ig_graded[0].get("status") if ig_graded else None
    else:
        ig_verdict, ig_status = None, None
    ok = (discovery_error is None and
          discovered_ids == ["ig-weekly-pulse"] and
          ig_verdict == "missed-or-stuck" and
          ig_status == "MISSED_OR_STUCK")
    bad += 0 if ok else 1
    print("    %-46s %-38s %s" % (
        "exact IG control discovered and graded",
        "%s/%s" % (ig_verdict, ig_status),
        "OK" if ok else "*** FAIL"))

    scheduler_case_count += 1
    try:
        _cron_match("0 8 * * 0-7", sched_now)
        got_error = False
    except ValueError:
        got_error = True
    bad += 0 if got_error else 1
    print("    %-46s %-5s (want %-5s) %s" % (
        "ambiguous Sunday alias range fails closed", got_error, True,
        "OK" if got_error else "*** FAIL"))

    scheduler_case_count += 1
    try:
        _project_task("ig-malformed", {"userSelectedFolders": 7})
        got_error = False
    except ValueError:
        got_error = True
    bad += 0 if got_error else 1
    print("    %-46s %-5s (want %-5s) %s" % (
        "malformed ownership binding fails closed", got_error, True,
        "OK" if got_error else "*** FAIL"))

    scheduler_case_count += 1
    try:
        _project_task("ngernduangold-malformed", {"userSelectedFolders": 7})
        got_error = False
    except ValueError:
        got_error = True
    bad += 0 if got_error else 1
    print("    %-46s %-5s (want %-5s) %s" % (
        "prefixed malformed ownership fails closed", got_error, True,
        "OK" if got_error else "*** FAIL"))

    # The production registry boundary must convert that malformed ownership
    # shape into UNKNOWN evidence instead of letting ValueError terminate the
    # process with Python's ambiguous exit code 1.
    scheduler_case_count += 1
    with tempfile.TemporaryDirectory(prefix="agrmal_") as malformed_td:
        malformed_path = Path(malformed_td) / "scheduled-tasks.json"
        malformed_raw = json.dumps({"scheduledTasks": [{
            "id": "unprefixed-project-task",
            "enabled": True,
            "filePath": "X",
            "userSelectedFolders": 7,
        }]}, sort_keys=True).encode("utf-8")
        malformed_path.write_bytes(malformed_raw)
        malformed_rows, malformed_error = _stable_raw_registry({
            "registry_path": str(malformed_path),
            "sha256": hashlib.sha256(malformed_raw).hexdigest(),
            "records": [{
                "id": "unprefixed-project-task",
                "enabled": True,
                "file_path": "X",
            }],
        })
    ok = (malformed_rows is None and
          malformed_error == "registry task ownership fields are malformed")
    bad += 0 if ok else 1
    print("    %-46s %-17s %s" % (
        "malformed registry becomes UNKNOWN boundary",
        "UNKNOWN" if ok else str(malformed_error),
        "OK" if ok else "*** FAIL"))

    due_ms = int(datetime.datetime(2026, 10, 9, 9, 0,
                                   tzinfo=LOCAL_TZ).timestamp() * 1000)
    grace_due_ms = int(datetime.datetime(2026, 8, 24, 9, 50,
                                         tzinfo=LOCAL_TZ).timestamp() * 1000)
    scheduler_cases = [
        ("stale dispatch is not hidden by fresh traces", [{
            "source": "cowork", "id": "ngernduangold-daily",
            "cronExpression": "0 8 * * *", "lastScheduledFor": "2026-08-23T01:00:00Z",
            "lastRunAt": "2026-08-23T01:01:00Z"}], "missed-or-stuck",
         "MISSED_OR_STUCK"),
        ("current dispatch without session is unknown", [{
            "source": "ccd", "id": "ngernduangold-daily",
            "cronExpression": "0 8 * * *", "lastScheduledFor": "2026-08-24T01:00:00Z",
            "lastRunAt": "2026-08-24T01:01:00Z"}], "unknown", "UNKNOWN"),
        ("bound error session is runner-failed", [{
            "source": "ccd", "id": "ngernduangold-error",
            "cronExpression": "0 8 * * *", "lastScheduledFor": "2026-08-24T01:00:00Z",
            "lastRunAt": "2026-08-24T01:01:00Z",
            "session_evidence": {"error_class": "WEEKLY_LIMIT",
                                 "session_sha256": "a" * 64}}],
         "runner-failed", "RUNNER_FAILED"),
        ("bound no-error session inside SLA is unverified", [{
            "source": "ccd", "id": "ngernduangold-running",
            "cronExpression": "0 8 * * *", "lastScheduledFor": "2026-08-24T01:00:00Z",
            "lastRunAt": "2026-08-24T01:01:00Z",
            "session_evidence": {"error_class": None,
                                 "session_sha256": "b" * 64}}],
         "unknown", "STARTED_UNVERIFIED"),
        ("slot without matching lastRun is missed-or-stuck", [{
            "source": "cowork", "id": "ngernduangold-dispatch-only",
            "cronExpression": "0 8 * * *", "lastScheduledFor": "2026-08-24T01:00:00Z",
            "lastRunAt": None}], "missed-or-stuck", "MISSED_OR_STUCK"),
        ("old no-error session without receipt is unknown", [{
            "source": "cowork", "id": "ngernduangold-no-deliverable",
            "cronExpression": "0 5 * * *", "lastScheduledFor": "2026-08-23T22:00:00Z",
            "lastRunAt": "2026-08-23T22:01:00Z",
            "session_evidence": {"error_class": None,
                                 "session_sha256": "c" * 64}}],
         "unknown", "UNKNOWN"),
        ("late catch-up cannot satisfy an earlier slot", [{
            "source": "cowork", "id": "ngernduangold-late",
            "cronExpression": "0 8 * * *", "lastScheduledFor": "2026-08-24T01:00:00Z",
            "lastRunAt": "2026-08-24T02:30:00Z"}],
         "missed-or-stuck", "MISSED_OR_STUCK"),
        ("future one-time job is not missed", [{
            "source": "cowork", "id": "ngernduangold-future", "fireAt": due_ms,
            "lastScheduledFor": None, "lastRunAt": None}], "ok", "SKIP"),
        ("one-time error inside grace is not hidden", [{
            "source": "cowork", "id": "ngernduangold-one-time-error",
            "fireAt": grace_due_ms,
            "lastScheduledFor": "2026-08-24T02:50:00Z",
            "lastRunAt": "2026-08-24T02:51:00Z",
            "session_evidence": {"error_class": "WEEKLY_LIMIT",
                                 "session_sha256": "e" * 64}}],
         "runner-failed", "RUNNER_FAILED"),
        ("malformed timestamp fails closed", [{
            "source": "cowork", "id": "ngernduangold-bad",
            "cronExpression": "0 8 * * *", "lastScheduledFor": "not-a-time",
            "lastRunAt": None}], "unknown", "UNKNOWN"),
    ]
    for label, rows, want_verdict, want_task in scheduler_cases:
        scheduler_case_count += 1
        got_verdict, why, got_rows = judge_scheduler(sched_now, rows)
        got_task = got_rows[0]["status"]
        ok = got_verdict == want_verdict and got_task == want_task
        bad += 0 if ok else 1
        print("    %-46s %-17s/%-20s %s" % (
            label, got_verdict, got_task, "OK" if ok else "*** FAIL"))
        if not ok:
            print("        %s" % why)

    scheduler_case_count += 1
    mixed_verdict, mixed_detail, mixed_rows = judge_scheduler(sched_now, [{
        "source": "cowork", "id": "ngernduangold-mixed-missed",
        "cronExpression": "0 8 * * *",
        "lastScheduledFor": "2026-08-23T01:00:00Z",
        "lastRunAt": "2026-08-23T01:01:00Z",
    }, {
        "source": "cowork", "id": "ngernduangold-mixed-failed",
        "cronExpression": "0 8 * * *",
        "lastScheduledFor": "2026-08-24T01:00:00Z",
        "lastRunAt": "2026-08-24T01:01:00Z",
        "session_evidence": {"error_class": "WEEKLY_LIMIT",
                             "session_sha256": "6" * 64},
    }])
    mixed_counts = _scheduler_state_counts(mixed_rows)
    ok = (mixed_verdict == "missed-or-stuck+runner-failed" and
          mixed_counts["missed_or_stuck"] == 1 and
          mixed_counts["current_runner_failed"] == 1 and
          mixed_counts["last_attempt_runner_failed"] == 0 and
          "1 current runner-failed" in mixed_detail)
    bad += 0 if ok else 1
    print("    %-46s %-38s %s" % (
        "mixed current missed and failed both aggregate",
        mixed_verdict, "OK" if ok else "*** FAIL"))

    scheduler_case_count += 1
    stale_verdict, stale_detail, stale_rows = judge_scheduler(sched_now, [{
        "source": "cowork", "id": "ngernduangold-stale-failed",
        "cronExpression": "0 8 * * *",
        "lastScheduledFor": "2026-08-18T01:00:00Z",
        "lastRunAt": "2026-08-18T01:01:00Z",
        "session_evidence": {"error_class": "WEEKLY_LIMIT",
                             "session_sha256": "7" * 64},
    }])
    stale_counts = _scheduler_state_counts(stale_rows)
    ok = (stale_verdict == "missed-or-stuck" and
          stale_rows[0].get("status") == "MISSED_OR_STUCK" and
          stale_counts["current_runner_failed"] == 0 and
          stale_counts["last_attempt_runner_failed"] == 1 and
          "0 current runner-failed" in stale_detail and
          "1 last-attempt runner-failed" in stale_detail)
    bad += 0 if ok else 1
    print("    %-46s %-38s %s" % (
        "stale failure stays separate from current miss",
        stale_verdict, "OK" if ok else "*** FAIL"))

    # A just-due slot must not hide the most recent slot whose grace window has
    # actually closed.  At 08:10 the 08:00 job is still inside its 20-minute
    # grace, so the grader must evaluate yesterday's mature 08:00 slot.
    scheduler_case_count += 1
    grace_now = datetime.datetime(2026, 8, 24, 8, 10, tzinfo=LOCAL_TZ)
    got_verdict, why, got_rows = judge_scheduler(grace_now, [{
        "source": "cowork", "id": "ngernduangold-grace-boundary",
        "cronExpression": "0 8 * * *",
        "lastScheduledFor": "2026-08-23T01:00:00Z",
        "lastRunAt": "2026-08-23T01:01:00Z",
        "session_evidence": {"error_class": "WEEKLY_LIMIT",
                             "session_sha256": "d" * 64},
    }])
    got_task = got_rows[0]["status"]
    got_due = got_rows[0]["due_at"]
    ok = (got_verdict == "runner-failed" and
          got_task == "RUNNER_FAILED" and
          got_due == "2026-08-23T08:00:00+07:00")
    bad += 0 if ok else 1
    print("    %-46s %-17s/%-20s %s" % (
        "inside-grace slot cannot hide mature failure", got_verdict, got_task,
        "OK" if ok else "*** FAIL"))
    if not ok:
        print("        %s; due=%s" % (why, got_due))

    current_grace_cases = [
        ("current no-error attempt stays in-flight", {
            "error_class": None, "session_id": "private-running",
            "session_sha256": "f" * 64, "error_sha256": None,
        }, "unknown", "STARTED_UNVERIFIED"),
        ("current explicit error overrides grace", {
            "error_class": "WEEKLY_LIMIT", "session_id": "private-failed",
            "session_sha256": "0" * 64, "error_sha256": "1" * 64,
        }, "runner-failed", "RUNNER_FAILED"),
    ]
    for label, evidence, want_verdict, want_task in current_grace_cases:
        scheduler_case_count += 1
        got_verdict, why, got_rows = judge_scheduler(grace_now, [{
            "source": "cowork", "id": "ngernduangold-current-grace",
            "cronExpression": "0 8 * * *",
            "lastScheduledFor": "2026-08-24T01:00:00Z",
            "lastRunAt": "2026-08-24T01:01:00Z",
            "session_evidence": evidence,
        }])
        got_task = got_rows[0]["status"]
        got_due = got_rows[0]["due_at"]
        ok = (got_verdict == want_verdict and got_task == want_task and
              got_due == "2026-08-24T08:00:00+07:00")
        bad += 0 if ok else 1
        print("    %-46s %-17s/%-20s %s" % (
            label, got_verdict, got_task, "OK" if ok else "*** FAIL"))
        if not ok:
            print("        %s; due=%s" % (why, got_due))

    # A task is only complete when the exact due slot, registry dispatch,
    # app-owned session, local receipt and every deliverable hash form one
    # chain.  These cases also prove a forged receipt cannot rescue a miss.
    receipt_record = {
        "source": "cowork",
        "id": "ngernduangold-receipt-selftest",
        "cronExpression": "0 8 * * *",
        "lastScheduledFor": "2026-08-24T01:00:00Z",
        "lastRunAt": "2026-08-24T01:01:00Z",
        "_task_record_sha256": "8" * 64,
        "session_evidence": {
            "error_class": None,
            "session_id": "private-receipt-selftest",
            "session_sha256": "9" * 64,
            "binding_sha256": "9" * 64,
            "error_sha256": None,
            "created_at": "2026-08-24T08:01:00+07:00",
            "last_activity_at": "2026-08-24T08:02:00+07:00",
        },
    }
    deliverable_path = Path(REPO) / "README.md"
    deliverable_raw = deliverable_path.read_bytes()

    def receipt_fixture(status="COMPLETED", blockers=None,
                        deliverable_sha=None, task_id=None):
        return {
            "schema_version": SCHEDULER_RECEIPT_SCHEMA_VERSION,
            "source": "cowork",
            "task_id": task_id or receipt_record["id"],
            "due_at": "2026-08-24T08:00:00+07:00",
            "registry": {
                "task_record_sha256": "8" * 64,
                "last_scheduled_for": "2026-08-24T08:00:00+07:00",
                "last_run_at": "2026-08-24T08:01:00+07:00",
            },
            "session": {
                "binding_sha256": "9" * 64,
                "created_at": "2026-08-24T08:01:00+07:00",
            },
            "terminal": {
                "status": status,
                "completed_at": "2026-08-24T08:03:00+07:00",
                "result_sha256": "a" * 64,
                "blockers": ([] if blockers is None else blockers),
            },
            "deliverables": [{
                "path": "README.md",
                "size": len(deliverable_raw),
                "sha256": (deliverable_sha or
                           hashlib.sha256(deliverable_raw).hexdigest()),
            }],
        }

    with tempfile.TemporaryDirectory(prefix="agsr_") as receipt_td:
        receipt_file = (Path(receipt_td) / "cowork" /
                        receipt_record["id"] /
                        "20260824T010000Z.json")
        receipt_file.parent.mkdir(parents=True)

        scheduler_case_count += 1
        receipt_file.write_text(json.dumps(receipt_fixture(), sort_keys=True),
                                encoding="utf-8")
        got_verdict, why, got_rows = judge_scheduler(
            sched_now, [receipt_record], receipt_root=receipt_td)
        got_row = got_rows[0]
        ok = (got_verdict == "ok" and got_row.get("status") == "COMPLETED" and
              got_row.get("receipt_evidence", {}).get("state") == "VALID" and
              got_row.get("evidence_chain", {}).get("deliverables") == "VALID")
        bad += 0 if ok else 1
        print("    %-46s %-38s %s" % (
            "exact receipt and deliverable close completion",
            "%s/%s" % (got_verdict, got_row.get("status")),
            "OK" if ok else "*** FAIL"))
        if not ok:
            print("        %s; %s" % (why, got_row.get("receipt_evidence")))

        scheduler_case_count += 1
        receipt_file.write_text(json.dumps(receipt_fixture(
            status="COMPLETED_BLOCKED", blockers=["OWNER_GATE"]),
            sort_keys=True), encoding="utf-8")
        got_verdict, why, got_rows = judge_scheduler(
            sched_now, [receipt_record], receipt_root=receipt_td)
        got_row = got_rows[0]
        ok = (got_verdict == "completed-blocked" and
              got_row.get("status") == "COMPLETED_BLOCKED" and
              got_row.get("receipt_evidence", {}).get("state") == "VALID")
        bad += 0 if ok else 1
        print("    %-46s %-38s %s" % (
            "blocked terminal receipt stays blocked",
            "%s/%s" % (got_verdict, got_row.get("status")),
            "OK" if ok else "*** FAIL"))

        scheduler_case_count += 1
        receipt_file.write_text(json.dumps(receipt_fixture(
            deliverable_sha="0" * 64), sort_keys=True), encoding="utf-8")
        got_verdict, why, got_rows = judge_scheduler(
            sched_now, [receipt_record], receipt_root=receipt_td)
        got_row = got_rows[0]
        ok = (got_verdict == "unknown" and
              got_row.get("status") == "UNKNOWN" and
              got_row.get("receipt_evidence", {}).get("state") == "INVALID" and
              got_row.get("evidence_chain", {}).get("deliverables") == "INVALID")
        bad += 0 if ok else 1
        print("    %-46s %-38s %s" % (
            "deliverable hash mismatch fails closed",
            "%s/%s" % (got_verdict, got_row.get("status")),
            "OK" if ok else "*** FAIL"))

        scheduler_case_count += 1
        stale_record = dict(receipt_record)
        stale_record.update({
            "lastScheduledFor": "2026-08-23T01:00:00Z",
            "lastRunAt": "2026-08-23T01:01:00Z",
        })
        got_verdict, why, got_rows = judge_scheduler(
            sched_now, [stale_record], receipt_root=receipt_td)
        got_row = got_rows[0]
        ok = (got_verdict == "missed-or-stuck" and
              got_row.get("status") == "MISSED_OR_STUCK" and
              "receipt_evidence" not in got_row and
              got_row.get("evidence_chain", {}).get("terminal_receipt") ==
              "NOT_CHECKED_WITHOUT_EXACT_DISPATCH")
        bad += 0 if ok else 1
        print("    %-46s %-38s %s" % (
            "receipt cannot rescue stale dispatch",
            "%s/%s" % (got_verdict, got_row.get("status")),
            "OK" if ok else "*** FAIL"))

    # Prove the app-owned registry timestamp is bound only to the exact session
    # file, and that raw error/prompt/account fields never leave the scanner.
    scheduler_case_count += 1
    session_td = tempfile.mkdtemp(prefix="ags_")
    try:
        session_path = Path(session_td) / "local_selftest.json"
        session_raw = json.dumps({
            "scheduledTaskId": "ngernduangold-session-selftest",
            "sessionId": "local_selftest",
            "createdAt": 1787533260000,
            "lastActivityAt": 1787533270000,
            "error": "Weekly limit reached for private@example.invalid",
            "errorAt": 1787533270000,
            "prompt": "must never leave scanner",
        }).encode("utf-8")
        session_path.write_bytes(session_raw)
        os.utime(session_path, (1787533260, 1787533260))
        enriched, scan_error = _attach_session_evidence(
            {"registry_path": str(Path(session_td) / "scheduled_tasks.json")},
            [{"id": "ngernduangold-session-selftest",
              "lastRunAt": "2026-08-24T01:01:00Z"}])
        evidence = enriched[0].get("session_evidence") if enriched else None
        allowed_keys = {
            "session_id", "created_at", "last_activity_at", "session_sha256",
            "binding_sha256",
            "error_class", "error_sha256", "error_at",
        }
        ok = (scan_error is None and isinstance(evidence, dict) and
              set(evidence) == allowed_keys and
              evidence.get("error_class") == "WEEKLY_LIMIT" and
              "private@example.invalid" not in repr(evidence) and
              "must never leave scanner" not in repr(evidence))
        bad += 0 if ok else 1
        print("    %-46s %-38s %s" % (
            "exact session binding emits safe whitelist",
            evidence.get("error_class") if isinstance(evidence, dict)
            else scan_error, "OK" if ok else "*** FAIL"))
    finally:
        shutil.rmtree(session_td, ignore_errors=True)

    scheduler_case_count += 1
    public = _public_scheduler_tasks([{
        "source": "cowork", "id": "ngernduangold-private-selftest",
        "status": "RUNNER_FAILED", "reason": "safe reason",
        "session_evidence": {
            "session_id": "private-session-id",
            "session_sha256": "2" * 64,
            "error_sha256": "3" * 64,
            "error_class": "WEEKLY_LIMIT",
            "error_at": "2026-08-24T08:01:10+07:00",
        },
    }])
    serialized_public = json.dumps(public, sort_keys=True)
    ok = ("private-session-id" not in serialized_public and
          "session_sha256" not in serialized_public and
          "error_sha256" not in serialized_public and
          "WEEKLY_LIMIT" in serialized_public)
    bad += 0 if ok else 1
    print("    %-46s %-38s %s" % (
        "public scheduler JSON removes identifiers", "redacted",
        "OK" if ok else "*** FAIL"))

    scheduler_case_count += 1
    private_exception_text = "private-path-and-account-must-not-leak"

    def unexpected_failure_fixture():
        raise RuntimeError(private_exception_text)

    guarded_stderr = io.StringIO()
    with contextlib.redirect_stderr(guarded_stderr):
        guarded_rc = _guarded_entrypoint(unexpected_failure_fixture)
    guarded_output = guarded_stderr.getvalue()
    ok = (guarded_rc == 3 and "RuntimeError" in guarded_output and
          private_exception_text not in guarded_output)
    bad += 0 if ok else 1
    print("    %-46s %-38s %s" % (
        "unexpected exception is sanitised exit 3",
        "exit %d" % guarded_rc, "OK" if ok else "*** FAIL"))

    print("\n%d cases, %d failed" % (
        len(cases) + len(fields) + len(rep_cases) + 2 + scheduler_case_count, bad))
    return 1 if bad else 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--quiet", action="store_true")
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument(
        ALERT_MUTATION_FLAG,
        dest="update_agent_silent_alert_file",
        action="store_true",
        help=("explicitly allow this invocation to atomically create, replace, "
              "or clear only AGENT-SILENT-ALERT.md"),
    )
    a = ap.parse_args()
    if a.selftest:
        if a.update_agent_silent_alert_file:
            ap.error("--selftest cannot mutate the production alert")
        return selftest()

    now = datetime.datetime.now()
    seen = []
    for lab, path in _traces():
        dt, rows = last_seen(path)
        seen.append((lab, dt, rows))
    verdict, hours, detail = judge(now, seen)

    # ชั้นที่สอง: งานเดินอยู่ แต่ไม่มีรายงานออกมาเลย (เคส 6 ส.ค. 2026)
    rep_dt, rep_path = newest_report()
    rep_verdict, rep_detail = judge_reporting(now, hours, rep_dt)

    # ชั้นที่สาม: อ่าน registry จริงแบบ hash-stable เพื่อไม่ให้ไฟล์ activity
    # ที่ถูกแตะด้วย manual audit บัง scheduler blackout ได้อีก
    records, scheduler_error = scheduler_records()
    if scheduler_error:
        scheduler_verdict, scheduler_detail, scheduler_tasks = (
            "unknown", scheduler_error, [])
    else:
        scheduler_verdict, scheduler_detail, scheduler_tasks = judge_scheduler(
            datetime.datetime.now(LOCAL_TZ), records)

    scheduler_blocking = any(
        row.get("status") in {
            "MISSED_OR_STUCK", "RUNNER_FAILED", "STUCK", "COMPLETED_BLOCKED"
        } or row.get("disabled_unresolved") is True
        for row in scheduler_tasks)
    alert_action = "unchanged_read_only"
    if scheduler_blocking:
        if a.update_agent_silent_alert_file:
            write_scheduler_alert(scheduler_detail, scheduler_tasks)
            alert_action = "atomically_replaced"
        code = 2
        aggregate_verdict = scheduler_verdict
        msg = "agent-gap %s  %s -> %s" % (
            scheduler_verdict.upper(), scheduler_detail,
            ("updated local alert" if a.update_agent_silent_alert_file
             else "read-only; local alert unchanged"))
    elif verdict == "silent":
        if a.update_agent_silent_alert_file:
            write_alert(hours, detail, seen)
            alert_action = "atomically_replaced"
        code = 2
        aggregate_verdict = "silent"
        msg = "agent-gap SILENT %.1fh -> %s" % (
            hours, ("updated local alert" if a.update_agent_silent_alert_file
                    else "read-only; local alert unchanged"))
    elif verdict == "ok" and rep_verdict == "reporting-dark":
        if a.update_agent_silent_alert_file:
            write_alert(hours, detail, seen, reporting=rep_detail)
            alert_action = "atomically_replaced"
        code = 2
        aggregate_verdict = "reporting-dark"
        msg = "agent-gap REPORTING-DARK  %s -> %s" % (
            rep_detail, ("updated local alert"
                         if a.update_agent_silent_alert_file
                         else "read-only; local alert unchanged"))
    elif verdict == "ok" and rep_verdict == "ok" and scheduler_verdict == "ok":
        cleared = (clear_alert()
                   if a.update_agent_silent_alert_file else False)
        if a.update_agent_silent_alert_file:
            alert_action = "deleted" if cleared else "unchanged_absent"
        code = 0
        aggregate_verdict = "ok"
        msg = "agent-gap OK  %s | รายงาน: %s | scheduler: %s | alert: %s" % (
            detail, rep_detail, scheduler_detail,
            ("cleared" if cleared else
             ("already absent" if a.update_agent_silent_alert_file
              else "read-only; unchanged")))
    else:
        code = 1
        aggregate_verdict = "unknown"
        if scheduler_verdict == "unknown":
            unknown_detail = scheduler_detail
        elif rep_verdict == "unknown":
            unknown_detail = rep_detail
        else:
            unknown_detail = detail
        msg = "agent-gap UNKNOWN  %s (ไม่ถือว่า PASS)" % unknown_detail

    if not a.quiet:
        print(msg)
    if a.json:
        print(json.dumps({"verdict": aggregate_verdict,
                          "activity": verdict, "hours": hours, "detail": detail,
                          "reporting": rep_verdict, "reporting_detail": rep_detail,
                          "scheduler": scheduler_verdict,
                          "scheduler_detail": scheduler_detail,
                          "scheduler_counts": _scheduler_state_counts(
                              scheduler_tasks),
                          "alert_mutation": {
                              "enabled": a.update_agent_silent_alert_file,
                              "action": alert_action,
                          },
                          "scheduler_tasks": _public_scheduler_tasks(
                              scheduler_tasks),
                          "traces": [{"trace": l, "last": d.isoformat() if d else None, "rows": r}
                                     for l, d, r in seen]}, ensure_ascii=False))
    return code


if __name__ == "__main__":
    sys.exit(_guarded_entrypoint())
