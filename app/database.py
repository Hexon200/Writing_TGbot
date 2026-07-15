from __future__ import annotations

import os
import sqlite3
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
DEFAULT_DB_PATH = DATA_DIR / "ielts_helper.sqlite3"
DB_PATH = Path(os.getenv("IELTS_DB_PATH", DEFAULT_DB_PATH))


SCHEMA = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS phrases (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    slug TEXT NOT NULL UNIQUE,
    category TEXT NOT NULL,
    phrase TEXT NOT NULL,
    example TEXT NOT NULL,
    band_note TEXT,
    related_slugs TEXT NOT NULL DEFAULT '[]',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_phrases_category ON phrases(category);
CREATE INDEX IF NOT EXISTS idx_phrases_slug ON phrases(slug);

CREATE TABLE IF NOT EXISTS samples (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    seed_key TEXT NOT NULL UNIQUE,
    task_type INTEGER NOT NULL CHECK (task_type IN (1, 2)),
    subtype TEXT NOT NULL,
    title TEXT NOT NULL,
    band_score INTEGER NOT NULL,
    prompt_text TEXT NOT NULL,
    prompt_image_url TEXT,
    body_markup TEXT NOT NULL,
    structure_breakdown TEXT NOT NULL DEFAULT '[]',
    tags TEXT NOT NULL DEFAULT '[]',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_samples_task_subtype ON samples(task_type, subtype);
CREATE INDEX IF NOT EXISTS idx_samples_band ON samples(band_score);

CREATE TABLE IF NOT EXISTS tips (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    seed_key TEXT NOT NULL UNIQUE,
    category TEXT NOT NULL,
    title TEXT NOT NULL,
    body TEXT NOT NULL,
    descriptor TEXT,
    tags TEXT NOT NULL DEFAULT '[]',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_tips_category ON tips(category);

CREATE TABLE IF NOT EXISTS bookmarks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    telegram_user_id TEXT NOT NULL,
    item_type TEXT NOT NULL CHECK (item_type IN ('sample', 'phrase', 'tip')),
    item_id INTEGER NOT NULL,
    interval INTEGER NOT NULL DEFAULT 0,
    repetition INTEGER NOT NULL DEFAULT 0,
    easiness_factor REAL NOT NULL DEFAULT 2.5,
    next_review_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (telegram_user_id, item_type, item_id)
);

CREATE INDEX IF NOT EXISTS idx_bookmarks_user ON bookmarks(telegram_user_id, created_at DESC);
CREATE TABLE IF NOT EXISTS user_settings (
    telegram_user_id TEXT PRIMARY KEY,
    daily_phrase_enabled INTEGER NOT NULL DEFAULT 0,
    last_daily_sent_date TEXT,
    last_daily_quiz_date TEXT,
    last_review_push_date TEXT,
    last_daily_phrase_id INTEGER,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS phrase_seen (
    telegram_user_id TEXT NOT NULL,
    phrase_id INTEGER NOT NULL,
    seen_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (telegram_user_id, phrase_id),
    FOREIGN KEY (phrase_id) REFERENCES phrases(id) ON DELETE CASCADE
);
"""


def get_connection() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db() -> None:
    with get_connection() as conn:
        conn.executescript(SCHEMA)
        _migrate_bookmarks(conn)


def _migrate_bookmarks(conn: sqlite3.Connection) -> None:
    columns = {row["name"] for row in conn.execute("PRAGMA table_info(bookmarks)").fetchall()}
    migrations = [
        ("interval", "ALTER TABLE bookmarks ADD COLUMN interval INTEGER NOT NULL DEFAULT 0"),
        ("repetition", "ALTER TABLE bookmarks ADD COLUMN repetition INTEGER NOT NULL DEFAULT 0"),
        ("easiness_factor", "ALTER TABLE bookmarks ADD COLUMN easiness_factor REAL NOT NULL DEFAULT 2.5"),
        ("next_review_at", "ALTER TABLE bookmarks ADD COLUMN next_review_at TEXT"),
    ]
    for column, statement in migrations:
        if column not in columns:
            conn.execute(statement)
    conn.execute(
        """
        UPDATE bookmarks
        SET next_review_at = CURRENT_TIMESTAMP
        WHERE next_review_at IS NULL OR next_review_at = ''
        """
    )
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_bookmarks_review_due
        ON bookmarks(telegram_user_id, item_type, next_review_at)
        """
    )
    _migrate_user_settings(conn)


def _migrate_user_settings(conn: sqlite3.Connection) -> None:
    columns = {row["name"] for row in conn.execute("PRAGMA table_info(user_settings)").fetchall()}
    migrations = [
        ("last_daily_quiz_date", "ALTER TABLE user_settings ADD COLUMN last_daily_quiz_date TEXT"),
        ("last_review_push_date", "ALTER TABLE user_settings ADD COLUMN last_review_push_date TEXT"),
    ]
    for column, statement in migrations:
        if column not in columns:
            conn.execute(statement)


def table_count(table_name: str) -> int:
    if table_name not in {"phrases", "samples", "tips", "bookmarks", "user_settings", "phrase_seen"}:
        raise ValueError(f"Unexpected table name: {table_name}")
    with get_connection() as conn:
        return int(conn.execute(f"SELECT COUNT(*) FROM {table_name}").fetchone()[0])
