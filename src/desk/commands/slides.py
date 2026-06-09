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
    is_scope_error,
    operation_receipt,
    output_result,
    parse_api_error,
    structured_error,
)
from desk.auth import get_credentials, get_last_auth_failure
from desk.console import error_console
from desk.services.slides import (
    ARRANGE_MODES,
    PREDEFINED_LAYOUTS,
    REGIONS,
    SHAPE_TYPES,
    SlidesClient,
)

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

    if is_scope_error(raw_error):
        # Missing scope (e.g. token predates the presentations scope) — tell the
        # user to re-auth, not to "request access". See ADR-030.
        code = ErrorCode.INSUFFICIENT_SCOPES
    elif "not found" in raw_error.lower() or "404" in raw_error:
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
        if slide.get("notes"):
            console.print(f"[dim]Notes:[/dim] {slide['notes']}")


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

    With --json, the response includes the new slide's placeholder objectIds and
    types, so you can `insert-text` into them directly without a separate inspect.

    Layout note: placeholders depend on the layout. SECTION_HEADER is title-only;
    for a section slide with a tagline use SECTION_TITLE_AND_DESCRIPTION (TITLE +
    SUBTITLE + BODY). TITLE_AND_BODY gives TITLE + BODY; BLANK has none.

    Examples:

        desk slides add-slide <id>

        desk slides add-slide <id> --layout TITLE_ONLY

        desk slides add-slide <id> --layout SECTION_TITLE_AND_DESCRIPTION

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
        changes={
            "layout": layout,
            "index": index,
            # Hand back placeholder objectIds so the caller can insert-text
            # without a separate inspect (ADR-030).
            "placeholders": result.get("placeholders", []),
        },
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


@slides.command("set-notes")
@click.argument("presentation_id")
@click.argument("slide")
@click.argument("text")
@click.option(
    "--mode", type=click.Choice(["replace", "append"]), default="replace",
    help="Replace existing notes (default) or append to them",
)
@click.option("--quiet", "-q", is_flag=True, help="Suppress success messages")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def set_notes(
    presentation_id: str, slide: str, text: str, mode: str, quiet: bool, as_json: bool,
) -> None:
    """Set a slide's speaker notes.

    SLIDE is a 0-based index or a slide objectId. Use `desk slides read` to see
    existing notes per slide.

    Examples:

        desk slides set-notes <id> 0 "Open with the Q3 revenue number."

        desk slides set-notes <id> 2 "Also mention churn." --mode append
    """
    client = _get_client(as_json)
    try:
        result = client.set_notes(presentation_id, slide, text, mode=mode)
    except Exception as e:
        _handle_api_error(e, as_json, {"presentation_id": presentation_id, "slide": slide})

    receipt = operation_receipt(
        operation="set-notes",
        target={"id": presentation_id, "slide_object_id": result.get("slideObjectId")},
        changes={"mode": mode, "text_length": len(text)},
    )
    output_result(receipt, as_json, quiet)


# ── Visual elements (Phase 2, ADR-027) ──────────────────────────────────────

@slides.command("insert-image")
@click.argument("presentation_id")
@click.argument("slide")
@click.option("--url", required=True, help="Publicly accessible image URL")
@click.option("--region", type=click.Choice(REGIONS), default=None,
              help="Named layout region (overrides --x/--y/--width/--height)")
@click.option("--x", type=float, default=None, help="Left position in points")
@click.option("--y", type=float, default=None, help="Top position in points")
@click.option("--width", type=float, default=None, help="Width in points")
@click.option("--height", type=float, default=None, help="Height in points")
@click.option("--quiet", "-q", is_flag=True, help="Suppress success messages")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def insert_image(
    presentation_id: str, slide: str, url: str, region: str | None,
    x: float | None, y: float | None, width: float | None, height: float | None,
    quiet: bool, as_json: bool,
) -> None:
    """Insert an image onto a slide from a public URL.

    SLIDE is a 0-based index or a slide objectId (see `desk slides inspect`).
    Position by --region (e.g. right-half) or in points; both are optional.

    Examples:

        desk slides insert-image <id> 0 --url "https://example.com/logo.png"

        desk slides insert-image <id> 0 --url "https://x/y.png" --region top-right

        desk slides insert-image <id> 1 --url "https://x/y.png" --x 100 --y 80 --width 200
    """
    _reject_region_with_coords(region, x, y, width, height, as_json)
    client = _get_client(as_json)
    try:
        result = client.insert_image(
            presentation_id, slide, url, x=x, y=y, width=width, height=height,
            region=region,
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
@click.option("--region", type=click.Choice(REGIONS), default=None,
              help="Named layout region (overrides --x/--y/--width/--height)")
@click.option("--x", type=float, default=None, help="Left position in points")
@click.option("--y", type=float, default=None, help="Top position in points")
@click.option("--width", type=float, default=None, help="Width in points")
@click.option("--height", type=float, default=None, help="Height in points")
@click.option("--quiet", "-q", is_flag=True, help="Suppress success messages")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def insert_table(
    presentation_id: str, slide: str, rows: int, cols: int, region: str | None,
    x: float | None, y: float | None, width: float | None, height: float | None,
    quiet: bool, as_json: bool,
) -> None:
    """Insert a table onto a slide.

    SLIDE is a 0-based index or a slide objectId. Position by --region or in
    points; omit both to let the API place and size the table.

    Examples:

        desk slides insert-table <id> 0 --rows 3 --cols 4

        desk slides insert-table <id> 0 --rows 3 --cols 4 --region bottom-half

        desk slides insert-table <id> 1 --rows 2 --cols 2 --x 50 --y 100
    """
    _reject_region_with_coords(region, x, y, width, height, as_json)
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
            region=region,
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
@click.option("--region", type=click.Choice(REGIONS), default=None,
              help="Named layout region (overrides --x/--y/--width/--height)")
@click.option("--x", type=float, default=None, help="Left position in points")
@click.option("--y", type=float, default=None, help="Top position in points")
@click.option("--width", type=float, default=None, help="Width in points")
@click.option("--height", type=float, default=None, help="Height in points")
@click.option("--quiet", "-q", is_flag=True, help="Suppress success messages")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def insert_shape(
    presentation_id: str, slide: str, shape_type: str, text: str | None,
    region: str | None,
    x: float | None, y: float | None, width: float | None, height: float | None,
    quiet: bool, as_json: bool,
) -> None:
    """Insert a shape (default text box) onto a slide, optionally with text.

    SLIDE is a 0-based index or a slide objectId. Position by --region or points.

    Examples:

        desk slides insert-shape <id> 0 --text "Key takeaway"

        desk slides insert-shape <id> 0 --text "Footnote" --region bottom

        desk slides insert-shape <id> 1 --type ELLIPSE --x 200 --y 120 --width 150
    """
    _reject_region_with_coords(region, x, y, width, height, as_json)
    client = _get_client(as_json)
    try:
        result = client.insert_shape(
            presentation_id, slide, shape_type=shape_type, text=text,
            x=x, y=y, width=width, height=height, region=region,
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


# ── Styling & layout (Phase 3a, ADR-028) ────────────────────────────────────

@slides.command("style")
@click.argument("presentation_id")
@click.argument("object_id")
@click.option("--bold/--no-bold", default=None, help="Set bold")
@click.option("--italic/--no-italic", default=None, help="Set italic")
@click.option("--underline/--no-underline", default=None, help="Set underline")
@click.option("--font-size", type=float, default=None, help="Font size in points")
@click.option("--font", default=None, help="Font family name")
@click.option("--color", default=None, help="Text color: #RRGGBB or a theme name")
@click.option("--start", type=int, default=None, help="Start char index (range)")
@click.option("--end", type=int, default=None, help="End char index (range)")
@click.option("--quiet", "-q", is_flag=True, help="Suppress success messages")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def style_cmd(
    presentation_id: str, object_id: str,
    bold: bool | None, italic: bool | None, underline: bool | None,
    font_size: float | None, font: str | None, color: str | None,
    start: int | None, end: int | None,
    quiet: bool, as_json: bool,
) -> None:
    """Style the text of a shape (by objectId).

    Styles the whole shape's text by default; pass --start/--end for a range.
    Find objectIds with `desk slides inspect <id>`.

    Examples:

        desk slides style <id> <object-id> --bold --font-size 24

        desk slides style <id> <object-id> --color "#1A73E8" --font "Roboto"

        desk slides style <id> <object-id> --italic --color ACCENT1
    """
    if (start is None) != (end is None):
        _emit_invalid_input("Provide both --start and --end, or neither.", as_json)

    client = _get_client(as_json)
    try:
        client.style_text(
            presentation_id, object_id,
            bold=bold, italic=italic, underline=underline,
            font_size=font_size, font_family=font, color=color,
            start=start, end=end,
        )
    except ValueError as e:
        _emit_invalid_input(str(e), as_json)
    except Exception as e:
        _handle_api_error(
            e, as_json, {"presentation_id": presentation_id, "object_id": object_id}
        )

    changes: dict = {}
    for key, val in (
        ("bold", bold), ("italic", italic), ("underline", underline),
        ("font_size", font_size), ("font", font), ("color", color),
    ):
        if val is not None:
            changes[key] = val
    if start is not None:
        changes["start"], changes["end"] = start, end

    receipt = operation_receipt(
        operation="style",
        target={"id": presentation_id, "object_id": object_id},
        changes=changes,
    )
    output_result(receipt, as_json, quiet)


@slides.command("format")
@click.argument("presentation_id")
@click.argument("object_id")
@click.option("--fill", default=None, help="Fill color (#RRGGBB or theme name; shapes only)")
@click.option("--outline", default=None, help="Outline color (#RRGGBB or theme name)")
@click.option("--outline-weight", type=float, default=None, help="Outline weight in points")
@click.option("--quiet", "-q", is_flag=True, help="Suppress success messages")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def format_cmd(
    presentation_id: str, object_id: str,
    fill: str | None, outline: str | None, outline_weight: float | None,
    quiet: bool, as_json: bool,
) -> None:
    """Apply fill/outline to a shape or image (by objectId).

    Shapes accept --fill and --outline; images accept --outline only.

    Examples:

        desk slides format <id> <object-id> --fill "#FFF3CD" --outline "#856404"

        desk slides format <id> <object-id> --outline ACCENT2 --outline-weight 2
    """
    client = _get_client(as_json)
    try:
        result = client.format_element(
            presentation_id, object_id,
            fill=fill, outline=outline, outline_weight=outline_weight,
        )
    except ValueError as e:
        _emit_invalid_input(str(e), as_json)
    except Exception as e:
        _handle_api_error(
            e, as_json, {"presentation_id": presentation_id, "object_id": object_id}
        )

    changes: dict = {"element_type": result.get("elementType")}
    if fill is not None:
        changes["fill"] = fill
    if outline is not None:
        changes["outline"] = outline
    if outline_weight is not None:
        changes["outline_weight"] = outline_weight

    receipt = operation_receipt(
        operation="format",
        target={"id": presentation_id, "object_id": object_id},
        changes=changes,
    )
    output_result(receipt, as_json, quiet)


@slides.command("place")
@click.argument("presentation_id")
@click.argument("object_id")
@click.option("--region", type=click.Choice(REGIONS), required=True,
              help="Named layout region to move/fit the element into")
@click.option("--quiet", "-q", is_flag=True, help="Suppress success messages")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def place_cmd(
    presentation_id: str, object_id: str, region: str, quiet: bool, as_json: bool,
) -> None:
    """Move and fit an existing element into a named region.

    Describe where you want it ("top-right", "left-half"); the command computes
    the geometry. Find objectIds with `desk slides inspect <id>`.

    Examples:

        desk slides place <id> <object-id> --region center

        desk slides place <id> <object-id> --region right-half
    """
    client = _get_client(as_json)
    try:
        client.place_element(presentation_id, object_id, region)
    except Exception as e:
        _handle_api_error(
            e, as_json,
            {"presentation_id": presentation_id, "object_id": object_id, "region": region},
        )

    receipt = operation_receipt(
        operation="place",
        target={"id": presentation_id, "object_id": object_id},
        changes={"region": region},
    )
    output_result(receipt, as_json, quiet)


@slides.command("arrange")
@click.argument("presentation_id")
@click.argument("object_ids", nargs=-1, required=True)
@click.option("--as", "mode", type=click.Choice(ARRANGE_MODES), required=True,
              help="Distribution: columns, rows, or grid")
@click.option("--region", type=click.Choice(REGIONS), default=None,
              help="Confine the arrangement to a region (default: whole slide)")
@click.option("--quiet", "-q", is_flag=True, help="Suppress success messages")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def arrange_cmd(
    presentation_id: str, object_ids: tuple[str, ...], mode: str,
    region: str | None, quiet: bool, as_json: bool,
) -> None:
    """Distribute existing elements evenly as columns, rows, or a grid.

    Name the elements and the arrangement; the command does the geometry.
    Order is preserved (row-major for grid). Find objectIds with
    `desk slides inspect <id>`.

    Examples:

        desk slides arrange <id> obj1 obj2 obj3 --as columns

        desk slides arrange <id> a b c d --as grid

        desk slides arrange <id> a b --as rows --region right-half
    """
    client = _get_client(as_json)
    try:
        client.arrange_elements(
            presentation_id, list(object_ids), mode, region=region,
        )
    except ValueError as e:
        _emit_invalid_input(str(e), as_json)
    except Exception as e:
        _handle_api_error(
            e, as_json,
            {"presentation_id": presentation_id, "mode": mode, "count": len(object_ids)},
        )

    changes: dict = {"mode": mode, "count": len(object_ids)}
    if region:
        changes["region"] = region

    receipt = operation_receipt(
        operation="arrange",
        target={"id": presentation_id, "object_ids": list(object_ids)},
        changes=changes,
    )
    output_result(receipt, as_json, quiet)


# ── Helpers ────────────────────────────────────────────────────────────────

def _emit_invalid_input(msg: str, as_json: bool) -> None:
    if as_json:
        error = structured_error(ErrorCode.INVALID_INPUT, msg)
        print(json.dumps(error, indent=2), file=sys.stderr)
    else:
        error_console.print(f"[red]Error: {msg}[/red]")
    sys.exit(1)


def _reject_region_with_coords(
    region: str | None,
    x: float | None, y: float | None,
    width: float | None, height: float | None,
    as_json: bool,
) -> None:
    """Region and explicit coordinates are mutually exclusive (ADR-028)."""
    if region and any(v is not None for v in (x, y, width, height)):
        _emit_invalid_input(
            "--region cannot be combined with --x/--y/--width/--height.", as_json
        )


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
