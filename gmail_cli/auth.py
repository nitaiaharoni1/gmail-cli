"""OAuth 2.0 authentication for Gmail API."""

import os
import json
from pathlib import Path
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from .utils import get_token_path, get_credentials_path, ensure_token_permissions
from .shared_auth import (
    check_token_health, refresh_token, ALL_SCOPES, 
    get_unified_token_path, migrate_tokens_to_unified
)


# Gmail API scopes
SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/gmail.modify",
    "https://www.googleapis.com/auth/gmail.settings.basic",  # For filters
]


def get_credentials(account=None):
    """
    Get valid user credentials from storage or run OAuth flow.
    Checks unified token first, then falls back to service-specific token.
    
    Args:
        account: Account name (optional). If None, uses default account.
    
    Returns:
        Credentials object, or None if authentication failed.
    """
    from .utils import get_token_path
    creds = None
    
    # Check for unified token first
    unified_path = get_unified_token_path(account)
    token_path = unified_path if unified_path.exists() else get_token_path(account)
    
    # Check token health first
    health = check_token_health(account, "gmail", SCOPES)
    
    if health["status"] == "scope_mismatch":
        print(f"⚠️  Token scope mismatch for account '{account or 'default'}'. Re-authentication required.")
        print(f"   Current scopes: {health.get('current_scopes', [])}")
        print(f"   Required scopes: {health.get('required_scopes', [])}")
        return None
    
    # Load existing token if available
    if token_path.exists():
        try:
            # For unified tokens, use SCOPES as required scopes (will extract subset)
            # For service-specific tokens, use SCOPES as exact match
            creds = Credentials.from_authorized_user_file(str(token_path), SCOPES)
        except Exception as e:
            print(f"Warning: Could not load existing token: {e}")
            creds = None
    
    # If there are no (valid) credentials available, let the user log in
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
                # Save refreshed token
                with open(token_path, "w") as token_file:
                    token_file.write(creds.to_json())
                ensure_token_permissions(token_path)
            except Exception as e:
                print(f"Error refreshing token: {e}")
                # Try using shared refresh function
                creds = refresh_token(account, "gmail", SCOPES)
                if not creds:
                    return None
        
        if not creds:
            return None
    
    return creds


def authenticate(account=None):
    """
    Run OAuth 2.0 flow to get user credentials.
    Requests all scopes (Gmail + Calendar) and saves to unified token.
    
    Args:
        account: Account name (optional). If provided, saves token for this account.
    
    Returns:
        Credentials object on success, None on failure.
    """
    from .utils import get_credentials_path, set_default_account
    
    # Try to migrate existing tokens first
    if migrate_tokens_to_unified(account):
        print("ℹ️  Migrated existing tokens to unified format.")
    
    credentials_path = get_credentials_path()
    
    if not credentials_path:
        print("❌ Error: credentials.json not found")
        print("\nPlease download credentials.json from Google Cloud Console:")
        print("1. Go to https://console.cloud.google.com/")
        print("2. Create/select a project")
        print("3. Enable Gmail API and Calendar API")
        print("4. Go to 'Credentials' → 'Create Credentials' → 'OAuth client ID'")
        print("5. Choose 'Desktop app' as application type")
        print("6. Download the JSON file and save it as 'credentials.json'")
        print("7. Place it in ~/.google/credentials.json")
        return None
    
    try:
        # Request all scopes for unified authentication
        print("🔐 Authenticating with Gmail + Calendar scopes...")
        flow = InstalledAppFlow.from_client_secrets_file(
            str(credentials_path), ALL_SCOPES
        )
        creds = flow.run_local_server(port=0)
        
        # Get email address to use as account name if not provided
        if not account:
            from googleapiclient.discovery import build
            temp_service = build("gmail", "v1", credentials=creds)
            profile = temp_service.users().getProfile(userId="me").execute()
            account = profile.get("emailAddress", "default")
        
        # Save credentials to unified token file
        unified_token_path = get_unified_token_path(account)
        with open(unified_token_path, "w") as token_file:
            token_file.write(creds.to_json())
        
        ensure_token_permissions(unified_token_path)
        
        # Set as default account if it's the first one
        set_default_account(account)
        
        # Determine which services are enabled based on scopes
        enabled_services = []
        token_scopes = set(creds.scopes or [])
        gmail_scopes = set(SCOPES)
        calendar_scopes = {
            "https://www.googleapis.com/auth/calendar.readonly",
            "https://www.googleapis.com/auth/calendar.events"
        }
        
        if gmail_scopes.issubset(token_scopes):
            enabled_services.append("Gmail")
        if calendar_scopes.issubset(token_scopes):
            enabled_services.append("Calendar")
        
        services_text = ", ".join(enabled_services) if enabled_services else "Gmail"
        
        print(f"✅ Authentication successful! Token saved.")
        print(f"✅ Authenticated as: {account}")
        print(f"✅ Services enabled: {services_text}")
        return creds
    
    except Exception as e:
        print(f"❌ Authentication failed: {e}")
        return None


def check_auth(account=None):
    """Check if user is authenticated, prompt to authenticate if not."""
    creds = get_credentials(account)
    
    if not creds:
        print("⚠️  Not authenticated. Run 'gmail init' to authenticate.")
        return None
    
    return creds

