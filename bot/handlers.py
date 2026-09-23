"""Telegram command and message handlers."""
from __future__ import annotations

import logging

from telegram import Update
from telegram.ext import ContextTypes

from models.schema import PersonaConfig, ValidationResult
from prompts.meera_persona import looks_like_prompt_injection, validate_voice
from services.context_manager import ContextManager
from services.gemini_client import GeminiClient, GeminiServiceError
from services.transcription import TranscriptionAdapter

logger = logging.getLogger(__name__)

MIN_NOTES_FOR_DRAFT = 1
TELEGRAM_MESSAGE_LIMIT = 4000


def _services(
    context: ContextTypes.DEFAULT_TYPE,
) -> tuple[ContextManager, GeminiClient, TranscriptionAdapter, PersonaConfig]:
    bot_data = context.application.bot_data
    return (
        bot_data["context_manager"],
        bot_data["gemini_client"],
        bot_data["transcription_adapter"],
        bot_data["persona"],
    )


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.effective_message.reply_text(
        "Hi, I'm your Meera-voice LinkedIn drafting bot.\n\n"
        "Send me text notes or voice messages throughout the day - observations, "
        "customer calls, half-formed thoughts. I'll hold onto them under your "
        "current topic thread.\n\n"
        "Commands:\n"
        "/newtopic <title> - start a fresh topic thread\n"
        "/addnote <text> - add a note explicitly\n"
        "/status - see what's accumulated so far\n"
        "/draft_post - turn the notes into a LinkedIn post in Meera's voice\n"
        "/clear - wipe the current topic's notes\n"
    )


async def newtopic_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    context_manager, *_ = _services(context)
    title = " ".join(context.args).strip() if context.args else "General"
    topic = await context_manager.start_new_topic(update.effective_chat.id, title)
    await update.effective_message.reply_text(f'Started a new topic thread: "{topic.title}".')


async def addnote_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not context.args:
        await update.effective_message.reply_text("Usage: /addnote <your observation>")
        return
    await _ingest_note(update, context, " ".join(context.args), source="text")


async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    context_manager, *_ = _services(context)
    status = await context_manager.get_status(update.effective_chat.id)
    if status["topic"] is None:
        await update.effective_message.reply_text("No active topic yet. Send a note or /newtopic to start one.")
        return
    await update.effective_message.reply_text(
        f"Topic: {status['topic']}\nNotes collected: {status['note_count']}"
    )


async def clear_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    context_manager, *_ = _services(context)
    removed = await context_manager.clear_active_topic(update.effective_chat.id)
    await update.effective_message.reply_text(f"Cleared {removed} note(s) from the current topic.")


async def text_message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    text = update.effective_message.text
    if not text:
        return
    await _ingest_note(update, context, text, source="text")


async def voice_message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    _, _, transcription_adapter, _ = _services(context)
    voice = update.effective_message.voice or update.effective_message.audio
    if voice is None:
        return

    telegram_file = await voice.get_file()
    audio_bytes = await telegram_file.download_as_bytearray()
    try:
        text = await transcription_adapter.transcribe(bytes(audio_bytes), mime_type=voice.mime_type or "audio/ogg")
    except NotImplementedError as exc:
        await update.effective_message.reply_text(
            "I couldn't transcribe that voice note - no transcription backend is "
            "configured yet. Send it as text for now."
        )
        logger.warning("Voice transcription unavailable: %s", exc)
        return
    except Exception:
        logger.exception("Voice transcription failed")
        await update.effective_message.reply_text(
            "Something went wrong transcribing that voice note. Please try again or send it as text."
        )
        return
    finally:
        del audio_bytes  # discard raw audio the moment we're done with it

    await _ingest_note(update, context, text, source="voice")


async def _ingest_note(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str, source: str) -> None:
    if looks_like_prompt_injection(text):
        await update.effective_message.reply_text(
            "That message looks like it's trying to override my instructions, so I'm not storing it as a note. "
            "Send your actual observation and I'll add it."
        )
        logger.warning("Rejected potential prompt injection from chat %s", update.effective_chat.id)
        return

    context_manager, *_ = _services(context)
    await context_manager.add_note(update.effective_chat.id, text, source=source)
    status = await context_manager.get_status(update.effective_chat.id)
    await update.effective_message.reply_text(
        f'Noted under "{status["topic"]}". ({status["note_count"]} notes so far)'
    )


async def draft_post_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    context_manager, gemini_client, _, persona = _services(context)
    chat_id = update.effective_chat.id
    notes = await context_manager.get_active_notes(chat_id)

    if len(notes) < MIN_NOTES_FOR_DRAFT:
        await update.effective_message.reply_text(
            "I don't have any notes for the current topic yet. Send a few observations first, "
            "or start a topic with /newtopic."
        )
        return

    note_texts = [n.text for n in notes]
    await update.effective_message.reply_text("Drafting your post in Meera's voice...")

    try:
        draft_text = await gemini_client.generate_post(note_texts, persona)
    except GeminiServiceError as exc:
        logger.exception("Gemini generation failed")
        await update.effective_message.reply_text(
            "Gemini couldn't generate a draft right now (rate limit or network issue).\n"
            f"Details: {exc}\n"
            "Send /draft_post again in a moment to retry."
        )
        return

    validation = validate_voice(draft_text, persona, source_facts=note_texts)
    message = _format_draft_message(draft_text, validation, note_texts)
    await _reply_in_chunks(update, message)


def _format_draft_message(draft_text: str, validation: ValidationResult, note_texts: list[str]) -> str:
    def mark(check) -> str:
        return "PASS" if check.passed else "FAIL"

    facts_block = "\n".join(f"- {t}" for t in note_texts)

    return (
        "---\n"
        "**[Draft LinkedIn Post: Meera Voice]**\n\n"
        f"{draft_text}\n\n"
        "---\n"
        "**Persona Criteria Validation Check:**\n"
        f"- Hook Impact: {mark(validation.hook_impact)} - {validation.hook_impact.rationale}\n"
        f"- Voice Alignment: {mark(validation.voice_alignment)} - {validation.voice_alignment.rationale}\n"
        f"- Context Preservation: {mark(validation.context_preservation)} - {validation.context_preservation.rationale}\n\n"
        "**Source notes used:**\n"
        f"{facts_block}\n"
        "---"
    )


async def _reply_in_chunks(update: Update, message: str) -> None:
    for start in range(0, len(message), TELEGRAM_MESSAGE_LIMIT):
        await update.effective_message.reply_text(message[start : start + TELEGRAM_MESSAGE_LIMIT])
