"""Configuration and path management."""

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

# Scopes for gcloud ADC (requires cloud-platform)
GCLOUD_SCOPES = [
    *SCOPES,
    "https://www.googleapis.com/auth/cloud-platform",
]


def ensure_config_dir() -> Path:
    """Ensure config directory exists and return its path."""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
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
