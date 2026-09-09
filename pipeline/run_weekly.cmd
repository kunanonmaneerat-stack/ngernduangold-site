@echo off
setlocal EnableExtensions EnableDelayedExpansion
set RUN_EXIT=0
set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8
set "TASK_NAME=ngernduangold_weekly"
set "PUBLICATION_STATE=BLOCKED_LOCAL_ONLY"
set "REPO_ROOT=C:\Users\nL_ku\ngernduangold-site"
set "PY=%REPO_ROOT%\pipeline\python_runtime.cmd"
set "BASE=%REPO_ROOT%\pipeline"
set "RECEIPT_TOOL=%BASE%\task_run_receipt.p"
set "RECEIPT_TOOL=%RECEIPT_TOOL%y"
set "RECEIPT_ROOT=%REPO_ROOT%\.local-private\runtime\task-runs"
REM ngernduangold — weekly growth review loop
REM GA4 (source+page) + GSC (keywords) -> weekly intent diagnostic
REM local-only: อ่าน GA4/GSC + เขียน report; ไม่มี Telegram/Slack/email/browser mutation
if not defined NGERNDUANGOLD_WEEKLY_LOG set "NGERNDUANGOLD_WEEKLY_LOG=C:\Users\nL_ku\ngernduangold-site\.local-private\runtime\weekly.log"
set "LOG=%NGERNDUANGOLD_WEEKLY_LOG%"
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
echo [%date% %time%] run_weekly start >> "%LOG%"
echo [%date% %time%] official_news_monitor >> "%LOG%"
set "STEP_NAME=official_news_monitor"
set "STEP_CONTRACT=official-news-v1"
call :graded "%PY%" "%BASE%\official_news_monitor.py" --strict
set OFFICIAL_NEWS_RC=!errorlevel!
if !OFFICIAL_NEWS_RC! EQU 1 echo [%date% %time%] OFFICIAL NEWS REVIEW_REQUIRED - see cowork-inbox\OFFICIAL-NEWS-REVIEW.md >> "%LOG%"
if !OFFICIAL_NEWS_RC! EQU 2 echo [%date% %time%] OFFICIAL NEWS BLOCKED - current source verification failed; monitoring continues >> "%LOG%"
if !OFFICIAL_NEWS_RC! GEQ 3 echo [%date% %time%] !! OFFICIAL NEWS RUNNER_FAILED - snapshot contract/runtime failure >> "%LOG%"
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
REM Measurement sources are independent.  A blocked GA4 capture must not stop
REM a valid finalized GSC refresh (or vice versa).  Keep the aggregate run
REM nonzero while allowing fail-closed reports and the repair loop to observe
REM every source in the same weekly run.
set "STEP_NAME=ga4_pull"
set "STEP_CONTRACT=block-on-2-v1"
call :required "%PY%" "%BASE%\ga4_pull.py"
set GA4_PULL_RC=!errorlevel!
if !GA4_PULL_RC! NEQ 0 echo [%date% %time%] ga4 pull COMPLETED_BLOCKED - independent GSC refresh continues >> "%LOG%"
set "STEP_NAME=gsc_pull"
set "STEP_CONTRACT=block-on-2-v1"
call :required "%PY%" "%BASE%\gsc_pull.py"
set GSC_PULL_RC=!errorlevel!
if !GSC_PULL_RC! NEQ 0 echo [%date% %time%] gsc pull COMPLETED_BLOCKED - fail-closed weekly diagnostics continue >> "%LOG%"
set "STEP_NAME=weekly_growth_review"
set "STEP_CONTRACT=zero-only-v1"
call :required "%PY%" "%BASE%\weekly_growth_review.py" --local-only || goto :abort
set "STEP_NAME=improvement_loop"
set "STEP_CONTRACT=improvement-loop-v1"
call :required "%PY%" "%BASE%\improvement_loop.py" run --cadence weekly --mode local-safe --json
set IMPROVEMENT_RC=!errorlevel!
if !IMPROVEMENT_RC! NEQ 0 echo [%date% %time%] improvement loop COMPLETED_BLOCKED - weekly evidence written, no growth action >> "%LOG%"
echo [%date% %time%] run_weekly end exit=!RUN_EXIT! >> "%LOG%"
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
echo [%date% %time%] run_weekly ABORTED reason=!ABORT_REASON! exit=!RUN_EXIT! >> "%LOG%"
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
