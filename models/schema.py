from __future__ import annotations

from pydantic import BaseModel, Field


class PersonaConfig(BaseModel):
    name: str = "Meera"
    archetype: str = "Thoughtful founder/builder"
    tone_traits: list[str] = Field(
        default_factory=lambda: ["direct", "authentic", "anti-platitude", "high-signal"]
    )
    banned_phrases: list[str] = Field(
        default_factory=lambda: [
            "delighted to share",
            "game-changer",
            "humbled",
            "thrilled to announce",
            "synergy",
            "circle back",
            "move the needle",
            "at the end of the day",
            "thought leader",
            "unlock your potential",
        ]
    )
    formatting_notes: str = "Clean whitespace, short paragraphs, clear takeaway, no hashtag spam."


class ValidationCheck(BaseModel):
    passed: bool
    rationale: str


class ValidationResult(BaseModel):
    hook_impact: ValidationCheck
    voice_alignment: ValidationCheck
    context_preservation: ValidationCheck

    @property
    def all_passed(self) -> bool:
        return (
            self.hook_impact.passed
            and self.voice_alignment.passed
            and self.context_preservation.passed
        )


class DraftPost(BaseModel):
    text: str
    validation: ValidationResult
    source_note_ids: list[int] = Field(default_factory=list)
