"""Morning brief — calendar + unread emails in one view."""

import json
import sys
from datetime import datetime

import click
from rich.console import Console

from desk.auth import get_credentials
from desk.services.calendar import CalendarClient
from desk.services.gmail import GmailClient

console = Console()


def _get_clients() -> tuple[CalendarClient, GmailClient]:
    """Get authenticated Calendar and Gmail clients or exit."""
    creds = get_credentials()
    if not creds:
        console.print("[red]Not authenticated.[/red]")
        console.print("Run: [cyan]desk setup[/cyan]")
        sys.exit(1)
    return CalendarClient(creds), GmailClient(creds)


@click.command()
@click.option("--max", "-n", "max_results", default=20, help="Max unread messages")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def brief(max_results: int, as_json: bool) -> None:
    """Morning brief — today's calendar + unread emails.

    Examples:

        desk brief

        desk brief --json

        desk brief --max 10
    """
    cal_client, gmail_client = _get_clients()
    events = cal_client.today()
    unread = gmail_client.search("is:unread", max_results=max_results)

    if as_json:
        print(json.dumps({
            "date": datetime.now().strftime("%Y-%m-%d"),
            "calendar": events,
            "unread": unread,
            "unread_count": len(unread),
        }, indent=2))
        return

    today = datetime.now()
    console.print(f"[bold]Morning Brief — {today.strftime('%A, %b %-d')}[/bold]")
    console.print()

    # Calendar
    console.print("[bold]Today[/bold]")
    if not events:
        console.print("  [dim]No events.[/dim]")
    else:
        for event in events:
            start = event.get("start", "")
            if "T" in start:
                time_str = start[11:16]
            else:
                time_str = "all day"
            summary = event.get("summary", "(no title)")
            console.print(f"  {time_str:>7}  {summary}")
    console.print()

    # Unread
    console.print(f"[bold]Unread ({len(unread)} messages)[/bold]")
    if not unread:
        console.print("  [dim]Inbox zero![/dim]")
    else:
        for msg in unread:
            sender = msg.get("from", "")
            # Extract just the name/address before angle brackets
            if "<" in sender:
                sender = sender.split("<")[0].strip().strip('"')
            subject = msg.get("subject", "(no subject)")
            console.print(f"  {sender[:20]:<20}  {subject[:50]}")
