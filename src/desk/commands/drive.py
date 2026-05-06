"""Drive commands — search, read, upload, download, share, and more."""

import json
import sys

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
from desk.console import error_console
from desk.services.drive import DriveClient

console = Console()


def _get_client(as_json: bool = False) -> DriveClient:
    """Get authenticated Drive client or exit."""
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
    return DriveClient(creds)


def _validate_drive_scope(drive_id: str | None, my_drive: bool, as_json: bool) -> None:
    """Error if both --drive-id and --my-drive are set."""
    if drive_id and my_drive:
        msg = "--drive-id and --my-drive are mutually exclusive"
        error = structured_error(ErrorCode.INVALID_INPUT, msg)
        output_result(error, as_json=as_json)
        sys.exit(1)


def _handle_api_error(e: Exception, as_json: bool, context: dict | None = None) -> None:
    """Handle API errors with structured output when --json is used."""
    raw_error = str(e)
    error_msg = parse_api_error(raw_error)

    if "not found" in raw_error.lower() or "404" in raw_error:
        code = ErrorCode.FILE_NOT_FOUND
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
def drive() -> None:
    """Google Drive — search, read, upload, download, share, and more."""
    pass


@drive.command()
@click.argument("query")
@click.option("--max", "-n", "max_results", default=20, help="Max results")
@click.option("--limit", "limit", default=None, type=int, help="Max results (alias for --max)")
@click.option("--page-token", "page_token", default=None, help="Continue from previous page")
@click.option("--drive-id", "drive_id", default=None, help="Scope to a Shared Drive")
@click.option("--my-drive", "my_drive", is_flag=True, help="Scope to My Drive only (faster)")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def search(
    query: str,
    max_results: int,
    limit: int | None,
    page_token: str | None,
    drive_id: str | None,
    my_drive: bool,
    as_json: bool,
) -> None:
    """Search for files in Drive.

    Searches across all drives (My Drive + Shared Drives) by default.
    Use --my-drive to limit to personal files, or --drive-id to target
    a specific Shared Drive.

    Examples:

        desk drive search "name contains 'report'"

        desk drive search "mimeType = 'application/vnd.google-apps.spreadsheet'"

        desk drive search "name contains 'budget'" --drive-id <shared-drive-id>

        desk drive search "name contains 'notes'" --my-drive
    """
    # --limit takes precedence if provided
    if limit is not None:
        max_results = limit

    _validate_drive_scope(drive_id, my_drive, as_json)
    client = _get_client(as_json)
    try:
        result = client.search(
            query, max_results=max_results, page_token=page_token,
            drive_id=drive_id, my_drive=my_drive,
        )
    except Exception as e:
        _handle_api_error(e, as_json, {"query": query})

    if as_json:
        print(json.dumps(result, indent=2))
        return

    files = result.get("files", [])
    if not files:
        console.print("No files found.")
        return

    _print_file_table(files)

    if result.get("nextPageToken"):
        console.print(f"\n[dim]More results available. Use --page-token {result['nextPageToken']}[/dim]")


def _collect_ids(file_ids: tuple[str, ...], stdin: bool) -> list[str]:
    """Collect file IDs from arguments and/or stdin."""
    ids = list(file_ids)
    if stdin:
        for line in sys.stdin:
            line = line.strip()
            if line:
                ids.append(line)
    return ids


@drive.command()
@click.argument("file_ids", nargs=-1)
@click.option("--stdin", is_flag=True, help="Read file IDs from stdin")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def read(file_ids: tuple[str, ...], stdin: bool, as_json: bool) -> None:
    """Read file content.

    Google Docs/Sheets/Slides are exported as plain text.
    Uploaded Office files (.docx, .xlsx) are converted locally.
    Other files are downloaded as-is.

    Accepts one or more file IDs as arguments, or piped via --stdin.

    Examples:

        desk drive read <file-id>

        desk drive read ID1 ID2 ID3

        desk drive list-folder <id> --json | jq -r '.files[].id' | desk drive read --stdin
    """
    ids = _collect_ids(file_ids, stdin)
    if not ids:
        msg = "No file IDs provided"
        if as_json:
            print(json.dumps(structured_error(ErrorCode.INVALID_INPUT, msg), indent=2), file=sys.stderr)
        else:
            error_console.print(f"[red]Error: {msg}[/red]")
        sys.exit(1)

    client = _get_client(as_json)

    # Single file: original behavior
    if len(ids) == 1:
        try:
            content = client.read(ids[0])
        except Exception as e:
            _handle_api_error(e, as_json, {"file_id": ids[0]})

        if as_json:
            print(json.dumps({"fileId": ids[0], "content": content}, indent=2))
        else:
            console.print(content)
        return

    # Multiple files: batch output
    if as_json:
        results = []
        for fid in ids:
            entry: dict = {"fileId": fid, "content": None, "error": None}
            try:
                entry["content"] = client.read(fid)
            except Exception as e:
                entry["error"] = structured_error(
                    ErrorCode.OPERATION_FAILED,
                    str(e),
                    details={"fileId": fid},
                )
            results.append(entry)
        print(json.dumps(results, indent=2))
    else:
        for i, fid in enumerate(ids):
            console.print(f"[dim]--- {fid} ---[/dim]")
            try:
                content = client.read(fid)
                console.print(content)
            except Exception as e:
                error_console.print(f"[red]Error reading {fid}: {e}[/red]")
            if i < len(ids) - 1:
                console.print()


@drive.command()
@click.argument("file_id")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def info(file_id: str, as_json: bool) -> None:
    """Get file metadata.

    Examples:

        desk drive info <file-id>
    """
    client = _get_client(as_json)
    try:
        metadata = client.info(file_id)
    except Exception as e:
        _handle_api_error(e, as_json, {"file_id": file_id})

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
@click.option("--limit", "limit", default=None, type=int, help="Max results (alias for --max)")
@click.option("--page-token", "page_token", default=None, help="Continue from previous page")
@click.option("--drive-id", "drive_id", default=None, help="Scope to a Shared Drive")
@click.option("--my-drive", "my_drive", is_flag=True, help="Scope to My Drive only (faster)")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def recent(
    max_results: int,
    limit: int | None,
    page_token: str | None,
    drive_id: str | None,
    my_drive: bool,
    as_json: bool,
) -> None:
    """List recently modified files.

    Includes files from Shared Drives by default.

    Examples:

        desk drive recent --max 10

        desk drive recent --my-drive
    """
    # --limit takes precedence if provided
    if limit is not None:
        max_results = limit

    _validate_drive_scope(drive_id, my_drive, as_json)
    client = _get_client(as_json)
    try:
        result = client.recent(
            max_results=max_results, page_token=page_token,
            drive_id=drive_id, my_drive=my_drive,
        )
    except Exception as e:
        _handle_api_error(e, as_json)

    if as_json:
        print(json.dumps(result, indent=2))
        return

    files = result.get("files", [])
    if not files:
        console.print("No recent files.")
        return

    _print_file_table(files)

    if result.get("nextPageToken"):
        console.print(f"\n[dim]More results available. Use --page-token {result['nextPageToken']}[/dim]")


@drive.command()
@click.argument("local_path", type=click.Path(exists=True))
@click.option("--folder", "-f", "folder_id", help="Parent folder ID")
@click.option("--quiet", "-q", is_flag=True, help="Suppress success messages")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def upload(local_path: str, folder_id: str | None, quiet: bool, as_json: bool) -> None:
    """Upload a local file to Drive.

    Examples:

        desk drive upload report.pdf

        desk drive upload data.csv --folder <folder-id>
    """
    client = _get_client(as_json)
    try:
        result = client.upload(local_path, folder_id=folder_id)
    except Exception as e:
        _handle_api_error(e, as_json, {"local_path": local_path, "folder_id": folder_id})

    receipt = operation_receipt(
        operation="upload",
        target={
            "id": result.get("id"),
            "name": result.get("name"),
            "link": result.get("webViewLink"),
        },
        undo_command=f"desk drive trash {result.get('id')}",
    )
    output_result(receipt, as_json, quiet)


@drive.command()
@click.argument("file_id")
@click.argument("dest", default=".", type=click.Path())
@click.option("--quiet", "-q", is_flag=True, help="Suppress success messages")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def download(file_id: str, dest: str, quiet: bool, as_json: bool) -> None:
    """Download a file from Drive.

    Google Docs export as PDF, Sheets as CSV.

    Examples:

        desk drive download <file-id>

        desk drive download <file-id> ~/Downloads/
    """
    client = _get_client(as_json)
    try:
        saved = client.download(file_id, dest)
    except Exception as e:
        _handle_api_error(e, as_json, {"file_id": file_id, "dest": dest})

    receipt = operation_receipt(
        operation="download",
        target={
            "id": file_id,
            "local_path": saved,
        },
    )
    output_result(receipt, as_json, quiet)


@drive.command()
@click.argument("name")
@click.option("--parent", "-p", "parent_id", help="Parent folder ID")
@click.option("--quiet", "-q", is_flag=True, help="Suppress success messages")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def mkdir(name: str, parent_id: str | None, quiet: bool, as_json: bool) -> None:
    """Create a folder in Drive.

    Examples:

        desk drive mkdir "Project Files"

        desk drive mkdir "Subfolder" --parent <folder-id>
    """
    client = _get_client(as_json)
    try:
        result = client.mkdir(name, parent_id=parent_id)
    except Exception as e:
        _handle_api_error(e, as_json, {"name": name, "parent_id": parent_id})

    receipt = operation_receipt(
        operation="mkdir",
        target={
            "id": result.get("id"),
            "name": result.get("name"),
            "link": result.get("webViewLink"),
        },
        undo_command=f"desk drive trash {result.get('id')}",
    )
    output_result(receipt, as_json, quiet)


@drive.command()
@click.argument("file_id")
@click.argument("folder_id")
@click.option("--quiet", "-q", is_flag=True, help="Suppress success messages")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def move(file_id: str, folder_id: str, quiet: bool, as_json: bool) -> None:
    """Move a file to a different folder.

    Examples:

        desk drive move <file-id> <folder-id>
    """
    client = _get_client(as_json)
    try:
        result = client.move(file_id, folder_id)
    except Exception as e:
        _handle_api_error(e, as_json, {"file_id": file_id, "folder_id": folder_id})

    receipt = operation_receipt(
        operation="move",
        target={
            "id": result.get("id"),
            "name": result.get("name"),
            "new_folder": folder_id,
        },
    )
    output_result(receipt, as_json, quiet)


@drive.command()
@click.argument("file_id")
@click.option("--dry-run", is_flag=True, help="Preview without executing")
@click.option("--quiet", "-q", is_flag=True, help="Suppress success messages")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def trash(file_id: str, dry_run: bool, quiet: bool, as_json: bool) -> None:
    """Move a file to trash.

    Examples:

        desk drive trash <file-id>

        desk drive trash <file-id> --dry-run
    """
    client = _get_client(as_json)

    # Get file info for preview/receipt
    try:
        file_info = client.info(file_id)
    except Exception as e:
        _handle_api_error(e, as_json, {"file_id": file_id})

    undo_cmd, undo_expires, _ = get_undo_info("drive-trash", file_id)

    if dry_run:
        preview = dry_run_preview(
            operation="trash",
            targets=[{"id": file_id, "name": file_info.get("name")}],
            reversible=True,
            undo_command=undo_cmd,
        )
        output_result(preview, as_json, quiet)
        return

    try:
        result = client.trash(file_id)
    except Exception as e:
        _handle_api_error(e, as_json, {"file_id": file_id})

    receipt = operation_receipt(
        operation="trash",
        target={
            "id": result.get("id"),
            "name": result.get("name"),
        },
        undo_command=undo_cmd,
        undo_expires=undo_expires,
    )
    output_result(receipt, as_json, quiet)


@drive.command()
@click.argument("file_id")
@click.option("--quiet", "-q", is_flag=True, help="Suppress success messages")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def untrash(file_id: str, quiet: bool, as_json: bool) -> None:
    """Restore a file from trash.

    Examples:

        desk drive untrash <file-id>
    """
    client = _get_client(as_json)
    try:
        result = client.untrash(file_id)
    except Exception as e:
        _handle_api_error(e, as_json, {"file_id": file_id})

    receipt = operation_receipt(
        operation="untrash",
        target={
            "id": result.get("id"),
            "name": result.get("name"),
        },
        undo_command=f"desk drive trash {file_id}",
    )
    output_result(receipt, as_json, quiet)


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
@click.option("--dry-run", is_flag=True, help="Preview without executing")
@click.option("--quiet", "-q", is_flag=True, help="Suppress success messages")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def share(file_id: str, email: str, role: str, dry_run: bool, quiet: bool, as_json: bool) -> None:
    """Share a file with someone.

    Examples:

        desk drive share <file-id> bob@example.com

        desk drive share <file-id> bob@example.com --role reader

        desk drive share <file-id> bob@example.com --dry-run
    """
    client = _get_client(as_json)

    if dry_run:
        # Get file info for preview
        try:
            file_info = client.info(file_id)
        except Exception as e:
            _handle_api_error(e, as_json, {"file_id": file_id})

        preview = dry_run_preview(
            operation="share",
            targets=[{"id": file_id, "name": file_info.get("name"), "email": email, "role": role}],
            reversible=True,
            undo_command=f"desk drive unshare {file_id} {email}",
        )
        output_result(preview, as_json, quiet)
        return

    try:
        client.share(file_id, email, role=role)
    except Exception as e:
        _handle_api_error(e, as_json, {"file_id": file_id, "email": email, "role": role})

    receipt = operation_receipt(
        operation="share",
        target={
            "id": file_id,
            "email": email,
            "role": role,
        },
        undo_command=f"desk drive unshare {file_id} {email}",
    )
    output_result(receipt, as_json, quiet)


@drive.command()
@click.argument("file_id")
@click.option("--quiet", "-q", is_flag=True, help="Suppress success messages")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def star(file_id: str, quiet: bool, as_json: bool) -> None:
    """Star a file.

    Examples:

        desk drive star <file-id>
    """
    client = _get_client(as_json)
    try:
        result = client.star(file_id, starred=True)
    except Exception as e:
        _handle_api_error(e, as_json, {"file_id": file_id})

    undo_cmd, _, _ = get_undo_info("drive-star", file_id)

    receipt = operation_receipt(
        operation="star",
        target={
            "id": result.get("id"),
            "name": result.get("name"),
        },
        undo_command=undo_cmd,
    )
    output_result(receipt, as_json, quiet)


@drive.command()
@click.argument("file_id")
@click.option("--quiet", "-q", is_flag=True, help="Suppress success messages")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def unstar(file_id: str, quiet: bool, as_json: bool) -> None:
    """Unstar a file.

    Examples:

        desk drive unstar <file-id>
    """
    client = _get_client(as_json)
    try:
        result = client.star(file_id, starred=False)
    except Exception as e:
        _handle_api_error(e, as_json, {"file_id": file_id})

    undo_cmd, _, _ = get_undo_info("drive-unstar", file_id)

    receipt = operation_receipt(
        operation="unstar",
        target={
            "id": result.get("id"),
            "name": result.get("name"),
        },
        undo_command=undo_cmd,
    )
    output_result(receipt, as_json, quiet)


@drive.command()
@click.argument("file_id")
@click.option("--name", "-n", help="Name for the copy")
@click.option("--folder", "-f", "folder_id", help="Destination folder ID")
@click.option("--quiet", "-q", is_flag=True, help="Suppress success messages")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def copy(file_id: str, name: str | None, folder_id: str | None, quiet: bool, as_json: bool) -> None:
    """Copy a file in Drive.

    Creates a copy of the file. Works with all file types including Google Docs,
    Sheets, and Slides. Useful for templates.

    Examples:

        desk drive copy <file-id>

        desk drive copy <file-id> --name "Copy of Report"

        desk drive copy <file-id> --folder <folder-id>
    """
    client = _get_client(as_json)
    try:
        result = client.copy(file_id, name=name, folder_id=folder_id)
    except Exception as e:
        _handle_api_error(e, as_json, {"file_id": file_id, "name": name, "folder_id": folder_id})

    receipt = operation_receipt(
        operation="copy",
        target={
            "id": result.get("id"),
            "name": result.get("name"),
            "source_id": file_id,
            "link": result.get("webViewLink"),
        },
        undo_command=f"desk drive trash {result.get('id')}",
    )
    output_result(receipt, as_json, quiet)


@drive.command()
@click.argument("file_id")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def permissions(file_id: str, as_json: bool) -> None:
    """List permissions on a file.

    Shows who has access to a file and their permission level.

    Examples:

        desk drive permissions <file-id>
    """
    client = _get_client(as_json)
    try:
        perms = client.list_permissions(file_id)
    except Exception as e:
        _handle_api_error(e, as_json, {"file_id": file_id})

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
@click.option("--quiet", "-q", is_flag=True, help="Suppress success messages")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def unshare(file_id: str, email: str, dry_run: bool, quiet: bool, as_json: bool) -> None:
    """Remove a user's access to a file.

    Examples:

        desk drive unshare <file-id> bob@example.com

        desk drive unshare <file-id> bob@example.com --dry-run
    """
    client = _get_client(as_json)

    if dry_run:
        # Get file info for preview
        try:
            file_info = client.info(file_id)
        except Exception as e:
            _handle_api_error(e, as_json, {"file_id": file_id})

        preview = dry_run_preview(
            operation="unshare",
            targets=[{"id": file_id, "name": file_info.get("name"), "email": email}],
            reversible=False,
            warnings=["Re-sharing may require the user to accept the invitation again"],
        )
        output_result(preview, as_json, quiet)
        return

    try:
        client.unshare(file_id, email)
    except ValueError as e:
        if as_json:
            error = structured_error(
                ErrorCode.INVALID_INPUT,
                str(e),
                suggestions=["Run `desk drive permissions <file-id>` to see who has access"],
            )
            print(json.dumps(error, indent=2), file=sys.stderr)
        else:
            error_console.print(f"[red]Error: {e}[/red]")
        sys.exit(1)
    except Exception as e:
        _handle_api_error(e, as_json, {"file_id": file_id, "email": email})

    receipt = operation_receipt(
        operation="unshare",
        target={
            "id": file_id,
            "email": email,
        },
    )
    output_result(receipt, as_json, quiet)


@drive.command("transfer-owner")
@click.argument("file_id")
@click.argument("email")
@click.option("--dry-run", is_flag=True, help="Preview without executing")
@click.option("--quiet", "-q", is_flag=True, help="Suppress success messages")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def transfer_owner(file_id: str, email: str, dry_run: bool, quiet: bool, as_json: bool) -> None:
    """Transfer ownership of a file.

    The new owner must be in the same Google Workspace domain.
    You will become an editor after transfer.

    Examples:

        desk drive transfer-owner <file-id> newowner@example.com
    """
    client = _get_client(as_json)

    if dry_run:
        # Get file info for preview
        try:
            file_info = client.info(file_id)
        except Exception as e:
            _handle_api_error(e, as_json, {"file_id": file_id})

        preview = dry_run_preview(
            operation="transfer-owner",
            targets=[{"id": file_id, "name": file_info.get("name"), "new_owner": email}],
            reversible=False,
            warnings=[
                "You will become an editor after transfer",
                "The new owner must be in the same Google Workspace domain",
            ],
        )
        output_result(preview, as_json, quiet)
        return

    try:
        client.transfer_ownership(file_id, email)
    except Exception as e:
        _handle_api_error(e, as_json, {"file_id": file_id, "email": email})

    receipt = operation_receipt(
        operation="transfer-owner",
        target={
            "id": file_id,
            "new_owner": email,
        },
    )
    output_result(receipt, as_json, quiet)


@drive.command()
@click.argument("file_id")
@click.option("--include-resolved", is_flag=True, help="Include resolved comments")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def comments(file_id: str, include_resolved: bool, as_json: bool) -> None:
    """List comments on a file.

    Works with all file types including Google Docs, Sheets, and Slides.

    Examples:

        desk drive comments <file-id>

        desk drive comments <file-id> --include-resolved
    """
    client = _get_client(as_json)
    try:
        comment_list = client.list_comments(file_id, include_resolved=include_resolved)
    except Exception as e:
        _handle_api_error(e, as_json, {"file_id": file_id})

    if as_json:
        print(json.dumps(comment_list, indent=2))
        return

    if not comment_list:
        console.print("No comments.")
        return

    table = Table(show_header=True)
    table.add_column("ID", style="dim", width=12)
    table.add_column("Author", width=20)
    table.add_column("Anchor", width=20)
    table.add_column("Content", width=35)
    table.add_column("Replies", width=7, justify="right")

    for c in comment_list:
        anchor = c.get("anchor", "")[:20] if c.get("anchor") else ""
        status = "[resolved] " if c.get("resolved") else ""
        table.add_row(
            c["id"],
            c.get("author", "")[:20],
            anchor,
            status + c.get("content", "")[:35],
            str(c.get("replyCount", 0)),
        )

    console.print(table)


@drive.command("add-comment")
@click.argument("file_id")
@click.option("--text", "-t", required=True, help="Comment text")
@click.option("--quiet", "-q", is_flag=True, help="Suppress success messages")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def add_comment(file_id: str, text: str, quiet: bool, as_json: bool) -> None:
    """Add a comment to a file.

    Works with all file types including Google Docs, Sheets, and Slides.

    Examples:

        desk drive add-comment <file-id> --text "Please review this section"
    """
    client = _get_client(as_json)
    try:
        result = client.add_comment(file_id, text)
    except Exception as e:
        _handle_api_error(e, as_json, {"file_id": file_id})

    receipt = operation_receipt(
        operation="add-comment",
        target={
            "id": result.get("id"),
            "file_id": file_id,
            "content": text[:50] + ("..." if len(text) > 50 else ""),
        },
    )
    output_result(receipt, as_json, quiet)


@drive.command("resolve-comment")
@click.argument("file_id")
@click.argument("comment_id")
@click.option("--reopen", is_flag=True, help="Reopen instead of resolve")
@click.option("--quiet", "-q", is_flag=True, help="Suppress success messages")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def resolve_comment(file_id: str, comment_id: str, reopen: bool, quiet: bool, as_json: bool) -> None:
    """Resolve or reopen a comment.

    Examples:

        desk drive resolve-comment <file-id> <comment-id>

        desk drive resolve-comment <file-id> <comment-id> --reopen
    """
    client = _get_client(as_json)
    try:
        client.resolve_comment(file_id, comment_id, resolved=not reopen)
    except Exception as e:
        _handle_api_error(e, as_json, {"file_id": file_id, "comment_id": comment_id})

    operation = "reopen-comment" if reopen else "resolve-comment"
    undo_flag = "" if reopen else " --reopen"
    receipt = operation_receipt(
        operation=operation,
        target={
            "id": comment_id,
            "file_id": file_id,
        },
        undo_command=f"desk drive resolve-comment {file_id} {comment_id}{undo_flag}",
    )
    output_result(receipt, as_json, quiet)


@drive.command("reply-comment")
@click.argument("file_id")
@click.argument("comment_id")
@click.option("--text", "-t", required=True, help="Reply text")
@click.option("--quiet", "-q", is_flag=True, help="Suppress success messages")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def reply_comment(file_id: str, comment_id: str, text: str, quiet: bool, as_json: bool) -> None:
    """Reply to a comment.

    Examples:

        desk drive reply-comment <file-id> <comment-id> --text "Done, thanks!"
    """
    client = _get_client(as_json)
    try:
        result = client.reply_comment(file_id, comment_id, text)
    except Exception as e:
        _handle_api_error(e, as_json, {"file_id": file_id, "comment_id": comment_id})

    receipt = operation_receipt(
        operation="reply-comment",
        target={
            "id": result.get("id"),
            "file_id": file_id,
            "comment_id": comment_id,
            "content": text[:50] + ("..." if len(text) > 50 else ""),
        },
    )
    output_result(receipt, as_json, quiet)


@drive.command("list-drives")
@click.option("--max", "-n", "max_results", type=int, default=100, help="Max results")
@click.option("--page-token", "page_token", default=None, help="Pagination token")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def list_drives(max_results: int, page_token: str | None, as_json: bool) -> None:
    """List available Shared Drives.

    Shows Shared Drives you have access to. Use the ID with --drive-id
    on search, recent, and list-folder to scope queries.

    Examples:

        desk drive list-drives

        desk drive list-drives --json
    """
    client = _get_client(as_json)
    try:
        result = client.list_drives(max_results=max_results, page_token=page_token)
    except Exception as e:
        _handle_api_error(e, as_json)

    if as_json:
        print(json.dumps(result, indent=2))
        return

    drives = result.get("drives", [])
    if not drives:
        console.print("No Shared Drives found.")
        return

    table = Table(show_header=True)
    table.add_column("ID", style="dim", width=25)
    table.add_column("Name", width=40)
    table.add_column("Created", width=20)

    for d in drives:
        table.add_row(
            d.get("id", ""),
            d.get("name", ""),
            d.get("createdTime", "")[:10],
        )

    console.print(table)

    if result.get("nextPageToken"):
        console.print(f"\n[dim]More results available. Use --page-token {result['nextPageToken']}[/dim]")


@drive.command("list-folder")
@click.argument("folder_id")
@click.option("--max", "-n", "max_results", type=int, default=100, help="Max files to return")
@click.option("--page-token", default=None, help="Pagination token")
@click.option(
    "--type", "file_type", default=None,
    help="Filter by MIME type (e.g. 'document', 'spreadsheet', 'pdf')",
)
@click.option("--drive-id", "drive_id", default=None, help="Scope to a Shared Drive")
@click.option("--my-drive", "my_drive", is_flag=True, help="Scope to My Drive only (faster)")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def list_folder(
    folder_id: str,
    max_results: int,
    page_token: str | None,
    file_type: str | None,
    drive_id: str | None,
    my_drive: bool,
    as_json: bool,
) -> None:
    """List files in a Drive folder.

    Returns file metadata (id, name, type, modified time). Does NOT read content.
    Pipe IDs to `desk drive read --stdin` to read content.

    Examples:

        desk drive list-folder <folder-id>

        desk drive list-folder <folder-id> --type document --json

        desk drive list-folder <id> --json | jq -r '.files[].id' | desk drive read --stdin
    """
    _validate_drive_scope(drive_id, my_drive, as_json)
    client = _get_client(as_json)

    try:
        result = client.list_folder(
            folder_id,
            max_results=max_results,
            page_token=page_token,
            file_type=file_type,
            drive_id=drive_id,
            my_drive=my_drive,
        )
    except Exception as e:
        _handle_api_error(e, as_json, {"folder_id": folder_id})

    if as_json:
        print(json.dumps(result, indent=2))
        return

    files = result.get("files", [])
    if not files:
        console.print("No files in folder.")
        return

    _print_file_table(files)

    if result.get("nextPageToken"):
        token = result["nextPageToken"]
        console.print(
            f"\n[dim]More results available. Use --page-token {token}[/dim]"
        )


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
