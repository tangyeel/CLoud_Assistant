"""
ai/gemini_client.py — High-Resilience Lightweight AI Fallback Cascade.
Supports Groq, OpenRouter, Cloudflare Workers AI, NVIDIA NIM, Cerebras, Gemini, and Custom LLM.
Prioritizes ultra-fast 3B–8B models to guarantee massive rate limits and instant responses.
"""
import json
import re
import httpx
from config import (
    AI_PROVIDER_ORDER,
    GROQ_API_KEY,
    GROQ_MODEL,
    OPENROUTER_API_KEY,
    OPENROUTER_MODEL,
    CLOUDFLARE_ACCOUNT_ID,
    CLOUDFLARE_API_TOKEN,
    CLOUDFLARE_MODEL,
    NVIDIA_API_KEY,
    NVIDIA_MODEL,
    CEREBRAS_API_KEY,
    CEREBRAS_MODEL,
    GEMINI_API_KEY,
    GEMINI_MODEL,
    CUSTOM_LLM_API_KEY,
    CUSTOM_LLM_BASE_URL,
    CUSTOM_LLM_MODEL,
)
from utils.logger import logger
from utils.retry import retry_on_failure

# ─── 1. Groq Setup ─────────────────────────────────────────────────────
groq_client = None
if GROQ_API_KEY:
    try:
        from groq import Groq
        groq_client = Groq(api_key=GROQ_API_KEY)
        logger.info(f"Initialized Groq client (Primary model: '{GROQ_MODEL}').")
    except Exception as e:
        logger.warning(f"Could not initialize Groq SDK: {e}")

# ─── 2. Gemini Setup ───────────────────────────────────────────────────
gemini_available = False
if GEMINI_API_KEY:
    try:
        import google.generativeai as genai
        genai.configure(api_key=GEMINI_API_KEY)
        gemini_available = True
        logger.info("Initialized Google Gemini SDK.")
    except Exception as e:
        logger.warning(f"Could not initialize Gemini SDK: {e}")


# ─── Provider Implementations ──────────────────────────────────────────

def _call_groq(prompt: str, system_instruction: str, as_json: bool = False) -> str | dict | None:
    """1. Groq (Fast 7B/8B/20B inference)."""
    if not groq_client:
        return None

    candidate_models = [GROQ_MODEL, "allam-2-7b", "openai/gpt-oss-20b", "llama-3.1-8b-instant"]
    seen = set()
    unique_models = [m for m in candidate_models if not (m in seen or seen.add(m))]

    for model in unique_models:
        try:
            messages = []
            if system_instruction:
                messages.append({"role": "system", "content": system_instruction})
            messages.append({"role": "user", "content": prompt})

            kwargs = {
                "messages": messages,
                "model": model,
                "temperature": 0.2 if as_json else 0.7,
            }
            if as_json:
                kwargs["response_format"] = {"type": "json_object"}
            else:
                kwargs["max_tokens"] = 2048

            completion = groq_client.chat.completions.create(**kwargs)
            content = completion.choices[0].message.content
            if not content:
                continue

            if as_json:
                return json.loads(content.strip())
            return content.strip()

        except Exception as e:
            logger.warning(f"Groq [{model}] failed: {e}. Trying next option...")

    return None


def _call_openrouter(prompt: str, system_instruction: str, as_json: bool = False) -> str | dict | None:
    """2. OpenRouter (Free tier 8B models with generous limits)."""
    if not OPENROUTER_API_KEY:
        return None

    candidate_models = [
        OPENROUTER_MODEL,
        "meta-llama/llama-3.1-8b-instruct:free",
        "mistralai/mistral-7b-instruct:free",
        "google/gemini-2.0-flash-lite-preview-02-05:free",
        "qwen/qwen-2.5-7b-instruct:free",
    ]
    seen = set()
    unique_models = [m for m in candidate_models if not (m in seen or seen.add(m))]

    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "HTTP-Referer": "https://github.com/assistant",
        "X-Title": "Personal AI Assistant",
        "Content-Type": "application/json",
    }

    messages = []
    if system_instruction:
        messages.append({"role": "system", "content": system_instruction})
    messages.append({"role": "user", "content": prompt})

    with httpx.Client(timeout=20.0) as client:
        for model in unique_models:
            try:
                payload = {
                    "model": model,
                    "messages": messages,
                    "temperature": 0.2 if as_json else 0.7,
                    "max_tokens": 1024,
                }
                if as_json:
                    payload["response_format"] = {"type": "json_object"}

                response = client.post(
                    "https://openrouter.ai/api/v1/chat/completions",
                    headers=headers,
                    json=payload,
                )

                if response.status_code == 200:
                    data = response.json()
                    content = data["choices"][0]["message"]["content"]
                    if content:
                        logger.info(f"✅ Generated via OpenRouter [{model}]")
                        if as_json:
                            return _extract_json_dict(content)
                        return content.strip()
                else:
                    logger.warning(f"OpenRouter [{model}] HTTP {response.status_code}: {response.text[:100]}")
            except Exception as e:
                logger.warning(f"OpenRouter [{model}] error: {e}")

    return None


def _call_cloudflare(prompt: str, system_instruction: str, as_json: bool = False) -> str | dict | None:
    """3. Cloudflare Workers AI (10,000 requests/day 100% free tier)."""
    if not CLOUDFLARE_ACCOUNT_ID or not CLOUDFLARE_API_TOKEN:
        return None

    candidate_models = [
        CLOUDFLARE_MODEL,
        "@cf/meta/llama-3.2-3b-instruct",
        "@cf/meta/llama-3.2-1b-instruct",
        "@cf/mistral/mistral-7b-instruct-v0.1",
    ]
    seen = set()
    unique_models = [m for m in candidate_models if not (m in seen or seen.add(m))]

    headers = {
        "Authorization": f"Bearer {CLOUDFLARE_API_TOKEN}",
        "Content-Type": "application/json",
    }

    messages = []
    if system_instruction:
        messages.append({"role": "system", "content": system_instruction})
    messages.append({"role": "user", "content": prompt})

    # Use Cloudflare OpenAI-compatible endpoint
    url = f"https://api.cloudflare.com/client/v4/accounts/{CLOUDFLARE_ACCOUNT_ID}/ai/v1/chat/completions"

    with httpx.Client(timeout=25.0) as client:
        for model in unique_models:
            try:
                payload = {
                    "model": model,
                    "messages": messages,
                    "temperature": 0.2 if as_json else 0.7,
                    "max_tokens": 1024,
                }
                if as_json:
                    payload["response_format"] = {"type": "json_object"}

                resp = client.post(url, headers=headers, json=payload)
                if resp.status_code == 200:
                    data = resp.json()
                    content = data["choices"][0]["message"]["content"]
                    if content:
                        logger.info(f"✅ Generated via Cloudflare AI [{model}]")
                        if as_json:
                            return _extract_json_dict(content)
                        return content.strip()
                else:
                    logger.warning(f"Cloudflare [{model}] HTTP {resp.status_code}: {resp.text[:100]}")
            except Exception as e:
                logger.warning(f"Cloudflare [{model}] failed: {e}")

    return None


def _call_nvidia(prompt: str, system_instruction: str, as_json: bool = False) -> str | dict | None:
    """4. NVIDIA NIM (Free inference credits for Llama 3.1 8B)."""
    if not NVIDIA_API_KEY:
        return None

    candidate_models = [
        NVIDIA_MODEL,
        "meta/llama-3.1-8b-instruct",
        "mistralai/mistral-7b-instruct-v0.3",
    ]
    seen = set()
    unique_models = [m for m in candidate_models if not (m in seen or seen.add(m))]

    headers = {
        "Authorization": f"Bearer {NVIDIA_API_KEY}",
        "Content-Type": "application/json",
    }

    messages = []
    if system_instruction:
        messages.append({"role": "system", "content": system_instruction})
    messages.append({"role": "user", "content": prompt})

    with httpx.Client(timeout=25.0) as client:
        for model in unique_models:
            try:
                payload = {
                    "model": model,
                    "messages": messages,
                    "temperature": 0.2 if as_json else 0.7,
                    "max_tokens": 1024,
                }
                if as_json:
                    payload["response_format"] = {"type": "json_object"}

                resp = client.post(
                    "https://integrate.api.nvidia.com/v1/chat/completions",
                    headers=headers,
                    json=payload,
                )
                if resp.status_code == 200:
                    data = resp.json()
                    content = data["choices"][0]["message"]["content"]
                    if content:
                        logger.info(f"✅ Generated via NVIDIA NIM [{model}]")
                        if as_json:
                            return _extract_json_dict(content)
                        return content.strip()
                else:
                    logger.warning(f"NVIDIA [{model}] HTTP {resp.status_code}: {resp.text[:100]}")
            except Exception as e:
                logger.warning(f"NVIDIA [{model}] failed: {e}")

    return None


def _call_cerebras(prompt: str, system_instruction: str, as_json: bool = False) -> str | dict | None:
    """5. Cerebras Cloud (High-speed 2,000 tokens/sec Llama 3.1 8B)."""
    if not CEREBRAS_API_KEY:
        return None

    headers = {
        "Authorization": f"Bearer {CEREBRAS_API_KEY}",
        "Content-Type": "application/json",
    }

    messages = []
    if system_instruction:
        messages.append({"role": "system", "content": system_instruction})
    messages.append({"role": "user", "content": prompt})

    try:
        with httpx.Client(timeout=15.0) as client:
            payload = {
                "model": CEREBRAS_MODEL,
                "messages": messages,
                "temperature": 0.2 if as_json else 0.7,
            }
            if as_json:
                payload["response_format"] = {"type": "json_object"}

            resp = client.post(
                "https://api.cerebras.ai/v1/chat/completions",
                headers=headers,
                json=payload,
            )
            if resp.status_code == 200:
                data = resp.json()
                content = data["choices"][0]["message"]["content"]
                if content:
                    logger.info(f"✅ Generated via Cerebras [{CEREBRAS_MODEL}]")
                    if as_json:
                        return _extract_json_dict(content)
                    return content.strip()
    except Exception as e:
        logger.warning(f"Cerebras call failed: {e}")

    return None


def _call_gemini(prompt: str, system_instruction: str, as_json: bool = False) -> str | dict | None:
    """6. Google Gemini (Lightweight 8B flash)."""
    if not gemini_available:
        return None

    try:
        import google.generativeai as genai
        models_to_try = [GEMINI_MODEL, "gemini-1.5-flash-8b", "gemini-2.5-flash"]
        seen = set()
        unique = [m for m in models_to_try if not (m in seen or seen.add(m))]

        for m_name in unique:
            try:
                kwargs = {
                    "model_name": m_name,
                    "generation_config": {"temperature": 0.2 if as_json else 0.7},
                }
                if system_instruction:
                    kwargs["system_instruction"] = system_instruction

                model = genai.GenerativeModel(**kwargs)
                res = model.generate_content(prompt)
                if res and res.text:
                    logger.info(f"✅ Generated via Gemini [{m_name}]")
                    if as_json:
                        return _extract_json_dict(res.text)
                    return res.text.strip()
            except Exception as e:
                logger.warning(f"Gemini [{m_name}] failed: {e}")
    except Exception as e:
        logger.warning(f"Gemini execution error: {e}")

    return None


def _call_custom_llm(prompt: str, system_instruction: str, as_json: bool = False) -> str | dict | None:
    """7. Custom / Local OpenAI-compatible endpoint (Orca, Together, Ollama, vLLM)."""
    if not CUSTOM_LLM_BASE_URL:
        return None

    base_url = CUSTOM_LLM_BASE_URL.rstrip("/")
    endpoint = f"{base_url}/chat/completions"

    headers = {"Content-Type": "application/json"}
    if CUSTOM_LLM_API_KEY:
        headers["Authorization"] = f"Bearer {CUSTOM_LLM_API_KEY}"

    messages = []
    if system_instruction:
        messages.append({"role": "system", "content": system_instruction})
    messages.append({"role": "user", "content": prompt})

    try:
        with httpx.Client(timeout=30.0) as client:
            payload = {
                "model": CUSTOM_LLM_MODEL or "default",
                "messages": messages,
                "temperature": 0.2 if as_json else 0.7,
            }
            if as_json:
                payload["response_format"] = {"type": "json_object"}

            resp = client.post(endpoint, headers=headers, json=payload)
            if resp.status_code == 200:
                data = resp.json()
                content = data["choices"][0]["message"]["content"]
                if content:
                    logger.info("✅ Generated via Custom LLM endpoint")
                    if as_json:
                        return _extract_json_dict(content)
                    return content.strip()
    except Exception as e:
        logger.warning(f"Custom LLM endpoint failed: {e}")

    return None


def _extract_json_dict(raw: str) -> dict:
    """Parse JSON with cleaning and regex extraction."""
    cleaned = raw.strip()
    if cleaned.startswith("```json"):
        cleaned = cleaned[7:]
    elif cleaned.startswith("```"):
        cleaned = cleaned[3:]
    if cleaned.endswith("```"):
        cleaned = cleaned[:-3]
    cleaned = cleaned.strip()

    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", cleaned, re.DOTALL)
        if match:
            return json.loads(match.group(0))
        raise


# ─── Provider Registry & Dynamic Hierarchy ─────────────────────────────

PROVIDER_MAP = {
    "cloudflare": (
        "Cloudflare Workers AI",
        CLOUDFLARE_MODEL,
        _call_cloudflare,
        lambda: bool(CLOUDFLARE_ACCOUNT_ID and CLOUDFLARE_API_TOKEN),
    ),
    "groq": (
        "Groq",
        GROQ_MODEL,
        _call_groq,
        lambda: bool(GROQ_API_KEY),
    ),
    "gemini": (
        "Google Gemini",
        GEMINI_MODEL,
        _call_gemini,
        lambda: bool(gemini_available),
    ),
    "cerebras": (
        "Cerebras Cloud",
        CEREBRAS_MODEL,
        _call_cerebras,
        lambda: bool(CEREBRAS_API_KEY),
    ),
    "nvidia": (
        "NVIDIA NIM",
        NVIDIA_MODEL,
        _call_nvidia,
        lambda: bool(NVIDIA_API_KEY),
    ),
    "openrouter": (
        "OpenRouter",
        OPENROUTER_MODEL,
        _call_openrouter,
        lambda: bool(OPENROUTER_API_KEY),
    ),
    "custom": (
        "Custom LLM",
        CUSTOM_LLM_MODEL or "default",
        _call_custom_llm,
        lambda: bool(CUSTOM_LLM_BASE_URL),
    ),
}


def get_active_hierarchy() -> list[dict]:
    """Return ordered list of providers and their current configuration status."""
    hierarchy = []
    for pid in AI_PROVIDER_ORDER:
        if pid not in PROVIDER_MAP:
            continue
        display_name, model_name, _, is_active = PROVIDER_MAP[pid]
        hierarchy.append({
            "id": pid,
            "name": display_name,
            "model": model_name,
            "active": is_active(),
        })
    return hierarchy


# ─── Public Cascade Functions ──────────────────────────────────────────

@retry_on_failure(max_retries=2, base_delay=1.0)
def generate_text(prompt: str, system_instruction: str = "") -> str:
    """
    Generate text using strict stability hierarchy:
    Tries each configured provider in order of AI_PROVIDER_ORDER.
    """
    attempted = []
    for pid in AI_PROVIDER_ORDER:
        if pid not in PROVIDER_MAP:
            continue
        name, model, func, is_configured = PROVIDER_MAP[pid]
        if not is_configured():
            continue

        try:
            res = func(prompt, system_instruction, as_json=False)
            if res:
                return res
            attempted.append(f"{name} ({model}) - empty response")
        except Exception as e:
            logger.warning(f"⚠️ Hierarchy fallback: {name} failed ({e}). Proceeding to next provider...")
            attempted.append(f"{name} ({model}) - {e}")

    raise RuntimeError(f"All configured AI providers failed. Attempts: {'; '.join(attempted)}")


@retry_on_failure(max_retries=2, base_delay=1.0)
def generate_json(prompt: str, system_instruction: str = "") -> dict:
    """
    Generate structured JSON using strict stability hierarchy.
    """
    attempted = []
    for pid in AI_PROVIDER_ORDER:
        if pid not in PROVIDER_MAP:
            continue
        name, model, func, is_configured = PROVIDER_MAP[pid]
        if not is_configured():
            continue

        try:
            res = func(prompt, system_instruction, as_json=True)
            if isinstance(res, dict):
                return res
            attempted.append(f"{name} ({model}) - non-dict JSON")
        except Exception as e:
            logger.warning(f"⚠️ Hierarchy fallback (JSON): {name} failed ({e}). Proceeding to next provider...")
            attempted.append(f"{name} ({model}) - {e}")

    raise RuntimeError(f"All configured AI providers failed to generate valid JSON. Attempts: {'; '.join(attempted)}")
