"""
bot/handlers.py — Telegram bot command, voice note, and interactive message handlers.
"""
import os
import uuid
from datetime import datetime, timedelta, timezone
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


_PENDING_EXAM_IMPORTS: dict[str, dict] = {}


@authorized_only
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /start command."""
    await update.effective_message.reply_text(
        "👋 **Welcome to your Autonomous AI Personal Assistant!**\n\n"
        "I am connected to your Google Workspace and ready 24/7.\n\n"
        "🎙️ **Two-Way Voice Supported:**\n"
        "Send me any voice note anytime — I will transcribe, execute, and speak back!\n\n"
        "📅 **Daily Briefings:**\n"
        "• Morning report at 06:30 AM (emails, tasks, calendar, classroom, weather)\n"
        "• Evening wind-down at 08:00 PM (commitments, deadlines, tomorrow's weather)\n\n"
        "⚡ **Smart Safeguards Active:**\n"
        "• 15-Minute Time-to-Leave lecture alerts\n"
        "• Calendar conflict detection with auto-suggested free slots\n"
        "• Thapar Attendance 75% safeguard (/attendance)\n\n"
        "Type /help for direct slash commands.",
        parse_mode="Markdown",
    )


def get_help_master_menu():
    """Build the master command navigation card with interactive buttons."""
    text = (
        "🤖 **J.A.R.V.I.S. Command & Intelligence Center**\n\n"
        "Welcome, sir. I am equipped with **20+ autonomous tools** covering Indian & global financial markets, "
        "university academic safeguards, cognitive vector memory, and ambient voice briefings.\n\n"
        "Select a category below for focused syntax & real-world examples, or tap **Full Guide**."
    )
    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("📈 Markets & Trading", callback_data="help_market"),
            InlineKeyboardButton("🎓 University & Schedule", callback_data="help_academic"),
        ],
        [
            InlineKeyboardButton("🧠 Memory & AI Analyst", callback_data="help_memory"),
            InlineKeyboardButton("🎙️ Voice & Briefings", callback_data="help_voice"),
        ],
        [
            InlineKeyboardButton("📖 Full Command Guide (All 20+)", callback_data="help_all"),
        ]
    ])
    return text, keyboard


def get_help_section(section: str):
    """Return specific help section text and back-navigation markup."""
    back_button = InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Help Menu", callback_data="help_menu")]])

    if section == "help_market":
        text = (
            "📈 **MARKET & FINANCIAL INTELLIGENCE**\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            "• `/market`\n"
            "  ↳ *Description:* Instant snapshot of Indian indices (Nifty 50, Sensex, VIX, Bank Nifty, Midcap, Smallcap), Global benchmarks (S&P 500, Nasdaq, Dow, FTSE, Nikkei), Gold, Crude & USD/INR.\n"
            "  ↳ *Usage:* `/market`\n\n"
            "• `/stock <name or symbol>`\n"
            "  ↳ *Description:* Live quote, 52W range, valuation ratios (P/E, P/B, EPS, Market Cap), upcoming earnings report date & recent news. Typo-tolerant (e.g. 'relince' resolves to Reliance).\n"
            "  ↳ *Usage:* `/stock Reliance` or `/stock infy` or `/stock tata moters`\n\n"
            "• `/watchlist [add | remove]`\n"
            "  ↳ *Description:* Manage your custom earnings watchlist. Only tracks quarterly results and sends autonomous alerts for stocks on this list.\n"
            "  ↳ *Usage:*\n"
            "    - View watchlist & countdowns: `/watchlist`\n"
            "    - Add multiple stocks: `/watchlist add Reliance, Infosys, Tata Motors`\n"
            "    - Remove stock: `/watchlist remove TCS`\n\n"
            "• `/earnings [stock]`\n"
            "  ↳ *Description:* Autonomous quarterly earnings triage. Evaluates Revenue, Operating Margin, Net Profit, and Consensus Beat/Miss %. Cross-checks against active investment theses.\n"
            "  ↳ *Usage:* `/earnings Infosys` or `/earnings` (triages all watchlist stocks)\n\n"
            "• `/ipo`\n"
            "  ↳ *Description:* Upcoming and open IPOs with issue price band, Grey Market Premium (GMP ₹ and % est. gain), subscription multiplier, and dates.\n"
            "  ↳ *Usage:* `/ipo` *(also auto-sent every Saturday at 08:00 AM)*\n\n"
            "• `/thesis [new | close]`\n"
            "  ↳ *Description:* Track high-conviction investment theses with entry price, targets, stop-losses, and rationale. Background checks alert when target or stoploss is breached.\n"
            "  ↳ *Usage:*\n"
            "    - View portfolio: `/thesis`\n"
            "    - Log new: `/thesis new INFY 1850 2100 1750 Cloud margin acceleration`\n"
            "    - Close: `/thesis close INFY`\n\n"
            "• `/alerts [cancel]`\n"
            "  ↳ *Description:* Persistent price target and percentage volatility alerts evaluated every 5 minutes.\n"
            "  ↳ *Usage:*\n"
            "    - View active: `/alerts`\n"
            "    - Cancel: `/alerts cancel alt_123` or `/alerts cancel Reliance`\n"
            "    - Set in plain English: *'Alert me when Infosys hits 1900'* or *'Alert if Nifty drops 2%'*\n\n"
            "• `/stealth [stock]`\n"
            "  ↳ *Description:* Official NSE deliverable volume screener. Detects where institutions are taking physical delivery into demat accounts (>60% delivery) vs day-trading churn.\n"
            "  ↳ *Usage:*\n"
            "    - Market-wide accumulation radar: `/stealth`\n"
            "    - Specific stock delivery check: `/stealth HDFCBANK` or `/stealth INFY`"
        )
        return text, back_button

    elif section == "help_academic":
        text = (
            "🎓 **ACADEMIC & SCHEDULE SAFEGUARDS**\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            "• `/attendance`\n"
            "  ↳ *Description:* Thapar University 75% attendance safeguard. Tracks attended vs missed lectures, calculates safe bunks remaining, and prompts for check-ins.\n"
            "  ↳ *Usage:* `/attendance`\n\n"
            "• `/classes`\n"
            "  ↳ *Description:* Scans Google Classroom across Personal & Thapar accounts. Only displays actionable, unsubmitted assignments with future due dates.\n"
            "  ↳ *Usage:* `/classes`\n\n"
            "• `/schedule`\n"
            "  ↳ *Description:* Agenda preview for today's commitments and university classes.\n"
            "  ↳ *Usage:* `/schedule`\n\n"
            "• `/tasks`\n"
            "  ↳ *Description:* Interactive Google Tasks list with one-tap [Done] and [Snooze 24h] action buttons.\n"
            "  ↳ *Usage:* `/tasks`\n\n"
            "• `/emails`\n"
            "  ↳ *Description:* Summarizes unread priority emails from the last 12 hours across Personal & Thapar inboxes.\n"
            "  ↳ *Usage:* `/emails`\n\n"
            "• *Exam Timetable OCR Vision:*\n"
            "  ↳ Send any photo of a printed or digital exam schedule. J.A.R.V.I.S. reads it with Vision AI and adds all exam dates to Google Calendar with one click."
        )
        return text, back_button

    elif section == "help_memory":
        text = (
            "🧠 **COGNITIVE MEMORY & REASONING**\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            "• `/memory`\n"
            "  ↳ *Description:* View the persistent personal facts, portfolio guidelines, and preferences learned autonomously by the 4-layer vector memory.\n"
            "  ↳ *Usage:* `/memory`\n\n"
            "• `/forget <topic or id>`\n"
            "  ↳ *Description:* Purge a specific learned preference, outdated habit, or memory ID from the Upstash Vector cloud store.\n"
            "  ↳ *Usage:* `/forget Tata Motors` or `/forget risk tolerance`\n\n"
            "• *Natural Language Stock Analysis:*\n"
            "  ↳ Tell Jarvis: *'Analyze ITC'* or *'Fundamental breakdown of HDFC Bank'*. Synthesizes a 4-pillar institutional breakdown (Moat, Financial Health, Valuation, Risks)."
        )
        return text, back_button

    elif section == "help_voice":
        text = (
            "🎙️ **VOICE, DAILY BRIEFINGS & TOOLS**\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            "• `/morning` — Trigger on-demand Jarvis British voice morning briefing (weather, schedule, priority emails, tasks, open assignments).\n"
            "• `/evening` — Forward-looking evening debrief focusing on tomorrow's earliest commitment, weather, and open deadlines.\n"
            "• `/weather` — Real-time weather and precipitation chance for Patiala.\n"
            "• `/news` — Live market, tech, and financial news headlines.\n"
            "• `/search <query>` — Real-time DuckDuckGo web search with cited sources.\n"
            "• `/status` — Diagnostic report (Google OAuth health, AI cascade order, Edge-TTS status, Upstash Vector connection).\n\n"
            "🎙️ *Two-Way Voice Support:*\n"
            "Send any Telegram voice note anytime. J.A.R.V.I.S. transcribes via Groq Whisper, executes your request, and responds with British voice audio!"
        )
        return text, back_button

    else:
        # Full guide
        all_text = (
            "📖 **J.A.R.V.I.S. Full Command Reference**\n\n"
            "📈 **MARKETS:**\n"
            "• `/market` — Real-time Indian & global index snapshot\n"
            "• `/stock <name>` — Quote, ratios, earnings date & news (typo-tolerant)\n"
            "• `/watchlist [add|remove]` — Custom earnings watchlist\n"
            "• `/earnings [stock]` — Autonomous quarterly financial results triage\n"
            "• `/ipo` — Live IPO GMP radar & subscription status\n"
            "• `/thesis [new|close]` — Investment thesis portfolio with target/SL tracking\n"
            "• `/alerts [cancel]` — 5-minute price target & movement alerts\n\n"
            "🎓 **ACADEMIC & SCHEDULE:**\n"
            "• `/attendance` — Thapar 75% attendance safeguard & safe bunks\n"
            "• `/classes` — Google Classroom unsubmitted assignments with future due dates\n"
            "• `/schedule` — Today's agenda & calendar commitments\n"
            "• `/tasks` — Interactive to-do list with [Done] and [Snooze] buttons\n"
            "• `/emails` — Unread priority emails across Personal & Thapar\n"
            "• *Photo OCR:* Upload exam schedule photos to sync with Google Calendar\n\n"
            "🧠 **MEMORY & AI:**\n"
            "• `/memory` — Inspect learned facts in Upstash Vector cloud\n"
            "• `/forget <topic>` — Erase a fact or outdated preference\n"
            "• *Natural Language:* Ask *'Analyze <stock>'* for 4-pillar fundamental report\n\n"
            "🎙️ **VOICE & UTILITIES:**\n"
            "• `/morning` — Morning British voice briefing\n"
            "• `/evening` — Evening preparatory debrief\n"
            "• `/weather` — Real-time Patiala forecast\n"
            "• `/news` — Top tech & finance news\n"
            "• `/search <q>` — Live web search\n"
            "• `/status` — System health & AI provider diagnostics\n\n"
            "🎙️ *Send voice notes anytime for spoken audio responses!*"
        )
        return all_text, back_button


@authorized_only
async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /help command with interactive category navigation."""
    text, markup = get_help_master_menu()
    await update.effective_message.reply_text(text, reply_markup=markup, parse_mode="Markdown")



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
async def cmd_market(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /market — Indian & Global market snapshot."""
    from utils.finance import get_market_snapshot
    card = get_market_snapshot()
    await update.effective_message.reply_text(card, parse_mode="Markdown")


@authorized_only
async def cmd_stock(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /stock <name> — typo-tolerant stock overview, news, and earnings."""
    query = " ".join(context.args) if context.args else ""
    if not query:
        await update.effective_message.reply_text(
            "Please provide a stock name or ticker, e.g. `/stock Reliance` or `/stock infy`",
            parse_mode="Markdown",
        )
        return

    from utils.finance import fuzzy_resolve_stock, get_stock_details
    name, ticker = fuzzy_resolve_stock(query)
    if not ticker:
        await update.effective_message.reply_text(
            f"❌ Could not resolve *'{query}'* to an active stock. Try the full company name (e.g. `/stock Tata Motors`).",
            parse_mode="Markdown",
        )
        return

    card = get_stock_details(ticker, company_name=name or "")
    await update.effective_message.reply_text(card, parse_mode="Markdown")


@authorized_only
async def cmd_ipo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /ipo — Live IPO intelligence & GMP report."""
    from utils.ipo import format_ipo_card
    card = format_ipo_card()
    await update.effective_message.reply_text(card, parse_mode="Markdown")


@authorized_only
async def cmd_thesis(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /thesis — view, new, or close investment thesis."""
    args = context.args or []
    from utils.thesis import format_theses_card, add_thesis, close_thesis

    if not args:
        card = format_theses_card()
        await update.effective_message.reply_text(card, parse_mode="Markdown")
        return

    subcmd = args[0].lower()
    if subcmd == "close" and len(args) > 1:
        target = " ".join(args[1:])
        ok, msg = close_thesis(target)
        await update.effective_message.reply_text(msg, parse_mode="Markdown")
    elif subcmd in ("new", "add", "log") and len(args) >= 3:
        # /thesis new <symbol> <entry> <target> [stoploss] [rationale...]
        sym = args[1]
        try:
            entry = float(args[2])
            target = float(args[3])
            sl = float(args[4]) if len(args) > 4 and args[4].replace(".", "", 1).isdigit() else None
            rat_idx = 5 if sl is not None else 4
            rationale = " ".join(args[rat_idx:]) if len(args) > rat_idx else ""
            ok, msg = add_thesis(sym, entry, target, sl, rationale)
            await update.effective_message.reply_text(msg, parse_mode="Markdown")
        except ValueError:
            await update.effective_message.reply_text(
                "❌ Invalid format. Usage: `/thesis new <symbol> <entry_price> <target_price> [stoploss] [rationale]`",
                parse_mode="Markdown",
            )
    else:
        # Default: view
        card = format_theses_card()
        await update.effective_message.reply_text(card, parse_mode="Markdown")


@authorized_only
async def cmd_alerts(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /alerts — view or cancel price alerts."""
    args = context.args or []
    from utils.price_alerts import list_alerts_card, cancel_alert

    if args and args[0].lower() in ("cancel", "del", "remove") and len(args) > 1:
        target = " ".join(args[1:])
        ok, msg = cancel_alert(target)
        await update.effective_message.reply_text(msg, parse_mode="Markdown")
    else:
        card = list_alerts_card()
        await update.effective_message.reply_text(card, parse_mode="Markdown")


@authorized_only
async def cmd_memory(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /memory — list learned facts and persistent preferences."""
    from utils.memory import list_all_memories
    card = list_all_memories()
    await update.effective_message.reply_text(card, parse_mode="Markdown")


@authorized_only
async def cmd_forget(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /forget <topic> — purge specific memories."""
    query = " ".join(context.args) if context.args else ""
    if not query:
        await update.effective_message.reply_text(
            "Please specify what you would like me to forget, e.g. `/forget Tata Motors` or `/forget risk tolerance`",
            parse_mode="Markdown",
        )
        return

    from utils.memory import forget_memory
    ok, msg = forget_memory(query)
    await update.effective_message.reply_text(msg, parse_mode="Markdown")


@authorized_only
async def cmd_watchlist(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /watchlist — view, add, or remove tracked stocks for earnings triage."""
    args = context.args or []
    from utils.earnings import format_watchlist_card, add_to_watchlist, remove_from_watchlist

    if not args:
        card = format_watchlist_card()
        await update.effective_message.reply_text(card, parse_mode="Markdown")
        return

    subcmd = args[0].lower()
    if subcmd in ("add", "new") and len(args) > 1:
        raw_stocks = " ".join(args[1:])
        count, added, msg = add_to_watchlist(raw_stocks)
        await update.effective_message.reply_text(msg, parse_mode="Markdown")
    elif subcmd in ("remove", "del", "delete", "rm") and len(args) > 1:
        target = " ".join(args[1:])
        ok, msg = remove_from_watchlist(target)
        await update.effective_message.reply_text(msg, parse_mode="Markdown")
    else:
        # Default: if user typed `/watchlist reliance` without typing 'add'
        raw_stocks = " ".join(args)
        count, added, msg = add_to_watchlist(raw_stocks)
        await update.effective_message.reply_text(msg, parse_mode="Markdown")


@authorized_only
async def cmd_earnings(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /earnings [stock] — autonomous quarterly results triage."""
    args = context.args or []
    from utils.earnings import triage_stock_earnings, get_watchlist
    from utils.finance import fuzzy_resolve_stock

    if args:
        stock_query = " ".join(args)
        name, ticker = fuzzy_resolve_stock(stock_query)
        if not ticker:
            await update.effective_message.reply_text(
                f"❌ Could not resolve *'{stock_query}'* to an active stock. Try the full company name (e.g. `/earnings Infosys`).",
                parse_mode="Markdown",
            )
            return
        triage_card = triage_stock_earnings(ticker, company_name=name or "")
        await update.effective_message.reply_text(triage_card, parse_mode="Markdown")
    else:
        # Triage all watchlist stocks
        watchlist = get_watchlist()
        if not watchlist:
            await update.effective_message.reply_text(
                "Your earnings watchlist is empty, sir. Add stocks using `/watchlist add <name>` (e.g. `/watchlist add Reliance, INFY`) or check a specific stock with `/earnings <name>`.",
                parse_mode="Markdown",
            )
            return

        await update.effective_message.reply_text(f"📊 Running autonomous earnings triage on your **{len(watchlist)} watchlist stocks**...")
        for w in watchlist[:5]:
            card = triage_stock_earnings(w["ticker"], w["company"])
            await update.effective_message.reply_text(card, parse_mode="Markdown")


@authorized_only
async def cmd_stealth(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /stealth [stock] — institutional deliverable volume screener."""
    args = context.args or []
    from utils.stealth_delivery import format_stealth_delivery_card
    from utils.finance import fuzzy_resolve_stock

    if args:
        query = " ".join(args)
        name, ticker = fuzzy_resolve_stock(query)
        target = ticker or query
        card = format_stealth_delivery_card(custom_symbol=target)
        await update.effective_message.reply_text(card, parse_mode="Markdown")
    else:
        card = format_stealth_delivery_card()
        await update.effective_message.reply_text(card, parse_mode="Markdown")






@authorized_only
async def handle_callback_query(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle interactive inline button taps."""
    query = update.callback_query
    await query.answer()

    data = query.data
    logger.info(f"Button callback triggered: {data}")

    if data.startswith("exam_cancel_"):
        _PENDING_EXAM_IMPORTS.pop(data.removeprefix("exam_cancel_"), None)
        await query.edit_message_text("Exam schedule import cancelled.")

    elif data.startswith("exam_add_"):
        token = data.removeprefix("exam_add_")
        draft = _PENDING_EXAM_IMPORTS.pop(token, None)
        if (not draft or draft["chat_id"] != update.effective_chat.id
                or draft["expires"] < datetime.now(timezone.utc)):
            await query.edit_message_text("This exam schedule preview expired. Please upload the photo again.")
            return

        from google_services.calendar_service import create_event
        created, failed = [], []
        for exam in draft["exams"]:
            try:
                if exam["start_datetime"]:
                    create_event(
                        summary=f"Exam: {exam['subject']}",
                        start_datetime=exam["start_datetime"],
                        end_datetime=exam["end_datetime"],
                        location=exam["location"],
                        description="Added from an exam schedule photo.",
                    )
                else:
                    exam_date = datetime.strptime(exam["date"], "%Y-%m-%d").date()
                    create_event(
                        summary=f"Exam: {exam['subject']}",
                        start_datetime=exam_date.isoformat(),
                        end_datetime=(exam_date + timedelta(days=1)).isoformat(),
                        location=exam["location"],
                        description="Added from an exam schedule photo.",
                        all_day=True,
                    )
                created.append(exam["subject"])
            except Exception as e:
                logger.error(f"Could not add exam '{exam['subject']}' to Calendar: {e}")
                failed.append(exam["subject"])

        result = f"✅ Added {len(created)} exam(s) to Google Calendar."
        if failed:
            result += "\nCould not add: " + ", ".join(failed)
        await query.edit_message_text(result)

    elif data.startswith("help_"):
        if data == "help_menu":
            text, markup = get_help_master_menu()
            await query.edit_message_text(text, reply_markup=markup, parse_mode="Markdown")
        else:
            text, markup = get_help_section(data)
            await query.edit_message_text(text, reply_markup=markup, parse_mode="Markdown")

    elif data == "btn_agenda":
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


@authorized_only
async def handle_exam_schedule_photo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Read a timetable photo, preview detected exams, and wait for Calendar confirmation."""
    message = update.effective_message
    photo = message.photo[-1] if message and message.photo else None
    if not photo:
        return
    if photo.file_size and photo.file_size > 20 * 1024 * 1024:
        await message.reply_text("That image is too large. Please send a smaller photo of the timetable.")
        return

    status = await message.reply_text("🔎 Reading the exam schedule…")
    try:
        tg_file = await context.bot.get_file(photo.file_id)
        image_bytes = await tg_file.download_as_bytearray()
        from ai.gemini_client import read_exam_schedule_image

        today = datetime.now(ZoneInfo(TIMEZONE)).date().isoformat()
        parsed = read_exam_schedule_image(bytes(image_bytes), "image/jpeg", today)
        exams = []
        for row in parsed.get("exams", []):
            try:
                exam_date = datetime.strptime(str(row.get("date", "")), "%Y-%m-%d").date()
                subject = " ".join(str(row.get("subject", "")).split())[:150]
                if not subject:
                    continue
                start_time = row.get("start_time")
                end_time = row.get("end_time")
                start_datetime = end_datetime = None
                if start_time:
                    start_clock = datetime.strptime(str(start_time), "%H:%M").time()
                    start_dt = datetime.combine(exam_date, start_clock)
                    if end_time:
                        end_dt = datetime.combine(
                            exam_date, datetime.strptime(str(end_time), "%H:%M").time()
                        )
                        if end_dt <= start_dt:
                            continue
                    else:
                        end_dt = start_dt + timedelta(hours=2)
                    start_datetime = start_dt.isoformat()
                    end_datetime = end_dt.isoformat()
                exams.append({
                    "subject": subject,
                    "date": exam_date.isoformat(),
                    "start_datetime": start_datetime,
                    "end_datetime": end_datetime,
                    "location": " ".join(str(row.get("location") or "").split())[:200],
                })
            except (TypeError, ValueError):
                continue

        if not exams:
            await status.edit_text("I couldn’t read any complete exam dates. Try a clearer, straight-on photo.")
            return

        exams = exams[:25]
        now_utc = datetime.now(timezone.utc)
        _PENDING_EXAM_IMPORTS.update({
            key: value for key, value in _PENDING_EXAM_IMPORTS.items()
            if value["expires"] > now_utc
        })
        token = uuid.uuid4().hex[:12]
        _PENDING_EXAM_IMPORTS[token] = {
            "chat_id": update.effective_chat.id,
            "exams": exams,
            "expires": now_utc + timedelta(minutes=15),
        }
        rows = []
        for exam in exams:
            date_text = datetime.strptime(exam["date"], "%Y-%m-%d").strftime("%a, %b %d, %Y")
            time_text = (f"{exam['start_datetime'][11:16]}–{exam['end_datetime'][11:16]}"
                         if exam["start_datetime"] else "All day")
            location_text = f" · {exam['location']}" if exam["location"] else ""
            rows.append(f"• {date_text} · {time_text} · {exam['subject']}{location_text}")
        uncertain = parsed.get("uncertain", [])
        review_note = "\n\nPlease check the detected details before adding them." \
            if uncertain else "\n\nPlease review before adding these to your calendar."
        if uncertain:
            review_note += "\nNeeds a closer look: " + "; ".join(str(item) for item in uncertain[:4])

        keyboard = InlineKeyboardMarkup([[
            InlineKeyboardButton("✅ Add to Calendar", callback_data=f"exam_add_{token}"),
            InlineKeyboardButton("Cancel", callback_data=f"exam_cancel_{token}"),
        ]])
        await status.edit_text("📚 I found these exams:\n\n" + "\n".join(rows) + review_note,
                               reply_markup=keyboard)
    except Exception as e:
        logger.error(f"Exam schedule photo processing failed: {e}", exc_info=True)
        await status.edit_text(f"❌ I couldn’t read that schedule: {e}")


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
