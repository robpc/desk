"""Gmail CLI - Command-line interface."""

import json
import sys

import click
from rich.console import Console
from rich.table import Table

from gm import __version__
from gm.auth import get_auth_status, get_credentials, login
from gm.gmail import GmailClient

console = Console()


@click.group()
@click.version_option(version=__version__)
@click.option("--verbose", "-v", is_flag=True, help="Verbose output")
@click.pass_context
def main(ctx: click.Context, verbose: bool) -> None:
    """Gmail CLI - Manage your Gmail from the command line."""
    ctx.ensure_object(dict)
    ctx.obj["verbose"] = verbose


# --- Auth commands ---


@main.group()
def auth() -> None:
    """Authentication commands."""
    pass


@auth.command()
@click.pass_context
def login_cmd(ctx: click.Context) -> None:
    """Authenticate with Gmail."""
    verbose = ctx.obj.get("verbose", False)
    login(verbose=verbose)
    console.print("[green]Authentication successful![/green]")


# Rename to avoid conflict with login function
login_cmd.name = "login"


@auth.command()
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def status(as_json: bool) -> None:
    """Check authentication status."""
    info = get_auth_status()

    if as_json:
        print(json.dumps(info, indent=2))
        return

    if info["authenticated"]:
        console.print("[green]Authenticated[/green]")
    else:
        console.print("[red]Not authenticated[/red]")
        if not info["credentials_file"]:
            console.print(f"  Missing: {info['credentials_path']}")
        if not info["token_file"]:
            console.print(f"  Missing: {info['token_path']}")
            console.print("  Run: gm auth login")


# --- Gmail commands ---


def _get_client() -> GmailClient:
    """Get authenticated Gmail client or exit."""
    creds = get_credentials()
    if not creds:
        console.print("[red]Not authenticated. Run: gm auth login[/red]")
        sys.exit(1)
    return GmailClient(creds)


@main.command()
@click.argument("query")
@click.option("--max", "-n", "max_results", default=20, help="Max results")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def search(query: str, max_results: int, as_json: bool) -> None:
    """Search for messages.

    Uses Gmail search syntax (same as Gmail search box).

    Examples:

        gm search "from:boss is:unread"

        gm search "after:2024/01/01 has:attachment"
    """
    client = _get_client()
    messages = client.search(query, max_results=max_results)

    if as_json:
        print(json.dumps(messages, indent=2))
        return

    if not messages:
        console.print("No messages found.")
        return

    table = Table(show_header=True)
    table.add_column("ID", style="dim", width=16)
    table.add_column("From", width=30)
    table.add_column("Subject", width=40)
    table.add_column("Date", width=20)

    for msg in messages:
        table.add_row(
            msg["id"],
            msg["from"][:30],
            msg["subject"][:40],
            msg["date"][:20],
        )

    console.print(table)


@main.command()
@click.argument("message_id")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def read(message_id: str, as_json: bool) -> None:
    """Read a message by ID."""
    client = _get_client()
    message = client.read(message_id)

    if as_json:
        print(json.dumps(message, indent=2))
        return

    console.print(f"[bold]From:[/bold] {message['from']}")
    console.print(f"[bold]Subject:[/bold] {message['subject']}")
    console.print(f"[bold]Date:[/bold] {message['date']}")
    console.print()
    console.print(message.get("body", "(no body)"))


@main.command()
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def labels(as_json: bool) -> None:
    """List available labels."""
    client = _get_client()
    label_list = client.list_labels()

    if as_json:
        print(json.dumps(label_list, indent=2))
        return

    for label in sorted(label_list, key=lambda x: x["name"]):
        console.print(label["name"])


@main.command()
@click.argument("message_id")
@click.argument("label_name")
def label(message_id: str, label_name: str) -> None:
    """Add a label to a message."""
    client = _get_client()
    client.add_label(message_id, label_name)
    console.print(f"[green]Added label '{label_name}' to {message_id}[/green]")


@main.command()
@click.argument("message_id")
def archive(message_id: str) -> None:
    """Archive a message (remove from inbox)."""
    client = _get_client()
    client.archive(message_id)
    console.print(f"[green]Archived {message_id}[/green]")


if __name__ == "__main__":
    main()
