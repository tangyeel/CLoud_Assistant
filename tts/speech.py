"""
tts/speech.py — Text-to-Speech synthesis using Edge-TTS with gTTS fallback.
Converts text into audio files suitable for Telegram voice notes.
Features subtle authentic J.A.R.V.I.S. futuristic activation chime prepend!
"""
import os
import uuid
import time
import shutil
import subprocess
from pathlib import Path
import edge_tts
from config import TTS_VOICE, TTS_FALLBACK_VOICE, AUDIO_OUTPUT_DIR
from utils.logger import logger

# Ensure output and asset directories exist
os.makedirs(AUDIO_OUTPUT_DIR, exist_ok=True)
BASE_DIR = Path(__file__).resolve().parent.parent
ASSETS_DIR = BASE_DIR / "assets"
os.makedirs(ASSETS_DIR, exist_ok=True)
CHIME_WAV = str(ASSETS_DIR / "jarvis_chime.wav")


def _ensure_chime_exists() -> str | None:
    """Ensure the Jarvis acoustic chime WAV exists; synthesize if missing."""
    if os.path.exists(CHIME_WAV) and os.path.getsize(CHIME_WAV) > 1000:
        return CHIME_WAV

    try:
        import math
        import struct
        import wave
        sample_rate = 44100
        duration = 0.55
        num_samples = int(sample_rate * duration)

        with wave.open(CHIME_WAV, "w") as wav:
            wav.setnchannels(1)
            wav.setsampwidth(2)
            wav.setframerate(sample_rate)

            frames = bytearray()
            for i in range(num_samples):
                t = i / sample_rate
                if t < 0.12:
                    freq = 783.99
                    decay = math.exp(-t * 15.0)
                    sample = 0.45 * math.sin(2 * math.pi * freq * t) * decay
                else:
                    t2 = t - 0.12
                    freq1 = 1046.50
                    freq2 = 2093.00
                    decay = math.exp(-t2 * 7.0)
                    sample = (0.45 * math.sin(2 * math.pi * freq1 * t2) + 0.15 * math.sin(2 * math.pi * freq2 * t2)) * decay

                val = int(max(-1.0, min(1.0, sample)) * 32767)
                frames.extend(struct.pack("<h", val))

            wav.writeframes(frames)
        logger.info(f"Synthesized J.A.R.V.I.S. activation chime at {CHIME_WAV}")
        return CHIME_WAV
    except Exception as e:
        logger.warning(f"Failed to generate chime: {e}")
        return None


def _get_ffmpeg_bin() -> str | None:
    """Find FFmpeg binary path (system or bundled imageio-ffmpeg)."""
    sys_bin = shutil.which("ffmpeg")
    if sys_bin:
        return sys_bin
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return None


def _has_ffmpeg() -> bool:
    """Check if ffmpeg executable is available."""
    return _get_ffmpeg_bin() is not None


async def text_to_voice_note(text: str, voice: str = "") -> str:
    """
    Synthesize text into an audio file (.ogg with chime prepended if FFmpeg available, otherwise .mp3).

    Returns:
        Absolute filepath to the generated audio file.
    """
    if not voice:
        voice = TTS_VOICE

    file_id = uuid.uuid4().hex[:8]
    mp3_path = os.path.join(AUDIO_OUTPUT_DIR, f"tts_{file_id}.mp3")
    ogg_path = os.path.join(AUDIO_OUTPUT_DIR, f"tts_{file_id}.ogg")

    # 1. Primary engine: Edge-TTS
    try:
        return await _generate_with_edge_tts(text, voice, mp3_path, ogg_path)
    except Exception as e:
        logger.warning(f"Edge-TTS failed with voice '{voice}': {e}")

    # 2. Fallback voice with Edge-TTS
    if TTS_FALLBACK_VOICE and TTS_FALLBACK_VOICE != voice:
        try:
            logger.info(f"Retrying with fallback voice: {TTS_FALLBACK_VOICE}")
            return await _generate_with_edge_tts(text, TTS_FALLBACK_VOICE, mp3_path, ogg_path)
        except Exception as e:
            logger.warning(f"Edge-TTS fallback voice failed: {e}")

    # 3. Last resort engine: gTTS
    try:
        logger.info("Falling back to gTTS engine...")
        return _generate_with_gtts(text, mp3_path, ogg_path)
    except Exception as e:
        logger.error(f"All TTS synthesis engines failed: {e}")
        raise RuntimeError(f"Text-to-speech generation failed: {e}")


async def _generate_with_edge_tts(text: str, voice: str, mp3_path: str, ogg_path: str) -> str:
    """Generate audio stream via edge-tts and prepend Jarvis chime."""
    communicate = edge_tts.Communicate(text, voice)
    await communicate.save(mp3_path)

    if not os.path.exists(mp3_path) or os.path.getsize(mp3_path) == 0:
        raise RuntimeError("Edge-TTS created an empty file.")

    ffmpeg_bin = _get_ffmpeg_bin()
    if ffmpeg_bin:
        chime_file = _ensure_chime_exists()
        try:
            if chime_file and os.path.exists(chime_file):
                # Concatenate chime + speech into native OGG/Opus voice note
                cmd = [
                    ffmpeg_bin, "-y",
                    "-i", chime_file,
                    "-i", mp3_path,
                    "-filter_complex", "[0:a][1:a]concat=n=2:v=0:a=1[out]",
                    "-map", "[out]",
                    "-c:a", "libopus",
                    "-b:a", "64k",
                    ogg_path,
                ]
            else:
                cmd = [ffmpeg_bin, "-y", "-i", mp3_path, "-c:a", "libopus", "-b:a", "64k", ogg_path]

            subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            _safe_remove(mp3_path)
            logger.info(f"✅ Generated chimed OGG voice note: {ogg_path}")
            return os.path.abspath(ogg_path)
        except Exception as e:
            logger.warning(f"FFmpeg conversion failed ({e}); using native MP3.")

    logger.info(f"Using native MP3 audio: {mp3_path}")
    return os.path.abspath(mp3_path)


def _generate_with_gtts(text: str, mp3_path: str, ogg_path: str) -> str:
    """Generate audio via gTTS."""
    from gtts import gTTS
    tts = gTTS(text=text, lang="en", slow=False)
    tts.save(mp3_path)

    ffmpeg_bin = _get_ffmpeg_bin()
    if ffmpeg_bin:
        try:
            cmd = [ffmpeg_bin, "-y", "-i", mp3_path, "-c:a", "libopus", "-b:a", "64k", ogg_path]
            subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            _safe_remove(mp3_path)
            return os.path.abspath(ogg_path)
        except Exception:
            pass

    return os.path.abspath(mp3_path)


def _safe_remove(path: str) -> None:
    """Safely delete a file without raising errors."""
    try:
        if os.path.exists(path):
            os.remove(path)
    except OSError:
        pass


def cleanup_audio_files(max_age_hours: int = 12) -> int:
    """Clean up generated temporary audio files older than max_age_hours."""
    deleted = 0
    cutoff = time.time() - (max_age_hours * 3600)

    try:
        for fname in os.listdir(AUDIO_OUTPUT_DIR):
            fpath = os.path.join(AUDIO_OUTPUT_DIR, fname)
            if os.path.isfile(fpath) and os.path.getmtime(fpath) < cutoff:
                _safe_remove(fpath)
                deleted += 1
    except Exception as e:
        logger.warning(f"Audio cleanup warning: {e}")

    if deleted > 0:
        logger.info(f"🧹 Cleaned up {deleted} temporary audio files.")
    return deleted


async def send_audio_message(bot, chat_id: int, audio_path: str, caption: str = "", reply_markup=None) -> None:
    """
    Send audio file as Telegram native voice note (.ogg) or regular audio (.mp3).
    """
    with open(audio_path, "rb") as f:
        if audio_path.endswith(".ogg"):
            await bot.send_voice(
                chat_id=chat_id,
                voice=f,
                caption=caption,
                reply_markup=reply_markup,
                read_timeout=60,
                write_timeout=60,
                connect_timeout=30,
            )
        else:
            await bot.send_audio(
                chat_id=chat_id,
                audio=f,
                caption=caption,
                reply_markup=reply_markup,
                read_timeout=60,
                write_timeout=60,
                connect_timeout=30,
            )
