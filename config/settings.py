"""Environment configuration and persona-calibration loading."""
from __future__ import annotations

import json
import os
from pathlib import Path

from dotenv import load_dotenv
from pydantic import BaseModel

from models.schema import PersonaConfig

load_dotenv()

PERSONA_CONFIG_PATH = Path(__file__).parent / "persona.json"


class Settings(BaseModel):
    telegram_bot_token: str
    gemini_api_key: str
    database_url: str
    gemini_model: str = "gemini-flash-latest"
    webhook_secret: str = ""


class MissingEnvironmentVariable(RuntimeError):
    pass


def load_settings() -> Settings:
    required = {name: os.environ.get(name) for name in ("TELEGRAM_BOT_TOKEN", "GEMINI_API_KEY", "DATABASE_URL")}
    missing = [name for name, value in required.items() if not value]
    if missing:
        raise MissingEnvironmentVariable(
            f"Missing required environment variable(s): {', '.join(missing)}. "
            "Copy .env.example to .env and fill them in."
        )
    return Settings(
        telegram_bot_token=required["TELEGRAM_BOT_TOKEN"],
        gemini_api_key=required["GEMINI_API_KEY"],
        database_url=required["DATABASE_URL"],
        gemini_model=os.environ.get("GEMINI_MODEL", "gemini-flash-latest"),
        webhook_secret=os.environ.get("TELEGRAM_WEBHOOK_SECRET", ""),
    )


def load_persona_config(path: Path = PERSONA_CONFIG_PATH) -> PersonaConfig:
    """Load Meera's persona calibration from config/persona.json, falling back to defaults."""
    if not path.exists():
        return PersonaConfig()
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return PersonaConfig(**data)
