"""
utils/logger.py — Centralized logging using loguru with fallbacks.
"""
import sys
import os
from loguru import logger
from config import LOG_FILE, LOG_LEVEL

# Remove default logger configuration
logger.remove()

# Add standard console handler (stdout)
logger.add(
    sys.stdout,
    format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>",
    level=LOG_LEVEL,
    colorize=True,
)

# File handler (with rotation and retention)
try:
    os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)
    logger.add(
        LOG_FILE,
        rotation="10 MB",
        retention="7 days",
        compression="zip",
        format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} - {message}",
        level="DEBUG",
        enqueue=True,
        encoding="utf-8",
    )
except Exception as e:
    print(f"⚠️ Warning: Could not configure file logging: {e}")

__all__ = ["logger"]
