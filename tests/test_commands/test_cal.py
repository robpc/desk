"""Tests for cal CLI commands."""

import json
import pytest
from click.testing import CliRunner
from unittest.mock import MagicMock, patch


@pytest.fixture
def runner():
    """Create a Click CLI test runner."""
    return CliRunner()


@pytest.fixture
def mock_get_credentials():
    """Mock the get_credentials function."""
    with patch("desk.commands.cal.get_credentials") as mock:
        mock.return_value = MagicMock()
        yield mock


@pytest.fixture
def mock_calendar_client_class():
    """Mock the CalendarClient class."""
    with patch("desk.commands.cal.CalendarClient") as mock:
        yield mock


class TestCalToday:
    """Tests for desk cal today command."""

    def test_today_with_json_output(self, runner, mock_get_credentials, mock_calendar_client_class):
        """Should output today's events as JSON."""
        from desk.commands.cal import cal

        mock_client = MagicMock()
        mock_client.today.return_value = {
            "events": [
                {
                    "id": "event1",
                    "summary": "Morning Meeting",
                    "start": "2024-01-15T09:00:00",
                    "end": "2024-01-15T10:00:00",
                }
            ]
        }
        mock_calendar_client_class.return_value = mock_client

        result = runner.invoke(cal, ["today", "--json"])

        assert result.exit_code == 0
        output = json.loads(result.output)
        assert "events" in output
        assert len(output["events"]) == 1


class TestCalWeek:
    """Tests for desk cal week command."""

    def test_week_with_json_output(self, runner, mock_get_credentials, mock_calendar_client_class):
        """Should output week's events as JSON."""
        from desk.commands.cal import cal

        mock_client = MagicMock()
        mock_client.week.return_value = {
            "events": [
                {"id": "event1", "summary": "Monday Meeting"},
                {"id": "event2", "summary": "Friday Standup"},
            ]
        }
        mock_calendar_client_class.return_value = mock_client

        result = runner.invoke(cal, ["week", "--json"])

        assert result.exit_code == 0
        output = json.loads(result.output)
        assert len(output["events"]) == 2


class TestCalNext:
    """Tests for desk cal next command."""

    def test_next_with_json_output(self, runner, mock_get_credentials, mock_calendar_client_class):
        """Should output upcoming events as JSON."""
        from desk.commands.cal import cal

        mock_client = MagicMock()
        mock_client.next.return_value = {
            "events": [
                {"id": "event1", "summary": "Next Event"},
            ]
        }
        mock_calendar_client_class.return_value = mock_client

        result = runner.invoke(cal, ["next", "--json"])

        assert result.exit_code == 0
        output = json.loads(result.output)
        assert "events" in output


class TestCalUpdate:
    """Tests for desk cal update command."""

    def test_update_with_remove_attendee(self, runner, mock_get_credentials, mock_calendar_client_class):
        """Should pass remove_attendees through to client and show receipt."""
        from desk.commands.cal import cal

        mock_client = MagicMock()
        mock_client.update.return_value = {
            "id": "ev1",
            "summary": "Team Sync",
            "htmlLink": "https://calendar.google.com/event?eid=ev1",
            "removedAttendees": ["bob@example.com"],
        }
        mock_calendar_client_class.return_value = mock_client

        result = runner.invoke(cal, [
            "update", "ev1",
            "--remove-attendee", "bob@example.com",
            "--json",
        ])

        assert result.exit_code == 0
        mock_client.update.assert_called_once()
        call_kwargs = mock_client.update.call_args
        assert call_kwargs[1]["remove_attendees"] == ["bob@example.com"]

        output = json.loads(result.output)
        assert output["changes"]["removed_attendees"] == ["bob@example.com"]

    def test_update_remove_nonexistent_shows_not_found(self, runner, mock_get_credentials, mock_calendar_client_class):
        """Receipt should include not_found_attendees when email wasn't in attendee list."""
        from desk.commands.cal import cal

        mock_client = MagicMock()
        mock_client.update.return_value = {
            "id": "ev1",
            "summary": "Team Sync",
            "htmlLink": "https://calendar.google.com/event?eid=ev1",
            "removedAttendees": [],
        }
        mock_calendar_client_class.return_value = mock_client

        result = runner.invoke(cal, [
            "update", "ev1",
            "--remove-attendee", "nobody@example.com",
            "--json",
        ])

        assert result.exit_code == 0
        output = json.loads(result.output)
        assert output["changes"]["removed_attendees"] == []
        assert output["changes"]["not_found_attendees"] == ["nobody@example.com"]


class TestCalList:
    """Tests for desk cal list command."""

    def test_list_calendars_json(self, runner, mock_get_credentials, mock_calendar_client_class):
        """Should output calendars as JSON."""
        from desk.commands.cal import cal

        mock_client = MagicMock()
        mock_client.list_calendars.return_value = [
            {"id": "primary", "summary": "Primary", "primary": True},
        ]
        mock_calendar_client_class.return_value = mock_client

        result = runner.invoke(cal, ["list", "--json"])

        assert result.exit_code == 0
        output = json.loads(result.output)
        assert isinstance(output, list)
