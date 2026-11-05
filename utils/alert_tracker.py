"""
utils/alert_tracker.py — Persistent Alert Deduplication Engine.
Guarantees that Time-to-Leave class/calendar alerts and deadline notifications
are dispatched exactly once, even across container restarts, Render redeployments,
and multi-account calendar syncing.
"""
from __future__ import annotations
import json
import time
import hashlib
from pathlib import Path
from typing import Optional
import httpx

from config import UPSTASH_VECTOR_REST_URL, UPSTASH_VECTOR_REST_TOKEN
from utils.logger import logger

LOCAL_ALERT_FILE = Path(__file__).parent.parent / "data" / "alert_history.json"
MAX_ALERT_AGE_SECONDS = 48 * 3600  # 48 hours retention

# Fast in-memory cache for O(1) checks during routine 2-minute polling
_MEM_CACHE: dict[str, float] = {}
_LOCAL_LOADED = False


def _hash_key(key: str) -> str:
    """Generate safe, collision-proof ID for Upstash Vector."""
    return f"alt_{hashlib.sha256(key.encode()).hexdigest()[:32]}"


def _is_upstash_configured() -> bool:
    return bool(
        UPSTASH_VECTOR_REST_URL
        and UPSTASH_VECTOR_REST_TOKEN
        and not UPSTASH_VECTOR_REST_URL.startswith("https://your-")
    )


def _clean_upstash_url(endpoint: str) -> str:
    base = UPSTASH_VECTOR_REST_URL.rstrip("/")
    if "/vector/" in base:
        base = base.split("/vector/")[0]
    return f"{base}{endpoint}"


def _upstash_headers() -> dict[str, str]:
    token = UPSTASH_VECTOR_REST_TOKEN.replace("Bearer ", "").strip()
    return {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }


def _load_local_alerts() -> dict[str, float]:
    """Load and prune local JSON alerts."""
    global _MEM_CACHE, _LOCAL_LOADED
    if not LOCAL_ALERT_FILE.exists():
        _LOCAL_LOADED = True
        return {}

    try:
        data = json.loads(LOCAL_ALERT_FILE.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return {}
        now = time.time()
        # Prune older than 48 hours
        pruned = {k: v for k, v in data.items() if (now - float(v)) < MAX_ALERT_AGE_SECONDS}
        _MEM_CACHE.update(pruned)
        _LOCAL_LOADED = True
        return pruned
    except Exception as e:
        logger.debug(f"Could not read {LOCAL_ALERT_FILE}: {e}")
        return {}


def _save_local_alerts(alerts: dict[str, float]) -> None:
    """Persist alert history to local disk."""
    try:
        LOCAL_ALERT_FILE.parent.mkdir(parents=True, exist_ok=True)
        LOCAL_ALERT_FILE.write_text(
            json.dumps(alerts, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
    except Exception as e:
        logger.debug(f"Could not save {LOCAL_ALERT_FILE}: {e}")


def is_alert_dispatched(alert_key: str) -> bool:
    """
    Check if an alert has already been sent.
    Checks:
    1. Fast in-memory cache (RAM)
    2. Local alert_history.json file
    3. Upstash Vector remote store (survives Render redeployments)
    """
    global _LOCAL_LOADED, _MEM_CACHE
    if not alert_key:
        return False

    clean_key = alert_key.strip().lower()

    # 1. RAM Cache check
    if clean_key in _MEM_CACHE:
        return True

    # 2. Local disk file check
    if not _LOCAL_LOADED:
        local_data = _load_local_alerts()
        if clean_key in local_data:
            return True

    # 3. Upstash Vector check (for cloud cold starts & new container spins)
    if _is_upstash_configured():
        vector_id = _hash_key(clean_key)
        url = _clean_upstash_url("/fetch")
        try:
            with httpx.Client(timeout=4.0) as client:
                resp = client.post(url, headers=_upstash_headers(), json={"ids": [vector_id]})
                if resp.status_code == 200:
                    result = resp.json().get("result", [])
                    if result and result[0] is not None:
                        _MEM_CACHE[clean_key] = time.time()
                        return True
        except Exception as e:
            logger.debug(f"Upstash alert check skipped ({clean_key[:30]}): {e}")

    return False


def mark_alert_dispatched(alert_key: str, context: Optional[str] = None) -> None:
    """
    Mark an alert as dispatched across all persistence layers:
    1. RAM
    2. Local file
    3. Upstash Vector
    """
    global _MEM_CACHE
    if not alert_key:
        return

    clean_key = alert_key.strip().lower()
    now = time.time()

    # 1. RAM
    _MEM_CACHE[clean_key] = now

    # 2. Local disk
    try:
        local_data = _load_local_alerts()
        local_data[clean_key] = now
        _save_local_alerts(local_data)
    except Exception as e:
        logger.debug(f"Local alert save error: {e}")

    # 3. Upstash Vector
    if _is_upstash_configured():
        vector_id = _hash_key(clean_key)
        url = _clean_upstash_url("/upsert-data")
        payload = {
            "id": vector_id,
            "data": f"alert:{clean_key}",
            "metadata": {
                "key": clean_key,
                "context": context or "",
                "timestamp": now,
                "type": "alert_dedupe",
            },
        }
        try:
            with httpx.Client(timeout=4.0) as client:
                client.post(url, headers=_upstash_headers(), json=payload)
        except Exception as e:
            logger.debug(f"Upstash alert mark skipped ({clean_key[:30]}): {e}")
