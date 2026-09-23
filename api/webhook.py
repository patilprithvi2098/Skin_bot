"""Vercel serverless entrypoint: receives Telegram webhook POSTs at /api/webhook."""
from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
from http.server import BaseHTTPRequestHandler
from pathlib import Path

# Vercel runs this file from api/, so make the project root importable.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from bot.webhook import SECRET_HEADER, is_authorized, process_update_payload  # noqa: E402

logger = logging.getLogger(__name__)


class handler(BaseHTTPRequestHandler):
    def do_POST(self) -> None:
        if not is_authorized(self.headers.get(SECRET_HEADER), os.environ.get("TELEGRAM_WEBHOOK_SECRET", "")):
            self._respond(401, "unauthorized")
            return

        length = int(self.headers.get("Content-Length") or 0)
        try:
            payload = json.loads(self.rfile.read(length) or b"{}")
        except json.JSONDecodeError:
            self._respond(400, "invalid json")
            return

        try:
            asyncio.run(process_update_payload(payload))
        except Exception:
            # Still 200: a non-2xx makes Telegram redeliver the same update repeatedly.
            logger.exception("Failed to process Telegram update")
        self._respond(200, "ok")

    def do_GET(self) -> None:
        self._respond(200, "Meera LinkedIn bot webhook is live.")

    def _respond(self, status: int, body: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", "text/plain")
        self.end_headers()
        self.wfile.write(body.encode())
