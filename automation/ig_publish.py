#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# ig_publish.py — IG Reels auto-publisher via Instagram Content Publishing API (order 2026-07-11)
#
# Flow (per Meta spec): POST /{ig-user-id}/media (REELS + video_url + caption)
#                        -> poll GET /{creation-id}?fields=status_code until FINISHED
#                        -> POST /{ig-user-id}/media_publish
#
# Env:
#   IG_ACCESS_TOKEN  (required for live)  long-lived user token, instagram_content_publish scope
#   IG_USER_ID       (required for live)  IG Business Account ID (NOT the username)
#   DRY_RUN          default "1" — validate schedule/URL/caption only, no API call
#   OVERRIDE_DATE    optional YYYY-MM-DD (default: today Asia/Bangkok)
#   BASE_URL         default https://ngernduangold.com
#
# Exit: 0 = published/skipped/no-entry, 2 = FAILED (workflow turns red -> owner notified)
# Safety: caption must carry the education disclaimer + AI disclosure or we ABORT (comply fail-closed).
#         published.json prevents double-posting on re-runs (dedup guard).
import io, os, sys, json, time, datetime, urllib.request, urllib.parse, urllib.error

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCHEDULE = os.path.join(ROOT, "reels", "schedule.json")
LOG_DIR = os.path.join(ROOT, "automation-log", "ig-reels")
PUBLISHED = os.path.join(LOG_DIR, "published.json")
ALERT = os.path.join(ROOT, "automation-log", "cowork-inbox", "IG-PUBLISH-FAIL.md")
GRAPH = "https://graph.facebook.com/v22.0"

BASE_URL = os.environ.get("BASE_URL", "https://ngernduangold.com")
DRY_RUN = os.environ.get("DRY_RUN", "1") != "0"
TOKEN = os.environ.get("IG_ACCESS_TOKEN", "")
IG_USER = os.environ.get("IG_USER_ID", "")


def now_th():
    return datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=7)


def log(msg):
    print("[ig_publish] " + msg)


def fail(msg, date=""):
    log("FAIL: " + msg)
    os.makedirs(os.path.dirname(ALERT), exist_ok=True)
    io.open(ALERT, "w", encoding="utf-8").write(
        "# IG PUBLISH FAIL — %s\n\n- date: %s\n- error: %s\n- ดู runbook: automation-log/cc-outbox/RUNBOOK_ig-reels-api_20260711.md\n"
        % (now_th().strftime("%Y-%m-%d %H:%M"), date, msg))
    sys.exit(2)


def api(path, params, method="GET"):
    params = dict(params)
    params["access_token"] = TOKEN
    data = urllib.parse.urlencode(params).encode()
    url = GRAPH + path
    req = urllib.request.Request(url + ("?" + data.decode() if method == "GET" else ""),
                                 data=None if method == "GET" else data)
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", "replace")[:500]
        if '"code":190' in body:
            raise RuntimeError("TOKEN EXPIRED/INVALID (code 190) — refresh long-lived token, see runbook §4. " + body)
        raise RuntimeError("HTTP %d: %s" % (e.code, body))


def main():
    date = os.environ.get("OVERRIDE_DATE") or now_th().strftime("%Y-%m-%d")
    sched = json.load(io.open(SCHEDULE, encoding="utf-8"))
    entry = sched.get(date)
    if not entry:
        log("no schedule entry for %s — ต้องเติม batch ใน reels/schedule.json (last=%s)" % (date, max(sched)))
        return 0
    os.makedirs(LOG_DIR, exist_ok=True)
    pub = {}
    if os.path.exists(PUBLISHED):
        pub = json.load(io.open(PUBLISHED, encoding="utf-8"))
    if date in pub:
        log("already published %s (media_id=%s) — skip (dedup guard)" % (date, pub[date].get("media_id")))
        return 0

    caption = entry["caption"]
    video_url = BASE_URL + "/reels/" + entry["file"]

    # comply fail-closed: approved-sheet markers must be present
    if "ข้อมูลเพื่อการศึกษา" not in caption or "ผลิตด้วย AI" not in caption:
        fail("caption missing disclaimer/AI disclosure — refuse to publish", date)

    # hosted URL must be live before we hand it to Meta
    req = urllib.request.Request(video_url, method="HEAD", headers={"User-Agent": "Mozilla/5.0"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            ct = r.headers.get("Content-Type", "")
            if r.status != 200 or "video" not in ct:
                fail("video url %s -> %s %s (need 200 video/mp4)" % (video_url, r.status, ct), date)
    except Exception as e:
        fail("video url unreachable: %s (%s)" % (video_url, e), date)
    log("video OK: " + video_url)

    if DRY_RUN:
        log("DRY_RUN=1 — schedule/URL/caption validated, no API call. caption preview:")
        log(caption.replace("\n", " | ")[:220])
        return 0
    if not TOKEN or not IG_USER:
        # SOFT SKIP (order 11 ก.ค. §2): ยังไม่ใส่ secrets = ข้ามนุ่มนวล + แจ้งเตือน ไม่ทำ workflow แดงรายวัน
        # พอ secrets มา นัดถัดไป (20:00TH) โพสต์จริงเองอัตโนมัติ ไม่ต้องแก้อะไร
        skip_note = os.path.join(ROOT, "automation-log", "cowork-inbox", "IG-PUBLISH-SKIP.md")
        os.makedirs(os.path.dirname(skip_note), exist_ok=True)
        _msg = ("# IG SKIPPED — token missing — " + now_th().strftime("%Y-%m-%d %H:%M") + chr(10) + chr(10)
                + "- date: " + date + " (คลิป/แคปชันพร้อม hosting OK)" + chr(10)
                + "- เหตุผล: ยังไม่ได้ใส่ GitHub secrets IG_ACCESS_TOKEN/IG_USER_ID" + chr(10)
                + "- ทำตาม runbook §1 แล้วนัดถัดไป (20:00TH) จะโพสต์จริงเองอัตโนมัติ" + chr(10))
        io.open(skip_note, "w", encoding="utf-8").write(_msg)
        log("SKIPPED: IG token missing — pipeline พร้อม รอ secrets (alert -> cowork-inbox/IG-PUBLISH-SKIP.md)")
        return 0

    # 1) create media container
    r = api("/%s/media" % IG_USER, {
        "media_type": "REELS", "video_url": video_url,
        "caption": caption, "share_to_feed": "true"}, method="POST")
    cid = r.get("id")
    if not cid:
        fail("no creation id: %s" % r, date)
    log("creation_id=" + cid)

    # 2) poll until FINISHED (video processing ~30-60s, allow 5 min)
    status = ""
    for _ in range(60):
        time.sleep(5)
        s = api("/%s" % cid, {"fields": "status_code"})
        status = s.get("status_code", "")
        log("status=" + status)
        if status == "FINISHED":
            break
        if status == "ERROR":
            fail("container ERROR for %s (%s)" % (date, s), date)
    if status != "FINISHED":
        fail("container not FINISHED after 5min (last=%s)" % status, date)

    # 3) publish
    r = api("/%s/media_publish" % IG_USER, {"creation_id": cid}, method="POST")
    media_id = r.get("id", "")
    if not media_id:
        fail("publish returned no media id: %s" % r, date)

    pub[date] = {"creation_id": cid, "media_id": media_id,
                 "file": entry["file"], "ts": now_th().strftime("%Y-%m-%d %H:%M:%S+07:00")}
    io.open(PUBLISHED, "w", encoding="utf-8").write(json.dumps(pub, ensure_ascii=False, indent=1))
    io.open(os.path.join(LOG_DIR, "log-%s.md" % date), "w", encoding="utf-8").write(
        "# IG Reel published %s\n\n- file: %s\n- creation_id: %s\n- media_id: %s\n- caption:\n\n```\n%s\n```\n"
        % (date, entry["file"], cid, media_id, caption))
    log("PUBLISHED %s -> media_id=%s" % (date, media_id))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except RuntimeError as e:
        fail(str(e))
