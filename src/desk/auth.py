"""OAuth authentication for Google Workspace APIs.

Supports two authentication methods:
1. gcloud Application Default Credentials (ADC) - simplest, requires gcloud
2. User-provided OAuth credentials (credentials.json) - for teams
"""

import json as json_module
import logging
import os
import subprocess
import sys

from google.auth import default as google_auth_default
from google.auth.exceptions import DefaultCredentialsError, RefreshError, TransportError
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials

from desk import keyring_store
from desk.config import (
    CREDENTIALS_FILE,
    GCLOUD_SCOPES,
    SCOPES,
    TOKEN_FILE,
    ensure_config_dir,
)

# Fields safe to keep in plaintext metadata files (no secrets)
_TOKEN_SENSITIVE_FIELDS = ("token", "refresh_token", "client_secret")

# Debug logging - enable with DESK_DEBUG=1
_logger = logging.getLogger("desk.auth")
if os.environ.get("DESK_DEBUG"):
    logging.basicConfig(level=logging.DEBUG)
    _logger.setLevel(logging.DEBUG)

# Track why auth failed so callers can surface it
_last_auth_failure: dict[str, str | None] = {"reason": None, "error_code": None}


def get_last_auth_failure() -> tuple[str | None, str | None]:
    """Return (reason, error_code) for the last auth failure.

    reason: Human-readable diagnostic (what went wrong)
    error_code: Machine-readable code matching agent.ErrorCode values
    """
    return _last_auth_failure["reason"], _last_auth_failure["error_code"]


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
    # Clear any stale failure reason from a previous call
    _last_auth_failure["reason"] = None
    _last_auth_failure["error_code"] = None

    # First, try existing token from OAuth flow
    creds = _get_oauth_credentials()
    if creds:
        return creds

    # Second, try gcloud ADC
    creds = _get_adc_credentials()
    if creds:
        return creds

    return None


def _migrate_token_to_keyring() -> None:
    """Migrate token from token.json to keyring, then scrub secrets from file."""
    if not TOKEN_FILE.exists():
        return
    try:
        data = json_module.loads(TOKEN_FILE.read_text())
    except (json_module.JSONDecodeError, OSError):
        return
    if "token" not in data and "refresh_token" not in data:
        return  # Already scrubbed or not a real token
    # Write full token to keyring
    keyring_store.set_token(data)
    # Scrub secrets from file, keep metadata
    scrubbed = {k: v for k, v in data.items() if k not in _TOKEN_SENSITIVE_FIELDS}
    TOKEN_FILE.write_text(json_module.dumps(scrubbed))


def _migrate_credentials_to_keyring() -> None:
    """Migrate credentials.json to keyring, then remove the file."""
    if not CREDENTIALS_FILE.exists():
        return
    try:
        data = json_module.loads(CREDENTIALS_FILE.read_text())
    except (json_module.JSONDecodeError, OSError):
        return
    if "installed" in data:
        keyring_store.set_client_credentials(data)
        CREDENTIALS_FILE.unlink(missing_ok=True)


def _get_oauth_credentials() -> Credentials | None:
    """Get credentials from keyring or token.json (previous OAuth flow)."""
    # Try keyring first
    token_data = keyring_store.get_token()
    if token_data:
        try:
            creds = Credentials.from_authorized_user_info(token_data, SCOPES)
        except (ValueError, KeyError) as e:
            _logger.debug(f"Failed to parse keyring token: {e}")
            _last_auth_failure["reason"] = f"Corrupted keyring token: {e}"
            _last_auth_failure["error_code"] = "AUTH_INVALID"
            return None
    elif TOKEN_FILE.exists():
        # Fall back to file — check if it has secrets (needs migration)
        try:
            file_data = json_module.loads(TOKEN_FILE.read_text())
        except (json_module.JSONDecodeError, OSError):
            return None
        if "token" not in file_data and "refresh_token" not in file_data:
            return None  # Scrubbed metadata only, no usable token
        try:
            creds = Credentials.from_authorized_user_file(str(TOKEN_FILE), SCOPES)
        except (ValueError, KeyError) as e:
            _logger.debug(f"Failed to parse token file: {e}")
            _last_auth_failure["reason"] = f"Corrupted token file: {e}"
            _last_auth_failure["error_code"] = "AUTH_INVALID"
            return None
        except Exception as e:
            _logger.debug(f"Unexpected error loading token file: {type(e).__name__}: {e}")
            _last_auth_failure["reason"] = (
                f"Could not load token file: {type(e).__name__}: {e}"
            )
            _last_auth_failure["error_code"] = "AUTH_INVALID"
            return None
        # Migrate to keyring
        _migrate_token_to_keyring()
    else:
        return None

    if creds.valid:
        return creds

    if creds.expired and creds.refresh_token:
        try:
            creds.refresh(Request())
            _save_credentials(creds)
            return creds
        except RefreshError as e:
            _logger.debug(f"Token refresh failed: {e}")
            _last_auth_failure["reason"] = (
                "Token expired or revoked. Run `desk auth login` to re-authenticate."
            )
            _last_auth_failure["error_code"] = "AUTH_EXPIRED"
            return None
        except TransportError as e:
            _logger.debug(f"Token refresh network error: {e}")
            _last_auth_failure["reason"] = (
                f"Network error during token refresh: {e}."
                " Check your internet connection and try again."
            )
            _last_auth_failure["error_code"] = "AUTH_EXPIRED"
            return None
        except Exception as e:
            _logger.debug(f"Unexpected error refreshing token: {type(e).__name__}: {e}")
            _last_auth_failure["reason"] = (
                f"Token refresh failed: {type(e).__name__}: {e}."
                " Run `desk auth login` to re-authenticate."
            )
            _last_auth_failure["error_code"] = "AUTH_EXPIRED"
            return None

    if not creds.refresh_token:
        _last_auth_failure["reason"] = (
            "Token expired and no refresh token."
            " Run `desk auth login` to re-authenticate."
        )
        _last_auth_failure["error_code"] = "AUTH_EXPIRED"
    else:
        _last_auth_failure["reason"] = "Token invalid. Run `desk auth login` to re-authenticate."
        _last_auth_failure["error_code"] = "AUTH_INVALID"

    return None


def _get_adc_credentials() -> Credentials | None:
    """Get credentials from gcloud Application Default Credentials."""
    try:
        creds, project = google_auth_default(scopes=SCOPES)
        # ADC credentials auto-refresh, but let's ensure they're valid
        if hasattr(creds, "refresh") and not creds.valid:
            creds.refresh(Request())
        # Cache to token.json so subsequent invocations reuse the access token
        # instead of refreshing every time (~300ms savings per call)
        if hasattr(creds, "to_json") and getattr(creds, "refresh_token", None):
            _save_credentials(creds)
        return creds
    except DefaultCredentialsError:
        _logger.debug("No Application Default Credentials found")
        _last_auth_failure["reason"] = "No credentials found. Run `desk setup` to authenticate."
        _last_auth_failure["error_code"] = "AUTH_REQUIRED"
        return None
    except (RefreshError, TransportError) as e:
        _logger.debug(f"ADC refresh failed: {e}")
        _last_auth_failure["reason"] = (
            f"Credential refresh failed: {e}. Run `desk auth login --gcloud` to re-authenticate."
        )
        _last_auth_failure["error_code"] = "AUTH_EXPIRED"
        return None
    except Exception as e:
        _logger.debug(f"Unexpected error with ADC: {type(e).__name__}: {e}")
        _last_auth_failure["reason"] = (
            f"Unexpected auth error: {type(e).__name__}: {e}. Run `desk setup` to re-authenticate."
        )
        _last_auth_failure["error_code"] = "AUTH_INVALID"
        return None


def login(verbose: bool = False, credentials_path: str | None = None) -> Credentials:
    """Run OAuth flow to get new credentials.

    Opens browser for user to authenticate.

    Credentials resolution order:
    1. Explicit credentials_path argument
    2. Keyring client credentials
    3. User-provided ~/.desk/credentials.json (migrates to keyring)
    4. Error with instructions
    """
    from google_auth_oauthlib.flow import InstalledAppFlow

    ensure_config_dir()

    flow = None

    # 1. Explicit path
    if credentials_path:
        if verbose:
            print(f"Using credentials from {credentials_path}")
        flow = InstalledAppFlow.from_client_secrets_file(credentials_path, SCOPES)

    # 2. Keyring client credentials
    if flow is None:
        keyring_creds = keyring_store.get_client_credentials()
        if keyring_creds:
            if verbose:
                print("Using credentials from keychain")
            flow = InstalledAppFlow.from_client_config(keyring_creds, SCOPES)

    # 3. User-provided credentials file (migrate to keyring)
    if flow is None and CREDENTIALS_FILE.exists():
        if verbose:
            print(f"Using credentials from {CREDENTIALS_FILE}")
        flow = InstalledAppFlow.from_client_secrets_file(str(CREDENTIALS_FILE), SCOPES)
        _migrate_credentials_to_keyring()

    # 4. Error with instructions
    if flow is None:
        print("Error: No credentials available.", file=sys.stderr)
        print(file=sys.stderr)
        print("Options:", file=sys.stderr)
        print(file=sys.stderr)
        print("  Option 1 - Use gcloud (simplest):", file=sys.stderr)
        print("    desk auth login --gcloud", file=sys.stderr)
        print(file=sys.stderr)
        print("  Option 2 - Use team credentials:", file=sys.stderr)
        print("    desk auth set-client --client-id X --client-secret Y", file=sys.stderr)
        print(file=sys.stderr)
        print("  Option 3 - Use credentials file:", file=sys.stderr)
        print("    1. Get credentials.json from your team", file=sys.stderr)
        print(f"    2. Copy to {CREDENTIALS_FILE}", file=sys.stderr)
        print("    3. Run: desk auth login", file=sys.stderr)
        print(file=sys.stderr)
        sys.exit(1)

    if verbose:
        print("Opening browser for authentication...")

    creds = flow.run_local_server(port=0)
    _save_credentials(creds)

    if verbose:
        print("Token saved to keychain")

    return creds


def login_with_gcloud(verbose: bool = False) -> Credentials | None:
    """Authenticate using gcloud application-default login.

    Returns credentials if successful, None if gcloud not available.
    """
    # Check if gcloud is available
    if not _gcloud_available():
        if verbose:
            print("gcloud CLI not found", file=sys.stderr)
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
            print("gcloud authentication failed", file=sys.stderr)
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
    """Save credentials to keyring. Write non-sensitive metadata to token file."""
    ensure_config_dir()
    data = json_module.loads(creds.to_json())
    # Preserve quota_project_id for gcloud ADC credentials
    if getattr(creds, "quota_project_id", None):
        data["quota_project_id"] = creds.quota_project_id
    # Store full token in keyring
    keyring_store.set_token(data)
    # Write scrubbed metadata to file for debuggability
    scrubbed = {k: v for k, v in data.items() if k not in _TOKEN_SENSITIVE_FIELDS}
    TOKEN_FILE.write_text(json_module.dumps(scrubbed))


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
        "credentials_in_keyring": keyring_store.get_client_credentials() is not None,
        "credentials_path": str(CREDENTIALS_FILE),
        "token_file": TOKEN_FILE.exists(),
        "token_in_keyring": keyring_store.get_token() is not None,
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

    # Groups - try to list groups in the caller's customer (lightweight)
    # 403 here is expected for non-admin accounts even when the scope is granted.
    try:
        service = build("admin", "directory_v1", credentials=credentials)
        service.groups().list(customer="my_customer", maxResults=1).execute()
        results["groups"] = True
    except HttpError as e:
        _logger.debug(f"Groups access check failed: {e}")
        results["groups"] = False
    except Exception as e:
        _logger.debug(f"Groups access check error: {type(e).__name__}: {e}")
        results["groups"] = False

    return results
