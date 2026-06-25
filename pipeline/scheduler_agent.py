"""scheduler_agent.py — Agent ตั้ง/ตรวจ Windows Task Scheduler ให้ run_daily ยิงเองทุกเช้า
install : สร้าง scheduled task 'ngernduangold_daily' รัน run_daily.cmd 07:00 ทุกวัน (รันตอน owner ล็อกอิน)
status  : เช็กว่ามี task + เวลานัดถัดไป + ผลรันล่าสุด -> เขียน cowork-inbox + print
ปลอดภัย: แตะเฉพาะ task ของตัวเอง · ไม่ใส่รหัสผ่าน (รันแบบ logged-on) · ไม่โพสต์/ไม่ deploy
ใช้: py pipeline\\scheduler_agent.py install   |   py pipeline\\scheduler_agent.py status
"""
import os, sys, subprocess, datetime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INBOX = os.path.join(ROOT, "automation-log", "cowork-inbox")
TASK = "ngernduangold_daily"
RUN_DAILY = os.path.join(ROOT, "pipeline", "run_daily.cmd")
RUN_TIME = "07:00"


def _sch(args):
    try:
        p = subprocess.run(["schtasks"] + args, capture_output=True)
        out = (p.stdout or b"").decode("utf-8", "replace") + (p.stderr or b"").decode("utf-8", "replace")
        return p.returncode, out.strip()
    except Exception as e:
        return 99, "schtasks error: " + str(e)


def install():
    rc, out = _sch(["/create", "/tn", TASK, "/tr", RUN_DAILY,
                    "/sc", "DAILY", "/st", RUN_TIME, "/f"])
    ok = rc == 0
    print("[scheduler_agent] install:", "OK" if ok else "FAIL(rc=%d)" % rc)
    print(out[:300])
    return ok


def status():
    rc, out = _sch(["/query", "/tn", TASK, "/v", "/fo", "LIST"])
    exists = rc == 0
    # ดึงบรรทัดสำคัญ
    keep = []
    for line in out.splitlines():
        ls = line.strip()
        for k in ("TaskName", "Task To Run", "Next Run Time", "Last Run Time",
                  "Last Result", "Status", "Schedule Type", "Start Time",
                  "งานที่จะเรียกใช้", "เวลาที่เรียกใช้ครั้งถัดไป", "สถานะ"):
            if ls.startswith(k):
                keep.append(ls)
                break
    ts = datetime.datetime.now().strftime("%Y%m%d-%H%M")
    rep = ["# Scheduler Agent — สถานะ Task Scheduler (" + ts + ")",
           "> task: **" + TASK + "** · สั่งรัน: " + RUN_DAILY + " · นัด: ทุกวัน " + RUN_TIME,
           "> รันแบบ logged-on (ไม่ใส่รหัสผ่าน) — เครื่องต้องเปิด+ล็อกอินตอนเช้า", "",
           ("✅ พบ scheduled task — ยิงเองทุกเช้าแล้ว" if exists else "❌ ยังไม่พบ task (รัน install ก่อน)"),
           "", "## รายละเอียดจาก schtasks"]
    rep += ["- " + k for k in keep] if keep else ["- " + out[:500]]
    os.makedirs(INBOX, exist_ok=True)
    fp = os.path.join(INBOX, "scheduler-status-" + ts + ".md")
    open(fp, "w", encoding="utf-8").write("\n".join(rep))
    print("[scheduler_agent] status -> " + fp + " | exists:", exists)
    for k in keep:
        print("  " + k)
    return {"exists": exists, "file": fp, "lines": keep}


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    cmd = sys.argv[1] if len(sys.argv) > 1 else "status"
    if cmd == "install":
        install()
        status()
    else:
        status()
