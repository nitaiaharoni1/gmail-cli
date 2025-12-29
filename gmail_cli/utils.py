"""Utility functions for Gmail CLI."""

import os
import json
from pathlib import Path


def get_accounts_config_path():
    """Get the path to accounts configuration file."""
    return Path.home() / ".gmail_accounts.json"


def get_default_account():
    """Get the default account name."""
    config_path = get_accounts_config_path()
    if config_path.exists():
        try:
            with open(config_path) as f:
                config = json.load(f)
                return config.get("default_account")
        except:
            pass
    return None


def set_default_account(account_name):
    """Set the default account name."""
    config_path = get_accounts_config_path()
    config = {}
    if config_path.exists():
        try:
            with open(config_path) as f:
                config = json.load(f)
        except:
            pass
    
    config["default_account"] = account_name
    if "accounts" not in config:
        config["accounts"] = []
    if account_name not in config["accounts"]:
        config["accounts"].append(account_name)
    
    with open(config_path, "w") as f:
        json.dump(config, f, indent=2)
    ensure_token_permissions(config_path)


def list_accounts():
    """List all configured accounts."""
    config_path = get_accounts_config_path()
    if config_path.exists():
        try:
            with open(config_path) as f:
                config = json.load(f)
                return config.get("accounts", [])
        except:
            pass
    return []


def get_token_path(account=None):
    """Get the path to the token file for a specific account."""
    if account is None:
        account = get_default_account()
    
    if account:
        return Path.home() / f".gmail_token_{account}.json"
    else:
        # Legacy: default token file
        return Path.home() / ".gmail_token.json"


def get_credentials_path():
    """Get the path to credentials.json file."""
    # Check current directory first
    current_dir = Path.cwd() / "credentials.json"
    if current_dir.exists():
        return current_dir
    
    # Check home directory
    home_dir = Path.home() / "credentials.json"
    if home_dir.exists():
        return home_dir
    
    return None


def ensure_token_permissions(token_path):
    """Ensure token file has secure permissions (600)."""
    if token_path.exists():
        os.chmod(token_path, 0o600)


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

