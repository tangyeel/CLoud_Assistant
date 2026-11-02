"""
bot/router.py — Natural language message router and intent dispatcher.
Directs conversational requests to appropriate Google Workspace actions or AI reasoning.
"""
from datetime import datetime
from zoneinfo import ZoneInfo
from telegram import Bot
from ai.gemini_client import generate_json, generate_text
from ai.prompts import INTENT_PARSER_SYSTEM, INTENT_PARSER_PROMPT, GENERAL_QUESTION_SYSTEM
from google_services.gmail_service import get_unread_emails
from google_services.calendar_service import (
    get_todays_events,
    get_upcoming_events,
    create_event,
)
from google_services.tasks_service import get_pending_tasks, create_task, complete_task
from google_services.classroom_service import get_all_upcoming_assignments
from config import TIMEZONE
from utils.logger import logger


# Store pending schedule conflict proposals
_PENDING_CONFLICTS: dict[str, dict] = {}
_conflict_counter = 0


def store_pending_conflict(data: dict) -> str:
    global _conflict_counter
    _conflict_counter += 1
    cid = str(_conflict_counter)
    _PENDING_CONFLICTS[cid] = data
    return cid


def get_pending_conflict(cid: str) -> dict | None:
    return _PENDING_CONFLICTS.get(cid)


def _normalize_params(parsed: dict) -> dict:
    """Flatten any nested parameters/entities/data returned by different LLM models."""
    flat = dict(parsed)
    for subkey in ("parameters", "entities", "data", "arguments", "args"):
        if isinstance(parsed.get(subkey), dict):
            for k, v in parsed[subkey].items():
                if k not in flat or not flat[k]:
                    flat[k] = v
    return flat


async def route_message(message: str, bot: Bot) -> str:
    """
    Parse a natural language text command and execute the corresponding action.
    """
    tz = ZoneInfo(TIMEZONE)
    now = datetime.now(tz)
    today_str = now.strftime("%Y-%m-%d")
    current_time_str = now.strftime("%H:%M")

    # 1. Parse intent using AI
    intent = "unknown"
    params = {}

    try:
        prompt = INTENT_PARSER_PROMPT.format(
            message=message,
            today=today_str,
            current_time=current_time_str,
        )
        parsed = generate_json(prompt, system_instruction=INTENT_PARSER_SYSTEM)
        intent = parsed.get("intent", "unknown")
        params = _normalize_params(parsed)
        logger.info(f"Identified intent '{intent}' with normalized parameters: {params}")
    except Exception as e:
        logger.warning(f"Intent parser fallback triggered: {e}")
        intent = "general_question"
        params = {"question": message}

    # 2. Dispatch to specific handlers
    if intent == "schedule_event":
        return await _handle_schedule_event(params)

    elif intent == "create_task":
        return await _handle_create_task(params)

    elif intent == "query_emails":
        return await _handle_query_emails(params)

    elif intent == "query_calendar":
        return await _handle_query_calendar(params)

    elif intent == "query_tasks":
        from bot.handlers import get_tasks_with_buttons
        return get_tasks_with_buttons()

    elif intent == "query_classroom":
        return _handle_query_classroom()

    elif intent == "complete_task":
        return _handle_complete_task(params)

    elif intent == "query_attendance":
        from utils.attendance import format_attendance_card
        return format_attendance_card()

    elif intent == "query_weather":
        from utils.weather import get_weather
        city = params.get("city")
        w = get_weather(city)
        return w["text_card"]

    elif intent == "query_news":
        from utils.news import format_news_card
        return format_news_card()

    elif intent == "search_web":
        from utils.search import search_web, get_search_context_for_ai
        q = params.get("query") or message
        results = search_web(q, max_results=3)
        if not results:
            return f"🔍 No relevant results found on the web for *'{q}'*."
        context_str = get_search_context_for_ai(q)
        prompt = (
            f"User asked: '{q}'\n\n"
            f"Live web search results:\n{context_str}\n\n"
            f"Provide a concise, factual, polite answer (2-3 sentences) directly answering the user. "
            f"Tone: J.A.R.V.I.S., polite ('sir')."
        )
        try:
            ai_ans = generate_text(prompt, system_instruction=GENERAL_QUESTION_SYSTEM)
        except Exception:
            ai_ans = results[0]["snippet"]
        links = "\n".join([f"• [{r['title']}]({r['url']})" for r in results[:2]])
        return f"{ai_ans}\n\n🔗 **Sources:**\n{links}"

    elif intent == "morning_report":
        from reports.morning import run_morning_report
        await run_morning_report(bot)
        return "🌅 Your morning voice briefing has been generated and sent above."

    elif intent == "evening_report":
        from reports.evening import run_evening_report
        await run_evening_report(bot)
        return "🌙 Your evening wind-down report has been generated and sent above."

    elif intent == "general_question":
        return _handle_general_question(params.get("question", message))

    else:
        return _handle_general_question(message)


async def _handle_schedule_event(params: dict) -> str:
    """Create a calendar event from parsed details."""
    title = (
        params.get("title")
        or params.get("summary")
        or params.get("event")
        or params.get("event_name")
        or "Scheduled Meeting"
    )
    date = params.get("date") or params.get("start_date") or params.get("day") or ""
    start_time = params.get("start_time") or params.get("time") or params.get("start") or ""
    end_time = params.get("end_time") or params.get("end") or ""
    location = params.get("location", "")
    attendees = params.get("attendees", [])

    if not date or not start_time:
        return "❌ I need both a date and start time to book this event on your Calendar."

    # Format ISO datetime strings
    start_dt = f"{date}T{start_time}:00"
    if end_time:
        end_dt = f"{date}T{end_time}:00"
    else:
        # Default 1 hour duration
        try:
            from datetime import datetime, timedelta
            st = datetime.fromisoformat(f"{date}T{start_time}")
            et = st + timedelta(hours=1)
            end_dt = et.strftime("%Y-%m-%dT%H:%M:%S")
        except Exception:
            end_dt = f"{date}T{start_time}:00"

    # Check for schedule conflicts unless forced
    force = params.get("force", False)
    if not force:
        from google_services.calendar_service import check_event_conflicts, suggest_next_free_slot
        conflicts = check_event_conflicts(start_dt, end_dt)
        if conflicts:
            from telegram import InlineKeyboardMarkup, InlineKeyboardButton
            conf = conflicts[0]
            loc_str = f" in {conf['location']}" if conf.get("location") else ""
            suggested = suggest_next_free_slot(date)

            cid = store_pending_conflict({
                "title": title,
                "date": date,
                "start_time": start_time,
                "end_time": end_time,
                "start_dt": start_dt,
                "end_dt": end_dt,
                "location": location,
                "attendees": attendees,
                "suggested": suggested,
            })

            buttons = [
                [
                    InlineKeyboardButton(f"✅ Schedule at {suggested}", callback_data=f"cf_sug_{cid}"),
                    InlineKeyboardButton("⚠️ Schedule Anyway", callback_data=f"cf_any_{cid}"),
                ],
                [InlineKeyboardButton("❌ Cancel", callback_data="cf_cancel")],
            ]
            msg = (
                f"⚠️ **Schedule Conflict Detected, sir!**\n\n"
                f"That overlaps with your **{conf['summary']}**{loc_str} (`{conf['start']}`–`{conf['end']}`).\n\n"
                f"Would you prefer to schedule **'{title}'** for **{suggested}** instead?"
            )
            return (msg, InlineKeyboardMarkup(buttons))

    try:
        result = create_event(
            summary=title,
            start_datetime=start_dt,
            end_datetime=end_dt,
            location=location,
            attendees=attendees,
        )
        link = result.get("link", "")
        link_str = f"\n🔗 [View on Google Calendar]({link})" if link else ""
        loc_str = f"\n📍 Location: {location}" if location else ""
        return (
            f"✅ **Event Scheduled!**\n\n"
            f"📌 **{result['summary']}**\n"
            f"📅 Date: `{date}`\n"
            f"🕐 Time: `{start_time}` → `{end_time or '1 hour'}`"
            f"{loc_str}"
            f"{link_str}"
        )
    except Exception as e:
        logger.error(f"Failed to create event: {e}")
        return f"❌ Could not create calendar event: {e}"


async def _handle_create_task(params: dict) -> str:
    """Create a task or reminder."""
    title = (
        params.get("title")
        or params.get("task")
        or params.get("task_title")
        or params.get("name")
        or params.get("description")
        or "New Task"
    )
    due_date = params.get("due_date") or params.get("date") or params.get("due")
    notes = params.get("notes", "")

    due_rfc = None
    if due_date:
        due_rfc = f"{due_date}T23:59:59.000Z"

    try:
        result = create_task(title=title, notes=notes, due_date=due_rfc)
        due_info = f"\n📅 Due: `{due_date}`" if due_date else ""
        return f"✅ **Task Saved to Google Tasks!**\n\n📝 **{result['title']}**{due_info}"
    except Exception as e:
        logger.error(f"Failed to create task: {e}")
        return f"❌ Could not create task: {e}"


async def _handle_query_emails(params: dict) -> str:
    """Summarize unread emails."""
    hours_back = params.get("hours_back", 12)
    try:
        emails = get_unread_emails(hours_back=hours_back)
        if not emails:
            return f"📧 No new unread priority emails in the last {hours_back} hours."

        lines = [f"📧 **{len(emails)} Unread Priority Emails** (last {hours_back}h):\n"]
        for i, em in enumerate(emails[:10], 1):
            sender_clean = em['sender'].split("<")[0].strip().replace('"', '')
            lines.append(f"{i}. **{em['subject']}**")
            lines.append(f"   👤 {sender_clean}")
            if em.get('snippet'):
                lines.append(f"   💬 _{em['snippet'][:90]}..._")
            lines.append("")
        return "\n".join(lines)
    except Exception as e:
        return f"❌ Could not retrieve emails: {e}"


async def _handle_query_calendar(params: dict) -> str:
    """Fetch calendar events."""
    days = params.get("days_ahead", 1)
    try:
        if days <= 1:
            events = get_todays_events()
            header = "📅 **Today's Agenda:**\n"
        else:
            events = get_upcoming_events(days=days)
            header = f"📅 **Agenda (Next {days} Days):**\n"

        if not events:
            return f"{header}\nYour calendar is completely open! No events scheduled."

        lines = [header]
        for ev in events:
            t = ev['start']
            if "T" in str(t):
                try:
                    dt = datetime.fromisoformat(t)
                    t = dt.strftime("%b %d, %I:%M %p")
                except Exception:
                    pass
            loc = f" (📍 {ev['location']})" if ev.get("location") else ""
            lines.append(f"• **{t}** — {ev['summary']}{loc}")

        return "\n".join(lines)
    except Exception as e:
        return f"❌ Could not retrieve calendar: {e}"


def _handle_query_tasks() -> str:
    """Fetch pending tasks."""
    try:
        tasks = get_pending_tasks()
        if not tasks:
            return "✅ All clear! You have no pending tasks on your to-do list."

        lines = [f"📝 **{len(tasks)} Pending Tasks:**\n"]
        for i, t in enumerate(tasks, 1):
            due = f" — *Due: {t['due'][:10]}*" if t.get("due") else ""
            lines.append(f"{i}. {t['title']}{due}")
        return "\n".join(lines)
    except Exception as e:
        return f"❌ Could not retrieve tasks: {e}"


def _handle_query_classroom() -> str:
    """Fetch classroom coursework."""
    try:
        assignments = get_all_upcoming_assignments()
        if not assignments:
            return "📚 No upcoming Google Classroom assignments found."

        lines = [f"📚 **Upcoming Classroom Deadlines ({len(assignments)}):**\n"]
        for a in assignments[:10]:
            due = f" — *Due: {a['due_date']}*" if a.get("due_date") else ""
            lines.append(f"• **{a['title']}** [{a.get('course_name', 'Class')}]{due}")
        return "\n".join(lines)
    except Exception as e:
        return f"❌ Could not retrieve classroom coursework: {e}"


def _handle_complete_task(params: dict) -> str:
    """Mark a task complete by title keyword match."""
    task_keyword = params.get("task_title", "").lower()
    if not task_keyword:
        return "❌ Please specify which task you'd like to complete."

    try:
        tasks = get_pending_tasks()
        matched = None
        for t in tasks:
            if task_keyword in t["title"].lower():
                matched = t
                break

        if not matched:
            return f"❌ Could not find a pending task matching '{task_keyword}'."

        complete_task(matched["id"])
        return f"✅ Marked task as complete: **{matched['title']}** 🎉"
    except Exception as e:
        return f"❌ Could not complete task: {e}"


def _handle_general_question(question: str) -> str:
    """Answer general queries using Gemini AI."""
    try:
        return generate_text(question, system_instruction=GENERAL_QUESTION_SYSTEM)
    except Exception as e:
        return f"❌ AI Assistant reasoning failed: {e}"
