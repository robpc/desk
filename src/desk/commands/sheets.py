"""Sheets commands — read and update spreadsheets."""

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
from desk.services.sheets import SheetsClient

console = Console()


def _get_client(as_json: bool = False) -> SheetsClient:
    """Get authenticated Sheets client or exit."""
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
    return SheetsClient(creds)


def _handle_api_error(e: Exception, as_json: bool, context: dict | None = None) -> None:
    """Handle API errors with structured output when --json is used."""
    raw_error = str(e)
    error_msg = parse_api_error(raw_error)

    if is_scope_error(raw_error):
        code = ErrorCode.INSUFFICIENT_SCOPES
    elif "not found" in raw_error.lower() or "404" in raw_error:
        code = ErrorCode.SPREADSHEET_NOT_FOUND
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
def sheets() -> None:
    """Google Sheets — read and update spreadsheets."""
    pass


@sheets.command()
@click.argument("spreadsheet_id")
@click.option("--range", "-r", "ranges", multiple=True, help="A1 notation range (repeatable)")
@click.option("--sheet-id", type=int, help="Specific sheet ID to read")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def read(spreadsheet_id: str, ranges: tuple[str, ...], sheet_id: int | None, as_json: bool) -> None:
    """Read data from a spreadsheet.

    Without --range, reads the entire first sheet.

    Examples:

        desk sheets read <spreadsheet-id>

        desk sheets read <id> --range "Sheet1!A1:C10"

        desk sheets read <id> --range "Sheet1!A:A" --range "Sheet1!C:C"
    """
    client = _get_client(as_json)
    try:
        result = client.read(
            spreadsheet_id,
            ranges=list(ranges) if ranges else None,
            sheet_id=sheet_id,
        )
    except Exception as e:
        _handle_api_error(e, as_json, {"spreadsheet_id": spreadsheet_id})

    if as_json:
        print(json.dumps(result, indent=2))
        return

    # Display title if available
    if result.get("title"):
        console.print(f"[bold]{result['title']}[/bold]")
        console.print()

    # Display values as a table
    if "ranges" in result:
        # Multiple ranges
        for r in result["ranges"]:
            console.print(f"[dim]{r['range']}[/dim]")
            _print_values_table(r.get("values", []))
            console.print()
    else:
        if result.get("range"):
            console.print(f"[dim]{result['range']}[/dim]")
        _print_values_table(result.get("values", []))


@sheets.command("update-cell")
@click.argument("spreadsheet_id")
@click.argument("range_")
@click.argument("value")
@click.option("--quiet", "-q", is_flag=True, help="Suppress success messages")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def update_cell(spreadsheet_id: str, range_: str, value: str, quiet: bool, as_json: bool) -> None:
    """Update a single cell value.

    Examples:

        desk sheets update-cell <id> "Sheet1!A1" "Hello"

        desk sheets update-cell <id> "Sheet1!B2" "42"
    """
    client = _get_client(as_json)
    try:
        result = client.update_cell(spreadsheet_id, range_, value)
    except Exception as e:
        _handle_api_error(e, as_json, {"spreadsheet_id": spreadsheet_id, "range": range_})

    receipt = operation_receipt(
        operation="update-cell",
        target={
            "spreadsheet_id": spreadsheet_id,
            "range": result.get("updatedRange"),
            "value": value,
        },
    )
    output_result(receipt, as_json, quiet)


@sheets.command()
@click.argument("title")
@click.option("--quiet", "-q", is_flag=True, help="Suppress success messages")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def create(title: str, quiet: bool, as_json: bool) -> None:
    """Create a new spreadsheet.

    Examples:

        desk sheets create "Q1 Budget"
    """
    client = _get_client(as_json)
    try:
        result = client.create(title)
    except Exception as e:
        _handle_api_error(e, as_json, {"title": title})

    receipt = operation_receipt(
        operation="create",
        target={
            "id": result.get("spreadsheetId"),
            "title": result.get("title"),
            "link": result.get("spreadsheetUrl"),
        },
    )
    output_result(receipt, as_json, quiet)


@sheets.command()
@click.argument("spreadsheet_id")
@click.argument("range_")
@click.argument("values_json")
@click.option("--quiet", "-q", is_flag=True, help="Suppress success messages")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def write(spreadsheet_id: str, range_: str, values_json: str, quiet: bool, as_json: bool) -> None:
    """Write values to a range.

    VALUES_JSON is a JSON 2D array, e.g. '[["A","B"],["1","2"]]'

    Examples:

        desk sheets write <id> "Sheet1!A1:B2" '[["Name","Age"],["Alice","30"]]'
    """
    client = _get_client(as_json)
    try:
        values = json.loads(values_json)
    except json.JSONDecodeError:
        if as_json:
            error = structured_error(
                ErrorCode.INVALID_INPUT,
                "Invalid JSON. Expected a 2D array like '[[\"a\",\"b\"]]'",
                suggestions=["Ensure values are a JSON 2D array", "Check for proper escaping of quotes"],
            )
            print(json.dumps(error, indent=2), file=sys.stderr)
        else:
            error_console.print('[red]Invalid JSON. Expected a 2D array like \'[[]["a","b"]]\'[/red]')
        sys.exit(1)

    try:
        result = client.write(spreadsheet_id, range_, values)
    except Exception as e:
        _handle_api_error(e, as_json, {"spreadsheet_id": spreadsheet_id, "range": range_})

    receipt = operation_receipt(
        operation="write",
        target={
            "spreadsheet_id": spreadsheet_id,
            "range": result.get("updatedRange"),
            "cells_updated": result.get("updatedCells"),
        },
    )
    output_result(receipt, as_json, quiet)


@sheets.command()
@click.argument("spreadsheet_id")
@click.argument("range_")
@click.argument("values_json")
@click.option("--quiet", "-q", is_flag=True, help="Suppress success messages")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def append(spreadsheet_id: str, range_: str, values_json: str, quiet: bool, as_json: bool) -> None:
    """Append rows to a spreadsheet.

    VALUES_JSON is a JSON 2D array of rows to append.

    Examples:

        desk sheets append <id> "Sheet1!A:Z" '[["Alice","30"],["Bob","25"]]'
    """
    client = _get_client(as_json)
    try:
        values = json.loads(values_json)
    except json.JSONDecodeError:
        if as_json:
            error = structured_error(
                ErrorCode.INVALID_INPUT,
                "Invalid JSON. Expected a 2D array like '[[\"a\",\"b\"]]'",
                suggestions=["Ensure values are a JSON 2D array", "Check for proper escaping of quotes"],
            )
            print(json.dumps(error, indent=2), file=sys.stderr)
        else:
            error_console.print('[red]Invalid JSON. Expected a 2D array like \'[[]["a","b"]]\'[/red]')
        sys.exit(1)

    try:
        result = client.append(spreadsheet_id, range_, values)
    except Exception as e:
        _handle_api_error(e, as_json, {"spreadsheet_id": spreadsheet_id, "range": range_})

    receipt = operation_receipt(
        operation="append",
        target={
            "spreadsheet_id": spreadsheet_id,
            "range": result.get("updatedRange"),
            "rows_appended": result.get("updatedRows"),
        },
    )
    output_result(receipt, as_json, quiet)


@sheets.command()
@click.argument("spreadsheet_id")
@click.argument("range_")
@click.option("--quiet", "-q", is_flag=True, help="Suppress success messages")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def clear(spreadsheet_id: str, range_: str, quiet: bool, as_json: bool) -> None:
    """Clear values in a range.

    Examples:

        desk sheets clear <id> "Sheet1!A1:C10"
    """
    client = _get_client(as_json)
    try:
        result = client.clear(spreadsheet_id, range_)
    except Exception as e:
        _handle_api_error(e, as_json, {"spreadsheet_id": spreadsheet_id, "range": range_})

    receipt = operation_receipt(
        operation="clear",
        target={
            "spreadsheet_id": spreadsheet_id,
            "range": result.get("clearedRange"),
        },
    )
    output_result(receipt, as_json, quiet)


@sheets.command("list-sheets")
@click.argument("spreadsheet_id")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def list_sheets(spreadsheet_id: str, as_json: bool) -> None:
    """List all sheets (tabs) in a spreadsheet.

    Examples:

        desk sheets list-sheets <spreadsheet-id>
    """
    client = _get_client(as_json)
    try:
        sheet_list = client.list_sheets(spreadsheet_id)
    except Exception as e:
        _handle_api_error(e, as_json, {"spreadsheet_id": spreadsheet_id})

    if as_json:
        print(json.dumps(sheet_list, indent=2))
        return

    if not sheet_list:
        console.print("No sheets found.")
        return

    table = Table(show_header=True)
    table.add_column("Sheet ID", width=12)
    table.add_column("Name", width=30)
    table.add_column("Index", width=6, justify="right")
    table.add_column("Rows", width=8, justify="right")
    table.add_column("Cols", width=8, justify="right")

    for s in sheet_list:
        table.add_row(
            str(s["sheetId"]),
            s["title"],
            str(s["index"]),
            str(s["rowCount"]),
            str(s["columnCount"]),
        )

    console.print(table)


@sheets.command("add-sheet")
@click.argument("spreadsheet_id")
@click.option("--name", "-n", required=True, help="Name for the new sheet")
@click.option("--index", "-i", type=int, help="Position (0-based)")
@click.option("--quiet", "-q", is_flag=True, help="Suppress success messages")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def add_sheet(spreadsheet_id: str, name: str, index: int | None, quiet: bool, as_json: bool) -> None:
    """Add a new sheet (tab) to a spreadsheet.

    Examples:

        desk sheets add-sheet <id> --name "Q2 Data"

        desk sheets add-sheet <id> --name "Summary" --index 0
    """
    client = _get_client(as_json)
    try:
        result = client.add_sheet(spreadsheet_id, name, index=index)
    except Exception as e:
        _handle_api_error(e, as_json, {"spreadsheet_id": spreadsheet_id, "name": name})

    receipt = operation_receipt(
        operation="add-sheet",
        target={
            "spreadsheet_id": spreadsheet_id,
            "sheet_id": result.get("sheetId"),
            "name": result.get("title"),
        },
        undo_command=f"desk sheets delete-sheet {spreadsheet_id} --sheet-id {result.get('sheetId')} --yes",
    )
    output_result(receipt, as_json, quiet)


@sheets.command("delete-sheet")
@click.argument("spreadsheet_id")
@click.option("--sheet-id", type=int, required=True, help="Sheet ID to delete")
@click.option("--yes", "-y", is_flag=True, help="Skip confirmation prompt")
@click.option("--quiet", "-q", is_flag=True, help="Suppress success messages")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def delete_sheet(spreadsheet_id: str, sheet_id: int, yes: bool, quiet: bool, as_json: bool) -> None:
    """Delete a sheet (tab) from a spreadsheet.

    Examples:

        desk sheets delete-sheet <id> --sheet-id 123456

        desk sheets delete-sheet <id> --sheet-id 123456 --yes
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
        import click as click_module
        if not click_module.confirm(f"Delete sheet {sheet_id}? This cannot be undone."):
            console.print("[yellow]Cancelled[/yellow]")
            return

    try:
        client.delete_sheet(spreadsheet_id, sheet_id)
    except Exception as e:
        _handle_api_error(e, as_json, {"spreadsheet_id": spreadsheet_id, "sheet_id": sheet_id})

    receipt = operation_receipt(
        operation="delete-sheet",
        target={
            "spreadsheet_id": spreadsheet_id,
            "sheet_id": sheet_id,
        },
    )
    output_result(receipt, as_json, quiet)


@sheets.command("rename-sheet")
@click.argument("spreadsheet_id")
@click.option("--sheet-id", type=int, required=True, help="Sheet ID to rename")
@click.option("--name", "-n", required=True, help="New name for the sheet")
@click.option("--quiet", "-q", is_flag=True, help="Suppress success messages")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def rename_sheet(spreadsheet_id: str, sheet_id: int, name: str, quiet: bool, as_json: bool) -> None:
    """Rename a sheet (tab).

    Examples:

        desk sheets rename-sheet <id> --sheet-id 123456 --name "New Name"
    """
    client = _get_client(as_json)
    try:
        result = client.rename_sheet(spreadsheet_id, sheet_id, name)
    except Exception as e:
        _handle_api_error(e, as_json, {"spreadsheet_id": spreadsheet_id, "sheet_id": sheet_id, "name": name})

    receipt = operation_receipt(
        operation="rename-sheet",
        target={
            "spreadsheet_id": spreadsheet_id,
            "sheet_id": sheet_id,
            "name": result.get("title"),
        },
    )
    output_result(receipt, as_json, quiet)


def _print_values_table(values: list[list]) -> None:
    """Print a 2D values array as a Rich table."""
    if not values:
        console.print("[dim]No data[/dim]")
        return

    table = Table(show_header=True, show_lines=True)

    # Use first row as header
    max_cols = max(len(row) for row in values)
    for i in range(max_cols):
        header = values[0][i] if i < len(values[0]) else ""
        table.add_column(str(header))

    for row in values[1:]:
        cells = [str(row[i]) if i < len(row) else "" for i in range(max_cols)]
        table.add_row(*cells)

    console.print(table)
