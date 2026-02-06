"""OAuth authentication for Gmail API."""

import sys
from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow

from gm.config import CREDENTIALS_FILE, SCOPES, TOKEN_FILE, ensure_config_dir


def get_credentials() -> Credentials | None:
    """Get valid credentials, refreshing if needed.

    Returns None if no valid credentials exist.
    """
    if not TOKEN_FILE.exists():
        return None

    creds = Credentials.from_authorized_user_file(str(TOKEN_FILE), SCOPES)

    if creds.valid:
        return creds

    if creds.expired and creds.refresh_token:
        try:
            creds.refresh(Request())
            _save_credentials(creds)
            return creds
        except Exception:
            # Refresh failed, need to re-authenticate
            return None

    return None


def login(verbose: bool = False) -> Credentials:
    """Run OAuth flow to get new credentials.

    Opens browser for user to authenticate.
    """
    if not CREDENTIALS_FILE.exists():
        print(f"Error: No credentials file found at {CREDENTIALS_FILE}")
        print()
        print("To set up credentials:")
        print("1. Go to https://console.cloud.google.com/")
        print("2. Create a project and enable Gmail API")
        print("3. Create OAuth credentials (Desktop app)")
        print("4. Download and save as ~/.gm/credentials.json")
        sys.exit(1)

    ensure_config_dir()

    if verbose:
        print(f"Using credentials from {CREDENTIALS_FILE}")
        print("Opening browser for authentication...")

    flow = InstalledAppFlow.from_client_secrets_file(str(CREDENTIALS_FILE), SCOPES)
    creds = flow.run_local_server(port=0)

    _save_credentials(creds)

    if verbose:
        print(f"Token saved to {TOKEN_FILE}")

    return creds


def _save_credentials(creds: Credentials) -> None:
    """Save credentials to token file."""
    ensure_config_dir()
    TOKEN_FILE.write_text(creds.to_json())


def get_auth_status() -> dict:
    """Get current authentication status."""
    status = {
        "credentials_file": CREDENTIALS_FILE.exists(),
        "credentials_path": str(CREDENTIALS_FILE),
        "token_file": TOKEN_FILE.exists(),
        "token_path": str(TOKEN_FILE),
        "authenticated": False,
        "email": None,
    }

    creds = get_credentials()
    if creds:
        status["authenticated"] = True
        # Could fetch user email here if needed

    return status
