"""Idempotency key support for safe retries.

Allows agents to safely retry operations that might have partially succeeded.
Keys are stored locally and expire after a configurable period.

See ADR-004 and Idea 033 for design rationale.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from desk.config import CONFIG_DIR

IDEMPOTENCY_FILE = CONFIG_DIR / "idempotency.json"
DEFAULT_EXPIRY_DAYS = 7


def _load_store() -> dict[str, Any]:
    """Load the idempotency store from disk."""
    if not IDEMPOTENCY_FILE.exists():
        return {}
    try:
        with open(IDEMPOTENCY_FILE) as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}


def _save_store(store: dict[str, Any]) -> None:
    """Save the idempotency store to disk."""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    with open(IDEMPOTENCY_FILE, "w", opener=lambda p, flags: os.open(p, flags, 0o600)) as f:
        json.dump(store, f, indent=2)
    os.chmod(IDEMPOTENCY_FILE, 0o600)  # mitigation: restrict read access; operation result content risk remains


def _cleanup_expired(store: dict[str, Any]) -> dict[str, Any]:
    """Remove expired entries from the store."""
    now = datetime.now(timezone.utc)
    cleaned = {}
    for key, entry in store.items():
        expires_str = entry.get("expires")
        if expires_str:
            try:
                expires = datetime.fromisoformat(expires_str)
                if expires > now:
                    cleaned[key] = entry
            except ValueError:
                # Invalid date, skip entry
                pass
    return cleaned


def check_idempotency(key: str) -> dict[str, Any] | None:
    """Check if an operation was already performed with this key.

    Args:
        key: The idempotency key to check

    Returns:
        The cached result if found and not expired, None otherwise
    """
    store = _load_store()
    store = _cleanup_expired(store)

    entry = store.get(key)
    if entry:
        return {
            "cached": True,
            "original_timestamp": entry.get("timestamp"),
            "result": entry.get("result"),
        }
    return None


def record_idempotency(
    key: str,
    operation: str,
    result: dict[str, Any],
    expiry_days: int = DEFAULT_EXPIRY_DAYS,
) -> None:
    """Record an operation result for idempotency.

    Args:
        key: The idempotency key
        operation: Name of the operation (e.g., "mail.send")
        result: The result to cache
        expiry_days: How long to keep the entry
    """
    store = _load_store()
    store = _cleanup_expired(store)

    now = datetime.now(timezone.utc)
    expires = now + timedelta(days=expiry_days)

    store[key] = {
        "operation": operation,
        "timestamp": now.isoformat(),
        "expires": expires.isoformat(),
        "result": result,
    }

    _save_store(store)


def clear_idempotency(key: str | None = None) -> int:
    """Clear idempotency entries.

    Args:
        key: Specific key to clear, or None to clear all expired entries

    Returns:
        Number of entries removed
    """
    store = _load_store()
    original_count = len(store)

    if key:
        if key in store:
            del store[key]
    else:
        store = _cleanup_expired(store)

    _save_store(store)
    return original_count - len(store)
