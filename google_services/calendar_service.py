"""
google_services/calendar_service.py — Google Calendar query and scheduling integration.
"""
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from google_services.auth import build_service, has_thapar_account
from config import TIMEZONE
from utils.logger import logger
from utils.retry import retry_on_failure


def _get_accounts() -> list[str]:
    accounts = ["default"]
    if has_thapar_account():
        accounts.append("thapar")
    return accounts


@retry_on_failure(max_retries=3, base_delay=1.5)
def get_todays_events() -> list[dict]:
    """
    Fetch all events scheduled for today across connected accounts.
    """
    tz = ZoneInfo(TIMEZONE)
    now = datetime.now(tz)
    start_of_day = now.replace(hour=0, minute=0, second=0, microsecond=0)
    end_of_day = start_of_day + timedelta(days=1)

    all_events = []
    for acc in _get_accounts():
        try:
            service = build_service("calendar", "v3", account=acc)
            events_result = (
                service.events()
                .list(
                    calendarId="primary",
                    timeMin=start_of_day.isoformat(),
                    timeMax=end_of_day.isoformat(),
                    singleEvents=True,
                    orderBy="startTime",
                )
                .execute()
            )
            items = events_result.get("items", [])
            tag = " [Thapar]" if acc == "thapar" else ""
            for event in items:
                start = event["start"].get("dateTime", event["start"].get("date"))
                end = event["end"].get("dateTime", event["end"].get("date"))
                all_events.append({
                    "id": event.get("id"),
                    "account": acc,
                    "summary": f"{event.get('summary', '(No Title)')}{tag}",
                    "start": start,
                    "end": end,
                    "location": event.get("location", ""),
                    "description": event.get("description", ""),
                })
        except Exception as e:
            logger.warning(f"Failed to fetch today's events for account '{acc}': {e}")

    all_events.sort(key=lambda x: str(x.get("start", "")))
    logger.info(f"Retrieved {len(all_events)} events for today.")
    return all_events


@retry_on_failure(max_retries=3, base_delay=1.5)
def get_tomorrows_events() -> list[dict]:
    """
    Fetch all events scheduled specifically for tomorrow across connected accounts.
    """
    tz = ZoneInfo(TIMEZONE)
    now = datetime.now(tz)
    tomorrow = now + timedelta(days=1)
    start_of_tomorrow = tomorrow.replace(hour=0, minute=0, second=0, microsecond=0)
    end_of_tomorrow = start_of_tomorrow + timedelta(days=1)

    all_events = []
    for acc in _get_accounts():
        try:
            service = build_service("calendar", "v3", account=acc)
            events_result = (
                service.events()
                .list(
                    calendarId="primary",
                    timeMin=start_of_tomorrow.isoformat(),
                    timeMax=end_of_tomorrow.isoformat(),
                    singleEvents=True,
                    orderBy="startTime",
                )
                .execute()
            )
            items = events_result.get("items", [])
            tag = " [Thapar]" if acc == "thapar" else ""
            for event in items:
                start = event["start"].get("dateTime", event["start"].get("date"))
                end = event["end"].get("dateTime", event["end"].get("date"))
                all_events.append({
                    "id": event.get("id"),
                    "account": acc,
                    "summary": f"{event.get('summary', '(No Title)')}{tag}",
                    "start": start,
                    "end": end,
                    "location": event.get("location", ""),
                    "description": event.get("description", ""),
                })
        except Exception as e:
            logger.warning(f"Failed to fetch tomorrow's events for account '{acc}': {e}")

    all_events.sort(key=lambda x: str(x.get("start", "")))
    logger.info(f"Retrieved {len(all_events)} events for tomorrow.")
    return all_events


@retry_on_failure(max_retries=3, base_delay=1.5)
def get_upcoming_events(days: int = 7, max_results: int = 20) -> list[dict]:
    """
    Fetch upcoming events for the next N days across connected accounts.
    """
    tz = ZoneInfo(TIMEZONE)
    now = datetime.now(tz)
    future = now + timedelta(days=days)

    all_events = []
    for acc in _get_accounts():
        try:
            service = build_service("calendar", "v3", account=acc)
            events_result = (
                service.events()
                .list(
                    calendarId="primary",
                    timeMin=now.isoformat(),
                    timeMax=future.isoformat(),
                    maxResults=max_results,
                    singleEvents=True,
                    orderBy="startTime",
                )
                .execute()
            )
            items = events_result.get("items", [])
            tag = " [Thapar]" if acc == "thapar" else ""
            for event in items:
                start = event["start"].get("dateTime", event["start"].get("date"))
                end = event["end"].get("dateTime", event["end"].get("date"))
                all_events.append({
                    "id": event.get("id"),
                    "account": acc,
                    "summary": f"{event.get('summary', '(No Title)')}{tag}",
                    "start": start,
                    "end": end,
                    "location": event.get("location", ""),
                    "description": event.get("description", ""),
                })
        except Exception as e:
            logger.warning(f"Failed to fetch upcoming events for account '{acc}': {e}")

    all_events.sort(key=lambda x: str(x.get("start", "")))
    return all_events[:max_results]


def check_event_conflicts(start_iso: str, end_iso: str) -> list[dict]:
    """
    Check if proposed start and end times conflict with any scheduled events on that date.
    """
    try:
        tz = ZoneInfo(TIMEZONE)
        st = datetime.fromisoformat(start_iso)
        if st.tzinfo is None:
            st = st.replace(tzinfo=tz)
        et = datetime.fromisoformat(end_iso)
        if et.tzinfo is None:
            et = et.replace(tzinfo=tz)

        window_start = st.replace(hour=0, minute=0, second=0, microsecond=0)
        window_end = window_start + timedelta(days=1)

        conflicts = []
        for acc in _get_accounts():
            try:
                service = build_service("calendar", "v3", account=acc)
                results = service.events().list(
                    calendarId="primary",
                    timeMin=window_start.isoformat(),
                    timeMax=window_end.isoformat(),
                    singleEvents=True,
                    orderBy="startTime",
                ).execute()

                for ev in results.get("items", []):
                    ev_s_raw = ev["start"].get("dateTime", ev["start"].get("date"))
                    ev_e_raw = ev["end"].get("dateTime", ev["end"].get("date"))
                    if not ev_s_raw or not ev_e_raw:
                        continue

                    try:
                        ev_s = datetime.fromisoformat(ev_s_raw)
                        if ev_s.tzinfo is None:
                            ev_s = ev_s.replace(tzinfo=tz)
                        ev_e = datetime.fromisoformat(ev_e_raw)
                        if ev_e.tzinfo is None:
                            ev_e = ev_e.replace(tzinfo=tz)

                        # Overlap test: (StartA < EndB) and (EndA > StartB)
                        if (st < ev_e) and (et > ev_s):
                            conflicts.append({
                                "summary": ev.get("summary", "(No Title)"),
                                "start": ev_s.strftime("%I:%M %p"),
                                "end": ev_e.strftime("%I:%M %p"),
                                "location": ev.get("location", ""),
                                "account": acc,
                            })
                    except Exception:
                        pass
            except Exception as e:
                logger.warning(f"Conflict check query failed for {acc}: {e}")

        return conflicts
    except Exception as e:
        logger.warning(f"Conflict detection error: {e}")
        return []


def suggest_next_free_slot(date_str: str, duration_minutes: int = 60) -> str:
    """
    Find the next open free slot during daytime (09:00 to 20:00) on the given date.
    """
    try:
        tz = ZoneInfo(TIMEZONE)
        dt = datetime.fromisoformat(date_str) if "T" in date_str else datetime.strptime(date_str, "%Y-%m-%d")
        day_start = dt.replace(hour=9, minute=0, second=0, microsecond=0, tzinfo=tz)
        day_end = dt.replace(hour=20, minute=0, second=0, microsecond=0, tzinfo=tz)

        # Retrieve all events for this day
        events = []
        for acc in _get_accounts():
            try:
                service = build_service("calendar", "v3", account=acc)
                results = service.events().list(
                    calendarId="primary",
                    timeMin=day_start.isoformat(),
                    timeMax=day_end.isoformat(),
                    singleEvents=True,
                    orderBy="startTime",
                ).execute()
                for ev in results.get("items", []):
                    s = ev["start"].get("dateTime", ev["start"].get("date"))
                    e = ev["end"].get("dateTime", ev["end"].get("date"))
                    if s and e:
                        events.append((datetime.fromisoformat(s).astimezone(tz), datetime.fromisoformat(e).astimezone(tz)))
            except Exception:
                pass

        events.sort(key=lambda x: x[0])

        # Step through 30-min intervals to find a slot
        cursor = day_start
        while cursor + timedelta(minutes=duration_minutes) <= day_end:
            slot_end = cursor + timedelta(minutes=duration_minutes)
            has_conflict = False
            for ev_s, ev_e in events:
                if (cursor < ev_e) and (slot_end > ev_s):
                    has_conflict = True
                    cursor = ev_e  # jump to end of conflicting event
                    break
            if not has_conflict:
                return cursor.strftime("%I:%M %p")
            # advance 15 min if not jumped
            cursor += timedelta(minutes=15)

        return "02:00 PM"
    except Exception:
        return "02:00 PM"


@retry_on_failure(max_retries=3, base_delay=1.5)
def create_event(
    summary: str,
    start_datetime: str,
    end_datetime: str,
    description: str = "",
    location: str = "",
    attendees: list[str] | None = None,
) -> dict:
    """
    Create a new calendar event on the primary calendar.

    Args:
        summary: Event title.
        start_datetime: ISO 8601 string (e.g. '2026-11-03T15:00:00').
        end_datetime: ISO 8601 string.
        description: Description text.
        location: Event location or meeting link.
        attendees: List of attendee email addresses.
    """
    service = build_service("calendar", "v3")

    event_body = {
        "summary": summary,
        "location": location,
        "description": description,
        "start": {
            "dateTime": start_datetime,
            "timeZone": TIMEZONE,
        },
        "end": {
            "dateTime": end_datetime,
            "timeZone": TIMEZONE,
        },
    }

    if attendees:
        event_body["attendees"] = [{"email": a.strip()} for a in attendees if a.strip()]

    created = service.events().insert(calendarId="primary", body=event_body).execute()
    logger.info(f"✅ Created calendar event '{summary}' at {start_datetime}")

    return {
        "id": created["id"],
        "summary": created.get("summary"),
        "start": created["start"].get("dateTime", start_datetime),
        "end": created["end"].get("dateTime", end_datetime),
        "link": created.get("htmlLink", ""),
    }
