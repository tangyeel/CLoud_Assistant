"""
utils/finance.py — Market data, stock lookup, fuzzy name resolution, and pre-market radar.
All data fetched from free sources (yfinance, ddgs). No paid API keys required.
"""
from __future__ import annotations
import json
import time
import difflib
import re
from pathlib import Path
from typing import Optional

from utils.logger import logger

# ---------------------------------------------------------------------------
# Ticker maps
# ---------------------------------------------------------------------------

# Indian index tickers
INDIAN_INDICES: dict[str, str] = {
    "Nifty 50":        "^NSEI",
    "Sensex":          "^BSESN",
    "India VIX":       "^INDIAVIX",
    "Bank Nifty":      "^NSEBANK",
    "Nifty Midcap 150":"NIFTYMIDCAP150.NS",
    "Nifty Smallcap 250": "NIFTYSMLCAP250.NS",
}

GLOBAL_INDICES: dict[str, str] = {
    "S&P 500":   "^GSPC",
    "NASDAQ":    "^IXIC",
    "Dow Jones": "^DJI",
    "FTSE 100":  "^FTSE",
    "Nikkei 225":"^N225",
    "Hang Seng": "^HSI",
}

COMMODITIES: dict[str, str] = {
    "Gold":      "GC=F",
    "Crude WTI": "CL=F",
    "Brent":     "BZ=F",
    "USD/INR":   "USDINR=X",
}

# ---------------------------------------------------------------------------
# Simple cache helpers
# ---------------------------------------------------------------------------

_CACHE: dict[str, tuple[float, object]] = {}
_CACHE_TTL = 300  # 5 minutes for market data


def _cache_get(key: str) -> Optional[object]:
    entry = _CACHE.get(key)
    if entry and (time.time() - entry[0]) < _CACHE_TTL:
        return entry[1]
    return None


def _cache_set(key: str, value: object) -> None:
    _CACHE[key] = (time.time(), value)


# ---------------------------------------------------------------------------
# yfinance helper
# ---------------------------------------------------------------------------

def _yf_ticker(symbol: str) -> Optional[object]:
    """Return a yfinance Ticker; None on import failure."""
    try:
        import yfinance as yf  # type: ignore
        return yf.Ticker(symbol)
    except ImportError:
        logger.warning("yfinance is not installed — finance features unavailable.")
        return None


def _fetch_price(symbol: str) -> Optional[dict]:
    """Return {price, prev_close, change, change_pct} for a ticker symbol."""
    cached = _cache_get(f"price:{symbol}")
    if cached is not None:
        return cached  # type: ignore

    try:
        import yfinance as yf  # type: ignore
        t = yf.Ticker(symbol)
        # fast_info is lighter than .info
        fi = t.fast_info
        price = getattr(fi, "last_price", None)
        prev  = getattr(fi, "previous_close", None) or getattr(fi, "regular_market_previous_close", None)
        if price is None:
            hist = t.history(period="2d", interval="1d")
            if len(hist) >= 1:
                price = float(hist["Close"].iloc[-1])
            if len(hist) >= 2:
                prev = float(hist["Close"].iloc[-2])

        if price is None:
            return None

        change = round(price - prev, 2) if prev else 0.0
        change_pct = round((change / prev) * 100, 2) if prev else 0.0
        result = {
            "price": round(price, 2),
            "prev_close": round(prev, 2) if prev else None,
            "change": change,
            "change_pct": change_pct,
        }
        _cache_set(f"price:{symbol}", result)
        return result
    except Exception as e:
        logger.debug(f"_fetch_price({symbol}): {e}")
        return None


def _arrow(change: float) -> str:
    return "🟢 ▲" if change >= 0 else "🔴 ▼"


def _fmt_num(val: float, decimals: int = 2) -> str:
    if val >= 1_000:
        return f"{val:,.{decimals}f}"
    return f"{val:.{decimals}f}"


# ---------------------------------------------------------------------------
# /market — Snapshot
# ---------------------------------------------------------------------------

def get_market_snapshot() -> str:
    """Build and return a formatted Telegram Markdown market snapshot card."""
    lines: list[str] = ["📊 *Market Snapshot*\n"]

    # Indian Indices
    lines.append("🇮🇳 *Indian Indices*")
    for name, sym in INDIAN_INDICES.items():
        d = _fetch_price(sym)
        if d:
            arrow = _arrow(d["change"])
            lines.append(
                f"  {arrow} *{name}*: `{_fmt_num(d['price'])}` "
                f"({d['change']:+.2f} / {d['change_pct']:+.2f}%)"
            )
        else:
            lines.append(f"  ⚪ *{name}*: N/A")

    lines.append("")

    # Global Indices
    lines.append("🌍 *Global Indices*")
    for name, sym in GLOBAL_INDICES.items():
        d = _fetch_price(sym)
        if d:
            arrow = _arrow(d["change"])
            lines.append(
                f"  {arrow} *{name}*: `{_fmt_num(d['price'])}` "
                f"({d['change_pct']:+.2f}%)"
            )
        else:
            lines.append(f"  ⚪ *{name}*: N/A")

    lines.append("")

    # Commodities & FX
    lines.append("🛢️ *Commodities & FX*")
    for name, sym in COMMODITIES.items():
        d = _fetch_price(sym)
        if d:
            arrow = _arrow(d["change"])
            unit = "₹" if sym == "USDINR=X" else "$" if name != "USD/INR" else ""
            lines.append(
                f"  {arrow} *{name}*: `{unit}{_fmt_num(d['price'])}` "
                f"({d['change_pct']:+.2f}%)"
            )
        else:
            lines.append(f"  ⚪ *{name}*: N/A")

    lines.append(f"\n_Updated: {_now_ist()}_")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Stock Fuzzy Resolver
# ---------------------------------------------------------------------------

_NSE_SYMBOLS: dict[str, str] | None = None   # {company_name_lower: ticker}
_SYMBOLS_PATH = Path(__file__).parent.parent / "data" / "nse_symbols.json"


def _load_nse_symbols() -> dict[str, str]:
    global _NSE_SYMBOLS
    if _NSE_SYMBOLS is not None:
        return _NSE_SYMBOLS

    if _SYMBOLS_PATH.exists():
        try:
            raw: dict = json.loads(_SYMBOLS_PATH.read_text(encoding="utf-8"))
            _NSE_SYMBOLS = {k.lower(): v for k, v in raw.items()}
            logger.info(f"Loaded {len(_NSE_SYMBOLS)} NSE symbols from disk.")
            return _NSE_SYMBOLS
        except Exception as e:
            logger.warning(f"Could not load nse_symbols.json: {e}")

    # Fallback: minimal inline map for top 50 stocks
    _NSE_SYMBOLS = _BUILTIN_NSE_MAP()
    return _NSE_SYMBOLS


def _BUILTIN_NSE_MAP() -> dict[str, str]:
    """Minimal built-in name→ticker map covering the most popular Indian stocks."""
    return {
        "reliance": "RELIANCE.NS",
        "reliance industries": "RELIANCE.NS",
        "tcs": "TCS.NS",
        "tata consultancy services": "TCS.NS",
        "infosys": "INFY.NS",
        "infy": "INFY.NS",
        "hdfc bank": "HDFCBANK.NS",
        "hdfc": "HDFCBANK.NS",
        "icici bank": "ICICIBANK.NS",
        "icici": "ICICIBANK.NS",
        "wipro": "WIPRO.NS",
        "hcl tech": "HCLTECH.NS",
        "hcl technologies": "HCLTECH.NS",
        "kotak mahindra bank": "KOTAKBANK.NS",
        "kotak bank": "KOTAKBANK.NS",
        "kotak": "KOTAKBANK.NS",
        "axis bank": "AXISBANK.NS",
        "l&t": "LT.NS",
        "larsen": "LT.NS",
        "larsen and toubro": "LT.NS",
        "bajaj finance": "BAJFINANCE.NS",
        "bajaj finserv": "BAJAJFINSV.NS",
        "maruti": "MARUTI.NS",
        "maruti suzuki": "MARUTI.NS",
        "sun pharma": "SUNPHARMA.NS",
        "sun pharmaceutical": "SUNPHARMA.NS",
        "titan": "TITAN.NS",
        "asian paints": "ASIANPAINT.NS",
        "itc": "ITC.NS",
        "hindustan unilever": "HINDUNILVR.NS",
        "hul": "HINDUNILVR.NS",
        "power grid": "POWERGRID.NS",
        "ntpc": "NTPC.NS",
        "ongc": "ONGC.NS",
        "coal india": "COALINDIA.NS",
        "adani enterprises": "ADANIENT.NS",
        "adani ports": "ADANIPORTS.NS",
        "adani green": "ADANIGREEN.NS",
        "adani power": "ADANIPOWER.NS",
        "adani total gas": "ATGL.NS",
        "sbi": "SBIN.NS",
        "state bank": "SBIN.NS",
        "state bank of india": "SBIN.NS",
        "britannia": "BRITANNIA.NS",
        "nestle": "NESTLEIND.NS",
        "nestle india": "NESTLEIND.NS",
        "hero motocorp": "HEROMOTOCO.NS",
        "hero": "HEROMOTOCO.NS",
        "bajaj auto": "BAJAJ-AUTO.NS",
        "tata motors": "TATAMOTORS.NS",
        "tata steel": "TATASTEEL.NS",
        "jsw steel": "JSWSTEEL.NS",
        "hindalco": "HINDALCO.NS",
        "upl": "UPL.NS",
        "cipla": "CIPLA.NS",
        "dr reddy": "DRREDDY.NS",
        "dr reddys": "DRREDDY.NS",
        "divis lab": "DIVISLAB.NS",
        "bpcl": "BPCL.NS",
        "bharat petroleum": "BPCL.NS",
        "tech mahindra": "TECHM.NS",
        "tech m": "TECHM.NS",
        "ultratech cement": "ULTRACEMCO.NS",
        "ultratech": "ULTRACEMCO.NS",
        "grasim": "GRASIM.NS",
        "vedanta": "VEDL.NS",
        "indusind bank": "INDUSINDBK.NS",
        "indusind": "INDUSINDBK.NS",
        "eicher motors": "EICHERMOT.NS",
        "royal enfield": "EICHERMOT.NS",
        "motherson sumi": "MOTHERSUMI.NS",
        "havells": "HAVELLS.NS",
        "dmart": "DMART.NS",
        "avenue supermarts": "DMART.NS",
        "mrf": "MRF.NS",
        "page industries": "PAGEIND.NS",
        "nifty": "^NSEI",
        "sensex": "^BSESN",
        "bank nifty": "^NSEBANK",
        "banknifty": "^NSEBANK",
        "vix": "^INDIAVIX",
        "india vix": "^INDIAVIX",
    }


def fuzzy_resolve_stock(query: str) -> tuple[Optional[str], Optional[str]]:
    """
    Fuzzy-match a user query to a stock ticker.
    Returns (company_name, ticker) or (None, None) if no match.
    """
    q = query.strip().lower()
    sym_map = _load_nse_symbols()

    # 1. Exact match
    if q in sym_map:
        return q.title(), sym_map[q]

    # 2. Try rapidfuzz for best fuzzy match
    try:
        from rapidfuzz import process, fuzz  # type: ignore
        match = process.extractOne(
            q, list(sym_map.keys()), scorer=fuzz.WRatio, score_cutoff=65
        )
        if match:
            matched_name, score, _ = match
            logger.info(f"Fuzzy resolved '{query}' → '{matched_name}' (score={score})")
            return matched_name.title(), sym_map[matched_name]
    except ImportError:
        pass

    # 3. Fallback: difflib
    close = difflib.get_close_matches(q, list(sym_map.keys()), n=1, cutoff=0.6)
    if close:
        matched = close[0]
        return matched.title(), sym_map[matched]

    # 4. Substring match
    for name, ticker in sym_map.items():
        if q in name or name in q:
            return name.title(), ticker

    return None, None


# ---------------------------------------------------------------------------
# Stock Details
# ---------------------------------------------------------------------------

def get_stock_details(ticker: str, company_name: str = "") -> str:
    """
    Fetch comprehensive stock info and return a formatted Telegram Markdown card.
    """
    try:
        import yfinance as yf  # type: ignore
    except ImportError:
        return "❌ yfinance is not installed. Please add it to requirements.txt."

    try:
        t = yf.Ticker(ticker)
        info = t.info or {}
    except Exception as e:
        return f"❌ Could not fetch data for `{ticker}`: {e}"

    name    = info.get("longName") or info.get("shortName") or company_name or ticker
    price   = info.get("currentPrice") or info.get("regularMarketPrice")
    prev    = info.get("previousClose") or info.get("regularMarketPreviousClose")
    change  = round((price - prev), 2) if price and prev else 0
    chg_pct = round((change / prev) * 100, 2) if prev else 0
    arrow   = _arrow(change)

    high_52 = info.get("fiftyTwoWeekHigh")
    low_52  = info.get("fiftyTwoWeekLow")
    mkt_cap = info.get("marketCap")
    pe      = info.get("trailingPE") or info.get("forwardPE")
    pb      = info.get("priceToBook")
    eps     = info.get("trailingEps")
    div_yld = info.get("dividendYield")
    sector  = info.get("sector")
    volume  = info.get("volume") or info.get("regularMarketVolume")
    avg_vol = info.get("averageVolume")

    def _mktcap(v):
        if v is None:
            return "N/A"
        if v >= 1e12:
            return f"₹{v/1e12:.2f}T"
        if v >= 1e9:
            return f"₹{v/1e9:.2f}B"
        if v >= 1e7:
            return f"₹{v/1e7:.2f}Cr"
        return f"₹{v:,.0f}"

    lines = [
        f"📈 *{name}* (`{ticker}`)",
        f"{arrow} *₹{price:,.2f}*  ({change:+.2f} / {chg_pct:+.2f}%)\n",
        f"📊 *Key Stats*",
        f"  52W High: `{_fmt_num(high_52) if high_52 else 'N/A'}`  |  52W Low: `{_fmt_num(low_52) if low_52 else 'N/A'}`",
        f"  Market Cap: `{_mktcap(mkt_cap)}`" + (f"  |  Sector: `{sector}`" if sector else ""),
        f"  P/E: `{pe:.2f}`" + (f"  |  P/B: `{pb:.2f}`" if pb else "") if pe else "  P/E: `N/A`",
        f"  EPS: `{eps:.2f}`" if eps else "",
        f"  Dividend Yield: `{div_yld * 100:.2f}%`" if div_yld else "",
        f"  Volume: `{volume:,}`  Avg: `{avg_vol:,}`" if volume and avg_vol else "",
    ]

    # Earnings / Results date
    try:
        cal = t.calendar
        if isinstance(cal, dict):
            earnings_dates = cal.get("Earnings Date")
            if earnings_dates:
                if hasattr(earnings_dates, "__iter__") and not isinstance(earnings_dates, str):
                    ed = list(earnings_dates)[0]
                else:
                    ed = earnings_dates
                lines.append(f"\n📅 *Next Results/Earnings*: `{ed}`")
    except Exception:
        pass

    # Recent news (up to 3 headlines)
    try:
        news_items = t.news or []
        if news_items:
            lines.append("\n📰 *Recent News*")
            for item in news_items[:3]:
                headline = item.get("title", "")
                url = item.get("link") or item.get("url") or ""
                pub = item.get("publisher", "")
                if headline:
                    if url:
                        lines.append(f"  • [{headline[:70]}]({url})  _({pub})_")
                    else:
                        lines.append(f"  • {headline[:70]}  _({pub})_")
    except Exception as e:
        logger.debug(f"News fetch error for {ticker}: {e}")
        # Fallback: ddgs news
        try:
            from ddgs import DDGS
            with DDGS() as d:
                results = list(d.news(f"{name} stock NSE BSE", max_results=3))
            if results:
                lines.append("\n📰 *Recent News*")
                for r in results:
                    lines.append(f"  • [{r['title'][:70]}]({r['url']})")
        except Exception:
            pass

    lines.append(f"\n_Data via Yahoo Finance · {_now_ist()}_")
    return "\n".join(l for l in lines if l)


# ---------------------------------------------------------------------------
# AI Financial Analyst helper (builds the prompt context)
# ---------------------------------------------------------------------------

def build_analyst_context(ticker: str) -> dict:
    """
    Collect key financials for use in the analyst system prompt.
    Returns a dict with structured data.
    """
    try:
        import yfinance as yf  # type: ignore
        t = yf.Ticker(ticker)
        info = t.info or {}
    except Exception as e:
        return {"error": str(e)}

    return {
        "name": info.get("longName") or info.get("shortName") or ticker,
        "ticker": ticker,
        "sector": info.get("sector"),
        "industry": info.get("industry"),
        "price": info.get("currentPrice"),
        "52w_high": info.get("fiftyTwoWeekHigh"),
        "52w_low": info.get("fiftyTwoWeekLow"),
        "mkt_cap": info.get("marketCap"),
        "pe": info.get("trailingPE"),
        "forward_pe": info.get("forwardPE"),
        "pb": info.get("priceToBook"),
        "eps": info.get("trailingEps"),
        "roe": info.get("returnOnEquity"),
        "roa": info.get("returnOnAssets"),
        "revenue": info.get("totalRevenue"),
        "net_income": info.get("netIncomeToCommon"),
        "debt_equity": info.get("debtToEquity"),
        "current_ratio": info.get("currentRatio"),
        "fcf": info.get("freeCashflow"),
        "div_yield": info.get("dividendYield"),
        "beta": info.get("beta"),
        "summary": info.get("longBusinessSummary", "")[:600],
    }


# ---------------------------------------------------------------------------
# Pre-Market Radar data
# ---------------------------------------------------------------------------

def get_premarket_data() -> dict:
    """
    Collect pre-market data: Gift Nifty proxy, USD/INR, Crude, Gold + macro news.
    """
    result: dict = {}

    # Nifty futures proxy (use ^NSEI as a reasonable stand-in for Gift Nifty)
    for label, sym in [("Nifty 50", "^NSEI"), ("USD/INR", "USDINR=X"),
                        ("Gold", "GC=F"), ("Crude WTI", "CL=F"), ("Bank Nifty", "^NSEBANK")]:
        d = _fetch_price(sym)
        result[label] = d

    # Macro events via web search
    try:
        from ddgs import DDGS
        with DDGS() as ddgs:
            today_events = list(ddgs.text(
                "India economic calendar events today RBI monetary policy 2026",
                max_results=3
            ))
        result["macro_snippets"] = [r.get("body", r.get("title", ""))[:200] for r in today_events]
    except Exception as e:
        logger.debug(f"Macro news fetch error: {e}")
        result["macro_snippets"] = []

    return result


def format_premarket_card(data: dict) -> str:
    """Format pre-market data as a Telegram Markdown card."""
    lines = [f"🌅 *Pre-Market Radar* — {_now_ist()}\n"]

    index_map = {
        "Nifty 50": ("^NSEI", "🇮🇳"),
        "Bank Nifty": ("^NSEBANK", "🏦"),
        "USD/INR": ("USDINR=X", "💱"),
        "Gold": ("GC=F", "🥇"),
        "Crude WTI": ("CL=F", "🛢️"),
    }
    for label, (sym, emoji) in index_map.items():
        d = data.get(label)
        if d:
            arrow = _arrow(d["change"])
            unit = "₹" if label == "USD/INR" else ("$" if label in ("Gold", "Crude WTI") else "")
            lines.append(
                f"{emoji} {arrow} *{label}*: `{unit}{_fmt_num(d['price'])}` "
                f"({d['change_pct']:+.2f}%)"
            )
        else:
            lines.append(f"  ⚪ *{label}*: N/A")

    snippets = data.get("macro_snippets", [])
    if snippets:
        lines.append("\n📋 *Today's Macro Watch*")
        for s in snippets[:2]:
            lines.append(f"  • _{s[:180]}_")

    lines.append("\n_Markets open at 09:15 IST · Data via Yahoo Finance_")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Utility
# ---------------------------------------------------------------------------

def _now_ist() -> str:
    from datetime import datetime
    from zoneinfo import ZoneInfo
    return datetime.now(ZoneInfo("Asia/Kolkata")).strftime("%d %b %Y, %I:%M %p IST")
