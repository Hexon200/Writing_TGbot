from __future__ import annotations

import json
import re
from sqlite3 import Row
from typing import Any


MARKUP_RE = re.compile(r"\[\[([a-z0-9-]+)\|([^\]]+)\]\]")


def load_json(value: str | None, fallback: Any) -> Any:
    if not value:
        return fallback
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return fallback


def strip_markup(markup: str) -> str:
    return MARKUP_RE.sub(lambda match: match.group(2), markup)


def phrase_from_row(row: Row) -> dict[str, Any]:
    return {
        "id": row["id"],
        "slug": row["slug"],
        "category": row["category"],
        "phrase": row["phrase"],
        "example": row["example"],
        "band_note": row["band_note"],
        "related_slugs": load_json(row["related_slugs"], []),
    }


def sample_from_row(row: Row, include_body: bool = False, phrase_map: dict[str, dict[str, Any]] | None = None) -> dict[str, Any]:
    sample = {
        "id": row["id"],
        "task_type": row["task_type"],
        "subtype": row["subtype"],
        "title": row["title"],
        "band_score": row["band_score"],
        "prompt_text": row["prompt_text"],
        "prompt_image_url": row["prompt_image_url"],
        "structure_breakdown": load_json(row["structure_breakdown"], []),
        "tags": load_json(row["tags"], []),
    }
    plain_body = strip_markup(row["body_markup"])
    sample["preview"] = plain_body[:220] + ("..." if len(plain_body) > 220 else "")
    if include_body:
        sample["body_text"] = plain_body
        sample["body_markup"] = row["body_markup"]
        sample["body_segments"] = body_segments(row["body_markup"], phrase_map or {})
    return sample


def tip_from_row(row: Row) -> dict[str, Any]:
    return {
        "id": row["id"],
        "category": row["category"],
        "title": row["title"],
        "body": row["body"],
        "descriptor": row["descriptor"],
        "tags": load_json(row["tags"], []),
    }


def body_segments(markup: str, phrase_map: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    segments: list[dict[str, Any]] = []
    cursor = 0
    for match in MARKUP_RE.finditer(markup):
        if match.start() > cursor:
            segments.append({"type": "text", "text": markup[cursor:match.start()]})
        slug = match.group(1)
        text = match.group(2)
        phrase = phrase_map.get(slug)
        segments.append(
            {
                "type": "phrase",
                "text": text,
                "phrase_slug": slug,
                "phrase_id": phrase["id"] if phrase else None,
                "phrase": phrase,
            }
        )
        cursor = match.end()
    if cursor < len(markup):
        segments.append({"type": "text", "text": markup[cursor:]})
    return segments

