@echo off
set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8
REM ngernduangold — daily content + measure + schedule loop (Cowork handoff)
REM dispatcher -> daily_content -> ga4_pull -> traffic_analyst -> post_agent(+timing) -> hermes_digest
REM ปลอดภัย: ผลิต draft + วัดผล + ตารางคิว เท่านั้น ไม่โพสต์/ไม่ commit/ไม่ deploy
set LOG=C:\Users\nL_ku\ngernduangold-site\automation-log\dispatcher.log
set PY=C:\Users\nL_ku\AppData\Local\Python\pythoncore-3.14-64\python.exe
set BASE=C:\Users\nL_ku\ngernduangold-site\pipeline
echo [%date% %time%] run_daily start >> "%LOG%"
"%PY%" "%BASE%\dispatcher.py" >> "%LOG%" 2>&1
echo [%date% %time%] daily_content start >> "%LOG%"
"%PY%" "%BASE%\daily_content.py" >> "%LOG%" 2>&1
echo [%date% %time%] ga4_pull start >> "%LOG%"
"%PY%" "%BASE%\ga4_pull.py" >> "%LOG%" 2>&1
echo [%date% %time%] traffic_analyst start >> "%LOG%"
"%PY%" "%BASE%\traffic_analyst.py" >> "%LOG%" 2>&1
echo [%date% %time%] post_agent start (timing -> queue) >> "%LOG%"
"%PY%" "%BASE%\post_agent.py" >> "%LOG%" 2>&1
echo [%date% %time%] credit_tracker status >> "%LOG%"
"%PY%" "%BASE%\credit_tracker.py" status >> "%LOG%" 2>&1
echo [%date% %time%] dashboard_agent start (dashboard.html) >> "%LOG%"
"%PY%" "%BASE%\dashboard_agent.py" >> "%LOG%" 2>&1
echo [%date% %time%] post_dispatcher (video -> post plan) >> "%LOG%"
"%PY%" "%BASE%\post_dispatcher.py" >> "%LOG%" 2>&1
"%PY%" "%BASE%\posting_kit.py" >> "%LOG%" 2>&1
echo [%date% %time%] daily_post_reminder >> "%LOG%"
"%PY%" "%BASE%\daily_post_reminder.py" >> "%LOG%" 2>&1
echo [%date% %time%] hermes_digest start >> "%LOG%"
"%PY%" "%BASE%\hermes_digest.py" >> "%LOG%" 2>&1
echo [%date% %time%] cc_monitor (Claude Code status -> Cowork) >> "%LOG%"
"%PY%" "%BASE%\cc_monitor.py" >> "%LOG%" 2>&1
echo [%date% %time%] run_daily end exit=%errorlevel% >> "%LOG%"
