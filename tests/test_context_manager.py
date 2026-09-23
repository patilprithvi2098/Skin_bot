"""Integration tests against a real Postgres (Supabase) database.

Uses TEST_DATABASE_URL, falling back to DATABASE_URL from .env. Each test works
on fresh random chat_ids and deletes them afterwards, so it is safe to point at
the bot's own database. Skipped when no database URL is configured.
"""
import os
import random

import pytest
import pytest_asyncio
from dotenv import load_dotenv

from services.context_manager import ContextManager

load_dotenv()
DATABASE_URL = os.environ.get("TEST_DATABASE_URL") or os.environ.get("DATABASE_URL")

pytestmark = pytest.mark.skipif(not DATABASE_URL, reason="No TEST_DATABASE_URL / DATABASE_URL configured")


@pytest_asyncio.fixture
async def manager():
    cm = ContextManager(DATABASE_URL)
    await cm.init()
    cm.test_chat_ids = []
    yield cm
    if cm.test_chat_ids:
        await cm._db.execute("DELETE FROM topics WHERE chat_id = ANY($1::bigint[])", cm.test_chat_ids)
    await cm.close()


@pytest.fixture
def new_chat(manager):
    def make() -> int:
        chat_id = -random.randint(10**12, 10**13)
        manager.test_chat_ids.append(chat_id)
        return chat_id

    return make


async def test_add_note_creates_default_topic(manager, new_chat):
    chat = new_chat()
    note = await manager.add_note(chat_id=chat, text="First observation")
    assert note.text == "First observation"
    topic = await manager.get_active_topic(chat_id=chat)
    assert topic is not None
    assert topic.title == "General"


async def test_notes_accumulate_under_active_topic(manager, new_chat):
    chat = new_chat()
    await manager.add_note(chat, "note one")
    await manager.add_note(chat, "note two", source="voice")
    notes = await manager.get_active_notes(chat)
    assert [(n.text, n.source) for n in notes] == [("note one", "text"), ("note two", "voice")]


async def test_newtopic_archives_previous_topic(manager, new_chat):
    chat = new_chat()
    await manager.add_note(chat, "under first topic")
    await manager.start_new_topic(chat, "Second Topic")
    await manager.add_note(chat, "under second topic")
    notes = await manager.get_active_notes(chat)
    assert [n.text for n in notes] == ["under second topic"]
    assert (await manager.get_active_topic(chat)).title == "Second Topic"


async def test_status_reports_topic_and_count(manager, new_chat):
    chat = new_chat()
    await manager.add_note(chat, "a")
    await manager.add_note(chat, "b")
    status = await manager.get_status(chat)
    assert status["topic"] == "General"
    assert status["note_count"] == 2


async def test_status_with_no_topic_yet(manager, new_chat):
    status = await manager.get_status(new_chat())
    assert status == {"topic": None, "note_count": 0, "last_update": None}


async def test_clear_removes_notes_from_active_topic(manager, new_chat):
    chat = new_chat()
    await manager.add_note(chat, "a")
    await manager.add_note(chat, "b")
    removed = await manager.clear_active_topic(chat)
    assert removed == 2
    assert (await manager.get_status(chat))["note_count"] == 0


async def test_context_is_scoped_per_chat(manager, new_chat):
    chat_one, chat_two = new_chat(), new_chat()
    await manager.add_note(chat_one, "chat one note")
    await manager.add_note(chat_two, "chat two note")
    assert [n.text for n in await manager.get_active_notes(chat_one)] == ["chat one note"]
    assert [n.text for n in await manager.get_active_notes(chat_two)] == ["chat two note"]


async def test_notes_survive_a_new_connection(manager, new_chat):
    chat = new_chat()
    await manager.add_note(chat, "persisted across restarts")

    restarted = ContextManager(DATABASE_URL)
    await restarted.init()
    try:
        assert [n.text for n in await restarted.get_active_notes(chat)] == ["persisted across restarts"]
    finally:
        await restarted.close()
