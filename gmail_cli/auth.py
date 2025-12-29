"""OAuth 2.0 authentication for Gmail API."""

import os
import json
from pathlib import Path
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from .utils import get_token_path, get_credentials_path, ensure_token_permissions


# Gmail API scopes
SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/gmail.modify",
]


def get_credentials(account=None):
    """
    Get valid user credentials from storage or run OAuth flow.
    
    Args:
        account: Account name (optional). If None, uses default account.
    
    Returns:
        Credentials object, or None if authentication failed.
    """
    from .utils import get_token_path
    token_path = get_token_path(account)
    creds = None
    
    # Load existing token if available
    if token_path.exists():
        try:
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
                creds = None
        
        if not creds:
            return None
    
    return creds


def authenticate(account=None):
    """
    Run OAuth 2.0 flow to get user credentials.
    
    Args:
        account: Account name (optional). If provided, saves token for this account.
    
    Returns:
        Credentials object on success, None on failure.
    """
    from .utils import get_credentials_path, get_token_path, set_default_account
    credentials_path = get_credentials_path()
    
    if not credentials_path:
        print("❌ Error: credentials.json not found")
        print("\nPlease download credentials.json from Google Cloud Console:")
        print("1. Go to https://console.cloud.google.com/")
        print("2. Create/select a project")
        print("3. Enable Gmail API")
        print("4. Go to 'Credentials' → 'Create Credentials' → 'OAuth client ID'")
        print("5. Choose 'Desktop app' as application type")
        print("6. Download the JSON file and save it as 'credentials.json'")
        print("7. Place it in the current directory or your home directory")
        return None
    
    try:
        flow = InstalledAppFlow.from_client_secrets_file(
            str(credentials_path), SCOPES
        )
        creds = flow.run_local_server(port=0)
        
        # Get email address to use as account name if not provided
        if not account:
            from googleapiclient.discovery import build
            temp_service = build("gmail", "v1", credentials=creds)
            profile = temp_service.users().getProfile(userId="me").execute()
            account = profile.get("emailAddress", "default")
        
        # Save credentials for next run
        token_path = get_token_path(account)
        with open(token_path, "w") as token_file:
            token_file.write(creds.to_json())
        
        ensure_token_permissions(token_path)
        
        # Set as default account if it's the first one
        set_default_account(account)
        
        print("✅ Authentication successful! Token saved.")
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

