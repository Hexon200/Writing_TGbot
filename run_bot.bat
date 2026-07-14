@echo off
setlocal enabledelayedexpansion

cd /d %~dp0

:: Check if .env file exists, otherwise copy from example
if not exist .env (
    if exist .env.example (
        echo [WARNING] .env file not found. Copying from .env.example...
        copy .env.example .env
        echo [IMPORTANT] Please open .env and set your TELEGRAM_BOT_TOKEN before running the bot!
    ) else (
        echo [ERROR] Neither .env nor .env.example was found in this folder.
        pause
        exit /b 1
    )
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

echo [INFO] Starting Telegram Bot...
python -m app.bot

pause
