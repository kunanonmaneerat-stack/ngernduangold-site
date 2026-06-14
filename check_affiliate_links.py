# -*- coding: utf-8 -*-
"""Affiliate link health check for ngernduangold.
Parses every atth.me affiliate link out of build_site.py and verifies each still
resolves (follows redirects, expects HTTP 200). Exit code 1 if any link is broken
so it can gate a scheduled alert. Run:  python check_affiliate_links.py
"""
import re, sys, urllib.request, urllib.error

SRC = "build_site.py"
try:
    src = open(SRC, encoding="utf-8").read()
except FileNotFoundError:
    print("ERR: run this from the outputs/ folder (build_site.py not found)"); sys.exit(2)

links = sorted(set(re.findall(r"https://atth\.me/[0-9A-Za-z]+", src)))
if not links:
    print("WARN: no atth.me links found in build_site.py"); sys.exit(2)

bad = []
for u in links:
    try:
        req = urllib.request.Request(u, headers={"User-Agent": "Mozilla/5.0 (ngernduangold link-health)"})
        r = urllib.request.urlopen(req, timeout=20)
        code, final = r.getcode(), r.geturl()
        ok = code == 200  # atth.me responds 200 then redirects client-side; 200 = alive, 404/410/5xx = dead
        print(("OK   " if ok else "WARN ") + f"{u} -> {code} {final}")
        if not ok:
            bad.append((u, code, final))
    except urllib.error.HTTPError as e:
        print(f"DEAD {u} -> HTTP {e.code}"); bad.append((u, e.code, ""))
    except Exception as e:
        print(f"ERR  {u} -> {type(e).__name__}: {str(e)[:120]}"); bad.append((u, "ERR", str(e)[:120]))

print(f"\nchecked {len(links)} affiliate links — {len(bad)} problem(s)")
if bad:
    print("PROBLEM LINKS:")
    for u, c, f in bad:
        print(f"  - {u}  ({c})")
sys.exit(1 if bad else 0)
