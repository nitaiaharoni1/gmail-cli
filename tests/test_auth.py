"""Tests for Gmail CLI authentication."""

import pytest
from unittest.mock import patch, MagicMock
from gmail_cli.auth import get_credentials, authenticate, check_auth
from gmail_cli.shared_auth import check_token_health


def test_check_token_health_missing():
    """Test token health check with missing token."""
    health = check_token_health("nonexistent", "gmail", [])
    assert health["status"] == "missing"


def test_get_credentials_no_token():
    """Test getting credentials when no token exists."""
    with patch("gmail_cli.auth.get_token_path") as mock_path:
        mock_path.return_value.exists.return_value = False
        creds = get_credentials()
        assert creds is None


def test_check_auth_not_authenticated():
    """Test check_auth when not authenticated."""
    with patch("gmail_cli.auth.get_credentials", return_value=None):
        result = check_auth()
        assert result is None

