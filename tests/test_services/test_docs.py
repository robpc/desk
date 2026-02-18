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


class TestDocsReadTables:
    """Tests for table extraction in DocsClient.read."""

    def _make_paragraph(self, text):
        return {"paragraph": {"elements": [{"textRun": {"content": text}}]}}

    def _make_table(self, rows):
        """Build a Google Docs API table structure from a list of lists of strings."""
        return {
            "table": {
                "tableRows": [
                    {
                        "tableCells": [
                            {"content": [self._make_paragraph(cell)]}
                            for cell in row
                        ]
                    }
                    for row in rows
                ]
            }
        }

    def test_read_table_only_doc(self, mock_credentials):
        """Should extract table content from a doc with only tables."""
        with patch("desk.services.docs.build") as mock_build:
            mock_service = MagicMock()
            mock_build.return_value = mock_service

            documents_mock = mock_service.documents.return_value
            documents_mock.get.return_value.execute.return_value = {
                "documentId": "doc123",
                "title": "Table Doc",
                "body": {
                    "content": [
                        self._make_table([
                            ["Name", "Status"],
                            ["Alice", "Active"],
                            ["Bob", "Inactive"],
                        ])
                    ]
                },
            }

            from desk.services.docs import DocsClient

            client = DocsClient(mock_credentials)
            result = client.read("doc123")

            assert "Name" in result["body"]
            assert "Alice" in result["body"]
            assert "| Name | Status |" in result["body"]
            assert "| --- | --- |" in result["body"]
            assert "| Alice | Active |" in result["body"]

    def test_read_mixed_paragraphs_and_tables(self, mock_credentials):
        """Should preserve both paragraphs and tables."""
        with patch("desk.services.docs.build") as mock_build:
            mock_service = MagicMock()
            mock_build.return_value = mock_service

            documents_mock = mock_service.documents.return_value
            documents_mock.get.return_value.execute.return_value = {
                "documentId": "doc123",
                "title": "Mixed Doc",
                "body": {
                    "content": [
                        self._make_paragraph("Introduction\n"),
                        self._make_table([["Col A", "Col B"], ["1", "2"]]),
                        self._make_paragraph("Conclusion\n"),
                    ]
                },
            }

            from desk.services.docs import DocsClient

            client = DocsClient(mock_credentials)
            result = client.read("doc123")

            body = result["body"]
            assert "Introduction" in body
            assert "| Col A | Col B |" in body
            assert "Conclusion" in body
            # Paragraph before table before paragraph
            assert body.index("Introduction") < body.index("Col A")
            assert body.index("Col A") < body.index("Conclusion")

    def test_read_empty_table(self, mock_credentials):
        """Should handle table with no rows gracefully."""
        with patch("desk.services.docs.build") as mock_build:
            mock_service = MagicMock()
            mock_build.return_value = mock_service

            documents_mock = mock_service.documents.return_value
            documents_mock.get.return_value.execute.return_value = {
                "documentId": "doc123",
                "title": "Empty Table",
                "body": {
                    "content": [{"table": {"tableRows": []}}]
                },
            }

            from desk.services.docs import DocsClient

            client = DocsClient(mock_credentials)
            result = client.read("doc123")
            assert result["body"] == ""

    def test_read_table_with_pipe_in_cell(self, mock_credentials):
        """Should escape pipe characters in cell text."""
        with patch("desk.services.docs.build") as mock_build:
            mock_service = MagicMock()
            mock_build.return_value = mock_service

            documents_mock = mock_service.documents.return_value
            documents_mock.get.return_value.execute.return_value = {
                "documentId": "doc123",
                "title": "Pipe Doc",
                "body": {
                    "content": [
                        self._make_table([
                            ["Command", "Example"],
                            ["grep", "grep foo|bar"],
                        ])
                    ]
                },
            }

            from desk.services.docs import DocsClient

            client = DocsClient(mock_credentials)
            result = client.read("doc123")

            assert "grep foo\\|bar" in result["body"]

    def test_read_table_with_uneven_rows(self, mock_credentials):
        """Should pad shorter rows to match column count."""
        with patch("desk.services.docs.build") as mock_build:
            mock_service = MagicMock()
            mock_build.return_value = mock_service

            documents_mock = mock_service.documents.return_value
            documents_mock.get.return_value.execute.return_value = {
                "documentId": "doc123",
                "title": "Uneven Doc",
                "body": {
                    "content": [
                        {
                            "table": {
                                "tableRows": [
                                    {
                                        "tableCells": [
                                            {"content": [self._make_paragraph("A")]},
                                            {"content": [self._make_paragraph("B")]},
                                            {"content": [self._make_paragraph("C")]},
                                        ]
                                    },
                                    {
                                        "tableCells": [
                                            {"content": [self._make_paragraph("1")]},
                                        ]
                                    },
                                ]
                            }
                        }
                    ]
                },
            }

            from desk.services.docs import DocsClient

            client = DocsClient(mock_credentials)
            result = client.read("doc123")

            lines = result["body"].strip().split("\n")
            # Header should have 3 columns
            assert lines[0].count("|") == 4  # | A | B | C |
            # Data row should also have 3 columns (padded)
            assert lines[2].count("|") == 4  # | 1 |  |  |


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


class TestDocsFindAndReplace:
    """Tests for DocsClient.find_and_replace method."""

    def test_find_and_replace_basic(self, mock_credentials):
        """Should send replaceAllText request and return occurrences changed."""
        with patch("desk.services.docs.build") as mock_build:
            mock_service = MagicMock()
            mock_build.return_value = mock_service

            documents_mock = mock_service.documents.return_value
            documents_mock.batchUpdate.return_value.execute.return_value = {
                "replies": [{"replaceAllText": {"occurrencesChanged": 3}}],
                "documentId": "doc123",
            }

            from desk.services.docs import DocsClient

            client = DocsClient(mock_credentials)
            result = client.find_and_replace("doc123", "old", "new")

            assert result["documentId"] == "doc123"
            assert result["occurrences_changed"] == 3
            assert result["status"] == "ok"

            # Verify the API call structure
            call_kwargs = documents_mock.batchUpdate.call_args
            requests = call_kwargs[1]["body"]["requests"]
            assert len(requests) == 1
            req = requests[0]["replaceAllText"]
            assert req["containsText"]["text"] == "old"
            assert req["containsText"]["matchCase"] is True
            assert req["replaceText"] == "new"

    def test_find_and_replace_case_insensitive(self, mock_credentials):
        """Should pass matchCase=False when match_case is False."""
        with patch("desk.services.docs.build") as mock_build:
            mock_service = MagicMock()
            mock_build.return_value = mock_service

            documents_mock = mock_service.documents.return_value
            documents_mock.batchUpdate.return_value.execute.return_value = {
                "replies": [{"replaceAllText": {"occurrencesChanged": 1}}],
                "documentId": "doc123",
            }

            from desk.services.docs import DocsClient

            client = DocsClient(mock_credentials)
            result = client.find_and_replace("doc123", "OLD", "new", match_case=False)

            call_kwargs = documents_mock.batchUpdate.call_args
            req = call_kwargs[1]["body"]["requests"][0]["replaceAllText"]
            assert req["containsText"]["matchCase"] is False

    def test_find_and_replace_api_error(self, mock_credentials):
        """Should raise RuntimeError on API error."""
        with patch("desk.services.docs.build") as mock_build:
            mock_service = MagicMock()
            mock_build.return_value = mock_service

            documents_mock = mock_service.documents.return_value
            http_error = HttpError(
                resp=MagicMock(status=404),
                content=b'{"error": {"message": "Document not found"}}',
            )
            documents_mock.batchUpdate.return_value.execute.side_effect = http_error

            from desk.services.docs import DocsClient

            client = DocsClient(mock_credentials)
            with pytest.raises(RuntimeError, match="Docs API error"):
                client.find_and_replace("bad_id", "old", "new")


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
