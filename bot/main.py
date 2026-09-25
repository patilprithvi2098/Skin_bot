"""Application entrypoint: wires services into a python-telegram-bot Application."""
from __future__ import annotations

import logging

from telegram import Update
from telegram.ext import Application, CallbackQueryHandler, CommandHandler, ContextTypes, MessageHandler, filters

from bot.handlers import (
    RETRY_DRAFT,
    addnote_command,
    clear_command,
    draft_post_command,
    newtopic_command,
    retry_draft_callback,
    start_command,
    status_command,
    text_message_handler,
    voice_message_handler,
)
from config.settings import Settings, load_persona_config, load_settings
from services.context_manager import ContextManager
from services.gemini_client import GeminiClient
from services.transcription import NotConfiguredTranscriptionAdapter, TranscriptionAdapter

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


async def _post_init(application: Application) -> None:
    context_manager: ContextManager = application.bot_data["context_manager"]
    await context_manager.init()
    logger.info("Context database initialized.")


async def _post_shutdown(application: Application) -> None:
    context_manager: ContextManager = application.bot_data["context_manager"]
    await context_manager.close()


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.error("Unhandled exception while processing update: %s", update, exc_info=context.error)
    if isinstance(update, Update) and update.effective_message is not None:
        try:
            await update.effective_message.reply_text(
                "Something went wrong on my end. Please try that again in a moment."
            )
        except Exception:
            logger.exception("Failed to notify user about an unhandled error")


def build_application(
    settings: Settings | None = None,
    transcription_adapter: TranscriptionAdapter | None = None,
) -> Application:
    settings = settings or load_settings()

    application = (
        Application.builder()
        .token(settings.telegram_bot_token)
        .post_init(_post_init)
        .post_shutdown(_post_shutdown)
        .build()
    )

    application.bot_data["context_manager"] = ContextManager(settings.database_url)
    application.bot_data["gemini_client"] = GeminiClient(settings.gemini_api_key, settings.gemini_models)
    application.bot_data["transcription_adapter"] = transcription_adapter or NotConfiguredTranscriptionAdapter()
    application.bot_data["persona"] = load_persona_config()

    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("newtopic", newtopic_command))
    application.add_handler(CommandHandler("addnote", addnote_command))
    application.add_handler(CommandHandler("status", status_command))
    application.add_handler(CommandHandler("draft_post", draft_post_command))
    application.add_handler(CommandHandler("clear", clear_command))
    application.add_handler(CallbackQueryHandler(retry_draft_callback, pattern=f"^{RETRY_DRAFT}$"))
    application.add_handler(MessageHandler(filters.VOICE | filters.AUDIO, voice_message_handler))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_message_handler))
    application.add_error_handler(error_handler)

    return application


def main() -> None:
    application = build_application()
    logger.info("Starting Meera LinkedIn bot...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
