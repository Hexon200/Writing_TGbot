#!/bin/sh

# 1. Initialize or seed the database if it doesn't exist
# Since we use volume mount for the "data" directory, we verify if it exists.
# FastAPI lifespan will also call init_db() and ensure_seeded() automatically.

# 2. Run FastAPI in the foreground. Telegram updates are handled by FastAPI webhook mode.
echo "[INFO] Starting FastAPI Backend on port ${PORT:-8080}..."
export BOT_MODE=${BOT_MODE:-webhook}
exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8080}
