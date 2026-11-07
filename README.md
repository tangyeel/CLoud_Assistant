# 🤖 J.A.R.V.I.S. — Autonomous AI Personal Assistant & University Butler

[![Python 3.12](https://img.shields.io/badge/Python-3.12-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://python.org)
[![Telegram Bot](https://img.shields.io/badge/Telegram-Bot_API_v22-26A5E4?style=for-the-badge&logo=telegram&logoColor=white)](https://core.telegram.org/bots)
[![Groq Whisper](https://img.shields.io/badge/Groq-Whisper_Large_v3_Turbo-F55036?style=for-the-badge&logo=groq&logoColor=white)](https://groq.com)
[![Edge-TTS](https://img.shields.io/badge/Edge--TTS-British_RyanNeural-0078D7?style=for-the-badge&logo=microsoft&logoColor=white)](https://github.com/rany2/edge-tts)
[![Docker](https://img.shields.io/badge/Docker-Production_Container-2496ED?style=for-the-badge&logo=docker&logoColor=white)](https://docker.com)
[![Render](https://img.shields.io/badge/Render-24%2F7_Free_Hosting-46E3B7?style=for-the-badge&logo=render&logoColor=black)](https://render.com)
[![License: MIT](https://img.shields.io/badge/License-MIT-green?style=for-the-badge)](LICENSE)

> **A 100% Free-Forever, 24/7 Autonomous University Butler, Institutional Equity Research Desk & Cognitive Executive Assistant.**  
> Built for students, engineers, and market analysts. Powered by multi-provider LLM fallback cascades (Cloudflare Workers AI &rarr; Groq &rarr; Gemini &rarr; Cerebras &rarr; NVIDIA), Groq Whisper STT, British Edge-TTS, Dual-Account Google Workspace, and official National Stock Exchange (NSE) data pipelines.

---

## 📑 Table of Contents

- [Architectural Overview](#-architectural-overview)
- [Key Pillars & Capabilities](#-key-pillars--capabilities)
  - [1. 🧠 4-Layer Cognitive Memory & Neural Persona](#1--4-layer-cognitive-memory--neural-persona)
  - [2. 🎙️ Two-Way Voice, AI Condenser & Daily Briefings](#2-️-two-way-voice-ai-condenser--daily-briefings)
  - [3. 🎓 Academic & Timetable Safeguards (Thapar University)](#3--academic--timetable-safeguards-thapar-university)
  - [4. 📈 Institutional Equity Research & Financial Intelligence](#4--institutional-equity-research--financial-intelligence)
  - [5. ⚡ One-Tap Command Dock](#5--one-tap-command-dock)
- [Complete Slash Command Directory](#-complete-slash-command-directory)
- [Technology Stack & Zero-Cost Architecture](#-technology-stack--zero-cost-architecture)
- [Repository Structure](#-repository-structure)
- [24/7 Cloud Deployment Guide (Render + UptimeRobot)](#-247-cloud-deployment-guide-render--uptimerobot)
- [Configuration & Environment Variables](#-configuration--environment-variables)
- [Security & Privacy Safeguards](#-security--privacy-safeguards)

---

## 🏛️ Architectural Overview

```text
                                  ┌──────────────────────────────┐
                                  │   User (Telegram Mobile/PC)  │
                                  └──────────────┬───────────────┘
                                                 │
                                 [Voice / Photo / Text / Callback]
                                                 │
                                                 ▼
┌─────────────────────────────────────────────────────────────────────────────────────────────┐
│ J.A.R.V.I.S. Runtime Engine (Python 3.12 / python-telegram-bot v22)                          │
├─────────────────────────────────────────────────────────────────────────────────────────────┤
│ • Security Middleware: chat_id authorization decorator drops unauthorized access            │
│ • Voice Pipeline: Groq Whisper Large-v3-Turbo (~0.25s STT) + Spoken Note Condenser          │
│ • Vision Pipeline: Gemini 2.5 Flash Exam Schedule Photo OCR                                 │
│ • Fast Pre-Router: Deterministic ticker resolution (2,630+ NSE stocks) & dock dispatch      │
│ • 4-Layer Cognitive Memory: Working Context ↔ Episodic Recall ↔ Semantic Reflection         │
│ • Intent Classifier & Parser: Cloudflare Workers AI ↔ Groq allam-2-7b ↔ Gemini Flash        │
├─────────────────────────────────────────────────────────────────────────────────────────────┤
│ Autonomous Dispatchers & Core Domains:                                                      │
│  ├── Academic: Timetable Sync, 75% Attendance Safeguard, 15m Leave Alert + Weather Advisory  │
│  ├── Workspace: Dual-Account Google Calendar, Classroom, Gmail & Tasks                      │
│  ├── Equities: Institutional Deep Research, NSE Delivery Radar, Earnings Triage, Active IPOs │
│  └── Synthesis: British Neural Speech (en-GB-RyanNeural) + Sci-Fi Activation Chime          │
├─────────────────────────────────────────────────────────────────────────────────────────────┤
│ Infrastructure: Starlette HTTP Server (/health, /webhook) + APScheduler Background Daemons  │
└─────────────────────────────────────────────────────────────────────────────────────────────┘
```

---

## 🌟 Key Pillars & Capabilities

### 1. 🧠 4-Layer Cognitive Memory & Neural Persona
* **Working Memory:** Maintains immediate short-term context across conversation turns for dynamic pronoun and anaphora resolution (*"research HAL" &rarr; "what are its margins?" &rarr; "set an alert on it"*).
* **Episodic Recall:** Vector similarity retrieval over past user interactions, preferences, notes, and academic context.
* **Semantic Reflection:** Periodically consolidates recurring habits, rules, and core directives into persistent knowledge.
* **J.A.R.V.I.S. Persona:** Articulate, unflappable British butler persona addressed to *"sir"*, synthesized via Microsoft Edge-TTS (`en-GB-RyanNeural`) prepended with an authentic sci-fi activation chime.

### 2. 🎙️ Two-Way Voice, AI Condenser & Daily Briefings
* **Sub-Second Voice Interaction:** Send voice notes while walking across campus. Groq Whisper (`whisper-large-v3-turbo`) transcribes audio in ~0.25s, routes your intent, executes actions, and responds with a neural voice message.
* **Voice Note Condenser:** If you dictate rambling thoughts, spontaneous brainstorms, or unorganized spoken notes, Jarvis automatically distills them into structured bullet points and logs them into Google Tasks or cognitive memory.
* **Morning Radio Briefing (06:30 IST):** Autonomous radio-style briefing detailing today's lectures, pending assignments, unread emails, and live Patiala weather with rain probability.
* **Evening Debrief (20:00 IST):** Forward-looking nightcap covering tomorrow's earliest commitments, preparation requirements, and commute transit warnings.

### 3. 🎓 Academic & Timetable Safeguards (Thapar University)
* **75% Attendance Safeguard (`/attendance`):**
  * Tracks all 7 semester courses: *Operating Systems*, *Data Structures & Algorithms*, *Electronics Devices & Circuits*, *Discrete Mathematics*, *Object Oriented Programming Practices*, *AI For Engineers*, and *Aptitude Skills Building*.
  * Computes exact **safe bunks remaining** or **consecutive lectures required** to recover from shortages.
  * Dynamically queries your Google Calendar timetable to display today's specific lecture timeline and current date status (e.g. `Weekend — No university lectures scheduled`).
  * Check-in poll executes strictly **Monday–Friday at 17:05 IST** (after classes finish) and skips days without academic sessions.
* **15-Minute "Time-to-Leave" Class Alerts with Weather Advisory:**
  * Background cron inspects your calendar 10–18 minutes before class start times.
  * Sends an alert with class venue (e.g., *LT10, B304, C328*) accompanied by live Open-Meteo weather and transit recommendations.
* **Dual-Account Google Workspace Integration:** Seamlessly aggregates Personal (`token.json`) and University (`token_thapar.json`) accounts.
* **Google Classroom Actionable Deadlines (`/classes`):** Filters out past submissions and displays only actionable coursework with future due dates.
* **Exam Schedule Photo OCR:** Upload a smartphone photo of your university date-sheet; Jarvis uses Gemini Vision to extract dates, preview the schedule, and populate Google Calendar upon confirmation.
* **Intelligent Calendar Conflict Guard:** Intercepts overlapping bookings, highlights conflicting lectures, and auto-suggests the next open daytime gap.

### 4. 📈 Institutional Equity Research & Financial Intelligence
* **Institutional Stock Deep Research (`/deepdive <stock>` / `/research <stock>`):**
  * Ingests all **2,630+ active NSE companies** from official `EQUITY_L.csv` (7,952 aliases & security codes).
  * Direct ticker validation prevents fuzzy confusion (e.g., `CUMMINSIND` correctly resolves to Cummins India rather than IndusInd Bank).
  * Comprehensive research dossier featuring:
    * Live LTP, Day Change, and % Gain.
    * 52-Week High & Low range dynamics with visual bar and % proximity to All-Time High / 52-week low.
    * Last Reported Quarterly Financial Results (Revenue, Operating Margin %, PAT YoY growth).
    * Next Scheduled Earnings Declaration Date with countdown in days.
    * Future Outlook catalysts, growth drivers, guidance, and sector risks.
* **Strict Active IPO Radar & Autonomous Listing Day Alerts (`/ipo`):**
  * **Strict Active Filter:** Scrapes InvestorGain and suppresses all closed or already-listed shares; shows **only** IPOs currently open for retail bidding or upcoming.
  * **Weekend & Market Break Intelligence:** When the primary market is closed, explicitly indicates that retail bidding is closed and showcases **Recent Issues Awaiting Exchange Listing** (with expected listing dates and GMPs).
  * **Application Lifecycle Tracker (`/ipo apply <company>` or *"I applied for <company>"*):**
    * Automatically pulls issue price, lot size, and listing date into `ipo_applications.json`.
    * **10:00 AM Listing Day Alert:** Detects debut trading, announces official listing price, listing gains (`₹` and `+X.XX%`), and net profit per lot.
    * **15:45 Market Close Performance Report:** Delivers closing price, day return vs. issue price, and final lot gain, archiving position as `LISTED`.
* **NSE Stealth Institutional Delivery Screener (`/stealth [stock]`):**
  * Ingests official daily NSE Bhavcopy delivery reports.
  * Identifies true institutional accumulation (>60% physical demat delivery, >₹15 Cr turnover) versus day-trading churn.
  * Autonomous market-wide scan executes daily at 18:30 IST.
* **Autonomous Quarterly Earnings Triage (`/earnings [stock]`):**
  * Evaluates Revenue, Operating Margin, and Consensus Beat/Miss % across custom watchlists (`/watchlist add|remove`).
  * T-1 notification dispatched at 17:30 IST on the eve of earnings declarations.
* **High-Conviction Investment Theses & Portfolio (`/thesis`):**
  * Track conviction ideas with entry price, target price, stop-loss, and fundamental catalysts.
  * 5-minute background polling triggers immediate alerts if a target or stop-loss is breached.
* **Pre-Market Radar (09:00 IST Weekdays):**
  * Morning macroeconomic intelligence debriefing Nifty, GIFT Nifty, crude, USD/INR, and institutional FII/DII positioning before market open.

### 5. ⚡ One-Tap Command Dock (`/dock`)
* Persistent Telegram `ReplyKeyboardMarkup` provides single-tap access to primary operations without typing:
  * `📊 Market Snapshot`
  * `🎓 Today's Schedule`
  * `📝 Tasks`
  * `💼 Theses & Portfolio`
  * `🧠 Memory`
  * `🎙️ Morning Briefing`

---

## 💻 Complete Slash Command Directory

| Command | Category | Description | Example Usage |
| :--- | :--- | :--- | :--- |
| `/start` | System | Initialize assistant & activate One-Tap Command Dock | `/start` |
| `/dock` | System | Toggle persistent 1-tap mobile keyboard dock | `/dock` |
| `/help` | System | Interactive multi-category help documentation | `/help` |
| `/status` | System | Diagnostics, API connectivity & engine health | `/status` |
| `/morning` | Briefings | On-demand Morning Voice Briefing & Radio Report | `/morning` |
| `/evening` | Briefings | On-demand Evening Debrief & Tomorrow's Agenda | `/evening` |
| `/schedule` | Academic | Today's university timetable & agenda preview | `/schedule` |
| `/attendance`| Academic | Thapar 75% attendance safeguard & safe bunks | `/attendance` |
| `/classes` | Academic | Unsubmitted Google Classroom assignments | `/classes` |
| `/tasks` | Workspace| Google Tasks list with `[Done]` & `[Snooze 24h]` | `/tasks` |
| `/emails` | Workspace| Priority unread emails across Personal & Thapar | `/emails` |
| `/weather` | Utility | Real-time weather, forecast & rain probability | `/weather` or `/weather Delhi` |
| `/news` | Utility | Live tech, market & AI headlines radar | `/news` |
| `/search` | Utility | Free web search via DuckDuckGo | `/search quantum computing news` |
| `/memory` | Cognitive| View active 4-layer cognitive memory & reflection | `/memory` |
| `/forget` | Cognitive| Clear conversation working memory & context buffer| `/forget` |
| `/deepdive` | Equities | Institutional equity research dossier & outlook | `/deepdive HAL` or `/research RELIANCE` |
| `/ipo` | Equities | Active open IPOs, awaiting listings & my applied | `/ipo`, `/ipo awaiting`, `/ipo applied` |
| `/market` | Equities | Nifty, Sensex, Bank Nifty & sector snapshot | `/market` |
| `/stock` | Equities | Live quote, valuation ratios & company overview | `/stock INFY` or `/stock Tata Motors` |
| `/stealth` | Equities | NSE Bhavcopy institutional demat accumulation | `/stealth` or `/stealth HDFCBANK` |
| `/earnings`| Equities | Autonomous quarterly financial results triage | `/earnings TCS` or `/earnings` |
| `/watchlist`| Equities | Manage personal earnings triage watchlist | `/watchlist add HAL, BEL, TITAN` |
| `/thesis` | Equities | Investment thesis portfolio & stop-loss radar | `/thesis new INFY 1850 2100 1750 Cloud growth` |
| `/alerts` | Equities | 5-minute price target and volatility alerts | `/alerts` or `/alerts cancel alt_1` |

---

## ⚡ Technology Stack & Zero-Cost Architecture

Every service utilized is 100% free with no paid subscriptions or credit card requirements:

| Component | Provider / Technology | Pricing & Free Tier Limits |
| :--- | :--- | :--- |
| **Interface** | Telegram Bot API (`python-telegram-bot` v22) | 100% Free Unlimited |
| **Speech-to-Text** | Groq Whisper Large v3 Turbo | Free Tier (2,000 req/day, ~0.25s speed) |
| **Text-to-Speech** | Microsoft Edge-TTS (`en-GB-RyanNeural`) | 100% Free Unlimited |
| **AI LLM Cascade** | Cloudflare Workers AI &rarr; Groq (`allam-2-7b`) &rarr; Gemini Flash | 100% Free Tiers with automatic fallback |
| **Workspace Integration** | Google Calendar, Classroom, Gmail & Tasks API | 100% Free OAuth 2.0 |
| **Weather & Geocoding** | Open-Meteo API | 100% Free (10,000 req/day, no key) |
| **Live Web Search** | DuckDuckGo Search (`ddgs`) | 100% Free Unlimited |
| **Equity Market Data** | Yahoo Finance (`yfinance`) + Official NSE India Bhavcopy | 100% Free Public Market Data |
| **IPO & GMP Radar** | InvestorGain Live Intelligence Scraper | 100% Free Web Intelligence |
| **Hosting & Daemons** | Render.com Web Service + UptimeRobot keep-alive | 100% Free (No Credit Card Required) |

---

## 📁 Repository Structure

```text
.
├── ai/
│   ├── gemini_client.py       # Multi-provider LLM fallback cascade (Cloudflare/Groq/Gemini/Cerebras)
│   ├── prompts.py             # J.A.R.V.I.S. system prompts, intent parser & briefing templates
│   └── stt.py                 # Groq Whisper speech-to-text pipeline
├── bot/
│   ├── handlers.py            # Telegram slash commands, callbacks, voice & photo handlers
│   ├── middleware.py          # Security authorization decorator (TELEGRAM_CHAT_ID whitelisting)
│   └── router.py              # Fast deterministic pre-router & AI intent dispatcher
├── google_services/
│   ├── auth.py                # Dual-account OAuth 2.0 token loader & auto-refresher
│   ├── calendar_service.py    # Timetable agenda, conflict detection & daytime gap suggestions
│   ├── classroom_service.py   # Coursework discovery & unsubmitted assignment filtering
│   ├── gmail_service.py       # Dual-account unread priority email triage
│   └── tasks_service.py       # Task creation, completion & 24h snoozing
├── reports/
│   ├── morning.py             # Morning radio-style briefing generation pipeline
│   └── evening.py             # Evening preparatory debrief pipeline
├── scheduler/
│   └── jobs.py                # APScheduler cron triggers, leave alerts & market checks
├── tts/
│   └── speech.py              # Edge-TTS audio synthesis & activation chime prepending
├── utils/
│   ├── attendance.py          # Thapar 75% attendance margin engine & calendar timetable sync
│   ├── deep_research.py       # Institutional equity research dossier engine (2,630+ NSE stocks)
│   ├── earnings.py            # Autonomous quarterly financial results triage & watchlist
│   ├── finance.py             # Market snapshot, stock detail, fuzzy resolver & pre-market radar
│   ├── health.py              # /health Starlette endpoint for 24/7 uptime keep-alive
│   ├── ipo.py                 # Filtered active IPO radar, application tracker & listing day alerts
│   ├── logger.py              # Loguru structured logging with rotation
│   ├── memory.py              # 4-Layer Cognitive Vector Memory & Reflection System
│   ├── news.py                # Tech, startup & finance news scraper
│   ├── price_alerts.py        # 5-minute persistent price target & volatility alerts
│   ├── retry.py               # Exponential backoff and retry decorators
│   ├── search.py              # 100% free DuckDuckGo live web search
│   ├── stealth_delivery.py    # Official NSE Bhavcopy deliverable volume institutional radar
│   ├── thesis.py              # Investment thesis tracker with live P&L and stop-loss monitoring
│   └── weather.py             # Open-Meteo real-time weather & rain forecast
├── assets/
│   └── jarvis_chime.wav       # Authentic sci-fi acoustic chime prepended to voice notes
├── auth_setup.py              # Local browser-based Google OAuth token generation utility
├── config.py                  # Environment loader, Base64 credential restorer & validator
├── Dockerfile                 # Production Debian container with FFmpeg & Python 3.12
├── render.yaml                # Render Infrastructure-as-Code deployment blueprint
└── requirements.txt           # Pinned production dependencies
```

---

## 🚀 24/7 Cloud Deployment Guide (Render + UptimeRobot)

Deploy J.A.R.V.I.S. to the cloud in under 10 minutes for zero cost:

### 1. Perform One-Time Local OAuth Setup
Generate your personal and university Google OAuth tokens locally:
```powershell
# 1. Authorize Personal Account (Default)
python auth_setup.py

# 2. Authorize University Account (Optional Thapar Account)
python auth_setup.py --thapar
```

### 2. Export Base64 Credential Strings
To keep tokens persistent across headless cloud container restarts without commiting credentials to Git, run:
```powershell
python -c "
import base64
for name, path in [('GOOGLE_CREDENTIALS_B64', 'credentials/credentials.json'), ('GOOGLE_TOKEN_B64', 'credentials/token.json'), ('GOOGLE_THAPAR_TOKEN_B64', 'credentials/token_thapar.json')]:
    try:
        with open(path, 'rb') as f:
            print(f'{name}={base64.b64encode(f.read()).decode()}\n')
    except FileNotFoundError:
        pass
"
```

### 3. Deploy Docker Web Service on Render
1. Create a free account on [Render.com](https://render.com) (no credit card required).
2. Click **New +** &rarr; **Web Service** &rarr; Connect this GitHub repository.
3. Configure the service:
   * **Runtime:** `Docker`
   * **Instance Type:** `Free`
4. Add your Environment Variables (see [table below](#-configuration--environment-variables)).
5. Click **Create Web Service**. Render builds the Docker container and launches J.A.R.V.I.S.

### 4. Enable 24/7 Keep-Alive via UptimeRobot
Render free-tier containers go to sleep after 15 minutes of inbound HTTP inactivity. To keep J.A.R.V.I.S. awake 24/7 forever:
1. Register on [UptimeRobot.com](https://uptimerobot.com) (100% free).
2. Create an **HTTP(s) Monitor**:
   * **Monitor Type:** `HTTP(s)`
   * **Friendly Name:** `JARVIS Assistant`
   * **URL:** `https://<your-render-app-name>.onrender.com/health`
   * **Monitoring Interval:** `Every 10 minutes`
3. Every 10 minutes, UptimeRobot pings the `/health` endpoint, resetting Render's idle timer and ensuring continuous 24/7 execution.

---

## ⚙️ Configuration & Environment Variables

Configure these settings in your local `.env` file or Render dashboard:

| Variable | Required | Default | Purpose |
| :--- | :--- | :--- | :--- |
| `TELEGRAM_BOT_TOKEN` | **Yes** | — | Bot token from [@BotFather](https://t.me/BotFather) |
| `TELEGRAM_CHAT_ID` | **Yes** | — | Your numeric Telegram user ID (security whitelist) |
| `GROQ_API_KEY` | **Yes** | — | Free key from [console.groq.com](https://console.groq.com) |
| `CLOUDFLARE_ACCOUNT_ID` | Optional | — | Free Cloudflare Workers AI Account ID |
| `CLOUDFLARE_API_TOKEN` | Optional | — | Free Cloudflare Workers AI API Token |
| `GEMINI_API_KEY` | Optional | — | Google AI Studio key (powers photo OCR & fallback) |
| `AI_PROVIDER_ORDER` | Optional | `cloudflare,groq,gemini` | Comma-separated LLM provider hierarchy |
| `USER_CITY` | Optional | `Patiala` | City for Open-Meteo forecasts |
| `TIMEZONE` | Optional | `Asia/Kolkata` | Timezone for briefings, alerts, and calendar |
| `MORNING_REPORT_HOUR` | Optional | `6` | Hour for Morning Voice Briefing (0–23) |
| `MORNING_REPORT_MINUTE`| Optional | `30` | Minute for Morning Voice Briefing (0–59) |
| `EVENING_REPORT_HOUR` | Optional | `20` | Hour for Evening Debrief (0–23) |
| `EVENING_REPORT_MINUTE`| Optional | `0` | Minute for Evening Debrief (0–59) |
| `TTS_VOICE` | Optional | `en-GB-RyanNeural` | Microsoft Edge-TTS voice identifier |
| `GOOGLE_CREDENTIALS_B64`| In Cloud | — | Base64-encoded `credentials.json` |
| `GOOGLE_TOKEN_B64` | In Cloud | — | Base64-encoded personal `token.json` |
| `GOOGLE_THAPAR_TOKEN_B64`| Optional | — | Base64-encoded university `token_thapar.json` |

---

## 🔒 Security & Privacy Safeguards

- **Owner-Only Whitelisting:** Every incoming message, callback, and command is verified against `TELEGRAM_CHAT_ID`. Messages from any other Telegram user are silently dropped and logged.
- **Zero Credentials in Version Control:** `.env`, `credentials/`, `token.json`, and local data caches (`data/attendance.json`, `data/ipo_applications.json`) are strictly ignored via [`.gitignore`](.gitignore).
- **In-Memory Credential Reconstitution:** In cloud deployments, base64 environment variables are reconstituted directly into memory and verified during startup.
- **Sandboxed Execution:** Background jobs run strictly within isolated exception guards; an error in one provider or task cannot crash the main assistant process.

---

<div align="center">
  <b>Built with precision for autonomous operation.</b><br>
  <i>"At your service, sir."</i>
</div>
