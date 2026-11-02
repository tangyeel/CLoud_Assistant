"""
config.py — Centralized configuration loader for the Autonomous AI Personal Assistant.
Loads and validates environment variables.
"""
import os
import sys
import base64
from pathlib import Path
from dotenv import load_dotenv

# Load .env file from project root
load_dotenv()


def _get_env(var_name: str, default: str | None = None, required: bool = False) -> str:
    """Retrieve an environment variable with optional default or requirement check."""
    value = os.getenv(var_name, default)
    if required and (value is None or value == ""):
        print(f"❌ CONFIG ERROR: Missing required environment variable '{var_name}'.")
        return ""
    return value or ""


# --- Telegram Configuration ---
TELEGRAM_BOT_TOKEN: str = _get_env("TELEGRAM_BOT_TOKEN", default="")
_chat_id_raw = _get_env("TELEGRAM_CHAT_ID", default="0")
try:
    import re
    _match = re.search(r"-?\d+", str(_chat_id_raw))
    TELEGRAM_CHAT_ID: int = int(_match.group(0)) if _match else 0
except Exception:
    TELEGRAM_CHAT_ID = 0

TELEGRAM_WEBHOOK_URL: str = os.getenv("TELEGRAM_WEBHOOK_URL", "")

# --- Google OAuth Credentials Paths ---
BASE_DIR = Path(__file__).resolve().parent
GOOGLE_CREDENTIALS_PATH: str = os.getenv("GOOGLE_CREDENTIALS_PATH", str(BASE_DIR / "credentials" / "credentials.json"))
GOOGLE_TOKEN_PATH: str = os.getenv("GOOGLE_TOKEN_PATH", str(BASE_DIR / "credentials" / "token.json"))
GOOGLE_THAPAR_TOKEN_PATH: str = os.getenv("GOOGLE_THAPAR_TOKEN_PATH", str(BASE_DIR / "credentials" / "token_thapar.json"))

# Base64 strings for headless cloud environments (Render, Hugging Face, Zeabur)
GOOGLE_CREDENTIALS_B64: str = os.getenv("GOOGLE_CREDENTIALS_B64", "")
GOOGLE_TOKEN_B64: str = os.getenv("GOOGLE_TOKEN_B64", "")
GOOGLE_THAPAR_TOKEN_B64: str = os.getenv("GOOGLE_THAPAR_TOKEN_B64", "")

# Restore files from base64 if provided and target files do not exist
if GOOGLE_CREDENTIALS_B64 and not os.path.exists(GOOGLE_CREDENTIALS_PATH):
    try:
        os.makedirs(os.path.dirname(GOOGLE_CREDENTIALS_PATH), exist_ok=True)
        with open(GOOGLE_CREDENTIALS_PATH, "wb") as f:
            f.write(base64.b64decode(GOOGLE_CREDENTIALS_B64))
    except Exception as e:
        print(f"⚠️ Failed to decode GOOGLE_CREDENTIALS_B64: {e}")

if GOOGLE_TOKEN_B64 and not os.path.exists(GOOGLE_TOKEN_PATH):
    try:
        os.makedirs(os.path.dirname(GOOGLE_TOKEN_PATH), exist_ok=True)
        with open(GOOGLE_TOKEN_PATH, "wb") as f:
            f.write(base64.b64decode(GOOGLE_TOKEN_B64))
    except Exception as e:
        print(f"⚠️ Failed to decode GOOGLE_TOKEN_B64: {e}")

if GOOGLE_THAPAR_TOKEN_B64 and not os.path.exists(GOOGLE_THAPAR_TOKEN_PATH):
    try:
        os.makedirs(os.path.dirname(GOOGLE_THAPAR_TOKEN_PATH), exist_ok=True)
        with open(GOOGLE_THAPAR_TOKEN_PATH, "wb") as f:
            f.write(base64.b64decode(GOOGLE_THAPAR_TOKEN_B64))
    except Exception as e:
        print(f"⚠️ Failed to decode GOOGLE_THAPAR_TOKEN_B64: {e}")

# --- AI Hierarchy Order ---
# Ordered from most stable/highest uptime down to aggregators
DEFAULT_AI_ORDER = "cloudflare,groq,gemini,cerebras,nvidia,openrouter,custom"
AI_PROVIDER_ORDER: list[str] = [
    p.strip().lower()
    for p in os.getenv("AI_PROVIDER_ORDER", DEFAULT_AI_ORDER).split(",")
    if p.strip()
]
# Primary 1: Groq (Ultra-fast 7B/8B/20B models)
GROQ_API_KEY: str = _get_env("GROQ_API_KEY", default="")
GROQ_MODEL: str = os.getenv("GROQ_MODEL", "allam-2-7b")

# Fallback 2: OpenRouter (Free tier 7B/8B models)
OPENROUTER_API_KEY: str = _get_env("OPENROUTER_API_KEY", default="")
OPENROUTER_MODEL: str = os.getenv("OPENROUTER_MODEL", "meta-llama/llama-3.1-8b-instruct:free")

# Fallback 3: Cloudflare Workers AI (10,000 requests/day 100% free)
CLOUDFLARE_ACCOUNT_ID: str = _get_env("CLOUDFLARE_ACCOUNT_ID", default="")
CLOUDFLARE_API_TOKEN: str = _get_env("CLOUDFLARE_API_TOKEN", default="")
CLOUDFLARE_MODEL: str = os.getenv("CLOUDFLARE_MODEL", "@cf/meta/llama-3.2-3b-instruct")

# Fallback 4: NVIDIA NIM (Free credits for fast Llama 3.1 8B)
NVIDIA_API_KEY: str = _get_env("NVIDIA_API_KEY", default="")
NVIDIA_MODEL: str = os.getenv("NVIDIA_MODEL", "meta/llama-3.1-8b-instruct")

# Fallback 5: Cerebras Cloud (World's fastest inference, free tier 8B)
CEREBRAS_API_KEY: str = _get_env("CEREBRAS_API_KEY", default="")
CEREBRAS_MODEL: str = os.getenv("CEREBRAS_MODEL", "llama3.1-8b")

# Fallback 6: Google Gemini (Lightweight 8B flash)
GEMINI_API_KEY: str = _get_env("GEMINI_API_KEY", default="")
GEMINI_MODEL: str = os.getenv("GEMINI_MODEL", "gemini-1.5-flash-8b")

# Fallback 7: Custom / Local OpenAI-compatible endpoint (Ollama / vLLM / Orca)
CUSTOM_LLM_API_KEY: str = _get_env("CUSTOM_LLM_API_KEY", default="")
CUSTOM_LLM_BASE_URL: str = os.getenv("CUSTOM_LLM_BASE_URL", "")
CUSTOM_LLM_MODEL: str = os.getenv("CUSTOM_LLM_MODEL", "")

# --- Text-to-Speech (Jarvis Voice: British Neural) ---
TTS_VOICE: str = os.getenv("TTS_VOICE", "en-GB-RyanNeural")
TTS_FALLBACK_VOICE: str = os.getenv("TTS_FALLBACK_VOICE", "en-GB-ThomasNeural")
AUDIO_OUTPUT_DIR: str = os.getenv("AUDIO_OUTPUT_DIR", str(BASE_DIR / "audio"))

# --- Location / Weather Configuration ---
USER_CITY: str = os.getenv("USER_CITY", "Patiala")

# Ensure audio directory exists
os.makedirs(AUDIO_OUTPUT_DIR, exist_ok=True)

# --- Scheduler Configuration ---
TIMEZONE: str = os.getenv("TIMEZONE", "Asia/Kolkata")
MORNING_REPORT_HOUR: int = int(os.getenv("MORNING_REPORT_HOUR", "7"))
MORNING_REPORT_MINUTE: int = int(os.getenv("MORNING_REPORT_MINUTE", "30"))
EVENING_REPORT_HOUR: int = int(os.getenv("EVENING_REPORT_HOUR", "21"))
EVENING_REPORT_MINUTE: int = int(os.getenv("EVENING_REPORT_MINUTE", "0"))

# --- Server / Host ---
PORT: int = int(os.getenv("PORT", "8000"))
LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")
LOG_FILE: str = os.getenv("LOG_FILE", str(BASE_DIR / "logs" / "assistant.log"))

# Ensure logs directory exists
os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)

# --- Admin Alerts ---
SEND_ERROR_ALERTS: bool = os.getenv("SEND_ERROR_ALERTS", "true").lower() == "true"

# --- Excluded Classroom Course IDs ---
EXCLUDED_COURSE_IDS: list[str] = [cid.strip() for cid in os.getenv("EXCLUDED_COURSE_IDS", "").split(",") if cid.strip()]

# Allow OAuthLib to accept Google's aliased / remapped scopes
os.environ["OAUTHLIB_RELAX_TOKEN_SCOPE"] = "1"

# --- Google API OAuth Scopes ---
GOOGLE_SCOPES: list[str] = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.modify",
    "https://www.googleapis.com/auth/calendar",
    "https://www.googleapis.com/auth/calendar.events",
    "https://www.googleapis.com/auth/tasks",
    "https://www.googleapis.com/auth/classroom.courses.readonly",
    "https://www.googleapis.com/auth/classroom.student-submissions.me.readonly",
    "https://www.googleapis.com/auth/classroom.announcements.readonly",
]


def validate_config(exit_on_error: bool = False) -> bool:
    """Validate that all mandatory settings are populated."""
    missing = []
    if not TELEGRAM_BOT_TOKEN or TELEGRAM_BOT_TOKEN.startswith("your_"):
        missing.append("TELEGRAM_BOT_TOKEN")
    if not any([GROQ_API_KEY, OPENROUTER_API_KEY, CLOUDFLARE_API_TOKEN, NVIDIA_API_KEY, CEREBRAS_API_KEY, GEMINI_API_KEY, CUSTOM_LLM_API_KEY]):
        missing.append("At least one AI Key (Groq, OpenRouter, Cloudflare, NVIDIA, Cerebras, or Gemini)")

    if not TELEGRAM_CHAT_ID:
        print("ℹ️ Note: TELEGRAM_CHAT_ID is not configured yet.")
        print("   Send /start to your bot in Telegram to see your Chat ID and add it to .env.")

    if missing:
        msg = f"❌ Configuration validation failed! Missing required settings: {', '.join(missing)}"
        print(msg)
        if exit_on_error:
            sys.exit(1)
        return False
    return True
