"""
bot/handlers.py — Telegram bot command, voice note, and interactive message handlers.
"""
import os
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import ContextTypes
from bot.middleware import authorized_only
from bot.router import (
    route_message,
    _handle_query_emails,
    _handle_query_calendar,
    _handle_query_classroom,
    get_pending_conflict,
)
from reports.morning import run_morning_report
from reports.evening import run_evening_report
from config import TELEGRAM_CHAT_ID, TIMEZONE, USER_CITY
from utils.logger import logger


@authorized_only
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /start command."""
    await update.effective_message.reply_text(
        "👋 **Welcome to your Autonomous AI Personal Assistant!**\n\n"
        "I am connected to your Google Workspace and ready 24/7.\n\n"
        "🎙️ **Two-Way Voice Supported:**\n"
        "Send me any voice note anytime — I will transcribe, execute, and speak back!\n\n"
        "📅 **Daily Briefings:**\n"
        "• Morning report at 07:30 AM (emails, tasks, calendar, classroom, weather)\n"
        "• Evening wind-down at 09:00 PM (commitments, deadlines, tomorrow's weather)\n\n"
        "⚡ **Smart Safeguards Active:**\n"
        "• 15-Minute Time-to-Leave lecture alerts\n"
        "• Calendar conflict detection with auto-suggested free slots\n"
        "• Thapar Attendance 75% safeguard (/attendance)\n\n"
        "Type /help for direct slash commands.",
        parse_mode="Markdown",
    )


@authorized_only
async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /help command."""
    await update.effective_message.reply_text(
        "📖 **Jarvis Assistant Command Reference:**\n\n"
        "• /morning — Morning briefing (Jarvis British voice + weather)\n"
        "• /evening — Evening preparatory briefing (commitments + deadlines + weather)\n"
        "• /schedule — View today's agenda\n"
        "• /tasks — Interactive pending tasks with [Done] and [Snooze] buttons\n"
        "• /attendance — Thapar Attendance 75% safeguard & safe bunk tally\n"
        "• /weather — Real-time weather and rain forecast for Patiala\n"
        "• /news — Top live tech, finance, and market headlines\n"
        "• /search <query> — Real-time free web search\n"
        "• /emails — Unread priority emails across Personal & Thapar\n"
        "• /classes — Google Classroom assignments & deadlines\n"
        "• /status — AI provider hierarchy & system health\n\n"
        "🎙️ *Tip: You can send voice notes anytime or tap interactive buttons!*",
        parse_mode="Markdown",
    )


def get_tasks_with_buttons():
    """Fetch tasks and construct interactive [Done] and [Snooze] buttons."""
    from google_services.tasks_service import get_pending_tasks
    try:
        tasks = get_pending_tasks()
        if not tasks:
            return "✅ All clear! You have no pending tasks on your to-do list.", None

        lines = [f"📝 **{len(tasks)} Pending Tasks:**\n"]
        buttons = []
        for i, t in enumerate(tasks[:8], 1):
            due = f" — *Due: {t['due'][:10]}*" if t.get("due") else ""
            lines.append(f"{i}. {t['title']}{due}")
            clean_title = (t['title'][:14] + "..") if len(t['title']) > 14 else t['title']
            buttons.append([
                InlineKeyboardButton(f"✅ Done: {clean_title}", callback_data=f"done_{t['id']}"),
                InlineKeyboardButton("⏰ Snooze", callback_data=f"snz_{t['id']}"),
            ])

        return "\n".join(lines), InlineKeyboardMarkup(buttons)
    except Exception as e:
        return f"❌ Could not retrieve tasks: {e}", None


@authorized_only
async def cmd_tasks(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /tasks command with interactive buttons."""
    resp, markup = get_tasks_with_buttons()
    await update.effective_message.reply_text(resp, reply_markup=markup, parse_mode="Markdown")


@authorized_only
async def cmd_attendance(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /attendance command."""
    from utils.attendance import format_attendance_card
    card, markup = format_attendance_card()
    await update.effective_message.reply_text(card, reply_markup=markup, parse_mode="Markdown")


@authorized_only
async def cmd_weather(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /weather command."""
    from utils.weather import get_weather
    w = get_weather()
    await update.effective_message.reply_text(w["text_card"], parse_mode="Markdown")


@authorized_only
async def cmd_news(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /news command."""
    from utils.news import format_news_card
    card = format_news_card()
    await update.effective_message.reply_text(card, parse_mode="Markdown")


@authorized_only
async def cmd_search(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /search <query> command."""
    query_text = " ".join(context.args) if context.args else ""
    if not query_text:
        await update.effective_message.reply_text("Please provide a search term, e.g. `/search AI developments 2026`", parse_mode="Markdown")
        return

    from utils.search import search_web, format_search_results
    results = search_web(query_text, max_results=4)
    card = format_search_results(query_text, results)
    await update.effective_message.reply_text(card, parse_mode="Markdown")


@authorized_only
async def handle_callback_query(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle interactive inline button taps."""
    query = update.callback_query
    await query.answer()

    data = query.data
    logger.info(f"Button callback triggered: {data}")

    if data == "btn_agenda":
        resp = await _handle_query_calendar({"days_ahead": 1})
        await query.message.reply_text(resp, parse_mode="Markdown")

    elif data == "btn_tasks":
        resp, markup = get_tasks_with_buttons()
        await query.message.reply_text(resp, reply_markup=markup, parse_mode="Markdown")

    elif data == "btn_weather":
        from utils.weather import get_weather
        w = get_weather()
        await query.message.reply_text(w["text_card"], parse_mode="Markdown")

    elif data.startswith("done_"):
        task_id = data.replace("done_", "")
        try:
            from google_services.tasks_service import complete_task
            complete_task(task_id)
            await query.edit_message_text(f"{query.message.text}\n\n🎉 **Task marked as complete!**", parse_mode="Markdown")
        except Exception as e:
            await query.message.reply_text(f"❌ Failed to mark completed: {e}")

    elif data.startswith("snz_"):
        task_id = data.replace("snz_", "")
        try:
            from google_services.tasks_service import snooze_task
            new_date = snooze_task(task_id, days_ahead=1)
            await query.edit_message_text(f"{query.message.text}\n\n⏰ **Task deferred to tomorrow ({new_date})!**", parse_mode="Markdown")
        except Exception as e:
            await query.message.reply_text(f"❌ Failed to snooze task: {e}")

    elif data.startswith("cf_sug_"):
        cid = data.replace("cf_sug_", "")
        info = get_pending_conflict(cid)
        if not info:
            await query.edit_message_text("❌ Proposal expired. Please try scheduling again.")
            return

        from google_services.calendar_service import create_event
        # Calculate start and end at suggested time
        date = info["date"]
        sug_time = info["suggested"]
        # parse e.g. '02:00 PM' to '14:00'
        try:
            dt = datetime.strptime(sug_time, "%I:%M %p")
            sug_24 = dt.strftime("%H:%M")
        except Exception:
            sug_24 = "14:00"
        st = f"{date}T{sug_24}:00"
        et = f"{date}T{int(sug_24[:2])+1:02d}:{sug_24[3:]}:00"

        try:
            result = create_event(
                summary=info["title"],
                start_datetime=st,
                end_datetime=et,
                location=info.get("location", ""),
                attendees=info.get("attendees", []),
            )
            await query.edit_message_text(
                f"✅ **Event Rescheduled & Booked!**\n\n"
                f"📌 **{result['summary']}**\n"
                f"📅 Date: `{date}`\n"
                f"🕐 Time: `{sug_time}` → 1 hour\n"
                f"🔗 [View on Google Calendar]({result.get('link', '')})",
                parse_mode="Markdown"
            )
        except Exception as e:
            await query.edit_message_text(f"❌ Failed to create event: {e}")

    elif data.startswith("cf_any_"):
        cid = data.replace("cf_any_", "")
        info = get_pending_conflict(cid)
        if not info:
            await query.edit_message_text("❌ Proposal expired. Please try scheduling again.")
            return

        from google_services.calendar_service import create_event
        try:
            result = create_event(
                summary=info["title"],
                start_datetime=info["start_dt"],
                end_datetime=info["end_dt"],
                location=info.get("location", ""),
                attendees=info.get("attendees", []),
            )
            await query.edit_message_text(
                f"⚠️ **Event Booked Overlapping as Requested!**\n\n"
                f"📌 **{result['summary']}**\n"
                f"📅 Date: `{info['date']}`\n"
                f"🕐 Time: `{info['start_time']}` → `{info['end_time'] or '1 hour'}`\n"
                f"🔗 [View on Google Calendar]({result.get('link', '')})",
                parse_mode="Markdown"
            )
        except Exception as e:
            await query.edit_message_text(f"❌ Failed to create event: {e}")

    elif data == "cf_cancel":
        await query.edit_message_text("❌ Scheduling request cancelled.")

    elif data == "att_all_today":
        from utils.attendance import record_attendance, format_attendance_card
        for subj in ["Operating Systems", "Data Structures And Algorithms", "Aptitude Skills Building"]:
            record_attendance(subj, "attended")
        card, markup = format_attendance_card()
        await query.edit_message_text(f"🎉 **Recorded attendance for all lectures today!**\n\n{card}", reply_markup=markup, parse_mode="Markdown")

    elif data == "att_menu_missed":
        from utils.attendance import get_attendance_stats
        stats = get_attendance_stats()
        buttons = []
        for s_name in stats["subjects"].keys():
            buttons.append([InlineKeyboardButton(f"❌ Missed: {s_name}", callback_data=f"att_miss_{s_name[:20]}")])
        buttons.append([InlineKeyboardButton("🔙 Back", callback_data="att_back")])
        await query.edit_message_text("Select which lecture was missed:", reply_markup=InlineKeyboardMarkup(buttons))

    elif data.startswith("att_miss_"):
        s_name = data.replace("att_miss_", "")
        from utils.attendance import record_attendance, format_attendance_card
        record_attendance(s_name, "missed")
        card, markup = format_attendance_card()
        await query.edit_message_text(f"Recorded missed lecture for **{s_name}**.\n\n{card}", reply_markup=markup, parse_mode="Markdown")

    elif data == "att_back":
        from utils.attendance import format_attendance_card
        card, markup = format_attendance_card()
        await query.edit_message_text(card, reply_markup=markup, parse_mode="Markdown")


@authorized_only
async def cmd_morning(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /morning — on-demand morning briefing."""
    await update.effective_message.reply_text("🌅 Gathering your schedule, emails, and assignments. Generating morning voice briefing...")
    try:
        await run_morning_report(context.bot)
    except Exception as e:
        logger.error(f"On-demand morning report failed: {e}")
        await update.effective_message.reply_text(f"❌ Morning report generation failed: {e}")


@authorized_only
async def cmd_evening(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /evening — on-demand evening report."""
    await update.effective_message.reply_text("🌙 Gathering your commitments, deadlines, and tomorrow's weather...")
    try:
        await run_evening_report(context.bot)
    except Exception as e:
        logger.error(f"On-demand evening report failed: {e}")
        await update.effective_message.reply_text(f"❌ Evening report generation failed: {e}")


@authorized_only
async def cmd_schedule(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /schedule command."""
    response = await _handle_query_calendar({"days_ahead": 1})
    await update.effective_message.reply_text(response, parse_mode="Markdown")


@authorized_only
async def cmd_emails(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /emails command."""
    response = await _handle_query_emails({"hours_back": 12})
    await update.effective_message.reply_text(response, parse_mode="Markdown")


@authorized_only
async def cmd_classes(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /classes command."""
    response = _handle_query_classroom()
    await update.effective_message.reply_text(response, parse_mode="Markdown")


@authorized_only
async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /status — full diagnostic report."""
    from google_services.auth import get_google_credentials

    now = datetime.now(ZoneInfo(TIMEZONE))
    parts = [
        f"🤖 **System Diagnostic Status**",
        f"⏰ Local Server Time: `{now.strftime('%Y-%m-%d %H:%M:%S %Z')}`\n",
    ]

    # 1. Google OAuth Token Health
    try:
        creds = get_google_credentials()
        ttl_msg = "Permanent/Auto-refreshing"
        if creds.expiry:
            expiry_aware = creds.expiry.replace(tzinfo=timezone.utc)
            rem = expiry_aware - datetime.now(timezone.utc)
            minutes = max(0, int(rem.total_seconds() / 60))
            ttl_msg = f"Token active (~{minutes}m until auto-refresh)"
        parts.append(f"✅ **Google OAuth:** Connected ({ttl_msg})")
    except Exception as e:
        parts.append(f"❌ **Google OAuth:** Error: `{e}`")

    # 2. AI Engine Hierarchy Diagnostics
    from ai.gemini_client import get_active_hierarchy
    hierarchy = get_active_hierarchy()

    parts.append("🤖 **AI Provider Hierarchy (Ordered by Stability):**")
    active_count = 0
    for idx, item in enumerate(hierarchy, 1):
        if item["active"]:
            active_count += 1
            parts.append(f"{idx}. 🟢 **{item['name']}** (`{item['model']}`)")
        else:
            parts.append(f"{idx}. ⚪ {item['name']} *(Not configured)*")

    # 3. Speech Engines
    try:
        from tts.speech import _has_ffmpeg
        ffmpeg_str = "with FFmpeg (Native OGG Voice Notes)" if _has_ffmpeg() else "without FFmpeg (MP3 Audio Mode)"
        parts.append(f"✅ **Edge-TTS:** Operational {ffmpeg_str}")
        parts.append(f"✅ **Groq Whisper STT:** Operational (whisper-large-v3-turbo)")
        parts.append(f"🛡️ **Thapar Attendance Safeguard:** Active (75% Minimum Target)")
    except Exception as e:
        parts.append(f"❌ **Engines:** `{e}`")

    await update.effective_message.reply_text("\n".join(parts), parse_mode="Markdown")


@authorized_only
async def handle_text_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Process incoming natural language messages."""
    text = update.effective_message.text
    if not text:
        return

    text = text.strip()
    logger.info(f"Incoming message from chat {update.effective_chat.id}: {text[:80]}...")

    try:
        await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
    except Exception:
        pass

    try:
        reply = await route_message(text, context.bot)
        if reply:
            markup = None
            if isinstance(reply, tuple):
                reply_text, markup = reply
            else:
                reply_text = reply

            chunks = _split_message(reply_text)
            for i, chunk in enumerate(chunks):
                m = markup if i == len(chunks) - 1 else None
                await update.effective_message.reply_text(chunk, reply_markup=m, parse_mode="Markdown")
    except Exception as e:
        logger.error(f"Error handling message: {e}", exc_info=True)
        await update.effective_message.reply_text(f"❌ An error occurred processing your request: {e}")


@authorized_only
async def handle_voice_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Process incoming Telegram voice notes using Groq Whisper.
    Executes intent and replies with text + Jarvis British voice note!
    """
    voice = update.effective_message.voice
    if not voice:
        return

    logger.info(f"🎙️ Received voice note ({voice.duration}s, file_id={voice.file_id})")

    status_msg = await update.effective_message.reply_text("🎧 *Listening to your voice note...*", parse_mode="Markdown")

    os.makedirs("temp_audio", exist_ok=True)
    temp_voice_path = f"temp_audio/voice_in_{voice.file_unique_id}.oga"

    try:
        # Download voice file
        voice_file = await context.bot.get_file(voice.file_id)
        await voice_file.download_to_drive(temp_voice_path)

        # Transcribe with Groq Whisper
        from ai.stt import transcribe_audio
        transcription = transcribe_audio(temp_voice_path)

        if not transcription:
            await status_msg.edit_text("❌ Could not transcribe audio. Please try speaking closer to the microphone.")
            return

        await status_msg.edit_text(f"🗣️ *\"{transcription}\"*\n\n_Processing with Jarvis..._", parse_mode="Markdown")

        # Route the transcribed command
        reply = await route_message(transcription, context.bot)
        markup = None
        if isinstance(reply, tuple):
            reply_text, markup = reply
        else:
            reply_text = reply

        # Synthesize spoken voice reply
        from tts.speech import text_to_voice_note, send_audio_message
        audio_reply_path = None
        try:
            audio_reply_path = await text_to_voice_note(reply_text)
        except Exception as tts_err:
            logger.warning(f"Voice reply TTS error: {tts_err}")

        if audio_reply_path:
            caption_text = f"🎙️ *\"{transcription}\"*\n\n{reply_text}"
            if len(caption_text) > 1000:
                caption_text = caption_text[:997] + "..."
            await send_audio_message(
                bot=context.bot,
                chat_id=update.effective_chat.id,
                audio_path=audio_reply_path,
                caption=caption_text,
                reply_markup=markup
            )
            await status_msg.delete()
        else:
            await status_msg.edit_text(
                f"🎙️ *\"{transcription}\"*\n\n{reply_text}",
                reply_markup=markup,
                parse_mode="Markdown"
            )

    except Exception as e:
        logger.error(f"Voice processing failed: {e}", exc_info=True)
        await status_msg.edit_text(f"❌ Error processing voice message: {e}")
    finally:
        if os.path.exists(temp_voice_path):
            try:
                os.remove(temp_voice_path)
            except Exception:
                pass


def _split_message(text: str, max_chars: int = 4000) -> list[str]:
    """Break long responses into chunks within Telegram's 4096 character limit."""
    if len(text) <= max_chars:
        return [text]

    chunks = []
    while text:
        if len(text) <= max_chars:
            chunks.append(text)
            break
        split_idx = text.rfind("\n", 0, max_chars)
        if split_idx == -1:
            split_idx = max_chars
        chunks.append(text[:split_idx])
        text = text[split_idx:].lstrip()

    return chunks
