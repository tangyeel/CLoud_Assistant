# Project Map: J.A.R.V.I.S. Personal Assistant

> Read this first to orient future work without rereading the entire repository. This map was checked against the source on 2026-11-04. It describes the checked-in implementation, not a promise that external services or credentials are currently working.

## What this project is

A Python 3.12 Telegram personal assistant. It accepts slash commands, text, voice notes and inline-button actions; reads/writes Google Workspace data; uses a configurable cascade of language model providers; generates scheduled/on-demand briefings; and exposes a small Starlette health/webhook server. Main runtime entry: [`main.py`](main.py).

## Start here / source-of-truth order

1. [`PROJECT_MAP.md`](PROJECT_MAP.md) — navigation, implemented state and architecture summary.
2. [`README.md`](README.md) — user-facing capabilities, deployment and security overview; some details are stale.
3. Source code — authoritative for what currently runs.
4. [`FEATURES.md`](FEATURES.md) — detailed product specification and future ideas; it is not an implementation checklist.
5. [`IMPLEMENTATION_GUIDE.md`](IMPLEMENTATION_GUIDE.md) and [`blueprint.md`](blueprint.md) — build/deployment guidance and original architecture; parts predate the current code.

There is no `AGENTS.md` in the repository at the time of mapping.

## Runtime architecture

```text
Telegram update
  -> main.py (python-telegram-bot app, webhook or polling)
  -> bot/middleware.py authorization (decorated handlers)
  -> bot/handlers.py command/callback/voice/text handling
       -> bot/router.py parses intent with AI and dispatches action
            -> google_services/*, utils/*, reports/*
  -> Telegram text / inline keyboard / audio response

Starlette HTTP server: /health, /, /webhook
APScheduler in the same process: morning, evening, leave alerts,
attendance check-in and audio cleanup
```

### Startup and hosting

- `main.py` builds the PTB application and registers commands, callbacks, voice and plain-text handlers. Its Starlette lifespan initializes the bot, starts APScheduler, and selects webhook mode when `TELEGRAM_WEBHOOK_URL` is set; otherwise it starts Telegram polling. `python main.py --polling` runs standalone polling.
- `utils/health.py` backs `GET /health`; `GET /` is a plain status response.
- `Dockerfile` installs FFmpeg and runs `python main.py`. `render.yaml` is a Render blueprint with `sync: false` secret settings. `requirements.txt` lists runtime dependencies (mostly minimum versions, not exact pins).
- `auth_setup.py` performs browser OAuth for the default account or `--thapar` and prints a base64 token value for deployment.

## Feature map: implemented state

| Capability | Current behavior | Main code |
|---|---|---|
| Owner-only Telegram access | `authorized_only` compares chat ID; if unset, returns setup hint. Applied to handlers. | `bot/middleware.py`, `bot/handlers.py` |
| Natural-language interaction | AI parses intent and routes calendar/task/email/calendar/classroom/attendance/weather/news/search/report/general requests. | `ai/prompts.py`, `bot/router.py` |
| Exam schedule photo import | Telegram photo -> Gemini vision JSON extraction -> preview/uncertainty notice -> explicit confirmation -> timed or all-day Calendar events. Pending previews expire after 15 minutes; requires Gemini API key. | `bot/handlers.py`, `ai/gemini_client.py`, `google_services/calendar_service.py` |
| Calendar | Read today's/tomorrow/upcoming events across default + optional Thapar token; create event; detect overlap and offer suggested time / schedule anyway / cancel. | `google_services/calendar_service.py`, `bot/router.py`, callback handler |
| Tasks | List/create/complete; snooze helper exists. Google Tasks defaults to `@default` task list. | `google_services/tasks_service.py`, `bot/router.py`, `bot/handlers.py` |
| Gmail | Fetch unread metadata/snippets from recent window, excluding promotions/social/forums; default + optional Thapar. Helper can fetch body or mark read. No implemented AI email action classification or inline email actions. | `google_services/gmail_service.py`, `bot/router.py` |
| Classroom | Discover active courses across accounts (excluded IDs configurable), fetch coursework and aggregate/sort. | `google_services/classroom_service.py` |
| Morning briefing | Fetch weather, unread email metadata, today's calendar, pending tasks and Classroom work; AI script with template fallback; Edge-TTS voice or text; agenda/tasks/weather buttons. | `reports/morning.py`, `ai/prompts.py` |
| Evening briefing | Tomorrow's calendar, assignments, tasks and weather; forward-looking AI script with fallback; voice or text. Does not implement the spec's recap of completed events/tasks. | `reports/evening.py` |
| Scheduled jobs | Morning report defaults to 06:30 and evening to 20:00; two-minute calendar scan sends Telegram class alerts for Thapar calendar items and reminders for other events 10–18 minutes before start; 14:05 attendance prompt; deadline scan every 10 minutes (24h and 2h lead defaults); six-hour audio cleanup. Alert dedupe is in-memory and resets on process restart. | `scheduler/jobs.py`, `config.py` |
| Voice input | Telegram voice download -> Groq Whisper -> normal intent route -> spoken TTS response when possible; deletes input audio in `finally`. | `bot/handlers.py`, `ai/stt.py`, `tts/speech.py` |
| AI provider fallback | Ordered providers configurable via `AI_PROVIDER_ORDER`; supports Cloudflare, Groq, Gemini, Cerebras, NVIDIA, OpenRouter and custom OpenAI-compatible endpoint. Text/JSON generation helpers. | `ai/gemini_client.py`, `config.py` |
| TTS | Edge-TTS primary with gTTS fallback; FFmpeg/ffmpeg binary conversion for Telegram voice OGG when possible; chime helper and stale-file cleanup. | `tts/speech.py`, `assets/` |
| Attendance | Local JSON counts per subject, 75% safe-bunks/required-classes calculation, inline check-in buttons; data is ignored by Git. | `utils/attendance.py`, `data/` |
| Weather/news/search | Open-Meteo geocode/forecast; DDGS search; finance/tech news retrieval; callable by slash command and natural-language router. | `utils/weather.py`, `utils/search.py`, `utils/news.py` |
| Diagnostics/resilience | `/status`, rotating Loguru logger, retry decorators, health endpoint, isolated fetch and AI/TTS/text fallbacks in reports. | `bot/handlers.py`, `utils/logger.py`, `utils/retry.py`, `utils/health.py` |

### Telegram commands registered in `main.py`

`/start`, `/help`, `/morning`, `/evening`, `/schedule`, `/tasks`, `/weather`, `/emails`, `/classes`, `/status`, `/attendance`, `/news`, `/search`, `/market`, `/stock`, `/ipo`, `/thesis`, `/alerts`, `/memory`, `/forget`, `/watchlist`, `/earnings`.

## Spec status and gaps

`FEATURES.md` is a broad aspirational specification, not a reliable shipped-feature list. The following substantial features are specified but not implemented in the current source: Telegram setup wizard beyond showing the chat ID; changing configuration in chat; smart silence hours/queue; weekly digest; persistent conversation memory; exam/assignment mode; full admin commands (`/logs`, `/force_refresh`, `/restart_jobs`); Gmail reply/star/archive/mute quick actions; calendar edit/delete/share/reminder quick actions; assignment submission-state tracking and new-assignment notifications; report duplicate suppression and retry-after-failure; per-source report error narration; scanning all Google Task lists. Deadline alerts now exist for dated tasks and Classroom coursework; Classroom submission status is not checked, so submitted work may still be reminded.

Partial or mismatched areas:

- **Calendar spec:** Event creation is present, but no date clarification workflow, event update/delete flow, or robust timezone-aware local-date parsing in the router. Conflict proposal storage is process memory. The time-slot suggestion is an approximate first gap and its UI choice is callback-driven.
- **Task spec:** Creation/list/completion exist. The due-date router formats parsed dates as `23:59Z`; no scheduler sends deadline reminders. Snooze is a service helper, but no normal user flow is wired to it.
- **Gmail spec:** Current operation is unread metadata/snippet listing (12h defaults), not AI-ranked full-message summaries. `get_email_body` and `mark_as_read` are helpers, not full user flows.
- **Classroom spec:** Coursework discovery is present, but there is no student submission query/status, remembered course state, or proactive assignment notification.
- **Graceful degradation:** Reports continue after source fetch exceptions and fall back for AI/TTS, but the source fetch helper returns `[]` for any failure (including weather, whose expected value is a dict). No all-sources-failed delayed retry exists.
- **Dual account:** Calendar/Gmail/Classroom use an existing Thapar token if present. Tasks use only the default account. OAuth refresh is automatic, but browser reauthorization cannot work headlessly in production if refresh fails.
- **Buttons/security:** Schedule conflict and attendance actions are wired; morning briefing has Agenda/Tasks/Weather callbacks. No general rate limiting or private-data callback expiry is present.
- **Docs/config drift:** README/Render setup lists a smaller/older provider and environment set than `config.py`/`.env.example`; README's advertised default voice differs from config's `en-GB-RyanNeural`. Check current code and `.env.example` when changing deployment docs.
- **Cloud scheduling:** The hosted Starlette lifecycle now explicitly registers APScheduler jobs. Scheduled delivery still requires the cloud process to remain running at the scheduled time; current alert deduplication is process-local.

## Module-by-module navigation

### Configuration and process

- [`config.py`](config.py): `.env` loading, Telegram IDs, OAuth paths/base64 restoration, AI provider order and keys/models, TTS, city, timezone/schedule, server/log settings, Classroom exclusions, scopes and validation. **Import side effects:** may materialize credential files from base64 and create audio/log directories.
- [`main.py`](main.py): PTB wiring + Starlette routes/lifecycle and polling mode.
- [`auth_setup.py`](auth_setup.py): local OAuth setup for one or both Google accounts.
- [`bot/middleware.py`](bot/middleware.py): authorization decorator.

### Telegram interface and routing

- [`bot/handlers.py`](bot/handlers.py): all command handlers, callback action branches, text routing, voice-note processing, message splitting.
- [`bot/router.py`](bot/router.py): LLM intent parse, parameter normalization, and action dispatch. Calendar conflicts return `(message, keyboard)`; handlers unpack this shape.
- [`ai/prompts.py`](ai/prompts.py): briefing, intent parser and general-answer prompts.
- [`ai/gemini_client.py`](ai/gemini_client.py): provider adapters, response/JSON normalization, provider availability/hierarchy.
- [`ai/stt.py`](ai/stt.py): lazy Groq client and Whisper transcription.

### Google integrations

- [`google_services/auth.py`](google_services/auth.py): load OAuth token, refresh/save, or launch local OAuth flow; build Google API service.
- [`google_services/calendar_service.py`](google_services/calendar_service.py): event queries, overlap detection, free-slot suggestion, event creation.
- [`google_services/tasks_service.py`](google_services/tasks_service.py): task list and default-list operations.
- [`google_services/gmail_service.py`](google_services/gmail_service.py): unread query, metadata, body decode, mark read.
- [`google_services/classroom_service.py`](google_services/classroom_service.py): active course/coursework aggregation.

### Background output and utilities

- [`reports/morning.py`](reports/morning.py), [`reports/evening.py`](reports/evening.py): data collection -> context formatting -> AI/fallback -> TTS/fallback -> Telegram send.
- [`scheduler/jobs.py`](scheduler/jobs.py): APScheduler jobs and Telegram bot reference.
- [`tts/speech.py`](tts/speech.py): synthesis, conversion, send helper, cleanup; [`assets/`](assets/) holds the chime.
- [`utils/attendance.py`](utils/attendance.py): local attendance persistence/calculation/card.
- [`utils/weather.py`](utils/weather.py), [`utils/news.py`](utils/news.py), [`utils/search.py`](utils/search.py): external information features.
- [`utils/retry.py`](utils/retry.py), [`utils/logger.py`](utils/logger.py), [`utils/health.py`](utils/health.py): cross-cutting operations.

### Data and deployment files

- `credentials/`: local OAuth files are ignored; `credentials/README.md` documents setup. Never put secrets in the project map.
- `data/attendance.json`: runtime-local attendance state, ignored by Git. `data/.gitkeep` is tracked.
- `audio/`, `logs/`, `temp_audio/`: generated/runtime files; temporary voice inputs are removed after processing.
- [`requirements.txt`](requirements.txt), [`Dockerfile`](Dockerfile), [`render.yaml`](render.yaml), [`.env.example`](.env.example), [`.gitignore`](.gitignore): dependencies, deployment, configuration template, ignore policy.

## Typical end-to-end flows

### Text request

1. PTB delivers update to decorated handler. Authorization is by `effective_chat.id`.
2. `handle_text_message` calls `route_message`.
3. Router supplies current configured-local date/time to `generate_json` with intent parser prompt.
4. Dispatch invokes integration/service code; response is formatted and sent as Markdown, splitting long text near newlines.
5. Most network-facing service functions use retry decorators; report data fetching has per-source try/catch.

### Scheduled morning briefing

1. APScheduler fires using `TIMEZONE` and report hour/minute.
2. `run_morning_report` fetches weather, Gmail, Calendar, Tasks and Classroom serially.
3. It formats data for AI; provider cascade generates spoken script or local template is used.
4. TTS creates voice file (OGG if conversion available, otherwise MP3); Telegram receives voice/audio or text fallback; cleanup runs.

### Google OAuth / dual account

1. Place downloaded Google OAuth client JSON at configured credentials path.
2. Run `python auth_setup.py` and optionally `python auth_setup.py --thapar` locally.
3. Token files are refreshed and saved by `google_services/auth.py`; cloud can restore base64 credentials/tokens at config import if target file is absent.
4. Services treat presence of `token_thapar.json` as account availability. Keep credentials and token values private.

## Configuration index

Use [`.env.example`](.env.example) as the variable list. Main groups: Telegram (`TELEGRAM_*`); Google paths and base64 (`GOOGLE_*`); AI provider credentials/models and order (`AI_PROVIDER_ORDER`, `*_API_KEY`, `*_MODEL`); TTS/audio (`TTS_*`, `AUDIO_OUTPUT_DIR`); locale/schedule (`USER_CITY`, `TIMEZONE`, `*_REPORT_*`); server/logging (`PORT`, `LOG_*`, `SEND_ERROR_ALERTS`); Classroom filter (`EXCLUDED_COURSE_IDS`). `config.py` contains actual defaults and validation. Do not copy real `.env` values into docs or prompts.

## Fast change locator

- Add a Telegram command: register it in `main.py`, implement in `bot/handlers.py`, protect with `@authorized_only`.
- Add a natural-language action: define/adjust JSON shape in `ai/prompts.py`, add dispatch in `bot/router.py`, call a service in `google_services/` or `utils/`.
- Add a Google API operation: put it in corresponding `google_services/*_service.py`; auth is centralized in `google_services/auth.py`.
- Change a briefing: update data fetch/format/send in `reports/morning.py` or `reports/evening.py`, plus its prompt in `ai/prompts.py`.
- Add or change scheduled work: `scheduler/jobs.py`; register it in `start_scheduler()`.
- Change settings/defaults: `config.py` and `.env.example`, then reconcile `README.md` and `render.yaml` if deploy-facing.
- Update this map when architecture, exposed commands, shipped feature state or deployment assumptions change. Keep it factual and concise; don’t duplicate full feature prose from `FEATURES.md`.
