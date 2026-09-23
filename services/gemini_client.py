"""Gemini LLM integration: context summarization and Meera-voice post generation."""
from __future__ import annotations

import logging

from google import genai

from models.schema import PersonaConfig
from prompts.meera_persona import build_generation_prompt, build_summarization_prompt

logger = logging.getLogger(__name__)


class GeminiServiceError(Exception):
    """Raised when the Gemini API cannot fulfill a request (rate limit, network, empty response)."""


class GeminiClient:
    def __init__(self, api_key: str, model: str):
        self._client = genai.Client(api_key=api_key)
        self._model = model

    async def generate_post(self, notes: list[str], persona: PersonaConfig | None = None) -> str:
        prompt = build_generation_prompt(notes, persona)
        return await self._generate(prompt)

    async def summarize_notes(self, notes: list[str]) -> str:
        prompt = build_summarization_prompt(notes)
        return await self._generate(prompt)

    async def _generate(self, prompt: str) -> str:
        try:
            response = await self._client.aio.models.generate_content(
                model=self._model,
                contents=prompt,
            )
        except Exception as exc:  # google-genai surfaces rate limits/network errors here
            logger.exception("Gemini API request failed")
            raise GeminiServiceError(str(exc)) from exc

        text = getattr(response, "text", None)
        if not text:
            raise GeminiServiceError("Gemini returned an empty response.")
        return text.strip()
