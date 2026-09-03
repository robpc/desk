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


class TestWriteCalendarFlag:
    """Tests for --calendar on create/update/delete (ADR-034, issue #88)."""

    @staticmethod
    def _catalog():
        return [
            {"id": "primary", "summary": "Home", "primary": True},
            {"id": "family@group.calendar.google.com", "summary": "Family"},
            {"id": "kids@group.calendar.google.com", "summary": "Kids School"},
        ]

    # --- create ---

    def test_create_defaults_to_primary(
        self, runner, mock_get_credentials, mock_calendar_client_class
    ):
        from desk.commands.cal import cal

        mock_client = MagicMock()
        mock_client.create.return_value = {"id": "e1", "summary": "Standup"}
        mock_calendar_client_class.return_value = mock_client

        result = runner.invoke(
            cal,
            ["create", "Standup", "--start", "2026-11-11T10:00:00",
             "--end", "2026-11-11T10:30:00", "--json"],
        )

        assert result.exit_code == 0
        assert mock_client.create.call_args.kwargs["calendar_id"] == "primary"
        # No catalog fetch when the flag is omitted.
        mock_client.list_calendars.assert_not_called()

    def test_create_resolves_friendly_name(
        self, runner, mock_get_credentials, mock_calendar_client_class
    ):
        from desk.commands.cal import cal

        mock_client = MagicMock()
        mock_client.list_calendars.return_value = self._catalog()
        mock_client.create.return_value = {"id": "e1", "summary": "Dinner"}
        mock_calendar_client_class.return_value = mock_client

        result = runner.invoke(
            cal,
            ["create", "Dinner", "--start", "2026-11-11T18:00:00",
             "--end", "2026-11-11T20:00:00", "-c", "family", "--json"],
        )

        assert result.exit_code == 0
        assert (
            mock_client.create.call_args.kwargs["calendar_id"]
            == "family@group.calendar.google.com"
        )

    def test_create_receipt_carries_calendar_and_undo(
        self, runner, mock_get_credentials, mock_calendar_client_class
    ):
        from desk.commands.cal import cal

        mock_client = MagicMock()
        mock_client.list_calendars.return_value = self._catalog()
        mock_client.create.return_value = {"id": "e1", "summary": "Dinner"}
        mock_calendar_client_class.return_value = mock_client

        result = runner.invoke(
            cal,
            ["create", "Dinner", "--start", "2026-11-11T18:00:00",
             "--end", "2026-11-11T20:00:00", "-c", "Family", "--json"],
        )

        assert result.exit_code == 0
        output = json.loads(result.output)
        cal_id = "family@group.calendar.google.com"
        assert output["targets"][0]["calendar_id"] == cal_id
        # The undo command must round-trip to the same calendar.
        assert f"-c {cal_id}" in output["undo"]["command"]

    def test_create_dry_run_shows_resolved_calendar(
        self, runner, mock_get_credentials, mock_calendar_client_class
    ):
        from desk.commands.cal import cal

        mock_client = MagicMock()
        mock_client.list_calendars.return_value = self._catalog()
        mock_calendar_client_class.return_value = mock_client

        result = runner.invoke(
            cal,
            ["create", "Dinner", "--start", "2026-11-11T18:00:00",
             "--end", "2026-11-11T20:00:00", "-c", "Family",
             "--dry-run", "--json"],
        )

        assert result.exit_code == 0
        output = json.loads(result.output)
        assert (
            output["targets"][0]["calendar_id"]
            == "family@group.calendar.google.com"
        )
        mock_client.create.assert_not_called()

    def test_create_unknown_calendar_is_invalid_input(
        self, runner, mock_get_credentials, mock_calendar_client_class
    ):
        from desk.commands.cal import cal

        mock_client = MagicMock()
        mock_client.list_calendars.return_value = self._catalog()
        mock_calendar_client_class.return_value = mock_client

        result = runner.invoke(
            cal,
            ["create", "Dinner", "--start", "2026-11-11T18:00:00",
             "--end", "2026-11-11T20:00:00", "-c", "Nope", "--json"],
        )

        assert result.exit_code == 1
        assert json.loads(result.stderr)["error"]["code"] == "INVALID_INPUT"
        # Resolution fails before anything is written.
        mock_client.create.assert_not_called()

    def test_create_rejects_repeated_calendar(
        self, runner, mock_get_credentials, mock_calendar_client_class
    ):
        from desk.commands.cal import cal

        mock_client = MagicMock()
        # Both names are resolvable, so a pass here would mean the second -c
        # silently won rather than the pair being rejected.
        mock_client.list_calendars.return_value = self._catalog()
        mock_calendar_client_class.return_value = mock_client

        result = runner.invoke(
            cal,
            ["create", "Dinner", "--start", "2026-11-11T18:00:00",
             "--end", "2026-11-11T20:00:00",
             "-c", "Family", "-c", "Kids School", "--json"],
        )

        # A write targets one calendar. Click's scalar-option default would
        # keep "Kids School" without a word; ADR-034 rejects instead.
        assert result.exit_code == 1
        assert json.loads(result.stderr)["error"]["code"] == "INVALID_INPUT"
        mock_client.create.assert_not_called()

    def test_delete_rejects_repeated_calendar(
        self, runner, mock_get_credentials, mock_calendar_client_class
    ):
        from desk.commands.cal import cal

        mock_client = MagicMock()
        mock_client.list_calendars.return_value = self._catalog()
        mock_calendar_client_class.return_value = mock_client

        result = runner.invoke(
            cal,
            ["delete", "e1", "-c", "Family", "-c", "Kids School", "--yes", "--json"],
        )

        assert result.exit_code == 1
        assert json.loads(result.stderr)["error"]["code"] == "INVALID_INPUT"
        # Rejected before the event is even looked up.
        mock_client.get_event.assert_not_called()
        mock_client.delete.assert_not_called()

    def test_create_dry_run_undo_carries_calendar(
        self, runner, mock_get_credentials, mock_calendar_client_class
    ):
        from desk.commands.cal import cal

        mock_client = MagicMock()
        mock_client.list_calendars.return_value = self._catalog()
        mock_calendar_client_class.return_value = mock_client

        result = runner.invoke(
            cal,
            ["create", "Dinner", "--start", "2026-11-11T18:00:00",
             "--end", "2026-11-11T20:00:00", "-c", "Family",
             "--dry-run", "--json"],
        )

        assert result.exit_code == 0
        output = json.loads(result.output)
        # A bare "desk cal delete <event-id>" would undo against primary.
        assert "-c family@group.calendar.google.com" in output["undo_would_be"]

    # --- update ---

    def test_update_defaults_to_primary(
        self, runner, mock_get_credentials, mock_calendar_client_class
    ):
        from desk.commands.cal import cal

        mock_client = MagicMock()
        mock_client.update.return_value = {"id": "e1", "summary": "New"}
        mock_calendar_client_class.return_value = mock_client

        result = runner.invoke(cal, ["update", "e1", "-s", "New", "--json"])

        assert result.exit_code == 0
        assert mock_client.update.call_args.kwargs["calendar_id"] == "primary"

    def test_update_targets_named_calendar(
        self, runner, mock_get_credentials, mock_calendar_client_class
    ):
        from desk.commands.cal import cal

        mock_client = MagicMock()
        mock_client.list_calendars.return_value = self._catalog()
        mock_client.update.return_value = {"id": "e1", "summary": "New"}
        mock_calendar_client_class.return_value = mock_client

        result = runner.invoke(
            cal, ["update", "e1", "-s", "New", "-c", "Family", "--json"]
        )

        assert result.exit_code == 0
        cal_id = "family@group.calendar.google.com"
        assert mock_client.update.call_args.kwargs["calendar_id"] == cal_id
        assert json.loads(result.output)["targets"][0]["calendar_id"] == cal_id

    # --- delete ---

    def test_delete_defaults_to_primary(
        self, runner, mock_get_credentials, mock_calendar_client_class
    ):
        from desk.commands.cal import cal

        mock_client = MagicMock()
        mock_client.get_event.return_value = {"summary": "Dinner", "attendeeCount": 0}
        mock_calendar_client_class.return_value = mock_client

        result = runner.invoke(cal, ["delete", "e1", "--yes", "--json"])

        assert result.exit_code == 0
        assert mock_client.get_event.call_args.kwargs["calendar_id"] == "primary"
        assert mock_client.delete.call_args.kwargs["calendar_id"] == "primary"

    def test_delete_resolves_once_for_lookup_and_delete(
        self, runner, mock_get_credentials, mock_calendar_client_class
    ):
        from desk.commands.cal import cal

        mock_client = MagicMock()
        mock_client.list_calendars.return_value = self._catalog()
        mock_client.get_event.return_value = {"summary": "Dinner", "attendeeCount": 0}
        mock_calendar_client_class.return_value = mock_client

        result = runner.invoke(
            cal, ["delete", "e1", "-c", "Family", "--yes", "--json"]
        )

        assert result.exit_code == 0
        cal_id = "family@group.calendar.google.com"
        # The event previewed must be the event deleted.
        assert mock_client.get_event.call_args.kwargs["calendar_id"] == cal_id
        assert mock_client.delete.call_args.kwargs["calendar_id"] == cal_id
        assert json.loads(result.output)["targets"][0]["calendar_id"] == cal_id
        # Catalog resolved once, not once per API call.
        assert mock_client.list_calendars.call_count == 1

    def test_delete_dry_run_shows_resolved_calendar(
        self, runner, mock_get_credentials, mock_calendar_client_class
    ):
        from desk.commands.cal import cal

        mock_client = MagicMock()
        mock_client.list_calendars.return_value = self._catalog()
        mock_client.get_event.return_value = {"summary": "Dinner", "attendeeCount": 0}
        mock_calendar_client_class.return_value = mock_client

        result = runner.invoke(
            cal, ["delete", "e1", "-c", "Family", "--dry-run", "--json"]
        )

        assert result.exit_code == 0
        output = json.loads(result.output)
        assert (
            output["targets"][0]["calendar_id"]
            == "family@group.calendar.google.com"
        )
        mock_client.delete.assert_not_called()


class TestCreateDryRunResolvesTimes:
    """`cal create --dry-run` previews resolved times, not raw input.

    Echoing back the string the caller typed tells them nothing they did
    not already know. It also hides the issue #89 class of bug: a naive
    datetime silently landing on a different offset was only observable
    by creating a real event. See idea 031 / ADR-004 — a dry-run exists so
    the caller can verify what *would happen*.
    """

    @pytest.fixture
    def ny_timezone(self):
        import os
        import time

        original = os.environ.get("TZ")
        os.environ["TZ"] = "America/New_York"
        time.tzset()
        yield
        if original is None:
            del os.environ["TZ"]
        else:
            os.environ["TZ"] = original
        time.tzset()

    def test_naive_datetime_shows_resolved_offset(
        self, runner, mock_get_credentials, mock_calendar_client_class, ny_timezone
    ):
        from desk.commands.cal import cal

        mock_client = MagicMock()
        mock_calendar_client_class.return_value = mock_client

        result = runner.invoke(
            cal,
            ["create", "Reading", "--start", "2026-11-11T17:30:00",
             "--end", "2026-11-11T18:30:00", "--dry-run", "--json"],
        )

        assert result.exit_code == 0
        target = json.loads(result.output)["targets"][0]
        # EST, because November is EST — the whole point of issue #89.
        assert target["start"] == "2026-11-11T17:30:00-05:00"
        assert target["end"] == "2026-11-11T18:30:00-05:00"
        mock_client.create.assert_not_called()

    def test_summer_date_shows_summer_offset(
        self, runner, mock_get_credentials, mock_calendar_client_class, ny_timezone
    ):
        from desk.commands.cal import cal

        mock_client = MagicMock()
        mock_calendar_client_class.return_value = mock_client

        result = runner.invoke(
            cal,
            ["create", "Picnic", "--start", "2026-07-04T17:30:00",
             "--end", "2026-07-04T18:30:00", "--dry-run", "--json"],
        )

        assert result.exit_code == 0
        assert json.loads(result.output)["targets"][0]["start"] == (
            "2026-07-04T17:30:00-04:00"
        )

    def test_explicit_offset_passes_through(
        self, runner, mock_get_credentials, mock_calendar_client_class, ny_timezone
    ):
        from desk.commands.cal import cal

        mock_client = MagicMock()
        mock_calendar_client_class.return_value = mock_client

        result = runner.invoke(
            cal,
            ["create", "Call", "--start", "2026-11-11T17:30:00-08:00",
             "--end", "2026-11-11T18:30:00-08:00", "--dry-run", "--json"],
        )

        assert result.exit_code == 0
        assert json.loads(result.output)["targets"][0]["start"] == (
            "2026-11-11T17:30:00-08:00"
        )

    def test_all_day_stays_a_bare_date(
        self, runner, mock_get_credentials, mock_calendar_client_class, ny_timezone
    ):
        from desk.commands.cal import cal

        mock_client = MagicMock()
        mock_calendar_client_class.return_value = mock_client

        result = runner.invoke(
            cal,
            ["create", "Holiday", "--start", "2026-11-11",
             "--end", "2026-11-12", "--dry-run", "--json"],
        )

        assert result.exit_code == 0
        target = json.loads(result.output)["targets"][0]
        # All-day events have no offset to resolve; don't invent one.
        assert target["start"] == "2026-11-11"
        assert target["end"] == "2026-11-12"

    def test_unparseable_time_is_invalid_input(
        self, runner, mock_get_credentials, mock_calendar_client_class
    ):
        from desk.commands.cal import cal

        mock_client = MagicMock()
        mock_calendar_client_class.return_value = mock_client

        result = runner.invoke(
            cal,
            ["create", "Nope", "--start", "next tuesday",
             "--end", "2026-11-11T18:30:00", "--dry-run", "--json"],
        )

        # Previously a dry-run never parsed, so bad input surfaced only on
        # the real call. Now it fails here, which is the point of a preview.
        assert result.exit_code == 1
        assert json.loads(result.stderr)["error"]["code"] == "INVALID_INPUT"
        mock_client.create.assert_not_called()
