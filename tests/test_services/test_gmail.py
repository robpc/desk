"""Tests for Gmail service client."""

import base64
from unittest.mock import MagicMock, patch

import pytest
from googleapiclient.errors import HttpError


class MockBatchHttpRequest:
    """Mock for service.new_batch_http_request() that simulates batch execution.

    Stores added requests and, on execute(), invokes callbacks with responses
    from a provided response_map (keyed by request_id).
    """

    def __init__(self, callback, response_map=None, error_ids=None):
        self._callback = callback
        self._response_map = response_map or {}
        self._error_ids = set(error_ids or [])
        self._requests = []

    def add(self, request, request_id=None):
        self._requests.append((request_id, request))

    def execute(self):
        for request_id, _request in self._requests:
            if request_id in self._error_ids:
                self._callback(request_id, None, Exception(f"Error for {request_id}"))
            elif request_id in self._response_map:
                self._callback(request_id, self._response_map[request_id], None)
            else:
                # Default: call back with empty dict
                self._callback(request_id, {}, None)


def _make_batch_factory(response_map=None, error_ids=None):
    """Create a factory function for MockBatchHttpRequest with preset responses."""
    def factory(callback):
        return MockBatchHttpRequest(
            callback, response_map=response_map, error_ids=error_ids
        )
    return factory


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


class TestBatchGet:
    """Tests for GmailClient._batch_get helper."""

    def test_empty_input_returns_empty(self, mock_credentials):
        """Should return empty results and empty failures for empty input."""
        with patch("desk.services.gmail.build") as mock_build:
            mock_service = MagicMock()
            mock_build.return_value = mock_service

            from desk.services.gmail import GmailClient

            client = GmailClient(mock_credentials)
            results, failed = client._batch_get([])

            assert results == {}
            assert failed == []

    def test_all_succeed_returns_complete_dict(self, mock_credentials):
        """Should return all results and no failures when all succeed."""
        with patch("desk.services.gmail.build") as mock_build:
            mock_service = MagicMock()
            mock_build.return_value = mock_service

            response_map = {
                "id1": {"data": "response1"},
                "id2": {"data": "response2"},
                "id3": {"data": "response3"},
            }
            mock_service.new_batch_http_request.side_effect = _make_batch_factory(
                response_map=response_map
            )

            from desk.services.gmail import GmailClient

            client = GmailClient(mock_credentials)
            requests = [
                ("id1", MagicMock()),
                ("id2", MagicMock()),
                ("id3", MagicMock()),
            ]
            results, failed = client._batch_get(requests)

            assert results == response_map
            assert failed == []

    def test_partial_failure_records_failed_ids(self, mock_credentials):
        """Should omit failed items from results and list them in failed."""
        with patch("desk.services.gmail.build") as mock_build:
            mock_service = MagicMock()
            mock_build.return_value = mock_service

            response_map = {
                "id1": {"data": "response1"},
                "id3": {"data": "response3"},
            }
            mock_service.new_batch_http_request.side_effect = _make_batch_factory(
                response_map=response_map, error_ids=["id2"]
            )

            from desk.services.gmail import GmailClient

            client = GmailClient(mock_credentials)
            requests = [
                ("id1", MagicMock()),
                ("id2", MagicMock()),
                ("id3", MagicMock()),
            ]
            results, failed = client._batch_get(requests)

            assert "id1" in results
            assert "id2" not in results
            assert "id3" in results
            assert failed == ["id2"]

    def test_all_fail_raises_runtime_error(self, mock_credentials):
        """Should raise RuntimeError when ALL requests fail."""
        with patch("desk.services.gmail.build") as mock_build:
            mock_service = MagicMock()
            mock_build.return_value = mock_service

            mock_service.new_batch_http_request.side_effect = _make_batch_factory(
                error_ids=["id1", "id2"]
            )

            from desk.services.gmail import GmailClient

            client = GmailClient(mock_credentials)
            requests = [("id1", MagicMock()), ("id2", MagicMock())]

            with pytest.raises(RuntimeError, match="All 2 batch requests failed"):
                client._batch_get(requests)

    def test_chunks_above_100_into_multiple_batches(self, mock_credentials):
        """Should split inputs above 100 into multiple sequential batches."""
        with patch("desk.services.gmail.build") as mock_build:
            mock_service = MagicMock()
            mock_build.return_value = mock_service

            response_map = {f"id{i}": {"data": f"r{i}"} for i in range(250)}
            mock_service.new_batch_http_request.side_effect = _make_batch_factory(
                response_map=response_map
            )

            from desk.services.gmail import GmailClient

            client = GmailClient(mock_credentials)
            requests = [(f"id{i}", MagicMock()) for i in range(250)]

            results, failed = client._batch_get(requests)

            assert len(results) == 250
            assert failed == []
            # 250 requests at 100 per chunk = 3 sub-batches.
            assert mock_service.new_batch_http_request.call_count == 3

    def test_chunk_execute_failure_does_not_abort_other_chunks(
        self, mock_credentials
    ):
        """A chunk whose execute() raises should mark its ids failed and proceed."""
        with patch("desk.services.gmail.build") as mock_build:
            mock_service = MagicMock()
            mock_build.return_value = mock_service

            response_map = {f"id{i}": {"data": f"r{i}"} for i in range(150)}

            # First chunk (ids 0-99) raises on execute(); second chunk (100-149)
            # succeeds via the mock factory.
            call_count = {"n": 0}

            def factory(callback):
                call_count["n"] += 1
                batch = MockBatchHttpRequest(callback, response_map=response_map)
                if call_count["n"] == 1:

                    def raising_execute():
                        raise RuntimeError("chunk 1 transport failure")

                    batch.execute = raising_execute  # type: ignore[method-assign]
                    return batch
                return batch

            mock_service.new_batch_http_request.side_effect = factory

            from desk.services.gmail import GmailClient

            client = GmailClient(mock_credentials)
            requests = [(f"id{i}", MagicMock()) for i in range(150)]

            results, failed = client._batch_get(requests)

            # First 100 ids should be in failed; last 50 should be in results.
            assert len(results) == 50
            assert len(failed) == 100
            assert "id0" in failed
            assert "id99" in failed
            assert "id100" in results
            assert "id149" in results


class TestGmailSearch:
    """Tests for GmailClient.search method."""

    def _make_msg_response(self, msg_id, thread_id="thread1"):
        return {
            "id": msg_id,
            "threadId": thread_id,
            "snippet": "Test snippet",
            "payload": {
                "headers": [
                    {"name": "From", "value": "test@example.com"},
                    {"name": "Subject", "value": "Test Subject"},
                    {"name": "Date", "value": "Mon, 1 Jan 2024 10:00:00 -0500"},
                ]
            },
        }

    def test_search_returns_messages(self, mock_credentials):
        """Should return list of messages matching query."""
        with patch("desk.services.gmail.build") as mock_build:
            mock_service = MagicMock()
            mock_build.return_value = mock_service

            messages_mock = mock_service.users.return_value.messages.return_value
            messages_mock.list.return_value.execute.return_value = {
                "messages": [
                    {"id": "msg1", "threadId": "thread1"},
                    {"id": "msg2", "threadId": "thread2"},
                ]
            }

            response_map = {
                "msg1": self._make_msg_response("msg1", "thread1"),
                "msg2": self._make_msg_response("msg2", "thread2"),
            }
            mock_service.new_batch_http_request.side_effect = _make_batch_factory(
                response_map=response_map
            )

            from desk.services.gmail import GmailClient

            client = GmailClient(mock_credentials)
            result = client.search("is:unread")

            assert "messages" in result
            assert len(result["messages"]) == 2
            assert result["messages"][0]["id"] == "msg1"
            assert result["messages"][1]["id"] == "msg2"

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

    def test_search_preserves_order(self, mock_credentials):
        """Should preserve Gmail's message ordering."""
        with patch("desk.services.gmail.build") as mock_build:
            mock_service = MagicMock()
            mock_build.return_value = mock_service

            messages_mock = mock_service.users.return_value.messages.return_value
            messages_mock.list.return_value.execute.return_value = {
                "messages": [
                    {"id": "msg3", "threadId": "t3"},
                    {"id": "msg1", "threadId": "t1"},
                    {"id": "msg2", "threadId": "t2"},
                ]
            }

            response_map = {
                "msg1": self._make_msg_response("msg1", "t1"),
                "msg2": self._make_msg_response("msg2", "t2"),
                "msg3": self._make_msg_response("msg3", "t3"),
            }
            mock_service.new_batch_http_request.side_effect = _make_batch_factory(
                response_map=response_map
            )

            from desk.services.gmail import GmailClient

            client = GmailClient(mock_credentials)
            result = client.search("is:unread")

            ids = [m["id"] for m in result["messages"]]
            assert ids == ["msg3", "msg1", "msg2"]


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


class TestCollectHeaders:
    """Tests for _collect_headers helper (ADR-022)."""

    @staticmethod
    def _hdrs():
        return [
            {"name": "From", "value": "a@example.com"},
            {"name": "Subject", "value": "Hi"},
            {"name": "List-Unsubscribe", "value": "<mailto:u@x>"},
            {"name": "Received", "value": "by host1"},
            {"name": "Received", "value": "by host2"},
        ]

    def test_empty_requested_returns_empty(self):
        from desk.services.gmail import _collect_headers
        assert _collect_headers(self._hdrs(), []) == {}

    def test_wildcard_returns_every_header(self):
        from desk.services.gmail import _collect_headers
        out = _collect_headers(self._hdrs(), ["*"])
        assert set(out.keys()) == {
            "From", "Subject", "List-Unsubscribe", "Received"
        }
        # Each value is a list of strings, preserving order for multi-valued.
        assert out["Received"] == ["by host1", "by host2"]
        assert out["From"] == ["a@example.com"]

    def test_case_insensitive_match_preserves_source_casing(self):
        from desk.services.gmail import _collect_headers
        out = _collect_headers(self._hdrs(), ["list-unsubscribe"])
        assert "List-Unsubscribe" in out
        assert out["List-Unsubscribe"] == ["<mailto:u@x>"]

    def test_unknown_name_silently_omitted(self):
        from desk.services.gmail import _collect_headers
        out = _collect_headers(self._hdrs(), ["X-Does-Not-Exist"])
        assert out == {}

    def test_multi_valued_header_returns_all_occurrences(self):
        from desk.services.gmail import _collect_headers
        out = _collect_headers(self._hdrs(), ["Received"])
        assert out == {"Received": ["by host1", "by host2"]}


class TestGmailReadWithHeaders:
    """Tests for GmailClient.read with extra_headers (ADR-022)."""

    def test_read_with_explicit_headers_returns_dict(self, mock_credentials):
        body_text = "body"
        encoded_body = base64.urlsafe_b64encode(body_text.encode()).decode()

        with patch("desk.services.gmail.build") as mock_build:
            mock_service = MagicMock()
            mock_build.return_value = mock_service
            messages_mock = mock_service.users.return_value.messages.return_value
            messages_mock.get.return_value.execute.return_value = {
                "id": "m1",
                "threadId": "t1",
                "payload": {
                    "headers": [
                        {"name": "From", "value": "a@x"},
                        {"name": "Subject", "value": "s"},
                        {"name": "List-Unsubscribe", "value": "<mailto:u@x>"},
                    ],
                    "body": {"data": encoded_body},
                },
            }

            from desk.services.gmail import GmailClient
            client = GmailClient(mock_credentials)
            result = client.read("m1", extra_headers=["List-Unsubscribe"])

            assert result["headers"] == {
                "List-Unsubscribe": ["<mailto:u@x>"]
            }

    def test_read_without_headers_flag_has_no_headers_field(self, mock_credentials):
        body_text = "body"
        encoded_body = base64.urlsafe_b64encode(body_text.encode()).decode()

        with patch("desk.services.gmail.build") as mock_build:
            mock_service = MagicMock()
            mock_build.return_value = mock_service
            messages_mock = mock_service.users.return_value.messages.return_value
            messages_mock.get.return_value.execute.return_value = {
                "id": "m1",
                "threadId": "t1",
                "payload": {
                    "headers": [{"name": "From", "value": "a@x"}],
                    "body": {"data": encoded_body},
                },
            }

            from desk.services.gmail import GmailClient
            client = GmailClient(mock_credentials)
            result = client.read("m1")

            assert "headers" not in result


class TestGmailSearchWithHeaders:
    """Tests for GmailClient.search with extra_headers (ADR-022)."""

    def test_search_with_headers_augments_metadataHeaders(self, mock_credentials):
        with patch("desk.services.gmail.build") as mock_build:
            mock_service = MagicMock()
            mock_build.return_value = mock_service
            messages_mock = mock_service.users.return_value.messages.return_value
            messages_mock.list.return_value.execute.return_value = {
                "messages": [{"id": "m1", "threadId": "t1"}]
            }
            response_map = {
                "m1": {
                    "id": "m1",
                    "threadId": "t1",
                    "payload": {
                        "headers": [
                            {"name": "From", "value": "a@x"},
                            {"name": "List-Unsubscribe", "value": "<u>"},
                        ]
                    },
                }
            }
            mock_service.new_batch_http_request.side_effect = _make_batch_factory(
                response_map=response_map
            )

            from desk.services.gmail import GmailClient
            client = GmailClient(mock_credentials)
            result = client.search("is:unread", extra_headers=["List-Unsubscribe"])

            # The List-Unsubscribe name appears in metadataHeaders kwargs passed
            # to messages.get() for the batched per-message fetch.
            get_calls = messages_mock.get.call_args_list
            assert any(
                "List-Unsubscribe" in (call.kwargs.get("metadataHeaders") or [])
                for call in get_calls
            )
            assert result["messages"][0]["headers"] == {
                "List-Unsubscribe": ["<u>"]
            }

    def test_search_with_wildcard_drops_metadataHeaders(self, mock_credentials):
        with patch("desk.services.gmail.build") as mock_build:
            mock_service = MagicMock()
            mock_build.return_value = mock_service
            messages_mock = mock_service.users.return_value.messages.return_value
            messages_mock.list.return_value.execute.return_value = {
                "messages": [{"id": "m1", "threadId": "t1"}]
            }
            mock_service.new_batch_http_request.side_effect = _make_batch_factory(
                response_map={
                    "m1": {"id": "m1", "threadId": "t1", "payload": {"headers": []}}
                }
            )

            from desk.services.gmail import GmailClient
            client = GmailClient(mock_credentials)
            client.search("is:unread", extra_headers=["*"])

            get_calls = messages_mock.get.call_args_list
            # No metadataHeaders kwarg when wildcard is requested.
            assert all("metadataHeaders" not in call.kwargs for call in get_calls)


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

            thread_response = {
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
            response_map = {
                "thread1": thread_response,
                "thread2": {**thread_response, "id": "thread2"},
            }
            mock_service.new_batch_http_request.side_effect = _make_batch_factory(
                response_map=response_map
            )

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


class TestGmailListDrafts:
    """Tests for GmailClient.list_drafts method."""

    def test_list_drafts_returns_drafts(self, mock_credentials):
        """Should return list of drafts with details."""
        with patch("desk.services.gmail.build") as mock_build:
            mock_service = MagicMock()
            mock_build.return_value = mock_service

            drafts_mock = mock_service.users.return_value.drafts.return_value
            drafts_mock.list.return_value.execute.return_value = {
                "drafts": [{"id": "draft1"}, {"id": "draft2"}]
            }

            response_map = {
                "draft1": {
                    "id": "draft1",
                    "message": {
                        "id": "msg1",
                        "snippet": "Draft 1 snippet",
                        "payload": {
                            "headers": [
                                {"name": "To", "value": "alice@example.com"},
                                {"name": "Subject", "value": "Draft Subject 1"},
                            ]
                        },
                    },
                },
                "draft2": {
                    "id": "draft2",
                    "message": {
                        "id": "msg2",
                        "snippet": "Draft 2 snippet",
                        "payload": {
                            "headers": [
                                {"name": "To", "value": "bob@example.com"},
                                {"name": "Subject", "value": "Draft Subject 2"},
                            ]
                        },
                    },
                },
            }
            mock_service.new_batch_http_request.side_effect = _make_batch_factory(
                response_map=response_map
            )

            from desk.services.gmail import GmailClient

            client = GmailClient(mock_credentials)
            result = client.list_drafts()

            assert "drafts" in result
            assert len(result["drafts"]) == 2
            assert result["drafts"][0]["id"] == "draft1"
            assert result["drafts"][0]["to"] == "alice@example.com"
            assert result["drafts"][1]["subject"] == "Draft Subject 2"

    def test_list_drafts_empty(self, mock_credentials):
        """Should return empty list when no drafts."""
        with patch("desk.services.gmail.build") as mock_build:
            mock_service = MagicMock()
            mock_build.return_value = mock_service

            drafts_mock = mock_service.users.return_value.drafts.return_value
            drafts_mock.list.return_value.execute.return_value = {"drafts": []}

            from desk.services.gmail import GmailClient

            client = GmailClient(mock_credentials)
            result = client.list_drafts()

            assert result == {"drafts": []}


class TestLabelCache:
    """Tests for label cache behavior in GmailClient."""

    def test_label_cache_avoids_repeated_api_calls(self, mock_credentials):
        """_get_label_id should call list_labels once, then use cache."""
        with patch("desk.services.gmail.build") as mock_build:
            mock_service = MagicMock()
            mock_build.return_value = mock_service

            labels_mock = mock_service.users.return_value.labels.return_value
            labels_mock.list.return_value.execute.return_value = {
                "labels": [
                    {"id": "Label_1", "name": "Work"},
                    {"id": "Label_2", "name": "Personal"},
                ]
            }

            from desk.services.gmail import GmailClient

            client = GmailClient(mock_credentials)

            # First call populates cache
            result1 = client._get_label_id("Work")
            assert result1 == "Label_1"

            # Second call should use cache, not call API again
            result2 = client._get_label_id("Personal")
            assert result2 == "Label_2"

            # list_labels should have been called only once
            labels_mock.list.return_value.execute.assert_called_once()

    def test_label_cache_invalidated_after_create(self, mock_credentials):
        """Cache should be cleared after create_label."""
        with patch("desk.services.gmail.build") as mock_build:
            mock_service = MagicMock()
            mock_build.return_value = mock_service

            labels_mock = mock_service.users.return_value.labels.return_value
            labels_mock.list.return_value.execute.return_value = {
                "labels": []
            }
            labels_mock.create.return_value.execute.return_value = {
                "id": "Label_new", "name": "NewLabel"
            }

            from desk.services.gmail import GmailClient

            client = GmailClient(mock_credentials)

            # Populate cache
            client._get_label_id("anything")
            assert client._labels_cache is not None

            # create_label should invalidate
            client.create_label("NewLabel")
            assert client._labels_cache is None

    def test_label_cache_invalidated_after_delete(self, mock_credentials):
        """Cache should be cleared after delete_label."""
        with patch("desk.services.gmail.build") as mock_build:
            mock_service = MagicMock()
            mock_build.return_value = mock_service

            labels_mock = mock_service.users.return_value.labels.return_value
            labels_mock.list.return_value.execute.return_value = {
                "labels": [{"id": "Label_1", "name": "ToDelete"}]
            }

            from desk.services.gmail import GmailClient

            client = GmailClient(mock_credentials)

            # Populate cache
            client._get_label_id("ToDelete")
            assert client._labels_cache is not None

            # delete_label should invalidate
            client.delete_label("ToDelete")
            assert client._labels_cache is None

    def test_label_cache_invalidated_after_rename(self, mock_credentials):
        """Cache should be cleared after rename_label."""
        with patch("desk.services.gmail.build") as mock_build:
            mock_service = MagicMock()
            mock_build.return_value = mock_service

            labels_mock = mock_service.users.return_value.labels.return_value
            # First call: returns old label; second call (after invalidation): returns renamed
            labels_mock.list.return_value.execute.side_effect = [
                {"labels": [{"id": "Label_1", "name": "OldName"}]},
                {"labels": [{"id": "Label_1", "name": "OldName"}]},
                {"labels": [{"id": "Label_1", "name": "NewName"}]},
            ]
            labels_mock.patch.return_value.execute.return_value = {
                "id": "Label_1", "name": "NewName"
            }

            from desk.services.gmail import GmailClient

            client = GmailClient(mock_credentials)

            # Populate cache via rename_label's internal _get_label_id calls
            client.rename_label("OldName", "NewName")

            # Cache should be invalidated
            assert client._labels_cache is None


class TestTimeoutServiceCache:
    """Tests for timeout service caching in GmailClient."""

    def test_timeout_service_cached_by_value(self, mock_credentials):
        """Same timeout value should return cached service."""
        with patch("desk.services.gmail.build") as mock_build:
            mock_service = MagicMock()
            mock_build.return_value = mock_service

            from desk.services.gmail import GmailClient

            client = GmailClient(mock_credentials)

            svc1 = client._build_service_with_timeout(300)
            svc2 = client._build_service_with_timeout(300)

            assert svc1 is svc2
            # build() called once for __init__, once for timeout=300
            assert mock_build.call_count == 2

    def test_different_timeouts_get_different_services(self, mock_credentials):
        """Different timeout values should create separate services."""
        with patch("desk.services.gmail.build") as mock_build:
            # Return a new MagicMock for each call so they're distinct objects
            mock_build.side_effect = lambda *a, **kw: MagicMock()

            from desk.services.gmail import GmailClient

            client = GmailClient(mock_credentials)

            svc1 = client._build_service_with_timeout(300)
            svc2 = client._build_service_with_timeout(600)

            assert svc1 is not svc2
            # build() called once for __init__, once for 300, once for 600
            assert mock_build.call_count == 3


class TestExtractBodyParts:
    """Tests for GmailClient._extract_body_parts method."""

    def test_returns_plain_and_html(self, mock_credentials):
        """Should return both plain text and HTML from multipart message."""
        plain_text = "Hello plain"
        html_text = "<p>Hello html</p>"
        encoded_plain = base64.urlsafe_b64encode(plain_text.encode()).decode()
        encoded_html = base64.urlsafe_b64encode(html_text.encode()).decode()

        with patch("desk.services.gmail.build") as mock_build:
            mock_build.return_value = MagicMock()
            from desk.services.gmail import GmailClient

            client = GmailClient(mock_credentials)
            payload = {
                "mimeType": "multipart/alternative",
                "parts": [
                    {"mimeType": "text/plain", "body": {"data": encoded_plain}},
                    {"mimeType": "text/html", "body": {"data": encoded_html}},
                ],
            }
            plain, html = client._extract_body_parts(payload)

            assert plain == plain_text
            assert html == html_text

    def test_plain_only(self, mock_credentials):
        """Should return plain text and empty HTML when only plain is present."""
        plain_text = "Just plain"
        encoded = base64.urlsafe_b64encode(plain_text.encode()).decode()

        with patch("desk.services.gmail.build") as mock_build:
            mock_build.return_value = MagicMock()
            from desk.services.gmail import GmailClient

            client = GmailClient(mock_credentials)
            payload = {
                "mimeType": "text/plain",
                "body": {"data": encoded},
            }
            plain, html = client._extract_body_parts(payload)

            assert plain == plain_text
            assert html == ""

    def test_html_only_direct(self, mock_credentials):
        """Should return HTML when mimeType is text/html directly."""
        html_text = "<p>HTML only</p>"
        encoded = base64.urlsafe_b64encode(html_text.encode()).decode()

        with patch("desk.services.gmail.build") as mock_build:
            mock_build.return_value = MagicMock()
            from desk.services.gmail import GmailClient

            client = GmailClient(mock_credentials)
            payload = {
                "mimeType": "text/html",
                "body": {"data": encoded},
            }
            plain, html = client._extract_body_parts(payload)

            assert plain == ""
            assert html == html_text

    def test_nested_multipart(self, mock_credentials):
        """Should recurse into nested multipart structures."""
        plain_text = "Nested plain"
        html_text = "<p>Nested html</p>"
        encoded_plain = base64.urlsafe_b64encode(plain_text.encode()).decode()
        encoded_html = base64.urlsafe_b64encode(html_text.encode()).decode()

        with patch("desk.services.gmail.build") as mock_build:
            mock_build.return_value = MagicMock()
            from desk.services.gmail import GmailClient

            client = GmailClient(mock_credentials)
            payload = {
                "mimeType": "multipart/mixed",
                "parts": [
                    {
                        "mimeType": "multipart/alternative",
                        "parts": [
                            {"mimeType": "text/plain", "body": {"data": encoded_plain}},
                            {"mimeType": "text/html", "body": {"data": encoded_html}},
                        ],
                    },
                ],
            }
            plain, html = client._extract_body_parts(payload)

            assert plain == plain_text
            assert html == html_text


class TestParseFullMessageLinks:
    """Tests for links in _parse_full_message."""

    def test_includes_links_from_html(self, mock_credentials):
        """Should include links array extracted from HTML body."""
        plain_text = "Check this doc"
        html_text = '<p>Check <a href="https://docs.google.com/document/d/1abc/edit">this doc</a></p>'
        encoded_plain = base64.urlsafe_b64encode(plain_text.encode()).decode()
        encoded_html = base64.urlsafe_b64encode(html_text.encode()).decode()

        with patch("desk.services.gmail.build") as mock_build:
            mock_build.return_value = MagicMock()
            from desk.services.gmail import GmailClient

            client = GmailClient(mock_credentials)
            msg = {
                "id": "msg1",
                "threadId": "t1",
                "payload": {
                    "headers": [{"name": "From", "value": "test@example.com"}],
                    "parts": [
                        {"mimeType": "text/plain", "body": {"data": encoded_plain}},
                        {"mimeType": "text/html", "body": {"data": encoded_html}},
                    ],
                },
            }
            result = client._parse_full_message(msg)

            assert "links" in result
            assert len(result["links"]) == 1
            assert result["links"][0]["type"] == "google-doc"
            assert result["links"][0]["readable_via"] == "desk docs read 1abc"

    def test_empty_links_when_no_html(self, mock_credentials):
        """Should return empty links when no HTML part."""
        plain_text = "Just plain text"
        encoded = base64.urlsafe_b64encode(plain_text.encode()).decode()

        with patch("desk.services.gmail.build") as mock_build:
            mock_build.return_value = MagicMock()
            from desk.services.gmail import GmailClient

            client = GmailClient(mock_credentials)
            msg = {
                "id": "msg1",
                "threadId": "t1",
                "payload": {
                    "headers": [{"name": "From", "value": "test@example.com"}],
                    "mimeType": "text/plain",
                    "body": {"data": encoded},
                },
            }
            result = client._parse_full_message(msg)

            assert result["links"] == []


class TestListSendAsAliases:
    """Tests for GmailClient.list_send_as_aliases method."""

    def test_returns_aliases(self, mock_credentials):
        """Should return list of alias dicts."""
        with patch("desk.services.gmail.build") as mock_build:
            mock_service = MagicMock()
            mock_build.return_value = mock_service

            settings = mock_service.users.return_value.settings.return_value
            send_as = settings.sendAs.return_value
            send_as.list.return_value.execute.return_value = {
                "sendAs": [
                    {
                        "sendAsEmail": "primary@example.com",
                        "displayName": "Primary",
                        "isDefault": True,
                        "isPrimary": True,
                        "verificationStatus": "accepted",
                    },
                    {
                        "sendAsEmail": "alias@example.com",
                        "displayName": "Alias",
                        "isDefault": False,
                        "isPrimary": False,
                        "verificationStatus": "accepted",
                    },
                ]
            }

            from desk.services.gmail import GmailClient

            client = GmailClient(mock_credentials)
            result = client.list_send_as_aliases()

            assert len(result) == 2
            assert result[0]["sendAsEmail"] == "primary@example.com"
            assert result[0]["isDefault"] is True
            assert result[1]["sendAsEmail"] == "alias@example.com"

    def test_empty_aliases(self, mock_credentials):
        """Should return empty list when no aliases configured."""
        with patch("desk.services.gmail.build") as mock_build:
            mock_service = MagicMock()
            mock_build.return_value = mock_service

            settings = mock_service.users.return_value.settings.return_value
            send_as = settings.sendAs.return_value
            send_as.list.return_value.execute.return_value = {"sendAs": []}

            from desk.services.gmail import GmailClient

            client = GmailClient(mock_credentials)
            result = client.list_send_as_aliases()

            assert result == []


class TestDetectSendAsAlias:
    """Tests for GmailClient.detect_send_as_alias method."""

    def _make_client_with_aliases(self, mock_credentials, aliases):
        """Helper to create a client with mocked aliases."""
        with patch("desk.services.gmail.build") as mock_build:
            mock_service = MagicMock()
            mock_build.return_value = mock_service

            settings = mock_service.users.return_value.settings.return_value
            send_as = settings.sendAs.return_value
            send_as.list.return_value.execute.return_value = {
                "sendAs": aliases
            }

            from desk.services.gmail import GmailClient

            return GmailClient(mock_credentials)

    def test_matches_delivered_to(self, mock_credentials):
        """Should match Delivered-To header first."""
        aliases = [
            {"sendAsEmail": "alias@example.com", "isPrimary": False,
             "verificationStatus": "accepted"},
            {"sendAsEmail": "primary@example.com", "isPrimary": True,
             "verificationStatus": "accepted"},
        ]
        client = self._make_client_with_aliases(mock_credentials, aliases)
        msg = {
            "deliveredTo": "alias@example.com",
            "to": "primary@example.com",
        }
        assert client.detect_send_as_alias(msg) == "alias@example.com"

    def test_matches_to_header(self, mock_credentials):
        """Should match To header when Delivered-To is absent."""
        aliases = [
            {"sendAsEmail": "alias@example.com", "isPrimary": False,
             "verificationStatus": "accepted"},
        ]
        client = self._make_client_with_aliases(mock_credentials, aliases)
        msg = {"to": "alias@example.com", "deliveredTo": ""}
        assert client.detect_send_as_alias(msg) == "alias@example.com"

    def test_matches_cc_header(self, mock_credentials):
        """Should match CC when To doesn't match."""
        aliases = [
            {"sendAsEmail": "alias@example.com", "isPrimary": False,
             "verificationStatus": "accepted"},
        ]
        client = self._make_client_with_aliases(mock_credentials, aliases)
        msg = {
            "to": "someone@other.com",
            "cc": "alias@example.com",
            "deliveredTo": "",
        }
        assert client.detect_send_as_alias(msg) == "alias@example.com"

    def test_returns_none_when_no_match(self, mock_credentials):
        """Should return None when no alias matches."""
        aliases = [
            {"sendAsEmail": "primary@example.com", "isPrimary": True,
             "verificationStatus": "accepted"},
        ]
        client = self._make_client_with_aliases(mock_credentials, aliases)
        msg = {"to": "unknown@other.com", "deliveredTo": "", "cc": ""}
        assert client.detect_send_as_alias(msg) is None

    def test_matches_name_angle_bracket_format(self, mock_credentials):
        """Should match 'Name <email>' format in To header."""
        aliases = [
            {"sendAsEmail": "alias@example.com", "isPrimary": False,
             "verificationStatus": "accepted"},
        ]
        client = self._make_client_with_aliases(mock_credentials, aliases)
        msg = {
            "to": "My Alias <alias@example.com>",
            "deliveredTo": "",
        }
        assert client.detect_send_as_alias(msg) == "alias@example.com"

    def test_case_insensitive_match(self, mock_credentials):
        """Should match case-insensitively."""
        aliases = [
            {"sendAsEmail": "Alias@Example.com", "isPrimary": False,
             "verificationStatus": "accepted"},
        ]
        client = self._make_client_with_aliases(mock_credentials, aliases)
        msg = {
            "to": "alias@example.com",
            "deliveredTo": "",
        }
        assert client.detect_send_as_alias(msg) == "alias@example.com"


class TestSendFromAlias:
    """Tests for from_addr parameter on send/reply/forward."""

    def test_send_sets_from_header(self, mock_credentials):
        """send() with from_addr should set From MIME header."""
        with patch("desk.services.gmail.build") as mock_build:
            mock_service = MagicMock()
            mock_build.return_value = mock_service

            users = mock_service.users.return_value
            messages = users.messages.return_value
            messages.send.return_value.execute.return_value = {
                "id": "msg123", "threadId": "t1"
            }

            from desk.services.gmail import GmailClient

            client = GmailClient(mock_credentials)
            client.send(
                to=["recipient@example.com"],
                subject="Test",
                body="Hello",
                from_addr="alias@example.com",
            )

            call_kwargs = messages.send.call_args[1]
            import base64 as b64
            raw = b64.urlsafe_b64decode(
                call_kwargs["body"]["raw"]
            ).decode("utf-8")
            assert "alias@example.com" in raw
            assert "from:" in raw.lower()

    def test_send_without_from_has_no_from_header(self, mock_credentials):
        """send() without from_addr should not set explicit From."""
        with patch("desk.services.gmail.build") as mock_build:
            mock_service = MagicMock()
            mock_build.return_value = mock_service

            users = mock_service.users.return_value
            messages = users.messages.return_value
            messages.send.return_value.execute.return_value = {
                "id": "msg123", "threadId": "t1"
            }

            from desk.services.gmail import GmailClient

            client = GmailClient(mock_credentials)
            client.send(
                to=["recipient@example.com"],
                subject="Test",
                body="Hello",
            )

            call_kwargs = messages.send.call_args[1]
            import base64 as b64
            raw = b64.urlsafe_b64decode(
                call_kwargs["body"]["raw"]
            ).decode("utf-8")
            assert "From: alias" not in raw
