"""OAuth authentication for Gmail API.

Supports two authentication methods:
1. gcloud Application Default Credentials (ADC) - simplest, requires gcloud
2. User-provided OAuth credentials (credentials.json) - for teams
"""

import subprocess
import sys
from pathlib import Path

from google.auth import default as google_auth_default
from google.auth.exceptions import DefaultCredentialsError
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow

from gm.config import CREDENTIALS_FILE, GCLOUD_SCOPES, SCOPES, TOKEN_FILE, ensure_config_dir


class AuthMethod:
    """Authentication method identifiers."""

    GCLOUD_ADC = "gcloud_adc"
    OAUTH_CLIENT = "oauth_client"
    NONE = "none"


def get_credentials() -> Credentials | None:
    """Get valid credentials using best available method.

    Tries in order:
    1. Existing token.json (from previous OAuth flow)
    2. gcloud Application Default Credentials
    3. Returns None if neither available

    Returns None if no valid credentials exist.
    """
    # First, try existing token from OAuth flow
    creds = _get_oauth_credentials()
    if creds:
        return creds

    # Second, try gcloud ADC
    creds = _get_adc_credentials()
    if creds:
        return creds

    return None


def _get_oauth_credentials() -> Credentials | None:
    """Get credentials from token.json (previous OAuth flow)."""
    if not TOKEN_FILE.exists():
        return None

    try:
        creds = Credentials.from_authorized_user_file(str(TOKEN_FILE), SCOPES)
    except Exception:
        return None

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


def _get_adc_credentials() -> Credentials | None:
    """Get credentials from gcloud Application Default Credentials."""
    try:
        creds, project = google_auth_default(scopes=SCOPES)
        # ADC credentials auto-refresh, but let's ensure they're valid
        if hasattr(creds, "refresh") and not creds.valid:
            creds.refresh(Request())
        return creds
    except DefaultCredentialsError:
        return None
    except Exception:
        return None


def login(verbose: bool = False) -> Credentials:
    """Run OAuth flow to get new credentials.

    Opens browser for user to authenticate.
    Requires credentials.json to be present.
    """
    if not CREDENTIALS_FILE.exists():
        print(f"Error: No credentials file found at {CREDENTIALS_FILE}")
        print()
        print("Options:")
        print()
        print("  Option 1 - Use gcloud (simplest):")
        print("    gcloud auth application-default login \\")
        print(f'      --scopes={",".join(SCOPES)}')
        print()
        print("  Option 2 - Use team credentials:")
        print("    1. Get credentials.json from your team's 1Password vault")
        print(f"    2. Copy to {CREDENTIALS_FILE}")
        print("    3. Run: gm auth login")
        print()
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


def login_with_gcloud(verbose: bool = False) -> Credentials | None:
    """Authenticate using gcloud application-default login.

    Returns credentials if successful, None if gcloud not available.
    """
    # Check if gcloud is available
    if not _gcloud_available():
        if verbose:
            print("gcloud CLI not found")
        return None

    if verbose:
        print("Running gcloud auth application-default login...")

    scopes_arg = ",".join(GCLOUD_SCOPES)
    result = subprocess.run(
        [
            "gcloud",
            "auth",
            "application-default",
            "login",
            f"--scopes={scopes_arg}",
        ],
        capture_output=False,  # Let user see the browser prompt
    )

    if result.returncode != 0:
        if verbose:
            print("gcloud authentication failed")
        return None

    # Now try to get the credentials
    return _get_adc_credentials()


def _gcloud_available() -> bool:
    """Check if gcloud CLI is available."""
    try:
        result = subprocess.run(
            ["gcloud", "--version"],
            capture_output=True,
            timeout=5,
        )
        return result.returncode == 0
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return False


def _save_credentials(creds: Credentials) -> None:
    """Save credentials to token file."""
    ensure_config_dir()
    TOKEN_FILE.write_text(creds.to_json())


def get_auth_status() -> dict:
    """Get current authentication status."""
    gcloud_available = _gcloud_available()

    status = {
        "method": AuthMethod.NONE,
        "authenticated": False,
        "gcloud_available": gcloud_available,
        "credentials_file": CREDENTIALS_FILE.exists(),
        "credentials_path": str(CREDENTIALS_FILE),
        "token_file": TOKEN_FILE.exists(),
        "token_path": str(TOKEN_FILE),
        "email": None,
    }

    # Check OAuth token first
    creds = _get_oauth_credentials()
    if creds:
        status["authenticated"] = True
        status["method"] = AuthMethod.OAUTH_CLIENT
        return status

    # Check gcloud ADC
    creds = _get_adc_credentials()
    if creds:
        status["authenticated"] = True
        status["method"] = AuthMethod.GCLOUD_ADC
        return status

    return status
