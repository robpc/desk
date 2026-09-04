"""Tests for version and build provenance (ADR-036, issue #93)."""

import json
import subprocess
import sys
import types
from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner


@pytest.fixture
def no_build_info():
    """Ensure desk._build_info looks absent, whatever the install shape."""
    saved = sys.modules.pop("desk._build_info", None)
    with patch.dict(sys.modules, {"desk._build_info": None}):
        yield
    if saved is not None:
        sys.modules["desk._build_info"] = saved


@pytest.fixture
def fake_build_info():
    """Inject a build-time provenance module, as a real wheel would carry."""
    module = types.ModuleType("desk._build_info")
    module.COMMIT = "a837d65"
    module.COMMIT_DATE = "2026-09-03"
    with patch.dict(sys.modules, {"desk._build_info": module}):
        yield module


class TestVersionResolution:
    def test_build_info_wins(self, fake_build_info):
        """A baked stamp is authoritative — no git call needed."""
        from desk.version import get_version_info

        with patch("desk.version.subprocess.run") as run:
            info = get_version_info()

        assert info["commit"] == "a837d65"
        assert info["commit_date"] == "2026-09-03"
        assert info["source"] == "build"
        # An installed wheel must not depend on git being present.
        run.assert_not_called()

    def test_falls_back_to_git_for_editable_installs(self, no_build_info):
        from desk.version import get_version_info

        def fake_run(cmd, **kwargs):
            out = "deadbee" if "rev-parse" in cmd else "2026-09-03"
            return MagicMock(returncode=0, stdout=out + "\n")

        with patch("desk.version.subprocess.run", side_effect=fake_run):
            info = get_version_info()

        assert info["commit"] == "deadbee"
        assert info["source"] == "git"

    def test_no_provenance_anywhere(self, no_build_info):
        from desk.version import get_version_info

        with patch("desk.version.subprocess.run",
                   return_value=MagicMock(returncode=128, stdout="")):
            info = get_version_info()

        assert info["commit"] is None
        assert info["commit_date"] is None
        assert info["source"] == "unknown"
        # The version itself is never lost.
        assert info["version"]

    def test_git_failure_never_raises(self, no_build_info):
        """--version must not blow up because git is missing or broken."""
        from desk.version import get_version_info

        for boom in (FileNotFoundError("no git"),
                     subprocess.TimeoutExpired("git", 5),
                     OSError("permission denied")):
            with patch("desk.version.subprocess.run", side_effect=boom):
                info = get_version_info()
            assert info["source"] == "unknown"

    def test_commit_without_date_still_reported(self, no_build_info):
        from desk.version import get_version_info

        def fake_run(cmd, **kwargs):
            if "rev-parse" in cmd:
                return MagicMock(returncode=0, stdout="deadbee\n")
            return MagicMock(returncode=1, stdout="")

        with patch("desk.version.subprocess.run", side_effect=fake_run):
            info = get_version_info()

        assert info["commit"] == "deadbee"
        assert info["commit_date"] is None


class TestFormatVersion:
    def test_full_provenance(self):
        from desk.version import format_version

        line = format_version(
            {"version": "0.3.0", "commit": "a837d65",
             "commit_date": "2026-09-03", "source": "build"}
        )

        assert line == "desk, version 0.3.0 (a837d65, 2026-09-03)"

    def test_commit_without_date(self):
        from desk.version import format_version

        line = format_version(
            {"version": "0.3.0", "commit": "a837d65",
             "commit_date": None, "source": "git"}
        )

        assert line == "desk, version 0.3.0 (a837d65)"

    def test_no_commit_reads_exactly_as_before(self):
        """Degrading to today's output, not to something odd like '()'."""
        from desk.version import format_version

        line = format_version(
            {"version": "0.3.0", "commit": None,
             "commit_date": None, "source": "unknown"}
        )

        assert line == "desk, version 0.3.0"

    def test_version_number_stays_the_third_token(self):
        """Callers parsing the number out of the line keep working."""
        from desk.version import format_version

        line = format_version(
            {"version": "0.3.0", "commit": "a837d65",
             "commit_date": "2026-09-03", "source": "build"}
        )

        assert line.split()[2] == "0.3.0"


class TestVersionCLI:
    @pytest.fixture
    def runner(self):
        return CliRunner()

    def test_version_flag_prints_provenance(self, runner, fake_build_info):
        from desk.cli import main

        result = runner.invoke(main, ["--version"])

        assert result.exit_code == 0
        assert result.output.strip() == "desk, version 0.3.0 (a837d65, 2026-09-03)"

    def test_version_json(self, runner, fake_build_info):
        from desk.cli import main

        result = runner.invoke(main, ["--version", "--json"])

        assert result.exit_code == 0
        payload = json.loads(result.output)
        assert payload["commit"] == "a837d65"
        assert payload["commit_date"] == "2026-09-03"
        # `source` tells a caller how much to trust `commit`.
        assert payload["source"] == "build"
        assert set(payload) == {"version", "commit", "commit_date", "source"}

    def test_version_exits_before_doing_any_work(self, runner, fake_build_info):
        """Introspection only — no audit logger, no auth, no migration."""
        from desk.cli import main

        with patch("desk.cli.get_audit_logger") as audit:
            result = runner.invoke(main, ["--version"])

        assert result.exit_code == 0
        audit.assert_not_called()

    def test_capabilities_carries_the_commit(self, runner, fake_build_info):
        """Agents check for a fix here, not in --version."""
        from desk.cli import main

        result = runner.invoke(main, ["--capabilities", "all"])

        assert result.exit_code == 0
        assert json.loads(result.output)["commit"] == "a837d65"

    def test_filtered_capabilities_carries_the_commit(self, runner, fake_build_info):
        from desk.cli import main

        result = runner.invoke(main, ["--capabilities", "cal"])

        assert result.exit_code == 0
        assert json.loads(result.output)["commit"] == "a837d65"
