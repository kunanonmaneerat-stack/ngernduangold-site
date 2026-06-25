# -*- coding: utf-8 -*-
import io, re
P = "build_site.py"
src = io.open(P, encoding="utf-8").read()
# match href="/<slug>-2026"  (bare, no .html / # / ? after) -> add .html
pat = re.compile(r'href="(/[a-z0-9-]+-2026)"')
found = pat.findall(src)
print("fixing %d bare links:" % len(found), found)
src2 = pat.sub(r'href="\1.html"', src)
io.open(P, "w", encoding="utf-8").write(src2)
# verify none remain
left = pat.findall(src2)
print("remaining bare links:", len(left))
