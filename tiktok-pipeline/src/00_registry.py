#!/usr/bin/env python3
# 00_registry.py — scan CLIPS_DIR for vid_*.mp4 -> clip_registry.json (source of truth).
# topic_th + article_slug inferred per clip; duration via ffprobe (real). cta: bio=product/convert, follow=educational.
import argparse, json, subprocess, sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
import config as C

# stem -> (topic_th, article_slug, cta). slugs are real pages on the site. unknown clips default to /quiz + follow.
META = {
    "vid_credit":     ("บัตรเครดิตคืนเงิน เลือกให้คุ้ม",      "/credit-card-cashback-2026",        "bio"),
    "vid_salary15k":  ("เงินเดือน 15,000 สมัครบัตรให้ผ่าน",   "/credit-card-salary-15000-2026",    "bio"),
    "vid_easyapprove":("เพิ่มโอกาสอนุมัติบัตร/สินเชื่อ",       "/credit-card-easy-approval-2026",   "bio"),
    "vid_score":      ("เครดิตสกอร์/เครดิตบูโร เข้าใจง่าย",    "/krungsri-credit-card-rejected-2026","follow"),
    "vid_docs":       ("เอกสารสมัครบัตร/สินเชื่อ เตรียมอะไร",  "/credit-card-documents-2026",       "bio"),
    "vid_freelance":  ("ฟรีแลนซ์สมัครบัตรเครดิตยังไง",         "/credit-card-freelance-2026",       "bio"),
    "vid_install0":   ("ผ่อน 0% ใช้ให้คุ้ม ไม่เสียดอก",        "/credit-card-installment-0-2026",   "bio"),
    "vid_debt":       ("ปลดหนี้บัตรหลายใบ รวมเป็นก้อนเดียว",   "/debt-consolidation-2026",          "follow"),
    "vid_insure":     ("ประกันที่มนุษย์เงินเดือนควรรู้",        "/insurance-compare-2026",           "bio"),
    "vid_em":         ("เงินสำรองฉุกเฉิน ควรมีกี่เดือน",        "/emergency-fund-2026",              "follow"),
    "vid_save":       ("ออมเงินให้อยู่ เงินเดือนน้อยก็เก็บได้", "/how-to-save-money-2026",           "follow"),
    "vid_compound":   ("ดอกเบี้ยทบต้น พลังของการออมยาว",       "/high-yield-savings-2026",          "follow"),
    "vid_invest":     ("เริ่มลงทุนต้องเริ่มยังไง",              "/quiz",                             "follow"),
    "vid_invest2":    ("ลงทุนต่อยอด เข้าใจความเสี่ยงก่อน",      "/quiz",                             "follow"),
    "vid_index":      ("กองทุนดัชนีคืออะไร เริ่มยังไง",         "/quiz",                             "follow"),
    "vid_retire":     ("วางแผนเกษียณ เริ่มเร็วได้เปรียบ",       "/quiz",                             "follow"),
    "vid_tax":        ("วางแผนภาษีสิ้นปี ใช้สิทธิลดหย่อน",      "/quiz",                             "follow"),
    "vid_books":      ("หนังสือการเงินน่าอ่านสำหรับมือใหม่",    "/how-to-save-money-2026",           "follow"),
    "vid_side":       ("รายได้เสริมมนุษย์เงินเดือน",            "/how-to-save-money-2026",           "follow"),
}

def duration(path):
    try:
        out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
                             capture_output=True, text=True, timeout=30)
        return round(float(out.stdout.strip()), 1)
    except Exception:
        return None

def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--clips-dir", default=None); a = ap.parse_args()
    cdir = pathlib.Path(a.clips_dir) if a.clips_dir else C.CLIPS_DIR
    clips = sorted(cdir.glob("vid_*.mp4")) if cdir.exists() else []
    if not clips:
        print(f"[00_registry] ไม่พบ vid_*.mp4 ใน {cdir} — ตั้ง TIKTOK_CLIPS_DIR หรือ --clips-dir ให้ชี้คลังคลิป (Cowork outputs)")
    reg = []
    for p in clips:
        stem = p.stem
        topic, slug, cta = META.get(stem, (stem.replace("vid_", "").replace("_", " "), "/quiz", "follow"))
        reg.append({"clip": p.name, "topic_th": topic, "article_slug": slug,
                    "bio_utm": "?utm_source=tiktok&utm_medium=bio", "cta": cta,
                    "caption_file": f"captions/{stem}.txt", "status": "ready",
                    "duration_s": duration(p), "claims_flagged": []})
    C.jsave(C.ROOT / "clip_registry.json", reg)
    print(f"[00_registry] {len(reg)} clips -> clip_registry.json (bio={sum(1 for r in reg if r['cta']=='bio')} / follow={sum(1 for r in reg if r['cta']=='follow')})")

if __name__ == "__main__":
    main()
