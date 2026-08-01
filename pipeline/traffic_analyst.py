"""traffic_analyst.py — Agent วิเคราะห์: รับข้อมูลจาก traffic_monitor + GA4 -> ตรวจความพอ/ถูกต้อง
-> พิสูจน์คำแนะนำ consult (bottleneck=reach? funnel แปลงผลไหม?) -> ส่ง verdict + decision ให้ Cowork
กฎ owner: พิสูจน์ไม่ได้ = คงทุก agent ไว้ · พิสูจน์ได้ = ทำตามคำแนะนำให้เกิดประโยชน์สูงสุด
ปลอดภัย: อ่าน/เขียนไฟล์เท่านั้น (ไม่ลบ/ไม่ปิด agent เอง — แค่เสนอ decision ให้ Cowork)
GA4: ใช้ ga4-metrics.csv (จาก ga4_pull.py) เป็น conversion จริง — คำนวณ % และจัดอันดับช่องจาก GA4
"""
import io, json, os, sys, datetime
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import traffic_monitor as tm

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INBOX = os.path.join(ROOT, "automation-log", "cowork-inbox")
GA4_FILE = os.path.join(ROOT, "automation-log", "ga4-metrics.csv")
REACH_BASELINE = 500   # traffic ที่ถือว่า "พ้น cold-start" พอจะทดสอบ funnel
MIN_POSTS = 10
MIN_CHANNELS = 2


SALES_LOG = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                         "automation-log", "sales-log.jsonl")


def read_sales():
    """ยอดขายจริงจาก sales-log.jsonl — ตัวเดียวที่นับเป็นเงิน

    แยกจาก affiliate_click โดยสิ้นเชิง: คลิกคือความสนใจ เงินคือผลลัพธ์ ถ้าไม่แยกสองอย่างนี้
    รายงานจะสรุปว่า funnel ทำงานทั้งที่ยังไม่เคยมีใครจ่ายเงินสักบาท (เกิดจริง 28 วันก่อน 1 ส.ค. 2026)
    """
    n, baht = 0, 0.0
    if not os.path.exists(SALES_LOG):
        return {"count": 0, "baht": 0.0, "has_log": False}
    try:
        for line in io.open(SALES_LOG, encoding="utf-8"):
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except Exception:
                continue
            if not isinstance(rec, dict) or "amount_thb" not in rec:
                continue          # แถว metadata/header ไม่ใช่ยอดขาย
            n += 1
            baht += float(rec.get("amount_thb") or 0)
    except OSError:
        return {"count": 0, "baht": 0.0, "has_log": False}
    return {"count": n, "baht": baht, "has_log": True}


def _pct(n, d):
    return (100.0 * n / d) if d else 0.0


def _load_ga4():
    """อ่าน conversion จริงจาก GA4 (ga4-metrics.csv) — ตัวปิดช่องวัดผลของ loop"""
    res = {"sessions": 0, "quiz_start": 0, "conversion": 0, "buy_intent": 0, "channels": [],
           "connected": False, "by_channel": {}}
    if not os.path.exists(GA4_FILE):
        return res
    import csv
    try:
        with open(GA4_FILE, encoding="utf-8") as f:
            for row in csv.DictReader(f):
                s = int(row.get("sessions") or 0)
                q = int(row.get("quiz_start") or 0)
                c = int(row.get("affiliate_click") or row.get("conversion") or 0)  # หัวเก่า=conversion (ก่อน 1 ส.ค. 2026)
                src = row.get("source") or "?"
                res["sessions"] += s
                res["quiz_start"] += q
                res["conversion"] += c
                res["buy_intent"] += int(row.get("buy_intent_click") or 0)
                res["by_channel"][src] = {"sessions": s, "quiz_start": q, "conversion": c}
                if s > 0:
                    res["channels"].append(src)
        res["connected"] = True
    except Exception:
        pass
    return res


def analyze():
    r = tm.run()
    agg, tot = r["agg"], r["total"]
    rows_n = r["rows"]
    notes, decision, verdict = [], "", ""

    ga4 = _load_ga4()
    has_conv_data = (tot["quiz_start"] + tot["conversion"] + ga4["quiz_start"] + ga4["conversion"]) > 0
    reach_proxy = max(tot["views"], ga4["sessions"])           # traffic จริง = Meta reach หรือ GA4 sessions
    has_decent_reach = reach_proxy >= REACH_BASELINE
    channels_with_data = [c for c in agg if agg[c]["views"] > 0]
    chan_union = set(channels_with_data) | set(ga4["channels"])
    enough = rows_n >= MIN_POSTS and len(chan_union) >= MIN_CHANNELS and has_conv_data

    # ---- ความพอ/ช่องว่างของข้อมูล ----
    gaps = []
    if not has_conv_data:
        if ga4["connected"]:
            gaps.append("GA4 เชื่อมแล้วแต่ยังไม่มี quiz_start/conversion (ยังไม่มีคนคลิกเข้าเว็บ/quiz — รอ reach)")
        else:
            gaps.append("ยังไม่เชื่อม GA4 = ไม่มีข้อมูล conversion (รัน ga4_pull.py · ดู GA4-CONNECT-SETUP.md)")
    if not has_decent_reach:
        gaps.append("traffic ยังต่ำกว่า baseline (%d) — reach_proxy=%d (Meta reach %d / GA4 sessions %d)"
                    % (REACH_BASELINE, reach_proxy, tot["views"], ga4["sessions"]))
    if len(chan_union) < MIN_CHANNELS:
        gaps.append("มีข้อมูลแค่ %d ช่อง (ต้อง >=%d)" % (len(chan_union), MIN_CHANNELS))
    if rows_n < MIN_POSTS:
        gaps.append("ข้อมูลโพสต์น้อย (%d แถว < %d)" % (rows_n, MIN_POSTS))

    # ---- อัตราจาก GA4 (ของจริง) ----
    sales = read_sales()
    conv_per_session = _pct(ga4["conversion"], ga4["sessions"])
    quiz_per_session = _pct(ga4["quiz_start"], ga4["sessions"])
    # ช่อง EV สูงสุด จาก GA4 conversion
    best = sorted(ga4["by_channel"].items(),
                  key=lambda kv: (kv[1]["conversion"], kv[1]["sessions"]), reverse=True)
    top_conv = [(k, v) for k, v in best if v["conversion"] > 0][:4]
    top_str = ", ".join("%s (%d conv / %d sess)" % (k, v["conversion"], v["sessions"]) for k, v in top_conv) or "—"

    # ---- พิสูจน์: bottleneck = reach หรือ conversion ----
    if not enough:
        verdict = "INSUFFICIENT (พิสูจน์ยังไม่ได้)"
        decision = ("คงทุก agent ไว้ทั้งหมดตามกฎ owner + เดินเครื่องเก็บข้อมูลต่อ: "
                    "(1) เชื่อม GA4 หรือกรอกตัวเลขจริงต่อช่อง (2) รอ traffic ทดสอบได้ "
                    "(3) มีข้อมูล >=%d ช่อง ค่อยตัดสิน") % (MIN_CHANNELS)
    else:
        total_clicks = tot["conversion"] + ga4["conversion"]   # affiliate_click รวม (คลิก ไม่ใช่เงิน)
        total_quiz = tot["quiz_start"] + ga4["quiz_start"]
        # เงินเป็นตัวตัดสิน ไม่ใช่คลิก: verdict เดิมประกาศ PROVEN จาก affiliate_click อย่างเดียว
        # ทำให้ทั้งระบบไปทุ่ม reach ขณะที่หน้าขายยังไม่มีปุ่มจ่ายเงินเลย (พบ 1 ส.ค. 2026)
        if sales["count"] > 0:
            verdict = "PROVEN: มีรายได้จริงแล้ว — reach คือคอขวดถัดไป"
            decision = ("ทุ่ม reach ของช่องที่นำไปสู่ยอดขายจริง (ยอด %d ชิ้น · %.0f บาท · "
                        "affiliate_click %d) — ลงแรง: %s"
                        % (sales["count"], sales["baht"], total_clicks,
                           ", ".join(k for k, _ in top_conv[:3]) or "Pantip"))
        elif total_clicks > 0 or total_quiz > 0:
            verdict = ("UNPROVEN: มีคนสนใจ (affiliate_click %d · quiz %d) แต่ยังไม่มีหลักฐานว่าปลายทางรับเงินได้ "
                       "— ยอดขายที่บันทึกไว้ = 0" % (total_clicks, total_quiz))
            decision = ("ห้ามสรุปว่า funnel แปลงผลจากคลิกอย่างเดียว · ก่อนเติม reach ให้ยืนยันปลายทางก่อน: "
                        "หน้าขายมีปุ่มจ่ายเงินจริงไหม · ช่องทางรับเงิน (LINE/พร้อมเพย์) เปิดอยู่ไหม · "
                        "ถ้าขายได้แล้วแต่ไม่ได้บันทึก ให้บันทึกด้วย tools/log_sale.py "
                        "(คลิกที่ไม่กลายเป็นเงิน = เทน้ำใส่ถังรั่ว)")
        else:
            verdict = "REFUTED: traffic ถึงเกณฑ์แล้วแต่ไม่มีทั้งคลิกและยอดขาย = ปัญหาอยู่ที่ funnel"
            decision = "consult ถูกบางส่วน: ก่อน freeze ให้แก้ funnel (CTA/quiz/landing) เพราะ traffic มาแล้วแต่ไม่แปลงเป็นเงิน"
        notes.append("ช่อง EV สูงสุด (GA4 affiliate_click): " + top_str)
        if conv_per_session > 0:
            notes.append("อัตราคลิกรวม (GA4): affiliate_click/session=%.1f%% · quiz/session=%.1f%% (ยังไม่ใช่อัตราแปลงเป็นเงิน)" % (conv_per_session, quiz_per_session))

    ts = r["ts"]
    out = ["# Traffic Analyst — verdict ส่ง Cowork (" + ts + ")",
           "> รับข้อมูลจาก traffic_monitor (" + os.path.basename(r["file"]) + ") + GA4 · ทดสอบคำแนะนำ consult",
           "",
           "## สรุปข้อมูลปัจจุบัน",
           "- แถวข้อมูล: %d · ช่องที่มีข้อมูล: %s" % (rows_n, ", ".join(sorted(chan_union)) or "—"),
           "- Meta reach: views=%d clicks=%d" % (tot["views"], tot["clicks"]),
           "- GA4 (เว็บจริง): %s" % (
               "sessions=%d quiz_start=%d affiliate_click=%d" % (ga4["sessions"], ga4["quiz_start"], ga4["conversion"])
               if ga4["connected"] else "ยังไม่เชื่อม (รัน ga4_pull.py -> ปลดล็อก verdict)")]
    if ga4["connected"] and top_conv:
        out += ["- GA4 affiliate_click รายช่อง (สูงสุด): " + top_str]
    out += ["",
            "## ตัวเลขสองบรรทัดที่ห้ามสลับกัน",
            "- **affiliate_click (คลิก ≠ เงิน)** : %d — จะเป็นเงินต่อเมื่อ AccessTrade อนุมัติ conversion" % (tot["conversion"] + ga4["conversion"]),
            "- **buy_intent_click (กดปุ่มซื้อสินค้าเรา)** : %d — ความตั้งใจซื้อ ยังไม่ใช่เงิน แต่บอกว่าคนเดินมาถึงปุ่มแล้ว" % ga4.get("buy_intent", 0),
            "- **ยอดขายจริง (sales-log.jsonl)** : %d ชิ้น · %.0f บาท%s" % (
                sales["count"], sales["baht"],
                "" if sales["has_log"] else "  ⚠️ ยังไม่มีไฟล์ sales-log.jsonl"),
            "",
            "## ช่องว่างข้อมูล (ทำไมพิสูจน์ได้/ไม่ได้)"]
    out += ["- " + g for g in gaps] or ["- (ข้อมูลพอ)"]
    out += ["", "## VERDICT", "**" + verdict + "**", "",
            "## DECISION (ตามกฎ owner: พิสูจน์ไม่ได้=คง agent · ได้=ทำตาม)", decision]
    if notes:
        out += ["", "## หมายเหตุ"] + ["- " + n for n in notes]
    os.makedirs(INBOX, exist_ok=True)
    vp = os.path.join(INBOX, "traffic-verdict-" + ts + ".md")
    open(vp, "w", encoding="utf-8").write("\n".join(out))
    print("[traffic_analyst] -> " + vp)
    print("[traffic_analyst] VERDICT: " + verdict)
    print("[traffic_analyst] DECISION: " + decision[:160])
    return {"verdict": verdict, "decision": decision, "file": vp, "enough": enough}


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    analyze()
