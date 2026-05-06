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
            "doc123", find_text="OLD", replace_text="new", match_case=False, tab_id=None
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

    def test_create_with_body_uses_markdown_by_default(self, runner, mock_get_credentials, mock_docs_client_class):
        """Should pass markdown=True by default when body is provided."""
        from desk.commands.docs import docs

        mock_client = MagicMock()
        mock_client.create.return_value = {
            "documentId": "doc_id",
            "title": "Title",
            "webViewLink": "https://docs.google.com/document/d/doc_id",
        }
        mock_docs_client_class.return_value = mock_client

        result = runner.invoke(docs, ["create", "Title", "--body", "# Hello", "--json"])

        assert result.exit_code == 0
        mock_client.create.assert_called_once_with("Title", body="# Hello", markdown=True)

    def test_create_with_plain_flag(self, runner, mock_get_credentials, mock_docs_client_class):
        """Should pass markdown=False when --plain is used."""
        from desk.commands.docs import docs

        mock_client = MagicMock()
        mock_client.create.return_value = {
            "documentId": "doc_id",
            "title": "Title",
            "webViewLink": "https://docs.google.com/document/d/doc_id",
        }
        mock_docs_client_class.return_value = mock_client

        result = runner.invoke(docs, ["create", "Title", "--body", "plain text", "--plain", "--json"])

        assert result.exit_code == 0
        mock_client.create.assert_called_once_with("Title", body="plain text", markdown=False)

    def test_create_with_file(self, runner, mock_get_credentials, mock_docs_client_class, tmp_path):
        """Should read content from file."""
        from desk.commands.docs import docs

        md_file = tmp_path / "test.md"
        md_file.write_text("# From File")

        mock_client = MagicMock()
        mock_client.create.return_value = {
            "documentId": "doc_id",
            "title": "Title",
            "webViewLink": "https://docs.google.com/document/d/doc_id",
        }
        mock_docs_client_class.return_value = mock_client

        result = runner.invoke(docs, ["create", "Title", "--file", str(md_file), "--json"])

        assert result.exit_code == 0
        mock_client.create.assert_called_once_with("Title", body="# From File", markdown=True)

    def test_create_no_body_creates_empty_doc(self, runner, mock_get_credentials, mock_docs_client_class):
        """Should create empty doc when no content is provided."""
        from desk.commands.docs import docs

        mock_client = MagicMock()
        mock_client.create.return_value = {
            "documentId": "doc_id",
            "title": "Empty",
            "webViewLink": "https://docs.google.com/document/d/doc_id",
        }
        mock_docs_client_class.return_value = mock_client

        result = runner.invoke(docs, ["create", "Empty", "--json"])

        assert result.exit_code == 0
        mock_client.create.assert_called_once_with("Empty", body="", markdown=True)

    def test_create_empty_body_creates_empty_doc(self, runner, mock_get_credentials, mock_docs_client_class):
        """Should create empty doc when --body is empty string."""
        from desk.commands.docs import docs

        mock_client = MagicMock()
        mock_client.create.return_value = {
            "documentId": "doc_id",
            "title": "Empty",
            "webViewLink": "https://docs.google.com/document/d/doc_id",
        }
        mock_docs_client_class.return_value = mock_client

        result = runner.invoke(docs, ["create", "Empty", "--body", "", "--json"])

        assert result.exit_code == 0
        mock_client.create.assert_called_once_with("Empty", body="", markdown=True)

    def test_create_body_and_file_conflict(self, runner, mock_get_credentials, mock_docs_client_class, tmp_path):
        """Should error when both --body and --file are provided."""
        from desk.commands.docs import docs

        md_file = tmp_path / "test.md"
        md_file.write_text("# From File")

        result = runner.invoke(
            docs, ["create", "Title", "--body", "inline", "--file", str(md_file), "--json"]
        )

        assert result.exit_code != 0


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
        mock_client.insert_at.assert_called_once_with("doc123", "Hello", index=None, tab_id=None)

    def test_insert_at_index(self, runner, mock_get_credentials, mock_docs_client_class):
        """Should insert text at specific index."""
        from desk.commands.docs import docs

        mock_client = MagicMock()
        mock_client.insert_at.return_value = {"documentId": "doc123", "status": "ok"}
        mock_docs_client_class.return_value = mock_client

        result = runner.invoke(docs, ["insert", "doc123", "Hello", "--at", "5", "--json"])

        assert result.exit_code == 0
        mock_client.insert_at.assert_called_once_with("doc123", "Hello", index=5, tab_id=None)


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
        mock_client.delete_range.assert_called_once_with("doc123", 5, 20, tab_id=None)

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

    def test_write_markdown_with_spacing_flags(
        self, runner, mock_get_credentials, mock_docs_client_class
    ):
        """Should plumb spacing flags through to write_markdown."""
        from desk.commands.docs import docs

        mock_client = MagicMock()
        mock_client.write_markdown.return_value = {"documentId": "doc123", "status": "ok"}
        mock_docs_client_class.return_value = mock_client

        result = runner.invoke(
            docs, [
                "write-markdown", "doc123",
                "--body", "Hello.\n\nWorld.",
                "--space-below", "8",
                "--line-spacing", "115",
                "--json",
            ],
        )

        assert result.exit_code == 0
        output = json.loads(result.output)
        assert output["changes"]["space_below"] == 8
        assert output["changes"]["line_spacing"] == 115
        kwargs = mock_client.write_markdown.call_args.kwargs
        assert kwargs["space_below"] == 8
        assert kwargs["line_spacing"] == 115

    def test_write_markdown_invalid_spacing_value(
        self, runner, mock_get_credentials, mock_docs_client_class
    ):
        """Should surface ValueError from service as INVALID_INPUT."""
        from desk.commands.docs import docs

        mock_client = MagicMock()
        mock_client.write_markdown.side_effect = ValueError("space_below must be >= 0")
        mock_docs_client_class.return_value = mock_client

        result = runner.invoke(
            docs, [
                "write-markdown", "doc123",
                "--body", "Hello.",
                "--space-below", "-3",
                "--json",
            ],
        )

        assert result.exit_code != 0
        output = json.loads(result.output)
        assert output["success"] is False
        assert output["error"]["code"] == "INVALID_INPUT"


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
        mock_client.insert_table.assert_called_once_with("doc123", 3, 4, index=None, tab_id=None)

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
            "doc123", 1, 20,
            heading=2, alignment=None,
            space_above=None, space_below=None, line_spacing=None,
            indent_start=None, indent_end=None, indent_first_line=None,
            tab_id=None,
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

    def test_spacing_flags(self, runner, mock_get_credentials, mock_docs_client_class):
        """Should pass spacing/indent flags to update_paragraph_style."""
        from desk.commands.docs import docs

        mock_client = MagicMock()
        mock_client.update_paragraph_style.return_value = {"documentId": "doc123", "status": "ok"}
        mock_docs_client_class.return_value = mock_client

        result = runner.invoke(
            docs, [
                "paragraph-style", "doc123",
                "--start", "1", "--end", "99",
                "--space-above", "4",
                "--space-below", "8",
                "--line-spacing", "115",
                "--indent-first-line", "24",
                "--json",
            ],
        )

        assert result.exit_code == 0
        output = json.loads(result.output)
        assert output["changes"]["space_above"] == 4
        assert output["changes"]["space_below"] == 8
        assert output["changes"]["line_spacing"] == 115
        assert output["changes"]["indent_first_line"] == 24
        kwargs = mock_client.update_paragraph_style.call_args.kwargs
        assert kwargs["space_above"] == 4
        assert kwargs["space_below"] == 8
        assert kwargs["line_spacing"] == 115
        assert kwargs["indent_first_line"] == 24

    def test_invalid_spacing_value(self, runner, mock_get_credentials, mock_docs_client_class):
        """Should surface ValueError from service as INVALID_INPUT."""
        from desk.commands.docs import docs

        mock_client = MagicMock()
        mock_client.update_paragraph_style.side_effect = ValueError("space_below must be >= 0")
        mock_docs_client_class.return_value = mock_client

        result = runner.invoke(
            docs, [
                "paragraph-style", "doc123",
                "--start", "1", "--end", "10",
                "--space-below", "-5",
                "--json",
            ],
        )

        assert result.exit_code != 0
        output = json.loads(result.output)
        assert output["success"] is False
        assert output["error"]["code"] == "INVALID_INPUT"


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
            "doc123", "https://example.com/img.png", index=None, width=None, height=None, tab_id=None
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
            "doc123", "https://example.com/img.png", index=5, width=200.0, height=100.0, tab_id=None
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


class TestDocsListTabs:
    """Tests for desk docs list-tabs command."""

    def test_list_tabs_json(self, runner, mock_get_credentials, mock_docs_client_class):
        """Should output tab list as JSON."""
        from desk.commands.docs import docs

        mock_client = MagicMock()
        mock_client.list_tabs.return_value = [
            {"tabId": "t.0", "title": "Tab 1", "index": 0, "parentTabId": None},
            {"tabId": "t.1", "title": "Tab 2", "index": 1, "parentTabId": None},
        ]
        mock_docs_client_class.return_value = mock_client

        result = runner.invoke(docs, ["list-tabs", "doc123", "--json"])

        assert result.exit_code == 0
        output = json.loads(result.output)
        assert len(output) == 2
        assert output[0]["tabId"] == "t.0"
        assert output[1]["title"] == "Tab 2"


class TestDocsAddTab:
    """Tests for desk docs add-tab command."""

    def test_add_tab(self, runner, mock_get_credentials, mock_docs_client_class):
        """Should create a new tab."""
        from desk.commands.docs import docs

        mock_client = MagicMock()
        mock_client.add_tab.return_value = {"tabId": "t.new", "title": "Notes"}
        mock_docs_client_class.return_value = mock_client

        result = runner.invoke(docs, ["add-tab", "doc123", "--title", "Notes", "--json"])

        assert result.exit_code == 0
        output = json.loads(result.output)
        assert output["success"] is True
        assert output["operation"] == "add-tab"
        assert output["undo"]["available"] is True
        assert "delete-tab" in output["undo"]["command"]
        mock_client.add_tab.assert_called_once_with("doc123", "Notes", index=None, parent_tab_id=None)

    def test_add_tab_with_index_and_parent(self, runner, mock_get_credentials, mock_docs_client_class):
        """Should pass index and parent to service."""
        from desk.commands.docs import docs

        mock_client = MagicMock()
        mock_client.add_tab.return_value = {"tabId": "t.child", "title": "Sub"}
        mock_docs_client_class.return_value = mock_client

        result = runner.invoke(
            docs, ["add-tab", "doc123", "--title", "Sub", "--index", "2", "--parent", "t.0", "--json"]
        )

        assert result.exit_code == 0
        mock_client.add_tab.assert_called_once_with("doc123", "Sub", index=2, parent_tab_id="t.0")


class TestDocsDeleteTab:
    """Tests for desk docs delete-tab command."""

    def test_delete_tab_with_yes(self, runner, mock_get_credentials, mock_docs_client_class):
        """Should delete tab when --yes is provided."""
        from desk.commands.docs import docs

        mock_client = MagicMock()
        mock_client.delete_tab.return_value = {"documentId": "doc123", "status": "ok"}
        mock_docs_client_class.return_value = mock_client

        result = runner.invoke(docs, ["delete-tab", "doc123", "--tab", "t.1", "--yes", "--json"])

        assert result.exit_code == 0
        output = json.loads(result.output)
        assert output["success"] is True
        assert output["operation"] == "delete-tab"
        mock_client.delete_tab.assert_called_once_with("doc123", "t.1")


class TestDocsRenameTab:
    """Tests for desk docs rename-tab command."""

    def test_rename_tab(self, runner, mock_get_credentials, mock_docs_client_class):
        """Should rename a tab."""
        from desk.commands.docs import docs

        mock_client = MagicMock()
        mock_client.rename_tab.return_value = {"tabId": "t.0", "title": "Renamed"}
        mock_docs_client_class.return_value = mock_client

        result = runner.invoke(
            docs, ["rename-tab", "doc123", "--tab", "t.0", "--title", "Renamed", "--json"]
        )

        assert result.exit_code == 0
        output = json.loads(result.output)
        assert output["success"] is True
        assert output["operation"] == "rename-tab"
        mock_client.rename_tab.assert_called_once_with("doc123", "t.0", "Renamed")


class TestDocsTabOption:
    """Tests for --tab option on content commands."""

    def test_read_with_tab(self, runner, mock_get_credentials, mock_docs_client_class):
        """Should pass tab_id to read."""
        from desk.commands.docs import docs

        mock_client = MagicMock()
        mock_client.read.return_value = {
            "documentId": "doc123",
            "title": "Test",
            "body": "Tab content",
        }
        mock_client.get_tabs_cached.return_value = [{"tabId": "t.1", "title": "Tab 1"}]
        mock_docs_client_class.return_value = mock_client

        result = runner.invoke(docs, ["read", "doc123", "--tab", "t.1", "--json"])

        assert result.exit_code == 0
        mock_client.read.assert_called_once_with("doc123", tab_id="t.1")

    def test_insert_with_tab(self, runner, mock_get_credentials, mock_docs_client_class):
        """Should pass tab_id to insert_at."""
        from desk.commands.docs import docs

        mock_client = MagicMock()
        mock_client.insert_at.return_value = {"documentId": "doc123", "status": "ok"}
        mock_client.get_tabs_cached.return_value = [{"tabId": "t.1", "title": "Tab 1"}]
        mock_docs_client_class.return_value = mock_client

        result = runner.invoke(
            docs, ["insert", "doc123", "Hello", "--tab", "t.1", "--json"]
        )

        assert result.exit_code == 0
        mock_client.insert_at.assert_called_once_with("doc123", "Hello", index=None, tab_id="t.1")

    def test_write_markdown_with_tab(self, runner, mock_get_credentials, mock_docs_client_class):
        """Should pass tab_id to write_markdown."""
        from desk.commands.docs import docs

        mock_client = MagicMock()
        mock_client.write_markdown.return_value = {"documentId": "doc123", "status": "ok"}
        mock_client.get_tabs_cached.return_value = [{"tabId": "t.1", "title": "Tab 1"}]
        mock_docs_client_class.return_value = mock_client

        result = runner.invoke(
            docs, ["write-markdown", "doc123", "--body", "# Hello", "--tab", "t.1", "--json"]
        )

        assert result.exit_code == 0
        mock_client.write_markdown.assert_called_once_with(
            "doc123", "# Hello",
            index=None, replace=False, tab_id="t.1",
            space_above=None, space_below=None, line_spacing=None,
            indent_start=None, indent_end=None, indent_first_line=None,
        )

    def test_update_with_tab(self, runner, mock_get_credentials, mock_docs_client_class):
        """Should pass tab_id to update."""
        from desk.commands.docs import docs

        mock_client = MagicMock()
        mock_client.update.return_value = {"documentId": "doc123", "mode": "append", "status": "ok"}
        mock_client.get_tabs_cached.return_value = [{"tabId": "t.1", "title": "Tab 1"}]
        mock_docs_client_class.return_value = mock_client

        result = runner.invoke(
            docs, ["update", "doc123", "New text", "--tab", "t.1", "--json"]
        )

        assert result.exit_code == 0
        mock_client.update.assert_called_once_with("doc123", "New text", mode="append", tab_id="t.1")

    def test_delete_range_with_tab(self, runner, mock_get_credentials, mock_docs_client_class):
        """Should pass tab_id to delete_range."""
        from desk.commands.docs import docs

        mock_client = MagicMock()
        mock_client.delete_range.return_value = {"documentId": "doc123", "status": "ok"}
        mock_client.get_tabs_cached.return_value = [{"tabId": "t.1", "title": "Tab 1"}]
        mock_docs_client_class.return_value = mock_client

        result = runner.invoke(
            docs, ["delete-range", "doc123", "--start", "5", "--end", "20", "--tab", "t.1", "--json"]
        )

        assert result.exit_code == 0
        mock_client.delete_range.assert_called_once_with("doc123", 5, 20, tab_id="t.1")

    def test_style_with_tab(self, runner, mock_get_credentials, mock_docs_client_class):
        """Should pass tab_id to update_text_style."""
        from desk.commands.docs import docs

        mock_client = MagicMock()
        mock_client.update_text_style.return_value = {"documentId": "doc123", "status": "ok"}
        mock_client.get_tabs_cached.return_value = [{"tabId": "t.1", "title": "Tab 1"}]
        mock_docs_client_class.return_value = mock_client

        result = runner.invoke(
            docs, ["style", "doc123", "--start", "1", "--end", "10", "--bold", "--tab", "t.1", "--json"]
        )

        assert result.exit_code == 0
        call_kwargs = mock_client.update_text_style.call_args
        assert call_kwargs[1]["tab_id"] == "t.1"

    def test_paragraph_style_with_tab(self, runner, mock_get_credentials, mock_docs_client_class):
        """Should pass tab_id to update_paragraph_style."""
        from desk.commands.docs import docs

        mock_client = MagicMock()
        mock_client.update_paragraph_style.return_value = {"documentId": "doc123", "status": "ok"}
        mock_client.get_tabs_cached.return_value = [{"tabId": "t.1", "title": "Tab 1"}]
        mock_docs_client_class.return_value = mock_client

        result = runner.invoke(
            docs, ["paragraph-style", "doc123", "--start", "1", "--end", "20", "--heading", "2", "--tab", "t.1", "--json"]
        )

        assert result.exit_code == 0
        mock_client.update_paragraph_style.assert_called_once_with(
            "doc123", 1, 20,
            heading=2, alignment=None,
            space_above=None, space_below=None, line_spacing=None,
            indent_start=None, indent_end=None, indent_first_line=None,
            tab_id="t.1",
        )

    def test_insert_table_with_tab(self, runner, mock_get_credentials, mock_docs_client_class):
        """Should pass tab_id to insert_table."""
        from desk.commands.docs import docs

        mock_client = MagicMock()
        mock_client.insert_table.return_value = {"documentId": "doc123", "status": "ok"}
        mock_client.get_tabs_cached.return_value = [{"tabId": "t.1", "title": "Tab 1"}]
        mock_docs_client_class.return_value = mock_client

        result = runner.invoke(
            docs, ["insert-table", "doc123", "--rows", "3", "--cols", "4", "--tab", "t.1", "--json"]
        )

        assert result.exit_code == 0
        mock_client.insert_table.assert_called_once_with("doc123", 3, 4, index=None, tab_id="t.1")

    def test_insert_image_with_tab(self, runner, mock_get_credentials, mock_docs_client_class):
        """Should pass tab_id to insert_image."""
        from desk.commands.docs import docs

        mock_client = MagicMock()
        mock_client.insert_image.return_value = {"documentId": "doc123", "status": "ok"}
        mock_client.get_tabs_cached.return_value = [{"tabId": "t.1", "title": "Tab 1"}]
        mock_docs_client_class.return_value = mock_client

        result = runner.invoke(
            docs, ["insert-image", "doc123", "--uri", "https://example.com/img.png", "--tab", "t.1", "--json"]
        )

        assert result.exit_code == 0
        mock_client.insert_image.assert_called_once_with(
            "doc123", "https://example.com/img.png", index=None, width=None, height=None, tab_id="t.1"
        )


class TestWithTabResolution:
    """Tests for the _with_tab_resolution wrapper (ADR-018, optimistic-then-fallback)."""

    def test_none_passes_through_with_no_lookup(self):
        from desk.commands.docs import _with_tab_resolution

        client = MagicMock()
        called_with = []
        result, resolved = _with_tab_resolution(
            client, "doc123", None, False, lambda tid: called_with.append(tid) or "ok",
        )
        assert result == "ok"
        assert resolved is None
        assert called_with == [None]
        client.get_tabs_cached.assert_not_called()

    def test_id_happy_path_skips_list_tabs(self):
        """Valid ID path: no list_tabs round-trip — fn called once with the value."""
        from desk.commands.docs import _with_tab_resolution

        client = MagicMock()
        result, resolved = _with_tab_resolution(
            client, "doc123", "t.abc", False, lambda tid: ("body", tid),
        )
        assert result == ("body", "t.abc")
        assert resolved == "t.abc"
        client.get_tabs_cached.assert_not_called()

    def test_non_tab_error_reraises_without_listing(self):
        """A non-tab-shaped error should propagate untouched."""
        from desk.commands.docs import _with_tab_resolution

        client = MagicMock()

        def fn(_tid):
            raise RuntimeError("Document not found: doc123")

        with pytest.raises(RuntimeError, match="Document not found"):
            _with_tab_resolution(client, "doc123", "t.abc", False, fn)
        client.get_tabs_cached.assert_not_called()

    def test_tab_error_with_real_id_reraises_original(self):
        """If error is tab-shaped but value matches a real tab ID, reraise."""
        from desk.commands.docs import _with_tab_resolution

        client = MagicMock()
        client.get_tabs_cached.return_value = [
            {"tabId": "t.abc", "title": "Transcript"},
        ]

        def fn(_tid):
            raise RuntimeError("Tab not found: t.abc — this came from somewhere weird")

        # The ID is real, so we should not mask the original error with a TAB_NOT_FOUND.
        with pytest.raises(RuntimeError, match="came from somewhere weird"):
            _with_tab_resolution(client, "doc123", "t.abc", False, fn)
        client.get_tabs_cached.assert_called_once_with("doc123")

    def test_title_resolves_and_retries(self):
        """Tab-shaped error + valid title → list once + retry with resolved ID."""
        from desk.commands.docs import _with_tab_resolution

        client = MagicMock()
        client.get_tabs_cached.return_value = [
            {"tabId": "t.xyz", "title": "Transcript"},
        ]

        calls = []

        def fn(tid):
            calls.append(tid)
            if tid == "Transcript":
                raise RuntimeError("Tab not found: Transcript")
            return f"body-of-{tid}"

        result, resolved = _with_tab_resolution(
            client, "doc123", "Transcript", False, fn,
        )
        assert result == "body-of-t.xyz"
        assert resolved == "t.xyz"
        assert calls == ["Transcript", "t.xyz"]

    def test_title_match_is_case_insensitive_and_trimmed(self):
        from desk.commands.docs import _with_tab_resolution

        client = MagicMock()
        client.get_tabs_cached.return_value = [
            {"tabId": "t.xyz", "title": "Transcript"},
        ]

        def fn(tid):
            if tid != "t.xyz":
                raise RuntimeError("Tab not found")
            return "ok"

        for value in ("TRANSCRIPT", "  transcript  ", "Transcript"):
            client.get_tabs_cached.reset_mock()
            result, resolved = _with_tab_resolution(client, "doc123", value, False, fn)
            assert result == "ok"
            assert resolved == "t.xyz"

    def test_ambiguous_title_emits_structured_error(self, capsys):
        from desk.commands.docs import _with_tab_resolution

        client = MagicMock()
        client.get_tabs_cached.return_value = [
            {"tabId": "t.1", "title": "Notes"},
            {"tabId": "t.2", "title": "Notes"},
        ]

        def fn(_tid):
            raise RuntimeError("Tab not found: Notes")

        with pytest.raises(SystemExit) as exc:
            _with_tab_resolution(client, "doc123", "Notes", True, fn)
        assert exc.value.code == 1
        payload = json.loads(capsys.readouterr().err)
        assert payload["error"]["code"] == "TAB_NAME_AMBIGUOUS"
        assert {m["tabId"] for m in payload["error"]["details"]["matches"]} == {"t.1", "t.2"}

    def test_no_match_emits_structured_error_with_available_tabs(self, capsys):
        from desk.commands.docs import _with_tab_resolution

        client = MagicMock()
        client.get_tabs_cached.return_value = [
            {"tabId": "t.1", "title": "Notes"},
            {"tabId": "t.2", "title": "Drafts"},
        ]

        def fn(_tid):
            raise RuntimeError("Tab not found: Transcript")

        with pytest.raises(SystemExit) as exc:
            _with_tab_resolution(client, "doc123", "Transcript", True, fn)
        assert exc.value.code == 1
        payload = json.loads(capsys.readouterr().err)
        assert payload["error"]["code"] == "TAB_NOT_FOUND"
        assert {t["tabId"] for t in payload["error"]["details"]["available_tabs"]} == {"t.1", "t.2"}

    def test_list_tabs_failure_reraises_original(self):
        """If list_tabs itself fails, surface the original operation error."""
        from desk.commands.docs import _with_tab_resolution

        client = MagicMock()
        client.get_tabs_cached.side_effect = RuntimeError("list_tabs blew up")

        def fn(_tid):
            raise RuntimeError("Tab not found: foo")

        with pytest.raises(RuntimeError, match="Tab not found: foo"):
            _with_tab_resolution(client, "doc123", "foo", False, fn)


class TestTabResolutionEndToEnd:
    """End-to-end CLI tests for tab name resolution (ADR-018)."""

    def test_read_resolves_title_to_id(
        self, runner, mock_get_credentials, mock_docs_client_class,
    ):
        from desk.commands.docs import docs

        mock_client = MagicMock()
        mock_client.get_tabs_cached.return_value = [
            {"tabId": "t.xyz", "title": "Transcript"},
            {"tabId": "t.abc", "title": "Notes"},
        ]

        body_result = {"documentId": "doc123", "title": "Test", "body": "x"}

        def read_side_effect(_doc_id, tab_id=None):
            if tab_id == "Transcript":
                raise RuntimeError("Tab not found: Transcript")
            return body_result

        mock_client.read.side_effect = read_side_effect
        mock_docs_client_class.return_value = mock_client

        result = runner.invoke(
            docs, ["read", "doc123", "--tab", "Transcript", "--json"]
        )
        assert result.exit_code == 0, result.output
        # Two calls: optimistic with title, retry with resolved ID
        assert mock_client.read.call_count == 2
        assert mock_client.read.call_args_list[1].kwargs["tab_id"] == "t.xyz"

    def test_read_with_id_does_not_call_list_tabs(
        self, runner, mock_get_credentials, mock_docs_client_class,
    ):
        """Optimistic path: a valid ID should not trigger list_tabs."""
        from desk.commands.docs import docs

        mock_client = MagicMock()
        mock_client.read.return_value = {
            "documentId": "doc123", "title": "Test", "body": "x",
        }
        mock_docs_client_class.return_value = mock_client

        result = runner.invoke(docs, ["read", "doc123", "--tab", "t.xyz", "--json"])
        assert result.exit_code == 0
        mock_client.get_tabs_cached.assert_not_called()
        mock_client.read.assert_called_once_with("doc123", tab_id="t.xyz")

    def test_read_with_unknown_title_errors_with_available_tabs(
        self, runner, mock_get_credentials, mock_docs_client_class,
    ):
        from desk.commands.docs import docs

        mock_client = MagicMock()
        mock_client.get_tabs_cached.return_value = [
            {"tabId": "t.xyz", "title": "Transcript"},
        ]
        mock_client.read.side_effect = RuntimeError("Tab not found: DoesNotExist")
        mock_docs_client_class.return_value = mock_client

        result = runner.invoke(
            docs, ["read", "doc123", "--tab", "DoesNotExist", "--json"]
        )
        assert result.exit_code == 1
        payload = json.loads(result.output)
        assert payload["error"]["code"] == "TAB_NOT_FOUND"

    def test_delete_tab_accepts_title(
        self, runner, mock_get_credentials, mock_docs_client_class,
    ):
        """delete-tab should resolve a title to an ID like the content commands."""
        from desk.commands.docs import docs

        mock_client = MagicMock()
        mock_client.get_tabs_cached.return_value = [
            {"tabId": "t.kill", "title": "Drafts"},
            {"tabId": "t.keep", "title": "Notes"},
        ]

        def delete_side_effect(_doc_id, tab_id):
            if tab_id == "Drafts":
                raise RuntimeError("Tab not found: Drafts")
            return {"documentId": "doc123", "status": "ok"}

        mock_client.delete_tab.side_effect = delete_side_effect
        mock_docs_client_class.return_value = mock_client

        result = runner.invoke(
            docs, ["delete-tab", "doc123", "--tab", "Drafts", "--yes", "--json"]
        )
        assert result.exit_code == 0, result.output
        assert mock_client.delete_tab.call_count == 2
        assert mock_client.delete_tab.call_args_list[1].args == ("doc123", "t.kill")

    def test_rename_tab_accepts_title(
        self, runner, mock_get_credentials, mock_docs_client_class,
    ):
        from desk.commands.docs import docs

        mock_client = MagicMock()
        mock_client.get_tabs_cached.return_value = [
            {"tabId": "t.abc", "title": "Old Name"},
        ]

        def rename_side_effect(_doc_id, tab_id, title):
            if tab_id == "Old Name":
                raise RuntimeError("Tab not found: Old Name")
            return {"tabId": tab_id, "title": title}

        mock_client.rename_tab.side_effect = rename_side_effect
        mock_docs_client_class.return_value = mock_client

        result = runner.invoke(
            docs,
            ["rename-tab", "doc123", "--tab", "Old Name", "--title", "New Name", "--json"],
        )
        assert result.exit_code == 0, result.output
        assert mock_client.rename_tab.call_count == 2
        assert mock_client.rename_tab.call_args_list[1].args == ("doc123", "t.abc", "New Name")


class TestErrorStreamDiscipline:
    """ADR-019: errors land on stderr, stdout stays empty on failure.

    Regression coverage for issue #18: `desk docs read --tab <bad>` was
    writing its error to stdout, which broke `A || B` shell fallback chains.
    """

    def test_unknown_tab_human_mode_writes_to_stderr_not_stdout(
        self, runner, mock_get_credentials, mock_docs_client_class,
    ):
        from desk.commands.docs import docs

        mock_client = MagicMock()
        mock_client.get_tabs_cached.return_value = [
            {"tabId": "t.notes", "title": "Notes"},
        ]
        mock_client.read.side_effect = RuntimeError("Tab not found: Transcript")
        mock_docs_client_class.return_value = mock_client

        result = runner.invoke(docs, ["read", "doc123", "--tab", "Transcript"])

        assert result.exit_code == 1
        assert result.stdout == ""
        assert "No tab matches 'Transcript'" in result.stderr
        assert "Notes" in result.stderr

    def test_unknown_tab_json_mode_writes_envelope_to_stderr(
        self, runner, mock_get_credentials, mock_docs_client_class,
    ):
        from desk.commands.docs import docs

        mock_client = MagicMock()
        mock_client.get_tabs_cached.return_value = [
            {"tabId": "t.notes", "title": "Notes"},
        ]
        mock_client.read.side_effect = RuntimeError("Tab not found: Transcript")
        mock_docs_client_class.return_value = mock_client

        result = runner.invoke(
            docs, ["read", "doc123", "--tab", "Transcript", "--json"]
        )

        assert result.exit_code == 1
        assert result.stdout == ""
        payload = json.loads(result.stderr)
        assert payload["error"]["code"] == "TAB_NOT_FOUND"
