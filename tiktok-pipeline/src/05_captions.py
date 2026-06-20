#!/usr/bin/env python3
# 05_captions.py — clip_registry + rules (+ approved week1 seed) -> captions/<clip>.txt (compliant).
# week1-approved captions used verbatim; the rest template-generated (safe, no numbers) + 2-layer compliance.
# Optional: QWEN_API_KEY -> Qwen freshens hook/value per clip (fallback = template).
import argparse, re, sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
import config as C

DISC_BASE = "เนื้อหาเพื่อการศึกษา ไม่ใช่คำแนะนำเฉพาะบุคคล · มีลิงก์พันธมิตร · ผลิตด้วย AI"
DISC_INVEST = "เนื้อหาเพื่อการศึกษา ไม่ใช่คำแนะนำการลงทุน · การลงทุนมีความเสี่ยง · มีลิงก์พันธมิตร · ผลิตด้วย AI"
DISC_INS_EXTRA = " · การพิจารณา/เคลมเป็นไปตามเงื่อนไขบริษัทประกันที่ได้รับอนุญาตจาก คปภ."

# safe principle-based body (hook+value, NO numbers) for non-week1 clips
VALUE = {
  "vid_books":    "ความรู้การเงินดี ๆ เริ่มจากหนังสือไม่กี่เล่ม\nเลือกเล่มที่อ่านจบจริงและเอาไปใช้ได้ ไม่ต้องอ่านเยอะ",
  "vid_compound": "ยิ่งเริ่มออม/ลงทุนเร็ว ดอกเบี้ยทบต้นยิ่งทำงานแทนเรา\nเริ่มจากจำนวนที่ไหว ความสม่ำเสมอสำคัญกว่าก้อนใหญ่",
  "vid_docs":     "เอกสารครบตั้งแต่แรก ช่วยให้พิจารณาไวขึ้น\nเตรียมบัตรประชาชน + สลิป/เดินบัญชี ให้พร้อมก่อนยื่น",
  "vid_em":       "เงินสำรองคือกันชนเวลาฉุกเฉิน จะได้ไม่ต้องกู้ดอกแพง\nเริ่มเก็บทีละน้อยในบัญชีที่ถอนง่าย แยกจากเงินใช้",
  "vid_freelance":"ฟรีแลนซ์ไม่มีสลิปก็สมัครบัตรได้ ถ้าเดินบัญชีสม่ำเสมอ\nเตรียมหลักฐานรายได้ย้อนหลังให้พร้อม",
  "vid_index":    "กองทุนดัชนีคือการกระจายความเสี่ยงแบบต้นทุนต่ำ\nศึกษาความเสี่ยงและค่าธรรมเนียมก่อนทุกครั้ง",
  "vid_install0": "ผ่อน 0% คุ้มถ้าจ่ายครบตามงวดและไม่กดเงินสด\nอ่านเงื่อนไขร้าน/บัตรก่อนรูดทุกครั้ง",
  "vid_insure":   "ประกันคือการโอนความเสี่ยง เลือกตามความเสี่ยงจริงของเรา\nอ่านข้อยกเว้นและเทียบก่อนซื้อ",
  "vid_invest2":  "ลงทุนต่อยอดได้เมื่อเข้าใจความเสี่ยงของแต่ละสินทรัพย์\nกระจายความเสี่ยง อย่าทุ่มที่เดียว",
  "vid_retire":   "วางแผนเกษียณ ยิ่งเริ่มเร็วยิ่งสบายปลายทาง\nเริ่มจากกันเงินส่วนหนึ่งทุกเดือนแบบอัตโนมัติ",
  "vid_salary15k":"เงินเดือนถึงเกณฑ์ก็สมัครบัตรใบแรกได้\nเลือกใบที่เกณฑ์ไม่สูงและตรงการใช้จ่ายจริง",
  "vid_side":     "รายได้เสริมช่วยเร่งเป้าหมายการเงินให้ถึงไวขึ้น\nเลือกงานที่ทำต่อเนื่องได้ ไม่กระทบงานหลัก",
}
HASH = {
  "vid_books": ["#หนังสือการเงิน", "#ความรู้การเงิน", "#พัฒนาตัวเอง"],
  "vid_compound": ["#ดอกเบี้ยทบต้น", "#ออมเงิน", "#วางแผนการเงิน"],
  "vid_docs": ["#สินเชื่อ", "#เอกสารสมัคร", "#ขอสินเชื่อ"],
  "vid_em": ["#เงินสำรองฉุกเฉิน", "#ออมเงิน", "#เก็บเงิน"],
  "vid_freelance": ["#ฟรีแลนซ์", "#บัตรเครดิต", "#อาชีพอิสระ"],
  "vid_index": ["#กองทุนรวม", "#ลงทุน", "#DCA"],
  "vid_install0": ["#ผ่อน0", "#บัตรเครดิต", "#ผ่อนสินค้า"],
  "vid_insure": ["#ประกัน", "#ประกันภัย", "#วางแผนการเงิน"],
  "vid_invest2": ["#ลงทุน", "#กระจายความเสี่ยง", "#มือใหม่ลงทุน"],
  "vid_retire": ["#วางแผนเกษียณ", "#ออมเงิน", "#กองทุน"],
  "vid_salary15k": ["#บัตรเครดิต", "#เงินเดือน15000", "#บัตรใบแรก"],
  "vid_side": ["#รายได้เสริม", "#หาเงิน", "#งานเสริม"],
}

def disclosure(stem, slug):
    invest = any(k in stem for k in ("invest", "index", "retire", "compound", "tax")) or slug == "/quiz"
    ins = "insure" in stem or slug in ("/insurance-compare-2026", "/travel-insurance-vacation-2026")
    d = DISC_INVEST if invest else DISC_BASE
    return d + (DISC_INS_EXTRA if ins else "")

def template_caption(reg):
    stem = pathlib.Path(reg["clip"]).stem
    body = VALUE.get(stem, f"{reg['topic_th']}\nเข้าใจหลักการก่อนตัดสินใจ ตัวเลขจริงเช็กล่าสุดเสมอ")
    cta = "เทียบแบบไม่ขายฝัน 👉 ลิงก์ในโปรไฟล์" if reg["cta"] == "bio" else "กดติดตามไว้ + เซฟโพสต์นี้"
    tags = HASH.get(stem, ["#การวางแผนการเงิน", "#ออมเงิน", "#ลงทุน"]) + ["#มนุษย์เงินเดือน", "#การเงิน"]
    return f"{body}\n{cta}\n\n{disclosure(stem, reg['article_slug'])}\n" + " ".join(tags)

def audit(text, rules):
    flags = []
    for w in rules["forbidden"]:
        if w in text:
            flags.append(f"คำต้องห้าม: {w}")
    if re.search(rules["url_pattern"], text):
        flags.append("พบ URL/ลิงก์ในแคปชัน")
    if "เพื่อการศึกษา" not in text or "ลิงก์พันธมิตร" not in text or "AI" not in text:
        flags.append("disclosure ไม่ครบ")
    return sorted(set(flags))

def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--dry-run", action="store_true"); a = ap.parse_args()
    reg = C.jload(C.ROOT / "clip_registry.json"); rules = C.jload(C.ROOT / "compliance_rules.json")
    approved = {}
    wk = C.INPUT / "week1_captions.json"
    if wk.exists():
        approved = {c["clip"]: c["caption"] for c in C.jload(wk)}
    use_llm = (not a.dry_run) and C.HAS_KEY
    report = ["# 🛡️ Caption Generation + Compliance", ""]
    npass = 0
    for r in reg:
        clip = r["clip"]
        src = "approved(week1)"
        if clip in approved:
            cap = approved[clip]
        else:
            cap = template_caption(r); src = "template"
            if use_llm:
                try:
                    sysp = "แต่ง caption TikTok การเงินไทยให้สด ไม่ขายฝัน · ห้ามตัวเลข/URL/คำการันตี · คงโครง hook+value+CTA+disclosure+hashtag · คืนข้อความ caption ล้วน."
                    cand = C.qwen_chat(sysp, cap, temperature=0.7).strip()
                    if cand and not audit(cand, rules):
                        cap = cand; src = "qwen"
                except Exception as e:
                    report.append(f"  - ⚠️ {clip}: Qwen ล้มเหลว ({e}) → template")
        # auto-replace fixable forbidden, then re-audit
        for wbad, good in rules["replacements"].items():
            cap = cap.replace(wbad, good)
        flags = audit(cap, rules)
        r["claims_flagged"] = flags
        ok = len(flags) == 0
        npass += ok
        (C.CAPTIONS / f"{pathlib.Path(clip).stem}.txt").write_text(cap + "\n", encoding="utf-8")
        report.append(f"- {'✅' if ok else '❌'} **{clip}** ({src}, {r['cta']})" + ("" if ok else " — " + "; ".join(flags)))
    C.jsave(C.ROOT / "clip_registry.json", reg)   # write back claims_flagged
    report.insert(1, f"_{len(reg)} clips · ผ่าน {npass}/{len(reg)} · mode: {'qwen' if use_llm else 'template/approved'}_\n")
    pathlib.Path(C.DRAFTS / "captions_report.md").write_text("\n".join(report) + "\n", encoding="utf-8")
    print(f"[05_captions] {npass}/{len(reg)} PASS → captions/*.txt (+ drafts/captions_report.md)")

if __name__ == "__main__":
    main()
