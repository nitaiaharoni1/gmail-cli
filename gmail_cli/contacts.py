"""Local contacts management for Google CLI tools."""

import json
import os
from pathlib import Path
from typing import Dict, List, Optional
from .shared_auth import GOOGLE_CONFIG_DIR


CONTACTS_FILE = GOOGLE_CONFIG_DIR / "contacts.json"


def ensure_contacts_file():
    """Ensure contacts file exists with default structure."""
    GOOGLE_CONFIG_DIR.mkdir(exist_ok=True)
    
    if not CONTACTS_FILE.exists():
        default_data = {
            "contacts": {},
            "groups": []
        }
        with open(CONTACTS_FILE, "w") as f:
            json.dump(default_data, f, indent=2)
        os.chmod(CONTACTS_FILE, 0o600)
    
    return CONTACTS_FILE


def load_contacts() -> Dict:
    """Load contacts from file."""
    ensure_contacts_file()
    
    try:
        with open(CONTACTS_FILE) as f:
            return json.load(f)
    except Exception:
        return {"contacts": {}, "groups": []}


def save_contacts(data: Dict):
    """Save contacts to file."""
    ensure_contacts_file()
    
    with open(CONTACTS_FILE, "w") as f:
        json.dump(data, f, indent=2)
    os.chmod(CONTACTS_FILE, 0o600)


def add_contact(email: str, name: str, description: str = "", groups: List[str] = None) -> bool:
    """Add a contact."""
    if groups is None:
        groups = []
    
    email = email.lower().strip()
    data = load_contacts()
    
    contact = {
        "name": name.strip(),
        "email": email,
        "description": description.strip(),
        "groups": groups
    }
    
    data["contacts"][email] = contact
    
    # Ensure groups exist
    for group in groups:
        if group not in data["groups"]:
            data["groups"].append(group)
    
    save_contacts(data)
    return True


def remove_contact(email: str) -> bool:
    """Remove a contact."""
    email = email.lower().strip()
    data = load_contacts()
    
    if email not in data["contacts"]:
        return False
    
    del data["contacts"][email]
    save_contacts(data)
    return True


def get_contact(email: str) -> Optional[Dict]:
    """Get a single contact by email."""
    email = email.lower().strip()
    data = load_contacts()
    return data["contacts"].get(email)


def list_contacts(group: Optional[str] = None) -> List[Dict]:
    """List all contacts, optionally filtered by group."""
    data = load_contacts()
    contacts = list(data["contacts"].values())
    
    if group:
        contacts = [c for c in contacts if group in c.get("groups", [])]
    
    return sorted(contacts, key=lambda x: x["name"].lower())


def find_contacts(query: str) -> List[Dict]:
    """Search contacts by name, email, or description."""
    query = query.lower().strip()
    data = load_contacts()
    results = []
    
    for contact in data["contacts"].values():
        name_match = query in contact["name"].lower()
        email_match = query in contact["email"].lower()
        desc_match = query in contact.get("description", "").lower()
        
        if name_match or email_match or desc_match:
            results.append(contact)
    
    return sorted(results, key=lambda x: x["name"].lower())


def update_contact(email: str, name: Optional[str] = None, description: Optional[str] = None, 
                  groups: Optional[List[str]] = None) -> bool:
    """Update contact details."""
    email = email.lower().strip()
    data = load_contacts()
    
    if email not in data["contacts"]:
        return False
    
    contact = data["contacts"][email]
    
    if name is not None:
        contact["name"] = name.strip()
    if description is not None:
        contact["description"] = description.strip()
    if groups is not None:
        contact["groups"] = groups
        # Ensure groups exist
        for group in groups:
            if group not in data["groups"]:
                data["groups"].append(group)
    
    save_contacts(data)
    return True


def add_group(name: str) -> bool:
    """Add a new group."""
    name = name.strip()
    data = load_contacts()
    
    if name not in data["groups"]:
        data["groups"].append(name)
        save_contacts(data)
        return True
    return False


def remove_group(name: str) -> bool:
    """Remove a group (contacts keep their groups, but group is removed from list)."""
    name = name.strip()
    data = load_contacts()
    
    if name not in data["groups"]:
        return False
    
    data["groups"].remove(name)
    
    # Remove group from all contacts
    for contact in data["contacts"].values():
        if name in contact.get("groups", []):
            contact["groups"].remove(name)
    
    save_contacts(data)
    return True


def list_groups() -> List[str]:
    """List all groups."""
    data = load_contacts()
    return sorted(data.get("groups", []))


def resolve_contacts(names_or_emails: List[str]) -> List[str]:
    """Resolve contact names or emails to email addresses."""
    data = load_contacts()
    resolved = []
    
    for item in names_or_emails:
        item_lower = item.lower().strip()
        
        # Check if it's already an email
        if "@" in item_lower:
            # Check if it exists in contacts
            if item_lower in data["contacts"]:
                resolved.append(data["contacts"][item_lower]["email"])
            else:
                # Use as-is if not in contacts
                resolved.append(item)
        else:
            # Try to find by name
            found = False
            for contact in data["contacts"].values():
                if contact["name"].lower() == item_lower or item_lower in contact["name"].lower():
                    resolved.append(contact["email"])
                    found = True
                    break
            
            if not found:
                # If not found, use as-is (might be an email without @)
                resolved.append(item)
    
    return resolved

