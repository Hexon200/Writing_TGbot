@echo off
setlocal enabledelayedexpansion

cd /d %~dp0

:: Check if Python is installed
where python >nul 2>nul
if %errorlevel% neq 0 (
    echo [ERROR] Python was not found on your PATH. Please install Python and try again.
    pause
    exit /b 1
)

:: Create virtual environment if it doesn't exist
if not exist .venv (
    echo [INFO] Creating Python virtual environment (.venv)...
    python -m venv .venv
    if !errorlevel! neq 0 (
        echo [ERROR] Failed to create virtual environment.
        pause
        exit /b 1
    )
)

:: Activate virtual environment and install requirements
echo [INFO] Activating virtual environment...
call .venv\Scripts\activate.bat

echo [INFO] Checking/Installing dependencies...
python -m pip install --upgrade pip
pip install -r requirements.txt
if !errorlevel! neq 0 (
    echo [ERROR] Failed to install dependencies.
    pause
    exit /b 1
)

:: Seed database if not already initialized
if not exist data\ielts_helper.sqlite3 (
    echo [INFO] Seeding database for the first time...
    python -m app.seed --reset
)

echo [INFO] Starting FastAPI Backend on http://127.0.0.1:8010...
uvicorn app.main:app --reload --port 8010

pause
