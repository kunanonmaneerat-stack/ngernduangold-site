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
check("runway_guard says anything else",
      run_check("check_queue", HERE=fake_tool("runway_guard.py", 2, '{"verdict":"BROKEN","problems":["x"]}')),
      "FAIL")
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
