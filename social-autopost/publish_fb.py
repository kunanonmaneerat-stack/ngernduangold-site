#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# publish_fb.py — FB Page daily feed post + first-comment link ผ่าน Graph API (order 2026-07-11)
#
# Flow: POST /{page-id}/feed (message เท่านั้น ไม่มี URL ในบอดี้ — reach)
#       -> POST /{post_id}/comments (ลิงก์ในคอมเมนต์แรก)
#
# Env:
#   FB_PAGE_ID, FB_PAGE_TOKEN   (Page Access Token; แยกจาก IG secrets)
#   DRY_RUN default "1" · OVERRIDE_DATE optional YYYY-MM-DD
#
# Behaviors (mirror ig_publish):
#   - secrets ยังไม่มา -> SOFT SKIP เขียว + alert FB-PUBLISH-SKIP.md (ไม่แดงรายวัน)
#   - comply fail-closed: body ต้องมี disclaimer · ห้ามมี URL ในบอดี้ · affiliate=true ต้องมี "มีลิงก์พันธมิตร" · ไม่มี bare %
#   - dedup published-fb.json · โพสต์ขึ้นแล้วแต่คอมเมนต์พลาด -> บันทึก published (กันโพสต์ซ้ำ) + alert ให้เติมคอมเมนต์มือ
# Exit: 0 = ok/skip · 2 = fail
import io, os, sys, json, re, datetime, urllib.request, urllib.parse, urllib.error

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HERE = os.path.dirname(os.path.abspath(__file__))
CONTENT_MAP = os.path.join(HERE, "feed_content_map.json")
LOG_DIR = os.path.join(ROOT, "automation-log", "fb-feed")
PUBLISHED = os.path.join(LOG_DIR, "published-fb.json")
INBOX = os.path.join(ROOT, "automation-log", "cowork-inbox")
GRAPH = "https://graph.facebook.com/v22.0"

DRY_RUN = os.environ.get("DRY_RUN", "1") != "0"
PAGE_ID = os.environ.get("FB_PAGE_ID", "")
TOKEN = os.environ.get("FB_PAGE_TOKEN", "")


def now_th():
    return datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=7)


def log(msg):
    print("[fb_feed] " + msg)


def write_note(name, body):
    os.makedirs(INBOX, exist_ok=True)
    io.open(os.path.join(INBOX, name), "w", encoding="utf-8").write(body)


def fail(msg, date=""):
    log("FAIL: " + msg)
    write_note("FB-PUBLISH-FAIL.md",
               "# FB PUBLISH FAIL — %s\n\n- date: %s\n- error: %s\n- ดู social-autopost/runbook.md §FB\n"
               % (now_th().strftime("%Y-%m-%d %H:%M"), date, msg))
    sys.exit(2)


def api(path, params):
    params = dict(params)
    params["access_token"] = TOKEN
    data = urllib.parse.urlencode(params).encode()
    try:
        with urllib.request.urlopen(urllib.request.Request(GRAPH + path, data=data), timeout=60) as r:
            return json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", "replace")[:400]
        if '"code":190' in body:
            raise RuntimeError("PAGE TOKEN EXPIRED/INVALID (code 190) — ดู runbook §FB token. " + body)
        raise RuntimeError("HTTP %d: %s" % (e.code, body))


def main():
    date = os.environ.get("OVERRIDE_DATE") or now_th().strftime("%Y-%m-%d")
    cmap = json.load(io.open(CONTENT_MAP, encoding="utf-8"))
    entry = cmap.get(date)
    if not entry:
        log("no feed entry for %s — ต้องเติมคลังโพสต์ (last=%s) · Cowork ส่ง 14-day pack มาเติมได้" % (date, max(cmap)))
        return 0
    os.makedirs(LOG_DIR, exist_ok=True)
    pub = json.load(io.open(PUBLISHED, encoding="utf-8")) if os.path.exists(PUBLISHED) else {}
    if date in pub:
        log("already posted %s (post_id=%s) — skip (dedup)" % (date, pub[date].get("post_id")))
        return 0

    text, comment = entry["fbText"], entry["firstComment"]

    # comply fail-closed (กติกา order §6)
    if "ข้อมูลเพื่อการศึกษา" not in text:
        fail("body missing disclaimer — refuse to post", date)
    if "http://" in text or "https://" in text or "ngernduangold.com" in text:
        fail("URL in post body (ต้องอยู่คอมเมนต์แรกเท่านั้น) — refuse", date)
    if entry.get("affiliate") and "มีลิงก์พันธมิตร" not in text:
        fail("affiliate post missing affiliate marker — refuse", date)
    if re.search(r"\d+\s*%", text + comment):
        fail("bare % found — refuse", date)
    if "ngernduangold.com" not in comment:
        fail("firstComment missing link", date)

    if DRY_RUN:
        log("DRY_RUN=1 — validated %s | body %d chars | comment: %s" % (date, len(text), comment[:80]))
        return 0
    if not PAGE_ID or not TOKEN:
        write_note("FB-PUBLISH-SKIP.md",
                   "# FB SKIPPED — token missing — %s\n\n- date: %s (โพสต์พร้อมแล้ว)\n"
                   "- ใส่ secrets FB_PAGE_ID/FB_PAGE_TOKEN ตาม runbook §FB แล้วนัดถัดไป (15:00TH) โพสต์เอง\n"
                   % (now_th().strftime("%Y-%m-%d %H:%M"), date))
        log("SKIPPED: FB token missing — รอ secrets (alert -> cowork-inbox/FB-PUBLISH-SKIP.md)")
        return 0

    r = api("/%s/feed" % PAGE_ID, {"message": text})
    post_id = r.get("id", "")
    if not post_id:
        fail("no post id: %s" % r, date)
    log("posted: " + post_id)
    pub[date] = {"post_id": post_id, "ts": now_th().strftime("%Y-%m-%d %H:%M:%S+07:00")}
    io.open(PUBLISHED, "w", encoding="utf-8").write(json.dumps(pub, ensure_ascii=False, indent=1))

    try:
        c = api("/%s/comments" % post_id, {"message": comment})
        pub[date]["comment_id"] = c.get("id", "")
        io.open(PUBLISHED, "w", encoding="utf-8").write(json.dumps(pub, ensure_ascii=False, indent=1))
        log("first comment: " + pub[date]["comment_id"])
    except RuntimeError as e:
        # โพสต์ขึ้นแล้ว — อย่าโพสต์ซ้ำ แต่ต้องแจ้งให้เติมคอมเมนต์ลิงก์มือ
        write_note("FB-PUBLISH-FAIL.md",
                   "# FB comment FAIL (โพสต์ขึ้นแล้ว) — %s\n\n- post_id: %s\n- error: %s\n"
                   "- ให้เติมคอมเมนต์แรกด้วยมือ: %s\n" % (date, post_id, e, comment))
        log("comment FAIL (post already up) — alert written")
        sys.exit(2)

    io.open(os.path.join(LOG_DIR, "log-%s.md" % date), "w", encoding="utf-8").write(
        "# FB post %s\n\n- post_id: %s\n- comment_id: %s\n\n```\n%s\n```\n\nfirst comment:\n```\n%s\n```\n"
        % (date, post_id, pub[date].get("comment_id", ""), text, comment))
    log("DONE %s" % date)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except RuntimeError as e:
        fail(str(e))
