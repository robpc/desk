"""Sheets commands — read and update spreadsheets."""

import json
import sys

import click
from rich.console import Console
from rich.table import Table

from desk.auth import get_credentials
from desk.services.sheets import SheetsClient

console = Console()


def _get_client() -> SheetsClient:
    """Get authenticated Sheets client or exit."""
    creds = get_credentials()
    if not creds:
        console.print("[red]Not authenticated.[/red]")
        console.print("Run: [cyan]desk setup[/cyan]")
        sys.exit(1)
    return SheetsClient(creds)


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
    client = _get_client()
    result = client.read(
        spreadsheet_id,
        ranges=list(ranges) if ranges else None,
        sheet_id=sheet_id,
    )

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
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def update_cell(spreadsheet_id: str, range_: str, value: str, as_json: bool) -> None:
    """Update a single cell value.

    Examples:

        desk sheets update-cell <id> "Sheet1!A1" "Hello"

        desk sheets update-cell <id> "Sheet1!B2" "42"
    """
    client = _get_client()
    result = client.update_cell(spreadsheet_id, range_, value)

    if as_json:
        print(json.dumps(result, indent=2))
    else:
        console.print(f"[green]Updated {result['updatedRange']}[/green]")


@sheets.command()
@click.argument("title")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def create(title: str, as_json: bool) -> None:
    """Create a new spreadsheet.

    Examples:

        desk sheets create "Q1 Budget"
    """
    client = _get_client()
    result = client.create(title)

    if as_json:
        print(json.dumps(result, indent=2))
    else:
        console.print(f"[green]Created: {result['title']}[/green]")
        if result.get("spreadsheetUrl"):
            console.print(f"[dim]{result['spreadsheetUrl']}[/dim]")


@sheets.command()
@click.argument("spreadsheet_id")
@click.argument("range_")
@click.argument("values_json")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def write(spreadsheet_id: str, range_: str, values_json: str, as_json: bool) -> None:
    """Write values to a range.

    VALUES_JSON is a JSON 2D array, e.g. '[["A","B"],["1","2"]]'

    Examples:

        desk sheets write <id> "Sheet1!A1:B2" '[["Name","Age"],["Alice","30"]]'
    """
    client = _get_client()
    try:
        values = json.loads(values_json)
    except json.JSONDecodeError:
        console.print('[red]Invalid JSON. Expected a 2D array like \'[[]["a","b"]]\'[/red]')
        sys.exit(1)
    result = client.write(spreadsheet_id, range_, values)

    if as_json:
        print(json.dumps(result, indent=2))
    else:
        console.print(
            f"[green]Updated {result['updatedRange']} ({result['updatedCells']} cells)[/green]"
        )


@sheets.command()
@click.argument("spreadsheet_id")
@click.argument("range_")
@click.argument("values_json")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def append(spreadsheet_id: str, range_: str, values_json: str, as_json: bool) -> None:
    """Append rows to a spreadsheet.

    VALUES_JSON is a JSON 2D array of rows to append.

    Examples:

        desk sheets append <id> "Sheet1!A:Z" '[["Alice","30"],["Bob","25"]]'
    """
    client = _get_client()
    try:
        values = json.loads(values_json)
    except json.JSONDecodeError:
        console.print('[red]Invalid JSON. Expected a 2D array like \'[[]["a","b"]]\'[/red]')
        sys.exit(1)
    result = client.append(spreadsheet_id, range_, values)

    if as_json:
        print(json.dumps(result, indent=2))
    else:
        console.print(
            f"[green]Appended {result['updatedRows']} rows to {result['updatedRange']}[/green]"
        )


@sheets.command()
@click.argument("spreadsheet_id")
@click.argument("range_")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def clear(spreadsheet_id: str, range_: str, as_json: bool) -> None:
    """Clear values in a range.

    Examples:

        desk sheets clear <id> "Sheet1!A1:C10"
    """
    client = _get_client()
    result = client.clear(spreadsheet_id, range_)

    if as_json:
        print(json.dumps(result, indent=2))
    else:
        console.print(f"[green]Cleared {result['clearedRange']}[/green]")


@sheets.command("list-sheets")
@click.argument("spreadsheet_id")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def list_sheets(spreadsheet_id: str, as_json: bool) -> None:
    """List all sheets (tabs) in a spreadsheet.

    Examples:

        desk sheets list-sheets <spreadsheet-id>
    """
    client = _get_client()
    sheet_list = client.list_sheets(spreadsheet_id)

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
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def add_sheet(spreadsheet_id: str, name: str, index: int | None, as_json: bool) -> None:
    """Add a new sheet (tab) to a spreadsheet.

    Examples:

        desk sheets add-sheet <id> --name "Q2 Data"

        desk sheets add-sheet <id> --name "Summary" --index 0
    """
    client = _get_client()
    result = client.add_sheet(spreadsheet_id, name, index=index)

    if as_json:
        print(json.dumps(result, indent=2))
    else:
        console.print(f"[green]Added sheet: {result['title']}[/green]")
        console.print(f"[dim]Sheet ID: {result['sheetId']}[/dim]")


@sheets.command("delete-sheet")
@click.argument("spreadsheet_id")
@click.option("--sheet-id", type=int, required=True, help="Sheet ID to delete")
@click.option("--yes", "-y", is_flag=True, help="Skip confirmation prompt")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def delete_sheet(spreadsheet_id: str, sheet_id: int, yes: bool, as_json: bool) -> None:
    """Delete a sheet (tab) from a spreadsheet.

    Examples:

        desk sheets delete-sheet <id> --sheet-id 123456

        desk sheets delete-sheet <id> --sheet-id 123456 --yes
    """
    if not yes:
        if not sys.stdin.isatty():
            console.print("[red]Error: Non-interactive mode requires --yes flag[/red]")
            sys.exit(1)
        import click as click_module
        if not click_module.confirm(f"Delete sheet {sheet_id}? This cannot be undone."):
            console.print("[yellow]Cancelled[/yellow]")
            return

    client = _get_client()
    client.delete_sheet(spreadsheet_id, sheet_id)

    if as_json:
        print(json.dumps({"action": "delete-sheet", "sheetId": sheet_id}))
    else:
        console.print(f"[green]Deleted sheet {sheet_id}[/green]")


@sheets.command("rename-sheet")
@click.argument("spreadsheet_id")
@click.option("--sheet-id", type=int, required=True, help="Sheet ID to rename")
@click.option("--name", "-n", required=True, help="New name for the sheet")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def rename_sheet(spreadsheet_id: str, sheet_id: int, name: str, as_json: bool) -> None:
    """Rename a sheet (tab).

    Examples:

        desk sheets rename-sheet <id> --sheet-id 123456 --name "New Name"
    """
    client = _get_client()
    result = client.rename_sheet(spreadsheet_id, sheet_id, name)

    if as_json:
        print(json.dumps(result, indent=2))
    else:
        console.print(f"[green]Renamed sheet to: {result['title']}[/green]")


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
