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
    "https://www.googleapis.com/auth/presentations",
]

# Scopes for gcloud ADC
GCLOUD_SCOPES = [
    *SCOPES,
]

# Scope -> the commands that need it. Drives the `@requires_scope` gate's
# "affected commands" list and the `enabled` flag in `--capabilities`.
# See ADR-034.
#
# An entry is either a bare service name ("slides"), meaning every command in
# that service, or a specific "service command" pair ("cal create") when a scope
# only covers part of a service.
#
# Only scopes worth gating need an entry. Most of Desk's scopes are requested
# together at first login, so a user either has all of them or isn't
# authenticated at all — gating those would add noise without catching anything.
# The entries that matter are scopes added *after* a release, which existing
# tokens predate.
SCOPE_COMMANDS: dict[str, list[str]] = {
    # Added in ADR-026 (Slides). Tokens issued before it lack this scope, which
    # is the drift that the dead scope-diff (issue #82) failed to report.
    "https://www.googleapis.com/auth/presentations": ["slides"],
}


def scopes_for_service(service: str) -> list[str]:
    """Return scopes every command in `service` needs.

    Excludes scopes registered against individual commands — those are gated per
    command, not at the service's client helper.
    """
    return sorted(
        scope for scope, targets in SCOPE_COMMANDS.items() if service in targets
    )


def scopes_for_command(service: str, command: str) -> list[str]:
    """Return the scopes a given command needs, service-wide entries included."""
    keys = {service, f"{service} {command}"}
    return sorted(
        scope for scope, targets in SCOPE_COMMANDS.items() if keys & set(targets)
    )


def commands_for_scopes(scopes: list[str]) -> list[str]:
    """Human-readable list of what a set of missing scopes blocks."""
    affected: set[str] = set()
    for scope in scopes:
        for target in SCOPE_COMMANDS.get(scope, []):
            affected.add(f"{target} (all commands)" if " " not in target else target)
    return sorted(affected)


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
