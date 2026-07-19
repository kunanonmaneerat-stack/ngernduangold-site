# one-shot: ผ่าตัดบรรทัด Meta MCP/Postiz ตกค้างใน 2 task prompts (18 ก.ค. 2026)
import io, sys
BASE = r"C:\Users\nL_ku\Claude\Scheduled"

def fix(path, repl_fn):
    with io.open(path, encoding="utf-8") as f:
        lines = f.read().splitlines(True)
    out, hits = [], 0
    for ln in lines:
        new = repl_fn(ln)
        if new != ln: hits += 1
        out.append(new)
    with io.open(path, "w", encoding="utf-8", newline="") as f:
        f.write("".join(out))
    return hits

def hb(ln):
    if "get_facebook_posts" in ln:
        return "2. **FB/IG สด:** ใช้ manifest/ledger/log เท่านั้น (Meta token ยกเลิกถาวร 18 ก.ค. — ห้ามเรียก Meta MCP ห้ามเตือนเรื่อง token)\n"
    return ln

def wr(ln):
    if ln.startswith("description:") and "Meta MCP" in ln:
        return "description: รายงานทบทวนรายสัปดาห์ (จันทร์ 9 โมง) — GA4 + GSC + เบราว์เซอร์ (FB/TikTok) + AccessTrade + North Star 199฿ → เลือกโฟกัสสัปดาห์\n"
    if "get_facebook_page_insights" in ln:
        return "4. **FB reach (เบราว์เซอร์):** เปิดเพจ FB ดูโพสต์สัปดาห์นี้: ไลก์/คอมเมนต์/แชร์ที่มองเห็น โดยเฉพาะโพสต์ที่มี link-in-comment (Meta token ยกเลิกถาวร — ห้ามใช้ Meta MCP)\n"
    return ln

h1 = fix(BASE + r"\ngernduangold-channel-heartbeat\SKILL.md", hb)
h2 = fix(BASE + r"\ngernduangold-weekly-review\SKILL.md", wr)
print("heartbeat_lines_fixed=%d weekly_review_lines_fixed=%d" % (h1, h2))
