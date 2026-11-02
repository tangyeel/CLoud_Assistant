"""
google_services/classroom_service.py — Google Classroom courses, assignments, and announcements.
Supports dual accounts (Personal + Thapar University).
"""
from google_services.auth import build_service, has_thapar_account
from config import EXCLUDED_COURSE_IDS
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
def get_coursework(course_id: str, account: str = "default", max_results: int = 10) -> list[dict]:
    """
    Fetch assignments / coursework for a given course on specific account.
    """
    service = build_service("classroom", "v1", account=account)
    results = (
        service.courses()
        .courseWork()
        .list(courseId=course_id, pageSize=max_results, orderBy="dueDate desc")
        .execute()
    )

    items = results.get("courseWork", [])
    parsed = []
    for cw in items:
        due = cw.get("dueDate", {})
        due_time = cw.get("dueTime", {})

        due_str = ""
        if due:
            due_str = f"{due.get('year')}-{due.get('month', 1):02d}-{due.get('day', 1):02d}"
            if due_time:
                due_str += f" {due_time.get('hours', 0):02d}:{due_time.get('minutes', 0):02d}"

        parsed.append({
            "id": cw["id"],
            "title": cw.get("title", "(Untitled)"),
            "description": cw.get("description", ""),
            "due_date": due_str,
            "max_points": cw.get("maxPoints", 0),
            "state": cw.get("state", ""),
            "link": cw.get("alternateLink", ""),
        })

    return parsed


@retry_on_failure(max_retries=3, base_delay=1.5)
def get_all_upcoming_assignments() -> list[dict]:
    """
    Aggregate all upcoming assignments across all active courses (Personal + Thapar).
    """
    courses = get_active_courses()
    all_assignments = []

    for course in courses:
        try:
            acc = course.get("account", "default")
            items = get_coursework(course["id"], account=acc, max_results=5)
            for item in items:
                item["course_name"] = course["name"]
            all_assignments.extend(items)
        except Exception as e:
            logger.warning(f"Could not fetch coursework for course '{course['name']}': {e}")

    # Sort assignments by due date if available
    all_assignments.sort(key=lambda x: x.get("due_date") or "9999-99-99")
    logger.info(f"Retrieved {len(all_assignments)} assignments across courses.")
    return all_assignments
