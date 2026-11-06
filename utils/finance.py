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
            # Fallback to official NSE Bhavcopy delivery data
            try:
                from utils.stealth_delivery import get_stock_delivery_data
                bhav = get_stock_delivery_data(symbol)
                if bhav and bhav.get("close"):
                    price = float(bhav["close"])
                    change_pct = float(bhav.get("change_pct", 0.0))
                    prev = round(price / (1.0 + change_pct / 100.0), 2) if change_pct != 0 else price
            except Exception:
                pass

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


def _sync_nse_symbols_from_exchange() -> dict[str, str]:
    """Download full official equity list from NSE (EQUITY_L.csv) and cache to disk."""
    import httpx, csv, io
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
    url = "https://nsearchives.nseindia.com/content/equities/EQUITY_L.csv"
    symbols: dict[str, str] = dict(_BUILTIN_NSE_MAP())
    try:
        r = httpx.get(url, headers=headers, timeout=6.0)
        if r.status_code == 200:
            reader = csv.DictReader(io.StringIO(r.text))
            for row in reader:
                sym = row.get("SYMBOL", "").strip().upper()
                name = row.get("NAME OF COMPANY", "").strip()
                if not sym:
                    continue
                ticker = f"{sym}.NS"
                symbols[sym.lower()] = ticker
                if name:
                    clean_name = name.lower()
                    symbols[clean_name] = ticker
                    for suffix in [" limited", " ltd.", " ltd", " india limited", " (india) limited"]:
                        if clean_name.endswith(suffix):
                            short_name = clean_name[:-len(suffix)].strip()
                            if short_name and short_name not in symbols:
                                symbols[short_name] = ticker

            _SYMBOLS_PATH.parent.mkdir(parents=True, exist_ok=True)
            _SYMBOLS_PATH.write_text(json.dumps(symbols, indent=2, ensure_ascii=False), encoding="utf-8")
            logger.info(f"Synchronized {len(symbols)} NSE symbol mappings to disk.")
            return symbols
    except Exception as e:
        logger.warning(f"Failed to sync NSE symbols from exchange: {e}")
    return symbols


def _load_nse_symbols() -> dict[str, str]:
    global _NSE_SYMBOLS
    if _NSE_SYMBOLS is not None:
        return _NSE_SYMBOLS

    if _SYMBOLS_PATH.exists():
        try:
            raw: dict = json.loads(_SYMBOLS_PATH.read_text(encoding="utf-8"))
            if len(raw) >= 500:
                _NSE_SYMBOLS = {k.lower(): v for k, v in raw.items()}
                logger.info(f"Loaded {len(_NSE_SYMBOLS)} NSE symbols from disk.")
                return _NSE_SYMBOLS
        except Exception as e:
            logger.warning(f"Could not load nse_symbols.json: {e}")

    # Auto-sync full list from exchange or fallback to builtin
    _NSE_SYMBOLS = _sync_nse_symbols_from_exchange()
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
    Prioritizes exact ticker matches before running typo fuzzy matching.
    """
    clean_raw = query.strip()
    q = clean_raw.lower()
    sym_map = _load_nse_symbols()

    # 1. Exact match in sym_map keys
    if q in sym_map:
        return q.title(), sym_map[q]

    # Strip .NS or .BO suffix if provided by user (e.g. "CUMMINSIND.NS" -> "cumminsind")
    bare_q = q.replace(".ns", "").replace(".bo", "").strip()
    if bare_q in sym_map:
        return bare_q.title(), sym_map[bare_q]

    # 2. Check if clean_raw matches any ticker in sym_map values
    upper_q = clean_raw.upper().replace(".NS", "").replace(".BO", "")
    target_ns = f"{upper_q}.NS"
    for name_k, t_val in sym_map.items():
        if t_val.upper() == target_ns:
            return name_k.title(), t_val

    # 3. Direct ticker validation for single-word queries (e.g. unknown new IPOs or global symbols)
    if " " not in clean_raw and len(clean_raw) <= 15:
        try:
            import yfinance as yf
            t_obj = yf.Ticker(target_ns)
            fast_p = getattr(t_obj.fast_info, "last_price", None)
            if fast_p is not None:
                long_n = getattr(t_obj.info, "get", lambda k: None)("longName") or upper_q
                logger.info(f"Direct ticker validated '{target_ns}' -> '{long_n}'")
                sym_map[q] = target_ns
                sym_map[bare_q] = target_ns
                return long_n, target_ns
        except Exception:
            pass

    # 4. RapidFuzz with strict threshold (score_cutoff=82) to avoid false positive cross-company collisions
    try:
        from rapidfuzz import process, fuzz  # type: ignore
        match = process.extractOne(
            q, list(sym_map.keys()), scorer=fuzz.WRatio, score_cutoff=82
        )
        if match:
            matched_name, score, _ = match
            logger.info(f"Fuzzy resolved '{query}' → '{matched_name}' (score={score})")
            return matched_name.title(), sym_map[matched_name]
    except ImportError:
        pass

    # 5. Fallback: difflib with strict cutoff (0.8)
    close = difflib.get_close_matches(q, list(sym_map.keys()), n=1, cutoff=0.8)
    if close:
        matched = close[0]
        return matched.title(), sym_map[matched]

    # 6. Prefix match for longer queries (e.g. "cummins ind" -> "cummins india")
    if len(q) >= 5:
        for name, ticker in sym_map.items():
            if name.startswith(q) or q.startswith(name):
                return name.title(), ticker

    return None, None


# ---------------------------------------------------------------------------
# Stock Details
# ---------------------------------------------------------------------------

def get_stock_details(ticker: str, company_name: str = "") -> str:
    """
    Fetch comprehensive stock info and return a formatted Telegram Markdown card.
    Guaranteed crash-proof with fallback to official NSE Bhavcopy data.
    """
    import re
    try:
        import yfinance as yf  # type: ignore
    except ImportError:
        return "❌ yfinance is not installed. Please add it to requirements.txt."

    info = {}
    t = None
    try:
        t = yf.Ticker(ticker)
        info = t.info or {}
    except Exception as e:
        logger.debug(f"yfinance info fetch exception for {ticker}: {e}")

    # Fallback to fast_info or history if info is empty/throttled
    price = info.get("currentPrice") or info.get("regularMarketPrice")
    prev = info.get("previousClose") or info.get("regularMarketPreviousClose")
    
    if price is None and t is not None:
        try:
            fast_p = getattr(t.fast_info, "last_price", None)
            fast_prev = getattr(t.fast_info, "previous_close", None)
            if fast_p:
                price = float(fast_p)
            if fast_prev:
                prev = float(fast_prev)
        except Exception:
            pass

    # Secondary fallback to official NSE Bhavcopy data
    bhav_data = None
    try:
        from utils.stealth_delivery import get_stock_delivery_data
        bhav_data = get_stock_delivery_data(ticker)
        if bhav_data:
            if price is None and bhav_data.get("close"):
                price = float(bhav_data["close"])
            if not prev and bhav_data.get("change_pct") is not None and price:
                pct = float(bhav_data["change_pct"])
                prev = price / (1.0 + (pct / 100.0))
    except Exception as e:
        logger.debug(f"Bhavcopy fallback error: {e}")

    name = info.get("longName") or info.get("shortName") or company_name or ticker
    name = re.sub(r'[*_`\[\]]', '', str(name)).strip()

    change = round((price - prev), 2) if price is not None and prev is not None else 0.0
    chg_pct = round((change / prev) * 100, 2) if prev else 0.0
    arrow = _arrow(change)

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

    # If volume missing, check bhav_data
    if not volume and bhav_data:
        volume = bhav_data.get("traded_qty")

    def _mktcap(v):
        if v is None:
            return "N/A"
        try:
            fv = float(v)
            if fv >= 1e12:
                return f"₹{fv/1e12:.2f}T"
            if fv >= 1e9:
                return f"₹{fv/1e9:.2f}B"
            if fv >= 1e7:
                return f"₹{fv/1e7:.2f}Cr"
            return f"₹{fv:,.0f}"
        except Exception:
            return "N/A"

    price_header = (
        f"{arrow} *₹{price:,.2f}*  ({change:+.2f} / {chg_pct:+.2f}%)\n"
        if price is not None
        else "📊 *Price tracking pending active trading quote*\n"
    )

    pe_val = float(pe) if pe and isinstance(pe, (int, float)) else None
    pb_val = float(pb) if pb and isinstance(pb, (int, float)) else None
    pe_str = f"  P/E: `{pe_val:.2f}`" if pe_val else "  P/E: `N/A`"
    if pb_val:
        pe_str += f"  |  P/B: `{pb_val:.2f}`"

    eps_val = float(eps) if eps and isinstance(eps, (int, float)) else None
    div_val = float(div_yld) if div_yld and isinstance(div_yld, (int, float)) else None
    vol_val = int(volume) if volume and isinstance(volume, (int, float)) else None
    avg_val = int(avg_vol) if avg_vol and isinstance(avg_vol, (int, float)) else None

    lines = [
        f"📈 *{name}* (`{ticker}`)",
        price_header,
        f"📊 *Key Stats*",
        f"  52W High: `{_fmt_num(high_52) if high_52 else 'N/A'}`  |  52W Low: `{_fmt_num(low_52) if low_52 else 'N/A'}`",
        f"  Market Cap: `{_mktcap(mkt_cap)}`" + (f"  |  Sector: `{sector}`" if sector else ""),
        pe_str,
    ]
    if eps_val:
        lines.append(f"  EPS: `{eps_val:.2f}`")
    if div_val:
        lines.append(f"  Dividend Yield: `{div_val * 100:.2f}%`")
    if vol_val:
        lines.append(f"  Volume: `{vol_val:,}`" + (f"  Avg: `{avg_val:,}`" if avg_val else ""))

    # Institutional delivery metric if available
    if bhav_data:
        lines.append(f"  Delivery: `{bhav_data['delivery_pct']}%` (`₹{bhav_data['turnover_cr']} Cr` traded)")

    # Earnings / Results date
    try:
        if t is not None:
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

    # Recent news (safely unpack legacy & modern yfinance structures)
    try:
        news_items = (t.news if t is not None else []) or []
        if news_items:
            valid_news = []
            for item in news_items:
                headline = item.get("title") or (item.get("content") or {}).get("title") or ""
                url = (
                    item.get("link")
                    or item.get("url")
                    or ((item.get("content") or {}).get("canonicalUrl") or {}).get("url")
                    or ((item.get("content") or {}).get("clickThroughUrl") or {}).get("url")
                    or ""
                )
                pub = (
                    item.get("publisher")
                    or ((item.get("content") or {}).get("provider") or {}).get("displayName")
                    or ""
                )
                if headline:
                    clean_hl = re.sub(r'[*_`\[\]()]', '', headline).strip()[:70]
                    clean_pub = re.sub(r'[*_`\[\]()]', '', pub).strip()
                    pub_str = f" _({clean_pub})_" if clean_pub else ""
                    if url:
                        valid_news.append(f"  • [{clean_hl}]({url}){pub_str}")
                    else:
                        valid_news.append(f"  • {clean_hl}{pub_str}")
                if len(valid_news) >= 3:
                    break

            if valid_news:
                lines.append("\n📰 *Recent News*")
                lines.extend(valid_news)
    except Exception as e:
        logger.debug(f"News fetch error for {ticker}: {e}")

    lines.append(f"\n_Data via Yahoo Finance & NSE Bhavcopy · {_now_ist()}_")
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

    price = info.get("currentPrice") or info.get("regularMarketPrice")
    if price is None and t is not None:
        price = getattr(t.fast_info, "last_price", None)

    return {
        "name": info.get("longName") or info.get("shortName") or ticker,
        "ticker": ticker,
        "sector": info.get("sector"),
        "industry": info.get("industry"),
        "price": price,
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
