"""
tts module initialization.
"""
from tts.speech import text_to_voice_note, cleanup_audio_files, send_audio_message

__all__ = ["text_to_voice_note", "cleanup_audio_files", "send_audio_message"]
