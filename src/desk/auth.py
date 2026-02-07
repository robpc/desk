"""OAuth authentication for Google Workspace APIs.

Supports two authentication methods:
1. gcloud Application Default Credentials (ADC) - simplest, requires gcloud
2. User-provided OAuth credentials (credentials.json) - for teams
"""

import logging
import os
import subprocess
import sys

from google.auth import default as google_auth_default
from google.auth.exceptions import DefaultCredentialsError, RefreshError, TransportError
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow

from desk.config import CREDENTIALS_FILE, GCLOUD_SCOPES, SCOPES, TOKEN_FILE, ensure_config_dir

# Debug logging - enable with DESK_DEBUG=1
_logger = logging.getLogger("desk.auth")
if os.environ.get("DESK_DEBUG"):
    logging.basicConfig(level=logging.DEBUG)
    _logger.setLevel(logging.DEBUG)


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
    except (ValueError, KeyError) as e:
        _logger.debug(f"Failed to parse token file: {e}")
        return None
    except Exception as e:
        _logger.debug(f"Unexpected error loading token file: {type(e).__name__}: {e}")
        return None

    if creds.valid:
        return creds

    if creds.expired and creds.refresh_token:
        try:
            creds.refresh(Request())
            _save_credentials(creds)
            return creds
        except (RefreshError, TransportError) as e:
            _logger.debug(f"Token refresh failed: {e}")
            return None
        except Exception as e:
            _logger.debug(f"Unexpected error refreshing token: {type(e).__name__}: {e}")
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
        _logger.debug("No Application Default Credentials found")
        return None
    except (RefreshError, TransportError) as e:
        _logger.debug(f"ADC refresh failed: {e}")
        return None
    except Exception as e:
        _logger.debug(f"Unexpected error with ADC: {type(e).__name__}: {e}")
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
        print("    desk auth login --gcloud")
        print()
        print("  Option 2 - Use team credentials:")
        print("    1. Get credentials.json from your team's 1Password vault")
        print(f"    2. Copy to {CREDENTIALS_FILE}")
        print("    3. Run: desk auth login")
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
    os.chmod(TOKEN_FILE, 0o600)


def get_auth_status(verify: bool = False) -> dict:
    """Get current authentication status.

    Args:
        verify: If True, test actual API access for each service (slower but accurate)
    """
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
        "services": None,  # Populated if verify=True
    }

    # Check OAuth token first
    creds = _get_oauth_credentials()
    if creds:
        status["authenticated"] = True
        status["method"] = AuthMethod.OAUTH_CLIENT
        if verify:
            status["services"] = verify_service_access(creds)
        return status

    # Check gcloud ADC
    creds = _get_adc_credentials()
    if creds:
        status["authenticated"] = True
        status["method"] = AuthMethod.GCLOUD_ADC
        if verify:
            status["services"] = verify_service_access(creds)
        return status

    return status


def verify_service_access(credentials: Credentials) -> dict[str, bool]:
    """Test actual API access for each service.

    Makes lightweight API calls to verify the credentials have the necessary scopes.

    Returns:
        Dict mapping service name to access status (True = working, False = no access)
    """
    from googleapiclient.discovery import build
    from googleapiclient.errors import HttpError

    results = {}

    # Gmail - try to get labels (lightweight)
    try:
        service = build("gmail", "v1", credentials=credentials)
        service.users().labels().list(userId="me").execute()
        results["mail"] = True
    except HttpError as e:
        _logger.debug(f"Gmail access check failed: {e}")
        results["mail"] = False
    except Exception as e:
        _logger.debug(f"Gmail access check error: {type(e).__name__}: {e}")
        results["mail"] = False

    # Drive - try to list files (limit 1)
    try:
        service = build("drive", "v3", credentials=credentials)
        service.files().list(pageSize=1).execute()
        results["drive"] = True
    except HttpError as e:
        _logger.debug(f"Drive access check failed: {e}")
        results["drive"] = False
    except Exception as e:
        _logger.debug(f"Drive access check error: {type(e).__name__}: {e}")
        results["drive"] = False

    # Sheets - try to create and immediately delete (no good read-only check)
    # Actually, just try to access the API at all with a fake spreadsheet
    try:
        service = build("sheets", "v4", credentials=credentials)
        # Try to get a non-existent spreadsheet - will fail with 404 if scopes OK, 403 if not
        service.spreadsheets().get(spreadsheetId="nonexistent_test_id").execute()
        results["sheets"] = True
    except HttpError as e:
        if e.resp.status == 404:
            # 404 = scopes are fine, just spreadsheet doesn't exist
            results["sheets"] = True
        elif e.resp.status == 403:
            results["sheets"] = False
        else:
            _logger.debug(f"Sheets access check unexpected: {e}")
            results["sheets"] = False
    except Exception as e:
        _logger.debug(f"Sheets access check error: {type(e).__name__}: {e}")
        results["sheets"] = False

    # Docs - similar pattern
    try:
        service = build("docs", "v1", credentials=credentials)
        service.documents().get(documentId="nonexistent_test_id").execute()
        results["docs"] = True
    except HttpError as e:
        if e.resp.status == 404:
            results["docs"] = True
        elif e.resp.status == 403:
            results["docs"] = False
        else:
            _logger.debug(f"Docs access check unexpected: {e}")
            results["docs"] = False
    except Exception as e:
        _logger.debug(f"Docs access check error: {type(e).__name__}: {e}")
        results["docs"] = False

    # Calendar - try to list calendars
    try:
        service = build("calendar", "v3", credentials=credentials)
        service.calendarList().list(maxResults=1).execute()
        results["cal"] = True
    except HttpError as e:
        _logger.debug(f"Calendar access check failed: {e}")
        results["cal"] = False
    except Exception as e:
        _logger.debug(f"Calendar access check error: {type(e).__name__}: {e}")
        results["cal"] = False

    return results
