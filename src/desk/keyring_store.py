"""OS keychain credential storage via the keyring library.

Isolates all keyring interactions so auth.py can route storage
through keyring with file-based fallback for migration.
"""

from __future__ import annotations

import json

import keyring
import keyring.errors

KEYRING_SERVICE = "desk-google"


class KeyringUnavailableError(RuntimeError):
    """Raised when no usable keyring backend is available."""


def check_keyring_backend() -> None:
    """Verify a real keyring backend is available.

    Raises KeyringUnavailableError if the backend is a fail or null backend.
    """
    backend = keyring.get_keyring()
    backend_name = type(backend).__name__
    if backend_name in ("fail", "Fail", "NullKeyring", "NoKeyring"):
        raise KeyringUnavailableError(
            f"No usable keyring backend found (got {backend_name}). "
            "Install a backend like keyring[macOS] or keyring[SecretService], "
            "or set the PYTHON_KEYRING_BACKEND environment variable."
        )


def get_client_credentials() -> dict | None:
    """Read the full client credentials dict (installed block) from keyring.

    Returns the parsed dict (e.g. {"installed": {...}}) or None if not stored.
    """
    data = keyring.get_password(KEYRING_SERVICE, "client:credentials")
    if data is None:
        return None
    try:
        return json.loads(data)
    except (json.JSONDecodeError, TypeError):
        return None


def set_client_credentials(credentials: dict) -> None:
    """Store the full client credentials dict in keyring as JSON."""
    keyring.set_password(KEYRING_SERVICE, "client:credentials", json.dumps(credentials))


def get_token() -> dict | None:
    """Read the OAuth token dict from keyring.

    Returns the parsed token dict or None if not stored.
    """
    data = keyring.get_password(KEYRING_SERVICE, "oauth:token")
    if data is None:
        return None
    try:
        return json.loads(data)
    except (json.JSONDecodeError, TypeError):
        return None


def set_token(token: dict) -> None:
    """Store the OAuth token dict in keyring as JSON."""
    keyring.set_password(KEYRING_SERVICE, "oauth:token", json.dumps(token))


def delete_token() -> bool:
    """Delete the OAuth token from keyring. Returns True if it existed."""
    try:
        if keyring.get_password(KEYRING_SERVICE, "oauth:token") is not None:
            keyring.delete_password(KEYRING_SERVICE, "oauth:token")
            return True
    except keyring.errors.PasswordDeleteError:
        pass
    return False


def clear_all() -> bool:
    """Delete all desk credentials from keyring. Returns True if anything was deleted."""
    deleted = False
    for key in ("client:credentials", "oauth:token"):
        try:
            if keyring.get_password(KEYRING_SERVICE, key) is not None:
                keyring.delete_password(KEYRING_SERVICE, key)
                deleted = True
        except keyring.errors.PasswordDeleteError:
            pass
    return deleted
