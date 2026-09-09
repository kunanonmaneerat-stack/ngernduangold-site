"""hermes_digest.py — local-only daily watcher digest.
อ่าน traffic_monitor (Meta reach) + GA4 (observed intent) + traffic_analyst (verdict)
+ นับ content package วันนี้ + เช็ก baseline · เขียน cowork-inbox + summary image
ไม่ส่ง Telegram/Slack/email/browser · ใช้: py pipeline/hermes_digest.py --local-only
"""
import argparse, os, sys, glob, datetime
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import traffic_monitor, traffic_analyst, credit_tracker

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INBOX = os.path.join(ROOT, "automation-log", "cowork-inbox")
PKG = os.path.join(ROOT, "automation-log", "content-packages")
BASELINE = 500


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

    # Observed click distribution only; never call this a revenue winner.
    top = sorted(ga4["by_channel"].items(),
                 key=lambda kv: (kv[1]["affiliate_click"], kv[1]["sessions"]), reverse=True)
    top_str = ", ".join("%s(%d)" % (k, v["affiliate_click"])
                        for k, v in top if v["affiliate_click"] > 0)

    lines = ["ngernduangold — สรุปรายวัน " + datetime.date.today().isoformat()]
    if ga4["connected"]:
        lines.append("traffic: Meta reach %d views · GA4 %d sessions" % (tot["views"], ga4["sessions"]))
        lines.append("GA4 observed intent: quiz_start=%d · affiliate_click=%d · trust=%s" %
                     (ga4["quiz_start"], ga4["affiliate_click"], ga4["trust_label"]))
        if top_str:
            lines.append("affiliate_click distribution (ไม่ใช่ผู้ชนะ/รายได้): " + top_str)
    else:
        lines.append("reach รวม(ช่องที่วัดได้): %d views | manual legacy intent: quiz=%d intent=%d (ยังไม่เชื่อม GA4)" %
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
    with open(os.path.join(INBOX, "digest-" + ts + ".md"), "w", encoding="utf-8") as handle:
        handle.write("# Daily Digest (Hermes)\n\n" + msg)
    try:
        import summary_card
        png = summary_card.build()
        print("[hermes_digest] local summary image -> " + png)
    except Exception as e:
        print("[hermes_digest] ภาพ skip:", str(e)[:90])
    print("[hermes_digest] digest:\n" + msg)
    print("[hermes_digest] notification: local-only (no Telegram/Slack/email/browser mutation)")
    return msg, False


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    parser = argparse.ArgumentParser()
    parser.add_argument("--local-only", action="store_true",
                        help="explicitly document the scheduled local-only posture")
    parser.parse_args()
    run()
