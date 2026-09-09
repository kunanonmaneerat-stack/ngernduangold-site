#!/usr/bin/env python3
"""Local visual-QA and quota evidence; never publication authority.

An explicit, parseable visual ``pass: true`` exits 0 only for the visual check.
``--quota`` reports quota-only evidence. Neither result authorizes scheduling or
publication, and an actor label such as ``--actor owner`` is never accepted as
identity proof. A missing key, provider error, unreadable response, or failed
visual check fails closed. NO evasion logic.
"""
import os, sys, json, math
try:  # cp874-safe: UTF-8 stdout/stderr so Thai/emoji prints never crash on Windows console (idempotent)
    import sys as _sys; _sys.stdout.reconfigure(encoding="utf-8", errors="replace"); _sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import free_ai
from pantip_eligibility import evaluate_pantip_eligibility

CHECKLIST = """ตรวจคลิป/เฟรมนี้ตาม checklist (ตอบ JSON ล้วน: {"pass":true/false,"fails":["ข้อที่ตก..."],"notes":""}):
1. Hook อ่านออกใน 1.5 วิแรก (ฟอนต์/คอนทราสต์พอ)
2. ไม่มีข้อความทับซ้อน / หลุด safe-zone (บน 12% ล่าง 20%) / สะกดผิด
3. ไม่มี watermark แพลตฟอร์มอื่น (โดยเฉพาะโลโก้ TikTok บนคลิป multicast)
4. สัดส่วน 9:16, อ่านง่ายบนมือถือ
5. แบรนด์ตรง (สี/โลโก้ เงินเดือนสมองทอง) + มี disclosure
6. CTA + "ลิงก์ในไบโอ/คอมเมนต์" ชัด
7. ถ้าใช้ภาพ AI สร้าง ต้องมี label AI
ตก = pass:false + ระบุข้อใน fails."""


# ---- POSTING-POLICY quota gate (POSTING-POLICY_antispam_20260702) ----
QUOTA_PER_DAY = {"pinterest": 5}
QUOTA_DEFAULT = 2
MIN_GAP_HOURS = 3
COUNTED_POST_TYPES = {"text", "video", "image"}
ALLOWED_CHANNEL_STATES = {"active", "manual"}
POLICY_CHANNEL = {
    "fb": "facebook", "facebook-page2": "facebook", "ig": "instagram", "yt": "youtube",
    "tiktok": "tiktok", "threads": "threads", "pinterest": "pinterest",
    "pantip": "pantip",
}
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _reject_json_constant(value):
    raise ValueError("non-finite JSON number: %s" % value)


def _reject_json_duplicates(pairs):
    value = {}
    for key, item in pairs:
        if key in value:
            raise ValueError("duplicate JSON key: %s" % key)
        value[key] = item
    return value


def _strict_json_loads(value):
    document = json.loads(
        value,
        parse_constant=_reject_json_constant,
        object_pairs_hook=_reject_json_duplicates,
    )

    def require_finite(item):
        if isinstance(item, float) and not math.isfinite(item):
            raise ValueError("non-finite JSON number")
        if isinstance(item, dict):
            for nested in item.values():
                require_finite(nested)
        elif isinstance(item, list):
            for nested in item:
                require_finite(nested)

    require_finite(document)
    return document


def _load_posting_policy():
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    path = os.path.join(root, ".system_control", "policy.json")
    try:
        before = os.stat(path)
        with open(path, "rb") as fh:
            raw = fh.read()
        after = os.stat(path)
        if ((before.st_size, before.st_mtime_ns) !=
                (after.st_size, after.st_mtime_ns) or len(raw) != after.st_size):
            raise ValueError("policy changed while being read")
        return _strict_json_loads(raw.decode("utf-8-sig"))
    except Exception:
        return None


def publication_authority(*_args, **_kwargs):
    """Compatibility denial: QA/quota evidence can never grant publication rights."""
    return (
        False,
        "qa_gate is QA/quota-only; actor labels are not authentication and never "
        "authorize scheduling or publication",
    )


def prepublish_policy_gate(channel, *, policy=None):
    """Deny prepublish use, explicitly honoring publication_authorized=false.

    Even a future ``publication_authorized=true`` is insufficient here because
    qa_gate has no authenticated owner or per-piece approval mechanism.
    """
    policy = _load_posting_policy() if policy is None else policy
    if not isinstance(policy, dict) or not isinstance(policy.get("channels"), dict):
        return False, "policy.json missing or invalid — fail closed"
    normalized = POLICY_CHANNEL.get(str(channel).strip().lower(), str(channel).strip().lower())
    channel_cfg = policy["channels"].get(normalized)
    if not isinstance(channel_cfg, dict):
        return False, "channel %s missing from policy.json — fail closed" % normalized
    if channel_cfg.get("publication_authorized") is not True:
        return False, "publication_authorized=false for channel %s" % normalized
    return (
        False,
        "qa_gate cannot authenticate owner identity or per-piece approval; "
        "publication remains blocked",
    )


def _posting_rules(policy, channel):
    limits = (policy or {}).get("limits")
    if not isinstance(limits, dict):
        raise ValueError("limits missing")
    per_day = limits.get("posts_per_day")
    if not isinstance(per_day, dict) or "default" not in per_day:
        raise ValueError("posts_per_day missing")
    for key, value in per_day.items():
        if (not isinstance(key, str) or not key.strip() or
                key != key.strip().casefold() or isinstance(value, bool) or
                not isinstance(value, int) or value <= 0):
            raise ValueError("invalid posts_per_day")
    default_cap = per_day["default"]
    cap = per_day.get(channel, QUOTA_PER_DAY.get(channel, default_cap))
    min_gap = limits.get("min_gap_hours")
    if (isinstance(min_gap, bool) or not isinstance(min_gap, (int, float)) or
            not math.isfinite(min_gap) or min_gap <= 0):
        raise ValueError("invalid minimum gap")
    post_types = limits.get("post_types")
    if (not isinstance(post_types, list) or
            any(not isinstance(item, str) or not item.strip() for item in post_types) or
            len(post_types) != len(set(post_types)) or
            set(post_types) != COUNTED_POST_TYPES):
        raise ValueError("invalid counted post types")
    counted = set(post_types)
    state = (((policy or {}).get("channels") or {}).get(channel) or {}).get("state")
    return cap, min_gap, counted, state


def posting_quota(channel, *, now=None, ledger_rows=None, policy=None,
                  content_id=None, placement_id=None):
    """(ok, reason) — อ่าน post-ledger ของวันนี้: Pantip hard-block + โควตา/วัน + ห่างขั้นต่ำ 3 ชม.
    FAIL จะบอกเวลาที่โพสต์ได้ครั้งถัดไปเสมอ."""
    import datetime as _dt
    _al = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "automation-log")
    if _al not in sys.path:
        sys.path.insert(0, _al)
    import post_ledger as PL
    ch = PL.norm_channel(channel)
    policy_channel = POLICY_CHANNEL.get(ch, ch)
    now = now or PL.now_local()
    policy = _load_posting_policy() if policy is None else policy
    if not isinstance(policy, dict) or not isinstance(policy.get("channels"), dict):
        return False, "policy.json missing or invalid — fail closed"
    channel_cfg = policy["channels"].get(policy_channel)
    if not isinstance(channel_cfg, dict):
        return False, "channel %s missing from policy.json — fail closed" % policy_channel
    if policy_channel == "pantip":
        pantip = evaluate_pantip_eligibility(
            policy,
            now=now,
            content_id=content_id,
            placement_id=placement_id,
        )
        if not pantip.allowed:
            return False, "Pantip eligibility blocked: " + pantip.reason
    state = channel_cfg.get("state")
    allowed = state in ALLOWED_CHANNEL_STATES
    weekly_quota = None
    if state == "limited":
        try:
            phase_until = _dt.date.fromisoformat(str(channel_cfg["phase_until"]))
            weekly_quota = int(channel_cfg.get("weekly_quota") or 0)
            allowed = phase_until >= now.date() and weekly_quota > 0
        except (KeyError, TypeError, ValueError):
            allowed = False
    if not allowed:
        return False, "channel state/window is not explicitly allowed in policy.json (%s)" % state
    try:
        cap, min_gap_hours, counted_types, _ = _posting_rules(policy, ch)
    except (TypeError, ValueError):
        return False, "posting limits invalid in policy.json — fail closed"
    if cap <= 0:
        return False, "posting quota is zero in policy.json — fail closed"
    if (not isinstance(now, _dt.datetime) or
            now.tzinfo is None or now.utcoffset() is None):
        return False, "current time must be timezone-aware — fail closed"
    now = now.astimezone(PL.TZ)
    stamps = []
    daily_count = 0
    unknown_daily_times = 0
    weekly_count = 0
    week_start = now.date() - _dt.timedelta(days=now.weekday())
    week_end = week_start + _dt.timedelta(days=6)
    try:
        rows = list(PL.iter_ledger()) if ledger_rows is None else list(ledger_rows)
    except Exception as exc:
        return False, "post-ledger unavailable or corrupt (%s) — fail closed" % type(exc).__name__
    for row_number, r in enumerate(rows, 1):
        if not isinstance(r, dict):
            return False, "post-ledger row %d is malformed — fail closed" % row_number
        if r.get("type") not in counted_types or PL.norm_channel(r.get("channel")) != ch:
            continue
        t = None
        scheduled = r.get("publish_at") or r.get("scheduled_for")
        if scheduled is not None:
            raw_scheduled = str(scheduled).strip()
            try:
                if len(raw_scheduled) == 10:
                    eff_date = _dt.date.fromisoformat(raw_scheduled)
                else:
                    t = _dt.datetime.fromisoformat(raw_scheduled.replace("Z", "+00:00"))
                    if t.tzinfo is None or t.utcoffset() is None:
                        raise ValueError("scheduled time has no timezone")
                    t = t.astimezone(PL.TZ)
                    eff_date = t.date()
            except (TypeError, ValueError, OverflowError):
                return False, (
                    "post-ledger row %d has invalid scheduled publication time — fail closed"
                    % row_number
                )
        else:
            try:
                t = _dt.datetime.fromisoformat(
                    str(r.get("posted_at") or r.get("ts") or "").strip().replace(
                        "Z", "+00:00"
                    )
                )
                if t.tzinfo is None or t.utcoffset() is None:
                    raise ValueError("publication time has no timezone")
                t = t.astimezone(PL.TZ)
            except (TypeError, ValueError, OverflowError):
                return False, (
                    "post-ledger row %d has invalid publication time — fail closed"
                    % row_number
                )
            eff_date = t.date()
        if week_start <= eff_date <= week_end:
            weekly_count += 1
        if eff_date == now.date():
            daily_count += 1
            if t is None:
                unknown_daily_times += 1
            else:
                stamps.append(t)
    if weekly_quota is not None and weekly_count >= weekly_quota:
        return False, "weekly quota full (%d/%d this week · channel %s)" % (weekly_count, weekly_quota, ch)
    if daily_count >= cap:
        nxt = (now + _dt.timedelta(days=1)).replace(hour=8, minute=0, second=0, microsecond=0)
        return False, "โควตาเต็ม (%d/%d วันนี้ ช่อง %s) — โพสต์ได้อีกครั้ง: %s" % (daily_count, cap, ch, nxt.strftime("%Y-%m-%d %H:%M"))
    if unknown_daily_times:
        return False, (
            "มีโพสต์/คิววันนี้ %d รายการแต่ไม่มีเวลาเผยแพร่ที่แน่นอน; "
            "พิสูจน์ช่วงห่างไม่ได้ — fail closed" % unknown_daily_times
        )
    if stamps:
        last = max(stamps)
        gap_h = (now - last).total_seconds() / 3600.0
        if gap_h < min_gap_hours:
            nxt = last + _dt.timedelta(hours=min_gap_hours)
            return False, "ยังไม่ครบ 3 ชม.จากโพสต์ก่อน (%.1f ชม.) — โพสต์ได้อีกครั้ง: %s" % (gap_h, nxt.strftime("%H:%M"))
    weekly_note = (" · week %d/%d" % (weekly_count, weekly_quota)
                   if weekly_quota is not None else "")
    return True, "ok (%d/%d วันนี้%s · gap ผ่าน)" % (daily_count, cap, weekly_note)


def check(frame_path):
    if not os.path.exists(frame_path):
        return {"pass": False, "fails": ["frame not found: " + frame_path], "status": "NO_FILE"}
    try:
        import PIL.Image  # google-generativeai accepts PIL images for vision
        img = PIL.Image.open(frame_path)
    except Exception as e:
        # fall back: pass the path note; if no key it will skip anyway
        img = None
    try:
        txt, st = free_ai.generate(CHECKLIST, model="smart", images=([img] if img else None))  # vision QA gate
    finally:
        if img is not None:
            img.close()
    if st == "NO_KEY":
        return {"pass": None, "fails": [], "status": "SKIP_NO_KEY"}
    if st != "ok" or not txt:
        return {"pass": None, "fails": [], "status": st}
    try:
        data = _strict_json_loads(txt[txt.find("{"):txt.rfind("}") + 1])
        if not isinstance(data, dict):
            raise ValueError("visual QA output is not an object")
        data["status"] = "ok"
        return data
    except Exception:
        return {"pass": None, "fails": [], "status": "PARSE_ERROR", "raw": txt[:200]}


def main(argv=None):
    args = list(sys.argv[1:] if argv is None else argv)
    if args and args[0] == "--quota":
        if len(args) < 2:
            print("QUOTA-ONLY BLOCKED: --quota requires a channel")
            return 2
        if "--actor" in args[2:]:
            print(
                "QUOTA-ONLY BLOCKED: --actor is not accepted; an actor label is "
                "not identity proof and qa_gate never authorizes publication"
            )
            return 2
        if len(args) != 2:
            print("QUOTA-ONLY BLOCKED: unsupported arguments")
            return 2
        ok, reason = posting_quota(args[1])
        print(
            ("QUOTA-ONLY OK " if ok else "QUOTA-ONLY FAIL ")
            + reason
            + " | NOT PUBLICATION AUTHORITY"
        )
        return 0 if ok else 2
    if args and args[0] == "--prepublish":
        if len(args) != 2:
            print("PREPUBLISH BLOCKED: --prepublish requires exactly one channel")
            return 2
        _ok, reason = prepublish_policy_gate(args[1])
        print("PREPUBLISH BLOCKED: " + reason)
        return 2
    if not args:
        print(
            "usage: python qa_gate.py <frame.png> | --quota <channel> "
            "| --prepublish <channel> (deny-only compatibility check)"
        )
        return 0
    if len(args) != 1:
        print("VISUAL-QA-ONLY BLOCKED: expected exactly one frame path")
        return 2
    res = check(args[0])
    print(json.dumps(res, ensure_ascii=False))
    print("# VISUAL-QA-ONLY: this result never authorizes scheduling or publication")
    passed = res.get("status") == "ok" and res.get("pass") is True
    if not passed:
        print("# PUBLICATION_BLOCKED: visual QA did not return an explicit pass")
    return 0 if passed else 2


if __name__ == "__main__":
    sys.exit(main())
