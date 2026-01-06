"""Utility functions for Gmail CLI."""

import os
import json
from pathlib import Path
from .shared_auth import (
    get_default_account as _get_default_account,
    set_default_account as _set_default_account,
    list_accounts as _list_accounts,
    get_token_path as _get_token_path,
    get_credentials_path as _get_credentials_path,
    ensure_token_permissions as _ensure_token_permissions,
)


def get_default_account():
    """Get the default account name."""
    return _get_default_account("gmail")


def set_default_account(account_name):
    """Set the default account name."""
    _set_default_account(account_name)


def list_accounts():
    """List all configured accounts."""
    return _list_accounts()


def get_token_path(account=None):
    """Get the path to the token file for a specific account."""
    return _get_token_path(account, "gmail")


def get_credentials_path():
    """Get the path to credentials.json file."""
    return _get_credentials_path()


def ensure_token_permissions(token_path):
    """Ensure token file has secure permissions (600)."""
    _ensure_token_permissions(token_path)


def format_email_address(email_dict):
    """Format email address from Gmail API response."""
    if isinstance(email_dict, str):
        return email_dict
    return email_dict.get("emailAddress", "")


def format_date(date_str):
    """Format date string for display."""
    if not date_str:
        return ""
    # Gmail API returns dates in RFC 3339 format
    try:
        from datetime import datetime
        dt = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
        return dt.strftime("%Y-%m-%d %H:%M:%S")
    except:
        return date_str

