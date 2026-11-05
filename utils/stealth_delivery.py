"""
utils/stealth_delivery.py — Stealth Institutional Delivery Accumulation Screener.
Pulls official NSE Full Bhavcopy deliverable data (100% free) to detect where institutions
are taking physical delivery into demat accounts rather than intraday day-trading.
"""
from __future__ import annotations
import io
import time
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from typing import Optional
import httpx
import pandas as pd

from config import TIMEZONE
from utils.logger import logger
from utils.earnings import get_watchlist

_BHAV_CACHE: tuple[str, pd.DataFrame] | None = None
_CACHE_TIMESTAMP: float = 0.0
_CACHE_TTL = 7200  # 2 hours


def _clean_symbol(sym: str) -> str:
    """Normalize symbol by stripping exchange extensions (.NS, .BO)."""
    return sym.upper().replace(".NS", "").replace(".BO", "").strip()


def fetch_nse_bhavcopy_delivery(target_date: Optional[datetime.date] = None) -> Optional[pd.DataFrame]:
    """
    Fetch the latest available official NSE sec_bhavdata_full CSV.
    Rolls back up to 4 days to find the most recent trading day (handles weekends/holidays).
    """
    global _BHAV_CACHE, _CACHE_TIMESTAMP
    now_ts = time.time()

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        ),
        "Accept": "*/*",
    }

    base_date = target_date or datetime.now(ZoneInfo(TIMEZONE)).date()

    # Try today, yesterday, up to 4 days back
    for offset in range(5):
        d = base_date - timedelta(days=offset)
        # Skip Saturday and Sunday
        if d.weekday() >= 5:
            continue

        d_str = d.strftime("%d%m%Y")
        if _BHAV_CACHE and _BHAV_CACHE[0] == d_str and (now_ts - _CACHE_TIMESTAMP) < _CACHE_TTL:
            return _BHAV_CACHE[1]

        url = f"https://nsearchives.nseindia.com/products/content/sec_bhavdata_full_{d_str}.csv"
        try:
            with httpx.Client(timeout=12.0, follow_redirects=True) as client:
                resp = client.get(url, headers=headers)
                if resp.status_code == 200 and "SYMBOL" in resp.text:
                    df = pd.read_csv(io.StringIO(resp.text))
                    df.columns = df.columns.str.strip()

                    # Clean whitespace in string columns
                    for col in ["SYMBOL", "SERIES", "DATE1", "DELIV_PER"]:
                        if col in df.columns:
                            df[col] = df[col].astype(str).str.strip()

                    # Convert numeric columns
                    for col in ["DELIV_PER", "TURNOVER_LACS", "TTL_TRD_QNTY", "DELIV_QTY", "CLOSE_PRICE", "PREV_CLOSE"]:
                        if col in df.columns:
                            df[col] = pd.to_numeric(df[col], errors="coerce")

                    # Keep equity series only
                    if "SERIES" in df.columns:
                        df = df[df["SERIES"] == "EQ"].copy()

                    _BHAV_CACHE = (d_str, df)
                    _CACHE_TIMESTAMP = now_ts
                    logger.info(f"Loaded NSE Full Bhavcopy delivery data for {d_str} ({len(df)} equities).")
                    return df
        except Exception as e:
            logger.debug(f"Could not load bhavdata for {d_str}: {e}")

    return _BHAV_CACHE[1] if _BHAV_CACHE else None


def get_stock_delivery_data(symbol: str) -> Optional[dict]:
    """Get delivery metrics for a specific stock."""
    df = fetch_nse_bhavcopy_delivery()
    if df is None or df.empty:
        return None

    clean_sym = _clean_symbol(symbol)
    matched = df[df["SYMBOL"] == clean_sym]
    if matched.empty:
        return None

    row = matched.iloc[0]
    prev_close = row.get("PREV_CLOSE") or 0.0
    close_price = row.get("CLOSE_PRICE") or 0.0
    change_pct = ((close_price - prev_close) / prev_close) * 100 if prev_close else 0.0

    return {
        "symbol": clean_sym,
        "date": str(row.get("DATE1", "")),
        "close": round(close_price, 2),
        "change_pct": round(change_pct, 2),
        "traded_qty": int(row.get("TTL_TRD_QNTY") or 0),
        "delivered_qty": int(row.get("DELIV_QTY") or 0),
        "delivery_pct": round(float(row.get("DELIV_PER") or 0.0), 2),
        "turnover_cr": round(float(row.get("TURNOVER_LACS") or 0.0) / 100.0, 2),
    }


def screen_stealth_accumulation(
    min_delivery_pct: float = 60.0,
    min_turnover_cr: float = 15.0,
    top_n: int = 6,
) -> list[dict]:
    """
    Screen for non-ETF stocks with high turnover (>= ₹15 Cr) and high delivery percentage (>= 60%).
    Indicates real institutional accumulation taking shares into demat accounts.
    """
    df = fetch_nse_bhavcopy_delivery()
    if df is None or df.empty:
        return []

    # Exclude ETF keywords
    etf_keywords = ["ETF", "BEES", "CASE", "LIQUID", "GOLD", "SILVER", "NIFTY", "SENSEX"]
    pattern = "|".join(etf_keywords)
    filtered = df[~df["SYMBOL"].str.contains(pattern, case=False, na=False)].copy()

    # Apply criteria: Delivery % >= min_delivery_pct and Turnover (in Lakhs) >= min_turnover_cr * 100
    min_lacs = min_turnover_cr * 100.0
    candidates = filtered[
        (filtered["DELIV_PER"] >= min_delivery_pct) & (filtered["TURNOVER_LACS"] >= min_lacs)
    ].sort_values(by="DELIV_PER", ascending=False)

    results = []
    for _, row in candidates.head(top_n).iterrows():
        prev_close = row.get("PREV_CLOSE") or 0.0
        close_price = row.get("CLOSE_PRICE") or 0.0
        change_pct = ((close_price - prev_close) / prev_close) * 100 if prev_close else 0.0

        results.append({
            "symbol": row["SYMBOL"],
            "date": str(row.get("DATE1", "")),
            "close": round(close_price, 2),
            "change_pct": round(change_pct, 2),
            "turnover_cr": round(float(row.get("TURNOVER_LACS") or 0.0) / 100.0, 2),
            "delivery_pct": round(float(row.get("DELIV_PER") or 0.0), 2),
            "traded_qty": int(row.get("TTL_TRD_QNTY") or 0),
        })

    return results


def format_stealth_delivery_card(custom_symbol: Optional[str] = None) -> str:
    """Format the delivery accumulation card for Telegram."""
    df = fetch_nse_bhavcopy_delivery()
    if df is None or df.empty:
        return (
            "🐋 **Stealth Institutional Delivery Radar**\n\n"
            "⚠️ Unable to load latest NSE Deliverable Bhavcopy. "
            "NSE publishes deliverable reports after 18:00 IST on trading days."
        )

    date_str = _BHAV_CACHE[0] if _BHAV_CACHE else "Latest Trading Session"

    # Single stock deep-dive
    if custom_symbol:
        data = get_stock_delivery_data(custom_symbol)
        if not data:
            return f"❌ Could not find deliverable volume data for *'{custom_symbol}'* in the latest NSE session."

        arrow = "🟢 ▲" if data["change_pct"] >= 0 else "🔴 ▼"
        signal = "🔥 **High Institutional Conviction**" if data["delivery_pct"] >= 60 else (
            "⚖️ Moderate Delivery" if data["delivery_pct"] >= 40 else "⚡ Heavy Intraday Speculation"
        )

        return (
            f"🐋 **Institutional Delivery Analysis: {data['symbol']}**\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"• **Close Price:** `₹{data['close']:,.2f}` ({arrow} {data['change_pct']:+.2f}%)\n"
            f"• **Delivery Percentage:** `{data['delivery_pct']}%`\n"
            f"• **Deliverable Volume:** `{data['delivered_qty']:,}` shares\n"
            f"• **Total Turnover:** `₹{data['turnover_cr']} Crores`\n"
            f"• **Signal:** {signal}\n\n"
            f"💡 _Stocks with >60% delivery indicate institutions taking shares into demat accounts._\n"
            f"_Date: {data['date']}_"
        )

    # Full radar: Watchlist + Market Leaders
    lines = [
        f"🐋 **Stealth Institutional Delivery Radar**",
        f"_Source: Official NSE Bhavcopy · Date: {date_str}_\n"
    ]

    # 1. User's Watchlist Check
    watchlist = get_watchlist()
    if watchlist:
        lines.append("📋 **Your Watchlist Delivery Radar**")
        for w in watchlist[:5]:
            d = get_stock_delivery_data(w["ticker"])
            if d:
                icon = "🔥" if d["delivery_pct"] >= 60 else "📌"
                lines.append(
                    f"  {icon} *{w['company']}*: `{d['delivery_pct']}%` delivery "
                    f"(`₹{d['turnover_cr']} Cr` traded | {d['change_pct']:+.2f}%)"
                )
        lines.append("")

    # 2. Market-Wide Stealth Accumulation
    screened = screen_stealth_accumulation(min_delivery_pct=60.0, min_turnover_cr=15.0, top_n=6)
    if screened:
        lines.append("🚀 **Top Stealth Institutional Accumulations (₹15Cr+ & >60% Delivery)**")
        for s in screened:
            arrow = "▲" if s["change_pct"] >= 0 else "▼"
            lines.append(
                f"  • *{s['symbol']}*: `₹{s['close']:,.2f}` ({arrow} {s['change_pct']:+.2f}%)\n"
                f"    ↳ Delivery: **{s['delivery_pct']}%** | Turnover: `₹{s['turnover_cr']} Cr`"
            )
        lines.append("")

    lines.append("💡 **Institutional Rule:** High delivery (>60%) with turnover > ₹15Cr signals smart money accumulation, not day-trading churn.")
    lines.append("💡 _Use `/stealth <stock>` for a single stock delivery check._")
    return "\n".join(lines)
