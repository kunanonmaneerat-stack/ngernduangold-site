#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# publish_tiktok.py — TikTok Studio uploader ผ่าน Playwright (order MASTER 2026-07-11)
#
# ⚠️ สถานะ: ทดลอง (experimental) — TikTok ไม่มี organic API สำหรับบัญชีทั่วไป; ตัวนี้ขับหน้า
#   TikTok Studio ด้วยเบราว์เซอร์จริง + persistent profile ที่ "เจ้าของ login เองครั้งเดียว"
#   ไม่มี/ห้ามใส่เทคนิคหลบ bot-detection ใด ๆ (ตามคำสั่ง) — ถ้า TikTok บล็อกให้สลับ fallback semi-auto
#
# โหมด:
#   python publish_tiktok.py --login            เปิดเบราว์เซอร์ให้เจ้าของ login (session ค้างใน .tiktok-profile/)
#   python publish_tiktok.py --check            ตรวจว่า session ยัง login อยู่ + เปิดหน้า upload ได้ (ไม่โพสต์)
#   python publish_tiktok.py [--date YYYY-MM-DD] [--live]
#       default = DRY RUN: ทำทุกขั้นถึง "พร้อมกดโพสต์" แล้วถ่าย screenshot หยุด (ไม่กด Post)
#       --live  = กด Post จริง (ใช้ตอนทดสอบ 1 คลิปแรก และใน scheduled task หลังผ่านเทส)
#
# Exit: 0 = ok/skip · 2 = fail (เขียน alert + screenshot ไว้ที่ logs/)
import io, os, sys, json, time, datetime, argparse

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
PROFILE = os.path.join(HERE, ".tiktok-profile")          # gitignored — session/cookies ห้าม commit
LOGS = os.path.join(HERE, "logs")                        # gitignored
CONTENT_MAP = os.path.join(HERE, "content_map.json")
PUBLISHED = os.path.join(LOGS, "published-tiktok.json")
ALERT = os.path.join(ROOT, "automation-log", "cowork-inbox", "TIKTOK-PUBLISH-FAIL.md")
UPLOAD_URL = "https://www.tiktok.com/tiktokstudio/upload"

# selectors รวมไว้ที่เดียว — TikTok เปลี่ยน UI บ่อย แก้ตรงนี้จุดเดียว (ดู runbook §selector)
SEL = {
    "file_input": 'input[type="file"]',
    "caption_editor": 'div[contenteditable="true"]',
    "post_button": 'button[data-e2e="post_video_button"], button:has-text("Post"), button:has-text("โพสต์")',
    "upload_done_hint": 'div:has-text("Uploaded"), span:has-text("Uploaded"), [data-e2e="upload_done"]',
    "ai_label_section": 'div:has-text("AI-generated content")',
    "ai_label_switch": 'div:has-text("AI-generated content") input[type="checkbox"], '
                       'div:has-text("AI-generated content") [role="switch"]',
}


def now_th():
    return datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=7)


def log(msg):
    print("[tiktok] " + msg)


def fail(msg, page=None, date=""):
    log("FAIL: " + msg)
    os.makedirs(LOGS, exist_ok=True)
    shot = ""
    if page is not None:
        shot = os.path.join(LOGS, "fail-%s.png" % now_th().strftime("%Y%m%d-%H%M%S"))
        try:
            page.screenshot(path=shot, full_page=True)
            log("screenshot -> " + shot)
        except Exception:
            shot = "(screenshot failed)"
    os.makedirs(os.path.dirname(ALERT), exist_ok=True)
    io.open(ALERT, "w", encoding="utf-8").write(
        "# TIKTOK PUBLISH FAIL — %s\n\n- date: %s\n- error: %s\n- screenshot: %s\n"
        "- ถ้าโดนบล็อก/หน้าเปลี่ยน: ดู social-autopost/runbook.md (§TikTok selector / §fallback semi-auto)\n"
        % (now_th().strftime("%Y-%m-%d %H:%M"), date, msg, shot))
    sys.exit(2)


def launch(p, headed=True):
    os.makedirs(PROFILE, exist_ok=True)
    # เบราว์เซอร์ตรง ๆ ไม่แต่ง fingerprint/stealth — นโยบาย: ไม่ทำ evasion
    return p.chromium.launch_persistent_context(
        PROFILE, headless=not headed, viewport={"width": 1280, "height": 860},
        args=["--disable-blink-features=AutomationControlled"] if False else [])


def logged_in(page):
    page.goto(UPLOAD_URL, wait_until="domcontentloaded", timeout=60000)
    page.wait_for_timeout(5000)
    return "login" not in page.url


def mode_login(p):
    ctx = launch(p, headed=True)
    page = ctx.new_page()
    page.goto("https://www.tiktok.com/login", wait_until="domcontentloaded", timeout=60000)
    log("เบราว์เซอร์เปิดแล้ว — login บัญชี TikTok ของแบรนด์ให้เสร็จ แล้วปิดหน้าต่างนี้ (session จะถูกจำไว้)")
    try:
        page.wait_for_event("close", timeout=600000)   # รอเจ้าของปิดเอง (สูงสุด 10 นาที)
    except Exception:
        pass
    ctx.close()
    log("login mode จบ — รัน --check เพื่อยืนยัน")
    return 0


def mode_check(p):
    ctx = launch(p, headed=True)
    page = ctx.new_page()
    ok = logged_in(page)
    if ok:
        log("CHECK OK: session ใช้ได้ เปิดหน้า upload ได้ (%s)" % page.url)
    else:
        log("CHECK FAIL: ยังไม่ได้ login (โดน redirect ไป %s) — รัน --login ก่อน" % page.url)
    ctx.close()
    return 0 if ok else 2


def mode_post(p, date, live):
    cmap = json.load(io.open(CONTENT_MAP, encoding="utf-8"))
    entry = cmap.get(date)
    if not entry:
        log("no content_map entry for %s — ต้องเติม batch (last=%s)" % (date, max(cmap)))
        return 0
    os.makedirs(LOGS, exist_ok=True)
    pub = json.load(io.open(PUBLISHED, encoding="utf-8")) if os.path.exists(PUBLISHED) else {}
    if date in pub:
        log("already posted %s — skip (dedup)" % date)
        return 0
    clip = os.path.join(ROOT, "reels", entry["clipFile"])
    if not os.path.exists(clip):
        fail("clip not found: %s" % clip, date=date)
    caption = entry["tiktokCaption"]
    if "ข้อมูลเพื่อการศึกษา" not in caption or "ผลิตด้วย AI" not in caption:
        fail("caption missing disclaimer/AI disclosure — refuse to post", date=date)

    ctx = launch(p, headed=True)
    page = ctx.new_page()
    try:
        if not logged_in(page):
            fail("session หลุด — รัน --login ใหม่", page, date)
        log("upload page OK: " + page.url)

        page.set_input_files(SEL["file_input"], clip)
        log("file set: " + os.path.basename(clip))
        # รออัปโหลด/ประมวลผล (ไฟล์ ~2MB ปกติไม่นาน แต่เผื่อ 3 นาที)
        try:
            page.wait_for_selector(SEL["upload_done_hint"], timeout=180000)
        except Exception:
            page.wait_for_timeout(20000)   # บาง UI ไม่มีข้อความ Uploaded — ให้เวลาเพิ่มแล้วไปต่อ
        log("upload processed")

        ed = page.locator(SEL["caption_editor"]).first
        ed.click()
        page.keyboard.press("Control+A")
        page.keyboard.press("Delete")
        ed.type(caption, delay=15)
        log("caption typed (%d chars)" % len(caption))

        # AI-generated label: TikTok toggle ได้ — พยายามเปิด ถ้าหา switch ไม่เจอไม่ถือว่า fail
        try:
            sec = page.locator(SEL["ai_label_section"]).first
            sec.scroll_into_view_if_needed(timeout=5000)
            sw = page.locator(SEL["ai_label_switch"]).first
            state = sw.get_attribute("aria-checked") or sw.get_attribute("checked") or ""
            if state in ("false", "", None):
                sw.click()
                log("AI-generated label: toggled ON")
            else:
                log("AI-generated label: already ON")
        except Exception as e:
            log("AI label switch not found (%s) — พึ่งคำ 'ผลิตด้วย AI' ในแคปชัน (มีแล้ว) + แจ้งใน log" % e)

        shot = os.path.join(LOGS, "ready-%s.png" % date)
        page.screenshot(path=shot, full_page=True)
        log("pre-post screenshot -> " + shot)

        if not live:
            log("DRY RUN — ทุกขั้นพร้อมโพสต์แล้ว แต่ไม่กด Post (ใช้ --live เพื่อโพสต์จริง)")
            ctx.close()
            return 0

        page.locator(SEL["post_button"]).first.click()
        log("Post clicked — รอผล")
        page.wait_for_timeout(15000)
        shot2 = os.path.join(LOGS, "posted-%s.png" % date)
        page.screenshot(path=shot2, full_page=True)
        pub[date] = {"file": entry["clipFile"], "ts": now_th().strftime("%Y-%m-%d %H:%M:%S+07:00"),
                     "screenshot": shot2}
        io.open(PUBLISHED, "w", encoding="utf-8").write(json.dumps(pub, ensure_ascii=False, indent=1))
        log("POSTED %s (ยืนยันบนแอป/Studio อีกครั้ง + screenshot: %s)" % (date, shot2))
        ctx.close()
        return 0
    except SystemExit:
        raise
    except Exception as e:
        fail("unexpected: %s" % e, page, date)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--login", action="store_true")
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--live", action="store_true")
    ap.add_argument("--date", default="")
    a = ap.parse_args()
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        if a.login:
            return mode_login(p)
        if a.check:
            return mode_check(p)
        date = a.date or now_th().strftime("%Y-%m-%d")
        return mode_post(p, date, a.live)


if __name__ == "__main__":
    sys.exit(main())
