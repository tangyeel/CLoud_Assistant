"""
google_services/classroom_service.py — Google Classroom courses, assignments, and announcements.
Supports dual accounts (Personal + Thapar University).
"""
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from google_services.auth import build_service, has_thapar_account
from config import EXCLUDED_COURSE_IDS, TIMEZONE
from utils.logger import logger
from utils.retry import retry_on_failure



def _get_accounts() -> list[str]:
    """Return list of accounts to check, prioritizing Thapar for classroom."""
    accounts = []
    if has_thapar_account():
        accounts.append("thapar")
    accounts.append("default")
    return accounts


@retry_on_failure(max_retries=3, base_delay=1.5)
def get_active_courses() -> list[dict]:
    """
    Fetch all active courses across all connected accounts.
    """
    all_courses = []
    seen_ids = set()

    for acc in _get_accounts():
        try:
            service = build_service("classroom", "v1", account=acc)
            results = service.courses().list(courseStates=["ACTIVE"], pageSize=30).execute()
            courses = results.get("courses", [])

            for c in courses:
                if c["id"] in EXCLUDED_COURSE_IDS or c["id"] in seen_ids:
                    continue
                seen_ids.add(c["id"])
                tag = " (Thapar)" if acc == "thapar" else ""
                all_courses.append({
                    "id": c["id"],
                    "name": f"{c.get('name', '(Unnamed Course)')}{tag}",
                    "section": c.get("section", ""),
                    "description": c.get("description", ""),
                    "account": acc,
                })
        except Exception as e:
            logger.warning(f"Could not fetch Classroom courses for account '{acc}': {e}")

    logger.info(f"Retrieved {len(all_courses)} active Classroom courses across accounts.")
    return all_courses


@retry_on_failure(max_retries=3, base_delay=1.5)
def get_coursework(
    course_id: str,
    account: str = "default",
    max_results: int = 20,
    filter_unsubmitted_only: bool = True,
    filter_future_only: bool = True,
) -> list[dict]:
    """
    Fetch assignments / coursework for a given course on specific account.
    By default:
    - Filters out coursework that has already been turned in or returned.
    - Filters out coursework whose due date is in the past or has no due date.
    """
    tz = ZoneInfo(TIMEZONE)
    now = datetime.now(tz)
    service = build_service("classroom", "v1", account=account)

    # 1. Fetch user's student submissions for this course to check turn-in state
    submission_map: dict[str, str] = {}
    try:
        sub_resp = (
            service.courses()
            .courseWork()
            .studentSubmissions()
            .list(courseId=course_id, courseWorkId="-", userId="me")
            .execute()
        )
        for s in sub_resp.get("studentSubmissions", []):
            cw_id = s.get("courseWorkId")
            if cw_id:
                submission_map[cw_id] = s.get("state", "NEW")
    except Exception as e:
        logger.debug(f"Could not fetch student submissions for course {course_id}: {e}")

    # 2. Fetch coursework items
    results = (
        service.courses()
        .courseWork()
        .list(courseId=course_id, pageSize=max_results, orderBy="dueDate desc")
        .execute()
    )

    items = results.get("courseWork", [])
    parsed = []
    for cw in items:
        cw_id = cw["id"]
        sub_state = submission_map.get(cw_id, "NEW")
        is_submitted = sub_state in ("TURNED_IN", "RETURNED")

        # Skip if already submitted
        if filter_unsubmitted_only and is_submitted:
            continue

        due = cw.get("dueDate", {})
        due_time = cw.get("dueTime", {})

        due_str = ""
        due_dt = None
        if due:
            year = due.get("year")
            month = due.get("month", 1)
            day = due.get("day", 1)
            hours = due_time.get("hours", 23) if due_time else 23
            minutes = due_time.get("minutes", 59) if due_time else 59
            
            # Google Classroom due dates are UTC
            try:
                utc_dt = datetime(year, month, day, hours, minutes, tzinfo=timezone.utc)
                due_dt = utc_dt.astimezone(tz)
                due_str = due_dt.strftime("%Y-%m-%d %H:%M")
            except Exception:
                due_str = f"{year}-{month:02d}-{day:02d} {hours:02d}:{minutes:02d}"

        # If user requested only future assignments that can still be submitted:
        if filter_future_only:
            # Skip if no due date (e.g. general course reading/materials)
            if not due_dt:
                continue
            # Skip if due date has already passed
            if due_dt <= now:
                continue

        parsed.append({
            "id": cw_id,
            "title": cw.get("title", "(Untitled)"),
            "description": cw.get("description", ""),
            "due_date": due_str,
            "due_datetime": due_dt.isoformat() if due_dt else None,
            "max_points": cw.get("maxPoints", 0),
            "state": cw.get("state", ""),
            "submission_state": sub_state,
            "is_submitted": is_submitted,
            "link": cw.get("alternateLink", ""),
        })

    return parsed


@retry_on_failure(max_retries=3, base_delay=1.5)
def get_all_upcoming_assignments(
    max_per_course: int = 20,
    filter_unsubmitted_only: bool = True,
    filter_future_only: bool = True,
) -> list[dict]:
    """
    Aggregate actionable assignments across all active courses (Personal + Thapar).
    By default returns only assignments that:
    1. Have not yet been submitted by the student (state != TURNED_IN / RETURNED).
    2. Have an active due date strictly in the future (due > now).
    """
    courses = get_active_courses()
    all_assignments = []

    for course in courses:
        try:
            acc = course.get("account", "default")
            items = get_coursework(
                course["id"],
                account=acc,
                max_results=max_per_course,
                filter_unsubmitted_only=filter_unsubmitted_only,
                filter_future_only=filter_future_only,
            )
            for item in items:
                item["course_name"] = course["name"]
            all_assignments.extend(items)
        except Exception as e:
            logger.warning(f"Could not fetch coursework for course '{course['name']}': {e}")

    # Sort assignments by due date ascending (most urgent first)
    all_assignments.sort(key=lambda x: x.get("due_date") or "9999-99-99")
    logger.info(f"Retrieved {len(all_assignments)} actionable upcoming assignments across courses.")
    return all_assignments

