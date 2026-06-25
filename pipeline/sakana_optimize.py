"""sakana_optimize.py — Evolutionary content optimizer (Gemini idea #5) ด้วย Sakana Fugu.

อ่าน winner จริงจาก automation-log/ga4-pages.csv (หน้าที่ convert ได้)
-> ให้ Sakana Fugu เจน Threads post variants ใหม่ (comply-safe, ไทย)
-> เขียน pipeline/article-posts-sakana.json (รีวิว/ตั้งคิวต่อด้วย postiz_article_scheduler.py --file ... --go)

ปลอดภัย: เจน "ดราฟต์" เท่านั้น ไม่โพสต์เอง · ยึด ธปท/กลต/คปภ ไม่ใช้คำการันตี
ต้องรันบนเครื่องที่เข้าเน็ตได้ (เช่น ผ่าน Desktop Commander) เพราะเรียก api.sakana.ai
ใช้:  py pipeline/sakana_optimize.py            (เจน)
      py pipeline/sakana_optimize.py --topn 3 --variants 2
"""
import os, sys, csv, json, time, urllib.request, urllib.error, datetime

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
PAGES = os.path.join(ROOT, "automation-log", "ga4-pages.csv")
OUT = os.path.join(ROOT, "pipeline", "article-posts-sakana.json")
BASE = "https://ngernduangold.netlify.app/"
API = "https://api.sakana.ai/v1/chat/completions"
MODEL = os.environ.get("SAKANA_MODEL", "fugu")
UTILITY = {"/", "/index.html", "/contact", "/about", "/disclaimer", "/privacy",
           "/quiz", "/quiz.html", "/links", "/links.html"}

SYS = ("คุณเป็นนักเขียนโพสต์ Threads การเงินไทยสาย comply-safe ของเว็บ 'เงินเดือนสมองทอง'. "
       "กฎเด็ดขาด: ห้ามใช้คำการันตี (เช่น อนุมัติแน่นอน/การันตีผลตอบแทน/กู้ผ่านชัวร์); "
       "ใช้คำแบบ 'มีโอกาส/ช่วง/ทั่วไป'; ยึดแนวทาง ธปท./กลต./คปภ.; เป็นข้อมูลเพื่อการศึกษา ไม่ใช่คำแนะนำ. "
       "เขียนกระชับ มี hook สะดุดใน 1 บรรทัดแรก แล้วคุณค่า 1-2 บรรทัด.")


def get_key():
    k = os.environ.get("SAKANA_API_KEY")
    if k:
        return k.strip()
    p = os.path.join(ROOT, "secrets", "sakana-key.txt")
    return open(p, encoding="utf-8").read().strip() if os.path.exists(p) else None


def topic(slug):
    s = slug.split("?")[0].strip("/").replace(".html", "").replace("-2026", "")
    return s.replace("-", " ")


def url(slug):
    s = slug.split("?")[0].strip("/")
    return f"{BASE}{s}?utm_source=threads&utm_medium=social&utm_content={s}"


def fugu(key, user, tries=4):
    body = json.dumps({"model": MODEL, "messages": [
        {"role": "system", "content": SYS}, {"role": "user", "content": user}]}).encode("utf-8")
    last = None
    for i in range(tries):
        try:
            req = urllib.request.Request(API, data=body, method="POST", headers={
                "Content-Type": "application/json", "Authorization": "Bearer " + key})
            with urllib.request.urlopen(req, timeout=180) as r:
                d = json.loads(r.read().decode("utf-8"))
            return d["choices"][0]["message"]["content"]
        except urllib.error.HTTPError as e:
            last = e
            if e.code == 429 and i < tries - 1:
                time.sleep(15 * (i + 1)); continue
            raise
    raise last


def main():
    args = sys.argv[1:]
    def opt(n, dv):
        return args[args.index(n) + 1] if n in args else dv
    topn = int(opt("--topn", 3)); variants = int(opt("--variants", 2))
    key = get_key()
    if not key:
        print("[!] ไม่มี Sakana key (secrets/sakana-key.txt หรือ env SAKANA_API_KEY)"); return
    if not os.path.exists(PAGES):
        print("[!] ยังไม่มี ga4-pages.csv — รัน ga4_pull.py ก่อน (run_weekly)"); return

    rows = list(csv.DictReader(open(PAGES, encoding="utf-8")))
    winners = []
    for r in rows:
        p = (r.get("page") or "").split("?")[0]
        try:
            conv = int(float(r.get("conversion", 0) or 0))
        except Exception:
            conv = 0
        if conv > 0 and p not in UTILITY and p not in ("/",):
            winners.append((p, conv))
    winners.sort(key=lambda x: -x[1])
    winners = winners[:topn]
    if not winners:
        print("[i] ยังไม่มีหน้า winner (conversion>0) — รอ traffic/loop เก็บข้อมูลก่อน"); return

    posts = []
    for slug, conv in winners:
        t = topic(slug); u = url(slug)
        prompt = (f"หัวข้อบทความที่ 'แปลงผลได้จริง' (มีคนคลิกสมัคร): {t}\n"
                  f"ลิงก์บทความ: {u}\n\n"
                  f"เขียนโพสต์ Threads ภาษาไทยใหม่ {variants} เวอร์ชัน (คนละมุม/hook) เพื่อดึงคนเข้าบทความนี้ซ้ำ. "
                  f"แต่ละโพสต์: hook 1 บรรทัด + คุณค่า + ใส่ลิงก์ + 3 แฮชแท็กไทย. "
                  f"ตอบกลับเป็น JSON array ของสตริงเท่านั้น (เช่น [\"โพสต์1...\",\"โพสต์2...\"]) ไม่ต้องมีคำอธิบายอื่น.")
        try:
            out = fugu(key, prompt)
        except Exception as e:
            print("  [x] %s -> Fugu error: %s" % (t, e)); continue
        # parse JSON array (เผื่อมี markdown fence)
        txt = out.strip()
        if "```" in txt:
            txt = txt.split("```")[1].replace("json", "", 1).strip() if txt.count("```") >= 2 else txt
        try:
            arr = json.loads(txt[txt.index("["):txt.rindex("]") + 1])
        except Exception:
            arr = [out.strip()]
        for i, content in enumerate(arr[:variants], 1):
            posts.append({"topic": f"{t}-fugu{i}", "content": content})
        print("  [ok] %s -> %d variants" % (t, min(len(arr), variants)))
        time.sleep(8)

    cfg = {"channel": "threads", "hour_ict": 15, "per_day": 1,
           "note": "Sakana Fugu optimizer — variants ของหน้า winner (double-down). รีวิวก่อน --go",
           "generated": datetime.datetime.now().isoformat(timespec="seconds"), "posts": posts}
    json.dump(cfg, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print("เขียน %s | %d โพสต์ จาก %d winner (model=%s)" % (OUT, len(posts), len(winners), MODEL))
    print("ตั้งคิว: py pipeline\\postiz_article_scheduler.py --file pipeline\\article-posts-sakana.json --go")


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    main()
