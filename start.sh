#!/bin/sh

# 1. Initialize or seed the database if it doesn't exist
# Since we use volume mount for the "data" directory, we verify if it exists.
# FastAPI lifespan will also call init_db() and ensure_seeded() automatically.

# 2. Start the FastAPI backend server in the background
echo "[INFO] Starting FastAPI Backend on port ${PORT:-8010}..."
uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8010} &

# 3. Start the Telegram Bot in the foreground
echo "[INFO] Starting Telegram Bot..."
python -m app.bot
