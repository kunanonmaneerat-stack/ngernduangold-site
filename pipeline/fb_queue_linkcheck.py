#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""fb_queue_linkcheck — daily link-health for the FB/Threads queue destinations
(order-flow-fb-master-20260702 งาน B1). Run BEFORE 08:00 each queue day.

Checks every destination page used by QUEUE_fb-threads (first-comment links) returns
HTTP 200 with real content. Writes automation-log/cowork-inbox/linkhealth-fb-<date>.md.
Any non-200 -> file is flagged ⚠️ + exit 1 so a wrapper/cron can alert. stdlib only, $0.
"""
import os, sys, datetime, urllib.request, urllib.error
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUTDIR = os.path.join(ROOT, "automation-log", "cowork-inbox")
BASE = "https://ngernduangold.com"
# ทุกหน้าปลายทางในคิว FB 2-8 ก.ค. (เช็กทั้งชุดทุกวัน — กันสลับวัน/แก้คิว)
PAGES = ["/title-loan-2026.html", "/kept-savings-2026.html", "/debt-consolidation-2026.html",
         "/emergency-fund-2026.html", "/credit-bureau-check-2026.html",
         "/park-money-high-interest-2026.html", "/links"]


def check(url):
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "ngernduangold-fbqueue-linkcheck"})
        r = urllib.request.urlopen(req, timeout=20)
        body = r.read(4096).decode("utf-8", "replace")
        ok = (r.status == 200) and ("<h1" in body or "<title" in body)
        return r.status, ok
    except urllib.error.HTTPError as e:
        return e.code, False
    except Exception as e:
        return "ERR:" + str(e)[:60], False


def main():
    today = datetime.date.today().isoformat()
    rows, bad = [], []
    for p in PAGES:
        st, ok = check(BASE + p)
        rows.append((p, st, ok))
        if not ok:
            bad.append((p, st))
    os.makedirs(OUTDIR, exist_ok=True)
    out = os.path.join(OUTDIR, "linkhealth-fb-%s.md" % today)
    L = ["# %s FB-queue link-health — %s" % ("⚠️ มีลิงก์พัง!" if bad else "✅", today),
         "> ยิงก่อน 08:00 กันโพสต์ลิงก์ตาย (order-flow-fb-master งาน B1) · เช็กทุกหน้าปลายทางในคิว", ""]
    for p, st, ok in rows:
        L.append("- %s `%s` -> %s" % ("✅" if ok else "❌", p, st))
    if bad:
        L += ["", "**อย่าโพสต์ลิงก์ที่ ❌ วันนี้ — แจ้ง CC/เจ้าของแก้ก่อน**"]
    open(out, "w", encoding="utf-8").write("\n".join(L) + "\n")
    print(("FAIL %d broken" % len(bad) if bad else "OK all %d pages 200" % len(rows)), "->", out)
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
