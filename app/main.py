from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from app.content import phrase_from_row, sample_from_row, tip_from_row
from app.database import BASE_DIR, get_connection, init_db
from app.seed import ensure_seeded


FRONTEND_DIR = BASE_DIR / "frontend"


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    ensure_seeded()
    yield


app = FastAPI(title="IELTS Writing Helper", version="0.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")
app.mount("/assets", StaticFiles(directory=FRONTEND_DIR / "assets"), name="assets")


class BookmarkIn(BaseModel):
    telegram_user_id: str = Field(min_length=1)
    item_type: Literal["sample", "phrase", "tip"]
    item_id: int = Field(gt=0)


@app.get("/")
def index() -> FileResponse:
    return FileResponse(FRONTEND_DIR / "index.html")


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/samples")
def list_samples(
    task: int | None = Query(default=None, ge=1, le=2),
    sample_type: str | None = Query(default=None, alias="type"),
    band: int | None = Query(default=None, ge=1, le=9),
) -> dict[str, object]:
    query = "SELECT * FROM samples WHERE 1=1"
    params: list[object] = []
    if task is not None:
        query += " AND task_type = ?"
        params.append(task)
    if sample_type:
        query += " AND subtype = ?"
        params.append(sample_type)
    if band is not None:
        query += " AND band_score = ?"
        params.append(band)
    query += " ORDER BY task_type, subtype, title, band_score"
    with get_connection() as conn:
        rows = conn.execute(query, params).fetchall()
    return {"items": [sample_from_row(row) for row in rows]}


@app.get("/api/samples/{sample_id}")
def sample_detail(sample_id: int) -> dict[str, object]:
    with get_connection() as conn:
        row = conn.execute("SELECT * FROM samples WHERE id = ?", (sample_id,)).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="Sample not found")
        phrases = conn.execute("SELECT * FROM phrases").fetchall()
    phrase_map = {phrase["slug"]: phrase_from_row(phrase) for phrase in phrases}
    return sample_from_row(row, include_body=True, phrase_map=phrase_map)


@app.get("/api/phrases")
def list_phrases(category: str | None = None) -> dict[str, object]:
    query = "SELECT * FROM phrases"
    params: list[object] = []
    if category:
        query += " WHERE category = ?"
        params.append(category)
    query += " ORDER BY category, phrase"
    with get_connection() as conn:
        rows = conn.execute(query, params).fetchall()
    return {"items": [phrase_from_row(row) for row in rows]}


@app.get("/api/phrases/{phrase_id}")
def phrase_detail(phrase_id: int) -> dict[str, object]:
    with get_connection() as conn:
        row = conn.execute("SELECT * FROM phrases WHERE id = ?", (phrase_id,)).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Phrase not found")
    return phrase_from_row(row)


@app.get("/api/tips")
def list_tips(category: str | None = None) -> dict[str, object]:
    query = "SELECT * FROM tips"
    params: list[object] = []
    if category:
        query += " WHERE category = ?"
        params.append(category)
    query += " ORDER BY category, title"
    with get_connection() as conn:
        rows = conn.execute(query, params).fetchall()
    return {"items": [tip_from_row(row) for row in rows]}


@app.get("/api/search")
def search(q: str = Query(min_length=1), limit: int = Query(default=8, ge=1, le=25)) -> dict[str, object]:
    needle = f"%{q.lower()}%"
    with get_connection() as conn:
        sample_rows = conn.execute(
            """
            SELECT * FROM samples
            WHERE lower(title || ' ' || subtype || ' ' || prompt_text || ' ' || body_markup || ' ' || tags) LIKE ?
            ORDER BY task_type, subtype, band_score
            LIMIT ?
            """,
            (needle, limit),
        ).fetchall()
        phrase_rows = conn.execute(
            """
            SELECT * FROM phrases
            WHERE lower(category || ' ' || phrase || ' ' || example || ' ' || coalesce(band_note, '')) LIKE ?
            ORDER BY category, phrase
            LIMIT ?
            """,
            (needle, limit),
        ).fetchall()
        tip_rows = conn.execute(
            """
            SELECT * FROM tips
            WHERE lower(category || ' ' || title || ' ' || body || ' ' || coalesce(descriptor, '')) LIKE ?
            ORDER BY category, title
            LIMIT ?
            """,
            (needle, limit),
        ).fetchall()
    return {
        "samples": [sample_from_row(row) for row in sample_rows],
        "phrases": [phrase_from_row(row) for row in phrase_rows],
        "tips": [tip_from_row(row) for row in tip_rows],
    }


@app.get("/api/bookmarks")
def list_bookmarks(telegram_user_id: str = Query(min_length=1)) -> dict[str, object]:
    with get_connection() as conn:
        bookmark_rows = conn.execute(
            """
            SELECT item_type, item_id, created_at
            FROM bookmarks
            WHERE telegram_user_id = ?
            ORDER BY created_at DESC
            """,
            (telegram_user_id,),
        ).fetchall()

        items: list[dict[str, object]] = []
        for bookmark in bookmark_rows:
            item_type = bookmark["item_type"]
            item_id = bookmark["item_id"]
            table = {"sample": "samples", "phrase": "phrases", "tip": "tips"}[item_type]
            row = conn.execute(f"SELECT * FROM {table} WHERE id = ?", (item_id,)).fetchone()
            if row is None:
                continue
            if item_type == "sample":
                item = sample_from_row(row)
            elif item_type == "phrase":
                item = phrase_from_row(row)
            else:
                item = tip_from_row(row)
            items.append({"item_type": item_type, "created_at": bookmark["created_at"], "item": item})
    return {"items": items}


@app.post("/api/bookmarks", status_code=201)
def create_bookmark(bookmark: BookmarkIn) -> dict[str, object]:
    _assert_item_exists(bookmark.item_type, bookmark.item_id)
    with get_connection() as conn:
        conn.execute(
            """
            INSERT OR IGNORE INTO bookmarks (telegram_user_id, item_type, item_id)
            VALUES (?, ?, ?)
            """,
            (bookmark.telegram_user_id, bookmark.item_type, bookmark.item_id),
        )
    return {"ok": True}


@app.delete("/api/bookmarks")
def delete_bookmark(bookmark: BookmarkIn) -> dict[str, object]:
    with get_connection() as conn:
        conn.execute(
            """
            DELETE FROM bookmarks
            WHERE telegram_user_id = ? AND item_type = ? AND item_id = ?
            """,
            (bookmark.telegram_user_id, bookmark.item_type, bookmark.item_id),
        )
    return {"ok": True}


def _assert_item_exists(item_type: str, item_id: int) -> None:
    table = {"sample": "samples", "phrase": "phrases", "tip": "tips"}[item_type]
    with get_connection() as conn:
        row = conn.execute(f"SELECT id FROM {table} WHERE id = ?", (item_id,)).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail=f"{item_type.title()} not found")

