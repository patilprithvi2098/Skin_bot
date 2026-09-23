import pytest_asyncio

from services.context_manager import ContextManager


@pytest_asyncio.fixture
async def manager(tmp_path):
    db_path = tmp_path / "test.db"
    cm = ContextManager(str(db_path))
    await cm.init()
    yield cm
    await cm.close()


async def test_add_note_creates_default_topic(manager):
    note = await manager.add_note(chat_id=1, text="First observation")
    assert note.text == "First observation"
    topic = await manager.get_active_topic(chat_id=1)
    assert topic is not None
    assert topic.title == "General"


async def test_notes_accumulate_under_active_topic(manager):
    await manager.add_note(1, "note one")
    await manager.add_note(1, "note two")
    notes = await manager.get_active_notes(1)
    assert [n.text for n in notes] == ["note one", "note two"]


async def test_newtopic_archives_previous_topic(manager):
    await manager.add_note(1, "under first topic")
    await manager.start_new_topic(1, "Second Topic")
    await manager.add_note(1, "under second topic")
    notes = await manager.get_active_notes(1)
    assert [n.text for n in notes] == ["under second topic"]


async def test_status_reports_topic_and_count(manager):
    await manager.add_note(1, "a")
    await manager.add_note(1, "b")
    status = await manager.get_status(1)
    assert status["topic"] == "General"
    assert status["note_count"] == 2


async def test_status_with_no_topic_yet(manager):
    status = await manager.get_status(999)
    assert status == {"topic": None, "note_count": 0, "last_update": None}


async def test_clear_removes_notes_from_active_topic_only(manager):
    await manager.add_note(1, "a")
    removed = await manager.clear_active_topic(1)
    assert removed == 1
    status = await manager.get_status(1)
    assert status["note_count"] == 0


async def test_context_is_scoped_per_chat(manager):
    await manager.add_note(1, "chat one note")
    await manager.add_note(2, "chat two note")
    notes_chat_1 = await manager.get_active_notes(1)
    notes_chat_2 = await manager.get_active_notes(2)
    assert [n.text for n in notes_chat_1] == ["chat one note"]
    assert [n.text for n in notes_chat_2] == ["chat two note"]
