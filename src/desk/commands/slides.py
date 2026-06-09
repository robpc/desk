"""Slides commands — read, create, and edit Google Slides presentations.

Phase 1 (ADR-026, Idea 054): content CRUD. Slides addresses text and
structural edits by ``objectId``; use ``desk slides inspect <id>`` to discover
the objectIds and placeholder types to target, mirroring ``desk docs inspect``.
"""

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
from desk.console import error_console
from desk.services.slides import PREDEFINED_LAYOUTS, SHAPE_TYPES, SlidesClient

console = Console()


def _get_client(as_json: bool = False) -> SlidesClient:
    """Get authenticated Slides client or exit."""
    creds = get_credentials()
    if not creds:
        reason, error_code = get_last_auth_failure()
        if as_json:
            code = ErrorCode(error_code) if error_code else ErrorCode.AUTH_REQUIRED
            error = structured_error(code, reason or "Not authenticated")
            print(json.dumps(error, indent=2), file=sys.stderr)
        else:
            error_console.print("[red]Not authenticated.[/red]")
            if reason:
                error_console.print(f"[yellow]{escape(reason)}[/yellow]")
            else:
                error_console.print("Run: [cyan]desk setup[/cyan]")
        sys.exit(1)
    return SlidesClient(creds)


def _handle_api_error(e: Exception, as_json: bool, context: dict | None = None) -> None:
    """Handle API errors with structured output when --json is used."""
    raw_error = str(e)
    error_msg = parse_api_error(raw_error)

    if "not found" in raw_error.lower() or "404" in raw_error:
        code = ErrorCode.PRESENTATION_NOT_FOUND
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


@click.group()
def slides() -> None:
    """Google Slides — read and edit presentations."""
    pass


# ── Presentation creation ───────────────────────────────────────────────

@slides.command()
@click.argument("title")
@click.option("--quiet", "-q", is_flag=True, help="Suppress success messages")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def create(title: str, quiet: bool, as_json: bool) -> None:
    """Create a new Google Slides presentation.

    The new deck starts with a single default slide. Use `desk slides add-slide`
    and `desk slides insert-text` to populate it.

    Examples:

        desk slides create "Q3 Review"
    """
    client = _get_client(as_json)
    try:
        result = client.create(title)
    except Exception as e:
        _handle_api_error(e, as_json, {"title": title})

    receipt = operation_receipt(
        operation="create",
        target={
            "id": result.get("presentationId"),
            "title": result.get("title"),
            "link": result.get("webViewLink"),
        },
        changes={"slide_count": result.get("slideCount")},
    )
    output_result(receipt, as_json, quiet)


# ── Read / inspect / export ───────────────────────────────────────────────

@slides.command()
@click.argument("presentation_id")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def read(presentation_id: str, as_json: bool) -> None:
    """Read a presentation's text content, slide by slide.

    Examples:

        desk slides read <presentation-id>
    """
    client = _get_client(as_json)
    try:
        result = client.read(presentation_id)
    except Exception as e:
        _handle_api_error(e, as_json, {"presentation_id": presentation_id})

    if as_json:
        print(json.dumps(result, indent=2))
        return

    console.print(f"[bold]{result['title']}[/bold]")
    console.print(f"[dim]{result['slideCount']} slide(s)[/dim]")
    for slide in result["slides"]:
        console.print()
        console.print(f"[cyan]Slide {slide['index']}[/cyan] [dim]({slide['objectId']})[/dim]")
        if slide["text"]:
            console.print(slide["text"])
        else:
            console.print("[dim](no text)[/dim]")


@slides.command("inspect")
@click.argument("presentation_id")
@click.option("--quiet", "-q", is_flag=True, help="Suppress output")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def inspect_cmd(presentation_id: str, quiet: bool, as_json: bool) -> None:
    """Inspect presentation structure with objectIds.

    Shows each slide's objectId and its page elements (type, objectId,
    placeholder type, and preview text). Use this to find the objectId to
    target with insert-text or delete-object.

    Examples:

        desk slides inspect <presentation-id>
    """
    client = _get_client(as_json)
    try:
        result = client.inspect(presentation_id)
    except Exception as e:
        _handle_api_error(e, as_json, {"presentation_id": presentation_id})

    if as_json:
        print(json.dumps(result, indent=2))
        return

    if quiet:
        return

    console.print(f"[bold]{result['title']}[/bold]")
    console.print(f"[dim]{result['slideCount']} slide(s)[/dim]")

    for slide in result["slides"]:
        console.print()
        console.print(
            f"[cyan]Slide {slide['index']}[/cyan] [dim]{slide['objectId']}[/dim]"
        )
        if not slide["elements"]:
            console.print("  [dim](no elements)[/dim]")
        for elem in slide["elements"]:
            etype = elem["type"]
            oid = elem["objectId"]
            if etype == "shape":
                placeholder = elem.get("placeholder")
                label = placeholder or elem.get("shapeType", "SHAPE")
                text_preview = elem.get("text", "")
                if text_preview:
                    console.print(
                        f"  [yellow]{label}[/yellow] [dim]{oid}[/dim] "
                        f"{escape(text_preview[:80])}"
                    )
                else:
                    console.print(
                        f"  [yellow]{label}[/yellow] [dim]{oid}[/dim] [dim](empty)[/dim]"
                    )
            elif etype == "table":
                rows = elem.get("rows", 0)
                cols = elem.get("columns", 0)
                console.print(
                    f"  [magenta]TABLE[/magenta] [dim]{oid}[/dim] {rows}x{cols}"
                )
            else:
                console.print(
                    f"  [blue]{etype.upper()}[/blue] [dim]{oid}[/dim]"
                )


@slides.command()
@click.argument("presentation_id")
@click.argument("dest", type=click.Path())
@click.option(
    "--format",
    "-f",
    "fmt",
    type=click.Choice(["pdf", "pptx", "txt"]),
    default="pdf",
    help="Export format",
)
@click.option("--quiet", "-q", is_flag=True, help="Suppress success messages")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def export(presentation_id: str, dest: str, fmt: str, quiet: bool, as_json: bool) -> None:
    """Export a presentation to a different format.

    Examples:

        desk slides export <id> deck.pdf

        desk slides export <id> deck.pptx --format pptx
    """
    from pathlib import Path

    client = _get_client(as_json)
    try:
        content = client.export(presentation_id, fmt=fmt)
    except Exception as e:
        _handle_api_error(e, as_json, {"presentation_id": presentation_id, "format": fmt})

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
                suggestions=[
                    "Check that the destination path is writable",
                    "Check disk space",
                ],
            )
            print(json.dumps(error, indent=2), file=sys.stderr)
        else:
            error_console.print(f"[red]Error writing file: {e}[/red]")
        sys.exit(1)

    receipt = operation_receipt(
        operation="export",
        target={
            "id": presentation_id,
            "format": fmt,
            "local_path": str(dest_path),
        },
    )
    output_result(receipt, as_json, quiet)


# ── Slide structure ───────────────────────────────────────────────────────

@slides.command("add-slide")
@click.argument("presentation_id")
@click.option(
    "--layout",
    type=click.Choice(PREDEFINED_LAYOUTS),
    default="TITLE_AND_BODY",
    help="Predefined slide layout",
)
@click.option("--index", "-i", type=int, default=None, help="0-based insertion position")
@click.option("--quiet", "-q", is_flag=True, help="Suppress success messages")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def add_slide(
    presentation_id: str, layout: str, index: int | None, quiet: bool, as_json: bool,
) -> None:
    """Add a slide with a predefined layout.

    After adding, run `desk slides inspect <id>` to find the new slide's
    placeholder objectIds, then `desk slides insert-text` to fill them.

    Examples:

        desk slides add-slide <id>

        desk slides add-slide <id> --layout TITLE_ONLY

        desk slides add-slide <id> --layout BLANK --index 0
    """
    if index is not None and index < 0:
        msg = "--index must be >= 0"
        if as_json:
            error = structured_error(ErrorCode.INVALID_INPUT, msg)
            print(json.dumps(error, indent=2), file=sys.stderr)
        else:
            error_console.print(f"[red]Error: {msg}[/red]")
        sys.exit(1)

    client = _get_client(as_json)
    try:
        result = client.add_slide(presentation_id, layout=layout, index=index)
    except Exception as e:
        _handle_api_error(e, as_json, {"presentation_id": presentation_id, "layout": layout})

    receipt = operation_receipt(
        operation="add-slide",
        target={"id": presentation_id, "slide_object_id": result.get("objectId")},
        changes={"layout": layout, "index": index},
        undo_command=(
            f"desk slides delete-object {presentation_id} {result.get('objectId')} --yes"
        ),
    )
    output_result(receipt, as_json, quiet)


@slides.command("delete-slide")
@click.argument("presentation_id")
@click.argument("slide")
@click.option("--yes", "-y", is_flag=True, help="Skip confirmation prompt")
@click.option("--quiet", "-q", is_flag=True, help="Suppress success messages")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def delete_slide(
    presentation_id: str, slide: str, yes: bool, quiet: bool, as_json: bool,
) -> None:
    """Delete a slide by 0-based index or objectId.

    Examples:

        desk slides delete-slide <id> 2

        desk slides delete-slide <id> <slide-object-id> --yes
    """
    if not _confirm_destructive(f"Delete slide {slide}? This cannot be undone.", yes, as_json):
        return

    client = _get_client(as_json)
    try:
        result = client.delete_slide(presentation_id, slide)
    except Exception as e:
        _handle_api_error(e, as_json, {"presentation_id": presentation_id, "slide": slide})

    receipt = operation_receipt(
        operation="delete-slide",
        target={"id": presentation_id, "slide_object_id": result.get("objectId")},
    )
    output_result(receipt, as_json, quiet)


@slides.command("delete-object")
@click.argument("presentation_id")
@click.argument("object_id")
@click.option("--yes", "-y", is_flag=True, help="Skip confirmation prompt")
@click.option("--quiet", "-q", is_flag=True, help="Suppress success messages")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def delete_object(
    presentation_id: str, object_id: str, yes: bool, quiet: bool, as_json: bool,
) -> None:
    """Delete a page element (shape, image, table) by objectId.

    Find objectIds with `desk slides inspect <id>`.

    Examples:

        desk slides delete-object <id> <object-id> --yes
    """
    if not _confirm_destructive(
        f"Delete object {object_id}? This cannot be undone.", yes, as_json
    ):
        return

    client = _get_client(as_json)
    try:
        result = client.delete_object(presentation_id, object_id)
    except Exception as e:
        _handle_api_error(
            e, as_json, {"presentation_id": presentation_id, "object_id": object_id}
        )

    receipt = operation_receipt(
        operation="delete-object",
        target={"id": presentation_id, "object_id": result.get("objectId")},
    )
    output_result(receipt, as_json, quiet)


@slides.command("duplicate-slide")
@click.argument("presentation_id")
@click.argument("slide")
@click.option("--quiet", "-q", is_flag=True, help="Suppress success messages")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def duplicate_slide(
    presentation_id: str, slide: str, quiet: bool, as_json: bool,
) -> None:
    """Duplicate a slide by 0-based index or objectId.

    Useful for reusing a template slide's structure.

    Examples:

        desk slides duplicate-slide <id> 0
    """
    client = _get_client(as_json)
    try:
        result = client.duplicate_slide(presentation_id, slide)
    except Exception as e:
        _handle_api_error(e, as_json, {"presentation_id": presentation_id, "slide": slide})

    receipt = operation_receipt(
        operation="duplicate-slide",
        target={"id": presentation_id, "slide_object_id": result.get("objectId")},
        changes={"source_object_id": result.get("sourceObjectId")},
        undo_command=(
            f"desk slides delete-object {presentation_id} {result.get('objectId')} --yes"
        ),
    )
    output_result(receipt, as_json, quiet)


@slides.command("move-slide")
@click.argument("presentation_id")
@click.argument("slide")
@click.option("--to", "insertion_index", required=True, type=int, help="0-based target position")
@click.option("--quiet", "-q", is_flag=True, help="Suppress success messages")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def move_slide(
    presentation_id: str, slide: str, insertion_index: int, quiet: bool, as_json: bool,
) -> None:
    """Reorder a slide to a new 0-based position.

    Examples:

        desk slides move-slide <id> 3 --to 0
    """
    if insertion_index < 0:
        msg = "--to must be >= 0"
        if as_json:
            error = structured_error(ErrorCode.INVALID_INPUT, msg)
            print(json.dumps(error, indent=2), file=sys.stderr)
        else:
            error_console.print(f"[red]Error: {msg}[/red]")
        sys.exit(1)

    client = _get_client(as_json)
    try:
        result = client.move_slide(presentation_id, slide, insertion_index)
    except Exception as e:
        _handle_api_error(
            e, as_json,
            {"presentation_id": presentation_id, "slide": slide, "to": insertion_index},
        )

    receipt = operation_receipt(
        operation="move-slide",
        target={"id": presentation_id, "slide_object_id": result.get("objectId")},
        changes={"insertion_index": insertion_index},
    )
    output_result(receipt, as_json, quiet)


# ── Text ───────────────────────────────────────────────────────────────────

@slides.command("insert-text")
@click.argument("presentation_id")
@click.argument("object_id")
@click.argument("text")
@click.option(
    "--at", type=int, default=0,
    help="0-based character index within the shape's text (default 0)",
)
@click.option("--quiet", "-q", is_flag=True, help="Suppress success messages")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def insert_text(
    presentation_id: str, object_id: str, text: str, at: int, quiet: bool, as_json: bool,
) -> None:
    """Insert text into a shape or placeholder by objectId.

    Find the target objectId with `desk slides inspect <id>` — typically a
    placeholder such as TITLE or BODY on a freshly added slide.

    Examples:

        desk slides insert-text <id> <object-id> "Quarterly Review"

        desk slides insert-text <id> <object-id> "Appended" --at 10
    """
    if at < 0:
        msg = "--at must be >= 0"
        if as_json:
            error = structured_error(ErrorCode.INVALID_INPUT, msg)
            print(json.dumps(error, indent=2), file=sys.stderr)
        else:
            error_console.print(f"[red]Error: {msg}[/red]")
        sys.exit(1)

    client = _get_client(as_json)
    try:
        client.insert_text(presentation_id, object_id, text, index=at)
    except Exception as e:
        _handle_api_error(
            e, as_json, {"presentation_id": presentation_id, "object_id": object_id}
        )

    receipt = operation_receipt(
        operation="insert-text",
        target={"id": presentation_id, "object_id": object_id},
        changes={"at": at, "text_length": len(text)},
    )
    output_result(receipt, as_json, quiet)


@slides.command("replace-text")
@click.argument("presentation_id")
@click.argument("find")
@click.argument("replace")
@click.option("--ignore-case", is_flag=True, help="Case-insensitive find")
@click.option("--quiet", "-q", is_flag=True, help="Suppress success messages")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def replace_text(
    presentation_id: str, find: str, replace: str,
    ignore_case: bool, quiet: bool, as_json: bool,
) -> None:
    """Find and replace text across the whole presentation.

    Examples:

        desk slides replace-text <id> "{{name}}" "Robert"

        desk slides replace-text <id> "draft" "final" --ignore-case
    """
    client = _get_client(as_json)
    try:
        result = client.replace_text(
            presentation_id, find, replace, match_case=not ignore_case,
        )
    except Exception as e:
        _handle_api_error(e, as_json, {"presentation_id": presentation_id, "find": find})

    receipt = operation_receipt(
        operation="replace-text",
        target={"id": presentation_id},
        changes={
            "find": find,
            "replace": replace,
            "ignore_case": ignore_case,
            "occurrences_changed": result["occurrences_changed"],
        },
    )
    output_result(receipt, as_json, quiet)


# ── Visual elements (Phase 2, ADR-027) ──────────────────────────────────────

@slides.command("insert-image")
@click.argument("presentation_id")
@click.argument("slide")
@click.option("--url", required=True, help="Publicly accessible image URL")
@click.option("--x", type=float, default=None, help="Left position in points")
@click.option("--y", type=float, default=None, help="Top position in points")
@click.option("--width", type=float, default=None, help="Width in points")
@click.option("--height", type=float, default=None, help="Height in points")
@click.option("--quiet", "-q", is_flag=True, help="Suppress success messages")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def insert_image(
    presentation_id: str, slide: str, url: str,
    x: float | None, y: float | None, width: float | None, height: float | None,
    quiet: bool, as_json: bool,
) -> None:
    """Insert an image onto a slide from a public URL.

    SLIDE is a 0-based index or a slide objectId (see `desk slides inspect`).
    Position/size are in points and optional.

    Examples:

        desk slides insert-image <id> 0 --url "https://example.com/logo.png"

        desk slides insert-image <id> 1 --url "https://x/y.png" --x 100 --y 80 --width 200
    """
    client = _get_client(as_json)
    try:
        result = client.insert_image(
            presentation_id, slide, url, x=x, y=y, width=width, height=height,
        )
    except Exception as e:
        _handle_api_error(
            e, as_json, {"presentation_id": presentation_id, "slide": slide, "url": url}
        )

    receipt = operation_receipt(
        operation="insert-image",
        target={"id": presentation_id, "object_id": result.get("objectId")},
        changes={"slide_object_id": result.get("slideObjectId"), "url": url},
        undo_command=(
            f"desk slides delete-object {presentation_id} {result.get('objectId')} --yes"
        ),
    )
    output_result(receipt, as_json, quiet)


@slides.command("insert-table")
@click.argument("presentation_id")
@click.argument("slide")
@click.option("--rows", required=True, type=int, help="Number of rows")
@click.option("--cols", required=True, type=int, help="Number of columns")
@click.option("--x", type=float, default=None, help="Left position in points")
@click.option("--y", type=float, default=None, help="Top position in points")
@click.option("--width", type=float, default=None, help="Width in points")
@click.option("--height", type=float, default=None, help="Height in points")
@click.option("--quiet", "-q", is_flag=True, help="Suppress success messages")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def insert_table(
    presentation_id: str, slide: str, rows: int, cols: int,
    x: float | None, y: float | None, width: float | None, height: float | None,
    quiet: bool, as_json: bool,
) -> None:
    """Insert a table onto a slide.

    SLIDE is a 0-based index or a slide objectId. Omit position/size to let the
    API place and size the table.

    Examples:

        desk slides insert-table <id> 0 --rows 3 --cols 4

        desk slides insert-table <id> 1 --rows 2 --cols 2 --x 50 --y 100
    """
    if rows < 1 or cols < 1:
        msg = f"Invalid table dimensions: rows={rows}, cols={cols}. Both must be >= 1."
        if as_json:
            error = structured_error(ErrorCode.INVALID_INPUT, msg)
            print(json.dumps(error, indent=2), file=sys.stderr)
        else:
            error_console.print(f"[red]Error: {msg}[/red]")
        sys.exit(1)

    client = _get_client(as_json)
    try:
        result = client.insert_table(
            presentation_id, slide, rows, cols, x=x, y=y, width=width, height=height,
        )
    except Exception as e:
        _handle_api_error(
            e, as_json,
            {"presentation_id": presentation_id, "slide": slide, "rows": rows, "cols": cols},
        )

    receipt = operation_receipt(
        operation="insert-table",
        target={"id": presentation_id, "object_id": result.get("objectId")},
        changes={"slide_object_id": result.get("slideObjectId"), "rows": rows, "cols": cols},
        undo_command=(
            f"desk slides delete-object {presentation_id} {result.get('objectId')} --yes"
        ),
    )
    output_result(receipt, as_json, quiet)


@slides.command("insert-shape")
@click.argument("presentation_id")
@click.argument("slide")
@click.option(
    "--type", "shape_type",
    type=click.Choice(SHAPE_TYPES),
    default="TEXT_BOX",
    help="Shape type",
)
@click.option("--text", default=None, help="Text to place in the shape")
@click.option("--x", type=float, default=None, help="Left position in points")
@click.option("--y", type=float, default=None, help="Top position in points")
@click.option("--width", type=float, default=None, help="Width in points")
@click.option("--height", type=float, default=None, help="Height in points")
@click.option("--quiet", "-q", is_flag=True, help="Suppress success messages")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def insert_shape(
    presentation_id: str, slide: str, shape_type: str, text: str | None,
    x: float | None, y: float | None, width: float | None, height: float | None,
    quiet: bool, as_json: bool,
) -> None:
    """Insert a shape (default text box) onto a slide, optionally with text.

    SLIDE is a 0-based index or a slide objectId.

    Examples:

        desk slides insert-shape <id> 0 --text "Key takeaway"

        desk slides insert-shape <id> 1 --type ELLIPSE --x 200 --y 120 --width 150
    """
    client = _get_client(as_json)
    try:
        result = client.insert_shape(
            presentation_id, slide, shape_type=shape_type, text=text,
            x=x, y=y, width=width, height=height,
        )
    except Exception as e:
        _handle_api_error(
            e, as_json,
            {"presentation_id": presentation_id, "slide": slide, "type": shape_type},
        )

    changes: dict = {"slide_object_id": result.get("slideObjectId"), "type": shape_type}
    if text:
        changes["text_length"] = len(text)

    receipt = operation_receipt(
        operation="insert-shape",
        target={"id": presentation_id, "object_id": result.get("objectId")},
        changes=changes,
        undo_command=(
            f"desk slides delete-object {presentation_id} {result.get('objectId')} --yes"
        ),
    )
    output_result(receipt, as_json, quiet)


# ── Helpers ────────────────────────────────────────────────────────────────

def _confirm_destructive(prompt: str, yes: bool, as_json: bool) -> bool:
    """Confirm a destructive action. Returns True to proceed, False to cancel.

    Requires --yes in non-interactive mode (mirrors `desk docs delete-tab`).
    """
    if yes:
        return True
    if not sys.stdin.isatty():
        if as_json:
            error = structured_error(
                ErrorCode.INVALID_INPUT,
                "Non-interactive mode requires --yes flag",
                suggestions=["Use --yes to confirm in non-interactive mode"],
            )
            print(json.dumps(error, indent=2), file=sys.stderr)
        else:
            error_console.print("[red]Error: Non-interactive mode requires --yes flag[/red]")
        sys.exit(1)
    if not click.confirm(prompt):
        console.print("[yellow]Cancelled[/yellow]")
        return False
    return True
