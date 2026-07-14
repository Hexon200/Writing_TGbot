from __future__ import annotations

import argparse
import json
from pathlib import Path

from app.database import BASE_DIR, get_connection, init_db, table_count


SEED_PATH = BASE_DIR / "content" / "seed.json"


def _json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False)


def reset_content_tables() -> None:
    with get_connection() as conn:
        conn.execute("DELETE FROM bookmarks")
        conn.execute("DELETE FROM phrase_seen")
        conn.execute("DELETE FROM user_settings")
        conn.execute("DELETE FROM samples")
        conn.execute("DELETE FROM tips")
        conn.execute("DELETE FROM phrases")
        conn.execute(
            """
            DELETE FROM sqlite_sequence
            WHERE name IN ('bookmarks', 'samples', 'tips', 'phrases')
            """
        )


def load_seed(seed_path: Path = SEED_PATH, reset: bool = False) -> None:
    init_db()
    if reset:
        reset_content_tables()

    data = json.loads(seed_path.read_text(encoding="utf-8"))

    with get_connection() as conn:
        for phrase in data.get("phrases", []):
            conn.execute(
                """
                INSERT INTO phrases (slug, category, phrase, example, band_note, related_slugs, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(slug) DO UPDATE SET
                    category = excluded.category,
                    phrase = excluded.phrase,
                    example = excluded.example,
                    band_note = excluded.band_note,
                    related_slugs = excluded.related_slugs,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (
                    phrase["slug"],
                    phrase["category"],
                    phrase["phrase"],
                    phrase["example"],
                    phrase.get("band_note"),
                    _json(phrase.get("related_slugs", [])),
                ),
            )

        for sample in data.get("samples", []):
            conn.execute(
                """
                INSERT INTO samples (
                    seed_key, task_type, subtype, title, band_score, prompt_text,
                    prompt_image_url, body_markup, structure_breakdown, tags, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(seed_key) DO UPDATE SET
                    task_type = excluded.task_type,
                    subtype = excluded.subtype,
                    title = excluded.title,
                    band_score = excluded.band_score,
                    prompt_text = excluded.prompt_text,
                    prompt_image_url = excluded.prompt_image_url,
                    body_markup = excluded.body_markup,
                    structure_breakdown = excluded.structure_breakdown,
                    tags = excluded.tags,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (
                    sample["seed_key"],
                    sample["task_type"],
                    sample["subtype"],
                    sample["title"],
                    sample["band_score"],
                    sample["prompt_text"],
                    sample.get("prompt_image_url"),
                    sample["body_markup"],
                    _json(sample.get("structure_breakdown", [])),
                    _json(sample.get("tags", [])),
                ),
            )

        for tip in data.get("tips", []):
            conn.execute(
                """
                INSERT INTO tips (seed_key, category, title, body, descriptor, tags, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(seed_key) DO UPDATE SET
                    category = excluded.category,
                    title = excluded.title,
                    body = excluded.body,
                    descriptor = excluded.descriptor,
                    tags = excluded.tags,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (
                    tip["seed_key"],
                    tip["category"],
                    tip["title"],
                    tip["body"],
                    tip.get("descriptor"),
                    _json(tip.get("tags", [])),
                ),
            )


def ensure_seeded() -> None:
    init_db()
    if table_count("phrases") == 0 and table_count("samples") == 0 and SEED_PATH.exists():
        load_seed(SEED_PATH)


def main() -> None:
    parser = argparse.ArgumentParser(description="Load IELTS Writing Helper seed content.")
    parser.add_argument("--reset", action="store_true", help="Clear seeded content and user data before loading.")
    parser.add_argument("--seed", default=str(SEED_PATH), help="Path to seed JSON.")
    args = parser.parse_args()
    load_seed(Path(args.seed), reset=args.reset)
    print("Seed content loaded.")


if __name__ == "__main__":
    main()
