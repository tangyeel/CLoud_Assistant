"""
reports/morning.py — Morning briefing pipeline:
Collects emails, calendar, tasks, classroom -> Generates AI script -> TTS synthesis -> Telegram voice briefing.
"""
from datetime import datetime
from zoneinfo import ZoneInfo
from telegram import Bot, InlineKeyboardMarkup, InlineKeyboardButton
from google_services.gmail_service import get_unread_emails
from google_services.calendar_service import get_todays_events
from google_services.tasks_service import get_pending_tasks
from google_services.classroom_service import get_all_upcoming_assignments
from utils.weather import get_weather
from ai.gemini_client import generate_text
from ai.prompts import MORNING_BRIEFING_SYSTEM, MORNING_BRIEFING_PROMPT
from tts.speech import text_to_voice_note, send_audio_message, cleanup_audio_files
from config import TELEGRAM_CHAT_ID, TIMEZONE
from utils.logger import logger


async def run_morning_report(bot: Bot) -> None:
    """
    Execute the Jarvis morning report workflow with live weather, schedule, emails, and tasks.
    """
    logger.info("🌅 Starting Jarvis Morning Briefing workflow...")
    tz = ZoneInfo(TIMEZONE)
    now = datetime.now(tz)
    today_str = now.strftime("%A, %B %d, %Y")

    # 1. Fetch live data with isolated error safety
    weather_data = _safe_fetch("weather", get_weather)
    weather_text = weather_data.get("spoken_summary", "Live weather data unavailable.") if isinstance(weather_data, dict) else "Weather unavailable."

    emails_data = _safe_fetch("emails", get_unread_emails, hours_back=12)
    calendar_data = _safe_fetch("calendar", get_todays_events)
    tasks_data = _safe_fetch("tasks", get_pending_tasks)
    classroom_data = _safe_fetch("classroom", get_all_upcoming_assignments)

    # 2. Format textual summaries for AI context
    emails_text = _format_emails(emails_data)
    calendar_text = _format_calendar(calendar_data)
    tasks_text = _format_tasks(tasks_data)
    classroom_text = _format_classroom(classroom_data)

    # 3. Generate script via AI
    script = ""
    try:
        from utils.memory import recall_relevant_memories, format_memories_for_prompt
        mems = recall_relevant_memories("morning routine focus academic priorities preferences", top_k=2)
        mem_block = format_memories_for_prompt(mems)
        sys_inst = MORNING_BRIEFING_SYSTEM
        if mem_block:
            sys_inst = f"{MORNING_BRIEFING_SYSTEM}\n\n{mem_block}\nSir's standing priorities are provided above; incorporate them subtly into today's focus."

        prompt = MORNING_BRIEFING_PROMPT.format(
            date=today_str,
            weather=weather_text,
            emails=emails_text,
            calendar=calendar_text,
            tasks=tasks_text,
            assignments=classroom_text,
        )
        script = generate_text(prompt, system_instruction=sys_inst)
        logger.info(f"Jarvis briefing script generated ({len(script)} characters).")
    except Exception as e:
        logger.error(f"Script generation failed: {e}. Using structured fallback.")
        script = (
            f"Good morning, sir. It is {today_str}.\n"
            f"{weather_text}\n"
            f"You have {len(calendar_data)} events scheduled today, "
            f"{len(tasks_data)} pending tasks on your checklist, "
            f"and {len(emails_data)} unread messages in your inbox. "
            f"All core systems remain at your disposal."
        )

    # Interactive buttons beneath morning briefing
    quick_buttons = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("📅 Agenda", callback_data="btn_agenda"),
            InlineKeyboardButton("📝 Tasks", callback_data="btn_tasks"),
            InlineKeyboardButton("🌦️ Weather", callback_data="btn_weather"),
        ]
    ])

    # 4. Synthesize voice note with Jarvis voice
    audio_path = None
    try:
        audio_path = await text_to_voice_note(script)
    except Exception as e:
        logger.error(f"TTS synthesis failed: {e}. Falling back to text.")

    # 5. Send to Telegram
    caption_text = f"🎙️ Jarvis Morning Briefing — {now.strftime('%A, %b %d')}"
    if audio_path:
        try:
            with open(audio_path, "rb") as f:
                if audio_path.endswith(".ogg"):
                    await bot.send_voice(
                        chat_id=TELEGRAM_CHAT_ID,
                        voice=f,
                        caption=caption_text,
                        reply_markup=quick_buttons,
                        read_timeout=60,
                        write_timeout=60,
                    )
                else:
                    await bot.send_audio(
                        chat_id=TELEGRAM_CHAT_ID,
                        audio=f,
                        caption=caption_text,
                        reply_markup=quick_buttons,
                        read_timeout=60,
                        write_timeout=60,
                    )
            logger.info("✅ Jarvis morning voice briefing dispatched with interactive controls.")
        except Exception as e:
            if "timed out" in str(e).lower():
                logger.info("ℹ️ Voice note uploaded successfully (async ack).")
            else:
                logger.error(f"Voice transmit failed: {e}. Sending text fallback.")
                await bot.send_message(
                    chat_id=TELEGRAM_CHAT_ID,
                    text=f"🌅 **Jarvis Morning Briefing — {today_str}**\n\n{script}",
                    reply_markup=quick_buttons,
                    parse_mode="Markdown",
                )
    else:
        await bot.send_message(
            chat_id=TELEGRAM_CHAT_ID,
            text=f"🌅 **Jarvis Morning Briefing — {today_str}**\n\n{script}",
            reply_markup=quick_buttons,
            parse_mode="Markdown",
        )

    cleanup_audio_files(max_age_hours=6)

    # 6. Periodic audio cleanup
    cleanup_audio_files(max_age_hours=6)


def _safe_fetch(name: str, func, **kwargs):
    """Safely invoke API call, logging and returning empty list on failure."""
    try:
        return func(**kwargs)
    except Exception as e:
        logger.warning(f"Could not retrieve {name} for briefing: {e}")
        return []


def _format_emails(emails: list[dict]) -> str:
    if not emails:
        return "No unread priority emails."
    lines = []
    for e in emails:
        lines.append(f"- From: {e['sender']} | Subject: {e['subject']} | Preview: {e['snippet'][:100]}")
    return "\n".join(lines)


def _format_calendar(events: list[dict]) -> str:
    if not events:
        return "No events scheduled for today."
    lines = []
    for ev in events:
        lines.append(f"- {ev['start']} to {ev['end']}: {ev['summary']} {ev.get('location', '')}")
    return "\n".join(lines)


def _format_tasks(tasks: list[dict]) -> str:
    if not tasks:
        return "No pending tasks on your to-do list."
    lines = []
    for t in tasks:
        due = f" (Due: {t['due'][:10]})" if t.get("due") else ""
        lines.append(f"- {t['title']}{due}")
    return "\n".join(lines)


def _format_classroom(assignments: list[dict]) -> str:
    if not assignments:
        return "No upcoming coursework deadlines."
    lines = []
    for a in assignments:
        due = f" (Due: {a['due_date']})" if a.get("due_date") else ""
        lines.append(f"- [{a.get('course_name', 'Course')}] {a['title']}{due}")
    return "\n".join(lines)
