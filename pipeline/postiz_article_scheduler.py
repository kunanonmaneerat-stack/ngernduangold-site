"""postiz_article_scheduler.py — ยิงบทความเข้า Postiz ตั้งเวลาอัตโนมัติ (ผ่าน Public API)
อ่าน pipeline/article-posts.json + Postiz API key -> หา integration (ช่อง) -> ตั้งเวลากระจายวันละ N โพสต์
ปลอดภัย: DEFAULT = --dry-run (พรีวิวเฉย ๆ ไม่ยิง). ต้องใส่ --go ถึงจะยิงจริง (เจ้าของยืนยัน)
API: POST https://api.postiz.com/public/v1/posts  (Authorization: <key>)
key: env POSTIZ_API_KEY หรือไฟล์ secrets/postiz-key.txt (gitignored)
ใช้:  py pipeline/postiz_article_scheduler.py            # พรีวิว
      py pipeline/postiz_article_scheduler.py --go       # ยิงจริง (ตั้งเวลา)
      py pipeline/postiz_article_scheduler.py --go --channel threads --per-day 1 --hour 19
"""
import os, sys, json, datetime, urllib.request, urllib.error
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BASE = "https://api.postiz.com/public/v1"
CFG  = os.path.join(ROOT, "pipeline", "article-posts.json")
KEYF = os.path.join(ROOT, "secrets", "postiz-key.txt")
ICT  = datetime.timezone(datetime.timedelta(hours=7))

def get_key():
    k = os.environ.get("POSTIZ_API_KEY", "").strip()
    if not k and os.path.exists(KEYF):
        k = open(KEYF, encoding="utf-8").read().strip()
    return k

def api(path, key, method="GET", body=None):
    url = BASE + path
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Authorization", key)
    if data: req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status, json.loads(r.read().decode("utf-8") or "null")
    except urllib.error.HTTPError as e:
        return e.code, (e.read().decode("utf-8")[:300] if e.fp else str(e))
    except Exception as e:
        return 0, str(e)

def find_integration(integrations, channel):
    # match by provider/identifier == channel (e.g. "threads")
    for it in integrations or []:
        ident = str(it.get("identifier") or it.get("provider") or it.get("providerIdentifier") or "").lower()
        if ident == channel.lower():
            return it
    # fallback: substring
    for it in integrations or []:
        blob = json.dumps(it).lower()
        if channel.lower() in blob:
            return it
    return None

def main():
    args = sys.argv[1:]
    go = "--go" in args
    def opt(name, default):
        if name in args:
            try: return args[args.index(name)+1]
            except Exception: return default
        return default
    cfg_path = opt("--file", CFG)
    cfg = json.load(open(cfg_path, encoding="utf-8"))
    channel = opt("--channel", cfg.get("channel", "threads"))
    per_day = int(opt("--per-day", cfg.get("per_day", 1)))
    hour    = int(opt("--hour", cfg.get("hour_ict", 19)))
    posts   = cfg["posts"]

    # schedule dates: เริ่มพรุ่งนี้ เวลา hour:00 ICT, วันละ per_day โพสต์
    start = (datetime.datetime.now(ICT) + datetime.timedelta(days=1)).replace(hour=hour, minute=0, second=0, microsecond=0)
    dates = []
    slot = 0
    for i in range(len(posts)):
        d = start + datetime.timedelta(days=(i // per_day))
        # ถ้าหลายโพสต์/วัน ค่อยๆเลื่อนชั่วโมง
        d = d.replace(hour=hour + (i % per_day)*2)
        dates.append(d)
    print("=== Postiz article scheduler ===")
    print("channel=%s · per_day=%d · hour=%02d:00 ICT · posts=%d" % (channel, per_day, hour, len(posts)))

    key = get_key()
    if not key:
        print("\n[!] ยังไม่มี Postiz API key (env POSTIZ_API_KEY หรือ secrets/postiz-key.txt)")
        print("    ออก key: Postiz > Settings > Developers > Public API > Generate\n")
    integ = None
    if key:
        st, ints = api("/integrations", key)
        if st == 200 and isinstance(ints, list):
            integ = find_integration(ints, channel)
            print("integrations พบ %d ช่อง · เลือก: %s" % (len(ints), (integ or {}).get("name","<ไม่พบ %s>"%channel)))
        else:
            print("[!] /integrations error %s: %s" % (st, ints))

    print("\n--- แผนตั้งเวลา ---")
    for i, p in enumerate(posts):
        print("%2d. %s · %s" % (i+1, dates[i].strftime("%a %d/%m %H:%M ICT"), p["topic"]))

    if not go:
        print("\n[DRY-RUN] ยังไม่ยิง — เพิ่ม --go เพื่อตั้งเวลาจริง (ต้องมี key + integration)")
        return
    if not key or not integ:
        print("\n[STOP] ยิงไม่ได้: ขาด key หรือหา integration ไม่เจอ"); return

    iid = integ.get("id")
    ok = 0
    for i, p in enumerate(posts):
        date_utc = dates[i].astimezone(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")
        body = {"type":"schedule","date":date_utc,"shortLink":False,"tags":[],
                "posts":[{"integration":{"id":iid},
                          "value":[{"content":p["content"],"image":[]}],
                          "settings":{"__type":channel}}]}
        st, resp = api("/posts", key, "POST", body)
        tag = "OK" if st in (200,201) else "ERR %s"%st
        print("  [%s] %s @ %s" % (tag, p["topic"], date_utc))
        if st in (200,201): ok += 1
    print("\nเสร็จ: ตั้งเวลาสำเร็จ %d/%d โพสต์ -> ดูใน Postiz Calendar" % (ok, len(posts)))

if __name__ == "__main__":
    main()
