"""
utils/ipo.py — Live IPO Intelligence, Filtered Active Radar & Application Lifecycle Tracker.
Features:
1. Strict Active Filter: Only displays IPOs that have NOT closed their bidding dates.
2. Awaiting Listing Radar: Separately highlights closed IPOs awaiting exchange debut.
3. IPO Application Tracker: Tracks user bids, lot sizes, and schedules listing day monitoring.
4. Autonomous Listing Day Alerts:
   - Morning Listing Alert (10:00 AM IST) with Listing Price, Gain (₹ & %), and Lot Profit.
   - Day-End Performance Report (15:45 IST) with Closing Price, Intraday Range, and Total Return.
"""
from __future__ import annotations
import os
import json
import time
import re
from datetime import datetime, date
from pathlib import Path
from typing import Optional
from zoneinfo import ZoneInfo
import httpx
from bs4 import BeautifulSoup
from telegram import InlineKeyboardMarkup, InlineKeyboardButton
from config import TIMEZONE
from utils.logger import logger

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
IPO_APPS_FILE = DATA_DIR / "ipo_applications.json"

_IPO_CACHE: tuple[float, list[dict]] | None = None
_IPO_CACHE_TTL = 1800  # 30 minutes cache

_PERF_CACHE: tuple[float, list[dict]] | None = None
_PERF_CACHE_TTL = 1800  # 30 minutes cache


def parse_ipo_date(date_str: str, default_year: int = 2026) -> Optional[date]:
    """
    Parse date strings from InvestorGain like '5-Nov', '29-Oct', '4-NovGMP: 1', '6-Nov-26'.
    """
    if not date_str:
        return None
    clean = date_str.split("GMP")[0].strip()
    m = re.search(r"(\d{1,2})-([A-Za-z]{3})(?:-(\d{2,4}))?", clean)
    if not m:
        return None
    day = int(m.group(1))
    mon = m.group(2).capitalize()
    yr = int(m.group(3)) if m.group(3) else default_year
    if yr < 100:
        yr += 2000
    try:
        return datetime.strptime(f"{day}-{mon}-{yr}", "%d-%b-%Y").date()
    except Exception:
        return None


def fetch_live_ipo_data() -> list[dict]:
    """
    Fetch live IPO GMP and schedule data from InvestorGain.
    Parses and standardizes:
    - name, exchange_type, status ('OPEN', 'UPCOMING', 'AWAITING_LISTING', 'LISTED')
    - price, lot_size, gmp, gain_pct, subscription, rating
    - open_date, close_date, listing_date and their parsed date objects.
    """
    global _IPO_CACHE
    now = time.time()
    if _IPO_CACHE and (now - _IPO_CACHE[0]) < _IPO_CACHE_TTL:
        return _IPO_CACHE[1]

    url = "https://www.investorgain.com/report/ipo-gmp-live/331/"
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        ),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
    }

    ipos: list[dict] = []
    tz = ZoneInfo(TIMEZONE)
    today = datetime.now(tz).date()

    try:
        with httpx.Client(timeout=15.0, headers=headers, follow_redirects=True) as client:
            resp = client.get(url)
            if resp.status_code != 200:
                logger.warning(f"InvestorGain returned HTTP {resp.status_code}")
                return _IPO_CACHE[1] if _IPO_CACHE else []

            soup = BeautifulSoup(resp.text, "html.parser")
            table = soup.find("table")
            if not table:
                logger.warning("No table found on InvestorGain GMP report page.")
                return _IPO_CACHE[1] if _IPO_CACHE else []

            rows = table.find_all("tr")
            for r in rows[1:]:
                cols = [c.get_text(strip=True) for c in r.find_all(["td", "th"])]
                if len(cols) < 9:
                    continue

                raw_name = cols[0]
                if not raw_name or "Google" in raw_name or "Advertisement" in raw_name or "Name" in raw_name:
                    continue

                # Strip trailing status tags 'C' (Closed), 'O' (Open), 'U' (Upcoming)
                status_flag = "C" if raw_name.endswith("C") else ("O" if raw_name.endswith("O") else ("U" if raw_name.endswith("U") else ""))
                clean_name = re.sub(r"\[email&#160;protected\]", "", raw_name)
                clean_name = re.sub(r"\[email\s*protected\]", "", clean_name)
                clean_name = re.sub(r"\(\s*[0-9\.\+\-]+%\s*\)", "", clean_name)
                clean_name = re.sub(r"(BSE|NSE)\s*(SME|Mainboard)?[OCU]?$", r" (\1 \2)", clean_name).strip()
                clean_name = re.sub(r"\s+", " ", clean_name).strip()
                if not clean_name:
                    clean_name = raw_name

                # Column mapping:
                # 0: Name, 1: GMP, 2: Rating, 3: Sub, 4: Price, 5: Size, 6: Lot, 7: Open, 8: Close, 10: Listing
                gmp_raw = cols[1] if len(cols) > 1 else "--"
                rating = cols[2] if len(cols) > 2 else ""
                sub = cols[3] if len(cols) > 3 else "--"
                price_str = cols[4] if len(cols) > 4 else "--"
                lot_str = cols[6] if len(cols) > 6 else "1"
                open_d = cols[7] if len(cols) > 7 else ""
                close_d = cols[8] if len(cols) > 8 else ""
                listing_d = cols[10] if len(cols) > 10 else ""

                # Extract gain % from GMP string if present (e.g. '₹1(1.06%)')
                gain_match = re.search(r"\(([\d\.\+\-]+%)\)", gmp_raw)
                gain_pct = gain_match.group(1) if gain_match else ""

                # Simplify GMP display
                gmp_val_match = re.search(r"₹\s*([0-9\.\-]+)", gmp_raw)
                gmp_display = f"₹{gmp_val_match.group(1)}" if gmp_val_match else gmp_raw.split("(")[0].strip()

                # Parse numeric price and lot
                price_val: Optional[float] = None
                p_match = re.search(r"([0-9]+(?:\.[0-9]+)?)", price_str.replace(",", ""))
                if p_match:
                    try:
                        price_val = float(p_match.group(1))
                    except ValueError:
                        pass

                lot_size = 1
                l_match = re.search(r"([0-9]+(?:,[0-9]+)?)", lot_str)
                if l_match:
                    try:
                        lot_size = int(l_match.group(1).replace(",", ""))
                    except ValueError:
                        pass

                open_dt = parse_ipo_date(open_d)
                close_dt = parse_ipo_date(close_d)
                listing_dt = parse_ipo_date(listing_d)

                # Classify IPO Status
                if close_dt:
                    if close_dt >= today:
                        if open_dt and open_dt > today:
                            status = "UPCOMING"
                        else:
                            status = "OPEN"
                    else:
                        if listing_dt and listing_dt >= today:
                            status = "AWAITING_LISTING"
                        else:
                            status = "LISTED"
                else:
                    if status_flag == "O":
                        status = "OPEN"
                    elif status_flag == "U":
                        status = "UPCOMING"
                    else:
                        status = "CLOSED"

                ipos.append({
                    "name": clean_name,
                    "raw_name": raw_name,
                    "status": status,
                    "price": f"₹{price_str}" if price_str and price_str != "--" and not price_str.startswith("₹") else price_str,
                    "price_val": price_val,
                    "lot_size": lot_size,
                    "gmp": gmp_display,
                    "gain_pct": gain_pct,
                    "subscription": sub,
                    "rating": rating,
                    "open_date": open_d.split("GMP")[0].strip(),
                    "close_date": close_d.split("GMP")[0].strip(),
                    "listing_date": listing_d.split("GMP")[0].strip(),
                    "open_date_obj": open_dt,
                    "close_date_obj": close_dt,
                    "listing_date_obj": listing_dt,
                })

            if ipos:
                _IPO_CACHE = (now, ipos)
                logger.info(f"Fetched {len(ipos)} IPO records from InvestorGain.")
                return ipos

    except Exception as e:
        logger.error(f"Error fetching IPO data from InvestorGain: {e}")

    if _IPO_CACHE:
        return _IPO_CACHE[1]
    return []


def get_active_ipos() -> list[dict]:
    """
    Return ONLY IPOs that have not closed their application window (close_date >= today).
    """
    all_ipos = fetch_live_ipo_data()
    today = datetime.now(ZoneInfo(TIMEZONE)).date()
    active: list[dict] = []
    for item in all_ipos:
        c_dt = item.get("close_date_obj")
        if c_dt and c_dt >= today:
            active.append(item)
        elif not c_dt and item.get("status") in ("OPEN", "UPCOMING"):
            active.append(item)
    return active


def get_awaiting_listing_ipos() -> list[dict]:
    """
    Return IPOs whose bidding has closed but are awaiting listing on exchange (listing_date >= today).
    """
    all_ipos = fetch_live_ipo_data()
    today = datetime.now(ZoneInfo(TIMEZONE)).date()
    awaiting: list[dict] = []
    for item in all_ipos:
        l_dt = item.get("listing_date_obj")
        c_dt = item.get("close_date_obj")
        if l_dt and l_dt >= today and (not c_dt or c_dt < today or item.get("status") == "AWAITING_LISTING"):
            awaiting.append(item)
    return awaiting


def fetch_ipo_performance_tracker() -> list[dict]:
    """
    Fetch listed IPO performance metrics from InvestorGain's performance tracker.
    Returns list of dicts with:
    {company, symbol, listing_date, issue_price, listing_price, listing_gain_pct, day_close, day_close_gain_pct}
    """
    global _PERF_CACHE
    now = time.time()
    if _PERF_CACHE and (now - _PERF_CACHE[0]) < _PERF_CACHE_TTL:
        return _PERF_CACHE[1]

    url = "https://www.investorgain.com/report/ipo-gmp-performance-tracker/377/"
    headers = {"User-Agent": "Mozilla/5.0"}
    records: list[dict] = []

    try:
        with httpx.Client(timeout=15.0, headers=headers, follow_redirects=True) as client:
            resp = client.get(url)
            if resp.status_code == 200:
                soup = BeautifulSoup(resp.text, "html.parser")
                table = soup.find("table")
                if table:
                    rows = table.find_all("tr")
                    for r in rows[1:]:
                        cols = [c.get_text(strip=True) for c in r.find_all(["td", "th"])]
                        if len(cols) >= 10:
                            comp = cols[0]
                            sym = cols[1]
                            l_date = cols[2]
                            iss_price_str = cols[6]
                            list_p_str = cols[8]
                            close_p_str = cols[9]

                            # Parse prices
                            def _parse_val_pct(text: str) -> tuple[Optional[float], Optional[float]]:
                                m = re.search(r"₹?\s*([0-9\.\,]+)\s*(?:\(([+-]?[0-9\.\,]+)%?\))?", text)
                                if not m:
                                    return None, None
                                val = float(m.group(1).replace(",", ""))
                                pct = float(m.group(2).replace(",", "")) if m.group(2) else None
                                return val, pct

                            iss_p, _ = _parse_val_pct(iss_price_str)
                            list_p, list_pct = _parse_val_pct(list_p_str)
                            close_p, close_pct = _parse_val_pct(close_p_str)

                            records.append({
                                "company": comp,
                                "symbol": sym,
                                "listing_date": l_date,
                                "issue_price": iss_p,
                                "listing_price": list_p,
                                "listing_gain_pct": list_pct,
                                "day_close": close_p,
                                "day_close_gain_pct": close_pct,
                            })

                    if records:
                        _PERF_CACHE = (now, records)
                        return records
    except Exception as e:
        logger.warning(f"Error fetching performance tracker: {e}")

    return _PERF_CACHE[1] if _PERF_CACHE else []


def _normalize_ipo_name(s: str) -> str:
    s = re.sub(r"\(\s*[0-9\.\+\-]+%\s*\)", "", s)
    s = re.sub(r"[^a-zA-Z0-9]", "", s).lower()
    for t in ["nsesme", "bsesme", "sme", "mainboard", "ipo"]:
        s = s.replace(t, "")
    return s


def fetch_ipo_listing_metrics(company_name: str, symbol: Optional[str] = None) -> Optional[dict]:
    """
    Fetch listing day metrics (Listing price, gain %, day-end close) for a newly listed stock.
    Prioritizes InvestorGain performance tracker, with yfinance as real-time fallback.
    """
    target_norm = _normalize_ipo_name(company_name)

    # 1. Check InvestorGain Performance Tracker
    tracker_data = fetch_ipo_performance_tracker()
    for row in tracker_data:
        r_norm = _normalize_ipo_name(row.get("company", ""))
        r_sym = row.get("symbol", "").lower()
        if (target_norm and (target_norm in r_norm or r_norm in target_norm)) or (symbol and symbol.lower() == r_sym):
            return {
                "listing_price": row.get("listing_price"),
                "listing_gain_pct": row.get("listing_gain_pct"),
                "day_close": row.get("day_close"),
                "day_close_gain_pct": row.get("day_close_gain_pct"),
                "symbol": row.get("symbol"),
                "day_high": None,
                "day_low": None,
            }

    # 2. yfinance Fallback
    try:
        import yfinance as yf
        candidates = []
        if symbol:
            candidates.extend([f"{symbol}.NS", f"{symbol}.BO", symbol])
        from utils.finance import resolve_ticker
        resolved = resolve_ticker(company_name)
        if resolved:
            candidates.append(resolved)

        for sym in candidates:
            try:
                t = yf.Ticker(sym)
                hist = t.history(period="5d")
                if not hist.empty:
                    last_row = hist.iloc[-1]
                    open_p = round(float(last_row["Open"]), 2)
                    close_p = round(float(last_row["Close"]), 2)
                    high_p = round(float(last_row["High"]), 2)
                    low_p = round(float(last_row["Low"]), 2)
                    return {
                        "listing_price": open_p,
                        "listing_gain_pct": None,
                        "day_close": close_p,
                        "day_close_gain_pct": None,
                        "symbol": sym,
                        "day_high": high_p,
                        "day_low": low_p,
                    }
            except Exception:
                continue
    except Exception as e:
        logger.debug(f"yfinance quote error for {company_name}: {e}")

    return None


# ---------------------------------------------------------------------------
# IPO Application Tracker Storage & Management
# ---------------------------------------------------------------------------

def _load_applications() -> list[dict]:
    os.makedirs(DATA_DIR, exist_ok=True)
    if not IPO_APPS_FILE.exists():
        return []
    try:
        with open(IPO_APPS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"Error loading ipo_applications.json: {e}")
        return []


def _save_applications(apps: list[dict]) -> None:
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(IPO_APPS_FILE, "w", encoding="utf-8") as f:
        json.dump(apps, f, indent=2)


def apply_for_ipo(
    query_name: str,
    issue_price: Optional[float] = None,
    lot_size: Optional[int] = None
) -> tuple[bool, str]:
    """
    Log an IPO application by matching the company against live market data.
    Sets up listing day alert notifications.
    """
    clean_q = query_name.strip()
    all_ipos = fetch_live_ipo_data()
    tz = ZoneInfo(TIMEZONE)
    today = datetime.now(tz).date()

    # Match in live IPO table or performance tracker
    norm_q = re.sub(r"[^a-zA-Z0-9]", "", clean_q).lower()
    matched_ipo: Optional[dict] = None
    for item in all_ipos:
        n1 = re.sub(r"[^a-zA-Z0-9]", "", item["name"]).lower()
        n2 = re.sub(r"[^a-zA-Z0-9]", "", item["raw_name"]).lower()
        if norm_q in n1 or norm_q in n2 or n1 in norm_q:
            matched_ipo = item
            break

    if not matched_ipo:
        tracker_data = fetch_ipo_performance_tracker()
        for row in tracker_data:
            c1 = re.sub(r"[^a-zA-Z0-9]", "", row.get("company", "")).lower()
            if norm_q in c1 or c1 in norm_q:
                matched_ipo = {
                    "name": row["company"],
                    "price_val": row.get("issue_price"),
                    "lot_size": 1,
                    "listing_date": row.get("listing_date"),
                    "listing_date_obj": parse_ipo_date(row.get("listing_date")),
                }
                break

    # If matched, auto-populate details
    official_name = matched_ipo["name"] if matched_ipo else clean_q
    final_price = issue_price or (matched_ipo.get("price_val") if matched_ipo else None)
    final_lot = lot_size or (matched_ipo.get("lot_size") if matched_ipo else 1)
    listing_date_str = matched_ipo.get("listing_date") if matched_ipo else None
    listing_date_obj = matched_ipo.get("listing_date_obj") if matched_ipo else None

    # Load existing applications to avoid duplicate
    apps = _load_applications()
    for existing in apps:
        if existing["name"].lower() == official_name.lower() and existing.get("status") == "APPLIED":
            return True, (
                f"🎩 Sir, you are already registered as having applied for **{official_name}**.\n\n"
                f"💰 **Issue Price:** `₹{existing.get('issue_price', '--')}`\n"
                f"📅 **Scheduled Listing:** `{existing.get('listing_date', 'TBD')}`\n\n"
                f"I am actively monitoring the exchange feeds and will notify you promptly on listing day."
            )

    # If listing date object not present, estimate or format
    if listing_date_obj:
        listing_date_iso = listing_date_obj.isoformat()
        listing_date_display = listing_date_obj.strftime("%A, %b %d, %Y")
    else:
        listing_date_iso = today.isoformat()
        listing_date_display = "Listing date to be announced"

    app_id = f"ipo_{int(time.time())}"
    new_app = {
        "id": app_id,
        "name": official_name,
        "query": clean_q,
        "issue_price": final_price or 100.0,
        "lot_size": final_lot,
        "applied_date": today.isoformat(),
        "listing_date": listing_date_iso,
        "listing_date_display": listing_date_display,
        "status": "APPLIED",
        "notified_listing": False,
        "listing_price": None,
        "listing_gain_pct": None,
        "listing_gain_amount": None,
        "notified_day_end": False,
        "closing_price": None,
        "day_end_gain_pct": None,
        "day_end_gain_amount": None,
    }

    # Check if stock has ALREADY listed (e.g. past listing date)
    if listing_date_obj and listing_date_obj <= today:
        metrics = fetch_ipo_listing_metrics(official_name)
        if metrics and metrics.get("listing_price"):
            lp = metrics["listing_price"]
            iss_p = new_app["issue_price"]
            gain = round(lp - iss_p, 2)
            gain_pct = round((gain / iss_p * 100), 2) if iss_p > 0 else 0.0
            lot_prof = round(gain * final_lot, 2)

            new_app["notified_listing"] = True
            new_app["listing_price"] = lp
            new_app["listing_gain_pct"] = gain_pct
            new_app["listing_gain_amount"] = lot_prof

            close_p = metrics.get("day_close")
            if close_p:
                c_gain = round(close_p - iss_p, 2)
                c_pct = round((c_gain / iss_p * 100), 2) if iss_p > 0 else 0.0
                new_app["notified_day_end"] = True
                new_app["closing_price"] = close_p
                new_app["day_end_gain_pct"] = c_pct
                new_app["day_end_gain_amount"] = round(c_gain * final_lot, 2)
                new_app["status"] = "LISTED"

            apps.append(new_app)
            _save_applications(apps)

            icon = "🚀" if gain >= 0 else "🔻"
            sign = "+" if gain >= 0 else ""
            res_lines = [
                f"🎩 Very well, sir. Logged application for **{official_name}**.",
                f"ℹ️ *Note: This IPO has already debuted on the exchange ({listing_date_display}).*\n",
                f"💰 **Issue Price:** `₹{iss_p:,.2f}`",
                f"🚀 **Listing Debut:** `₹{lp:,.2f}` ({sign}{gain_pct}%)",
                f"{icon} **Listing Gain:** `{sign}₹{gain:,.2f}` (`{sign}₹{lot_prof:,.2f}` per lot)",
            ]
            if close_p:
                c_sign = "+" if c_gain >= 0 else ""
                res_lines.append(f"🏁 **Day-End Close:** `₹{close_p:,.2f}` ({c_sign}{c_pct}%)")
            res_lines.append("\n✅ *Position registered and archived in your IPO Portfolio Tracker.*")
            return True, "\n".join(res_lines)

    apps.append(new_app)
    _save_applications(apps)

    price_str = f"₹{final_price:,.2f}" if final_price else "Band Cutoff"
    capital_str = f" (`₹{final_price * final_lot:,.2f}` total capital)" if final_price and final_lot > 1 else ""

    confirmation = (
        f"🎩 Very well, sir. I have logged your IPO application:\n\n"
        f"🏢 **Company:** {official_name}\n"
        f"💰 **Issue Price:** `{price_str}`\n"
        f"📦 **Lot Size:** {final_lot:,} shares{capital_str}\n"
        f"📅 **Scheduled Listing:** {listing_date_display}\n\n"
        f"🔔 **Automated Listing Day Protocol Activated:**\n"
        f"1. At 10:00 AM on listing day, I will immediately alert you with the official listing price, listing gains (₹ and %), and lot profit.\n"
        f"2. At market close (15:45 IST), I will deliver your comprehensive Day-End Performance Report."
    )
    return True, confirmation


def get_applied_ipos() -> list[dict]:
    """Return all tracked IPO applications."""
    return _load_applications()


def cancel_applied_ipo(query: str) -> tuple[bool, str]:
    """Remove a tracked IPO application."""
    apps = _load_applications()
    clean_q = query.strip().lower()
    matched_idx = None
    for i, a in enumerate(apps):
        if clean_q in a["name"].lower() or a["name"].lower() in clean_q:
            matched_idx = i
            break

    if matched_idx is None:
        return False, f"Could not find an active application matching *'{query}'*."

    removed = apps.pop(matched_idx)
    _save_applications(apps)
    return True, f"✅ Removed tracking for **{removed['name']}**."


def format_applied_ipos_card() -> tuple[str, InlineKeyboardMarkup]:
    """Generate Markdown card of user's tracked IPO applications."""
    apps = _load_applications()
    if not apps:
        msg = (
            "📋 **My Applied IPOs Tracker**\n\n"
            "You are not currently tracking any active IPO applications, sir.\n\n"
            "💡 *To track an application, simply say:*\n"
            "• `I applied for Antala Industries`\n"
            "• `Applied for Vedant Poly Fabs at 94`\n"
            "• `/ipo apply <company>`"
        )
        buttons = [[InlineKeyboardButton("🚀 Explore Open IPOs", callback_data="ipo_view_active")]]
        return msg, InlineKeyboardMarkup(buttons)

    lines = [
        "📋 **Your Tracked IPO Applications**\n",
    ]

    for a in apps:
        status_icon = "🟢" if a.get("status") == "APPLIED" else "🏁"
        lines.append(f"{status_icon} **{a['name']}** — *{a.get('status', 'APPLIED')}*")
        lines.append(f"   💰 Issue: `₹{a.get('issue_price', '--')}`  |  Lot: `{a.get('lot_size', 1):,}` shares")
        lines.append(f"   📅 Listing: `{a.get('listing_date_display', a.get('listing_date', 'TBD'))}`")

        if a.get("listing_price"):
            sign = "+" if (a.get("listing_gain_pct") or 0) >= 0 else ""
            lines.append(f"   🚀 Listed: `₹{a['listing_price']}` ({sign}{a.get('listing_gain_pct', 0)}% | `{sign}₹{a.get('listing_gain_amount', 0):,}`) ")
        if a.get("closing_price"):
            sign = "+" if (a.get("day_end_gain_pct") or 0) >= 0 else ""
            lines.append(f"   🏁 Day Close: `₹{a['closing_price']}` ({sign}{a.get('day_end_gain_pct', 0)}% | `{sign}₹{a.get('day_end_gain_amount', 0):,}`) ")
        lines.append("")

    lines.append("──────────────────────")
    buttons = [
        [
            InlineKeyboardButton("🚀 Open IPOs", callback_data="ipo_view_active"),
            InlineKeyboardButton("🕒 Awaiting Listing", callback_data="ipo_view_awaiting"),
        ]
    ]
    return "\n".join(lines), InlineKeyboardMarkup(buttons)


# ---------------------------------------------------------------------------
# Listing Day Alert Notification Dispatcher
# ---------------------------------------------------------------------------

def check_ipo_listing_day_alerts() -> list[str]:
    """
    Check tracked IPO applications and return listing alerts for delivery to Telegram.
    Triggered periodically during market hours by scheduler.
    """
    apps = _load_applications()
    if not apps:
        return []

    tz = ZoneInfo(TIMEZONE)
    now = datetime.now(tz)
    today = now.date()
    alerts: list[str] = []
    updated = False

    for app in apps:
        if app.get("status") != "APPLIED":
            continue

        l_date_str = app.get("listing_date")
        if not l_date_str:
            continue

        try:
            l_date = date.fromisoformat(l_date_str)
        except Exception:
            l_date = parse_ipo_date(l_date_str)

        if not l_date or l_date > today:
            continue

        # Stock is listing today or listed in past without notification
        iss_price = float(app.get("issue_price", 100.0))
        lot_size = int(app.get("lot_size", 1))

        # 1. MORNING LISTING ALERT (After 09:55 AM IST)
        if not app.get("notified_listing") and (now.hour > 9 or (now.hour == 9 and now.minute >= 55) or l_date < today):
            metrics = fetch_ipo_listing_metrics(app["name"])
            if metrics and metrics.get("listing_price"):
                lp = float(metrics["listing_price"])
                gain = round(lp - iss_price, 2)
                gain_pct = round((gain / iss_price * 100), 2) if iss_price > 0 else 0.0
                lot_profit = round(gain * lot_size, 2)

                app["notified_listing"] = True
                app["listing_price"] = lp
                app["listing_gain_pct"] = gain_pct
                app["listing_gain_amount"] = lot_profit
                updated = True

                icon = "🚀" if gain >= 0 else "🔻"
                sign = "+" if gain >= 0 else ""

                msg = (
                    f"🔔 **IPO LISTING DAY ALERT: {app['name']} IS LIVE!**\n\n"
                    f"💰 **Issue Price:** `₹{iss_price:,.2f}`\n"
                    f"🚀 **Listing Price:** `₹{lp:,.2f}`\n"
                    f"{icon} **Listing Gain:** `{sign}₹{gain:,.2f} ({sign}{gain_pct}%)`\n"
                    f"💵 **Net Profit per Lot:** `{sign}₹{lot_profit:,.2f}` ({lot_size:,} shares)\n\n"
                    f"Sir, I am monitoring intraday movements and will deliver your complete Day-End Performance Report at market close (15:45 IST)."
                )
                alerts.append(msg)

        # 2. DAY-END PERFORMANCE REPORT (After 15:45 IST or next day)
        if app.get("notified_listing") and not app.get("notified_day_end"):
            is_market_closed = (now.hour > 15 or (now.hour == 15 and now.minute >= 45) or l_date < today)
            if is_market_closed:
                metrics = fetch_ipo_listing_metrics(app["name"])
                if metrics and metrics.get("day_close"):
                    close_p = float(metrics["day_close"])
                    c_gain = round(close_p - iss_price, 2)
                    c_gain_pct = round((c_gain / iss_price * 100), 2) if iss_price > 0 else 0.0
                    c_lot_profit = round(c_gain * lot_size, 2)

                    app["notified_day_end"] = True
                    app["closing_price"] = close_p
                    app["day_end_gain_pct"] = c_gain_pct
                    app["day_end_gain_amount"] = c_lot_profit
                    app["status"] = "LISTED"
                    updated = True

                    icon = "🏁" if c_gain >= 0 else "🔻"
                    sign = "+" if c_gain >= 0 else ""

                    msg = (
                        f"📊 **IPO DAY-END PERFORMANCE REPORT: {app['name']}**\n\n"
                        f"💰 **Issue Price:** `₹{iss_price:,.2f}`\n"
                        f"🚀 **Listing Open:** `₹{app.get('listing_price', iss_price):,.2f}`\n"
                        f"🏁 **Day-End Close:** `₹{close_p:,.2f}`\n"
                        f"{icon} **Total Day Return:** `{sign}₹{c_gain:,.2f} ({sign}{c_gain_pct}% vs Issue)`\n"
                        f"💵 **Final Lot Profit:** `{sign}₹{c_lot_profit:,.2f}` ({lot_size:,} shares)\n\n"
                        f"🎩 Sir, the listing cycle is complete. Position recorded as **LISTED** in your portfolio tracker."
                    )
                    alerts.append(msg)

    if updated:
        _save_applications(apps)

    return alerts


# ---------------------------------------------------------------------------
# Telegram Card Formatting
# ---------------------------------------------------------------------------

def format_ipo_card(view: str = "active", max_items: int = 8) -> tuple[str, InlineKeyboardMarkup]:
    """
    Generate rich Telegram Markdown card for IPOs.
    Strictly filters to only show open/upcoming IPOs that haven't closed.
    Provides toggle buttons for Awaiting Listing and Applied IPOs.
    """
    tz = ZoneInfo(TIMEZONE)
    now = datetime.now(tz)
    date_display = now.strftime("%A, %b %d, %Y")

    if view == "awaiting":
        awaiting = get_awaiting_listing_ipos()
        lines = [
            "🕒 **IPOs Awaiting Exchange Listing**",
            f"📅 *{date_display}*\n",
            "_Bidding has closed for these issues; currently awaiting allotment & exchange debut._\n"
        ]
        if not awaiting:
            lines.append("🌴 No closed IPOs are currently awaiting listing.")
        else:
            for item in awaiting[:max_items]:
                gain_str = f" ({item['gain_pct']} est. gain)" if item.get("gain_pct") else ""
                lines.append(f"📌 **{item['name']}**")
                lines.append(f"   💰 Issue Price: `{item['price']}`  |  GMP: `{item['gmp']}`{gain_str}")
                if item.get("listing_date"):
                    lines.append(f"   📅 Scheduled Listing: *{item['listing_date']}*")
                lines.append("")

        lines.append("──────────────────────")
        lines.append("💡 *Track an IPO:* Say `I applied for <Company>` to receive listing day alerts!")
        buttons = [
            [
                InlineKeyboardButton("🚀 View Active IPOs", callback_data="ipo_view_active"),
                InlineKeyboardButton("📋 My Applied IPOs", callback_data="ipo_view_applied"),
            ],
            [InlineKeyboardButton("🔄 Refresh", callback_data="ipo_refresh")],
        ]
        return "\n".join(lines), InlineKeyboardMarkup(buttons)

    # Default 'active' view
    active_ipos = get_active_ipos()
    awaiting = get_awaiting_listing_ipos()

    lines = [
        "🚀 **Live IPO & Grey Market Premium (GMP) Radar**",
        f"📅 *{date_display}*\n",
    ]

    buttons = []

    if active_ipos:
        lines.append(f"_Showing {len(active_ipos[:max_items])} active IPOs open for retail bidding:_\n")
        for item in active_ipos[:max_items]:
            status_tag = "🟢 OPEN" if item.get("status") == "OPEN" else "⏳ UPCOMING"
            rating_icon = "🔥 " if "🔥" in item.get("rating", "") else ""
            gain_str = f" ({item['gain_pct']} est. gain)" if item.get("gain_pct") else ""

            lines.append(f"{rating_icon}**{item['name']}**  `[{status_tag}]`")
            lines.append(f"   💰 Issue Price: `{item['price']}`  |  GMP: `{item['gmp']}`{gain_str}")
            if item.get("subscription") and item["subscription"] != "--":
                lines.append(f"   👥 Subscribed: `{item['subscription']}`  |  Lot: `{item.get('lot_size', 1):,}` shares")
            if item.get("close_date"):
                lines.append(f"   📅 Closes on: *{item['close_date']}*  |  Listing: *{item.get('listing_date', 'TBA')}*")
            lines.append("")

        buttons.append([
            InlineKeyboardButton("🕒 Awaiting Listing", callback_data="ipo_view_awaiting"),
            InlineKeyboardButton("📋 My Applied IPOs", callback_data="ipo_view_applied"),
        ])
    else:
        # Bidding window is closed today (e.g. weekend or between cycles)
        lines.append("🚫 **Primary Market Bidding Closed:**")
        lines.append("There are currently no mainboard or SME IPOs actively accepting retail bids today (Primary market bidding is closed on weekends & between issue cycles).\n")

        if awaiting:
            lines.append(f"🕒 **Recent Issues Awaiting Exchange Listing ({len(awaiting)}):**")
            for item in awaiting[:3]:
                gain_str = f" ({item['gain_pct']})" if item.get("gain_pct") else ""
                lines.append(f"• **{item['name']}**")
                lines.append(f"   💰 Issue: `{item['price']}`  |  GMP: `{item['gmp']}`{gain_str}  |  📅 Listing: *{item.get('listing_date', 'TBA')}*")
            lines.append("")

        buttons.append([
            InlineKeyboardButton("🕒 All Awaiting Listing", callback_data="ipo_view_awaiting"),
            InlineKeyboardButton("📋 My Applied IPOs", callback_data="ipo_view_applied"),
        ])

    buttons.append([InlineKeyboardButton("🔄 Refresh", callback_data="ipo_refresh")])
    lines.append("──────────────────────")
    lines.append("💡 *Applied for an IPO?* Simply type `I applied for <Company>` to enable automatic Listing Day & Market Close alerts!")
    return "\n".join(lines), InlineKeyboardMarkup(buttons)


def format_ipo_card_text() -> str:
    """Return only the markdown text of the active IPO card."""
    text, _ = format_ipo_card()
    return text
