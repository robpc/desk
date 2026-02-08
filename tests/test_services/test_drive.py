"""Tests for Drive service client."""

import pytest
from unittest.mock import MagicMock, patch

from googleapiclient.errors import HttpError


class TestDriveClientInit:
    """Tests for DriveClient initialization."""

    def test_creates_service_with_credentials(self, mock_credentials):
        """Should create Drive service with provided credentials."""
        with patch("desk.services.drive.build") as mock_build:
            mock_build.return_value = MagicMock()
            from desk.services.drive import DriveClient

            client = DriveClient(mock_credentials)

            mock_build.assert_called_once_with("drive", "v3", credentials=mock_credentials)


class TestDriveSearch:
    """Tests for DriveClient.search method."""

    def test_search_returns_files(self, mock_credentials):
        """Should return list of files matching query."""
        with patch("desk.services.drive.build") as mock_build:
            mock_service = MagicMock()
            mock_build.return_value = mock_service

            files_mock = mock_service.files.return_value
            files_mock.list.return_value.execute.return_value = {
                "files": [
                    {"id": "file1", "name": "Report.docx"},
                    {"id": "file2", "name": "Data.xlsx"},
                ]
            }

            from desk.services.drive import DriveClient

            client = DriveClient(mock_credentials)
            result = client.search("name contains 'Report'")

            assert "files" in result
            assert len(result["files"]) == 2

    def test_search_with_max_results(self, mock_credentials):
        """Should pass max_results as pageSize to API."""
        with patch("desk.services.drive.build") as mock_build:
            mock_service = MagicMock()
            mock_build.return_value = mock_service

            files_mock = mock_service.files.return_value
            files_mock.list.return_value.execute.return_value = {"files": []}

            from desk.services.drive import DriveClient

            client = DriveClient(mock_credentials)
            client.search("name contains 'test'", max_results=10)

            call_kwargs = files_mock.list.call_args[1]
            assert call_kwargs["pageSize"] == 10

    def test_search_api_error_raises_runtime_error(self, mock_credentials):
        """Should raise RuntimeError on API error."""
        with patch("desk.services.drive.build") as mock_build:
            mock_service = MagicMock()
            mock_build.return_value = mock_service

            files_mock = mock_service.files.return_value
            http_error = HttpError(
                resp=MagicMock(status=400),
                content=b'{"error": {"message": "Invalid query"}}'
            )
            files_mock.list.return_value.execute.side_effect = http_error

            from desk.services.drive import DriveClient

            client = DriveClient(mock_credentials)
            with pytest.raises(RuntimeError, match="Drive API error"):
                client.search("invalid:query")


class TestDriveInfo:
    """Tests for DriveClient.info method."""

    def test_info_returns_file_metadata(self, mock_credentials):
        """Should return detailed file metadata."""
        with patch("desk.services.drive.build") as mock_build:
            mock_service = MagicMock()
            mock_build.return_value = mock_service

            files_mock = mock_service.files.return_value
            files_mock.get.return_value.execute.return_value = {
                "id": "file123",
                "name": "Document.docx",
                "mimeType": "application/vnd.google-apps.document",
            }

            from desk.services.drive import DriveClient

            client = DriveClient(mock_credentials)
            result = client.info("file123")

            assert result["id"] == "file123"
            assert result["name"] == "Document.docx"


class TestDriveRecent:
    """Tests for DriveClient.recent method."""

    def test_recent_returns_files(self, mock_credentials):
        """Should return list of recently modified files."""
        with patch("desk.services.drive.build") as mock_build:
            mock_service = MagicMock()
            mock_build.return_value = mock_service

            files_mock = mock_service.files.return_value
            files_mock.list.return_value.execute.return_value = {
                "files": [
                    {"id": "file1", "name": "Recent1.docx"},
                    {"id": "file2", "name": "Recent2.docx"},
                ]
            }

            from desk.services.drive import DriveClient

            client = DriveClient(mock_credentials)
            result = client.recent()

            assert "files" in result
            assert len(result["files"]) == 2


class TestDriveTrash:
    """Tests for DriveClient trash operations."""

    def test_trash_updates_file(self, mock_credentials):
        """Should update file with trashed=True."""
        with patch("desk.services.drive.build") as mock_build:
            mock_service = MagicMock()
            mock_build.return_value = mock_service

            files_mock = mock_service.files.return_value
            files_mock.update.return_value.execute.return_value = {"id": "file123"}

            from desk.services.drive import DriveClient

            client = DriveClient(mock_credentials)
            client.trash("file123")

            files_mock.update.assert_called_once()
            call_kwargs = files_mock.update.call_args[1]
            assert call_kwargs["body"]["trashed"] is True

    def test_untrash_updates_file(self, mock_credentials):
        """Should update file with trashed=False."""
        with patch("desk.services.drive.build") as mock_build:
            mock_service = MagicMock()
            mock_build.return_value = mock_service

            files_mock = mock_service.files.return_value
            files_mock.update.return_value.execute.return_value = {"id": "file123"}

            from desk.services.drive import DriveClient

            client = DriveClient(mock_credentials)
            client.untrash("file123")

            call_kwargs = files_mock.update.call_args[1]
            assert call_kwargs["body"]["trashed"] is False


class TestDriveStar:
    """Tests for DriveClient star operations."""

    def test_star_updates_file(self, mock_credentials):
        """Should update file with starred=True."""
        with patch("desk.services.drive.build") as mock_build:
            mock_service = MagicMock()
            mock_build.return_value = mock_service

            files_mock = mock_service.files.return_value
            files_mock.update.return_value.execute.return_value = {"id": "file123"}

            from desk.services.drive import DriveClient

            client = DriveClient(mock_credentials)
            client.star("file123")

            call_kwargs = files_mock.update.call_args[1]
            assert call_kwargs["body"]["starred"] is True


class TestDriveShare:
    """Tests for DriveClient.share method."""

    def test_share_creates_permission(self, mock_credentials):
        """Should create permission for email."""
        with patch("desk.services.drive.build") as mock_build:
            mock_service = MagicMock()
            mock_build.return_value = mock_service

            permissions_mock = mock_service.permissions.return_value
            permissions_mock.create.return_value.execute.return_value = {
                "id": "perm123",
                "role": "reader",
            }

            from desk.services.drive import DriveClient

            client = DriveClient(mock_credentials)
            client.share("file123", "user@example.com", role="reader")

            permissions_mock.create.assert_called_once()
            call_kwargs = permissions_mock.create.call_args[1]
            assert call_kwargs["body"]["emailAddress"] == "user@example.com"
            assert call_kwargs["body"]["role"] == "reader"
