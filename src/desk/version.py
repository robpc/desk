"""Version and build provenance.

`desk --version` names the commit a build came from, so two builds of the
same version number can be told apart. See ADR-036.
"""

import subprocess
from pathlib import Path

from desk import __version__

__all__ = ["get_version_info", "format_version"]


def _from_build_info() -> tuple[str, str] | None:
    """Read provenance baked in at build time by hatch_build.py."""
    try:
        from desk import _build_info
    except ImportError:
        return None
    commit = getattr(_build_info, "COMMIT", None)
    if not commit:
        return None
    return commit, getattr(_build_info, "COMMIT_DATE", None) or ""


def _from_git() -> tuple[str, str] | None:
    """Resolve HEAD from the checkout this package lives in.

    Only reached for editable installs, where there was no build step to
    bake anything in. Never raises: a broken git, a missing binary or a
    non-repository all degrade to no provenance rather than a traceback
    out of `--version`.
    """
    root = Path(__file__).resolve().parent
    try:
        result = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "--short", "HEAD"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        if result.returncode != 0:
            return None
        commit = result.stdout.strip()
        if not commit:
            return None
        dated = subprocess.run(
            ["git", "-C", str(root), "show", "-s", "--format=%cs", "HEAD"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        date = dated.stdout.strip() if dated.returncode == 0 else ""
        return commit, date
    except (OSError, subprocess.SubprocessError):
        return None


def get_version_info() -> dict:
    """Return version plus build provenance.

    ``source`` distinguishes a reproducible build stamp (``build``) from a
    dev checkout's live read (``git``) from nothing at all (``unknown``),
    so a caller knows how much to trust ``commit``.
    """
    for source, resolver in (("build", _from_build_info), ("git", _from_git)):
        found = resolver()
        if found:
            commit, date = found
            return {
                "version": __version__,
                "commit": commit,
                "commit_date": date or None,
                "source": source,
            }
    return {
        "version": __version__,
        "commit": None,
        "commit_date": None,
        "source": "unknown",
    }


def format_version(info: dict | None = None) -> str:
    """Human-readable version line.

    The number stays first and unchanged; provenance is a suffix, so a
    caller reading the first token still gets what it always got.
    """
    info = info or get_version_info()
    if not info["commit"]:
        return f"desk, version {info['version']}"
    detail = info["commit"]
    if info["commit_date"]:
        detail = f"{detail}, {info['commit_date']}"
    return f"desk, version {info['version']} ({detail})"
