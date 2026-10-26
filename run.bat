@echo off
cd /d "%~dp0"
title Document Translator - Gemini Flash

if not exist ".venv\Scripts\python.exe" (
    echo [SETUP] Creating isolated virtual environment...
    python -m venv .venv
    echo [SETUP] Installing dependencies...
    .venv\Scripts\python.exe -m pip install --upgrade pip
    .venv\Scripts\pip.exe install -r requirements.txt
)

echo [START] Launching Document Translator...
.venv\Scripts\python.exe gui.py

if %errorlevel% neq 0 (
    echo.
    echo [ERROR] The program exited with error code %errorlevel%.
    pause
)
