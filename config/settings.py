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
    gemini_model: str = "gemini-flash-latest"
    db_path: str = "meera_bot.db"
    webhook_secret: str = ""


class MissingEnvironmentVariable(RuntimeError):
    pass


def load_settings() -> Settings:
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    api_key = os.environ.get("GEMINI_API_KEY")
    missing = [name for name, value in (("TELEGRAM_BOT_TOKEN", token), ("GEMINI_API_KEY", api_key)) if not value]
    if missing:
        raise MissingEnvironmentVariable(
            f"Missing required environment variable(s): {', '.join(missing)}. "
            "Copy .env.example to .env and fill them in."
        )
    return Settings(
        telegram_bot_token=token,
        gemini_api_key=api_key,
        gemini_model=os.environ.get("GEMINI_MODEL", "gemini-flash-latest"),
        db_path=os.environ.get("MEERA_BOT_DB_PATH", "meera_bot.db"),
        webhook_secret=os.environ.get("TELEGRAM_WEBHOOK_SECRET", ""),
    )


def load_persona_config(path: Path = PERSONA_CONFIG_PATH) -> PersonaConfig:
    """Load Meera's persona calibration from config/persona.json, falling back to defaults."""
    if not path.exists():
        return PersonaConfig()
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return PersonaConfig(**data)
