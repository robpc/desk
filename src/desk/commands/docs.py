"""Docs commands — read and update Google Docs."""

import json
import sys

import click
from rich.console import Console
from rich.markup import escape

from desk.agent import (
    ERROR_SUGGESTIONS,
    ErrorCode,
    operation_receipt,
    output_result,
    parse_api_error,
    structured_error,
)
from desk.auth import get_credentials, get_last_auth_failure
from desk.services.docs import DocsClient

console = Console()


def _get_client(as_json: bool = False) -> DocsClient:
    """Get authenticated Docs client or exit."""
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
    return DocsClient(creds)


def _handle_api_error(e: Exception, as_json: bool, context: dict | None = None) -> None:
    """Handle API errors with structured output when --json is used."""
    raw_error = str(e)
    error_msg = parse_api_error(raw_error)

    if "not found" in raw_error.lower() or "404" in raw_error:
        code = ErrorCode.DOCUMENT_NOT_FOUND
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
def docs() -> None:
    """Google Docs — read and update documents."""
    pass


@docs.command()
@click.argument("title")
@click.option("--body", "-b", default="", help="Initial document content")
@click.option("--quiet", "-q", is_flag=True, help="Suppress success messages")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def create(title: str, body: str, quiet: bool, as_json: bool) -> None:
    """Create a new Google Doc.

    Examples:

        desk docs create "Meeting Notes"

        desk docs create "Draft" --body "Hello world"
    """
    client = _get_client(as_json)
    try:
        result = client.create(title, body=body)
    except Exception as e:
        _handle_api_error(e, as_json, {"title": title})

    receipt = operation_receipt(
        operation="create",
        target={
            "id": result.get("documentId"),
            "title": result.get("title"),
            "link": result.get("webViewLink"),
        },
    )
    output_result(receipt, as_json, quiet)


@docs.command()
@click.argument("document_id")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def read(document_id: str, as_json: bool) -> None:
    """Read a document's content.

    Examples:

        desk docs read <document-id>
    """
    client = _get_client(as_json)
    try:
        result = client.read(document_id)
    except Exception as e:
        _handle_api_error(e, as_json, {"document_id": document_id})

    if as_json:
        print(json.dumps(result, indent=2))
        return

    console.print(f"[bold]{result['title']}[/bold]")
    console.print()
    console.print(result["body"])


@docs.command()
@click.argument("document_id")
@click.argument("text")
@click.option(
    "--mode",
    "-m",
    type=click.Choice(["append", "prepend", "replace"]),
    default="append",
    help="Where to insert: append (end), prepend (beginning), replace (all)",
)
@click.option(
    "--find", "-f", default=None,
    help="Find and replace: TEXT replaces all occurrences of FIND",
)
@click.option("--ignore-case", is_flag=True, help="Case-insensitive find (use with --find)")
@click.option("--quiet", "-q", is_flag=True, help="Suppress success messages")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def update(
    document_id: str, text: str, mode: str,
    find: str | None, ignore_case: bool,
    quiet: bool, as_json: bool,
) -> None:
    """Insert or replace text in a document.

    Examples:

        desk docs update <id> "New text at the end"

        desk docs update <id> "Text at start" --mode prepend

        desk docs update <id> "Replace everything" --mode replace

        desk docs update <id> "New Title" --find "Template Title"

        desk docs update <id> "new" --find "old" --ignore-case
    """
    if find and mode != "append":
        if as_json:
            error = structured_error(
                ErrorCode.INVALID_INPUT,
                "--find and --mode cannot be used together",
                suggestions=[
                    "Use --find alone for find-and-replace",
                    "Use --mode alone for insert/replace",
                ],
            )
            print(json.dumps(error, indent=2))
        else:
            console.print("[red]Error: --find and --mode cannot be used together[/red]")
        sys.exit(1)

    client = _get_client(as_json)

    if find:
        try:
            result = client.find_and_replace(
                document_id, find_text=find, replace_text=text, match_case=not ignore_case
            )
        except Exception as e:
            _handle_api_error(e, as_json, {"document_id": document_id, "find": find})

        receipt = operation_receipt(
            operation="find_and_replace",
            target={"id": document_id},
            changes={
                "find": find,
                "replace": text,
                "ignore_case": ignore_case,
                "occurrences_changed": result["occurrences_changed"],
            },
        )
        output_result(receipt, as_json, quiet)
        return

    try:
        result = client.update(document_id, text, mode=mode)
    except Exception as e:
        _handle_api_error(e, as_json, {"document_id": document_id, "mode": mode})

    receipt = operation_receipt(
        operation="update",
        target={
            "id": document_id,
        },
        changes={
            "mode": mode,
            "text_length": len(text),
        },
    )
    output_result(receipt, as_json, quiet)


@docs.command()
@click.argument("document_id")
@click.argument("dest", type=click.Path())
@click.option(
    "--format",
    "-f",
    "fmt",
    type=click.Choice(["pdf", "txt", "docx", "html"]),
    default="pdf",
    help="Export format",
)
@click.option("--quiet", "-q", is_flag=True, help="Suppress success messages")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def export(document_id: str, dest: str, fmt: str, quiet: bool, as_json: bool) -> None:
    """Export a document to a different format.

    Examples:

        desk docs export <id> report.pdf

        desk docs export <id> notes.txt --format txt

        desk docs export <id> doc.docx --format docx
    """
    from pathlib import Path

    client = _get_client(as_json)
    try:
        content = client.export(document_id, fmt=fmt)
    except Exception as e:
        _handle_api_error(e, as_json, {"document_id": document_id, "format": fmt})

    dest_path = Path(dest)
    try:
        if isinstance(content, str):
            dest_path.write_text(content, encoding="utf-8")
        else:
            dest_path.write_bytes(content)
    except OSError as e:
        if as_json:
            error = structured_error(
                ErrorCode.LOCAL_FILE_WRITE_ERROR,
                f"Failed to write file: {e}",
                suggestions=["Check that the destination path is writable", "Check disk space"],
            )
            print(json.dumps(error, indent=2))
        else:
            console.print(f"[red]Error writing file: {e}[/red]")
        sys.exit(1)

    receipt = operation_receipt(
        operation="export",
        target={
            "id": document_id,
            "format": fmt,
            "local_path": str(dest_path),
        },
    )
    output_result(receipt, as_json, quiet)
