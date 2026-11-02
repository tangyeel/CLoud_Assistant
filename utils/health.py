"""
utils/health.py — Health check endpoint for uptime monitoring and keep-alive pings.
"""
from starlette.requests import Request
from starlette.responses import JSONResponse
from datetime import datetime
from zoneinfo import ZoneInfo
from config import TIMEZONE

# Track server launch timestamp
try:
    _start_time = datetime.now(ZoneInfo(TIMEZONE))
except Exception:
    _start_time = datetime.utcnow()


async def health_check(request: Request) -> JSONResponse:
    """
    HTTP GET /health
    Returns 200 OK with server health, current timestamp, and uptime.
    Used by UptimeRobot / cron-job.org / Render keep-alive pings.
    """
    try:
        now = datetime.now(ZoneInfo(TIMEZONE))
    except Exception:
        now = datetime.utcnow()

    uptime = now - _start_time

    return JSONResponse(
        {
            "status": "healthy",
            "timestamp": now.isoformat(),
            "uptime_seconds": int(uptime.total_seconds()),
            "uptime_human": str(uptime).split(".")[0],
        },
        status_code=200,
    )
