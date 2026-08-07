@echo off
setlocal
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo Python environment is being created...
    py -3 -m venv .venv || python -m venv .venv
    if errorlevel 1 (
        echo.
        echo Python 3 could not be found. Please install Python 3 and try again.
        pause
        exit /b 1
    )
    echo Installing required packages...
    .venv\Scripts\python.exe -m pip install -r requirements.txt
    if errorlevel 1 (
        echo.
        echo Package installation failed. Please check your internet connection and try again.
        pause
        exit /b 1
    )
)

echo Starting Memo Garden...
start "" /b powershell -NoProfile -Command "Start-Sleep -Seconds 2; Start-Process 'http://127.0.0.1:5000'"
.venv\Scripts\python.exe memo_app\app.py

pause
