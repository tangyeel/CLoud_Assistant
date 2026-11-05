"""
utils/deep_research.py — Autonomous Institutional Deep Research Engine.
Generates comprehensive equity dossiers featuring:
1. LTP & 52-Week High/Low range position & dynamics
2. Last reported quarterly earnings triage (Revenue, Operating Margin, PAT, QoQ growth)
3. Next earnings announcement date & days countdown
4. Forward future outlook, business catalysts, and sector momentum
5. Risk matrix & personalized strategic investment verdict
"""
from __future__ import annotations
import re
from datetime import datetime
from zoneinfo import ZoneInfo
from typing import Optional

from config import TIMEZONE
from utils.logger import logger
from utils.finance import fuzzy_resolve_stock, _fetch_price
from utils.earnings import fetch_upcoming_earnings_date
from utils.search import search_web
from utils.memory import recall_relevant_memories, format_memories_for_prompt
from ai.gemini_client import generate_text
from ai.prompts import DEEP_RESEARCH_SYSTEM, DEEP_RESEARCH_PROMPT


def _fmt_inr(val: Optional[float]) -> str:
    """Format large numbers into Cr / B / T with INR symbol."""
    if val is None or val == 0:
        return "N/A"
    abs_v = abs(val)
    if abs_v >= 1e12:
        return f"₹{val/1e12:.2f}T"
    if abs_v >= 1e9:
        return f"₹{val/1e9:.2f}B"
    if abs_v >= 1e7:
        return f"₹{val/1e7:.2f}Cr"
    return f"₹{val:,.2f}"


def execute_deep_research(query: str) -> str:
    """
    Execute end-to-end deep research for a given stock query or ticker.
    Gathers real-time price, 52W range, latest quarterly financials, next earnings date,
    web research catalysts, and synthesizes an executive research dossier.
    """
    clean_q = query.strip()
    for prefix in [
        "deep research on ",
        "deep research for ",
        "deep research ",
        "deep dive on ",
        "deep dive into ",
        "deep dive for ",
        "deep dive ",
        "future outlook for ",
        "future outlook of ",
        "future outlook on ",
        "future outlook ",
        "research on ",
        "research for ",
        "research ",
    ]:
        if clean_q.lower().startswith(prefix):
            clean_q = clean_q[len(prefix):].strip()
            break

    name, ticker = fuzzy_resolve_stock(clean_q)
    if not ticker:
        # Fallback to uppercase symbol
        sym = clean_q.upper().replace(" ", "")
        ticker = f"{sym}.NS" if not sym.endswith((".NS", ".BO")) and len(sym) <= 12 else sym
        name = clean_q.title()

    logger.info(f"🔬 Starting deep research on '{name}' ({ticker})...")

    # 1. Fetch live market & valuation data via yfinance
    info: dict = {}
    last_price = None
    day_change_pct = 0.0
    day_change_inr = 0.0
    year_high = None
    year_low = None
    mkt_cap = None
    pe = None
    pb = None
    ticker_obj = None

    try:
        import yfinance as yf
        ticker_obj = yf.Ticker(ticker)
        fast = getattr(ticker_obj, "fast_info", None)
        if fast is not None:
            last_price = getattr(fast, "last_price", None)
            year_high = getattr(fast, "year_high", None)
            year_low = getattr(fast, "year_low", None)
            mkt_cap = getattr(fast, "market_cap", None)

        info = ticker_obj.info or {}
        if last_price is None:
            last_price = info.get("currentPrice") or info.get("regularMarketPrice")
        if year_high is None:
            year_high = info.get("fiftyTwoWeekHigh")
        if year_low is None:
            year_low = info.get("fiftyTwoWeekLow")
        if mkt_cap is None:
            mkt_cap = info.get("marketCap")

        pe = info.get("trailingPE") or info.get("forwardPE")
        pb = info.get("priceToBook")
        resolved_name = info.get("longName") or info.get("shortName") or name
        if resolved_name:
            name = resolved_name
    except Exception as e:
        logger.warning(f"yfinance fetch error for {ticker}: {e}")

    # Fallback to Bhavcopy / price fetcher if needed
    if last_price is None or year_high is None or year_low is None:
        pdata = _fetch_price(ticker)
        if pdata:
            last_price = last_price or pdata.get("price")
            day_change_pct = pdata.get("change_pct", 0.0)
            day_change_inr = pdata.get("change", 0.0)

    if last_price is None:
        return f"❌ Could not retrieve market data for *'{clean_q}'* (`{ticker}`). Please verify the stock ticker or company name."

    # Compute 52W High/Low distance & range percentage
    dist_high_str = "N/A"
    dist_low_str = "N/A"
    range_bar = "[──────────]"
    range_pct_str = "N/A"

    if year_high and year_high > 0:
        dh = ((last_price - year_high) / year_high) * 100
        dist_high_str = f"{dh:+.2f}% from 52W High"
    if year_low and year_low > 0:
        dl = ((last_price - year_low) / year_low) * 100
        dist_low_str = f"{dl:+.2f}% from 52W Low"

    if year_high and year_low and year_high > year_low:
        range_pct = ((last_price - year_low) / (year_high - year_low)) * 100
        range_pct = max(0.0, min(100.0, range_pct))
        filled = int(round(range_pct / 10))
        range_bar = f"[{'█' * filled}{'░' * (10 - filled)}]"
        range_pct_str = f"{range_pct:.1f}% percentile"

    # Format price strings
    chg_icon = "🟢" if day_change_pct >= 0 else "🔴"
    price_str = f"₹{last_price:,.2f} ({chg_icon} {day_change_pct:+.2f}%)"
    high_52_str = f"₹{year_high:,.2f}" if year_high else "N/A"
    low_52_str = f"₹{year_low:,.2f}" if year_low else "N/A"
    mkt_cap_str = _fmt_inr(mkt_cap)
    pe_str = f"{pe:.2f}x" if pe else "N/A"
    pb_str = f"{pb:.2f}x" if pb else "N/A"

    # 2. Extract Last Reported Quarterly Financials
    last_quarter_name = "Latest Quarter"
    revenue_str = "N/A"
    rev_growth_str = "YoY"
    ebitda_str = "N/A"
    ebitda_margin_str = "N/A"
    pat_str = "N/A"
    pat_growth_str = "YoY"
    earnings_summary = "Healthy quarterly operational execution."

    try:
        if ticker_obj is not None:
            qi = ticker_obj.quarterly_income_stmt
            if qi is not None and not qi.empty and len(qi.columns) >= 1:
                cols = list(qi.columns)
                curr_col = cols[0]
                if hasattr(curr_col, "strftime"):
                    last_quarter_name = curr_col.strftime("%b %Y")
                else:
                    last_quarter_name = str(curr_col)[:10]

                # Find revenue
                for r_key in ["Total Revenue", "Operating Revenue", "Revenue"]:
                    if r_key in qi.index:
                        c_rev = float(qi.loc[r_key].values[0])
                        revenue_str = _fmt_inr(c_rev)
                        if len(cols) >= 2:
                            p_rev = float(qi.loc[r_key].values[1])
                            if p_rev > 0:
                                g = ((c_rev - p_rev) / p_rev) * 100
                                rev_growth_str = f"{g:+.2f}% QoQ"
                        break

                # Find EBITDA / Operating Income
                for o_key in ["Operating Income", "EBITDA", "EBIT"]:
                    if o_key in qi.index:
                        c_op = float(qi.loc[o_key].values[0])
                        ebitda_str = _fmt_inr(c_op)
                        # calculate margin if revenue exists
                        if "c_rev" in locals() and c_rev > 0:
                            ebitda_margin_str = f"{(c_op / c_rev) * 100:.1f}%"
                        break

                # Find Net Profit (PAT)
                for p_key in ["Net Income Common Stockholders", "Net Income", "Normalized Income"]:
                    if p_key in qi.index:
                        c_pat = float(qi.loc[p_key].values[0])
                        pat_str = _fmt_inr(c_pat)
                        if len(cols) >= 2:
                            p_pat = float(qi.loc[p_key].values[1])
                            if p_pat != 0:
                                pg = ((c_pat - p_pat) / abs(p_pat)) * 100
                                pat_growth_str = f"{pg:+.2f}% QoQ"
                        break
    except Exception as q_err:
        logger.debug(f"Quarterly financials parse error: {q_err}")

    # Fallback to annual figures if quarterly was unpopulated
    if revenue_str == "N/A" and info.get("totalRevenue"):
        revenue_str = _fmt_inr(info.get("totalRevenue"))
        rev_growth_str = "TTM"
    if pat_str == "N/A" and info.get("netIncomeToCommon"):
        pat_str = _fmt_inr(info.get("netIncomeToCommon"))
        pat_growth_str = "TTM"
    if ebitda_margin_str == "N/A" and info.get("operatingMargins"):
        ebitda_margin_str = f"{info['operatingMargins']*100:.1f}%"

    # 3. Next Earnings Announcement Date & Countdown
    next_ed_raw = fetch_upcoming_earnings_date(ticker)
    next_earnings_date = next_ed_raw or "To be announced"
    countdown_str = "Tentative declaration window"
    today_dt = datetime.now(ZoneInfo(TIMEZONE)).date()

    if next_ed_raw:
        try:
            ed_dt = datetime.strptime(next_ed_raw[:10], "%Y-%m-%d").date()
            diff_days = (ed_dt - today_dt).days
            if diff_days == 0:
                countdown_str = "🚨 REPORTS TODAY!"
            elif diff_days == 1:
                countdown_str = "⚠️ Reports Tomorrow!"
            elif diff_days > 1:
                countdown_str = f"in {diff_days} days"
            else:
                countdown_str = f"Reported on {next_ed_raw[:10]} (Next cycle pending)"
        except Exception:
            pass

    # 4. Gather Fresh Web Research & Future Catalysts
    web_catalysts = "Leading domestic industry participant with active market footprint."
    try:
        search_query = f"{name} {ticker} growth future outlook catalysts order book target 2026"
        results = search_web(search_query, max_results=3)
        if results:
            snippets = []
            for r in results:
                title = r.get("title", "")
                snippet = r.get("snippet", "")
                url = r.get("url", "")
                clean_title = re.sub(r'[*_`\[\]()]', '', title).strip()
                clean_snip = re.sub(r'[*_`\[\]()]', '', snippet).strip()
                if clean_snip:
                    snippets.append(f"• **{clean_title}**: {clean_snip[:220]} (Source: {url})")
            if snippets:
                web_catalysts = "\n".join(snippets)
    except Exception as search_err:
        logger.debug(f"Web catalyst search failed: {search_err}")

    # 5. Cognitive Memory Injection (User Preferences)
    user_mems = recall_relevant_memories(f"{ticker} {name} risk appetite horizon portfolio", top_k=2)
    mem_block = format_memories_for_prompt(user_mems)
    sys_instruction = DEEP_RESEARCH_SYSTEM
    if mem_block:
        sys_instruction = f"{DEEP_RESEARCH_SYSTEM}\n\n{mem_block}\nIncorporate sir's recalled risk profile and investment guidelines into the strategic verdict."

    # 6. Synthesize Full Report via LLM Cascade
    prompt = DEEP_RESEARCH_PROMPT.format(
        company_name=name,
        ticker=ticker,
        price_str=price_str,
        high_52_str=high_52_str,
        dist_high_str=dist_high_str,
        low_52_str=low_52_str,
        dist_low_str=dist_low_str,
        range_bar=range_bar,
        range_pct_str=range_pct_str,
        mkt_cap_str=mkt_cap_str,
        pe_str=pe_str,
        pb_str=pb_str,
        last_quarter_name=last_quarter_name,
        revenue_str=revenue_str,
        rev_growth_str=rev_growth_str,
        ebitda_str=ebitda_str,
        ebitda_margin_str=ebitda_margin_str,
        pat_str=pat_str,
        pat_growth_str=pat_growth_str,
        earnings_summary=earnings_summary,
        next_earnings_date=next_earnings_date,
        countdown_str=countdown_str,
        web_catalysts=web_catalysts,
    )

    try:
        report = generate_text(prompt, system_instruction=sys_instruction)
        header = (
            f"🏛️ **Institutional Deep Research Dossier: {name} (`{ticker}`)**\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"💰 **LTP:** `{price_str}` | **52W Range:** `{low_52_str}` ↔ `{high_52_str}`\n"
            f"🎯 **52W Position:** `{range_bar}` ({dist_high_str})\n"
            f"📅 **Next Results:** `{next_earnings_date}` ({countdown_str})\n\n"
        )
        return header + report
    except Exception as llm_err:
        logger.error(f"Deep research LLM failure: {llm_err}")
        # Deterministic Fallback Card
        return (
            f"🏛️ **Deep Research Dossier: {name} (`{ticker}`)**\n\n"
            f"📈 **Price Dynamics:**\n"
            f"• Current LTP: `{price_str}`\n"
            f"• 52-Week High: `{high_52_str}` ({dist_high_str})\n"
            f"• 52-Week Low: `{low_52_str}` ({dist_low_str})\n"
            f"• 52W Percentile: `{range_bar}` ({range_pct_str})\n\n"
            f"📊 **Latest Financial Results ({last_quarter_name}):**\n"
            f"• Revenue: `{revenue_str}` ({rev_growth_str})\n"
            f"• EBITDA: `{ebitda_str}` (Margin: `{ebitda_margin_str}`)\n"
            f"• Net Profit: `{pat_str}` ({pat_growth_str})\n\n"
            f"📅 **Next Earnings Catalyst:**\n"
            f"• Scheduled: `{next_earnings_date}` ({countdown_str})\n\n"
            f"🚀 **Market Catalysts:**\n"
            f"{web_catalysts[:400]}"
        )
