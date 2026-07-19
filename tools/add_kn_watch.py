# เพิ่ม knowledge-post เข้า cadence watch ของ heartbeat (19 ก.ค. 2026)
import io
P = r"C:\Users\nL_ku\Claude\Scheduled\ngernduangold-channel-heartbeat\SKILL.md"
MARK = "**YouTube comment-link:**"
ADD = "- **Knowledge-post เที่ยง (Threads+FB text):** task 12:40 → ledger channel=threads/facebook type=text วันนี้ · ขาดทั้งคู่หลัง 13:30 = ⚠️ (เริ่มนับ 20 ก.ค.)\n"
s = io.open(P, encoding="utf-8").read()
if "Knowledge-post" not in s and MARK in s:
    i = s.index(MARK)
    j = s.index("\n", i) + 1
    io.open(P, "w", encoding="utf-8", newline="").write(s[:j] + ADD + s[j:])
    print("added")
else:
    print("skip")
