#!/usr/bin/env python3
# 01_research.py — pain_seed -> ranked top-5 topics. Qwen 3.7 (primary) / deterministic fallback (--dry-run).
import argparse, re, sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
import config as C

RESEARCH_PROMPT = """คุณคือนักวางกลยุทธ์คอนเทนต์การเงินไทย จุดยืน "ไม่ขายฝัน".
อินพุต: รายการ pain point จริงจากผู้ใช้ (พร้อม source).
งาน: จัดอันดับ + เลือก 5 หัวข้อทำคลิป TikTok สั้นที่ "ใกล้ตัดสินใจ + payout สูง + ยังตอบน้อย".
กฎ: ห้ามแต่งตัวเลข/เบี้ย/ดอก/สถิติ ถ้าไม่มีในอินพุต ให้พูดเชิงหลักการแทน.
แต่ละหัวข้อ map กับ slug บทความจาก ARTICLE_MAP ที่ให้ (ใช้ slug ที่มีจริงเท่านั้น).
เอาต์พุตเป็น JSON array เท่านั้น (ห้ามมีข้อความอื่น):
[{"rank":1,"topic_th":"...","why_now":"...","target_emotion":"...","article_slug":"/...","affiliate_angle":"...","risk_notes":"..."}]"""

def _topic_from(seed):
    h = seed.get("hook_seed", "") or seed.get("pain_quote", "")
    t = re.split(r"[?:—]", h)[0].strip()
    return (t[:60] if t else seed.get("audience", "หัวข้อการเงิน"))

def fallback(seeds, amap):
    slugs = set(amap["map"].values())
    EMO = {"/debt-consolidation-2026": "ปลดทุกข์/เครียดหนี้", "/krungsri-credit-card-rejected-2026": "งง/กังวลโดนปฏิเสธ",
           "/credit-card-salary-15000-2026": "อยากผ่าน/ไม่มั่นใจ", "/high-yield-savings-2026": "กลัวเสียโอกาส", "/quiz": "เลือกไม่ถูก"}
    out = []
    for i, s in enumerate(seeds):
        slug = s.get("article_slug_guess", "/quiz")
        if slug not in slugs:
            slug = "/quiz"
        ins = ("ประกัน" in s.get("affiliate_angle", "")) or slug in ("/insurance-compare-2026", "/travel-insurance-vacation-2026")
        out.append({"rank": i + 1, "topic_th": _topic_from(s), "why_now": s.get("recurrence", "pain เกิดซ้ำบน Pantip"),
                    "target_emotion": EMO.get(slug, "ความกังวลทางการเงิน"), "article_slug": slug,
                    "affiliate_angle": s.get("affiliate_angle", ""),
                    "risk_notes": "ตัวเลขทุกตัวต้องเช็กล่าสุด ห้าม fabricate" + (" · ประกัน=ไม่การันตี (คปภ.)" if ins else "")})
    return out[:5]

def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--dry-run", action="store_true"); a = ap.parse_args()
    seeds = C.jload(C.INPUT / "pain_seed.json"); amap = C.jload(C.ROOT / "article_map.json")
    slugs = set(amap["map"].values())
    use_llm = C.gate(a.dry_run)
    if use_llm:
        try:
            user = f"ARTICLE_MAP slugs: {sorted(slugs)}\n\nPAIN SEED:\n{C.json.dumps(seeds, ensure_ascii=False, indent=2)}"
            topics = C.extract_json(C.qwen_chat(RESEARCH_PROMPT, user))
            for t in topics:
                if t.get("article_slug") not in slugs:
                    t["article_slug"] = "/quiz"
        except Exception as e:
            print(f"[01] Qwen ล้มเหลว ({e}) → ใช้ fallback"); topics = fallback(seeds, amap)
    else:
        topics = fallback(seeds, amap)
    C.jsave(C.DRAFTS / "topics.json", topics)
    print(f"[01_research] {'LLM' if use_llm else 'dry-run/fallback'} → {len(topics)} topics → drafts/topics.json")

if __name__ == "__main__":
    main()
