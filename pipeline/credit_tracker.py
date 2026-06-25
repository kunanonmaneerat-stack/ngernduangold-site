"""credit_tracker.py — Agent ติดตามเครดิต Google Flow (Veo/Omni Flash) -> อัปเดต Cowork
โควต้า 1000 credits/เดือน · วิดีโอ 10 วิ = 15 credits/คลิป · ภาพ = 4 credits
เก็บ ledger (automation-log/flow-credits.json) · เขียนสรุปเข้า cowork-inbox
ให้ dashboard_agent / summary_card / hermes_digest อ่านต่อ -> โชว์บน Cowork + Telegram
รีเซ็ตยอดอัตโนมัติเมื่อขึ้นเดือนใหม่ · ปลอดภัย: อ่าน/เขียนไฟล์เท่านั้น (ไม่จ่ายเงิน/ไม่ซื้อเครดิต)
ใช้:
  py pipeline/credit_tracker.py status
  py pipeline/credit_tracker.py log "ฮุกหัวข้อหนี้บัตร" 15
  py pipeline/credit_tracker.py init 970     # ตั้งยอดคงเหลือปัจจุบัน
  py pipeline/credit_tracker.py plan
"""
import os, sys, json, datetime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
AL = os.path.join(ROOT, "automation-log")
INBOX = os.path.join(AL, "cowork-inbox")
STATE = os.path.join(AL, "flow-credits.json")

QUOTA = 1000        # credits/เดือน (Google Flow PRO)
COST_VIDEO = 15     # 10-วิ วิดีโอ/คลิป (Veo Omni Flash)
COST_IMAGE = 4      # ภาพ (เผื่อใช้)


def _month():
    return datetime.date.today().strftime("%Y-%m")


def _blank():
    return {"month": _month(), "quota": QUOTA, "used": 0, "log": []}


def _save(st):
    os.makedirs(AL, exist_ok=True)
    json.dump(st, open(STATE, "w", encoding="utf-8"), ensure_ascii=False, indent=2)


def _load():
    st = _blank()
    if os.path.exists(STATE):
        try:
            st = json.load(open(STATE, encoding="utf-8"))
        except Exception:
            st = _blank()
    if st.get("month") != _month():     # ขึ้นเดือนใหม่ = รีเซ็ตโควต้า
        st = _blank()
        _save(st)
    st.setdefault("quota", QUOTA)
    st.setdefault("used", 0)
    st.setdefault("log", [])
    return st


def remaining(st=None):
    st = st or _load()
    return max(0, int(st["quota"]) - int(st["used"]))


def init(bal):
    """ตั้งยอดคงเหลือปัจจุบัน (เช่น 970) -> used = quota - bal"""
    st = _load()
    st["used"] = max(0, int(st["quota"]) - int(bal))
    _save(st)
    return st


def log(desc, credits=COST_VIDEO, n=1):
    st = _load()
    c = int(credits) * int(n)
    st["used"] = int(st["used"]) + c
    st["log"].append({"ts": datetime.datetime.now().strftime("%Y-%m-%d %H:%M"),
                      "desc": desc, "credits": c, "balance": remaining(st)})
    _save(st)
    return st


def summary_line():
    """บรรทัดสั้นสำหรับ digest/การ์ด"""
    st = _load()
    rem = remaining(st)
    return "Flow credits: %d/%d เหลือ (~%d คลิป @ %d)" % (rem, st["quota"], rem // COST_VIDEO, COST_VIDEO)


def status(write=True):
    st = _load()
    rem = remaining(st)
    clips = rem // COST_VIDEO
    pct_used = int(round(100.0 * st["used"] / st["quota"])) if st["quota"] else 0
    if write:
        lines = ["# Flow Credits — สถานะ (credit_tracker) " + datetime.datetime.now().strftime("%Y-%m-%d %H:%M"),
                 "",
                 "- เดือน: %s" % st["month"],
                 "- โควต้า: %d credits/เดือน" % st["quota"],
                 "- ใช้ไป: %d credits (%d%%)" % (st["used"], pct_used),
                 "- คงเหลือ: **%d credits**  (~%d คลิปวิดีโอ @ %d/คลิป)" % (rem, clips, COST_VIDEO),
                 "",
                 "## ประวัติการใช้ล่าสุด"]
        hist = st["log"][-12:][::-1]
        for e in hist:
            lines.append("- %s · %s · -%d (เหลือ %d)" % (e["ts"], e["desc"], e["credits"], e["balance"]))
        if not hist:
            lines.append("- (ยังไม่มีการใช้)")
        os.makedirs(INBOX, exist_ok=True)
        ts = datetime.datetime.now().strftime("%Y%m%d-%H%M")
        open(os.path.join(INBOX, "flow-credits-" + ts + ".md"), "w", encoding="utf-8").write("\n".join(lines))
    return {"month": st["month"], "quota": st["quota"], "used": st["used"],
            "remaining": rem, "clips_left": clips, "pct_used": pct_used}


def plan():
    """แผนใช้เครดิตให้คุ้มสุด: ทำ 2 หัวข้อ converted ดีสุดให้ครบคลิปเต็มก่อน แล้วค่อยขยาย"""
    st = _load(); rem = remaining(st); clips = rem // COST_VIDEO
    lines = ["# แผนใช้ Flow credits ให้คุ้มสุด (credit_tracker.plan)",
             "เหลือ %d credits = ~%d คลิปวิดีโอ 10 วิ" % (rem, clips), "",
             "ลำดับความคุ้ม (เกาะหัวข้อที่ GA4 บอกว่า converted ดีสุด):",
             "1) เติมหัวข้อ #1 หนี้บัตร/รวมหนี้ ให้ครบ 4–6 คลิป ต่อเป็น TikTok เต็ม (เหลืออีก ~4 คลิป = 60 cr)",
             "2) เติมหัวข้อ #2 เงินเดือนชนเดือน/ออม ให้ครบ 4–6 คลิป (อีก ~5 คลิป = 75 cr)",
             "3) เปิดหัวข้อใหม่ที่ converted รองลงมา หัวข้อละ 4–6 คลิป จนกว่าเครดิตจะหมด",
             "",
             "กติกา: log ทุกคลิปที่เจน เพื่อให้ Cowork/Telegram เห็นยอดเรียลไทม์",
             "เตือน: เหลือ < %d cr (=%d คลิป) ให้ชะลอ เก็บไว้คลิปสำคัญ" % (COST_VIDEO * 4, 4)]
    os.makedirs(INBOX, exist_ok=True)
    ts = datetime.datetime.now().strftime("%Y%m%d-%H%M")
    open(os.path.join(INBOX, "flow-credit-plan-" + ts + ".md"), "w", encoding="utf-8").write("\n".join(lines))
    return "\n".join(lines)


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    cmd = sys.argv[1] if len(sys.argv) > 1 else "status"
    if cmd == "init":
        bal = int(sys.argv[2]) if len(sys.argv) > 2 else 970
        st = init(bal)
        print("[credit_tracker] init -> เหลือ %d/%d" % (remaining(st), st["quota"]))
    elif cmd == "log":
        desc = sys.argv[2] if len(sys.argv) > 2 else "video clip"
        cr = int(sys.argv[3]) if len(sys.argv) > 3 else COST_VIDEO
        st = log(desc, cr)
        print("[credit_tracker] log '%s' -%d -> เหลือ %d/%d" % (desc, cr, remaining(st), st["quota"]))
    elif cmd == "plan":
        print(plan())
    else:
        s = status()
        print("[credit_tracker] เหลือ %d/%d (~%d คลิป) · ใช้ไป %d%%" %
              (s["remaining"], s["quota"], s["clips_left"], s["pct_used"]))
