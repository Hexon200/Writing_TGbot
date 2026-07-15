from __future__ import annotations

import asyncio
import html
import os
import random
import re
from datetime import UTC, datetime

from aiogram import Bot, Dispatcher, F, Router
from aiogram.filters import Command
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    InlineQuery,
    InlineQueryResultArticle,
    InputTextMessageContent,
    Message,
    Update,
    WebAppInfo,
)
from dotenv import load_dotenv

from app.content import phrase_from_row, sample_from_row, strip_markup, tip_from_row
from app.database import get_connection, init_db
from app.review import update_phrase_review
from app.seed import ensure_seeded


load_dotenv()

router = Router()


def get_bot_token() -> str:
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        raise RuntimeError("Set TELEGRAM_BOT_TOKEN in .env or the environment.")
    return token


def build_bot() -> Bot:
    return Bot(token=get_bot_token())


def build_dispatcher() -> Dispatcher:
    dp = Dispatcher()
    dp.include_router(router)
    return dp


async def feed_webhook_update(bot: Bot, dispatcher: Dispatcher, data: dict[str, object]) -> None:
    update = Update.model_validate(data, context={"bot": bot})
    await dispatcher.feed_update(bot, update)


async def set_webhook(bot: Bot, webhook_url: str) -> None:
    secret_token = os.getenv("TELEGRAM_WEBHOOK_SECRET")
    kwargs = {"drop_pending_updates": True}
    if secret_token:
        kwargs["secret_token"] = secret_token
    await bot.set_webhook(webhook_url, **kwargs)


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


@router.message(Command("quiz"))
async def quiz_command(message: Message) -> None:
    poll = _build_quiz_poll()
    if poll is None:
        await message.answer("No phrases are available yet.")
        return
    await message.answer_poll(
        question=poll["question"],
        options=poll["options"],
        type="quiz",
        correct_option_id=poll["correct_option_id"],
        is_anonymous=False,
    )


@router.callback_query(F.data.startswith("review:"))
async def review_callback(callback: CallbackQuery) -> None:
    parts = (callback.data or "").split(":")
    if len(parts) != 3:
        await callback.answer("Invalid review action.", show_alert=True)
        return
    try:
        phrase_id = int(parts[1])
        quality = int(parts[2])
    except ValueError:
        await callback.answer("Invalid review action.", show_alert=True)
        return

    with get_connection() as conn:
        try:
            result = update_phrase_review(conn, str(callback.from_user.id), phrase_id, quality)
        except LookupError:
            await callback.answer("Phrase not found.", show_alert=True)
            return

    await callback.answer(f"Scheduled next review in {result.interval} days!", show_alert=True)
    if callback.message:
        try:
            await callback.message.edit_reply_markup(reply_markup=None)
        except Exception:
            pass


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
            today = now.date().isoformat()
            await _send_due_reviews(bot, today)
            await _send_due_daily_phrases(bot, today)
            await _send_daily_quiz_polls(bot, today)
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


async def _send_due_reviews(bot: Bot, today: str) -> None:
    with get_connection() as conn:
        users = conn.execute(
            """
            SELECT DISTINCT b.telegram_user_id
            FROM bookmarks b
            LEFT JOIN user_settings s ON s.telegram_user_id = b.telegram_user_id
            WHERE b.item_type = 'phrase'
              AND datetime(coalesce(b.next_review_at, CURRENT_TIMESTAMP)) <= datetime('now')
              AND coalesce(s.last_review_push_date, '') != ?
            """,
            (today,),
        ).fetchall()

    for user in users:
        user_id = user["telegram_user_id"]
        with get_connection() as conn:
            row = conn.execute(
                """
                SELECT p.*
                FROM bookmarks b
                JOIN phrases p ON p.id = b.item_id
                WHERE b.telegram_user_id = ?
                  AND b.item_type = 'phrase'
                  AND datetime(coalesce(b.next_review_at, CURRENT_TIMESTAMP)) <= datetime('now')
                ORDER BY datetime(coalesce(b.next_review_at, CURRENT_TIMESTAMP)), b.created_at
                LIMIT 1
                """,
                (user_id,),
            ).fetchone()
        if row is None:
            continue
        phrase = phrase_from_row(row)
        try:
            await bot.send_message(
                user_id,
                _format_review_prompt(phrase),
                parse_mode="HTML",
                reply_markup=_review_keyboard(phrase["id"]),
            )
        except Exception:
            continue
        with get_connection() as conn:
            conn.execute(
                """
                INSERT INTO user_settings (telegram_user_id, last_review_push_date, updated_at)
                VALUES (?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(telegram_user_id) DO UPDATE SET
                    last_review_push_date = excluded.last_review_push_date,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (user_id, today),
            )


async def _send_daily_quiz_polls(bot: Bot, today: str) -> None:
    with get_connection() as conn:
        users = conn.execute(
            """
            SELECT telegram_user_id
            FROM user_settings
            WHERE daily_phrase_enabled = 1
              AND coalesce(last_daily_quiz_date, '') != ?
            """,
            (today,),
        ).fetchall()

    for user in users:
        user_id = user["telegram_user_id"]
        poll = _build_quiz_poll()
        if poll is None:
            continue
        try:
            await bot.send_poll(
                chat_id=user_id,
                question=poll["question"],
                options=poll["options"],
                type="quiz",
                correct_option_id=poll["correct_option_id"],
                is_anonymous=False,
            )
        except Exception:
            continue
        with get_connection() as conn:
            conn.execute(
                """
                UPDATE user_settings
                SET last_daily_quiz_date = ?, updated_at = CURRENT_TIMESTAMP
                WHERE telegram_user_id = ?
                """,
                (today, user_id),
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


def _review_keyboard(phrase_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="🔴 Hard", callback_data=f"review:{phrase_id}:1"),
                InlineKeyboardButton(text="🟡 Good", callback_data=f"review:{phrase_id}:3"),
                InlineKeyboardButton(text="🟢 Easy", callback_data=f"review:{phrase_id}:5"),
            ]
        ]
    )


def _format_review_prompt(phrase: dict[str, object]) -> str:
    note = f"\n<i>{html.escape(str(phrase['band_note']))}</i>" if phrase.get("band_note") else ""
    return (
        "<b>Review phrase</b>\n"
        f"<b>{html.escape(str(phrase['phrase']))}</b>\n"
        f"{html.escape(str(phrase['example']))}"
        f"{note}"
    )


def _build_quiz_poll() -> dict[str, object] | None:
    with get_connection() as conn:
        phrase_rows = conn.execute("SELECT * FROM phrases ORDER BY RANDOM() LIMIT 12").fetchall()
        if len(phrase_rows) < 4:
            return None
        correct = phrase_from_row(phrase_rows[0])
        others = [phrase_from_row(row) for row in phrase_rows[1:]]

    if random.choice([True, False]):
        question = _blank_phrase_question(correct)
        distractors = [item["phrase"] for item in others if item["phrase"] != correct["phrase"]][:3]
        options = [correct["phrase"], *distractors]
    else:
        question = f"In which category does the phrase '{correct['phrase']}' belong?"
        correct_option = _label_for_category(str(correct["category"]))
        distractors = []
        for item in others:
            label = _label_for_category(str(item["category"]))
            if label != correct_option and label not in distractors:
                distractors.append(label)
            if len(distractors) == 3:
                break
        if len(distractors) < 3:
            question = _blank_phrase_question(correct)
            distractors = [item["phrase"] for item in others if item["phrase"] != correct["phrase"]][:3]
            options = [correct["phrase"], *distractors]
        else:
            options = [correct_option, *distractors]

    options = [str(option)[:100] for option in options[:4]]
    correct_text = options[0]
    random.shuffle(options)
    return {
        "question": question[:300],
        "options": options,
        "correct_option_id": options.index(correct_text),
    }


def _blank_phrase_question(phrase: dict[str, object]) -> str:
    text = str(phrase["phrase"])
    example = str(phrase["example"])
    blanked = re.sub(re.escape(text), "_____", example, count=1, flags=re.IGNORECASE)
    if blanked == example:
        blanked = example.replace(text.split()[0], "_____", 1)
    return f"Which phrase completes this sentence? {blanked}"


def _label_for_category(category: str) -> str:
    return category.replace("_", " ").capitalize()


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
    bot = build_bot()
    dp = build_dispatcher()

    # Local polling mode only. Do not run this process on Railway while webhook hosting is active.
    print("[INFO] Deleting existing webhook if any...")
    await bot.delete_webhook(drop_pending_updates=True)

    asyncio.create_task(daily_phrase_loop(bot))
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
