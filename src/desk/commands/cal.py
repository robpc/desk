"""Calendar commands — view and create events."""

import json
import sys

import click
from rich.console import Console
from rich.markup import escape
from rich.table import Table

from desk.agent import (
    ERROR_SUGGESTIONS,
    ErrorCode,
    dry_run_preview,
    is_scope_error,
    operation_receipt,
    output_result,
    parse_api_error,
    structured_error,
)
from desk.auth import get_credentials, get_last_auth_failure
from desk.console import error_console
from desk.services.calendar import CalendarClient, parse_time_input

console = Console()


def _get_client(as_json: bool = False) -> CalendarClient:
    """Get authenticated Calendar client or exit."""
    creds = get_credentials()
    if not creds:
        reason, error_code = get_last_auth_failure()
        if as_json:
            code = ErrorCode(error_code) if error_code else ErrorCode.AUTH_REQUIRED
            error = structured_error(
                code,
                reason or "Not authenticated",
            )
            print(json.dumps(error, indent=2), file=sys.stderr)
        else:
            error_console.print("[red]Not authenticated.[/red]")
            if reason:
                error_console.print(f"[yellow]{escape(reason)}[/yellow]")
            else:
                error_console.print("Run: [cyan]desk setup[/cyan]")
        sys.exit(1)
    return CalendarClient(creds)


def _resolve_calendars(
    client: CalendarClient, raw: tuple[str, ...], as_json: bool
) -> list[str]:
    """Resolve --calendar values to canonical Calendar IDs.

    Accepts calendar IDs, friendly names (case-insensitive against
    ``summary`` from ``cal list``), or the literal ``primary``. See
    ADR-023.

    Empty tuple → ``["primary"]``.

    On ambiguous or unknown names, emits a structured INVALID_INPUT error
    and exits 1, matching the rest of the module's error contract.
    """
    if not raw:
        return ["primary"]

    catalog: list[dict] | None = None
    resolved: list[str] = []

    for value in raw:
        if value == "primary" or "@" in value:
            resolved.append(value)
            continue
        if catalog is None:
            try:
                catalog = client.list_calendars()
            except Exception as e:
                _handle_api_error(e, as_json, {"step": "resolve_calendar"})
        # Match the display name or the owner's title, so a user can type
        # the name they see and older scripts keep working (ADR-035).
        wanted = value.casefold()
        matches = [
            c
            for c in (catalog or [])
            if wanted in {
                c.get("summary", "").casefold(),
                c.get("summary_original", "").casefold(),
            }
        ]
        if len(matches) == 1:
            resolved.append(matches[0]["id"])
        elif not matches:
            _emit_resolution_error(
                as_json,
                value,
                f"No calendar matches '{value}'.",
                ["Run `desk cal list` to see available calendars."],
            )
        else:
            ids = ", ".join(m["id"] for m in matches)
            _emit_resolution_error(
                as_json,
                value,
                f"Multiple calendars match '{value}': {ids}",
                [
                    "Disambiguate by using the calendar ID directly.",
                    "Run `desk cal list` to see the full mapping.",
                ],
            )

    return resolved


def _emit_resolution_error(
    as_json: bool, value: str, message: str, suggestions: list[str]
) -> None:
    """Emit an INVALID_INPUT error for a calendar-resolution failure and exit."""
    if as_json:
        error = structured_error(
            code=ErrorCode.INVALID_INPUT,
            message=message,
            suggestions=suggestions,
            retryable=False,
            details={"calendar": value},
        )
        print(json.dumps(error, indent=2), file=sys.stderr)
    else:
        error_console.print(f"[red]Error: {message}[/red]")
        for s in suggestions:
            error_console.print(f"  [cyan]- {s}[/cyan]")
    sys.exit(1)


def _resolve_write_calendar(
    client: CalendarClient, values: tuple[str, ...], as_json: bool
) -> str:
    """Resolve the single ``--calendar`` target for a write command.

    Wraps :func:`_resolve_calendars` for the single-target case. An empty
    tuple (flag omitted) resolves to ``"primary"``, preserving pre-ADR-034
    behavior.

    The option is declared ``multiple=True`` purely so a repeated ``-c``
    can be *rejected*. Click's default for a scalar option is to keep the
    last value silently, which for a write target means quietly writing to
    a calendar the caller did not name last on purpose. See ADR-034.
    """
    if not values:
        return "primary"
    if len(values) > 1:
        _emit_resolution_error(
            as_json,
            ", ".join(values),
            "A write targets one calendar; --calendar was given more than once.",
            [
                "Pass a single -c/--calendar value.",
                "To write to several calendars, run the command once per calendar.",
            ],
        )
    return _resolve_calendars(client, values, as_json)[0]


def _preview_time(value: str, as_json: bool) -> str:
    """Resolve a --start/--end the way a real write would, for --dry-run.

    Returns the flat string shape ``_parse_event`` produces, so a dry-run
    target reads the same as the receipt from the real call. Echoing the
    raw input back instead would hide exactly the class of bug issue #89
    was — a naive datetime silently landing on a different offset.
    """
    try:
        parsed = parse_time_input(value)
    except ValueError as e:
        _emit_resolution_error(
            as_json,
            value,
            f"Could not parse time '{value}': {e}",
            [
                "Use ISO 8601: YYYY-MM-DDTHH:MM:SS or YYYY-MM-DD for all-day.",
                "An explicit offset (2026-11-11T17:30:00-05:00) is honored as given.",
            ],
        )
    return parsed.get("dateTime") or parsed.get("date", "")


def _merge_events(per_calendar: list[dict]) -> dict:
    """Merge multiple per-calendar query results into one events dict.

    Sorts the merged event list by ``start`` (lexicographic over ISO 8601
    works for both ``date`` and ``dateTime``). See ADR-023.
    """
    events: list[dict] = []
    for r in per_calendar:
        events.extend(r.get("events", []))
    events.sort(key=lambda e: e.get("start", ""))
    return {"events": events}


def _handle_api_error(e: Exception, as_json: bool, context: dict | None = None) -> None:
    """Handle API errors with structured output when --json is used."""
    raw_error = str(e)
    error_msg = parse_api_error(raw_error)

    if is_scope_error(raw_error):
        code = ErrorCode.INSUFFICIENT_SCOPES
    elif "not found" in raw_error.lower() or "404" in raw_error:
        code = ErrorCode.EVENT_NOT_FOUND
    elif "401" in raw_error or "invalid credentials" in raw_error.lower():
        code = ErrorCode.AUTH_EXPIRED
    elif "403" in raw_error or "permission" in raw_error.lower():
        code = ErrorCode.PERMISSION_DENIED
    elif "429" in raw_error or "rate" in raw_error.lower():
        code = ErrorCode.RATE_LIMITED
    elif "400" in raw_error or "invalid" in raw_error.lower():
        code = ErrorCode.INVALID_INPUT
    else:
        code = ErrorCode.OPERATION_FAILED

    suggestions = ERROR_SUGGESTIONS.get(code, [])

    if as_json:
        error = structured_error(
            code=code,
            message=error_msg,
            suggestions=suggestions,
            retryable=code == ErrorCode.RATE_LIMITED,
            details=context,
        )
        print(json.dumps(error, indent=2), file=sys.stderr)
    else:
        error_console.print(f"[red]Error: {error_msg}[/red]")
        if suggestions:
            error_console.print("[dim]Suggestions:[/dim]")
            for s in suggestions:
                error_console.print(f"  [cyan]- {s}[/cyan]")

    sys.exit(1)


@click.group()
def cal() -> None:
    """Google Calendar — view and create events."""
    pass


_CALENDAR_OPTION_HELP = (
    "Calendar ID, friendly name from `desk cal list` (case-insensitive), or "
    "'primary'. Repeatable to merge across calendars (sorted by start time)."
)


_WRITE_CALENDAR_OPTION_HELP = (
    "Calendar to write to: calendar ID, friendly name from `desk cal list` "
    "(case-insensitive), or 'primary'. Defaults to 'primary'. Not repeatable "
    "— a write targets one calendar."
)


def _reject_page_token_with_multi_calendar(
    calendar_ids: list[str], page_token: str | None, as_json: bool
) -> None:
    """Multi-calendar mode + --page-token combo is unsupported. See ADR-023."""
    if page_token and len(calendar_ids) > 1:
        _emit_resolution_error(
            as_json,
            "--page-token",
            "--page-token is not supported when multiple --calendar are given.",
            [
                "Paginate per-calendar by issuing separate calls with one "
                "--calendar each.",
                "Future: structured per-calendar page tokens may be added.",
            ],
        )


@cal.command()
@click.option("--date", "-d", default=None, help="Date to show (YYYY-MM-DD). Defaults to today.")
@click.option(
    "-c",
    "--calendar",
    "calendars",
    multiple=True,
    help=_CALENDAR_OPTION_HELP,
)
@click.option("--page-token", "page_token", default=None, help="Continue from previous page")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def today(
    date: str | None,
    calendars: tuple[str, ...],
    page_token: str | None,
    as_json: bool,
) -> None:
    """Show events for a day.

    Examples:

        desk cal today

        desk cal today --date 2026-02-09

        desk cal today -c primary -c "Family" --json
    """
    client = _get_client(as_json)
    calendar_ids = _resolve_calendars(client, calendars, as_json)
    _reject_page_token_with_multi_calendar(calendar_ids, page_token, as_json)

    try:
        per_cal = [
            client.today(calendar_id=cid, page_token=page_token, date=date)
            for cid in calendar_ids
        ]
    except Exception as e:
        _handle_api_error(e, as_json)

    if len(calendar_ids) == 1:
        result = per_cal[0]
    else:
        result = _merge_events(per_cal)

    if as_json:
        print(json.dumps(result, indent=2))
        return

    events = result.get("events", [])
    title = f"Events for {date}" if date else "Today"
    _print_events(events, title)

    if result.get("nextPageToken"):
        console.print(f"\n[dim]More results available. Use --page-token {result['nextPageToken']}[/dim]")


@cal.command()
@click.option("--date", "-d", default=None, help="Date in target week (YYYY-MM-DD)")
@click.option(
    "-c",
    "--calendar",
    "calendars",
    multiple=True,
    help=_CALENDAR_OPTION_HELP,
)
@click.option("--page-token", "page_token", default=None, help="Continue from previous page")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def week(
    date: str | None,
    calendars: tuple[str, ...],
    page_token: str | None,
    as_json: bool,
) -> None:
    """Show events for a week.

    Examples:

        desk cal week

        desk cal week --date 2026-02-12

        desk cal week -c primary -c "Family"
    """
    client = _get_client(as_json)
    calendar_ids = _resolve_calendars(client, calendars, as_json)
    _reject_page_token_with_multi_calendar(calendar_ids, page_token, as_json)

    try:
        per_cal = [
            client.week(calendar_id=cid, page_token=page_token, date=date)
            for cid in calendar_ids
        ]
    except Exception as e:
        _handle_api_error(e, as_json)

    if len(calendar_ids) == 1:
        result = per_cal[0]
    else:
        result = _merge_events(per_cal)

    if as_json:
        print(json.dumps(result, indent=2))
        return

    events = result.get("events", [])
    title = f"Week of {date}" if date else "This week"
    _print_events(events, title)

    if result.get("nextPageToken"):
        console.print(f"\n[dim]More results available. Use --page-token {result['nextPageToken']}[/dim]")


@cal.command("next")
@click.option("--max", "-n", "max_results", default=10, help="Max results (per calendar)")
@click.option("--limit", "limit", default=None, type=int, help="Max results (alias for --max)")
@click.option(
    "-c",
    "--calendar",
    "calendars",
    multiple=True,
    help=_CALENDAR_OPTION_HELP,
)
@click.option("--page-token", "page_token", default=None, help="Continue from previous page")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def next_events(
    max_results: int,
    limit: int | None,
    calendars: tuple[str, ...],
    page_token: str | None,
    as_json: bool,
) -> None:
    """Show upcoming events.

    With multiple --calendar, --max applies per calendar (e.g. -c A -c B --max 10
    returns up to 20 events, sorted by start time).

    Examples:

        desk cal next --max 5

        desk cal next -c primary -c "Family" --max 10
    """
    # --limit takes precedence if provided
    if limit is not None:
        max_results = limit

    client = _get_client(as_json)
    calendar_ids = _resolve_calendars(client, calendars, as_json)
    _reject_page_token_with_multi_calendar(calendar_ids, page_token, as_json)

    try:
        per_cal = [
            client.next(
                max_results=max_results, calendar_id=cid, page_token=page_token
            )
            for cid in calendar_ids
        ]
    except Exception as e:
        _handle_api_error(e, as_json)

    if len(calendar_ids) == 1:
        result = per_cal[0]
    else:
        result = _merge_events(per_cal)

    if as_json:
        print(json.dumps(result, indent=2))
        return

    events = result.get("events", [])
    _print_events(events, "Upcoming")

    if result.get("nextPageToken"):
        console.print(f"\n[dim]More results available. Use --page-token {result['nextPageToken']}[/dim]")


@cal.command("list")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def list_calendars(as_json: bool) -> None:
    """List all calendars.

    Examples:

        desk cal list
    """
    client = _get_client(as_json)
    try:
        calendars = client.list_calendars()
    except Exception as e:
        _handle_api_error(e, as_json)

    if as_json:
        print(json.dumps(calendars, indent=2))
        return

    if not calendars:
        console.print("No calendars found.")
        return

    for cal_item in calendars:
        primary = " [green](primary)[/green]" if cal_item.get("primary") else ""
        console.print(f"{cal_item['summary']}{primary}")
        original = cal_item.get("summary_original", "")
        # Only worth showing when the user renamed the calendar, otherwise
        # it just repeats the line above (ADR-035).
        if original and original != cal_item["summary"]:
            console.print(
                f"  [dim]{cal_item['id']} — owner's title: {escape(original)}[/dim]"
            )
        else:
            console.print(f"  [dim]{cal_item['id']}[/dim]")


@cal.command()
@click.argument("summary")
@click.option("--start", required=True, help="Start time (ISO 8601 or YYYY-MM-DD)")
@click.option("--end", required=True, help="End time (ISO 8601 or YYYY-MM-DD)")
@click.option("--description", "-d", default="", help="Event description")
@click.option("--attendee", "-a", "attendees", multiple=True, help="Attendee email (repeatable)")
@click.option("-c", "--calendar", "calendar", multiple=True, help=_WRITE_CALENDAR_OPTION_HELP)
@click.option("--dry-run", is_flag=True, help="Preview without executing")
@click.option("--quiet", "-q", is_flag=True, help="Suppress success messages")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def create(
    summary: str,
    start: str,
    end: str,
    description: str,
    attendees: tuple[str, ...],
    calendar: tuple[str, ...],
    dry_run: bool,
    quiet: bool,
    as_json: bool,
) -> None:
    """Create a new event.

    Examples:

        desk cal create "Standup" --start 2024-01-15T10:00:00 --end 2024-01-15T10:30:00

        desk cal create "Sync" --start 2024-01-15T10:00:00 --end 2024-01-15T11:00:00 -a bob@co.com

        desk cal create "Dinner" --start 2024-01-15T18:00:00 --end 2024-01-15T20:00:00 -c Family
    """
    client = _get_client(as_json)
    calendar_id = _resolve_write_calendar(client, calendar, as_json)

    if dry_run:
        target = {
            "summary": summary,
            "start": _preview_time(start, as_json),
            "end": _preview_time(end, as_json),
            "calendar_id": calendar_id,
        }
        if attendees:
            target["attendees"] = list(attendees)
        preview = dry_run_preview(
            operation="create event",
            targets=[target],
            reversible=True,
            undo_command=f"desk cal delete <event-id> -c {calendar_id}",
            warnings=["Attendees will receive invitation emails"] if attendees else None,
        )
        output_result(preview, as_json, quiet)
        return

    try:
        event = client.create(
            summary,
            start,
            end,
            description=description,
            attendees=list(attendees) if attendees else None,
            calendar_id=calendar_id,
        )
    except Exception as e:
        _handle_api_error(
            e,
            as_json,
            {"summary": summary, "start": start, "end": end, "calendar_id": calendar_id},
        )

    receipt = operation_receipt(
        operation="create",
        target={
            "id": event.get("id"),
            "summary": event.get("summary"),
            "start": event.get("start"),
            "end": event.get("end"),
            "calendar_id": calendar_id,
            "link": event.get("htmlLink"),
        },
        undo_command=f"desk cal delete {event.get('id')} -c {calendar_id} --yes",
    )
    output_result(receipt, as_json, quiet)


@cal.command()
@click.argument("event_id")
@click.option("-c", "--calendar", "calendar", multiple=True, help=_WRITE_CALENDAR_OPTION_HELP)
@click.option("--yes", "-y", is_flag=True, help="Skip confirmation prompt")
@click.option("--dry-run", is_flag=True, help="Preview without executing")
@click.option("--quiet", "-q", is_flag=True, help="Suppress success messages")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def delete(
    event_id: str,
    calendar: tuple[str, ...],
    yes: bool,
    dry_run: bool,
    quiet: bool,
    as_json: bool,
) -> None:
    """Delete an event.

    Deleting an event with attendees sends cancellation emails to all attendees.
    Use --yes to skip confirmation (for scripting).

    Examples:

        desk cal delete <event-id>

        desk cal delete <event-id> --yes

        desk cal delete <event-id> --dry-run

        desk cal delete <event-id> -c Family
    """
    client = _get_client(as_json)
    # Resolve once and reuse: the event shown in the confirmation prompt must
    # be the event that gets deleted (ADR-034).
    calendar_id = _resolve_write_calendar(client, calendar, as_json)

    # Fetch event details for confirmation/preview
    try:
        event = client.get_event(event_id, calendar_id=calendar_id)
    except RuntimeError as e:
        _handle_api_error(e, as_json, {"event_id": event_id, "calendar_id": calendar_id})

    attendee_count = event.get("attendeeCount", 0)

    if dry_run:
        warnings = []
        if attendee_count > 0:
            warnings.append(f"Cancellation emails will be sent to {attendee_count} attendee(s)")
        preview = dry_run_preview(
            operation="delete event",
            targets=[{
                "id": event_id,
                "summary": event.get("summary"),
                "start": event.get("start"),
                "calendar_id": calendar_id,
                "attendees": attendee_count,
            }],
            reversible=False,
            warnings=warnings if warnings else None,
        )
        output_result(preview, as_json, quiet)
        return

    # Require confirmation if there are attendees
    if attendee_count > 0 and not yes:
        # Check if we're in an interactive terminal
        if not sys.stdin.isatty():
            if as_json:
                error = structured_error(
                    ErrorCode.INVALID_INPUT,
                    "Event has attendees. Use --yes to confirm deletion in non-interactive mode.",
                    suggestions=["Use --dry-run to preview the operation", "Use --yes to skip confirmation"],
                    details={"event_id": event_id, "calendar_id": calendar_id, "attendees": attendee_count},
                )
                print(json.dumps(error, indent=2), file=sys.stderr)
            else:
                error_console.print("[red]Error: This event has attendees. Use --yes to confirm deletion in non-interactive mode.[/red]")
                console.print(f"[yellow]Event: {event.get('summary', '(no title)')}[/yellow]")
                console.print(f"[yellow]Attendees: {attendee_count}[/yellow]")
            sys.exit(1)

        console.print(f"[yellow]Event: {event.get('summary', '(no title)')}[/yellow]")
        console.print(f"[yellow]Start: {event.get('start', '')}[/yellow]")
        console.print(f"[yellow]Attendees: {attendee_count}[/yellow]")
        console.print()
        console.print("[bold red]Deleting this event will send cancellation emails to all attendees.[/bold red]")

        if not click.confirm("Are you sure you want to delete this event?"):
            console.print("Cancelled.")
            return

    try:
        client.delete(event_id, calendar_id=calendar_id)
    except Exception as e:
        _handle_api_error(e, as_json, {"event_id": event_id, "calendar_id": calendar_id})

    receipt = operation_receipt(
        operation="delete",
        target={
            "id": event_id,
            "summary": event.get("summary"),
            "calendar_id": calendar_id,
        },
    )
    output_result(receipt, as_json, quiet)


@cal.command()
@click.argument("event_id")
@click.option("--summary", "-s", help="New title")
@click.option("--start", help="New start time (ISO 8601)")
@click.option("--end", help="New end time (ISO 8601)")
@click.option("--description", "-d", help="New description")
@click.option(
    "--add-attendee", "-a", "add_attendees", multiple=True, help="Email to add (repeatable)"
)
@click.option(
    "--remove-attendee", "-r", "remove_attendees", multiple=True, help="Email to remove (sends cancellation notification)"
)
@click.option("-c", "--calendar", "calendar", multiple=True, help=_WRITE_CALENDAR_OPTION_HELP)
@click.option("--quiet", "-q", is_flag=True, help="Suppress success messages")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def update(
    event_id: str,
    summary: str | None,
    start: str | None,
    end: str | None,
    description: str | None,
    add_attendees: tuple[str, ...],
    remove_attendees: tuple[str, ...],
    calendar: tuple[str, ...],
    quiet: bool,
    as_json: bool,
) -> None:
    """Update an existing event.

    Only provided fields are changed.

    Examples:

        desk cal update <id> --summary "New Title"

        desk cal update <id> --start 2024-01-15T14:00:00 --end 2024-01-15T15:00:00

        desk cal update <id> -a newperson@example.com

        desk cal update <id> -r former.employee@example.com

        desk cal update <id> -c Family --summary "New Title"
    """
    client = _get_client(as_json)
    calendar_id = _resolve_write_calendar(client, calendar, as_json)
    try:
        event = client.update(
            event_id,
            summary=summary,
            start=start,
            end=end,
            description=description,
            add_attendees=list(add_attendees) if add_attendees else None,
            remove_attendees=list(remove_attendees) if remove_attendees else None,
            calendar_id=calendar_id,
        )
    except Exception as e:
        _handle_api_error(e, as_json, {"event_id": event_id, "calendar_id": calendar_id})

    changes = {}
    if summary:
        changes["summary"] = summary
    if start:
        changes["start"] = start
    if end:
        changes["end"] = end
    if description:
        changes["description"] = description
    if add_attendees:
        changes["added_attendees"] = list(add_attendees)
    if remove_attendees:
        actually_removed = event.get("removedAttendees", [])
        changes["removed_attendees"] = actually_removed
        not_found = [e for e in remove_attendees if e.lower() not in {r.lower() for r in actually_removed}]
        if not_found:
            changes["not_found_attendees"] = list(not_found)

    receipt = operation_receipt(
        operation="update",
        target={
            "id": event.get("id"),
            "summary": event.get("summary"),
            "calendar_id": calendar_id,
            "link": event.get("htmlLink"),
        },
        changes=changes,
    )
    output_result(receipt, as_json, quiet)


@cal.command()
@click.argument("query")
@click.option("--max", "-n", "max_results", default=10, help="Max results (per calendar)")
@click.option("--limit", "limit", default=None, type=int, help="Max results (alias for --max)")
@click.option(
    "-c",
    "--calendar",
    "calendars",
    multiple=True,
    help=_CALENDAR_OPTION_HELP,
)
@click.option("--page-token", "page_token", default=None, help="Continue from previous page")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def find(
    query: str,
    max_results: int,
    limit: int | None,
    calendars: tuple[str, ...],
    page_token: str | None,
    as_json: bool,
) -> None:
    """Search for events by text.

    Examples:

        desk cal find "standup"

        desk cal find "review" --max 5

        desk cal find "school" -c primary -c "Family"
    """
    # --limit takes precedence if provided
    if limit is not None:
        max_results = limit

    client = _get_client(as_json)
    calendar_ids = _resolve_calendars(client, calendars, as_json)
    _reject_page_token_with_multi_calendar(calendar_ids, page_token, as_json)

    try:
        per_cal = [
            client.find(
                query,
                max_results=max_results,
                calendar_id=cid,
                page_token=page_token,
            )
            for cid in calendar_ids
        ]
    except Exception as e:
        _handle_api_error(e, as_json, {"query": query})

    if len(calendar_ids) == 1:
        result = per_cal[0]
    else:
        result = _merge_events(per_cal)

    if as_json:
        print(json.dumps(result, indent=2))
        return

    events = result.get("events", [])
    _print_events(events, f"Results for '{query}'")

    if result.get("nextPageToken"):
        console.print(f"\n[dim]More results available. Use --page-token {result['nextPageToken']}[/dim]")


@cal.command()
@click.option("--max", "-n", "max_results", default=20, help="Max results")
@click.option("--limit", "limit", default=None, type=int, help="Max results (alias for --max)")
@click.option("--page-token", "page_token", default=None, help="Continue from previous page")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def invitations(max_results: int, limit: int | None, page_token: str | None, as_json: bool) -> None:
    """List pending invitations.

    Shows events where you haven't yet responded (needsAction).

    Examples:

        desk cal invitations

        desk cal invitations --max 10
    """
    # --limit takes precedence if provided
    if limit is not None:
        max_results = limit

    client = _get_client(as_json)
    try:
        result = client.invitations(max_results=max_results, page_token=page_token)
    except Exception as e:
        _handle_api_error(e, as_json)

    if as_json:
        print(json.dumps(result, indent=2))
        return

    events = result.get("events", [])
    if not events:
        console.print("No pending invitations.")
        return

    _print_events(events, "Pending Invitations")

    if result.get("nextPageToken"):
        console.print(f"\n[dim]More results available. Use --page-token {result['nextPageToken']}[/dim]")


@cal.command()
@click.argument("event_id")
@click.option(
    "--status",
    "-s",
    required=True,
    type=click.Choice(["accepted", "declined", "tentative"]),
    help="Your response",
)
@click.option("--quiet", "-q", is_flag=True, help="Suppress success messages")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def respond(event_id: str, status: str, quiet: bool, as_json: bool) -> None:
    """Respond to an event invitation.

    Accepts, declines, or marks an event as tentative.
    Sends your response to the organizer.

    Examples:

        desk cal respond <event-id> --status accepted

        desk cal respond <event-id> --status declined

        desk cal respond <event-id> --status tentative
    """
    client = _get_client(as_json)

    try:
        event = client.respond(event_id, status)
    except ValueError as e:
        if as_json:
            error = structured_error(
                ErrorCode.INVALID_INPUT,
                str(e),
                suggestions=["Use --status accepted, declined, or tentative"],
            )
            print(json.dumps(error, indent=2), file=sys.stderr)
        else:
            error_console.print(f"[red]Error: {e}[/red]")
        sys.exit(1)
    except Exception as e:
        _handle_api_error(e, as_json, {"event_id": event_id, "status": status})

    receipt = operation_receipt(
        operation="respond",
        target={
            "id": event.get("id"),
            "summary": event.get("summary"),
            "response": status,
        },
    )
    output_result(receipt, as_json, quiet)


@cal.command()
@click.argument("emails", nargs=-1, required=True)
@click.option("--start", required=True, help="Start of time range (ISO 8601)")
@click.option("--end", required=True, help="End of time range (ISO 8601)")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def freebusy(emails: tuple[str, ...], start: str, end: str, as_json: bool) -> None:
    """Query free/busy information.

    Check availability for one or more people without seeing event details.
    Returns busy time blocks within the specified range.

    Examples:

        desk cal freebusy alice@example.com --start 2024-01-15T09:00:00 --end 2024-01-15T17:00:00

        desk cal freebusy alice@example.com bob@example.com --start 2024-01-15 --end 2024-01-16
    """
    client = _get_client(as_json)
    try:
        result = client.freebusy(list(emails), start, end)
    except Exception as e:
        _handle_api_error(e, as_json, {"emails": list(emails), "start": start, "end": end})

    if as_json:
        print(json.dumps(result, indent=2))
        return

    table = Table(show_header=True)
    table.add_column("Email", width=35)
    table.add_column("Busy Periods", width=50)

    for email in emails:
        busy = result.get(email, [])
        if not busy:
            periods_str = "(free)"
        else:
            periods = []
            for period in busy:
                start_time = period.get("start", "")[:16].replace("T", " ")
                end_time = period.get("end", "")[:16].replace("T", " ")
                periods.append(f"{start_time} - {end_time}")
            periods_str = "\n".join(periods)
        table.add_row(email, periods_str)

    console.print(table)


def _print_events(events: list[dict], title: str) -> None:
    """Print events as a table."""
    if not events:
        console.print(f"{title}: no events.")
        return

    table = Table(title=title, show_header=True)
    table.add_column("Time", width=25)
    table.add_column("Event", width=40)
    table.add_column("Location", width=25)
    table.add_column("Att", width=3)

    for event in events:
        start = event.get("start", "")
        # Strip seconds from datetime for readability
        if "T" in start:
            start = start[:16].replace("T", " ")
        attachments = event.get("attachments", [])
        att_indicator = str(len(attachments)) if attachments else ""
        table.add_row(
            start,
            event.get("summary", "(no title)"),
            event.get("location", ""),
            att_indicator,
        )

    console.print(table)
