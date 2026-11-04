"""
utils/earnings.py — Autonomous Earnings Triage & Custom Watchlist Tracker.
Tracks quarterly financial results, consensus beats/misses, upcoming dates, and thesis impacts
for a user-configurable watchlist of stocks.
"""
from __future__ import annotations
import json
from datetime import datetime, date
from pathlib import Path
from zoneinfo import ZoneInfo
from typing import Optional, Any

from config import TIMEZONE
from utils.logger import logger
from utils.finance import fuzzy_resolve_stock, _fetch_price

WATCHLIST_FILE = Path(__file__).parent.parent / "data" / "watchlist.json"


# ============================================================================
# 1. Watchlist Persistence & CRUD
# ============================================================================

def _load_watchlist() -> list[dict]:
    if not WATCHLIST_FILE.exists():
        return []
    try:
        data = json.loads(WATCHLIST_FILE.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except Exception as e:
        logger.error(f"Error loading {WATCHLIST_FILE}: {e}")
        return []


def _save_watchlist(watchlist: list[dict]) -> None:
    try:
        WATCHLIST_FILE.parent.mkdir(parents=True, exist_ok=True)
        WATCHLIST_FILE.write_text(json.dumps(watchlist, indent=2, ensure_ascii=False), encoding="utf-8")
    except Exception as e:
        logger.error(f"Error saving {WATCHLIST_FILE}: {e}")


def get_watchlist() -> list[dict]:
    """Return the active list of tracked stocks."""
    return _load_watchlist()


def add_to_watchlist(raw_input: str) -> tuple[int, list[str], str]:
    """
    Add one or multiple stocks to the watchlist.
    Accepts comma-separated values (e.g. 'Reliance, Infosys, Tata Motors').
    Resolves typos via fuzzy resolver and fetches upcoming earnings dates.
    """
    items = [item.strip() for item in raw_input.replace("and", ",").split(",") if item.strip()]
    if not items:
        return 0, [], "❌ Please provide at least one stock name to add (e.g. `/watchlist add Reliance, INFY`)."

    watchlist = _load_watchlist()
    existing_tickers = {w["ticker"] for w in watchlist}
    added_names = []
    skipped_names = []

    now_ist = datetime.now(ZoneInfo(TIMEZONE)).isoformat()

    for item in items:
        name, ticker = fuzzy_resolve_stock(item)
        if not ticker:
            ticker = f"{item.upper()}.NS"
            name = item.title()

        if ticker in existing_tickers:
            skipped_names.append(name or ticker)
            continue

        # Fetch upcoming earnings date
        earnings_date_str = fetch_upcoming_earnings_date(ticker)

        entry = {
            "company": name,
            "ticker": ticker,
            "added_at": now_ist,
            "next_earnings": earnings_date_str,
            "last_triage_date": None,
        }
        watchlist.append(entry)
        existing_tickers.add(ticker)
        added_names.append(f"**{name}** (`{ticker}`)")

    if added_names:
        _save_watchlist(watchlist)

    msg_lines = []
    if added_names:
        msg_lines.append(f"✅ Added {len(added_names)} stock(s) to your earnings watchlist:\n" + "\n".join([f"• {n}" for n in added_names]))
    if skipped_names:
        msg_lines.append(f"ℹ️ Already in your watchlist: {', '.join(skipped_names)}")

    return len(added_names), added_names, "\n\n".join(msg_lines)


def remove_from_watchlist(query: str) -> tuple[bool, str]:
    """Remove a stock from the watchlist (typo-tolerant)."""
    clean_q = query.strip().lower()
    if not clean_q:
        return False, "Please specify which stock to remove (e.g. `/watchlist remove Reliance`)."

    name, ticker = fuzzy_resolve_stock(clean_q)
    target_ticker = ticker.lower() if ticker else clean_q

    watchlist = _load_watchlist()
    matched = None
    for w in watchlist:
        if (
            w["ticker"].lower() == target_ticker
            or (ticker and w["ticker"].lower() == ticker.lower())
            or clean_q in w["company"].lower()
            or clean_q in w["ticker"].lower()
        ):
            matched = w
            break

    if not matched:
        return False, f"❌ *'{query}'* was not found in your watchlist, sir."

    watchlist = [w for w in watchlist if w["ticker"] != matched["ticker"]]
    _save_watchlist(watchlist)
    return True, f"✅ Removed **{matched['company']}** (`{matched['ticker']}`) from your earnings watchlist."


def fetch_upcoming_earnings_date(ticker: str) -> Optional[str]:
    """Retrieve the next scheduled earnings date from yfinance."""
    try:
        import yfinance as yf
        t = yf.Ticker(ticker)
        cal = t.calendar
        if isinstance(cal, dict):
            ed = cal.get("Earnings Date")
            if ed:
                if hasattr(ed, "__iter__") and not isinstance(ed, (str, bytes)):
                    first_val = list(ed)[0]
                    return str(first_val)
                return str(ed)
        # Check earnings_dates dataframe
        ed_df = t.earnings_dates
        if ed_df is not None and not ed_df.empty:
            now_ts = datetime.now()
            # find first date in future
            for dt_idx in ed_df.index:
                dt_naive = dt_idx.replace(tzinfo=None) if hasattr(dt_idx, "replace") else dt_idx
                if dt_naive >= now_ts:
                    return dt_naive.strftime("%Y-%m-%d")
    except Exception as e:
        logger.debug(f"Could not retrieve earnings date for {ticker}: {e}")
    return None


# ============================================================================
# 2. Watchlist Display & Formatting
# ============================================================================

def format_watchlist_card() -> str:
    """Format the active earnings watchlist with live prices and earnings countdowns."""
    watchlist = _load_watchlist()
    if not watchlist:
        return (
            "📋 **Earnings Watchlist**\n\n"
            "Your watchlist is currently empty, sir.\n\n"
            "_Add stocks to start autonomous earnings tracking:_\n"
            "• `/watchlist add Reliance, Infosys, Tata Motors`\n"
            "• Or say: *'Add HDFC Bank to my watchlist'*"
        )

    lines = [f"📋 **Earnings Watchlist ({len(watchlist)} Stocks Tracked)**\n"]
    today_dt = datetime.now(ZoneInfo(TIMEZONE)).date()

    for w in watchlist:
        ticker = w["ticker"]
        price_info = _fetch_price(ticker)
        cmp_str = f"`₹{price_info['price']:,.2f}` ({price_info['change_pct']:+.2f}%)" if price_info else "N/A"

        ed_str = w.get("next_earnings") or fetch_upcoming_earnings_date(ticker)
        countdown_str = "Date unannounced"
        if ed_str:
            try:
                ed_date = datetime.strptime(ed_str[:10], "%Y-%m-%d").date()
                days_left = (ed_date - today_dt).days
                if days_left == 0:
                    countdown_str = "🚨 **REPORTS TODAY!**"
                elif days_left == 1:
                    countdown_str = "⚠️ **Reports Tomorrow!**"
                elif days_left > 1:
                    countdown_str = f"in {days_left} days (`{ed_str[:10]}`)"
                else:
                    countdown_str = f"Reported on `{ed_str[:10]}`"
            except Exception:
                countdown_str = f"`{ed_str[:10]}`"

        lines.append(f"📌 **{w['company']}** (`{ticker}`)")
        lines.append(f"   💰 CMP: {cmp_str}")
        lines.append(f"   📅 Next Results: {countdown_str}")
        lines.append("")

    lines.append("💡 _Use `/earnings <stock>` for an on-demand financial results breakdown._")
    lines.append("💡 _Use `/watchlist add <stock>` or `/watchlist remove <stock>` to modify._")
    return "\n".join(lines)


# ============================================================================
# 3. Autonomous Earnings Triage Engine
# ============================================================================

def triage_stock_earnings(ticker: str, company_name: str = "") -> str:
    """
    Perform an executive triage on the latest quarterly financial results.
    Pulls YoY / QoQ growth, surprise % vs estimates, compares with user's investment thesis,
    and returns a structured Telegram markdown card.
    """
    try:
        import yfinance as yf
        t = yf.Ticker(ticker)
    except Exception as e:
        return f"❌ Could not initialize financial engine for `{ticker}`: {e}"

    resolved_name = company_name or getattr(t.info, "get", lambda k: None)("longName") or ticker

    # 1. Fetch latest reported quarterly financials
    revenue_metrics = "N/A"
    ebitda_metrics = "N/A"
    pat_metrics = "N/A"
    surprise_info = ""

    try:
        qi = t.quarterly_income_stmt
        if qi is not None and not qi.empty and len(qi.columns) >= 2:
            cols = list(qi.columns)
            curr_q = cols[0]
            prev_q = cols[1]
            q_name = curr_q.strftime("%b %Y") if hasattr(curr_q, "strftime") else str(curr_q)[:10]

            def _fmt_curr(val):
                if val is None or val == 0:
                    return "N/A"
                if abs(val) >= 1e12:
                    return f"₹{val/1e12:.2f}T"
                if abs(val) >= 1e9:
                    return f"₹{val/1e9:.2f}B"
                if abs(val) >= 1e7:
                    return f"₹{val/1e7:.2f}Cr"
                return f"₹{val:,.0f}"

            # Revenue
            if "Total Revenue" in qi.index:
                rev_curr = qi.loc["Total Revenue"].iloc[0]
                rev_prev = qi.loc["Total Revenue"].iloc[1]
                qoq_growth = ((rev_curr - rev_prev) / rev_prev) * 100 if rev_prev else 0
                revenue_metrics = f"{_fmt_curr(rev_curr)} ({qoq_growth:+.2f}% QoQ)"

            # Operating / EBITDA Income
            if "Operating Income" in qi.index:
                op_curr = qi.loc["Operating Income"].iloc[0]
                op_prev = qi.loc["Operating Income"].iloc[1]
                op_growth = ((op_curr - op_prev) / op_prev) * 100 if op_prev else 0
                margin_curr = (op_curr / rev_curr) * 100 if "Total Revenue" in qi.index and rev_curr else 0
                ebitda_metrics = f"{_fmt_curr(op_curr)} (Margin: {margin_curr:.1f}%, {op_growth:+.2f}% QoQ)"

            # Net Income (PAT)
            if "Net Income" in qi.index:
                pat_curr = qi.loc["Net Income"].iloc[0]
                pat_prev = qi.loc["Net Income"].iloc[1]
                pat_growth = ((pat_curr - pat_prev) / pat_prev) * 100 if pat_prev else 0
                pat_metrics = f"{_fmt_curr(pat_curr)} ({pat_growth:+.2f}% QoQ)"
    except Exception as e:
        logger.debug(f"Quarterly income statement parse error: {e}")

    # 2. Check earnings surprise %
    try:
        ed_df = t.earnings_dates
        if ed_df is not None and not ed_df.empty:
            for dt_idx, row in ed_df.iterrows():
                rep = row.get("Reported EPS")
                est = row.get("EPS Estimate")
                surp = row.get("Surprise(%)")
                if rep is not None and not str(rep).lower() == "nan":
                    surp_val = float(surp) if surp is not None and not str(surp).lower() == "nan" else 0.0
                    verdict = "🟢 BEAT" if surp_val > 0 else ("🔴 MISS" if surp_val < 0 else "⚪ IN-LINE")
                    surprise_info = f"• **EPS Consensus:** Reported `{rep:.2f}` vs Est `{est:.2f}` &rarr; **{verdict} ({surp_val:+.2f}%)**"
                    break
    except Exception as e:
        logger.debug(f"Earnings surprise check error: {e}")

    # 3. Cross-reference with User's Investment Thesis in data/thesis.json
    thesis_cross_check = ""
    try:
        from utils.thesis import _load_theses
        theses = _load_theses()
        matching_theses = [th for th in theses if th.get("status") == "OPEN" and th.get("ticker") == ticker]
        if matching_theses:
            th = matching_theses[0]
            thesis_cross_check = (
                f"\n🎯 **Impact on Your Active Thesis (`{th['id']}`):**\n"
                f"• Entry: `₹{th['entry_price']}` | Target: `₹{th['target_price']}` | SL: `₹{th.get('stoploss', 'N/A')}`\n"
                f"• Original Rationale: _{th.get('rationale', 'Long position')}_\n"
            )
    except Exception as e:
        logger.debug(f"Thesis cross check error: {e}")

    # 4. Formulate Executive Triage Card
    now_str = datetime.now(ZoneInfo(TIMEZONE)).strftime("%d %b %Y, %I:%M %p")
    lines = [
        f"⚡ **Autonomous Earnings Triage: {resolved_name}** (`{ticker}`)",
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        f"• **Revenue:** `{revenue_metrics}`",
        f"• **Operating Income / EBITDA:** `{ebitda_metrics}`",
        f"• **Net Profit (PAT):** `{pat_metrics}`",
    ]
    if surprise_info:
        lines.append(surprise_info)

    if thesis_cross_check:
        lines.append(thesis_cross_check)

    # Next earnings schedule
    next_ed = fetch_upcoming_earnings_date(ticker)
    if next_ed:
        lines.append(f"📅 **Next Results Date:** `{next_ed}`")

    lines.append(f"\n_Data via Yahoo Finance · Evaluated: {now_str}_")
    return "\n".join(lines)


# ============================================================================
# 4. Scheduled Background Triage Scanner
# ============================================================================

def check_watchlist_earnings_updates() -> list[str]:
    """
    Called by APScheduler during post-market hours (e.g. 17:30 IST).
    Checks if any watchlist company:
    1. Reports results TOMORROW &rarr; Early heads-up notification.
    2. Reported results TODAY &rarr; Generates and sends full autonomous triage card.
    """
    watchlist = _load_watchlist()
    if not watchlist:
        return []

    notifications: list[str] = []
    today = datetime.now(ZoneInfo(TIMEZONE)).date()
    modified = False

    for w in watchlist:
        ticker = w["ticker"]
        ed_str = w.get("next_earnings") or fetch_upcoming_earnings_date(ticker)
        if not ed_str:
            continue

        try:
            ed_date = datetime.strptime(ed_str[:10], "%Y-%m-%d").date()
            days_diff = (ed_date - today).days

            # T-1 Day Heads-up
            if days_diff == 1 and w.get("last_heads_up") != str(today):
                w["last_heads_up"] = str(today)
                modified = True
                price_info = _fetch_price(ticker)
                cmp_str = f" (CMP: `₹{price_info['price']}`)" if price_info else ""
                notifications.append(
                    f"⚠️ **Earnings Tomorrow Alert**\n\n"
                    f"📌 **{w['company']}** (`{ticker}`){cmp_str}\n"
                    f"📅 Scheduled to report quarterly financial results **tomorrow** (`{ed_str[:10]}`).\n\n"
                    f"I will monitor the declarations and send an autonomous triage as soon as results drop, sir."
                )

            # Results Day Triage
            elif days_diff == 0 and w.get("last_triage_date") != str(today):
                w["last_triage_date"] = str(today)
                modified = True
                triage_card = triage_stock_earnings(ticker, w["company"])
                notifications.append(
                    f"🚨 **LIVE EARNINGS DECLARATION**\n\n{triage_card}"
                )

        except Exception as e:
            logger.debug(f"Error checking earnings update for {ticker}: {e}")

    if modified:
        _save_watchlist(watchlist)

    return notifications
