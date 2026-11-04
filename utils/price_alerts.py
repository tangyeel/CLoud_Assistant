"""
utils/price_alerts.py — Plain-English Price & Movement Alerts.
Persists alert rules in data/price_alerts.json and continuously evaluates them.
"""
from __future__ import annotations
import json
import uuid
import re
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo
from typing import Optional

from utils.logger import logger
from utils.finance import fuzzy_resolve_stock, _fetch_price

ALERTS_FILE = Path(__file__).parent.parent / "data" / "price_alerts.json"


def _load_alerts() -> list[dict]:
    if not ALERTS_FILE.exists():
        return []
    try:
        data = json.loads(ALERTS_FILE.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except Exception as e:
        logger.error(f"Error loading {ALERTS_FILE}: {e}")
        return []


def _save_alerts(alerts: list[dict]) -> None:
    try:
        ALERTS_FILE.parent.mkdir(parents=True, exist_ok=True)
        ALERTS_FILE.write_text(json.dumps(alerts, indent=2, ensure_ascii=False), encoding="utf-8")
    except Exception as e:
        logger.error(f"Error saving {ALERTS_FILE}: {e}")


def create_price_alert(
    query: str,
    target_price: Optional[float] = None,
    pct_change: Optional[float] = None,
    direction: Optional[str] = None,  # "above", "below", "either"
    raw_instruction: str = "",
) -> tuple[bool, str]:
    """
    Create a new persistent price alert for a stock or index.
    Auto-detects direction if target_price is given relative to CMP.
    """
    company_name, ticker = fuzzy_resolve_stock(query)
    if not ticker:
        ticker = f"{query.upper()}.NS"
        company_name = query.title()

    price_data = _fetch_price(ticker)
    cmp = price_data["price"] if price_data else None

    # Determine alert type & conditions
    if target_price is not None and target_price > 0:
        alert_type = "price"
        if not direction:
            if cmp is not None:
                direction = "above" if target_price >= cmp else "below"
            else:
                direction = "above"
        threshold = round(float(target_price), 2)
    elif pct_change is not None and pct_change != 0:
        alert_type = "pct_change"
        direction = direction or ("above" if pct_change > 0 else "below")
        threshold = round(abs(float(pct_change)), 2)
    else:
        return False, "❌ I need either a target price (e.g. 1900) or a percentage move (e.g. 2%)."

    alert_id = f"alt_{uuid.uuid4().hex[:6]}"
    now_ist = datetime.now(ZoneInfo("Asia/Kolkata")).isoformat()

    alert_obj = {
        "id": alert_id,
        "company": company_name,
        "ticker": ticker,
        "alert_type": alert_type,  # 'price' or 'pct_change'
        "threshold": threshold,
        "direction": direction,    # 'above', 'below'
        "baseline_price": cmp,
        "raw_instruction": raw_instruction or f"Alert when {company_name} is {direction} {threshold}",
        "created_at": now_ist,
        "active": True,
        "triggered": False,
    }

    alerts = _load_alerts()
    alerts.append(alert_obj)
    _save_alerts(alerts)

    cmp_str = f" (CMP: `₹{cmp}`)" if cmp else ""
    if alert_type == "price":
        cond_str = f"crosses {'above' if direction == 'above' else 'below'} `₹{threshold}`"
    else:
        cond_str = f"moves {direction} by `{threshold}%` from current baseline"

    msg = (
        f"🔔 **Price Alert Activated** (`{alert_id}`)\n\n"
        f"📌 **{company_name}** (`{ticker}`){cmp_str}\n"
        f"🎯 Condition: {cond_str}\n\n"
        f"I am actively monitoring this and will alert you the moment it triggers, sir."
    )
    return True, msg


def parse_and_create_alert_from_text(text: str) -> tuple[bool, str]:
    """
    Parse natural language alert requests like:
    - 'Alert me when Infosys hits 1900'
    - 'Alert if Reliance drops below 1200'
    - 'Notify me when Nifty drops 2%'
    - 'Alert when Tata Motors moves up 5%'
    """
    clean = text.lower()

    # Pattern 1: Percentage movement
    pct_match = re.search(r"(\w[\w\s]{1,25})\s+(?:drops?|falls?|down|slumps?)\s+(\d+(?:\.\d+)?)\s*%", clean)
    if pct_match:
        stock = pct_match.group(1).strip()
        val = float(pct_match.group(2))
        return create_price_alert(stock, pct_change=-val, direction="below", raw_instruction=text)

    pct_match_up = re.search(r"(\w[\w\s]{1,25})\s+(?:gains?|rises?|up|moves up|jumps?)\s+(\d+(?:\.\d+)?)\s*%", clean)
    if pct_match_up:
        stock = pct_match_up.group(1).strip()
        val = float(pct_match_up.group(2))
        return create_price_alert(stock, pct_change=val, direction="above", raw_instruction=text)

    # Pattern 2: Price hits / reaches / drops below
    price_match = re.search(
        r"(?:alert|notify|tell me)?\s*(?:when|if)?\s*([a-zA-Z\s]{2,25})\s*(?:hits|reaches|crosses|touches|at|drops below|falls below|goes below|above|below)?\s*(?:rs\.?|inr|₹)?\s*(\d+(?:\.\d+)?)",
        clean,
    )
    if price_match:
        stock = price_match.group(1).replace("alert me when", "").replace("notify me when", "").strip()
        price_val = float(price_match.group(2))
        direction = "below" if any(w in clean for w in ["below", "drop", "fall"]) else "above"
        return create_price_alert(stock, target_price=price_val, direction=direction, raw_instruction=text)

    return False, "❌ Could not parse price alert parameters. Try: *'Alert me when Infosys hits 1900'* or *'Alert when Nifty drops 2%'*."


def list_alerts_card() -> str:
    """Format active and recent price alerts."""
    alerts = _load_alerts()
    active = [a for a in alerts if a.get("active")]

    if not active:
        return (
            "🔔 **Active Price Alerts**\n\n"
            "You have no active price alerts configured, sir.\n\n"
            "_You can set one in plain English anytime:_\n"
            "• `Alert me when Infosys hits 1900`\n"
            "• `Alert if Nifty drops 2%`\n"
            "• `/alerts cancel <id>` to remove an alert."
        )

    lines = [f"🔔 **Active Price Alerts ({len(active)})**\n"]
    for a in active:
        ticker = a["ticker"]
        price_data = _fetch_price(ticker)
        cmp_str = f" (CMP: `₹{price_data['price']}`)" if price_data else ""

        if a["alert_type"] == "price":
            cond = f"{'≥' if a['direction'] == 'above' else '≤'} `₹{a['threshold']}`"
        else:
            cond = f"{a['direction']} by `{a['threshold']}%`"

        lines.append(f"📌 **{a['company']}** (`{a['id']}`)")
        lines.append(f"   Condition: {cond}{cmp_str}")
        lines.append(f"   _{a.get('raw_instruction', '')}_")
        lines.append("")

    lines.append("💡 _Use `/alerts cancel <id>` to remove an active alert._")
    return "\n".join(lines)


def cancel_alert(alert_id_or_stock: str) -> tuple[bool, str]:
    """Cancel an active alert by ID or company name."""
    alerts = _load_alerts()
    matched = None
    query = alert_id_or_stock.strip().lower()

    for a in alerts:
        if a.get("active") and (
            a["id"].lower() == query or query in a["company"].lower() or query in a["ticker"].lower()
        ):
            matched = a
            break

    if not matched:
        return False, f"❌ No active alert found matching '{alert_id_or_stock}'."

    matched["active"] = False
    _save_alerts(alerts)
    return True, f"✅ Cancelled price alert (`{matched['id']}`) for **{matched['company']}**."


def check_price_alerts_triggers() -> list[str]:
    """
    Evaluate all active alerts against live prices.
    Returns list of notification alert messages if conditions are met.
    """
    alerts = _load_alerts()
    notifications: list[str] = []
    modified = False

    for a in alerts:
        if not a.get("active"):
            continue

        price_data = _fetch_price(a["ticker"])
        if not price_data:
            continue

        cmp = price_data["price"]
        triggered = False
        message = ""

        if a["alert_type"] == "price":
            threshold = a["threshold"]
            if a["direction"] == "above" and cmp >= threshold:
                triggered = True
                message = (
                    f"🔔 **PRICE ALERT TRIGGERED!**\n\n"
                    f"📈 **{a['company']}** (`{a['ticker']}`) has crossed above your target!\n"
                    f"• Current Price: `₹{cmp}` (Target: `₹{threshold}`)\n"
                    f"• Baseline when set: `₹{a.get('baseline_price', 'N/A')}`\n\n"
                    f"Condition met, sir."
                )
            elif a["direction"] == "below" and cmp <= threshold:
                triggered = True
                message = (
                    f"⚠️ **PRICE ALERT TRIGGERED!**\n\n"
                    f"📉 **{a['company']}** (`{a['ticker']}`) has dropped below your threshold!\n"
                    f"• Current Price: `₹{cmp}` (Threshold: `₹{threshold}`)\n"
                    f"• Baseline when set: `₹{a.get('baseline_price', 'N/A')}`\n\n"
                    f"Condition met, sir."
                )

        elif a["alert_type"] == "pct_change":
            base = a.get("baseline_price")
            if base and base > 0:
                pct_diff = ((cmp - base) / base) * 100
                threshold = a["threshold"]
                if a["direction"] == "above" and pct_diff >= threshold:
                    triggered = True
                    message = (
                        f"🚀 **VOLATILITY ALERT TRIGGERED!**\n\n"
                        f"📈 **{a['company']}** is up `+{pct_diff:.2f}%` from baseline!\n"
                        f"• CMP: `₹{cmp}` (Baseline: `₹{base}`)\n"
                        f"• Threshold: `+{threshold}%`\n"
                    )
                elif a["direction"] == "below" and pct_diff <= -threshold:
                    triggered = True
                    message = (
                        f"🔻 **VOLATILITY ALERT TRIGGERED!**\n\n"
                        f"📉 **{a['company']}** is down `{pct_diff:.2f}%` from baseline!\n"
                        f"• CMP: `₹{cmp}` (Baseline: `₹{base}`)\n"
                        f"• Threshold: `-{threshold}%`\n"
                    )

        if triggered:
            a["active"] = False
            a["triggered"] = True
            a["triggered_at"] = datetime.now(ZoneInfo("Asia/Kolkata")).isoformat()
            a["triggered_price"] = cmp
            modified = True
            notifications.append(message)

    if modified:
        _save_alerts(alerts)

    return notifications
