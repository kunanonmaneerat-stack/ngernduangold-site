#!/usr/bin/env python3
"""Regression checks for live-prompt and scheduled-workflow remote mutations."""
import pathlib
import tempfile

import automation_policy_guard as guard


def check(label, condition):
    if not condition:
        raise AssertionError(label)
    print("PASS", label)


def main():
    strict_rejected = 0
    for raw in ('{"enabled":false,"enabled":true}', '{"unused":NaN}',
                '{"unused":1e999}'):
        try:
            guard._strict_json_loads(raw)
        except ValueError:
            strict_rejected += 1
    check("scheduler evidence JSON is duplicate/non-finite strict", strict_rejected == 3)
    check("executable push is detected", guard.executable_git_lines("run `git push` now") == [1])
    check("explicit prohibition is not treated as a command", guard.executable_git_lines("ห้าม git push") == [])
    check("live uploader is detected", guard.executable_publisher_lines(
        "py tools/yt_upload_batch2.py --live --dates 2026-08-16") == [1])
    check("browser comment mutation is detected", guard.executable_publisher_lines(
        "ใช้ claude-in-chrome แล้วคลิกปุ่มส่ง comment") == [1])
    check("spaced Claude in Chrome comment mutation is detected", guard.executable_publisher_lines(
        "ใช้ Claude in Chrome แล้วคลิกปุ่มส่ง comment") == [1])
    check("deploy command is detected", guard.executable_publisher_lines(
        "run netlify deploy --prod") == [1])
    check("publisher prohibition is allowed", guard.executable_publisher_lines(
        "ห้ามเรียก yt_upload_batch2.py --live") == [])
    check("long policy explanation is not a browser command", guard.executable_publisher_lines(
        "อำนาจเผยแพร่ต้องอ่าน policy และ role matrix ให้ครบ; ถ้าไม่ผ่านให้ BLOCKED และห้ามเรียก uploader/browser publisher") == [])
    check("formatted Thai prohibition list is not executable git", guard.executable_git_lines(
        "**6 · ห้าม** โพสต์เอง · แก้ไฟล์ · git push") == [])
    check("commit plus push without a git prefix is detected", guard.executable_git_lines(
        "แล้ว commit automation-log + push") == [1])
    check("negation in another clause cannot hide uploader", guard.executable_publisher_lines(
        "Do not stop; run tools/yt_upload_batch2.py --live") == [1])
    check("explicit YouTube repair mutation is detected", guard.executable_publisher_lines(
        "python tools/post_guard.py --repair-youtube --date 2026-08-16") == [1])
    check("multi-line browser publish is detected", guard.executable_publisher_lines(
        "Open browser\nClick Publish") == [2])
    check("Thai imperative repost is detected", guard.executable_publisher_lines(
        "- FAILED — ซ่อมแล้วโพสต์ซ้ำวันนี้\n- NOT-POSTED — โพสต์ให้เรียบร้อย") == [1, 2])
    check("Thai publication prohibition remains safe", guard.executable_publisher_lines(
        "ห้ามโพสต์ซ้ำวันนี้ และห้ามเผยแพร่ให้เรียบร้อยแทนเจ้าของ") == [])
    check("Thai prohibition cannot hide a later positive clause",
          guard.executable_publisher_lines(
              "ห้ามโพสต์ชิ้นเก่า, แต่ให้โพสต์ชิ้นใหม่ทันที") == [1])
    check("explicit early tombstone marks legacy body non-executable", guard.prompt_is_tombstoned(
        "---\nname: old\n---\n## RETIRED — NO-OP\nlegacy yt_upload_batch2.py --live"))
    check("description alone is not a tombstone", not guard.prompt_is_tombstoned(
        "---\ndescription: [PAUSED]\n---\nlegacy yt_upload_batch2.py --live"))
    check("explicit collision tombstone is recognised", guard.prompt_is_resolved_tombstone(
        "---\nname: moved\n---\n# ป้ายหลุมศพ — อย่ารันอะไรจากไฟล์นี้\nหยุด"))
    check("explicit non-executable mirror is recognised", guard.prompt_is_resolved_tombstone(
        "---\nname: mirror\n---\nNON_EXECUTABLE_MIRROR\nread-only archive"))
    check("same-date/provider attribution shortcut is detected",
          guard.first_signal_attribution_risks(
              "ใช้ same-date+provider attribution จับคู่ conversion"
          ) == [("same_date_provider", 1)])
    check("unrelated Thai negation cannot hide same-date attribution",
          guard.first_signal_attribution_risks(
              "ห้ามรอ ใช้ same-date+provider attribution จับคู่ conversion"
          ) == [("same_date_provider", 1)])
    check("double-down without paid deterministic evidence is detected",
          guard.first_signal_attribution_risks(
              "พบ conversion แล้ว double-down หน้านี้ทันที"
          ) == [("scale_without_paid_deterministic", 1)])
    check("pending conversion cannot be called revenue",
          guard.first_signal_attribution_risks(
              "pending conversion นี้คือรายได้แรก"
          ) == [("pending_as_revenue", 1)])
    check("raw AccessTrade clicks cannot be treated as demand",
          guard.first_signal_attribution_risks(
              "ใช้ raw AccessTrade clicks เป็น demand เพื่อเลือกหน้า"
          ) == [("raw_clicks_as_demand", 1)])
    check("paid deterministic scale and explicit prohibitions are safe",
          guard.first_signal_attribution_risks(
              "ห้ามใช้ same-date+provider attribution\n"
              "`pending` ไม่ใช่รายได้\n"
              "`raw AccessTrade clicks = contaminated` — ห้ามใช้เป็น demand\n"
              "winner/scale ได้เฉพาะ paid + deterministic evidence"
          ) == [])
    risk_cases = {
        "external_notify": "send message to Slack now",
        "external_storage_write": "upload the report to Google Drive with create_file",
        "package_install": "python -m pip install requests",
        "scheduler_mutation": "update_scheduled_task(taskId, enabled:true)",
        "browser_control": "open browser and inspect the page",
        "upload_or_live_publish": "upload video now",
        "remote_git": "git push origin main",
        "deploy": "vercel deploy --prod",
    }
    for category, text in risk_cases.items():
        check("automation risk detects " + category,
              category in {item[0] for item in guard.executable_automation_risks(text)})
    check("prohibited automation mutations remain non-executable",
          guard.executable_automation_risks(
              "ห้ามเปิด browser; ห้าม run git push; ห้าม run npm install; ห้าม deploy"
          ) == [])
    check("Telegram-on-fail flag is an external notification",
          guard.executable_automation_risks(
              "py tools/postdeploy_click_test.py --telegram-on-fail"
          ) == [("external_notify", 1)])
    check("Thai Slack posting is an external notification",
          ("external_notify", 1) in guard.executable_automation_risks(
              "โพสต์สรุปเข้า Slack ห้อง slack.ops"
          ))
    check("scheduled publisher workflow is detected", guard.workflow_is_scheduled_mutator(
        "on:\n  schedule:\n    - cron: x\npermissions:\n  contents: write\nsteps:\n - run: git push\n"))
    check("manual disabled tombstone is allowed", not guard.workflow_is_scheduled_mutator(
        "on: workflow_dispatch\npermissions:\n  contents: read\njobs:\n  retired:\n    if: false\n"))
    query_folded = guard.WINDOWS_TASK_QUERY.casefold()
    check("Windows inventory command is query-only",
          "get-scheduledtask" in query_folded and not any(
              token in query_folded for token in (
                  "set-scheduledtask", "register-scheduledtask",
                  "unregister-scheduledtask", "start-scheduledtask",
                  "enable-scheduledtask", "disable-scheduledtask",
              )
          ))
    with tempfile.TemporaryDirectory() as raw:
        base = pathlib.Path(raw)
        missing = base / "missing"
        findings = guard.scan(
            prompt_roots=(missing,), workflow_root=missing,
            automation_root=missing,
            windows_inventory={"status": "UNKNOWN", "reason": "test query failure"},
            windows_repo=base,
        )
        check("unreadable automation inventory fails closed", len(findings) >= 2)
        left, right = base / "left", base / "right"
        for root in (left, right):
            knowledge = root / "ngernduangold-knowledge-post-noon"
            knowledge.mkdir(parents=True)
            mirror = "NON_EXECUTABLE_MIRROR\n" if root == right else ""
            knowledge.joinpath("SKILL.md").write_text(
                "---\nname: knowledge\n---\n" + mirror + "Asia/Bangkok ห้าม fallback\n"
                "py tools/validate_knowledge_posts.py <path> --content-id <content_id>\n"
                "py pipeline/official_news_monitor.py\n", encoding="utf-8")
        shared_left = left / "shared-live"
        shared_right = right / "shared-live"
        shared_left.mkdir()
        shared_right.mkdir()
        shared_left.joinpath("SKILL.md").write_text("---\nname: x\n---\nread only\n", encoding="utf-8")
        shared_right.joinpath("SKILL.md").write_text("---\nname: x\n---\nwrite remote\n", encoding="utf-8")

        def registry(states):
            sources = []
            for name, root, side in (("cowork", left, 0), ("ccd", right, 1)):
                records = []
                for task_id, pair in states.items():
                    state = pair[side]
                    if state == "mirror":
                        continue
                    records.append({
                        "id": task_id,
                        "enabled": state == "live",
                        "file_path": str(root / task_id / "SKILL.md"),
                    })
                sources.append({"name": name, "task_root": str(root),
                                "registry_path": str(base / (name + ".json")),
                                "sha256": "fixture", "size": 0, "mtime_ns": 1,
                                "records": records})
            return {"schema_version": 1, "status": "OK", "sources": sources}

        base_states = {"ngernduangold-knowledge-post-noon": ("live", "mirror")}

        def findings(pair, extra=None):
            states = dict(base_states)
            states["shared-live"] = pair
            if extra:
                states.update(extra)
            return guard.shared_live_prompt_drift(
                (left, right), scheduler_registry=registry(states))

        check("both live scheduler records fail", len(findings(("live", "live"))) == 1)
        check("exactly one live owner plus registry-absent mirror passes",
              findings(("live", "mirror")) == [])
        check("different prompt bytes do not override registry ownership",
              findings(("mirror", "live")) == [])
        check("both unregistered mirrors fail", len(findings(("mirror", "mirror"))) == 1)
        check("both disabled registry records are retired and pass",
              findings(("retired", "retired")) == [])
        check("disabled owner plus absent mirror is globally retired",
              findings(("mirror", "retired")) == [])
        shared_right.joinpath("SKILL.md").write_text(
            "---\nname: x\n---\nNON_EXECUTABLE_MIRROR\n", encoding="utf-8")
        check("prompt self-claimed mirror cannot hide two live registries",
              len(findings(("live", "live"))) == 1)
        shared_right.joinpath("SKILL.md").write_text(
            "---\nname: x\n---\n## RETIRED — NO-OP\n", encoding="utf-8")
        check("enabled registry pointing at explicit retirement fails",
              len(findings(("mirror", "live"))) == 1)
        shared_left.joinpath("SKILL.md").write_text(
            "---\nname: x\n---\n## RETIRED — NO-OP\n", encoding="utf-8")
        check("both explicit retirements pass without registry records",
              findings(("mirror", "mirror")) == [])
        shared_left.joinpath("SKILL.md").write_text(
            "---\nname: x\n---\nread only\n", encoding="utf-8")
        shared_right.joinpath("SKILL.md").write_text(
            "---\nname: x\n---\nwrite remote\n", encoding="utf-8")
        unknown = guard.shared_live_prompt_drift(
            (left, right), scheduler_registry={"status": "UNKNOWN", "reason": "locked"})
        check("unreadable registry fails closed", len(unknown) == 1 and "UNKNOWN" in unknown[0])
        duplicate_inventory = registry({**base_states, "shared-live": ("live", "mirror")})
        duplicate_inventory["sources"][0]["records"].append(
            dict(duplicate_inventory["sources"][0]["records"][-1]))
        check("duplicate registry records fail closed", "duplicate id" in
              guard.shared_live_prompt_drift(
                  (left, right), scheduler_registry=duplicate_inventory)[0])
        mismatch_inventory = registry({**base_states, "shared-live": ("live", "mirror")})
        mismatch_inventory["sources"][0]["records"][-1]["file_path"] = str(base / "escape.md")
        check("registry filePath outside the bound root fails closed", "filePath mismatch" in
              guard.shared_live_prompt_drift(
                  (left, right), scheduler_registry=mismatch_inventory)[0])
        export = guard.scheduler_ownership_export(
            (left, right), scheduler_registry=registry(
                {**base_states, "shared-live": ("mirror", "live")}))
        exported = next(item for item in export["ownership"]
                        if item["task_id"] == "shared-live")
        check("machine-readable export identifies one live CCD owner",
              exported["verdict"] == "PASS" and
              [item["state"] for item in exported["roots"]] == ["mirror", "live"])

        role_path = base / "roles.json"
        role_path.write_text(__import__("json").dumps({
            "default": "deny",
            "actors": {
                "cowork": {
                    "external_notify": False,
                    "external_storage_write": False,
                    "package_install": False,
                    "scheduler_mutation": False,
                    "git_push": False,
                    "social_publish": False,
                    "deploy": False,
                },
                "claude_code": {
                    "external_notify": False,
                    "external_storage_write": False,
                    "package_install": False,
                    "scheduler_mutation": False,
                    "git_push": False,
                    "social_publish": False,
                    "deploy": False,
                },
            },
        }), encoding="utf-8")
        risky_task = left / "ngernduangold-risky-live"
        risky_task.mkdir()
        risky_task.joinpath("SKILL.md").write_text(
            "เงินเดือนสมองทอง\nsend message to Slack\n"
            "python -m pip install requests\n"
            "update_scheduled_task(taskId, enabled:true)\n"
            "upload to Google Drive with create_file\n",
            encoding="utf-8",
        )
        risky_inventory = registry({
            **base_states,
            "shared-live": ("mirror", "live"),
            "ngernduangold-risky-live": ("live", "mirror"),
        })
        enabled_findings = guard.scan_enabled_claude_tasks(
            risky_inventory, role_path=role_path
        )
        check("enabled Claude prompt external effects are capability-gated",
              any("external_notify" in item for item in enabled_findings) and
              any("external_storage_write" in item for item in enabled_findings) and
              any("package_install" in item for item in enabled_findings) and
              any("scheduler_mutation" in item for item in enabled_findings))
        retired_task = right / "ngernduangold-retired-live"
        retired_task.mkdir()
        retired_task.joinpath("SKILL.md").write_text(
            "เงินเดือนสมองทอง\n## RETIRED — NO-OP\n", encoding="utf-8"
        )
        retired_inventory = registry({
            **base_states,
            "shared-live": ("mirror", "live"),
            "ngernduangold-retired-live": ("mirror", "live"),
        })
        check("enabled registry pointing at a project tombstone is reported",
              any("retired no-op" in item for item in
                  guard.scan_enabled_claude_tasks(
                      retired_inventory, role_path=role_path)))

        user_data = base / "user-data"
        for storage, root, state in (
                ("local-agent-mode-sessions", left, False),
                ("claude-code-sessions", right, True)):
            target = user_data / storage / "account" / "org" / "scheduled-tasks.json"
            target.parent.mkdir(parents=True)
            target.write_text(
                __import__("json").dumps({"scheduledTasks": [{
                    "id": "shared-live", "enabled": state,
                    "filePath": str(root / "shared-live" / "SKILL.md"),
                }]}), encoding="utf-8")
        discovered = guard.query_claude_scheduler_registries(
            (left, right), user_data_roots=(user_data,))
        check("bounded registry discovery loads both manager JSON files",
              discovered["status"] == "OK" and len(discovered["sources"]) == 2)
        check("registry discovery exports stable hashes",
              all(len(source["sha256"]) == 64 for source in discovered["sources"]))
        check("missing registry candidate fails closed",
              guard.query_claude_scheduler_registries(
                  (left, right), user_data_roots=(base / "no-registry",)
              )["status"] == "UNKNOWN")
        good_contract = guard.knowledge_prompt_contract((left, right))
        check("knowledge prompt requires item-scoped validation", good_contract == [])
        left.joinpath("ngernduangold-knowledge-post-noon", "SKILL.md").write_text(
            "---\nname: knowledge\n---\n"
            "py tools/validate_knowledge_posts.py <path>\n"
            "py pipeline/official_news_monitor.py --strict\n", encoding="utf-8")
        bad_contract = guard.knowledge_prompt_contract((left, right))
        check("knowledge prompt rejects missing content id and global strict gate",
              len(bad_contract) == 3)

        operational = {
            "ngernduangold-channel-heartbeat": (
                "--routine ngernduangold-channel-heartbeat --status started\n"
                "post-ledger.jsonl` สงวนไว้สำหรับ content/attempt evidence เท่านั้น\n"
                "ก่อน return/ข้าม/หยุดทุก branch\n"
            ),
            "ngernduangold-video-post-verify": (
                "--routine ngernduangold-video-post-verify --status ok\n"
                "ห้าม append/แก้ `automation-log/latest.md` โดยตรง\n"
                "task result เท่านั้น\n"
            ),
            "ngernduangold-weekly-review": (
                "WINDOWS ARTIFACT CONSUMER\nrun_weekly end exit=0\n"
                "policy.json → products.items\nห้ามเรียก `run_weekly.cmd`\n"
            ),
        }
        for task_id, prompt in operational.items():
            target = left / task_id
            target.mkdir(exist_ok=True)
            target.joinpath("SKILL.md").write_text(prompt, encoding="utf-8")
        check("operational proof and weekly ownership contract passes",
              guard.operational_prompt_contract((left, right)) == [])
        left.joinpath("ngernduangold-channel-heartbeat", "SKILL.md").write_text(
            "ให้ append 1 แถวลง `automation-log/post-ledger.jsonl`", encoding="utf-8")
        left.joinpath("ngernduangold-video-post-verify", "SKILL.md").write_text(
            "เขียนบรรทัดสั้นๆ ต่อท้าย `automation-log/latest.md`", encoding="utf-8")
        left.joinpath("ngernduangold-weekly-review", "SKILL.md").write_text(
            "run `pipeline/run_weekly.cmd` now", encoding="utf-8")
        broken_operational = guard.operational_prompt_contract((left, right))
        check("operational proof and duplicate weekly regressions fail closed",
              len(broken_operational) >= 6)

        first_signal_good = (
            "report-only\n"
            "`AccessTrade conversion ID`\n"
            "actual `Sub ID` หรือ `click ID`\n"
            "`timestamp/session join`\n"
            "merchant-level `UNATTRIBUTED`\n"
            "`pending` ไม่ใช่รายได้\n"
            "`raw AccessTrade clicks = contaminated` และห้ามใช้เป็น demand\n"
            "`paid + deterministic` evidence เท่านั้น\n"
            "ห้ามใช้ same-date+provider attribution\n"
            "ห้ามประกาศ winner/scale/double-down\n"
            "ห้าม Run now/แก้ scheduled task\n"
        )
        for root in (left, right):
            target = root / "ngernduangold-first-signal"
            target.mkdir(exist_ok=True)
            target.joinpath("SKILL.md").write_text(
                first_signal_good, encoding="utf-8"
            )
        check("first-signal paid deterministic contract passes",
              guard.first_signal_prompt_contract((left, right)) == [])
        right.joinpath(
            "ngernduangold-first-signal", "SKILL.md"
        ).write_text(first_signal_good + "mirror drift\n", encoding="utf-8")
        check("first-signal active mirror byte drift fails",
              any("prompt bytes diverge" in item for item in
                  guard.first_signal_prompt_contract((left, right))))
        right.joinpath(
            "ngernduangold-first-signal", "SKILL.md"
        ).write_text(first_signal_good, encoding="utf-8")
        left.joinpath(
            "ngernduangold-first-signal", "SKILL.md"
        ).write_text(
            first_signal_good +
            "ใช้ same-date+provider attribution จับคู่ conversion\n"
            "เจอ conversion แล้ว double-down ทันที\n",
            encoding="utf-8",
        )
        broken_first_signal = guard.first_signal_prompt_contract((left, right))
        check("first-signal shortcut and unbound scale fail closed",
              any("same_date_provider" in item for item in broken_first_signal)
              and any("scale_without_paid_deterministic" in item
                      for item in broken_first_signal))

        codex_root = base / "codex-automations"

        def write_automation(task_id, prompt, status="ACTIVE",
                             notification="failed_runs_only"):
            target = codex_root / task_id
            target.mkdir(parents=True, exist_ok=True)
            escaped = prompt.replace("\\", "\\\\").replace('"', '\\"')
            target.joinpath("automation.toml").write_text(
                "version = 1\n"
                f'id = "{task_id}"\n'
                'kind = "heartbeat"\n'
                f'name = "{task_id}"\n'
                f'prompt = "{escaped}"\n'
                f'status = "{status}"\n'
                'rrule = "FREQ=DAILY;BYHOUR=10;BYMINUTE=5"\n'
                f'notification_policy = "{notification}"\n',
                encoding="utf-8",
            )

        write_automation(
            "ngernduangold-weekly-control-tower",
            "inspect local evidence; no external action",
        )
        check("current-shape Codex control tower passes",
              guard.scan_codex_automations(codex_root) == [])
        for index, (category, prompt) in enumerate(risk_cases.items(), 1):
            write_automation("ngernduangold-risk-%02d" % index, prompt)
        codex_findings = guard.scan_codex_automations(codex_root)
        for category in risk_cases:
            check("Codex TOML catches " + category,
                  any(("risk " + category) in item for item in codex_findings))
        write_automation(
            "ngernduangold-disabled-tiktok", "upload video with browser",
            status="DISABLED",
        )
        check("disabled Codex automation body is non-executable",
              not any("ngernduangold-disabled-tiktok" in item
                      for item in guard.scan_codex_automations(codex_root)))
        write_automation(
            "ngernduangold-external-notify", "local report only",
            notification="always",
        )
        check("external Codex notification policy fails",
              any("external notification policy" in item
                  for item in guard.scan_codex_automations(codex_root)))
        write_automation(
            "ngernduangold-self-edit",
            "วันที่ 18 ให้ลบเงื่อนไขออกจาก automation id นี้และคืนตารางทำงานเป็นวันละครั้ง",
        )
        self_edit_findings = guard.scan_codex_automations(codex_root)
        check("natural-language Codex self-scheduling mutation fails",
              any("ngernduangold-self-edit risk scheduler_mutation" in item
                  for item in self_edit_findings))
        write_automation(
            "ngernduangold-read-only-schedule",
            "ห้ามแก้ automation หรือตารางทำงาน; รายงานสถานะอย่างเดียว",
        )
        prohibited_schedule_findings = guard.scan_codex_automations(codex_root)
        check("explicit scheduler-mutation prohibition remains safe",
              not any("ngernduangold-read-only-schedule risk scheduler_mutation" in item
                      for item in prohibited_schedule_findings))

        task_repo = base / "task-repo"
        pipeline = task_repo / "pipeline"
        pipeline.mkdir(parents=True)
        daily = pipeline / "run_daily.cmd"
        weekly = pipeline / "run_weekly.cmd"
        daily.write_text("@echo off\necho local daily\n", encoding="utf-8")
        weekly.write_text("@echo off\necho local weekly\n", encoding="utf-8")
        check("queue-only receipt contract is not classified as publication",
              guard.executable_automation_risks(
                  'set "STEP_CONTRACT=queue-agent-v1"'
              ) == [])
        safe_windows = {
            "status": "OK",
            "tasks": [
                {"TaskPath": "\\", "TaskName": "ngernduangold_daily",
                 "State": "Ready", "Actions": [{"Execute": str(daily),
                                                    "Arguments": "",
                                                    "WorkingDirectory": ""}]},
                {"TaskPath": "\\", "TaskName": "ngernduangold_weekly",
                 "State": "Ready", "Actions": [{"Execute": str(weekly),
                                                    "Arguments": "",
                                                    "WorkingDirectory": str(task_repo)}]},
                {"TaskPath": "\\", "TaskName": "ngern-tiktok-daily",
                 "State": "Disabled", "Actions": [{"Execute": "chrome.exe",
                                                       "Arguments": "upload video",
                                                       "WorkingDirectory": ""}]},
            ],
        }
        check("daily weekly and disabled TikTok Windows tasks pass",
              guard.scan_windows_scheduled_tasks(safe_windows, repo=task_repo) == [])
        hidden_owner = {
            "status": "OK",
            "tasks": [{
                "TaskPath": "\\\\", "TaskName": "quiet-helper", "State": "Ready",
                "Actions": [{"Execute": str(daily), "Arguments": "",
                             "WorkingDirectory": ""}],
            }],
        }
        check("unexpected Windows task identity cannot hide a project runner",
              any("unexpected task identity" in item for item in
                  guard.scan_windows_scheduled_tasks(hidden_owner, repo=task_repo)))
        duplicate_runner = {
            "status": "OK",
            "tasks": [
                {"TaskPath": "\\\\", "TaskName": "ngernduangold-copy-a",
                 "State": "Ready", "Actions": [{"Execute": str(daily),
                                                   "Arguments": "",
                                                   "WorkingDirectory": ""}]},
                {"TaskPath": "\\\\", "TaskName": "ngernduangold-copy-b",
                 "State": "Ready", "Actions": [{"Execute": str(daily),
                                                   "Arguments": "",
                                                   "WorkingDirectory": ""}]},
            ],
        }
        check("duplicate enabled Windows owners of one runner fail",
              any("duplicate enabled Windows task owners" in item for item in
                  guard.scan_windows_scheduled_tasks(duplicate_runner, repo=task_repo)))
        risky_windows = {"status": "OK", "tasks": []}
        for index, (category, command) in enumerate(risk_cases.items(), 1):
            risky_windows["tasks"].append({
                "TaskPath": "\\", "TaskName": "ngernduangold-risk-%02d" % index,
                "State": "Ready",
                "Actions": [{"Execute": "cmd.exe", "Arguments": "/c " + command,
                             "WorkingDirectory": ""}],
            })
        windows_findings = guard.scan_windows_scheduled_tasks(
            risky_windows, repo=task_repo
        )
        for category in risk_cases:
            check("Windows action catches " + category,
                  any(("risk " + category) in item for item in windows_findings))
        check("Windows task query UNKNOWN fails closed",
              len(guard.scan_windows_scheduled_tasks(
                  {"status": "UNKNOWN", "reason": "access denied"}, repo=task_repo
              )) == 1)

        class QueryResult:
            def __init__(self, returncode=0, stdout="[]"):
                self.returncode = returncode
                self.stdout = stdout
                self.stderr = ""

        check("Windows query nonzero becomes UNKNOWN",
              guard.query_windows_scheduled_tasks(
                  runner=lambda *args, **kwargs: QueryResult(5, "")
              )["status"] == "UNKNOWN")
        check("Windows query invalid JSON becomes UNKNOWN",
              guard.query_windows_scheduled_tasks(
                  runner=lambda *args, **kwargs: QueryResult(0, "not-json")
              )["status"] == "UNKNOWN")
        check("Windows query valid JSON is normalized",
              guard.query_windows_scheduled_tasks(
                  runner=lambda *args, **kwargs: QueryResult(0, "[]")
              ) == {"status": "OK", "tasks": []})

        fallback_xml = ("""
<Tasks>
  <Task version="1.3" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">
    <RegistrationInfo><URI>\\Ops\\ngernduangold_daily</URI></RegistrationInfo>
    <Settings><Enabled>true</Enabled></Settings>
    <Actions><Exec>
      <Command>C:\\safe\\run_daily.cmd</Command>
      <Arguments>--local-only</Arguments>
      <WorkingDirectory>C:\\safe</WorkingDirectory>
    </Exec></Actions>
  </Task>
  <Task version="1.3" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">
    <RegistrationInfo><URI>\\ngernduangold-daily-queue</URI></RegistrationInfo>
    <Settings><Enabled>false</Enabled></Settings>
    <Actions><Exec><Command>C:\\safe\\legacy.cmd</Command></Exec></Actions>
  </Task>
</Tasks>
""").encode("utf-8")

        class SequenceRunner:
            def __init__(self, *results):
                self.results = list(results)
                self.calls = []

            def __call__(self, command, **kwargs):
                self.calls.append((command, kwargs))
                if not self.results:
                    raise AssertionError("unexpected query call")
                return self.results.pop(0)

        fallback_runner = SequenceRunner(
            QueryResult(5, ""), QueryResult(0, fallback_xml)
        )
        fallback_inventory = guard.query_windows_scheduled_tasks(
            runner=fallback_runner
        )
        check("schtasks XML fallback is used after CIM query failure",
              fallback_inventory["status"] == "OK"
              and fallback_runner.calls[1][0] == list(guard.WINDOWS_TASK_XML_COMMAND))
        check("schtasks XML fallback normalizes identity action and enabled state",
              fallback_inventory["tasks"] == [
                  {"TaskPath": "\\Ops\\", "TaskName": "ngernduangold_daily",
                   "State": "Ready", "Actions": [{
                       "Execute": "C:\\safe\\run_daily.cmd",
                       "Arguments": "--local-only",
                       "WorkingDirectory": "C:\\safe",
                   }]},
                  {"TaskPath": "\\", "TaskName": "ngernduangold-daily-queue",
                   "State": "Disabled", "Actions": [{
                       "Execute": "C:\\safe\\legacy.cmd",
                       "Arguments": "", "WorkingDirectory": "",
                   }]},
              ])
        no_enabled_xml = fallback_xml.replace(
            b"<Enabled>true</Enabled>", b""
        )
        default_enabled = guard._parse_schtasks_xml(no_enabled_xml)
        check("missing XML Enabled uses the Windows schema default true",
              default_enabled[0]["State"] == "Ready")
        unsafe_xml = (b'<!DOCTYPE Tasks [<!ENTITY x "unsafe">]>'
                      b'<Tasks></Tasks>')
        unsafe_runner = SequenceRunner(
            QueryResult(5, ""), QueryResult(0, unsafe_xml)
        )
        check("schtasks XML DTD and entity declarations fail closed",
              guard.query_windows_scheduled_tasks(
                  runner=unsafe_runner
              )["status"] == "UNKNOWN")
        duplicate_xml = fallback_xml.replace(
            b"\\ngernduangold-daily-queue", b"\\Ops\\ngernduangold_daily"
        )
        duplicate_runner = SequenceRunner(
            QueryResult(5, ""), QueryResult(0, duplicate_xml)
        )
        check("schtasks XML duplicate task identity fails closed",
              guard.query_windows_scheduled_tasks(
                  runner=duplicate_runner
              )["status"] == "UNKNOWN")
        invalid_enabled_xml = fallback_xml.replace(
            b"<Enabled>true</Enabled>", b"<Enabled>maybe</Enabled>"
        )
        invalid_enabled_runner = SequenceRunner(
            QueryResult(5, ""), QueryResult(0, invalid_enabled_xml)
        )
        check("schtasks XML ambiguous enabled state fails closed",
              guard.query_windows_scheduled_tasks(
                  runner=invalid_enabled_runner
              )["status"] == "UNKNOWN")
        opaque_action_xml = fallback_xml.replace(
            b"<Exec>\n      <Command>C:\\safe\\run_daily.cmd</Command>\n"
            b"      <Arguments>--local-only</Arguments>\n"
            b"      <WorkingDirectory>C:\\safe</WorkingDirectory>\n    </Exec>",
            b"<ComHandler><ClassId>{00000000-0000-0000-0000-000000000000}"
            b"</ClassId></ComHandler>",
        )
        opaque_inventory = guard._parse_schtasks_xml(opaque_action_xml)
        check("non-Exec XML action remains opaque for downstream fail-closed scan",
              opaque_inventory[0]["Actions"] == [{
                  "Execute": "", "Arguments": "", "WorkingDirectory": "",
              }])
        source_root = base / "source"
        for relative, markers in {
            pathlib.Path("automation/ig_publish.py"): (
                "authorize_live_publication", "PUBLICATION_ACTOR",
                "target_identity=IG_USER", "approval=entry.get",
                "content_source_evidence=", "media_qa_path=",
                "verify_execution_authorization"),
            pathlib.Path("social-autopost/publish_fb.py"): (
                "authorize_live_publication", "PUBLICATION_ACTOR",
                "target_identity=PAGE_ID", "approval=entry.get",
                "content_source_evidence=", "media_qa_path=",
                "verify_execution_authorization"),
            pathlib.Path("social-autopost/publish_tiktok.py"): (
                "authorize_live_publication", 'add_argument("--actor"',
                'add_argument("--target-account"', "target_identity=target_account",
                "approval=entry.get", "content_source_evidence=", "media_qa_path=",
                "verify_execution_authorization"),
            pathlib.Path("tools/yt_upload_batch2.py"): (
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
                "_assert_reconciliation_clear", "_begin_attempt", "_finish_attempt",
                "PENDING_REMOTE", "reconciliation-only"),
            pathlib.Path("tools/publication_authority.py"): (
                "publication_authorized", "social_publish", "target_identity", "REQUIRED_VALIDATIONS",
                "RECEIPT_FIELDS", "_load_private_receipt", "_consume_private_receipt",
                "RECEIPT_SCHEMA_VERSION = 2", "EVIDENCE_HASH_FIELDS",
                "content_source_sha256", "_media_qa_evidence", "_enforce_slot_window",
                "verify_execution_authorization",
                "content_calendar.json", "Asia/Bangkok",
                '"youtube": ("channel_id",)',
                "source_checked_at", "tools/privacy_guard.py", "tools/public_identity_guard.py"),
            pathlib.Path("tools/action_authority.py"): (
                "require_actor_capabilities", 'value.get("default") != "deny"',
                "capabilities.get(action) is not True"),
            pathlib.Path("pipeline/official_news_monitor.py"): (
                "programmatic source acknowledgement is disabled", "confined_cli_path",
                "owner-controlled process", 'parser.add_argument("--actor"'),
            pathlib.Path("pipeline/push_agent.py"): (
                "permanently local-only", "if do_commit or do_push",
                "human owner must perform Git", "no files staged, committed, pushed, or deployed"),
        }.items():
            path = source_root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            content = "\n".join(markers)
            if relative == pathlib.Path("automation/ig_publish.py"):
                content += (
                    "\ndef main():\nauthorize_live_publication(\n"
                    "urllib.request.Request(video_url\nverify_execution_authorization(\n"
                    'result = api("/%s/media"'
                )
            elif relative == pathlib.Path("social-autopost/publish_fb.py"):
                content += (
                    "\ndef main():\nauthorize_live_publication(\n"
                    "verify_execution_authorization(\n"
                    'result = api("/%s/feed"'
                )
            elif relative == pathlib.Path("social-autopost/publish_tiktok.py"):
                content += (
                    "\ndef mode_post():\nauthorize_live_publication(\nctx = launch(\n"
                    "verify_execution_authorization(\npage.set_input_files("
                )
            elif relative == pathlib.Path("tools/yt_upload_batch2.py"):
                content += (
                    "\ndef run_live():\nvalidate_live_upload(\n"
                    "get_credentials(interactive=True)\n"
                    "verify_authenticated_youtube_channel(\n"
                    "_begin_attempt(\nverify_execution_authorization(\n"
                    "request = service.videos().insert(\n"
                    "MediaFileUpload(\n_finish_attempt(action, \"POSTED\"\n"
                    "write_json(UPLOAD_LOG_PATH"
                )
            elif relative == pathlib.Path("pipeline/official_news_monitor.py"):
                content += (
                    "\ndef authorize_acknowledgements():\n"
                    "raise ActionBlocked('programmatic source acknowledgement is disabled')\n"
                    "confined_cli_path(DEFAULT_OUT, ROOT, '.json')"
                )
            elif relative == pathlib.Path("pipeline/push_agent.py"):
                content += (
                    "\ndef execute(do_commit=False, do_push=False):\n"
                    "if do_commit or do_push:\n return 2\n"
                    "run = runner or _run\n"
                    "print('permanently local-only; human owner must perform Git; "
                    "no files staged, committed, pushed, or deployed')"
                )
            path.write_text(content, encoding="utf-8")
        check("legacy publisher sources retain shared authority gates",
              guard.publisher_source_contract(source_root) == [])
        (source_root / "automation/ig_publish.py").write_text(
            "legacy live publisher", encoding="utf-8")
        check("missing legacy publisher gate fails closed",
              len(guard.publisher_source_contract(source_root)) >= 1)
    print("automation policy guard: all checks passed")


if __name__ == "__main__":
    main()
