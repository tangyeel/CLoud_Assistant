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
    DEADLINE_ALERT_HOURS,
    DEADLINE_ALERT_CHECK_MINUTES,
    PREMARKET_RADAR_HOUR,
    PREMARKET_RADAR_MINUTE,
    SATURDAY_IPO_HOUR,
    SATURDAY_IPO_MINUTE,
    PRICE_ALERT_CHECK_MINUTES,
    TELEGRAM_CHAT_ID,
    SEND_ERROR_ALERTS,
)
from utils.logger import logger
from utils.alert_tracker import is_alert_dispatched, mark_alert_dispatched
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


async def _check_upcoming_commitments():
    """
    Check for events starting in 10-18 minutes and send 15-minute Time-to-Leave alert.
    Uses persistent alert tracker to guarantee exactly one alert across container restarts,
    Render redeployments, and multi-account calendar syncing.
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
            raw_event_id = ev.get("id", "")
            start_raw = ev.get("start")
            if not start_raw or "T" not in str(start_raw):
                continue

            summary = ev.get("summary", "")
            clean_summary = summary.replace(" [Thapar]", "").strip().lower()
            start_time_key = str(start_raw)[:16]

            key_id = f"cal_id:{raw_event_id}" if raw_event_id else ""
            key_time = f"cal_time:{clean_summary}:{start_time_key}"

            # Skip if this specific event occurrence was already alerted
            if (key_id and is_alert_dispatched(key_id)) or is_alert_dispatched(key_time):
                continue

            try:
                ev_dt = datetime.fromisoformat(start_raw)
                if ev_dt.tzinfo is None:
                    ev_dt = ev_dt.replace(tzinfo=tz)
                diff_sec = (ev_dt - now).total_seconds()
                diff_min = diff_sec / 60.0

                # Trigger when 10 to 18 minutes away
                if 10.0 <= diff_min <= 18.0:
                    if key_id:
                        mark_alert_dispatched(key_id, context=summary)
                    mark_alert_dispatched(key_time, context=summary)

                    time_str = ev_dt.strftime("%I:%M %p")
                    loc = ev.get("location")
                    loc_str = f"📍 Location: {loc}\n" if loc else ""
                    is_class = ev.get("account") == "thapar"
                    alert_title = "🎓 Class Alert: Time to Leave!" if is_class else "⏰ Reminder: Time to Leave!"

                    # Weather & Campus Transit Assessment
                    transit_advisory = ""
                    try:
                        from utils.weather import get_weather
                        from config import USER_CITY
                        w = get_weather(USER_CITY)
                        w_code = w.get("weather_code", 0)
                        temp = w.get("temperature")
                        cond = w.get("condition", "")
                        rain_chance = w.get("rain_chance", 0)

                        if w_code in (51, 53, 55, 61, 63, 65, 80, 81, 82, 95, 96, 99) or rain_chance >= 50:
                            transit_advisory = f"🌧️ **Transit Advisory:** Active precipitation in {w['city']} ({cond}). Grab an umbrella before stepping out!\n"
                        elif w_code in (45, 48):
                            transit_advisory = f"🌫️ **Transit Advisory:** Dense fog reported in {w['city']}. Allow extra time for campus transit.\n"
                        elif temp is not None and temp >= 38:
                            transit_advisory = f"☀️ **Heat Advisory:** High temperature ({temp}°C) in {w['city']}. Stay hydrated!\n"
                        elif temp is not None and temp <= 10:
                            transit_advisory = f"🧥 **Cold Advisory:** Chilly ({temp}°C) outside in {w['city']}. Grab a warm jacket!\n"
                    except Exception as wex:
                        logger.debug(f"Transit advisory check skipped: {wex}")

                    adv_str = f"\n{transit_advisory}" if transit_advisory else ""

                    msg = (
                        f"{alert_title}\n\n"
                        f"📌 {ev['summary']}\n"
                        f"{loc_str}"
                        f"🕒 Starts at: {time_str} (~{int(diff_min)} mins remaining)\n"
                        f"{adv_str}\n"
                        f"Head out now to arrive comfortably on time, sir."
                    )
                    await _bot_instance.send_message(
                        chat_id=TELEGRAM_CHAT_ID,
                        text=msg,
                    )
                    logger.info(f"✅ Dispatched {'class' if is_class else 'calendar'} alert for '{ev['summary']}'.")
            except Exception as parse_err:
                logger.debug(f"Event time parse skip: {parse_err}")

    except Exception as e:
        logger.warning(f"Error checking upcoming commitments: {e}")


async def _attendance_daily_poll():
    """Daily check-in for attendance strictly on weekdays after class hours (17:05)."""
    if not _bot_instance or not TELEGRAM_CHAT_ID:
        return

    from utils.attendance import get_todays_classes, format_attendance_card
    try:
        classes = get_todays_classes()
        if not classes:
            logger.info("No academic lectures conducted today; skipping attendance poll.")
            return

        card, markup = format_attendance_card()
        msg = (
            f"🎓 **Daily Academic Attendance Check-In**\n\n"
            f"University lectures have concluded for the day. Did you attend all your scheduled classes today?\n\n"
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


async def _check_deadlines():
    """Send each pending task/coursework alert once per configured lead time."""
    if not _bot_instance or not TELEGRAM_CHAT_ID:
        return

    from datetime import datetime, timedelta
    from google_services.tasks_service import get_pending_tasks
    from google_services.classroom_service import get_all_upcoming_assignments

    tz = ZoneInfo(TIMEZONE)
    now = datetime.now(tz)
    sources = []
    try:
        sources.extend(("Task", item.get("id", ""), item.get("title", "Task"), item.get("due"), "")
                       for item in get_pending_tasks())
    except Exception as e:
        logger.warning(f"Could not check task deadlines: {e}")
    try:
        assignments = get_all_upcoming_assignments(max_per_course=100)
        sources.extend(("Classroom", item.get("id", ""), item.get("title", "Assignment"),
                        item.get("due_date"), item.get("course_name", "")) for item in assignments)
    except Exception as e:
        logger.warning(f"Could not check Classroom deadlines: {e}")

    for source, item_id, title, due_raw, course in sources:
        if not item_id or not due_raw:
            continue
        try:
            due_text = str(due_raw)
            due = datetime.fromisoformat(due_text.replace("Z", "+00:00"))
            if due.tzinfo is None:
                # Classroom due dates without a time mean the end of that local day.
                if source == "Classroom" and len(due_text) == 10:
                    due += timedelta(days=1) - timedelta(seconds=1)
                due = due.replace(tzinfo=tz)
            due = due.astimezone(tz)
        except (TypeError, ValueError):
            continue

        minutes_left = (due - now).total_seconds() / 60
        for lead_hours in DEADLINE_ALERT_HOURS:
            lead_minutes = lead_hours * 60
            if not (lead_minutes - DEADLINE_ALERT_CHECK_MINUTES < minutes_left <= lead_minutes):
                continue
            key = f"deadline:{source}:{course}:{item_id}:{due.isoformat()[:16]}:{lead_hours}h"
            if is_alert_dispatched(key):
                continue
            mark_alert_dispatched(key, context=f"{title} ({lead_hours}h)")
            when = due.strftime("%a, %b %d at %I:%M %p")
            course_line = f"\n📚 Course: **{course}**" if course else ""
            alert_text = (
                f"⏳ Deadline in about {lead_hours}h\n\n"
                f"{'📝' if source == 'Task' else '🎓'} {title}{course_line}\n"
                f"📅 Due: {when}"
            )
            try:
                await _bot_instance.send_message(
                    chat_id=TELEGRAM_CHAT_ID,
                    text=alert_text,
                    parse_mode="Markdown",
                )
                logger.info(f"Sent {lead_hours}h {source} deadline alert for '{title}'.")
            except Exception:
                try:
                    await _bot_instance.send_message(
                        chat_id=TELEGRAM_CHAT_ID,
                        text=alert_text,
                    )
                except Exception as e:
                    logger.warning(f"Could not send deadline alert for '{title}': {e}")


async def _premarket_radar_job():
    """Trigger daily Pre-Market Radar at 09:00 IST."""
    logger.info("⏰ Trigger: Starting scheduled Pre-Market Radar...")
    if not _bot_instance or not TELEGRAM_CHAT_ID:
        return

    try:
        from utils.finance import get_premarket_data, format_premarket_card
        data = get_premarket_data()
        card = format_premarket_card(data)
        await _bot_instance.send_message(
            chat_id=TELEGRAM_CHAT_ID,
            text=card,
            parse_mode="Markdown",
        )
        logger.info("✅ Dispatched Pre-Market Radar to Telegram.")
    except Exception as e:
        logger.error(f"Pre-Market Radar job failed: {e}", exc_info=True)


async def _saturday_ipo_job():
    """Trigger weekly Saturday IPO report at 08:00 IST."""
    logger.info("⏰ Trigger: Starting scheduled Saturday IPO Briefing...")
    if not _bot_instance or not TELEGRAM_CHAT_ID:
        return

    try:
        from utils.ipo import format_ipo_card
        card, markup = format_ipo_card()
        msg = f"🌅 **Saturday Weekend IPO Intelligence Briefing**\n\n{card}"
        await _bot_instance.send_message(
            chat_id=TELEGRAM_CHAT_ID,
            text=msg,
            reply_markup=markup,
            parse_mode="Markdown",
        )
        logger.info("✅ Dispatched Saturday IPO Briefing to Telegram.")
    except Exception as e:
        logger.error(f"Saturday IPO job failed: {e}", exc_info=True)


async def _ipo_listing_tracker_job():
    """
    Monitor tracked IPO applications for Listing Day Debut & Day-End Close performance.
    Dispatches notifications on the morning of listing (10:00 AM) and market close (15:45 IST).
    """
    if not _bot_instance or not TELEGRAM_CHAT_ID:
        return

    try:
        from utils.ipo import check_ipo_listing_day_alerts
        alerts = check_ipo_listing_day_alerts()
        for alert_msg in alerts:
            await _bot_instance.send_message(
                chat_id=TELEGRAM_CHAT_ID,
                text=alert_msg,
                parse_mode="Markdown",
            )
            logger.info("Dispatched IPO listing notification to Telegram.")
    except Exception as e:
        logger.warning(f"Error checking IPO listing alerts: {e}")


async def _check_market_alerts_job():
    """Check both price alerts and investment thesis triggers."""
    if not _bot_instance or not TELEGRAM_CHAT_ID:
        return

    try:
        from utils.price_alerts import check_price_alerts_triggers
        from utils.thesis import check_thesis_triggers

        alerts = check_price_alerts_triggers()
        for alt_msg in alerts:
            await _bot_instance.send_message(
                chat_id=TELEGRAM_CHAT_ID,
                text=alt_msg,
                parse_mode="Markdown",
            )
            logger.info("Dispatched live price alert to Telegram.")

        thesis_alerts = check_thesis_triggers()
        for th_msg in thesis_alerts:
            await _bot_instance.send_message(
                chat_id=TELEGRAM_CHAT_ID,
                text=th_msg,
                parse_mode="Markdown",
            )
            logger.info("Dispatched thesis alert to Telegram.")

    except Exception as e:
        logger.warning(f"Error checking market alerts: {e}")


async def _check_watchlist_earnings_job():
    """Scan watchlist companies for earnings declarations or T-1 heads-up at 17:30 IST."""
    if not _bot_instance or not TELEGRAM_CHAT_ID:
        return

    try:
        from utils.earnings import check_watchlist_earnings_updates
        updates = check_watchlist_earnings_updates()
        for note in updates:
            await _bot_instance.send_message(
                chat_id=TELEGRAM_CHAT_ID,
                text=note,
                parse_mode="Markdown",
            )
            logger.info("Dispatched watchlist earnings notification to Telegram.")
    except Exception as e:
        logger.warning(f"Watchlist earnings scan error: {e}")


async def _check_stealth_delivery_job():
    """
    18:30 IST Post-Market Scan: Deliverable Volume & Smart Money Demat Accumulation.
    Dispatches the daily delivery radar to Telegram.
    """
    if not _bot_instance or not TELEGRAM_CHAT_ID:
        return

    try:
        from utils.stealth_delivery import format_stealth_delivery_card
        card = format_stealth_delivery_card()
        if card and "Unable to load" not in card:
            await _bot_instance.send_message(
                chat_id=TELEGRAM_CHAT_ID,
                text=card,
                parse_mode="Markdown",
            )
            logger.info("Dispatched Stealth Delivery Radar to Telegram.")
    except Exception as e:
        logger.warning(f"Stealth delivery scheduler error: {e}")


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

    # Daily Attendance Poll (17:05 Mon-Fri, strictly after class hours)
    scheduler.add_job(
        _attendance_daily_poll,
        trigger="cron",
        day_of_week="mon-fri",
        hour=17,
        minute=5,
        id="attendance_daily_poll",
        replace_existing=True,
    )

    # IPO Listing Day & Performance Monitor (Every 15m 09:45-16:15 IST weekdays)
    scheduler.add_job(
        _ipo_listing_tracker_job,
        trigger="cron",
        day_of_week="mon-fri",
        hour="9-16",
        minute="0,15,30,45",
        id="ipo_listing_tracker",
        replace_existing=True,
    )
    logger.info("📅 IPO Listing Day & Performance Monitor scheduled (09:45-16:15 weekdays)")

    # Pre-Market Radar Job (09:00 IST daily)
    scheduler.add_job(
        _premarket_radar_job,
        trigger="cron",
        hour=PREMARKET_RADAR_HOUR,
        minute=PREMARKET_RADAR_MINUTE,
        id="premarket_radar",
        replace_existing=True,
        misfire_grace_time=300,
    )
    logger.info(
        f"📅 Pre-Market Radar scheduled daily at {PREMARKET_RADAR_HOUR:02d}:{PREMARKET_RADAR_MINUTE:02d} ({TIMEZONE})"
    )

    # Saturday Weekly IPO Briefing (08:00 IST Saturday)
    scheduler.add_job(
        _saturday_ipo_job,
        trigger="cron",
        day_of_week="sat",
        hour=SATURDAY_IPO_HOUR,
        minute=SATURDAY_IPO_MINUTE,
        id="saturday_ipo_briefing",
        replace_existing=True,
        misfire_grace_time=600,
    )
    logger.info(
        f"📅 Saturday IPO Briefing scheduled weekly at {SATURDAY_IPO_HOUR:02d}:{SATURDAY_IPO_MINUTE:02d} ({TIMEZONE})"
    )

    # Price & Thesis Market Alerts Polling (Every 5 mins)
    scheduler.add_job(
        _check_market_alerts_job,
        trigger="interval",
        minutes=PRICE_ALERT_CHECK_MINUTES,
        id="market_alerts_monitor",
        replace_existing=True,
    )
    logger.info(
        f"🔔 Market price alerts monitor active (every {PRICE_ALERT_CHECK_MINUTES} mins)"
    )

    # Watchlist Earnings Triage Scanner (17:30 IST Mon-Fri post-market)
    scheduler.add_job(
        _check_watchlist_earnings_job,
        trigger="cron",
        day_of_week="mon-fri",
        hour=17,
        minute=30,
        id="watchlist_earnings_scanner",
        replace_existing=True,
        misfire_grace_time=600,
    )
    logger.info("📅 Watchlist Earnings Triage Scanner scheduled at 17:30 IST weekdays")

    # Stealth Institutional Delivery Radar (18:30 IST Mon-Fri post-market)
    scheduler.add_job(
        _check_stealth_delivery_job,
        trigger="cron",
        day_of_week="mon-fri",
        hour=18,
        minute=30,
        id="stealth_delivery_scanner",
        replace_existing=True,
        misfire_grace_time=600,
    )
    logger.info("📅 Stealth Institutional Delivery Scanner scheduled at 18:30 IST weekdays")



    scheduler.add_job(
        _check_deadlines,
        trigger="interval",
        minutes=DEADLINE_ALERT_CHECK_MINUTES,
        id="deadline_alerts",
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
