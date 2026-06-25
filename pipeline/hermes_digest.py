"""hermes_digest.py — Watcher agent (ตาม Opus+Gemini): รวมสถานะรายวัน -> ส่ง Telegram ผ่าน Hermes
อ่าน traffic_monitor (Meta reach) + GA4 (conversion จริง) + traffic_analyst (verdict)
+ นับ content package วันนี้ + เช็ก baseline · ส่ง digest สั้นเข้า Telegram (owner) + เขียน cowork-inbox
ไม่โพสต์/ไม่ deploy (แค่เฝ้า+รายงาน) · ใช้: py pipeline/hermes_digest.py
"""
import os, sys, glob, subprocess, datetime
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import traffic_monitor, traffic_analyst, credit_tracker

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INBOX = os.path.join(ROOT, "automation-log", "cowork-inbox")
PKG = os.path.join(ROOT, "automation-log", "content-packages")
HERMES_HOME = r"C:\Users\nL_ku\AppData\Local\hermes"
HERMES_PY = os.path.join(HERMES_HOME, "hermes-agent", "venv", "Scripts", "python.exe")
BASELINE = 500


def hermes_send(msg):
    try:
        env = os.environ.copy()
        env.setdefault("TELEGRAM_HOME_CHANNEL", "8431211539")
        subprocess.run([HERMES_PY, "-m", "hermes_cli.main", "send", "--to", "telegram", msg],
                       cwd=os.path.join(HERMES_HOME, "hermes-agent"), timeout=90, env=env)
        return True
    except Exception as e:
        print("[hermes_digest] Telegram send failed (รันบนเครื่อง owner เท่านั้น):", str(e)[:80])
        return False


def build():
    agg, rows = traffic_monitor.collect()
    mon = traffic_monitor.run()
    an = traffic_analyst.analyze()
    tot = mon["total"]
    ga4 = traffic_analyst._load_ga4()
    # best post + baseline check (Meta reach)
    best = None
    for r in rows:
        try:
            v = int(float(r.get("views", 0) or 0))
        except Exception:
            v = 0
        if best is None or v > best[1]:
            best = (r.get("source", ""), v, r.get("topic", ""))
    over = [r for r in rows if (int(float(r.get("views", 0) or 0)) >= BASELINE)]
    today = datetime.date.today().strftime("%Y%m%d")
    pkgs = len(glob.glob(os.path.join(PKG, today + "*")))

    # ช่อง converted ดีสุด จาก GA4
    top = sorted(ga4["by_channel"].items(),
                 key=lambda kv: (kv[1]["conversion"], kv[1]["sessions"]), reverse=True)
    top_str = ", ".join("%s(%d)" % (k, v["conversion"]) for k, v in top if v["conversion"] > 0)

    lines = ["ngernduangold — สรุปรายวัน " + datetime.date.today().isoformat()]
    if ga4["connected"]:
        lines.append("traffic: Meta reach %d views · GA4 %d sessions" % (tot["views"], ga4["sessions"]))
        lines.append("conversion (GA4 จริง): quiz_start=%d · affiliate_click=%d" % (ga4["quiz_start"], ga4["conversion"]))
        if top_str:
            lines.append("ช่อง converted ดีสุด: " + top_str)
    else:
        lines.append("reach รวม(ช่องที่วัดได้): %d views | conversion: quiz=%d สมัคร=%d (ยังไม่เชื่อม GA4)" %
                     (tot["views"], tot["quiz_start"], tot["conversion"]))
    lines.append("คอนเทนต์ผลิตวันนี้: %d แพ็กเกจ (ดราฟต์ รอรีวิว+โพสต์)" % pkgs)
    try:
        lines.append(credit_tracker.summary_line())
    except Exception:
        pass
    if best:
        lines.append("คลิปดีสุด: %s (%d views)" % (best[2] or best[0], best[1]))
    lines.append(("มีคลิปทะลุ baseline %d แล้ว!" % BASELINE) if over
                 else ("ยังไม่มีคลิป reach >= %d (ยังไม่พ้น cold-start)" % BASELINE))
    lines.append("VERDICT: " + an["verdict"])
    lines.append("DECISION: " + an["decision"][:170])
    lines.append("งาน owner วันนี้: Pantip value 1-2 โพสต์ + โพสต์ใหม่ใช้ CTA 'คอมเมนต์ เช็กสิทธิ์'")
    return "\n".join([l for l in lines if l])


def run():
    msg = build()
    os.makedirs(INBOX, exist_ok=True)
    ts = datetime.datetime.now().strftime("%Y%m%d-%H%M")
    open(os.path.join(INBOX, "digest-" + ts + ".md"), "w", encoding="utf-8").write("# Daily Digest (Hermes)\n\n" + msg)
    sent = hermes_send(msg)
    try:
        import summary_card
        png = summary_card.build()
        hermes_send("MEDIA:" + png)
        print("[hermes_digest] ส่งภาพสรุปเข้า Telegram แล้ว")
    except Exception as e:
        print("[hermes_digest] ภาพ skip:", str(e)[:90])
    print("[hermes_digest] digest:\n" + msg)
    print("[hermes_digest] Telegram:", "ส่งแล้ว" if sent else "ไม่ส่ง (เขียน cowork-inbox แทน)")
    return msg, sent


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    run()
