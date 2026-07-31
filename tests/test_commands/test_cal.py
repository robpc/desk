"""Tests for cal CLI commands."""

import json
from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner


@pytest.fixture
def runner():
    """Create a Click CLI test runner."""
    return CliRunner()


@pytest.fixture
def mock_get_credentials():
    """Mock the get_credentials function."""
    with patch("desk.commands.cal.get_credentials") as mock:
        mock.return_value = MagicMock()
        yield mock


@pytest.fixture
def mock_calendar_client_class():
    """Mock the CalendarClient class."""
    with patch("desk.commands.cal.CalendarClient") as mock:
        yield mock


class TestCalToday:
    """Tests for desk cal today command."""

    def test_today_with_json_output(self, runner, mock_get_credentials, mock_calendar_client_class):
        """Should output today's events as JSON."""
        from desk.commands.cal import cal

        mock_client = MagicMock()
        mock_client.today.return_value = {
            "events": [
                {
                    "id": "event1",
                    "summary": "Morning Meeting",
                    "start": "2024-01-15T09:00:00",
                    "end": "2024-01-15T10:00:00",
                }
            ]
        }
        mock_calendar_client_class.return_value = mock_client

        result = runner.invoke(cal, ["today", "--json"])

        assert result.exit_code == 0
        output = json.loads(result.output)
        assert "events" in output
        assert len(output["events"]) == 1


class TestCalWeek:
    """Tests for desk cal week command."""

    def test_week_with_json_output(self, runner, mock_get_credentials, mock_calendar_client_class):
        """Should output week's events as JSON."""
        from desk.commands.cal import cal

        mock_client = MagicMock()
        mock_client.week.return_value = {
            "events": [
                {"id": "event1", "summary": "Monday Meeting"},
                {"id": "event2", "summary": "Friday Standup"},
            ]
        }
        mock_calendar_client_class.return_value = mock_client

        result = runner.invoke(cal, ["week", "--json"])

        assert result.exit_code == 0
        output = json.loads(result.output)
        assert len(output["events"]) == 2


class TestCalNext:
    """Tests for desk cal next command."""

    def test_next_with_json_output(self, runner, mock_get_credentials, mock_calendar_client_class):
        """Should output upcoming events as JSON."""
        from desk.commands.cal import cal

        mock_client = MagicMock()
        mock_client.next.return_value = {
            "events": [
                {"id": "event1", "summary": "Next Event"},
            ]
        }
        mock_calendar_client_class.return_value = mock_client

        result = runner.invoke(cal, ["next", "--json"])

        assert result.exit_code == 0
        output = json.loads(result.output)
        assert "events" in output


class TestCalUpdate:
    """Tests for desk cal update command."""

    def test_update_with_remove_attendee(self, runner, mock_get_credentials, mock_calendar_client_class):
        """Should pass remove_attendees through to client and show receipt."""
        from desk.commands.cal import cal

        mock_client = MagicMock()
        mock_client.update.return_value = {
            "id": "ev1",
            "summary": "Team Sync",
            "htmlLink": "https://calendar.google.com/event?eid=ev1",
            "removedAttendees": ["bob@example.com"],
        }
        mock_calendar_client_class.return_value = mock_client

        result = runner.invoke(cal, [
            "update", "ev1",
            "--remove-attendee", "bob@example.com",
            "--json",
        ])

        assert result.exit_code == 0
        mock_client.update.assert_called_once()
        call_kwargs = mock_client.update.call_args
        assert call_kwargs[1]["remove_attendees"] == ["bob@example.com"]

        output = json.loads(result.output)
        assert output["changes"]["removed_attendees"] == ["bob@example.com"]

    def test_update_remove_nonexistent_shows_not_found(self, runner, mock_get_credentials, mock_calendar_client_class):
        """Receipt should include not_found_attendees when email wasn't in attendee list."""
        from desk.commands.cal import cal

        mock_client = MagicMock()
        mock_client.update.return_value = {
            "id": "ev1",
            "summary": "Team Sync",
            "htmlLink": "https://calendar.google.com/event?eid=ev1",
            "removedAttendees": [],
        }
        mock_calendar_client_class.return_value = mock_client

        result = runner.invoke(cal, [
            "update", "ev1",
            "--remove-attendee", "nobody@example.com",
            "--json",
        ])

        assert result.exit_code == 0
        output = json.loads(result.output)
        assert output["changes"]["removed_attendees"] == []
        assert output["changes"]["not_found_attendees"] == ["nobody@example.com"]


class TestCalList:
    """Tests for desk cal list command."""

    def test_list_calendars_json(self, runner, mock_get_credentials, mock_calendar_client_class):
        """Should output calendars as JSON."""
        from desk.commands.cal import cal

        mock_client = MagicMock()
        mock_client.list_calendars.return_value = [
            {"id": "primary", "summary": "Primary", "primary": True},
        ]
        mock_calendar_client_class.return_value = mock_client

        result = runner.invoke(cal, ["list", "--json"])

        assert result.exit_code == 0
        output = json.loads(result.output)
        assert isinstance(output, list)


class TestMultiCalendarFlag:
    """Tests for --calendar flag (ADR-023, issue #27)."""

    @staticmethod
    def _catalog():
        return [
            {"id": "primary", "summary": "Home", "primary": True},
            {"id": "family@group.calendar.google.com", "summary": "Family"},
            {"id": "kids@group.calendar.google.com", "summary": "Kids School"},
        ]

    def test_no_flag_defaults_to_primary(
        self, runner, mock_get_credentials, mock_calendar_client_class
    ):
        from desk.commands.cal import cal

        mock_client = MagicMock()
        mock_client.today.return_value = {"events": []}
        mock_calendar_client_class.return_value = mock_client

        result = runner.invoke(cal, ["today", "--json"])

        assert result.exit_code == 0
        mock_client.today.assert_called_once_with(
            calendar_id="primary", page_token=None, date=None
        )
        # No catalog fetch when no friendly name was used.
        mock_client.list_calendars.assert_not_called()

    def test_friendly_name_resolves_case_insensitively(
        self, runner, mock_get_credentials, mock_calendar_client_class
    ):
        from desk.commands.cal import cal

        mock_client = MagicMock()
        mock_client.list_calendars.return_value = self._catalog()
        mock_client.today.return_value = {
            "events": [
                {
                    "id": "e1",
                    "summary": "Soccer",
                    "start": "2026-05-18T10:00:00",
                    "calendar_id": "family@group.calendar.google.com",
                }
            ]
        }
        mock_calendar_client_class.return_value = mock_client

        result = runner.invoke(cal, ["today", "-c", "family", "--json"])

        assert result.exit_code == 0
        mock_client.today.assert_called_once_with(
            calendar_id="family@group.calendar.google.com",
            page_token=None,
            date=None,
        )

    def test_calendar_id_passes_through_without_catalog_lookup(
        self, runner, mock_get_credentials, mock_calendar_client_class
    ):
        from desk.commands.cal import cal

        mock_client = MagicMock()
        mock_client.today.return_value = {"events": []}
        mock_calendar_client_class.return_value = mock_client

        result = runner.invoke(
            cal,
            ["today", "-c", "family@group.calendar.google.com", "--json"],
        )

        assert result.exit_code == 0
        # @-containing value treated as ID, no catalog fetch needed.
        mock_client.list_calendars.assert_not_called()
        mock_client.today.assert_called_once_with(
            calendar_id="family@group.calendar.google.com",
            page_token=None,
            date=None,
        )

    def test_unknown_friendly_name_errors_with_invalid_input(
        self, runner, mock_get_credentials, mock_calendar_client_class
    ):
        from desk.commands.cal import cal

        mock_client = MagicMock()
        mock_client.list_calendars.return_value = self._catalog()
        mock_calendar_client_class.return_value = mock_client

        result = runner.invoke(
            cal, ["today", "-c", "Bogus", "--json"]        )

        assert result.exit_code == 1
        err = json.loads(result.stderr)
        assert err["error"]["code"] == "INVALID_INPUT"
        assert "Bogus" in err["error"]["details"]["calendar"]

    def test_ambiguous_friendly_name_errors(
        self, runner, mock_get_credentials, mock_calendar_client_class
    ):
        from desk.commands.cal import cal

        mock_client = MagicMock()
        mock_client.list_calendars.return_value = [
            {"id": "a@g.com", "summary": "Family"},
            {"id": "b@g.com", "summary": "Family"},
        ]
        mock_calendar_client_class.return_value = mock_client

        result = runner.invoke(
            cal, ["today", "-c", "Family", "--json"]        )

        assert result.exit_code == 1
        err = json.loads(result.stderr)
        assert err["error"]["code"] == "INVALID_INPUT"
        assert "Multiple" in err["error"]["message"]

    def test_multi_calendar_merges_and_sorts_by_start(
        self, runner, mock_get_credentials, mock_calendar_client_class
    ):
        from desk.commands.cal import cal

        mock_client = MagicMock()
        mock_client.list_calendars.return_value = self._catalog()
        # Primary returns a later event; Family returns an earlier one.
        # The merge must sort them by `start`.
        mock_client.today.side_effect = [
            {"events": [
                {"id": "p1", "summary": "Stand-up",
                 "start": "2026-05-18T10:00:00", "calendar_id": "primary"}
            ]},
            {"events": [
                {"id": "f1", "summary": "Soccer drop-off",
                 "start": "2026-05-18T07:30:00",
                 "calendar_id": "family@group.calendar.google.com"}
            ]},
        ]
        mock_calendar_client_class.return_value = mock_client

        result = runner.invoke(
            cal, ["today", "-c", "primary", "-c", "Family", "--json"]
        )

        assert result.exit_code == 0
        output = json.loads(result.output)
        assert [e["id"] for e in output["events"]] == ["f1", "p1"]
        assert output["events"][0]["calendar_id"].startswith("family@")
        assert output["events"][1]["calendar_id"] == "primary"

    def test_multi_calendar_rejects_page_token(
        self, runner, mock_get_credentials, mock_calendar_client_class
    ):
        from desk.commands.cal import cal

        mock_client = MagicMock()
        mock_client.list_calendars.return_value = self._catalog()
        mock_calendar_client_class.return_value = mock_client

        result = runner.invoke(
            cal,
            ["today", "-c", "primary", "-c", "Family",
             "--page-token", "abc", "--json"],
        )

        assert result.exit_code == 1
        err = json.loads(result.stderr)
        assert err["error"]["code"] == "INVALID_INPUT"
        assert "--page-token" in err["error"]["message"]

    def test_find_multi_calendar_merges(
        self, runner, mock_get_credentials, mock_calendar_client_class
    ):
        from desk.commands.cal import cal

        mock_client = MagicMock()
        mock_client.list_calendars.return_value = self._catalog()
        mock_client.find.side_effect = [
            {"events": [{"id": "p1", "summary": "Open house",
                         "start": "2026-06-01T18:00:00",
                         "calendar_id": "primary"}]},
            {"events": [{"id": "k1", "summary": "School fair",
                         "start": "2026-05-25T09:00:00",
                         "calendar_id": "kids@group.calendar.google.com"}]},
        ]
        mock_calendar_client_class.return_value = mock_client

        result = runner.invoke(
            cal,
            ["find", "school", "-c", "primary", "-c", "Kids School", "--json"],
        )

        assert result.exit_code == 0
        output = json.loads(result.output)
        assert [e["id"] for e in output["events"]] == ["k1", "p1"]


class TestCalCreateEventFields:
    """Flags added in ADR-035 (issue #80)."""

    def _client(self, mock_class, event=None):
        client = MagicMock()
        client.create.return_value = event or {
            "id": "e1",
            "summary": "Training",
            "htmlLink": "https://cal/e1",
        }
        mock_class.return_value = client
        return client

    def test_meet_flag_reaches_service(
        self, runner, mock_get_credentials, mock_calendar_client_class
    ):
        from desk.commands.cal import cal

        client = self._client(mock_calendar_client_class)
        result = runner.invoke(
            cal,
            ["create", "Training", "--start", "2026-08-01T10:00:00",
             "--end", "2026-08-01T11:00:00", "--meet", "--json"],
        )

        assert result.exit_code == 0
        assert client.create.call_args.kwargs["meet"] is True

    def test_guest_and_location_flags_reach_service(
        self, runner, mock_get_credentials, mock_calendar_client_class
    ):
        from desk.commands.cal import cal

        client = self._client(mock_calendar_client_class)
        result = runner.invoke(
            cal,
            ["create", "Training", "--start", "2026-08-01T10:00:00",
             "--end", "2026-08-01T11:00:00", "--hide-guest-list",
             "--no-guest-invites", "--guests-can-modify",
             "--location", "Room 4", "--visibility", "private", "--free", "--json"],
        )

        assert result.exit_code == 0
        kwargs = client.create.call_args.kwargs
        assert kwargs["hide_guest_list"] is True
        assert kwargs["no_guest_invites"] is True
        assert kwargs["guests_can_modify"] is True
        assert kwargs["location"] == "Room 4"
        assert kwargs["visibility"] == "private"
        assert kwargs["free"] is True

    def test_send_updates_defaults_to_all(
        self, runner, mock_get_credentials, mock_calendar_client_class
    ):
        from desk.commands.cal import cal

        client = self._client(mock_calendar_client_class)
        runner.invoke(
            cal,
            ["create", "Training", "--start", "2026-08-01T10:00:00",
             "--end", "2026-08-01T11:00:00", "--json"],
        )

        assert client.create.call_args.kwargs["send_updates"] == "all"

    def test_send_updates_none(
        self, runner, mock_get_credentials, mock_calendar_client_class
    ):
        from desk.commands.cal import cal

        client = self._client(mock_calendar_client_class)
        runner.invoke(
            cal,
            ["create", "Training", "--start", "2026-08-01T10:00:00",
             "--end", "2026-08-01T11:00:00", "--send-updates", "none", "--json"],
        )

        assert client.create.call_args.kwargs["send_updates"] == "none"

    def test_rejects_unknown_send_updates_value(
        self, runner, mock_get_credentials, mock_calendar_client_class
    ):
        from desk.commands.cal import cal

        self._client(mock_calendar_client_class)
        result = runner.invoke(
            cal,
            ["create", "Training", "--start", "2026-08-01T10:00:00",
             "--end", "2026-08-01T11:00:00", "--send-updates", "externalOnly"],
        )

        assert result.exit_code != 0

    def test_receipt_reports_meet_link(
        self, runner, mock_get_credentials, mock_calendar_client_class
    ):
        from desk.commands.cal import cal

        self._client(
            mock_calendar_client_class,
            event={
                "id": "e1",
                "summary": "Training",
                "htmlLink": "https://cal/e1",
                "meetLink": "https://meet.google.com/abc-defg-hij",
                "conferenceId": "abc-defg-hij",
            },
        )
        result = runner.invoke(
            cal,
            ["create", "Training", "--start", "2026-08-01T10:00:00",
             "--end", "2026-08-01T11:00:00", "--meet", "--json"],
        )

        payload = json.loads(result.output)
        assert payload["targets"][0]["meetLink"] == "https://meet.google.com/abc-defg-hij"
        assert payload["targets"][0]["conferenceId"] == "abc-defg-hij"

    def test_receipt_reports_pending_conference(
        self, runner, mock_get_credentials, mock_calendar_client_class
    ):
        """Async conference creation must not be reported as a link that exists."""
        from desk.commands.cal import cal

        self._client(
            mock_calendar_client_class,
            event={
                "id": "e1",
                "summary": "Training",
                "htmlLink": "https://cal/e1",
                "meetLink": "",
                "conferenceStatus": "pending",
            },
        )
        result = runner.invoke(
            cal,
            ["create", "Training", "--start", "2026-08-01T10:00:00",
             "--end", "2026-08-01T11:00:00", "--meet", "--json"],
        )

        payload = json.loads(result.output)
        assert payload["targets"][0]["meetLink"] is None
        assert payload["targets"][0]["conferenceStatus"] == "pending"

    def test_dry_run_omits_email_warning_when_quiet(
        self, runner, mock_get_credentials, mock_calendar_client_class
    ):
        from desk.commands.cal import cal

        self._client(mock_calendar_client_class)
        result = runner.invoke(
            cal,
            ["create", "Training", "--start", "2026-08-01T10:00:00",
             "--end", "2026-08-01T11:00:00", "-a", "bob@co.com",
             "--send-updates", "none", "--dry-run", "--json"],
        )

        payload = json.loads(result.output)
        assert not payload.get("warnings")

    def test_dry_run_warns_about_emails_by_default(
        self, runner, mock_get_credentials, mock_calendar_client_class
    ):
        from desk.commands.cal import cal

        self._client(mock_calendar_client_class)
        result = runner.invoke(
            cal,
            ["create", "Training", "--start", "2026-08-01T10:00:00",
             "--end", "2026-08-01T11:00:00", "-a", "bob@co.com",
             "--dry-run", "--json"],
        )

        payload = json.loads(result.output)
        assert any("invitation emails" in w for w in payload["warnings"])


class TestCalUpdateEventFields:
    def test_meet_added_reported_in_changes(
        self, runner, mock_get_credentials, mock_calendar_client_class
    ):
        from desk.commands.cal import cal

        client = MagicMock()
        client.update.return_value = {
            "id": "e1",
            "summary": "Training",
            "conferenceAdded": True,
            "meetLink": "https://meet.google.com/abc-defg-hij",
        }
        mock_calendar_client_class.return_value = client
        result = runner.invoke(cal, ["update", "e1", "--meet", "--json"])

        payload = json.loads(result.output)
        assert payload["changes"]["meet"] == "added"

    def test_existing_conference_reported_as_already_present(
        self, runner, mock_get_credentials, mock_calendar_client_class
    ):
        from desk.commands.cal import cal

        client = MagicMock()
        client.update.return_value = {
            "id": "e1",
            "summary": "Training",
            "conferenceAdded": False,
        }
        mock_calendar_client_class.return_value = client
        result = runner.invoke(cal, ["update", "e1", "--meet", "--json"])

        payload = json.loads(result.output)
        assert payload["changes"]["meet"] == "already present"


class TestCalDeleteSendUpdates:
    def test_quiet_delete_passes_through(
        self, runner, mock_get_credentials, mock_calendar_client_class
    ):
        from desk.commands.cal import cal

        client = MagicMock()
        client.get_event.return_value = {"id": "e1", "summary": "T", "attendeeCount": 3}
        mock_calendar_client_class.return_value = client
        result = runner.invoke(
            cal, ["delete", "e1", "--send-updates", "none", "--yes", "--json"]
        )

        assert result.exit_code == 0
        assert client.delete.call_args.kwargs["send_updates"] == "none"

    def test_dry_run_drops_cancellation_warning_when_quiet(
        self, runner, mock_get_credentials, mock_calendar_client_class
    ):
        from desk.commands.cal import cal

        client = MagicMock()
        client.get_event.return_value = {"id": "e1", "summary": "T", "attendeeCount": 3}
        mock_calendar_client_class.return_value = client
        result = runner.invoke(
            cal, ["delete", "e1", "--send-updates", "none", "--dry-run", "--json"]
        )

        payload = json.loads(result.output)
        assert not payload.get("warnings")
