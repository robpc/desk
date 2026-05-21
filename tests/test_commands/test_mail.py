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

    def test_read_passes_headers_csv_to_client(
        self, runner, mock_get_credentials, mock_gmail_client_class
    ):
        """--headers should be split on commas and passed to client.read."""
        from desk.commands.mail import mail

        mock_client = MagicMock()
        mock_client.read.return_value = {
            "id": "m1",
            "from": "a@x",
            "subject": "s",
            "date": "d",
            "body": "b",
            "headers": {"List-Unsubscribe": ["<u>"]},
        }
        mock_gmail_client_class.return_value = mock_client

        result = runner.invoke(
            mail,
            ["read", "m1", "--json", "--headers", "List-Unsubscribe,Auto-Submitted"],
        )

        assert result.exit_code == 0
        mock_client.read.assert_called_once_with(
            "m1", extra_headers=["List-Unsubscribe", "Auto-Submitted"]
        )

    def test_read_passes_wildcard_to_client(
        self, runner, mock_get_credentials, mock_gmail_client_class
    ):
        """--headers '*' should pass ['*'] to client.read."""
        from desk.commands.mail import mail

        mock_client = MagicMock()
        mock_client.read.return_value = {
            "id": "m1",
            "from": "a@x",
            "subject": "s",
            "date": "d",
            "body": "b",
            "headers": {},
        }
        mock_gmail_client_class.return_value = mock_client

        result = runner.invoke(mail, ["read", "m1", "--json", "--headers", "*"])

        assert result.exit_code == 0
        mock_client.read.assert_called_once_with("m1", extra_headers=["*"])


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

    def test_archive_json_receipt_includes_equivalent(
        self, runner, mock_get_credentials, mock_gmail_client_class
    ):
        """JSON receipt should include the `equivalent` modify call (ADR-025)."""
        from desk.commands.mail import mail

        mock_client = MagicMock()
        mock_client.read.return_value = {
            "id": "msg123", "subject": "Test", "from": "x@y", "date": "d",
        }
        mock_gmail_client_class.return_value = mock_client

        result = runner.invoke(mail, ["archive", "msg123", "--json"])

        assert result.exit_code == 0
        output = json.loads(result.output)
        assert output.get("equivalent") == "desk mail modify --remove-label INBOX <ids>"

    def test_archive_human_output_shows_equivalent_line(
        self, runner, mock_get_credentials, mock_gmail_client_class
    ):
        """Non-JSON success path should print a dim equivalent line (ADR-025)."""
        from desk.commands.mail import mail

        mock_client = MagicMock()
        mock_gmail_client_class.return_value = mock_client

        result = runner.invoke(mail, ["archive", "msg123"])

        assert result.exit_code == 0
        assert "equivalent:" in result.output
        assert "desk mail modify --remove-label INBOX" in result.output


class TestMailUnreadDeprecation:
    """Tests for the `mail unread` deprecation warning (ADR-025)."""

    def test_unread_emits_deprecation_warning_to_stderr(
        self, runner, mock_get_credentials, mock_gmail_client_class
    ):
        from desk.commands.mail import mail

        mock_client = MagicMock()
        mock_client.search.return_value = {"messages": []}
        mock_gmail_client_class.return_value = mock_client

        result = runner.invoke(mail, ["unread", "--json"])

        assert result.exit_code == 0
        assert "Deprecation" in result.stderr
        assert "desk mail search" in result.stderr
        # And the actual behavior is unchanged: still calls search with is:unread
        mock_client.search.assert_called_once()
        call = mock_client.search.call_args
        assert call.args[0] == "is:unread"


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


class TestMailReadLinks:
    """Tests for links display in desk mail read command."""

    def test_read_shows_links_section_for_hidden_urls(self, runner, mock_get_credentials, mock_gmail_client_class):
        """Should show Links section when URLs are hidden from plain text."""
        from desk.commands.mail import mail

        mock_client = MagicMock()
        mock_client.read.return_value = {
            "id": "msg123",
            "from": "sender@example.com",
            "subject": "Meeting Notes",
            "date": "2026-02-10",
            "body": "Here are the meeting notes.",
            "links": [
                {
                    "url": "https://docs.google.com/document/d/1abc/edit",
                    "text": "Meeting Notes Doc",
                    "type": "google-doc",
                    "readable_via": "desk docs read 1abc",
                },
            ],
        }
        mock_gmail_client_class.return_value = mock_client

        result = runner.invoke(mail, ["read", "msg123"])

        assert result.exit_code == 0
        assert "Links:" in result.output
        assert "Meeting Notes Doc" in result.output
        assert "https://docs.google.com/document/d/1abc/edit" in result.output
        assert "desk docs read 1abc" in result.output

    def test_read_omits_links_section_when_all_visible(self, runner, mock_get_credentials, mock_gmail_client_class):
        """Should not show Links section when all URLs are already in body."""
        from desk.commands.mail import mail

        mock_client = MagicMock()
        mock_client.read.return_value = {
            "id": "msg123",
            "from": "sender@example.com",
            "subject": "Test",
            "date": "2026-02-10",
            "body": "Visit https://example.com for details.",
            "links": [
                {
                    "url": "https://example.com",
                    "text": "Example",
                    "type": "external",
                    "readable_via": None,
                },
            ],
        }
        mock_gmail_client_class.return_value = mock_client

        result = runner.invoke(mail, ["read", "msg123"])

        assert result.exit_code == 0
        assert "Links:" not in result.output

    def test_read_omits_links_section_when_no_links(self, runner, mock_get_credentials, mock_gmail_client_class):
        """Should not show Links section when message has no links."""
        from desk.commands.mail import mail

        mock_client = MagicMock()
        mock_client.read.return_value = {
            "id": "msg123",
            "from": "sender@example.com",
            "subject": "Test",
            "date": "2026-02-10",
            "body": "Plain text email.",
            "links": [],
        }
        mock_gmail_client_class.return_value = mock_client

        result = runner.invoke(mail, ["read", "msg123"])

        assert result.exit_code == 0
        assert "Links:" not in result.output

    def test_read_json_includes_all_links(self, runner, mock_get_credentials, mock_gmail_client_class):
        """JSON output should include all links regardless of visibility in body."""
        from desk.commands.mail import mail

        mock_client = MagicMock()
        mock_client.read.return_value = {
            "id": "msg123",
            "from": "sender@example.com",
            "subject": "Test",
            "date": "2026-02-10",
            "body": "Visit https://example.com",
            "links": [
                {
                    "url": "https://example.com",
                    "text": "Example",
                    "type": "external",
                    "readable_via": None,
                },
                {
                    "url": "https://docs.google.com/document/d/1abc/edit",
                    "text": "Doc",
                    "type": "google-doc",
                    "readable_via": "desk docs read 1abc",
                },
            ],
        }
        mock_gmail_client_class.return_value = mock_client

        result = runner.invoke(mail, ["read", "msg123", "--json"])

        assert result.exit_code == 0
        output = json.loads(result.output)
        assert len(output["links"]) == 2


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
