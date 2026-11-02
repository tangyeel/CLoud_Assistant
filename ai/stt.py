"""
ai/stt.py — High-speed Speech-to-Text using Groq Whisper (whisper-large-v3-turbo).
Transcribes Telegram voice notes (.ogg / .oga) in ~0.25 seconds with 100% free tier.
"""
import os
from groq import Groq
from config import GROQ_API_KEY
from utils.logger import logger
from utils.retry import retry_on_failure


_groq_client = None

def _get_client() -> Groq | None:
    global _groq_client
    if _groq_client is None and GROQ_API_KEY:
        try:
            _groq_client = Groq(api_key=GROQ_API_KEY)
        except Exception as e:
            logger.error(f"Failed to initialize Groq client for STT: {e}")
    return _groq_client


@retry_on_failure(max_retries=2, base_delay=1.0)
def transcribe_audio(audio_path: str) -> str:
    """
    Transcribe an audio file (.oga, .ogg, .mp3, .wav) using Groq Whisper.

    Args:
        audio_path: Local filesystem path to the audio file.

    Returns:
        Transcribed plain text string, or empty string if failed.
    """
    if not os.path.exists(audio_path):
        logger.warning(f"Audio file not found: {audio_path}")
        return ""

    client = _get_client()
    if not client:
        logger.warning("Groq client unavailable for STT. Ensure GROQ_API_KEY is configured.")
        return ""

    filename = os.path.basename(audio_path)
    logger.debug(f"Transcribing audio file '{filename}' with Groq Whisper...")

    try:
        with open(audio_path, "rb") as f:
            transcription = client.audio.transcriptions.create(
                file=(filename, f),
                model="whisper-large-v3-turbo",
                response_format="text",
                temperature=0.0,
            )

        text = str(transcription).strip()
        logger.info(f"🎙️ Groq Whisper transcription complete: '{text[:60]}...'")
        return text

    except Exception as e:
        logger.error(f"Groq Whisper transcription failed on {filename}: {e}")
        # Try fallback to whisper-large-v3
        try:
            with open(audio_path, "rb") as f:
                transcription = client.audio.transcriptions.create(
                    file=(filename, f),
                    model="whisper-large-v3",
                    response_format="text",
                )
            text = str(transcription).strip()
            logger.info(f"🎙️ Whisper-v3 fallback transcription: '{text[:60]}...'")
            return text
        except Exception as err2:
            logger.error(f"Whisper fallback also failed: {err2}")
            return ""
