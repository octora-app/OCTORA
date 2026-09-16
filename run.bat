@echo off
REM OCTORA - Windows launcher (Rouqil Tech)
title OCTORA
cd /d "%~dp0"

where python >nul 2>nul
if errorlevel 1 (
    echo [OCTORA] ERROR: Python not found.
    echo [OCTORA] Install Python 3.10+ from https://www.python.org/downloads/
    echo [OCTORA] IMPORTANT: tick "Add python.exe to PATH" during install.
    echo.
    pause
    exit /b 1
)

if not exist ".venv\Scripts\python.exe" (
    if exist ".venv" rmdir /s /q ".venv"
    echo [OCTORA] First run: creating virtual environment...
    python -m venv .venv
    if errorlevel 1 (
        echo [OCTORA] ERROR: could not create the virtual environment.
        echo.
        pause
        exit /b 1
    )
    call ".venv\Scripts\activate.bat"
    echo [OCTORA] Installing dependencies (one-time, needs internet)...
    python -m pip install --upgrade pip >nul 2>&1
    pip install -r requirements.txt
    if errorlevel 1 (
        echo [OCTORA] ERROR: dependency install failed.
        echo [OCTORA] Check your internet connection and run this file again.
        echo.
        pause
        exit /b 1
    )
) else (
    call ".venv\Scripts\activate.bat"
)

echo [OCTORA] Launching...
python main.py
if errorlevel 1 (
    echo.
    echo [OCTORA] The app exited with an error - see the message above.
    echo [OCTORA] Support: https://octora.pages.dev
    echo.
)
pause
