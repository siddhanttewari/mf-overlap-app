@echo off
setlocal
title MF Overlap App
cd /d "%~dp0"

echo ============================================================
echo   MF Overlap App - Starting up
echo ============================================================
echo.

REM Step 1: check Python is installed
python --version >nul 2>&1
if errorlevel 1 goto NOPYTHON

REM Step 2: check Flask is installed; if yes, skip to running
python -c "import flask" >nul 2>&1
if not errorlevel 1 goto RUNSERVER

REM Step 3: first-time install of dependencies
echo Installing dependencies (first time only, takes ~30 seconds)...
echo.
python -m pip install --quiet -r requirements.txt
if errorlevel 1 goto PIPFAIL
echo Dependencies installed.
echo.

:RUNSERVER
echo Starting server. Your browser will open in a few seconds...
echo.
start "" cmd /c "ping 127.0.0.1 -n 4 >nul & start chrome http://localhost:5000"
python app.py
echo.
echo Server stopped.
pause
exit /b 0

:NOPYTHON
echo [ERROR] Python is not installed or not on PATH.
echo Please reinstall Python 3.11+ from the Microsoft Store.
echo.
pause
exit /b 1

:PIPFAIL
echo.
echo [ERROR] Could not install dependencies.
echo Try this command manually in this terminal:
echo     python -m pip install -r requirements.txt
echo.
pause
exit /b 1
