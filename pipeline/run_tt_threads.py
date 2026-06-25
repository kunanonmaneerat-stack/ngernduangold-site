"""run_tt_threads.py — สั่ง creator agents (TikTok + Threads) ผลิตแพ็กเกจฮุกดราม่า/คำถามปลายเปิด
เกาะหัวข้อที่ converted ดี (หนี้/ออม/สินเชื่อ) · ผ่าน comply_gate + content_review · ดราฟต์ รอ owner โพสต์
ใช้: py pipeline/run_tt_threads.py
"""
import os, sys, datetime
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import content_creators
try:
    import content_review
except Exception:
    content_review = None

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PKG = os.path.join(ROOT, "automation-log", "content-packages")
INBOX = os.path.join(ROOT, "automation-log", "cowork-inbox")

HOOK = ("เปิดด้วยฮุกดราม่า/คำถามปลายเปิดที่คนเลื่อนผ่านไม่ได้ใน 1-3 วิแรก "
        "(แนว 'อายุ 30 มีหนี้บัตร 5 ใบ ปกติไหม?' / 'เงินเดือนเข้าวันเดียวหายเกลี้ยง ใครเป็นบ้าง?') "
        "ให้คนอยากคอมเมนต์/แชร์ประสบการณ์ · กระตุ้นคอมเมนต์ก่อนขาย · น้ำเสียงเพื่อนคุยกัน ไม่สั่งสอน")

TOPICS = [
    "หนี้บัตรหลายใบ จ่ายขั้นต่ำยอดไม่ลด อยากรวมหนี้ก้อนเดียวลดดอก",
    "เงินเดือนชนเดือน เงินเข้าวันเดียวหมด เริ่มออมยังไงให้อยู่",
    "อยากได้เงินด่วนจากรถ จำนำทะเบียน/รถแลกเงิน เลือกยังไงไม่โดนเอาเปรียบ",
]


def main():
    ts = datetime.datetime.now().strftime("%Y%m%d-%H%M")
    sec = ["# แพ็กเกจ TikTok + Threads — ฮุกดราม่า/คำถามปลายเปิด (" + ts + ")",
           "> เกาะหัวข้อที่ converted ดี (หนี้/ออม/สินเชื่อ) · CTA คอมเมนต์ 'เช็กสิทธิ์' · **ดราฟต์ รอ owner รีวิว+โพสต์**",
           "> TikTok = สคริปต์ถ่ายคลิป · Threads = ก๊อปวางโพสต์ได้เลย", ""]
    allok = 0
    alln = 0
    for topic in TOPICS:
        sec.append("\n---\n## หัวข้อ: " + topic)
        for key in ["tiktok", "threads"]:
            r = content_creators.create(key, topic, extra=HOOK)
            alln += 1
            allok += 1 if r["ok"] else 0
            tag = "PASS" if r["ok"] else ("FLAG: " + "; ".join(r["issues"]))
            sec.append("\n### " + r["platform"] + "  _(" + str(r["model"]) + " · comply " + tag + ")_")
            sec.append((r["content"] or "(ว่าง — ลองรันใหม่)"))
    md = "\n".join(sec)
    os.makedirs(PKG, exist_ok=True)
    os.makedirs(INBOX, exist_ok=True)
    pkg = os.path.join(PKG, ts + "-tiktok-threads-drama.md")
    open(pkg, "w", encoding="utf-8").write(md)
    open(os.path.join(INBOX, "content-tt-threads-" + ts + ".md"), "w", encoding="utf-8").write(md)
    if content_review:
        try:
            content_review.run(pkg)
        except Exception as e:
            print("[run_tt_threads] review skip:", str(e)[:80])
    print("[run_tt_threads] OK -> " + pkg + " | comply " + str(allok) + "/" + str(alln))
    return pkg


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    main()
