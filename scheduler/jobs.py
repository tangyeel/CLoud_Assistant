"""
scheduler/jobs.py — APScheduler job configurations for scheduled proactive voice briefings.
"""
from zoneinfo import ZoneInfo
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.events import EVENT_JOB_ERROR, EVENT_JOB_MISSED
from config import (
    TIMEZONE,
    MORNING_REPORT_HOUR,
    MORNING_REPORT_MINUTE,
    EVENING_REPORT_HOUR,
    EVENING_REPORT_MINUTE,
    TELEGRAM_CHAT_ID,
    SEND_ERROR_ALERTS,
)
from utils.logger import logger
from tts.speech import cleanup_audio_files

# Scheduler instance using configured timezone
scheduler = AsyncIOScheduler(timezone=ZoneInfo(TIMEZONE))

# Bot instance stored on startup
_bot_instance = None


def set_bot(bot):
    """Store bot reference for scheduler execution."""
    global _bot_instance
    _bot_instance = bot


async def _morning_job():
    """Trigger morning briefing voice pipeline."""
    logger.info("⏰ Cron trigger: Starting scheduled morning briefing...")
    if not _bot_instance:
        logger.error("Bot instance not available for morning job.")
        return

    try:
        from reports.morning import run_morning_report
        await run_morning_report(_bot_instance)
    except Exception as e:
        logger.error(f"Morning scheduled briefing failed: {e}", exc_info=True)
        if SEND_ERROR_ALERTS and _bot_instance and TELEGRAM_CHAT_ID:
            try:
                await _bot_instance.send_message(
                    chat_id=TELEGRAM_CHAT_ID,
                    text=f"🚨 **Cron Alert**: Morning report job encountered an error:\n`{e}`",
                    parse_mode="Markdown"
                )
            except Exception:
                pass


async def _evening_job():
    """Trigger evening report voice pipeline."""
    logger.info("⏰ Cron trigger: Starting scheduled evening report...")
    if not _bot_instance:
        logger.error("Bot instance not available for evening job.")
        return

    try:
        from reports.evening import run_evening_report
        await run_evening_report(_bot_instance)
    except Exception as e:
        logger.error(f"Evening scheduled report failed: {e}", exc_info=True)
        if SEND_ERROR_ALERTS and _bot_instance and TELEGRAM_CHAT_ID:
            try:
                await _bot_instance.send_message(
                    chat_id=TELEGRAM_CHAT_ID,
                    text=f"🚨 **Cron Alert**: Evening report job encountered an error:\n`{e}`",
                    parse_mode="Markdown"
                )
            except Exception:
                pass


async def _cleanup_job():
    """Run periodic maintenance on audio cache directory."""
    cleanup_audio_files(max_age_hours=12)


# Cache of alerted event IDs to avoid repeated reminders
_alerted_event_ids: set[str] = set()


async def _check_upcoming_commitments():
    """
    Check for events starting in 10-18 minutes and send 15-minute Time-to-Leave alert.
    """
    if not _bot_instance or not TELEGRAM_CHAT_ID:
        return

    from datetime import datetime
    from zoneinfo import ZoneInfo
    from google_services.calendar_service import get_todays_events

    try:
        tz = ZoneInfo(TIMEZONE)
        now = datetime.now(tz)
        events = get_todays_events()

        for ev in events:
            ev_id = ev.get("id")
            if not ev_id or ev_id in _alerted_event_ids:
                continue

            start_raw = ev.get("start")
            if not start_raw or "T" not in str(start_raw):
                continue

            try:
                ev_dt = datetime.fromisoformat(start_raw)
                if ev_dt.tzinfo is None:
                    ev_dt = ev_dt.replace(tzinfo=tz)
                diff_sec = (ev_dt - now).total_seconds()
                diff_min = diff_sec / 60.0

                # Trigger when 10 to 18 minutes away
                if 10.0 <= diff_min <= 18.0:
                    _alerted_event_ids.add(ev_id)
                    time_str = ev_dt.strftime("%I:%M %p")
                    loc = ev.get("location")
                    loc_str = f"📍 Location: **{loc}**\n" if loc else ""

                    msg = (
                        f"⏰ **15-Minute Alert: Time to Leave!**\n\n"
                        f"📌 **{ev['summary']}**\n"
                        f"{loc_str}"
                        f"🕒 Starts at: **{time_str}** (~{int(diff_min)} mins remaining)\n\n"
                        f"Head out now to arrive comfortably on time, sir."
                    )
                    await _bot_instance.send_message(
                        chat_id=TELEGRAM_CHAT_ID,
                        text=msg,
                        parse_mode="Markdown"
                    )
                    logger.info(f"✅ Dispatched 15-min Time-to-Leave alert for '{ev['summary']}'.")
            except Exception as parse_err:
                logger.debug(f"Event time parse skip: {parse_err}")

    except Exception as e:
        logger.warning(f"Error checking upcoming commitments: {e}")


async def _attendance_daily_poll():
    """Daily check-in for attendance right after class hours (14:05)."""
    if not _bot_instance or not TELEGRAM_CHAT_ID:
        return

    from utils.attendance import format_attendance_card
    try:
        card, markup = format_attendance_card()
        msg = (
            f"🎓 **Daily Attendance Check-In**\n\n"
            f"Classes have concluded for the afternoon. Did you attend all your scheduled lectures today?\n\n"
            f"{card}"
        )
        await _bot_instance.send_message(
            chat_id=TELEGRAM_CHAT_ID,
            text=msg,
            reply_markup=markup,
            parse_mode="Markdown"
        )
        logger.info("✅ Sent daily attendance poll.")
    except Exception as e:
        logger.warning(f"Daily attendance poll error: {e}")


def _job_error_listener(event):
    if event.exception:
        logger.error(f"Scheduler job error in '{event.job_id}': {event.exception}", exc_info=True)


def _job_missed_listener(event):
    logger.warning(f"⚠️ Scheduler missed job '{event.job_id}'. Will execute on next window.")


def start_scheduler():
    """Initialize cron triggers and start the scheduler."""
    if scheduler.running:
        logger.debug("Scheduler is already running.")
        return
    scheduler.add_listener(_job_error_listener, EVENT_JOB_ERROR)
    scheduler.add_listener(_job_missed_listener, EVENT_JOB_MISSED)

    # Morning Voice Briefing Job
    scheduler.add_job(
        _morning_job,
        trigger="cron",
        hour=MORNING_REPORT_HOUR,
        minute=MORNING_REPORT_MINUTE,
        id="morning_briefing",
        replace_existing=True,
        misfire_grace_time=600,
    )
    logger.info(
        f"📅 Morning report scheduled daily at {MORNING_REPORT_HOUR:02d}:{MORNING_REPORT_MINUTE:02d} ({TIMEZONE})"
    )

    # Evening Wind-down Report Job
    scheduler.add_job(
        _evening_job,
        trigger="cron",
        hour=EVENING_REPORT_HOUR,
        minute=EVENING_REPORT_MINUTE,
        id="evening_report",
        replace_existing=True,
        misfire_grace_time=600,
    )
    logger.info(
        f"📅 Evening report scheduled daily at {EVENING_REPORT_HOUR:02d}:{EVENING_REPORT_MINUTE:02d} ({TIMEZONE})"
    )

    # 15-Minute Time-to-Leave Alert Check (runs every 2 minutes)
    scheduler.add_job(
        _check_upcoming_commitments,
        trigger="interval",
        minutes=2,
        id="commitment_15m_alerts",
        replace_existing=True,
    )

    # Daily Attendance Poll (14:05 daily)
    scheduler.add_job(
        _attendance_daily_poll,
        trigger="cron",
        hour=14,
        minute=5,
        id="attendance_daily_poll",
        replace_existing=True,
    )

    # Cache cleanup every 6 hours
    scheduler.add_job(
        _cleanup_job,
        trigger="interval",
        hours=6,
        id="audio_cache_cleanup",
        replace_existing=True,
    )

    scheduler.start()
    logger.info("✅ APScheduler successfully activated.")


def stop_scheduler():
    """Shut down scheduler gracefully."""
    if scheduler.running:
        scheduler.shutdown(wait=False)
        logger.info("Scheduler stopped.")
