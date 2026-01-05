"""Operation history tracking for Gmail CLI."""

import json
import os
from pathlib import Path
from datetime import datetime
from .shared_auth import GOOGLE_CONFIG_DIR


HISTORY_FILE = GOOGLE_CONFIG_DIR / "history.json"
MAX_HISTORY_ENTRIES = 100


def ensure_history_file():
    """Ensure history file exists."""
    GOOGLE_CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    
    if not HISTORY_FILE.exists():
        with open(HISTORY_FILE, "w") as f:
            json.dump({"operations": []}, f, indent=2)
        os.chmod(HISTORY_FILE, 0o600)
    
    return HISTORY_FILE


def add_operation(operation_type, details, undoable=True, undo_func=None):
    """
    Add an operation to history.
    
    Args:
        operation_type: Type of operation (e.g., 'send', 'delete', 'trash')
        details: Dict with operation details
        undoable: Whether this operation can be undone
        undo_func: Function name/identifier for undo (if undoable)
    """
    ensure_history_file()
    
    with open(HISTORY_FILE) as f:
        history = json.load(f)
    
    operation = {
        "timestamp": datetime.utcnow().isoformat(),
        "type": operation_type,
        "details": details,
        "undoable": undoable,
        "undo_func": undo_func
    }
    
    history["operations"].append(operation)
    
    # Keep only last MAX_HISTORY_ENTRIES
    if len(history["operations"]) > MAX_HISTORY_ENTRIES:
        history["operations"] = history["operations"][-MAX_HISTORY_ENTRIES:]
    
    with open(HISTORY_FILE, "w") as f:
        json.dump(history, f, indent=2)
    
    os.chmod(HISTORY_FILE, 0o600)


def get_recent_operations(limit=10):
    """Get recent operations from history."""
    ensure_history_file()
    
    with open(HISTORY_FILE) as f:
        history = json.load(f)
    
    operations = history.get("operations", [])
    return operations[-limit:]


def get_last_undoable_operation():
    """Get the last undoable operation."""
    ensure_history_file()
    
    with open(HISTORY_FILE) as f:
        history = json.load(f)
    
    operations = history.get("operations", [])
    
    # Find last undoable operation
    for operation in reversed(operations):
        if operation.get("undoable"):
            return operation
    
    return None

