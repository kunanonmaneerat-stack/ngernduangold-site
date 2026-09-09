@echo off
setlocal EnableExtensions DisableDelayedExpansion

REM Resolve one Python runtime that can execute every scheduled media guard.
REM The launcher is intentionally the stable executable recorded by
REM task_run_receipt.py; the selected interpreter is accepted only after an
REM actual import preflight.  A missing dependency is a runner failure, never a
REM media FAIL/PASS verdict.
set "RUNTIME_RC=86"
set "SELECTED_PY="
set "REPO_ROOT=%~dp0.."

if defined NGERNDUANGOLD_PYTHON call :probe "%NGERNDUANGOLD_PYTHON%"
if defined SELECTED_PY goto :run
if /I "%NGERNDUANGOLD_PYTHON_STRICT%"=="1" goto :missing

call :probe "%REPO_ROOT%\.venv\Scripts\python.exe"
if defined SELECTED_PY goto :run
call :probe "%REPO_ROOT%\venv\Scripts\python.exe"
if defined SELECTED_PY goto :run
if defined CODEX_WORKSPACE_PYTHON call :probe "%CODEX_WORKSPACE_PYTHON%"
if defined SELECTED_PY goto :run
call :probe "%USERPROFILE%\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
if defined SELECTED_PY goto :run
call :probe "%LOCALAPPDATA%\Python\pythoncore-3.14-64\python.exe"
if defined SELECTED_PY goto :run

for %%P in ("%LOCALAPPDATA%\Python\*\python.exe") do if not defined SELECTED_PY call :probe "%%~fP"
if defined SELECTED_PY goto :run
for /f "usebackq delims=" %%P in (`where.exe python.exe 2^>nul`) do if not defined SELECTED_PY call :probe "%%~fP"
if defined SELECTED_PY goto :run

:missing
>&2 echo [runtime] RUNNER_FAILED: no Python runtime imports numpy, cv2, PIL, and cryptography
exit /b %RUNTIME_RC%

:probe
if defined SELECTED_PY exit /b 0
if "%~1"=="" exit /b 0
if not exist "%~1" exit /b 0
"%~1" -c "import sys, numpy, cv2, PIL, cryptography; assert sys.version_info >= (3, 11); assert sys.maxsize > 2**32; assert numpy.__version__ and cv2.__version__ and PIL.__version__ and cryptography.__version__" >nul 2>&1
if errorlevel 1 exit /b 0
set "SELECTED_PY=%~f1"
exit /b 0

:run
"%SELECTED_PY%" %*
exit /b %errorlevel%
