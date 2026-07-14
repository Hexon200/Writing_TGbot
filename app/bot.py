from __future__ import annotations

import asyncio
import html
import os
import random
from datetime import UTC, datetime

from aiogram import Bot, Dispatcher, F, Router
from aiogram.filters import Command
from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    InlineQuery,
    InlineQueryResultArticle,
    InputTextMessageContent,
    Message,
    WebAppInfo,
)
from dotenv import load_dotenv

from app.content import phrase_from_row, sample_from_row, strip_markup, tip_from_row
from app.database import get_connection, init_db
from app.seed import ensure_seeded


load_dotenv()

router = Router()


def _webapp_keyboard() -> InlineKeyboardMarkup | None:
    webapp_url = os.getenv("WEBAPP_URL")
    if not webapp_url:
        return None
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Open library", web_app=WebAppInfo(url=webapp_url))]
        ]
    )


@router.message(Command("start"))
async def start(message: Message) -> None:
    await message.answer(
        "IELTS Writing Helper is ready. Use /random for a quick reference, /daily_on for one phrase per day, or open the library.",
        reply_markup=_webapp_keyboard(),
    )


@router.message(Command("daily_on"))
async def daily_on(message: Message) -> None:
    user_id = str(message.from_user.id)
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO user_settings (telegram_user_id, daily_phrase_enabled, updated_at)
            VALUES (?, 1, CURRENT_TIMESTAMP)
            ON CONFLICT(telegram_user_id) DO UPDATE SET
                daily_phrase_enabled = 1,
                updated_at = CURRENT_TIMESTAMP
            """,
            (user_id,),
        )
    await message.answer("Daily phrase push is on.")


@router.message(Command("daily_off"))
async def daily_off(message: Message) -> None:
    user_id = str(message.from_user.id)
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO user_settings (telegram_user_id, daily_phrase_enabled, updated_at)
            VALUES (?, 0, CURRENT_TIMESTAMP)
            ON CONFLICT(telegram_user_id) DO UPDATE SET
                daily_phrase_enabled = 0,
                updated_at = CURRENT_TIMESTAMP
            """,
            (user_id,),
        )
    await message.answer("Daily phrase push is off.")


@router.message(Command("random"))
async def random_reference(message: Message) -> None:
    choice = random.choice(["phrase", "sample", "tip"])
    with get_connection() as conn:
        if choice == "phrase":
            row = conn.execute("SELECT * FROM phrases ORDER BY RANDOM() LIMIT 1").fetchone()
            phrase = phrase_from_row(row)
            text = _format_phrase(phrase)
        elif choice == "sample":
            row = conn.execute("SELECT * FROM samples ORDER BY RANDOM() LIMIT 1").fetchone()
            sample = sample_from_row(row, include_body=True)
            text = (
                f"<b>{html.escape(sample['title'])}</b>\n"
                f"Task {sample['task_type']} · Band {sample['band_score']}\n\n"
                f"{html.escape(sample['preview'])}"
            )
        else:
            row = conn.execute("SELECT * FROM tips ORDER BY RANDOM() LIMIT 1").fetchone()
            tip = tip_from_row(row)
            text = f"<b>{html.escape(tip['title'])}</b>\n{html.escape(tip['body'])}"
    await message.answer(text, parse_mode="HTML", reply_markup=_webapp_keyboard())


@router.inline_query()
async def inline_phrase_search(inline_query: InlineQuery) -> None:
    query = inline_query.query.strip().lower()
    if not query:
        query = "overall"
    needle = f"%{query}%"
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT * FROM phrases
            WHERE lower(category || ' ' || phrase || ' ' || example || ' ' || coalesce(band_note, '')) LIKE ?
            ORDER BY category, phrase
            LIMIT 20
            """,
            (needle,),
        ).fetchall()
    results = []
    for row in rows:
        phrase = phrase_from_row(row)
        body = _format_phrase(phrase, plain=True)
        results.append(
            InlineQueryResultArticle(
                id=f"phrase-{phrase['id']}",
                title=phrase["phrase"],
                description=phrase["example"],
                input_message_content=InputTextMessageContent(message_text=body),
            )
        )
    await inline_query.answer(results, cache_time=30, is_personal=True)


async def daily_phrase_loop(bot: Bot) -> None:
    hour = int(os.getenv("DAILY_PHRASE_HOUR_UTC", "6"))
    while True:
        now = datetime.now(UTC)
        if now.hour == hour:
            await _send_due_daily_phrases(bot, now.date().isoformat())
        await asyncio.sleep(60)


async def _send_due_daily_phrases(bot: Bot, today: str) -> None:
    with get_connection() as conn:
        users = conn.execute(
            """
            SELECT telegram_user_id
            FROM user_settings
            WHERE daily_phrase_enabled = 1
              AND coalesce(last_daily_sent_date, '') != ?
            """,
            (today,),
        ).fetchall()

    for user in users:
        user_id = user["telegram_user_id"]
        phrase = _select_daily_phrase(user_id)
        if phrase is None:
            continue
        try:
            await bot.send_message(user_id, _format_phrase(phrase), parse_mode="HTML", reply_markup=_webapp_keyboard())
        except Exception:
            continue
        with get_connection() as conn:
            conn.execute(
                """
                INSERT OR IGNORE INTO phrase_seen (telegram_user_id, phrase_id)
                VALUES (?, ?)
                """,
                (user_id, phrase["id"]),
            )
            conn.execute(
                """
                UPDATE user_settings
                SET last_daily_sent_date = ?, last_daily_phrase_id = ?, updated_at = CURRENT_TIMESTAMP
                WHERE telegram_user_id = ?
                """,
                (today, phrase["id"], user_id),
            )


def _select_daily_phrase(user_id: str) -> dict[str, object] | None:
    with get_connection() as conn:
        row = conn.execute(
            """
            SELECT p.*
            FROM phrases p
            LEFT JOIN phrase_seen s
              ON s.phrase_id = p.id AND s.telegram_user_id = ?
            WHERE s.phrase_id IS NULL
            ORDER BY RANDOM()
            LIMIT 1
            """,
            (user_id,),
        ).fetchone()
        if row is None:
            row = conn.execute("SELECT * FROM phrases ORDER BY RANDOM() LIMIT 1").fetchone()
    return phrase_from_row(row) if row else None


def _format_phrase(phrase: dict[str, object], plain: bool = False) -> str:
    if plain:
        note = f"\nNote: {phrase['band_note']}" if phrase.get("band_note") else ""
        return f"{phrase['phrase']}\n{phrase['example']}{note}"
    note_html = f"\n<i>{html.escape(str(phrase['band_note']))}</i>" if phrase.get("band_note") else ""
    return (
        f"<b>{html.escape(str(phrase['phrase']))}</b>\n"
        f"{html.escape(str(phrase['example']))}"
        f"{note_html}"
    )


async def main() -> None:
    init_db()
    ensure_seeded()
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        raise RuntimeError("Set TELEGRAM_BOT_TOKEN in .env or the environment.")
    bot = Bot(token=token)
    dp = Dispatcher()
    dp.include_router(router)
    asyncio.create_task(daily_phrase_loop(bot))
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())

