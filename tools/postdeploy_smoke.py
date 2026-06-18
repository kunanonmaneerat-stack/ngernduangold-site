#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""postdeploy_smoke — auto-verify affiliate buttons / sub_id / rel / GA4 / og / no-linktr
across every page. กัน flow คลิกทำเงินพังเงียบเวลาแก้เว็บ. stdlib only.

MODES
  --src DIR    ตรวจ HTML ที่ build แล้วในเครื่อง (เช่น --src site) = BUILD-TIME GATE.
               exit code != 0 ถ้ามี fail → Netlify deploy ล้ม → เวอร์ชันพังไม่ขึ้น live.
  --live       fetch หน้า live จริงจาก sitemap.xml = DAILY RE-CHECK.
OPTIONS
  --report [PATH]      เขียนรายงาน markdown (default automation-log/smoke-latest.md)
  --telegram-on-fail   ยิง Telegram เฉพาะตอน fail (ผ่านเงียบ)

ASSERT ต่อปุ่ม a[href*=atth.me]: rel มี sponsored+nofollow+noopener · data-provider อยู่ใน canon ·
  href มี campaign code · utm_content = channel_page_provider (lowercase, provider in canon)
ASSERT ต่อหน้า: GA4 G-17PPE0M1B8 + 'affiliate_click' · og:image + og:title · 0 linktr.ee
(หมายเหตุ: การ build sub_id ตอน ?utm_source=test เป็น runtime JS — ตรวจระดับ runtime ด้วย Playwright แยก
 ดู postdeploy_click_test.py; สคริปต์นี้ตรวจ static ingredients ครบ)
"""
import os, re, sys, argparse, datetime, urllib.request
from html import unescape

# Windows console may be cp874 (Thai) and crash on emoji — force UTF-8, never raise.
for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

GA_ID = "G-17PPE0M1B8"
CANON = {"krungsri", "kept", "srisawad", "carforcash", "ktcphboom",
         "happycash", "ktcproud", "refinance", "loan",
         "scbprotect", "scb", "anc", "tuneprotect", "msig", "thanachart", "fwd", "viriyah"}
BASE = "https://ngernduangold.netlify.app"
HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)

def _attrs(tag):
    return {m.group(1).lower(): m.group(2)
            for m in re.finditer(r'([\w-]+)\s*=\s*"([^"]*)"', tag)}

def check_page(html):
    """return (button_count, [fail strings])"""
    fails, btn = [], 0
    if html.startswith("__FETCH_FAIL__"):
        return 0, ["fetch ล้ม: " + html[:80]]
    if re.search(r"linktr", html, re.I):
        fails.append("พบ linktr.ee/Linktree")
    if GA_ID not in html:
        fails.append("ไม่พบ GA4 " + GA_ID)
    if "affiliate_click" not in html:
        fails.append("ไม่พบ event 'affiliate_click'")
    if "og:image" not in html:
        fails.append("ไม่มี og:image")
    if "og:title" not in html:
        fails.append("ไม่มี og:title")
    for tag in re.findall(r"<a\b[^>]*>", html):
        if "atth.me" not in tag:
            continue
        btn += 1
        a = _attrs(tag)
        href = unescape(a.get("href", ""))
        rel = a.get("rel", "").lower()
        m = re.search(r"atth\.me/([0-9A-Za-z]+)", href)
        code = m.group(1) if m else "?"
        if not m:
            fails.append("ปุ่ม atth.me href ว่าง/ไม่มี code: " + href[:40]); continue
        for need in ("sponsored", "nofollow", "noopener"):
            if need not in rel:
                fails.append("ปุ่ม %s ขาด rel '%s'" % (code, need))
        prov = a.get("data-provider", "")
        if not prov:
            fails.append("ปุ่ม %s ไม่มี data-provider" % code)
        elif prov not in CANON:
            fails.append("ปุ่ม %s data-provider '%s' ไม่อยู่ใน canon" % (code, prov))
        uc = re.search(r"utm_content=([^&\"']+)", href)
        if not uc:
            fails.append("ปุ่ม %s ไม่มี utm_content (sub_id)" % code)
        else:
            sub = uc.group(1)
            parts = sub.split("_")
            if sub != sub.lower():
                fails.append("sub_id ไม่ lowercase: " + sub)
            if len(parts) < 3 or parts[-1] not in CANON:
                fails.append("sub_id format ผิด (channel_page_provider, provider in canon): " + sub)
    return btn, fails

def pages_local(src):
    out = {}
    for fn in sorted(os.listdir(src)):
        if not fn.endswith(".html"):
            continue
        content = open(os.path.join(src, fn), encoding="utf-8", errors="replace").read()
        if content.startswith("google-site-verification:"):
            continue  # GSC ownership token, not a content page (sitemap/--live exclude it too)
        out[fn] = content
    return out

def pages_live():
    sm = urllib.request.urlopen(BASE + "/sitemap.xml", timeout=25).read().decode("utf-8", "replace")
    out = {}
    for u in re.findall(r"<loc>([^<]+)</loc>", sm):
        try:
            req = urllib.request.Request(u, headers={"User-Agent": "ngernduangold-smoke"})
            out[u] = urllib.request.urlopen(req, timeout=25).read().decode("utf-8", "replace")
        except Exception as e:
            out[u] = "__FETCH_FAIL__ %s" % e
    return out

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src")
    ap.add_argument("--live", action="store_true")
    ap.add_argument("--report", nargs="?", const=os.path.join(REPO, "automation-log", "smoke-latest.md"))
    ap.add_argument("--telegram-on-fail", action="store_true")
    a = ap.parse_args()

    if a.live:
        pages, mode = pages_live(), "LIVE"
    elif a.src:
        pages, mode = pages_local(a.src), "BUILD(%s)" % a.src
    else:
        print("usage: --src DIR | --live"); sys.exit(2)

    total_btn, passed, results = 0, 0, []
    for name, html in pages.items():
        btn, fails = check_page(html)
        total_btn += btn
        if not fails:
            passed += 1
        results.append((name, btn, fails))

    n = len(pages)
    ok = (passed == n)
    head = "%s/%d หน้าผ่าน · ปุ่ม atth.me รวม %d ตัว · %s" % (
        passed, n, total_btn, "✅ PASS" if ok else "❌ FAIL")
    print("🧪 smoke check [%s] — %s" % (mode, head))
    for name, btn, fails in results:
        if fails:
            print("  ❌ %s (%d ปุ่ม): %s" % (name, btn, " | ".join(fails)))

    if a.report:
        ts = datetime.datetime.now(datetime.timezone.utc).astimezone().isoformat(timespec="seconds")
        lines = ["# 🧪 smoke check ล่าสุด", "", "_%s · %s · %s_" % (ts, mode, head), ""]
        for name, btn, fails in results:
            lines.append("- %s **%s** (%d ปุ่ม)%s" % (
                "✅" if not fails else "❌", name, btn,
                "" if not fails else " — " + "; ".join(fails)))
        os.makedirs(os.path.dirname(a.report), exist_ok=True)
        open(a.report, "w", encoding="utf-8").write("\n".join(lines) + "\n")
        print("report ->", a.report)

    if not ok and a.telegram_on_fail:
        try:
            sys.path.insert(0, os.path.join(REPO, "automation-log"))
            import telegram_notify
            bad = [n for n, _, f in results if f]
            telegram_notify.notify("🧪 SMOKE FAIL [%s] %s\nหน้าที่พัง: %s" % (mode, head, ", ".join(bad)[:300]))
        except Exception as e:
            sys.stderr.write("telegram skip: %s\n" % e)

    sys.exit(0 if ok else 1)

if __name__ == "__main__":
    main()
