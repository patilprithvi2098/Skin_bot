"""Postgres-backed (Supabase) session context manager, scoped by Telegram chat_id.

Notes accumulate under a single active "topic thread" per chat. Starting a new
topic archives the previous one (its notes stay in the database but drop out
of `get_active_notes`), so a chat can hold several distillation-ready threads
over time without them bleeding into each other.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Optional

import asyncpg

SCHEMA = """
CREATE TABLE IF NOT EXISTS topics (
    id BIGSERIAL PRIMARY KEY,
    chat_id BIGINT NOT NULL,
    title TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    active BOOLEAN NOT NULL DEFAULT true
);

CREATE TABLE IF NOT EXISTS notes (
    id BIGSERIAL PRIMARY KEY,
    chat_id BIGINT NOT NULL,
    topic_id BIGINT NOT NULL REFERENCES topics (id) ON DELETE CASCADE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    text TEXT NOT NULL,
    source TEXT NOT NULL CHECK (source IN ('text', 'voice'))
);

CREATE UNIQUE INDEX IF NOT EXISTS topics_one_active_per_chat ON topics (chat_id) WHERE active;
CREATE INDEX IF NOT EXISTS notes_topic_id_idx ON notes (topic_id, id);

ALTER TABLE topics ENABLE ROW LEVEL SECURITY;
ALTER TABLE notes ENABLE ROW LEVEL SECURITY;
"""

_TOPIC_COLUMNS = "id, chat_id, title, created_at, active"
_NOTE_COLUMNS = "id, chat_id, topic_id, created_at, text, source"

# Schema DDL only needs to run once per process, not on every webhook request.
_schema_ready = False


@dataclass
class Note:
    id: int
    chat_id: int
    topic_id: int
    created_at: datetime
    text: str
    source: str


@dataclass
class Topic:
    id: int
    chat_id: int
    title: str
    created_at: datetime
    active: bool


class ContextManager:
    """Tracks per-chat topic threads and the notes accumulated under them."""

    def __init__(self, database_url: str):
        self._database_url = database_url
        self._conn: Optional[asyncpg.Connection] = None

    async def init(self) -> None:
        global _schema_ready
        # Supabase's transaction pooler can't hold prepared statements across transactions.
        self._conn = await asyncpg.connect(self._database_url, statement_cache_size=0)
        if not _schema_ready:
            await self._conn.execute(SCHEMA)
            _schema_ready = True

    async def close(self) -> None:
        if self._conn is not None:
            await self._conn.close()
            self._conn = None

    @property
    def _db(self) -> asyncpg.Connection:
        assert self._conn is not None, "ContextManager.init() was not called"
        return self._conn

    async def _get_or_create_active_topic(self, chat_id: int) -> Topic:
        # ON CONFLICT makes this safe when two updates for a new chat arrive at once.
        await self._db.execute(
            "INSERT INTO topics (chat_id, title) VALUES ($1, 'General') "
            "ON CONFLICT (chat_id) WHERE active DO NOTHING",
            chat_id,
        )
        topic = await self.get_active_topic(chat_id)
        assert topic is not None
        return topic

    async def start_new_topic(self, chat_id: int, title: str) -> Topic:
        async with self._db.transaction():
            await self._db.execute("UPDATE topics SET active = false WHERE chat_id = $1 AND active", chat_id)
            row = await self._db.fetchrow(
                f"INSERT INTO topics (chat_id, title) VALUES ($1, $2) RETURNING {_TOPIC_COLUMNS}",
                chat_id,
                title,
            )
        return Topic(**dict(row))

    async def get_active_topic(self, chat_id: int) -> Optional[Topic]:
        row = await self._db.fetchrow(
            f"SELECT {_TOPIC_COLUMNS} FROM topics WHERE chat_id = $1 AND active",
            chat_id,
        )
        return Topic(**dict(row)) if row else None

    async def add_note(self, chat_id: int, text: str, source: str = "text") -> Note:
        topic = await self._get_or_create_active_topic(chat_id)
        row = await self._db.fetchrow(
            f"INSERT INTO notes (chat_id, topic_id, text, source) VALUES ($1, $2, $3, $4) RETURNING {_NOTE_COLUMNS}",
            chat_id,
            topic.id,
            text,
            source,
        )
        return Note(**dict(row))

    async def get_active_notes(self, chat_id: int) -> list[Note]:
        rows = await self._db.fetch(
            f"SELECT {', '.join('n.' + c for c in _NOTE_COLUMNS.split(', '))} "
            "FROM notes n JOIN topics t ON t.id = n.topic_id "
            "WHERE t.chat_id = $1 AND t.active ORDER BY n.id",
            chat_id,
        )
        return [Note(**dict(r)) for r in rows]

    async def get_status(self, chat_id: int) -> dict:
        topic = await self.get_active_topic(chat_id)
        if topic is None:
            return {"topic": None, "note_count": 0, "last_update": None}
        notes = await self.get_active_notes(chat_id)
        return {
            "topic": topic.title,
            "note_count": len(notes),
            "last_update": notes[-1].created_at if notes else topic.created_at,
        }

    async def clear_active_topic(self, chat_id: int) -> int:
        topic = await self.get_active_topic(chat_id)
        if topic is None:
            return 0
        status = await self._db.execute("DELETE FROM notes WHERE topic_id = $1", topic.id)
        return int(status.split()[-1])
