"""Gemini LLM integration: context summarization and Meera-voice post generation."""
from __future__ import annotations

import logging

from google import genai

from models.schema import PersonaConfig
from prompts.meera_persona import build_generation_prompt, build_summarization_prompt

logger = logging.getLogger(__name__)


class GeminiServiceError(Exception):
    """Raised when every configured Gemini model fails (overloaded, rate limited, retired, network)."""


class GeminiClient:
    def __init__(self, api_key: str, models: list[str]):
        if not models:
            raise ValueError("At least one Gemini model is required")
        self._client = genai.Client(api_key=api_key)
        self._models = models

    async def generate_post(self, notes: list[str], persona: PersonaConfig | None = None) -> str:
        return await self._generate(build_generation_prompt(notes, persona))

    async def summarize_notes(self, notes: list[str]) -> str:
        return await self._generate(build_summarization_prompt(notes))

    async def _generate(self, prompt: str) -> str:
        # Popular models regularly return 503 "high demand" or get retired; fall through to the next one.
        errors = []
        for model in self._models:
            try:
                response = await self._client.aio.models.generate_content(model=model, contents=prompt)
            except Exception as exc:
                logger.warning("Gemini model %s failed: %s", model, exc)
                errors.append(f"{model}: {exc}")
                continue
            text = (getattr(response, "text", None) or "").strip()
            if text:
                return text
            errors.append(f"{model}: empty response")
        raise GeminiServiceError("; ".join(errors))
