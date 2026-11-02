"""
reports/evening.py — Evening preparatory briefing pipeline:
Focuses strictly on:
1. Commitment Alerts (tomorrow's schedule preview & earliest commitment)
2. Looming Deadlines (Classroom coursework & pending tasks)
3. Tomorrow's Weather (temperature range, conditions, and rain probability)
No recap of past events or completed items.
"""
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from telegram import Bot
from google_services.calendar_service import get_tomorrows_events
from google_services.tasks_service import get_pending_tasks
from google_services.classroom_service import get_all_upcoming_assignments
from utils.weather import get_tomorrow_weather
from ai.gemini_client import generate_text
from ai.prompts import EVENING_REPORT_SYSTEM, EVENING_REPORT_PROMPT
from tts.speech import text_to_voice_note, send_audio_message, cleanup_audio_files
from config import TELEGRAM_CHAT_ID, TIMEZONE, USER_CITY
from utils.logger import logger


async def run_evening_report(bot: Bot) -> None:
    """
    Execute the forward-looking evening preparatory briefing.
    """
    logger.info("🌙 Starting Evening Preparatory Briefing workflow...")
    tz = ZoneInfo(TIMEZONE)
    now = datetime.now(tz)
    tomorrow = now + timedelta(days=1)
    tomorrow_str = tomorrow.strftime("%A, %B %d, %Y")

    # 1. Fetch relevant tomorrow & deadline data
    tomorrow_events = _safe_fetch("tomorrow_events", get_tomorrows_events)
    assignments_data = _safe_fetch("classroom", get_all_upcoming_assignments)
    tasks_data = _safe_fetch("tasks", get_pending_tasks)
    weather_data = _safe_fetch("weather", get_tomorrow_weather, city_name=USER_CITY)

    # 2. Format textual summaries
    commitments_text = _format_commitments(tomorrow_events)
    deadlines_text = _format_deadlines(assignments_data, tasks_data)
    weather_spoken = weather_data.get("spoken_summary") if isinstance(weather_data, dict) else f"Weather forecast unavailable for {USER_CITY}."

    # 3. Generate script via Gemini AI / Fallback cascade
    script = ""
    try:
        prompt = EVENING_REPORT_PROMPT.format(
            tomorrow_date=tomorrow_str,
            commitments=commitments_text,
            deadlines=deadlines_text,
            city=USER_CITY,
            weather=weather_spoken,
        )
        script = generate_text(prompt, system_instruction=EVENING_REPORT_SYSTEM)
        logger.info(f"AI evening report script generated ({len(script)} characters).")
    except Exception as e:
        logger.error(f"AI evening script generation failed: {e}. Using structured fallback.")
        earliest_note = f"Your first commitment tomorrow is at {tomorrow_events[0]['start']}." if tomorrow_events else "You have a clear schedule tomorrow."
        script = (
            f"Good evening, sir. Here is your preparation for tomorrow, {tomorrow_str}.\n"
            f"{earliest_note}\n"
            f"You have {len(assignments_data)} assignments in your pipeline and {len(tasks_data)} pending tasks.\n"
            f"{weather_spoken}\n"
            f"Have a restful evening, sir."
        )

    # 4. Synthesize voice note
    audio_path = None
    try:
        audio_path = await text_to_voice_note(script)
    except Exception as e:
        logger.error(f"Evening TTS synthesis failed: {e}. Falling back to text.")

    # 5. Dispatch message
    if audio_path:
        try:
            await send_audio_message(
                bot=bot,
                chat_id=TELEGRAM_CHAT_ID,
                audio_path=audio_path,
                caption=f"🌙 Evening Briefing — Preparation for {tomorrow.strftime('%A, %b %d')}"
            )
            logger.info("✅ Evening voice report dispatched to Telegram.")
        except Exception as e:
            if "timed out" in str(e).lower():
                logger.info("ℹ️ Evening voice note uploaded successfully (acknowledged asynchronously by Telegram).")
            else:
                logger.error(f"Failed to transmit evening audio: {e}. Sending text fallback.")
                await bot.send_message(
                    chat_id=TELEGRAM_CHAT_ID,
                    text=f"🌙 **Evening Briefing — {tomorrow_str}**\n\n{script}",
                    parse_mode="Markdown"
                )
    else:
        await bot.send_message(
            chat_id=TELEGRAM_CHAT_ID,
            text=f"🌙 **Evening Briefing — {tomorrow_str}**\n\n{script}",
            parse_mode="Markdown"
        )

    cleanup_audio_files(max_age_hours=6)


def _safe_fetch(name: str, func, **kwargs):
    try:
        return func(**kwargs)
    except Exception as e:
        logger.warning(f"Could not retrieve {name} for evening report: {e}")
        return []


def _format_commitments(tomorrow_events: list[dict]) -> str:
    if not tomorrow_events:
        return "No commitments scheduled on your calendar for tomorrow."

    lines = []
    earliest = tomorrow_events[0]
    lines.append(f"Earliest commitment: '{earliest['summary']}' starting at {earliest['start']}.")
    lines.append("Full schedule for tomorrow:")
    for ev in tomorrow_events:
        loc = f" (at {ev['location']})" if ev.get("location") else ""
        lines.append(f"- {ev['start']} to {ev['end']}: {ev['summary']}{loc}")
    return "\n".join(lines)


def _format_deadlines(assignments: list[dict], tasks: list[dict]) -> str:
    lines = []
    if assignments:
        lines.append("Looming Academic Deadlines (Classroom):")
        for a in assignments[:6]:
            due = f" [Due: {a['due_date']}]" if a.get("due_date") else ""
            lines.append(f"- [{a.get('course_name', 'Class')}] {a['title']}{due}")
    else:
        lines.append("Classroom: No imminent deadlines.")

    if tasks:
        lines.append("\nPending Tasks:")
        for t in tasks[:6]:
            due = f" [Due: {t['due'][:10]}]" if t.get("due") else ""
            lines.append(f"- {t['title']}{due}")
    else:
        lines.append("Tasks: To-do list is clear.")

    return "\n".join(lines)
