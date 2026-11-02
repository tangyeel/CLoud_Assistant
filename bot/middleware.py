"""
bot/middleware.py — Access control and authorization guard.
Ensures only the authorized owner can interact with the bot.
"""
from functools import wraps
from telegram import Update
from telegram.ext import ContextTypes
from config import TELEGRAM_CHAT_ID
from utils.logger import logger


def authorized_only(func):
    """
    Decorator that verifies incoming messages originate from TELEGRAM_CHAT_ID.
    If TELEGRAM_CHAT_ID is not yet configured (0), it provides a setup hint.
    """
    @wraps(func)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
        if not update.effective_chat or not update.effective_user:
            return

        chat_id = update.effective_chat.id

        # Setup helper: If no chat ID has been configured yet
        if TELEGRAM_CHAT_ID == 0:
            logger.info(f"First-run interaction detected from chat_id={chat_id}")
            await update.effective_message.reply_text(
                f"👋 **Setup Assistant**\n\n"
                f"Your Telegram Chat ID is: `{chat_id}`\n\n"
                f"Please add this to your `.env` file:\n"
                f"`TELEGRAM_CHAT_ID={chat_id}`\n\n"
                f"Then restart the assistant to secure your bot.",
                parse_mode="Markdown",
            )
            return

        # Verification check
        if chat_id != TELEGRAM_CHAT_ID:
            logger.warning(
                f"⛔ Unauthorized access attempt from chat_id={chat_id}, "
                f"user=@{update.effective_user.username or 'unknown'}"
            )
            await update.effective_message.reply_text("⛔ Unauthorized. This is a private personal assistant.")
            return

        return await func(update, context, *args, **kwargs)

    return wrapper
