"""Tests for retry logic."""

import pytest
from unittest.mock import MagicMock
from gmail_cli.retry import with_retry, is_retryable_error
from googleapiclient.errors import HttpError


def test_is_retryable_error_500():
    """Test retryable error detection for 500 status."""
    error = HttpError(MagicMock(status=500), b"")
    assert is_retryable_error(error) is True


def test_is_retryable_error_404():
    """Test non-retryable error detection for 404 status."""
    error = HttpError(MagicMock(status=404), b"")
    assert is_retryable_error(error) is False


@with_retry(max_retries=2)
def failing_function():
    """Test function that fails."""
    raise Exception("Test error")


def test_retry_decorator():
    """Test retry decorator."""
    with pytest.raises(Exception):
        failing_function()

