"""Webhook-mode update processing for serverless hosts (Vercel).

Each invocation builds a fresh Application: serverless runtimes give each
request its own event loop, and PTB's HTTP client can't be shared across loops.
"""
from __future__ import annotations

import hmac

from telegram import Update

from bot.main import build_application
from config.settings import Settings, load_settings
from services.context_manager import ContextManager

SECRET_HEADER = "X-Telegram-Bot-Api-Secret-Token"


def is_authorized(received_secret: str | None, expected_secret: str) -> bool:
    if not expected_secret:
        return False
    return hmac.compare_digest(received_secret or "", expected_secret)


async def process_update_payload(payload: dict, settings: Settings | None = None) -> None:
    application = build_application(settings or load_settings())
    context_manager: ContextManager = application.bot_data["context_manager"]
    await context_manager.init()
    try:
        async with application:
            update = Update.de_json(payload, application.bot)
            await application.process_update(update)
    finally:
        await context_manager.close()
