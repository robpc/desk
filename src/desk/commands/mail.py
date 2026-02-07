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
@click.option("--dry-run", is_flag=True, help="Preview without sending")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def send(
    to_addrs: tuple[str, ...],
    cc_addrs: tuple[str, ...],
    bcc_addrs: tuple[str, ...],
    subject: str,
    body_text: str | None,
    body_file: str | None,
    from_stdin: bool,
    dry_run: bool,
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

    if dry_run:
        preview = {
            "dry_run": True,
            "action": "send",
            "to": list(to_addrs),
            "cc": list(cc_addrs) if cc_addrs else [],
            "bcc": list(bcc_addrs) if bcc_addrs else [],
            "subject": subject,
            "body_preview": body[:200] + "..." if len(body) > 200 else body,
        }
        if as_json:
            print(json.dumps(preview, indent=2))
        else:
            console.print(f"[yellow]Would send message:[/yellow]")
            console.print(f"  To: {', '.join(to_addrs)}")
            if cc_addrs:
                console.print(f"  CC: {', '.join(cc_addrs)}")
            if bcc_addrs:
                console.print(f"  BCC: {', '.join(bcc_addrs)}")
            console.print(f"  Subject: {subject}")
            console.print(f"  Body: {len(body)} characters")
        return

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


def _get_body(
    body_text: str | None,
    body_file: str | None,
    from_stdin: bool,
    required: bool = True,
) -> str:
    """Get body content from one of the available sources."""
    body_sources = sum([body_text is not None, body_file is not None, from_stdin])

    if body_sources == 0:
        if required:
            console.print("[red]Error: Must provide body via --body, --body-file, or --stdin[/red]")
            sys.exit(1)
        return ""

    if body_sources > 1:
        console.print("[red]Error: Use only one of --body, --body-file, or --stdin[/red]")
        sys.exit(1)

    if body_text is not None:
        return body_text
    elif body_file is not None:
        try:
            with open(body_file) as f:
                return f.read()
        except FileNotFoundError:
            console.print(f"[red]Error: File not found: {body_file}[/red]")
            sys.exit(1)
        except OSError as e:
            console.print(f"[red]Error reading file: {e}[/red]")
            sys.exit(1)
    else:  # from_stdin
        return sys.stdin.read()


@mail.command()
@click.argument("message_id")
@click.option("--all", "-a", "reply_all", is_flag=True, help="Reply to all recipients")
@click.option("--body", "-b", "body_text", default=None, help="Reply body (plain text)")
@click.option("--body-file", "-f", "body_file", default=None, help="Read body from file")
@click.option("--stdin", "from_stdin", is_flag=True, help="Read body from stdin")
@click.option("--dry-run", is_flag=True, help="Preview without sending")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def reply(
    message_id: str,
    reply_all: bool,
    body_text: str | None,
    body_file: str | None,
    from_stdin: bool,
    dry_run: bool,
    as_json: bool,
) -> None:
    """Reply to a message.

    Examples:

        desk mail reply MESSAGE_ID --body "Thanks for the update!"

        desk mail reply MESSAGE_ID --all --body "Sounds good to everyone"

        echo "Response" | desk mail reply MESSAGE_ID --stdin
    """
    body = _get_body(body_text, body_file, from_stdin)

    if dry_run:
        action = "reply-all" if reply_all else "reply"
        preview = {
            "dry_run": True,
            "action": action,
            "message_id": message_id,
            "body_preview": body[:200] + "..." if len(body) > 200 else body,
        }
        if as_json:
            print(json.dumps(preview, indent=2))
        else:
            console.print(f"[yellow]Would {action} to message {message_id}[/yellow]")
            console.print(f"  Body: {len(body)} characters")
        return

    client = _get_client()
    result = client.reply(message_id, body=body, reply_all=reply_all)

    if as_json:
        print(json.dumps(result, indent=2))
    else:
        action = "Replied to all" if reply_all else "Replied to"
        console.print(f"[green]{action} message[/green]")
        console.print(f"[dim]Message ID: {result.get('id', 'unknown')}[/dim]")


@mail.command()
@click.argument("message_id")
@click.option("--to", "-t", "to_addrs", multiple=True, required=True, help="Recipient (repeatable)")
@click.option("--body", "-b", "body_text", default=None, help="Additional message (plain text)")
@click.option("--body-file", "-f", "body_file", default=None, help="Read additional message from file")
@click.option("--stdin", "from_stdin", is_flag=True, help="Read additional message from stdin")
@click.option("--dry-run", is_flag=True, help="Preview without sending")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def forward(
    message_id: str,
    to_addrs: tuple[str, ...],
    body_text: str | None,
    body_file: str | None,
    from_stdin: bool,
    dry_run: bool,
    as_json: bool,
) -> None:
    """Forward a message.

    Examples:

        desk mail forward MESSAGE_ID --to "colleague@example.com"

        desk mail forward MESSAGE_ID --to "user@example.com" --body "FYI - see below"
    """
    body = _get_body(body_text, body_file, from_stdin, required=False)

    if dry_run:
        preview = {
            "dry_run": True,
            "action": "forward",
            "message_id": message_id,
            "to": list(to_addrs),
            "body_preview": body[:200] + "..." if body and len(body) > 200 else body,
        }
        if as_json:
            print(json.dumps(preview, indent=2))
        else:
            console.print(f"[yellow]Would forward message {message_id} to {', '.join(to_addrs)}[/yellow]")
            if body:
                console.print(f"  Additional note: {len(body)} characters")
        return

    client = _get_client()
    result = client.forward(message_id, to=list(to_addrs), body=body)

    if as_json:
        print(json.dumps(result, indent=2))
    else:
        console.print(f"[green]Forwarded message to {', '.join(to_addrs)}[/green]")
        console.print(f"[dim]Message ID: {result.get('id', 'unknown')}[/dim]")


# -----------------------------------------------------------------------------
# Drafts
# -----------------------------------------------------------------------------


@mail.command()
@click.option("--max", "-n", "max_results", default=20, help="Max results")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def drafts(max_results: int, as_json: bool) -> None:
    """List drafts.

    Examples:

        desk mail drafts

        desk mail drafts --json
    """
    client = _get_client()
    draft_list = client.list_drafts(max_results=max_results)

    if as_json:
        print(json.dumps(draft_list, indent=2))
        return

    if not draft_list:
        console.print("No drafts.")
        return

    table = Table(show_header=True)
    table.add_column("ID", style="dim", width=20)
    table.add_column("To", width=30)
    table.add_column("Subject", width=40)

    for d in draft_list:
        table.add_row(
            d["id"],
            d.get("to", "")[:30],
            d.get("subject", "")[:40],
        )

    console.print(table)


@mail.group()
def draft() -> None:
    """Draft operations — create, read, send, delete, update."""
    pass


@draft.command()
@click.option("--to", "-t", "to_addrs", multiple=True, required=True, help="Recipient (repeatable)")
@click.option("--cc", "cc_addrs", multiple=True, help="CC recipient (repeatable)")
@click.option("--bcc", "bcc_addrs", multiple=True, help="BCC recipient (repeatable)")
@click.option("--subject", "-s", required=True, help="Email subject")
@click.option("--body", "-b", "body_text", default=None, help="Email body (plain text)")
@click.option("--body-file", "-f", "body_file", default=None, help="Read body from file")
@click.option("--stdin", "from_stdin", is_flag=True, help="Read body from stdin")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def create(
    to_addrs: tuple[str, ...],
    cc_addrs: tuple[str, ...],
    bcc_addrs: tuple[str, ...],
    subject: str,
    body_text: str | None,
    body_file: str | None,
    from_stdin: bool,
    as_json: bool,
) -> None:
    """Create a draft.

    Examples:

        desk mail draft create --to "user@example.com" --subject "Proposal" --body "..."

        desk mail draft create --to "a@example.com" --subject "Report" --body-file report.txt
    """
    body = _get_body(body_text, body_file, from_stdin)

    client = _get_client()
    result = client.create_draft(
        to=list(to_addrs),
        subject=subject,
        body=body,
        cc=list(cc_addrs) if cc_addrs else None,
        bcc=list(bcc_addrs) if bcc_addrs else None,
    )

    if as_json:
        print(json.dumps(result, indent=2))
    else:
        console.print(f"[green]Created draft[/green]")
        console.print(f"[dim]Draft ID: {result.get('id', 'unknown')}[/dim]")


@draft.command("read")
@click.argument("draft_id")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def draft_read(draft_id: str, as_json: bool) -> None:
    """Read a draft by ID.

    Examples:

        desk mail draft read DRAFT_ID
    """
    client = _get_client()
    d = client.read_draft(draft_id)

    if as_json:
        print(json.dumps(d, indent=2))
        return

    console.print(f"[bold]Draft ID:[/bold] {d.get('draftId', '')}")
    console.print(f"[bold]To:[/bold] {d.get('to', '')}")
    if d.get("cc"):
        console.print(f"[bold]CC:[/bold] {d['cc']}")
    console.print(f"[bold]Subject:[/bold] {d.get('subject', '')}")
    console.print()
    console.print(d.get("body", "(no body)"))


@draft.command("send")
@click.argument("draft_id")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def draft_send(draft_id: str, as_json: bool) -> None:
    """Send a draft.

    Examples:

        desk mail draft send DRAFT_ID
    """
    client = _get_client()
    result = client.send_draft(draft_id)

    if as_json:
        print(json.dumps(result, indent=2))
    else:
        console.print(f"[green]Sent draft[/green]")
        console.print(f"[dim]Message ID: {result.get('id', 'unknown')}[/dim]")


@draft.command("delete")
@click.argument("draft_id")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def draft_delete(draft_id: str, as_json: bool) -> None:
    """Delete a draft.

    Examples:

        desk mail draft delete DRAFT_ID
    """
    client = _get_client()
    client.delete_draft(draft_id)

    if as_json:
        print(json.dumps({"action": "delete", "draftId": draft_id}))
    else:
        console.print(f"[green]Deleted draft {draft_id}[/green]")


@draft.command("update")
@click.argument("draft_id")
@click.option("--to", "-t", "to_addrs", multiple=True, help="New recipient (repeatable)")
@click.option("--cc", "cc_addrs", multiple=True, help="New CC recipient (repeatable)")
@click.option("--bcc", "bcc_addrs", multiple=True, help="New BCC recipient (repeatable)")
@click.option("--subject", "-s", default=None, help="New subject")
@click.option("--body", "-b", "body_text", default=None, help="New body (plain text)")
@click.option("--body-file", "-f", "body_file", default=None, help="Read new body from file")
@click.option("--stdin", "from_stdin", is_flag=True, help="Read new body from stdin")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def update(
    draft_id: str,
    to_addrs: tuple[str, ...],
    cc_addrs: tuple[str, ...],
    bcc_addrs: tuple[str, ...],
    subject: str | None,
    body_text: str | None,
    body_file: str | None,
    from_stdin: bool,
    as_json: bool,
) -> None:
    """Update a draft.

    Only specified fields are updated; others are preserved.

    Examples:

        desk mail draft update DRAFT_ID --subject "New subject"

        desk mail draft update DRAFT_ID --body "Updated content"
    """
    # Get body if any body option provided
    body = None
    if body_text is not None or body_file is not None or from_stdin:
        body = _get_body(body_text, body_file, from_stdin)

    client = _get_client()
    result = client.update_draft(
        draft_id,
        to=list(to_addrs) if to_addrs else None,
        subject=subject,
        body=body,
        cc=list(cc_addrs) if cc_addrs else None,
        bcc=list(bcc_addrs) if bcc_addrs else None,
    )

    if as_json:
        print(json.dumps(result, indent=2))
    else:
        console.print(f"[green]Updated draft[/green]")
        console.print(f"[dim]Draft ID: {result.get('id', 'unknown')}[/dim]")


# -----------------------------------------------------------------------------
# Attachments
# -----------------------------------------------------------------------------


@mail.command()
@click.argument("message_id")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def attachments(message_id: str, as_json: bool) -> None:
    """List attachments for a message.

    Examples:

        desk mail attachments MESSAGE_ID

        desk mail attachments MESSAGE_ID --json
    """
    client = _get_client()
    att_list = client.list_attachments(message_id)

    if as_json:
        print(json.dumps(att_list, indent=2))
        return

    if not att_list:
        console.print("No attachments.")
        return

    table = Table(show_header=True)
    table.add_column("Filename", width=40)
    table.add_column("Type", width=25)
    table.add_column("Size", width=10, justify="right")

    for att in att_list:
        size = att.get("size", 0)
        if size > 1024 * 1024:
            size_str = f"{size / (1024 * 1024):.1f} MB"
        elif size > 1024:
            size_str = f"{size / 1024:.1f} KB"
        else:
            size_str = f"{size} B"
        table.add_row(
            att.get("filename", ""),
            att.get("mimeType", ""),
            size_str,
        )

    console.print(table)


@mail.command()
@click.argument("message_id")
@click.argument("filename")
@click.option("--output", "-o", "output_path", default=None, help="Save to file instead of stdout")
def attachment(message_id: str, filename: str, output_path: str | None) -> None:
    """Download a single attachment.

    Without --output, writes binary data to stdout (for piping).
    With --output, saves to the specified file.

    Examples:

        desk mail attachment MESSAGE_ID "report.pdf" --output report.pdf

        desk mail attachment MESSAGE_ID "data.csv" | head -5

        desk mail attachment MESSAGE_ID "image.png" | base64
    """
    client = _get_client()

    try:
        data = client.get_attachment_by_filename(message_id, filename)
    except ValueError as e:
        console.print(f"[red]Error: {e}[/red]")
        sys.exit(1)

    if output_path:
        try:
            with open(output_path, "wb") as f:
                f.write(data)
            console.print(f"[green]Saved {filename} to {output_path}[/green]")
            console.print(f"[dim]{len(data)} bytes[/dim]")
        except OSError as e:
            console.print(f"[red]Error writing file: {e}[/red]")
            sys.exit(1)
    else:
        # Write to stdout as binary
        sys.stdout.buffer.write(data)


@mail.command("download-attachments")
@click.argument("message_id")
@click.option("--output-dir", "-o", "output_dir", default=".", help="Directory to save files")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def download_attachments(message_id: str, output_dir: str, as_json: bool) -> None:
    """Download all attachments from a message.

    Examples:

        desk mail download-attachments MESSAGE_ID

        desk mail download-attachments MESSAGE_ID --output-dir ./downloads/
    """
    import os

    client = _get_client()
    att_list = client.list_attachments(message_id)

    if not att_list:
        if as_json:
            print(json.dumps({"downloaded": [], "count": 0}))
        else:
            console.print("No attachments to download.")
        return

    # Ensure output directory exists
    os.makedirs(output_dir, exist_ok=True)

    downloaded = []
    for att in att_list:
        filename = att["filename"]
        attachment_id = att["attachmentId"]

        # Handle filename collisions
        output_path = os.path.join(output_dir, filename)
        counter = 1
        base, ext = os.path.splitext(filename)
        while os.path.exists(output_path):
            output_path = os.path.join(output_dir, f"{base}_{counter}{ext}")
            counter += 1

        data = client.get_attachment(message_id, attachment_id)
        with open(output_path, "wb") as f:
            f.write(data)

        downloaded.append({
            "filename": filename,
            "path": output_path,
            "size": len(data),
        })

    if as_json:
        print(json.dumps({"downloaded": downloaded, "count": len(downloaded)}))
    else:
        console.print(f"[green]Downloaded {len(downloaded)} attachment(s)[/green]")
        for d in downloaded:
            console.print(f"  {d['path']} ({d['size']} bytes)")


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
@click.option("--dry-run", is_flag=True, help="Preview without executing")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def label(label_name: str, message_ids: tuple[str, ...], stdin: bool, dry_run: bool, as_json: bool) -> None:
    """Add a label to messages.

    Examples:

        desk mail label Work ID1 ID2 ID3

        desk mail search "from:boss" --json | jq -r '.[].id' | desk mail label Important --stdin
    """
    ids = _collect_ids(message_ids, stdin)
    if not ids:
        console.print("[yellow]No message IDs provided.[/yellow]")
        return

    if dry_run:
        if as_json:
            print(json.dumps({"dry_run": True, "action": "label", "label": label_name, "count": len(ids), "ids": ids}))
        else:
            console.print(f"[yellow]Would add label '{label_name}' to {len(ids)} message(s)[/yellow]")
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
@click.option("--dry-run", is_flag=True, help="Preview without executing")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def archive(message_ids: tuple[str, ...], stdin: bool, dry_run: bool, as_json: bool) -> None:
    """Archive messages (remove from inbox).

    Examples:

        desk mail archive ID1 ID2 ID3

        desk mail search "from:bot" --json | jq -r '.[].id' | desk mail archive --stdin
    """
    ids = _collect_ids(message_ids, stdin)
    if not ids:
        console.print("[yellow]No message IDs provided.[/yellow]")
        return

    if dry_run:
        if as_json:
            print(json.dumps({"dry_run": True, "action": "archive", "count": len(ids), "ids": ids}))
        else:
            console.print(f"[yellow]Would archive {len(ids)} message(s)[/yellow]")
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
@click.option("--dry-run", is_flag=True, help="Preview without executing")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def mark_read(message_ids: tuple[str, ...], stdin: bool, dry_run: bool, as_json: bool) -> None:
    """Mark messages as read.

    Examples:

        desk mail mark-read ID1 ID2 ID3
    """
    ids = _collect_ids(message_ids, stdin)
    if not ids:
        console.print("[yellow]No message IDs provided.[/yellow]")
        return

    if dry_run:
        if as_json:
            print(json.dumps({"dry_run": True, "action": "mark-read", "count": len(ids), "ids": ids}))
        else:
            console.print(f"[yellow]Would mark {len(ids)} message(s) as read[/yellow]")
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
@click.option("--dry-run", is_flag=True, help="Preview without executing")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def mark_unread(message_ids: tuple[str, ...], stdin: bool, dry_run: bool, as_json: bool) -> None:
    """Mark messages as unread.

    Examples:

        desk mail mark-unread ID1 ID2 ID3
    """
    ids = _collect_ids(message_ids, stdin)
    if not ids:
        console.print("[yellow]No message IDs provided.[/yellow]")
        return

    if dry_run:
        if as_json:
            print(json.dumps({"dry_run": True, "action": "mark-unread", "count": len(ids), "ids": ids}))
        else:
            console.print(f"[yellow]Would mark {len(ids)} message(s) as unread[/yellow]")
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
@click.option("--dry-run", is_flag=True, help="Preview without executing")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def trash(message_ids: tuple[str, ...], stdin: bool, dry_run: bool, as_json: bool) -> None:
    """Move messages to trash.

    Examples:

        desk mail trash ID1 ID2 ID3
    """
    ids = _collect_ids(message_ids, stdin)
    if not ids:
        console.print("[yellow]No message IDs provided.[/yellow]")
        return

    if dry_run:
        if as_json:
            print(json.dumps({"dry_run": True, "action": "trash", "count": len(ids), "ids": ids}))
        else:
            console.print(f"[yellow]Would move {len(ids)} message(s) to trash[/yellow]")
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
@click.option("--dry-run", is_flag=True, help="Preview without executing")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def star(message_ids: tuple[str, ...], stdin: bool, dry_run: bool, as_json: bool) -> None:
    """Star messages.

    Examples:

        desk mail star ID1 ID2 ID3
    """
    ids = _collect_ids(message_ids, stdin)
    if not ids:
        console.print("[yellow]No message IDs provided.[/yellow]")
        return

    if dry_run:
        if as_json:
            print(json.dumps({"dry_run": True, "action": "star", "count": len(ids), "ids": ids}))
        else:
            console.print(f"[yellow]Would star {len(ids)} message(s)[/yellow]")
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
@click.option("--dry-run", is_flag=True, help="Preview without executing")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def unstar(message_ids: tuple[str, ...], stdin: bool, dry_run: bool, as_json: bool) -> None:
    """Remove star from messages.

    Examples:

        desk mail unstar ID1 ID2 ID3
    """
    ids = _collect_ids(message_ids, stdin)
    if not ids:
        console.print("[yellow]No message IDs provided.[/yellow]")
        return

    if dry_run:
        if as_json:
            print(json.dumps({"dry_run": True, "action": "unstar", "count": len(ids), "ids": ids}))
        else:
            console.print(f"[yellow]Would unstar {len(ids)} message(s)[/yellow]")
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
@click.option("--dry-run", is_flag=True, help="Preview without executing")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def remove_label(label_name: str, message_ids: tuple[str, ...], stdin: bool, dry_run: bool, as_json: bool) -> None:
    """Remove a label from messages.

    Examples:

        desk mail remove-label Work ID1 ID2 ID3
    """
    ids = _collect_ids(message_ids, stdin)
    if not ids:
        console.print("[yellow]No message IDs provided.[/yellow]")
        return

    if dry_run:
        if as_json:
            print(json.dumps({"dry_run": True, "action": "remove-label", "label": label_name, "count": len(ids), "ids": ids}))
        else:
            console.print(f"[yellow]Would remove label '{label_name}' from {len(ids)} message(s)[/yellow]")
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
@click.option("--dry-run", is_flag=True, help="Preview without executing")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def modify(
    message_ids: tuple[str, ...],
    add_labels: tuple[str],
    remove_labels: tuple[str],
    stdin: bool,
    dry_run: bool,
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

    changes = []
    if add_labels:
        changes.append(f"+{', +'.join(add_labels)}")
    if remove_labels:
        changes.append(f"-{', -'.join(remove_labels)}")

    if dry_run:
        if as_json:
            print(json.dumps({"dry_run": True, "action": "modify", "changes": changes, "count": len(ids), "ids": ids}))
        else:
            console.print(f"[yellow]Would modify {len(ids)} message(s): {' '.join(changes)}[/yellow]")
        return

    client = _get_client()
    client.batch_modify(
        ids,
        add_labels=list(add_labels) if add_labels else None,
        remove_labels=list(remove_labels) if remove_labels else None,
    )

    if as_json:
        print(json.dumps({"action": "modify", "changes": changes, "count": len(ids), "ids": ids}))
    else:
        console.print(f"[green]Modified {len(ids)} message(s): {' '.join(changes)}[/green]")
