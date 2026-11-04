"""
utils/thesis.py — Investment Thesis Tracker.
Persists theses in data/thesis.json, tracks live prices, targets, stop-losses, and returns formatted cards.
"""
from __future__ import annotations
import json
import uuid
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo
from typing import Optional

from utils.logger import logger
from utils.finance import fuzzy_resolve_stock, _fetch_price

THESIS_FILE = Path(__file__).parent.parent / "data" / "thesis.json"


def _load_theses() -> list[dict]:
    if not THESIS_FILE.exists():
        return []
    try:
        data = json.loads(THESIS_FILE.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except Exception as e:
        logger.error(f"Error loading {THESIS_FILE}: {e}")
        return []


def _save_theses(theses: list[dict]) -> None:
    try:
        THESIS_FILE.parent.mkdir(parents=True, exist_ok=True)
        THESIS_FILE.write_text(json.dumps(theses, indent=2, ensure_ascii=False), encoding="utf-8")
    except Exception as e:
        logger.error(f"Error saving {THESIS_FILE}: {e}")


def add_thesis(
    query: str,
    entry_price: float,
    target_price: float,
    stoploss: Optional[float] = None,
    rationale: str = "",
) -> tuple[bool, str]:
    """
    Log a new investment thesis.
    Resolves query to company name & ticker.
    """
    company_name, ticker = fuzzy_resolve_stock(query)
    if not ticker:
        ticker = f"{query.upper()}.NS"
        company_name = query.title()

    # If entry_price is 0 or not given, fetch current market price
    if entry_price <= 0:
        price_data = _fetch_price(ticker)
        if price_data:
            entry_price = price_data["price"]
        else:
            return False, f"Could not determine current price for {ticker}. Please provide entry price."

    thesis_id = f"th_{uuid.uuid4().hex[:6]}"
    now_ist = datetime.now(ZoneInfo("Asia/Kolkata")).isoformat()

    thesis = {
        "id": thesis_id,
        "ticker": ticker,
        "company": company_name,
        "entry_price": round(float(entry_price), 2),
        "target_price": round(float(target_price), 2),
        "stoploss": round(float(stoploss), 2) if stoploss else None,
        "rationale": rationale.strip(),
        "created_at": now_ist,
        "status": "OPEN",  # OPEN, CLOSED
        "target_hit": False,
        "stoploss_hit": False,
    }

    theses = _load_theses()
    theses.append(thesis)
    _save_theses(theses)

    sl_str = f" | Stoploss: ₹{thesis['stoploss']}" if thesis["stoploss"] else ""
    msg = (
        f"✅ **Investment Thesis Logged** (`{thesis_id}`)\n\n"
        f"📌 **{company_name}** (`{ticker}`)\n"
        f"💰 Entry: `₹{thesis['entry_price']}`\n"
        f"🎯 Target: `₹{thesis['target_price']}`{sl_str}\n"
        f"📝 *Rationale:* {rationale or 'Fundamental long position'}\n\n"
        f"I will monitor this position and alert you when price targets or stop-losses are reached, sir."
    )
    return True, msg


def close_thesis(thesis_id_or_company: str) -> tuple[bool, str]:
    """Close an active thesis by ID or company name."""
    theses = _load_theses()
    matched = None
    query = thesis_id_or_company.strip().lower()

    for t in theses:
        if t["status"] == "OPEN" and (
            t["id"].lower() == query or query in t["company"].lower() or query in t["ticker"].lower()
        ):
            matched = t
            break

    if not matched:
        return False, f"❌ No open investment thesis found matching '{thesis_id_or_company}'."

    matched["status"] = "CLOSED"
    matched["closed_at"] = datetime.now(ZoneInfo("Asia/Kolkata")).isoformat()
    _save_theses(theses)

    # Fetch final price to compute realized P&L
    final_price_data = _fetch_price(matched["ticker"])
    pnl_str = ""
    if final_price_data:
        exit_p = final_price_data["price"]
        diff = exit_p - matched["entry_price"]
        pct = (diff / matched["entry_price"]) * 100
        pnl_str = f"\n🏁 Exit Price: `₹{exit_p}` | Realized: `{diff:+.2f}` ({pct:+.2f}%)"

    return True, f"✅ Closed thesis for **{matched['company']}** (`{matched['id']}`).{pnl_str}"


def format_theses_card(include_closed: bool = False) -> str:
    """Format all investment theses with live prices, current P&L, and target distances."""
    theses = _load_theses()
    active = [t for t in theses if t.get("status") == "OPEN"]

    if not active:
        return (
            "💼 **Investment Thesis Portfolio**\n\n"
            "You have no open investment theses recorded, sir.\n\n"
            "_To log one, tell me:_\n"
            "`Log thesis: Buy Infosys at 1800, target 2100, stoploss 1700, reason: cloud growth`\n"
            "or use `/thesis new <symbol> <entry> <target> [stoploss]`"
        )

    lines = [f"💼 **Active Investment Theses ({len(active)})**\n"]

    for t in active:
        ticker = t["ticker"]
        price_data = _fetch_price(ticker)
        cmp_line = ""
        pnl_line = ""
        if price_data:
            cmp = price_data["price"]
            diff = cmp - t["entry_price"]
            pnl_pct = (diff / t["entry_price"]) * 100
            icon = "🟢" if diff >= 0 else "🔴"
            cmp_line = f"CMP: `₹{cmp}` ({icon} {diff:+.2f} / {pnl_pct:+.2f}%)"

            # Target distance
            tgt_dist = ((t["target_price"] - cmp) / cmp) * 100
            tgt_info = f"Target: `₹{t['target_price']}` ({tgt_dist:+.1f}% away)"
        else:
            tgt_info = f"Target: `₹{t['target_price']}`"

        sl_info = f" | SL: `₹{t['stoploss']}`" if t.get("stoploss") else ""
        lines.append(f"📌 **{t['company']}** (`{t['id']}`)")
        lines.append(f"   Entry: `₹{t['entry_price']}` | {cmp_line}")
        lines.append(f"   🎯 {tgt_info}{sl_info}")
        if t.get("rationale"):
            lines.append(f"   📝 _{t['rationale']}_")
        lines.append("")

    lines.append("💡 _Use `/thesis close <id>` to mark a position as completed._")
    return "\n".join(lines)


def check_thesis_triggers() -> list[str]:
    """
    Check all open theses against live market prices.
    Returns list of notification alert messages if targets/stoplosses are hit.
    """
    theses = _load_theses()
    alerts: list[str] = []
    modified = False

    for t in theses:
        if t.get("status") != "OPEN":
            continue

        price_data = _fetch_price(t["ticker"])
        if not price_data:
            continue

        cmp = price_data["price"]

        # Target check
        if cmp >= t["target_price"] and not t.get("target_hit"):
            t["target_hit"] = True
            modified = True
            gain = ((cmp - t["entry_price"]) / t["entry_price"]) * 100
            alerts.append(
                f"🎯 **THESIS TARGET REACHED!**\n\n"
                f"📌 **{t['company']}** (`{t['ticker']}`)\n"
                f"• Current Price: `₹{cmp}` (Target: `₹{t['target_price']}`)\n"
                f"• Entry: `₹{t['entry_price']}` | Gain: `+{gain:.2f}%` 🚀\n"
                f"• Original Thesis: _{t.get('rationale', 'Target achieved')}_\n\n"
                f"Consider taking profits or trailing your stoploss, sir."
            )

        # Stoploss check
        if t.get("stoploss") and cmp <= t["stoploss"] and not t.get("stoploss_hit"):
            t["stoploss_hit"] = True
            modified = True
            loss = ((cmp - t["entry_price"]) / t["entry_price"]) * 100
            alerts.append(
                f"⚠️ **THESIS STOPLOSS BREACHED!**\n\n"
                f"📌 **{t['company']}** (`{t['ticker']}`)\n"
                f"• Current Price: `₹{cmp}` (Stoploss: `₹{t['stoploss']}`)\n"
                f"• Entry: `₹{t['entry_price']}` | Drawdown: `{loss:.2f}%`\n"
                f"• Thesis: _{t.get('rationale', 'Risk threshold hit')}_\n\n"
                f"Action required: Check support levels or execute risk management plan."
            )

    if modified:
        _save_theses(theses)

    return alerts
