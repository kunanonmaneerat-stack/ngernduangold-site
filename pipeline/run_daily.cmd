@echo off
setlocal EnableExtensions EnableDelayedExpansion
set RUN_EXIT=0
set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8
set "TASK_NAME=ngernduangold_daily"
set "PUBLICATION_STATE=BLOCKED_LOCAL_ONLY"
set "REPO_ROOT=C:\Users\nL_ku\ngernduangold-site"
set "PY=%REPO_ROOT%\pipeline\python_runtime.cmd"
set "BASE=%REPO_ROOT%\pipeline"
set "RECEIPT_TOOL=%BASE%\task_run_receipt.p"
set "RECEIPT_TOOL=%RECEIPT_TOOL%y"
set "RECEIPT_ROOT=%REPO_ROOT%\.local-private\runtime\task-runs"
REM ngernduangold — daily content + measure + schedule loop (Cowork handoff)
REM dispatcher -> daily_content -> ga4_pull -> traffic_analyst -> post_agent(+timing) -> local digest
REM local-only: ผลิต draft + วัดผล + ตารางคิวเท่านั้น; ไม่มี Telegram/Slack/email/browser mutation
if not defined NGERNDUANGOLD_DISPATCHER_LOG set "NGERNDUANGOLD_DISPATCHER_LOG=C:\Users\nL_ku\ngernduangold-site\.local-private\runtime\dispatcher.log"
set "LOG=%NGERNDUANGOLD_DISPATCHER_LOG%"
set "TASK_RUN_ID="
set "ABORT_REASON="
set "ABORT_STEP="
for /f "usebackq delims=" %%R in (`^"^"%PY%" "%RECEIPT_TOOL%" start --root "%RECEIPT_ROOT%" --task "%TASK_NAME%" --runner "%~f0" --log "%LOG%"^"`) do if not defined TASK_RUN_ID set "TASK_RUN_ID=%%R"
if not defined TASK_RUN_ID (
  echo [%date% %time%] task receipt start failed - runner evidence unavailable >> "%LOG%"
  exit /b 3
)
cd /d "%REPO_ROOT%"
set "CWD_RC=!errorlevel!"
call :record_internal "runner.chdir" !CWD_RC!
if !errorlevel! NEQ 0 (
  set RUN_EXIT=3
  set "ABORT_REASON=receipt_record_chdir_failed"
  goto :abort
)
if !CWD_RC! NEQ 0 (
  set RUN_EXIT=3
  set "ABORT_REASON=working_directory_failed"
  goto :abort
)
set "LOG_DIR_RC=0"
for %%I in ("%LOG%") do if not exist "%%~dpI" (
  mkdir "%%~dpI"
  set "LOG_DIR_RC=!errorlevel!"
)
call :record_internal "runner.log_directory" !LOG_DIR_RC!
if !errorlevel! NEQ 0 (
  set RUN_EXIT=3
  set "ABORT_REASON=receipt_record_log_directory_failed"
  goto :abort
)
if !LOG_DIR_RC! NEQ 0 (
  set RUN_EXIT=3
  set "ABORT_REASON=log_directory_failed"
  goto :abort
)
call "%PY%" "%RECEIPT_TOOL%" rotate-log --path "%LOG%" --max-bytes 5242880 --keep 3 --quiet
set "LOG_PREP_RC=!errorlevel!"
call :record_internal "runner.log_prepare" !LOG_PREP_RC!
if !errorlevel! NEQ 0 (
  set RUN_EXIT=3
  set "ABORT_REASON=receipt_record_log_prepare_failed"
  goto :abort
)
if !LOG_PREP_RC! NEQ 0 (
  set RUN_EXIT=3
  set "ABORT_REASON=log_prepare_failed"
  goto :abort
)
echo [%date% %time%] comply_gate_stitch scan (components\stitch) >> "%LOG%"
set "STEP_NAME=comply_gate_stitch"
set "STEP_CONTRACT=scan-on-1-v1"
call :required "%PY%" "%BASE%\..\tools\comply_gate_stitch.py" "%BASE%\..\components\stitch" || goto :abort
echo [%date% %time%] run_daily start >> "%LOG%"
REM uptime: is the site actually serving? Added 1 Aug 2026 by the token audit.
REM Was a Cowork agent task firing every 6h (120 LLM runs/month + a Chrome tab on the
REM owner's screen) to answer a yes/no that one HTTP request answers. It also reads the
REM page BODY, because Netlify's paused / usage-limit pages return a healthy 200 - which
REM is exactly the outage we care about. exit 2 = down (writes SITE-DOWN-ALERT.md),
REM exit 1 = could not look (no network) and is deliberately NOT reported as an outage.
set "STEP_NAME=uptime_check"
set "STEP_CONTRACT=review-or-block-v1"
call :graded "%PY%" "%BASE%\..\tools\uptime_check.py"
if !STEP_RC! EQU 2 echo [%date% %time%] !! SITE DOWN - see cowork-inbox\SITE-DOWN-ALERT.md >> "%LOG%"
REM agent-gap: did the AGENT layer do anything in the last 26h? Added 7 Aug 2026.
REM This block exists because THIS layer is the only one that survives the failure it
REM watches for. Cowork agent tasks fire only while the desktop app is open, so when the
REM owner is away every agent stops silently - 27-30 Jul (4 days) and 3-5 Aug (3 days),
REM neither noticed until someone asked. The ops Slack channel has a written rule saying
REM "no message = the system is dead", but Slack can only be written BY an agent, so the
REM alarm died with the thing it was alarming about. This scheduled invocation is the
REM only production caller explicitly authorised to update the one local alert file.
REM exit 2 = silent, writes the alert;
REM exit 1 = could not tell, which is deliberately NOT reported as silence.
echo [%date% %time%] agent_gap_check >> "%LOG%"
set "STEP_NAME=agent_gap_check"
set "STEP_CONTRACT=review-or-block-v1"
call :graded "%PY%" "%BASE%\..\tools\agent_gap_check.py" --update-agent-silent-alert-file
if !STEP_RC! EQU 2 echo [%date% %time%] !! AGENT LAYER SILENT - see cowork-inbox\AGENT-SILENT-ALERT.md >> "%LOG%"
echo [%date% %time%] automation_policy_guard >> "%LOG%"
REM A policy finding must keep publication blocked, but this runner has been
REM reduced to local/read-only work.  Preserve exit 2 and keep the monitoring
REM path alive so the owner can see and repair the finding.
set "STEP_NAME=automation_policy_guard"
set "STEP_CONTRACT=block-on-2-v1"
call :required "%PY%" "%BASE%\..\tools\automation_policy_guard.py"
set AUTOMATION_POLICY_RC=!errorlevel!
if !AUTOMATION_POLICY_RC! NEQ 0 echo [%date% %time%] automation policy COMPLETED_BLOCKED - local monitoring continues >> "%LOG%"
echo [%date% %time%] privacy_guard >> "%LOG%"
set "STEP_NAME=privacy_guard"
set "STEP_CONTRACT=privacy-guard-v1"
call :required "%PY%" "%BASE%\..\tools\privacy_guard.py" || goto :abort
echo [%date% %time%] public_identity_guard >> "%LOG%"
set "STEP_NAME=public_identity_guard"
set "STEP_CONTRACT=block-on-2-v1"
call :required "%PY%" "%BASE%\..\tools\public_identity_guard.py" || goto :abort
echo [%date% %time%] manifest_contract >> "%LOG%"
set "STEP_NAME=manifest_contract"
set "STEP_CONTRACT=validation-on-1-v1"
call :required "%PY%" "%BASE%\..\tools\manifest_contract.py" || goto :abort
echo [%date% %time%] content_calendar_guard >> "%LOG%"
REM Calendar exits 1/2 are closed lifecycle/safety states, not runner failures.
REM Continue local evidence/monitoring; exit 3 is reserved for runner failure.
set "STEP_NAME=content_calendar_guard"
set "STEP_CONTRACT=calendar-v1"
call :graded "%PY%" "%BASE%\..\tools\content_calendar_guard.py" --json
set CALENDAR_RC=!errorlevel!
if !CALENDAR_RC! EQU 1 echo [%date% %time%] content calendar COMPLETED_BLOCKED - stale slots retained; no backfill/promotion; monitoring continues >> "%LOG%"
if !CALENDAR_RC! EQU 2 echo [%date% %time%] content calendar BLOCKED - safety findings retained; no publication; monitoring continues >> "%LOG%"
if !CALENDAR_RC! GEQ 3 echo [%date% %time%] !! content calendar RUNNER_FAILED - evidence tail cannot trust guard execution >> "%LOG%"
if !CALENDAR_RC! GEQ 3 goto :abort
set "STEP_NAME=dispatcher"
set "STEP_CONTRACT=novelty-queue-v1"
call :novelty_queue "%PY%" "%BASE%\dispatcher.py" --local-only
set DISPATCHER_RC=!errorlevel!
if !DISPATCHER_RC! EQU 10 echo [%date% %time%] dispatcher NOVELTY_EXHAUSTED - SKIP; diagnostic tail continues >> "%LOG%"
if !DISPATCHER_RC! EQU 20 echo [%date% %time%] dispatcher BLOCKED_UNKNOWN - diagnostic tail continues >> "%LOG%"
if !DISPATCHER_RC! NEQ 0 if !DISPATCHER_RC! NEQ 10 if !DISPATCHER_RC! NEQ 20 goto :abort
echo [%date% %time%] daily_content start >> "%LOG%"
set "STEP_NAME=daily_content"
set "STEP_CONTRACT=novelty-queue-v1"
call :novelty_queue "%PY%" "%BASE%\daily_content.py" --local-only
set DAILY_CONTENT_RC=!errorlevel!
if !DAILY_CONTENT_RC! EQU 10 echo [%date% %time%] daily_content NOVELTY_EXHAUSTED - SKIP; diagnostic tail continues >> "%LOG%"
if !DAILY_CONTENT_RC! EQU 20 echo [%date% %time%] daily_content BLOCKED_UNKNOWN - diagnostic tail continues >> "%LOG%"
if !DAILY_CONTENT_RC! NEQ 0 if !DAILY_CONTENT_RC! NEQ 10 if !DAILY_CONTENT_RC! NEQ 20 goto :abort
echo [%date% %time%] ga4_pull start >> "%LOG%"
REM GA4 trust/metadata failure is a decision block, not permission to blind the
REM rest of the local safety loop.  Preserve exit 2, but still run media QA,
REM dashboard, improvement diagnostics and final preflight.  Every downstream
REM analytics consumer is independently fail-closed on an invalid GA4 bundle.
set "STEP_NAME=ga4_pull"
set "STEP_CONTRACT=block-on-2-v1"
call :required "%PY%" "%BASE%\ga4_pull.py"
set GA4_PULL_RC=!errorlevel!
if !GA4_PULL_RC! NEQ 0 echo [%date% %time%] ga4 pull COMPLETED_BLOCKED - safety and repair tail continues >> "%LOG%"
echo [%date% %time%] fb_queue_linkcheck (order-flow-fb-master B1) >> "%LOG%"
REM Link health is an external observation. A DNS/HTTP failure must block the
REM affected link plan, but it must not blind independent media QA, dashboard,
REM improvement diagnostics or final preflight.
set "STEP_NAME=fb_queue_linkcheck"
set "STEP_CONTRACT=validation-on-1-v1"
call :required "%PY%" "%BASE%\fb_queue_linkcheck.py"
set FB_LINKCHECK_RC=!errorlevel!
if !FB_LINKCHECK_RC! NEQ 0 echo [%date% %time%] fb link check COMPLETED_BLOCKED - safety and repair tail continues >> "%LOG%"
REM Daily media coverage is source-aware: all canonical reels get a fresh Veo frame scan,
REM while every future video/image route must also pass an exact-hash visual QA receipt.
REM Images are never sent to the Veo-only detector; quarantine is never enumerated.
echo [%date% %time%] daily_media_gate: canonical reels + hash-bound future media >> "%LOG%"
set "STEP_NAME=daily_media_gate"
set "STEP_CONTRACT=block-on-2-v1"
call :required "%PY%" "%BASE%\..\tools\daily_media_gate.py" --fps 3 --json
set WATERMARK_RC=!errorlevel!
if !WATERMARK_RC! GEQ 1 echo MEDIA QA ALERT: canonical/future media coverage FAIL - DO NOT POST until fixed. See dispatcher.log > "%BASE%\..\automation-log\cowork-inbox\WATERMARK-ALERT.md"
if !WATERMARK_RC! EQU 0 if exist "%BASE%\..\automation-log\cowork-inbox\WATERMARK-ALERT.md" del "%BASE%\..\automation-log\cowork-inbox\WATERMARK-ALERT.md"
REM Exit 2 is a verified fail-closed media block. Keep publication closed but
REM preserve the independent improvement/dashboard/preflight evidence tail.
REM Any other non-zero is outside the declared contract and aborts fail-closed.
if !WATERMARK_RC! NEQ 0 if !WATERMARK_RC! NEQ 2 goto :abort
echo [%date% %time%] improvement_loop local-safe observation >> "%LOG%"
REM FAILED_VALIDATION is an expected decision block, not a runner crash.  The
REM loop is local-safe and emits private evidence; keep diagnostics running
REM while RUN_EXIT remains nonzero and no publisher is reachable.
set "STEP_NAME=improvement_loop"
set "STEP_CONTRACT=improvement-loop-v1"
call :required "%PY%" "%BASE%\improvement_loop.py" run --cadence daily --mode local-safe --json
set IMPROVEMENT_RC=!errorlevel!
if !IMPROVEMENT_RC! NEQ 0 echo [%date% %time%] improvement loop COMPLETED_BLOCKED - diagnostic tail continues >> "%LOG%"
echo [%date% %time%] traffic_analyst start >> "%LOG%"
set "STEP_NAME=traffic_analyst"
set "STEP_CONTRACT=generic"
call :required "%PY%" "%BASE%\traffic_analyst.py" || goto :abort
echo [%date% %time%] post_agent start (timing -> queue) >> "%LOG%"
REM A declared-but-blocked queue is an expected fail-closed state, not a reason
REM to blind the monitoring tail.  post_agent has no publisher side effect;
REM preserve its nonzero result in RUN_EXIT but continue dashboard/digest/preflight.
set "STEP_NAME=post_agent"
set "STEP_CONTRACT=queue-agent-v1"
call :required "%PY%" "%BASE%\post_agent.py"
set POST_QUEUE_RC=!errorlevel!
if !POST_QUEUE_RC! NEQ 0 echo [%date% %time%] post_agent COMPLETED_BLOCKED - monitoring tail continues >> "%LOG%"
echo [%date% %time%] credit_tracker status >> "%LOG%"
set "STEP_NAME=credit_tracker_status"
set "STEP_CONTRACT=generic"
call :required "%PY%" "%BASE%\credit_tracker.py" status || goto :abort
echo [%date% %time%] dashboard_agent start (dashboard.html) >> "%LOG%"
set "STEP_NAME=dashboard_agent"
set "STEP_CONTRACT=generic"
call :required "%PY%" "%BASE%\dashboard_agent.py" || goto :abort
REM DISABLED 31 Jul 2026 -- post_dispatcher + daily_post_reminder are a LEGACY pair that
REM plan from automation-log/video-out/ (raw Google Flow clips, June, 720x1280 WITH the Veo
REM sparkle watermark) and know nothing about the current pipeline (manifest -> reels/*.mp4,
REM 1080x1920, watermark-free). They were still writing post-plan.json every morning, telling
REM the reminder to post hard-blocked footage on the exact days b3-05..b3-07 are queued, and
REM the paths inside it pointed at a dead sandbox mount. video-post-verify caught it 30 Jul
REM 21:45 (watermark on 9-30 of 30 frames). Same watermark class that burned 5 IG reels 9 Jul.
REM The daily card is now produced by the Cowork task `daily-social-post-reminder` (08:00)
REM straight from the manifest, so nothing here is lost. Re-enable ONLY after post_dispatcher
REM is rewritten to read .system_control/content_manifest.json instead of video-out/.
REM echo [%date% %time%] post_dispatcher (video -> post plan) >> "%LOG%"
REM "%PY%" "%BASE%\post_dispatcher.py" >> "%LOG%" 2>&1
REM Its legacy producer is intentionally disabled above.  Missing legacy input
REM is a safe SKIP; malformed input needs review, while I/O/runtime errors remain fatal.
set "STEP_NAME=posting_kit"
set "STEP_CONTRACT=posting-kit-v1"
call :graded "%PY%" "%BASE%\posting_kit.py" --allow-missing-legacy-plan
set POSTING_KIT_RC=!errorlevel!
if !POSTING_KIT_RC! EQU 1 echo [%date% %time%] posting kit REVIEW_REQUIRED - legacy input/output requires review; monitoring continues >> "%LOG%"
if !POSTING_KIT_RC! GEQ 2 goto :abort
REM echo [%date% %time%] daily_post_reminder >> "%LOG%"
REM "%PY%" "%BASE%\daily_post_reminder.py" >> "%LOG%" 2>&1
echo [%date% %time%] hermes_digest start >> "%LOG%"
set "STEP_NAME=hermes_digest"
set "STEP_CONTRACT=generic"
call :required "%PY%" "%BASE%\hermes_digest.py" --local-only || goto :abort
echo [%date% %time%] cc_monitor (Claude Code status -> Cowork) >> "%LOG%"
set "STEP_NAME=cc_monitor"
set "STEP_CONTRACT=generic"
call :required "%PY%" "%BASE%\cc_monitor.py" --local-only || goto :abort
REM preflight: the one standing checklist (queue / delivery gap / captions / posted
REM records / disclosure / attribution). Runs HERE because the dispatcher keeps running
REM even when every Cowork scheduled task is disabled -- which is exactly what happened
REM 27-30 Jul 2026: dispatcher fired daily, nothing shipped, and no guard said a word.
REM exit 2 = FAIL -> drop an alert file that the morning routines will surface.
REM guard self-test FIRST: a guard that has gone blind still prints PASS, so the
REM checklist is only worth reading if its own checks are proven to still fire.
echo [%date% %time%] guard self-test >> "%LOG%"
set "STEP_NAME=preflight_self_test"
set "STEP_CONTRACT=zero-only-v1"
call :required "%PY%" "%BASE%\..\tools\test_preflight_checks.py"
if errorlevel 1 (
  echo GUARD SELF-TEST FAIL - preflight results cannot be trusted until this is fixed. See the private dispatcher log. > "%BASE%\..\automation-log\cowork-inbox\GUARD-SELFTEST-ALERT.md"
  echo [%date% %time%] !! guard self-test FAIL >> "%LOG%"
) else (
  if exist "%BASE%\..\automation-log\cowork-inbox\GUARD-SELFTEST-ALERT.md" del "%BASE%\..\automation-log\cowork-inbox\GUARD-SELFTEST-ALERT.md"
)
if !STEP_RC! NEQ 0 goto :abort
echo [%date% %time%] preflight start >> "%LOG%"
set "STEP_NAME=preflight"
set "STEP_CONTRACT=review-or-block-v1"
call :graded "%PY%" "%BASE%\..\tools\preflight.py"
set PREFLIGHT_RC=!errorlevel!
if !PREFLIGHT_RC! GEQ 2 (
  echo PREFLIGHT FAIL - see the private dispatcher log for the failing check. Do not post until resolved.>"%BASE%\..\automation-log\cowork-inbox\PREFLIGHT-ALERT.md"
  echo [%date% %time%] !! preflight FAIL - alert written >> "%LOG%"
) else if !PREFLIGHT_RC! EQU 0 (
  if exist "%BASE%\..\automation-log\cowork-inbox\PREFLIGHT-ALERT.md" del "%BASE%\..\automation-log\cowork-inbox\PREFLIGHT-ALERT.md"
)
echo [%date% %time%] run_daily end exit=!RUN_EXIT! >> "%LOG%"
call :close_receipt "end" !RUN_EXIT! "normal_end"
set CLOSE_RC=!errorlevel!
if !CLOSE_RC! EQU 2 if !RUN_EXIT! LSS 2 set RUN_EXIT=2
if !CLOSE_RC! NEQ 0 if !CLOSE_RC! NEQ 2 (
  echo [%date% %time%] task receipt close reported runner or evidence failure - forcing runner failure >> "%LOG%"
  set RUN_EXIT=3
)
exit /b !RUN_EXIT!

:abort
if !RUN_EXIT! LSS 2 set RUN_EXIT=2
if not defined ABORT_REASON set "ABORT_REASON=unclassified_abort"
echo [%date% %time%] run_daily ABORTED reason=!ABORT_REASON! exit=!RUN_EXIT! >> "%LOG%"
call :close_receipt "abort" !RUN_EXIT! "!ABORT_REASON!" "!ABORT_STEP!"
set CLOSE_RC=!errorlevel!
if !CLOSE_RC! EQU 2 if !RUN_EXIT! LSS 2 set RUN_EXIT=2
if !CLOSE_RC! NEQ 0 if !CLOSE_RC! NEQ 2 (
  echo [%date% %time%] task receipt abort-close reported runner or evidence failure >> "%LOG%"
  set RUN_EXIT=3
)
exit /b !RUN_EXIT!

:required
set "ABORT_REASON="
set "ABORT_STEP="
call "%PY%" "%RECEIPT_TOOL%" exec --root "%RECEIPT_ROOT%" --task "%TASK_NAME%" --run-id "%TASK_RUN_ID%" --step "%STEP_NAME%" --wrapper required --contract "%STEP_CONTRACT%" -- %* >> "%LOG%" 2>&1
set STEP_RC=!errorlevel!
if !STEP_RC! EQU 90 (
  set RUN_EXIT=3
  set "ABORT_REASON=receipt_exec_failed_!STEP_NAME!"
  set "ABORT_STEP="
  goto :abort
)
if !STEP_RC! GEQ 3 set RUN_EXIT=3
if !STEP_RC! EQU 2 if !RUN_EXIT! LSS 2 set RUN_EXIT=2
if !STEP_RC! EQU 1 if !RUN_EXIT! LSS 2 set RUN_EXIT=2
if !STEP_RC! NEQ 0 set "ABORT_REASON=step_nonzero"
if !STEP_RC! NEQ 0 set "ABORT_STEP=!STEP_NAME!"
exit /b !STEP_RC!

:novelty_queue
set "ABORT_REASON="
set "ABORT_STEP="
call "%PY%" "%RECEIPT_TOOL%" exec --root "%RECEIPT_ROOT%" --task "%TASK_NAME%" --run-id "%TASK_RUN_ID%" --step "%STEP_NAME%" --wrapper required --contract "%STEP_CONTRACT%" -- %* >> "%LOG%" 2>&1
set STEP_RC=!errorlevel!
if !STEP_RC! EQU 90 (
  set RUN_EXIT=3
  set "ABORT_REASON=receipt_exec_failed_!STEP_NAME!"
  set "ABORT_STEP="
  exit /b 3
)
if !STEP_RC! EQU 10 exit /b 10
if !STEP_RC! EQU 20 (
  if !RUN_EXIT! LSS 2 set RUN_EXIT=2
  set "ABORT_REASON=step_blocked_unknown"
  set "ABORT_STEP=!STEP_NAME!"
  exit /b 20
)
if !STEP_RC! NEQ 0 (
  set RUN_EXIT=3
  set "ABORT_REASON=step_unclassified"
  set "ABORT_STEP=!STEP_NAME!"
)
exit /b !STEP_RC!

:graded
set "ABORT_REASON="
set "ABORT_STEP="
call "%PY%" "%RECEIPT_TOOL%" exec --root "%RECEIPT_ROOT%" --task "%TASK_NAME%" --run-id "%TASK_RUN_ID%" --step "%STEP_NAME%" --wrapper graded --contract "%STEP_CONTRACT%" -- %* >> "%LOG%" 2>&1
set STEP_RC=!errorlevel!
if !STEP_RC! EQU 90 (
  set RUN_EXIT=3
  set "ABORT_REASON=receipt_exec_failed_!STEP_NAME!"
  set "ABORT_STEP="
  goto :abort
)
if !STEP_RC! GEQ 3 set RUN_EXIT=3
if !STEP_RC! EQU 2 if !RUN_EXIT! LSS 2 set RUN_EXIT=2
if !STEP_RC! EQU 1 if !RUN_EXIT! LSS 1 set RUN_EXIT=1
if !STEP_RC! NEQ 0 set "ABORT_REASON=step_nonzero"
if !STEP_RC! NEQ 0 set "ABORT_STEP=!STEP_NAME!"
exit /b !STEP_RC!

:record_internal
call "%PY%" "%RECEIPT_TOOL%" record --root "%RECEIPT_ROOT%" --task "%TASK_NAME%" --run-id "%TASK_RUN_ID%" --step "%~1" --wrapper internal --contract internal-v1 --raw-rc "%~2"
exit /b !errorlevel!

:close_receipt
if "%~4"=="" (
  call "%PY%" "%RECEIPT_TOOL%" finish --root "%RECEIPT_ROOT%" --task "%TASK_NAME%" --run-id "%TASK_RUN_ID%" --terminal "%~1" --terminal-reason "%~3" --publication-state "%PUBLICATION_STATE%" --final-rc "%~2"
) else (
  call "%PY%" "%RECEIPT_TOOL%" finish --root "%RECEIPT_ROOT%" --task "%TASK_NAME%" --run-id "%TASK_RUN_ID%" --terminal "%~1" --terminal-reason "%~3" --terminal-step "%~4" --publication-state "%PUBLICATION_STATE%" --final-rc "%~2"
)
exit /b !errorlevel!
