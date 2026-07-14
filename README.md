# IELTS Writing Helper

A Telegram Mini App content library for IELTS Writing reference material: Task 1 and Task 2 model answers, structural tips, a searchable phrase bank, bookmarks, inline phrase search, and an opt-in daily phrase push bot.

## Stack

- FastAPI
- SQLite
- Plain HTML/CSS/JS Telegram Mini App frontend
- Aiogram bot runner
- Editable JSON seed data in `content/seed.json`

## Quick Start

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python -m app.seed --reset
uvicorn app.main:app --reload
```

Open `http://127.0.0.1:8000` to test the Mini App in a browser. Telegram will use the same page as the Web App URL once it is exposed through HTTPS.

## Bot

Create `.env` from `.env.example`, set `TELEGRAM_BOT_TOKEN`, and run:

```powershell
python -m app.bot
```

Commands:

- `/random` sends a random phrase, sample, or tip.
- `/daily_on` enables daily phrase pushes for the Telegram user.
- `/daily_off` disables daily phrase pushes.
- Inline mode searches phrase-bank entries when users type `@yourbot comparing`.

Telegram inline mode must be enabled in BotFather.

## Content Editing

Edit `content/seed.json`, then run:

```powershell
python -m app.seed --reset
```

Highlight markup inside sample answers uses:

```text
[[phrase-slug|visible highlighted text]]
```

The backend resolves `phrase-slug` to a phrase-bank entry and sends structured text segments to the frontend. This keeps highlights content-driven instead of hardcoded in the UI.

## API

- `GET /api/samples?task=1&type=line_graph`
- `GET /api/samples/{id}`
- `GET /api/phrases?category=comparing_contrasting`
- `GET /api/phrases/{id}`
- `GET /api/tips`
- `GET /api/search?q=trend`
- `GET /api/bookmarks?telegram_user_id=123`
- `POST /api/bookmarks`
- `DELETE /api/bookmarks`

