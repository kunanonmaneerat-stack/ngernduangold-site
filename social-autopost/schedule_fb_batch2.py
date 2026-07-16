#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# schedule_fb_batch2.py — ตั้งเวลา FB video 21-26 ก.ค. ผ่าน Graph API (order 12 ก.ค. ค่ำ)
#
# ⛔ DUP-GUARD (ตาม order):
#   - HARD-EXCLUDE 2026-07-20 (owner ตั้ง manual ผ่าน Business Suite แล้ว — โค้ดนี้ปฏิเสธวัน 20 เสมอ)
#   - ก่อนสร้างแต่ละอัน: GET /{page}/scheduled_posts — ถ้าวันนั้นมีโพสต์ตั้งเวลาแล้ว = ข้าม
#   - dedup ฝั่งเรา: manifest posted.fb ต้อง null ก่อนตั้ง
#
# ใช้: FB_PAGE_ID + FB_PAGE_TOKEN (env) · DRY_RUN=1 default — validate ทุกอย่างโดยไม่ยิง API เขียน
#   POST /{page-id}/videos  file_url=<hosted mp4>  description=<captions.fb>  published=false
#        scheduled_publish_time=<unix 19:00 Asia/Bangkok ของวันนั้น>
# Exit: 0 ok/skip · 2 fail (หยุดทันที ไม่ retry — กัน rate-limit)
import io, os, sys, json, datetime, urllib.request, urllib.parse, urllib.error

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MANIFEST = os.path.join(ROOT, ".system_control", "content_manifest.json")
GRAPH = "https://graph.facebook.com/v22.0"
BASE = "https://ngernduangold.com"
DATES = ["2026-07-21", "2026-07-22", "2026-07-23", "2026-07-24", "2026-07-25", "2026-07-26"]
FORBIDDEN = {"2026-07-20"}          # manual แล้ว — ห้ามแตะเด็ดขาด

DRY = os.environ.get("DRY_RUN", "1") != "0"
PAGE = os.environ.get("FB_PAGE_ID", "")
TOK = os.environ.get("FB_PAGE_TOKEN", "")


def unix_19th(date_str):
    y, m, dd = map(int, date_str.split("-"))
    dt = datetime.datetime(y, m, dd, 19, 0, tzinfo=datetime.timezone(datetime.timedelta(hours=7)))
    return int(dt.timestamp())


def api(path, params, method="GET"):
    params = dict(params); params["access_token"] = TOK
    data = urllib.parse.urlencode(params).encode()
    req = urllib.request.Request(GRAPH + path + ("?" + data.decode() if method == "GET" else ""),
                                 data=None if method == "GET" else data)
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            return json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        raise RuntimeError("HTTP %d: %s" % (e.code, e.read().decode("utf-8", "replace")[:300]))


def main():
    man = json.load(io.open(MANIFEST, encoding="utf-8"))
    by = {it["date"]: it for it in man["items"]}

    for f in FORBIDDEN:
        assert f not in DATES, "FORBIDDEN date in DATES!"

    # dup-guard ฝั่ง FB: วันไหนมี scheduled post อยู่แล้ว = ข้าม
    scheduled_days = set()
    if not DRY and PAGE and TOK:
        try:
            sp = api("/%s/scheduled_posts" % PAGE, {"fields": "id,scheduled_publish_time", "limit": "100"})
            for p in sp.get("data", []):
                t = p.get("scheduled_publish_time", "")
                if t:
                    scheduled_days.add(str(t)[:10])
            print("[fb] existing scheduled days:", sorted(scheduled_days) or "-")
        except RuntimeError as e:
            print("[fb] scheduled_posts query FAIL — หยุดเพื่อความปลอดภัย (กันตั้งซ้ำ):", e)
            return 2

    now_th = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=7)))
    results = []
    for date in DATES:
        it = by[date]
        if unix_19th(date) <= int(now_th.timestamp()):
            results.append((date, "GAP past-date (19:00 ผ่านแล้ว) — ห้ามโพสต์ย้อนหลัง รายงานให้เจ้าของตัดสิน"))
            continue
        cap = it["captions"]["fb"]
        if not cap or "ข้อมูลเพื่อการศึกษา" not in cap:
            results.append((date, "FAIL caption missing/disclaimer")); continue
        if it["affiliate"] and "มีลิงก์พันธมิตร" not in cap:
            results.append((date, "FAIL affiliate marker missing")); continue
        if it["posted"].get("fb"):
            results.append((date, "SKIP already: %s" % str(it["posted"]["fb"])[:40])); continue
        if date in scheduled_days:
            results.append((date, "SKIP scheduled on FB already")); continue
        url = BASE + "/" + it["reel"]
        ts = unix_19th(date)
        if DRY:
            results.append((date, "DRY ok (url=%s ts=%d)" % (it["reel"], ts))); continue
        if not PAGE or not TOK:
            results.append((date, "BLOCKED no token")); continue
        try:
            r = api("/%s/videos" % PAGE, {"file_url": url, "description": cap,
                                          "published": "false", "scheduled_publish_time": str(ts)},
                    method="POST")
            vid = r.get("id", "")
            it["posted"]["fb"] = "scheduled %s 19:00+07:00 (video_id=%s)" % (date, vid)
            results.append((date, "SCHEDULED id=%s" % vid))
        except RuntimeError as e:
            results.append((date, "FAIL %s" % e))
            break  # หยุดทันทีตาม order — ไม่ retry รัว

    io.open(MANIFEST, "w", encoding="utf-8").write(json.dumps(man, ensure_ascii=False, indent=1))
    print("\n== FB batch2 (21-26) ==")
    ok = True
    for date, res in results:
        print("%s : %s" % (date, res))
        if res.startswith("FAIL"):
            ok = False
    print("(2026-07-20 = HARD-EXCLUDED — ไม่ถูกแตะ)")
    return 0 if ok else 2


if __name__ == "__main__":
    sys.exit(main())
