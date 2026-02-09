"""Tests for Docs service client."""

import pytest
from unittest.mock import MagicMock, patch

from googleapiclient.errors import HttpError


class TestDocsClientInit:
    """Tests for DocsClient initialization."""

    def test_creates_only_docs_service_on_init(self, mock_credentials):
        """Should only create Docs service on init; Drive is lazy."""
        with patch("desk.services.docs.build") as mock_build:
            mock_build.return_value = MagicMock()
            from desk.services.docs import DocsClient

            client = DocsClient(mock_credentials)

            # Only Docs service created eagerly
            assert mock_build.call_count == 1
            assert mock_build.call_args_list[0][0] == ("docs", "v1")

    def test_drive_service_created_lazily_on_first_access(self, mock_credentials):
        """Drive service should be created on first access to _drive property."""
        with patch("desk.services.docs.build") as mock_build:
            mock_build.return_value = MagicMock()
            from desk.services.docs import DocsClient

            client = DocsClient(mock_credentials)
            assert mock_build.call_count == 1

            # Access _drive triggers Drive build
            _ = client._drive
            assert mock_build.call_count == 2
            assert mock_build.call_args_list[1][0] == ("drive", "v3")

            # Second access should not trigger another build
            _ = client._drive
            assert mock_build.call_count == 2


class TestDocsRead:
    """Tests for DocsClient.read method."""

    def test_read_returns_document_content(self, mock_credentials):
        """Should return document content."""
        with patch("desk.services.docs.build") as mock_build:
            mock_service = MagicMock()
            mock_build.return_value = mock_service

            documents_mock = mock_service.documents.return_value
            documents_mock.get.return_value.execute.return_value = {
                "documentId": "doc123",
                "title": "Test Document",
                "body": {
                    "content": [
                        {"paragraph": {"elements": [{"textRun": {"content": "Hello World\n"}}]}},
                    ]
                },
            }

            from desk.services.docs import DocsClient

            client = DocsClient(mock_credentials)
            result = client.read("doc123")

            assert "documentId" in result
            assert result["title"] == "Test Document"

    def test_read_does_not_build_drive_service(self, mock_credentials):
        """read() should not trigger Drive service creation."""
        with patch("desk.services.docs.build") as mock_build:
            mock_service = MagicMock()
            mock_build.return_value = mock_service

            documents_mock = mock_service.documents.return_value
            documents_mock.get.return_value.execute.return_value = {
                "documentId": "doc123",
                "title": "Test",
                "body": {"content": []},
            }

            from desk.services.docs import DocsClient

            client = DocsClient(mock_credentials)
            client.read("doc123")

            # Only Docs build, no Drive build
            assert mock_build.call_count == 1

    def test_read_not_found_raises_error(self, mock_credentials):
        """Should raise error when document not found."""
        with patch("desk.services.docs.build") as mock_build:
            mock_service = MagicMock()
            mock_build.return_value = mock_service

            documents_mock = mock_service.documents.return_value
            http_error = HttpError(
                resp=MagicMock(status=404),
                content=b'{"error": {"message": "Document not found"}}'
            )
            documents_mock.get.return_value.execute.side_effect = http_error

            from desk.services.docs import DocsClient

            client = DocsClient(mock_credentials)
            with pytest.raises(RuntimeError, match="Docs API error"):
                client.read("nonexistent_id")


class TestDocsCreate:
    """Tests for DocsClient.create method."""

    def test_create_returns_document(self, mock_credentials):
        """Should return created document."""
        with patch("desk.services.docs.build") as mock_build:
            mock_service = MagicMock()
            mock_build.return_value = mock_service

            documents_mock = mock_service.documents.return_value
            documents_mock.create.return_value.execute.return_value = {
                "documentId": "new_doc_id",
                "title": "New Document",
            }

            from desk.services.docs import DocsClient

            client = DocsClient(mock_credentials)
            result = client.create("New Document")

            assert result["documentId"] == "new_doc_id"
            assert result["title"] == "New Document"
            documents_mock.create.assert_called_once()

    def test_create_triggers_drive_build(self, mock_credentials):
        """create() needs Drive for webViewLink, so it should build Drive."""
        with patch("desk.services.docs.build") as mock_build:
            mock_service = MagicMock()
            mock_build.return_value = mock_service

            documents_mock = mock_service.documents.return_value
            documents_mock.create.return_value.execute.return_value = {
                "documentId": "new_doc_id",
                "title": "New Document",
            }

            from desk.services.docs import DocsClient

            client = DocsClient(mock_credentials)
            assert mock_build.call_count == 1  # Only Docs

            client.create("New Document")

            # Docs + Drive = 2 builds
            assert mock_build.call_count == 2


class TestDocsUpdate:
    """Tests for DocsClient.update method."""

    def test_update_appends_text(self, mock_credentials):
        """Should batch update document with text append."""
        with patch("desk.services.docs.build") as mock_build:
            mock_service = MagicMock()
            mock_build.return_value = mock_service

            documents_mock = mock_service.documents.return_value
            # Mock get to return document structure for finding end index
            documents_mock.get.return_value.execute.return_value = {
                "documentId": "doc123",
                "body": {"content": [{"endIndex": 10}]},
            }
            documents_mock.batchUpdate.return_value.execute.return_value = {
                "replies": [],
                "documentId": "doc123",
            }

            from desk.services.docs import DocsClient

            client = DocsClient(mock_credentials)
            result = client.update("doc123", text="New text to append")

            documents_mock.batchUpdate.assert_called_once()

    def test_update_replaces_text(self, mock_credentials):
        """Should replace all document content when mode=replace."""
        with patch("desk.services.docs.build") as mock_build:
            mock_service = MagicMock()
            mock_build.return_value = mock_service

            documents_mock = mock_service.documents.return_value
            documents_mock.get.return_value.execute.return_value = {
                "documentId": "doc123",
                "body": {"content": [{"endIndex": 50}]},
            }
            documents_mock.batchUpdate.return_value.execute.return_value = {
                "replies": [],
                "documentId": "doc123",
            }

            from desk.services.docs import DocsClient

            client = DocsClient(mock_credentials)
            result = client.update("doc123", text="New content", mode="replace")

            documents_mock.batchUpdate.assert_called_once()
