#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tests for the preflight guards added 31 Jul 2026.

WHY THIS FILE EXISTS
  Every guard in here was written after a real incident, and each one was verified
  once by hand in the session that wrote it. A guard verified only once is a guard
  that quietly rots: the dangerous failure mode is not "it breaks loudly", it is
  "it keeps returning PASS after it has gone blind". So every check must prove it
  can BOTH fire and stay quiet, on every run.

  Covers:
    check_posting_cap      - <=2 posts/day/channel, >=3h apart (POSTING-POLICY rule 2)
    check_repeat_failures  - same channel failing repeatedly, and recovery detection
    check_open_decisions   - plan gates whose date passed with nobody closing them
    check_content_cliff    - a gate scheduled after the queue it is meant to refill
    manifest_posted_status - the "published" vocabulary gap in post_guard

USAGE
  py tools\\test_preflight_checks.py        # exit 0 = all pass

ASCII-ONLY SOURCE: repo rule - scripts that touch Thai must not contain Thai literals.
"""
import io, os, sys, json, datetime, importlib

# A Thai Windows console is cp874. This file prints fixture text containing U+26D4 and
# other symbols that cp874 cannot encode, so running it by hand died with
# UnicodeEncodeError *before reaching the meta-tests* - i.e. the suite whose entire job
# is to prove no guard is blind was itself unable to report on Windows, while passing
# in the sandbox. Tests that only pass where nobody runs them are not tests.
for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
TMP = os.path.join(HERE, "_test_ledger.tmp.jsonl")

import preflight as P
import post_guard as G

REPO_REAL = os.path.dirname(HERE)
TODAY = datetime.date.today().isoformat()
YESTERDAY = (datetime.date.today() - datetime.timedelta(days=1)).isoformat()

results = []


def check(label, got, want):
    ok = got == want
    results.append(ok)
    print("  %-52s %-5s (want %-5s) %s" % (label, got, want, "OK" if ok else "*** FAIL"))
    return ok


# Fixtures live in the OS temp dir, never inside the repo. Writing them under tools/
# left junk beside the code that the sandbox could not delete, and one bad glob away
# from being committed. Tests should leave no trace in the tree they are testing.
import tempfile
TMPDIR = tempfile.mkdtemp(prefix="pf_fixtures_")


def _fresh_tmp():
    return TMPDIR


def write(rel, data):
    """Write a fixture file under TMPDIR; dict/list -> json, str -> text."""
    path = os.path.join(TMPDIR, rel)
    d = os.path.dirname(path)
    if d and not os.path.isdir(d):
        os.makedirs(d)
    with io.open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(json.dumps(data, ensure_ascii=False) if isinstance(data, (dict, list)) else data)
    return path


def run_check(fn_name, **consts):
    """Call one preflight check with module constants swapped for fixtures.

    Why a generic runner: nine of the fourteen checks had no test at all, and writing a
    bespoke harness per check is exactly the friction that let that happen. One runner
    means adding a case is three lines, so there is no excuse to skip it.
    """
    importlib.reload(P)
    for k, v in consts.items():
        setattr(P, k, v)
    P.results[:] = []
    getattr(P, fn_name)()
    return P.results[0]["status"] if P.results else "(no result)"


def run_check_detail(fn_name, **consts):
    """Same as run_check but returns the DETAIL text, not the status.

    Added 7 Aug 2026: a check can return the right status for the wrong reason,
    or the right status with an empty message that tells the reader nothing.
    check_queue's unknown-verdict branch was doing exactly that. Asserting on
    status alone would not have caught it.
    """
    importlib.reload(P)
    for k, v in consts.items():
        setattr(P, k, v)
    P.results[:] = []
    getattr(P, fn_name)()
    return P.results[0].get("detail", "") if P.results else ""


def run_cap(rows):
    importlib.reload(P)
    with io.open(TMP, "w", encoding="utf-8", newline="\n") as fh:
        for r in rows:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")
    P.LEDGER = TMP
    P.results[:] = []
    P.check_posting_cap()
    return P.results[0]["status"]


def run_fail(rows):
    importlib.reload(P)
    with io.open(TMP, "w", encoding="utf-8", newline="\n") as fh:
        for r in rows:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")
    P.LEDGER = TMP
    P.results[:] = []
    P.check_repeat_failures()
    return P.results[0]


def live(hh, ch="facebook", ty="text", day=None):
    return {"type": ty, "channel": ch, "text_first80": "x",
            "ts": "%sT%s:00:00+07:00" % (day or TODAY, hh)}


def sched(i, publish_day):
    """A clip uploaded now but shown to the audience on publish_day."""
    return {"type": "video", "channel": "youtube", "clip_id": "c%d" % i,
            "text_first80": "x", "ts": "%sT09:%02d:00+07:00" % (TODAY, i * 3),
            "publish_at": publish_day, "source": "cc-dispatcher"}


def fail(ch, hh, day=None, why="NOT POSTED - x"):
    return {"type": "failure", "channel": ch, "text_first80": why,
            "ts": "%sT%s:00:00+07:00" % (day or TODAY, hh)}


print("POSTING CAP  (POSTING-POLICY rule 2: <=2/day/channel, >=3h apart)")
check("live posts 5h apart", run_cap([live("09"), live("14")]), "PASS")
check("live posts 1h apart", run_cap([live("09"), live("10")]), "FAIL")
check("3 live posts, well spaced -> over cap",
      run_cap([live("09"), live("13"), live("17")]), "FAIL")
check("comment does not count as a post",
      run_cap([live("09"), {"type": "comment", "channel": "facebook",
                            "text_first80": "c", "ts": TODAY + "T09:30:00+07:00"}]), "PASS")
check("empty ledger", run_cap([]), "PASS")
check("breach dated yesterday is history, not a gate",
      run_cap([live("09", day=YESTERDAY), live("10", day=YESTERDAY)]), "WARN")
# The false positive that this check shipped with on day one:
check("YT catch-up, 3 clips publishing on 3 days",
      run_cap([sched(0, TODAY), sched(1, "2026-08-01"), sched(2, "2026-08-02")]), "PASS")
check("YT 3 clips all publishing the SAME day",
      run_cap([sched(0, TODAY), sched(1, TODAY), sched(2, TODAY)]), "FAIL")
check("one scheduled + one live on the same day",
      run_cap([sched(0, TODAY), live("09")]), "PASS")
check("pinterest 3 pins spaced (cap is 5)",
      run_cap([live(h, "pinterest", "image") for h in ("01", "05", "09")]), "PASS")
check("pinterest 6 pins",
      run_cap([live(h, "pinterest", "image")
               for h in ("01", "05", "09", "13", "17", "21")]), "FAIL")

print("\nPOLICY WIRING  (numbers must come from policy.json, and fail safe without it)")
importlib.reload(P)
check("cap default read from policy", P.POST_CAP_DEFAULT, 2)
check("pinterest override read from policy", P.POST_CAP_BY_CHANNEL.get("pinterest"), 5)
check("min gap read from policy", P.POST_MIN_GAP_HOURS, 3)
_saved, P.POLICY = P.POLICY, os.path.join(HERE, "no-such-policy.json")
_caps, _gap, _types = P._limits()
P.POLICY = _saved
check("missing policy still enforces the written rule", (_caps.get("default"), _gap), (2, 3))

print("\nREPEAT FAILURES  (must fire when broken, go quiet once genuinely fixed)")
check("one failure is noise", run_fail([fail("facebook", "09")])["status"], "PASS")
check("two failures same channel", run_fail([fail("facebook", "09"), fail("facebook", "11")])["status"], "WARN")
check("three failures same channel",
      run_fail([fail("facebook", "09"), fail("facebook", "11"), fail("facebook", "13")])["status"], "FAIL")
check("delivered again after the last failure = recovered",
      run_fail([fail("facebook", "09"), fail("facebook", "11"), fail("facebook", "13"),
                live("15")])["status"], "PASS")
check("a success BEFORE the last failure is not recovery",
      run_fail([live("08"), fail("facebook", "09"), fail("facebook", "11"),
                fail("facebook", "13")])["status"], "FAIL")
check("failures older than the window are ignored",
      run_fail([fail("facebook", "09", day="2026-06-01"),
                fail("facebook", "11", day="2026-06-01")])["status"], "PASS")
_r = run_fail([fail("tiktok", "09"), fail("tiktok", "11")])
check("auto=false + no auto_legs is tagged as drift", "DRIFT" in _r["detail"], True)
_r = run_fail([fail("facebook", "09"), fail("facebook", "11")])
check("a channel with declared auto_legs is not drift", "DRIFT" in _r["detail"], False)

print("\nPROMPT DRIFT  (must know every date field policy owns, not just 'until')")
importlib.reload(P)
_pol = json.load(io.open(P.POLICY, encoding="utf-8"))
_chan = _pol.get("channels", {})
# Rebuild the same mapping check_prompt_drift builds, and assert it covers BOTH fields.
_owned = {}
for _ch, _v in _chan.items():
    for _f in ("until", "phase_until"):
        if _v.get(_f):
            _owned[_ch] = _v[_f]
            break
check("a channel with 'until' is owned", _owned.get("instagram"), _chan["instagram"]["until"])
check("a channel with only 'phase_until' is owned",
      _owned.get("pantip"), _chan["pantip"].get("phase_until"))
check("a channel with neither is not owned", "threads" in _owned, False)
# The regression itself: on 1 Aug 2026 the auditor prompt carried an expired Pantip phase
# date and this check said PASS, because the mapping only read 'until'.
check("pantip contributes a date at all", bool(_owned.get("pantip")), True)

# --- the two false-FAIL bugs found 1 Aug 2026 ---
_sd = P.SCHEDULED_DIR


def run_drift(body):
    """Write ONE fake task prompt and see what the drift check says about it."""
    importlib.reload(P)
    d = os.path.join(HERE, "_test_sched.tmp")
    t = os.path.join(d, "fake-task")
    if not os.path.isdir(t):
        os.makedirs(t)
    with io.open(os.path.join(t, "SKILL.md"), "w", encoding="utf-8", newline="\n") as fh:
        fh.write(body)
    P.SCHEDULED_DIR = d
    P.results[:] = []
    P.check_prompt_drift()
    return P.results[0]["status"]


_ig = json.load(io.open(P.POLICY, encoding="utf-8"))["channels"]["instagram"]["until"]
_wrong = _ig[:8] + ("01" if not _ig.endswith("01") else "02")     # same month, wrong day
check("real claim: 'instagram' + a wrong date in that month",
      run_drift("instagram is paused until %s" % _wrong), "FAIL")
check("'ig' inside the word 'ignore' is NOT the channel",
      run_drift("ignore anything older than %s" % _wrong), "PASS")
check("a date inside a FILENAME is a reference, not a claim",
      run_drift("instagram: read HANDOFF_%s.md for context" % _wrong), "PASS")
check("bare alias 'ig' as a real word still counts",
      run_drift("ig paused until %s" % _wrong), "FAIL")
check("correct date for the channel is fine",
      run_drift("instagram is paused until %s" % _ig), "PASS")
import shutil
shutil.rmtree(os.path.join(HERE, "_test_sched.tmp"), ignore_errors=True)
P.SCHEDULED_DIR = _sd

print("\nDEAD TOOLING  (a prompt may NAME a retired tool to ban it; ordering one is drift)")
_sd2 = P.SCHEDULED_DIR


def run_dead_unowned(body):
    """เคสเดียวกันแต่ไม่ใช่ task ของเรา -> ต้อง WARN ไม่ใช่ FAIL"""
    d = os.path.join(HERE, '_test_dead.tmp')
    t2 = os.path.join(d, 'fake-task')
    if not os.path.isdir(t2):
        os.makedirs(t2)
    with io.open(os.path.join(t2, 'SKILL.md'), 'w', encoding='utf-8', newline=chr(10)) as fh:
        fh.write(body)
    P.SCHEDULED_DIR = d
    P.results[:] = []
    P.check_dead_tooling()
    return P.results[0]['status']


def run_dead(body):
    d = os.path.join(HERE, "_test_dead.tmp")
    t2 = os.path.join(d, "fake-task")
    if not os.path.isdir(t2):
        os.makedirs(t2)
    with io.open(os.path.join(t2, "SKILL.md"), "w", encoding="utf-8", newline="\n") as fh:
        fh.write(body)
    P.SCHEDULED_DIR = d
    P.OWN_TASKS_DIR = d          # the fake task counts as ours, so drift is a hard FAIL
    P.results[:] = []
    P.check_dead_tooling()
    return P.results[0]["status"]


check("ordering a Postiz call is drift",
      run_dead("2) เติมคิวด้วย integrationSchedulePostTool ผ่าน Postiz MCP"), "FAIL")
check("ordering a Meta MCP call is drift",
      run_dead("1) FB: get_facebook_posts(page_id=...) ดูโพสต์ล่าสุด"), "FAIL")
check("pointing at the old netlify.app host is drift",
      run_dead("ตรวจลิงก์บนเว็บ ngernduangold.netlify.app"), "FAIL")
check("naming Postiz in order to BAN it must pass",
      run_dead("ห้ามใช้ Postiz ทุกรูปแบบ - เลิกใช้ 19 มิ.ย. 2026"), "PASS")
check("naming Meta MCP in order to BAN it must pass",
      run_dead("**ห้ามทำ:** Meta MCP get_facebook_posts - token ยกเลิกถาวร 18 ก.ค. 2026"), "PASS")
check("explaining the 301 from netlify.app must pass",
      run_dead("โดเมนจริงคือ ngernduangold.com (ngernduangold.netlify.app 301 -> apex)"), "PASS")
check("a clean prompt passes",
      run_dead("อ่านสถานะจาก policy.json แล้วรายงาน"), "PASS")

# ownership split: the same drift in a prompt we do NOT own must warn, never block, because
# this agent has no mandate to rewrite Cowork's prompts.
_od = P.OWN_TASKS_DIR
P.OWN_TASKS_DIR = os.path.join(HERE, "_nonexistent_owned.tmp")
check("someone else's prompt with the same drift only warns",
      run_dead_unowned("2) เติมคิวผ่าน Postiz MCP"), "WARN")
P.OWN_TASKS_DIR = _od
shutil.rmtree(os.path.join(HERE, "_test_dead.tmp"), ignore_errors=True)
P.SCHEDULED_DIR = _sd2

print("\nPOLICY DATES IN PROMPTS  (a channel deadline belongs in policy.json, not in a prompt)")
_od3 = P.OWN_TASKS_DIR
_sd3 = P.SCHEDULED_DIR


def run_dates(body, owned=True):
    """Write one fake prompt and read the verdict. owned=False puts it in the other root."""
    d = os.path.join(HERE, "_test_dates.tmp")
    t3 = os.path.join(d, "fake-task")
    if not os.path.isdir(t3):
        os.makedirs(t3)
    with io.open(os.path.join(t3, "SKILL.md"), "w", encoding="utf-8", newline=chr(10)) as fh:
        fh.write(body)
    empty = os.path.join(HERE, "_test_dates_empty.tmp")
    if not os.path.isdir(empty):
        os.makedirs(empty)
    P.OWN_TASKS_DIR = d if owned else empty
    P.SCHEDULED_DIR = empty if owned else d
    P.results[:] = []
    P.check_policy_dates_in_prompts()
    return P.results[0]["status"]


# --- must fire: the date is acting as the channel deadline ---
check("Thai date as a channel deadline",
      run_dates("Pantip FROZEN \u0e16\u0e36\u0e07 16 \u0e01.\u0e04. \u2014 \u0e2b\u0e49\u0e32\u0e21\u0e42\u0e1e\u0e2a\u0e15\u0e4c"), "FAIL")
check("ISO date as a channel deadline",
      run_dates("instagram paused until 2026-08-25"), "FAIL")
check("Thai date + Thai channel word",
      run_dates("\u0e1e\u0e31\u0e19\u0e17\u0e34\u0e1b \u0e40\u0e1b\u0e34\u0e14\u0e2d\u0e35\u0e01\u0e04\u0e23\u0e31\u0e49\u0e07 14 \u0e2a.\u0e04. 2026"), "FAIL")

# --- must stay quiet: history, filenames, unrelated words ---
check("recording WHEN something died is history, not a deadline",
      run_dates("Meta MCP get_instagram_posts \u2014 token \u0e22\u0e01\u0e40\u0e25\u0e34\u0e01\u0e16\u0e32\u0e27\u0e23 18 \u0e01.\u0e04. 2026"), "PASS")
check("a date inside a FILENAME is a reference",
      run_dates("threads: \u0e2d\u0e48\u0e32\u0e19 HANDOFF_2026-08-01.md \u0e08\u0e19\u0e16\u0e36\u0e07\u0e17\u0e49\u0e32\u0e22"), "PASS")
check("deadline without any channel name is not ours to police",
      run_dates("\u0e2a\u0e48\u0e07\u0e23\u0e32\u0e22\u0e07\u0e32\u0e19\u0e16\u0e36\u0e07 2026-08-14"), "PASS")
check("pointing at policy.json is the correct form",
      run_dates("pantip: \u0e2d\u0e48\u0e32\u0e19\u0e2a\u0e16\u0e32\u0e19\u0e30\u0e08\u0e32\u0e01 policy.json \u2192 channels.pantip"), "PASS")
check("'ig' inside a longer word is not the channel",
      run_dates("ignore rows until 2026-08-25"), "PASS")

# --- ownership split, same rule as dead tooling ---
check("same drift in someone else's prompt only warns",
      run_dates("Pantip FROZEN \u0e16\u0e36\u0e07 16 \u0e01.\u0e04.", owned=False), "WARN")

shutil.rmtree(os.path.join(HERE, "_test_dates.tmp"), ignore_errors=True)
shutil.rmtree(os.path.join(HERE, "_test_dates_empty.tmp"), ignore_errors=True)
P.OWN_TASKS_DIR = _od3
P.SCHEDULED_DIR = _sd3

print("\nSALES RECORDED  (clicks without a single recorded sale must not stay silent)")
_sl, _repo = P.SALES_LOG, P.REPO


def run_sales(sales_lines, ga4_csv=None):
    d = os.path.join(TMPDIR, "_test_sales")
    al = os.path.join(d, "automation-log")
    if not os.path.isdir(al):
        os.makedirs(al)
    sp = os.path.join(al, "sales-log.jsonl")
    if sales_lines is None:
        if os.path.exists(sp):
            os.remove(sp)
    else:
        with io.open(sp, "w", encoding="utf-8", newline=chr(10)) as fh:
            fh.write(chr(10).join(sales_lines) + chr(10))
    gp = os.path.join(al, "ga4-metrics.csv")
    if ga4_csv is None:
        if os.path.exists(gp):
            os.remove(gp)
    else:
        with io.open(gp, "w", encoding="utf-8", newline=chr(10)) as fh:
            fh.write(ga4_csv)
    P.SALES_LOG = sp
    P.REPO = d
    P.results[:] = []
    P.check_sales_recorded()
    return P.results[0]["status"]


_HEADER = '{"note":"metadata header","created":"2026-07-24"}'
_SALE = '{"date":"2026-08-01","product":"letter-kit-199","amount_thb":199,"source":"line"}'
_GA4_CLICKS = "source,sessions,quiz_start,affiliate_click" + chr(10) + "pantip,18,2,5" + chr(10)
_GA4_ZERO = "source,sessions,quiz_start,affiliate_click" + chr(10) + "direct,166,0,0" + chr(10)
_GA4_OLDHEAD = "source,sessions,quiz_start,conversion" + chr(10) + "pantip,18,2,5" + chr(10)

check("clicks but not one sale recorded", run_sales([_HEADER], _GA4_CLICKS), "WARN")
check("a real sale on record", run_sales([_HEADER, _SALE], _GA4_CLICKS), "PASS")
check("no clicks and no sales is consistent", run_sales([_HEADER], _GA4_ZERO), "PASS")
check("no sales log at all", run_sales(None, _GA4_CLICKS), "WARN")
check("empty log and no GA4 to compare", run_sales([_HEADER], None), "WARN")
check("metadata header alone is not a sale", run_sales([_HEADER], _GA4_CLICKS), "WARN")
check("old CSV header (conversion) is still read", run_sales([_HEADER], _GA4_OLDHEAD), "WARN")

shutil.rmtree(os.path.join(TMPDIR, "_test_sales"), ignore_errors=True)
P.SALES_LOG, P.REPO = _sl, _repo

print("\nSYNTHETIC TRAFFIC  (our own robots must not be counted as an audience)")
_gm = P.GA4_METRICS
_syn_dir = tempfile.mkdtemp(prefix="pf_syn_")   # fixture อยู่นอก repo (ของเดิมเคยค้างใน tools/)


def run_syn(csv_text):
    p = os.path.join(_syn_dir, "ga4-metrics.csv")
    if csv_text is None:
        if os.path.exists(p):
            os.remove(p)
        P.GA4_METRICS = os.path.join(_syn_dir, "missing.csv")
    else:
        with io.open(p, "w", encoding="utf-8", newline=chr(10)) as fh:
            fh.write(csv_text)
        P.GA4_METRICS = p
    P.results[:] = []
    P.check_synthetic_traffic()
    return P.results[0]["status"]


_H = "source,sessions,quiz_start,affiliate_click" + chr(10)
# ของจริง 1 ส.ค. 2026: direct 166/209 = 79% และ quiz_start 0
_REAL = _H + "direct,166,0,2" + chr(10) + "pantip,18,2,5" + chr(10) + "fb,13,0,0" + chr(10) + "chatgpt,8,0,2" + chr(10) + "yt,3,0,0" + chr(10) + "bing,1,0,0" + chr(10)
_DIRECT_ENGAGED = _H + "direct,166,4,2" + chr(10) + "pantip,18,2,5" + chr(10)
_BALANCED = _H + "direct,40,0,1" + chr(10) + "pantip,120,6,5" + chr(10)
_EMPTY = _H

check("direct ท่วมและไม่มี engagement เลย", run_syn(_REAL), "WARN")
check("direct ท่วมแต่มี engagement = คนจริง", run_syn(_DIRECT_ENGAGED), "PASS")
check("direct ไม่ท่วม", run_syn(_BALANCED), "PASS")
check("ยังไม่มี sessions", run_syn(_EMPTY), "PASS")
check("ไม่มีไฟล์ ga4-metrics.csv", run_syn(None), "WARN")

shutil.rmtree(_syn_dir, ignore_errors=True)
P.GA4_METRICS = _gm

print("\nOPEN DECISIONS  (an expired plan gate must stay visible on every run)")
_real_policy = P.POLICY


def run_gates(gates):
    importlib.reload(P)
    with io.open(os.path.join(HERE, "_test_policy.tmp.json"), "w",
                 encoding="utf-8", newline="\n") as fh:
        base = json.load(io.open(_real_policy, encoding="utf-8"))
        base["gates"] = gates
        fh.write(json.dumps(base, ensure_ascii=False))
    P.POLICY = os.path.join(HERE, "_test_policy.tmp.json")
    P.results[:] = []
    P.check_open_decisions()
    return P.results[0]["status"]


_t = datetime.date.today()
_fut = lambda n: (_t + datetime.timedelta(days=n)).isoformat()
_past = lambda n: (_t - datetime.timedelta(days=n)).isoformat()
check("far-future gate only", run_gates([{"date": _fut(30), "task": "far"}]), "PASS")
check("gate due in 2 days", run_gates([{"date": _fut(2), "task": "soon"}]), "WARN")
check("gate overdue and not closed", run_gates([{"date": _past(5), "task": "x"}]), "WARN")
check("gate overdue but marked DONE",
      run_gates([{"date": _past(5), "task": "x", "status": "DONE"}]), "PASS")
check("gate overdue but marked SUPERSEDED is also closed",
      run_gates([{"date": _past(5), "task": "x", "status": "SUPERSEDED"}]), "PASS")
check("gate overdue with an unknown status is still open",
      run_gates([{"date": _past(5), "task": "x", "status": "MAYBE"}]), "WARN")
check("no gates declared", run_gates([]), "PASS")
try:
    os.remove(os.path.join(HERE, "_test_policy.tmp.json"))
except OSError:
    pass
P.POLICY = _real_policy

print("\nCONTENT CLIFF  (a gate must not land after the queue it refills runs out)")
_MAN = P.MANIFEST


def run_cliff(last_queue_date, gates):
    importlib.reload(P)
    mp = os.path.join(HERE, "_test_manifest.tmp.json")
    with io.open(mp, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(json.dumps({"items": [{"date": last_queue_date, "id": "x"}]},
                            ensure_ascii=False))
    pp = os.path.join(HERE, "_test_policy.tmp.json")
    with io.open(pp, "w", encoding="utf-8", newline="\n") as fh:
        base = json.load(io.open(_MAN.replace("content_manifest.json", "policy.json"),
                                 encoding="utf-8"))
        base["gates"] = gates
        fh.write(json.dumps(base, ensure_ascii=False))
    P.MANIFEST, P.POLICY = mp, pp
    P.results[:] = []
    P.check_content_cliff()
    return P.results[0]["status"]


_g = lambda d: [{"date": d, "task": "batch4-gate", "decides": ["batch4 production volume"]}]
check("gate lands AFTER the queue ends", run_cliff("2026-08-05", _g("2026-08-06")), "WARN")
check("gate lands ON the last queued day", run_cliff("2026-08-05", _g("2026-08-05")), "WARN")
check("gate lands well BEFORE the queue ends", run_cliff("2026-08-05", _g("2026-08-01")), "PASS")
# the real 31 Jul shape: a late gate is fine IF an earlier content gate can refill first
check("a bridge gate before the queue end covers a later one",
      run_cliff("2026-08-05", [{"date": "2026-08-03", "task": "bridge-clips",
                                "decides": ["produce bridge clips"]}] + _g("2026-08-06")), "PASS")
check("gate that decides something else entirely",
      run_cliff("2026-08-05", [{"date": "2026-08-09", "task": "owner review",
                                "decides": ["instagram return"]}]), "PASS")
check("a content gate already marked DONE",
      run_cliff("2026-08-05", [{"date": "2026-08-09", "task": "batch4-gate",
                                "decides": ["batch4 production"], "status": "DONE"}]), "PASS")
for _f in ("_test_manifest.tmp.json", "_test_policy.tmp.json"):
    try:
        os.remove(os.path.join(HERE, _f))
    except OSError:
        pass
importlib.reload(P)

print("\nMANIFEST VOCABULARY  (post_guard must understand what the uploader writes)")
def status(v):
    r = G.manifest_posted_status({"posted": {"youtube": v}}, "YOUTUBE", "youtube")
    return (r or {}).get("status") if isinstance(r, dict) else None
check("'published (...)' - what yt_upload writes past its slot", status("published (yt-api X)"), "POSTED")
check("'scheduled (...)'", status("scheduled (yt-api X)"), "SCHEDULED-UI")
check("'posted (...)'", status("posted (fb reel)"), "POSTED")
check("empty string is not a claim", status(""), None)
check("unknown word is not a claim", status("queued"), None)
check("'scheduled ... published' stays scheduled",
      status("scheduled, will be published 19:00"), "SCHEDULED-UI")

print("\nDELIVERY GAP  (the check that would have caught the 4-day blackout)")
_fresh_tmp()
_led = lambda days: write("led.jsonl", "\n".join(json.dumps(
    {"type": "text", "channel": "facebook", "text_first80": "x",
     "ts": "%sT09:00:00+07:00" % (datetime.date.today() - datetime.timedelta(days=days)).isoformat()})
    for _ in [0]))
check("posted today", run_check("check_delivery_gap", LEDGER=_led(0)), "PASS")
check("silent %d days" % P.DELIVERY_WARN_DAYS,
      run_check("check_delivery_gap", LEDGER=_led(P.DELIVERY_WARN_DAYS)), "WARN")
check("silent %d days" % P.DELIVERY_FAIL_DAYS,
      run_check("check_delivery_gap", LEDGER=_led(P.DELIVERY_FAIL_DAYS)), "FAIL")
check("ledger with no content rows at all",
      run_check("check_delivery_gap", LEDGER=write("empty.jsonl", "")), "FAIL")
check("ledger file missing entirely",
      run_check("check_delivery_gap", LEDGER=os.path.join(TMPDIR, "nope.jsonl")), "FAIL")

print("\nCAPTIONS  (must reject what the posting policy forbids, and only that)")
_cap = lambda txt, ch="threads": write("man.json", {"items": [{"id": "x", "captions": {ch: txt}}]})
check("clean caption", run_check("check_captions", MANIFEST=_cap("\u0e02\u0e49\u0e2d\u0e21\u0e39\u0e25")), "PASS")
check("literal backslash-n token", run_check("check_captions", MANIFEST=_cap("a\\nb")), "FAIL")
check("banned word 'guarantee'",
      run_check("check_captions", MANIFEST=_cap("\u0e01\u0e32\u0e23\u0e31\u0e19\u0e15\u0e35 100")), "FAIL")
check("a percentage figure", run_check("check_captions", MANIFEST=_cap("\u0e14\u0e2d\u0e01 5%")), "FAIL")
check("url on a non-youtube channel",
      run_check("check_captions", MANIFEST=_cap("see https://x.com")), "FAIL")
check("url IS allowed on youtube",
      run_check("check_captions", MANIFEST=_cap("see https://x.com", "youtube")), "PASS")
check("empty manifest is a failure, not a pass",
      run_check("check_captions", MANIFEST=write("m0.json", {"items": []})), "FAIL")

print("\nPOSTED TRUTH  (a 'posted' record must not outrun the evidence)")
_pt = lambda vid, logged: (write("m.json", {"items": [{"id": "x", "date": "2026-08-01",
                                                       "posted": {"youtube": "published (yt-api %s)" % vid}}]}),
                           write("y.json", {"2026-08-01": logged}))
_m, _y = _pt("ABC123", "ABC123")
check("manifest agrees with upload log", run_check("check_posted_truth", MANIFEST=_m, YTLOG=_y), "PASS")
_m, _y = _pt("ABC123", "ZZZ999")
check("manifest claims a different videoId", run_check("check_posted_truth", MANIFEST=_m, YTLOG=_y), "FAIL")
_m, _y = _pt("ABC123", None)
check("upload log has no row for that date", run_check("check_posted_truth", MANIFEST=_m, YTLOG=_y), "FAIL")
check("no youtube claim at all = nothing to contradict",
      run_check("check_posted_truth",
                MANIFEST=write("m2.json", {"items": [{"id": "x", "date": "2026-08-01"}]}),
                YTLOG=write("y2.json", {})), "PASS")

print("\nCOMPETING PLAN  (only the manifest may decide what gets posted)")
_today = datetime.date.today().isoformat()
check("no rival plan file",
      run_check("check_competing_plan", REPO=TMPDIR, MANIFEST=write("m3.json", {"items": []})), "PASS")
_al = os.path.join(TMPDIR, "automation-log")
os.makedirs(_al, exist_ok=True)
write("automation-log/post-plan.json", [{"day": _today, "file": "reels/2026-08-01_b3-02.mp4"}])
check("rival plan naming the same clip as the manifest",
      run_check("check_competing_plan", REPO=TMPDIR,
                MANIFEST=write("m4.json", {"items": [{"date": _today, "reel": "reels/2026-08-01_b3-02.mp4"}]})),
      "PASS")
write("automation-log/post-plan.json", [{"day": _today, "file": "C:\\\\repo\\\\reels\\\\x.mp4"}])
check("rival plan using a WINDOWS absolute path to reels",
      run_check("check_competing_plan", REPO=TMPDIR,
                MANIFEST=write("m4b.json", {"items": [{"date": _today, "reel": "reels/x.mp4"}]})), "PASS")
write("automation-log/post-plan.json", [{"day": _today, "file": "reels/2026-08-01_b3-02.mp4"}])
check("rival plan naming a DIFFERENT clip",
      run_check("check_competing_plan", REPO=TMPDIR,
                MANIFEST=write("m5.json", {"items": [{"date": _today, "reel": "reels/other.mp4"}]})), "FAIL")
write("automation-log/post-plan.json", [{"day": _today, "file": "media/clips-web/old.mp4"}])
check("rival plan naming a non-reels/ file (the 31 Jul legacy bug)",
      run_check("check_competing_plan", REPO=TMPDIR, MANIFEST=write("m6.json", {"items": []})), "FAIL")
write("automation-log/post-plan.json", "{not json")
check("rival plan that is unreadable",
      run_check("check_competing_plan", REPO=TMPDIR, MANIFEST=write("m7.json", {"items": []})), "WARN")

print("\nDISCLOSURE  (driven by real anchors - must survive the negation trap)")
AFF = '<a href="https://atth.me/x?utm_content=fb_home_scb">go</a>'
HAS = u"\u0e21\u0e35\u0e25\u0e34\u0e07\u0e01\u0e4c\u0e1e\u0e31\u0e19\u0e18\u0e21\u0e34\u0e15\u0e23"
BOX = u"* " + HAS + u" \u2014 \u0e40\u0e23\u0e32\u0e2d\u0e32\u0e08\u0e44\u0e14\u0e49\u0e23\u0e31\u0e1a"


def site_with(html):
    d = os.path.join(TMPDIR, "site_%d" % abs(hash(html)))
    os.makedirs(d, exist_ok=True)
    with io.open(os.path.join(d, "p.html"), "w", encoding="utf-8", newline="\n") as fh:
        fh.write(html)
    return d


check("affiliate links WITH the disclosure box",
      run_check("check_disclosure", SITE=site_with(AFF + BOX)), "PASS")
check("affiliate links with NO disclosure box",
      run_check("check_disclosure", SITE=site_with(AFF)), "FAIL")
check("affiliate links on a page claiming it has none",
      run_check("check_disclosure", SITE=site_with(AFF + BOX + u"\u0e44\u0e21\u0e48" + HAS)), "FAIL")
check("page with NO affiliate links and no box is fine",
      run_check("check_disclosure", SITE=site_with("<p>hello</p>")), "PASS")
check("over-disclosing (box, no links) is not a violation",
      run_check("check_disclosure", SITE=site_with(BOX)), "PASS")
check("site/ not built is a WARN, never a silent PASS",
      run_check("check_disclosure", SITE=os.path.join(TMPDIR, "no-site")), "WARN")

print("\nATTRIBUTION  (every affiliate button needs a channel_page_provider sub id)")
check("well-formed sub id", run_check("check_attribution", SITE=site_with(AFF)), "PASS")
check("sub id with too few parts",
      run_check("check_attribution",
                SITE=site_with('<a href="https://atth.me/x?utm_content=fb_home">go</a>')), "FAIL")
check("no utm_content at all",
      run_check("check_attribution", SITE=site_with('<a href="https://atth.me/x">go</a>')), "FAIL")
check("site/ not built is a WARN",
      run_check("check_attribution", SITE=os.path.join(TMPDIR, "no-site2")), "WARN")

print("\nQUEUED CLIP SPEC  (checks on the way IN, not on the way out)")
check("policy.json missing -> WARN, not a silent pass",
      run_check("check_queued_clip_spec", REPO=os.path.join(TMPDIR, "no-repo")), "WARN")
check("nothing queued from today onward -> WARN",
      run_check("check_queued_clip_spec", REPO=REPO_REAL,
                SCHEDULE=write("s0.json", {"2020-01-01": {"file": "old.mp4"}})), "WARN")
check("queued clip missing on disk -> FAIL",
      run_check("check_queued_clip_spec", REPO=REPO_REAL,
                SCHEDULE=write("s1.json", {_today: {"file": "definitely-not-here.mp4"}})),
      "FAIL" if __import__("shutil").which("ffprobe") else "FAIL")

print("\nSTUCK RUNS  (evidence written before the risky step, then actually read)")


def runlog_dir(rows, name="2026-08.jsonl"):
    """Build a fake automation-log holding one month file."""
    d = os.path.join(TMPDIR, "runlogs_%d" % abs(hash(str(rows))))
    os.makedirs(d, exist_ok=True)
    for f in os.listdir(d):
        os.unlink(os.path.join(d, f))
    with io.open(os.path.join(d, name), "w", encoding="utf-8", newline="\n") as fh:
        for r in rows:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")
    return d


def _run(routine, status, hours_ago):
    ts = (datetime.datetime.now() - datetime.timedelta(hours=hours_ago)).isoformat(timespec="seconds")
    return {"ts": ts, "routine": routine, "status": status, "summary": "x", "metrics": {}}


check("a finished run is not stuck",
      run_check("check_stuck_runs", RUNLOG_DIR=runlog_dir([_run("a", "ok", 30)])), "PASS")
check("started 30h ago and never finished",
      run_check("check_stuck_runs", RUNLOG_DIR=runlog_dir([_run("a", "started", 30)])), "WARN")
# The whole point of writing `started` first is that the finishing row overwrites it.
check("started THEN ok is a completed run, not a stuck one",
      run_check("check_stuck_runs",
                RUNLOG_DIR=runlog_dir([_run("a", "started", 30), _run("a", "ok", 29)])), "PASS")
check("started THEN fail is also finished (it reported)",
      run_check("check_stuck_runs",
                RUNLOG_DIR=runlog_dir([_run("a", "started", 30), _run("a", "fail", 29)])), "PASS")
# A round that is genuinely mid-flight must not be called stuck - this check runs at
# 08:00, the same hour several tasks fire.
check("started 1h ago is mid-flight, not stuck",
      run_check("check_stuck_runs", RUNLOG_DIR=runlog_dir([_run("a", "started", 1)])), "PASS")
check("one stuck routine among healthy ones still fires",
      run_check("check_stuck_runs",
                RUNLOG_DIR=runlog_dir([_run("a", "ok", 2), _run("b", "started", 40),
                                       _run("c", "ok", 1)])), "WARN")
check("the stuck routine is NAMED, not just counted",
      "b" in run_check_detail("check_stuck_runs",
                RUNLOG_DIR=runlog_dir([_run("a", "ok", 2), _run("b", "started", 40)])),
      True)
check("an unreadable timestamp is surfaced, never skipped",
      run_check("check_stuck_runs",
                RUNLOG_DIR=runlog_dir([{"ts": "not-a-date", "routine": "a", "status": "started"}])),
      "WARN")
check("no runlog at all is a WARN, never a silent PASS",
      run_check("check_stuck_runs", RUNLOG_DIR=os.path.join(TMPDIR, "no-runlogs")), "WARN")
# post-ledger.jsonl lives in the same directory and has no `routine` key. Reading it
# as a runlog would be the same class of bug as the 27-30 Jul manifest/schedule mixup.
check("rows without a routine key are ignored, not crashed on",
      run_check("check_stuck_runs",
                RUNLOG_DIR=runlog_dir([{"type": "video", "channel": "threads", "ts": "2026-08-01"},
                                       _run("a", "ok", 2)])), "PASS")

print("\nDELEGATED CHECKS  (queue + build gate shell out - prove the mapping)")


def fake_tool(name, code, out):
    d = _sub = os.path.join(TMPDIR, "bin"); os.makedirs(d, exist_ok=True)
    with io.open(os.path.join(d, name), "w", encoding="utf-8", newline="\n") as fh:
        fh.write("import sys\nprint(%r)\nsys.exit(%d)\n" % (out, code))
    return d


check("runway_guard says OK",
      run_check("check_queue", HERE=fake_tool("runway_guard.py", 0, '{"verdict":"OK","effective_runway_days":9}')),
      "PASS")
check("runway_guard says LOW_RUNWAY",
      run_check("check_queue", HERE=fake_tool("runway_guard.py", 0, '{"verdict":"LOW_RUNWAY","effective_runway_days":1}')),
      "WARN")
check("runway_guard says PARKED (approved pause is not a fault)",
      run_check("check_queue", HERE=fake_tool("runway_guard.py", 0,
                '{"verdict":"PARKED","effective_runway_days":0,'
                '"park":{"until":"2026-08-10","decided_by":"GATE"}}')),
      "PASS")
check("PARKED still prints WHY, never an empty pass",
      "2026-08-10" in run_check_detail("check_queue", HERE=fake_tool("runway_guard.py", 0,
                '{"verdict":"PARKED","effective_runway_days":0,'
                '"park":{"until":"2026-08-10","decided_by":"GATE"}}')),
      True)
check("runway_guard says PARK_OVERRUN (the pause expired)",
      run_check("check_queue", HERE=fake_tool("runway_guard.py", 1,
                '{"verdict":"PARK_OVERRUN","effective_runway_days":0,'
                '"problems":["park ended 2026-08-10"]}')),
      "FAIL")
check("runway_guard says DRIFT",
      run_check("check_queue", HERE=fake_tool("runway_guard.py", 2,
                '{"verdict":"DRIFT","problems":["schedule missing a day"]}')),
      "FAIL")
# The 7 Aug 2026 bug: PARKED was added to runway_guard and this consumer mapped
# every unknown verdict to a FAIL with an EMPTY message. A blank FAIL tells the
# next reader nothing, so the unknown branch must now name the verdict it saw.
check("an unknown verdict fails LOUDLY and names itself",
      run_check("check_queue", HERE=fake_tool("runway_guard.py", 2, '{"verdict":"BROKEN","problems":["x"]}')),
      "FAIL")
check("...and the message actually contains the unknown verdict",
      "BROKEN" in run_check_detail("check_queue",
                   HERE=fake_tool("runway_guard.py", 2, '{"verdict":"BROKEN","problems":["x"]}')),
      True)
check("runway_guard cannot run at all",
      run_check("check_queue", HERE=os.path.join(TMPDIR, "no-bin")), "FAIL")
check("smoke test passes", run_check("check_build_gate", HERE=fake_tool("postdeploy_smoke.py", 0, "ok")), "PASS")
check("smoke test fails", run_check("check_build_gate", HERE=fake_tool("postdeploy_smoke.py", 1, "boom")), "FAIL")

print("\nTWO TASK ROOTS  (the guard must read the file the scheduler runs, not the mirror)")


def two_roots(cc_files, cowork_files):
    """Build a fake pair of task roots and return (OWN_TASKS_DIR, SCHEDULED_DIR)."""
    base = os.path.join(TMPDIR, "roots_%d" % abs(hash(str(cc_files) + str(cowork_files))))
    a, b = os.path.join(base, "cc"), os.path.join(base, "cowork")
    for root, files in ((a, cc_files), (b, cowork_files)):
        for name, body in files.items():
            d = os.path.join(root, name)
            os.makedirs(d, exist_ok=True)
            with io.open(os.path.join(d, "SKILL.md"), "w", encoding="utf-8", newline="\n") as fh:
                fh.write(body)
        if not os.path.isdir(root):
            os.makedirs(root)
    return a, b


ORDER = "run Postiz to refill the queue"
BAN = u"\u0e2b\u0e49\u0e32\u0e21\u0e43\u0e0a\u0e49 Postiz"          # "do not use Postiz"

# The exact 1 Aug shape: the CC file is dirty, the mirror is clean. Reading the mirror
# (what the first version did) reports everything fine.
_a, _b = two_roots({"t": ORDER}, {"t": BAN})
check("dirty cc file, clean mirror -> must FAIL",
      run_check("check_dead_tooling", OWN_TASKS_DIR=_a, SCHEDULED_DIR=_b), "FAIL")
_a, _b = two_roots({"t": BAN}, {"t": ORDER})
check("clean cc file, dirty mirror -> WARN (not ours to fix)",
      run_check("check_dead_tooling", OWN_TASKS_DIR=_a, SCHEDULED_DIR=_b), "WARN")
_a, _b = two_roots({"t": BAN}, {"t": BAN})
check("both roots merely forbid the dead tool -> PASS",
      run_check("check_dead_tooling", OWN_TASKS_DIR=_a, SCHEDULED_DIR=_b), "PASS")
# clicktest lives only in the cc root and was never scanned before
_a, _b = two_roots({"cc-only": ORDER}, {})
check("a cc-only task is scanned too (clicktest was not)",
      run_check("check_dead_tooling", OWN_TASKS_DIR=_a, SCHEDULED_DIR=_b), "FAIL")

# A retired task naming a dead tool is history, not an order. Nine permanently-closed
# Cowork prompts sat in this warning line, which is how a warning stops being read.
_RET = '---\nname: t\ndescription: [ปิด 19 มิ.ย. 2026] Postiz เลิกใช้\n---\nrun Postiz to refill the queue\n'
_LIVE = '---\nname: t\ndescription: daily queue refill\n---\nrun Postiz to refill the queue\n'
_a, _b = two_roots({}, {"t": _RET})
check("retired task naming a dead tool is history, not drift",
      run_check("check_dead_tooling", OWN_TASKS_DIR=_a, SCHEDULED_DIR=_b), "PASS")
_a, _b = two_roots({}, {"t": _LIVE})
check("a LIVE task with the same body still warns",
      run_check("check_dead_tooling", OWN_TASKS_DIR=_a, SCHEDULED_DIR=_b), "WARN")
_a, _b = two_roots({"t": _RET}, {})
check("retired cc task does not FAIL the gate either",
      run_check("check_dead_tooling", OWN_TASKS_DIR=_a, SCHEDULED_DIR=_b), "PASS")

print("\nTASK MIRROR  (one id must not mean two different sets of orders)")
_a, _b = two_roots({"t": "same"}, {"t": "same"})
check("identical in both roots", run_check("check_task_mirror", OWN_TASKS_DIR=_a, SCHEDULED_DIR=_b), "PASS")
_a, _b = two_roots({"t": "orders A"}, {"t": "orders B"})
check("same id, different orders", run_check("check_task_mirror", OWN_TASKS_DIR=_a, SCHEDULED_DIR=_b), "WARN")
_a, _b = two_roots({"only-cc": "x"}, {"other": "y"})
check("cc task absent from the mirror", run_check("check_task_mirror", OWN_TASKS_DIR=_a, SCHEDULED_DIR=_b), "WARN")
check("a root that does not exist is a WARN, never a silent PASS",
      run_check("check_task_mirror", OWN_TASKS_DIR=os.path.join(TMPDIR, "nope"),
                SCHEDULED_DIR=os.path.join(TMPDIR, "nope2")), "WARN")

# RESOLVED COLLISIONS (7 Aug 2026). `ngernduangold-weekly-review` is one id that once
# meant two unrelated jobs; the CC side was replaced by a tombstone on purpose. The two
# files MUST differ, so warning about it forever is noise that teaches the reader to
# skim past this check. But the loophole must stay shut: two LIVE prompts that differ is
# still the dangerous case, and a tombstone must not be able to hide it.
_TOMB = '---\nname: t\ndescription: [ปิด 1 ส.ค. 2026 - ย้ายชื่อ] moved to another id\n---\nreport and stop\n'
_LIVE = '---\nname: t\ndescription: the real weekly review\n---\ndo the actual work\n'
_a, _b = two_roots({"t": _TOMB}, {"t": _LIVE})
check("one side is a tombstone -> resolved collision, not drift",
      run_check("check_task_mirror", OWN_TASKS_DIR=_a, SCHEDULED_DIR=_b), "PASS")
check("...but it must still be SAID, never silently swallowed",
      "retired on one side" in run_check_detail("check_task_mirror", OWN_TASKS_DIR=_a, SCHEDULED_DIR=_b),
      True)
_a, _b = two_roots({"t": _LIVE}, {"t": _TOMB})
check("the tombstone may be on either side", 
      run_check("check_task_mirror", OWN_TASKS_DIR=_a, SCHEDULED_DIR=_b), "PASS")
_a, _b = two_roots({"t": _LIVE}, {"t": _LIVE.replace("actual", "completely different")})
check("two LIVE prompts that differ is still drift",
      run_check("check_task_mirror", OWN_TASKS_DIR=_a, SCHEDULED_DIR=_b), "WARN")
_a, _b = two_roots({"t": _TOMB}, {"t": _TOMB.replace("another", "a third")})
check("two tombstones that differ still warns (only ONE side may be retired)",
      run_check("check_task_mirror", OWN_TASKS_DIR=_a, SCHEDULED_DIR=_b), "WARN")
_a, _b = two_roots({"t": _TOMB, "u": _LIVE}, {"t": _LIVE, "u": _LIVE.replace("actual", "other")})
check("a resolved collision does not mask a real one alongside it",
      run_check("check_task_mirror", OWN_TASKS_DIR=_a, SCHEDULED_DIR=_b), "WARN")

print("\nPOLICY DATES noise filters  (six times today a guard flagged the lesson about itself)")
_a, _b = two_roots({}, {"t": '---\nname: t\ndescription: [⛔ PAUSED 2 ก.ค. 2026] retired\n---\nPantip FROZEN ถึง 16 ก.ค. — พัก\n'})
check('retired task with a decorated marker [⛔ PAUSED ...]',
      run_check("check_policy_dates_in_prompts", OWN_TASKS_DIR=_a, SCHEDULED_DIR=_b), 'PASS')
_a, _b = two_roots({}, {"t": '---\nname: t\ndescription: live\n---\n**ห้ามเขียนวันซ้ำ** — ของเดิมมี "Pantip พักถึง 16 ก.ค."\n'})
check('quoting the stale line in order to ban it',
      run_check("check_policy_dates_in_prompts", OWN_TASKS_DIR=_a, SCHEDULED_DIR=_b), 'PASS')
_a, _b = two_roots({}, {"t": '---\nname: t\ndescription: live\n---\nอ่านคลัง: ถึง 1 ส.ค. ใช้ไฟล์ A → ได้ threads_text\n'})
check('a content-library rotation is a schedule, not channel policy',
      run_check("check_policy_dates_in_prompts", OWN_TASKS_DIR=_a, SCHEDULED_DIR=_b), 'PASS')
_a, _b = two_roots({}, {"t": '---\nname: t\ndescription: live\n---\ninstagram พักถึง 25 ส.ค.\n'})
check('a real channel pause deadline still fires',
      run_check("check_policy_dates_in_prompts", OWN_TASKS_DIR=_a, SCHEDULED_DIR=_b), 'WARN')

print("\nPOLICY DATES follow-ups  (retired tasks + field names)")
# --- two gaps found 1 Aug 2026 when the check listed 20 names and 13 were closed tasks ---
_RET_P = '---\nname: t\ndescription: [ปิด 19 มิ.ย. 2026] retired\n---\ninstagram พักถึง 25 ส.ค.\n'
_FLD_P = '---\nname: t\ndescription: live\n---\nอ่าน phase_until จาก policy.json แทน (pantip) 30 ก.ค.\n'
_a, _b = two_roots({}, {"t": _RET_P})
check("retired task quoting an expired window is history, not drift",
      run_check("check_policy_dates_in_prompts", OWN_TASKS_DIR=_a, SCHEDULED_DIR=_b), "PASS")
_a, _b = two_roots({}, {"t": _FLD_P})
check("'phase_until' is a FIELD NAME, not the deadline word 'until'",
      run_check("check_policy_dates_in_prompts", OWN_TASKS_DIR=_a, SCHEDULED_DIR=_b), "PASS")

print("\nGA4 INTERNAL IP  (the rule that existed, was Active, and matched nothing)")
# 1 Aug 2026: GA4 had an internal-traffic rule pinned to 184.22.17.215 and an ACTIVE
# Exclude filter, while the machine had been rotated to 27.130.5.93 by the ISP. Every
# visible signal said "protected". Nothing on disk recorded the real egress IP, so
# nothing could contradict it. These cases exist so the next rotation is loud.


def ga4_env(pinned, host_ip, days_ago=0, state="Active", drop_block=False, no_host=False):
    """Build a policy + host_ip fixture pair and return them as constant overrides."""
    ga4 = {} if drop_block else {"internal_traffic": {"filter_state": state, "ips": pinned}}
    pol = write("pol_%s.json" % abs(hash((str(pinned), host_ip, days_ago, state,
                                          drop_block, no_host))),
                {"ga4": ga4})
    if no_host:
        return {"POLICY": pol, "HOST_IP_FILE": os.path.join(TMPDIR, "no_such_host_ip.json")}
    seen = (datetime.datetime.now() - datetime.timedelta(days=days_ago)).strftime(
        "%Y-%m-%dT%H:%M:%S")
    hip = write("hip_%s.json" % abs(hash((host_ip, days_ago))),
                {"ip": host_ip, "checked_at": seen})
    return {"POLICY": pol, "HOST_IP_FILE": hip}


check("egress ip is inside the pinned CIDR",
      run_check("check_ga4_internal_ip", **ga4_env(["27.130.5.93/32"], "27.130.5.93")), "PASS")
check("THE REAL 1 Aug CASE: pinned 184.22.17.215, box is on 27.130.5.93",
      run_check("check_ga4_internal_ip", **ga4_env(["184.22.17.215/32"], "27.130.5.93")), "WARN")
check("both old and new pinned -> still covered",
      run_check("check_ga4_internal_ip",
                **ga4_env(["184.22.17.215/32", "27.130.5.93/32"], "27.130.5.93")), "PASS")
check("real CIDR math, not string compare (/24 contains .93)",
      run_check("check_ga4_internal_ip", **ga4_env(["27.130.5.0/24"], "27.130.5.93")), "PASS")
check("neighbouring /24 does NOT contain it",
      run_check("check_ga4_internal_ip", **ga4_env(["27.130.6.0/24"], "27.130.5.93")), "WARN")
check("Data Filter left in Testing = configured but not excluding",
      run_check("check_ga4_internal_ip",
                **ga4_env(["27.130.5.93/32"], "27.130.5.93", state="Testing")), "WARN")
check("no ga4.internal_traffic block at all",
      run_check("check_ga4_internal_ip",
                **ga4_env(["27.130.5.93/32"], "27.130.5.93", drop_block=True)), "WARN")
check("ips list empty = not protected, must not read as PASS",
      run_check("check_ga4_internal_ip", **ga4_env([], "27.130.5.93")), "WARN")
check("unparseable CIDR in policy is surfaced, not skipped",
      run_check("check_ga4_internal_ip", **ga4_env(["27.130.5.93/nope"], "27.130.5.93")), "WARN")
check("host_ip.json missing = blind, and blind must never print PASS",
      run_check("check_ga4_internal_ip",
                **ga4_env(["27.130.5.93/32"], "27.130.5.93", no_host=True)), "WARN")
check("host_ip.json 30 days old = uptime_check stopped running",
      run_check("check_ga4_internal_ip",
                **ga4_env(["27.130.5.93/32"], "27.130.5.93", days_ago=30)), "WARN")
check("6 days old is still inside the freshness window",
      run_check("check_ga4_internal_ip",
                **ga4_env(["27.130.5.93/32"], "27.130.5.93", days_ago=6)), "PASS")
_p = write("pol_badip.json", {"ga4": {"internal_traffic":
                                      {"filter_state": "Active", "ips": ["27.130.5.93/32"]}}})
_h = write("hip_badip.json", {"ip": "not-an-ip", "checked_at":
                              datetime.datetime.now().strftime("%Y-%m-%dT%H:%M:%S")})
check("garbage recorded as the host ip is a WARN, not a crash",
      run_check("check_ga4_internal_ip", POLICY=_p, HOST_IP_FILE=_h), "WARN")
_h = write("hip_badts.json", {"ip": "27.130.5.93", "checked_at": "yesterday-ish"})
check("unreadable checked_at is a WARN, not an assumed-fresh PASS",
      run_check("check_ga4_internal_ip", POLICY=_p, HOST_IP_FILE=_h), "WARN")

print("\nMETA  (no check may exist without proof it can both fire and stay quiet)")
importlib.reload(P)
_all = sorted(n for n in dir(P) if n.startswith("check_") and callable(getattr(P, n)))
_src = io.open(os.path.join(HERE, "test_preflight_checks.py"), encoding="utf-8").read()
_uncovered = [n for n in _all if ('"%s"' % n) not in _src and ("P.%s(" % n) not in _src]
check("every check_* in preflight has a test here", _uncovered, [])

# Having a test is not the same as being RUN. check_task_mirror was written, tested and
# passing on 1 Aug 2026 while main() never called it -- so preflight printed fifteen lines
# and the sixteenth check simply did not exist at runtime. A guard nobody invokes looks
# exactly like a guard that always passes, which is the failure this whole file is about.
_pf = io.open(os.path.join(HERE, "preflight.py"), encoding="utf-8").read()
_main = _pf.split("def main(")[1] if "def main(" in _pf else ""
_unwired = [n for n in _all if ("%s()" % n) not in _main]
# check_build_gate is inside `if args.full:` but still appears in main's text, so it
# counts as wired -- the thing being asserted is "reachable from main", not "always run".
check("every check_* is actually called by main()", _unwired, [])
print("     %d check(s) in preflight, all exercised and wired" % len(_all))

import shutil
shutil.rmtree(TMPDIR, ignore_errors=True)

try:
    os.remove(TMP)
except OSError:
    pass

bad = results.count(False)
print("\n%d checks, %d failed" % (len(results), bad))
print("ALL PASS" if not bad else "*** FAILURES ABOVE ***")
sys.exit(1 if bad else 0)
