#!/usr/bin/env python3
"""Fail closed when scheduled automation can mutate remote/public state."""
import argparse
import hashlib
import json
import math
import re
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

try:
    import tomllib
except ImportError:  # pragma: no cover - Python < 3.11 is reported UNKNOWN
    tomllib = None


def _strict_json_loads(value):
    def reject_constant(token):
        raise ValueError("non-finite JSON constant: " + token)

    def reject_duplicates(pairs):
        result = {}
        for key, item in pairs:
            if key in result:
                raise ValueError("duplicate JSON key: " + key)
            result[key] = item
        return result

    document = json.loads(
        value,
        parse_constant=reject_constant,
        object_pairs_hook=reject_duplicates,
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


ROOT = Path(__file__).resolve().parents[1]
PROMPT_ROOTS = (
    Path(r"C:\Users\nL_ku\Claude\Scheduled"),
    Path(r"C:\Users\nL_ku\.claude\scheduled-tasks"),
)
CLAUDE_REGISTRY_SPECS = (
    ("cowork", "local-agent-mode-sessions"),
    ("ccd", "claude-code-sessions"),
)
CODEX_AUTOMATIONS_ROOT = Path.home() / ".codex" / "automations"
WINDOWS_TASK_NAME_RE = re.compile(r"(?:ngernduangold|ngern-tiktok)", re.IGNORECASE)
GIT_MUTATION = re.compile(
    r"(?:\bgit\s+(?:add|commit|push)\b|\bcommit\b[^\r\n;|]{0,80}\bpush\b)",
    re.IGNORECASE,
)
PROMPT_MUTATION = re.compile(
    r"(?:post_guard\.py[^\r\n]*--repair-youtube|yt_upload[^\r\n]*--live|"
    r"publish_(?:fb|ig)|schedule_(?:fb|ig)|\bfile_upload\b|"
    r"(?:netlify|vercel|wrangler)\s+deploy|npm\s+run\s+deploy|"
    r"(?:claude(?:-|\s+)in(?:-|\s+)chrome|windows(?:-|\s+)mcp|browser)[^\r\n]{0,80}(?:\bpublish\b|\bpost\b|\bcomment\b|คอมเมนต์|โพสต์|เผยแพร่)|"
    r"(?:\bpublish\b|\bpost\b|\bcomment\b|คอมเมนต์|โพสต์|เผยแพร่)[^\r\n]{0,80}(?:claude(?:-|\s+)in(?:-|\s+)chrome|windows(?:-|\s+)mcp|browser)|"
    r"(?:^|→)\s*(?:\*\*)?(?:click|press|คลิก|กด)[^\r\n]{0,80}(?:\bpublish\b|\bpost\b|\bshare\b|\bcomment\b|โพสต์|แชร์|เผยแพร่|คอมเมนต์)|"
    r"ปุ่มส่ง[^\r\n]*(?:comment|คอมเมนต์)|คลิกช่องคอมเมนต์|"
    r"(?:^|(?<=[\s—→:(])|(?<=แต่))(?:ให้|ต้อง|จง|โปรด)\s*"
    r"(?:ทำการ|ดำเนินการ|ซ่อม(?:แล้ว)?)?\s*"
    r"(?:โพสต์(?:ซ้ำ)?|เผยแพร่|อัปโหลด|กดส่ง)|"
    r"(?:^|[—→:]\s*)(?:ซ่อม(?:แล้ว)?\s*)?"
    r"(?:โพสต์ซ้ำวันนี้|โพสต์ให้เรียบร้อย|เผยแพร่ให้เรียบร้อย|อัปโหลดให้เรียบร้อย))",
    re.IGNORECASE,
)
AUTOMATION_RISK_PATTERNS = {
    "external_notify": re.compile(
        r"(?:\b(?:send|notify|message|email|post)\b[^\r\n]{0,80}"
        r"\b(?:slack|telegram|discord|teams|gmail|e-?mail|sms|webhook|line\s*notify)\b|"
        r"\b(?:slack|telegram|discord|teams|gmail|e-?mail|sms|webhook|line\s*notify)\b"
        r"[^\r\n]{0,80}\b(?:send|notify|message|post)\b|"
        r"(?:ส่ง|แจ้ง|โพสต์)[^\r\n]{0,80}(?:อีเมล|ไลน์|เทเลแกรม|สแล็ก|Slack|Telegram|เว็บฮุก)|"
        r"--[a-z0-9_-]*(?:telegram|slack|webhook|email)[a-z0-9_-]*|"
        r"(?:curl|invoke-webrequest|invoke-restmethod)[^\r\n]{0,120}(?:webhook|hooks\.slack|api\.telegram))",
        re.IGNORECASE,
    ),
    "external_storage_write": re.compile(
        r"(?:\bcreate_file\b|"
        r"(?:google\s+drive|drive\s+connector)[^\r\n]{0,120}"
        r"(?:\bupload\b|\bcreate\b|\bwrite\b|อัปโหลด|อัป)|"
        r"(?:\bupload\b|อัปโหลด|อัป)[^\r\n]{0,120}"
        r"(?:google\s+drive|drive\s+connector|parentId))",
        re.IGNORECASE,
    ),
    "package_install": re.compile(
        r"(?:\bpython(?:\.exe)?\s+-m\s+pip\s+install\b|"
        r"\b(?:pip3?|uv|poetry|npm|pnpm|yarn|bun|choco|winget|scoop|apt(?:-get)?|dnf|yum)"
        r"\s+(?:install|add)\b|\bnpx\b)",
        re.IGNORECASE,
    ),
    "scheduler_mutation": re.compile(
        r"(?:\b(?:update|create|delete|enable|disable|start|register|unregister)"
        r"_scheduled_task\b|"
        r"\b(?:register|unregister|enable|disable|start|set)-scheduledtask\b|"
        r"\bupdate_scheduled_task\b|"
        r"\b(?:edit|update|change|remove|delete|enable|disable|start|create|"
        r"restore|reschedule)\b[^\r\n]{0,100}"
        r"\b(?:automation\s+(?:id|task|schedule|rrule|config)|"
        r"scheduled[ -]?task|scheduler|schedule|rrule|cron)\b|"
        r"(?:ให้|ต้อง|จง|โปรด)\s*(?:ทำการ)?\s*"
        r"(?:ลบ|แก้|เปลี่ยน|คืน|(?<!ติด)ตั้ง|ปิด|เปิด|เลื่อน|สร้าง)"
        r"[^\r\n]{0,100}(?:automation(?:\s+(?:id|task|schedule|rrule|config|นี้))?|"
        r"scheduled[ -]?task|scheduler|ตารางทำงาน|rrule|cron|งานตามเวลา))",
        re.IGNORECASE,
    ),
    "browser_control": re.compile(
        r"\b(?:chrome|chromium|firefox|msedge|browser|playwright|selenium|"
        r"computer-use|windows-mcp|claude(?:-|\s+)in(?:-|\s+)chrome)\b",
        re.IGNORECASE,
    ),
    "upload_or_live_publish": re.compile(
        r"(?:\b(?:upload|publish|submit)\b|"
        r"\bpost\b(?!\s+(?:ledger|guard|history|plan|queue|id)\b)|"
        r"อัปโหลด|โพสต์|เผยแพร่)",
        re.IGNORECASE,
    ),
    "deploy": re.compile(
        r"(?:\b(?:netlify|vercel|wrangler)\s+deploy\b|\bnpm\s+run\s+deploy\b|"
        r"\bdeploy\b|ดีพลอย)",
        re.IGNORECASE,
    ),
}
PROJECT_PROMPT_RE = re.compile(
    r"(?:ngernduangold|เงินเดือนสมองทอง|"
    r"C:\\Users\\nL_ku\\ngernduangold-site)",
    re.IGNORECASE,
)
CLAUDE_SIDE_EFFECT_CAPABILITIES = {
    "external_notify": "external_notify",
    "external_storage_write": "external_storage_write",
    "package_install": "package_install",
    "scheduler_mutation": "scheduler_mutation",
    "remote_git": "git_push",
    "remote_publisher": "social_publish",
    "deploy": "deploy",
}
WORKFLOW_MUTATION = re.compile(
    r"git\s+push|publish_fb|publish_ig|schedule_fb|schedule_ig|DRY_RUN\s*:\s*0|contents\s*:\s*write",
    re.IGNORECASE,
)
FIRST_SIGNAL_SAME_DATE_PROVIDER = re.compile(
    r"(?:same[- ]?date|same\s+day|date\s*\+\s*provider|"
    r"วันที่เดียวกัน|วันเดียวกัน)"
    r"[^;\r\n|]{0,100}(?:provider|merchant|campaign|ผู้ให้บริการ|แคมเปญ)",
    re.IGNORECASE,
)
FIRST_SIGNAL_SCALE = re.compile(
    r"(?:\b(?:winner|scale|double[- ]?down)\b|ผู้ชนะ|ทุ่มต่อ|ขยายผล)",
    re.IGNORECASE,
)
FIRST_SIGNAL_PENDING_REVENUE = re.compile(
    r"(?:(?:\bpending\b|รออนุมัติ)[^;\r\n|]{0,80}"
    r"(?:\brevenue\b|รายได้|ทำเงิน)|"
    r"(?:\brevenue\b|รายได้|ทำเงิน)[^;\r\n|]{0,80}"
    r"(?:\bpending\b|รออนุมัติ))",
    re.IGNORECASE,
)
FIRST_SIGNAL_RAW_CLICKS_DEMAND = re.compile(
    r"(?:(?:raw\s+AccessTrade\s+clicks|ยอดคลิกดิบ(?:ของ)?\s*AccessTrade)"
    r"[^;\r\n|]{0,100}(?:demand|signal|winner|scale|ทุ่มต่อ|เลือก(?:หน้า|ช่อง|หัวข้อ))|"
    r"(?:demand|signal|winner|scale|ทุ่มต่อ|เลือก(?:หน้า|ช่อง|หัวข้อ))"
    r"[^;\r\n|]{0,100}(?:raw\s+AccessTrade\s+clicks|ยอดคลิกดิบ(?:ของ)?\s*AccessTrade))",
    re.IGNORECASE,
)
FIRST_SIGNAL_SAFE_NEGATION = re.compile(
    r"(?:\b(?:do\s+not|never|must\s+not|not\s+sufficient|insufficient|"
    r"no\s+winner)\b|"
    r"(?:ห้าม|อย่า)\s*(?:ใช้|สรุป|จับคู่|ประกาศ|เสนอ|นับ)|"
    r"ไม่(?:ใช่|ถือเป็น|เพียงพอ|อนุญาตให้|เสนอ|ประกาศ|นำไปใช้))",
    re.IGNORECASE,
)
FIRST_SIGNAL_CLAUSE_BREAK = re.compile(
    r"[;|]|\bbut\b|\bhowever\b|แต่",
    re.IGNORECASE,
)


DIRECT_PROHIBITION = re.compile(
    r"(?:\bdo\s+not\b|\bnever\b|\bmust\s+not\b|ห้าม|อย่า)[\s`*_#·:—-]{0,20}"
    r"(?:run|invoke|call|use|open|click|press|upload|publish|post|share|deploy|git|"
    r"send|notify|message|email|รัน|เรียก|ใช้|เปิด|คลิก|กด|ส่ง|แจ้ง|"
    r"อัปโหลด|โพสต์|แชร์|เผยแพร่|ดีพลอย)",
    re.IGNORECASE,
)
BARE_PROHIBITION = re.compile(
    r"(?:\bdo\s+not\b|\bnever\b|\bmust\s+not\b|ห้าม|อย่า)\s*[`*_]*\s*$",
    re.IGNORECASE,
)
SCOPED_PROHIBITION = re.compile(
    r"(?:\bdo\s+not\b|\bnever\b|\bmust\s+not\b|"
    r"(?<![ก-๙])(?:ห้าม|อย่า)(?![ก-๙]))"
    r"[^;|,\r\n]{0,120}$",
    re.IGNORECASE,
)


def mutation_is_explicitly_prohibited(line, match_start):
    """Recognise a prohibition only in the same clause as the mutation.

    This avoids the dangerous trap ``Do not stop; run uploader --live`` where a
    negation elsewhere on the line used to exempt the live action.
    """
    prefix = line[:match_start]
    clause = re.split(r"[;|]|\bbut\b|\bhowever\b|แต่", prefix,
                      flags=re.IGNORECASE)[-1]
    return bool("no-op" in clause.casefold() or
                DIRECT_PROHIBITION.search(clause) or BARE_PROHIBITION.search(clause) or
                SCOPED_PROHIBITION.search(clause))


def executable_git_lines(text):
    findings = []
    for number, line in enumerate(text.splitlines(), 1):
        for match in GIT_MUTATION.finditer(line):
            if not mutation_is_explicitly_prohibited(line, match.start()):
                findings.append(number)
                break
    return findings


def executable_publisher_lines(text):
    """Return non-negated lines that directly invoke public/remote mutation."""
    findings = []
    for number, line in enumerate(text.splitlines(), 1):
        for match in PROMPT_MUTATION.finditer(line):
            if not mutation_is_explicitly_prohibited(line, match.start()):
                findings.append(number)
                break
    return findings


def executable_automation_risks(text):
    """Return ``(category, line)`` for high-risk automation instructions."""
    scanners = [("remote_git", GIT_MUTATION), ("remote_publisher", PROMPT_MUTATION)]
    scanners.extend(AUTOMATION_RISK_PATTERNS.items())
    findings = []
    seen = set()
    for number, line in enumerate(str(text).splitlines(), 1):
        for category, pattern in scanners:
            for match in pattern.finditer(line):
                if mutation_is_explicitly_prohibited(line, match.start()):
                    continue
                key = (category, number)
                if key not in seen:
                    seen.add(key)
                    findings.append(key)
                break
    return findings


def prompt_is_tombstoned(text):
    """Ignore legacy instructions only when an early explicit no-op tombstone exists."""
    head = "\n".join(text.splitlines()[:25]).casefold()
    return "## retired — no-op" in head or "## retired - no-op" in head


def prompt_is_resolved_tombstone(text):
    """Recognise a deliberately stopped half of a dual-root task collision."""
    head = "\n".join(text.splitlines()[:25]).casefold()
    return (prompt_is_tombstoned(text)
            or "# ป้ายหลุมศพ" in head
            or "non_executable_mirror" in head)


def prompt_is_explicitly_retired(text):
    """Return true only for an explicit early retirement marker.

    ``NON_EXECUTABLE_MIRROR`` is deliberately excluded. Mirror ownership is a
    registry fact, not something a prompt may claim about itself.
    """
    head = "\n".join(text.splitlines()[:25]).casefold()
    return prompt_is_tombstoned(text) or "# ป้ายหลุมศพ" in head


def _first_signal_clause(line, start, end):
    """Return the clause containing a candidate attribution instruction."""
    left, right = 0, len(line)
    for match in FIRST_SIGNAL_CLAUSE_BREAK.finditer(line):
        if match.end() <= start:
            left = match.end()
        elif match.start() >= end:
            right = match.start()
            break
    return line[left:right]


def first_signal_attribution_risks(text):
    """Detect fail-open first-signal inference and scaling instructions.

    A paid AccessTrade outcome can only name a channel/page winner when the
    prompt also requires deterministic evidence. Same-date/provider matching,
    pending-as-revenue, and raw AccessTrade click demand inference are always
    denied unless the containing clause explicitly prohibits them.
    """
    patterns = (
        ("same_date_provider", FIRST_SIGNAL_SAME_DATE_PROVIDER),
        ("scale_without_paid_deterministic", FIRST_SIGNAL_SCALE),
        ("pending_as_revenue", FIRST_SIGNAL_PENDING_REVENUE),
        ("raw_clicks_as_demand", FIRST_SIGNAL_RAW_CLICKS_DEMAND),
    )
    findings = []
    seen = set()
    for number, line in enumerate(str(text).splitlines(), 1):
        for category, pattern in patterns:
            for match in pattern.finditer(line):
                clause = _first_signal_clause(line, match.start(), match.end())
                prohibited = bool(FIRST_SIGNAL_SAFE_NEGATION.search(clause))
                evidence_bound = (
                    category == "scale_without_paid_deterministic"
                    and "paid" in clause.casefold()
                    and "deterministic" in clause.casefold()
                )
                if prohibited or evidence_bound:
                    continue
                key = (category, number)
                if key not in seen:
                    seen.add(key)
                    findings.append(key)
                break
    return findings


def _normalized_path(path):
    """Normalize a local identity path without requiring it to exist."""
    try:
        value = str(Path(path).resolve(strict=False))
    except (OSError, ValueError, TypeError):
        value = str(path)
    return value.replace("/", "\\").casefold()


def _candidate_claude_user_data_roots(home=None):
    """Return bounded Claude Desktop user-data locations (no recursive scan)."""
    home = Path(home) if home is not None else Path.home()
    candidates = [home / "AppData" / "Roaming" / "Claude"]
    packages = home / "AppData" / "Local" / "Packages"
    if packages.is_dir():
        candidates.extend(
            path / "LocalCache" / "Roaming" / "Claude"
            for path in sorted(packages.glob("Claude_*"))
        )
    unique = []
    seen = set()
    for path in candidates:
        key = _normalized_path(path)
        if key not in seen:
            seen.add(key)
            unique.append(path)
    return unique


def _load_claude_registry(path, name, task_root):
    """Read and validate one scheduler registry from a stable byte snapshot."""
    path = Path(path)
    task_root = Path(task_root)
    try:
        before = path.stat()
        raw = path.read_bytes()
        after = path.stat()
    except OSError as exc:
        return None, "%s registry unreadable (%s)" % (name, type(exc).__name__)
    if (before.st_size != after.st_size or
            before.st_mtime_ns != after.st_mtime_ns or
            len(raw) != after.st_size):
        return None, "%s registry changed while being read" % name
    try:
        document = _strict_json_loads(raw.decode("utf-8-sig"))
    except (UnicodeError, ValueError):
        return None, "%s registry is not valid UTF-8 JSON" % name
    rows = document.get("scheduledTasks") if isinstance(document, dict) else None
    if not isinstance(rows, list):
        return None, "%s registry scheduledTasks is not a list" % name
    records = []
    seen = set()
    for row in rows:
        if not isinstance(row, dict):
            return None, "%s registry contains a malformed record" % name
        task_id = row.get("id")
        enabled = row.get("enabled")
        file_path = row.get("filePath")
        if (not isinstance(task_id, str) or not task_id or
                not isinstance(enabled, bool) or
                not isinstance(file_path, str) or not file_path):
            return None, "%s registry record identity/state is malformed" % name
        if task_id in seen:
            return None, "%s registry has duplicate id: %s" % (name, task_id)
        seen.add(task_id)
        expected = task_root / task_id / "SKILL.md"
        if _normalized_path(file_path) != _normalized_path(expected):
            return None, "%s registry filePath escapes bound root: %s" % (name, task_id)
        if not Path(file_path).is_file():
            return None, "%s registry task file is missing: %s" % (name, task_id)
        records.append({
            "id": task_id,
            "enabled": enabled,
            "file_path": str(Path(file_path)),
        })
    return {
        "name": name,
        "task_root": str(task_root),
        "registry_path": str(path),
        "sha256": hashlib.sha256(raw).hexdigest(),
        "size": len(raw),
        "mtime_ns": after.st_mtime_ns,
        "records": records,
    }, None


def query_claude_scheduler_registries(prompt_roots=PROMPT_ROOTS,
                                      user_data_roots=None):
    """Locate the two enabled-state registries used by Claude Desktop.

    Folder presence is never treated as execution authority. Each manager must
    resolve to exactly one valid account/org registry whose ``filePath`` values
    are bound to that manager's prompt root.
    """
    if len(prompt_roots) < len(CLAUDE_REGISTRY_SPECS):
        return {"schema_version": 1, "status": "UNKNOWN",
                "reason": "two prompt roots are required", "sources": []}
    bases = ([Path(path) for path in user_data_roots]
             if user_data_roots is not None else _candidate_claude_user_data_roots())
    sources = []
    for index, (name, storage_dir) in enumerate(CLAUDE_REGISTRY_SPECS):
        candidates = []
        for base in bases:
            candidates.extend(sorted((base / storage_dir).glob("*/*/scheduled-tasks.json")))
        unique = []
        seen = set()
        for candidate in candidates:
            key = _normalized_path(candidate)
            if key not in seen:
                seen.add(key)
                unique.append(candidate)
        if len(unique) != 1:
            return {
                "schema_version": 1,
                "status": "UNKNOWN",
                "reason": "%s registry candidate count is %d" % (name, len(unique)),
                "sources": sources,
            }
        source, error = _load_claude_registry(unique[0], name, prompt_roots[index])
        if error:
            return {"schema_version": 1, "status": "UNKNOWN",
                    "reason": error, "sources": sources}
        sources.append(source)
    for source in sources:
        try:
            current = Path(source["registry_path"]).stat()
        except OSError as exc:
            return {"schema_version": 1, "status": "UNKNOWN",
                    "reason": "registry stability check failed (%s)" % type(exc).__name__,
                    "sources": sources}
        if (current.st_size != source["size"] or
                current.st_mtime_ns != source["mtime_ns"]):
            return {"schema_version": 1, "status": "UNKNOWN",
                    "reason": "registry changed during cross-source snapshot",
                    "sources": sources}
    return {"schema_version": 1, "status": "OK", "sources": sources}


def _validated_registry_maps(inventory, prompt_roots):
    """Validate an injected/discovered inventory and index records by task id."""
    if not isinstance(inventory, dict) or inventory.get("status") != "OK":
        reason = inventory.get("reason") if isinstance(inventory, dict) else "invalid inventory"
        return None, "Claude scheduler registry UNKNOWN: " + str(reason)
    sources = inventory.get("sources")
    if not isinstance(sources, list) or len(sources) != len(CLAUDE_REGISTRY_SPECS):
        return None, "Claude scheduler registry UNKNOWN: source count mismatch"
    maps = []
    for index, ((expected_name, _storage), source) in enumerate(
            zip(CLAUDE_REGISTRY_SPECS, sources)):
        if not isinstance(source, dict) or source.get("name") != expected_name:
            return None, "Claude scheduler registry UNKNOWN: source identity mismatch"
        if _normalized_path(source.get("task_root")) != _normalized_path(prompt_roots[index]):
            return None, "Claude scheduler registry UNKNOWN: task root mismatch"
        records = source.get("records")
        if not isinstance(records, list):
            return None, "Claude scheduler registry UNKNOWN: records missing"
        indexed = {}
        for record in records:
            if not isinstance(record, dict):
                return None, "Claude scheduler registry UNKNOWN: malformed record"
            task_id = record.get("id")
            enabled = record.get("enabled")
            file_path = record.get("file_path")
            if (not isinstance(task_id, str) or not task_id or
                    not isinstance(enabled, bool) or
                    not isinstance(file_path, str)):
                return None, "Claude scheduler registry UNKNOWN: malformed record fields"
            if task_id in indexed:
                return None, "Claude scheduler registry UNKNOWN: duplicate id " + task_id
            expected = Path(prompt_roots[index]) / task_id / "SKILL.md"
            if _normalized_path(file_path) != _normalized_path(expected):
                return None, "Claude scheduler registry UNKNOWN: filePath mismatch " + task_id
            indexed[task_id] = record
        maps.append(indexed)
    return maps, None


def scheduler_ownership_export(prompt_roots=PROMPT_ROOTS, scheduler_registry=None,
                               user_data_roots=None):
    """Return a machine-readable owner/mirror/retired view for shared prompts."""
    inventory = scheduler_registry
    if inventory is None:
        inventory = query_claude_scheduler_registries(prompt_roots, user_data_roots)
    maps, error = _validated_registry_maps(inventory, prompt_roots)
    if error:
        return {"schema_version": 1, "status": "UNKNOWN", "reason": error,
                "sources": inventory.get("sources", []) if isinstance(inventory, dict) else [],
                "ownership": []}
    left, right = [Path(path) for path in prompt_roots[:2]]
    left_ids = {path.parent.name: path for path in left.glob("*/SKILL.md")}
    right_ids = {path.parent.name: path for path in right.glob("*/SKILL.md")}
    ownership = []
    for task_id in sorted(set(left_ids) & set(right_ids)):
        root_states = []
        for index, (name, _storage) in enumerate(CLAUDE_REGISTRY_SPECS):
            path = (left_ids, right_ids)[index][task_id]
            try:
                text = path.read_text(encoding="utf-8")
            except (OSError, UnicodeError):
                return {"schema_version": 1, "status": "UNKNOWN",
                        "reason": "shared prompt unreadable: " + task_id,
                        "sources": inventory.get("sources", []), "ownership": ownership}
            record = maps[index].get(task_id)
            explicit_retirement = prompt_is_explicitly_retired(text)
            if record is not None and record["enabled"]:
                state = "live"
            elif record is not None or explicit_retirement:
                state = "retired"
            else:
                state = "mirror"
            root_states.append({
                "name": name,
                "prompt_path": str(path),
                "registry_state": ("enabled" if record and record["enabled"] else
                                   "disabled" if record else "absent"),
                "explicit_retirement": explicit_retirement,
                "state": state,
                "inconsistent": bool(record and record["enabled"] and explicit_retirement),
            })
        live_count = sum(item["state"] == "live" for item in root_states)
        inconsistent = any(item["inconsistent"] for item in root_states)
        if inconsistent:
            verdict, reason = "FAIL", "enabled registry points to retired prompt"
        elif live_count > 1:
            verdict, reason = "FAIL", "both roots are live"
        elif live_count == 1:
            verdict, reason = "PASS", "exactly one live owner"
        elif all(item["state"] == "mirror" for item in root_states):
            verdict, reason = "FAIL", "both roots are unregistered mirrors"
        else:
            verdict, reason = "PASS", "no live owner; task is explicitly retired"
        ownership.append({"task_id": task_id, "roots": root_states,
                          "verdict": verdict, "reason": reason})
    return {"schema_version": 1, "status": "OK",
            "sources": inventory.get("sources", []), "ownership": ownership}


def shared_live_prompt_drift(prompt_roots, scheduler_registry=None,
                             user_data_roots=None):
    """Fail only from scheduler authority, never from prompt self-description."""
    if len(prompt_roots) < 2:
        return []
    left, right = prompt_roots[:2]
    if not left.exists() or not right.exists():
        return []
    export = scheduler_ownership_export(
        prompt_roots, scheduler_registry=scheduler_registry,
        user_data_roots=user_data_roots,
    )
    if export.get("status") != "OK":
        return [export.get("reason", "Claude scheduler registry UNKNOWN")]
    findings = []
    for item in export["ownership"]:
        if item["verdict"] == "PASS":
            continue
        if item["reason"] == "both roots are live":
            findings.append("duplicate executable task id across scheduler registries: " +
                            item["task_id"])
        elif item["reason"] == "both roots are unregistered mirrors":
            findings.append("duplicate prompt id has no registered owner (both mirrors): " +
                            item["task_id"])
        else:
            findings.append(item["reason"] + ": " + item["task_id"])
    return findings


def scan_enabled_claude_tasks(inventory, role_path=None):
    """Scan only registry-enabled project prompts for unattended side effects.

    Folder presence is not execution authority, so disabled/orphan prompt bodies
    are intentionally ignored here. Conversely, an enabled registry entry that
    points at an explicit no-op tombstone is operational drift: it burns a
    scheduler slot and can hide a mistakenly retired live routine.
    """
    if not isinstance(inventory, dict) or inventory.get("status") != "OK":
        reason = inventory.get("reason") if isinstance(inventory, dict) else "invalid inventory"
        return ["Claude scheduler registry UNKNOWN: " + str(reason)]
    sources = inventory.get("sources")
    if not isinstance(sources, list):
        return ["Claude scheduler registry UNKNOWN: sources missing"]
    role_path = Path(role_path) if role_path is not None else (
        ROOT / ".system_control" / "role_capabilities.json"
    )
    try:
        roles = _strict_json_loads(role_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, ValueError):
        return ["role capability matrix is unreadable for enabled Claude tasks"]
    if not isinstance(roles, dict) or roles.get("default") != "deny":
        return ["role capability matrix does not default deny for enabled Claude tasks"]
    actors = roles.get("actors")
    actors = actors if isinstance(actors, dict) else {}
    manager_actor = {"cowork": "cowork", "ccd": "claude_code"}
    findings = []
    for source in sources:
        if not isinstance(source, dict):
            findings.append("Claude scheduler registry UNKNOWN: malformed source")
            continue
        manager = source.get("name")
        actor_name = manager_actor.get(manager)
        capabilities = actors.get(actor_name) if actor_name else None
        if not isinstance(capabilities, dict):
            findings.append(
                "Claude scheduler manager has no role capability mapping: " + str(manager)
            )
            continue
        records = source.get("records")
        if not isinstance(records, list):
            findings.append("Claude scheduler registry UNKNOWN: records missing")
            continue
        for record in records:
            if not isinstance(record, dict) or record.get("enabled") is not True:
                continue
            task_id = record.get("id")
            file_path = record.get("file_path")
            if not isinstance(task_id, str) or not isinstance(file_path, str):
                findings.append("Claude scheduler registry UNKNOWN: enabled record malformed")
                continue
            path = Path(file_path)
            try:
                text = path.read_text(encoding="utf-8")
            except (OSError, UnicodeError):
                findings.append("enabled Claude task prompt unreadable: " + task_id)
                continue
            if not (WINDOWS_TASK_NAME_RE.search(task_id) or PROJECT_PROMPT_RE.search(text)):
                continue
            if prompt_is_explicitly_retired(text):
                findings.append("enabled Claude task points to retired no-op prompt: " + task_id)
                continue
            for category, line in executable_automation_risks(text):
                capability = CLAUDE_SIDE_EFFECT_CAPABILITIES.get(category)
                if capability is None:
                    continue
                if capabilities.get(capability) is True:
                    continue
                findings.append(
                    "enabled Claude task %s lacks %s capability for %s at %s:%d" %
                    (task_id, capability, category, path, line)
                )
    return findings


def knowledge_prompt_contract(prompt_roots):
    """Protect the item-scoped source gate in the live knowledge-post routine."""
    if not prompt_roots:
        return ["knowledge prompt root unavailable"]
    path = prompt_roots[0] / "ngernduangold-knowledge-post-noon" / "SKILL.md"
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return ["knowledge publication prompt unreadable: " + str(path)]
    findings = []
    if prompt_is_tombstoned(text):
        return findings
    invocations = [
        line for line in text.splitlines()
        if "validate_knowledge_posts.py" in line
        and not mutation_is_explicitly_prohibited(
            line, line.find("validate_knowledge_posts.py"))
    ]
    if not invocations or any("--content-id" not in line for line in invocations):
        findings.append("knowledge prompt does not bind validation to --content-id")
    strict_lines = [
        line for line in text.splitlines()
        if re.search(r"official_news_monitor\.py[^\r\n]*--strict", line, re.IGNORECASE)
        and not mutation_is_explicitly_prohibited(
            line, line.find("official_news_monitor.py"))
    ]
    if strict_lines:
        findings.append("knowledge prompt uses global --strict backlog as an item gate")
    if "Asia/Bangkok" not in text or "ห้าม fallback" not in text:
        findings.append("knowledge prompt does not pin the date row and block fallback")
    return findings


def link_health_prompt_contract(prompt_roots):
    """Require live/local landing parity without following affiliate trackers."""
    findings = []
    required = "postdeploy_smoke.py --live --compare-src site"
    for root in prompt_roots:
        path = root / "ngernduangold-link-health" / "SKILL.md"
        if not path.exists():
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            findings.append("link-health prompt unreadable: " + str(path))
            continue
        if prompt_is_tombstoned(text):
            continue
        if required not in text:
            findings.append("link-health prompt lacks fail-closed live/local comparison: " + str(path))
        if "ไม่ตาม tracker/affiliate redirect" not in text:
            findings.append("link-health prompt does not prohibit affiliate tracker requests: " + str(path))
    return findings


def operational_prompt_contract(prompt_roots):
    """Pin local proof ownership and prevent duplicate weekly execution."""
    if not prompt_roots:
        return ["operational prompt root unavailable"]
    root = Path(prompt_roots[0])
    specifications = {
        "ngernduangold-channel-heartbeat": (
            "--routine ngernduangold-channel-heartbeat --status started",
            "post-ledger.jsonl` สงวนไว้สำหรับ content/attempt evidence เท่านั้น",
            "ก่อน return/ข้าม/หยุดทุก branch",
        ),
        "ngernduangold-video-post-verify": (
            "--routine ngernduangold-video-post-verify --status ok",
            "ห้าม append/แก้ `automation-log/latest.md` โดยตรง",
            "task result เท่านั้น",
        ),
        "ngernduangold-weekly-review": (
            "WINDOWS ARTIFACT CONSUMER",
            "run_weekly end exit=0",
            "policy.json → products.items",
            "ห้ามเรียก `run_weekly.cmd`",
        ),
    }
    findings = []
    texts = {}
    for task_id, markers in specifications.items():
        path = root / task_id / "SKILL.md"
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeError):
            findings.append("operational prompt unreadable: " + str(path))
            continue
        texts[task_id] = text
        missing = [marker for marker in markers if marker not in text]
        if missing:
            findings.append(
                "operational prompt contract missing for %s: %s" %
                (task_id, ", ".join(missing))
            )
    heartbeat = texts.get("ngernduangold-channel-heartbeat", "")
    if "ให้ append 1 แถวลง `automation-log/post-ledger.jsonl`" in heartbeat:
        findings.append("channel heartbeat still writes proof directly to post ledger")
    video = texts.get("ngernduangold-video-post-verify", "")
    if "เขียนบรรทัดสั้นๆ ต่อท้าย `automation-log/latest.md`" in video:
        findings.append("video verifier still edits generated latest.md directly")
    weekly = texts.get("ngernduangold-weekly-review", "")
    for number, line in enumerate(weekly.splitlines(), 1):
        start = line.find("run_weekly.cmd")
        if start >= 0 and not mutation_is_explicitly_prohibited(line, start):
            findings.append(
                "Cowork weekly review can execute Windows weekly runner at line %d" % number
            )
    return findings


def first_signal_prompt_contract(prompt_roots):
    """Bind first-money attribution to paid, deterministic merchant evidence."""
    if len(prompt_roots) < 2:
        return ["first-signal prompt roots unavailable"]
    required = (
        "report-only",
        "`AccessTrade conversion ID`",
        "actual `Sub ID` หรือ `click ID`",
        "`timestamp/session join`",
        "merchant-level `UNATTRIBUTED`",
        "`pending` ไม่ใช่รายได้",
        "`raw AccessTrade clicks = contaminated`",
        "`paid + deterministic`",
        "ห้ามใช้ same-date+provider attribution",
        "ห้ามประกาศ winner/scale/double-down",
        "ห้าม Run now/แก้ scheduled task",
    )
    findings = []
    prompt_bytes = []
    for root in prompt_roots[:2]:
        path = Path(root) / "ngernduangold-first-signal" / "SKILL.md"
        try:
            raw = path.read_bytes()
            text = raw.decode("utf-8")
        except (OSError, UnicodeError):
            findings.append("first-signal prompt unreadable: " + str(path))
            continue
        prompt_bytes.append((path, raw))
        missing = [marker for marker in required if marker not in text]
        if missing:
            findings.append(
                "first-signal prompt contract missing at %s: %s" %
                (path, ", ".join(missing))
            )
        for category, line in first_signal_attribution_risks(text):
            findings.append(
                "first-signal prompt %s risk at %s:%d" %
                (category, path, line)
            )
    if len(prompt_bytes) == 2 and prompt_bytes[0][1] != prompt_bytes[1][1]:
        findings.append(
            "first-signal active/mirror prompt bytes diverge: %s != %s" %
            (prompt_bytes[0][0], prompt_bytes[1][0])
        )
    return findings


def workflow_is_scheduled_mutator(text):
    return bool(re.search(r"(?m)^\s*schedule\s*:", text) and WORKFLOW_MUTATION.search(text))


def publisher_source_contract(source_root=ROOT):
    """Keep every retained live-capable publisher behind the shared local gate."""
    contracts = {
        Path("automation/ig_publish.py"): (
            "authorize_live_publication", "PUBLICATION_ACTOR",
            "target_identity=IG_USER", "approval=entry.get",
            "content_source_evidence=", "media_qa_path=",
            "verify_execution_authorization",
        ),
        Path("social-autopost/publish_fb.py"): (
            "authorize_live_publication", "PUBLICATION_ACTOR",
            "target_identity=PAGE_ID", "approval=entry.get",
            "content_source_evidence=", "media_qa_path=",
            "verify_execution_authorization",
        ),
        Path("social-autopost/publish_tiktok.py"): (
            "authorize_live_publication", 'add_argument("--actor"',
            'add_argument("--target-account"', "target_identity=target_account",
            "approval=entry.get", "content_source_evidence=", "media_qa_path=",
            "verify_execution_authorization",
        ),
        Path("tools/yt_upload_batch2.py"): (
            'add_argument(\n        "--target-channel-id"',
            'add_argument(\n        "--receipt-nonce"',
            'channel_policy.get("channel_id")',
            "authorize_live_publication",
            "receipt_nonce=inputs",
            "content_source_evidence=inputs",
            "media_qa_path=inputs",
            "verify_execution_authorization",
            "validate_youtube_target_identity",
            "verify_authenticated_youtube_channel",
            "mine=True",
            "target_channel_id=target_channel_id",
            "_assert_reconciliation_clear",
            "_begin_attempt",
            "_finish_attempt",
            "PENDING_REMOTE",
            "reconciliation-only",
        ),
        Path("tools/publication_authority.py"): (
            "publication_authorized", "social_publish", "target_identity", "REQUIRED_VALIDATIONS",
            "RECEIPT_FIELDS", "_load_private_receipt", "_consume_private_receipt",
            "RECEIPT_SCHEMA_VERSION = 2", "EVIDENCE_HASH_FIELDS",
            "content_source_sha256", "_media_qa_evidence", "_enforce_slot_window",
            "verify_execution_authorization",
            "content_calendar.json", "Asia/Bangkok",
            '"youtube": ("channel_id",)',
            "source_checked_at", "tools/privacy_guard.py", "tools/public_identity_guard.py",
        ),
        Path("tools/action_authority.py"): (
            "require_actor_capabilities", 'value.get("default") != "deny"',
            "capabilities.get(action) is not True",
        ),
        Path("pipeline/official_news_monitor.py"): (
            "programmatic source acknowledgement is disabled", "confined_cli_path",
            "owner-controlled process", 'parser.add_argument("--actor"',
        ),
        Path("pipeline/push_agent.py"): (
            "permanently local-only", "if do_commit or do_push",
            "human owner must perform Git", "no files staged, committed, pushed, or deployed",
        ),
    }
    findings = []
    for relative, markers in contracts.items():
        path = Path(source_root) / relative
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            findings.append("publisher authority source unreadable: " + str(path))
            continue
        missing = [marker for marker in markers if marker not in text]
        if missing:
            findings.append(
                "publisher lacks authority contract %s: %s" %
                (path, ", ".join(missing))
            )
    ordered_boundaries = {
        Path("automation/ig_publish.py"): ("def main():", "urllib.request.Request(video_url"),
        Path("social-autopost/publish_fb.py"): ("def main():", "result = api("),
        Path("social-autopost/publish_tiktok.py"): ("def mode_post", "ctx = launch("),
    }
    for relative, (section_start, external_boundary) in ordered_boundaries.items():
        path = Path(source_root) / relative
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            continue
        start = text.find(section_start)
        section = text[start:] if start >= 0 else ""
        authority = section.find("authorize_live_publication(")
        boundary = section.find(external_boundary)
        if authority < 0 or boundary < 0 or authority > boundary:
            findings.append("publisher authority gate is not before external action: " + str(path))
    execution_boundaries = {
        Path("automation/ig_publish.py"): ("def main():", 'result = api("/%s/media"'),
        Path("social-autopost/publish_fb.py"): ("def main():", 'result = api("/%s/feed"'),
        Path("social-autopost/publish_tiktok.py"): ("def mode_post", "page.set_input_files("),
        Path("tools/yt_upload_batch2.py"): ("def run_live(", "MediaFileUpload("),
    }
    for relative, (section_start, mutation_boundary) in execution_boundaries.items():
        path = Path(source_root) / relative
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            continue
        start = text.find(section_start)
        section = text[start:] if start >= 0 else ""
        verifier = section.find("verify_execution_authorization(")
        boundary = section.find(mutation_boundary)
        if verifier < 0 or boundary < 0 or verifier > boundary:
            findings.append(
                "publisher execution revalidation is not before remote mutation: " + str(path)
            )
    youtube_path = Path(source_root) / "tools" / "yt_upload_batch2.py"
    try:
        youtube_text = youtube_path.read_text(encoding="utf-8")
    except OSError:
        youtube_text = ""
    live_start = youtube_text.find("def run_live(")
    live_section = youtube_text[live_start:] if live_start >= 0 else ""
    local_gate = live_section.find("validate_live_upload(")
    oauth_boundary = live_section.find("get_credentials(interactive=True)")
    remote_gate = live_section.find("verify_authenticated_youtube_channel(")
    media_boundary = live_section.find("MediaFileUpload(")
    attempt_boundary = live_section.find("_begin_attempt(")
    remote_mutation = live_section.find("request = service.videos().insert(")
    terminal_posted = live_section.find('_finish_attempt(action, "POSTED"')
    success_registry = live_section.find("write_json(UPLOAD_LOG_PATH")
    if (
        local_gate < 0
        or oauth_boundary < 0
        or local_gate > oauth_boundary
        or remote_gate < 0
        or media_boundary < 0
        or remote_gate > media_boundary
        or attempt_boundary < 0
        or remote_mutation < 0
        or attempt_boundary > remote_mutation
        or terminal_posted < 0
        or success_registry < 0
        or terminal_posted > success_registry
    ):
        findings.append(
            "YouTube authority/identity/attempt gates are not before external success: "
            + str(youtube_path)
        )
    push_path = Path(source_root) / "pipeline" / "push_agent.py"
    try:
        push_text = push_path.read_text(encoding="utf-8")
    except OSError:
        push_text = ""
    mutation_block = push_text.find("if do_commit or do_push")
    build_boundary = push_text.find("run = runner or _run")
    reachable_git = any(
        marker in push_text
        for marker in ('["git", "add"', '["git", "commit"', '["git", "push"')
    )
    if mutation_block < 0 or build_boundary < 0 or mutation_block > build_boundary or reachable_git:
        findings.append(
            "agent-facing release helper is not permanently local-only: " + str(push_path)
        )
    source_path = Path(source_root) / "pipeline" / "official_news_monitor.py"
    try:
        source_text = source_path.read_text(encoding="utf-8")
    except OSError:
        source_text = ""
    ack_function = source_text.find("def authorize_acknowledgements(")
    ack_block = source_text.find("programmatic source acknowledgement is disabled", ack_function)
    unsafe_ack_return = source_text.find("return sorted(requested)", ack_function)
    if ack_function < 0 or ack_block < 0 or unsafe_ack_return >= 0:
        findings.append(
            "agent-facing source monitor still permits programmatic acknowledgement: "
            + str(source_path)
        )
    return findings


def _string_fields(value, prefix=()):
    if isinstance(value, dict):
        for key, child in value.items():
            yield from _string_fields(child, prefix + (str(key),))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            yield from _string_fields(child, prefix + (str(index),))
    elif isinstance(value, str):
        yield ".".join(prefix), value


def scan_codex_automations(automation_root=CODEX_AUTOMATIONS_ROOT):
    """Read and scan bounded Codex automation TOML inventory."""
    root = Path(automation_root)
    if not root.is_dir():
        return ["Codex automation inventory UNKNOWN: root missing: " + str(root)]
    if tomllib is None:
        return ["Codex automation inventory UNKNOWN: tomllib unavailable"]
    findings = []
    seen_ids = {}
    try:
        directories = sorted(path for path in root.iterdir() if path.is_dir())
    except OSError as exc:
        return [
            "Codex automation inventory UNKNOWN: root unreadable (%s)" %
            type(exc).__name__
        ]
    for directory in directories:
        if not WINDOWS_TASK_NAME_RE.search(directory.name):
            continue
        path = directory / "automation.toml"
        if not path.is_file():
            findings.append(
                "Codex automation inventory UNKNOWN: automation.toml missing: "
                + str(directory)
            )
            continue
        try:
            with path.open("rb") as handle:
                document = tomllib.load(handle)
        except (OSError, ValueError) as exc:
            findings.append(
                "Codex automation inventory UNKNOWN: unreadable TOML %s (%s)" %
                (path, type(exc).__name__)
            )
            continue
        if not isinstance(document, dict):
            findings.append("Codex automation inventory UNKNOWN: non-object TOML: " + str(path))
            continue
        task_id = document.get("id")
        if not isinstance(task_id, str) or not task_id.strip():
            findings.append("Codex automation inventory UNKNOWN: id missing: " + str(path))
            continue
        task_id = task_id.strip()
        if not WINDOWS_TASK_NAME_RE.search(task_id):
            continue
        if task_id != directory.name:
            findings.append("Codex automation id/path mismatch: " + str(path))
        if task_id in seen_ids:
            findings.append("duplicate Codex automation id: " + task_id)
        else:
            seen_ids[task_id] = path

        status = document.get("status")
        normalized_status = status.strip().upper() if isinstance(status, str) else ""
        if normalized_status not in {"ACTIVE", "PAUSED", "INACTIVE", "DISABLED"}:
            findings.append(
                "Codex automation inventory UNKNOWN: invalid status for %s" % task_id
            )
            continue
        notification = document.get("notification_policy")
        if notification is not None and notification not in {"never", "failed_runs_only"}:
            findings.append("external notification policy in Codex automation: " + task_id)
        if normalized_status != "ACTIVE":
            continue
        prompt = document.get("prompt")
        if not isinstance(prompt, str) or not prompt.strip():
            findings.append("Codex automation inventory UNKNOWN: active prompt missing: " + task_id)
            continue
        for field, value in _string_fields(document):
            leaf = field.rsplit(".", 1)[-1].casefold()
            execution_field = (
                leaf in {"prompt", "command", "action", "script", "instructions"}
                or any(token in leaf for token in ("webhook", "slack", "telegram", "notify"))
            )
            if not execution_field:
                continue
            for category, line in executable_automation_risks(value):
                findings.append(
                    "Codex automation %s risk %s in %s:%d" %
                    (task_id, category, field, line)
                )
    return findings


WINDOWS_TASK_QUERY = r"""
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new()
$rows = @(
  Get-ScheduledTask |
    ForEach-Object {
      [pscustomobject]@{
        TaskPath = $_.TaskPath
        TaskName = $_.TaskName
        State = [string]$_.State
        Actions = @($_.Actions | ForEach-Object {
          [pscustomobject]@{
            Execute = $_.Execute
            Arguments = $_.Arguments
            WorkingDirectory = $_.WorkingDirectory
          }
        })
      }
    }
)
[Console]::Write((ConvertTo-Json -InputObject $rows -Compress -Depth 6))
"""


WINDOWS_TASK_XML_COMMAND = ("schtasks.exe", "/Query", "/XML", "ONE")
WINDOWS_TASK_XML_NAMESPACE = "http://schemas.microsoft.com/windows/2004/02/mit/task"
WINDOWS_TASK_XML_MAX_BYTES = 16 * 1024 * 1024
WINDOWS_TASK_XML_MAX_TASKS = 4096
WINDOWS_TASK_XML_MAX_ACTIONS = 64
WINDOWS_TASK_XML_MAX_FIELD_CHARS = 32768


def _query_result_status(result, label):
    returncode = getattr(result, "returncode", None)
    if (not isinstance(returncode, int) or isinstance(returncode, bool)):
        return None, "%s result has invalid exit status" % label
    if returncode != 0:
        return None, "%s exit %d" % (label, returncode)
    stdout = getattr(result, "stdout", None)
    if not isinstance(stdout, (str, bytes)):
        return None, "%s result has invalid stdout" % label
    return stdout, None


def _single_xml_child(parent, tag, label, required=False):
    matches = parent.findall(tag)
    if len(matches) > 1:
        raise ValueError("duplicate " + label)
    if not matches:
        if required:
            raise ValueError("missing " + label)
        return None
    return matches[0]


def _xml_field(parent, tag, label, required=False, default=""):
    child = _single_xml_child(parent, tag, label, required=required)
    if child is None:
        return default
    if list(child):
        raise ValueError("nested content in " + label)
    value = child.text or ""
    if len(value) > WINDOWS_TASK_XML_MAX_FIELD_CHARS or "\x00" in value:
        raise ValueError("invalid " + label)
    if required and not value:
        raise ValueError("empty " + label)
    return value


def _task_identity_from_uri(uri):
    if (not isinstance(uri, str) or not uri.startswith("\\") or
            uri.endswith("\\") or uri.strip() != uri or "/" in uri):
        raise ValueError("invalid task URI")
    parts = uri[1:].split("\\")
    if (not parts or any(not part or part in {".", ".."} for part in parts) or
            any(any(ord(character) < 32 for character in part) for part in parts)):
        raise ValueError("invalid task URI")
    name = parts[-1]
    task_path = "\\" if len(parts) == 1 else "\\" + "\\".join(parts[:-1]) + "\\"
    return task_path, name


def _parse_schtasks_xml(stdout):
    """Parse the read-only ``schtasks /Query /XML ONE`` inventory strictly."""
    if isinstance(stdout, bytes):
        if len(stdout) > WINDOWS_TASK_XML_MAX_BYTES:
            raise ValueError("XML inventory exceeds size limit")
        if stdout.startswith((b"\xff\xfe", b"\xfe\xff")):
            text = stdout.decode("utf-16")
        else:
            text = stdout.decode("utf-8-sig")
    elif isinstance(stdout, str):
        if len(stdout.encode("utf-8")) > WINDOWS_TASK_XML_MAX_BYTES:
            raise ValueError("XML inventory exceeds size limit")
        text = stdout
    else:
        raise ValueError("XML inventory has invalid type")
    lowered = text.casefold()
    if "\x00" in text or "<!doctype" in lowered or "<!entity" in lowered:
        raise ValueError("unsafe XML declaration")
    try:
        root = ET.fromstring(text)
    except ET.ParseError as exc:
        raise ValueError("malformed XML inventory") from exc
    if root.tag != "Tasks":
        raise ValueError("unexpected XML root")
    task_nodes = list(root)
    task_tag = "{%s}Task" % WINDOWS_TASK_XML_NAMESPACE
    if len(task_nodes) > WINDOWS_TASK_XML_MAX_TASKS:
        raise ValueError("XML inventory exceeds task limit")
    if any(node.tag != task_tag for node in task_nodes):
        raise ValueError("unexpected XML task element")

    prefix = "{%s}" % WINDOWS_TASK_XML_NAMESPACE
    tasks = []
    identities = set()
    for task in task_nodes:
        registration = _single_xml_child(
            task, prefix + "RegistrationInfo", "RegistrationInfo", required=True
        )
        uri = _xml_field(
            registration, prefix + "URI", "RegistrationInfo/URI", required=True
        )
        task_path, task_name = _task_identity_from_uri(uri)
        identity = (task_path + task_name).casefold()
        if identity in identities:
            raise ValueError("duplicate task identity")
        identities.add(identity)

        settings = _single_xml_child(task, prefix + "Settings", "Settings", required=True)
        enabled = _xml_field(settings, prefix + "Enabled", "Settings/Enabled",
                             default="true").strip().casefold()
        if enabled not in {"true", "false"}:
            raise ValueError("invalid Settings/Enabled")

        actions_node = _single_xml_child(task, prefix + "Actions", "Actions", required=True)
        action_nodes = list(actions_node)
        if len(action_nodes) > WINDOWS_TASK_XML_MAX_ACTIONS:
            raise ValueError("XML inventory exceeds action limit")
        actions = []
        for action in action_nodes:
            if action.tag != prefix + "Exec":
                # Preserve an opaque action so the downstream project-task scan
                # reports UNKNOWN instead of silently treating it as harmless.
                actions.append({"Execute": "", "Arguments": "",
                                "WorkingDirectory": ""})
                continue
            actions.append({
                "Execute": _xml_field(
                    action, prefix + "Command", "Exec/Command", required=True
                ),
                "Arguments": _xml_field(
                    action, prefix + "Arguments", "Exec/Arguments", default=""
                ),
                "WorkingDirectory": _xml_field(
                    action, prefix + "WorkingDirectory", "Exec/WorkingDirectory",
                    default="",
                ),
            })
        tasks.append({
            "TaskPath": task_path,
            "TaskName": task_name,
            "State": "Ready" if enabled == "true" else "Disabled",
            "Actions": actions,
        })
    return tasks


def _query_windows_tasks_with_powershell(runner):
    try:
        result = runner(
            ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command",
             WINDOWS_TASK_QUERY],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=30, check=False,
        )
    except Exception as exc:
        return None, "PowerShell query failed (%s)" % type(exc).__name__
    stdout, error = _query_result_status(result, "PowerShell query")
    if error:
        return None, error
    if not isinstance(stdout, str):
        return None, "PowerShell query result has invalid text encoding"
    try:
        tasks = _strict_json_loads(stdout)
    except (TypeError, ValueError):
        return None, "PowerShell query returned invalid JSON"
    if isinstance(tasks, dict):
        tasks = [tasks]
    if not isinstance(tasks, list):
        return None, "PowerShell query returned non-list inventory"
    return tasks, None


def _query_windows_tasks_with_schtasks(runner):
    try:
        result = runner(
            list(WINDOWS_TASK_XML_COMMAND), capture_output=True, text=False,
            timeout=30, check=False,
        )
    except Exception as exc:
        return None, "schtasks XML fallback failed (%s)" % type(exc).__name__
    stdout, error = _query_result_status(result, "schtasks XML fallback")
    if error:
        return None, error
    try:
        return _parse_schtasks_xml(stdout), None
    except (UnicodeError, ValueError):
        return None, "schtasks XML fallback returned invalid inventory"


def query_windows_scheduled_tasks(runner=subprocess.run):
    """Read task actions without mutation, falling back when CIM is unavailable."""
    tasks, primary_error = _query_windows_tasks_with_powershell(runner)
    if primary_error is None:
        return {"status": "OK", "tasks": tasks}
    tasks, fallback_error = _query_windows_tasks_with_schtasks(runner)
    if fallback_error is None:
        return {"status": "OK", "tasks": tasks}
    return {
        "status": "UNKNOWN",
        "reason": "%s; %s" % (primary_error, fallback_error),
    }


SCRIPT_PATH_RE = re.compile(
    r'(?:"([^"\r\n]+\.(?:cmd|bat|ps1|py))"|([^\s"\r\n]+\.(?:cmd|bat|ps1|py)))',
    re.IGNORECASE,
)
INTERPRETER_NAMES = {
    "cmd", "cmd.exe", "powershell", "powershell.exe", "pwsh", "pwsh.exe",
    "python", "python.exe", "python3", "python3.exe", "py", "py.exe",
}


def _inside(path, root):
    try:
        Path(path).resolve().relative_to(Path(root).resolve())
        return True
    except (OSError, ValueError):
        return False


def _resolve_action_script(path, repo, working_directory=None):
    selected = Path(path)
    if not selected.is_absolute():
        base = (Path(working_directory) if isinstance(working_directory, str)
                and working_directory.strip() else Path(repo))
        selected = base / selected
    return selected.resolve(strict=False)


def _action_references_repo(action, repo):
    if not isinstance(action, dict):
        return False
    try:
        needle = str(Path(repo).resolve()).replace("/", "\\").casefold()
    except (OSError, ValueError):
        return False
    combined = " ".join(
        str(action.get(field) or "")
        for field in ("Execute", "Arguments", "WorkingDirectory")
    ).replace("/", "\\").casefold()
    return needle in combined


def _scan_local_action_script(path, task_id, repo, working_directory=None):
    selected = _resolve_action_script(path, repo, working_directory)
    if not _inside(selected, repo):
        return ["Windows task action target is outside repo: " + task_id]
    if not selected.is_file():
        return ["Windows task action UNKNOWN (script missing): " + task_id]
    try:
        text = selected.read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        return ["Windows task action UNKNOWN (script unreadable): " + task_id]
    suffix = selected.suffix.casefold()
    if suffix in {".cmd", ".bat"}:
        text = "\n".join(
            line for line in text.splitlines()
            if not line.lstrip().casefold().startswith(("rem ", "@rem ", "::"))
        )
    elif suffix == ".ps1":
        text = "\n".join(
            line for line in text.splitlines()
            if not line.lstrip().startswith("#")
        )
    return [
        "Windows task %s script risk %s at %s:%d" %
        (task_id, category, selected, line)
        for category, line in executable_automation_risks(text)
    ]


def scan_windows_scheduled_tasks(inventory=None, repo=ROOT):
    """Validate enabled actions from the bounded Windows task inventory."""
    current = inventory if inventory is not None else query_windows_scheduled_tasks()
    if not isinstance(current, dict) or current.get("status") != "OK":
        reason = current.get("reason") if isinstance(current, dict) else "invalid inventory"
        return ["Windows Scheduled Task inventory UNKNOWN: " + str(reason)]
    tasks = current.get("tasks")
    if not isinstance(tasks, list):
        return ["Windows Scheduled Task inventory UNKNOWN: tasks is not a list"]
    findings = []
    seen = set()
    script_owners = {}
    for task in tasks:
        if not isinstance(task, dict):
            findings.append("Windows Scheduled Task inventory UNKNOWN: malformed task row")
            continue
        name = task.get("TaskName")
        path = task.get("TaskPath")
        if not isinstance(name, str) or not name or not isinstance(path, str):
            findings.append("Windows Scheduled Task inventory UNKNOWN: task identity missing")
            continue
        actions = task.get("Actions")
        if isinstance(actions, dict):
            actions = [actions]
        name_matches = bool(WINDOWS_TASK_NAME_RE.search(name))
        references_repo = bool(
            isinstance(actions, list)
            and any(_action_references_repo(action, repo) for action in actions)
        )
        if not name_matches and not references_repo:
            continue
        task_id = path + name
        if task_id.casefold() in seen:
            findings.append("duplicate Windows Scheduled Task identity: " + task_id)
            continue
        seen.add(task_id.casefold())
        state = task.get("State")
        state = state.strip().casefold() if isinstance(state, str) else ""
        if state == "disabled":
            continue
        if state not in {"ready", "running", "queued"}:
            findings.append("Windows Scheduled Task state UNKNOWN: " + task_id)
            continue
        if references_repo and not name_matches:
            findings.append(
                "Windows project action uses unexpected task identity: " + task_id
            )
        if not isinstance(actions, list) or not actions:
            findings.append("Windows Scheduled Task action UNKNOWN: " + task_id)
            continue
        for action in actions:
            if not isinstance(action, dict):
                findings.append("Windows Scheduled Task action UNKNOWN: " + task_id)
                continue
            execute = action.get("Execute")
            arguments = action.get("Arguments") or ""
            working_directory = action.get("WorkingDirectory") or ""
            if not isinstance(execute, str) or not execute.strip() or not isinstance(arguments, str):
                findings.append("Windows Scheduled Task action UNKNOWN: " + task_id)
                continue
            command = (execute + " " + arguments).strip()
            for category, line in executable_automation_risks(command):
                findings.append("Windows task %s action risk %s" % (task_id, category))
            executable = Path(execute.strip().strip('"'))
            if executable.suffix.casefold() in {".cmd", ".bat", ".ps1", ".py"}:
                selected = _resolve_action_script(executable, repo, working_directory)
                if _inside(selected, repo):
                    script_owners.setdefault(_normalized_path(selected), set()).add(task_id)
                findings.extend(_scan_local_action_script(
                    executable, task_id, repo, working_directory
                ))
                continue
            if executable.name.casefold() in INTERPRETER_NAMES:
                matches = [left or right for left, right in SCRIPT_PATH_RE.findall(arguments)]
                if not matches:
                    findings.append("Windows task action UNKNOWN (opaque interpreter): " + task_id)
                    continue
                for script in matches:
                    selected = _resolve_action_script(script, repo, working_directory)
                    if _inside(selected, repo):
                        script_owners.setdefault(_normalized_path(selected), set()).add(task_id)
                    findings.extend(_scan_local_action_script(
                        script, task_id, repo, working_directory
                    ))
                continue
            findings.append("Windows task action UNKNOWN (opaque executable): " + task_id)
    for script, owners in sorted(script_owners.items()):
        if len(owners) > 1:
            findings.append(
                "duplicate enabled Windows task owners for project runner %s: %s" %
                (script, ", ".join(sorted(owners)))
            )
    return findings


def scan(prompt_roots=PROMPT_ROOTS, workflow_root=None,
         automation_root=CODEX_AUTOMATIONS_ROOT, windows_inventory=None,
         windows_repo=ROOT, scheduler_registry=None,
         claude_user_data_roots=None):
    findings = []
    registry_inventory = scheduler_registry
    if registry_inventory is None:
        registry_inventory = query_claude_scheduler_registries(
            prompt_roots, claude_user_data_roots
        )
    for base in prompt_roots:
        if not base.exists():
            findings.append("prompt root missing: " + str(base))
            continue
        for path in sorted(base.rglob("SKILL.md")):
            try:
                text = path.read_text(encoding="utf-8")
            except OSError as exc:
                findings.append("prompt unreadable: %s (%s)" % (path, exc))
                continue
            if prompt_is_tombstoned(text):
                continue
            for line in executable_git_lines(text):
                findings.append("remote git mutation in %s:%d" % (path, line))
            for line in executable_publisher_lines(text):
                findings.append("remote publisher/deploy mutation in %s:%d" % (path, line))
    findings.extend(shared_live_prompt_drift(
        prompt_roots, scheduler_registry=registry_inventory,
        user_data_roots=claude_user_data_roots,
    ))
    findings.extend(scan_enabled_claude_tasks(registry_inventory))
    findings.extend(knowledge_prompt_contract(prompt_roots))
    findings.extend(link_health_prompt_contract(prompt_roots))
    findings.extend(operational_prompt_contract(prompt_roots))
    findings.extend(first_signal_prompt_contract(prompt_roots))
    findings.extend(publisher_source_contract())
    findings.extend(scan_codex_automations(automation_root))
    findings.extend(scan_windows_scheduled_tasks(windows_inventory, repo=windows_repo))
    workflow_root = workflow_root or (ROOT / ".github" / "workflows")
    if not workflow_root.exists():
        findings.append("workflow root missing: " + str(workflow_root))
    else:
        for path in sorted(workflow_root.glob("*.y*ml")):
            try:
                text = path.read_text(encoding="utf-8")
            except OSError as exc:
                findings.append("workflow unreadable: %s (%s)" % (path, exc))
                continue
            if workflow_is_scheduled_mutator(text):
                findings.append("scheduled remote mutator in " + str(path))
    primary_root = prompt_roots[0] if prompt_roots else PROMPT_ROOTS[0]
    idle = primary_root / "threads-video-idle-window" / "SKILL.md"
    backfill = primary_root / "ngernduangold-fb-reel-backfill" / "SKILL.md"
    for path, marker in ((idle, "RETIRED — NO-OP"), (backfill, "RETIRED — NO-OP")):
        try:
            if marker not in path.read_text(encoding="utf-8"):
                findings.append("publication tombstone missing: " + str(path))
        except OSError:
            findings.append("publication prompt unreadable: " + str(path))
    return findings


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--registry-json", action="store_true",
        help="print the read-only Claude scheduler ownership export as JSON",
    )
    args = parser.parse_args(argv)
    if args.registry_json:
        export = scheduler_ownership_export()
        print(json.dumps(export, ensure_ascii=False, sort_keys=True))
        return 0 if export.get("status") == "OK" else 2
    findings = scan()
    if findings:
        for finding in findings:
            print("FAIL " + finding)
        return 2
    print(
        "PASS automation policy guard: Codex TOML, Windows task actions, "
        "prompt ownership and workflow mutation checks passed"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
