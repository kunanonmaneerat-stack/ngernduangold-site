#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""postdeploy_click_test — RUNTIME proof that affiliate_click fires + sub_id ถูกต้อง.

ยืนยันสิ่งที่ static smoke (postdeploy_smoke.py) ทำไม่ได้: โหลดหน้า live จริง →
wrap window.dataLayer.push → คลิกปุ่ม affiliate แรก → assert event 'affiliate_click'
ยิงจริง + sub_id/channel/provider ถูกตามพฤติกรรม JS จริง:
  /links?utm_source=test  → hub JS rewrite → channel=test, sub_id=test_links_{provider}
  article CTA (cta/go)    → ไม่ถูก rewrite → channel=website, sub_id=website_{page}_{provider}
(handler GA อ่าน sub_id=utm_content, channel=utm_source จาก a.href — build_site.py บรรทัด 14)

ต้องมี Playwright:  pip install playwright && python -m playwright install chromium
รัน:  python tools/postdeploy_click_test.py [--base URL] [--report] [--telegram-on-fail]
⚠️ ต้อง chromium → ไม่ใช่ build-gate/HTTP-only · รัน on-demand หรือ host ที่มี browser.
"""
import os, sys, re, argparse, datetime

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

CANON = {"krungsri", "kept", "srisawad", "carforcash", "ktcphboom",
         "happycash", "ktcproud", "refinance", "loan",
         "scbprotect", "scb", "axapa", "axamotor", "gettgo", "klook", "anc", "tuneprotect", "msig", "thanachart", "fwd", "viriyah"}
HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)

# (path, css selector, expected channel, expected sub_id prefix)
TARGETS = [
    ("/links?utm_source=test", 'a.hubbtn[href*="atth.me"]', "test", "test_"),
    ("/title-loan-2026", 'a[href*="atth.me"]', "website", "website_"),
    ("/credit-card-salary-15000-2026", 'a[href*="atth.me"]', "website", "website_"),
    ("/lifestyle-credit-card-2026", 'a[href*="atth.me"]', "lifestyle", "lifestyle_"),
    ("/insurance-compare-2026", 'a.go[href*="atth.me"]', "ins", "ins_"),
]

# wrap dataLayer.push BEFORE page scripts → จับ affiliate_click ทุกแบบ (gtag args หรือ dict)
WRAP = """
window.__aff = [];
window.__ev = [];
window.dataLayer = window.dataLayer || [];
var _p = window.dataLayer.push.bind(window.dataLayer);
window.dataLayer.push = function () {
  try {
    for (var i = 0; i < arguments.length; i++) {
      var a = arguments[i];
      if (a && (a[1] === 'affiliate_click' || a.event === 'affiliate_click'))
        window.__aff.push(a[2] || a);
      if (a && a[0] === 'event' && a[1]) window.__ev.push(a[1]);
    }
  } catch (e) {}
  return _p.apply(window.dataLayer, arguments);
};
"""

def _through_interstitial(page):
    """If the comparison interstitial modal opened (card/loan CTAs), click its continue button
    so the real affiliate_click fires on the original atth.me href (sub_id unchanged)."""
    try:
        cont = page.query_selector('#interstitial-continue')
        if cont and cont.is_visible():
            try:
                cont.click(timeout=4000, no_wait_after=True)
            except Exception:
                try: cont.evaluate("e => e.click()")
                except Exception: pass
            page.wait_for_timeout(300)
    except Exception:
        pass

def run(base, targets):
    from playwright.sync_api import sync_playwright
    results = []
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        for path, sel, exp_ch, exp_prefix in targets:
            fails, got = [], None
            ctx = browser.new_context()
            page = ctx.new_page()
            page.add_init_script(WRAP)
            page.route(re.compile(r"atth\.me"), lambda r: r.abort())  # ไม่โหลด affiliate จริง
            try:
                page.goto(base + path, wait_until="domcontentloaded", timeout=30000)
                page.wait_for_timeout(1500)            # ให้ GA + hub JS รัน/rewrite
                el = page.query_selector(sel)
                if not el:
                    fails.append("ไม่เจอปุ่ม %s" % sel)
                else:
                    try:
                        el.click(timeout=4000, no_wait_after=True)
                    except Exception:
                        try:
                            el.evaluate("e => e.click()")
                        except Exception:
                            pass
                    page.wait_for_timeout(400)
                    _through_interstitial(page)
                    aff = page.evaluate("() => window.__aff || []")
                    if not aff:
                        fails.append("affiliate_click ไม่ยิงหลังคลิก")
                    else:
                        got = aff[0]
                        sub = str(got.get("sub_id", ""))
                        ch = str(got.get("channel", ""))
                        prov = str(got.get("provider", ""))
                        parts = sub.split("_")
                        if sub != sub.lower():
                            fails.append("sub_id ไม่ lowercase: " + sub)
                        if len(parts) < 3 or parts[-1] not in CANON:
                            fails.append("sub_id format ผิด: " + sub)
                        if exp_ch and ch != exp_ch:
                            fails.append("channel ได้ '%s' คาด '%s'" % (ch, exp_ch))
                        if exp_prefix and not sub.startswith(exp_prefix):
                            fails.append("sub_id ขึ้นต้นผิด: '%s' คาด '%s...'" % (sub, exp_prefix))
                        if prov not in CANON:
                            fails.append("provider '%s' ไม่อยู่ใน canon" % prov)
            except Exception as e:
                fails.append("error: " + str(e)[:140])
            ctx.close()
            results.append((path, got, fails))
        browser.close()
    return results

def run_quiz(base, q1="urgent", q2="car"):
    """Drive /quiz: Q1 -> Q2 -> click result affiliate button.
    Assert affiliate_click fires with channel=quiz + sub_id quiz_* + quiz_start/complete events."""
    from playwright.sync_api import sync_playwright
    path, fails, got = "/quiz (%s->%s)" % (q1, q2), [], None
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        ctx = browser.new_context()
        page = ctx.new_page()
        page.add_init_script(WRAP)
        page.route(re.compile(r"atth\.me"), lambda r: r.abort())
        try:
            page.goto(base + "/quiz", wait_until="domcontentloaded", timeout=30000)
            page.wait_for_timeout(1200)
            page.click('[data-q1="%s"]' % q1, timeout=5000); page.wait_for_timeout(400)
            page.click('[data-q2="%s"]' % q2, timeout=5000); page.wait_for_timeout(500)
            el = page.query_selector('#quiz-result a.go[href*="atth.me"]')
            if not el:
                fails.append("ไม่เจอปุ่ม result affiliate หลังตอบ quiz")
            else:
                try:
                    el.click(timeout=4000, no_wait_after=True)
                except Exception:
                    try: el.evaluate("e => e.click()")
                    except Exception: pass
                page.wait_for_timeout(400)
                _through_interstitial(page)
                aff = page.evaluate("() => window.__aff || []")
                if not aff:
                    fails.append("affiliate_click ไม่ยิงหลังคลิก result")
                else:
                    got = aff[0]
                    sub, ch, prov = str(got.get("sub_id","")), str(got.get("channel","")), str(got.get("provider",""))
                    parts = sub.split("_")
                    if ch != "quiz": fails.append("channel ได้ '%s' คาด 'quiz'" % ch)
                    if not sub.startswith("quiz_"): fails.append("sub_id ไม่ขึ้นต้น quiz_: " + sub)
                    if len(parts) < 3 or parts[-1] not in CANON: fails.append("sub_id format ผิด: " + sub)
                    if prov not in CANON: fails.append("provider '%s' ไม่อยู่ใน canon" % prov)
            ev = page.evaluate("() => window.__ev || []")
            if "quiz_start" not in ev: fails.append("event quiz_start ไม่ยิง")
            if "quiz_complete" not in ev: fails.append("event quiz_complete ไม่ยิง")
        except Exception as e:
            fails.append("error: " + str(e)[:140])
        ctx.close()
        browser.close()
    return (path, got, fails)

def run_events(base):
    """Verify micro-conversion events fire: scroll_to_compare_table (scroll to .cmp) +
    view_conditions_click (open FAQ details)."""
    from playwright.sync_api import sync_playwright
    path, fails, got = "/title-loan-2026 (micro-events)", [], None
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        ctx = browser.new_context(); page = ctx.new_page()
        page.add_init_script(WRAP)
        page.route(re.compile(r"atth\.me"), lambda r: r.abort())
        try:
            page.goto(base + "/title-loan-2026", wait_until="domcontentloaded", timeout=30000)
            page.wait_for_timeout(1200)
            page.evaluate("() => { var e = document.querySelector('.cmp,.ctable'); if (e) e.scrollIntoView(); }")
            page.wait_for_timeout(600)
            s = page.query_selector('details summary')
            if s:
                try: s.click(timeout=4000)
                except Exception: pass
            page.wait_for_timeout(400)
            ev = page.evaluate("() => window.__ev || []")
            got = {"events": [e for e in ev if e in ("scroll_to_compare_table", "view_conditions_click")]}
            if "scroll_to_compare_table" not in ev: fails.append("scroll_to_compare_table ไม่ยิง")
            if "view_conditions_click" not in ev: fails.append("view_conditions_click ไม่ยิง")
        except Exception as e:
            fails.append("error: " + str(e)[:140])
        ctx.close(); browser.close()
    return (path, got, fails)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="https://ngernduangold.netlify.app")
    ap.add_argument("--report", nargs="?",
                    const=os.path.join(REPO, "automation-log", "clicktest-latest.md"))
    ap.add_argument("--telegram-on-fail", action="store_true")
    a = ap.parse_args()
    try:
        results = run(a.base, TARGETS)
        results.append(run_quiz(a.base))
        results.append(run_quiz(a.base, "protect", "travel"))
        results.append(run_quiz(a.base, "protect", "pa"))
        results.append(run_events(a.base))
    except ImportError:
        print("❌ Playwright ไม่ได้ติดตั้ง — `pip install playwright && python -m playwright install chromium`")
        sys.exit(2)

    npass = sum(1 for _, _, f in results if not f)
    ok = npass == len(results)
    head = "%d/%d หน้า runtime ผ่าน" % (npass, len(results))
    print("🖱️ click-test [%s] — %s · %s" % (a.base, head, "✅ PASS" if ok else "❌ FAIL"))
    for path, got, fails in results:
        info = ("sub_id=%s channel=%s" % (got.get("sub_id"), got.get("channel"))) if got else "no event"
        print("  %s %s — %s%s" % ("✅" if not fails else "❌", path, info,
                                  "" if not fails else " | " + " ; ".join(fails)))

    if a.report:
        ts = datetime.datetime.now(datetime.timezone.utc).astimezone().isoformat(timespec="seconds")
        L = ["# 🖱️ runtime click-test ล่าสุด", "", "_%s · %s · %s_" % (ts, a.base, head), ""]
        for path, got, fails in results:
            ev = ("sub_id=`%s` channel=`%s` provider=`%s`" % (
                got.get("sub_id"), got.get("channel"), got.get("provider"))) if got else "ไม่มี event"
            L.append("- %s **%s** — %s%s" % ("✅" if not fails else "❌", path, ev,
                                             "" if not fails else " — " + "; ".join(fails)))
        os.makedirs(os.path.dirname(a.report), exist_ok=True)
        open(a.report, "w", encoding="utf-8").write("\n".join(L) + "\n")
        print("report ->", a.report)

    if not ok and a.telegram_on_fail:
        try:
            sys.path.insert(0, os.path.join(REPO, "automation-log"))
            import telegram_notify
            telegram_notify.notify("🖱️ CLICK-TEST FAIL — %s\n%s" % (
                head, ", ".join(p for p, _, f in results if f)[:300]))
        except Exception as e:
            sys.stderr.write("tg skip: %s\n" % e)

    sys.exit(0 if ok else 1)

if __name__ == "__main__":
    main()
