"""Tests for Gmail service client."""

import base64
import pytest
from unittest.mock import MagicMock, patch

from googleapiclient.errors import HttpError


class TestGmailClientInit:
    """Tests for GmailClient initialization."""

    def test_creates_service_with_credentials(self, mock_credentials):
        """Should create Gmail service with provided credentials."""
        with patch("desk.services.gmail.build") as mock_build:
            mock_build.return_value = MagicMock()
            from desk.services.gmail import GmailClient

            client = GmailClient(mock_credentials)

            mock_build.assert_called_once_with("gmail", "v1", credentials=mock_credentials)
            assert client.user_id == "me"


class TestGmailSearch:
    """Tests for GmailClient.search method."""

    def test_search_returns_messages(self, mock_credentials):
        """Should return list of messages matching query."""
        with patch("desk.services.gmail.build") as mock_build:
            mock_service = MagicMock()
            mock_build.return_value = mock_service

            # Configure mock chain
            messages_mock = mock_service.users.return_value.messages.return_value
            messages_mock.list.return_value.execute.return_value = {
                "messages": [
                    {"id": "msg1", "threadId": "thread1"},
                    {"id": "msg2", "threadId": "thread2"},
                ]
            }
            messages_mock.get.return_value.execute.return_value = {
                "id": "msg1",
                "threadId": "thread1",
                "snippet": "Test snippet",
                "payload": {
                    "headers": [
                        {"name": "From", "value": "test@example.com"},
                        {"name": "Subject", "value": "Test Subject"},
                        {"name": "Date", "value": "Mon, 1 Jan 2024 10:00:00 -0500"},
                    ]
                },
            }

            from desk.services.gmail import GmailClient

            client = GmailClient(mock_credentials)
            result = client.search("is:unread")

            assert "messages" in result
            assert len(result["messages"]) == 2

    def test_search_with_max_results(self, mock_credentials):
        """Should pass max_results to API."""
        with patch("desk.services.gmail.build") as mock_build:
            mock_service = MagicMock()
            mock_build.return_value = mock_service

            messages_mock = mock_service.users.return_value.messages.return_value
            messages_mock.list.return_value.execute.return_value = {"messages": []}

            from desk.services.gmail import GmailClient

            client = GmailClient(mock_credentials)
            client.search("is:unread", max_results=5)

            messages_mock.list.assert_called_once()
            call_kwargs = messages_mock.list.call_args[1]
            assert call_kwargs["maxResults"] == 5

    def test_search_with_page_token(self, mock_credentials):
        """Should pass page token to API."""
        with patch("desk.services.gmail.build") as mock_build:
            mock_service = MagicMock()
            mock_build.return_value = mock_service

            messages_mock = mock_service.users.return_value.messages.return_value
            messages_mock.list.return_value.execute.return_value = {"messages": []}

            from desk.services.gmail import GmailClient

            client = GmailClient(mock_credentials)
            client.search("is:unread", page_token="next_page_token")

            call_kwargs = messages_mock.list.call_args[1]
            assert call_kwargs["pageToken"] == "next_page_token"

    def test_search_returns_next_page_token(self, mock_credentials):
        """Should include nextPageToken in result when available."""
        with patch("desk.services.gmail.build") as mock_build:
            mock_service = MagicMock()
            mock_build.return_value = mock_service

            messages_mock = mock_service.users.return_value.messages.return_value
            messages_mock.list.return_value.execute.return_value = {
                "messages": [],
                "nextPageToken": "abc123",
            }

            from desk.services.gmail import GmailClient

            client = GmailClient(mock_credentials)
            result = client.search("is:unread")

            assert result["nextPageToken"] == "abc123"

    def test_search_api_error_raises_runtime_error(self, mock_credentials):
        """Should raise RuntimeError on API error."""
        with patch("desk.services.gmail.build") as mock_build:
            mock_service = MagicMock()
            mock_build.return_value = mock_service

            messages_mock = mock_service.users.return_value.messages.return_value
            http_error = HttpError(
                resp=MagicMock(status=400),
                content=b'{"error": {"message": "Invalid query"}}'
            )
            messages_mock.list.return_value.execute.side_effect = http_error

            from desk.services.gmail import GmailClient

            client = GmailClient(mock_credentials)
            with pytest.raises(RuntimeError, match="Gmail API error"):
                client.search("invalid query syntax")


class TestGmailRead:
    """Tests for GmailClient.read method."""

    def test_read_returns_message_with_body(self, mock_credentials):
        """Should return message with parsed body."""
        body_text = "Hello, this is the message body."
        encoded_body = base64.urlsafe_b64encode(body_text.encode()).decode()

        with patch("desk.services.gmail.build") as mock_build:
            mock_service = MagicMock()
            mock_build.return_value = mock_service

            messages_mock = mock_service.users.return_value.messages.return_value
            messages_mock.get.return_value.execute.return_value = {
                "id": "msg123",
                "threadId": "thread456",
                "payload": {
                    "headers": [
                        {"name": "From", "value": "sender@example.com"},
                        {"name": "Subject", "value": "Test Subject"},
                    ],
                    "body": {"data": encoded_body},
                },
            }

            from desk.services.gmail import GmailClient

            client = GmailClient(mock_credentials)
            result = client.read("msg123")

            assert result["id"] == "msg123"
            assert result["from"] == "sender@example.com"
            assert result["subject"] == "Test Subject"
            assert result["body"] == body_text

    def test_read_not_found_raises_error(self, mock_credentials):
        """Should raise error when message not found."""
        with patch("desk.services.gmail.build") as mock_build:
            mock_service = MagicMock()
            mock_build.return_value = mock_service

            messages_mock = mock_service.users.return_value.messages.return_value
            http_error = HttpError(
                resp=MagicMock(status=404),
                content=b'{"error": {"message": "Not found"}}'
            )
            messages_mock.get.return_value.execute.side_effect = http_error

            from desk.services.gmail import GmailClient

            client = GmailClient(mock_credentials)
            with pytest.raises(RuntimeError, match="Gmail API error"):
                client.read("nonexistent_id")


class TestGmailModify:
    """Tests for GmailClient.modify method."""

    def test_modify_adds_labels(self, mock_credentials):
        """Should call modify with addLabelIds."""
        with patch("desk.services.gmail.build") as mock_build:
            mock_service = MagicMock()
            mock_build.return_value = mock_service

            # Mock labels list for label resolution
            labels_mock = mock_service.users.return_value.labels.return_value
            labels_mock.list.return_value.execute.return_value = {"labels": []}

            messages_mock = mock_service.users.return_value.messages.return_value

            from desk.services.gmail import GmailClient

            client = GmailClient(mock_credentials)
            client.modify("msg123", add_labels=["STARRED"])

            messages_mock.modify.assert_called_once()
            call_kwargs = messages_mock.modify.call_args[1]
            assert "STARRED" in call_kwargs["body"]["addLabelIds"]

    def test_modify_removes_labels(self, mock_credentials):
        """Should call modify with removeLabelIds."""
        with patch("desk.services.gmail.build") as mock_build:
            mock_service = MagicMock()
            mock_build.return_value = mock_service

            labels_mock = mock_service.users.return_value.labels.return_value
            labels_mock.list.return_value.execute.return_value = {"labels": []}

            messages_mock = mock_service.users.return_value.messages.return_value

            from desk.services.gmail import GmailClient

            client = GmailClient(mock_credentials)
            client.modify("msg123", remove_labels=["INBOX"])

            messages_mock.modify.assert_called_once()
            call_kwargs = messages_mock.modify.call_args[1]
            assert "INBOX" in call_kwargs["body"]["removeLabelIds"]

    def test_modify_with_no_changes_does_nothing(self, mock_credentials):
        """Should not call API when no labels to add/remove."""
        with patch("desk.services.gmail.build") as mock_build:
            mock_service = MagicMock()
            mock_build.return_value = mock_service

            messages_mock = mock_service.users.return_value.messages.return_value

            from desk.services.gmail import GmailClient

            client = GmailClient(mock_credentials)
            client.modify("msg123")

            messages_mock.modify.assert_not_called()


class TestGmailBatchModify:
    """Tests for GmailClient.batch_modify method."""

    def test_batch_modify_multiple_ids(self, mock_credentials):
        """Should call batchModify with all message IDs."""
        with patch("desk.services.gmail.build") as mock_build:
            mock_service = MagicMock()
            mock_build.return_value = mock_service

            labels_mock = mock_service.users.return_value.labels.return_value
            labels_mock.list.return_value.execute.return_value = {"labels": []}

            messages_mock = mock_service.users.return_value.messages.return_value

            from desk.services.gmail import GmailClient

            client = GmailClient(mock_credentials)
            client.batch_modify(
                ["msg1", "msg2", "msg3"],
                add_labels=["STARRED"],
            )

            messages_mock.batchModify.assert_called_once()
            call_kwargs = messages_mock.batchModify.call_args[1]
            assert call_kwargs["body"]["ids"] == ["msg1", "msg2", "msg3"]

    def test_batch_modify_empty_list_does_nothing(self, mock_credentials):
        """Should not call API with empty message list."""
        with patch("desk.services.gmail.build") as mock_build:
            mock_service = MagicMock()
            mock_build.return_value = mock_service

            messages_mock = mock_service.users.return_value.messages.return_value

            from desk.services.gmail import GmailClient

            client = GmailClient(mock_credentials)
            client.batch_modify([], add_labels=["STARRED"])

            messages_mock.batchModify.assert_not_called()


class TestGmailSend:
    """Tests for GmailClient.send method."""

    def test_send_returns_message_metadata(self, mock_credentials):
        """Should return sent message metadata."""
        with patch("desk.services.gmail.build") as mock_build:
            mock_service = MagicMock()
            mock_build.return_value = mock_service

            messages_mock = mock_service.users.return_value.messages.return_value
            messages_mock.send.return_value.execute.return_value = {
                "id": "sent_msg_id",
                "threadId": "thread_id",
                "labelIds": ["SENT"],
            }

            from desk.services.gmail import GmailClient

            client = GmailClient(mock_credentials)
            result = client.send(
                to=["recipient@example.com"],
                subject="Test Subject",
                body="Test body",
            )

            assert result["id"] == "sent_msg_id"
            messages_mock.send.assert_called_once()

    def test_send_with_cc_and_bcc(self, mock_credentials):
        """Should include CC and BCC in message."""
        with patch("desk.services.gmail.build") as mock_build:
            mock_service = MagicMock()
            mock_build.return_value = mock_service

            messages_mock = mock_service.users.return_value.messages.return_value
            messages_mock.send.return_value.execute.return_value = {"id": "msg_id"}

            from desk.services.gmail import GmailClient

            client = GmailClient(mock_credentials)
            client.send(
                to=["to@example.com"],
                subject="Test",
                body="Test body",
                cc=["cc@example.com"],
                bcc=["bcc@example.com"],
            )

            messages_mock.send.assert_called_once()


class TestGmailListLabels:
    """Tests for GmailClient.list_labels method."""

    def test_list_labels_returns_labels(self, mock_credentials):
        """Should return list of labels."""
        with patch("desk.services.gmail.build") as mock_build:
            mock_service = MagicMock()
            mock_build.return_value = mock_service

            labels_mock = mock_service.users.return_value.labels.return_value
            labels_mock.list.return_value.execute.return_value = {
                "labels": [
                    {"id": "INBOX", "name": "INBOX", "type": "system"},
                    {"id": "Label_1", "name": "Work", "type": "user"},
                ]
            }

            from desk.services.gmail import GmailClient

            client = GmailClient(mock_credentials)
            result = client.list_labels()

            assert len(result) == 2
            assert result[0]["name"] == "INBOX"


class TestGmailCreateLabel:
    """Tests for GmailClient.create_label method."""

    def test_create_label_returns_created_label(self, mock_credentials):
        """Should return created label."""
        with patch("desk.services.gmail.build") as mock_build:
            mock_service = MagicMock()
            mock_build.return_value = mock_service

            labels_mock = mock_service.users.return_value.labels.return_value
            # Empty labels list means label doesn't exist
            labels_mock.list.return_value.execute.return_value = {"labels": []}
            labels_mock.create.return_value.execute.return_value = {
                "id": "Label_123",
                "name": "NewLabel",
            }

            from desk.services.gmail import GmailClient

            client = GmailClient(mock_credentials)
            result = client.create_label("NewLabel")

            assert result["id"] == "Label_123"
            assert result["name"] == "NewLabel"

    def test_create_label_with_color(self, mock_credentials):
        """Should set color when provided."""
        with patch("desk.services.gmail.build") as mock_build:
            mock_service = MagicMock()
            mock_build.return_value = mock_service

            labels_mock = mock_service.users.return_value.labels.return_value
            labels_mock.list.return_value.execute.return_value = {"labels": []}
            labels_mock.create.return_value.execute.return_value = {
                "id": "Label_123",
                "name": "ColoredLabel",
            }

            from desk.services.gmail import GmailClient

            client = GmailClient(mock_credentials)
            client.create_label("ColoredLabel", color="blue")

            call_kwargs = labels_mock.create.call_args[1]
            assert "color" in call_kwargs["body"]

    def test_create_label_invalid_color_raises_error(self, mock_credentials):
        """Should raise ValueError for invalid color."""
        with patch("desk.services.gmail.build") as mock_build:
            mock_service = MagicMock()
            mock_build.return_value = mock_service

            labels_mock = mock_service.users.return_value.labels.return_value
            labels_mock.list.return_value.execute.return_value = {"labels": []}

            from desk.services.gmail import GmailClient

            client = GmailClient(mock_credentials)
            with pytest.raises(ValueError, match="Invalid color"):
                client.create_label("TestLabel", color="neon_pink")

    def test_create_label_already_exists_raises_error(self, mock_credentials):
        """Should raise ValueError if label already exists."""
        with patch("desk.services.gmail.build") as mock_build:
            mock_service = MagicMock()
            mock_build.return_value = mock_service

            labels_mock = mock_service.users.return_value.labels.return_value
            labels_mock.list.return_value.execute.return_value = {
                "labels": [{"id": "Label_1", "name": "Existing"}]
            }

            from desk.services.gmail import GmailClient

            client = GmailClient(mock_credentials)
            with pytest.raises(ValueError, match="already exists"):
                client.create_label("Existing")


class TestGmailThreads:
    """Tests for thread-related operations."""

    def test_search_threads_returns_threads(self, mock_credentials):
        """Should return list of threads."""
        with patch("desk.services.gmail.build") as mock_build:
            mock_service = MagicMock()
            mock_build.return_value = mock_service

            threads_mock = mock_service.users.return_value.threads.return_value
            threads_mock.list.return_value.execute.return_value = {
                "threads": [{"id": "thread1"}, {"id": "thread2"}]
            }
            threads_mock.get.return_value.execute.return_value = {
                "id": "thread1",
                "snippet": "Thread snippet",
                "messages": [
                    {
                        "id": "msg1",
                        "payload": {
                            "headers": [
                                {"name": "From", "value": "test@example.com"},
                                {"name": "Subject", "value": "Thread Subject"},
                            ]
                        },
                    }
                ],
            }

            from desk.services.gmail import GmailClient

            client = GmailClient(mock_credentials)
            result = client.search_threads("is:unread")

            assert "threads" in result
            assert len(result["threads"]) == 2

    def test_get_thread_returns_full_thread(self, mock_credentials):
        """Should return thread with all messages."""
        body_text = "Message body"
        encoded_body = base64.urlsafe_b64encode(body_text.encode()).decode()

        with patch("desk.services.gmail.build") as mock_build:
            mock_service = MagicMock()
            mock_build.return_value = mock_service

            threads_mock = mock_service.users.return_value.threads.return_value
            threads_mock.get.return_value.execute.return_value = {
                "id": "thread123",
                "messages": [
                    {
                        "id": "msg1",
                        "threadId": "thread123",
                        "payload": {
                            "headers": [{"name": "From", "value": "test@example.com"}],
                            "body": {"data": encoded_body},
                        },
                    }
                ],
            }

            from desk.services.gmail import GmailClient

            client = GmailClient(mock_credentials)
            result = client.get_thread("thread123")

            assert result["id"] == "thread123"
            assert result["messageCount"] == 1
            assert len(result["messages"]) == 1
