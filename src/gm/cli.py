"""Gmail CLI - Command-line interface."""

import json
import shutil
import sys
from pathlib import Path

import click
from rich.console import Console
from rich.table import Table

from gm import __version__
from gm.auth import (
    AuthMethod,
    get_auth_status,
    get_credentials,
    login,
    login_with_gcloud,
)
from gm.config import CONFIG_DIR, CREDENTIALS_FILE, SCOPES
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


# --- Setup command ---


@main.command()
@click.option(
    "--credentials",
    "-c",
    type=click.Path(exists=True, path_type=Path),
    help="Path to credentials.json file",
)
@click.option("--gcloud", "use_gcloud", is_flag=True, help="Use gcloud for authentication")
@click.pass_context
def setup(ctx: click.Context, credentials: Path | None, use_gcloud: bool) -> None:
    """Set up Gmail CLI authentication.

    For personal use (simplest):

        gm setup --gcloud

    For team setup (with shared credentials):

        gm setup --credentials ~/Downloads/credentials.json
    """
    verbose = ctx.obj.get("verbose", False)

    if use_gcloud:
        console.print("Authenticating with gcloud...")
        creds = login_with_gcloud(verbose=verbose)
        if creds:
            console.print("[green]Authentication successful![/green]")
            console.print("You can now use gm commands.")
        else:
            console.print("[red]gcloud authentication failed.[/red]")
            console.print("Make sure gcloud is installed and try again.")
            sys.exit(1)
        return

    if credentials:
        # Copy credentials to config dir
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        shutil.copy(credentials, CREDENTIALS_FILE)
        console.print(f"Copied credentials to {CREDENTIALS_FILE}")
        console.print()
        console.print("Now running authentication flow...")
        login(verbose=verbose)
        console.print("[green]Authentication successful![/green]")
        return

    # Interactive setup
    console.print("[bold]Gmail CLI Setup[/bold]")
    console.print()

    # Check if gcloud is available
    status = get_auth_status()

    if status["gcloud_available"]:
        console.print("Choose setup method:")
        console.print()
        console.print("  [bold]1.[/bold] gcloud (simplest, for personal use)")
        console.print("     Run: [cyan]gm setup --gcloud[/cyan]")
        console.print()
        console.print("  [bold]2.[/bold] Team credentials (for shared projects)")
        console.print("     Run: [cyan]gm setup --credentials /path/to/credentials.json[/cyan]")
    else:
        console.print("gcloud not found. Using team credentials setup.")
        console.print()
        console.print("To set up:")
        console.print("  1. Get credentials.json from your team's 1Password vault")
        console.print("  2. Run: [cyan]gm setup --credentials /path/to/credentials.json[/cyan]")


# --- Auth commands ---


@main.group()
def auth() -> None:
    """Authentication commands."""
    pass


@auth.command("login")
@click.option("--gcloud", "use_gcloud", is_flag=True, help="Use gcloud for authentication")
@click.pass_context
def auth_login(ctx: click.Context, use_gcloud: bool) -> None:
    """Authenticate with Gmail.

    Use --gcloud for gcloud-based auth, or ensure credentials.json exists.
    """
    verbose = ctx.obj.get("verbose", False)

    if use_gcloud:
        creds = login_with_gcloud(verbose=verbose)
        if creds:
            console.print("[green]Authentication successful![/green]")
        else:
            console.print("[red]gcloud authentication failed.[/red]")
            sys.exit(1)
    else:
        login(verbose=verbose)
        console.print("[green]Authentication successful![/green]")


@auth.command("status")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def auth_status(as_json: bool) -> None:
    """Check authentication status."""
    info = get_auth_status()

    if as_json:
        print(json.dumps(info, indent=2))
        return

    if info["authenticated"]:
        method_display = {
            AuthMethod.GCLOUD_ADC: "gcloud ADC",
            AuthMethod.OAUTH_CLIENT: "OAuth credentials",
        }.get(info["method"], info["method"])

        console.print(f"[green]Authenticated[/green] via {method_display}")
    else:
        console.print("[red]Not authenticated[/red]")
        console.print()
        if info["gcloud_available"]:
            console.print("Quick setup: [cyan]gm setup --gcloud[/cyan]")
        else:
            console.print("Run: [cyan]gm setup[/cyan] for setup instructions")


# --- Gmail commands ---


def _get_client() -> GmailClient:
    """Get authenticated Gmail client or exit."""
    creds = get_credentials()
    if not creds:
        console.print("[red]Not authenticated.[/red]")
        console.print("Run: [cyan]gm setup[/cyan]")
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


@main.command("mark-read")
@click.argument("message_id")
def mark_read(message_id: str) -> None:
    """Mark a message as read."""
    client = _get_client()
    client.mark_read(message_id)
    console.print(f"[green]Marked {message_id} as read[/green]")


@main.command()
@click.argument("message_id")
def trash(message_id: str) -> None:
    """Move a message to trash."""
    client = _get_client()
    client.trash(message_id)
    console.print(f"[green]Moved {message_id} to trash[/green]")


@main.command()
@click.option("--max", "-n", "max_results", default=20, help="Max results")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def unread(max_results: int, as_json: bool) -> None:
    """List unread messages.

    Shortcut for: gmail search "is:unread"

    Examples:

        gmail unread

        gmail unread --max 10
    """
    client = _get_client()
    messages = client.search("is:unread", max_results=max_results)

    if as_json:
        print(json.dumps(messages, indent=2))
        return

    if not messages:
        console.print("No unread messages.")
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
def star(message_id: str) -> None:
    """Star a message."""
    client = _get_client()
    client.star(message_id)
    console.print(f"[green]Starred {message_id}[/green]")


@main.command()
@click.argument("message_id")
def unstar(message_id: str) -> None:
    """Remove star from a message."""
    client = _get_client()
    client.unstar(message_id)
    console.print(f"[green]Unstarred {message_id}[/green]")


@main.command("remove-label")
@click.argument("message_id")
@click.argument("label_name")
def remove_label(message_id: str, label_name: str) -> None:
    """Remove a label from a message."""
    client = _get_client()
    client.remove_label(message_id, label_name)
    console.print(f"[green]Removed label '{label_name}' from {message_id}[/green]")


@main.command()
@click.argument("message_id")
@click.option("--add-label", "-a", "add_labels", multiple=True, help="Label to add (repeatable)")
@click.option("--remove-label", "-r", "remove_labels", multiple=True, help="Label to remove (repeatable)")
def modify(message_id: str, add_labels: tuple[str], remove_labels: tuple[str]) -> None:
    """Modify message labels (generic operation).

    Compose arbitrary label changes. System labels (INBOX, UNREAD, STARRED, etc.)
    and user labels are both supported.

    Examples:

        gmail modify ID --remove-label INBOX --remove-label UNREAD

        gmail modify ID --add-label Work --remove-label INBOX
    """
    if not add_labels and not remove_labels:
        console.print("[yellow]Nothing to do. Use --add-label or --remove-label.[/yellow]")
        return

    client = _get_client()
    client.modify(
        message_id,
        add_labels=list(add_labels) if add_labels else None,
        remove_labels=list(remove_labels) if remove_labels else None,
    )

    changes = []
    if add_labels:
        changes.append(f"+{', +'.join(add_labels)}")
    if remove_labels:
        changes.append(f"-{', -'.join(remove_labels)}")

    console.print(f"[green]Modified {message_id}: {' '.join(changes)}[/green]")


if __name__ == "__main__":
    main()
