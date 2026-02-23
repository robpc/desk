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
    operation_receipt,
    output_result,
    parse_api_error,
    structured_error,
)
from desk.auth import get_credentials, get_last_auth_failure
from desk.services.calendar import CalendarClient

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
            print(json.dumps(error, indent=2))
        else:
            console.print("[red]Not authenticated.[/red]")
            if reason:
                console.print(f"[yellow]{escape(reason)}[/yellow]")
            else:
                console.print("Run: [cyan]desk setup[/cyan]")
        sys.exit(1)
    return CalendarClient(creds)


def _handle_api_error(e: Exception, as_json: bool, context: dict | None = None) -> None:
    """Handle API errors with structured output when --json is used."""
    raw_error = str(e)
    error_msg = parse_api_error(raw_error)

    if "not found" in raw_error.lower() or "404" in raw_error:
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
        print(json.dumps(error, indent=2))
    else:
        console.print(f"[red]Error: {error_msg}[/red]")
        if suggestions:
            console.print("[dim]Suggestions:[/dim]")
            for s in suggestions:
                console.print(f"  [cyan]- {s}[/cyan]")

    sys.exit(1)


@click.group()
def cal() -> None:
    """Google Calendar — view and create events."""
    pass


@cal.command()
@click.option("--date", "-d", default=None, help="Date to show (YYYY-MM-DD). Defaults to today.")
@click.option("--page-token", "page_token", default=None, help="Continue from previous page")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def today(date: str | None, page_token: str | None, as_json: bool) -> None:
    """Show events for a day.

    Examples:

        desk cal today

        desk cal today --date 2026-02-09
    """
    client = _get_client(as_json)
    try:
        result = client.today(page_token=page_token, date=date)
    except Exception as e:
        _handle_api_error(e, as_json)

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
@click.option("--page-token", "page_token", default=None, help="Continue from previous page")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def week(date: str | None, page_token: str | None, as_json: bool) -> None:
    """Show events for a week.

    Examples:

        desk cal week

        desk cal week --date 2026-02-12
    """
    client = _get_client(as_json)
    try:
        result = client.week(page_token=page_token, date=date)
    except Exception as e:
        _handle_api_error(e, as_json)

    if as_json:
        print(json.dumps(result, indent=2))
        return

    events = result.get("events", [])
    title = f"Week of {date}" if date else "This week"
    _print_events(events, title)

    if result.get("nextPageToken"):
        console.print(f"\n[dim]More results available. Use --page-token {result['nextPageToken']}[/dim]")


@cal.command("next")
@click.option("--max", "-n", "max_results", default=10, help="Max results")
@click.option("--limit", "limit", default=None, type=int, help="Max results (alias for --max)")
@click.option("--page-token", "page_token", default=None, help="Continue from previous page")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def next_events(max_results: int, limit: int | None, page_token: str | None, as_json: bool) -> None:
    """Show upcoming events.

    Examples:

        desk cal next --max 5
    """
    # --limit takes precedence if provided
    if limit is not None:
        max_results = limit

    client = _get_client(as_json)
    try:
        result = client.next(max_results=max_results, page_token=page_token)
    except Exception as e:
        _handle_api_error(e, as_json)

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
        console.print(f"  [dim]{cal_item['id']}[/dim]")


@cal.command()
@click.argument("summary")
@click.option("--start", required=True, help="Start time (ISO 8601 or YYYY-MM-DD)")
@click.option("--end", required=True, help="End time (ISO 8601 or YYYY-MM-DD)")
@click.option("--description", "-d", default="", help="Event description")
@click.option("--attendee", "-a", "attendees", multiple=True, help="Attendee email (repeatable)")
@click.option("--dry-run", is_flag=True, help="Preview without executing")
@click.option("--quiet", "-q", is_flag=True, help="Suppress success messages")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def create(
    summary: str,
    start: str,
    end: str,
    description: str,
    attendees: tuple[str, ...],
    dry_run: bool,
    quiet: bool,
    as_json: bool,
) -> None:
    """Create a new event.

    Examples:

        desk cal create "Standup" --start 2024-01-15T10:00:00 --end 2024-01-15T10:30:00

        desk cal create "Sync" --start 2024-01-15T10:00:00 --end 2024-01-15T11:00:00 -a bob@co.com
    """
    client = _get_client(as_json)

    if dry_run:
        target = {
            "summary": summary,
            "start": start,
            "end": end,
        }
        if attendees:
            target["attendees"] = list(attendees)
        preview = dry_run_preview(
            operation="create event",
            targets=[target],
            reversible=True,
            undo_command="desk cal delete <event-id>",
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
        )
    except Exception as e:
        _handle_api_error(e, as_json, {"summary": summary, "start": start, "end": end})

    receipt = operation_receipt(
        operation="create",
        target={
            "id": event.get("id"),
            "summary": event.get("summary"),
            "start": event.get("start"),
            "end": event.get("end"),
            "link": event.get("htmlLink"),
        },
        undo_command=f"desk cal delete {event.get('id')} --yes",
    )
    output_result(receipt, as_json, quiet)


@cal.command()
@click.argument("event_id")
@click.option("--yes", "-y", is_flag=True, help="Skip confirmation prompt")
@click.option("--dry-run", is_flag=True, help="Preview without executing")
@click.option("--quiet", "-q", is_flag=True, help="Suppress success messages")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def delete(event_id: str, yes: bool, dry_run: bool, quiet: bool, as_json: bool) -> None:
    """Delete an event.

    Deleting an event with attendees sends cancellation emails to all attendees.
    Use --yes to skip confirmation (for scripting).

    Examples:

        desk cal delete <event-id>

        desk cal delete <event-id> --yes

        desk cal delete <event-id> --dry-run
    """
    client = _get_client(as_json)

    # Fetch event details for confirmation/preview
    try:
        event = client.get_event(event_id)
    except RuntimeError as e:
        _handle_api_error(e, as_json, {"event_id": event_id})

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
                    details={"event_id": event_id, "attendees": attendee_count},
                )
                print(json.dumps(error, indent=2))
            else:
                console.print("[red]Error: This event has attendees. Use --yes to confirm deletion in non-interactive mode.[/red]")
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
        client.delete(event_id)
    except Exception as e:
        _handle_api_error(e, as_json, {"event_id": event_id})

    receipt = operation_receipt(
        operation="delete",
        target={
            "id": event_id,
            "summary": event.get("summary"),
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
    """
    client = _get_client(as_json)
    try:
        event = client.update(
            event_id,
            summary=summary,
            start=start,
            end=end,
            description=description,
            add_attendees=list(add_attendees) if add_attendees else None,
            remove_attendees=list(remove_attendees) if remove_attendees else None,
        )
    except Exception as e:
        _handle_api_error(e, as_json, {"event_id": event_id})

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
            "link": event.get("htmlLink"),
        },
        changes=changes,
    )
    output_result(receipt, as_json, quiet)


@cal.command()
@click.argument("query")
@click.option("--max", "-n", "max_results", default=10, help="Max results")
@click.option("--limit", "limit", default=None, type=int, help="Max results (alias for --max)")
@click.option("--page-token", "page_token", default=None, help="Continue from previous page")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def find(query: str, max_results: int, limit: int | None, page_token: str | None, as_json: bool) -> None:
    """Search for events by text.

    Examples:

        desk cal find "standup"

        desk cal find "review" --max 5
    """
    # --limit takes precedence if provided
    if limit is not None:
        max_results = limit

    client = _get_client(as_json)
    try:
        result = client.find(query, max_results=max_results, page_token=page_token)
    except Exception as e:
        _handle_api_error(e, as_json, {"query": query})

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
            print(json.dumps(error, indent=2))
        else:
            console.print(f"[red]Error: {e}[/red]")
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

    for event in events:
        start = event.get("start", "")
        # Strip seconds from datetime for readability
        if "T" in start:
            start = start[:16].replace("T", " ")
        table.add_row(
            start,
            event.get("summary", "(no title)"),
            event.get("location", ""),
        )

    console.print(table)
