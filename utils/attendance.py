"""
utils/attendance.py — Thapar University Attendance Tracker & Safeguard.
Tracks attendance percentages per subject against the 75% minimum threshold.
Calculates safe skips (bunks remaining) or deficit recovery requirements.
Synchronizes dynamically with Google Calendar timetable to reflect today's lectures.
"""
from __future__ import annotations
import os
import json
import math
from datetime import datetime
from pathlib import Path
from typing import Optional
from zoneinfo import ZoneInfo
from telegram import InlineKeyboardMarkup, InlineKeyboardButton
from config import TIMEZONE
from utils.logger import logger

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
ATTENDANCE_FILE = DATA_DIR / "attendance.json"

KNOWN_SEMESTER_SUBJECTS = [
    "Operating Systems",
    "Data Structures And Algorithms",
    "Electronics Devices And Circuits",
    "Discrete Mathematics",
    "Object Oriented Programming Practices",
    "AI For Engineers",
    "Aptitude Skills Building",
]

DEFAULT_SUBJECTS = {
    "Operating Systems": {"attended": 23, "total": 26},
    "Data Structures And Algorithms": {"attended": 31, "total": 35},
    "Electronics Devices And Circuits": {"attended": 24, "total": 28},
    "Discrete Mathematics": {"attended": 22, "total": 25},
    "Object Oriented Programming Practices": {"attended": 25, "total": 28},
    "AI For Engineers": {"attended": 19, "total": 21},
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
            data = json.load(f)
    except Exception as e:
        logger.error(f"Error loading attendance file: {e}")
        data = {"subjects": DEFAULT_SUBJECTS, "history": []}

    # Ensure all semester subjects are populated
    subjects = data.get("subjects", {})
    updated = False
    for subj, default_rec in DEFAULT_SUBJECTS.items():
        if subj not in subjects:
            subjects[subj] = dict(default_rec)
            updated = True

    if updated:
        data["subjects"] = subjects
        _save_data(data)

    return data


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
            # Safe skips formula: (att / (tot + x)) >= 0.75  ==> x <= (att - 0.75*tot)/0.75
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
            # Needed recovery formula: (att + x)/(tot + x) >= 0.75 ==> 0.25*x >= 0.75*tot - att
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


def get_todays_classes() -> list[dict]:
    """
    Fetch today's scheduled university lectures from Google Calendar.
    Strictly filters for verified academic curriculum subjects, ignoring personal events, trains, etc.
    """
    try:
        from google_services.calendar_service import get_todays_events
        events = get_todays_events()
    except Exception as e:
        logger.warning(f"Could not retrieve calendar events for attendance check: {e}")
        return []

    classes: list[dict] = []
    for ev in events:
        summary = ev.get("summary", "").replace(" [Thapar]", "").strip()
        matched_subj: Optional[str] = None

        for subj in KNOWN_SEMESTER_SUBJECTS:
            if subj.lower() in summary.lower() or summary.lower() in subj.lower():
                matched_subj = subj
                break

        if matched_subj:
            start_raw = ev.get("start", "")
            time_str = "Scheduled"
            if "T" in str(start_raw):
                try:
                    dt = datetime.fromisoformat(start_raw)
                    time_str = dt.strftime("%I:%M %p")
                except Exception:
                    pass

            classes.append({
                "subject": matched_subj,
                "summary": summary,
                "time": time_str,
                "start": start_raw,
            })

    return classes


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
    data.setdefault("history", []).append({
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
    """
    Generate formatted Telegram card with current date, today's schedule,
    statistics, and action buttons.
    """
    tz = ZoneInfo(TIMEZONE)
    now = datetime.now(tz)
    date_display = now.strftime("%A, %b %d, %Y")

    stats = get_attendance_stats()
    subjects = stats["subjects"]
    overall_pct = stats["overall_pct"]
    overall_icon = "🟢" if overall_pct >= 75.0 else "🔴"

    todays_classes = get_todays_classes()

    lines = [
        "🎓 **Thapar Academic Attendance & Safeguard**",
        f"📅 *{date_display}*\n",
    ]

    # Display today's academic schedule status
    if todays_classes:
        lines.append(f"📌 **Today's Scheduled Lectures ({len(todays_classes)}):**")
        for cl in todays_classes:
            lines.append(f"   • `{cl['time']}` — **{cl['subject']}**")
        lines.append("")
    else:
        is_weekend = now.weekday() >= 5
        status_note = "Weekend — No university lectures scheduled." if is_weekend else "No university lectures scheduled today."
        lines.append(f"🌴 **Today's Schedule:** {status_note}\n")

    lines.append(f"📊 Overall Attendance: {overall_icon} **{overall_pct}%** ({stats['overall_attended']}/{stats['overall_total']})\n")

    for name, s in subjects.items():
        icon = "🟢" if s["status"] == "safe" else "🚨"
        lines.append(f"{icon} **{name}**: **{s['percentage']}%** ({s['attended']}/{s['total']})")
        if s["status"] == "safe":
            lines.append(f"   └ 🛡️ Margin: *{s['safe_bunks']} safe bunks remaining*")
        else:
            lines.append(f"   └ ⚠️ Shortage: *Must attend next {s['needed']} classes!*")
        lines.append("")

    lines.append("──────────────────────")
    lines.append("⚡ *One-tap actions below:*")

    # Fast check-in buttons tailored to whether lectures were conducted today
    buttons = []
    if todays_classes:
        buttons.append([
            InlineKeyboardButton("✅ Attended Today's Classes", callback_data="att_all_today"),
            InlineKeyboardButton("📝 Mark Missed", callback_data="att_menu_missed"),
        ])
    else:
        buttons.append([
            InlineKeyboardButton("📝 Mark Missed Class", callback_data="att_menu_missed"),
            InlineKeyboardButton("🔄 Refresh", callback_data="att_back"),
        ])

    return "\n".join(lines), InlineKeyboardMarkup(buttons)


def format_attendance_card_text() -> str:
    """Return only the markdown text of the attendance card (for chat router)."""
    text, _ = format_attendance_card()
    return text
