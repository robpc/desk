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

    def test_read_single_file_json(self, runner, mock_get_credentials, mock_drive_client_class):
        """Should output file content as JSON for a single file."""
        from desk.commands.drive import drive

        mock_client = MagicMock()
        mock_client.read.return_value = "File content here"
        mock_drive_client_class.return_value = mock_client

        result = runner.invoke(drive, ["read", "file123", "--json"])

        assert result.exit_code == 0
        output = json.loads(result.output)
        assert output["content"] == "File content here"
        assert output["fileId"] == "file123"

    def test_read_single_file_human(self, runner, mock_get_credentials, mock_drive_client_class):
        """Should output file content as plain text for a single file."""
        from desk.commands.drive import drive

        mock_client = MagicMock()
        mock_client.read.return_value = "Hello from the file"
        mock_drive_client_class.return_value = mock_client

        result = runner.invoke(drive, ["read", "file123"])

        assert result.exit_code == 0
        assert "Hello from the file" in result.output

    def test_read_multiple_files_json(self, runner, mock_get_credentials, mock_drive_client_class):
        """Should output batch JSON for multiple file IDs."""
        from desk.commands.drive import drive

        mock_client = MagicMock()
        mock_client.read.side_effect = ["Content A", "Content B", "Content C"]
        mock_drive_client_class.return_value = mock_client

        result = runner.invoke(drive, ["read", "id1", "id2", "id3", "--json"])

        assert result.exit_code == 0
        output = json.loads(result.output)
        assert isinstance(output, list)
        assert len(output) == 3
        assert output[0]["fileId"] == "id1"
        assert output[0]["content"] == "Content A"
        assert output[2]["fileId"] == "id3"
        assert output[2]["content"] == "Content C"

    def test_read_multiple_files_human(self, runner, mock_get_credentials, mock_drive_client_class):
        """Should output batch content with separators for human output."""
        from desk.commands.drive import drive

        mock_client = MagicMock()
        mock_client.read.side_effect = ["Content A", "Content B"]
        mock_drive_client_class.return_value = mock_client

        result = runner.invoke(drive, ["read", "id1", "id2"])

        assert result.exit_code == 0
        assert "--- id1 ---" in result.output
        assert "Content A" in result.output
        assert "--- id2 ---" in result.output
        assert "Content B" in result.output

    def test_read_multiple_files_with_error(self, runner, mock_get_credentials, mock_drive_client_class):
        """Should report per-file errors in batch mode without stopping."""
        from desk.commands.drive import drive

        mock_client = MagicMock()
        mock_client.read.side_effect = [
            "Content A",
            RuntimeError("File not found"),
            "Content C",
        ]
        mock_drive_client_class.return_value = mock_client

        result = runner.invoke(drive, ["read", "id1", "id2", "id3", "--json"])

        assert result.exit_code == 0
        output = json.loads(result.output)
        assert len(output) == 3
        assert output[0]["content"] == "Content A"
        assert output[1]["error"] is not None
        assert output[1]["content"] is None
        assert output[2]["content"] == "Content C"

    def test_read_stdin(self, runner, mock_get_credentials, mock_drive_client_class):
        """Should read file IDs from stdin with --stdin flag."""
        from desk.commands.drive import drive

        mock_client = MagicMock()
        mock_client.read.side_effect = ["Content from stdin A", "Content from stdin B"]
        mock_drive_client_class.return_value = mock_client

        result = runner.invoke(drive, ["read", "--stdin", "--json"], input="fileA\nfileB\n")

        assert result.exit_code == 0
        output = json.loads(result.output)
        assert isinstance(output, list)
        assert len(output) == 2
        assert output[0]["fileId"] == "fileA"
        assert output[1]["fileId"] == "fileB"

    def test_read_no_ids_errors(self, runner, mock_get_credentials, mock_drive_client_class):
        """Should error when no file IDs are provided."""
        from desk.commands.drive import drive

        result = runner.invoke(drive, ["read", "--json"])

        assert result.exit_code != 0
        output = json.loads(result.output)
        assert output["error"]["code"] == "INVALID_INPUT"

    def test_read_args_and_stdin_combined(self, runner, mock_get_credentials, mock_drive_client_class):
        """Should combine IDs from args and stdin."""
        from desk.commands.drive import drive

        mock_client = MagicMock()
        mock_client.read.side_effect = ["C1", "C2", "C3"]
        mock_drive_client_class.return_value = mock_client

        result = runner.invoke(drive, ["read", "arg_id", "--stdin", "--json"], input="stdin_id1\nstdin_id2\n")

        assert result.exit_code == 0
        output = json.loads(result.output)
        assert len(output) == 3
        assert output[0]["fileId"] == "arg_id"
        assert output[1]["fileId"] == "stdin_id1"
        assert output[2]["fileId"] == "stdin_id2"


class TestDriveListFolder:
    """Tests for desk drive list-folder command."""

    def test_list_folder_json_output(self, runner, mock_get_credentials, mock_drive_client_class):
        """Should output folder contents as JSON."""
        from desk.commands.drive import drive

        mock_client = MagicMock()
        mock_client.list_folder.return_value = {
            "files": [
                {"id": "f1", "name": "Doc.docx", "mimeType": "application/vnd.google-apps.document",
                 "modifiedTime": "2026-01-01T00:00:00Z", "size": "1234"},
                {"id": "f2", "name": "Sheet.xlsx", "mimeType": "application/vnd.google-apps.spreadsheet",
                 "modifiedTime": "2026-01-02T00:00:00Z", "size": "5678"},
            ]
        }
        mock_drive_client_class.return_value = mock_client

        result = runner.invoke(drive, ["list-folder", "folder123", "--json"])

        assert result.exit_code == 0
        output = json.loads(result.output)
        assert "files" in output
        assert len(output["files"]) == 2
        assert output["files"][0]["id"] == "f1"

    def test_list_folder_human_output(self, runner, mock_get_credentials, mock_drive_client_class):
        """Should output folder contents as a table for humans."""
        from desk.commands.drive import drive

        mock_client = MagicMock()
        mock_client.list_folder.return_value = {
            "files": [
                {"id": "f1", "name": "Doc.docx", "mimeType": "application/vnd.google-apps.document",
                 "modifiedTime": "2026-01-01T00:00:00Z"},
            ]
        }
        mock_drive_client_class.return_value = mock_client

        result = runner.invoke(drive, ["list-folder", "folder123"])

        assert result.exit_code == 0
        assert "Doc.docx" in result.output

    def test_list_folder_empty(self, runner, mock_get_credentials, mock_drive_client_class):
        """Should handle empty folder gracefully."""
        from desk.commands.drive import drive

        mock_client = MagicMock()
        mock_client.list_folder.return_value = {"files": []}
        mock_drive_client_class.return_value = mock_client

        result = runner.invoke(drive, ["list-folder", "empty_folder"])

        assert result.exit_code == 0
        assert "No files in folder" in result.output

    def test_list_folder_with_page_token(self, runner, mock_get_credentials, mock_drive_client_class):
        """Should pass page_token to the service and show pagination hint."""
        from desk.commands.drive import drive

        mock_client = MagicMock()
        mock_client.list_folder.return_value = {
            "files": [{"id": "f1", "name": "Doc.docx", "mimeType": "text/plain",
                        "modifiedTime": "2026-01-01T00:00:00Z"}],
            "nextPageToken": "next_token_abc",
        }
        mock_drive_client_class.return_value = mock_client

        result = runner.invoke(drive, ["list-folder", "folder123", "--page-token", "prev_token"])

        assert result.exit_code == 0
        mock_client.list_folder.assert_called_once_with(
            "folder123", max_results=100, page_token="prev_token", file_type=None,
            drive_id=None, my_drive=False,
        )
        assert "next_token_abc" in result.output

    def test_list_folder_with_type_filter(self, runner, mock_get_credentials, mock_drive_client_class):
        """Should pass file_type filter to the service."""
        from desk.commands.drive import drive

        mock_client = MagicMock()
        mock_client.list_folder.return_value = {"files": []}
        mock_drive_client_class.return_value = mock_client

        result = runner.invoke(drive, ["list-folder", "folder123", "--type", "document"])

        assert result.exit_code == 0
        mock_client.list_folder.assert_called_once_with(
            "folder123", max_results=100, page_token=None, file_type="document",
            drive_id=None, my_drive=False,
        )

    def test_list_folder_with_max(self, runner, mock_get_credentials, mock_drive_client_class):
        """Should pass max_results to the service."""
        from desk.commands.drive import drive

        mock_client = MagicMock()
        mock_client.list_folder.return_value = {"files": []}
        mock_drive_client_class.return_value = mock_client

        result = runner.invoke(drive, ["list-folder", "folder123", "--max", "10"])

        assert result.exit_code == 0
        mock_client.list_folder.assert_called_once_with(
            "folder123", max_results=10, page_token=None, file_type=None,
            drive_id=None, my_drive=False,
        )

    def test_list_folder_json_includes_next_page_token(self, runner, mock_get_credentials, mock_drive_client_class):
        """Should include nextPageToken in JSON output."""
        from desk.commands.drive import drive

        mock_client = MagicMock()
        mock_client.list_folder.return_value = {
            "files": [{"id": "f1", "name": "A.txt"}],
            "nextPageToken": "token123",
        }
        mock_drive_client_class.return_value = mock_client

        result = runner.invoke(drive, ["list-folder", "folder123", "--json"])

        assert result.exit_code == 0
        output = json.loads(result.output)
        assert output["nextPageToken"] == "token123"


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


class TestDriveListDrives:
    """Tests for desk drive list-drives command."""

    def test_list_drives_json(self, runner, mock_get_credentials, mock_drive_client_class):
        """Should output JSON with envelope structure {"drives": [...]}."""
        from desk.commands.drive import drive

        mock_client = MagicMock()
        mock_client.list_drives.return_value = {
            "drives": [
                {"id": "drive1", "name": "Engineering", "createdTime": "2026-01-01T00:00:00Z"},
                {"id": "drive2", "name": "Design", "createdTime": "2026-02-01T00:00:00Z"},
            ]
        }
        mock_drive_client_class.return_value = mock_client

        result = runner.invoke(drive, ["list-drives", "--json"])

        assert result.exit_code == 0
        output = json.loads(result.output)
        assert "drives" in output
        assert len(output["drives"]) == 2
        assert output["drives"][0]["name"] == "Engineering"

    def test_list_drives_human(self, runner, mock_get_credentials, mock_drive_client_class):
        """Should output human-readable table."""
        from desk.commands.drive import drive

        mock_client = MagicMock()
        mock_client.list_drives.return_value = {
            "drives": [
                {"id": "drive1", "name": "Engineering", "createdTime": "2026-01-01T00:00:00Z"},
            ]
        }
        mock_drive_client_class.return_value = mock_client

        result = runner.invoke(drive, ["list-drives"])

        assert result.exit_code == 0
        assert "Engineering" in result.output

    def test_list_drives_empty(self, runner, mock_get_credentials, mock_drive_client_class):
        """Should show 'No Shared Drives found.' for empty result."""
        from desk.commands.drive import drive

        mock_client = MagicMock()
        mock_client.list_drives.return_value = {"drives": []}
        mock_drive_client_class.return_value = mock_client

        result = runner.invoke(drive, ["list-drives"])

        assert result.exit_code == 0
        assert "No Shared Drives found." in result.output

    def test_list_drives_with_max(self, runner, mock_get_credentials, mock_drive_client_class):
        """Should pass --max flag through to the service."""
        from desk.commands.drive import drive

        mock_client = MagicMock()
        mock_client.list_drives.return_value = {"drives": []}
        mock_drive_client_class.return_value = mock_client

        result = runner.invoke(drive, ["list-drives", "--max", "10"])

        assert result.exit_code == 0
        mock_client.list_drives.assert_called_once_with(max_results=10, page_token=None)

    def test_list_drives_json_includes_next_page_token(self, runner, mock_get_credentials, mock_drive_client_class):
        """Should include nextPageToken in JSON output when present."""
        from desk.commands.drive import drive

        mock_client = MagicMock()
        mock_client.list_drives.return_value = {
            "drives": [{"id": "drive1", "name": "Eng", "createdTime": "2026-01-01T00:00:00Z"}],
            "nextPageToken": "token_page2",
        }
        mock_drive_client_class.return_value = mock_client

        result = runner.invoke(drive, ["list-drives", "--json"])

        assert result.exit_code == 0
        output = json.loads(result.output)
        assert output["nextPageToken"] == "token_page2"


class TestDriveSearchDriveScope:
    """Tests for --drive-id and --my-drive flags on search."""

    def test_search_with_drive_id(self, runner, mock_get_credentials, mock_drive_client_class):
        """Should pass drive_id to the service."""
        from desk.commands.drive import drive

        mock_client = MagicMock()
        mock_client.search.return_value = {"files": []}
        mock_drive_client_class.return_value = mock_client

        result = runner.invoke(drive, ["search", "test", "--drive-id", "xyz"])

        assert result.exit_code == 0
        mock_client.search.assert_called_once_with(
            "test", max_results=20, page_token=None,
            drive_id="xyz", my_drive=False,
        )

    def test_search_with_my_drive(self, runner, mock_get_credentials, mock_drive_client_class):
        """Should pass my_drive=True to the service."""
        from desk.commands.drive import drive

        mock_client = MagicMock()
        mock_client.search.return_value = {"files": []}
        mock_drive_client_class.return_value = mock_client

        result = runner.invoke(drive, ["search", "test", "--my-drive"])

        assert result.exit_code == 0
        mock_client.search.assert_called_once_with(
            "test", max_results=20, page_token=None,
            drive_id=None, my_drive=True,
        )

    def test_drive_id_and_my_drive_mutual_exclusion(self, runner, mock_get_credentials, mock_drive_client_class):
        """Should produce a structured error when both flags are used."""
        from desk.commands.drive import drive

        result = runner.invoke(drive, ["search", "test", "--drive-id", "xyz", "--my-drive", "--json"])

        assert result.exit_code != 0
        output = json.loads(result.output)
        assert output["error"]["code"] == "INVALID_INPUT"
        assert "mutually exclusive" in output["error"]["message"]
