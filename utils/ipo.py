"""
utils/ipo.py — Live IPO intelligence & Grey Market Premium (GMP) tracker.
Scrapes live data from InvestorGain with fallback, caching, and Telegram formatting.
"""
from __future__ import annotations
import time
import re
from typing import Optional
import httpx
from bs4 import BeautifulSoup
from utils.logger import logger

_IPO_CACHE: tuple[float, list[dict]] | None = None
_IPO_CACHE_TTL = 3600  # 1 hour cache


def fetch_live_ipo_data() -> list[dict]:
    """
    Fetch live IPO GMP data from InvestorGain.
    Returns a list of dicts with keys:
    {name, price, gmp, gain_pct, rating, sub, open_date, close_date, listing_date, status}
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
            for r in rows[1:]:  # skip header
                cols = [c.get_text(strip=True) for c in r.find_all(["td", "th"])]
                if len(cols) < 9:
                    continue

                raw_name = cols[0]
                if not raw_name or "Google" in raw_name or "Advertisement" in raw_name:
                    continue

                # Strip trailing status flags like 'O' (Open), 'C' (Closed), 'U' (Upcoming)
                clean_name = re.sub(r"(BSE|NSE)\s*(SME|Mainboard)?[OCU]?$", r" (\1 \2)", raw_name).strip()
                if not clean_name:
                    clean_name = raw_name

                # Column mapping:
                # 0: Name
                # 1: GMP
                # 2: Rating (🔥)
                # 3: Subscription (e.g. '4.82x')
                # 4: Price band (e.g. '66')
                # 5: IPO Size (e.g. '₹22.98 Cr')
                # 7: Open date
                # 8: Close date
                # 10: Listing date
                gmp_raw = cols[1] if len(cols) > 1 else "--"
                rating = cols[2] if len(cols) > 2 else ""
                sub = cols[3] if len(cols) > 3 else "--"
                price = cols[4] if len(cols) > 4 else "--"
                open_d = cols[7] if len(cols) > 7 else ""
                close_d = cols[8] if len(cols) > 8 else ""
                listing_d = cols[10] if len(cols) > 10 else ""

                # Extract gain % from GMP string if present (e.g. '₹1(1.06%)')
                gain_match = re.search(r"\(([\d\.\+\-]+%)\)", gmp_raw)
                gain_pct = gain_match.group(1) if gain_match else ""

                # Simplify GMP display
                gmp_val_match = re.search(r"₹\s*([0-9\.\-]+)", gmp_raw)
                gmp_display = f"₹{gmp_val_match.group(1)}" if gmp_val_match else gmp_raw.split("(")[0].strip()

                dates_parts = []
                if close_d:
                    # Clean up any trailing text in date
                    c_clean = close_d.split("GMP")[0].strip()
                    dates_parts.append(f"Closes: {c_clean}")
                if listing_d:
                    dates_parts.append(f"Listing: {listing_d.strip()}")

                ipos.append({
                    "name": clean_name,
                    "gmp": gmp_display,
                    "gain_pct": gain_pct,
                    "price": f"₹{price}" if price and price != "--" and not price.startswith("₹") else price,
                    "subscription": sub,
                    "rating": rating,
                    "dates": " · ".join(dates_parts),
                })


            if ipos:
                _IPO_CACHE = (now, ipos)
                logger.info(f"Fetched {len(ipos)} live IPO records from InvestorGain.")
                return ipos

    except Exception as e:
        logger.error(f"Error fetching IPO data from InvestorGain: {e}")

    # Fallback to cached if available
    if _IPO_CACHE:
        return _IPO_CACHE[1]
    return []


def format_ipo_card(max_items: int = 8) -> str:
    """Format parsed IPO data into a rich Telegram Markdown card."""
    ipos = fetch_live_ipo_data()
    if not ipos:
        return (
            "📋 *IPO & Grey Market Radar*\n\n"
            "⚠️ Unable to fetch live IPO data right now. Please check back later or visit "
            "[InvestorGain](https://www.investorgain.com/report/ipo-gmp-live/331/)."
        )

    lines = [
        "🚀 *Live IPO & Grey Market Premium (GMP) Radar*\n",
        f"_Source: InvestorGain · Updated: {time.strftime('%d %b %Y, %I:%M %p')}_\n"
    ]

    for i, item in enumerate(ipos[:max_items], 1):
        rating_icon = "🔥 " if "🔥" in item.get("rating", "") else "📌 "
        gain_str = f" ({item['gain_pct']} est. gain)" if item.get("gain_pct") else ""

        lines.append(f"{rating_icon}*{item['name']}*")
        lines.append(f"   💰 *Issue Price:* `{item['price']}`  |  *GMP:* `{item['gmp']}`{gain_str}")
        if item.get("subscription") and item["subscription"] != "--":
            lines.append(f"   👥 *Subscribed:* `{item['subscription']}`")
        if item.get("dates"):
            lines.append(f"   📅 _{item['dates']}_")
        lines.append("")


    lines.append("💡 _GMP is indicative and fluctuates based on grey market sentiment._")
    return "\n".join(lines)
