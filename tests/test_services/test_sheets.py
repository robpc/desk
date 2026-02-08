"""Tests for Sheets service client."""

import pytest
from unittest.mock import MagicMock, patch

from googleapiclient.errors import HttpError


class TestSheetsClientInit:
    """Tests for SheetsClient initialization."""

    def test_creates_service_with_credentials(self, mock_credentials):
        """Should create Sheets service with provided credentials."""
        with patch("desk.services.sheets.build") as mock_build:
            mock_build.return_value = MagicMock()
            from desk.services.sheets import SheetsClient

            client = SheetsClient(mock_credentials)

            mock_build.assert_called_once_with("sheets", "v4", credentials=mock_credentials)


class TestSheetsRead:
    """Tests for SheetsClient.read method."""

    def test_read_returns_values(self, mock_credentials):
        """Should return spreadsheet values."""
        with patch("desk.services.sheets.build") as mock_build:
            mock_service = MagicMock()
            mock_build.return_value = mock_service

            spreadsheets_mock = mock_service.spreadsheets.return_value
            # Mock get for metadata
            spreadsheets_mock.get.return_value.execute.return_value = {
                "properties": {"title": "Test Sheet"},
                "sheets": [{"properties": {"sheetId": 0, "title": "Sheet1"}}],
            }
            # Mock values.get for data
            values_mock = spreadsheets_mock.values.return_value
            values_mock.get.return_value.execute.return_value = {
                "range": "Sheet1!A1:C3",
                "values": [
                    ["Name", "Age", "City"],
                    ["Alice", "30", "NYC"],
                    ["Bob", "25", "LA"],
                ],
            }

            from desk.services.sheets import SheetsClient

            client = SheetsClient(mock_credentials)
            # read without ranges returns metadata + first sheet
            result = client.read("spreadsheet_id")

            assert "values" in result
            assert len(result["values"]) == 3
            assert result["values"][0] == ["Name", "Age", "City"]

    def test_read_not_found_raises_error(self, mock_credentials):
        """Should raise error when spreadsheet not found."""
        with patch("desk.services.sheets.build") as mock_build:
            mock_service = MagicMock()
            mock_build.return_value = mock_service

            values_mock = mock_service.spreadsheets.return_value.values.return_value
            http_error = HttpError(
                resp=MagicMock(status=404),
                content=b'{"error": {"message": "Spreadsheet not found"}}'
            )
            values_mock.get.return_value.execute.side_effect = http_error

            from desk.services.sheets import SheetsClient

            client = SheetsClient(mock_credentials)
            with pytest.raises(RuntimeError, match="Sheets API error"):
                client.read("nonexistent_id")


class TestSheetsWrite:
    """Tests for SheetsClient.write method."""

    def test_write_updates_values(self, mock_credentials):
        """Should write values to spreadsheet."""
        with patch("desk.services.sheets.build") as mock_build:
            mock_service = MagicMock()
            mock_build.return_value = mock_service

            values_mock = mock_service.spreadsheets.return_value.values.return_value
            values_mock.update.return_value.execute.return_value = {
                "updatedCells": 6,
                "updatedRows": 2,
                "updatedColumns": 3,
            }

            from desk.services.sheets import SheetsClient

            client = SheetsClient(mock_credentials)
            values = [
                ["Header1", "Header2", "Header3"],
                ["Val1", "Val2", "Val3"],
            ]
            result = client.write("spreadsheet_id", "Sheet1!A1:C2", values)

            assert result["updatedCells"] == 6
            values_mock.update.assert_called_once()


class TestSheetsAppend:
    """Tests for SheetsClient.append method."""

    def test_append_adds_rows(self, mock_credentials):
        """Should append rows to spreadsheet."""
        with patch("desk.services.sheets.build") as mock_build:
            mock_service = MagicMock()
            mock_build.return_value = mock_service

            values_mock = mock_service.spreadsheets.return_value.values.return_value
            values_mock.append.return_value.execute.return_value = {
                "spreadsheetId": "spreadsheet_id",
                "tableRange": "Sheet1!A1:C1",
                "updates": {
                    "spreadsheetId": "spreadsheet_id",
                    "updatedRange": "Sheet1!A2:C3",
                    "updatedRows": 2,
                    "updatedCells": 6,
                }
            }

            from desk.services.sheets import SheetsClient

            client = SheetsClient(mock_credentials)
            values = [
                ["NewRow1", "Data1", "Data2"],
                ["NewRow2", "Data3", "Data4"],
            ]
            result = client.append("spreadsheet_id", "Sheet1", values)

            values_mock.append.assert_called_once()


class TestSheetsClear:
    """Tests for SheetsClient.clear method."""

    def test_clear_removes_values(self, mock_credentials):
        """Should clear values from range."""
        with patch("desk.services.sheets.build") as mock_build:
            mock_service = MagicMock()
            mock_build.return_value = mock_service

            values_mock = mock_service.spreadsheets.return_value.values.return_value
            values_mock.clear.return_value.execute.return_value = {
                "clearedRange": "Sheet1!A1:C10",
            }

            from desk.services.sheets import SheetsClient

            client = SheetsClient(mock_credentials)
            result = client.clear("spreadsheet_id", "Sheet1!A1:C10")

            assert "clearedRange" in result
            values_mock.clear.assert_called_once()


class TestSheetsCreate:
    """Tests for SheetsClient.create method."""

    def test_create_returns_spreadsheet(self, mock_credentials):
        """Should return created spreadsheet."""
        with patch("desk.services.sheets.build") as mock_build:
            mock_service = MagicMock()
            mock_build.return_value = mock_service

            spreadsheets_mock = mock_service.spreadsheets.return_value
            spreadsheets_mock.create.return_value.execute.return_value = {
                "spreadsheetId": "new_spreadsheet_id",
                "spreadsheetUrl": "https://docs.google.com/spreadsheets/d/new_spreadsheet_id",
                "properties": {"title": "New Spreadsheet"},
            }

            from desk.services.sheets import SheetsClient

            client = SheetsClient(mock_credentials)
            result = client.create("New Spreadsheet")

            assert result["spreadsheetId"] == "new_spreadsheet_id"
            spreadsheets_mock.create.assert_called_once()
