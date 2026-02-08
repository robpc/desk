"""Tests for drive CLI commands."""

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
    with patch("desk.commands.drive.get_credentials") as mock:
        mock.return_value = MagicMock()
        yield mock


@pytest.fixture
def mock_drive_client_class():
    """Mock the DriveClient class."""
    with patch("desk.commands.drive.DriveClient") as mock:
        yield mock


class TestDriveSearch:
    """Tests for desk drive search command."""

    def test_search_with_json_output(self, runner, mock_get_credentials, mock_drive_client_class):
        """Should output JSON when --json flag is used."""
        from desk.commands.drive import drive

        mock_client = MagicMock()
        mock_client.search.return_value = {
            "files": [
                {
                    "id": "file1",
                    "name": "Document.docx",
                    "mimeType": "application/vnd.google-apps.document",
                }
            ]
        }
        mock_drive_client_class.return_value = mock_client

        result = runner.invoke(drive, ["search", "name contains 'Document'", "--json"])

        assert result.exit_code == 0
        output = json.loads(result.output)
        assert "files" in output
        assert len(output["files"]) == 1

    def test_search_no_results(self, runner, mock_get_credentials, mock_drive_client_class):
        """Should handle no results gracefully."""
        from desk.commands.drive import drive

        mock_client = MagicMock()
        mock_client.search.return_value = {"files": []}
        mock_drive_client_class.return_value = mock_client

        result = runner.invoke(drive, ["search", "name contains 'nonexistent'"])

        assert result.exit_code == 0
        assert "No files found" in result.output


class TestDriveRecent:
    """Tests for desk drive recent command."""

    def test_recent_with_json_output(self, runner, mock_get_credentials, mock_drive_client_class):
        """Should output recent files as JSON."""
        from desk.commands.drive import drive

        mock_client = MagicMock()
        mock_client.recent.return_value = {
            "files": [
                {"id": "file1", "name": "Recent.docx"},
                {"id": "file2", "name": "Another.pdf"},
            ]
        }
        mock_drive_client_class.return_value = mock_client

        result = runner.invoke(drive, ["recent", "--json"])

        assert result.exit_code == 0
        output = json.loads(result.output)
        assert len(output["files"]) == 2


class TestDriveRead:
    """Tests for desk drive read command."""

    def test_read_with_json_output(self, runner, mock_get_credentials, mock_drive_client_class):
        """Should output file content as JSON."""
        from desk.commands.drive import drive

        mock_client = MagicMock()
        mock_client.read.return_value = "File content here"
        mock_drive_client_class.return_value = mock_client

        result = runner.invoke(drive, ["read", "file123", "--json"])

        assert result.exit_code == 0
        output = json.loads(result.output)
        assert output["content"] == "File content here"


class TestDriveInfo:
    """Tests for desk drive info command."""

    def test_info_with_json_output(self, runner, mock_get_credentials, mock_drive_client_class):
        """Should output file info as JSON."""
        from desk.commands.drive import drive

        mock_client = MagicMock()
        mock_client.info.return_value = {
            "id": "file123",
            "name": "Document.docx",
            "mimeType": "application/vnd.google-apps.document",
            "modifiedTime": "2024-01-15T10:00:00Z",
            "size": "12345",
        }
        mock_drive_client_class.return_value = mock_client

        result = runner.invoke(drive, ["info", "file123", "--json"])

        assert result.exit_code == 0
        output = json.loads(result.output)
        assert output["id"] == "file123"
        assert output["name"] == "Document.docx"
