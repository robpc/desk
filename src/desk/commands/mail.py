"""Mail commands — Gmail operations."""

import json
import sys
import time

import click
from rich.console import Console
from rich.markup import escape
from rich.table import Table

from desk.agent import (
    ERROR_SUGGESTIONS,
    ErrorCode,
    dry_run_preview,
    get_undo_info,
    operation_receipt,
    output_result,
    parse_api_error,
    structured_error,
)
from desk.auth import get_credentials, get_last_auth_failure
from desk.idempotency import check_idempotency, record_idempotency
from desk.links import filter_links_not_in_text
from desk.services.gmail import GmailClient

console = Console()

# Max IDs per Gmail batchModify call
_BATCH_MODIFY_CHUNK = 1000


def _get_client(as_json: bool = False) -> GmailClient:
    """Get authenticated Gmail client or exit."""
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


def _get_message_summaries(client: GmailClient, ids: list[str], max_fetch: int = 10) -> list[dict]:
    """Fetch basic message info for receipts/previews.

    For large batches, only fetches first max_fetch items to avoid slowdown.
    Uses batch metadata fetch (1 API call) instead of sequential full reads.
    Returns list of dicts with id, subject, from, date.
    """
    fetch_ids = ids[:max_fetch]
    summaries = []

    if fetch_ids:
        requests = [
            (
                msg_id,
                client.service.users()
                .messages()
                .get(
                    userId=client.user_id,
                    id=msg_id,
                    format="metadata",
                    metadataHeaders=["From", "Subject", "Date"],
                ),
            )
            for msg_id in fetch_ids
        ]
        try:
            batch_results = client._batch_get(requests)
        except RuntimeError:
            batch_results = {}

        # Build summaries preserving order
        for msg_id in fetch_ids:
            if msg_id in batch_results:
                parsed = client._parse_message_metadata(batch_results[msg_id])
                summaries.append({
                    "id": msg_id,
                    "subject": parsed.get("subject", "(no subject)"),
                    "from": parsed.get("from", "unknown"),
                    "date": parsed.get("date", ""),
                })
            else:
                summaries.append({"id": msg_id})

    # For remaining items, just include IDs
    for msg_id in ids[max_fetch:]:
        summaries.append({"id": msg_id})

    return summaries


def _handle_api_error(e: Exception, as_json: bool, context: dict | None = None) -> None:
    """Handle API errors with structured output when --json is used.

    Args:
        e: The exception that occurred
        as_json: Whether to output structured JSON
        context: Additional context about the operation
    """
    raw_error = str(e)
    # Parse to get human-readable message
    error_msg = parse_api_error(raw_error)

    # Determine error code based on error message
    if "not found" in raw_error.lower() or "404" in raw_error:
        code = ErrorCode.MESSAGE_NOT_FOUND
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

    # Get suggestions for this error code
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


def _print_links_section(message: dict) -> None:
    """Print a Links section for URLs hidden from the plain text body.

    Only prints links whose URL doesn't already appear in the plain text,
    so users/agents aren't shown redundant information.
    """
    all_links = message.get("links", [])
    if not all_links:
        return

    hidden = filter_links_not_in_text(all_links, message.get("body", ""))
    if not hidden:
        return

    console.print()
    console.print("[bold]Links:[/bold]")
    for link in hidden:
        text = link.get("text", "")
        if text:
            console.print(f"  {text}")
        console.print(f"    {link['url']}")
        if link.get("readable_via"):
            console.print(f"    [dim]→ {link['readable_via']}[/dim]")


def _query_bulk_operate(
    client: GmailClient,
    query: str,
    operation: str,
    add_labels: list[str] | None = None,
    remove_labels: list[str] | None = None,
    dry_run: bool = False,
    quiet: bool = False,
    as_json: bool = False,
) -> None:
    """Execute a bulk operation on all messages matching a query.

    Paginates through all matching messages and calls batchModify in chunks
    of 1000. Emits per-batch JSON receipts when --json is used.

    Args:
        client: Authenticated Gmail client
        query: Gmail search query
        operation: Operation name (e.g., "archive", "mark-read")
        add_labels: Labels to add
        remove_labels: Labels to remove
        dry_run: If True, show count and exit without executing
        quiet: Suppress human-readable output
        as_json: Output structured JSON
    """
    if dry_run:
        count = client.count_messages(query)
        if as_json:
            preview = dry_run_preview(
                operation=operation,
                targets=[{"query": query, "estimated_count": count}],
                reversible=True,
                undo_command=None,
            )
            print(json.dumps(preview, indent=2))
        elif not quiet:
            console.print(f"[yellow]Query '{query}' matches ~{count} message(s)[/yellow]")
            console.print(
                f"[dim]Use --yes to execute: desk mail {operation} --query '{query}' --yes[/dim]"
            )
        return

    # Fetch all matching IDs
    start_time = time.monotonic()
    all_ids = client.search_all_ids(query)
    total = len(all_ids)

    if total == 0:
        if as_json:
            print(json.dumps({
                "success": True,
                "operation": operation,
                "query": query,
                "total_processed": 0,
                "message": "No messages matched query",
            }, indent=2))
        elif not quiet:
            console.print(f"[yellow]No messages match query: {query}[/yellow]")
        return

    # Process in chunks of 1000
    total_processed = 0
    total_failed = 0
    batch_num = 0

    for i in range(0, total, _BATCH_MODIFY_CHUNK):
        chunk = all_ids[i : i + _BATCH_MODIFY_CHUNK]
        batch_num += 1

        try:
            client.batch_modify(chunk, add_labels=add_labels, remove_labels=remove_labels)
            total_processed += len(chunk)
        except Exception as e:
            total_failed += len(chunk)
            if as_json:
                print(json.dumps({
                    "batch": batch_num,
                    "error": str(e),
                    "failed_count": len(chunk),
                    "total_so_far": total_processed,
                }, indent=2), flush=True)
                continue
            else:
                ctx = {"operation": operation, "query": query, "batch": batch_num}
                _handle_api_error(e, as_json, ctx)

        if as_json:
            print(json.dumps({
                "batch": batch_num,
                "processed": len(chunk),
                "total_so_far": total_processed,
                "failed": 0,
            }, indent=2), flush=True)

    elapsed_ms = int((time.monotonic() - start_time) * 1000)

    if as_json:
        print(json.dumps({
            "complete": True,
            "operation": operation,
            "query": query,
            "total_processed": total_processed,
            "total_failed": total_failed,
            "elapsed_ms": elapsed_ms,
        }, indent=2))
    elif not quiet:
        console.print(
            f"[green]{operation}: processed {total_processed} message(s) matching '{query}'[/green]"
        )
        if total_failed:
            console.print(f"[red]Failed: {total_failed}[/red]")


def _resolve_query_or_ids(
    message_ids: tuple[str, ...],
    stdin: bool,
    query: str | None,
    yes: bool,
    operation: str,
    as_json: bool,
) -> tuple[list[str] | None, str | None]:
    """Resolve message IDs from arguments/stdin, or validate --query + --yes.

    Returns:
        (ids, query) — one will be set, the other None.
        If --query is used without --yes (and not dry-run), exits with error.
    """
    if query and message_ids:
        msg = "--query and message IDs are mutually exclusive"
        if as_json:
            print(json.dumps(structured_error(ErrorCode.INVALID_INPUT, msg), indent=2))
        else:
            console.print(f"[red]Error: {msg}[/red]")
        sys.exit(1)

    if query and stdin:
        msg = "--query and --stdin are mutually exclusive"
        if as_json:
            print(json.dumps(structured_error(ErrorCode.INVALID_INPUT, msg), indent=2))
        else:
            console.print(f"[red]Error: {msg}[/red]")
        sys.exit(1)

    if query:
        if not yes:
            # Check count and tell the user to add --yes
            creds = get_credentials()
            if not creds:
                console.print("[red]Not authenticated.[/red]")
                sys.exit(1)
            client = GmailClient(creds)
            count = client.count_messages(query)
            msg = (
                f"Query '{query}' matches ~{count} message(s). "
                f"Add --yes to execute: desk mail {operation} --query '{query}' --yes"
            )
            if as_json:
                print(json.dumps(structured_error(
                    ErrorCode.INVALID_INPUT,
                    msg,
                    suggestions=[f"Add --yes flag: desk mail {operation} --query '{query}' --yes"],
                ), indent=2))
            else:
                console.print(f"[yellow]{msg}[/yellow]")
            sys.exit(1)
        return None, query

    ids = _collect_ids(message_ids, stdin)
    return ids, None


@click.group()
def mail() -> None:
    """Gmail — search, read, label, archive."""
    pass


@mail.command()
@click.argument("query")
@click.option("--max", "-n", "max_results", default=20, help="Max results")
@click.option("--limit", "limit", default=None, type=int, help="Max results (alias for --max)")
@click.option("--page-token", "page_token", default=None, help="Continue from previous page")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def search(query: str, max_results: int, limit: int | None, page_token: str | None, as_json: bool) -> None:
    """Search for messages.

    Uses Gmail search syntax (same as Gmail search box).

    Examples:

        desk mail search "from:boss is:unread"

        desk mail search "after:2024/01/01 has:attachment"

        desk mail search "is:unread" --json | jq '.nextPageToken'
    """
    # --limit takes precedence if provided
    if limit is not None:
        max_results = limit

    client = _get_client()
    result = client.search(query, max_results=max_results, page_token=page_token)

    if as_json:
        print(json.dumps(result, indent=2))
        return

    messages = result.get("messages", [])
    if not messages:
        console.print("No messages found.")
        return

    table = Table(show_header=True, expand=True)
    table.add_column("ID", style="dim", min_width=16, no_wrap=True)
    table.add_column("From", min_width=20, ratio=1, no_wrap=True)
    table.add_column("Subject", min_width=30, ratio=2)
    table.add_column("Date", min_width=20, no_wrap=True)

    for msg in messages:
        table.add_row(
            msg["id"],
            msg["from"],
            msg["subject"],
            msg["date"],
        )

    console.print(table)

    if result.get("nextPageToken"):
        console.print(f"\n[dim]More results available. Use --page-token {result['nextPageToken']}[/dim]")


# -----------------------------------------------------------------------------
# Threads
# -----------------------------------------------------------------------------


@mail.command()
@click.argument("query")
@click.option("--max", "-n", "max_results", default=20, help="Max results")
@click.option("--limit", "limit", default=None, type=int, help="Max results (alias for --max)")
@click.option("--page-token", "page_token", default=None, help="Continue from previous page")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def threads(query: str, max_results: int, limit: int | None, page_token: str | None, as_json: bool) -> None:
    """Search for threads (conversations).

    Like search, but groups messages by conversation.

    Examples:

        desk mail threads "from:boss"

        desk mail threads "subject:project update" --json
    """
    # --limit takes precedence if provided
    if limit is not None:
        max_results = limit

    client = _get_client()
    result = client.search_threads(query, max_results=max_results, page_token=page_token)

    if as_json:
        print(json.dumps(result, indent=2))
        return

    thread_list = result.get("threads", [])
    if not thread_list:
        console.print("No threads found.")
        return

    table = Table(show_header=True)
    table.add_column("Thread ID", style="dim", width=16)
    table.add_column("From", width=25)
    table.add_column("Subject", width=35)
    table.add_column("Msgs", width=4, justify="right")
    table.add_column("Date", width=18)

    for t in thread_list:
        table.add_row(
            t["id"],
            t.get("from", "")[:25],
            t.get("subject", "")[:35],
            str(t.get("messageCount", 0)),
            t.get("date", "")[:18],
        )

    console.print(table)

    if result.get("nextPageToken"):
        console.print(f"\n[dim]More results available. Use --page-token {result['nextPageToken']}[/dim]")


@mail.command()
@click.argument("thread_id")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def thread(thread_id: str, as_json: bool) -> None:
    """Read an entire thread (conversation).

    Shows all messages in the thread in chronological order.

    Examples:

        desk mail thread THREAD_ID
    """
    client = _get_client()
    t = client.get_thread(thread_id)

    if as_json:
        print(json.dumps(t, indent=2))
        return

    console.print(f"[bold]Thread: {t['id']}[/bold] ({t['messageCount']} messages)")
    console.print()

    for i, msg in enumerate(t["messages"], 1):
        console.print(f"[bold cyan]--- Message {i}/{t['messageCount']} ---[/bold cyan]")
        console.print(f"[bold]From:[/bold] {msg.get('from', '')}")
        console.print(f"[bold]Date:[/bold] {msg.get('date', '')}")
        console.print(f"[bold]Subject:[/bold] {msg.get('subject', '')}")
        console.print()
        console.print(msg.get("body", "(no body)"))
        _print_links_section(msg)
        console.print()


@mail.command("thread-archive")
@click.argument("thread_id")
@click.option("--dry-run", is_flag=True, help="Preview without executing")
@click.option("--quiet", "-q", is_flag=True, help="Suppress success messages")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def thread_archive(thread_id: str, dry_run: bool, quiet: bool, as_json: bool) -> None:
    """Archive an entire thread (remove from inbox).

    Examples:

        desk mail thread-archive THREAD_ID
    """
    if dry_run:
        if as_json:
            print(json.dumps({"dry_run": True, "action": "thread-archive", "threadId": thread_id}))
        elif not quiet:
            console.print(f"[yellow]Would archive thread {thread_id}[/yellow]")
        return

    client = _get_client()
    client.modify_thread(thread_id, remove_labels=["INBOX"])

    if as_json:
        print(json.dumps({"action": "thread-archive", "threadId": thread_id}))
    elif not quiet:
        console.print(f"[green]Archived thread {thread_id}[/green]")


@mail.command("thread-label")
@click.argument("label_name")
@click.argument("thread_id")
@click.option("--dry-run", is_flag=True, help="Preview without executing")
@click.option("--quiet", "-q", is_flag=True, help="Suppress success messages")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def thread_label(label_name: str, thread_id: str, dry_run: bool, quiet: bool, as_json: bool) -> None:
    """Add a label to an entire thread.

    Examples:

        desk mail thread-label Work THREAD_ID
    """
    if dry_run:
        if as_json:
            print(json.dumps({"dry_run": True, "action": "thread-label", "label": label_name, "threadId": thread_id}))
        elif not quiet:
            console.print(f"[yellow]Would add label '{label_name}' to thread {thread_id}[/yellow]")
        return

    client = _get_client()
    client.modify_thread(thread_id, add_labels=[label_name])

    if as_json:
        print(json.dumps({"action": "thread-label", "label": label_name, "threadId": thread_id}))
    elif not quiet:
        console.print(f"[green]Added label '{label_name}' to thread {thread_id}[/green]")


@mail.command("thread-trash")
@click.argument("thread_id")
@click.option("--dry-run", is_flag=True, help="Preview without executing")
@click.option("--quiet", "-q", is_flag=True, help="Suppress success messages")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def thread_trash(thread_id: str, dry_run: bool, quiet: bool, as_json: bool) -> None:
    """Move an entire thread to trash.

    Examples:

        desk mail thread-trash THREAD_ID
    """
    if dry_run:
        if as_json:
            print(json.dumps({"dry_run": True, "action": "thread-trash", "threadId": thread_id}))
        elif not quiet:
            console.print(f"[yellow]Would move thread {thread_id} to trash[/yellow]")
        return

    client = _get_client()
    client.modify_thread(thread_id, add_labels=["TRASH"], remove_labels=["INBOX"])

    if as_json:
        print(json.dumps({"action": "thread-trash", "threadId": thread_id}))
    elif not quiet:
        console.print(f"[green]Moved thread {thread_id} to trash[/green]")


@mail.command()
@click.argument("message_id")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def read(message_id: str, as_json: bool) -> None:
    """Read a message by ID."""
    client = _get_client(as_json)
    try:
        message = client.read(message_id)
    except Exception as e:
        _handle_api_error(e, as_json, {"operation": "read", "message_id": message_id})

    if as_json:
        print(json.dumps(message, indent=2))
        return

    console.print(f"[bold]From:[/bold] {message['from']}")
    console.print(f"[bold]Subject:[/bold] {message['subject']}")
    console.print(f"[bold]Date:[/bold] {message['date']}")
    console.print()
    console.print(message.get("body", "(no body)"))
    _print_links_section(message)


@mail.command()
@click.option("--to", "-t", "to_addrs", multiple=True, required=True, help="Recipient (repeatable)")
@click.option("--cc", "cc_addrs", multiple=True, help="CC recipient (repeatable)")
@click.option("--bcc", "bcc_addrs", multiple=True, help="BCC recipient (repeatable)")
@click.option("--subject", "-s", required=True, help="Email subject")
@click.option("--body", "-b", "body_text", default=None, help="Email body (plain text)")
@click.option("--body-file", "-f", "body_file", default=None, help="Read body from file")
@click.option("--stdin", "from_stdin", is_flag=True, help="Read body from stdin")
@click.option("--html", "is_html", is_flag=True, help="Treat body as HTML")
@click.option("--from", "from_addr", default=None, help="Send from alias (use 'desk mail aliases')")
@click.option("--idempotency-key", "idempotency_key", default=None, help="Key for safe retries (prevents duplicate sends)")
@click.option("--dry-run", is_flag=True, help="Preview without sending")
@click.option("--quiet", "-q", is_flag=True, help="Suppress success messages")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def send(
    to_addrs: tuple[str, ...],
    cc_addrs: tuple[str, ...],
    bcc_addrs: tuple[str, ...],
    subject: str,
    body_text: str | None,
    body_file: str | None,
    from_stdin: bool,
    is_html: bool,
    from_addr: str | None,
    idempotency_key: str | None,
    dry_run: bool,
    quiet: bool,
    as_json: bool,
) -> None:
    """Send an email.

    Body can be provided via --body, --body-file, or --stdin.

    Use --idempotency-key for safe retries (agents). If a send with the same key
    was already performed, returns the cached result instead of sending again.

    Examples:

        desk mail send --to "user@example.com" --subject "Hello" --body "Message"

        desk mail send --to "a@example.com" --cc "b@example.com" --subject "Update" --body "..."

        echo "Report content" | desk mail send --to "boss@example.com" --subject "Report" --stdin

        desk mail send --to "user@example.com" --subject "Notes" --body-file notes.txt

        # Safe retry with idempotency key
        desk mail send --to "user@example.com" --subject "Report" --body "..." --idempotency-key "task-123"
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
        targets = [{
            "to": list(to_addrs),
            "cc": list(cc_addrs) if cc_addrs else [],
            "bcc": list(bcc_addrs) if bcc_addrs else [],
            "subject": subject,
            "body_length": len(body),
            "body_preview": body[:100] + "..." if len(body) > 100 else body,
        }]
        if as_json:
            preview = dry_run_preview(
                operation="send",
                targets=targets,
                reversible=False,
                undo_command=None,
                warnings=["This action cannot be undone - email will be sent immediately"],
            )
            print(json.dumps(preview, indent=2))
        elif not quiet:
            console.print(f"[yellow]Would send message:[/yellow]")
            console.print(f"  To: {', '.join(to_addrs)}")
            if cc_addrs:
                console.print(f"  CC: {', '.join(cc_addrs)}")
            if bcc_addrs:
                console.print(f"  BCC: {', '.join(bcc_addrs)}")
            console.print(f"  Subject: {subject}")
            console.print(f"  Body: {len(body)} characters")
            console.print(f"\n[yellow]Warning: This action cannot be undone[/yellow]")
        return

    # Check idempotency key before sending
    if idempotency_key:
        cached = check_idempotency(idempotency_key)
        if cached:
            if as_json:
                receipt = cached["result"]
                receipt["idempotency"] = {
                    "key": idempotency_key,
                    "status": "cached",
                    "original_timestamp": cached["original_timestamp"],
                    "note": "Operation was already executed; returning cached result",
                }
                print(json.dumps(receipt, indent=2))
            elif not quiet:
                console.print(f"[yellow]Already sent (cached from {cached['original_timestamp']})[/yellow]")
                console.print(f"[dim]Message ID: {cached['result'].get('targets', [{}])[0].get('id', 'unknown')}[/dim]")
            return

    client = _get_client(as_json)
    result = client.send(
        to=list(to_addrs),
        subject=subject,
        body=body,
        cc=list(cc_addrs) if cc_addrs else None,
        bcc=list(bcc_addrs) if bcc_addrs else None,
        html=is_html,
        from_addr=from_addr,
    )

    receipt = operation_receipt(
        operation="send",
        target={
            "id": result.get("id", "unknown"),
            "thread_id": result.get("threadId", "unknown"),
            "to": list(to_addrs),
            "subject": subject,
        },
        undo_command=None,
        undo_expires=None,
    )

    # Record for idempotency if key provided
    if idempotency_key:
        record_idempotency(idempotency_key, "mail.send", receipt)
        receipt["idempotency"] = {
            "key": idempotency_key,
            "status": "executed",
        }

    if as_json:
        print(json.dumps(receipt, indent=2))
    elif not quiet:
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
@click.option("--html", "is_html", is_flag=True, help="Treat body as HTML")
@click.option("--from", "from_addr", default=None, help="Reply from alias (auto-detected if omitted)")
@click.option("--dry-run", is_flag=True, help="Preview without sending")
@click.option("--quiet", "-q", is_flag=True, help="Suppress success messages")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def reply(
    message_id: str,
    reply_all: bool,
    body_text: str | None,
    body_file: str | None,
    from_stdin: bool,
    is_html: bool,
    from_addr: str | None,
    dry_run: bool,
    quiet: bool,
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
        elif not quiet:
            console.print(f"[yellow]Would {action} to message {message_id}[/yellow]")
            console.print(f"  Body: {len(body)} characters")
        return

    client = _get_client()
    result = client.reply(
        message_id, body=body, reply_all=reply_all, html=is_html,
        from_addr=from_addr,
    )

    if as_json:
        print(json.dumps(result, indent=2))
    elif not quiet:
        action = "Replied to all" if reply_all else "Replied to"
        console.print(f"[green]{action} message[/green]")
        console.print(f"[dim]Message ID: {result.get('id', 'unknown')}[/dim]")


@mail.command()
@click.argument("message_id")
@click.option("--to", "-t", "to_addrs", multiple=True, required=True, help="Recipient (repeatable)")
@click.option("--body", "-b", "body_text", default=None, help="Additional message (plain text)")
@click.option("--body-file", "-f", "body_file", default=None, help="Read additional message from file")
@click.option("--stdin", "from_stdin", is_flag=True, help="Read additional message from stdin")
@click.option("--html", "is_html", is_flag=True, help="Treat body as HTML")
@click.option("--from", "from_addr", default=None, help="Forward from alias")
@click.option("--dry-run", is_flag=True, help="Preview without sending")
@click.option("--quiet", "-q", is_flag=True, help="Suppress success messages")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def forward(
    message_id: str,
    to_addrs: tuple[str, ...],
    body_text: str | None,
    body_file: str | None,
    from_stdin: bool,
    is_html: bool,
    from_addr: str | None,
    dry_run: bool,
    quiet: bool,
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
        elif not quiet:
            console.print(f"[yellow]Would forward message {message_id} to {', '.join(to_addrs)}[/yellow]")
            if body:
                console.print(f"  Additional note: {len(body)} characters")
        return

    client = _get_client()
    result = client.forward(
        message_id, to=list(to_addrs), body=body, html=is_html,
        from_addr=from_addr,
    )

    if as_json:
        print(json.dumps(result, indent=2))
    elif not quiet:
        console.print(f"[green]Forwarded message to {', '.join(to_addrs)}[/green]")
        console.print(f"[dim]Message ID: {result.get('id', 'unknown')}[/dim]")


@mail.command()
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def aliases(as_json: bool) -> None:
    """List send-as aliases.

    Shows email addresses you can send from. Use the address with
    --from on send, reply, and forward commands.

    Examples:

        desk mail aliases

        desk mail aliases --json
    """
    client = _get_client(as_json)
    try:
        alias_list = client.list_send_as_aliases()
    except Exception as e:
        _handle_api_error(e, as_json, {"operation": "list-aliases"})

    if as_json:
        print(json.dumps(alias_list, indent=2))
        return

    if not alias_list:
        console.print("No send-as aliases configured.")
        return

    table = Table(show_header=True)
    table.add_column("Email", no_wrap=True)
    table.add_column("Name")
    table.add_column("Default", width=8)
    table.add_column("Status")

    for a in alias_list:
        default = "yes" if a.get("isDefault") else ""
        status = a.get("verificationStatus", "")
        table.add_row(
            a.get("sendAsEmail", ""),
            a.get("displayName", ""),
            default,
            status,
        )

    console.print(table)


# -----------------------------------------------------------------------------
# Drafts
# -----------------------------------------------------------------------------


@mail.command()
@click.option("--max", "-n", "max_results", default=20, help="Max results")
@click.option("--limit", "limit", default=None, type=int, help="Max results (alias for --max)")
@click.option("--page-token", "page_token", default=None, help="Continue from previous page")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def drafts(max_results: int, limit: int | None, page_token: str | None, as_json: bool) -> None:
    """List drafts.

    Examples:

        desk mail drafts

        desk mail drafts --json
    """
    # --limit takes precedence if provided
    if limit is not None:
        max_results = limit

    client = _get_client()
    result = client.list_drafts(max_results=max_results, page_token=page_token)

    if as_json:
        print(json.dumps(result, indent=2))
        return

    draft_list = result.get("drafts", [])
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

    if result.get("nextPageToken"):
        console.print(f"\n[dim]More results available. Use --page-token {result['nextPageToken']}[/dim]")


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
@click.option("--html", "is_html", is_flag=True, help="Treat body as HTML")
@click.option("--quiet", "-q", is_flag=True, help="Suppress success messages")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def create(
    to_addrs: tuple[str, ...],
    cc_addrs: tuple[str, ...],
    bcc_addrs: tuple[str, ...],
    subject: str,
    body_text: str | None,
    body_file: str | None,
    from_stdin: bool,
    is_html: bool,
    quiet: bool,
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
        html=is_html,
    )

    if as_json:
        print(json.dumps(result, indent=2))
    elif not quiet:
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
    _print_links_section(d)


@draft.command("send")
@click.argument("draft_id")
@click.option("--quiet", "-q", is_flag=True, help="Suppress success messages")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def draft_send(draft_id: str, quiet: bool, as_json: bool) -> None:
    """Send a draft.

    Examples:

        desk mail draft send DRAFT_ID
    """
    client = _get_client()
    result = client.send_draft(draft_id)

    if as_json:
        print(json.dumps(result, indent=2))
    elif not quiet:
        console.print(f"[green]Sent draft[/green]")
        console.print(f"[dim]Message ID: {result.get('id', 'unknown')}[/dim]")


@draft.command("delete")
@click.argument("draft_id")
@click.option("--quiet", "-q", is_flag=True, help="Suppress success messages")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def draft_delete(draft_id: str, quiet: bool, as_json: bool) -> None:
    """Delete a draft.

    Examples:

        desk mail draft delete DRAFT_ID
    """
    client = _get_client()
    client.delete_draft(draft_id)

    if as_json:
        print(json.dumps({"action": "delete", "draftId": draft_id}))
    elif not quiet:
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
@click.option("--html", "is_html", is_flag=True, help="Treat body as HTML")
@click.option("--quiet", "-q", is_flag=True, help="Suppress success messages")
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
    is_html: bool,
    quiet: bool,
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
        html=is_html,
    )

    if as_json:
        print(json.dumps(result, indent=2))
    elif not quiet:
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
@click.option("--color", "-c", default=None, help="Label color (berry, red, orange, yellow, green, teal, blue, purple, gray, brown)")
@click.option("--quiet", "-q", is_flag=True, help="Suppress success messages")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def create_label(name: str, color: str | None, quiet: bool, as_json: bool) -> None:
    """Create a new label.

    Use "/" for nested labels (appears hierarchically in Gmail UI).

    Examples:

        desk mail create-label "Projects/Orion"

        desk mail create-label "Urgent" --color red
    """
    client = _get_client()

    try:
        label = client.create_label(name, color=color)
    except ValueError as e:
        console.print(f"[red]Error: {e}[/red]")
        sys.exit(1)

    if as_json:
        print(json.dumps(label, indent=2))
    elif not quiet:
        msg = f"[green]Created label '{name}'"
        if color:
            msg += f" (color: {color})"
        msg += "[/green]"
        console.print(msg)


@mail.command("delete-label")
@click.argument("name")
@click.option("--yes", "-y", is_flag=True, help="Skip confirmation prompt")
@click.option("--dry-run", is_flag=True, help="Preview without executing")
@click.option("--quiet", "-q", is_flag=True, help="Suppress success messages")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def delete_label(name: str, yes: bool, dry_run: bool, quiet: bool, as_json: bool) -> None:
    """Delete a label.

    This removes the label from all messages that have it, then deletes the
    label itself. For labels with many messages, this batch-removes the label
    first to avoid Gmail API timeouts.

    Examples:

        desk mail delete-label "Old Project"

        desk mail delete-label "Temp" --yes

        desk mail delete-label "Github" --yes
    """
    client = _get_client(as_json)

    # Check label exists and get message count
    label_query = f"label:{name.replace(' ', '-')}"
    msg_count = client.count_messages(label_query)

    if dry_run:
        if as_json:
            preview = dry_run_preview(
                operation="delete-label",
                targets=[{"label": name, "estimated_messages": msg_count}],
                reversible=False,
                undo_command=None,
            )
            print(json.dumps(preview, indent=2))
        elif not quiet:
            console.print(f"[yellow]Would delete label '{name}' (~{msg_count} messages)[/yellow]")
            if msg_count > 0:
                console.print("[dim]Label will be batch-removed from messages first, then deleted[/dim]")
        return

    # Confirm unless --yes flag provided
    if not yes:
        if not sys.stdin.isatty():
            msg = (
                f"Label '{name}' has ~{msg_count} message(s). "
                f"Non-interactive mode requires --yes flag"
            )
            if as_json:
                error = structured_error(
                    ErrorCode.INVALID_INPUT,
                    msg,
                    suggestions=[f"Add --yes flag: desk mail delete-label '{name}' --yes"],
                )
                output_result(error, as_json, quiet)
            else:
                console.print(f"[red]Error: {msg}[/red]")
            sys.exit(1)
        if not click.confirm(f"Delete label '{name}'? (~{msg_count} messages will be unlabeled)"):
            console.print("[yellow]Cancelled[/yellow]")
            return

    # For labels with messages, batch-remove first to avoid API timeout
    start_time = time.monotonic()
    messages_cleaned = 0

    if msg_count > 0:
        try:
            label_id = client._get_label_id(name)
            if not label_id:
                raise ValueError(f"Label not found: {name}")

            # Fetch all message IDs with this label
            all_ids = client.search_all_ids(label_query)

            # Batch-remove label in chunks
            for i in range(0, len(all_ids), _BATCH_MODIFY_CHUNK):
                chunk = all_ids[i : i + _BATCH_MODIFY_CHUNK]
                client.batch_modify(chunk, remove_labels=[label_id])
                messages_cleaned += len(chunk)

                if as_json:
                    print(json.dumps({
                        "phase": "removing-label",
                        "processed": len(chunk),
                        "total_so_far": messages_cleaned,
                    }, indent=2), flush=True)

        except ValueError as e:
            error = structured_error(ErrorCode.LABEL_NOT_FOUND, str(e))
            output_result(error, as_json, quiet)
            sys.exit(1)
        except RuntimeError as e:
            _handle_api_error(e, as_json, {"operation": "delete-label", "phase": "removing-label", "name": name})

    # Now delete the empty (or near-empty) label
    try:
        client.delete_label(name)
    except ValueError as e:
        error = structured_error(ErrorCode.LABEL_NOT_FOUND, str(e))
        output_result(error, as_json, quiet)
        sys.exit(1)
    except (TimeoutError, RuntimeError) as e:
        error_str = str(e)
        if "insufficient" in error_str.lower() and "scope" in error_str.lower():
            error = structured_error(ErrorCode.INSUFFICIENT_SCOPES, parse_api_error(error_str))
        else:
            error = structured_error(
                ErrorCode.OPERATION_FAILED,
                parse_api_error(error_str),
                retryable=True,
            )
        output_result(error, as_json, quiet)
        sys.exit(1)

    elapsed_ms = int((time.monotonic() - start_time) * 1000)

    if as_json:
        receipt = operation_receipt(
            "delete-label",
            {"name": name, "messages_cleaned": messages_cleaned, "elapsed_ms": elapsed_ms},
            undo_command=None,
        )
        print(json.dumps(receipt, indent=2))
    elif not quiet:
        msg = f"[green]Deleted label '{name}'"
        if messages_cleaned > 0:
            msg += f" (removed from {messages_cleaned} messages)"
        msg += "[/green]"
        console.print(msg)


@mail.command("rename-label")
@click.argument("old_name")
@click.argument("new_name")
@click.option("--quiet", "-q", is_flag=True, help="Suppress success messages")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def rename_label(old_name: str, new_name: str, quiet: bool, as_json: bool) -> None:
    """Rename a label.

    Examples:

        desk mail rename-label "Old Name" "New Name"

        desk mail rename-label "Projects/Alpha" "Projects/Beta"
    """
    client = _get_client()

    try:
        label = client.rename_label(old_name, new_name)
    except ValueError as e:
        console.print(f"[red]Error: {e}[/red]")
        sys.exit(1)

    if as_json:
        print(json.dumps(label, indent=2))
    elif not quiet:
        console.print(f"[green]Renamed '{old_name}' to '{new_name}'[/green]")


@mail.command()
@click.argument("label_name")
@click.argument("message_ids", nargs=-1)
@click.option("--stdin", is_flag=True, help="Read message IDs from stdin")
@click.option("--query", "-Q", default=None, help="Gmail query — operate on all matching messages")
@click.option("--yes", "-y", is_flag=True, help="Confirm query-based bulk operation")
@click.option("--dry-run", is_flag=True, help="Preview without executing")
@click.option("--quiet", "-q", is_flag=True, help="Suppress success messages")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def label(label_name: str, message_ids: tuple[str, ...], stdin: bool, query: str | None, yes: bool, dry_run: bool, quiet: bool, as_json: bool) -> None:
    """Add a label to messages.

    Examples:

        desk mail label Work ID1 ID2 ID3

        desk mail label Important --query 'from:ceo@company.com' --yes
    """
    ids, resolved_query = _resolve_query_or_ids(
        message_ids, stdin, query, yes or dry_run, "label", as_json,
    )

    if resolved_query:
        client = _get_client(as_json)
        label_id = client._get_label_id(label_name)
        if not label_id:
            label_id = client._resolve_label(label_name)
        _query_bulk_operate(
            client, resolved_query, "label",
            add_labels=[label_id],
            dry_run=dry_run, quiet=quiet, as_json=as_json,
        )
        return

    if not ids:
        console.print("[yellow]No message IDs provided.[/yellow]")
        return

    undo_cmd, undo_expires, reversible = get_undo_info("label", ids, label=label_name)

    if dry_run:
        if as_json:
            preview = dry_run_preview(
                operation="label",
                targets=[{"id": i, "label": label_name} for i in ids],
                reversible=reversible,
                undo_command=undo_cmd,
            )
            print(json.dumps(preview, indent=2))
        elif not quiet:
            console.print(f"[yellow]Would add label '{label_name}' to {len(ids)} message(s)[/yellow]")
            console.print(f"[dim]Undo would be: {undo_cmd}[/dim]")
        return

    client = _get_client(as_json)
    label_id = client._get_label_id(label_name)
    if not label_id:
        label_id = client._resolve_label(label_name)

    client.batch_modify(ids, add_labels=[label_id])

    if as_json:
        receipt = operation_receipt(
            operation="label",
            target=[{"id": i} for i in ids],
            undo_command=undo_cmd,
            undo_expires=undo_expires,
            changes={"labels_added": [label_name]},
        )
        print(json.dumps(receipt, indent=2))
    elif not quiet:
        console.print(f"[green]Added label '{label_name}' to {len(ids)} message(s)[/green]")
        console.print(f"[dim]Undo: {undo_cmd}[/dim]")


@mail.command()
@click.argument("message_ids", nargs=-1)
@click.option("--stdin", is_flag=True, help="Read message IDs from stdin")
@click.option("--query", "-Q", default=None, help="Gmail query — operate on all matching messages")
@click.option("--yes", "-y", is_flag=True, help="Confirm query-based bulk operation")
@click.option("--dry-run", is_flag=True, help="Preview without executing")
@click.option("--quiet", "-q", is_flag=True, help="Suppress success messages")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def archive(message_ids: tuple[str, ...], stdin: bool, query: str | None, yes: bool, dry_run: bool, quiet: bool, as_json: bool) -> None:
    """Archive messages (remove from inbox).

    Examples:

        desk mail archive ID1 ID2 ID3

        desk mail search "from:bot" --json | jq -r '.[].id' | desk mail archive --stdin

        desk mail archive --query 'label:Github is:unread' --yes
    """
    ids, resolved_query = _resolve_query_or_ids(
        message_ids, stdin, query, yes or dry_run, "archive", as_json,
    )

    if resolved_query:
        client = _get_client(as_json)
        _query_bulk_operate(
            client, resolved_query, "archive",
            remove_labels=["INBOX"],
            dry_run=dry_run, quiet=quiet, as_json=as_json,
        )
        return

    if not ids:
        console.print("[yellow]No message IDs provided.[/yellow]")
        return

    undo_cmd, undo_expires, reversible = get_undo_info("archive", ids)

    if dry_run:
        client = _get_client(as_json)
        targets = _get_message_summaries(client, ids)
        if as_json:
            preview = dry_run_preview(
                operation="archive",
                targets=targets,
                reversible=reversible,
                undo_command=undo_cmd,
            )
            print(json.dumps(preview, indent=2))
        elif not quiet:
            console.print(f"[yellow]Would archive {len(ids)} message(s):[/yellow]")
            for t in targets[:5]:
                if "subject" in t:
                    console.print(f"  - {t['subject']} (from {t.get('from', 'unknown')})")
                else:
                    console.print(f"  - {t['id']}")
            if len(ids) > 5:
                console.print(f"  ... and {len(ids) - 5} more")
            console.print(f"\n[dim]Undo would be: {undo_cmd}[/dim]")
        return

    client = _get_client(as_json)
    try:
        client.batch_modify(ids, remove_labels=["INBOX"])
    except Exception as e:
        _handle_api_error(e, as_json, {"operation": "archive", "ids": ids})

    if as_json:
        targets = _get_message_summaries(client, ids)
        receipt = operation_receipt(
            operation="archive",
            target=targets,
            undo_command=undo_cmd,
            undo_expires=undo_expires,
            changes={"labels_removed": ["INBOX"]},
        )
        print(json.dumps(receipt, indent=2))
    elif not quiet:
        console.print(f"[green]Archived {len(ids)} message(s)[/green]")
        console.print(f"[dim]Undo: {undo_cmd}[/dim]")


@mail.command("mark-read")
@click.argument("message_ids", nargs=-1)
@click.option("--stdin", is_flag=True, help="Read message IDs from stdin")
@click.option("--query", "-Q", default=None, help="Gmail query — operate on all matching messages")
@click.option("--yes", "-y", is_flag=True, help="Confirm query-based bulk operation")
@click.option("--dry-run", is_flag=True, help="Preview without executing")
@click.option("--quiet", "-q", is_flag=True, help="Suppress success messages")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def mark_read(message_ids: tuple[str, ...], stdin: bool, query: str | None, yes: bool, dry_run: bool, quiet: bool, as_json: bool) -> None:
    """Mark messages as read.

    Examples:

        desk mail mark-read ID1 ID2 ID3

        desk mail mark-read --query 'label:Github is:unread' --yes
    """
    ids, resolved_query = _resolve_query_or_ids(
        message_ids, stdin, query, yes or dry_run, "mark-read", as_json,
    )

    if resolved_query:
        client = _get_client(as_json)
        _query_bulk_operate(
            client, resolved_query, "mark-read",
            remove_labels=["UNREAD"],
            dry_run=dry_run, quiet=quiet, as_json=as_json,
        )
        return

    if not ids:
        console.print("[yellow]No message IDs provided.[/yellow]")
        return

    undo_cmd, undo_expires, reversible = get_undo_info("mark-read", ids)

    if dry_run:
        if as_json:
            preview = dry_run_preview(
                operation="mark-read",
                targets=[{"id": i} for i in ids],
                reversible=reversible,
                undo_command=undo_cmd,
            )
            print(json.dumps(preview, indent=2))
        elif not quiet:
            console.print(f"[yellow]Would mark {len(ids)} message(s) as read[/yellow]")
            console.print(f"[dim]Undo would be: {undo_cmd}[/dim]")
        return

    client = _get_client(as_json)
    client.batch_modify(ids, remove_labels=["UNREAD"])

    if as_json:
        receipt = operation_receipt(
            operation="mark-read",
            target=[{"id": i} for i in ids],
            undo_command=undo_cmd,
            undo_expires=undo_expires,
            changes={"labels_removed": ["UNREAD"]},
        )
        print(json.dumps(receipt, indent=2))
    elif not quiet:
        console.print(f"[green]Marked {len(ids)} message(s) as read[/green]")
        console.print(f"[dim]Undo: {undo_cmd}[/dim]")


@mail.command("mark-unread")
@click.argument("message_ids", nargs=-1)
@click.option("--stdin", is_flag=True, help="Read message IDs from stdin")
@click.option("--query", "-Q", default=None, help="Gmail query — operate on all matching messages")
@click.option("--yes", "-y", is_flag=True, help="Confirm query-based bulk operation")
@click.option("--dry-run", is_flag=True, help="Preview without executing")
@click.option("--quiet", "-q", is_flag=True, help="Suppress success messages")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def mark_unread(message_ids: tuple[str, ...], stdin: bool, query: str | None, yes: bool, dry_run: bool, quiet: bool, as_json: bool) -> None:
    """Mark messages as unread.

    Examples:

        desk mail mark-unread ID1 ID2 ID3

        desk mail mark-unread --query 'from:bot' --yes
    """
    ids, resolved_query = _resolve_query_or_ids(
        message_ids, stdin, query, yes or dry_run, "mark-unread", as_json,
    )

    if resolved_query:
        client = _get_client(as_json)
        _query_bulk_operate(
            client, resolved_query, "mark-unread",
            add_labels=["UNREAD"],
            dry_run=dry_run, quiet=quiet, as_json=as_json,
        )
        return

    if not ids:
        console.print("[yellow]No message IDs provided.[/yellow]")
        return

    undo_cmd, undo_expires, reversible = get_undo_info("mark-unread", ids)

    if dry_run:
        if as_json:
            preview = dry_run_preview(
                operation="mark-unread",
                targets=[{"id": i} for i in ids],
                reversible=reversible,
                undo_command=undo_cmd,
            )
            print(json.dumps(preview, indent=2))
        elif not quiet:
            console.print(f"[yellow]Would mark {len(ids)} message(s) as unread[/yellow]")
            console.print(f"[dim]Undo would be: {undo_cmd}[/dim]")
        return

    client = _get_client(as_json)
    client.batch_modify(ids, add_labels=["UNREAD"])

    if as_json:
        receipt = operation_receipt(
            operation="mark-unread",
            target=[{"id": i} for i in ids],
            undo_command=undo_cmd,
            undo_expires=undo_expires,
            changes={"labels_added": ["UNREAD"]},
        )
        print(json.dumps(receipt, indent=2))
    elif not quiet:
        console.print(f"[green]Marked {len(ids)} message(s) as unread[/green]")
        console.print(f"[dim]Undo: {undo_cmd}[/dim]")


@mail.command()
@click.argument("message_ids", nargs=-1)
@click.option("--stdin", is_flag=True, help="Read message IDs from stdin")
@click.option("--query", "-Q", default=None, help="Gmail query — operate on all matching messages")
@click.option("--yes", "-y", is_flag=True, help="Confirm query-based bulk operation")
@click.option("--dry-run", is_flag=True, help="Preview without executing")
@click.option("--quiet", "-q", is_flag=True, help="Suppress success messages")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def trash(message_ids: tuple[str, ...], stdin: bool, query: str | None, yes: bool, dry_run: bool, quiet: bool, as_json: bool) -> None:
    """Move messages to trash.

    Examples:

        desk mail trash ID1 ID2 ID3

        desk mail trash --query 'older_than:1y label:Promotions' --yes
    """
    ids, resolved_query = _resolve_query_or_ids(
        message_ids, stdin, query, yes or dry_run, "trash", as_json,
    )

    if resolved_query:
        client = _get_client(as_json)
        _query_bulk_operate(
            client, resolved_query, "trash",
            add_labels=["TRASH"], remove_labels=["INBOX"],
            dry_run=dry_run, quiet=quiet, as_json=as_json,
        )
        return

    if not ids:
        console.print("[yellow]No message IDs provided.[/yellow]")
        return

    undo_cmd, undo_expires, reversible = get_undo_info("trash", ids)

    if dry_run:
        client = _get_client(as_json)
        targets = _get_message_summaries(client, ids)
        if as_json:
            preview = dry_run_preview(
                operation="trash",
                targets=targets,
                reversible=reversible,
                undo_command=undo_cmd,
                warnings=["Messages in trash are auto-deleted after 30 days"],
            )
            print(json.dumps(preview, indent=2))
        elif not quiet:
            console.print(f"[yellow]Would move {len(ids)} message(s) to trash:[/yellow]")
            for t in targets[:5]:
                if "subject" in t:
                    console.print(f"  - {t['subject']} (from {t.get('from', 'unknown')})")
                else:
                    console.print(f"  - {t['id']}")
            if len(ids) > 5:
                console.print(f"  ... and {len(ids) - 5} more")
            console.print(f"\n[yellow]Warning: Messages in trash are auto-deleted after 30 days[/yellow]")
            console.print(f"[dim]Undo would be: {undo_cmd}[/dim]")
        return

    client = _get_client(as_json)
    try:
        client.batch_modify(ids, add_labels=["TRASH"], remove_labels=["INBOX"])
    except Exception as e:
        _handle_api_error(e, as_json, {"operation": "trash", "ids": ids})

    if as_json:
        targets = _get_message_summaries(client, ids)
        receipt = operation_receipt(
            operation="trash",
            target=targets,
            undo_command=undo_cmd,
            undo_expires=undo_expires,
            changes={"labels_added": ["TRASH"], "labels_removed": ["INBOX"]},
        )
        print(json.dumps(receipt, indent=2))
    elif not quiet:
        console.print(f"[green]Moved {len(ids)} message(s) to trash[/green]")
        console.print(f"[dim]Undo: {undo_cmd}[/dim]")
        console.print(f"[dim]Expires: {undo_expires}[/dim]")


@mail.command()
@click.option("--max", "-n", "max_results", default=20, help="Max results")
@click.option("--limit", "limit", default=None, type=int, help="Max results (alias for --max)")
@click.option("--page-token", "page_token", default=None, help="Continue from previous page")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def unread(max_results: int, limit: int | None, page_token: str | None, as_json: bool) -> None:
    """List unread messages.

    Shortcut for: desk mail search "is:unread"
    """
    # --limit takes precedence if provided
    if limit is not None:
        max_results = limit

    client = _get_client()
    result = client.search("is:unread", max_results=max_results, page_token=page_token)

    if as_json:
        print(json.dumps(result, indent=2))
        return

    messages = result.get("messages", [])
    if not messages:
        console.print("No unread messages.")
        return

    table = Table(show_header=True, expand=True)
    table.add_column("ID", style="dim", min_width=16, no_wrap=True)
    table.add_column("From", min_width=20, ratio=1, no_wrap=True)
    table.add_column("Subject", min_width=30, ratio=2)
    table.add_column("Date", min_width=20, no_wrap=True)

    for msg in messages:
        table.add_row(
            msg["id"],
            msg["from"],
            msg["subject"],
            msg["date"],
        )

    console.print(table)

    if result.get("nextPageToken"):
        console.print(f"\n[dim]More results available. Use --page-token {result['nextPageToken']}[/dim]")


@mail.command()
@click.argument("message_ids", nargs=-1)
@click.option("--stdin", is_flag=True, help="Read message IDs from stdin")
@click.option("--query", "-Q", default=None, help="Gmail query — operate on all matching messages")
@click.option("--yes", "-y", is_flag=True, help="Confirm query-based bulk operation")
@click.option("--dry-run", is_flag=True, help="Preview without executing")
@click.option("--quiet", "-q", is_flag=True, help="Suppress success messages")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def star(message_ids: tuple[str, ...], stdin: bool, query: str | None, yes: bool, dry_run: bool, quiet: bool, as_json: bool) -> None:
    """Star messages.

    Examples:

        desk mail star ID1 ID2 ID3

        desk mail star --query 'from:ceo@company.com' --yes
    """
    ids, resolved_query = _resolve_query_or_ids(
        message_ids, stdin, query, yes or dry_run, "star", as_json,
    )

    if resolved_query:
        client = _get_client(as_json)
        _query_bulk_operate(
            client, resolved_query, "star",
            add_labels=["STARRED"],
            dry_run=dry_run, quiet=quiet, as_json=as_json,
        )
        return

    if not ids:
        console.print("[yellow]No message IDs provided.[/yellow]")
        return

    undo_cmd, undo_expires, reversible = get_undo_info("star", ids)

    if dry_run:
        if as_json:
            preview = dry_run_preview(
                operation="star",
                targets=[{"id": i} for i in ids],
                reversible=reversible,
                undo_command=undo_cmd,
            )
            print(json.dumps(preview, indent=2))
        elif not quiet:
            console.print(f"[yellow]Would star {len(ids)} message(s)[/yellow]")
            console.print(f"[dim]Undo would be: {undo_cmd}[/dim]")
        return

    client = _get_client(as_json)
    client.batch_modify(ids, add_labels=["STARRED"])

    if as_json:
        receipt = operation_receipt(
            operation="star",
            target=[{"id": i} for i in ids],
            undo_command=undo_cmd,
            undo_expires=undo_expires,
            changes={"labels_added": ["STARRED"]},
        )
        print(json.dumps(receipt, indent=2))
    elif not quiet:
        console.print(f"[green]Starred {len(ids)} message(s)[/green]")
        console.print(f"[dim]Undo: {undo_cmd}[/dim]")


@mail.command()
@click.argument("message_ids", nargs=-1)
@click.option("--stdin", is_flag=True, help="Read message IDs from stdin")
@click.option("--query", "-Q", default=None, help="Gmail query — operate on all matching messages")
@click.option("--yes", "-y", is_flag=True, help="Confirm query-based bulk operation")
@click.option("--dry-run", is_flag=True, help="Preview without executing")
@click.option("--quiet", "-q", is_flag=True, help="Suppress success messages")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def unstar(message_ids: tuple[str, ...], stdin: bool, query: str | None, yes: bool, dry_run: bool, quiet: bool, as_json: bool) -> None:
    """Remove star from messages.

    Examples:

        desk mail unstar ID1 ID2 ID3

        desk mail unstar --query 'is:starred older_than:6m' --yes
    """
    ids, resolved_query = _resolve_query_or_ids(
        message_ids, stdin, query, yes or dry_run, "unstar", as_json,
    )

    if resolved_query:
        client = _get_client(as_json)
        _query_bulk_operate(
            client, resolved_query, "unstar",
            remove_labels=["STARRED"],
            dry_run=dry_run, quiet=quiet, as_json=as_json,
        )
        return

    if not ids:
        console.print("[yellow]No message IDs provided.[/yellow]")
        return

    undo_cmd, undo_expires, reversible = get_undo_info("unstar", ids)

    if dry_run:
        if as_json:
            preview = dry_run_preview(
                operation="unstar",
                targets=[{"id": i} for i in ids],
                reversible=reversible,
                undo_command=undo_cmd,
            )
            print(json.dumps(preview, indent=2))
        elif not quiet:
            console.print(f"[yellow]Would unstar {len(ids)} message(s)[/yellow]")
            console.print(f"[dim]Undo would be: {undo_cmd}[/dim]")
        return

    client = _get_client(as_json)
    client.batch_modify(ids, remove_labels=["STARRED"])

    if as_json:
        receipt = operation_receipt(
            operation="unstar",
            target=[{"id": i} for i in ids],
            undo_command=undo_cmd,
            undo_expires=undo_expires,
            changes={"labels_removed": ["STARRED"]},
        )
        print(json.dumps(receipt, indent=2))
    elif not quiet:
        console.print(f"[green]Unstarred {len(ids)} message(s)[/green]")
        console.print(f"[dim]Undo: {undo_cmd}[/dim]")


@mail.command()
@click.argument("message_ids", nargs=-1)
@click.option("--stdin", is_flag=True, help="Read message IDs from stdin")
@click.option("--query", "-Q", default=None, help="Gmail query — operate on all matching messages")
@click.option("--yes", "-y", is_flag=True, help="Confirm query-based bulk operation")
@click.option("--dry-run", is_flag=True, help="Preview without executing")
@click.option("--quiet", "-q", is_flag=True, help="Suppress success messages")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def spam(message_ids: tuple[str, ...], stdin: bool, query: str | None, yes: bool, dry_run: bool, quiet: bool, as_json: bool) -> None:
    """Report messages as spam.

    Moves messages to spam folder.

    Examples:

        desk mail spam ID1 ID2 ID3

        desk mail spam --query 'from:suspicious@domain.com' --yes
    """
    ids, resolved_query = _resolve_query_or_ids(
        message_ids, stdin, query, yes or dry_run, "spam", as_json,
    )

    if resolved_query:
        client = _get_client(as_json)
        _query_bulk_operate(
            client, resolved_query, "spam",
            add_labels=["SPAM"], remove_labels=["INBOX"],
            dry_run=dry_run, quiet=quiet, as_json=as_json,
        )
        return

    if not ids:
        console.print("[yellow]No message IDs provided.[/yellow]")
        return

    if dry_run:
        if as_json:
            print(json.dumps({"dry_run": True, "action": "spam", "count": len(ids), "ids": ids}))
        elif not quiet:
            console.print(f"[yellow]Would report {len(ids)} message(s) as spam[/yellow]")
        return

    client = _get_client()
    client.batch_modify(ids, add_labels=["SPAM"], remove_labels=["INBOX"])

    if as_json:
        print(json.dumps({"action": "spam", "count": len(ids), "ids": ids}))
    elif not quiet:
        console.print(f"[green]Reported {len(ids)} message(s) as spam[/green]")


@mail.command("not-spam")
@click.argument("message_ids", nargs=-1)
@click.option("--stdin", is_flag=True, help="Read message IDs from stdin")
@click.option("--query", "-Q", default=None, help="Gmail query — operate on all matching messages")
@click.option("--yes", "-y", is_flag=True, help="Confirm query-based bulk operation")
@click.option("--dry-run", is_flag=True, help="Preview without executing")
@click.option("--quiet", "-q", is_flag=True, help="Suppress success messages")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def not_spam(message_ids: tuple[str, ...], stdin: bool, query: str | None, yes: bool, dry_run: bool, quiet: bool, as_json: bool) -> None:
    """Mark messages as not spam.

    Moves messages from spam folder to inbox.

    Examples:

        desk mail not-spam ID1 ID2 ID3

        desk mail not-spam --query 'in:spam from:trusted@domain.com' --yes
    """
    ids, resolved_query = _resolve_query_or_ids(
        message_ids, stdin, query, yes or dry_run, "not-spam", as_json,
    )

    if resolved_query:
        client = _get_client(as_json)
        _query_bulk_operate(
            client, resolved_query, "not-spam",
            add_labels=["INBOX"], remove_labels=["SPAM"],
            dry_run=dry_run, quiet=quiet, as_json=as_json,
        )
        return

    if not ids:
        console.print("[yellow]No message IDs provided.[/yellow]")
        return

    if dry_run:
        if as_json:
            print(json.dumps({"dry_run": True, "action": "not-spam", "count": len(ids), "ids": ids}))
        elif not quiet:
            console.print(f"[yellow]Would mark {len(ids)} message(s) as not spam[/yellow]")
        return

    client = _get_client()
    client.batch_modify(ids, add_labels=["INBOX"], remove_labels=["SPAM"])

    if as_json:
        print(json.dumps({"action": "not-spam", "count": len(ids), "ids": ids}))
    elif not quiet:
        console.print(f"[green]Marked {len(ids)} message(s) as not spam[/green]")


@mail.command()
@click.argument("message_ids", nargs=-1)
@click.option("--stdin", is_flag=True, help="Read message IDs from stdin")
@click.option("--query", "-Q", default=None, help="Gmail query — operate on all matching messages")
@click.option("--yes", "-y", is_flag=True, help="Confirm query-based bulk operation")
@click.option("--dry-run", is_flag=True, help="Preview without executing")
@click.option("--quiet", "-q", is_flag=True, help="Suppress success messages")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def important(message_ids: tuple[str, ...], stdin: bool, query: str | None, yes: bool, dry_run: bool, quiet: bool, as_json: bool) -> None:
    """Mark messages as important.

    Examples:

        desk mail important ID1 ID2 ID3

        desk mail important --query 'from:ceo@company.com' --yes
    """
    ids, resolved_query = _resolve_query_or_ids(
        message_ids, stdin, query, yes or dry_run, "important", as_json,
    )

    if resolved_query:
        client = _get_client(as_json)
        _query_bulk_operate(
            client, resolved_query, "important",
            add_labels=["IMPORTANT"],
            dry_run=dry_run, quiet=quiet, as_json=as_json,
        )
        return

    if not ids:
        console.print("[yellow]No message IDs provided.[/yellow]")
        return

    if dry_run:
        if as_json:
            print(json.dumps({"dry_run": True, "action": "important", "count": len(ids), "ids": ids}))
        elif not quiet:
            console.print(f"[yellow]Would mark {len(ids)} message(s) as important[/yellow]")
        return

    client = _get_client()
    client.batch_modify(ids, add_labels=["IMPORTANT"])

    if as_json:
        print(json.dumps({"action": "important", "count": len(ids), "ids": ids}))
    elif not quiet:
        console.print(f"[green]Marked {len(ids)} message(s) as important[/green]")


@mail.command("not-important")
@click.argument("message_ids", nargs=-1)
@click.option("--stdin", is_flag=True, help="Read message IDs from stdin")
@click.option("--query", "-Q", default=None, help="Gmail query — operate on all matching messages")
@click.option("--yes", "-y", is_flag=True, help="Confirm query-based bulk operation")
@click.option("--dry-run", is_flag=True, help="Preview without executing")
@click.option("--quiet", "-q", is_flag=True, help="Suppress success messages")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def not_important(message_ids: tuple[str, ...], stdin: bool, query: str | None, yes: bool, dry_run: bool, quiet: bool, as_json: bool) -> None:
    """Remove important marker from messages.

    Examples:

        desk mail not-important ID1 ID2 ID3

        desk mail not-important --query 'is:important older_than:1y' --yes
    """
    ids, resolved_query = _resolve_query_or_ids(
        message_ids, stdin, query, yes or dry_run, "not-important", as_json,
    )

    if resolved_query:
        client = _get_client(as_json)
        _query_bulk_operate(
            client, resolved_query, "not-important",
            remove_labels=["IMPORTANT"],
            dry_run=dry_run, quiet=quiet, as_json=as_json,
        )
        return

    if not ids:
        console.print("[yellow]No message IDs provided.[/yellow]")
        return

    if dry_run:
        if as_json:
            print(json.dumps({"dry_run": True, "action": "not-important", "count": len(ids), "ids": ids}))
        elif not quiet:
            console.print(f"[yellow]Would remove important from {len(ids)} message(s)[/yellow]")
        return

    client = _get_client()
    client.batch_modify(ids, remove_labels=["IMPORTANT"])

    if as_json:
        print(json.dumps({"action": "not-important", "count": len(ids), "ids": ids}))
    elif not quiet:
        console.print(f"[green]Removed important from {len(ids)} message(s)[/green]")


@mail.command("remove-label")
@click.argument("label_name")
@click.argument("message_ids", nargs=-1)
@click.option("--stdin", is_flag=True, help="Read message IDs from stdin")
@click.option("--query", "-Q", default=None, help="Gmail query — operate on all matching messages")
@click.option("--yes", "-y", is_flag=True, help="Confirm query-based bulk operation")
@click.option("--dry-run", is_flag=True, help="Preview without executing")
@click.option("--quiet", "-q", is_flag=True, help="Suppress success messages")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def remove_label(label_name: str, message_ids: tuple[str, ...], stdin: bool, query: str | None, yes: bool, dry_run: bool, quiet: bool, as_json: bool) -> None:
    """Remove a label from messages.

    Examples:

        desk mail remove-label Work ID1 ID2 ID3

        desk mail remove-label Github --query 'label:Github' --yes
    """
    ids, resolved_query = _resolve_query_or_ids(
        message_ids, stdin, query, yes or dry_run, "remove-label", as_json,
    )

    if resolved_query:
        client = _get_client(as_json)
        label_id = client._get_label_id(label_name)
        if not label_id:
            label_id = client._resolve_label(label_name)
        _query_bulk_operate(
            client, resolved_query, "remove-label",
            remove_labels=[label_id],
            dry_run=dry_run, quiet=quiet, as_json=as_json,
        )
        return

    if not ids:
        console.print("[yellow]No message IDs provided.[/yellow]")
        return

    if dry_run:
        if as_json:
            print(json.dumps({"dry_run": True, "action": "remove-label", "label": label_name, "count": len(ids), "ids": ids}))
        elif not quiet:
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
    elif not quiet:
        console.print(f"[green]Removed label '{label_name}' from {len(ids)} message(s)[/green]")


# -----------------------------------------------------------------------------
# Filters
# -----------------------------------------------------------------------------


@mail.command()
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def filters(as_json: bool) -> None:
    """List all email filters.

    Examples:

        desk mail filters

        desk mail filters --json
    """
    client = _get_client()
    filter_list = client.list_filters()

    if as_json:
        print(json.dumps(filter_list, indent=2))
        return

    if not filter_list:
        console.print("No filters.")
        return

    table = Table(show_header=True)
    table.add_column("ID", style="dim", width=20)
    table.add_column("Criteria", width=35)
    table.add_column("Actions", width=30)

    for f in filter_list:
        criteria = f.get("criteria", {})
        criteria_parts = []
        if criteria.get("from"):
            criteria_parts.append(f"from:{criteria['from']}")
        if criteria.get("to"):
            criteria_parts.append(f"to:{criteria['to']}")
        if criteria.get("subject"):
            criteria_parts.append(f"subject:{criteria['subject']}")
        if criteria.get("query"):
            criteria_parts.append(criteria["query"])
        if criteria.get("hasAttachment"):
            criteria_parts.append("has:attachment")

        table.add_row(
            f["id"],
            " ".join(criteria_parts)[:35],
            f.get("actionSummary", "")[:30],
        )

    console.print(table)


@mail.command("filter")
@click.argument("filter_id")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def filter_detail(filter_id: str, as_json: bool) -> None:
    """Get details of a specific filter.

    Examples:

        desk mail filter <filter-id>
    """
    client = _get_client()
    f = client.get_filter(filter_id)

    if as_json:
        print(json.dumps(f, indent=2))
        return

    console.print(f"[bold]Filter ID:[/bold] {f['id']}")
    console.print()
    console.print("[bold]Criteria:[/bold]")
    criteria = f.get("criteria", {})
    if criteria.get("from"):
        console.print(f"  From: {criteria['from']}")
    if criteria.get("to"):
        console.print(f"  To: {criteria['to']}")
    if criteria.get("subject"):
        console.print(f"  Subject contains: {criteria['subject']}")
    if criteria.get("query"):
        console.print(f"  Query: {criteria['query']}")
    if criteria.get("hasAttachment"):
        console.print("  Has attachment: yes")
    console.print()
    console.print("[bold]Actions:[/bold]")
    console.print(f"  {f.get('actionSummary', 'none')}")


@mail.command("create-filter")
@click.option("--from", "from_addr", help="Filter by sender")
@click.option("--to", "to_addr", help="Filter by recipient")
@click.option("--subject", help="Filter by subject (contains)")
@click.option("--query", help="Raw Gmail search query")
@click.option("--has-attachment", is_flag=True, help="Messages with attachments")
@click.option("--add-label", "add_labels", multiple=True, help="Label to add (repeatable)")
@click.option("--remove-label", "remove_labels", multiple=True, help="Label to remove (repeatable)")
@click.option("--archive", is_flag=True, help="Skip inbox")
@click.option("--mark-read", is_flag=True, help="Mark as read")
@click.option("--star", is_flag=True, help="Star the message")
@click.option("--forward", help="Email to forward to")
@click.option("--never-spam", is_flag=True, help="Never mark as spam")
@click.option("--quiet", "-q", is_flag=True, help="Suppress success messages")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def create_filter(
    from_addr: str | None,
    to_addr: str | None,
    subject: str | None,
    query: str | None,
    has_attachment: bool,
    add_labels: tuple[str, ...],
    remove_labels: tuple[str, ...],
    archive: bool,
    mark_read: bool,
    star: bool,
    forward: str | None,
    never_spam: bool,
    quiet: bool,
    as_json: bool,
) -> None:
    """Create an email filter.

    At least one criteria and one action required.

    Examples:

        desk mail create-filter --from "boss@example.com" --add-label Important

        desk mail create-filter --subject "Invoice" --archive --add-label Invoices

        desk mail create-filter --query "list:news@example.com" --archive --mark-read
    """
    client = _get_client()

    try:
        f = client.create_filter(
            from_addr=from_addr,
            to_addr=to_addr,
            subject=subject,
            query=query,
            has_attachment=has_attachment if has_attachment else None,
            add_labels=list(add_labels) if add_labels else None,
            remove_labels=list(remove_labels) if remove_labels else None,
            archive=archive,
            mark_read=mark_read,
            star=star,
            forward=forward,
            never_spam=never_spam,
        )
    except ValueError as e:
        console.print(f"[red]Error: {e}[/red]")
        sys.exit(1)

    if as_json:
        print(json.dumps(f, indent=2))
    elif not quiet:
        console.print(f"[green]Created filter[/green]")
        console.print(f"[dim]Filter ID: {f['id']}[/dim]")


@mail.command("delete-filter")
@click.argument("filter_id")
@click.option("--yes", "-y", is_flag=True, help="Skip confirmation")
@click.option("--quiet", "-q", is_flag=True, help="Suppress success messages")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def delete_filter(filter_id: str, yes: bool, quiet: bool, as_json: bool) -> None:
    """Delete an email filter.

    Examples:

        desk mail delete-filter <filter-id>

        desk mail delete-filter <filter-id> --yes
    """
    if not yes:
        if not sys.stdin.isatty():
            if as_json:
                error = structured_error(
                    ErrorCode.INVALID_INPUT,
                    "Non-interactive mode requires --yes flag",
                    suggestions=["Add --yes flag to skip confirmation"],
                )
                output_result(error, as_json, quiet)
            else:
                console.print("[red]Error: Non-interactive mode requires --yes flag[/red]")
            sys.exit(1)
        if not click.confirm(f"Delete filter {filter_id}?"):
            console.print("[yellow]Cancelled[/yellow]")
            return

    client = _get_client(as_json)

    try:
        client.delete_filter(filter_id)
    except RuntimeError as e:
        error_str = str(e)
        # Check for scope errors
        if "insufficient" in error_str.lower() and "scope" in error_str.lower():
            error = structured_error(
                ErrorCode.INSUFFICIENT_SCOPES,
                parse_api_error(error_str),
            )
        else:
            error = structured_error(
                ErrorCode.OPERATION_FAILED,
                parse_api_error(error_str),
                retryable=True,
            )
        output_result(error, as_json, quiet)
        sys.exit(1)

    if as_json:
        receipt = operation_receipt(
            "delete-filter",
            {"filterId": filter_id},
            undo_command=None,  # Can't undo filter deletion
        )
        print(json.dumps(receipt, indent=2))
    elif not quiet:
        console.print(f"[green]Deleted filter {filter_id}[/green]")


# -----------------------------------------------------------------------------
# Vacation Responder
# -----------------------------------------------------------------------------


@mail.command("vacation-status")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def vacation_status(as_json: bool) -> None:
    """Show vacation auto-reply settings.

    Examples:

        desk mail vacation-status

        desk mail vacation-status --json
    """
    client = _get_client()
    settings = client.get_vacation()

    if as_json:
        print(json.dumps(settings, indent=2))
        return

    status = "[green]ENABLED[/green]" if settings["enabled"] else "[dim]DISABLED[/dim]"
    console.print(f"[bold]Status:[/bold] {status}")

    if settings["enabled"] or settings.get("subject") or settings.get("message"):
        if settings.get("subject"):
            console.print(f"[bold]Subject:[/bold] {settings['subject']}")
        if settings.get("message"):
            console.print(f"[bold]Message:[/bold]")
            console.print(settings["message"][:500])
        if settings.get("startTime"):
            from datetime import datetime
            start = datetime.fromtimestamp(settings["startTime"] / 1000)
            console.print(f"[bold]Start:[/bold] {start.strftime('%Y-%m-%d')}")
        if settings.get("endTime"):
            from datetime import datetime
            end = datetime.fromtimestamp(settings["endTime"] / 1000)
            console.print(f"[bold]End:[/bold] {end.strftime('%Y-%m-%d')}")

        restrictions = []
        if settings.get("contactsOnly"):
            restrictions.append("contacts only")
        if settings.get("domainOnly"):
            restrictions.append("domain only")
        if restrictions:
            console.print(f"[bold]Restrictions:[/bold] {', '.join(restrictions)}")


@mail.command("vacation")
@click.option("--enable", is_flag=True, help="Enable vacation responder")
@click.option("--disable", is_flag=True, help="Disable vacation responder")
@click.option("--message", "-m", help="Auto-reply message")
@click.option("--subject", "-s", help="Auto-reply subject")
@click.option("--start", "start_date", help="Start date (YYYY-MM-DD)")
@click.option("--end", "end_date", help="End date (YYYY-MM-DD)")
@click.option("--contacts-only", is_flag=True, help="Only reply to contacts")
@click.option("--domain-only", is_flag=True, help="Only reply to same domain")
@click.option("--quiet", "-q", is_flag=True, help="Suppress success messages")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def vacation(
    enable: bool,
    disable: bool,
    message: str | None,
    subject: str | None,
    start_date: str | None,
    end_date: str | None,
    contacts_only: bool,
    domain_only: bool,
    quiet: bool,
    as_json: bool,
) -> None:
    """Set vacation auto-reply settings.

    Examples:

        desk mail vacation --enable --message "I'm out of office until Monday."

        desk mail vacation --enable --message "On vacation" --start 2024-02-10 --end 2024-02-17

        desk mail vacation --disable
    """
    if enable and disable:
        console.print("[red]Error: Cannot use both --enable and --disable[/red]")
        sys.exit(1)

    if not enable and not disable and not message and not subject:
        console.print("[yellow]Nothing to do. Use --enable, --disable, or set message/subject.[/yellow]")
        return

    # Determine enabled state
    if disable:
        enabled = False
    elif enable:
        enabled = True
    else:
        # If setting message/subject but not explicitly enabling, enable it
        enabled = True

    client = _get_client()
    settings = client.set_vacation(
        enabled=enabled,
        message=message,
        subject=subject,
        start_date=start_date,
        end_date=end_date,
        contacts_only=contacts_only,
        domain_only=domain_only,
    )

    if as_json:
        print(json.dumps(settings, indent=2))
    elif not quiet:
        if enabled:
            console.print("[green]Vacation responder enabled[/green]")
        else:
            console.print("[green]Vacation responder disabled[/green]")


@mail.command()
@click.argument("message_ids", nargs=-1)
@click.option("--add-label", "-a", "add_labels", multiple=True, help="Label to add (repeatable)")
@click.option(
    "--remove-label", "-r", "remove_labels", multiple=True, help="Label to remove (repeatable)"
)
@click.option("--stdin", is_flag=True, help="Read message IDs from stdin")
@click.option("--query", "-Q", default=None, help="Gmail query — operate on all matching messages")
@click.option("--yes", "-y", is_flag=True, help="Confirm query-based bulk operation")
@click.option("--dry-run", is_flag=True, help="Preview without executing")
@click.option("--quiet", "-q", is_flag=True, help="Suppress success messages")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def modify(
    message_ids: tuple[str, ...],
    add_labels: tuple[str],
    remove_labels: tuple[str],
    stdin: bool,
    query: str | None,
    yes: bool,
    dry_run: bool,
    quiet: bool,
    as_json: bool,
) -> None:
    """Modify message labels (generic operation).

    Compose arbitrary label changes. System labels (INBOX, UNREAD, STARRED, etc.)
    and user labels are both supported.

    Examples:

        desk mail modify ID --remove-label INBOX --remove-label UNREAD

        desk mail modify ID1 ID2 --add-label Work --remove-label INBOX

        desk mail modify --query 'label:OldProject' --add-label Archive --remove-label INBOX --yes
    """
    if not add_labels and not remove_labels:
        console.print("[yellow]Nothing to do. Use --add-label or --remove-label.[/yellow]")
        return

    ids, resolved_query = _resolve_query_or_ids(
        message_ids, stdin, query, yes or dry_run, "modify", as_json,
    )

    if resolved_query:
        client = _get_client(as_json)
        _query_bulk_operate(
            client, resolved_query, "modify",
            add_labels=list(add_labels) if add_labels else None,
            remove_labels=list(remove_labels) if remove_labels else None,
            dry_run=dry_run, quiet=quiet, as_json=as_json,
        )
        return

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
            preview = dry_run_preview(
                operation="modify",
                targets=[{"id": i} for i in ids],
                reversible=True,
                undo_command=None,  # Undo depends on what labels were changed
            )
            preview["changes"] = {"add_labels": list(add_labels), "remove_labels": list(remove_labels)}
            print(json.dumps(preview, indent=2))
        elif not quiet:
            console.print(f"[yellow]Would modify {len(ids)} message(s): {' '.join(changes)}[/yellow]")
        return

    client = _get_client(as_json)
    try:
        client.batch_modify(
            ids,
            add_labels=list(add_labels) if add_labels else None,
            remove_labels=list(remove_labels) if remove_labels else None,
        )
    except Exception as e:
        _handle_api_error(e, as_json, {"operation": "modify", "ids": ids})

    if as_json:
        receipt = operation_receipt(
            operation="modify",
            target=[{"id": i} for i in ids],
            undo_command=None,
            changes={"labels_added": list(add_labels), "labels_removed": list(remove_labels)},
        )
        print(json.dumps(receipt, indent=2))
    elif not quiet:
        console.print(f"[green]Modified {len(ids)} message(s): {' '.join(changes)}[/green]")
