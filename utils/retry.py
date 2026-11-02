"""
utils/retry.py — Exponential backoff retry decorators for sync and async operations.
"""
import time
import asyncio
import functools
from utils.logger import logger


def retry_on_failure(
    max_retries: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 60.0,
    exceptions: tuple = (Exception,),
):
    """
    Synchronous decorator that retries a function with exponential backoff.
    """
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            last_exception = None
            for attempt in range(max_retries + 1):
                try:
                    return func(*args, **kwargs)
                except exceptions as e:
                    last_exception = e
                    if attempt == max_retries:
                        logger.error(
                            f"❌ {func.__name__} failed permanently after {max_retries + 1} attempts: {e}"
                        )
                        raise
                    delay = min(base_delay * (2 ** attempt), max_delay)
                    logger.warning(
                        f"⚠️ {func.__name__} attempt {attempt + 1}/{max_retries + 1} failed: {e}. "
                        f"Retrying in {delay:.1f}s..."
                    )
                    time.sleep(delay)
            raise last_exception
        return wrapper
    return decorator


def async_retry_on_failure(
    max_retries: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 60.0,
    exceptions: tuple = (Exception,),
):
    """
    Asynchronous decorator that retries an async coroutine with exponential backoff.
    """
    def decorator(func):
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            last_exception = None
            for attempt in range(max_retries + 1):
                try:
                    return await func(*args, **kwargs)
                except exceptions as e:
                    last_exception = e
                    if attempt == max_retries:
                        logger.error(
                            f"❌ Async {func.__name__} failed permanently after {max_retries + 1} attempts: {e}"
                        )
                        raise
                    delay = min(base_delay * (2 ** attempt), max_delay)
                    logger.warning(
                        f"⚠️ Async {func.__name__} attempt {attempt + 1}/{max_retries + 1} failed: {e}. "
                        f"Retrying in {delay:.1f}s..."
                    )
                    await asyncio.sleep(delay)
            raise last_exception
        return wrapper
    return decorator
