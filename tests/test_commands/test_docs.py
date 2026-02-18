"""Tests for docs CLI commands."""

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
    with patch("desk.commands.docs.get_credentials") as mock:
        mock.return_value = MagicMock()
        yield mock


@pytest.fixture
def mock_docs_client_class():
    """Mock the DocsClient class."""
    with patch("desk.commands.docs.DocsClient") as mock:
        yield mock


class TestDocsRead:
    """Tests for desk docs read command."""

    def test_read_with_json_output(self, runner, mock_get_credentials, mock_docs_client_class):
        """Should output document content as JSON."""
        from desk.commands.docs import docs

        mock_client = MagicMock()
        mock_client.read.return_value = {
            "documentId": "doc123",
            "title": "Test Document",
            "body": "Document content here",
        }
        mock_docs_client_class.return_value = mock_client

        result = runner.invoke(docs, ["read", "doc123", "--json"])

        assert result.exit_code == 0
        output = json.loads(result.output)
        assert output["documentId"] == "doc123"
        assert output["title"] == "Test Document"


class TestDocsUpdate:
    """Tests for desk docs update command."""

    def test_find_and_replace_json_output(self, runner, mock_get_credentials, mock_docs_client_class):
        """Should output find-and-replace receipt as JSON."""
        from desk.commands.docs import docs

        mock_client = MagicMock()
        mock_client.find_and_replace.return_value = {
            "documentId": "doc123",
            "occurrences_changed": 5,
            "status": "ok",
        }
        mock_docs_client_class.return_value = mock_client

        result = runner.invoke(docs, ["update", "doc123", "new text", "--find", "old text", "--json"])

        assert result.exit_code == 0
        output = json.loads(result.output)
        assert output["success"] is True
        assert output["operation"] == "find_and_replace"
        assert output["changes"]["occurrences_changed"] == 5

    def test_find_with_ignore_case(self, runner, mock_get_credentials, mock_docs_client_class):
        """Should pass match_case=False when --ignore-case is used."""
        from desk.commands.docs import docs

        mock_client = MagicMock()
        mock_client.find_and_replace.return_value = {
            "documentId": "doc123",
            "occurrences_changed": 2,
            "status": "ok",
        }
        mock_docs_client_class.return_value = mock_client

        result = runner.invoke(docs, ["update", "doc123", "new", "--find", "OLD", "--ignore-case", "--json"])

        assert result.exit_code == 0
        mock_client.find_and_replace.assert_called_once_with(
            "doc123", find_text="OLD", replace_text="new", match_case=False
        )

    def test_find_and_mode_conflict(self, runner, mock_get_credentials, mock_docs_client_class):
        """Should error when --find and --mode are both provided."""
        from desk.commands.docs import docs

        result = runner.invoke(docs, ["update", "doc123", "text", "--find", "old", "--mode", "prepend", "--json"])

        assert result.exit_code != 0
        output = json.loads(result.output)
        assert output["success"] is False
        assert "cannot be used together" in output["error"]["message"]


class TestDocsCreate:
    """Tests for desk docs create command."""

    def test_create_document_json_output(self, runner, mock_get_credentials, mock_docs_client_class):
        """Should output created document receipt as JSON."""
        from desk.commands.docs import docs

        mock_client = MagicMock()
        mock_client.create.return_value = {
            "documentId": "doc_id",
            "title": "Title",
            "webViewLink": "https://docs.google.com/document/d/doc_id",
        }
        mock_docs_client_class.return_value = mock_client

        result = runner.invoke(docs, ["create", "Title", "--json"])

        assert result.exit_code == 0
        output = json.loads(result.output)
        # CLI outputs operation receipt, not raw API response
        assert output["success"] is True
        assert output["operation"] == "create"


class TestDocsInsert:
    """Tests for desk docs insert command."""

    def test_insert_at_end(self, runner, mock_get_credentials, mock_docs_client_class):
        """Should insert text at end of document."""
        from desk.commands.docs import docs

        mock_client = MagicMock()
        mock_client.insert_at.return_value = {"documentId": "doc123", "status": "ok"}
        mock_docs_client_class.return_value = mock_client

        result = runner.invoke(docs, ["insert", "doc123", "Hello", "--at", "end", "--json"])

        assert result.exit_code == 0
        output = json.loads(result.output)
        assert output["success"] is True
        assert output["operation"] == "insert"
        mock_client.insert_at.assert_called_once_with("doc123", "Hello", index=None)

    def test_insert_at_index(self, runner, mock_get_credentials, mock_docs_client_class):
        """Should insert text at specific index."""
        from desk.commands.docs import docs

        mock_client = MagicMock()
        mock_client.insert_at.return_value = {"documentId": "doc123", "status": "ok"}
        mock_docs_client_class.return_value = mock_client

        result = runner.invoke(docs, ["insert", "doc123", "Hello", "--at", "5", "--json"])

        assert result.exit_code == 0
        mock_client.insert_at.assert_called_once_with("doc123", "Hello", index=5)


class TestDocsDeleteRange:
    """Tests for desk docs delete-range command."""

    def test_delete_range(self, runner, mock_get_credentials, mock_docs_client_class):
        """Should delete content in range."""
        from desk.commands.docs import docs

        mock_client = MagicMock()
        mock_client.delete_range.return_value = {"documentId": "doc123", "status": "ok"}
        mock_docs_client_class.return_value = mock_client

        result = runner.invoke(
            docs, ["delete-range", "doc123", "--start", "5", "--end", "20", "--json"]
        )

        assert result.exit_code == 0
        output = json.loads(result.output)
        assert output["success"] is True
        mock_client.delete_range.assert_called_once_with("doc123", 5, 20)

    def test_delete_range_invalid(self, runner, mock_get_credentials, mock_docs_client_class):
        """Should error when start >= end."""
        from desk.commands.docs import docs

        result = runner.invoke(
            docs, ["delete-range", "doc123", "--start", "20", "--end", "5", "--json"]
        )

        assert result.exit_code != 0
        output = json.loads(result.output)
        assert output["success"] is False


class TestDocsStyle:
    """Tests for desk docs style command."""

    def test_bold_style(self, runner, mock_get_credentials, mock_docs_client_class):
        """Should apply bold style."""
        from desk.commands.docs import docs

        mock_client = MagicMock()
        mock_client.update_text_style.return_value = {"documentId": "doc123", "status": "ok"}
        mock_docs_client_class.return_value = mock_client

        result = runner.invoke(
            docs, ["style", "doc123", "--start", "1", "--end", "10", "--bold", "--json"]
        )

        assert result.exit_code == 0
        output = json.loads(result.output)
        assert output["success"] is True
        assert output["changes"]["bold"] is True

    def test_style_receipt_includes_applied_styles(
        self, runner, mock_get_credentials, mock_docs_client_class
    ):
        """Receipt should include which styles were applied."""
        from desk.commands.docs import docs

        mock_client = MagicMock()
        mock_client.update_text_style.return_value = {"documentId": "doc123", "status": "ok"}
        mock_docs_client_class.return_value = mock_client

        result = runner.invoke(
            docs,
            ["style", "doc123", "--start", "1", "--end", "10", "--bold", "--italic", "--font-size", "14", "--json"],
        )

        assert result.exit_code == 0
        output = json.loads(result.output)
        assert output["changes"]["bold"] is True
        assert output["changes"]["italic"] is True
        assert output["changes"]["font_size"] == 14.0


class TestDocsInspect:
    """Tests for desk docs inspect command."""

    def test_inspect_json(self, runner, mock_get_credentials, mock_docs_client_class):
        """Should output document structure as JSON."""
        from desk.commands.docs import docs

        mock_client = MagicMock()
        mock_client.inspect.return_value = {
            "documentId": "doc123",
            "title": "Test",
            "endIndex": 50,
            "elements": [
                {"type": "paragraph", "startIndex": 1, "endIndex": 15, "style": "HEADING_1", "text": "Hello"},
            ],
        }
        mock_docs_client_class.return_value = mock_client

        result = runner.invoke(docs, ["inspect", "doc123", "--json"])

        assert result.exit_code == 0
        output = json.loads(result.output)
        assert output["title"] == "Test"
        assert len(output["elements"]) == 1


class TestDocsWriteMarkdown:
    """Tests for desk docs write-markdown command."""

    def test_write_markdown_body(self, runner, mock_get_credentials, mock_docs_client_class):
        """Should write markdown from --body flag."""
        from desk.commands.docs import docs

        mock_client = MagicMock()
        mock_client.write_markdown.return_value = {"documentId": "doc123", "status": "ok"}
        mock_docs_client_class.return_value = mock_client

        result = runner.invoke(
            docs, ["write-markdown", "doc123", "--body", "# Hello", "--json"]
        )

        assert result.exit_code == 0
        output = json.loads(result.output)
        assert output["success"] is True
        assert output["operation"] == "write_markdown"


class TestDocsInsertTable:
    """Tests for desk docs insert-table command."""

    def test_insert_table(self, runner, mock_get_credentials, mock_docs_client_class):
        """Should insert table."""
        from desk.commands.docs import docs

        mock_client = MagicMock()
        mock_client.insert_table.return_value = {"documentId": "doc123", "status": "ok"}
        mock_docs_client_class.return_value = mock_client

        result = runner.invoke(
            docs, ["insert-table", "doc123", "--rows", "3", "--cols", "4", "--at", "end", "--json"]
        )

        assert result.exit_code == 0
        output = json.loads(result.output)
        assert output["success"] is True
        mock_client.insert_table.assert_called_once_with("doc123", 3, 4, index=None)

    def test_insert_table_invalid_rows(self, runner, mock_get_credentials, mock_docs_client_class):
        """Should error when rows < 1."""
        from desk.commands.docs import docs

        result = runner.invoke(
            docs, ["insert-table", "doc123", "--rows", "0", "--cols", "2", "--json"]
        )

        assert result.exit_code != 0
        output = json.loads(result.output)
        assert output["success"] is False
        assert output["error"]["code"] == "INVALID_INPUT"

    def test_insert_table_invalid_cols(self, runner, mock_get_credentials, mock_docs_client_class):
        """Should error when cols < 1."""
        from desk.commands.docs import docs

        result = runner.invoke(
            docs, ["insert-table", "doc123", "--rows", "2", "--cols", "-1", "--json"]
        )

        assert result.exit_code != 0
        output = json.loads(result.output)
        assert output["success"] is False


class TestDocsParagraphStyle:
    """Tests for desk docs paragraph-style command."""

    def test_heading_style(self, runner, mock_get_credentials, mock_docs_client_class):
        """Should apply heading style."""
        from desk.commands.docs import docs

        mock_client = MagicMock()
        mock_client.update_paragraph_style.return_value = {"documentId": "doc123", "status": "ok"}
        mock_docs_client_class.return_value = mock_client

        result = runner.invoke(
            docs, ["paragraph-style", "doc123", "--start", "1", "--end", "20", "--heading", "2", "--json"]
        )

        assert result.exit_code == 0
        output = json.loads(result.output)
        assert output["success"] is True
        assert output["changes"]["heading"] == 2
        mock_client.update_paragraph_style.assert_called_once_with(
            "doc123", 1, 20, heading=2, alignment=None
        )

    def test_alignment_style(self, runner, mock_get_credentials, mock_docs_client_class):
        """Should apply alignment."""
        from desk.commands.docs import docs

        mock_client = MagicMock()
        mock_client.update_paragraph_style.return_value = {"documentId": "doc123", "status": "ok"}
        mock_docs_client_class.return_value = mock_client

        result = runner.invoke(
            docs, ["paragraph-style", "doc123", "--start", "1", "--end", "50", "--alignment", "CENTER", "--json"]
        )

        assert result.exit_code == 0
        output = json.loads(result.output)
        assert output["changes"]["alignment"] == "CENTER"

    def test_heading_out_of_range(self, runner, mock_get_credentials, mock_docs_client_class):
        """Should error when heading > 6."""
        from desk.commands.docs import docs

        result = runner.invoke(
            docs, ["paragraph-style", "doc123", "--start", "1", "--end", "20", "--heading", "99", "--json"]
        )

        assert result.exit_code != 0
        output = json.loads(result.output)
        assert output["success"] is False
        assert output["error"]["code"] == "INVALID_INPUT"

    def test_heading_negative(self, runner, mock_get_credentials, mock_docs_client_class):
        """Should error when heading < 0."""
        from desk.commands.docs import docs

        result = runner.invoke(
            docs, ["paragraph-style", "doc123", "--start", "1", "--end", "20", "--heading", "-1", "--json"]
        )

        assert result.exit_code != 0
        output = json.loads(result.output)
        assert output["success"] is False


class TestDocsInsertImage:
    """Tests for desk docs insert-image command."""

    def test_insert_image_at_end(self, runner, mock_get_credentials, mock_docs_client_class):
        """Should insert image at end of document."""
        from desk.commands.docs import docs

        mock_client = MagicMock()
        mock_client.insert_image.return_value = {"documentId": "doc123", "status": "ok"}
        mock_docs_client_class.return_value = mock_client

        result = runner.invoke(
            docs, ["insert-image", "doc123", "--uri", "https://example.com/img.png", "--at", "end", "--json"]
        )

        assert result.exit_code == 0
        output = json.loads(result.output)
        assert output["success"] is True
        assert output["operation"] == "insert_image"
        assert output["changes"]["uri"] == "https://example.com/img.png"
        mock_client.insert_image.assert_called_once_with(
            "doc123", "https://example.com/img.png", index=None, width=None, height=None
        )

    def test_insert_image_at_index_with_size(self, runner, mock_get_credentials, mock_docs_client_class):
        """Should insert image at specific index with dimensions."""
        from desk.commands.docs import docs

        mock_client = MagicMock()
        mock_client.insert_image.return_value = {"documentId": "doc123", "status": "ok"}
        mock_docs_client_class.return_value = mock_client

        result = runner.invoke(
            docs,
            ["insert-image", "doc123", "--uri", "https://example.com/img.png",
             "--at", "5", "--width", "200", "--height", "100", "--json"],
        )

        assert result.exit_code == 0
        mock_client.insert_image.assert_called_once_with(
            "doc123", "https://example.com/img.png", index=5, width=200.0, height=100.0
        )


class TestParseAt:
    """Tests for _parse_at edge cases."""

    def test_parse_at_invalid_string(self, runner, mock_get_credentials, mock_docs_client_class):
        """Should error with structured JSON for non-integer --at."""
        from desk.commands.docs import docs

        result = runner.invoke(
            docs, ["insert", "doc123", "Hello", "--at", "abc", "--json"]
        )

        assert result.exit_code != 0
        output = json.loads(result.output)
        assert output["success"] is False
        assert output["error"]["code"] == "INVALID_INPUT"

    def test_parse_at_zero(self, runner, mock_get_credentials, mock_docs_client_class):
        """Should error when --at is 0 (indices are 1-based)."""
        from desk.commands.docs import docs

        result = runner.invoke(
            docs, ["insert", "doc123", "Hello", "--at", "0", "--json"]
        )

        assert result.exit_code != 0
        output = json.loads(result.output)
        assert output["success"] is False
        assert output["error"]["code"] == "INDEX_OUT_OF_RANGE"

    def test_parse_at_negative(self, runner, mock_get_credentials, mock_docs_client_class):
        """Should error when --at is negative."""
        from desk.commands.docs import docs

        result = runner.invoke(
            docs, ["insert", "doc123", "Hello", "--at", "-5", "--json"]
        )

        assert result.exit_code != 0
        output = json.loads(result.output)
        assert output["success"] is False
