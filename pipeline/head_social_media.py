"""head_social_media.py — หัวหน้าทีมโซเชียล: รับ 'แผนถ่ายทำ + Google Flow prompts' จาก
tiktok_video_creator (ซึ่งรับสคริปต์จาก tiktok creator) -> รวมเป็น Social Media Handoff
+ แนบเวลาดีสุด -> ส่ง Cowork · ปลอดภัย: ผลิตไฟล์ handoff เท่านั้น ไม่โพสต์เอง
ใช้: py pipeline/head_social_media.py
"""
import os, sys, datetime
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import tiktok_video_creator
try:
    import post_timing
except Exception:
    post_timing = None

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INBOX = os.path.join(ROOT, "automation-log", "cowork-inbox")
PKG = os.path.join(ROOT, "automation-log", "content-packages")
TOPICS = [
    "หนี้บัตรหลายใบ จ่ายขั้นต่ำยอดไม่ลด อยากรวมหนี้ก้อนเดียวลดดอก",
    "เงินเดือนชนเดือน เงินเข้าวันเดียวหมด เริ่มออมยังไงให้อยู่",
]


def run(topics=None):
    topics = topics or TOPICS
    tslot = []
    if post_timing:
        try:
            tslot = [h for h, _, _ in post_timing.analyze()["slots"].get("tiktok", [])]
        except Exception:
            tslot = []
    slot_str = " / ".join("%02d:00" % h for h in tslot) or "19:00 / 21:00 / 22:00"

    ts = datetime.datetime.now().strftime("%Y%m%d-%H%M")
    sec = ["# 🎬 Social Media Handoff — TikTok Video + Google Flow (head_social_media) " + ts,
           "> สาย: tiktok creator → tiktok_video_creator → **head_social_media** → Cowork คุมคิว",
           "> มี **Google Flow / Veo prompts (อังกฤษ)** ในแต่ละหัวข้อ — ก๊อปไปเจนคลิปใน Flow ได้เลย",
           "> เวลาโพสต์ TikTok ดีสุด (post_timing): **" + slot_str + "**",
           "> ถ่ายเอง/เจน Flow แล้วอัปผ่าน TikTok Studio ตามเวลา (owner กดเอง — ไม่ auto-post)", ""]
    okc = 0
    for topic in topics:
        r = tiktok_video_creator.create(topic)
        okc += 1 if r["ok"] else 0
        sec.append("\n---\n## หัวข้อ: " + topic)
        sec.append("\n### 📝 สคริปต์ (tiktok creator)")
        sec.append(r["script"] or "(ไม่มี)")
        sec.append("\n### 🎬 แผนถ่ายทำ + 🎞️ Google Flow prompts (tiktok_video_creator · " +
                   str(r["model"]) + " · comply " + ("PASS" if r["ok"] else "FLAG") + ")")
        sec.append(r["plan"] or "(ว่าง)")
    md = "\n".join(sec)
    os.makedirs(INBOX, exist_ok=True)
    os.makedirs(PKG, exist_ok=True)
    fp = os.path.join(INBOX, "social-handoff-tiktok-" + ts + ".md")
    open(fp, "w", encoding="utf-8").write(md)
    open(os.path.join(PKG, ts + "-tiktok-video-flow.md"), "w", encoding="utf-8").write(md)
    print("[head_social_media] -> " + fp + " | %d คลิป · comply %d/%d" % (len(topics), okc, len(topics)))
    return {"file": fp, "count": len(topics)}


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    run()
