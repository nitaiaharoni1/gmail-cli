"""Shared Google authentication utilities for unified account management."""

import os
import json
from pathlib import Path
from datetime import datetime
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow


# Shared config directory structure
GOOGLE_CONFIG_DIR = Path.home() / ".google"
GOOGLE_CONFIG_FILE = GOOGLE_CONFIG_DIR / "config.json"
GOOGLE_CREDENTIALS_FILE = GOOGLE_CONFIG_DIR / "credentials.json"
GOOGLE_TOKENS_DIR = GOOGLE_CONFIG_DIR / "tokens"


def ensure_google_config_dir():
    """Ensure the .google config directory exists."""
    GOOGLE_CONFIG_DIR.mkdir(exist_ok=True)
    GOOGLE_TOKENS_DIR.mkdir(exist_ok=True, mode=0o700)


def get_shared_config():
    """Get shared configuration."""
    ensure_google_config_dir()
    if GOOGLE_CONFIG_FILE.exists():
        try:
            with open(GOOGLE_CONFIG_FILE) as f:
                return json.load(f)
        except:
            pass
    return {}


def save_shared_config(config):
    """Save shared configuration."""
    ensure_google_config_dir()
    with open(GOOGLE_CONFIG_FILE, "w") as f:
        json.dump(config, f, indent=2)
    os.chmod(GOOGLE_CONFIG_FILE, 0o600)


def get_default_account(service_name=None):
    """
    Get the default account name.
    
    Args:
        service_name: Optional service name (e.g., 'gmail', 'calendar')
                     to get service-specific default
    
    Returns:
        Account name or None
    """
    # Check environment variable first
    env_var = os.getenv("GMAIL_ACCOUNT") if service_name == "gmail" else os.getenv("GOOGLE_CALENDAR_ACCOUNT")
    if env_var:
        return env_var
    
    # Check directory-based profile (.google-account file)
    current_dir = Path.cwd()
    for parent in [current_dir] + list(current_dir.parents)[:5]:  # Check up to 5 levels up
        profile_file = parent / ".google-account"
        if profile_file.exists():
            try:
                with open(profile_file) as f:
                    account = f.read().strip()
                    if account:
                        return account
            except:
                pass
    
    # Check shared config
    config = get_shared_config()
    if service_name:
        service_key = f"{service_name}_default_account"
        if service_key in config:
            return config[service_key]
    
    return config.get("default_account")


def set_default_account(account_name, service_name=None):
    """
    Set the default account name.
    
    Args:
        account_name: Account name to set as default
        service_name: Optional service name for service-specific default
    """
    config = get_shared_config()
    
    if service_name:
        service_key = f"{service_name}_default_account"
        config[service_key] = account_name
    
    config["default_account"] = account_name
    
    # Ensure account is in accounts list
    if "accounts" not in config:
        config["accounts"] = []
    if account_name not in config["accounts"]:
        config["accounts"].append(account_name)
    
    save_shared_config(config)


def list_accounts():
    """List all configured accounts."""
    config = get_shared_config()
    return config.get("accounts", [])


def get_token_path(account=None, service_name="gmail"):
    """
    Get the path to the token file for a specific account.
    
    Args:
        account: Account name (optional). If None, uses default account.
        service_name: Service name (e.g., 'gmail', 'calendar')
    
    Returns:
        Path to token file
    """
    if account is None:
        account = get_default_account(service_name)
    
    ensure_google_config_dir()
    
    if account:
        return GOOGLE_TOKENS_DIR / f"{service_name}_{account}.json"
    else:
        # Legacy: default token file
        return Path.home() / f".{service_name}_token.json"


def get_credentials_path():
    """
    Get the path to credentials.json file.
    Checks shared location first, then legacy locations.
    """
    # Check shared location first
    if GOOGLE_CREDENTIALS_FILE.exists():
        return GOOGLE_CREDENTIALS_FILE
    
    # Check current directory
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


def check_token_health(account=None, service_name="gmail", required_scopes=None):
    """
    Check token status and validity.
    
    Args:
        account: Account name (optional)
        service_name: Service name (e.g., 'gmail', 'calendar')
        required_scopes: List of required OAuth scopes
    
    Returns:
        Dict with status information
    """
    token_path = get_token_path(account, service_name)
    
    if not token_path.exists():
        return {
            "status": "missing",
            "message": "No token found",
            "account": account,
            "token_path": str(token_path)
        }
    
    try:
        creds = Credentials.from_authorized_user_file(str(token_path), required_scopes or [])
        
        # Check if scopes match current requirements
        if required_scopes and set(creds.scopes or []) != set(required_scopes):
            return {
                "status": "scope_mismatch",
                "current_scopes": list(creds.scopes or []),
                "required_scopes": required_scopes,
                "message": "Token scopes don't match. Re-auth required.",
                "account": account
            }
        
        # Check expiry
        if creds.expired:
            if creds.refresh_token:
                return {
                    "status": "expired_refreshable",
                    "message": "Token expired but can be refreshed",
                    "account": account
                }
            return {
                "status": "expired",
                "message": "Token expired, re-auth required",
                "account": account
            }
        
        expires_in = None
        if creds.expiry:
            expires_in = int((creds.expiry - datetime.utcnow()).total_seconds())
        
        return {
            "status": "valid",
            "expires_in": expires_in,
            "account": account
        }
    
    except Exception as e:
        return {
            "status": "error",
            "message": f"Error checking token: {e}",
            "account": account
        }


def refresh_token(account=None, service_name="gmail", required_scopes=None):
    """
    Refresh an expired token.
    
    Args:
        account: Account name (optional)
        service_name: Service name (e.g., 'gmail', 'calendar')
        required_scopes: List of required OAuth scopes
    
    Returns:
        Credentials object or None
    """
    token_path = get_token_path(account, service_name)
    
    if not token_path.exists():
        return None
    
    try:
        creds = Credentials.from_authorized_user_file(str(token_path), required_scopes or [])
        
        if creds.expired and creds.refresh_token:
            creds.refresh(Request())
            
            # Save refreshed token
            with open(token_path, "w") as token_file:
                token_file.write(creds.to_json())
            ensure_token_permissions(token_path)
            
            return creds
    
    except Exception as e:
        print(f"Error refreshing token: {e}")
        return None
    
    return None

