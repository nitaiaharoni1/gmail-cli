"""Configuration management for Gmail CLI."""

import json
import os
from pathlib import Path
from .shared_auth import GOOGLE_CONFIG_DIR


PREFERENCES_FILE = GOOGLE_CONFIG_DIR / "preferences.json"


def ensure_preferences_file():
    """Ensure preferences file exists with defaults."""
    GOOGLE_CONFIG_DIR.mkdir(exist_ok=True)
    
    if not PREFERENCES_FILE.exists():
        default_prefs = {
            "default_output_format": "table",
            "default_max_results": 10,
            "timezone": "UTC",
            "verbose": False
        }
        # Write directly to avoid recursion
        with open(PREFERENCES_FILE, "w") as f:
            json.dump(default_prefs, f, indent=2)
        os.chmod(PREFERENCES_FILE, 0o600)
    
    return PREFERENCES_FILE


def load_preferences():
    """Load user preferences."""
    ensure_preferences_file()
    
    try:
        with open(PREFERENCES_FILE) as f:
            return json.load(f)
    except:
        # Return defaults if file is corrupted
        return get_default_preferences()


def save_preferences(preferences):
    """Save user preferences."""
    # Ensure directory exists but don't call ensure_preferences_file to avoid recursion
    GOOGLE_CONFIG_DIR.mkdir(exist_ok=True)
    
    with open(PREFERENCES_FILE, "w") as f:
        json.dump(preferences, f, indent=2)
    
    # Ensure secure permissions
    os.chmod(PREFERENCES_FILE, 0o600)


def get_default_preferences():
    """Get default preferences."""
    return {
        "default_output_format": "table",
        "default_max_results": 10,
        "timezone": "UTC",
        "verbose": False
    }


def get_preference(key, default=None):
    """Get a specific preference value."""
    prefs = load_preferences()
    return prefs.get(key, default)


def set_preference(key, value):
    """Set a specific preference value."""
    prefs = load_preferences()
    prefs[key] = value
    save_preferences(prefs)

