"""Shared Google authentication utilities for unified account management."""

import os
import json
from pathlib import Path
from datetime import datetime
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials


# Shared config directory structure
GOOGLE_CONFIG_DIR = Path.home() / ".google"
GOOGLE_CONFIG_FILE = GOOGLE_CONFIG_DIR / "config.json"
GOOGLE_CREDENTIALS_FILE = GOOGLE_CONFIG_DIR / "credentials.json"
GOOGLE_TOKENS_DIR = GOOGLE_CONFIG_DIR / "tokens"

# All Google CLI scopes (Gmail + Calendar + People) for unified authentication
ALL_SCOPES = [
    # Gmail scopes
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/gmail.modify",
    "https://www.googleapis.com/auth/gmail.settings.basic",
    # Calendar scopes
    "https://www.googleapis.com/auth/calendar.readonly",
    "https://www.googleapis.com/auth/calendar.events",
    # People API scope (for contacts)
    "https://www.googleapis.com/auth/contacts.readonly",
]


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
    Uses unified global default account for both Gmail and Calendar.
    
    Args:
        service_name: Optional service name (e.g., 'gmail', 'calendar')
                     Used only for environment variable lookup
    
    Returns:
        Account name or None
    """
    # Check environment variable first (service-specific override)
    if service_name == "gmail":
        env_var = os.getenv("GMAIL_ACCOUNT")
    elif service_name == "calendar":
        env_var = os.getenv("GOOGLE_CALENDAR_ACCOUNT")
    else:
        env_var = None
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
    
    # Use unified global default account (ignores service-specific defaults)
    config = get_shared_config()
    return config.get("default_account")


def set_default_account(account_name):
    """
    Set the unified default account name for both Gmail and Calendar.
    
    Args:
        account_name: Account name to set as default
    """
    config = get_shared_config()
    
    # Set unified global default account
    config["default_account"] = account_name
    
    # Remove any service-specific defaults (cleanup from old configs)
    if "gmail_default_account" in config:
        del config["gmail_default_account"]
    if "calendar_default_account" in config:
        del config["calendar_default_account"]
    
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


def get_unified_token_path(account=None):
    """
    Get the path to the unified token file for a specific account.
    Unified tokens contain all scopes (Gmail + Calendar).
    
    Args:
        account: Account name (optional). If None, uses default account.
    
    Returns:
        Path to unified token file
    """
    if account is None:
        account = get_default_account()
    
    ensure_google_config_dir()
    
    if account:
        return GOOGLE_TOKENS_DIR / f"google_{account}.json"
    else:
        return GOOGLE_TOKENS_DIR / "google_default.json"


def get_token_path(account=None, service_name="gmail"):
    """
    Get the path to the token file for a specific account.
    Checks for unified token first, then falls back to service-specific token.
    
    Args:
        account: Account name (optional). If None, uses default account.
        service_name: Service name (e.g., 'gmail', 'calendar')
    
    Returns:
        Path to token file (unified or service-specific)
    """
    if account is None:
        account = get_default_account(service_name)
    
    ensure_google_config_dir()
    
    # Check for unified token first
    unified_path = get_unified_token_path(account)
    if unified_path.exists():
        return unified_path
    
    # Fall back to service-specific token
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
    Checks unified token first, then service-specific token.
    
    Args:
        account: Account name (optional)
        service_name: Service name (e.g., 'gmail', 'calendar')
        required_scopes: List of required OAuth scopes
    
    Returns:
        Dict with status information
    """
    # Check unified token first
    unified_path = get_unified_token_path(account)
    token_path = unified_path if unified_path.exists() else get_token_path(account, service_name)
    
    if not token_path.exists():
        return {
            "status": "missing",
            "message": "No token found",
            "account": account,
            "token_path": str(token_path)
        }
    
    try:
        creds = Credentials.from_authorized_user_file(str(token_path), required_scopes or [])
        
        # For unified tokens, check if required scopes are subset of token scopes
        # For service-specific tokens, check exact match
        is_unified = unified_path.exists() and token_path == unified_path
        if required_scopes:
            if is_unified:
                # Unified token should contain all required scopes
                token_scopes = set(creds.scopes or [])
                required_set = set(required_scopes)
                if not required_set.issubset(token_scopes):
                    return {
                        "status": "scope_mismatch",
                        "current_scopes": list(creds.scopes or []),
                        "required_scopes": required_scopes,
                        "message": "Token scopes don't match. Re-auth required.",
                        "account": account
                    }
            else:
                # Service-specific token must match exactly
                if set(creds.scopes or []) != set(required_scopes):
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
            "account": account,
            "is_unified": is_unified
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
    Checks unified token first, then service-specific token.
    
    Args:
        account: Account name (optional)
        service_name: Service name (e.g., 'gmail', 'calendar')
        required_scopes: List of required OAuth scopes
    
    Returns:
        Credentials object or None
    """
    # Check unified token first
    unified_path = get_unified_token_path(account)
    token_path = unified_path if unified_path.exists() else get_token_path(account, service_name)
    
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


def migrate_tokens_to_unified(account=None):
    """
    Migrate existing service-specific tokens to unified token format.
    Combines Gmail and Calendar tokens into a single unified token.
    
    Args:
        account: Account name (optional). If None, uses default account.
    
    Returns:
        True if migration successful, False otherwise
    """
    if account is None:
        account = get_default_account()
    
    if not account:
        return False
    
    ensure_google_config_dir()
    
    gmail_token_path = GOOGLE_TOKENS_DIR / f"gmail_{account}.json"
    calendar_token_path = GOOGLE_TOKENS_DIR / f"calendar_{account}.json"
    unified_token_path = get_unified_token_path(account)
    
    # If unified token already exists, skip migration
    if unified_token_path.exists():
        return True
    
    # Try to load and merge tokens
    gmail_creds = None
    calendar_creds = None
    
    if gmail_token_path.exists():
        try:
            gmail_creds = Credentials.from_authorized_user_file(str(gmail_token_path), [])
        except:
            pass
    
    if calendar_token_path.exists():
        try:
            calendar_creds = Credentials.from_authorized_user_file(str(calendar_token_path), [])
        except:
            pass
    
    # Prefer the token with more scopes or refresh token
    unified_creds = None
    if gmail_creds and calendar_creds:
        # Merge: use Gmail token as base (usually has more scopes)
        unified_creds = gmail_creds
        # Ensure all scopes are included
        all_scopes = set((gmail_creds.scopes or []) + (calendar_creds.scopes or []))
        unified_creds = Credentials(
            token=unified_creds.token,
            refresh_token=unified_creds.refresh_token or calendar_creds.refresh_token,
            token_uri=unified_creds.token_uri,
            client_id=unified_creds.client_id,
            client_secret=unified_creds.client_secret,
            scopes=list(all_scopes)
        )
    elif gmail_creds:
        unified_creds = gmail_creds
    elif calendar_creds:
        unified_creds = calendar_creds
    
    if unified_creds:
        # Save unified token
        with open(unified_token_path, "w") as token_file:
            token_file.write(unified_creds.to_json())
        ensure_token_permissions(unified_token_path)
        
        return True
    
    return False

