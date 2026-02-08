"""Tests for mail CLI commands."""

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
    with patch("desk.commands.mail.get_credentials") as mock:
        mock.return_value = MagicMock()
        yield mock


@pytest.fixture
def mock_gmail_client_class():
    """Mock the GmailClient class."""
    with patch("desk.commands.mail.GmailClient") as mock:
        yield mock


class TestMailSearch:
    """Tests for desk mail search command."""

    def test_search_with_json_output(self, runner, mock_get_credentials, mock_gmail_client_class):
        """Should output JSON when --json flag is used."""
        from desk.commands.mail import mail

        mock_client = MagicMock()
        mock_client.search.return_value = {
            "messages": [
                {
                    "id": "msg1",
                    "from": "test@example.com",
                    "subject": "Test Subject",
                    "date": "2024-01-15",
                }
            ]
        }
        mock_gmail_client_class.return_value = mock_client

        result = runner.invoke(mail, ["search", "is:unread", "--json"])

        assert result.exit_code == 0
        output = json.loads(result.output)
        assert "messages" in output
        assert len(output["messages"]) == 1

    def test_search_no_results(self, runner, mock_get_credentials, mock_gmail_client_class):
        """Should handle no results gracefully."""
        from desk.commands.mail import mail

        mock_client = MagicMock()
        mock_client.search.return_value = {"messages": []}
        mock_gmail_client_class.return_value = mock_client

        result = runner.invoke(mail, ["search", "from:nobody"])

        assert result.exit_code == 0
        assert "No messages found" in result.output

    def test_search_with_max_option(self, runner, mock_get_credentials, mock_gmail_client_class):
        """Should pass max_results to client."""
        from desk.commands.mail import mail

        mock_client = MagicMock()
        mock_client.search.return_value = {"messages": []}
        mock_gmail_client_class.return_value = mock_client

        runner.invoke(mail, ["search", "is:unread", "--max", "5"])

        mock_client.search.assert_called_once()
        _, kwargs = mock_client.search.call_args
        assert kwargs.get("max_results") == 5


class TestMailRead:
    """Tests for desk mail read command."""

    def test_read_with_json_output(self, runner, mock_get_credentials, mock_gmail_client_class):
        """Should output message as JSON when --json flag is used."""
        from desk.commands.mail import mail

        mock_client = MagicMock()
        mock_client.read.return_value = {
            "id": "msg123",
            "from": "sender@example.com",
            "subject": "Test Subject",
            "body": "Hello World",
        }
        mock_gmail_client_class.return_value = mock_client

        result = runner.invoke(mail, ["read", "msg123", "--json"])

        assert result.exit_code == 0
        output = json.loads(result.output)
        assert output["id"] == "msg123"
        assert output["body"] == "Hello World"


class TestMailThreads:
    """Tests for desk mail threads command."""

    def test_threads_with_json_output(self, runner, mock_get_credentials, mock_gmail_client_class):
        """Should output threads as JSON."""
        from desk.commands.mail import mail

        mock_client = MagicMock()
        mock_client.search_threads.return_value = {
            "threads": [
                {
                    "id": "thread1",
                    "from": "test@example.com",
                    "subject": "Thread Subject",
                    "messageCount": 3,
                    "date": "2024-01-15",
                }
            ]
        }
        mock_gmail_client_class.return_value = mock_client

        result = runner.invoke(mail, ["threads", "is:unread", "--json"])

        assert result.exit_code == 0
        output = json.loads(result.output)
        assert "threads" in output


class TestMailArchive:
    """Tests for desk mail archive command."""

    def test_archive_with_json_output(self, runner, mock_get_credentials, mock_gmail_client_class):
        """Should output operation receipt as JSON."""
        from desk.commands.mail import mail

        mock_client = MagicMock()
        mock_client.read.return_value = {
            "id": "msg123",
            "subject": "Test",
            "from": "test@example.com",
            "date": "2024-01-15",
        }
        mock_client.modify.return_value = None
        mock_gmail_client_class.return_value = mock_client

        result = runner.invoke(mail, ["archive", "msg123", "--json"])

        assert result.exit_code == 0
        output = json.loads(result.output)
        assert output["success"] is True


class TestMailLabels:
    """Tests for desk mail labels command."""

    def test_labels_json_output(self, runner, mock_get_credentials, mock_gmail_client_class):
        """Should output labels as JSON."""
        from desk.commands.mail import mail

        mock_client = MagicMock()
        mock_client.list_labels.return_value = [
            {"id": "INBOX", "name": "INBOX", "type": "system"},
        ]
        mock_gmail_client_class.return_value = mock_client

        result = runner.invoke(mail, ["labels", "--json"])

        assert result.exit_code == 0
        output = json.loads(result.output)
        assert isinstance(output, list)


class TestMailCreateLabel:
    """Tests for desk mail create-label command."""

    def test_create_label(self, runner, mock_get_credentials, mock_gmail_client_class):
        """Should create a new label."""
        from desk.commands.mail import mail

        mock_client = MagicMock()
        mock_client.create_label.return_value = {
            "id": "Label_123",
            "name": "NewLabel",
        }
        mock_gmail_client_class.return_value = mock_client

        result = runner.invoke(mail, ["create-label", "NewLabel"])

        assert result.exit_code == 0
        assert "NewLabel" in result.output
