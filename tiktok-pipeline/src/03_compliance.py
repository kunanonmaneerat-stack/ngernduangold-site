#!/usr/bin/env python3
# 03_compliance.py — 2-layer audit: (a) rule/regex (always) + (b) Qwen rewrite (if key).
# Outputs scripts_clean.json (+ compliance_pass/flags per clip) and compliance_report.md.
import argparse, re, sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
import config as C

def _texts(clip):
    out = list(clip.get("hook_variants", []))
    for s in clip.get("script", []):
        out += [s.get("onscreen", ""), s.get("tts", "")]
    return out

def audit_one(clip, rules):
    forb = rules["forbidden"]; repl = rules["replacements"]
    urlp = re.compile(rules["url_pattern"]); nump = re.compile(rules["number_claim_pattern"])
    flags = []

    def fix(s):
        for w in forb:
            if w in s:
                s = s.replace(w, repl[w]) if w in repl else s  # keep; residual check flags it
        return s

    clip["hook_variants"] = [fix(x) for x in clip.get("hook_variants", [])]
    for seg in clip.get("script", []):
        seg["onscreen"] = fix(seg.get("onscreen", "")); seg["tts"] = fix(seg.get("tts", ""))

    # hard rule: no URL/link in onscreen or tts
    for seg in clip.get("script", []):
        if urlp.search(seg.get("onscreen", "")) or urlp.search(seg.get("tts", "")):
            flags.append(f"พบ URL/ลิงก์ใน segment {seg.get('t','')}")
    # residual forbidden anywhere
    blob = " ".join(_texts(clip))
    for w in forb:
        if w in blob:
            flags.append(f"ยังพบคำต้องห้าม: {w}")
    # soft: number-claims need human source-check (does NOT fail; legal facts like ThaiESG 30% are ok)
    nums = sorted(set(m.group(0) for seg in clip.get("script", []) for m in nump.finditer(seg.get("onscreen", "") + " " + seg.get("tts", ""))))
    clip["number_warnings"] = [f"เช็กแหล่งตัวเลข: {n}" for n in nums]

    ins = ("ประกัน" in clip.get("affiliate_angle", "")) or clip.get("article_slug") in ("/insurance-compare-2026", "/travel-insurance-vacation-2026")
    clip["disclosure"] = rules["required_disclosure"] + (" · " + rules["insurance_extra"] if ins else "")
    clip["flags"] = sorted(set(flags))
    clip["compliance_pass"] = len(clip["flags"]) == 0
    return clip

def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--dry-run", action="store_true"); a = ap.parse_args()
    scripts = C.jload(C.DRAFTS / "scripts.json"); rules = C.jload(C.ROOT / "compliance_rules.json")
    use_llm = (not a.dry_run) and C.HAS_KEY   # regex always runs; LLM only rewrites flagged clips
    clean, report = [], ["# 🛡️ Compliance Report", ""]
    for clip in scripts:
        clip = audit_one(clip, rules)
        if clip["flags"] and use_llm:
            try:
                sysp = "แก้สคริปต์ TikTok การเงินไทยให้ผ่าน compliance: ลบคำการันตี/ตัวเลขไม่มีแหล่ง/URL ออก คงโครงเดิม. คืน JSON object เดิมเท่านั้น."
                clip = audit_one(C.extract_json(C.qwen_chat(sysp, C.json.dumps(clip, ensure_ascii=False))), rules)
            except Exception as e:
                report.append(f"- ⚠️ {clip.get('clip_id')}: Qwen rewrite ล้มเหลว ({e}) — คงสถานะ rule-based")
        mark = "✅ PASS" if clip["compliance_pass"] else "❌ FAIL"
        nw = f" · ⚠️เช็กตัวเลข {len(clip['number_warnings'])}" if clip.get("number_warnings") else ""
        report.append(f"- **{clip.get('clip_id')}** {mark} — {clip.get('topic_th')}" + ("" if clip["compliance_pass"] else " · flags: " + "; ".join(clip["flags"])) + nw)
        clean.append(clip)
    npass = sum(1 for c in clean if c["compliance_pass"])
    report.insert(1, f"_{len(clean)} clips · mode: {'LLM-rewrite' if use_llm else 'rule-based'} · **ผ่าน {npass}/{len(clean)}** (เฉพาะ PASS ส่งต่อ manifest)_\n")
    C.jsave(C.DRAFTS / "scripts_clean.json", clean)
    pathlib.Path(C.DRAFTS / "compliance_report.md").write_text("\n".join(report) + "\n", encoding="utf-8")
    print(f"[03_compliance] {'LLM' if use_llm else 'rule-based'} → {npass}/{len(clean)} PASS → drafts/scripts_clean.json + compliance_report.md")

if __name__ == "__main__":
    main()
