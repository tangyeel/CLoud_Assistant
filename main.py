"""
main.py — Main application entry point for Autonomous AI Personal Assistant.
Supports both Webhook mode (production/Render/cloud) and Polling mode (local testing).
"""
import os
import sys
import asyncio
from contextlib import asynccontextmanager
from http import HTTPStatus
import uvicorn
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import Response, PlainTextResponse
from starlette.routing import Route
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    filters,
)
from config import (
    TELEGRAM_BOT_TOKEN,
    TELEGRAM_WEBHOOK_URL,
    PORT,
    validate_config,
)
from bot.handlers import (
    cmd_start,
    cmd_help,
    cmd_morning,
    cmd_evening,
    cmd_schedule,
    cmd_tasks,
    cmd_emails,
    cmd_classes,
    cmd_status,
    cmd_weather,
    cmd_attendance,
    cmd_news,
    cmd_search,
    cmd_market,
    cmd_stock,
    cmd_ipo,
    cmd_thesis,
    cmd_alerts,
    cmd_memory,
    cmd_forget,
    cmd_watchlist,
    cmd_earnings,
    handle_callback_query,
    handle_text_message,
    handle_voice_message,
    handle_exam_schedule_photo,
)
from scheduler.jobs import start_scheduler, stop_scheduler, set_bot
from utils.health import health_check
from utils.logger import logger


async def on_bot_post_init(application: Application) -> None:
    """Invoked inside PTB's running asyncio event loop."""
    set_bot(application.bot)
    start_scheduler()
    if not TELEGRAM_WEBHOOK_URL:
        try:
            await application.bot.delete_webhook()
            logger.info("Cleared previous webhook.")
        except Exception as e:
            logger.warning(f"Webhook reset check: {e}")


async def on_bot_post_shutdown(application: Application) -> None:
    """Invoked when PTB stops."""
    stop_scheduler()


def build_telegram_app() -> Application | None:
    """Build and configure the python-telegram-bot application."""
    if not TELEGRAM_BOT_TOKEN:
        logger.warning("TELEGRAM_BOT_TOKEN is not configured yet in .env.")
        return None

    app = (
        Application.builder()
        .token(TELEGRAM_BOT_TOKEN)
        .read_timeout(60)
        .write_timeout(60)
        .connect_timeout(30)
        .post_init(on_bot_post_init)
        .post_shutdown(on_bot_post_shutdown)
        .build()
    )

    # Register slash commands
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(CommandHandler("morning", cmd_morning))
    app.add_handler(CommandHandler("evening", cmd_evening))
    app.add_handler(CommandHandler("schedule", cmd_schedule))
    app.add_handler(CommandHandler("tasks", cmd_tasks))
    app.add_handler(CommandHandler("weather", cmd_weather))
    app.add_handler(CommandHandler("emails", cmd_emails))
    app.add_handler(CommandHandler("classes", cmd_classes))
    app.add_handler(CommandHandler("status", cmd_status))
    app.add_handler(CommandHandler("attendance", cmd_attendance))
    app.add_handler(CommandHandler("news", cmd_news))
    app.add_handler(CommandHandler("search", cmd_search))
    app.add_handler(CommandHandler("market", cmd_market))
    app.add_handler(CommandHandler("stock", cmd_stock))
    app.add_handler(CommandHandler("ipo", cmd_ipo))
    app.add_handler(CommandHandler("thesis", cmd_thesis))
    app.add_handler(CommandHandler("alerts", cmd_alerts))
    app.add_handler(CommandHandler("memory", cmd_memory))
    app.add_handler(CommandHandler("forget", cmd_forget))
    app.add_handler(CommandHandler("watchlist", cmd_watchlist))
    app.add_handler(CommandHandler("earnings", cmd_earnings))




    # Register interactive callback query handler for inline button taps
    app.add_handler(CallbackQueryHandler(handle_callback_query))

    # Register voice note handler (Two-Way Voice via Groq Whisper STT)
    app.add_handler(MessageHandler(filters.VOICE, handle_voice_message))

    # Read exam timetables sent as Telegram photos.
    app.add_handler(MessageHandler(filters.PHOTO, handle_exam_schedule_photo))

    # Register conversational natural language message handler
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_message))

    return app


ptb_app = build_telegram_app()


# ─── Starlette Webhook & Health Endpoints ──────────────────────────────
async def telegram_webhook(request: Request) -> Response:
    """Receive Telegram webhook update payloads."""
    if request.method == "POST":
        try:
            data = await request.json()
            if ptb_app:
                update = Update.de_json(data, ptb_app.bot)
                await ptb_app.process_update(update)
        except Exception as e:
            logger.error(f"Error parsing webhook payload: {e}", exc_info=True)
        return Response(status_code=HTTPStatus.OK)
    return PlainTextResponse("Telegram webhook endpoint. Send updates via POST.", status_code=HTTPStatus.METHOD_NOT_ALLOWED)


async def home_route(request: Request) -> Response:
    """Root status greeting."""
    return PlainTextResponse("Autonomous AI Personal Assistant is running 24/7.")


routes = [
    Route("/webhook", telegram_webhook, methods=["POST"]),
    Route("/health", health_check, methods=["GET"]),
    Route("/", home_route, methods=["GET"]),
]


# ─── Lifespan Lifecycle for Starlette Webhook Server ───────────────────
@asynccontextmanager
async def lifespan(app: Starlette):
    """Manage application startup and shutdown lifecycle."""
    logger.info("🚀 Starting AI Assistant Web Server on port %s...", PORT)

    if ptb_app:
        await ptb_app.initialize()
        await ptb_app.start()
        set_bot(ptb_app.bot)
        start_scheduler()

        if TELEGRAM_WEBHOOK_URL:
            clean_url = TELEGRAM_WEBHOOK_URL.rstrip("/")
            webhook_endpoint = f"{clean_url}/webhook"
            await ptb_app.bot.set_webhook(url=webhook_endpoint, allowed_updates=Update.ALL_TYPES)
            logger.info(f"✅ Telegram webhook connected: {webhook_endpoint}")
        else:
            await ptb_app.bot.delete_webhook()
            await ptb_app.updater.start_polling(allowed_updates=Update.ALL_TYPES)
            logger.info("✅ Telegram background polling started.")

    logger.info("✅ Assistant background services fully initialized.")

    yield

    logger.info("🛑 Shutting down AI Assistant...")
    if ptb_app:
        if not TELEGRAM_WEBHOOK_URL and ptb_app.updater and ptb_app.updater.running:
            await ptb_app.updater.stop()
        stop_scheduler()
        await ptb_app.stop()
        await ptb_app.shutdown()
    logger.info("👋 Assistant offline.")


starlette_app = Starlette(routes=routes, lifespan=lifespan)


# ─── Local Polling Runner Helper ───────────────────────────────────────
def run_polling_mode():
    """
    Run the assistant in standalone local polling mode.
    """
    logger.info("🔄 Launching in STANDALONE POLLING MODE...")
    validate_config(exit_on_error=False)

    app = build_telegram_app()
    if not app:
        logger.error("Cannot start polling: TELEGRAM_BOT_TOKEN is missing from .env.")
        sys.exit(1)

    logger.info("🤖 Bot is now polling for messages. Press Ctrl+C to stop.")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


# ─── CLI Entrypoint ────────────────────────────────────────────────────
if __name__ == "__main__":
    if "--polling" in sys.argv:
        run_polling_mode()
    else:
        logger.info(f"🌐 Launching AI Assistant on port {PORT}...")
        uvicorn.run(
            "main:starlette_app",
            host="0.0.0.0",
            port=PORT,
            log_level="info",
        )
