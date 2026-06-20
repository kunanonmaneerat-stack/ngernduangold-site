#!/usr/bin/env python3
# verify_captions.py — independent compliance check for a TikTok caption pack (Cowork-authored).
# Checks each caption: (1) no forbidden claim word, (2) no URL/link in caption (bio-only rule),
# (3) disclosure present (educational + affiliate + AI), (4) investment/tax risk line if applicable.
# Usage: python src/verify_captions.py [--file input/week1_captions.json]
import argparse, re, sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
import config as C

def check(cap, rules):
    flags = []
    text = cap["caption"]
    # 1) forbidden claim words
    for w in rules["forbidden"]:
        if w in text:
            flags.append(f"คำต้องห้าม: {w}")
    # 2) URL in caption (exclude the non-URL Thai phrases "ลิงก์ในโปรไฟล์/ไบโอ")
    if re.search(rules["url_pattern"], text):
        flags.append("พบ URL/ลิงก์ในแคปชัน (ต้อง bio-only)")
    # 3) disclosure present
    low = text
    if "เพื่อการศึกษา" not in low:
        flags.append("ขาด disclosure: เพื่อการศึกษา")
    if "ลิงก์พันธมิตร" not in low:
        flags.append("ขาด disclosure: มีลิงก์พันธมิตร")
    if " AI" not in low and "ผลิตด้วย AI" not in low:
        flags.append("ขาด disclosure: ผลิตด้วย AI")
    # 4) investment/tax topics need risk line
    t = (cap.get("topic", "") + cap.get("id", ""))
    if any(k in t for k in ("ลงทุน", "invest", "ภาษี", "tax")):
        if ("ความเสี่ยง" not in text) and ("มีเงื่อนไข" not in text):
            flags.append("หัวข้อลงทุน/ภาษี ควรมี 'ความเสี่ยง/มีเงื่อนไข'")
    return sorted(set(flags))

def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--file", default="input/week1_captions.json"); a = ap.parse_args()
    caps = C.jload(C.ROOT / a.file); rules = C.jload(C.ROOT / "compliance_rules.json")
    rows, npass = [], 0
    for cap in caps:
        fl = check(cap, rules)
        ok = len(fl) == 0
        npass += ok
        rows.append((cap["id"], cap.get("day"), cap.get("cta"), ok, fl))
        print(f"  {'✅' if ok else '❌'} day{cap.get('day')} {cap['id']} ({cap.get('cta')})" + ("" if ok else " — " + "; ".join(fl)))
    print(f"[verify_captions] {npass}/{len(caps)} PASS")
    # report
    rep = ["# 🛡️ Caption Compliance Verify", "", f"_{a.file} · ผ่าน {npass}/{len(caps)}_", ""]
    for cid, d, cta, ok, fl in rows:
        rep.append(f"- {'✅ PASS' if ok else '❌ FAIL'} · day{d} `{cid}` (CTA={cta})" + ("" if ok else " — " + "; ".join(fl)))
    pathlib.Path(C.DRAFTS / "caption_verify_report.md").write_text("\n".join(rep) + "\n", encoding="utf-8")
    sys.exit(0 if npass == len(caps) else 1)

if __name__ == "__main__":
    main()
