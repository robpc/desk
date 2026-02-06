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


def _collect_ids(message_ids: tuple[str, ...], stdin: bool) -> list[str]:
    """Collect message IDs from arguments and/or stdin.

    Args:
        message_ids: IDs passed as arguments
        stdin: Whether to read IDs from stdin

    Returns:
        List of message IDs
    """
    ids = list(message_ids)

    if stdin:
        # Read IDs from stdin, one per line
        for line in sys.stdin:
            line = line.strip()
            if line:
                ids.append(line)

    return ids


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
@click.argument("label_name")
@click.argument("message_ids", nargs=-1)
@click.option("--stdin", is_flag=True, help="Read message IDs from stdin")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def label(label_name: str, message_ids: tuple[str, ...], stdin: bool, as_json: bool) -> None:
    """Add a label to messages.

    Supports multiple IDs and stdin for batch operations.

    Examples:

        gmail label Work ID1 ID2 ID3

        gmail search "from:boss" --json | jq -r '.[].id' | gmail label Important --stdin
    """
    ids = _collect_ids(message_ids, stdin)
    if not ids:
        console.print("[yellow]No message IDs provided.[/yellow]")
        return

    client = _get_client()
    # Resolve label name to ID
    label_id = client._get_label_id(label_name)
    if not label_id:
        label_id = client._resolve_label(label_name)

    client.batch_modify(ids, add_labels=[label_id])

    if as_json:
        print(json.dumps({"action": "label", "label": label_name, "count": len(ids), "ids": ids}))
    else:
        console.print(f"[green]Added label '{label_name}' to {len(ids)} message(s)[/green]")


@main.command()
@click.argument("message_ids", nargs=-1)
@click.option("--stdin", is_flag=True, help="Read message IDs from stdin")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def archive(message_ids: tuple[str, ...], stdin: bool, as_json: bool) -> None:
    """Archive messages (remove from inbox).

    Supports multiple IDs and stdin for batch operations.

    Examples:

        gmail archive ID1 ID2 ID3

        gmail search "from:bot" --json | jq -r '.[].id' | gmail archive --stdin
    """
    ids = _collect_ids(message_ids, stdin)
    if not ids:
        console.print("[yellow]No message IDs provided.[/yellow]")
        return

    client = _get_client()
    client.batch_modify(ids, remove_labels=["INBOX"])

    if as_json:
        print(json.dumps({"action": "archive", "count": len(ids), "ids": ids}))
    else:
        console.print(f"[green]Archived {len(ids)} message(s)[/green]")


@main.command("mark-read")
@click.argument("message_ids", nargs=-1)
@click.option("--stdin", is_flag=True, help="Read message IDs from stdin")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def mark_read(message_ids: tuple[str, ...], stdin: bool, as_json: bool) -> None:
    """Mark messages as read.

    Supports multiple IDs and stdin for batch operations.

    Examples:

        gmail mark-read ID1 ID2 ID3

        gmail search "is:unread" --json | jq -r '.[].id' | gmail mark-read --stdin
    """
    ids = _collect_ids(message_ids, stdin)
    if not ids:
        console.print("[yellow]No message IDs provided.[/yellow]")
        return

    client = _get_client()
    client.batch_modify(ids, remove_labels=["UNREAD"])

    if as_json:
        print(json.dumps({"action": "mark-read", "count": len(ids), "ids": ids}))
    else:
        console.print(f"[green]Marked {len(ids)} message(s) as read[/green]")


@main.command()
@click.argument("message_ids", nargs=-1)
@click.option("--stdin", is_flag=True, help="Read message IDs from stdin")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def trash(message_ids: tuple[str, ...], stdin: bool, as_json: bool) -> None:
    """Move messages to trash.

    Supports multiple IDs and stdin for batch operations.

    Examples:

        gmail trash ID1 ID2 ID3

        gmail search "from:spam" --json | jq -r '.[].id' | gmail trash --stdin
    """
    ids = _collect_ids(message_ids, stdin)
    if not ids:
        console.print("[yellow]No message IDs provided.[/yellow]")
        return

    client = _get_client()
    client.batch_modify(ids, add_labels=["TRASH"], remove_labels=["INBOX"])

    if as_json:
        print(json.dumps({"action": "trash", "count": len(ids), "ids": ids}))
    else:
        console.print(f"[green]Moved {len(ids)} message(s) to trash[/green]")


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
@click.argument("message_ids", nargs=-1)
@click.option("--stdin", is_flag=True, help="Read message IDs from stdin")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def star(message_ids: tuple[str, ...], stdin: bool, as_json: bool) -> None:
    """Star messages.

    Supports multiple IDs and stdin for batch operations.

    Examples:

        gmail star ID1 ID2 ID3
    """
    ids = _collect_ids(message_ids, stdin)
    if not ids:
        console.print("[yellow]No message IDs provided.[/yellow]")
        return

    client = _get_client()
    client.batch_modify(ids, add_labels=["STARRED"])

    if as_json:
        print(json.dumps({"action": "star", "count": len(ids), "ids": ids}))
    else:
        console.print(f"[green]Starred {len(ids)} message(s)[/green]")


@main.command()
@click.argument("message_ids", nargs=-1)
@click.option("--stdin", is_flag=True, help="Read message IDs from stdin")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def unstar(message_ids: tuple[str, ...], stdin: bool, as_json: bool) -> None:
    """Remove star from messages.

    Supports multiple IDs and stdin for batch operations.

    Examples:

        gmail unstar ID1 ID2 ID3
    """
    ids = _collect_ids(message_ids, stdin)
    if not ids:
        console.print("[yellow]No message IDs provided.[/yellow]")
        return

    client = _get_client()
    client.batch_modify(ids, remove_labels=["STARRED"])

    if as_json:
        print(json.dumps({"action": "unstar", "count": len(ids), "ids": ids}))
    else:
        console.print(f"[green]Unstarred {len(ids)} message(s)[/green]")


@main.command("remove-label")
@click.argument("label_name")
@click.argument("message_ids", nargs=-1)
@click.option("--stdin", is_flag=True, help="Read message IDs from stdin")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def remove_label(label_name: str, message_ids: tuple[str, ...], stdin: bool, as_json: bool) -> None:
    """Remove a label from messages.

    Supports multiple IDs and stdin for batch operations.

    Examples:

        gmail remove-label Work ID1 ID2 ID3
    """
    ids = _collect_ids(message_ids, stdin)
    if not ids:
        console.print("[yellow]No message IDs provided.[/yellow]")
        return

    client = _get_client()
    # Resolve label name to ID
    label_id = client._get_label_id(label_name)
    if not label_id:
        label_id = client._resolve_label(label_name)

    client.batch_modify(ids, remove_labels=[label_id])

    if as_json:
        print(json.dumps({"action": "remove-label", "label": label_name, "count": len(ids), "ids": ids}))
    else:
        console.print(f"[green]Removed label '{label_name}' from {len(ids)} message(s)[/green]")


@main.command()
@click.argument("message_ids", nargs=-1)
@click.option("--add-label", "-a", "add_labels", multiple=True, help="Label to add (repeatable)")
@click.option("--remove-label", "-r", "remove_labels", multiple=True, help="Label to remove (repeatable)")
@click.option("--stdin", is_flag=True, help="Read message IDs from stdin")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def modify(message_ids: tuple[str, ...], add_labels: tuple[str], remove_labels: tuple[str], stdin: bool, as_json: bool) -> None:
    """Modify message labels (generic operation).

    Compose arbitrary label changes. System labels (INBOX, UNREAD, STARRED, etc.)
    and user labels are both supported.

    Supports multiple IDs and stdin for batch operations.

    Examples:

        gmail modify ID --remove-label INBOX --remove-label UNREAD

        gmail modify ID1 ID2 ID3 --add-label Work --remove-label INBOX

        gmail search "from:bot" --json | jq -r '.[].id' | gmail modify --stdin --remove-label INBOX
    """
    if not add_labels and not remove_labels:
        console.print("[yellow]Nothing to do. Use --add-label or --remove-label.[/yellow]")
        return

    ids = _collect_ids(message_ids, stdin)
    if not ids:
        console.print("[yellow]No message IDs provided.[/yellow]")
        return

    client = _get_client()
    client.batch_modify(
        ids,
        add_labels=list(add_labels) if add_labels else None,
        remove_labels=list(remove_labels) if remove_labels else None,
    )

    changes = []
    if add_labels:
        changes.append(f"+{', +'.join(add_labels)}")
    if remove_labels:
        changes.append(f"-{', -'.join(remove_labels)}")

    if as_json:
        print(json.dumps({"action": "modify", "changes": changes, "count": len(ids), "ids": ids}))
    else:
        console.print(f"[green]Modified {len(ids)} message(s): {' '.join(changes)}[/green]")


if __name__ == "__main__":
    main()
