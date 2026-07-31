"""Tests for meet CLI commands (ADR-036, issue #81)."""

import json
from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

MEET_SCOPE = "https://www.googleapis.com/auth/meetings.space.settings"


@pytest.fixture
def runner():
    return CliRunner()


@pytest.fixture
def mock_get_credentials():
    with patch("desk.commands.meet.get_credentials") as mock:
        mock.return_value = MagicMock()
        yield mock


@pytest.fixture
def scope_granted():
    """Pretend the user has consented to the Meet scope."""
    with patch("desk.auth.granted_scopes", return_value={MEET_SCOPE}):
        yield


@pytest.fixture
def mock_meet_client_class():
    with patch("desk.commands.meet.MeetClient") as mock:
        yield mock


class TestMeetUpdate:
    def test_sets_auto_record(
        self, runner, mock_get_credentials, scope_granted, mock_meet_client_class
    ):
        from desk.commands.meet import meet

        client = MagicMock()
        client.configure_artifacts.return_value = {
            "name": "spaces/x",
            "meetingCode": "abc-defg-hij",
            "meetingUri": "https://meet.google.com/abc-defg-hij",
            "autoRecord": "ON",
            "autoTranscript": "",
            "autoSmartNotes": "",
        }
        mock_meet_client_class.return_value = client

        result = runner.invoke(
            meet, ["update", "abc-defg-hij", "--auto-record", "on", "--json"]
        )

        assert result.exit_code == 0
        assert client.configure_artifacts.call_args.kwargs["auto_record"] == "on"
        payload = json.loads(result.output)
        assert payload["changes"]["autoRecord"] == "ON"

    def test_unmentioned_settings_passed_as_none(
        self, runner, mock_get_credentials, scope_granted, mock_meet_client_class
    ):
        """Only what the user asked for should reach the service."""
        from desk.commands.meet import meet

        client = MagicMock()
        client.configure_artifacts.return_value = {
            "name": "spaces/x", "meetingCode": "c", "meetingUri": "",
            "autoRecord": "ON", "autoTranscript": "", "autoSmartNotes": "",
        }
        mock_meet_client_class.return_value = client

        runner.invoke(meet, ["update", "abc", "--auto-record", "on", "--json"])

        kwargs = client.configure_artifacts.call_args.kwargs
        assert kwargs["auto_transcript"] is None
        assert kwargs["auto_smart_notes"] is None

    def test_rejects_invalid_value(
        self, runner, mock_get_credentials, scope_granted, mock_meet_client_class
    ):
        from desk.commands.meet import meet

        mock_meet_client_class.return_value = MagicMock()
        result = runner.invoke(meet, ["update", "abc", "--auto-record", "yes"])

        assert result.exit_code != 0

    def test_empty_update_is_a_structured_error(
        self, runner, mock_get_credentials, scope_granted, mock_meet_client_class
    ):
        from desk.commands.meet import meet

        client = MagicMock()
        client.configure_artifacts.side_effect = ValueError("Nothing to update.")
        mock_meet_client_class.return_value = client

        result = runner.invoke(meet, ["update", "abc", "--json"])

        assert result.exit_code == 1
        payload = json.loads(result.stderr)
        assert payload["error"]["code"] == "INVALID_INPUT"

    def test_all_three_settings(
        self, runner, mock_get_credentials, scope_granted, mock_meet_client_class
    ):
        from desk.commands.meet import meet

        client = MagicMock()
        client.configure_artifacts.return_value = {
            "name": "spaces/x", "meetingCode": "c", "meetingUri": "",
            "autoRecord": "ON", "autoTranscript": "ON", "autoSmartNotes": "ON",
        }
        mock_meet_client_class.return_value = client

        result = runner.invoke(
            meet,
            ["update", "abc", "--auto-record", "on", "--auto-transcript", "on",
             "--auto-smart-notes", "on", "--json"],
        )

        payload = json.loads(result.output)
        assert payload["changes"] == {
            "autoRecord": "ON",
            "autoTranscript": "ON",
            "autoSmartNotes": "ON",
        }


class TestMeetRead:
    def test_json_output(
        self, runner, mock_get_credentials, scope_granted, mock_meet_client_class
    ):
        from desk.commands.meet import meet

        client = MagicMock()
        client.get_space.return_value = {
            "name": "spaces/x",
            "meetingCode": "abc-defg-hij",
            "meetingUri": "https://meet.google.com/abc-defg-hij",
            "accessType": "TRUSTED",
            "entryPointAccess": "",
            "moderation": "ON",
            "autoRecord": "ON",
            "autoTranscript": "OFF",
            "autoSmartNotes": "",
        }
        mock_meet_client_class.return_value = client

        result = runner.invoke(meet, ["read", "abc-defg-hij", "--json"])

        assert result.exit_code == 0
        payload = json.loads(result.output)
        assert payload["autoRecord"] == "ON"
        assert payload["meetingCode"] == "abc-defg-hij"

    def test_human_output_marks_unset_settings(
        self, runner, mock_get_credentials, scope_granted, mock_meet_client_class
    ):
        """An absent setting must not read as "off"."""
        from desk.commands.meet import meet

        client = MagicMock()
        client.get_space.return_value = {
            "name": "spaces/x", "meetingCode": "abc", "meetingUri": "",
            "accessType": "", "entryPointAccess": "", "moderation": "",
            "autoRecord": "", "autoTranscript": "", "autoSmartNotes": "",
        }
        mock_meet_client_class.return_value = client

        result = runner.invoke(meet, ["read", "abc"])

        assert result.exit_code == 0
        assert "(unset)" in result.output


class TestMeetScopeGate:
    """The scope no existing token has — this gate is the common path (ADR-036)."""

    def test_blocked_without_scope(
        self, runner, mock_get_credentials, mock_meet_client_class
    ):
        from desk.commands.meet import meet

        mock_meet_client_class.return_value = MagicMock()
        with patch("desk.auth.granted_scopes", return_value={"https://x/other"}):
            result = runner.invoke(meet, ["read", "abc", "--json"])

        assert result.exit_code == 1
        payload = json.loads(result.stderr)
        assert payload["error"]["code"] == "INSUFFICIENT_SCOPES"
        assert MEET_SCOPE in payload["error"]["details"]["scope_needed"]
        assert payload["error"]["details"]["affected_commands"] == ["meet (all commands)"]

    def test_no_api_call_when_blocked(
        self, runner, mock_get_credentials, mock_meet_client_class
    ):
        """Fast fail — the gate must run before a client is built."""
        from desk.commands.meet import meet

        client = MagicMock()
        mock_meet_client_class.return_value = client
        with patch("desk.auth.granted_scopes", return_value=set()):
            runner.invoke(meet, ["update", "abc", "--auto-record", "on", "--json"])

        client.configure_artifacts.assert_not_called()

    def test_fails_open_when_grant_unknown(
        self, runner, mock_get_credentials, mock_meet_client_class
    ):
        """A token predating granted-scope persistence must not be blocked."""
        from desk.commands.meet import meet

        client = MagicMock()
        client.get_space.return_value = {
            "name": "spaces/x", "meetingCode": "abc", "meetingUri": "",
            "accessType": "", "entryPointAccess": "", "moderation": "",
            "autoRecord": "", "autoTranscript": "", "autoSmartNotes": "",
        }
        mock_meet_client_class.return_value = client

        with patch("desk.auth.granted_scopes", return_value=None):
            result = runner.invoke(meet, ["read", "abc", "--json"])

        assert result.exit_code == 0


class TestMeetHelpDocumentsLimitations:
    """#80/#81 asked for the Google limitations to be discoverable."""

    def test_group_help_covers_cohosts(self, runner):
        from desk.commands.meet import meet

        result = runner.invoke(meet, ["--help"])

        assert "Co-hosts" in result.output
        assert "Developer Preview" in result.output

    def test_group_help_covers_recurring_events(self, runner):
        from desk.commands.meet import meet

        result = runner.invoke(meet, ["--help"])

        assert "recurring" in result.output

    def test_cal_create_help_points_at_meet(self, runner):
        from desk.commands.cal import cal

        result = runner.invoke(cal, ["create", "--help"])

        assert "co-organizer" in result.output
        assert "desk meet" in result.output
