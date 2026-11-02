"""
utils/attendance.py — Thapar University Attendance Tracker & Safeguard.
Tracks attendance percentages per subject against the 75% minimum threshold.
Calculates safe skips (bunks remaining) or deficit recovery requirements.
"""
import os
import json
import math
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo
from telegram import InlineKeyboardMarkup, InlineKeyboardButton
from config import TIMEZONE
from utils.logger import logger

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
ATTENDANCE_FILE = DATA_DIR / "attendance.json"

DEFAULT_SUBJECTS = {
    "Operating Systems": {"attended": 23, "total": 26},
    "Data Structures And Algorithms": {"attended": 31, "total": 35},
    "Aptitude Skills Building": {"attended": 18, "total": 20},
}


def _load_data() -> dict:
    os.makedirs(DATA_DIR, exist_ok=True)
    if not ATTENDANCE_FILE.exists():
        initial = {"subjects": DEFAULT_SUBJECTS, "history": []}
        _save_data(initial)
        return initial

    try:
        with open(ATTENDANCE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"Error loading attendance file: {e}")
        return {"subjects": DEFAULT_SUBJECTS, "history": []}


def _save_data(data: dict) -> None:
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(ATTENDANCE_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


def get_attendance_stats() -> dict:
    """
    Compute attendance statistics, percentages, safe skips, or classes required.
    """
    data = _load_data()
    subjects = data.get("subjects", {})
    stats = {}
    total_attended = 0
    total_conducted = 0

    for name, record in subjects.items():
        att = record.get("attended", 0)
        tot = record.get("total", 0)
        total_attended += att
        total_conducted += tot

        pct = round((att / tot * 100), 1) if tot > 0 else 100.0

        if pct >= 75.0:
            # How many more can be skipped: (att / (tot + x)) >= 0.75  ==> x <= (att - 0.75*tot)/0.75
            safe_bunks = int((att - 0.75 * tot) / 0.75) if tot > 0 else 0
            stats[name] = {
                "attended": att,
                "total": tot,
                "percentage": pct,
                "status": "safe",
                "safe_bunks": max(0, safe_bunks),
                "needed": 0,
            }
        else:
            # How many consecutive classes needed: (att + x)/(tot + x) >= 0.75 ==> 0.25*x >= 0.75*tot - att
            needed = math.ceil((0.75 * tot - att) / 0.25)
            stats[name] = {
                "attended": att,
                "total": tot,
                "percentage": pct,
                "status": "danger",
                "safe_bunks": 0,
                "needed": max(1, needed),
            }

    overall_pct = round((total_attended / total_conducted * 100), 1) if total_conducted > 0 else 100.0
    return {
        "subjects": stats,
        "overall_attended": total_attended,
        "overall_total": total_conducted,
        "overall_pct": overall_pct,
    }


def record_attendance(subject: str, status: str) -> dict:
    """
    Record attendance for a subject ('attended' or 'missed').
    """
    data = _load_data()
    subjects = data.get("subjects", {})

    # Match case-insensitively or create new
    matched_key = None
    for k in subjects:
        if k.lower() == subject.lower() or subject.lower() in k.lower():
            matched_key = k
            break

    if not matched_key:
        matched_key = subject
        subjects[matched_key] = {"attended": 0, "total": 0}

    record = subjects[matched_key]
    record["total"] += 1
    if status == "attended":
        record["attended"] += 1

    tz = ZoneInfo(TIMEZONE)
    now = datetime.now(tz)
    data["history"].append({
        "timestamp": now.isoformat(),
        "date": now.strftime("%Y-%m-%d"),
        "subject": matched_key,
        "status": status,
    })

    _save_data(data)
    logger.info(f"Recorded attendance for '{matched_key}': {status} ({record['attended']}/{record['total']})")
    return subjects[matched_key]


def record_bulk(attended_subjects: list[str], missed_subjects: list[str]) -> None:
    """Record multiple subject attendances at once."""
    for s in attended_subjects:
        record_attendance(s, "attended")
    for s in missed_subjects:
        record_attendance(s, "missed")


def format_attendance_card() -> tuple[str, InlineKeyboardMarkup]:
    """Generate formatted Telegram card with statistics and action buttons."""
    stats = get_attendance_stats()
    subjects = stats["subjects"]

    overall_pct = stats["overall_pct"]
    overall_icon = "🟢" if overall_pct >= 75.0 else "🔴"

    lines = [
        "🎓 **Thapar Attendance & Timetable Safeguard**",
        f"📊 Overall Attendance: {overall_icon} **{overall_pct}%** ({stats['overall_attended']}/{stats['overall_total']})\n",
    ]

    buttons = []
    for name, s in subjects.items():
        icon = "🟢" if s["status"] == "safe" else "🚨"
        lines.append(f"{icon} **{name}**: **{s['percentage']}%** ({s['attended']}/{s['total']})")
        if s["status"] == "safe":
            lines.append(f"   └ 🛡️ Margin: *{s['safe_bunks']} safe bunks remaining*")
        else:
            lines.append(f"   └ ⚠️ Shortage: *Must attend next {s['needed']} classes!*")
        lines.append("")

    lines.append("──────────────────────")
    lines.append("⚡ *One-tap fast actions below:*")

    # Fast check-in buttons
    buttons.append([
        InlineKeyboardButton("✅ Attended All Today", callback_data="att_all_today"),
        InlineKeyboardButton("📝 Mark Missed", callback_data="att_menu_missed"),
    ])

    return "\n".join(lines), InlineKeyboardMarkup(buttons)
