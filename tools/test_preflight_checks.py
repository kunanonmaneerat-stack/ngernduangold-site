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
import copy, io, os, sys, json, datetime, importlib, hashlib, ipaddress, platform
from pathlib import Path

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
import import_accesstrade_csv as AT
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
    payload = copy.deepcopy(data)

    def materialize(item):
        if isinstance(item, dict):
            attestation = item.get("coverage_attestation")
            if isinstance(attestation, dict):
                observation = attestation.pop(
                    "_admin_observation_fixture", None
                )
                if observation is not None:
                    contract = attestation["admin_observation_contract"]
                    evidence_path = os.path.join(
                        os.path.dirname(path), contract["default"]
                    )
                    with io.open(
                        evidence_path, "wb"
                    ) as evidence_file:
                        evidence_file.write(_ga4_fixture_json_bytes(observation))
            for child in item.values():
                materialize(child)
        elif isinstance(item, list):
            for child in item:
                materialize(child)

    materialize(payload)
    with io.open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(json.dumps(payload, ensure_ascii=False) if isinstance(payload, (dict, list)) else payload)
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


def run_check_results(fn_name, **consts):
    """Return every result when one check intentionally reports separate concerns."""
    importlib.reload(P)
    for k, v in consts.items():
        setattr(P, k, v)
    P.results[:] = []
    getattr(P, fn_name)()
    return list(P.results)


def run_cap(rows):
    importlib.reload(P)
    with io.open(TMP, "w", encoding="utf-8", newline="\n") as fh:
        for r in rows:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")
    P.LEDGER = TMP
    P.results[:] = []
    P.check_posting_cap()
    return P.results[0]["status"]


def run_cap_raw(raw):
    importlib.reload(P)
    with io.open(TMP, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(raw)
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
check("malformed live timestamp cannot bypass gap",
      run_cap([live("09"), {"type": "text", "channel": "facebook",
                             "ts": TODAY + "T10:00:00+07:00junk"}]), "FAIL")
check("naive live timestamp is unclassifiable",
      run_cap([{"type": "text", "channel": "facebook",
                "ts": TODAY + "T10:00:00"}]), "FAIL")
check("duplicate ledger key is malformed",
      run_cap_raw('{"type":"comment","type":"text","channel":"facebook",'
                  '"ts":"%sT10:00:00+07:00"}\n' % TODAY), "FAIL")
check("non-finite ledger value is malformed",
      run_cap_raw('{"type":"comment","channel":"facebook","unused":NaN,'
                  '"ts":"%sT10:00:00+07:00"}\n' % TODAY), "FAIL")
check("overflowed JSON number is malformed",
      run_cap_raw('{"type":"comment","channel":"facebook","unused":1e999,'
                  '"ts":"%sT10:00:00+07:00"}\n' % TODAY), "FAIL")

print("\nPOLICY WIRING  (numbers must come from policy.json, and fail safe without it)")
importlib.reload(P)
check("cap default read from policy", P.POST_CAP_DEFAULT, 2)
check("pinterest override read from policy", P.POST_CAP_BY_CHANNEL.get("pinterest"), 5)
check("min gap read from policy", P.POST_MIN_GAP_HOURS, 3)
_saved, P.POLICY = P.POLICY, os.path.join(HERE, "no-such-policy.json")
_caps, _gap, _types = P._limits()
P.POLICY = _saved
check("missing policy still enforces the written rule", (_caps.get("default"), _gap), (2, 3))
_fallback = ({"default": 2, "pinterest": 5}, 3, {"text", "video", "image"})
for _label, _raw in (
    ("duplicate policy key", '{"limits":{"posts_per_day":{"default":2,"default":999},"min_gap_hours":3,"post_types":["text","video","image"]}}'),
    ("NaN policy gap", '{"limits":{"posts_per_day":{"default":2},"min_gap_hours":NaN,"post_types":["text","video","image"]}}'),
    ("overflowed policy number", '{"limits":{"posts_per_day":{"default":2},"min_gap_hours":1e999,"post_types":["text","video","image"]}}'),
    ("boolean policy cap", '{"limits":{"posts_per_day":{"default":true},"min_gap_hours":3,"post_types":["text","video","image"]}}'),
    ("policy omits a post type", '{"limits":{"posts_per_day":{"default":2},"min_gap_hours":3,"post_types":["text","video"]}}'),
):
    _fixture = write("limits-%s.json" % _label.replace(" ", "-"), _raw)
    P.POLICY = _fixture
    check(_label + " falls back closed", P._limits(), _fallback)
P.POLICY = _saved

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
check("malformed delivery cannot forge recovery",
      run_fail([fail("facebook", "09"),
                {"type": "text", "channel": "facebook",
                 "ts": TODAY + "T99:00:00+07:00"}])["status"], "FAIL")
check("malformed failure row cannot disappear",
      run_fail([{"type": "failure", "channel": "facebook",
                 "ts": TODAY + "-not-a-time"}])["status"], "FAIL")

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
check("completed one-shot task is historical, not live drift",
      run_drift("---\nname: old\ndescription: [DONE 2026-08-16] closed gate\n---\n"
                "instagram was paused until %s" % _wrong), "PASS")
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

print("\nSALES RECORDED  (only a complete schema-5 event export may define paid revenue)")
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


def reconciled_sales(status=None):
    bangkok = datetime.timezone(datetime.timedelta(hours=7))
    now = datetime.datetime.now(bangkok)
    today = now.date()
    event_time = now - datetime.timedelta(seconds=3)
    extracted_time = now - datetime.timedelta(seconds=2)
    reconciled_time = now - datetime.timedelta(seconds=1)
    fields = [
        "event_id", "sale_id", "date", "product", "status", "gross_amount_thb", "fee_thb",
        "net_amount_thb", "channel_source", "ref", "note", "ts",
    ]
    rows = []
    if status:
        amounts = {
            "paid": (100, 10, 90),
            "pending": (100, 10, 90),
            "approved": (100, 10, 90),
        }[status]
        rows.append({
            "event_id": "event-sale-1-" + status,
            "sale_id": "sale-1", "date": event_time.date().isoformat(),
            "product": "affiliate-commission", "status": status,
            "gross_amount_thb": amounts[0], "fee_thb": amounts[1],
            "net_amount_thb": amounts[2], "channel_source": "atth",
            "ref": "ref-1", "note": "fixture",
            "ts": event_time.isoformat(timespec="seconds"),
        })
    start = today - datetime.timedelta(days=27)
    meta = {
        "_meta": "reconciled affiliate export", "schema_version": 5,
        "fields": fields, "products": {"affiliate-commission": {}},
        "blocked_products": [], "channel_source_values": ["atth"],
        "created": start.isoformat(), "updated": today.isoformat(),
        "source_system": "fixture", "coverage_start": start.isoformat(),
        "coverage_end": today.isoformat(),
        "extracted_at": extracted_time.isoformat(timespec="seconds"),
        "reconciled_at": reconciled_time.isoformat(timespec="seconds"),
        "source_snapshot_sha256": "a" * 64,
        "source_row_count": len(rows), "upstream_evidence": [], "complete": True,
    }
    bindings = []
    for row in rows:
        token = hashlib.sha256(("provider:" + row["event_id"]).encode("utf-8")).hexdigest()
        bindings.append({
            "provider_identity_sha256": token,
            "provider_conversion_id_hash": token,
            "transaction_id_hash": None,
            "campaign_id_hash": hashlib.sha256(
                ("campaign:" + row["event_id"]).encode("utf-8")
            ).hexdigest(),
            "source_row_sha256": hashlib.sha256(
                ("row:" + row["event_id"]).encode("utf-8")
            ).hexdigest(),
            "event_id": row["event_id"], "sale_id": row["sale_id"],
            "date": row["date"], "status": row["status"],
            "gross_amount_thb": row["gross_amount_thb"],
            "fee_thb": row["fee_thb"], "net_amount_thb": row["net_amount_thb"],
            "channel_source": row["channel_source"], "ref": row["ref"],
        })
    reward = sum(float(binding["gross_amount_thb"]) for binding in bindings)
    evidence = {
        "schema_version": 1, "provider": "accesstrade", "format": AT.FORMAT_ID,
        "verification_mode": AT.VERIFICATION_MODE,
        "raw_file_sha256": hashlib.sha256(b"preflight-raw-fixture").hexdigest(),
        "raw_file_row_count": len(bindings),
        "header_sha256": AT._header_sha256(),
        "browser_evidence_sha256": hashlib.sha256(
            b"preflight-browser-fixture"
        ).hexdigest(),
        "filter_assertion": {
            "coverage_start": start.isoformat(), "coverage_end": today.isoformat(),
            "date_basis": AT.DATE_BASIS, "status_filter": "ALL",
            "campaign_filter": "ALL", "asserted_conversion_count": len(bindings),
            "asserted_reward_thb": "%.2f" % reward, "currency": "THB",
            "timezone": "Asia/Bangkok",
            "asserted_from": "authenticated_browser_filter_not_csv",
        },
        "extracted_at": extracted_time.isoformat(timespec="seconds"),
        "importer_sha256": AT._importer_sha256(),
        "sub_id_available": False, "attribution_state": "UNATTRIBUTED",
        "bindings": bindings,
    }
    receipt = {
        "_meta": "private AccessTrade CSV evidence receipt",
        "evidence": evidence,
        "evidence_sha256": AT.canonical_sha256(evidence),
    }
    receipt_hash = AT.canonical_sha256(receipt)
    meta["upstream_evidence"] = [{
        "receipt_file_sha256": hashlib.sha256(
            (receipt_hash + chr(10)).encode("ascii")
        ).hexdigest(),
        "receipt_sha256": receipt_hash,
        "receipt": receipt,
        "canonical_source_sha256": meta["source_snapshot_sha256"],
        "canonical_source_row_count": len(rows),
    }]
    return [json.dumps(meta)] + [json.dumps(row) for row in rows]


_LEGACY_HEADER = '{"note":"metadata header","created":"2026-07-24"}'
_GA4_CLICKS = "source,sessions,quiz_start,affiliate_click" + chr(10) + "pantip,18,2,5" + chr(10)
_GA4_ZERO = "source,sessions,quiz_start,affiliate_click" + chr(10) + "direct,166,0,0" + chr(10)
_GA4_OLDHEAD = "source,sessions,quiz_start,conversion" + chr(10) + "pantip,18,2,5" + chr(10)

check("trusted zero-sale export is decisionable regardless of click CSV", run_sales(reconciled_sales(), _GA4_CLICKS), "PASS")
check("a paid affiliate transaction is recorded", run_sales(reconciled_sales("paid"), _GA4_CLICKS), "PASS")
check("pending settlement remains visible", run_sales(reconciled_sales("pending"), _GA4_ZERO), "WARN")
check("no sales log at all", run_sales(None, _GA4_CLICKS), "WARN")
check("legacy metadata is not accepted as reconciled", run_sales([_LEGACY_HEADER], None), "WARN")
check("old conversion CSV cannot make legacy revenue trusted", run_sales([_LEGACY_HEADER], _GA4_OLDHEAD), "WARN")

print("\nDASHBOARD PROVENANCE  (a stale trusted-zero artifact must not survive input changes)")
_dash_dir = tempfile.mkdtemp(prefix="pf_dashboard_")
_dash = os.path.join(_dash_dir, "dashboard.html")
_dash_sales = os.path.join(_dash_dir, "sales.jsonl")
_dash_reader = os.path.join(_dash_dir, "revenue_ledger.py")
_dash_log_sale_reader = os.path.join(_dash_dir, "log_sale.py")
_dash_accesstrade_reader = os.path.join(_dash_dir, "import_accesstrade_csv.py")
_dash_private_runtime_reader = os.path.join(_dash_dir, "private_runtime.py")
_dash_revenue_readers = (
    _dash_reader, _dash_log_sale_reader,
    _dash_accesstrade_reader, _dash_private_runtime_reader,
)
_dash_producer = os.path.join(_dash_dir, "dashboard_agent.py")
_dash_ga4_snapshot = os.path.join(_dash_dir, "ga4-snapshot.json")
_dash_ga4_metrics = os.path.join(_dash_dir, "ga4-metrics.csv")
_dash_ga4_pages = os.path.join(_dash_dir, "ga4-pages.csv")
_dash_ga4_funnel = os.path.join(_dash_dir, "ga4-funnel.csv")
_dash_ga4_pilot_sessions = os.path.join(_dash_dir, "ga4-pilot-sessions.csv")
_dash_gsc_snapshot = os.path.join(_dash_dir, "gsc-snapshot.json")
_dash_gsc_queries = os.path.join(_dash_dir, "gsc-queries.csv")
_dash_gsc_pages = os.path.join(_dash_dir, "gsc-pages.csv")
_dash_decision_reader = os.path.join(_dash_dir, "decision_readiness.py")
_dash_observation_reader = os.path.join(_dash_dir, "observation_snapshot.py")
_dash_ga4_producer = os.path.join(_dash_dir, "ga4_pull.py")
_dash_gsc_producer = os.path.join(_dash_dir, "gsc_pull.py")
_dash_ga4_trust_reader = os.path.join(_dash_dir, "ga4_decision_trust.py")
_dash_ga4_schema_reader = os.path.join(_dash_dir, "ga4_schema.py")
_dash_content_source_reader = os.path.join(_dash_dir, "content_source_gate.py")
_dash_analytics_inputs = (
    _dash_ga4_snapshot, _dash_ga4_metrics, _dash_ga4_pages,
    _dash_ga4_funnel, _dash_ga4_pilot_sessions, _dash_gsc_snapshot,
    _dash_gsc_queries, _dash_gsc_pages,
)
_dash_analytics_readers = (
    _dash_decision_reader, _dash_observation_reader,
    _dash_ga4_producer, _dash_gsc_producer,
    _dash_ga4_trust_reader, _dash_ga4_schema_reader,
    _dash_content_source_reader,
)
with io.open(_dash_sales, "w", encoding="utf-8") as fh:
    fh.write(chr(10).join(reconciled_sales()) + chr(10))
for _fixture_path in (
    *_dash_revenue_readers, _dash_producer,
    *_dash_analytics_inputs, *_dash_analytics_readers,
):
    with io.open(_fixture_path, "w", encoding="utf-8") as fh:
        fh.write("fixture: " + os.path.basename(_fixture_path) + chr(10))


def _hash(path):
    return hashlib.sha256(open(path, "rb").read()).hexdigest()


def _combined_hash(paths):
    digest = hashlib.sha256()
    for path in paths:
        selected = Path(path)
        digest.update(str(selected.resolve()).encode("utf-8"))
        digest.update(b"\0FILE\0")
        digest.update(selected.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def run_dashboard(*, sales_hash=None, reader_hash=None, producer_hash=None,
                  analytics_input_hash=None, analytics_reader_hash=None, trusted="true",
                  state="RECONCILED", quality_state=None, revenue_expiry=None,
                  ga4_trusted="true", ga4_state="CURRENT", ga4_expiry=None,
                  gsc_trusted="true", gsc_state="CURRENT",
                  gsc_expiry=None,
                  expected_ga4_trusted=None, expected_ga4_state=None,
                  expected_gsc_trusted=None, expected_gsc_state=None,
                  expected_ga4_sessions=None,
                  expected_gsc_impressions=None, expected_gsc_clicks=None,
                  paid_net="0.00", paid_count="0",
                  pending_amount="0.00", pending_count="0",
                  revenue_metric=None, revenue_count=None, pending_metric=None,
                  pending_count_metric=None, ga4_metric=None,
                  gsc_impressions=None, gsc_clicks=None,
                  ga4_metric_grain=None, gsc_metric_grain=None,
                  generated=None, include_all=True):
    generated = generated or datetime.datetime.now(datetime.timezone.utc).isoformat()
    expected_ga4_trusted = (ga4_trusted if expected_ga4_trusted is None
                            else expected_ga4_trusted)
    expected_ga4_state = ga4_state if expected_ga4_state is None else expected_ga4_state
    expected_gsc_trusted = (gsc_trusted if expected_gsc_trusted is None
                            else expected_gsc_trusted)
    expected_gsc_state = gsc_state if expected_gsc_state is None else expected_gsc_state
    expected_ga4_sessions = (10 if expected_ga4_sessions is None
                             else expected_ga4_sessions)
    expected_gsc_impressions = (20 if expected_gsc_impressions is None
                                else expected_gsc_impressions)
    expected_gsc_clicks = (2 if expected_gsc_clicks is None
                           else expected_gsc_clicks)
    future_expiry = (
        datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=1)
    ).isoformat(timespec="seconds")
    revenue_now = P._affiliate_revenue_summary()
    quality_state = quality_state or (
        revenue_now.get("quality_state") or "UNAVAILABLE"
    )
    if revenue_expiry is None:
        revenue_expiry = (
            revenue_now.get("trust_expires_at") or future_expiry
            if trusted == "true" else "UNAVAILABLE"
        )
    ga4_expiry = ga4_expiry or (
        future_expiry if ga4_trusted == "true" else "UNAVAILABLE"
    )
    gsc_expiry = gsc_expiry or (
        future_expiry if gsc_trusted == "true" else "UNAVAILABLE"
    )
    expected_ga4_expiry = (
        ga4_expiry if expected_ga4_trusted == "true" else None
    )
    expected_gsc_expiry = (
        gsc_expiry if expected_gsc_trusted == "true" else None
    )
    P.DASHBOARD_READINESS_READER = lambda: {
        "ga4": {"trusted": expected_ga4_trusted == "true",
                "state": expected_ga4_state,
                "expires_at": expected_ga4_expiry,
                "sessions": expected_ga4_sessions},
        "gsc": {"trusted": expected_gsc_trusted == "true",
                "state": expected_gsc_state,
                "expires_at": expected_gsc_expiry,
                "impressions": expected_gsc_impressions,
                "clicks": expected_gsc_clicks},
    }
    if trusted != "true":
        paid_net = paid_count = pending_amount = pending_count = "UNAVAILABLE"
    revenue_metric = revenue_metric or (
        (paid_net + chr(3647)) if trusted == "true" else "UNAVAILABLE"
    )
    revenue_count = revenue_count or paid_count
    pending_metric = pending_metric or (
        (pending_amount + chr(3647)) if trusted == "true" else "UNAVAILABLE"
    )
    pending_count_metric = pending_count_metric or pending_count
    ga4_metric = ga4_metric or (
        "10" if ga4_trusted == "true" else "UNAVAILABLE"
    )
    gsc_impressions = gsc_impressions or (
        "20" if gsc_trusted == "true" else "UNAVAILABLE"
    )
    gsc_clicks = gsc_clicks or (
        "2" if gsc_trusted == "true" else "UNAVAILABLE"
    )
    tags = [
        ("ngernduangold-dashboard-contract", P.DASHBOARD_CONTRACT_VERSION),
        ("ngernduangold-dashboard-generated-at", generated),
        ("ngernduangold-sales-input-sha256", sales_hash or _hash(_dash_sales)),
        ("ngernduangold-revenue-reader-sha256",
         reader_hash or _combined_hash(_dash_revenue_readers)),
        ("ngernduangold-dashboard-producer-sha256", producer_hash or _hash(_dash_producer)),
        ("ngernduangold-analytics-input-sha256",
         analytics_input_hash or _combined_hash(_dash_analytics_inputs)),
        ("ngernduangold-analytics-reader-sha256",
         analytics_reader_hash or _combined_hash(_dash_analytics_readers)),
        ("ngernduangold-revenue-trusted", trusted),
        ("ngernduangold-revenue-state", state),
        ("ngernduangold-revenue-quality-state", quality_state),
        ("ngernduangold-revenue-expires-at", revenue_expiry),
        ("ngernduangold-revenue-paid-net-thb", paid_net),
        ("ngernduangold-revenue-paid-count", paid_count),
        ("ngernduangold-revenue-pending-amount-thb", pending_amount),
        ("ngernduangold-revenue-pending-count", pending_count),
        ("ngernduangold-ga4-trusted", ga4_trusted),
        ("ngernduangold-ga4-state", ga4_state),
        ("ngernduangold-ga4-expires-at", ga4_expiry),
        ("ngernduangold-ga4-metric-grain",
         ga4_metric_grain or P.DASHBOARD_GA4_METRIC_GRAIN),
        ("ngernduangold-gsc-trusted", gsc_trusted),
        ("ngernduangold-gsc-state", gsc_state),
        ("ngernduangold-gsc-expires-at", gsc_expiry),
        ("ngernduangold-gsc-metric-grain",
         gsc_metric_grain or P.DASHBOARD_GSC_METRIC_GRAIN),
    ]
    if not include_all:
        tags = tags[:-1]
    with io.open(_dash, "w", encoding="utf-8") as fh:
        fh.write("<html><head>" + "".join(
            '<meta name="%s" content="%s">' % pair for pair in tags
        ) + "</head><body>" +
        '<b data-dashboard-source="revenue" data-dashboard-metric="revenue-28d">%s</b>' % revenue_metric +
        '<span data-dashboard-source="revenue" data-dashboard-metric="revenue-paid-count">%s</span>' % revenue_count +
        '<span data-dashboard-source="revenue" data-dashboard-metric="revenue-pending-amount">%s</span>' % pending_metric +
        '<span data-dashboard-source="revenue" data-dashboard-metric="revenue-pending-count">%s</span>' % pending_count_metric +
        '<b data-dashboard-source="ga4" data-dashboard-metric="ga4-sessions">%s</b>' % ga4_metric +
        '<b data-dashboard-source="gsc" data-dashboard-metric="gsc-impressions">%s</b>' % gsc_impressions +
        '<b data-dashboard-source="gsc" data-dashboard-metric="gsc-clicks">%s</b>' % gsc_clicks +
        "<script>Date.now() >= deadline; STALE_AT_VIEW</script></body></html>")
    P.results[:] = []
    P.check_dashboard_provenance()
    return P.results[0]["status"]


_old_dashboard = (
    P.DASHBOARD, P.REVENUE_READER, P.SALES_LOG_FILE, P.SALES_LOG,
    P.DASHBOARD_REVENUE_READERS,
    P.DASHBOARD_PRODUCER, P.DASHBOARD_ANALYTICS_INPUTS,
    P.DASHBOARD_ANALYTICS_READERS, P.DASHBOARD_READINESS_READER,
)
P.DASHBOARD, P.REVENUE_READER = _dash, _dash_reader
P.SALES_LOG_FILE, P.SALES_LOG = _dash_sales, _dash_sales
P.DASHBOARD_REVENUE_READERS = _dash_revenue_readers
P.DASHBOARD_PRODUCER = _dash_producer
P.DASHBOARD_ANALYTICS_INPUTS = _dash_analytics_inputs
P.DASHBOARD_ANALYTICS_READERS = _dash_analytics_readers
check("current hash-bound dashboard is accepted", run_dashboard(), "PASS")
check("changed reader invalidates dashboard", run_dashboard(reader_hash="0" * 64), "FAIL")
_before_transitive_change = _combined_hash(_dash_revenue_readers)
with io.open(_dash_accesstrade_reader, "a", encoding="utf-8") as fh:
    fh.write("# changed transitive reader" + chr(10))
check("changed transitive revenue reader invalidates dashboard",
      run_dashboard(reader_hash=_before_transitive_change), "FAIL")
check("changed producer invalidates dashboard", run_dashboard(producer_hash="0" * 64), "FAIL")
check("changed analytics input invalidates dashboard",
      run_dashboard(analytics_input_hash="0" * 64), "FAIL")
check("changed analytics reader invalidates dashboard",
      run_dashboard(analytics_reader_hash="0" * 64), "FAIL")
_before_official_source_reader_change = _combined_hash(_dash_analytics_readers)
with io.open(_dash_content_source_reader, "a", encoding="utf-8") as fh:
    fh.write("# changed official-source contract" + chr(10))
check("changed official-source transitive reader invalidates dashboard",
      run_dashboard(analytics_reader_hash=_before_official_source_reader_change),
      "FAIL")
check("missing provenance invalidates dashboard", run_dashboard(include_all=False), "FAIL")
check("truthful unavailable analytics labels are accepted", run_dashboard(
      ga4_trusted="false", ga4_state="INVALID_METADATA",
      gsc_trusted="false", gsc_state="INVALID_METADATA"), "PASS")
check("untrusted analytics cannot render numeric zero", run_dashboard(
      ga4_trusted="false", ga4_state="INVALID_METADATA", ga4_metric="0"), "FAIL")
check("analytics trust label must match strict reader", run_dashboard(
      ga4_trusted="true", ga4_state="CURRENT",
      expected_ga4_trusted="false", expected_ga4_state="INVALID_METADATA"), "FAIL")
check("trusted revenue cannot declare an expired runtime boundary", run_dashboard(
      revenue_expiry="2020-01-01T00:00:00+00:00"), "FAIL")
check("trusted analytics cannot declare an expired runtime boundary", run_dashboard(
      ga4_expiry="2020-01-01T00:00:00+00:00"), "FAIL")
check("trusted GA4 headline must equal strict observation total", run_dashboard(
      ga4_metric="11", expected_ga4_sessions=10), "FAIL")
check("trusted GSC headline must equal page-grain observation total", run_dashboard(
      gsc_impressions="19", expected_gsc_impressions=20), "FAIL")
check("query-grain GSC declaration is rejected", run_dashboard(
      gsc_metric_grain="gsc-queries-query-total"), "FAIL")


def run_pending_dashboard(*, paid_net="0.00"):
    with io.open(_dash_sales, "w", encoding="utf-8") as fh:
        fh.write(chr(10).join(reconciled_sales("pending")) + chr(10))
    return run_dashboard(
        sales_hash=_hash(_dash_sales), paid_net=paid_net, paid_count="0",
        pending_amount="90.00", pending_count="1",
    )


check("pending commission is separate from zero paid revenue",
      run_pending_dashboard(), "PASS")
check("pending commission cannot be promoted into paid revenue",
      run_pending_dashboard(paid_net="90.00"), "FAIL")


def run_unreconciled_with_false_trusted_label():
    with io.open(_dash_sales, "w", encoding="utf-8") as fh:
        fh.write(_LEGACY_HEADER + chr(10))
    return run_dashboard(sales_hash=_hash(_dash_sales))


check("trusted-zero label cannot mask unreconciled input",
      run_unreconciled_with_false_trusted_label(), "FAIL")


def run_all_invalid_truthfully_unavailable():
    with io.open(_dash_sales, "w", encoding="utf-8") as fh:
        fh.write(_LEGACY_HEADER + chr(10))
    return run_dashboard(
        sales_hash=_hash(_dash_sales), trusted="false", state="UNRECONCILED",
        ga4_trusted="false", ga4_state="INVALID_METADATA",
        gsc_trusted="false", gsc_state="INVALID_METADATA",
    )


check("invalid inputs pass only when every visible metric is unavailable",
      run_all_invalid_truthfully_unavailable(), "PASS")
(P.DASHBOARD, P.REVENUE_READER, P.SALES_LOG_FILE, P.SALES_LOG,
 P.DASHBOARD_REVENUE_READERS,
 P.DASHBOARD_PRODUCER, P.DASHBOARD_ANALYTICS_INPUTS,
 P.DASHBOARD_ANALYTICS_READERS, P.DASHBOARD_READINESS_READER) = _old_dashboard
shutil.rmtree(_dash_dir, ignore_errors=True)

shutil.rmtree(os.path.join(TMPDIR, "_test_sales"), ignore_errors=True)
P.SALES_LOG, P.REPO = _sl, _repo

print("\nGATE STATUS VOCABULARY  (a prose status must not read as an unmade decision)")
_pol_real = P.POLICY
_gate_dir = tempfile.mkdtemp(prefix="pf_gate_")


def run_gate(status):
    g = {"date": "2020-01-01", "task": "t-gate", "decides": ["x"]}
    if status is not None:
        g["status"] = status
    p = os.path.join(_gate_dir, "policy.json")
    with io.open(p, "w", encoding="utf-8") as fh:
        json.dump({"gates": [g]}, fh)
    P.POLICY = p
    P.results[:] = []
    P.check_open_decisions()
    return P.results[0]


check("no status at all -> still overdue", run_gate(None)["status"], "WARN")
check("SUPERSEDED closes the gate", run_gate("SUPERSEDED")["status"], "PASS")
check("lowercase decided closes it too", run_gate("decided")["status"], "PASS")
_prose = run_gate("CLOSED 2026-08-09 - RAN, COULD NOT DECIDE")
check("prose status still warns", _prose["status"], "WARN")
check("...but names the unusable word",
      "yes" if "is not one of" in _prose["detail"] else "no", "yes")
check("...and quotes it back", "yes" if "COULD NOT DECIDE" in _prose["detail"] else "no", "yes")
check("a real unmade decision is not annotated",
      "yes" if "is not one of" not in run_gate(None)["detail"] else "no", "yes")

shutil.rmtree(_gate_dir, ignore_errors=True)
P.POLICY = _pol_real

print("\nSYNTHETIC TRAFFIC  (our own robots must not be counted as an audience)")
_gm = P.GA4_METRICS
_syn_dir = tempfile.mkdtemp(prefix="pf_syn_")   # fixture อยู่นอก repo (ของเดิมเคยค้างใน tools/)


def run_syn(csv_text, trusted=True):
    p = os.path.join(_syn_dir, "ga4-metrics.csv")
    if csv_text is None:
        if os.path.exists(p):
            os.remove(p)
        P.GA4_METRICS = os.path.join(_syn_dir, "missing.csv")
    else:
        with io.open(p, "w", encoding="utf-8", newline=chr(10)) as fh:
            fh.write(csv_text)
        P.GA4_METRICS = p
    P.GA4_TRUST_EVALUATOR = lambda *_: type(
        "Trust", (), {"trusted": trusted, "reason": "fixture"}
    )()
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
check("untrusted GA4 suppresses traffic-shape interpretation", run_syn(_REAL, trusted=False), "WARN")

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
    for _ in [0]) + "\n")
check("posted today", run_check("check_delivery_gap", LEDGER=_led(0)), "PASS")
check("silent %d days" % P.DELIVERY_WARN_DAYS,
      run_check("check_delivery_gap", LEDGER=_led(P.DELIVERY_WARN_DAYS)), "WARN")
check("silent %d days" % P.DELIVERY_FAIL_DAYS,
      run_check("check_delivery_gap", LEDGER=_led(P.DELIVERY_FAIL_DAYS)), "FAIL")
_comment_does_not_reset = write(
    "comment_does_not_reset.jsonl",
    chr(10).join([
        json.dumps({"type": "text", "channel": "facebook",
                    "ts": "%sT09:00:00+07:00" % (datetime.date.today() - datetime.timedelta(days=P.DELIVERY_FAIL_DAYS)).isoformat()}),
        json.dumps({"type": "comment", "channel": "pantip",
                    "ts": datetime.date.today().isoformat() + "T09:00:00+07:00"}),
    ]) + "\n",
)
check("a fresh community reply cannot hide a stale owned feed",
      run_check("check_delivery_gap", LEDGER=_comment_does_not_reset), "FAIL")
check("ledger with no content rows at all",
      run_check("check_delivery_gap", LEDGER=write("empty.jsonl", "")), "FAIL")
check("ledger file missing entirely",
      run_check("check_delivery_gap", LEDGER=os.path.join(TMPDIR, "nope.jsonl")), "FAIL")
_bad_delivery_time = write(
    "bad-delivery-time.jsonl",
    json.dumps({"type": "text", "channel": "facebook",
                "ts": TODAY + "T99:00:00+07:00"}) + "\n",
)
check("malformed content time cannot report fresh delivery",
      run_check("check_delivery_gap", LEDGER=_bad_delivery_time), "FAIL")

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
check("policy.json missing -> FAIL closed",
      run_check("check_queued_clip_spec", REPO=os.path.join(TMPDIR, "no-repo")), "FAIL")
check("nothing queued from today onward -> WARN",
      run_check("check_queued_clip_spec", REPO=REPO_REAL,
                SCHEDULE=write("s0.json", {"2020-01-01": {"file": "old.mp4"}})), "WARN")
check("queued clip missing on disk -> FAIL",
      run_check("check_queued_clip_spec", REPO=REPO_REAL,
                SCHEDULE=write("s1.json", {_today: {"file": "definitely-not-here.mp4"}})),
      "FAIL")
_clip_repo = os.path.join(TMPDIR, "cliprepo")
_clip = write("cliprepo/reels/clip.mp4", "fixture")
_clip_policy = write("cliprepo/.system_control/policy.json",
                     {"specs": {"reel_width": 1080, "reel_height": 1920}})
_clip_report = write("cliprepo/automation-log/media-qa/clip.json", {"fixture": True})
_clip_schedule = write("cliprepo/reels/schedule.json", {
    _today: {"file": "clip.mp4", "qa_report": "automation-log/media-qa/clip.json"}
})
check("hash-bound clean queued clip -> PASS",
      run_check("check_queued_clip_spec", REPO=_clip_repo, SCHEDULE=_clip_schedule,
                QUEUED_CLIP_PROBER=lambda _path: "1080,1920",
                MEDIA_GUARD_RUNNER=lambda _asset, _report: (0, "PASS")), "PASS")
check("watermark guard failure -> FAIL",
      run_check("check_queued_clip_spec", REPO=_clip_repo, SCHEDULE=_clip_schedule,
                QUEUED_CLIP_PROBER=lambda _path: "1080,1920",
                MEDIA_GUARD_RUNNER=lambda _asset, _report: (2, "watermark detected")), "FAIL")
_no_receipt_schedule = write("cliprepo/reels/schedule-no-receipt.json", {
    _today: {"file": "clip.mp4"}
})
check("queued clip without QA receipt -> FAIL",
      run_check("check_queued_clip_spec", REPO=_clip_repo, SCHEDULE=_no_receipt_schedule,
                QUEUED_CLIP_PROBER=lambda _path: "1080,1920",
                MEDIA_GUARD_RUNNER=lambda _asset, _report: (0, "PASS")), "FAIL")

print("\nDELIVERABLES  (a page may not take money for a file that does not exist)")


def products(items, repo=None):
    """Write a policy.json holding a products block, return (POLICY, REPO)."""
    d = os.path.join(TMPDIR, "prod_%d" % abs(hash(str(items))))
    os.makedirs(os.path.join(d, ".system_control"), exist_ok=True)
    pol = os.path.join(d, ".system_control", "policy.json")
    normalized = []
    for item in items:
        item = dict(item)
        item.setdefault("promotion_authorized", True)
        normalized.append(item)
    with io.open(pol, "w", encoding="utf-8") as fh:
        json.dump({"products": {"items": normalized}}, fh, ensure_ascii=False)
    return pol, (repo or d)


def make(repo, rel, size):
    full = os.path.join(repo, rel)
    os.makedirs(os.path.dirname(full), exist_ok=True)
    with io.open(full, "wb") as fh:
        fh.write(b"x" * size)
    return rel


_d = os.path.join(TMPDIR, "prodrepo"); os.makedirs(_d, exist_ok=True)
_page = make(_d, "site/kit.html", 100)
_file = make(_d, "files/kit.pdf", 600 * 1024)

_pol, _ = products([{"id": "kit", "sold_on": _page, "deliverable": _file}])
check("page + real file -> ready",
      run_check("check_deliverables", POLICY=_pol, REPO=_d), "PASS")

# A file existing is not owner authorization to promote it. Purchase intent is
# allowed only when the explicit product switch is true, and every intent must
# carry a declared stable id.
with io.open(os.path.join(_d, _page), "w", encoding="utf-8") as fh:
    fh.write('<a data-buy="kit" href="https://example.test/checkout">buy</a>')
_pol, _ = products([{"id": "kit", "sold_on": _page, "deliverable": _file,
                     "promotion_authorized": False}])
check("deliverable ready but promotion unauthorized -> FAIL",
      run_check("check_deliverables", POLICY=_pol, REPO=_d), "FAIL")
_pol, _ = products([{"id": "kit", "sold_on": _page, "deliverable": _file,
                     "promotion_authorized": True}])
check("declared authorized purchase intent -> PASS",
      run_check("check_deliverables", POLICY=_pol, REPO=_d), "PASS")
with io.open(os.path.join(_d, _page), "w", encoding="utf-8") as fh:
    fh.write('<a data-note="send payment" href="https://example.test/checkout">buy</a>')
check("unbound data-note purchase intent -> FAIL",
      run_check("check_deliverables", POLICY=_pol, REPO=_d), "FAIL")
with io.open(os.path.join(_d, _page), "w", encoding="utf-8") as fh:
    fh.write('<a data-buy="unknown" href="https://example.test/checkout">buy</a>')
check("undeclared own-product id -> FAIL",
      run_check("check_deliverables", POLICY=_pol, REPO=_d), "FAIL")
with io.open(os.path.join(_d, _page), "w", encoding="utf-8") as fh:
    fh.write("ordinary product page")
with io.open(_pol, encoding="utf-8") as fh:
    _missing_auth = json.load(fh)
del _missing_auth["products"]["items"][0]["promotion_authorized"]
with io.open(_pol, "w", encoding="utf-8") as fh:
    json.dump(_missing_auth, fh)
check("missing promotion authorization -> FAIL closed",
      run_check("check_deliverables", POLICY=_pol, REPO=_d), "FAIL")

# THE 9 Aug CASE: the page is live, the promise is in it, the file does not exist.
_pol, _ = products([{"id": "kit", "sold_on": _page, "deliverable": None}])
check("page live, nothing to hand over -> FAIL",
      run_check("check_deliverables", POLICY=_pol, REPO=_d), "FAIL")
check("...and the product is NAMED",
      "kit" in run_check_detail("check_deliverables", POLICY=_pol, REPO=_d), True)

# A badge cannot conceal a live checkout.  Both source and generated output are
# inspected because build-time rewrites previously made the two disagree.
with io.open(os.path.join(_d, _page), "w", encoding="utf-8") as fh:
    fh.write('<div data-offer-status="paused"></div><a data-buy="kit" href="https://gumroad.com/l/kit">buy</a>')
_pol, _ = products([{"id": "kit", "sold_on": _page, "deliverable": None}])
check("paused badge plus checkout -> FAIL",
      run_check("check_deliverables", POLICY=_pol, REPO=_d), "FAIL")
with io.open(os.path.join(_d, _page), "w", encoding="utf-8") as fh:
    fh.write('<div data-offer-status="paused"></div><a href="/free-tool">free tool</a>')
check("paused badge plus free internal help -> PASS",
      run_check("check_deliverables", POLICY=_pol, REPO=_d), "PASS")

_pol, _ = products([{"id": "kit", "sold_on": _page, "deliverable": "files/nope.pdf"}])
check("file listed in policy but absent on disk -> FAIL",
      run_check("check_deliverables", POLICY=_pol, REPO=_d), "FAIL")

# A 40-byte "PDF" is a placeholder someone forgot to replace, not a product.
make(_d, "files/stub.pdf", 40)
_pol, _ = products([{"id": "kit", "sold_on": _page, "deliverable": "files/stub.pdf"}])
check("a placeholder-sized file is not a deliverable -> FAIL",
      run_check("check_deliverables", POLICY=_pol, REPO=_d), "FAIL")

# A retired product whose page is gone is not an outstanding promise. Without this
# the check would nag forever about things nobody can buy any more.
_pol, _ = products([{"id": "old", "sold_on": "site/deleted.html", "deliverable": None}])
check("product whose page no longer exists is out of scope",
      run_check("check_deliverables", POLICY=_pol, REPO=_d), "PASS")

# Gumroad hosts the file; disk cannot answer. Must say 'cannot check', never assume.
_pol, _ = products([{"id": "gr", "sold_on": _page, "deliverable": "gumroad:l/x"}])
check("authorized hosted fulfillment remains unverified -> WARN",
      run_check("check_deliverables", POLICY=_pol, REPO=_d), "WARN")
check("...and the report admits it could not verify it",
      "not checkable" in run_check_detail("check_deliverables", POLICY=_pol, REPO=_d), True)

# One good product must not mask one broken one.
with io.open(os.path.join(_d, _page), "w", encoding="utf-8") as fh:
    fh.write("ordinary product page")
_pol, _ = products([{"id": "ok", "sold_on": _page, "deliverable": _file},
                    {"id": "broken", "sold_on": _page, "deliverable": None}])
check("a ready product does not hide a missing one",
      run_check("check_deliverables", POLICY=_pol, REPO=_d), "FAIL")

_pol, _ = products([])
check("no products declared -> FAIL closed",
      run_check("check_deliverables", POLICY=_pol, REPO=_d), "FAIL")
check("unreadable policy -> FAIL closed",
      run_check("check_deliverables", POLICY=os.path.join(TMPDIR, "nope.json"), REPO=_d), "FAIL")

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
    bangkok = datetime.timezone(datetime.timedelta(hours=7))
    ts = (datetime.datetime.now(bangkok) - datetime.timedelta(hours=hours_ago)).isoformat(timespec="seconds")
    return {"ts": ts, "routine": routine, "status": status, "summary": "x", "metrics": {}}


def raw_runlog(text, name="2026-08.jsonl"):
    d = os.path.join(TMPDIR, "runlogs_raw_%d" % abs(hash(text)))
    os.makedirs(d, exist_ok=True)
    for f in os.listdir(d):
        path = os.path.join(d, f)
        if os.path.isfile(path):
            os.unlink(path)
        else:
            shutil.rmtree(path)
    with io.open(os.path.join(d, name), "w", encoding="utf-8", newline="") as fh:
        fh.write(text)
    return d


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
_valid_before = json.dumps(_run("a", "ok", 2))
_valid_after = json.dumps(_run("b", "ok", 1))
_malformed_dir = raw_runlog(_valid_before + "\n{broken-json\n" + _valid_after + "\n")
check("malformed middle JSONL row fails closed",
      run_check("check_stuck_runs", RUNLOG_DIR=_malformed_dir), "WARN")
check("malformed runlog is reported as UNKNOWN",
      "UNKNOWN" in run_check_detail("check_stuck_runs", RUNLOG_DIR=_malformed_dir), True)
_unreadable_dir = os.path.join(TMPDIR, "runlogs_unreadable")
shutil.rmtree(_unreadable_dir, ignore_errors=True)
os.makedirs(os.path.join(_unreadable_dir, "2026-08.jsonl"))
check("unreadable runlog path fails closed",
      run_check("check_stuck_runs", RUNLOG_DIR=_unreadable_dir), "WARN")
_z_stamp = (datetime.datetime.now(datetime.timezone.utc)
            - datetime.timedelta(hours=1)).isoformat(timespec="seconds").replace("+00:00", "Z")
check("Z timestamp is normalized before age comparison",
      run_check("check_stuck_runs", RUNLOG_DIR=runlog_dir([
          {"ts": _z_stamp, "routine": "utc-z", "status": "started"}
      ])), "PASS")
_weekly_dir = runlog_dir([_run("ngernduangold-weekly-review", "started", 30)])
check("weekly-review started remains reconciliation-required",
      run_check("check_stuck_runs", RUNLOG_DIR=_weekly_dir), "WARN")
check("weekly-review guard never claims a synthetic terminal",
      "do not synthesize" in run_check_detail("check_stuck_runs", RUNLOG_DIR=_weekly_dir), True)
check("no runlog at all is a WARN, never a silent PASS",
      run_check("check_stuck_runs", RUNLOG_DIR=os.path.join(TMPDIR, "no-runlogs")), "WARN")
# post-ledger.jsonl lives in the same directory and has no `routine` key. Reading it
# as a runlog would be the same class of bug as the 27-30 Jul manifest/schedule mixup.
check("rows without a routine key are ignored, not crashed on",
      run_check("check_stuck_runs",
                RUNLOG_DIR=runlog_dir([{"type": "video", "channel": "threads", "ts": "2026-08-01"},
                                       _run("a", "ok", 2)])), "PASS")

print("\nDELEGATED CHECKS  (queue + build gate shell out - prove the mapping)")


def fake_tool(name, code, out, delay_seconds=0):
    # Every invocation gets a fresh directory.  Reusing TMPDIR/bin meant that
    # the bounded-timeout case below killed content_calendar_guard.py and the
    # next case immediately tried to truncate that same executable path.  On
    # the scheduled Windows run the recently terminated path can still be held
    # briefly, so io.open() failed before the fail-closed assertion could run.
    # Isolation avoids the handle race without retrying or masking fixture I/O
    # failures: an unsuccessful mkdir/open still fails the self-test.
    d = tempfile.mkdtemp(prefix="fake_tool_", dir=TMPDIR)
    with io.open(os.path.join(d, name), "w", encoding="utf-8", newline="\n") as fh:
        fh.write(
            "import sys, time\ntime.sleep(%r)\nprint(%r)\nsys.exit(%d)\n"
            % (delay_seconds, out, code)
        )
    return d


_isolated_tool_a = fake_tool("content_calendar_guard.py", 0, "first fixture")
_isolated_tool_b = fake_tool("content_calendar_guard.py", 2, "second fixture")
check("delegated tool fixtures use isolated executable paths",
      _isolated_tool_a != _isolated_tool_b, True)
with io.open(os.path.join(_isolated_tool_a, "content_calendar_guard.py"),
             encoding="utf-8") as _isolated_a_fh:
    _isolated_a_text = _isolated_a_fh.read()
with io.open(os.path.join(_isolated_tool_b, "content_calendar_guard.py"),
             encoding="utf-8") as _isolated_b_fh:
    _isolated_b_text = _isolated_b_fh.read()
check("a later delegated fixture cannot overwrite an earlier one",
      "first fixture" in _isolated_a_text and "second fixture" in _isolated_b_text,
      True)


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
check("live release parity passes", run_check(
      "check_live_release_parity", HERE=fake_tool("postdeploy_smoke.py", 0, "live parity ok")), "PASS")
check("live release drift blocks production readiness", run_check(
      "check_live_release_parity", HERE=fake_tool("postdeploy_smoke.py", 1, "0/72 live pages match")), "FAIL")
check("live release verifier unavailable fails closed", run_check(
      "check_live_release_parity", HERE=os.path.join(TMPDIR, "no-release-verifier")), "FAIL")
check("privacy scan passes", run_check("check_privacy_guard", HERE=fake_tool("privacy_guard.py", 0, "clean")), "PASS")
check("privacy finding blocks publication", run_check("check_privacy_guard", HERE=fake_tool("privacy_guard.py", 1, "finding")), "FAIL")
check("privacy scanner failure also blocks", run_check("check_privacy_guard", HERE=fake_tool("privacy_guard.py", 2, "unavailable")), "FAIL")
check("automation ownership guard passes", run_check(
      "check_automation_policy_guard", HERE=fake_tool("automation_policy_guard.py", 0, "automation-policy-guard: PASS")), "PASS")
check("duplicate executable automation owner blocks preflight", run_check(
      "check_automation_policy_guard", HERE=fake_tool("automation_policy_guard.py", 1, "FAIL duplicate executable task id")), "FAIL")
check("automation guard unavailable fails closed", run_check(
      "check_automation_policy_guard", HERE=os.path.join(TMPDIR, "no-automation-guard")), "FAIL")
_identity_ok_dir = fake_tool(
    "public_identity_guard.py", 0,
    '{"verdict":"PASS","counts":{"pages":1,"caption_fields":1,"knowledge_rows":1,"outward_prompts":1}}')
check("public identity scan passes", run_check(
      "check_public_identity_guard",
      PUBLIC_IDENTITY_GUARD=os.path.join(_identity_ok_dir, "public_identity_guard.py")), "PASS")
_identity_fail_dir = fake_tool(
    "public_identity_guard.py", 2,
    '{"verdict":"FAIL","findings":[{"category":"PERSONAL_VOICE"}]}')
check("public identity finding blocks publication", run_check(
      "check_public_identity_guard",
      PUBLIC_IDENTITY_GUARD=os.path.join(_identity_fail_dir, "public_identity_guard.py")), "FAIL")
_identity_bad_dir = fake_tool("public_identity_guard.py", 0, "not-json")
check("malformed public identity evidence fails closed", run_check(
      "check_public_identity_guard",
      PUBLIC_IDENTITY_GUARD=os.path.join(_identity_bad_dir, "public_identity_guard.py")), "FAIL")
check("public identity scan budget covers the real inventory",
      P.PUBLIC_IDENTITY_TIMEOUT_SECONDS >= 180, True)
check("manifest contract passes", run_check("check_manifest_contract", HERE=fake_tool("manifest_contract.py", 0, "clean")), "PASS")
check("manifest evidence drift blocks", run_check("check_manifest_contract", HERE=fake_tool("manifest_contract.py", 1, "drift")), "FAIL")
_calendar_pass = '{"verdict":"PASS","process_state":"PASS","findings":[],"counts":{"placements":65,"content_ids":40,"publishable":0,"source_content_evaluated":37,"source_content_allowed":0,"source_content_blocked":37,"source_failure_reasons":37}}'
check("calendar guard timeout exceeds twice the measured high-water mark",
      P.CONTENT_CALENDAR_GUARD_TIMEOUT_SECONDS >= 104, True)
check("calendar guard timeout remains fixed at its explicit cap",
      P.CONTENT_CALENDAR_GUARD_TIMEOUT_SECONDS == 120, True)
check("content calendar contract passes", run_check(
      "check_content_calendar_contract",
      HERE=fake_tool("content_calendar_guard.py", 0, _calendar_pass)), "PASS")
_calendar_results = run_check_results(
    "check_content_calendar_contract",
    HERE=fake_tool("content_calendar_guard.py", 0, _calendar_pass))
check("calendar structure is reported separately",
      [(row["check"], row["status"]) for row in _calendar_results],
      [("calendar structure", "PASS"), ("publish readiness", "WARN")])
check("structural pass does not imply publish authority",
      "does not authorize posting" in _calendar_results[1]["detail"], True)
_calendar_bounded_success = run_check_results(
    "check_content_calendar_contract",
    HERE=fake_tool("content_calendar_guard.py", 0, _calendar_pass, delay_seconds=0.05),
    CONTENT_CALENDAR_GUARD_TIMEOUT_SECONDS=1)
check("calendar guard completing inside its bound is accepted",
      [(row["check"], row["status"]) for row in _calendar_bounded_success],
      [("calendar structure", "PASS"), ("publish readiness", "WARN")])
_calendar_real_timeout = run_check_results(
    "check_content_calendar_contract",
    HERE=fake_tool("content_calendar_guard.py", 0, _calendar_pass, delay_seconds=0.25),
    CONTENT_CALENDAR_GUARD_TIMEOUT_SECONDS=0.05)
check("calendar guard exceeding its bound fails closed",
      [(row["check"], row["status"]) for row in _calendar_real_timeout],
      [("calendar structure", "FAIL"), ("publish readiness", "FAIL")])
check("calendar timeout names the enforced bound",
      "timed out after 0.05s" in _calendar_real_timeout[0]["detail"], True)
_calendar_fail = '{"verdict":"FAIL","process_state":"BLOCKED","findings":[{"code":"PLACEMENT_DUPLICATE","message":"duplicate placement"}],"counts":{}}'
check("content calendar drift blocks preflight", run_check(
      "check_content_calendar_contract",
      HERE=fake_tool("content_calendar_guard.py", 2, _calendar_fail)), "FAIL")
_calendar_business_blocked = '{"verdict":"FAIL","process_state":"BLOCKED","findings":[{"code":"PERMANENT_DEDUP_INCOMPLETE","message":"history incomplete","classification":"PUBLICATION_BLOCKER"}],"counts":{"placements":65,"content_ids":40,"publishable":0,"source_content_evaluated":37,"source_content_allowed":0,"source_content_blocked":37,"source_failure_reasons":37}}'
_calendar_blocked_results = run_check_results(
    "check_content_calendar_contract",
    HERE=fake_tool("content_calendar_guard.py", 2, _calendar_business_blocked))
check("valid calendar control separates business blockers",
      [(row["check"], row["status"]) for row in _calendar_blocked_results],
      [("calendar structure", "PASS"), ("publish readiness", "FAIL")])
check("malformed calendar evidence fails closed", run_check(
      "check_content_calendar_contract",
      HERE=fake_tool("content_calendar_guard.py", 0, "not-json")), "FAIL")
_calendar_bad_source_counts = '{"verdict":"PASS","process_state":"PASS","findings":[],"counts":{"placements":1,"content_ids":1,"publishable":0,"source_content_evaluated":1,"source_content_allowed":1,"source_content_blocked":1,"source_failure_reasons":0}}'
check("inconsistent content-scoped source counts fail closed", run_check(
      "check_content_calendar_contract",
      HERE=fake_tool("content_calendar_guard.py", 0, _calendar_bad_source_counts)), "FAIL")

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

print("\nPROMPT BYTE CONSISTENCY  (ownership comes from the scheduler registry)")
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

print("\nGA4 INTERNAL IP  (every unverifiable trust state must fail closed)")
# A previous incident left an ACTIVE Exclude filter pinned to an obsolete address.
# Every visible signal said "protected" while the current host was uncovered.
# These documentation-network fixtures ensure the next rotation is loud without
# retaining or printing any real address.


def _ga4_fixture_json_bytes(value):
    return (
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n"
    ).encode("utf-8")


def bind_ga4_coverage(block):
    try:
        normalized = sorted({
            str(ipaddress.ip_network(str(value).strip(), strict=False))
            for value in block.get("ips", [])
        })
        fingerprint = hashlib.sha256(
            json.dumps(
                normalized, ensure_ascii=True, separators=(",", ":")
            ).encode("utf-8")
        ).hexdigest()
    except ValueError:
        fingerprint = "0" * 64
    verified_at = block["verified_at"]
    block["coverage_attestation"] = {
        "schema_version": 1,
        "source": "authenticated_ga4_admin_read_only",
        "verified_at": verified_at,
        "attested_at": verified_at + "T00:00:00+07:00",
        "cidr_set_sha256": fingerprint,
    }
    attestation = block["coverage_attestation"]
    raw_cidrs = block.get("ips", [])
    observation = {
        "schema_version": 1,
        "mode": "authenticated_browser_read_only",
        "observed_at": attestation["attested_at"],
        "external_mutations": [],
        "internal_traffic": {
            "filter_state": "Active",
            "filter_operation": "Exclude",
            "exact_normalized_set_match": True,
            "condition_count": len(set(raw_cidrs)),
            "private_contract_condition_count": len(set(raw_cidrs)),
            "raw_network_values_emitted": False,
            "cidr_set_sha256": fingerprint,
        },
    }
    evidence_name = "ga4-admin-observation-fixture.json"
    observation_bytes = _ga4_fixture_json_bytes(observation)
    attestation["admin_observation_contract"] = {
        "schema_version": 1,
        "default": evidence_name,
        "sha256": hashlib.sha256(observation_bytes).hexdigest(),
    }
    attestation["_admin_observation_fixture"] = observation
    return block


def ga4_env(pinned, host_ip, days_ago=0, state="Active", drop_block=False, no_host=False):
    """Build a policy + host_ip fixture pair and return them as constant overrides."""
    verified = (datetime.date.today() - datetime.timedelta(days=35)).isoformat()
    ga4 = {} if drop_block else {"internal_traffic": bind_ga4_coverage({
        "filter_state": state, "filter_operation": "Exclude",
        "verified_at": verified, "ips": pinned})}
    pol = write("pol_%s.json" % abs(hash((str(pinned), host_ip, days_ago, state,
                                          drop_block, no_host))),
                {"ga4": ga4})
    if no_host:
        return {"POLICY": pol, "HOST_IP_FILE": os.path.join(TMPDIR, "no_such_host_ip.json")}
    seen = (
        datetime.datetime.now(datetime.timezone.utc)
        - datetime.timedelta(days=days_ago)
    ).isoformat(timespec="seconds")
    hip = write("hip_%s.json" % abs(hash((host_ip, days_ago))),
                {"ip": host_ip, "checked_at": seen,
                 "source": "api.ipify.org", "host": platform.node()})
    return {"POLICY": pol, "HOST_IP_FILE": hip}


check("egress ip is inside the pinned CIDR",
      run_check("check_ga4_internal_ip", **ga4_env(["203.0.113.17/32"], "203.0.113.17")), "PASS")
check("historical rotated-address mismatch is blocked",
      run_check("check_ga4_internal_ip", **ga4_env(["198.51.100.42/32"], "203.0.113.17")), "FAIL")
check("both old and new pinned -> still covered",
      run_check("check_ga4_internal_ip",
                **ga4_env(["198.51.100.42/32", "203.0.113.17/32"], "203.0.113.17")), "PASS")
check("real CIDR math, not string compare (/24 contains fixture host)",
      run_check("check_ga4_internal_ip", **ga4_env(["203.0.113.0/24"], "203.0.113.17")), "PASS")
check("neighbouring /24 does NOT contain it",
      run_check("check_ga4_internal_ip", **ga4_env(["203.0.112.0/24"], "203.0.113.17")), "FAIL")
check("Data Filter left in Testing = configured but not excluding",
      run_check("check_ga4_internal_ip",
                **ga4_env(["203.0.113.17/32"], "203.0.113.17", state="Testing")), "FAIL")
check("no ga4.internal_traffic block at all",
      run_check("check_ga4_internal_ip",
                **ga4_env(["203.0.113.17/32"], "203.0.113.17", drop_block=True)), "FAIL")
check("ips list empty = not protected, must not read as PASS",
      run_check("check_ga4_internal_ip", **ga4_env([], "203.0.113.17")), "FAIL")
check("unparseable CIDR in policy is surfaced, not skipped",
      run_check("check_ga4_internal_ip", **ga4_env(["203.0.113.17/nope"], "203.0.113.17")), "FAIL")
check("host_ip.json missing = blind, and blind must never print PASS",
      run_check("check_ga4_internal_ip",
                **ga4_env(["203.0.113.17/32"], "203.0.113.17", no_host=True)), "FAIL")
check("host_ip.json 30 days old = uptime_check stopped running",
      run_check("check_ga4_internal_ip",
                **ga4_env(["203.0.113.17/32"], "203.0.113.17", days_ago=30)), "FAIL")
check("6 days old is still inside the freshness window",
      run_check("check_ga4_internal_ip",
                **ga4_env(["203.0.113.17/32"], "203.0.113.17", days_ago=6)), "PASS")
_p = write("pol_badip.json", {"ga4": {"internal_traffic":
                                      bind_ga4_coverage({"filter_state": "Active", "filter_operation": "Exclude",
                                       "verified_at": (datetime.date.today() - datetime.timedelta(days=35)).isoformat(),
                                       "ips": ["203.0.113.17/32"]})}})
_h = write("hip_badip.json", {"ip": "not-an-ip", "checked_at":
                              datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
                              "source": "api.ipify.org", "host": platform.node()})
check("garbage recorded as the host ip fails closed without a crash",
      run_check("check_ga4_internal_ip", POLICY=_p, HOST_IP_FILE=_h), "FAIL")
_h = write("hip_badts.json", {"ip": "203.0.113.17", "checked_at": "yesterday-ish",
                              "source": "api.ipify.org", "host": platform.node()})
check("unreadable checked_at fails closed, never assumed fresh",
      run_check("check_ga4_internal_ip", POLICY=_p, HOST_IP_FILE=_h), "FAIL")
_h = write("hip_wrong_host.json", {
    "ip": "203.0.113.17", "checked_at": datetime.datetime.now(
        datetime.timezone.utc
    ).isoformat(),
    "source": "api.ipify.org", "host": "different-fixture-host",
})
check("egress evidence from a different host fails closed",
      run_check("check_ga4_internal_ip", POLICY=_p, HOST_IP_FILE=_h), "FAIL")
check("host mismatch detail suppresses both network and hostname values",
      all(token not in run_check_detail(
          "check_ga4_internal_ip", POLICY=_p, HOST_IP_FILE=_h)
          for token in ("203.0.113", "different-fixture-host")), True)

print("\nOFFICIAL SOURCE MONITOR  (global queue is diagnostic; content gates are exact)")
_news_fresh = write("official_fresh.json", {
    "checked_at": datetime.datetime.now().isoformat(),
    "sources": [{"url": "https://example.test/official"}],
    "changed": [],
    "errors": [],
    "review_required": [],
})
check("schema-less synthetic clean snapshot never passes", run_check(
      "check_official_source_freshness", OFFICIAL_NEWS_SNAPSHOT=_news_fresh), "WARN")
_news_stale = write("official_stale.json", {
    "checked_at": (datetime.datetime.now() - datetime.timedelta(days=30)).isoformat(),
    "sources": [{"url": "https://example.test/official"}],
    "changed": [],
    "errors": [],
    "review_required": [],
})
check("stale global snapshot warns while content gates remain responsible", run_check(
      "check_official_source_freshness", OFFICIAL_NEWS_SNAPSHOT=_news_stale,
      OFFICIAL_NEWS_STALE_DAYS=7), "WARN")
_news_changed = write("official_changed.json", {
    "checked_at": datetime.datetime.now().isoformat(),
    "sources": [{"url": "https://example.test/official"}],
    "changed": [{"url": "https://example.test/official"}],
    "errors": [],
    "review_required": [],
})
check("changed global fingerprint warns without a site-wide block", run_check(
      "check_official_source_freshness", OFFICIAL_NEWS_SNAPSHOT=_news_changed), "WARN")
_news_pending = write("official_pending.json", {
    "checked_at": datetime.datetime.now().isoformat(),
    "sources": [{"url": "https://example.test/official"}],
    "changed": [],
    "errors": [],
    "review_required": ["source-a"],
})
check("durable global pending review remains visible without blocking unrelated content", run_check(
      "check_official_source_freshness", OFFICIAL_NEWS_SNAPSHOT=_news_pending), "WARN")
check("missing global snapshot never passes silently", run_check(
      "check_official_source_freshness",
      OFFICIAL_NEWS_SNAPSHOT=os.path.join(TMPDIR, "does-not-exist.json")), "WARN")
_news_future = write("official_future.json", {
    "schema": 3,
    "checked_at": (datetime.datetime.now(datetime.timezone.utc) +
                   datetime.timedelta(days=1)).isoformat(),
    "purpose": "change detection only; review official source before publishing",
    "changed": [], "errors": [], "review_required": [],
    "acknowledged_this_run": [], "sources": [],
})
check("future global timestamp never passes", run_check(
      "check_official_source_freshness", OFFICIAL_NEWS_SNAPSHOT=_news_future), "WARN")
_news_malformed = write("official_malformed.json", {
    "schema": 3,
    "checked_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    "purpose": "change detection only; review official source before publishing",
    "changed": "none", "errors": {}, "review_required": ["source-a", "source-a"],
    "acknowledged_this_run": [], "sources": [{"id": "source-a"}],
})
check("malformed and duplicate global state lists never pass", run_check(
      "check_official_source_freshness", OFFICIAL_NEWS_SNAPSHOT=_news_malformed), "WARN")

print("\nPROJECT BOUNDARY  (a trading-bot reminder must not live in a web-project report)")


_boundary_n = [0]


def make_boundary(files):
    """files: {relative-path: text}. Builds a throwaway repo root with automation-log/."""
    _boundary_n[0] += 1
    root = os.path.join(TMPDIR, "boundary_%03d" % _boundary_n[0])
    os.makedirs(os.path.join(root, "automation-log"))
    for rel, text in files.items():
        p = os.path.join(root, rel)
        d = os.path.dirname(p)
        if not os.path.isdir(d):
            os.makedirs(d)
        io.open(p, "w", encoding="utf-8", newline="\n").write(text)
    return root


def run_boundary(files):
    return run_check("check_project_boundary", REPO=make_boundary(files))


check("clean current report stays quiet", run_boundary({
      "automation-log/SYSTEM-POSTING_20260910.md": "# posting\n\nthreads ready\n"}), "PASS")
check("bybit in a current report fires", run_boundary({
      "automation-log/FINDINGS_20260910.md": "# x\n\nBybit key expires today\n"}), "FAIL")
check("case does not matter", run_boundary({
      "automation-log/NOTE_20260911.md": "GROQ_BYBIT_BOT folder\n"}), "FAIL")
check("the boundaries file itself may name every project", run_boundary({
      "PROJECT-BOUNDARIES.md": "## A. bybit cascade-fade\n## B. airbnb tm30\n"}), "PASS")
check("historical report before the guard existed is left alone", run_boundary({
      "automation-log/RESUME-CHECKLIST_20260905.md": "Bybit API key expires 10 Sep\n"}), "PASS")
check("undated file is not judged (no date, no era)", run_boundary({
      "automation-log/latest.md": "bybit\n"}), "PASS")
check("non-markdown is out of scope", run_boundary({
      "automation-log/2026-09_20260910.jsonl": '{"note":"bybit"}\n'}), "PASS")
check("detail names the file and the term", "SYSTEM-POSTING_20260910.md: bybit" in run_check_detail(
      "check_project_boundary",
      REPO=make_boundary({"automation-log/SYSTEM-POSTING_20260910.md": "bybit\n"})), True)
check("root-level markdown is covered too", run_boundary({
      "WEEK-PLAN_20260912.md": "airbnb bookkeeping\n"}), "FAIL")

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
if __name__ == "__main__":
    sys.exit(1 if bad else 0)
