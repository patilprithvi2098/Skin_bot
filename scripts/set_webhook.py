"""Register (or remove) the Telegram webhook.

Usage:
    python scripts/set_webhook.py https://<your-app>.vercel.app/api/webhook
    python scripts/set_webhook.py --delete
"""
from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from telegram import Bot, Update

load_dotenv(Path(__file__).resolve().parent.parent / ".env")


async def main(argv: list[str]) -> None:
    if len(argv) != 1:
        sys.exit(__doc__)

    bot = Bot(token=os.environ["TELEGRAM_BOT_TOKEN"])
    async with bot:
        if argv[0] == "--delete":
            await bot.delete_webhook()
            print("Webhook removed.")
            return

        secret = os.environ.get("TELEGRAM_WEBHOOK_SECRET")
        if not secret:
            sys.exit("TELEGRAM_WEBHOOK_SECRET must be set (same value as in Vercel).")
        await bot.set_webhook(url=argv[0], secret_token=secret, allowed_updates=Update.ALL_TYPES)
        info = await bot.get_webhook_info()
        print(f"Webhook set: {info.url} (pending updates: {info.pending_update_count})")


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1:]))
