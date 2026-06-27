@echo off
set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8
REM ngernduangold — weekly growth review loop
REM GA4 (source+page) + GSC (keywords) -> weekly_growth_review -> winners + double-down actions
REM ปลอดภัย: อ่าน GA4/GSC + เขียน report เท่านั้น (ไม่โพสต์/ไม่ deploy/ไม่ลบ)
set LOG=C:\Users\nL_ku\ngernduangold-site\automation-log\weekly.log
set PY=C:\Users\nL_ku\AppData\Local\Python\pythoncore-3.14-64\python.exe
set BASE=C:\Users\nL_ku\ngernduangold-site\pipeline
echo [%date% %time%] comply_gate_stitch scan (components\stitch) >> "%LOG%"
"%PY%" "%BASE%\..\tools\comply_gate_stitch.py" "%BASE%\..\components\stitch" >> "%LOG%" 2>&1
if errorlevel 1 echo [%date% %time%] !! comply_gate_stitch FAIL - fix components\stitch before deploy >> "%LOG%"
echo [%date% %time%] run_weekly start >> "%LOG%"
"%PY%" "%BASE%\ga4_pull.py" >> "%LOG%" 2>&1
"%PY%" "%BASE%\weekly_growth_review.py" >> "%LOG%" 2>&1
echo [%date% %time%] run_weekly end exit=%errorlevel% >> "%LOG%"
