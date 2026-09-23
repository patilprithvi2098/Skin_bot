"""Voice-note transcription seam.

Audio notes sent via Telegram are either pre-transcribed upstream or need to be
routed to a speech-to-text backend here. This module defines the adapter
interface the bot depends on; it never touches disk, and callers are expected
to discard the raw audio bytes as soon as `transcribe()` returns (or raises).

Plug the upstream Meera-tuned voice-to-text skill in by implementing
`TranscriptionAdapter` and passing an instance to `build_application()` in
`bot/main.py`.
"""
from __future__ import annotations

from abc import ABC, abstractmethod


class TranscriptionAdapter(ABC):
    @abstractmethod
    async def transcribe(self, audio_bytes: bytes, mime_type: str) -> str:
        """Transcribe raw audio bytes to text. Must not persist `audio_bytes`."""


class NotConfiguredTranscriptionAdapter(TranscriptionAdapter):
    """Default adapter: raises until a real voice-to-text backend is wired in."""

    async def transcribe(self, audio_bytes: bytes, mime_type: str) -> str:
        raise NotImplementedError(
            "No voice transcription backend is configured. Plug the upstream "
            "Meera voice-to-text skill into a TranscriptionAdapter and pass it "
            "to build_application(), or send text notes instead."
        )
