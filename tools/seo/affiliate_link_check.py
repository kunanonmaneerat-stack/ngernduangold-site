#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# affiliate_link_check.py — WO-4 (2026-07-12): affiliate link + disclosure health scanner
#
# สแกน BUILT pages (site/*.html = สิ่งที่ผู้ใช้เห็นจริง) หา outbound affiliate link:
#   - atth.me (AccessTrade ทุก format รวม /go/ short) และ internal /go/* (301 -> atth.me)
# เช็กต่อลิงก์: rel มี "sponsored" ไหม · หน้าเดียวกันมี disclosure "มีลิงก์พันธมิตร" ไหม
# option --http: HEAD ลิงก์ unique เช็ก 200/redirect/dead (ใช้ UA จริง กัน 403)
# ออกรายงาน: automation-log/AFFILIATE-HEALTH.md (ตาราง: หน้า | ลิงก์ | rel | disclosure | HTTP)
# Exit: 0 = ทุกลิงก์ครบ rel+disclosure (HTTP fail ไม่ทำ exit เพราะเป็น transient — ดูรายงาน)
#       1 = มีลิงก์ขาด rel หรือหน้าขาด disclosure
import io, os, re, sys, argparse, ssl, urllib.request, urllib.error, datetime

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SITE = os.path.join(ROOT, "site")
OUT = os.path.join(ROOT, "automation-log", "AFFILIATE-HEALTH.md")
WINNERS = {"kept-savings-2026.html", "debt-calculator.html", "links.html",
           "title-loan-2026.html", "debt-consolidation-2026.html"}

A_TAG = re.compile(r"<a\s[^>]*>", re.I | re.S)
HREF = re.compile(r'href="([^"]+)"', re.I)
REL = re.compile(r'rel="([^"]*)"', re.I)


def is_affiliate(href):
    return "atth.me" in href or href.startswith("/go/")


def http_head(url, cache, ctx):
    if url in cache:
        return cache[url]
    try:
        req = urllib.request.Request(url, method="HEAD", headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=25, context=ctx) as r:
            cache[url] = str(r.status)
    except urllib.error.HTTPError as e:
        cache[url] = "HTTP %d" % e.code
    except Exception as e:
        cache[url] = "ERR " + str(e)[:40]
    return cache[url]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--http", action="store_true", help="HEAD-check unique links")
    a = ap.parse_args()
    if not os.path.isdir(SITE):
        print("site/ not built — run build_site.py first")
        return 1
    ctx = ssl.create_default_context()
    cache = {}
    rows, problems = [], []
    pages = sorted(f for f in os.listdir(SITE) if f.endswith(".html") and not f.startswith("google"))
    for fn in pages:
        h = io.open(os.path.join(SITE, fn), encoding="utf-8").read()
        disclosure = "มีลิงก์พันธมิตร" in h or "ลิงก์พันธมิตร (affiliate)" in h
        for tag in A_TAG.findall(h):
            m = HREF.search(tag)
            if not m or not is_affiliate(m.group(1)):
                continue
            href = m.group(1)
            relm = REL.search(tag)
            rel_ok = bool(relm and "sponsored" in relm.group(1))
            status = ""
            if a.http:
                url = href if href.startswith("http") else "https://ngernduangold.com" + href
                status = http_head(url, cache, ctx)
            rows.append((fn, href, rel_ok, disclosure, status))
            if not rel_ok:
                problems.append("%s: %s ขาด rel=sponsored" % (fn, href[:60]))
            if not disclosure:
                problems.append("%s: หน้าไม่มี disclosure 'มีลิงก์พันธมิตร'" % fn)

    covered = {fn for fn, *_ in rows}
    lines = ["# AFFILIATE HEALTH — %s" % datetime.date.today().isoformat(), "",
             "สแกน built pages %d หน้า · เจอลิงก์ affiliate %d จุด (%d ลิงก์ unique) · winner ครอบคลุม: %s" % (
                 len(pages), len(rows), len({r[1] for r in rows}),
                 ", ".join(sorted(w for w in WINNERS if w in covered)) or "-"), ""]
    if a.http:
        lines.append("โหมด --http: เช็ก HEAD ลิงก์ unique แล้ว")
    lines += ["", "| หน้า | ลิงก์ | rel=sponsored | disclosure ในหน้า | HTTP |", "|---|---|---|---|---|"]
    for fn, href, rel_ok, disc, status in rows:
        lines.append("| %s | `%s` | %s | %s | %s |" % (
            fn, href[:58], "✅" if rel_ok else "❌", "✅" if disc else "❌", status or "-"))
    lines += ["", "## ปัญหา (%d)" % len(problems)]
    lines += ["- " + p for p in problems] or ["- ไม่มี — ทุกลิงก์มี rel=sponsored + disclosure ครบ"]
    miss_w = sorted(WINNERS - covered - {"debt-calculator.html"})
    if miss_w:
        lines += ["", "หมายเหตุ: winner ที่ไม่มีลิงก์ affiliate ตรง ๆ ในหน้า: %s (โดยดีไซน์ เช่น calculator ใช้หน้ากลาง)" % ", ".join(miss_w)]
    io.open(OUT, "w", encoding="utf-8").write(chr(10).join(lines) + chr(10))
    print("report -> %s | links %d | problems %d" % (OUT, len(rows), len(problems)))
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
