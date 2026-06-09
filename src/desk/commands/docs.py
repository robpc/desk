"""Docs commands — read, update, and edit Google Docs."""

import json
import sys

import click
from rich.console import Console
from rich.markup import escape
from rich.table import Table

from desk.agent import (
    ERROR_SUGGESTIONS,
    ErrorCode,
    is_scope_error,
    operation_receipt,
    output_result,
    parse_api_error,
    structured_error,
)
from desk.auth import get_credentials, get_last_auth_failure
from desk.console import error_console
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
            print(json.dumps(error, indent=2), file=sys.stderr)
        else:
            error_console.print("[red]Not authenticated.[/red]")
            if reason:
                error_console.print(f"[yellow]{escape(reason)}[/yellow]")
            else:
                error_console.print("Run: [cyan]desk setup[/cyan]")
        sys.exit(1)
    return DocsClient(creds)


def _handle_api_error(e: Exception, as_json: bool, context: dict | None = None) -> None:
    """Handle API errors with structured output when --json is used."""
    raw_error = str(e)
    error_msg = parse_api_error(raw_error)

    if is_scope_error(raw_error):
        code = ErrorCode.INSUFFICIENT_SCOPES
    elif "not found" in raw_error.lower() or "404" in raw_error:
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
        print(json.dumps(error, indent=2), file=sys.stderr)
    else:
        error_console.print(f"[red]Error: {error_msg}[/red]")
        if suggestions:
            error_console.print("[dim]Suggestions:[/dim]")
            for s in suggestions:
                error_console.print(f"  [cyan]- {s}[/cyan]")

    sys.exit(1)


def _read_content(text: str | None, file: str | None, stdin: bool) -> str:
    """Read content from text argument, file, or stdin.

    Priority: stdin > file > text. Only one source should be provided.
    """
    sources = sum([stdin, file is not None, text is not None])
    if sources > 1:
        raise click.UsageError("Provide only one of text, --file, or --stdin")
    if stdin:
        return sys.stdin.read()
    if file:
        from pathlib import Path

        return Path(file).read_text(encoding="utf-8")
    if text is not None:
        return text
    raise click.UsageError("Provide text, --file, or --stdin")


def _looks_like_tab_error(error: Exception) -> bool:
    """Heuristic: did this error come from a missing/invalid tab?

    Covers the read-path RuntimeError("Tab not found: ...") and the batchUpdate
    HttpError wrapped as RuntimeError("Docs API error: ...") whose payload
    typically mentions "tabId" / "tab" with "invalid" or "not found."
    """
    msg = str(error).lower()
    if "tab not found" in msg:
        return True
    return "tab" in msg and ("not found" in msg or "invalid" in msg)


def _emit_tab_ambiguous(
    document_id: str, value: str, matches: list[dict], as_json: bool,
) -> None:
    details = {
        "document_id": document_id,
        "value": value,
        "matches": [
            {"tabId": t.get("tabId", ""), "title": t.get("title", "")} for t in matches
        ],
    }
    error = structured_error(
        ErrorCode.TAB_NAME_AMBIGUOUS,
        f"Multiple tabs match '{value}'.",
        details=details,
    )
    if as_json:
        print(json.dumps(error, indent=2), file=sys.stderr)
    else:
        error_console.print(f"[red]Error: {error['error']['message']}[/red]")
        error_console.print("[dim]Matching tabs:[/dim]")
        for t in matches:
            error_console.print(f"  [cyan]{t.get('tabId', '')}[/cyan]  {t.get('title', '')}")
        error_console.print("[dim]Re-run with --tab <tabId>.[/dim]")
    sys.exit(1)


def _emit_tab_not_found(
    document_id: str, value: str, tabs: list[dict], as_json: bool,
) -> None:
    details = {
        "document_id": document_id,
        "value": value,
        "available_tabs": [
            {"tabId": t.get("tabId", ""), "title": t.get("title", "")} for t in tabs
        ],
    }
    error = structured_error(
        ErrorCode.TAB_NOT_FOUND,
        f"No tab matches '{value}'.",
        details=details,
    )
    if as_json:
        print(json.dumps(error, indent=2), file=sys.stderr)
    else:
        error_console.print(f"[red]Error: {error['error']['message']}[/red]")
        if tabs:
            error_console.print("[dim]Available tabs:[/dim]")
            for t in tabs:
                error_console.print(f"  [cyan]{t.get('tabId', '')}[/cyan]  {t.get('title', '')}")
        else:
            error_console.print("[dim]Document has no tabs.[/dim]")
    sys.exit(1)


def _with_tab_resolution(
    client: DocsClient,
    document_id: str,
    value: str | None,
    as_json: bool,
    fn,
):
    """Run fn(tab_id) optimistically. On a tab-shaped failure, list tabs and
    retry with the title-resolved ID. Returns (result, resolved_tab_id).

    See ADR-018. The optimistic call preserves zero overhead for valid IDs;
    only the title path pays the extra round-trips.
    """
    if value is None:
        return fn(None), None

    try:
        return fn(value), value
    except Exception as original_error:
        if not _looks_like_tab_error(original_error):
            raise

        try:
            tabs = client.get_tabs_cached(document_id)
        except Exception:
            raise original_error from None

        # If value was a real tabId, the original error was about something
        # else and we shouldn't mask it.
        if any(t.get("tabId") == value for t in tabs):
            raise original_error

        needle = value.strip().lower()
        matches = [t for t in tabs if t.get("title", "").strip().lower() == needle]

        if len(matches) == 1:
            resolved = matches[0]["tabId"]
            return fn(resolved), resolved

        if len(matches) > 1:
            _emit_tab_ambiguous(document_id, value, matches, as_json)

        _emit_tab_not_found(document_id, value, tabs, as_json)


def _parse_at(at: str, as_json: bool = False) -> int | None:
    """Parse --at value: 'end' returns None, otherwise integer index >= 1.

    Exits with structured error on invalid input.
    """
    if at.lower() == "end":
        return None
    try:
        val = int(at)
    except ValueError:
        msg = f"--at must be an integer or 'end', got '{at}'"
        if as_json:
            error = structured_error(ErrorCode.INVALID_INPUT, msg)
            print(json.dumps(error, indent=2), file=sys.stderr)
        else:
            error_console.print(f"[red]Error: {msg}[/red]")
        sys.exit(1)
    if val < 1:
        msg = "--at index must be >= 1 (Google Docs indices are 1-based)"
        if as_json:
            error = structured_error(ErrorCode.INDEX_OUT_OF_RANGE, msg)
            print(json.dumps(error, indent=2), file=sys.stderr)
        else:
            error_console.print(f"[red]Error: {msg}[/red]")
        sys.exit(1)
    return val


@click.group()
def docs() -> None:
    """Google Docs — read and update documents."""
    pass


# ── Document creation ───────────────────────────────────────────────────

@docs.command()
@click.argument("title")
@click.option("--body", "-b", default=None, help="Initial content (markdown by default)")
@click.option("--file", "-f", "file_path", help="Read content from file")
@click.option("--stdin", is_flag=True, help="Read content from stdin")
@click.option("--plain", is_flag=True, help="Insert content as plain text instead of markdown")
@click.option("--quiet", "-q", is_flag=True, help="Suppress success messages")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def create(
    title: str,
    body: str | None,
    file_path: str | None,
    stdin: bool,
    plain: bool,
    quiet: bool,
    as_json: bool,
) -> None:
    """Create a new Google Doc.

    Content is processed as markdown by default, producing native Google Docs
    formatting (headings, bold, italic, links, lists). Use --plain for raw text.

    Examples:

        desk docs create "Meeting Notes"

        desk docs create "Draft" --body "# Hello\\n\\n**Bold** text"

        desk docs create "Report" --file report.md

        desk docs create "Plain" --body "no formatting" --plain
    """
    content = ""
    if (body is not None and body != "") or file_path or stdin:
        try:
            content = _read_content(body, file_path, stdin)
        except (click.UsageError, OSError) as e:
            if as_json:
                error = structured_error(ErrorCode.INVALID_INPUT, str(e))
                print(json.dumps(error, indent=2), file=sys.stderr)
            else:
                error_console.print(f"[red]Error: {e}[/red]")
            sys.exit(1)

    client = _get_client(as_json)
    try:
        result = client.create(title, body=content, markdown=not plain)
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


# ── Read / inspect / export ─────────────────────────────────────────────

@docs.command()
@click.argument("document_id")
@click.option("--tab", "tab_id", default=None, help="Tab ID or title to read from")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def read(document_id: str, tab_id: str | None, as_json: bool) -> None:
    """Read a document's content.

    Examples:

        desk docs read <document-id>

        desk docs read <id> --tab <tab-id>
    """
    client = _get_client(as_json)
    try:
        result, _ = _with_tab_resolution(
            client, document_id, tab_id, as_json,
            lambda tid: client.read(document_id, tab_id=tid),
        )
    except Exception as e:
        _handle_api_error(e, as_json, {"document_id": document_id})

    if as_json:
        print(json.dumps(result, indent=2))
        return

    console.print(f"[bold]{result['title']}[/bold]")
    console.print()
    console.print(result["body"])


@docs.command("inspect")
@click.argument("document_id")
@click.option("--tab", "tab_id", default=None, help="Tab ID or title to inspect")
@click.option("--quiet", "-q", is_flag=True, help="Suppress output")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def inspect_cmd(document_id: str, tab_id: str | None, quiet: bool, as_json: bool) -> None:
    """Inspect document structure with indices.

    Shows each element's type, start/end indices, and preview text.
    Use this to plan index-based edits.

    Examples:

        desk docs inspect <id>

        desk docs inspect <id> --tab <tab-id>
    """
    client = _get_client(as_json)
    try:
        result, _ = _with_tab_resolution(
            client, document_id, tab_id, as_json,
            lambda tid: client.inspect(document_id, tab_id=tid),
        )
    except Exception as e:
        _handle_api_error(e, as_json, {"document_id": document_id})

    if as_json:
        print(json.dumps(result, indent=2))
        return

    if quiet:
        return

    console.print(f"[bold]{result['title']}[/bold]")
    console.print(f"[dim]Document end index: {result['endIndex']}[/dim]")
    console.print()

    for elem in result["elements"]:
        etype = elem["type"]
        start = elem["startIndex"]
        end = elem["endIndex"]

        if etype == "paragraph":
            style = elem.get("style", "NORMAL_TEXT")
            text_preview = elem.get("text", "")
            # Override display for special paragraph types
            if elem.get("horizontalRule"):
                console.print(
                    f"  [{start}:{end}] [magenta]HORIZONTAL_RULE[/magenta]"
                )
                continue
            if elem.get("bullet"):
                style = "BULLET_LIST"
            if text_preview:
                console.print(
                    f"  [{start}:{end}] [cyan]{style}[/cyan] {escape(text_preview[:80])}"
                )
            else:
                console.print(f"  [{start}:{end}] [cyan]{style}[/cyan] [dim](empty)[/dim]")
        elif etype == "table":
            rows = elem.get("rows", 0)
            cols = elem.get("columns", 0)
            console.print(f"  [{start}:{end}] [yellow]TABLE[/yellow] {rows}x{cols}")
        elif etype == "sectionBreak":
            console.print(f"  [{start}:{end}] [dim]SECTION_BREAK[/dim]")


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
            print(json.dumps(error, indent=2), file=sys.stderr)
        else:
            error_console.print(f"[red]Error writing file: {e}[/red]")
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


# ── Text operations ─────────────────────────────────────────────────────

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
@click.option("--tab", "tab_id", default=None, help="Tab ID or title to target")
@click.option("--quiet", "-q", is_flag=True, help="Suppress success messages")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def update(
    document_id: str, text: str, mode: str,
    find: str | None, ignore_case: bool,
    tab_id: str | None,
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
            print(json.dumps(error, indent=2), file=sys.stderr)
        else:
            error_console.print("[red]Error: --find and --mode cannot be used together[/red]")
        sys.exit(1)

    client = _get_client(as_json)

    if find:
        try:
            result, _ = _with_tab_resolution(
                client, document_id, tab_id, as_json,
                lambda tid: client.find_and_replace(
                    document_id, find_text=find, replace_text=text,
                    match_case=not ignore_case, tab_id=tid,
                ),
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
        result, _ = _with_tab_resolution(
            client, document_id, tab_id, as_json,
            lambda tid: client.update(document_id, text, mode=mode, tab_id=tid),
        )
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


@docs.command("insert")
@click.argument("document_id")
@click.argument("text", required=False)
@click.option("--at", default="end", help="Index to insert at (integer or 'end')")
@click.option(
    "--after-paragraph", type=int, default=None,
    help="Insert after the paragraph containing this index",
)
@click.option(
    "--before-paragraph", type=int, default=None,
    help="Insert before the paragraph containing this index",
)
@click.option("--file", "-f", "file_path", help="Read content from file")
@click.option("--stdin", is_flag=True, help="Read content from stdin")
@click.option("--tab", "tab_id", default=None, help="Tab ID or title to target")
@click.option("--quiet", "-q", is_flag=True, help="Suppress success messages")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def insert_cmd(
    document_id: str,
    text: str | None,
    at: str,
    after_paragraph: int | None,
    before_paragraph: int | None,
    file_path: str | None,
    stdin: bool,
    tab_id: str | None,
    quiet: bool,
    as_json: bool,
) -> None:
    """Insert text at a specific position in a document.

    Use --after-paragraph or --before-paragraph for paragraph-aware insertion
    that snaps to paragraph boundaries, preventing mid-word splits.

    Examples:

        desk docs insert <id> "New text" --at end

        desk docs insert <id> "Text at position 5" --at 5

        desk docs insert <id> --file notes.txt --at end

        desk docs insert <id> "\\n" --after-paragraph 637

        desk docs insert <id> "New section" --before-paragraph 638
    """
    # Validate that paragraph options aren't combined with --at
    para_opts = sum([after_paragraph is not None, before_paragraph is not None])
    if para_opts > 1:
        msg = "Use only one of --after-paragraph or --before-paragraph"
        if as_json:
            error = structured_error(ErrorCode.INVALID_INPUT, msg)
            print(json.dumps(error, indent=2), file=sys.stderr)
        else:
            error_console.print(f"[red]Error: {msg}[/red]")
        sys.exit(1)
    if para_opts == 1 and at != "end":
        msg = "--after-paragraph and --before-paragraph cannot be used with --at"
        if as_json:
            error = structured_error(ErrorCode.INVALID_INPUT, msg)
            print(json.dumps(error, indent=2), file=sys.stderr)
        else:
            error_console.print(f"[red]Error: {msg}[/red]")
        sys.exit(1)

    try:
        content = _read_content(text, file_path, stdin)
    except (click.UsageError, OSError) as e:
        if as_json:
            error = structured_error(ErrorCode.INVALID_INPUT, str(e))
            print(json.dumps(error, indent=2), file=sys.stderr)
        else:
            error_console.print(f"[red]Error: {e}[/red]")
        sys.exit(1)

    client = _get_client(as_json)

    # Resolve paragraph-aware index. The first tab-using call resolves the
    # tab_id (if a title was given); the resolved value is reused below.
    if after_paragraph is not None or before_paragraph is not None:
        try:
            if after_paragraph is not None:
                index, tab_id = _with_tab_resolution(
                    client, document_id, tab_id, as_json,
                    lambda tid: client.find_paragraph_boundary(
                        document_id, after_paragraph, position="after", tab_id=tid,
                    ),
                )
                at_label = f"after-paragraph({after_paragraph})->index({index})"
            else:
                index, tab_id = _with_tab_resolution(
                    client, document_id, tab_id, as_json,
                    lambda tid: client.find_paragraph_boundary(
                        document_id, before_paragraph, position="before", tab_id=tid,
                    ),
                )
                at_label = f"before-paragraph({before_paragraph})->index({index})"
        except Exception as e:
            _handle_api_error(e, as_json, {"document_id": document_id})
            return  # unreachable but makes type checker happy
    else:
        index = _parse_at(at, as_json)
        at_label = at

    try:
        if after_paragraph is None and before_paragraph is None:
            _, tab_id = _with_tab_resolution(
                client, document_id, tab_id, as_json,
                lambda tid: client.insert_at(
                    document_id, content, index=index, tab_id=tid,
                ),
            )
        else:
            client.insert_at(document_id, content, index=index, tab_id=tab_id)
    except Exception as e:
        _handle_api_error(e, as_json, {"document_id": document_id, "at": at_label})

    receipt = operation_receipt(
        operation="insert",
        target={"id": document_id},
        changes={"at": at_label, "text_length": len(content)},
    )
    output_result(receipt, as_json, quiet)


@docs.command("delete-range")
@click.argument("document_id")
@click.option("--start", required=True, type=int, help="Start index (inclusive)")
@click.option("--end", required=True, type=int, help="End index (exclusive)")
@click.option("--tab", "tab_id", default=None, help="Tab ID or title to target")
@click.option("--quiet", "-q", is_flag=True, help="Suppress success messages")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def delete_range_cmd(
    document_id: str, start: int, end: int, tab_id: str | None,
    quiet: bool, as_json: bool,
) -> None:
    """Delete content between two indices.

    Examples:

        desk docs delete-range <id> --start 5 --end 20
    """
    if start < 1 or end < 1 or start >= end:
        msg = (
            f"Invalid range: start={start}, end={end}. "
            "Both must be >= 1 and start must be less than end."
        )
        if as_json:
            error = structured_error(
                ErrorCode.INVALID_RANGE,
                msg,
                suggestions=["Use desk docs inspect <id> to see document indices"],
            )
            print(json.dumps(error, indent=2), file=sys.stderr)
        else:
            error_console.print(f"[red]Error: {msg}[/red]")
        sys.exit(1)

    client = _get_client(as_json)
    try:
        _with_tab_resolution(
            client, document_id, tab_id, as_json,
            lambda tid: client.delete_range(document_id, start, end, tab_id=tid),
        )
    except Exception as e:
        _handle_api_error(e, as_json, {"document_id": document_id, "start": start, "end": end})

    receipt = operation_receipt(
        operation="delete_range",
        target={"id": document_id},
        changes={"start": start, "end": end, "chars_deleted": end - start},
    )
    output_result(receipt, as_json, quiet)


# ── Styling ─────────────────────────────────────────────────────────────

@docs.command("style")
@click.argument("document_id")
@click.option("--start", required=True, type=int, help="Start index")
@click.option("--end", required=True, type=int, help="End index")
@click.option("--bold/--no-bold", default=None, help="Set bold")
@click.option("--italic/--no-italic", default=None, help="Set italic")
@click.option("--underline/--no-underline", default=None, help="Set underline")
@click.option("--strikethrough/--no-strikethrough", default=None, help="Set strikethrough")
@click.option("--code", is_flag=True, default=False, help="Set monospace font")
@click.option("--link", default=None, help="Set hyperlink URL")
@click.option("--font-size", type=float, default=None, help="Font size in points")
@click.option("--font", default=None, help="Font family name")
@click.option("--tab", "tab_id", default=None, help="Tab ID or title to target")
@click.option("--quiet", "-q", is_flag=True, help="Suppress success messages")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def style_cmd(
    document_id: str,
    start: int,
    end: int,
    bold: bool | None,
    italic: bool | None,
    underline: bool | None,
    strikethrough: bool | None,
    code: bool,
    link: str | None,
    font_size: float | None,
    font: str | None,
    tab_id: str | None,
    quiet: bool,
    as_json: bool,
) -> None:
    """Apply text styling to a range.

    Examples:

        desk docs style <id> --start 1 --end 10 --bold

        desk docs style <id> --start 5 --end 15 --italic --link "https://example.com"

        desk docs style <id> --start 1 --end 50 --code
    """
    client = _get_client(as_json)
    try:
        _with_tab_resolution(
            client, document_id, tab_id, as_json,
            lambda tid: client.update_text_style(
                document_id, start, end,
                bold=bold,
                italic=italic,
                code=code or None,
                link_url=link,
                font_size=font_size,
                underline=underline,
                strikethrough=strikethrough,
                font_family=font,
                tab_id=tid,
            ),
        )
    except Exception as e:
        _handle_api_error(e, as_json, {"document_id": document_id, "start": start, "end": end})

    applied_styles = {"start": start, "end": end}
    if bold is not None:
        applied_styles["bold"] = bold
    if italic is not None:
        applied_styles["italic"] = italic
    if underline is not None:
        applied_styles["underline"] = underline
    if strikethrough is not None:
        applied_styles["strikethrough"] = strikethrough
    if code:
        applied_styles["code"] = True
    if link is not None:
        applied_styles["link"] = link
    if font_size is not None:
        applied_styles["font_size"] = font_size
    if font is not None:
        applied_styles["font"] = font

    receipt = operation_receipt(
        operation="style",
        target={"id": document_id},
        changes=applied_styles,
    )
    output_result(receipt, as_json, quiet)


def _emit_invalid_input(msg: str, as_json: bool) -> None:
    if as_json:
        error = structured_error(ErrorCode.INVALID_INPUT, msg)
        print(json.dumps(error, indent=2), file=sys.stderr)
    else:
        error_console.print(f"[red]Error: {msg}[/red]")
    sys.exit(1)


@docs.command("paragraph-style")
@click.argument("document_id")
@click.option("--start", type=int, default=None, help="Start index (omit with --all)")
@click.option("--end", type=int, default=None, help="End index (omit with --all)")
@click.option(
    "--all",
    "all_",
    is_flag=True,
    help="Apply across the tab's entire body. Mutually exclusive with --start/--end.",
)
@click.option("--heading", type=int, default=None, help="Heading level 1-6, or 0 for normal")
@click.option(
    "--alignment",
    type=click.Choice(["START", "CENTER", "END", "JUSTIFIED"]),
    default=None,
    help="Text alignment",
)
@click.option("--space-above", type=int, default=None, help="Space above paragraph in points")
@click.option("--space-below", type=int, default=None, help="Space below paragraph in points")
@click.option(
    "--line-spacing", type=int, default=None,
    help="Line spacing as integer percentage (100=single, 115=1.15x, 150=1.5x)",
)
@click.option("--indent-start", type=int, default=None, help="Left indent in points")
@click.option("--indent-end", type=int, default=None, help="Right indent in points")
@click.option("--indent-first-line", type=int, default=None, help="First-line indent in points")
@click.option("--tab", "tab_id", default=None, help="Tab ID or title to target")
@click.option("--quiet", "-q", is_flag=True, help="Suppress success messages")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def paragraph_style_cmd(
    document_id: str,
    start: int | None,
    end: int | None,
    all_: bool,
    heading: int | None,
    alignment: str | None,
    space_above: int | None,
    space_below: int | None,
    line_spacing: int | None,
    indent_start: int | None,
    indent_end: int | None,
    indent_first_line: int | None,
    tab_id: str | None,
    quiet: bool,
    as_json: bool,
) -> None:
    """Apply paragraph styling to a range.

    Examples:

        desk docs paragraph-style <id> --start 1 --end 20 --heading 1

        desk docs paragraph-style <id> --start 1 --end 50 --alignment CENTER

        desk docs paragraph-style <id> --start 1 --end 999 --space-below 8

        desk docs paragraph-style <id> --all --space-below 8

        desk docs paragraph-style <id> --all --line-spacing 150 --tab "Notes"
    """
    if all_ and (start is not None or end is not None):
        _emit_invalid_input(
            "--all is mutually exclusive with --start/--end.",
            as_json,
        )
    if not all_ and (start is None or end is None):
        _emit_invalid_input(
            "Either --all or both --start and --end are required.",
            as_json,
        )

    if heading is not None and (heading < 0 or heading > 6):
        _emit_invalid_input(
            f"Invalid heading level: {heading}. Must be 0 (normal) or 1-6.",
            as_json,
        )

    client = _get_client(as_json)
    resolved_tab_id: str | None = tab_id

    if all_:
        try:
            extent, resolved_tab_id = _with_tab_resolution(
                client, document_id, tab_id, as_json,
                lambda tid: client.get_body_extent(document_id, tid),
            )
        except Exception as e:
            _handle_api_error(e, as_json, {"document_id": document_id, "all": True})
        resolved_start, resolved_end = extent
        if resolved_end <= resolved_start:
            receipt = operation_receipt(
                operation="paragraph_style",
                target={"id": document_id},
                changes={"all": True, "note": "document is empty"},
            )
            output_result(receipt, as_json, quiet)
            return
        start, end = resolved_start, resolved_end

    try:
        _with_tab_resolution(
            client, document_id, resolved_tab_id, as_json,
            lambda tid: client.update_paragraph_style(
                document_id, start, end,
                heading=heading,
                alignment=alignment,
                space_above=space_above,
                space_below=space_below,
                line_spacing=line_spacing,
                indent_start=indent_start,
                indent_end=indent_end,
                indent_first_line=indent_first_line,
                tab_id=tid,
            ),
        )
    except ValueError as e:
        _emit_invalid_input(str(e), as_json)
    except Exception as e:
        _handle_api_error(e, as_json, {"document_id": document_id, "start": start, "end": end})

    applied_styles: dict = {"start": start, "end": end}
    if all_:
        applied_styles["all"] = True
    if heading is not None:
        applied_styles["heading"] = heading
    if alignment is not None:
        applied_styles["alignment"] = alignment
    if space_above is not None:
        applied_styles["space_above"] = space_above
    if space_below is not None:
        applied_styles["space_below"] = space_below
    if line_spacing is not None:
        applied_styles["line_spacing"] = line_spacing
    if indent_start is not None:
        applied_styles["indent_start"] = indent_start
    if indent_end is not None:
        applied_styles["indent_end"] = indent_end
    if indent_first_line is not None:
        applied_styles["indent_first_line"] = indent_first_line

    receipt = operation_receipt(
        operation="paragraph_style",
        target={"id": document_id},
        changes=applied_styles,
    )
    output_result(receipt, as_json, quiet)


# ── Markdown / tables / images ──────────────────────────────────────────

@docs.command("write-markdown")
@click.argument("document_id")
@click.option("--body", "-b", default=None, help="Markdown content inline")
@click.option("--file", "-f", "file_path", help="Read markdown from file")
@click.option("--stdin", is_flag=True, help="Read markdown from stdin")
@click.option("--at", default="end", help="Index to insert at (integer or 'end')")
@click.option("--replace", is_flag=True, help="Replace entire document content")
@click.option("--tab", "tab_id", default=None, help="Tab ID or title to target")
@click.option(
    "--space-above", type=int, default=None,
    help="Space above body paragraphs in points (excludes headings/lists/code)",
)
@click.option(
    "--space-below", type=int, default=None,
    help="Space below body paragraphs in points (excludes headings/lists/code)",
)
@click.option(
    "--line-spacing", type=int, default=None,
    help="Line spacing on body paragraphs as integer percentage (100=single, 150=1.5x)",
)
@click.option(
    "--indent-start", type=int, default=None,
    help="Left indent on body paragraphs in points",
)
@click.option(
    "--indent-end", type=int, default=None,
    help="Right indent on body paragraphs in points",
)
@click.option(
    "--indent-first-line", type=int, default=None,
    help="First-line indent on body paragraphs in points",
)
@click.option("--quiet", "-q", is_flag=True, help="Suppress success messages")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def write_markdown_cmd(
    document_id: str,
    body: str | None,
    file_path: str | None,
    stdin: bool,
    at: str,
    replace: bool,
    tab_id: str | None,
    space_above: int | None,
    space_below: int | None,
    line_spacing: int | None,
    indent_start: int | None,
    indent_end: int | None,
    indent_first_line: int | None,
    quiet: bool,
    as_json: bool,
) -> None:
    """Write markdown content with native Google Docs formatting.

    Converts markdown headings, bold, italic, code, and links to native
    Google Docs styles. Optional spacing/indent flags apply to body
    paragraphs only — headings, list items, and fenced code blocks keep
    their inherited styling.

    Examples:

        desk docs write-markdown <id> --body "# New Section\\n\\nSome **bold** text"

        desk docs write-markdown <id> --file appendix.md --at end

        desk docs write-markdown <id> --file report.md --replace --space-below 8

        desk docs write-markdown <id> --file report.md --line-spacing 115
    """
    try:
        content = _read_content(body, file_path, stdin)
    except (click.UsageError, OSError) as e:
        if as_json:
            error = structured_error(ErrorCode.INVALID_INPUT, str(e))
            print(json.dumps(error, indent=2), file=sys.stderr)
        else:
            error_console.print(f"[red]Error: {e}[/red]")
        sys.exit(1)

    index = _parse_at(at, as_json) if not replace else None
    client = _get_client(as_json)
    try:
        _with_tab_resolution(
            client, document_id, tab_id, as_json,
            lambda tid: client.write_markdown(
                document_id, content,
                index=index, replace=replace, tab_id=tid,
                space_above=space_above,
                space_below=space_below,
                line_spacing=line_spacing,
                indent_start=indent_start,
                indent_end=indent_end,
                indent_first_line=indent_first_line,
            ),
        )
    except ValueError as e:
        _emit_invalid_input(str(e), as_json)
    except Exception as e:
        _handle_api_error(
            e, as_json, {"document_id": document_id, "replace": replace, "at": at}
        )

    changes: dict = {"replace": replace, "at": at, "text_length": len(content)}
    if space_above is not None:
        changes["space_above"] = space_above
    if space_below is not None:
        changes["space_below"] = space_below
    if line_spacing is not None:
        changes["line_spacing"] = line_spacing
    if indent_start is not None:
        changes["indent_start"] = indent_start
    if indent_end is not None:
        changes["indent_end"] = indent_end
    if indent_first_line is not None:
        changes["indent_first_line"] = indent_first_line

    receipt = operation_receipt(
        operation="write_markdown",
        target={"id": document_id},
        changes=changes,
    )
    output_result(receipt, as_json, quiet)


@docs.command("insert-table")
@click.argument("document_id")
@click.option("--rows", required=True, type=int, help="Number of rows")
@click.option("--cols", required=True, type=int, help="Number of columns")
@click.option("--at", default="end", help="Index to insert at (integer or 'end')")
@click.option("--tab", "tab_id", default=None, help="Tab ID or title to target")
@click.option("--quiet", "-q", is_flag=True, help="Suppress success messages")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def insert_table_cmd(
    document_id: str, rows: int, cols: int, at: str,
    tab_id: str | None, quiet: bool, as_json: bool,
) -> None:
    """Insert a table into a document.

    Examples:

        desk docs insert-table <id> --rows 3 --cols 4 --at end

        desk docs insert-table <id> --rows 2 --cols 2 --at 5
    """
    if rows < 1 or cols < 1:
        msg = f"Invalid table dimensions: rows={rows}, cols={cols}. Both must be >= 1."
        if as_json:
            error = structured_error(ErrorCode.INVALID_INPUT, msg)
            print(json.dumps(error, indent=2), file=sys.stderr)
        else:
            error_console.print(f"[red]Error: {msg}[/red]")
        sys.exit(1)

    index = _parse_at(at, as_json)
    client = _get_client(as_json)
    try:
        _with_tab_resolution(
            client, document_id, tab_id, as_json,
            lambda tid: client.insert_table(
                document_id, rows, cols, index=index, tab_id=tid,
            ),
        )
    except Exception as e:
        _handle_api_error(
            e, as_json, {"document_id": document_id, "rows": rows, "cols": cols, "at": at}
        )

    receipt = operation_receipt(
        operation="insert_table",
        target={"id": document_id},
        changes={"rows": rows, "cols": cols, "at": at},
    )
    output_result(receipt, as_json, quiet)


@docs.command("insert-image")
@click.argument("document_id")
@click.option("--uri", required=True, help="Public URL of the image")
@click.option("--at", default="end", help="Index to insert at (integer or 'end')")
@click.option("--width", type=float, default=None, help="Image width in points")
@click.option("--height", type=float, default=None, help="Image height in points")
@click.option("--tab", "tab_id", default=None, help="Tab ID or title to target")
@click.option("--quiet", "-q", is_flag=True, help="Suppress success messages")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def insert_image_cmd(
    document_id: str,
    uri: str,
    at: str,
    width: float | None,
    height: float | None,
    tab_id: str | None,
    quiet: bool,
    as_json: bool,
) -> None:
    """Insert an inline image into a document.

    The image URI must be publicly accessible.

    Examples:

        desk docs insert-image <id> --uri "https://example.com/image.png" --at end

        desk docs insert-image <id> --uri "https://example.com/logo.png" --at 5 --width 200
    """
    index = _parse_at(at, as_json)
    client = _get_client(as_json)
    try:
        _with_tab_resolution(
            client, document_id, tab_id, as_json,
            lambda tid: client.insert_image(
                document_id, uri, index=index, width=width, height=height, tab_id=tid,
            ),
        )
    except Exception as e:
        _handle_api_error(e, as_json, {"document_id": document_id, "uri": uri, "at": at})

    receipt = operation_receipt(
        operation="insert_image",
        target={"id": document_id},
        changes={"uri": uri, "at": at},
    )
    output_result(receipt, as_json, quiet)


# ── Tab management ──────────────────────────────────────────────────────

@docs.command("list-tabs")
@click.argument("document_id")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def list_tabs(document_id: str, as_json: bool) -> None:
    """List all tabs in a document.

    Examples:

        desk docs list-tabs <document-id>
    """
    client = _get_client(as_json)
    try:
        tab_list = client.list_tabs(document_id)
    except Exception as e:
        _handle_api_error(e, as_json, {"document_id": document_id})

    if as_json:
        print(json.dumps(tab_list, indent=2))
        return

    if not tab_list:
        console.print("No tabs found.")
        return

    table = Table(show_header=True)
    table.add_column("Tab ID", width=20)
    table.add_column("Title", width=30)
    table.add_column("Index", width=6, justify="right")
    table.add_column("Parent", width=20)

    for t in tab_list:
        table.add_row(
            t["tabId"],
            t["title"],
            str(t["index"]),
            t.get("parentTabId") or "",
        )

    console.print(table)


@docs.command("add-tab")
@click.argument("document_id")
@click.option("--title", "-t", required=True, help="Title for the new tab")
@click.option("--index", "-i", type=int, default=None, help="Position index")
@click.option("--parent", default=None, help="Parent tab ID for nesting")
@click.option("--quiet", "-q", is_flag=True, help="Suppress success messages")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def add_tab(
    document_id: str, title: str, index: int | None,
    parent: str | None, quiet: bool, as_json: bool,
) -> None:
    """Add a new tab to a document.

    Examples:

        desk docs add-tab <id> --title "Notes"

        desk docs add-tab <id> --title "Appendix" --index 2

        desk docs add-tab <id> --title "Sub-Tab" --parent <parent-tab-id>
    """
    client = _get_client(as_json)
    try:
        result = client.add_tab(document_id, title, index=index, parent_tab_id=parent)
    except Exception as e:
        _handle_api_error(e, as_json, {"document_id": document_id, "title": title})

    receipt = operation_receipt(
        operation="add-tab",
        target={
            "document_id": document_id,
            "tab_id": result.get("tabId"),
            "title": result.get("title"),
        },
        undo_command=f"desk docs delete-tab {document_id} --tab {result.get('tabId')} --yes",
    )
    output_result(receipt, as_json, quiet)


@docs.command("delete-tab")
@click.argument("document_id")
@click.option("--tab", "tab_id", required=True, help="Tab ID or title to delete")
@click.option("--yes", "-y", is_flag=True, help="Skip confirmation prompt")
@click.option("--quiet", "-q", is_flag=True, help="Suppress success messages")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def delete_tab(
    document_id: str, tab_id: str, yes: bool, quiet: bool, as_json: bool,
) -> None:
    """Delete a tab from a document.

    Examples:

        desk docs delete-tab <id> --tab <tab-id>

        desk docs delete-tab <id> --tab "Notes" --yes
    """
    client = _get_client(as_json)

    if not yes:
        if not sys.stdin.isatty():
            if as_json:
                error = structured_error(
                    ErrorCode.INVALID_INPUT,
                    "Non-interactive mode requires --yes flag",
                    suggestions=["Use --yes to confirm deletion in non-interactive mode"],
                )
                print(json.dumps(error, indent=2), file=sys.stderr)
            else:
                error_console.print("[red]Error: Non-interactive mode requires --yes flag[/red]")
            sys.exit(1)
        if not click.confirm(f"Delete tab {tab_id}? This cannot be undone."):
            console.print("[yellow]Cancelled[/yellow]")
            return

    try:
        _, resolved_tab_id = _with_tab_resolution(
            client, document_id, tab_id, as_json,
            lambda tid: client.delete_tab(document_id, tid),
        )
    except Exception as e:
        _handle_api_error(e, as_json, {"document_id": document_id, "tab_id": tab_id})

    receipt = operation_receipt(
        operation="delete-tab",
        target={
            "document_id": document_id,
            "tab_id": resolved_tab_id,
        },
    )
    output_result(receipt, as_json, quiet)


@docs.command("rename-tab")
@click.argument("document_id")
@click.option("--tab", "tab_id", required=True, help="Tab ID or title to rename")
@click.option("--title", "-t", required=True, help="New title for the tab")
@click.option("--quiet", "-q", is_flag=True, help="Suppress success messages")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def rename_tab(
    document_id: str, tab_id: str, title: str, quiet: bool, as_json: bool,
) -> None:
    """Rename a tab.

    Examples:

        desk docs rename-tab <id> --tab <tab-id> --title "New Name"

        desk docs rename-tab <id> --tab "Old Name" --title "New Name"
    """
    client = _get_client(as_json)
    try:
        result, _ = _with_tab_resolution(
            client, document_id, tab_id, as_json,
            lambda tid: client.rename_tab(document_id, tid, title),
        )
    except Exception as e:
        _handle_api_error(
            e, as_json, {"document_id": document_id, "tab_id": tab_id, "title": title}
        )

    receipt = operation_receipt(
        operation="rename-tab",
        target={
            "document_id": document_id,
            "tab_id": result.get("tabId"),
            "title": result.get("title"),
        },
    )
    output_result(receipt, as_json, quiet)
