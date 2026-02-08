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
