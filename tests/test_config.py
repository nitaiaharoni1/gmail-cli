"""Tests for Gmail CLI configuration."""

import pytest
from unittest.mock import patch
from gmail_cli.config import get_preference, set_preference, load_preferences


def test_get_preference_default():
    """Test getting preference with default value."""
    with patch("gmail_cli.config.load_preferences") as mock_load:
        mock_load.return_value = {}
        result = get_preference("nonexistent", "default_value")
        assert result == "default_value"


def test_set_preference():
    """Test setting a preference."""
    with patch("gmail_cli.config.load_preferences") as mock_load, \
         patch("gmail_cli.config.save_preferences") as mock_save:
        mock_load.return_value = {}
        set_preference("test_key", "test_value")
        mock_save.assert_called_once()
        call_args = mock_save.call_args[0][0]
        assert call_args["test_key"] == "test_value"

