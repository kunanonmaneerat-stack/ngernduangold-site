#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# validate.py — control-plane validator (WO-2, 2026-07-12)
# เช็ก content_manifest.json:
#   1) affiliate:true -> disclosure + แคปชันทุกช่องที่ไม่ว่างต้องมี "มีลิงก์พันธมิตร"
#   2) reel path ต้องมีจริง "เมื่อ status เลย Approved ไปแล้ว" (Rendered/Scheduled/Posted)
#      — Approved/Idea = ยังไม่ render ได้ (batch2) แค่เตือน ไม่ fail
#   3) ทุกแคปชันที่ไม่ว่างต้องมี "ข้อมูลเพื่อการศึกษา" + ไม่มี bare % + ไม่มี URL ใน tiktok caption
# Exit 0 = ผ่าน · 1 = พลาด
import io, os, sys, json, re

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MANIFEST = os.path.join(os.path.dirname(os.path.abspath(__file__)), "content_manifest.json")

NEED_FILE = {"Rendered", "Scheduled", "Posted"}


def main():
    data = json.load(io.open(MANIFEST, encoding="utf-8"))
    errs, warns = [], []
    for it in data["items"]:
        iid = it["id"]
        caps = {k: v for k, v in it["captions"].items() if v}
        if it.get("affiliate"):
            # regex + negative lookbehind: 'ไม่มีลิงก์พันธมิตร' ต้องไม่ผ่านเป็น disclosure
            _has = lambda t: re.search("(?<!ไม่)มีลิงก์พันธมิตร", t or "") is not None
            if not _has(it.get("disclosure", "")):
                errs.append("%s: affiliate=true แต่ disclosure ไม่มี 'มีลิงก์พันธมิตร'" % iid)
            for ch, c in caps.items():
                if not _has(c):
                    errs.append("%s: caption[%s] ขาด 'มีลิงก์พันธมิตร'" % (iid, ch))
        reel = os.path.join(ROOT, it["reel"])
        if it["status"] in NEED_FILE and not os.path.exists(reel):
            errs.append("%s: status=%s แต่ reel ไม่มีจริง: %s" % (iid, it["status"], it["reel"]))
        elif it["status"] not in NEED_FILE and not os.path.exists(reel):
            warns.append("%s: reel ยังไม่ render (%s) — status=%s ok" % (iid, it["reel"], it["status"]))
        for ch, c in caps.items():
            if "ข้อมูลเพื่อการศึกษา" not in c:
                errs.append("%s: caption[%s] ขาด disclaimer" % (iid, ch))
            if re.search(r"\d+\s*%", c):
                errs.append("%s: caption[%s] มี bare %%" % (iid, ch))
        if "ngernduangold.com" in caps.get("tiktok", ""):
            errs.append("%s: tiktok caption มี URL (ต้อง 'ลิงก์ในไบโอ')" % iid)
    for w in warns:
        print("WARN  " + w)
    for e in errs:
        print("ERROR " + e)
    print("validate: %d items | %d error | %d warn -> %s" % (
        len(data["items"]), len(errs), len(warns), "FAIL" if errs else "PASS"))
    return 1 if errs else 0


if __name__ == "__main__":
    sys.exit(main())
