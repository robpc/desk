"""Tests for Calendar service client."""

from unittest.mock import MagicMock, patch

import pytest
from googleapiclient.errors import HttpError


class TestCalendarClientInit:
    """Tests for CalendarClient initialization."""

    def test_creates_service_with_credentials(self, mock_credentials):
        """Should create Calendar service with provided credentials."""
        with patch("desk.services.calendar.build") as mock_build:
            mock_build.return_value = MagicMock()
            from desk.services.calendar import CalendarClient

            CalendarClient(mock_credentials)

            mock_build.assert_called_once_with("calendar", "v3", credentials=mock_credentials)


class TestCalendarToday:
    """Tests for CalendarClient.today method."""

    def test_today_returns_events(self, mock_credentials):
        """Should return today's events."""
        with patch("desk.services.calendar.build") as mock_build:
            mock_service = MagicMock()
            mock_build.return_value = mock_service

            events_mock = mock_service.events.return_value
            events_mock.list.return_value.execute.return_value = {
                "items": [
                    {
                        "id": "event1",
                        "summary": "Morning Meeting",
                        "start": {"dateTime": "2024-01-15T09:00:00-05:00"},
                        "end": {"dateTime": "2024-01-15T10:00:00-05:00"},
                    },
                ]
            }

            from desk.services.calendar import CalendarClient

            client = CalendarClient(mock_credentials)
            result = client.today()

            assert "events" in result
            assert len(result["events"]) == 1


class TestCalendarNext:
    """Tests for CalendarClient.next method."""

    def test_next_returns_upcoming_events(self, mock_credentials):
        """Should return next upcoming events."""
        with patch("desk.services.calendar.build") as mock_build:
            mock_service = MagicMock()
            mock_build.return_value = mock_service

            events_mock = mock_service.events.return_value
            events_mock.list.return_value.execute.return_value = {
                "items": [
                    {"id": "event1", "summary": "Next Event"},
                ]
            }

            from desk.services.calendar import CalendarClient

            client = CalendarClient(mock_credentials)
            result = client.next()

            assert "events" in result
            assert len(result["events"]) == 1

    def test_next_with_max_results(self, mock_credentials):
        """Should pass max_results to API."""
        with patch("desk.services.calendar.build") as mock_build:
            mock_service = MagicMock()
            mock_build.return_value = mock_service

            events_mock = mock_service.events.return_value
            events_mock.list.return_value.execute.return_value = {"items": []}

            from desk.services.calendar import CalendarClient

            client = CalendarClient(mock_credentials)
            client.next(max_results=5)

            call_kwargs = events_mock.list.call_args[1]
            assert call_kwargs["maxResults"] == 5


class TestCalendarListCalendars:
    """Tests for CalendarClient.list_calendars method."""

    def test_list_calendars_returns_calendars(self, mock_credentials):
        """Should return list of calendars."""
        with patch("desk.services.calendar.build") as mock_build:
            mock_service = MagicMock()
            mock_build.return_value = mock_service

            calendar_list_mock = mock_service.calendarList.return_value
            calendar_list_mock.list.return_value.execute.return_value = {
                "items": [
                    {"id": "primary", "summary": "Primary Calendar", "primary": True},
                    {"id": "work@group.calendar.google.com", "summary": "Work"},
                ]
            }

            from desk.services.calendar import CalendarClient

            client = CalendarClient(mock_credentials)
            result = client.list_calendars()

            assert len(result) == 2
            assert result[0]["primary"] is True


class TestCalendarCreate:
    """Tests for CalendarClient.create method."""

    def test_create_returns_event(self, mock_credentials):
        """Should return created event."""
        with patch("desk.services.calendar.build") as mock_build:
            mock_service = MagicMock()
            mock_build.return_value = mock_service

            events_mock = mock_service.events.return_value
            events_mock.insert.return_value.execute.return_value = {
                "id": "new_event_id",
                "summary": "New Event",
                "start": {"dateTime": "2024-01-15T14:00:00-05:00"},
                "end": {"dateTime": "2024-01-15T15:00:00-05:00"},
            }

            from desk.services.calendar import CalendarClient

            client = CalendarClient(mock_credentials)
            result = client.create(
                summary="New Event",
                start="2024-01-15T14:00:00-05:00",
                end="2024-01-15T15:00:00-05:00",
            )

            assert "id" in result
            events_mock.insert.assert_called_once()


class TestCalendarDelete:
    """Tests for CalendarClient.delete method."""

    def test_delete_calls_api(self, mock_credentials):
        """Should call delete API."""
        with patch("desk.services.calendar.build") as mock_build:
            mock_service = MagicMock()
            mock_build.return_value = mock_service

            events_mock = mock_service.events.return_value
            events_mock.delete.return_value.execute.return_value = None

            from desk.services.calendar import CalendarClient

            client = CalendarClient(mock_credentials)
            client.delete("event123")

            events_mock.delete.assert_called_once()
            call_kwargs = events_mock.delete.call_args[1]
            assert call_kwargs["eventId"] == "event123"

    def test_delete_not_found_raises_error(self, mock_credentials):
        """Should raise error when event not found."""
        with patch("desk.services.calendar.build") as mock_build:
            mock_service = MagicMock()
            mock_build.return_value = mock_service

            events_mock = mock_service.events.return_value
            http_error = HttpError(
                resp=MagicMock(status=404),
                content=b'{"error": {"message": "Not found"}}'
            )
            events_mock.delete.return_value.execute.side_effect = http_error

            from desk.services.calendar import CalendarClient

            client = CalendarClient(mock_credentials)
            with pytest.raises(RuntimeError, match="Calendar API error"):
                client.delete("nonexistent_id")


class TestCalendarUpdateRemoveAttendees:
    """Tests for CalendarClient.update with remove_attendees."""

    def _make_client(self, mock_credentials, mock_service):
        """Helper: create a CalendarClient backed by a mock service."""
        with patch("desk.services.calendar.build") as mock_build:
            mock_build.return_value = mock_service
            from desk.services.calendar import CalendarClient
            return CalendarClient(mock_credentials)

    def _setup_event(self, mock_service, attendees):
        """Helper: configure mock to return an event with given attendees."""
        events_mock = mock_service.events.return_value
        event = {
            "id": "ev1",
            "summary": "Team Sync",
            "start": {"dateTime": "2024-01-15T09:00:00-05:00"},
            "end": {"dateTime": "2024-01-15T10:00:00-05:00"},
            "attendees": [{"email": e} for e in attendees],
        }
        events_mock.get.return_value.execute.return_value = dict(event)
        # update() returns the same event structure
        events_mock.update.return_value.execute.return_value = dict(event)
        return events_mock

    def test_remove_attendee_filters_from_list(self, mock_credentials):
        """Should remove matching attendee from the event body sent to API."""
        mock_service = MagicMock()
        events_mock = self._setup_event(
            mock_service, ["alice@example.com", "bob@example.com"]
        )
        client = self._make_client(mock_credentials, mock_service)
        client.update("ev1", remove_attendees=["bob@example.com"])

        body = events_mock.update.call_args[1]["body"]
        emails = [a["email"] for a in body["attendees"]]
        assert "bob@example.com" not in emails
        assert "alice@example.com" in emails

    def test_remove_attendee_case_insensitive(self, mock_credentials):
        """Should match emails case-insensitively."""
        mock_service = MagicMock()
        events_mock = self._setup_event(
            mock_service, ["Alice@Example.com", "bob@example.com"]
        )
        client = self._make_client(mock_credentials, mock_service)
        client.update("ev1", remove_attendees=["alice@example.com"])

        body = events_mock.update.call_args[1]["body"]
        emails = [a["email"] for a in body["attendees"]]
        assert "Alice@Example.com" not in emails
        assert "bob@example.com" in emails

    def test_remove_nonexistent_attendee_is_no_op(self, mock_credentials):
        """Removing an email not in the list should leave attendees unchanged."""
        mock_service = MagicMock()
        events_mock = self._setup_event(
            mock_service, ["alice@example.com"]
        )
        client = self._make_client(mock_credentials, mock_service)
        result = client.update("ev1", remove_attendees=["nobody@example.com"])

        body = events_mock.update.call_args[1]["body"]
        emails = [a["email"] for a in body["attendees"]]
        assert "alice@example.com" in emails
        assert result["removedAttendees"] == []

    def test_remove_multiple_attendees(self, mock_credentials):
        """Should remove multiple attendees in one call."""
        mock_service = MagicMock()
        events_mock = self._setup_event(
            mock_service, ["alice@example.com", "bob@example.com", "carol@example.com"]
        )
        client = self._make_client(mock_credentials, mock_service)
        client.update("ev1", remove_attendees=["alice@example.com", "carol@example.com"])

        body = events_mock.update.call_args[1]["body"]
        emails = [a["email"] for a in body["attendees"]]
        assert emails == ["bob@example.com"]

    def test_removed_attendees_in_result(self, mock_credentials):
        """Result should include removedAttendees with actually removed emails."""
        mock_service = MagicMock()
        self._setup_event(
            mock_service, ["alice@example.com", "bob@example.com"]
        )
        client = self._make_client(mock_credentials, mock_service)
        result = client.update("ev1", remove_attendees=["bob@example.com"])

        assert result["removedAttendees"] == ["bob@example.com"]

    def test_no_removed_attendees_key_when_not_removing(self, mock_credentials):
        """Result should not include removedAttendees when not removing anyone."""
        mock_service = MagicMock()
        self._setup_event(mock_service, ["alice@example.com"])
        client = self._make_client(mock_credentials, mock_service)
        result = client.update("ev1", summary="New Title")

        assert "removedAttendees" not in result


class TestParseEventAttendees:
    """Tests for attendee structure in _parse_event output."""

    def _make_client_with_event(self, mock_credentials, event):
        """Helper: create a CalendarClient that returns a single event from today()."""
        with patch("desk.services.calendar.build") as mock_build:
            mock_service = MagicMock()
            mock_build.return_value = mock_service

            events_mock = mock_service.events.return_value
            events_mock.list.return_value.execute.return_value = {
                "items": [event]
            }

            from desk.services.calendar import CalendarClient

            client = CalendarClient(mock_credentials)
            result = client.today()
            return result["events"][0]

    def test_attendees_are_dicts_with_expected_keys(self, mock_credentials):
        """Attendees should be dicts with email, responseStatus, organizer, self."""
        event = self._make_client_with_event(mock_credentials, {
            "id": "ev1",
            "summary": "Sync",
            "start": {"dateTime": "2024-01-15T09:00:00-05:00"},
            "end": {"dateTime": "2024-01-15T10:00:00-05:00"},
            "attendees": [
                {
                    "email": "alice@example.com",
                    "responseStatus": "accepted",
                    "organizer": True,
                    "self": False,
                },
            ],
        })
        assert len(event["attendees"]) == 1
        attendee = event["attendees"][0]
        assert attendee["email"] == "alice@example.com"
        assert attendee["responseStatus"] == "accepted"
        assert attendee["organizer"] is True
        assert attendee["self"] is False

    def test_response_status_populated_from_api(self, mock_credentials):
        """Each attendee's responseStatus should reflect API data."""
        event = self._make_client_with_event(mock_credentials, {
            "id": "ev2",
            "summary": "Review",
            "start": {"dateTime": "2024-01-15T11:00:00-05:00"},
            "end": {"dateTime": "2024-01-15T12:00:00-05:00"},
            "attendees": [
                {"email": "alice@example.com", "responseStatus": "accepted"},
                {"email": "bob@example.com", "responseStatus": "declined"},
                {"email": "carol@example.com", "responseStatus": "tentative"},
            ],
        })
        statuses = {a["email"]: a["responseStatus"] for a in event["attendees"]}
        assert statuses["alice@example.com"] == "accepted"
        assert statuses["bob@example.com"] == "declined"
        assert statuses["carol@example.com"] == "tentative"

    def test_missing_response_status_defaults_to_needs_action(self, mock_credentials):
        """responseStatus should default to 'needsAction' when absent from API."""
        event = self._make_client_with_event(mock_credentials, {
            "id": "ev3",
            "summary": "New Invite",
            "start": {"dateTime": "2024-01-15T13:00:00-05:00"},
            "end": {"dateTime": "2024-01-15T14:00:00-05:00"},
            "attendees": [
                {"email": "dave@example.com"},
            ],
        })
        assert event["attendees"][0]["responseStatus"] == "needsAction"

    def test_missing_organizer_and_self_default_to_false(self, mock_credentials):
        """organizer and self should default to False when absent from API."""
        event = self._make_client_with_event(mock_credentials, {
            "id": "ev4",
            "summary": "Standup",
            "start": {"dateTime": "2024-01-15T09:30:00-05:00"},
            "end": {"dateTime": "2024-01-15T09:45:00-05:00"},
            "attendees": [
                {"email": "eve@example.com", "responseStatus": "accepted"},
            ],
        })
        assert event["attendees"][0]["organizer"] is False
        assert event["attendees"][0]["self"] is False

    def test_no_attendees_returns_empty_list(self, mock_credentials):
        """Events with no attendees should have an empty attendees list."""
        event = self._make_client_with_event(mock_credentials, {
            "id": "ev5",
            "summary": "Personal Block",
            "start": {"dateTime": "2024-01-15T12:00:00-05:00"},
            "end": {"dateTime": "2024-01-15T13:00:00-05:00"},
        })
        assert event["attendees"] == []
        assert event["attendeeCount"] == 0


class TestParseEventAttachments:
    """Tests for attachment extraction in _parse_event."""

    def _make_client_with_event(self, mock_credentials, raw_event):
        with patch("desk.services.calendar.build") as mock_build:
            mock_service = MagicMock()
            mock_build.return_value = mock_service

            from desk.services.calendar import CalendarClient

            client = CalendarClient(mock_credentials)
            return client._parse_event(raw_event)

    def test_event_with_attachments(self, mock_credentials):
        """Attachments should be included in parsed event."""
        event = self._make_client_with_event(mock_credentials, {
            "id": "ev1",
            "summary": "Review Meeting",
            "start": {"dateTime": "2024-01-15T09:00:00-05:00"},
            "end": {"dateTime": "2024-01-15T10:00:00-05:00"},
            "attachments": [
                {
                    "title": "Meeting Notes",
                    "fileUrl": "https://docs.google.com/document/d/abc",
                    "mimeType": "application/vnd.google-apps.document",
                },
                {
                    "title": "Slides",
                    "fileUrl": "https://docs.google.com/presentation/d/xyz",
                    "mimeType": "application/vnd.google-apps.presentation",
                },
            ],
        })
        assert len(event["attachments"]) == 2
        assert event["attachments"][0]["title"] == "Meeting Notes"
        assert event["attachments"][1]["fileUrl"] == "https://docs.google.com/presentation/d/xyz"

    def test_event_without_attachments_key(self, mock_credentials):
        """Events with no attachments key should have empty list."""
        event = self._make_client_with_event(mock_credentials, {
            "id": "ev2",
            "summary": "Quick Sync",
            "start": {"dateTime": "2024-01-15T11:00:00-05:00"},
            "end": {"dateTime": "2024-01-15T11:30:00-05:00"},
        })
        assert event["attachments"] == []

    def test_event_with_empty_attachments(self, mock_credentials):
        """Events with empty attachments array should have empty list."""
        event = self._make_client_with_event(mock_credentials, {
            "id": "ev3",
            "summary": "Standup",
            "start": {"dateTime": "2024-01-15T10:00:00-05:00"},
            "end": {"dateTime": "2024-01-15T10:15:00-05:00"},
            "attachments": [],
        })
        assert event["attachments"] == []

    def test_attachment_with_missing_fields(self, mock_credentials):
        """Attachments with missing fields should default to empty strings."""
        event = self._make_client_with_event(mock_credentials, {
            "id": "ev4",
            "summary": "Planning",
            "start": {"dateTime": "2024-01-15T14:00:00-05:00"},
            "end": {"dateTime": "2024-01-15T15:00:00-05:00"},
            "attachments": [{"fileUrl": "https://example.com/file"}],
        })
        assert len(event["attachments"]) == 1
        assert event["attachments"][0]["title"] == ""
        assert event["attachments"][0]["mimeType"] == ""
        assert event["attachments"][0]["fileUrl"] == "https://example.com/file"
