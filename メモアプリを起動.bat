@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"

set "PYTHON_CMD="
py -3.11 -c "import sys" >nul 2>&1
if not errorlevel 1 set "PYTHON_CMD=py -3.11"
if not defined PYTHON_CMD (
    python -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)" >nul 2>&1
    if not errorlevel 1 set "PYTHON_CMD=python"
)
if not defined PYTHON_CMD (
    echo [ERROR] Python 3.10 or later was not found.
    echo Python 3.11 is recommended: https://www.python.org/downloads/
    echo During installation, select "Add Python to PATH".
    pause
    exit /b 1
)

if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" -c "import sys,flask; raise SystemExit(0 if sys.version_info >= (3,10) else 1)" >nul 2>&1
    if errorlevel 1 (
        echo Rebuilding an incompatible virtual environment...
        rmdir /s /q ".venv"
    )
)

if not exist ".venv\Scripts\python.exe" (
    echo Creating the Python environment...
    %PYTHON_CMD% -m venv .venv
    if errorlevel 1 goto setup_error
    echo Installing required packages...
    ".venv\Scripts\python.exe" -m pip install --upgrade pip
    if errorlevel 1 goto setup_error
    ".venv\Scripts\python.exe" -m pip install -r requirements.txt
    if errorlevel 1 goto setup_error
)

powershell -NoProfile -Command "$listener=Get-NetTCPConnection -LocalPort 5001 -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1; if ($listener) { $p=Get-CimInstance Win32_Process -Filter ('ProcessId=' + $listener.OwningProcess) -ErrorAction SilentlyContinue; if ($p -and $p.Name -like 'python*' -and $p.CommandLine -like '*memo_app*app.py*') { Stop-Process -Id $p.ProcessId -Force; Start-Sleep -Milliseconds 500; exit 0 }; exit 1 }; exit 0" >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Port 5001 is being used by another application.
    pause
    exit /b 1
)
if exist "memo-garden.pid" del /q "memo-garden.pid" >nul 2>&1

echo Starting Memo Garden...
set "MEMO_GARDEN_DEBUG=0"
powershell -NoProfile -Command "$p=Start-Process -FilePath '%CD%\.venv\Scripts\python.exe' -ArgumentList 'memo_app\app.py' -WorkingDirectory '%CD%' -WindowStyle Hidden -RedirectStandardOutput '%CD%\memo-app.log' -RedirectStandardError '%CD%\memo-app-error.log' -PassThru; Set-Content -LiteralPath '%CD%\memo-garden.pid' -Value $p.Id -Encoding ascii"
if errorlevel 1 goto start_error
powershell -NoProfile -Command "$deadline=(Get-Date).AddSeconds(30); do { try { $r=Invoke-WebRequest -UseBasicParsing -TimeoutSec 2 'http://127.0.0.1:5001/'; if ($r.StatusCode -eq 200) { Start-Process 'http://127.0.0.1:5001/'; exit 0 } } catch {}; Start-Sleep -Milliseconds 500 } while ((Get-Date) -lt $deadline); exit 1" >nul 2>&1
if errorlevel 1 goto start_error
exit /b

:setup_error
echo [ERROR] Setup failed. Check the internet connection and message above.
pause
exit /b 1

:start_error
echo [ERROR] Memo Garden did not start within 30 seconds.
if exist "memo-app-error.log" type "memo-app-error.log"
pause
exit /b 1
