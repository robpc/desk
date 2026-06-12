"""Tests for sheets CLI commands."""

import json
from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner


@pytest.fixture
def runner():
    """Create a Click CLI test runner."""
    return CliRunner()


@pytest.fixture
def mock_get_credentials():
    """Mock the get_credentials function."""
    with patch("desk.commands.sheets.get_credentials") as mock:
        mock.return_value = MagicMock()
        yield mock


@pytest.fixture
def mock_sheets_client_class():
    """Mock the SheetsClient class."""
    with patch("desk.commands.sheets.SheetsClient") as mock:
        yield mock


class TestSheetsRead:
    """Tests for desk sheets read command."""

    def test_read_with_json_output(self, runner, mock_get_credentials, mock_sheets_client_class):
        """Should output spreadsheet data as JSON."""
        from desk.commands.sheets import sheets

        mock_client = MagicMock()
        mock_client.read.return_value = {
            "spreadsheetId": "spreadsheet_id",
            "title": "Test Sheet",
            "sheets": [{"id": 0, "title": "Sheet1"}],
            "range": "Sheet1!A1:C3",
            "values": [
                ["Name", "Age", "City"],
                ["Alice", "30", "NYC"],
            ],
        }
        mock_sheets_client_class.return_value = mock_client

        result = runner.invoke(sheets, ["read", "spreadsheet_id", "--json"])

        assert result.exit_code == 0
        output = json.loads(result.output)
        assert "values" in output


class TestSheetsCreate:
    """Tests for desk sheets create command."""

    def test_create_spreadsheet(self, runner, mock_get_credentials, mock_sheets_client_class):
        """Should create a new spreadsheet."""
        from desk.commands.sheets import sheets

        mock_client = MagicMock()
        mock_client.create.return_value = {
            "spreadsheetId": "new_spreadsheet_id",
            "spreadsheetUrl": "https://docs.google.com/spreadsheets/d/new_spreadsheet_id",
            "properties": {"title": "New Spreadsheet"},
        }
        mock_sheets_client_class.return_value = mock_client

        result = runner.invoke(sheets, ["create", "New Spreadsheet"])

        assert result.exit_code == 0
        mock_client.create.assert_called_once_with("New Spreadsheet")
