"""Retry logic with exponential backoff for API calls."""

import time
import logging
from functools import wraps
from googleapiclient.errors import HttpError


logger = logging.getLogger(__name__)


# HTTP status codes that should trigger retry
RETRYABLE_STATUS_CODES = {500, 502, 503, 504}
MAX_RETRIES = 3
BACKOFF_FACTOR = 2
INITIAL_DELAY = 1  # seconds


def is_retryable_error(error):
    """Check if an error is retryable."""
    if isinstance(error, HttpError):
        return error.resp.status in RETRYABLE_STATUS_CODES
    # For other exceptions, check if they're transient network errors
    error_str = str(error).lower()
    transient_keywords = ["timeout", "connection", "network", "temporary", "retry"]
    return any(keyword in error_str for keyword in transient_keywords)


def with_retry(max_retries=MAX_RETRIES, backoff_factor=BACKOFF_FACTOR, initial_delay=INITIAL_DELAY):
    """
    Decorator to retry a function with exponential backoff.
    
    Args:
        max_retries: Maximum number of retry attempts
        backoff_factor: Multiplier for delay between retries
        initial_delay: Initial delay in seconds before first retry
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            last_exception = None
            
            for attempt in range(max_retries + 1):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    last_exception = e
                    
                    # Don't retry on last attempt
                    if attempt == max_retries:
                        break
                    
                    # Only retry if error is retryable
                    if not is_retryable_error(e):
                        raise
                    
                    # Calculate delay with exponential backoff
                    delay = initial_delay * (backoff_factor ** attempt)
                    
                    logger.warning(
                        f"Attempt {attempt + 1}/{max_retries + 1} failed: {e}. "
                        f"Retrying in {delay}s..."
                    )
                    
                    time.sleep(delay)
            
            # If we get here, all retries failed
            logger.error(f"All {max_retries + 1} attempts failed. Last error: {last_exception}")
            raise last_exception
        
        return wrapper
    return decorator

