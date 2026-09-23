from unittest.mock import AsyncMock, MagicMock, patch

from bot import webhook
from bot.webhook import is_authorized
from config.settings import Settings


def test_is_authorized_accepts_matching_secret():
    assert is_authorized("s3cret", "s3cret") is True


def test_is_authorized_rejects_wrong_or_missing_secret():
    assert is_authorized("wrong", "s3cret") is False
    assert is_authorized(None, "s3cret") is False


def test_is_authorized_rejects_everything_when_no_secret_configured():
    assert is_authorized("", "") is False
    assert is_authorized("anything", "") is False


async def test_process_update_payload_dispatches_and_closes_db():
    settings = Settings(
        telegram_bot_token="123:fake",
        gemini_api_key="fake",
        database_url="postgresql://unused",
    )
    application = MagicMock()
    application.__aenter__ = AsyncMock(return_value=application)
    application.__aexit__ = AsyncMock(return_value=False)
    application.process_update = AsyncMock()
    context_manager = MagicMock(init=AsyncMock(), close=AsyncMock())
    application.bot_data = {"context_manager": context_manager}

    with patch.object(webhook, "build_application", return_value=application), \
         patch.object(webhook.Update, "de_json", return_value="parsed-update") as de_json:
        await webhook.process_update_payload({"update_id": 1}, settings)

    de_json.assert_called_once_with({"update_id": 1}, application.bot)
    application.process_update.assert_awaited_once_with("parsed-update")
    context_manager.init.assert_awaited_once()
    context_manager.close.assert_awaited_once()
