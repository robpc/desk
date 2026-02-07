"""Mail commands — Gmail operations."""

import json
import sys

import click
from rich.console import Console
from rich.table import Table

from desk.auth import get_credentials
from desk.services.gmail import GmailClient

console = Console()


def _get_client() -> GmailClient:
    """Get authenticated Gmail client or exit."""
    creds = get_credentials()
    if not creds:
        console.print("[red]Not authenticated.[/red]")
        console.print("Run: [cyan]desk setup[/cyan]")
        sys.exit(1)
    return GmailClient(creds)


def _collect_ids(message_ids: tuple[str, ...], stdin: bool) -> list[str]:
    """Collect message IDs from arguments and/or stdin."""
    ids = list(message_ids)
    if stdin:
        for line in sys.stdin:
            line = line.strip()
            if line:
                ids.append(line)
    return ids


@click.group()
def mail() -> None:
    """Gmail — search, read, label, archive."""
    pass


@mail.command()
@click.argument("query")
@click.option("--max", "-n", "max_results", default=20, help="Max results")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def search(query: str, max_results: int, as_json: bool) -> None:
    """Search for messages.

    Uses Gmail search syntax (same as Gmail search box).

    Examples:

        desk mail search "from:boss is:unread"

        desk mail search "after:2024/01/01 has:attachment"
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


@mail.command()
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


@mail.command()
@click.option("--to", "-t", "to_addrs", multiple=True, required=True, help="Recipient (repeatable)")
@click.option("--cc", "cc_addrs", multiple=True, help="CC recipient (repeatable)")
@click.option("--bcc", "bcc_addrs", multiple=True, help="BCC recipient (repeatable)")
@click.option("--subject", "-s", required=True, help="Email subject")
@click.option("--body", "-b", "body_text", default=None, help="Email body (plain text)")
@click.option("--body-file", "-f", "body_file", default=None, help="Read body from file")
@click.option("--stdin", "from_stdin", is_flag=True, help="Read body from stdin")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def send(
    to_addrs: tuple[str, ...],
    cc_addrs: tuple[str, ...],
    bcc_addrs: tuple[str, ...],
    subject: str,
    body_text: str | None,
    body_file: str | None,
    from_stdin: bool,
    as_json: bool,
) -> None:
    """Send an email.

    Body can be provided via --body, --body-file, or --stdin.

    Examples:

        desk mail send --to "user@example.com" --subject "Hello" --body "Message"

        desk mail send --to "a@example.com" --cc "b@example.com" --subject "Update" --body "..."

        echo "Report content" | desk mail send --to "boss@example.com" --subject "Report" --stdin

        desk mail send --to "user@example.com" --subject "Notes" --body-file notes.txt
    """
    # Determine body source
    body_sources = sum([body_text is not None, body_file is not None, from_stdin])
    if body_sources == 0:
        console.print("[red]Error: Must provide body via --body, --body-file, or --stdin[/red]")
        sys.exit(1)
    if body_sources > 1:
        console.print("[red]Error: Use only one of --body, --body-file, or --stdin[/red]")
        sys.exit(1)

    # Get body content
    if body_text is not None:
        body = body_text
    elif body_file is not None:
        try:
            with open(body_file) as f:
                body = f.read()
        except FileNotFoundError:
            console.print(f"[red]Error: File not found: {body_file}[/red]")
            sys.exit(1)
        except OSError as e:
            console.print(f"[red]Error reading file: {e}[/red]")
            sys.exit(1)
    else:  # from_stdin
        body = sys.stdin.read()

    client = _get_client()
    result = client.send(
        to=list(to_addrs),
        subject=subject,
        body=body,
        cc=list(cc_addrs) if cc_addrs else None,
        bcc=list(bcc_addrs) if bcc_addrs else None,
    )

    if as_json:
        print(json.dumps(result, indent=2))
    else:
        console.print(f"[green]Sent message to {', '.join(to_addrs)}[/green]")
        console.print(f"[dim]Message ID: {result.get('id', 'unknown')}[/dim]")


@mail.command()
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


@mail.command("create-label")
@click.argument("name")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def create_label(name: str, as_json: bool) -> None:
    """Create a new label.

    Use "/" for nested labels (appears hierarchically in Gmail UI).

    Examples:

        desk mail create-label "Projects/Orion"
    """
    client = _get_client()

    try:
        label = client.create_label(name)
    except ValueError as e:
        console.print(f"[yellow]{e}[/yellow]")
        return

    if as_json:
        print(json.dumps(label, indent=2))
    else:
        console.print(f"[green]Created label '{name}'[/green]")


@mail.command()
@click.argument("label_name")
@click.argument("message_ids", nargs=-1)
@click.option("--stdin", is_flag=True, help="Read message IDs from stdin")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def label(label_name: str, message_ids: tuple[str, ...], stdin: bool, as_json: bool) -> None:
    """Add a label to messages.

    Examples:

        desk mail label Work ID1 ID2 ID3

        desk mail search "from:boss" --json | jq -r '.[].id' | desk mail label Important --stdin
    """
    ids = _collect_ids(message_ids, stdin)
    if not ids:
        console.print("[yellow]No message IDs provided.[/yellow]")
        return

    client = _get_client()
    label_id = client._get_label_id(label_name)
    if not label_id:
        label_id = client._resolve_label(label_name)

    client.batch_modify(ids, add_labels=[label_id])

    if as_json:
        print(json.dumps({"action": "label", "label": label_name, "count": len(ids), "ids": ids}))
    else:
        console.print(f"[green]Added label '{label_name}' to {len(ids)} message(s)[/green]")


@mail.command()
@click.argument("message_ids", nargs=-1)
@click.option("--stdin", is_flag=True, help="Read message IDs from stdin")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def archive(message_ids: tuple[str, ...], stdin: bool, as_json: bool) -> None:
    """Archive messages (remove from inbox).

    Examples:

        desk mail archive ID1 ID2 ID3

        desk mail search "from:bot" --json | jq -r '.[].id' | desk mail archive --stdin
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


@mail.command("mark-read")
@click.argument("message_ids", nargs=-1)
@click.option("--stdin", is_flag=True, help="Read message IDs from stdin")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def mark_read(message_ids: tuple[str, ...], stdin: bool, as_json: bool) -> None:
    """Mark messages as read.

    Examples:

        desk mail mark-read ID1 ID2 ID3
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


@mail.command("mark-unread")
@click.argument("message_ids", nargs=-1)
@click.option("--stdin", is_flag=True, help="Read message IDs from stdin")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def mark_unread(message_ids: tuple[str, ...], stdin: bool, as_json: bool) -> None:
    """Mark messages as unread.

    Examples:

        desk mail mark-unread ID1 ID2 ID3
    """
    ids = _collect_ids(message_ids, stdin)
    if not ids:
        console.print("[yellow]No message IDs provided.[/yellow]")
        return

    client = _get_client()
    client.batch_modify(ids, add_labels=["UNREAD"])

    if as_json:
        print(json.dumps({"action": "mark-unread", "count": len(ids), "ids": ids}))
    else:
        console.print(f"[green]Marked {len(ids)} message(s) as unread[/green]")


@mail.command()
@click.argument("message_ids", nargs=-1)
@click.option("--stdin", is_flag=True, help="Read message IDs from stdin")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def trash(message_ids: tuple[str, ...], stdin: bool, as_json: bool) -> None:
    """Move messages to trash.

    Examples:

        desk mail trash ID1 ID2 ID3
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


@mail.command()
@click.option("--max", "-n", "max_results", default=20, help="Max results")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def unread(max_results: int, as_json: bool) -> None:
    """List unread messages.

    Shortcut for: desk mail search "is:unread"
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


@mail.command()
@click.argument("message_ids", nargs=-1)
@click.option("--stdin", is_flag=True, help="Read message IDs from stdin")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def star(message_ids: tuple[str, ...], stdin: bool, as_json: bool) -> None:
    """Star messages.

    Examples:

        desk mail star ID1 ID2 ID3
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


@mail.command()
@click.argument("message_ids", nargs=-1)
@click.option("--stdin", is_flag=True, help="Read message IDs from stdin")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def unstar(message_ids: tuple[str, ...], stdin: bool, as_json: bool) -> None:
    """Remove star from messages.

    Examples:

        desk mail unstar ID1 ID2 ID3
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


@mail.command("remove-label")
@click.argument("label_name")
@click.argument("message_ids", nargs=-1)
@click.option("--stdin", is_flag=True, help="Read message IDs from stdin")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def remove_label(label_name: str, message_ids: tuple[str, ...], stdin: bool, as_json: bool) -> None:
    """Remove a label from messages.

    Examples:

        desk mail remove-label Work ID1 ID2 ID3
    """
    ids = _collect_ids(message_ids, stdin)
    if not ids:
        console.print("[yellow]No message IDs provided.[/yellow]")
        return

    client = _get_client()
    label_id = client._get_label_id(label_name)
    if not label_id:
        label_id = client._resolve_label(label_name)

    client.batch_modify(ids, remove_labels=[label_id])

    if as_json:
        result = {"action": "remove-label", "label": label_name, "count": len(ids), "ids": ids}
        print(json.dumps(result))
    else:
        console.print(f"[green]Removed label '{label_name}' from {len(ids)} message(s)[/green]")


@mail.command()
@click.argument("message_ids", nargs=-1)
@click.option("--add-label", "-a", "add_labels", multiple=True, help="Label to add (repeatable)")
@click.option(
    "--remove-label", "-r", "remove_labels", multiple=True, help="Label to remove (repeatable)"
)
@click.option("--stdin", is_flag=True, help="Read message IDs from stdin")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def modify(
    message_ids: tuple[str, ...],
    add_labels: tuple[str],
    remove_labels: tuple[str],
    stdin: bool,
    as_json: bool,
) -> None:
    """Modify message labels (generic operation).

    Compose arbitrary label changes. System labels (INBOX, UNREAD, STARRED, etc.)
    and user labels are both supported.

    Examples:

        desk mail modify ID --remove-label INBOX --remove-label UNREAD

        desk mail modify ID1 ID2 --add-label Work --remove-label INBOX
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
