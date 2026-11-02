"""
bot module initialization.
"""
from bot.middleware import authorized_only
from bot.handlers import (
    cmd_start,
    cmd_help,
    cmd_morning,
    cmd_evening,
    cmd_status,
    cmd_weather,
    handle_callback_query,
    handle_text_message,
)

__all__ = [
    "authorized_only",
    "cmd_start",
    "cmd_help",
    "cmd_morning",
    "cmd_evening",
    "cmd_status",
    "cmd_weather",
    "handle_callback_query",
    "handle_text_message",
]
