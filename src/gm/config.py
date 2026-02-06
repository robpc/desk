"""Configuration and path management."""

from pathlib import Path

# Config directory
CONFIG_DIR = Path.home() / ".gm"
CREDENTIALS_FILE = CONFIG_DIR / "credentials.json"
TOKEN_FILE = CONFIG_DIR / "token.json"

# Gmail API scopes
SCOPES = [
    "https://www.googleapis.com/auth/gmail.modify",  # Read, send, delete, manage labels
]


def ensure_config_dir() -> Path:
    """Ensure config directory exists and return its path."""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    return CONFIG_DIR
