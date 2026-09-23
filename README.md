# Meera LinkedIn Bot

A Telegram bot that collects your notes through the day (text or voice) and turns them into a ready-to-review LinkedIn post in **Meera's** voice, using Google Gemini.

It does not publish to LinkedIn. It writes drafts for you to review and post yourself.

## How it works

1. Send the bot text messages or voice notes as things happen: customer calls, observations, half-formed thoughts.
2. Each message is stored as a timestamped note under your current **topic thread** (one thread per chat, scoped by `chat_id`).
3. Run `/draft_post`. Gemini writes a post from *only* those notes, using the Meera persona prompt.
4. A deterministic validator checks the draft (hook, banned jargon, how many of your notes are reflected) and shows the results under the draft. That check is plain Python rules, not a second LLM call.

## Commands

| Command | What it does |
|---|---|
| `/start` | Welcome message and command list |
| `/newtopic <title>` | Start a new topic thread (the previous one is archived) |
| `/addnote <text>` | Add a note explicitly (plain messages are added automatically too) |
| `/status` | Show the active topic and how many notes it has |
| `/draft_post` | Generate a Meera-voice draft from the active topic's notes |
| `/clear` | Delete all notes in the active topic |

Draft output format:

```
---
**[Draft LinkedIn Post: Meera Voice]**

<post>

---
**Persona Criteria Validation Check:**
- Hook Impact: PASS/FAIL - <rationale>
- Voice Alignment: PASS/FAIL - <rationale>
- Context Preservation: PASS/FAIL - <n>/<m> source notes are reflected in the draft.

**Source notes used:**
- <each note>
---
```

## Project layout

```
api/webhook.py              Vercel serverless entrypoint (Telegram webhook)
bot/main.py                 Application wiring + local polling entrypoint
bot/handlers.py             Command, text and voice handlers
bot/webhook.py              Webhook update processing + secret check
services/context_manager.py Postgres (Supabase) store for topics and notes (auto-creates schema)
services/gemini_client.py   Gemini calls (google-genai, async)
services/transcription.py   Voice-to-text adapter interface
prompts/meera_persona.py    Persona prompt, voice validator, prompt-injection filter
models/schema.py            Pydantic models (persona config, validation results)
config/settings.py          Env loading + persona.json loader
config/persona.json         Meera's persona calibration (edit to tune the voice)
scripts/set_webhook.py      Register/remove the Telegram webhook
tests/                      pytest suite (mocked Telegram + Gemini)
```

## Environment variables

Copy `.env.example` to `.env` for local runs. Never commit `.env`.

| Variable | Required | Default | Notes |
|---|---|---|---|
| `TELEGRAM_BOT_TOKEN` | yes | | From @BotFather |
| `GEMINI_API_KEY` | yes | | From Google AI Studio |
| `GEMINI_MODEL` | no | `gemini-flash-latest` | An alias that follows the current Flash model, so the bot keeps working when a version is retired |
| `DATABASE_URL` | yes | | Supabase **Transaction pooler** URI (port 6543) from Dashboard → Connect, with your database password filled in |
| `TELEGRAM_WEBHOOK_SECRET` | webhook only | | Random string. Telegram sends it back on every webhook call, and requests without it are rejected |

## Run locally (polling)

Requires Python 3.9+ (3.11+ recommended).

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env   # then fill in the values
python -m bot.main
```

Polling calls `deleteWebhook` on startup, which **disconnects the Vercel deployment** until you register the webhook again (see below).

## Deploy on Vercel (webhook mode)

1. Import the GitHub repo into Vercel. `api/webhook.py` is picked up automatically as a Python function at `/api/webhook`. `vercel.json` pins it to Mumbai (`bom1`), the same region as the Supabase database, so each message only makes short database round-trips.
2. Set these environment variables in the Vercel project: `TELEGRAM_BOT_TOKEN`, `GEMINI_API_KEY`, `GEMINI_MODEL`, `DATABASE_URL`, `TELEGRAM_WEBHOOK_SECRET`.
3. Point Telegram at the production URL (put the same `TELEGRAM_WEBHOOK_SECRET` in your local `.env`):
   ```bash
   python scripts/set_webhook.py https://<your-project>.vercel.app/api/webhook
   ```
4. A `GET` to `/api/webhook` returns `Meera LinkedIn bot webhook is live.` as a health check.

The production domain must not be behind Vercel Deployment Protection, or Telegram's requests will get a 401.

### Storage

Notes are stored in Supabase Postgres (tables `topics` and `notes`), so they survive cold starts, redeploys and bot restarts. The bot creates the tables on first run if they're missing.
- A partial unique index ensures each chat has exactly one active topic, even when two Telegram updates arrive at the same moment.
- Row-level security is on with no policies, so Supabase's public Data API can't read notes. Only the bot's direct database connection can, because it connects as the tables' owner.
- The bot connects through Supabase's transaction pooler, which suits serverless functions that open a short-lived connection for each request.

## Voice notes

Voice messages are downloaded into memory, handed to a `TranscriptionAdapter`, and the bytes are discarded right after. Nothing is written to disk. The default adapter isn't configured yet, so the bot replies asking you to send text. To connect the upstream Meera voice-to-text skill, subclass `TranscriptionAdapter` in `services/transcription.py` and pass it to `build_application(transcription_adapter=...)`.

## Safety and behaviour

- **No hardcoded secrets.** Everything comes from environment variables.
- **Prompt-injection filter.** Messages such as "ignore previous instructions" or "reveal your system prompt" are refused and never stored.
- **Traceability.** The prompt tells Gemini to use only facts from your notes, and the validator reports how many notes show up in the draft.
- **No notes, no draft.** `/draft_post` with an empty topic asks you for notes instead of inventing content.
- **Graceful failures.** Gemini errors (rate limit, 503, network) produce a Telegram message asking you to retry `/draft_post`. Unhandled errors are logged and the user gets a short apology.
- **Buzzword blocklist.** Edit `banned_phrases` in `config/persona.json` (it includes "delighted to share", "game-changer" and "humbled").

## Tests

```bash
pip install -r requirements-dev.txt
pytest
```

`tests/test_context_manager.py` runs against a real database. It uses `TEST_DATABASE_URL`, or `DATABASE_URL` from `.env`, and is skipped when neither is set. Each test uses its own random chat IDs and deletes them afterwards. The other tests mock Telegram, Gemini and storage.
