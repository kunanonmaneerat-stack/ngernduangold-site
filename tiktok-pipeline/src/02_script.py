#!/usr/bin/env python3
# 02_script.py — topics -> TikTok scripts (35-50s timecoded + 3 hooks). Qwen / fallback template.
import argparse, sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
import config as C

SCRIPT_PROMPT = """คุณคือนักเขียนสคริปต์ TikTok การเงินไทย สไตล์มนุษย์เงินเดือนตัวจริง ไม่ขายฝัน.
สร้างสคริปต์คลิปสั้น 35-50 วินาที/หัวข้อ — โครง: Hook 0-3วิ (หยุดนิ้ว/ชี้กับดัก) → กลาง 3-40วิ (อธิบายเชิงหลักการ/เทียบ) → CTA 5วิ ("ดูเช็กลิสต์เต็มในไบโอ").
สไตล์: no-face, kinetic text (onscreen) + TTS ไทย (tts).
ข้อห้าม: ห้ามใส่ URL/ลิงก์ใน onscreen หรือ tts (ลิงก์อยู่ bio เท่านั้น) · ห้ามแต่งตัวเลข/เบี้ย/ดอก/สถิติ — ถ้าพูดตัวเลขให้พูดเชิงหลักการหรือเติม "เช็กล่าสุด".
เอาต์พุต JSON array (1 ออบเจ็กต์/หัวข้อ ห้ามมีข้อความอื่น):
[{"clip_id":"tt-001","topic_th":"...","article_slug":"/...","length_sec":42,"hook_variants":["..3วิ..","..",".."],"script":[{"t":"0-3","onscreen":"...","tts":"..."}],"visual_style":"kinetic-text-navy-gold","music_mood":"calm-corporate"}]"""

def fallback(topics):
    out = []
    for i, t in enumerate(topics):
        topic = t["topic_th"]
        h = topic if "?" in topic else topic + " — กับดักที่หลายคนมองข้าม"
        scr = [
            {"t": "0-3",   "onscreen": h[:42], "tts": h},
            {"t": "3-12",  "onscreen": "ปัญหานี้มนุษย์เงินเดือนเจอบ่อย", "tts": f"เรื่องนี้เจอกันเยอะมาก โดยเฉพาะคน{t.get('audience','ทำงานประจำ')}"},
            {"t": "12-30", "onscreen": "เทียบเชิงหลักการ — ตัวเลขจริงเช็กล่าสุด", "tts": "ลองดูหลักการเทียบก่อนตัดสินใจ ตัวเลขจริงเปลี่ยนได้ ให้เช็กล่าสุดเสมอ"},
            {"t": "30-40", "onscreen": "เลือกตามสถานการณ์ของคุณ", "tts": "เลือกแบบที่ตรงกับการใช้งานจริงของคุณ ไม่ใช่ทุกคนเหมือนกัน"},
            {"t": "40-45", "onscreen": "เช็กลิสต์เต็ม + ตัวช่วยเทียบ — ลิงก์ในไบโอ", "tts": "ดูเช็กลิสต์เต็มและตัวช่วยเทียบได้ที่ลิงก์ในไบโอ"},
        ]
        out.append({"clip_id": f"tt-{i+1:03d}", "topic_th": topic, "article_slug": t["article_slug"], "length_sec": 45,
                    "hook_variants": [h, f"สิ่งที่แบงก์ไม่ค่อยบอก: {topic[:28]}", "ก่อนตัดสินใจเรื่องนี้ ดูให้จบใน 40 วิ"],
                    "script": scr, "visual_style": "kinetic-text-navy-gold", "music_mood": "calm-corporate",
                    "affiliate_angle": t.get("affiliate_angle", ""), "target_emotion": t.get("target_emotion", "")})
    return out

def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--dry-run", action="store_true"); a = ap.parse_args()
    topics = C.jload(C.DRAFTS / "topics.json")
    use_llm = C.gate(a.dry_run)
    if use_llm:
        try:
            scripts = C.extract_json(C.qwen_chat(SCRIPT_PROMPT, C.json.dumps(topics, ensure_ascii=False, indent=2), temperature=0.6))
            for i, s in enumerate(scripts):
                s.setdefault("clip_id", f"tt-{i+1:03d}")
        except Exception as e:
            print(f"[02] Qwen ล้มเหลว ({e}) → fallback"); scripts = fallback(topics)
    else:
        scripts = fallback(topics)
    C.jsave(C.DRAFTS / "scripts.json", scripts)
    print(f"[02_script] {'LLM' if use_llm else 'dry-run/fallback'} → {len(scripts)} scripts → drafts/scripts.json")

if __name__ == "__main__":
    main()
