"""post_agent.py — Agent คุมคิวโพสต์: รับสล็อตเวลาจาก post_timing + ดราฟต์ล่าสุด
-> จับคู่ (หัวข้อ x แพลตฟอร์ม) กับเวลาดีสุด 3 วันข้างหน้า -> ออกตารางคิวให้ owner/studio
ปลอดภัย: ไม่โพสต์เอง — ผลิตตารางคิว (เวลา+แพลตฟอร์ม+หัวข้อ+ไฟล์ดราฟต์) ให้คนกดโพสต์/ตั้งเวลาใน studio
ใช้: py pipeline/post_agent.py
"""
import os, sys, glob, re, datetime
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import post_timing

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INBOX = os.path.join(ROOT, "automation-log", "cowork-inbox")
PKG = os.path.join(ROOT, "automation-log", "content-packages")
DAYS_TH = {0: "จ", 1: "อ", 2: "พ", 3: "พฤ", 4: "ศ", 5: "ส", 6: "อา"}
# แพลตฟอร์มที่จะจัดคิว (FB = top converter + มี auto-DM, ใช้ข้อความดราฟต์ได้)
PLATS = ["fb", "threads", "tiktok"]


def latest_package():
    files = sorted(glob.glob(os.path.join(PKG, "*tiktok-threads*.md")) or glob.glob(os.path.join(PKG, "*.md")))
    return files[-1] if files else None


def topics_from(path):
    out = []
    if path and os.path.exists(path):
        for line in open(path, encoding="utf-8"):
            m = re.match(r"^##\s*หัวข้อ:\s*(.+)$", line.strip())
            if m:
                out.append(m.group(1).strip())
    return out


def next_slot(start_dt, hour):
    """คืน datetime ถัดไปที่ตรง hour (วันนี้ถ้ายังไม่ถึง ไม่งั้นวันถัดไป)"""
    cand = start_dt.replace(hour=hour, minute=0, second=0, microsecond=0)
    if cand <= start_dt:
        cand += datetime.timedelta(days=1)
    return cand


def run():
    tim = post_timing.analyze()
    slots = tim["slots"]
    pkg = latest_package()
    topics = topics_from(pkg) or ["(ไม่พบหัวข้อในแพ็กเกจ — รัน run_tt_threads.py ก่อน)"]
    now = datetime.datetime.now()

    rows = []          # (datetime, plat, topic)
    cursor = {p: now for p in PLATS}   # ไล่เวลาแยกต่อแพลตฟอร์ม กันชนกัน
    for ti, topic in enumerate(topics):
        for p in PLATS:
            sl = slots.get(p) or [(20, "ค่ำ", 2)]
            hour = sl[ti % len(sl)][0]          # สลับสล็อตของแพลตฟอร์มไปเรื่อย
            dt = next_slot(cursor[p], hour)
            rows.append((dt, p, topic))
            cursor[p] = dt + datetime.timedelta(hours=1)   # เลื่อนเคอร์เซอร์ของแพลตฟอร์มนั้น
    rows.sort(key=lambda r: r[0])

    ts = now.strftime("%Y%m%d-%H%M")
    out = ["# Post Queue — ตารางคิวโพสต์ (จาก post_timing + ดราฟต์ล่าสุด) " + ts,
           "> ที่มาเวลา: " + tim["source"],
           "> ดราฟต์เต็ม: " + (os.path.basename(pkg) if pkg else "—") + " (เปิดดูเนื้อหาเต็มก่อนโพสต์)",
           "> **ดราฟต์ + ตารางเวลา — owner กดโพสต์/ตั้งเวลาใน studio เอง (ไม่ auto-post)**",
           "",
           "| เวลา | วัน | แพลตฟอร์ม | หัวข้อ |",
           "| --- | --- | --- | --- |"]
    for dt, p, topic in rows:
        out.append("| %s น. | %s %d/%d | %s | %s |" %
                   (dt.strftime("%H:%M"), DAYS_TH.get(dt.weekday(), "?"), dt.day, dt.month,
                    p.upper(), topic[:40]))
    out += ["",
            "## วิธีใช้",
            "- **FB**: ก๊อปเนื้อหา (โพสต์เดี่ยวแนวดราม่า) -> Meta Business Suite -> ตั้งเวลาตามตาราง · CTA 'เช็กสิทธิ์' จะเข้า auto-DM",
            "- **Threads**: ก๊อปวางโพสต์ในแอป Threads ตามเวลา",
            "- **TikTok**: ถ่ายคลิปตามสคริปต์ -> อัปผ่าน TikTok Studio ตั้งเวลาตามตาราง",
            "- เวลาปรับจากออดิเอนซ์จริง (GA4) ผสม best-practice การเงินไทย — โพสต์ใหม่ ๆ ระบบจะอัปเวลาให้เองตามข้อมูลที่เพิ่มขึ้น"]
    os.makedirs(INBOX, exist_ok=True)
    fp = os.path.join(INBOX, "post-queue-" + ts + ".md")
    open(fp, "w", encoding="utf-8").write("\n".join(out))
    print("[post_agent] -> " + fp + " | %d slots" % len(rows))
    return {"file": fp, "rows": len(rows), "timing": tim["file"]}


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    run()
