"""Compatibility shim.

Shared Google authentication now lives in the standalone ``google-auth-core``
package, the single source of truth for the ~/.google credential store used by
all Google CLIs and MCP servers. This module re-exports that surface so the rest
of the CLI keeps importing ``from .shared_auth import ...`` unchanged.
"""

from google_auth_core import *  # noqa: F401,F403
from google_auth_core import (  # noqa: F401  explicit names used across the CLI
    ALL_SCOPES,
    GOOGLE_CONFIG_DIR,
    GOOGLE_CONFIG_FILE,
    GOOGLE_CREDENTIALS_FILE,
    GOOGLE_TOKENS_DIR,
    check_token_health,
    ensure_google_config_dir,
    ensure_token_permissions,
    get_account_aliases,
    get_credentials_path,
    get_default_account,
    get_shared_config,
    get_token_path,
    get_unified_token_path,
    list_accounts,
    migrate_tokens_to_unified,
    refresh_token,
    remove_account,
    remove_account_alias,
    resolve_account,
    save_shared_config,
    set_account_alias,
    set_default_account,
)
