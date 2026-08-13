"""Tests for Calendar event fields added in ADR-035 (issue #80).

Focused on the request bodies Desk sends, since that's where the gaps were:
no conferenceData, no guest permissions, and a hardcoded sendUpdates="all".
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from desk.services.calendar import CalendarClient


@pytest.fixture
def client():
    with patch("desk.services.calendar.build") as build:
        service = MagicMock()
        build.return_value = service
        c = CalendarClient(MagicMock())
        c._service_mock = service
        yield c


def _insert_call(client):
    return client._service_mock.events.return_value.insert.call_args


def _update_call(client):
    return client._service_mock.events.return_value.update.call_args


def _set_insert_result(client, result=None):
    client._service_mock.events.return_value.insert.return_value.execute.return_value = (
        result or {"id": "e1", "summary": "x"}
    )


def _set_get_result(client, result):
    client._service_mock.events.return_value.get.return_value.execute.return_value = result


def _set_update_result(client, result=None):
    client._service_mock.events.return_value.update.return_value.execute.return_value = (
        result or {"id": "e1", "summary": "x"}
    )


class TestSendUpdates:
    """The hardcoded "all" was the sharpest edge — you could never opt out."""

    def test_defaults_to_all_preserving_prior_behavior(self, client):
        _set_insert_result(client)
        client.create("Standup", "2026-08-01T10:00:00", "2026-08-01T10:30:00")

        assert _insert_call(client).kwargs["sendUpdates"] == "all"

    def test_none_is_honored(self, client):
        _set_insert_result(client)
        client.create(
            "Standup", "2026-08-01T10:00:00", "2026-08-01T10:30:00", send_updates="none"
        )

        assert _insert_call(client).kwargs["sendUpdates"] == "none"

    def test_cli_spelling_maps_to_api_spelling(self, client):
        """CLI says external-only; the API wants externalOnly."""
        _set_insert_result(client)
        client.create(
            "Standup",
            "2026-08-01T10:00:00",
            "2026-08-01T10:30:00",
            send_updates="external-only",
        )

        assert _insert_call(client).kwargs["sendUpdates"] == "externalOnly"

    def test_delete_can_be_quiet(self, client):
        """Deleting mailed a cancellation to every attendee unconditionally."""
        client.delete("e1", send_updates="none")

        call = client._service_mock.events.return_value.delete.call_args
        assert call.kwargs["sendUpdates"] == "none"

    def test_respond_can_be_quiet(self, client):
        _set_get_result(client, {"id": "e1", "attendees": [{"email": "me@x", "self": True}]})
        _set_update_result(client)
        client.respond("e1", "accepted", send_updates="none")

        assert _update_call(client).kwargs["sendUpdates"] == "none"


class TestMeetConference:
    def test_no_conference_unless_requested(self, client):
        _set_insert_result(client)
        client.create("Standup", "2026-08-01T10:00:00", "2026-08-01T10:30:00")

        assert "conferenceData" not in _insert_call(client).kwargs["body"]

    def test_meet_adds_create_request(self, client):
        _set_insert_result(client)
        client.create(
            "Standup", "2026-08-01T10:00:00", "2026-08-01T10:30:00", meet=True
        )

        body = _insert_call(client).kwargs["body"]
        req = body["conferenceData"]["createRequest"]
        assert req["conferenceSolutionKey"] == {"type": "hangoutsMeet"}
        assert req["requestId"]

    def test_conference_data_version_is_set(self, client):
        """Without conferenceDataVersion=1 the API silently ignores the request."""
        _set_insert_result(client)
        client.create(
            "Standup", "2026-08-01T10:00:00", "2026-08-01T10:30:00", meet=True
        )

        assert _insert_call(client).kwargs["conferenceDataVersion"] == 1

    def test_request_id_is_stable_for_the_same_event(self, client):
        """Calendar treats requestId as an idempotency key, so a retry must reuse it."""
        _set_insert_result(client)
        client.create("Standup", "2026-08-01T10:00:00", "2026-08-01T10:30:00", meet=True)
        first = _insert_call(client).kwargs["body"]["conferenceData"]["createRequest"][
            "requestId"
        ]

        client.create("Standup", "2026-08-01T10:00:00", "2026-08-01T10:30:00", meet=True)
        second = _insert_call(client).kwargs["body"]["conferenceData"]["createRequest"][
            "requestId"
        ]

        assert first == second

    def test_request_id_differs_across_events(self, client):
        _set_insert_result(client)
        client.create("Standup", "2026-08-01T10:00:00", "2026-08-01T10:30:00", meet=True)
        a = _insert_call(client).kwargs["body"]["conferenceData"]["createRequest"]["requestId"]

        client.create("Retro", "2026-08-02T10:00:00", "2026-08-02T10:30:00", meet=True)
        b = _insert_call(client).kwargs["body"]["conferenceData"]["createRequest"]["requestId"]

        assert a != b

    def test_update_adds_conference_when_absent(self, client):
        _set_get_result(client, {"id": "e1", "summary": "Standup", "start": {}})
        _set_update_result(client)
        result = client.update("e1", meet=True)

        assert "createRequest" in _update_call(client).kwargs["body"]["conferenceData"]
        assert result["conferenceAdded"] is True

    def test_update_is_idempotent_when_conference_exists(self, client):
        """Adding --meet twice must not request a second conference."""
        existing = {"conferenceId": "abc-defg-hij"}
        _set_get_result(
            client, {"id": "e1", "summary": "Standup", "conferenceData": existing}
        )
        _set_update_result(client)
        result = client.update("e1", meet=True)

        assert _update_call(client).kwargs["body"]["conferenceData"] == existing
        assert result["conferenceAdded"] is False


class TestEventOptions:
    def test_guest_flags_only_sent_when_asked(self, client):
        """Unset flags must leave Google's defaults alone."""
        _set_insert_result(client)
        client.create("Standup", "2026-08-01T10:00:00", "2026-08-01T10:30:00")

        body = _insert_call(client).kwargs["body"]
        for field in (
            "guestsCanSeeOtherGuests",
            "guestsCanInviteOthers",
            "guestsCanModify",
            "location",
            "visibility",
            "transparency",
        ):
            assert field not in body

    def test_guest_flags_map_to_api_fields(self, client):
        _set_insert_result(client)
        client.create(
            "Standup",
            "2026-08-01T10:00:00",
            "2026-08-01T10:30:00",
            hide_guest_list=True,
            no_guest_invites=True,
            guests_can_modify=True,
        )

        body = _insert_call(client).kwargs["body"]
        assert body["guestsCanSeeOtherGuests"] is False
        assert body["guestsCanInviteOthers"] is False
        assert body["guestsCanModify"] is True

    def test_location_and_visibility(self, client):
        _set_insert_result(client)
        client.create(
            "Standup",
            "2026-08-01T10:00:00",
            "2026-08-01T10:30:00",
            location="Room 4",
            visibility="private",
        )

        body = _insert_call(client).kwargs["body"]
        assert body["location"] == "Room 4"
        assert body["visibility"] == "private"

    def test_free_maps_to_transparency(self, client):
        _set_insert_result(client)
        client.create(
            "Standup", "2026-08-01T10:00:00", "2026-08-01T10:30:00", free=True
        )

        assert _insert_call(client).kwargs["body"]["transparency"] == "transparent"

    def test_update_applies_options(self, client):
        _set_get_result(client, {"id": "e1", "summary": "Standup"})
        _set_update_result(client)
        client.update("e1", location="Room 9", hide_guest_list=True)

        body = _update_call(client).kwargs["body"]
        assert body["location"] == "Room 9"
        assert body["guestsCanSeeOtherGuests"] is False


class TestParseEventConference:
    """The read-side gap not mentioned in #80: Meet links were dropped entirely."""

    def test_surfaces_meet_link_and_conference_id(self, client):
        parsed = client._parse_event(
            {
                "id": "e1",
                "summary": "Standup",
                "hangoutLink": "https://meet.google.com/abc-defg-hij",
                "conferenceData": {"conferenceId": "abc-defg-hij"},
            }
        )

        assert parsed["meetLink"] == "https://meet.google.com/abc-defg-hij"
        assert parsed["conferenceId"] == "abc-defg-hij"

    def test_empty_when_no_conference(self, client):
        parsed = client._parse_event({"id": "e1", "summary": "Standup"})

        assert parsed["meetLink"] == ""
        assert parsed["conferenceId"] == ""

    def test_reports_pending_conference_status(self, client):
        """Conference creation is async, so the link can lag the response."""
        parsed = client._parse_event(
            {
                "id": "e1",
                "summary": "Standup",
                "conferenceData": {
                    "createRequest": {"status": {"statusCode": "pending"}}
                },
            }
        )

        assert parsed["conferenceStatus"] == "pending"
        assert parsed["meetLink"] == ""

    def test_tolerates_null_conference_data(self, client):
        parsed = client._parse_event({"id": "e1", "conferenceData": None})

        assert parsed["conferenceId"] == ""
