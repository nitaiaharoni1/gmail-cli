"""Email templates management for Gmail CLI."""

import json
import os
from pathlib import Path
from .shared_auth import GOOGLE_CONFIG_DIR


TEMPLATES_DIR = GOOGLE_CONFIG_DIR / "templates"


def ensure_templates_dir():
    """Ensure templates directory exists."""
    TEMPLATES_DIR.mkdir(parents=True, exist_ok=True)
    return TEMPLATES_DIR


def list_templates():
    """List all available email templates."""
    ensure_templates_dir()
    templates = []
    
    for template_file in TEMPLATES_DIR.glob("*.json"):
        try:
            with open(template_file) as f:
                template = json.load(f)
                template["name"] = template_file.stem
                templates.append(template)
        except:
            continue
    
    return templates


def get_template(name):
    """Get a template by name."""
    ensure_templates_dir()
    template_path = TEMPLATES_DIR / f"{name}.json"
    
    if not template_path.exists():
        return None
    
    try:
        with open(template_path) as f:
            return json.load(f)
    except:
        return None


def create_template(name, to=None, subject=None, body=None, cc=None):
    """Create or update an email template."""
    ensure_templates_dir()
    
    template = {
        "to": to or "",
        "subject": subject or "",
        "body": body or "",
        "cc": cc or ""
    }
    
    template_path = TEMPLATES_DIR / f"{name}.json"
    with open(template_path, "w") as f:
        json.dump(template, f, indent=2)
    
    # Ensure secure permissions
    os.chmod(template_path, 0o600)
    
    return template


def delete_template(name):
    """Delete a template."""
    ensure_templates_dir()
    template_path = TEMPLATES_DIR / f"{name}.json"
    
    if template_path.exists():
        template_path.unlink()
        return True
    
    return False


def render_template(name, **kwargs):
    """Render a template with variable substitution."""
    template = get_template(name)
    if not template:
        raise ValueError(f"Template '{name}' not found")
    
    rendered = {}
    for key, value in template.items():
        if isinstance(value, str):
            # Simple variable substitution: {{var_name}}
            rendered_value = value
            for var_name, var_value in kwargs.items():
                rendered_value = rendered_value.replace(f"{{{{{var_name}}}}}}}", str(var_value))
            rendered[key] = rendered_value
        else:
            rendered[key] = value
    
    return rendered

