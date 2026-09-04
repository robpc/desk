"""Hatchling build hook: bake build provenance into the distribution.

Resolves the commit and its date from git at build time and injects a
generated ``desk/_build_info.py`` into the wheel and sdist. See ADR-036.

The file is injected via ``force_include`` rather than written into
``src/``: writing to the source tree would dirty the working copy on every
local build, and gitignoring it would risk hatchling's VCS-aware file
selection dropping it from the sdist.
"""

import os
import subprocess
import tempfile

from hatchling.builders.hooks.plugin.interface import BuildHookInterface

_TEMPLATE = '''"""Generated at build time. Do not edit. See ADR-036."""

COMMIT = {commit!r}
COMMIT_DATE = {commit_date!r}
'''


def _git(root: str, *args: str) -> str | None:
    """Run a git command, returning None on any failure."""
    try:
        out = subprocess.run(
            ["git", *args],
            cwd=root,
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if out.returncode != 0:
        return None
    value = out.stdout.strip()
    return value or None


def _existing_build_info(root: str) -> tuple[str | None, str | None]:
    """Read values from an already-generated _build_info.py.

    Covers the sdist -> wheel path, where the sdist carries the provenance
    but has no git repository to re-derive it from.
    """
    path = os.path.join(root, "src", "desk", "_build_info.py")
    namespace: dict = {}
    try:
        with open(path, encoding="utf-8") as fh:
            exec(compile(fh.read(), path, "exec"), namespace)  # noqa: S102
    except (OSError, SyntaxError, ValueError):
        return None, None
    return namespace.get("COMMIT"), namespace.get("COMMIT_DATE")


class CustomBuildHook(BuildHookInterface):
    def initialize(self, version: str, build_data: dict) -> None:
        root = self.root

        commit = _git(root, "rev-parse", "--short", "HEAD")
        commit_date = None
        if commit:
            commit_date = _git(root, "show", "-s", "--format=%cs", "HEAD")
        else:
            # No git here — carry through whatever the sdist already had
            # rather than overwriting it with unknowns.
            commit, commit_date = _existing_build_info(root)

        content = _TEMPLATE.format(commit=commit, commit_date=commit_date)

        fd, path = tempfile.mkstemp(prefix="desk_build_info_", suffix=".py")
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(content)

        target = (
            "src/desk/_build_info.py"
            if self.target_name == "sdist"
            else "desk/_build_info.py"
        )
        build_data.setdefault("force_include", {})[path] = target
