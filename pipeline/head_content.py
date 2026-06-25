"""head_content.py — หัวหน้าทีมครีเอเตอร์: สั่ง content_creators ครบ 6 แพลตฟอร์มต่อ 1 หัวข้อ
รวมเป็นแพ็กเกจ -> ส่ง Cowork คุมต่อ · เขียน content-packages/ + cowork-inbox/content- + review-
ผลิตดราฟต์เท่านั้น (ไม่โพสต์/commit/deploy)
ใช้:  py pipeline/head_content.py "หนี้บัตรหลายใบ จ่ายขั้นต่ำไม่ลด"
"""
import os, sys, datetime
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import content_creators as cc

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PKG_DIR = os.path.join(ROOT, "automation-log", "content-packages")
INBOX = os.path.join(ROOT, "automation-log", "cowork-inbox")
ORDER = ['pantip', 'ig', 'tiktok', 'fb', 'threads', 'yt']

ROUTE = {
 'Pantip': 'owner วางเอง (บัญชี Pantip) ลิงก์ในโปรไฟล์',
 'Instagram Reel': 'Meta Business Suite ตั้งเวลา (ฟรี) แนบวิดีโอ + auto-DM CreatorFlow',
 'TikTok': 'TikTok Studio ตั้งเวลา (ฟรี) pinned comment + ลิงก์ใน bio',
 'Facebook': 'Meta Business Suite ตั้งเวลา (ฟรี) ลิงก์ในคอมเมนต์แรก',
 'Threads': 'owner โพสต์เอง',
 'YouTube Shorts': 'YouTube Studio ตั้งเวลา (ฟรี) ลิงก์ใน description',
}


def _slug(s):
    return "".join(c if c.isalnum() else "-" for c in s)[:32].strip("-").lower() or "topic"


def run(topic, extra=""):
    os.makedirs(PKG_DIR, exist_ok=True)
    os.makedirs(INBOX, exist_ok=True)
    ts = datetime.datetime.now().strftime("%Y%m%d-%H%M")
    results = []
    for k in ORDER:
        try:
            results.append(cc.create(k, topic, extra))
        except Exception as e:
            results.append({'platform': cc.CREATORS[k][0], 'key': k, 'model': None,
                            'ok': False, 'issues': ['ERROR ' + str(e)[:80]], 'content': ''})
    pkg = os.path.join(PKG_DIR, ts + "-" + _slug(topic) + ".md")
    lines = ["# Content Package - " + topic, "> " + ts + " · 6 แพลตฟอร์ม · ดราฟต์"]
    okc = 0
    for r in results:
        flag = "OK" if r['ok'] else ("FLAG " + ", ".join(r['issues'])[:60])
        okc += 1 if r['ok'] else 0
        lines += ["", "## " + r['platform'] + "  (" + str(r['model'] or 'n/a') + " · " + flag + ")",
                  "_โพสต์ทาง: " + ROUTE.get(r['platform'], '-') + "_", "", r['content'] or "(ว่าง)"]
    open(pkg, "w", encoding="utf-8").write("\n".join(lines))
    note = os.path.join(INBOX, "content-" + ts + ".md")
    nl = ["# -> Cowork: แพ็กเกจคอนเทนต์ (" + ts + ")",
          "หัวข้อ: " + topic + " · comply " + str(okc) + "/" + str(len(results)),
          "ไฟล์: automation-log/content-packages/" + os.path.basename(pkg),
          "Cowork: อ่านแพ็กเกจ+review -> คิวตาม reach (Pantip,IG ก่อน) -> ตั้งเวลาช่องฟรี / Pantip ส่ง owner", "", "routing:"]
    for p, rt in ROUTE.items():
        nl.append("- " + p + " -> " + rt)
    open(note, "w", encoding="utf-8").write("\n".join(nl))
    try:
        import content_review
        content_review.run(pkg)
    except Exception as e:
        print("[head_content] review skipped:", str(e)[:80])
    print("[head_content] package -> " + pkg)
    print("[head_content] comply " + str(okc) + "/" + str(len(results)) + " OK")
    return pkg, note, results


if __name__ == '__main__':
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    topic = sys.argv[1] if len(sys.argv) > 1 else 'หนี้บัตรเครดิตหลายใบ จ่ายขั้นต่ำยอดไม่ลด อยากรวมหนี้ลดดอก'
    run(topic)
