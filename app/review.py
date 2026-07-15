from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from sqlite3 import Connection, Row

from app.content import phrase_from_row


@dataclass(frozen=True)
class ReviewResult:
    interval: int
    repetition: int
    easiness_factor: float
    next_review_at: str


def now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


def apply_sm2(interval: int, repetition: int, easiness_factor: float, quality: int) -> ReviewResult:
    if quality < 0 or quality > 5:
        raise ValueError("quality must be between 0 and 5")

    old_interval = max(0, int(interval or 0))
    old_repetition = max(0, int(repetition or 0))
    old_easiness = float(easiness_factor or 2.5)
    new_easiness = max(1.3, old_easiness + (0.1 - (5 - quality) * (0.08 + (5 - quality) * 0.02)))

    if quality < 3:
        new_repetition = 0
        new_interval = 1
    else:
        new_repetition = old_repetition + 1
        if new_repetition == 1:
            new_interval = 1
        elif new_repetition == 2:
            new_interval = 6
        else:
            new_interval = max(1, round(max(1, old_interval) * new_easiness))

    next_review_at = (datetime.now(UTC).replace(microsecond=0) + timedelta(days=new_interval)).isoformat()
    return ReviewResult(
        interval=new_interval,
        repetition=new_repetition,
        easiness_factor=round(new_easiness, 3),
        next_review_at=next_review_at,
    )


def ensure_phrase_bookmark(conn: Connection, telegram_user_id: str, phrase_id: int) -> Row:
    phrase = conn.execute("SELECT id FROM phrases WHERE id = ?", (phrase_id,)).fetchone()
    if phrase is None:
        raise LookupError("Phrase not found")
    conn.execute(
        """
        INSERT OR IGNORE INTO bookmarks (telegram_user_id, item_type, item_id, next_review_at)
        VALUES (?, 'phrase', ?, CURRENT_TIMESTAMP)
        """,
        (telegram_user_id, phrase_id),
    )
    row = conn.execute(
        """
        SELECT *
        FROM bookmarks
        WHERE telegram_user_id = ? AND item_type = 'phrase' AND item_id = ?
        """,
        (telegram_user_id, phrase_id),
    ).fetchone()
    if row is None:
        raise LookupError("Bookmark not found")
    return row


def update_phrase_review(conn: Connection, telegram_user_id: str, phrase_id: int, quality: int) -> ReviewResult:
    bookmark = ensure_phrase_bookmark(conn, telegram_user_id, phrase_id)
    result = apply_sm2(
        interval=bookmark["interval"],
        repetition=bookmark["repetition"],
        easiness_factor=bookmark["easiness_factor"],
        quality=quality,
    )
    conn.execute(
        """
        UPDATE bookmarks
        SET interval = ?,
            repetition = ?,
            easiness_factor = ?,
            next_review_at = ?
        WHERE telegram_user_id = ? AND item_type = 'phrase' AND item_id = ?
        """,
        (
            result.interval,
            result.repetition,
            result.easiness_factor,
            result.next_review_at,
            telegram_user_id,
            phrase_id,
        ),
    )
    return result


def review_state_from_row(row: Row | None) -> dict[str, object]:
    if row is None:
        return {
            "interval": 0,
            "repetition": 0,
            "easiness_factor": 2.5,
            "next_review_at": now_iso(),
        }
    return {
        "interval": row["interval"],
        "repetition": row["repetition"],
        "easiness_factor": row["easiness_factor"],
        "next_review_at": row["next_review_at"],
    }


def quiz_payload(phrase: Row, bookmark: Row | None, *, is_new: bool, source: str, due_count: int, total_bookmarked: int) -> dict[str, object]:
    return {
        "phrase": phrase_from_row(phrase),
        "item_id": phrase["id"],
        "is_new": is_new,
        "source": source,
        "review": review_state_from_row(bookmark),
        "stats": {
            "due_count": due_count,
            "total_bookmarked": total_bookmarked,
            "reviewed_count": max(0, total_bookmarked - due_count),
        },
    }
