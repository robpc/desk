"""Calendar commands — view and create events."""

import json
import sys

import click
from rich.console import Console
from rich.table import Table

from desk.auth import get_credentials
from desk.services.calendar import CalendarClient

console = Console()


def _get_client() -> CalendarClient:
    """Get authenticated Calendar client or exit."""
    creds = get_credentials()
    if not creds:
        console.print("[red]Not authenticated.[/red]")
        console.print("Run: [cyan]desk setup[/cyan]")
        sys.exit(1)
    return CalendarClient(creds)


@click.group()
def cal() -> None:
    """Google Calendar — view and create events."""
    pass


@cal.command()
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def today(as_json: bool) -> None:
    """Show today's events.

    Examples:

        desk cal today
    """
    client = _get_client()
    events = client.today()

    if as_json:
        print(json.dumps(events, indent=2))
        return

    _print_events(events, "Today")


@cal.command()
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def week(as_json: bool) -> None:
    """Show this week's events.

    Examples:

        desk cal week
    """
    client = _get_client()
    events = client.week()

    if as_json:
        print(json.dumps(events, indent=2))
        return

    _print_events(events, "This week")


@cal.command("next")
@click.option("--max", "-n", "max_results", default=10, help="Max results")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def next_events(max_results: int, as_json: bool) -> None:
    """Show upcoming events.

    Examples:

        desk cal next --max 5
    """
    client = _get_client()
    events = client.next(max_results=max_results)

    if as_json:
        print(json.dumps(events, indent=2))
        return

    _print_events(events, "Upcoming")


@cal.command("list")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def list_calendars(as_json: bool) -> None:
    """List all calendars.

    Examples:

        desk cal list
    """
    client = _get_client()
    calendars = client.list_calendars()

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
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def create(
    summary: str,
    start: str,
    end: str,
    description: str,
    attendees: tuple[str, ...],
    as_json: bool,
) -> None:
    """Create a new event.

    Examples:

        desk cal create "Standup" --start 2024-01-15T10:00:00 --end 2024-01-15T10:30:00

        desk cal create "Sync" --start 2024-01-15T10:00:00 --end 2024-01-15T11:00:00 -a bob@co.com
    """
    client = _get_client()
    event = client.create(
        summary,
        start,
        end,
        description=description,
        attendees=list(attendees) if attendees else None,
    )

    if as_json:
        print(json.dumps(event, indent=2))
    else:
        console.print(f"[green]Created event: {event['summary']}[/green]")
        if event.get("htmlLink"):
            console.print(f"[dim]{event['htmlLink']}[/dim]")


@cal.command()
@click.argument("event_id")
@click.option("--yes", "-y", is_flag=True, help="Skip confirmation prompt")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def delete(event_id: str, yes: bool, as_json: bool) -> None:
    """Delete an event.

    Deleting an event with attendees sends cancellation emails to all attendees.
    Use --yes to skip confirmation (for scripting).

    Examples:

        desk cal delete <event-id>

        desk cal delete <event-id> --yes
    """
    client = _get_client()

    # Fetch event details for confirmation
    try:
        event = client.get_event(event_id)
    except RuntimeError:
        console.print(f"[red]Event not found: {event_id}[/red]")
        sys.exit(1)

    attendee_count = event.get("attendeeCount", 0)

    # Require confirmation if there are attendees
    if attendee_count > 0 and not yes:
        # Check if we're in an interactive terminal
        if not sys.stdin.isatty():
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

    client.delete(event_id)

    if as_json:
        print(json.dumps({"eventId": event_id, "status": "deleted"}, indent=2))
    else:
        console.print("[green]Event deleted.[/green]")


@cal.command()
@click.argument("event_id")
@click.option("--summary", "-s", help="New title")
@click.option("--start", help="New start time (ISO 8601)")
@click.option("--end", help="New end time (ISO 8601)")
@click.option("--description", "-d", help="New description")
@click.option(
    "--add-attendee", "-a", "add_attendees", multiple=True, help="Email to add (repeatable)"
)
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def update(
    event_id: str,
    summary: str | None,
    start: str | None,
    end: str | None,
    description: str | None,
    add_attendees: tuple[str, ...],
    as_json: bool,
) -> None:
    """Update an existing event.

    Only provided fields are changed.

    Examples:

        desk cal update <id> --summary "New Title"

        desk cal update <id> --start 2024-01-15T14:00:00 --end 2024-01-15T15:00:00

        desk cal update <id> -a newperson@example.com
    """
    client = _get_client()
    event = client.update(
        event_id,
        summary=summary,
        start=start,
        end=end,
        description=description,
        add_attendees=list(add_attendees) if add_attendees else None,
    )

    if as_json:
        print(json.dumps(event, indent=2))
    else:
        console.print(f"[green]Updated: {event['summary']}[/green]")
        if event.get("htmlLink"):
            console.print(f"[dim]{event['htmlLink']}[/dim]")


@cal.command()
@click.argument("query")
@click.option("--max", "-n", "max_results", default=10, help="Max results")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def find(query: str, max_results: int, as_json: bool) -> None:
    """Search for events by text.

    Examples:

        desk cal find "standup"

        desk cal find "review" --max 5
    """
    client = _get_client()
    events = client.find(query, max_results=max_results)

    if as_json:
        print(json.dumps(events, indent=2))
        return

    _print_events(events, f"Results for '{query}'")


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
