"""post_agent.py — Agent คุมคิวโพสต์: รับสล็อตเวลาจาก post_timing + ดราฟต์ล่าสุด
-> จับคู่ (หัวข้อ x แพลตฟอร์ม) กับเวลาดีสุด 3 วันข้างหน้า -> ออกตารางคิวให้ owner/studio
ปลอดภัย: ไม่โพสต์เอง — ผลิตตารางคิว (เวลา+แพลตฟอร์ม+หัวข้อ+ไฟล์ดราฟต์) ให้คนกดโพสต์/ตั้งเวลาใน studio
ใช้: py pipeline/post_agent.py
"""
import os, sys, glob, re, datetime, json
from pathlib import Path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import post_timing
import comply_gate
import content_review

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INBOX = os.path.join(ROOT, "automation-log", "cowork-inbox")
PKG = os.path.join(ROOT, "automation-log", "content-packages")
KNOWLEDGE = os.path.join(ROOT, "automation-log")
TOOLS = os.path.join(ROOT, "tools")
POLICY_PATH = os.path.join(ROOT, ".system_control", "policy.json")
DAYS_TH = {0: "จ", 1: "อ", 2: "พ", 3: "พฤ", 4: "ศ", 5: "ส", 6: "อา"}
# แพลตฟอร์มที่จะจัดคิว (FB = top converter + มี auto-DM, ใช้ข้อความดราฟต์ได้)
PLATS = ["fb", "threads", "tiktok"]
POLICY_CHANNEL = {"fb": "facebook", "threads": "threads", "tiktok": "tiktok"}
ALLOWED_STATES = {"active", "manual"}


def eligible_platforms(policy_path=POLICY_PATH, today=None):
    try:
        with open(policy_path, encoding="utf-8") as fh:
            channels = (json.load(fh).get("channels") or {})
    except Exception:
        return []
    today = today or datetime.date.today()
    result = []
    for platform in PLATS:
        channel = channels.get(POLICY_CHANNEL[platform])
        if not isinstance(channel, dict):
            continue
        state = channel.get("state")
        allowed = state in ALLOWED_STATES
        if state == "limited":
            try:
                phase_until = datetime.date.fromisoformat(str(channel["phase_until"]))
                weekly_quota = int(channel.get("weekly_quota") or 0)
                allowed = phase_until >= today and weekly_quota > 0
            except (KeyError, TypeError, ValueError):
                allowed = False
        if allowed:
            result.append(platform)
    return result


def latest_package():
    files = glob.glob(os.path.join(PKG, "*.md"))
    return max(files, key=os.path.getmtime) if files else None


def knowledge_row_for_date(path, iso_date):
    """Return a validated knowledge-library row for a date, or (None, reasons)."""
    if TOOLS not in sys.path:
        sys.path.insert(0, TOOLS)
    try:
        import validate_knowledge_posts
        # The official-source gate is deliberately content scoped.  Passing no
        # content_id fails closed, while validating the entire library against a
        # single source set would either block unrelated rows or let the selected
        # row bypass its own sources.  Resolve today's immutable row id first, then
        # run the complete validator for that exact publication item.
        parsed_rows = validate_knowledge_posts.parse_rows(Path(path))
        selected = next((row for row in parsed_rows if row["date"] == iso_date), None)
        if selected is None:
            return None, ["no knowledge row for %s" % iso_date]
        rows, failures = validate_knowledge_posts.validate(
            Path(path), content_id=selected["id"])
    except Exception as exc:
        return None, ["knowledge validator unavailable: %s" % str(exc)[:80]]
    if failures:
        return None, ["knowledge validation failed: %s" % failures[0][:120]]
    return next((row for row in rows if row["id"] == selected["id"]), None), []


def latest_valid_knowledge(iso_date):
    files = sorted(glob.glob(os.path.join(KNOWLEDGE, "KNOWLEDGE-POSTS*.md")),
                   key=os.path.getmtime, reverse=True)
    reasons = []
    for path in files:
        row, problems = knowledge_row_for_date(path, iso_date)
        if row:
            return path, row, []
        reasons.extend(problems[:1])
    return None, None, reasons or ["no knowledge library found"]


def declared_knowledge_for_date(iso_date):
    """Return the newest library that explicitly owns the date, valid or not."""
    pattern = re.compile(r"(?m)^\|\s*" + re.escape(iso_date) + r"\s*\|")
    files = sorted(glob.glob(os.path.join(KNOWLEDGE, "KNOWLEDGE-POSTS*.md")),
                   key=os.path.getmtime, reverse=True)
    for path in files:
        try:
            with open(path, encoding="utf-8") as handle:
                text = handle.read()
            if pattern.search(text):
                return path
        except OSError:
            continue
    return None


def package_readiness(path):
    """Fail closed for generated packages until factual and content QA is clean."""
    if not path or not os.path.exists(path):
        return ["no generated package found"]
    with open(path, encoding="utf-8") as handle:
        text = handle.read()
    reasons = []
    ok, issues = comply_gate.check(text)
    if not ok or issues:
        reasons.append("compliance review has %d issue(s)" % len(issues))
    factual_flags = content_review.review_text(text)
    if factual_flags:
        reasons.append("factual verification has %d flag group(s)" % len(factual_flags))
    if any(marker in text for marker in ("\ufffd", "\u00e0\u00b8", "\u00e0\u00b9", "\x00")):
        reasons.append("encoding corruption marker found")
    if re.search(r"[\u3400-\u9fff]", text):
        reasons.append("unexpected CJK character found")
    return reasons


def select_content(day=None):
    """Prefer today's validated knowledge row; never silently queue an unsafe package."""
    iso_date = (day or datetime.date.today()).isoformat()
    path, row, reasons = latest_valid_knowledge(iso_date)
    if row:
        return path, [row["topic"]], "knowledge:%s" % row["id"], []
    declared = declared_knowledge_for_date(iso_date)
    if declared:
        # The date already belongs to a time-sensitive library.  Falling back to an
        # unrelated generated package would hide a failed source/fact review and make
        # the queue look publishable, so keep the slot empty until the declared row passes.
        return declared, [], "blocked", reasons[:1] or ["declared knowledge row is not publishable"]
    package = latest_package()
    package_reasons = package_readiness(package)
    if not package_reasons:
        return package, topics_from(package), "generated-package", []
    return package, [], "blocked", reasons[:1] + package_reasons


def topics_from(path):
    out = []
    if path and os.path.exists(path):
        with open(path, encoding="utf-8") as handle:
            for line in handle:
                m = re.match(r"^##\s*หัวข้อ:\s*(.+)$", line.strip())
                if m:
                    out.append(m.group(1).strip())
                elif not out:
                    m = re.match(r"^#\s*Content Package\s*-\s*(.+)$", line.strip())
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
    pkg, topics, source_kind, blocked_reasons = select_content()
    now = datetime.datetime.now()

    platforms = [p for p in eligible_platforms() if p in slots]
    rows = []          # (datetime, plat, topic)
    cursor = {p: now for p in platforms}   # ไล่เวลาแยกต่อแพลตฟอร์ม กันชนกัน
    for ti, topic in enumerate(topics):
        for p in platforms:
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
           "> แหล่งคอนเทนต์: " + source_kind,
           "> " + "\u0e04\u0e34\u0e27\u0e40\u0e15\u0e23\u0e35\u0e22\u0e21\u0e07\u0e32\u0e19\u0e2a\u0e33\u0e2b\u0e23\u0e31\u0e1a\u0e23\u0e30\u0e1a\u0e1a\u0e42\u0e1e\u0e2a\u0e15\u0e4c \u0e15\u0e49\u0e2d\u0e07\u0e1c\u0e48\u0e32\u0e19 policy + quota + dedup gate \u0e01\u0e48\u0e2d\u0e19\u0e40\u0e1c\u0e22\u0e41\u0e1e\u0e23\u0e48",
           "",
           "| เวลา | วัน | แพลตฟอร์ม | หัวข้อ |",
           "| --- | --- | --- | --- |"]
    for dt, p, topic in rows:
        out.append("| %s น. | %s %d/%d | %s | %s |" %
                   (dt.strftime("%H:%M"), DAYS_TH.get(dt.weekday(), "?"), dt.day, dt.month,
                   p.upper(), topic[:40]))
    if blocked_reasons:
        out += ["", "## BLOCKED"] + ["- " + reason for reason in blocked_reasons]
    timing_note = ("เวลาอิง GA4 เฉพาะ social (ตัด direct/internal/search/AI ออก) ร่วมกับกรอบเวลาของแต่ละช่องทาง"
                   if tim["source"].startswith("GA4 social-only") else
                   "รอบนี้ใช้กรอบเวลาเชิงประสบการณ์เท่านั้น เพราะข้อมูล GA4 social ใช้ไม่ได้หรือยังน้อยเกินเกณฑ์")
    out += ["",
            "## \u0e14\u0e48\u0e32\u0e19\u0e01\u0e48\u0e2d\u0e19\u0e40\u0e1c\u0e22\u0e41\u0e1e\u0e23\u0e48",
            "- \u0e04\u0e34\u0e27\u0e19\u0e35\u0e49\u0e40\u0e1b\u0e47\u0e19\u0e41\u0e1c\u0e19\u0e40\u0e17\u0e48\u0e32\u0e19\u0e31\u0e49\u0e19 \u0e07\u0e32\u0e19\u0e17\u0e35\u0e48\u0e25\u0e07\u0e17\u0e30\u0e40\u0e1a\u0e35\u0e22\u0e19\u0e43\u0e19\u0e23\u0e30\u0e1a\u0e1a\u0e40\u0e1b\u0e47\u0e19\u0e1c\u0e39\u0e49\u0e40\u0e1c\u0e22\u0e41\u0e1e\u0e23\u0e48\u0e2b\u0e25\u0e31\u0e07\u0e1c\u0e48\u0e32\u0e19\u0e14\u0e48\u0e32\u0e19",
            "- \u0e15\u0e23\u0e27\u0e08 policy state, quota, spacing, compliance, dedup \u0e41\u0e25\u0e30 ledger \u0e01\u0e48\u0e2d\u0e19\u0e17\u0e38\u0e01\u0e04\u0e23\u0e31\u0e49\u0e07",
            "- \u0e2b\u0e49\u0e32\u0e21\u0e42\u0e1e\u0e2a\u0e15\u0e4c\u0e0b\u0e49\u0e33\u0e14\u0e49\u0e27\u0e22\u0e21\u0e37\u0e2d \u0e16\u0e49\u0e32 ledger \u0e2b\u0e23\u0e37\u0e2d\u0e0a\u0e48\u0e2d\u0e07\u0e17\u0e32\u0e07\u0e22\u0e37\u0e19\u0e22\u0e31\u0e19\u0e27\u0e48\u0e32\u0e40\u0e1c\u0e22\u0e41\u0e1e\u0e23\u0e48\u0e41\u0e25\u0e49\u0e27",
            "- " + timing_note]
    os.makedirs(INBOX, exist_ok=True)
    fp = os.path.join(INBOX, "post-queue-" + ts + ".md")
    open(fp, "w", encoding="utf-8").write("\n".join(out))
    print("[post_agent] -> " + fp + " | %d slots" % len(rows))
    return {"file": fp, "rows": len(rows), "timing": tim["file"],
            "source_kind": source_kind, "blocked_reasons": blocked_reasons}


def queue_exit_code(result):
    """A declared-but-blocked content slot must fail the required daily step."""
    if not isinstance(result, dict):
        return 2
    return 2 if result.get("blocked_reasons") else 0


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    raise SystemExit(queue_exit_code(run()))
