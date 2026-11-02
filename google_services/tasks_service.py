"""
google_services/tasks_service.py — Google Tasks query, creation, and status management.
"""
from google_services.auth import build_service
from utils.logger import logger
from utils.retry import retry_on_failure


@retry_on_failure(max_retries=3, base_delay=1.5)
def get_task_lists() -> list[dict]:
    """
    Fetch all task lists owned by the user.
    """
    service = build_service("tasks", "v1")
    results = service.tasklists().list(maxResults=50).execute()
    return [{"id": tl["id"], "title": tl["title"]} for tl in results.get("items", [])]


@retry_on_failure(max_retries=3, base_delay=1.5)
def get_pending_tasks(task_list_id: str = "@default") -> list[dict]:
    """
    Fetch all incomplete tasks from the given task list.
    """
    service = build_service("tasks", "v1")
    results = (
        service.tasks()
        .list(
            tasklist=task_list_id,
            showCompleted=False,
            showHidden=False,
            maxResults=100,
        )
        .execute()
    )

    items = results.get("items", [])
    parsed = []
    for t in items:
        parsed.append({
            "id": t.get("id"),
            "title": t.get("title", "(Untitled)"),
            "due": t.get("due"),
            "notes": t.get("notes", ""),
            "status": t.get("status", "needsAction"),
        })

    logger.info(f"Retrieved {len(parsed)} pending tasks.")
    return parsed


@retry_on_failure(max_retries=3, base_delay=1.5)
def create_task(
    title: str,
    notes: str = "",
    due_date: str | None = None,
    task_list_id: str = "@default",
) -> dict:
    """
    Create a new Google Task item.

    Args:
        title: Task title.
        notes: Detailed notes or reminder instructions.
        due_date: RFC 3339 formatted timestamp (e.g. '2026-11-06T23:59:00Z').
        task_list_id: Target task list ID.
    """
    service = build_service("tasks", "v1")
    task_body = {"title": title}
    if notes:
        task_body["notes"] = notes
    if due_date:
        task_body["due"] = due_date

    created = service.tasks().insert(tasklist=task_list_id, body=task_body).execute()
    logger.info(f"✅ Created task: '{title}' (id={created.get('id')})")

    return {
        "id": created["id"],
        "title": created.get("title"),
        "due": created.get("due"),
        "status": created.get("status"),
    }


@retry_on_failure(max_retries=3, base_delay=1.5)
def complete_task(task_id: str, task_list_id: str = "@default") -> None:
    """
    Mark a task as completed.
    """
    service = build_service("tasks", "v1")
    service.tasks().patch(
        tasklist=task_list_id,
        task=task_id,
        body={"status": "completed"},
    ).execute()
    logger.info(f"✅ Marked task {task_id} as completed.")


@retry_on_failure(max_retries=3, base_delay=1.5)
def snooze_task(task_id: str, days_ahead: int = 1, task_list_id: str = "@default") -> str:
    """
    Snooze / defer a task's due date by N days.
    """
    from datetime import datetime, timedelta, timezone
    new_due = (datetime.now(timezone.utc) + timedelta(days=days_ahead)).strftime("%Y-%m-%dT23:59:00.000Z")
    service = build_service("tasks", "v1")
    service.tasks().patch(
        tasklist=task_list_id,
        task=task_id,
        body={"due": new_due},
    ).execute()
    logger.info(f"⏰ Snoozed task {task_id} to {new_due}")
    return new_due[:10]
