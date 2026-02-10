"""Self-update logic for Desk CLI.

Detects how desk was installed and performs the appropriate update.
See ADR-005 for design rationale.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from dataclasses import dataclass
from enum import Enum
from pathlib import Path


class InstallMethod(str, Enum):
    """How desk was installed."""

    EDITABLE_GIT = "editable_git"  # pip install -e . from a git clone
    PIP_FROM_GIT = "pip_from_git"  # pip install git+ssh://...
    UNKNOWN = "unknown"


@dataclass
class InstallInfo:
    """Information about how desk is installed."""

    method: InstallMethod
    repo_path: Path | None = None  # For editable installs
    git_url: str | None = None  # For pip-from-git installs
    branch: str | None = None  # Remote branch (default: main)


@dataclass
class UpdateCheck:
    """Result of checking for updates."""

    update_available: bool
    current_version: str
    remote_version: str | None = None
    commits_behind: int = 0
    error: str | None = None
    error_code: str | None = None


@dataclass
class UpdateResult:
    """Result of applying an update."""

    success: bool
    previous_version: str
    new_version: str | None = None
    error: str | None = None
    error_code: str | None = None


GIT_TIMEOUT = 30
PIP_TIMEOUT = 120


def detect_install() -> InstallInfo:
    """Detect how desk was installed using PEP 610 direct_url.json."""
    from importlib.metadata import distribution

    try:
        dist = distribution("desk")
    except Exception:
        return InstallInfo(method=InstallMethod.UNKNOWN)

    direct_url_text = dist.read_text("direct_url.json")
    if direct_url_text is None:
        return InstallInfo(method=InstallMethod.UNKNOWN)

    try:
        direct_url = json.loads(direct_url_text)
    except json.JSONDecodeError:
        return InstallInfo(method=InstallMethod.UNKNOWN)

    # Check for editable install (dir_info.editable == true)
    dir_info = direct_url.get("dir_info", {})
    if dir_info.get("editable", False):
        url = direct_url.get("url", "")
        # URL is file:///path/to/repo
        if url.startswith("file://"):
            repo_path = Path(url[7:])  # Strip file://
        else:
            repo_path = Path(url)

        # Verify it's actually a git repo
        if (repo_path / ".git").exists():
            return InstallInfo(
                method=InstallMethod.EDITABLE_GIT,
                repo_path=repo_path,
                branch="main",
            )
        else:
            return InstallInfo(method=InstallMethod.UNKNOWN)

    # Check for pip install from git URL (vcs_info present)
    vcs_info = direct_url.get("vcs_info", {})
    if vcs_info.get("vcs") == "git":
        url = direct_url.get("url", "")
        requested_revision = vcs_info.get("requested_revision", "main")
        return InstallInfo(
            method=InstallMethod.PIP_FROM_GIT,
            git_url=url,
            branch=requested_revision,
        )

    return InstallInfo(method=InstallMethod.UNKNOWN)


def _run_git(args: list[str], cwd: Path, timeout: int = GIT_TIMEOUT) -> subprocess.CompletedProcess:
    """Run a git command with timeout."""
    return subprocess.run(
        ["git"] + args,
        cwd=cwd,
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def _get_current_version() -> str:
    """Get the current installed version of desk."""
    from desk import __version__

    return __version__


def _extract_version_from_init(content: str) -> str | None:
    """Extract __version__ from __init__.py content."""
    match = re.search(r'__version__\s*=\s*["\']([^"\']+)["\']', content)
    return match.group(1) if match else None


def check_for_updates(info: InstallInfo) -> UpdateCheck:
    """Check if updates are available without applying them."""
    current_version = _get_current_version()

    if info.method == InstallMethod.UNKNOWN:
        return UpdateCheck(
            update_available=False,
            current_version=current_version,
            error="Cannot determine how desk was installed",
            error_code="UPDATE_UNKNOWN_INSTALL",
        )

    if info.method == InstallMethod.PIP_FROM_GIT:
        # For pip-from-git, we can't easily check without fetching
        # Just report current version and suggest running update
        return UpdateCheck(
            update_available=False,
            current_version=current_version,
            remote_version=None,
            commits_behind=0,
        )

    # Editable git install — fetch and compare
    assert info.repo_path is not None
    branch = info.branch or "main"

    try:
        result = _run_git(["fetch", "origin", branch], cwd=info.repo_path)
        if result.returncode != 0:
            stderr = result.stderr.strip()
            if "Could not resolve hostname" in stderr or "Network is unreachable" in stderr:
                return UpdateCheck(
                    update_available=False,
                    current_version=current_version,
                    error="Network error: could not reach remote",
                    error_code="UPDATE_NETWORK_ERROR",
                )
            if "Permission denied" in stderr or "publickey" in stderr:
                return UpdateCheck(
                    update_available=False,
                    current_version=current_version,
                    error="SSH authentication failed",
                    error_code="UPDATE_FAILED",
                )
            return UpdateCheck(
                update_available=False,
                current_version=current_version,
                error=f"git fetch failed: {stderr}",
                error_code="UPDATE_FAILED",
            )
    except FileNotFoundError:
        return UpdateCheck(
            update_available=False,
            current_version=current_version,
            error="git not found in PATH",
            error_code="UPDATE_NO_GIT",
        )
    except subprocess.TimeoutExpired:
        return UpdateCheck(
            update_available=False,
            current_version=current_version,
            error="git fetch timed out",
            error_code="UPDATE_NETWORK_ERROR",
        )

    # Count commits behind
    result = _run_git(
        ["rev-list", "--count", f"HEAD..origin/{branch}"],
        cwd=info.repo_path,
    )
    commits_behind = int(result.stdout.strip()) if result.returncode == 0 else 0

    # Get remote version
    remote_version = None
    result = _run_git(
        ["show", f"origin/{branch}:src/desk/__init__.py"],
        cwd=info.repo_path,
    )
    if result.returncode == 0:
        remote_version = _extract_version_from_init(result.stdout)

    return UpdateCheck(
        update_available=commits_behind > 0,
        current_version=current_version,
        remote_version=remote_version,
        commits_behind=commits_behind,
    )


def apply_update(info: InstallInfo) -> UpdateResult:
    """Apply an update based on install method."""
    current_version = _get_current_version()

    if info.method == InstallMethod.UNKNOWN:
        return UpdateResult(
            success=False,
            previous_version=current_version,
            error="Cannot determine how desk was installed",
            error_code="UPDATE_UNKNOWN_INSTALL",
        )

    if info.method == InstallMethod.PIP_FROM_GIT:
        return _update_pip_from_git(info, current_version)

    if info.method == InstallMethod.EDITABLE_GIT:
        return _update_editable_git(info, current_version)

    return UpdateResult(
        success=False,
        previous_version=current_version,
        error="Unsupported install method",
        error_code="UPDATE_UNKNOWN_INSTALL",
    )


def _update_editable_git(info: InstallInfo, current_version: str) -> UpdateResult:
    """Update an editable git install via git pull + pip install."""
    assert info.repo_path is not None
    branch = info.branch or "main"

    # git pull --ff-only
    try:
        result = _run_git(
            ["pull", "--ff-only", "origin", branch],
            cwd=info.repo_path,
        )
    except FileNotFoundError:
        return UpdateResult(
            success=False,
            previous_version=current_version,
            error="git not found in PATH",
            error_code="UPDATE_NO_GIT",
        )
    except subprocess.TimeoutExpired:
        return UpdateResult(
            success=False,
            previous_version=current_version,
            error="git pull timed out",
            error_code="UPDATE_NETWORK_ERROR",
        )

    if result.returncode != 0:
        stderr = result.stderr.strip()
        if "Not possible to fast-forward" in stderr or "diverged" in stderr.lower():
            return UpdateResult(
                success=False,
                previous_version=current_version,
                error="Local branch has diverged from remote",
                error_code="UPDATE_FAILED",
            )
        return UpdateResult(
            success=False,
            previous_version=current_version,
            error=f"git pull failed: {stderr}",
            error_code="UPDATE_FAILED",
        )

    if "Already up to date" in result.stdout:
        return UpdateResult(
            success=True,
            previous_version=current_version,
            new_version=current_version,
        )

    # pip install -e .
    try:
        pip_result = subprocess.run(
            [sys.executable, "-m", "pip", "install", "-e", "."],
            cwd=info.repo_path,
            capture_output=True,
            text=True,
            timeout=PIP_TIMEOUT,
        )
    except subprocess.TimeoutExpired:
        return UpdateResult(
            success=False,
            previous_version=current_version,
            error="pip install timed out",
            error_code="UPDATE_FAILED",
        )

    if pip_result.returncode != 0:
        return UpdateResult(
            success=False,
            previous_version=current_version,
            error=f"pip install failed: {pip_result.stderr.strip()}",
            error_code="UPDATE_FAILED",
        )

    # Read new version from the file on disk (not the cached import)
    init_path = info.repo_path / "src" / "desk" / "__init__.py"
    new_version = current_version
    if init_path.exists():
        extracted = _extract_version_from_init(init_path.read_text())
        if extracted:
            new_version = extracted

    return UpdateResult(
        success=True,
        previous_version=current_version,
        new_version=new_version,
    )


def _update_pip_from_git(info: InstallInfo, current_version: str) -> UpdateResult:
    """Update a pip-from-git install via pip install --upgrade."""
    assert info.git_url is not None

    git_spec = f"git+{info.git_url}"
    if info.branch:
        git_spec += f"@{info.branch}"

    try:
        result = subprocess.run(
            [sys.executable, "-m", "pip", "install", "--upgrade", git_spec],
            capture_output=True,
            text=True,
            timeout=PIP_TIMEOUT,
        )
    except subprocess.TimeoutExpired:
        return UpdateResult(
            success=False,
            previous_version=current_version,
            error="pip install timed out",
            error_code="UPDATE_FAILED",
        )

    if result.returncode != 0:
        stderr = result.stderr.strip()
        if "Permission denied" in stderr or "publickey" in stderr:
            return UpdateResult(
                success=False,
                previous_version=current_version,
                error="SSH authentication failed when cloning",
                error_code="UPDATE_FAILED",
            )
        return UpdateResult(
            success=False,
            previous_version=current_version,
            error=f"pip install failed: {stderr}",
            error_code="UPDATE_FAILED",
        )

    return UpdateResult(
        success=True,
        previous_version=current_version,
        new_version=None,  # Can't easily determine without re-importing
    )
