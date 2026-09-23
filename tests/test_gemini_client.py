from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from services.gemini_client import GeminiClient, GeminiServiceError


@pytest.fixture
def mock_genai_client():
    with patch("services.gemini_client.genai.Client") as mock_client_cls:
        mock_client = MagicMock()
        mock_client.aio.models.generate_content = AsyncMock(
            return_value=SimpleNamespace(text="Generated post text.")
        )
        mock_client_cls.return_value = mock_client
        yield mock_client


async def test_generate_post_returns_text(mock_genai_client):
    client = GeminiClient(api_key="fake-key", model="gemini-flash-latest")
    result = await client.generate_post(["note one", "note two"])
    assert result == "Generated post text."
    call_kwargs = mock_genai_client.aio.models.generate_content.call_args.kwargs
    assert "note one" in call_kwargs["contents"]
    assert call_kwargs["model"] == "gemini-flash-latest"


async def test_generate_post_raises_service_error_on_api_failure(mock_genai_client):
    mock_genai_client.aio.models.generate_content.side_effect = RuntimeError("rate limited")
    client = GeminiClient(api_key="fake-key", model="gemini-flash-latest")
    with pytest.raises(GeminiServiceError):
        await client.generate_post(["note one"])


async def test_generate_post_raises_on_empty_response(mock_genai_client):
    mock_genai_client.aio.models.generate_content.return_value = SimpleNamespace(text="")
    client = GeminiClient(api_key="fake-key", model="gemini-flash-latest")
    with pytest.raises(GeminiServiceError):
        await client.generate_post(["note one"])


async def test_summarize_notes_returns_text(mock_genai_client):
    mock_genai_client.aio.models.generate_content.return_value = SimpleNamespace(text="Summary text.")
    client = GeminiClient(api_key="fake-key", model="gemini-flash-latest")
    result = await client.summarize_notes(["note one"])
    assert result == "Summary text."
