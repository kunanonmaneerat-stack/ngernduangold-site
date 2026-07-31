@echo off
set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8
REM ngernduangold — daily content + measure + schedule loop (Cowork handoff)
REM dispatcher -> daily_content -> ga4_pull -> traffic_analyst -> post_agent(+timing) -> hermes_digest
REM ปลอดภัย: ผลิต draft + วัดผล + ตารางคิว เท่านั้น ไม่โพสต์/ไม่ commit/ไม่ deploy
set LOG=C:\Users\nL_ku\ngernduangold-site\automation-log\dispatcher.log
set PY=C:\Users\nL_ku\AppData\Local\Python\pythoncore-3.14-64\python.exe
set BASE=C:\Users\nL_ku\ngernduangold-site\pipeline
echo [%date% %time%] comply_gate_stitch scan (components\stitch) >> "%LOG%"
"%PY%" "%BASE%\..\tools\comply_gate_stitch.py" "%BASE%\..\components\stitch" >> "%LOG%" 2>&1
if errorlevel 1 echo [%date% %time%] !! comply_gate_stitch FAIL - fix components\stitch before deploy >> "%LOG%"
echo [%date% %time%] run_daily start >> "%LOG%"
"%PY%" "%BASE%\dispatcher.py" >> "%LOG%" 2>&1
echo [%date% %time%] daily_content start >> "%LOG%"
"%PY%" "%BASE%\daily_content.py" >> "%LOG%" 2>&1
echo [%date% %time%] ga4_pull start >> "%LOG%"
"%PY%" "%BASE%\ga4_pull.py" >> "%LOG%" 2>&1
echo [%date% %time%] fb_queue_linkcheck (order-flow-fb-master B1) >> "%LOG%"
"%PY%" "%BASE%\fb_queue_linkcheck.py" >> "%LOG%" 2>&1
echo [%date% %time%] qa_watermark gate: scan postable staging (FAIL = DO NOT POST) >> "%LOG%"
"%PY%" "%BASE%\..\tiktok-pipeline\src\qa_watermark.py" "%BASE%\..\_vidout\clean\*.mp4" "%BASE%\..\automation-log\_social-stage\_final_*.mp4" --fps 3 >> "%LOG%" 2>&1
if errorlevel 1 echo WATERMARK ALERT: qa_watermark FAIL in staging - DO NOT POST any staged clip until fixed. See dispatcher.log > "%BASE%\..\automation-log\cowork-inbox\WATERMARK-ALERT.md"
echo [%date% %time%] traffic_analyst start >> "%LOG%"
"%PY%" "%BASE%\traffic_analyst.py" >> "%LOG%" 2>&1
echo [%date% %time%] post_agent start (timing -> queue) >> "%LOG%"
"%PY%" "%BASE%\post_agent.py" >> "%LOG%" 2>&1
echo [%date% %time%] credit_tracker status >> "%LOG%"
"%PY%" "%BASE%\credit_tracker.py" status >> "%LOG%" 2>&1
echo [%date% %time%] dashboard_agent start (dashboard.html) >> "%LOG%"
"%PY%" "%BASE%\dashboard_agent.py" >> "%LOG%" 2>&1
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
"%PY%" "%BASE%\posting_kit.py" >> "%LOG%" 2>&1
REM echo [%date% %time%] daily_post_reminder >> "%LOG%"
REM "%PY%" "%BASE%\daily_post_reminder.py" >> "%LOG%" 2>&1
echo [%date% %time%] hermes_digest start >> "%LOG%"
"%PY%" "%BASE%\hermes_digest.py" >> "%LOG%" 2>&1
echo [%date% %time%] cc_monitor (Claude Code status -> Cowork) >> "%LOG%"
"%PY%" "%BASE%\cc_monitor.py" >> "%LOG%" 2>&1
REM preflight: the one standing checklist (queue / delivery gap / captions / posted
REM records / disclosure / attribution). Runs HERE because the dispatcher keeps running
REM even when every Cowork scheduled task is disabled -- which is exactly what happened
REM 27-30 Jul 2026: dispatcher fired daily, nothing shipped, and no guard said a word.
REM exit 2 = FAIL -> drop an alert file that the morning routines will surface.
REM guard self-test FIRST: a guard that has gone blind still prints PASS, so the
REM checklist is only worth reading if its own checks are proven to still fire.
echo [%date% %time%] guard self-test >> "%LOG%"
"%PY%" "%BASE%\..\tools\test_preflight_checks.py" >> "%LOG%" 2>&1
if errorlevel 1 (
  echo GUARD SELF-TEST FAIL - preflight results cannot be trusted until this is fixed. See dispatcher.log. > "%BASE%\..\automation-log\cowork-inbox\GUARD-SELFTEST-ALERT.md"
  echo [%date% %time%] !! guard self-test FAIL >> "%LOG%"
) else (
  if exist "%BASE%\..\automation-log\cowork-inbox\GUARD-SELFTEST-ALERT.md" del "%BASE%\..\automation-log\cowork-inbox\GUARD-SELFTEST-ALERT.md"
)
echo [%date% %time%] preflight start >> "%LOG%"
"%PY%" "%BASE%\..\tools\preflight.py" >> "%LOG%" 2>&1
if errorlevel 2 (
  echo PREFLIGHT FAIL - see automation-log\dispatcher.log for the failing check. Do not post until resolved. > "%BASE%\..\automation-log\cowork-inbox\PREFLIGHT-ALERT.md"
  echo [%date% %time%] !! preflight FAIL - alert written >> "%LOG%"
) else (
  if exist "%BASE%\..\automation-log\cowork-inbox\PREFLIGHT-ALERT.md" del "%BASE%\..\automation-log\cowork-inbox\PREFLIGHT-ALERT.md"
)
echo [%date% %time%] run_daily end exit=%errorlevel% >> "%LOG%"
