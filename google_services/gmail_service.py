"""
google_services/gmail_service.py — Gmail integration for reading, smart filtering, and summarization.
"""
import base64
from datetime import datetime, timedelta, timezone
from google_services.auth import build_service, has_thapar_account
from utils.logger import logger
from utils.retry import retry_on_failure


def _fetch_unread_from_account(
    account: str,
    max_results: int,
    hours_back: int,
    skip_categories: list[str],
) -> list[dict]:
    service = build_service("gmail", "v1", account=account)

    cutoff_dt = datetime.now(timezone.utc) - timedelta(hours=hours_back)
    after_epoch = int(cutoff_dt.timestamp())
    query_parts = ["is:unread", f"after:{after_epoch}"]

    for cat in skip_categories:
        query_parts.append(f"-category:{cat}")

    query = " ".join(query_parts)
    logger.debug(f"Querying Gmail ({account}): {query}")

    try:
        results = (
            service.users()
            .messages()
            .list(userId="me", q=query, maxResults=max_results)
            .execute()
        )
    except Exception as e:
        logger.error(f"Gmail list request failed for account '{account}': {e}")
        return []

    messages = results.get("messages", [])
    if not messages:
        return []

    emails = []
    prefix = "[Thapar] " if account == "thapar" else ""
    for msg_ref in messages:
        try:
            msg = (
                service.users()
                .messages()
                .get(
                    userId="me",
                    id=msg_ref["id"],
                    format="metadata",
                    metadataHeaders=["Subject", "From", "Date"],
                )
                .execute()
            )

            headers = {h["name"]: h["value"] for h in msg.get("payload", {}).get("headers", [])}
            emails.append({
                "id": msg["id"],
                "account": account,
                "subject": f"{prefix}{headers.get('Subject', '(No Subject)')}",
                "sender": headers.get("From", "(Unknown Sender)"),
                "snippet": msg.get("snippet", ""),
                "date": headers.get("Date", ""),
                "labels": msg.get("labelIds", []),
            })
        except Exception as e:
            logger.warning(f"Failed to fetch metadata for email {msg_ref['id']}: {e}")

    return emails


@retry_on_failure(max_retries=3, base_delay=1.5)
def get_unread_emails(
    max_results: int = 15,
    hours_back: int = 12,
    skip_categories: list[str] | None = None,
) -> list[dict]:
    """
    Fetch unread emails from the past N hours across connected accounts (Personal + Thapar).
    """
    if skip_categories is None:
        skip_categories = ["promotions", "social", "forums"]

    accounts = ["default"]
    if has_thapar_account():
        accounts.append("thapar")

    all_emails = []
    per_acc_limit = max_results if len(accounts) == 1 else (max_results // len(accounts)) + 2

    for acc in accounts:
        try:
            emails = _fetch_unread_from_account(acc, per_acc_limit, hours_back, skip_categories)
            all_emails.extend(emails)
        except Exception as e:
            logger.warning(f"Failed to fetch emails for account '{acc}': {e}")

    logger.info(f"Retrieved {len(all_emails)} unread emails across {accounts}.")
    return all_emails[:max_results]


@retry_on_failure(max_retries=3, base_delay=1.5)
def get_email_body(message_id: str, account: str = "default") -> str:
    """
    Fetch the decoded plain-text content of a specific email across accounts.
    """
    service = build_service("gmail", "v1", account=account)
    msg = service.users().messages().get(userId="me", id=message_id, format="full").execute()
    payload = msg.get("payload", {})
    return _extract_plain_text(payload)


def _extract_plain_text(payload: dict) -> str:
    """Recursively search for text/plain mime data."""
    if payload.get("mimeType") == "text/plain":
        data = payload.get("body", {}).get("data", "")
        if data:
            return base64.urlsafe_b64decode(data).decode("utf-8", errors="replace")

    for part in payload.get("parts", []):
        text = _extract_plain_text(part)
        if text:
            return text

    return ""


@retry_on_failure(max_retries=3, base_delay=1.5)
def mark_as_read(message_id: str, account: str = "default") -> None:
    """
    Remove the UNREAD label from a message across accounts.
    """
    service = build_service("gmail", "v1", account=account)
    service.users().messages().modify(
        userId="me",
        id=message_id,
        body={"removeLabelIds": ["UNREAD"]},
    ).execute()
    logger.debug(f"Marked email {message_id} ({account}) as read.")
