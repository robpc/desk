"""Audit logging — see ADR-020 and atrium ADR-004.

Two destinations on every log call: local file (mode 0600, rotated at
1 MB) and syslog (corp log forwarder ships it to SIEM on Yahoo machines;
routes to local syslog daemon elsewhere). Subcommand arguments,
document contents, and token contents are never logged.

Users who don't want audit logging can set DESK_AUDIT_DISABLED=1.
"""

from __future__ import annotations

import logging
import logging.handlers
import os
import platform
from pathlib import Path

_TAG = "desk-audit"
_LOG_NAME = "desk.audit"


class _NoOpLogger(logging.Logger):
    """Logger that silently drops all calls. Used when DESK_AUDIT_DISABLED=1."""

    def __init__(self):
        super().__init__(_LOG_NAME + ".noop")
        self.disabled = True

    def isEnabledFor(self, _level: int) -> bool:
        return False


def _syslog_address() -> str | tuple[str, int]:
    """Pick the syslog destination for this platform.

    macOS routes /var/run/syslog to the unified log. Linux uses /dev/log.
    Falls back to UDP localhost:514 if neither is present.
    """
    for path in ("/var/run/syslog", "/dev/log"):
        if Path(path).exists():
            return path
    return ("localhost", 514)


def get_audit_logger(config_dir: Path) -> logging.Logger:
    """Return a logger that writes to both the local audit.log and syslog.

    Idempotent: repeat calls return the same configured logger.
    Returns a no-op logger if DESK_AUDIT_DISABLED is set.
    """
    if os.environ.get("DESK_AUDIT_DISABLED"):
        return _NoOpLogger()

    logger = logging.getLogger(_LOG_NAME)
    if logger.handlers:
        return logger

    logger.setLevel(logging.INFO)
    logger.propagate = False  # Don't double-log via root.

    user = os.environ.get("USER") or os.environ.get("USERNAME") or "unknown"
    host = platform.node().split(".")[0] or "unknown"

    fmt = logging.Formatter(
        fmt=f"%(asctime)sZ user={user} host={host} %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
    )

    # Local file.
    audit_path = config_dir / "audit.log"
    try:
        config_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
        file_handler = logging.handlers.RotatingFileHandler(
            audit_path, maxBytes=1_048_576, backupCount=1
        )
        file_handler.setFormatter(fmt)
        logger.addHandler(file_handler)
        try:
            audit_path.chmod(0o600)
        except OSError:
            pass
    except OSError:
        # If the local file can't be opened, keep going — syslog still works.
        pass

    # Syslog.
    try:
        syslog_handler = logging.handlers.SysLogHandler(address=_syslog_address())
        syslog_handler.ident = _TAG + ": "
        syslog_handler.setFormatter(fmt)
        logger.addHandler(syslog_handler)
    except OSError:
        # Syslog unavailable (e.g. some test/container environments).
        # Local file alone is acceptable.
        pass

    return logger
