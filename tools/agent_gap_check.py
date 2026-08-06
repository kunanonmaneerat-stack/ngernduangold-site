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
  talks to Slack; it writes a file, and the first agent to wake up reports it.

WHAT COUNTS AS "THE AGENT LAYER DID SOMETHING"
  Three independent traces, so one broken writer cannot fake life or fake death:
    - automation-log/post-ledger.jsonl        real posts that went out
    - automation-log/post-guard/history.jsonl the daily guard actually ran
    - automation-log/<YYYY-MM>.jsonl          CC-side routine events
  The newest timestamp across all three is the last sign of life.

THREE-WAY VERDICT, deliberately (same rule as uptime_check)
  ok       - something happened inside the window
  silent   - nothing did, and we could read the files well enough to be sure
  unknown  - the traces are missing or unparseable. NOT reported as silence:
             "I could not look" must never be published as "it is dead", or the
             alert becomes noise and gets ignored on the morning it is real.

EXIT CODES
  0 = ok        1 = unknown      2 = silent (alert file written)

USAGE
  py tools\\agent_gap_check.py
  py tools\\agent_gap_check.py --json
  py tools\\agent_gap_check.py --selftest     # proves it can fire AND stay quiet
"""
import io, os, sys, json, glob, argparse, datetime

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
INBOX = os.path.join(REPO, "automation-log", "cowork-inbox")
ALERT = os.path.join(INBOX, "AGENT-SILENT-ALERT.md")

# 26h, not 24h: the agent tasks are jittered by several minutes and the owner's
# machine is not switched on at a fixed hour. 24h would cry wolf on a late start;
# 26h still catches a genuine missed day the very next morning.
WARN_HOURS = 26
# Two full days with nothing at all is the 27-30 Jul / 3-5 Aug shape. By this
# point content has already been missed and a measurement window is already dirty.
LOUD_HOURS = 48


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


def write_alert(hours, detail, seen):
    if not os.path.isdir(INBOX):
        os.makedirs(INBOX)
    days = hours / 24.0
    loud = hours >= LOUD_HOURS
    L = [
        "# %s ชั้น agent เงียบมา %.1f ชม. (%.1f วัน)" % ("🔴" if loud else "⚠️", hours, days),
        "",
        "เขียนโดย `tools/agent_gap_check.py` จาก **ชั้น cron** (run_daily.cmd) เมื่อ %s"
        % datetime.datetime.now().strftime("%Y-%m-%d %H:%M"),
        "ชั้นนี้รันจาก Windows Task Scheduler จึงไม่ตายพร้อมกับ agent — เป็นตัวเดียวที่พูดได้ตอนนี้",
        "",
        "- %s" % detail,
        "",
        "## ร่องรอยที่ตรวจ",
    ]
    for lab, dt, rows in seen:
        L.append("- `%s` — %s (%d แถว)" % (
            lab, dt.strftime("%Y-%m-%d %H:%M") if dt else "ไม่มีเวลาที่อ่านได้", rows))
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
    with io.open(ALERT, "w", encoding="utf-8", newline="\n") as fh:
        fh.write("\n".join(L) + "\n")


def clear_alert():
    if os.path.isfile(ALERT):
        try:
            os.remove(ALERT)
            return True
        except OSError:
            pass
    return False


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

    print("\n%d cases, %d failed" % (len(cases) + len(fields), bad))
    return 1 if bad else 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--quiet", action="store_true")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    if a.selftest:
        return selftest()

    now = datetime.datetime.now()
    seen = []
    for lab, path in _traces():
        dt, rows = last_seen(path)
        seen.append((lab, dt, rows))
    verdict, hours, detail = judge(now, seen)

    if verdict == "silent":
        write_alert(hours, detail, seen)
        code = 2
        msg = "agent-gap SILENT %.1fh -> wrote %s" % (hours, ALERT)
    elif verdict == "ok":
        cleared = clear_alert()
        code = 0
        msg = "agent-gap OK  %s%s" % (detail, "  (cleared stale alert)" if cleared else "")
    else:
        code = 1
        msg = "agent-gap UNKNOWN  %s (ไม่ถือว่าเงียบ)" % detail

    if not a.quiet:
        print(msg)
    if a.json:
        print(json.dumps({"verdict": verdict, "hours": hours, "detail": detail,
                          "traces": [{"trace": l, "last": d.isoformat() if d else None, "rows": r}
                                     for l, d, r in seen]}, ensure_ascii=False))
    return code


if __name__ == "__main__":
    sys.exit(main())
