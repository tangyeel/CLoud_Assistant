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
    Integrated with 4-Layer Cognitive Memory (Working Memory, Recall, Reflection).
    """
    import asyncio
    from utils.memory import (
        working_memory,
        recall_relevant_memories,
        format_memories_for_prompt,
        reflect_and_memorize,
    )

    # 1. Update Working Memory & Recall Relevant Semantic Memories
    working_memory.add_turn("user", message)
    recalled_mems = recall_relevant_memories(message, top_k=3)
    recalled_context = format_memories_for_prompt(recalled_mems)

    tz = ZoneInfo(TIMEZONE)
    now = datetime.now(tz)
    today_str = now.strftime("%Y-%m-%d")
    current_time_str = now.strftime("%H:%M")

    # 2. Parse intent using AI
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

    reply = ""

    # 3. Dispatch to specific handlers
    if intent == "schedule_event":
        reply = await _handle_schedule_event(params)

    elif intent == "create_task":
        reply = await _handle_create_task(params)

    elif intent == "query_emails":
        reply = await _handle_query_emails(params)

    elif intent == "query_calendar":
        reply = await _handle_query_calendar(params)

    elif intent == "query_tasks":
        from bot.handlers import get_tasks_with_buttons
        reply = get_tasks_with_buttons()

    elif intent == "query_classroom":
        reply = _handle_query_classroom()

    elif intent == "complete_task":
        reply = _handle_complete_task(params)

    elif intent == "query_attendance":
        from utils.attendance import format_attendance_card
        reply = format_attendance_card()

    elif intent == "query_weather":
        from utils.weather import get_weather
        city = params.get("city")
        w = get_weather(city)
        reply = w["text_card"]

    elif intent == "query_news":
        from utils.news import format_news_card
        reply = format_news_card()

    elif intent == "query_market":
        from utils.finance import get_market_snapshot
        reply = get_market_snapshot()

    elif intent == "query_stock":
        from utils.finance import fuzzy_resolve_stock, get_stock_details
        company_query = params.get("company") or params.get("stock") or params.get("symbol") or message
        name, ticker = fuzzy_resolve_stock(company_query)
        if not ticker:
            reply = f"❌ Could not identify stock for *'{company_query}'*. Try using full company name or ticker (e.g. `/stock Reliance`)."
        else:
            reply = get_stock_details(ticker, company_name=name or "")

    elif intent == "analyze_stock":
        reply = await _handle_analyze_stock(params, message)

    elif intent == "query_ipo":
        from utils.ipo import format_ipo_card
        reply = format_ipo_card()

    elif intent == "manage_thesis":
        reply = _handle_manage_thesis(params, message)

    elif intent == "set_price_alert":
        reply = _handle_set_price_alert(params, message)

    elif intent == "query_alerts":
        reply = _handle_query_alerts(params)

    elif intent == "manage_watchlist":
        from utils.earnings import format_watchlist_card, add_to_watchlist, remove_from_watchlist
        action = (params.get("action") or "view").lower()
        stocks = params.get("stocks") or params.get("company") or ""
        if action in ("add", "new") and stocks:
            count, added, msg = add_to_watchlist(stocks)
            reply = msg
        elif action in ("remove", "delete", "del") and stocks:
            ok, msg = remove_from_watchlist(stocks)
            reply = msg
        else:
            reply = format_watchlist_card()

    elif intent == "query_earnings":
        from utils.earnings import triage_stock_earnings, format_watchlist_card
        from utils.finance import fuzzy_resolve_stock
        stock_query = params.get("company") or params.get("stock") or ""
        if stock_query:
            name, ticker = fuzzy_resolve_stock(stock_query)
            if ticker:
                reply = triage_stock_earnings(ticker, company_name=name or "")
            else:
                reply = f"❌ Could not resolve *'{stock_query}'* to an active stock. Try the full company name."
        else:
            reply = format_watchlist_card()


    elif intent == "query_memory":
        from utils.memory import list_all_memories
        reply = list_all_memories()

    elif intent == "forget_memory":
        from utils.memory import forget_memory
        topic = params.get("topic") or message.replace("forget", "").replace("delete", "").strip()
        ok, msg = forget_memory(topic)
        reply = msg

    elif intent == "search_web":
        from utils.search import search_web, get_search_context_for_ai
        q = params.get("query") or message
        results = search_web(q, max_results=3)
        if not results:
            reply = f"🔍 No relevant results found on the web for *'{q}'*."
        else:
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
            reply = f"{ai_ans}\n\n🔗 **Sources:**\n{links}"

    elif intent == "morning_report":
        from reports.morning import run_morning_report
        await run_morning_report(bot)
        reply = "🌅 Your morning voice briefing has been generated and sent above."

    elif intent == "evening_report":
        from reports.evening import run_evening_report
        await run_evening_report(bot)
        reply = "🌙 Your evening wind-down report has been generated and sent above."

    elif intent == "general_question":
        reply = _handle_general_question(params.get("question", message), recalled_context=recalled_context)

    else:
        reply = _handle_general_question(message, recalled_context=recalled_context)

    # 4. Record Assistant Turn & Trigger Background Reflection
    try:
        reply_text = reply[0] if isinstance(reply, tuple) else str(reply)
        working_memory.add_turn("assistant", reply_text)
        asyncio.create_task(reflect_and_memorize(message, reply_text))
    except Exception as e:
        logger.debug(f"Memory post-processing skipped: {e}")

    return reply



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


def _handle_general_question(question: str, recalled_context: str = "") -> str:
    """Answer general queries using AI cascade, augmented with Working Memory & Recalled Facts."""
    try:
        from utils.memory import working_memory
        recent_history = working_memory.get_context_string(max_turns=6)

        system_instruction = GENERAL_QUESTION_SYSTEM
        if recalled_context:
            system_instruction = f"{GENERAL_QUESTION_SYSTEM}\n\n{recalled_context}"

        user_content = question
        if recent_history:
            user_content = f"Recent conversation flow:\n{recent_history}\n\nCurrent query: {question}"

        return generate_text(user_content, system_instruction=system_instruction)
    except Exception as e:
        return f"❌ AI Assistant reasoning failed: {e}"



async def _handle_analyze_stock(params: dict, message: str) -> str:
    """Run an AI financial fundamental analysis on a stock."""
    from utils.finance import fuzzy_resolve_stock, build_analyst_context
    from ai.prompts import ANALYST_SYSTEM, ANALYST_PROMPT

    company_query = params.get("company") or params.get("stock") or message
    name, ticker = fuzzy_resolve_stock(company_query)
    if not ticker:
        return f"❌ Could not identify stock for *'{company_query}'*. Please specify the company name (e.g. *Analyze Reliance*)."

    ctx = build_analyst_context(ticker)
    if ctx.get("error"):
        return f"❌ Could not retrieve financial data for `{ticker}`: {ctx['error']}"

    prompt = ANALYST_PROMPT.format(
        company_name=ctx.get("name") or name,
        ticker=ticker,
        sector=ctx.get("sector") or "N/A",
        industry=ctx.get("industry") or "N/A",
        price=f"₹{ctx['price']:,.2f}" if ctx.get("price") else "N/A",
        low_52=f"₹{ctx['52w_low']:,.2f}" if ctx.get("52w_low") else "N/A",
        high_52=f"₹{ctx['52w_high']:,.2f}" if ctx.get("52w_high") else "N/A",
        mkt_cap=f"₹{ctx['mkt_cap']:,}" if ctx.get("mkt_cap") else "N/A",
        pe=f"{ctx['pe']:.2f}" if ctx.get("pe") else "N/A",
        forward_pe=f"{ctx['forward_pe']:.2f}" if ctx.get("forward_pe") else "N/A",
        pb=f"{ctx['pb']:.2f}" if ctx.get("pb") else "N/A",
        roe=f"{ctx['roe']*100:.2f}%" if ctx.get("roe") else "N/A",
        roa=f"{ctx['roa']*100:.2f}%" if ctx.get("roa") else "N/A",
        debt_equity=f"{ctx['debt_equity']:.2f}" if ctx.get("debt_equity") else "N/A",
        current_ratio=f"{ctx['current_ratio']:.2f}" if ctx.get("current_ratio") else "N/A",
        fcf=f"₹{ctx['fcf']:,}" if ctx.get("fcf") else "N/A",
        div_yield=f"{ctx['div_yield']*100:.2f}%" if ctx.get("div_yield") else "N/A",
        beta=f"{ctx['beta']:.2f}" if ctx.get("beta") else "N/A",
        summary=ctx.get("summary") or "Leading industry participant.",
    )

    try:
        analysis = generate_text(prompt, system_instruction=ANALYST_SYSTEM)
        header = f"🏛️ **Financial Intelligence Assessment: {name} ({ticker})**\n\n"
        return header + analysis
    except Exception as e:
        logger.error(f"Stock analysis LLM failure: {e}")
        return f"❌ Financial analyst generation failed: {e}"


def _handle_manage_thesis(params: dict, message: str) -> str:
    """Handle thesis actions: log, view, close."""
    from utils.thesis import add_thesis, close_thesis, format_theses_card
    action = (params.get("action") or "view").lower()

    if action == "close":
        target = params.get("company") or params.get("thesis_id") or ""
        if not target:
            return "Please specify the thesis ID or company name to close (e.g. `/thesis close th_123` or `/thesis close Infosys`)."
        ok, msg = close_thesis(target)
        return msg

    elif action in ("log", "new", "add", "create"):
        company = params.get("company") or ""
        entry = float(params.get("entry_price") or 0)
        target = float(params.get("target_price") or 0)
        sl = float(params.get("stoploss") or 0) if params.get("stoploss") else None
        rationale = params.get("rationale") or ""

        if not company or target <= 0:
            return (
                "❌ To log an investment thesis, please provide company and target price.\n"
                "Example: `Log thesis: Buy HDFC Bank at 1720, target 1950, stoploss 1650, rationale: NIM expansion`"
            )

        ok, msg = add_thesis(
            query=company,
            entry_price=entry,
            target_price=target,
            stoploss=sl,
            rationale=rationale,
        )
        return msg

    else:
        # Default view
        return format_theses_card()


def _handle_set_price_alert(params: dict, message: str) -> str:
    """Set a price alert from parsed params or fallback to natural language text."""
    from utils.price_alerts import create_price_alert, parse_and_create_alert_from_text

    company = params.get("company")
    tgt = params.get("target_price")
    pct = params.get("pct_change")
    direction = params.get("direction")

    if company and (tgt or pct):
        ok, msg = create_price_alert(
            query=company,
            target_price=float(tgt) if tgt else None,
            pct_change=float(pct) if pct else None,
            direction=direction,
            raw_instruction=message,
        )
        return msg

    # Fallback to text parsing
    ok, msg = parse_and_create_alert_from_text(message)
    return msg


def _handle_query_alerts(params: dict) -> str:
    """List or cancel price alerts."""
    from utils.price_alerts import list_alerts_card, cancel_alert
    action = (params.get("action") or "view").lower()
    if action == "cancel":
        aid = params.get("alert_id") or params.get("company") or ""
        if not aid:
            return "Please specify the alert ID or company to cancel (e.g. `/alerts cancel alt_123`)."
        ok, msg = cancel_alert(aid)
        return msg
    return list_alerts_card()

