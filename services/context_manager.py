"""SQLite-backed session context manager, scoped by Telegram chat_id.

Notes accumulate under a single active "topic thread" per chat. Starting a new
topic archives the previous one (its notes stay in the database but drop out
of `get_active_notes`), so a chat can hold several distillation-ready threads
over time without them bleeding into each other.
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Optional

import aiosqlite

SCHEMA = """
CREATE TABLE IF NOT EXISTS topics (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    chat_id INTEGER NOT NULL,
    title TEXT NOT NULL,
    created_at REAL NOT NULL,
    active INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS notes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    chat_id INTEGER NOT NULL,
    topic_id INTEGER NOT NULL,
    timestamp REAL NOT NULL,
    text TEXT NOT NULL,
    source TEXT NOT NULL,
    FOREIGN KEY (topic_id) REFERENCES topics (id)
);

CREATE INDEX IF NOT EXISTS idx_notes_topic ON notes (topic_id);
CREATE INDEX IF NOT EXISTS idx_topics_chat_active ON topics (chat_id, active);
"""


@dataclass
class Note:
    id: int
    chat_id: int
    topic_id: int
    timestamp: float
    text: str
    source: str


@dataclass
class Topic:
    id: int
    chat_id: int
    title: str
    created_at: float
    active: bool


class ContextManager:
    """Tracks per-chat topic threads and the notes accumulated under them."""

    def __init__(self, db_path: str):
        self._db_path = db_path
        self._db: Optional[aiosqlite.Connection] = None

    async def init(self) -> None:
        self._db = await aiosqlite.connect(self._db_path)
        await self._db.executescript(SCHEMA)
        await self._db.commit()

    async def close(self) -> None:
        if self._db is not None:
            await self._db.close()
            self._db = None

    async def _get_or_create_active_topic(self, chat_id: int) -> Topic:
        topic = await self.get_active_topic(chat_id)
        if topic is not None:
            return topic
        return await self.start_new_topic(chat_id, title="General")

    async def start_new_topic(self, chat_id: int, title: str) -> Topic:
        assert self._db is not None
        await self._db.execute(
            "UPDATE topics SET active = 0 WHERE chat_id = ? AND active = 1",
            (chat_id,),
        )
        now = time.time()
        cursor = await self._db.execute(
            "INSERT INTO topics (chat_id, title, created_at, active) VALUES (?, ?, ?, 1)",
            (chat_id, title, now),
        )
        await self._db.commit()
        return Topic(id=cursor.lastrowid, chat_id=chat_id, title=title, created_at=now, active=True)

    async def get_active_topic(self, chat_id: int) -> Optional[Topic]:
        assert self._db is not None
        cursor = await self._db.execute(
            "SELECT id, chat_id, title, created_at, active FROM topics "
            "WHERE chat_id = ? AND active = 1 ORDER BY id DESC LIMIT 1",
            (chat_id,),
        )
        row = await cursor.fetchone()
        if row is None:
            return None
        return Topic(id=row[0], chat_id=row[1], title=row[2], created_at=row[3], active=bool(row[4]))

    async def add_note(self, chat_id: int, text: str, source: str = "text") -> Note:
        assert self._db is not None
        topic = await self._get_or_create_active_topic(chat_id)
        now = time.time()
        cursor = await self._db.execute(
            "INSERT INTO notes (chat_id, topic_id, timestamp, text, source) VALUES (?, ?, ?, ?, ?)",
            (chat_id, topic.id, now, text, source),
        )
        await self._db.commit()
        return Note(id=cursor.lastrowid, chat_id=chat_id, topic_id=topic.id, timestamp=now, text=text, source=source)

    async def get_active_notes(self, chat_id: int) -> list[Note]:
        assert self._db is not None
        topic = await self.get_active_topic(chat_id)
        if topic is None:
            return []
        cursor = await self._db.execute(
            "SELECT id, chat_id, topic_id, timestamp, text, source FROM notes "
            "WHERE topic_id = ? ORDER BY timestamp ASC",
            (topic.id,),
        )
        rows = await cursor.fetchall()
        return [
            Note(id=r[0], chat_id=r[1], topic_id=r[2], timestamp=r[3], text=r[4], source=r[5])
            for r in rows
        ]

    async def get_status(self, chat_id: int) -> dict:
        topic = await self.get_active_topic(chat_id)
        if topic is None:
            return {"topic": None, "note_count": 0, "last_update": None}
        notes = await self.get_active_notes(chat_id)
        return {
            "topic": topic.title,
            "note_count": len(notes),
            "last_update": notes[-1].timestamp if notes else topic.created_at,
        }

    async def clear_active_topic(self, chat_id: int) -> int:
        assert self._db is not None
        topic = await self.get_active_topic(chat_id)
        if topic is None:
            return 0
        cursor = await self._db.execute("DELETE FROM notes WHERE topic_id = ?", (topic.id,))
        await self._db.commit()
        return cursor.rowcount
