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
