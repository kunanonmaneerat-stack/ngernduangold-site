"""tiktok_video_creator.py — agent แปลง 'สคริปต์ TikTok' (จาก content_creators 'tiktok')
เป็น (ก) แผนถ่ายทำ shot-by-shot ถ่ายมือถือได้ + (ข) Google Flow / Veo prompts (อังกฤษ) สร้างคลิปจริง
รับข้อมูลจาก: content_creators.create('tiktok', topic) -> ส่งต่อ head_social_media · ผ่าน comply_gate
ใช้: py pipeline/tiktok_video_creator.py "หัวข้อ"
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import free_llm, comply_gate, content_creators

PERSONA = ("คุณเป็นโปรดิวเซอร์ TikTok สายการเงินไทย + เชี่ยวชาญ AI video (Google Flow/Veo) "
           "ทำคลิปไวรัลทุนต่ำ ฮุกแรงใน 3 วิ คปภ-safe — ออกได้ทั้งแผนถ่ายเองและ prompt ให้ Flow เจนคลิป")

SPEC = ("แปลงสคริปต์ TikTok ด้านล่างเป็น 2 ส่วน พร้อมใช้งานจริง:\n\n"
        "## ส่วน A — แผนถ่ายทำ (ถ่ายมือถือคนเดียวทุนต่ำ)\n"
        "ตารางช็อต (markdown): | # | เวลา(วิ) | ภาพ/มุมกล้อง | ข้อความบนจอ(ไทย) | บทพูด | b-roll |\n"
        "ความยาวรวม <= 30 วิ · ฮุก 3 วิแรกหยุดนิ้ว · บอกจังหวะตัด + แนวเพลงเทรนด์ (ไม่ระบุเพลงลิขสิทธิ์) "
        "+ ไอเดียปก(cover) + แคปชัน + 5 แฮชแท็ก (#fyp+การเงิน) + CTA คอมเมนต์ 'เช็กสิทธิ์'\n\n"
        "## ส่วน B — Google Flow / Veo prompts (สร้างคลิปด้วย AI)\n"
        "เขียน prompt **ภาษาอังกฤษ** 4-6 ตัว (คลิปละ ~6-8 วินาที) ก๊อปวางใน Google Flow ได้ทันที\n"
        "แต่ละ prompt ใส่: subject + action + setting + camera movement + lighting + mood + style "
        "และระบุ 'vertical 9:16, cinematic, realistic' เสมอ\n"
        "ห้ามใส่ตัวหนังสือ/ข้อความใน prompt (Veo เรนเดอร์ตัวอักษรไม่ชัด — ใส่ข้อความไทยตอนตัดต่อแทน) · "
        "เป็นภาพคน/บรรยากาศ/วัตถุประกอบ (ไม่อ้างอิงดารา/แบรนด์/โลโก้จริง) · "
        "ปิดท้ายบอกวิธีต่อคลิปใน Flow Scenebuilder + ใส่ข้อความไทย+เสียงพากย์ทีหลัง\n\n"
        "เขียนเป็นเนื้อจริงเลย ห้ามมีคำนำ")


def create(topic, script="", extra=""):
    if not script:
        script = (content_creators.create("tiktok", topic, extra) or {}).get("content", "")
    prompt = ("หัวข้อ: " + topic + "\n\n[สคริปต์ TikTok ที่ได้รับจาก tiktok creator]\n" +
              (script or "(ไม่มีสคริปต์)") + "\n\n" + SPEC +
              "\n\n[กฎความถูกต้อง-เนื้อหาไทย] " + comply_gate.RULE +
              "\n[ห้าม hallucinate] ห้ามแต่งชื่อธนาคาร/ผลิตภัณฑ์/ตัวเลขเฉพาะที่อาจไม่จริง พูดภาพรวม/ช่วงกว้าง บอกให้เช็กหน้าทางการ")
    t, m = free_llm.generate(prompt, system=PERSONA, max_tokens=1700, temperature=0.55)
    fixed, ok, issues = comply_gate.gate(t or "")
    return {"platform": "TikTok Video (plan + Flow prompts)", "key": "tiktok_video", "topic": topic,
            "model": m, "ok": ok, "issues": issues, "script": script, "plan": fixed}


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    topic = sys.argv[1] if len(sys.argv) > 1 else "หนี้บัตรหลายใบ อยากรวมหนี้ก้อนเดียวลดดอก"
    r = create(topic)
    print(r["platform"], "|", r["model"], "| comply", "PASS" if r["ok"] else r["issues"])
    print("--- OUTPUT ---")
    print(r["plan"][:1800])
