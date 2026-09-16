@echo off
REM OCTORA v1.0 - Windows launcher ("Automate Beyond Limits" by Rouqil Tech)
title OCTORA
cd /d "%~dp0"

where python >nul 2>nul
if errorlevel 1 (
    echo [OCTORA] Python not found! Install Python 3.10+ from https://www.python.org/downloads/
    echo          IMPORTANT: tick "Add python.exe to PATH" during install.
    pause
    exit /b 1
)

if not exist ".venv" (
    echo [OCTORA] First run: creating virtual environment...
    python -m venv .venv
    call .venv\Scripts\activate.bat
    echo [OCTORA] Installing dependencies (one-time, needs internet)...
    python -m pip install --upgrade pip
    pip install -r requirements.txt
) else (
    call .venv\Scripts\activate.bat
)

echo [OCTORA] Launching...
python main.py
pause
