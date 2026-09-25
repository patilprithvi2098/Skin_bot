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


def called_models(mock_client):
    return [c.kwargs["model"] for c in mock_client.aio.models.generate_content.call_args_list]


async def test_generate_post_returns_text(mock_genai_client):
    client = GeminiClient(api_key="fake-key", models=["gemini-flash-latest"])
    result = await client.generate_post(["note one", "note two"])
    assert result == "Generated post text."
    call_kwargs = mock_genai_client.aio.models.generate_content.call_args.kwargs
    assert "note one" in call_kwargs["contents"]
    assert call_kwargs["model"] == "gemini-flash-latest"


async def test_falls_back_to_next_model_when_primary_is_busy(mock_genai_client):
    mock_genai_client.aio.models.generate_content.side_effect = [
        RuntimeError("503 UNAVAILABLE high demand"),
        SimpleNamespace(text="Draft from fallback."),
    ]
    client = GeminiClient(api_key="fake-key", models=["busy-model", "spare-model", "unused-model"])
    assert await client.generate_post(["note one"]) == "Draft from fallback."
    assert called_models(mock_genai_client) == ["busy-model", "spare-model"]


async def test_empty_response_falls_through_to_next_model(mock_genai_client):
    mock_genai_client.aio.models.generate_content.side_effect = [
        SimpleNamespace(text=""),
        SimpleNamespace(text="Real draft."),
    ]
    client = GeminiClient(api_key="fake-key", models=["model-a", "model-b"])
    assert await client.generate_post(["note one"]) == "Real draft."


async def test_raises_service_error_when_every_model_fails(mock_genai_client):
    mock_genai_client.aio.models.generate_content.side_effect = RuntimeError("503 UNAVAILABLE")
    client = GeminiClient(api_key="fake-key", models=["model-a", "model-b"])
    with pytest.raises(GeminiServiceError, match="model-a.*model-b"):
        await client.generate_post(["note one"])
    assert called_models(mock_genai_client) == ["model-a", "model-b"]


async def test_summarize_notes_returns_text(mock_genai_client):
    mock_genai_client.aio.models.generate_content.return_value = SimpleNamespace(text="Summary text.")
    client = GeminiClient(api_key="fake-key", models=["gemini-flash-latest"])
    assert await client.summarize_notes(["note one"]) == "Summary text."


def test_requires_at_least_one_model(mock_genai_client):
    with pytest.raises(ValueError):
        GeminiClient(api_key="fake-key", models=[])
