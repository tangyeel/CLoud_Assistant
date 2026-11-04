# 🤖 J.A.R.V.I.S. — Autonomous AI Personal Assistant

> **A 100% Free-Forever, 24/7 Autonomous University Butler & Personal Assistant.**  
> Powered by lightweight LLM cascades (Cloudflare Workers AI, Groq, Gemini), Edge-TTS, Groq Whisper STT, and Google Workspace.

---

## 🌟 Key Capabilities

### 🎙️ Proactive Audio Briefings & Two-Way Voice
* **Morning Briefing (06:30 IST):** Jarvis synthesizes a morning radio-style report covering your day's schedule, unread emails, classroom assignments, to-dos, and real-time Patiala weather with rain probability.
* **Evening Briefing (20:00 IST):** A forward-looking wind-down debrief focused on tomorrow's earliest commitments, looming deadlines, and commute weather forecast.
* **Two-Way Voice (Whisper STT + Edge-TTS):** Send voice notes on Telegram while walking across campus. Groq Whisper (`whisper-large-v3-turbo`) transcribes in ~0.25s, executes your command, and replies with a British neural voice note prepended with an authentic sci-fi activation chime.

### 🎓 Academic & Timetable Safeguards (Thapar University)
* **Dual-Account Google Workspace:** Queries your Personal account (`token.json`) and University account (`token_thapar.json`) simultaneously.
* **15-Minute "Time-to-Leave" Alerts:** Background cron checks your calendar 10–18 minutes before classes start (e.g. *LT10, B304, C328*) and sends a notification to leave on time.
* **Deadline Alerts:** Checks pending Google Tasks and dated Classroom assignments every 10 minutes; sends reminders about 24 hours and 2 hours before the deadline.
* **Exam Schedule Photo Import:** Send a photo of your exam timetable; Jarvis extracts dates and times, previews them, and adds confirmed exams to Google Calendar.
* **Calendar Conflict Guard:** Intercepts overlapping bookings (e.g. *"Book gym tomorrow at 9 AM"*), alerts you to conflicting lectures, and auto-suggests the next open daytime slot.
* **75% Attendance Safeguard (`/attendance`):** Tracks attended vs. total classes per course, calculating **safe bunks remaining** or **consecutive lectures required** to maintain the 75% threshold. Prompts with a 1-tap poll at 14:05 daily.

### 🌐 Intelligence & News Radar
* **100% Free Live Web Search (`/search`):** Real-time web search powered by DuckDuckGo without any API key or billing requirement.
* **Finance & Tech News Radar (`/news`):** Pulls live market, startup, and AI headlines with clickable sources and 1-line takeaways.

---

## ⚡ Architecture & Tech Stack

| Component | Technology | Cost |
| :--- | :--- | :--- |
| **Interface** | Telegram Bot API (`python-telegram-bot` v22) | Free |
| **Speech-to-Text** | Groq Whisper Large v3 Turbo (~0.25s latency) | Free Tier (2,000 req/day) |
| **Text-to-Speech** | Microsoft Edge-TTS (`en-GB-RyanNeural`) + Custom Chime | 100% Free |
| **AI Cascade** | Cloudflare Workers AI &rarr; Groq (`allam-2-7b`) &rarr; Gemini Flash | 100% Free Tier |
| **Google Services** | Gmail, Calendar, Tasks, Classroom (OAuth 2.0) | Free |
| **Weather** | Open-Meteo API (Patiala geocoded forecast) | 100% Free |
| **Web & News** | DuckDuckGo Search (`ddgs`) | 100% Free |
| **Hosting** | Render.com Web Service + UptimeRobot keep-alive ping | 100% Free (No Card Required) |

---

## 📁 Repository Structure

```
.
├── ai/
│   ├── gemini_client.py   # Multi-provider LLM fallback cascade
│   ├── prompts.py         # J.A.R.V.I.S. system prompts & intent parser
│   └── stt.py             # Groq Whisper speech-to-text pipeline
├── bot/
│   ├── handlers.py        # Telegram commands, callbacks & voice handlers
│   ├── middleware.py      # Chat-ID authorization decorator
│   └── router.py          # Intent routing & conflict detection
├── google_services/
│   ├── auth.py            # OAuth 2.0 token management & multi-account
│   ├── calendar_service.py# Calendar agenda, conflict checks & slots
│   ├── classroom_service.py# Coursework deadlines & assignments
│   ├── gmail_service.py   # Unread email triage across accounts
│   └── tasks_service.py   # Task creation, completion & 24h snoozing
├── reports/
│   ├── morning.py         # Morning briefing pipeline
│   └── evening.py         # Evening preparatory debrief pipeline
├── scheduler/
│   └── jobs.py            # APScheduler cron triggers & 15m alerts
├── tts/
│   └── speech.py          # Edge-TTS audio synthesis & chime prepending
├── utils/
│   ├── attendance.py      # Thapar 75% attendance margin engine
│   ├── earnings.py        # Autonomous earnings triage & custom watchlist
│   ├── finance.py         # Market snapshot, stock detail & pre-market radar
│   ├── health.py          # /health endpoint for 24/7 uptime pings
│   ├── ipo.py             # Live IPO GMP scraper & Saturday report
│   ├── logger.py          # Loguru rotation
│   ├── memory.py          # 4-Layer Cognitive Vector Memory & Reflection
│   ├── news.py            # Tech & finance news scraper
│   ├── price_alerts.py    # Plain-English price & volatility alerts
│   ├── retry.py           # Exponential backoff decorators
│   ├── search.py          # DuckDuckGo live web search
│   ├── thesis.py          # Investment thesis tracker & live P&L
│   └── weather.py         # Open-Meteo real-time & daily forecast
├── assets/
│   └── jarvis_chime.wav   # Sci-fi activation chime
├── auth_setup.py          # Local one-time Google OAuth authorization utility
├── config.py              # Centralized environment loader & validator
├── Dockerfile             # Production container definition
├── render.yaml            # Render infrastructure-as-code blueprint
└── requirements.txt       # Pinned dependencies
```

---

## 🚀 24/7 Cloud Deployment Guide (Render.com + UptimeRobot)

### 1. Generate Base64 Environment Variables
To ensure zero token loss across cloud container restarts, generate Base64 strings from your local credentials:
```powershell
python -c "
import base64
for name, path in [('GOOGLE_CREDENTIALS_B64', 'credentials/credentials.json'), ('GOOGLE_TOKEN_B64', 'credentials/token.json'), ('GOOGLE_THAPAR_TOKEN_B64', 'credentials/token_thapar.json')]:
    with open(path, 'rb') as f:
        print(f'{name}={base64.b64encode(f.read()).decode()}\n')
"
```

### 2. Deploy to Render
1. Create a free account on [Render.com](https://render.com) (no credit card required).
2. Click **New +** &rarr; **Web Service** &rarr; Connect this GitHub repository.
3. Select **Runtime: Docker** & **Plan: Free**.
4. In **Environment Variables**, configure:
   * `TELEGRAM_BOT_TOKEN`
   * `TELEGRAM_CHAT_ID`
   * `GROQ_API_KEY`
   * `CLOUDFLARE_ACCOUNT_ID`
   * `CLOUDFLARE_API_TOKEN`
   * `USER_CITY` (`Patiala`)
   * `TIMEZONE` (`Asia/Kolkata`)
   * `GOOGLE_CREDENTIALS_B64`
   * `GOOGLE_TOKEN_B64`
   * `GOOGLE_THAPAR_TOKEN_B64`
5. Click **Create Web Service**.

### 3. Keep Awake 24/7 (Free Ping)
1. Register on [UptimeRobot.com](https://uptimerobot.com) (free).
2. Add a new **HTTP(s) Monitor**:
   * **URL:** `https://<your-render-app-name>.onrender.com/health`
   * **Interval:** `10 minutes`
3. Render receives the ping, resets its idle timer, and stays awake 24/7 completely free.

---

## 🔒 Security
* **Authorized Only:** Every interaction is whitelisted strictly to `TELEGRAM_CHAT_ID`. Messages from unauthorized accounts are dropped.
* **Zero Credentials in Git:** `.env` and `credentials/` files are strictly excluded via `.gitignore`.
