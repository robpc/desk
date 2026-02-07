"""Drive commands — search, read, upload, download, share, and more."""

import json
import sys

import click
from rich.console import Console
from rich.table import Table

from desk.auth import get_credentials
from desk.services.drive import DriveClient

console = Console()


def _get_client() -> DriveClient:
    """Get authenticated Drive client or exit."""
    creds = get_credentials()
    if not creds:
        console.print("[red]Not authenticated.[/red]")
        console.print("Run: [cyan]desk setup[/cyan]")
        sys.exit(1)
    return DriveClient(creds)


@click.group()
def drive() -> None:
    """Google Drive — search, read, upload, download, share, and more."""
    pass


@drive.command()
@click.argument("query")
@click.option("--max", "-n", "max_results", default=20, help="Max results")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def search(query: str, max_results: int, as_json: bool) -> None:
    """Search for files in Drive.

    Uses Drive search query syntax.

    Examples:

        desk drive search "name contains 'report'"

        desk drive search "mimeType = 'application/vnd.google-apps.spreadsheet'"
    """
    client = _get_client()
    files = client.search(query, max_results=max_results)

    if as_json:
        print(json.dumps(files, indent=2))
        return

    if not files:
        console.print("No files found.")
        return

    _print_file_table(files)


@drive.command()
@click.argument("file_id")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def read(file_id: str, as_json: bool) -> None:
    """Read file content.

    Google Docs/Sheets/Slides are exported as plain text.
    Other files are downloaded as-is.

    Examples:

        desk drive read <file-id>
    """
    client = _get_client()
    content = client.read(file_id)

    if as_json:
        print(json.dumps({"fileId": file_id, "content": content}, indent=2))
    else:
        console.print(content)


@drive.command()
@click.argument("file_id")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def info(file_id: str, as_json: bool) -> None:
    """Get file metadata.

    Examples:

        desk drive info <file-id>
    """
    client = _get_client()
    metadata = client.info(file_id)

    if as_json:
        print(json.dumps(metadata, indent=2))
        return

    console.print(f"[bold]Name:[/bold] {metadata.get('name', '')}")
    console.print(f"[bold]ID:[/bold] {metadata.get('id', '')}")
    console.print(f"[bold]Type:[/bold] {metadata.get('mimeType', '')}")
    console.print(f"[bold]Modified:[/bold] {metadata.get('modifiedTime', '')}")
    console.print(f"[bold]Created:[/bold] {metadata.get('createdTime', '')}")
    if metadata.get("webViewLink"):
        console.print(f"[bold]Link:[/bold] {metadata['webViewLink']}")
    if metadata.get("description"):
        console.print(f"[bold]Description:[/bold] {metadata['description']}")


@drive.command()
@click.option("--max", "-n", "max_results", default=20, help="Max results")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def recent(max_results: int, as_json: bool) -> None:
    """List recently modified files.

    Examples:

        desk drive recent --max 10
    """
    client = _get_client()
    files = client.recent(max_results=max_results)

    if as_json:
        print(json.dumps(files, indent=2))
        return

    if not files:
        console.print("No recent files.")
        return

    _print_file_table(files)


@drive.command()
@click.argument("local_path", type=click.Path(exists=True))
@click.option("--folder", "-f", "folder_id", help="Parent folder ID")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def upload(local_path: str, folder_id: str | None, as_json: bool) -> None:
    """Upload a local file to Drive.

    Examples:

        desk drive upload report.pdf

        desk drive upload data.csv --folder <folder-id>
    """
    client = _get_client()
    result = client.upload(local_path, folder_id=folder_id)

    if as_json:
        print(json.dumps(result, indent=2))
    else:
        console.print(f"[green]Uploaded: {result['name']}[/green]")
        if result.get("webViewLink"):
            console.print(f"[dim]{result['webViewLink']}[/dim]")


@drive.command()
@click.argument("file_id")
@click.argument("dest", default=".", type=click.Path())
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def download(file_id: str, dest: str, as_json: bool) -> None:
    """Download a file from Drive.

    Google Docs export as PDF, Sheets as CSV.

    Examples:

        desk drive download <file-id>

        desk drive download <file-id> ~/Downloads/
    """
    client = _get_client()
    saved = client.download(file_id, dest)

    if as_json:
        print(json.dumps({"fileId": file_id, "path": saved}, indent=2))
    else:
        console.print(f"[green]Downloaded to: {saved}[/green]")


@drive.command()
@click.argument("name")
@click.option("--parent", "-p", "parent_id", help="Parent folder ID")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def mkdir(name: str, parent_id: str | None, as_json: bool) -> None:
    """Create a folder in Drive.

    Examples:

        desk drive mkdir "Project Files"

        desk drive mkdir "Subfolder" --parent <folder-id>
    """
    client = _get_client()
    result = client.mkdir(name, parent_id=parent_id)

    if as_json:
        print(json.dumps(result, indent=2))
    else:
        console.print(f"[green]Created folder: {result['name']}[/green]")
        if result.get("webViewLink"):
            console.print(f"[dim]{result['webViewLink']}[/dim]")


@drive.command()
@click.argument("file_id")
@click.argument("folder_id")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def move(file_id: str, folder_id: str, as_json: bool) -> None:
    """Move a file to a different folder.

    Examples:

        desk drive move <file-id> <folder-id>
    """
    client = _get_client()
    result = client.move(file_id, folder_id)

    if as_json:
        print(json.dumps(result, indent=2))
    else:
        console.print(f"[green]Moved: {result['name']}[/green]")


@drive.command()
@click.argument("file_id")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def trash(file_id: str, as_json: bool) -> None:
    """Move a file to trash.

    Examples:

        desk drive trash <file-id>
    """
    client = _get_client()
    result = client.trash(file_id)

    if as_json:
        print(json.dumps(result, indent=2))
    else:
        console.print(f"[green]Trashed: {result['name']}[/green]")


@drive.command()
@click.argument("file_id")
@click.argument("email")
@click.option(
    "--role",
    "-r",
    type=click.Choice(["reader", "commenter", "writer"]),
    default="writer",
    help="Permission role",
)
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def share(file_id: str, email: str, role: str, as_json: bool) -> None:
    """Share a file with someone.

    Examples:

        desk drive share <file-id> bob@example.com

        desk drive share <file-id> bob@example.com --role reader
    """
    client = _get_client()
    result = client.share(file_id, email, role=role)

    if as_json:
        print(json.dumps(result, indent=2))
    else:
        console.print(f"[green]Shared with {email} as {role}[/green]")


@drive.command()
@click.argument("file_id")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def star(file_id: str, as_json: bool) -> None:
    """Star a file.

    Examples:

        desk drive star <file-id>
    """
    client = _get_client()
    result = client.star(file_id, starred=True)

    if as_json:
        print(json.dumps(result, indent=2))
    else:
        console.print(f"[green]Starred: {result['name']}[/green]")


@drive.command()
@click.argument("file_id")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def unstar(file_id: str, as_json: bool) -> None:
    """Unstar a file.

    Examples:

        desk drive unstar <file-id>
    """
    client = _get_client()
    result = client.star(file_id, starred=False)

    if as_json:
        print(json.dumps(result, indent=2))
    else:
        console.print(f"[green]Unstarred: {result['name']}[/green]")


@drive.command()
@click.argument("file_id")
@click.option("--name", "-n", help="Name for the copy")
@click.option("--folder", "-f", "folder_id", help="Destination folder ID")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def copy(file_id: str, name: str | None, folder_id: str | None, as_json: bool) -> None:
    """Copy a file in Drive.

    Creates a copy of the file. Works with all file types including Google Docs,
    Sheets, and Slides. Useful for templates.

    Examples:

        desk drive copy <file-id>

        desk drive copy <file-id> --name "Copy of Report"

        desk drive copy <file-id> --folder <folder-id>
    """
    client = _get_client()
    result = client.copy(file_id, name=name, folder_id=folder_id)

    if as_json:
        print(json.dumps(result, indent=2))
    else:
        console.print(f"[green]Copied to: {result['name']}[/green]")
        console.print(f"[dim]File ID: {result['id']}[/dim]")
        if result.get("webViewLink"):
            console.print(f"[dim]{result['webViewLink']}[/dim]")


@drive.command()
@click.argument("file_id")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def permissions(file_id: str, as_json: bool) -> None:
    """List permissions on a file.

    Shows who has access to a file and their permission level.

    Examples:

        desk drive permissions <file-id>
    """
    client = _get_client()
    perms = client.list_permissions(file_id)

    if as_json:
        print(json.dumps(perms, indent=2))
        return

    if not perms:
        console.print("No permissions found.")
        return

    table = Table(show_header=True)
    table.add_column("Role", width=12)
    table.add_column("Type", width=10)
    table.add_column("Email/Domain", width=35)
    table.add_column("Name", width=25)

    for perm in perms:
        email_or_domain = perm.get("emailAddress", perm.get("domain", ""))
        if perm.get("type") == "anyone":
            email_or_domain = "(anyone with link)"
        table.add_row(
            perm.get("role", ""),
            perm.get("type", ""),
            email_or_domain,
            perm.get("displayName", ""),
        )

    console.print(table)


@drive.command()
@click.argument("file_id")
@click.argument("email")
@click.option("--dry-run", is_flag=True, help="Preview without executing")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def unshare(file_id: str, email: str, dry_run: bool, as_json: bool) -> None:
    """Remove a user's access to a file.

    Examples:

        desk drive unshare <file-id> bob@example.com

        desk drive unshare <file-id> bob@example.com --dry-run
    """
    if dry_run:
        if as_json:
            print(json.dumps({"dry_run": True, "action": "unshare", "fileId": file_id, "email": email}))
        else:
            console.print(f"[yellow]Would remove {email}'s access to file {file_id}[/yellow]")
        return

    client = _get_client()
    try:
        client.unshare(file_id, email)
    except ValueError as e:
        console.print(f"[red]Error: {e}[/red]")
        sys.exit(1)

    if as_json:
        print(json.dumps({"action": "unshare", "fileId": file_id, "email": email}))
    else:
        console.print(f"[green]Removed {email}'s access[/green]")


@drive.command("transfer-owner")
@click.argument("file_id")
@click.argument("email")
@click.option("--dry-run", is_flag=True, help="Preview without executing")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def transfer_owner(file_id: str, email: str, dry_run: bool, as_json: bool) -> None:
    """Transfer ownership of a file.

    The new owner must be in the same Google Workspace domain.
    You will become an editor after transfer.

    Examples:

        desk drive transfer-owner <file-id> newowner@example.com
    """
    if dry_run:
        if as_json:
            print(json.dumps({"dry_run": True, "action": "transfer-owner", "fileId": file_id, "newOwner": email}))
        else:
            console.print(f"[yellow]Would transfer ownership of file {file_id} to {email}[/yellow]")
        return

    client = _get_client()
    result = client.transfer_ownership(file_id, email)

    if as_json:
        print(json.dumps(result, indent=2))
    else:
        console.print(f"[green]Transferred ownership to {email}[/green]")


def _print_file_table(files: list[dict]) -> None:
    """Print a list of Drive files as a table."""
    table = Table(show_header=True)
    table.add_column("ID", style="dim", width=20)
    table.add_column("Name", width=40)
    table.add_column("Type", width=20)
    table.add_column("Modified", width=20)

    for f in files:
        mime = f.get("mimeType", "")
        short_type = mime.replace("application/vnd.google-apps.", "g:")
        table.add_row(
            f["id"][:20],
            f.get("name", "")[:40],
            short_type[:20],
            f.get("modifiedTime", "")[:20],
        )

    console.print(table)
