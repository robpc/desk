"""Configuration and path management."""

import os
from pathlib import Path

# Config directory
CONFIG_DIR = Path.home() / ".desk"
CREDENTIALS_FILE = CONFIG_DIR / "credentials.json"
TOKEN_FILE = CONFIG_DIR / "token.json"

# Legacy config (for migration)
LEGACY_CONFIG_DIR = Path.home() / ".gmail-cli"

# Google Workspace API scopes
SCOPES = [
    "https://www.googleapis.com/auth/gmail.modify",
    "https://www.googleapis.com/auth/gmail.settings.basic",  # For filters and vacation
    "https://www.googleapis.com/auth/drive",
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/documents",
    "https://www.googleapis.com/auth/calendar",
    "https://www.googleapis.com/auth/forms.body",
    "https://www.googleapis.com/auth/forms.responses.readonly",
]

# Scopes for gcloud ADC
GCLOUD_SCOPES = [
    *SCOPES,
]


def ensure_config_dir() -> Path:
    """Ensure config directory exists with restricted permissions and return its path."""
    CONFIG_DIR.mkdir(parents=True, mode=0o700, exist_ok=True)
    os.chmod(CONFIG_DIR, 0o700)  # fix pre-existing directories
    return CONFIG_DIR


def migrate_legacy_config() -> bool:
    """Migrate ~/.gmail-cli/ to ~/.desk/ if legacy config exists.

    Returns True if migration happened.
    """
    if not LEGACY_CONFIG_DIR.exists():
        return False
    if CONFIG_DIR.exists():
        return False

    import shutil

    shutil.copytree(LEGACY_CONFIG_DIR, CONFIG_DIR)
    return True
