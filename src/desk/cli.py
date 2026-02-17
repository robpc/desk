"""Desk - Google Workspace CLI."""

import json
import shutil
import sys
from pathlib import Path

import click
from rich.console import Console
from rich.markup import escape

from desk import __version__
from desk.auth import (
    AuthMethod,
    get_auth_status,
    get_credentials,
    get_last_auth_failure,
    login,
    login_with_gcloud,
)
from desk.config import CONFIG_DIR, CREDENTIALS_FILE, migrate_legacy_config

console = Console()


def _get_credentials_or_exit():
    """Get authenticated credentials or exit with setup instructions."""
    creds = get_credentials()
    if not creds:
        reason, _error_code = get_last_auth_failure()
        console.print("[red]Not authenticated.[/red]")
        if reason:
            console.print(f"[yellow]{escape(reason)}[/yellow]")
        else:
            console.print("Run: [cyan]desk setup[/cyan]")
        sys.exit(1)
    return creds


def _get_capabilities() -> dict:
    """Return structured capabilities for agent introspection."""
    return {
        "version": __version__,
        "agent_first": True,
        "services": {
            "mail": {
                "description": "Gmail operations",
                "commands": {
                    "search": {"description": "Search messages", "batch": False, "destructive": False},
                    "threads": {"description": "Search threads", "batch": False, "destructive": False},
                    "thread": {"description": "Read thread", "batch": False, "destructive": False},
                    "read": {"description": "Read message", "batch": False, "destructive": False},
                    "send": {"description": "Send email", "batch": False, "destructive": True, "reversible": False},
                    "reply": {"description": "Reply to message", "batch": False, "destructive": True, "reversible": False},
                    "forward": {"description": "Forward message", "batch": False, "destructive": True, "reversible": False},
                    "archive": {"description": "Archive messages", "batch": True, "destructive": False, "reversible": True, "undo": "unarchive", "accepts_stdin": True},
                    "trash": {"description": "Move to trash", "batch": True, "destructive": True, "reversible": True, "undo": "untrash", "undo_expires": "30 days", "accepts_stdin": True},
                    "label": {"description": "Add label", "batch": True, "destructive": False, "reversible": True, "undo": "remove-label", "accepts_stdin": True},
                    "remove-label": {"description": "Remove label", "batch": True, "destructive": False, "reversible": True, "undo": "label", "accepts_stdin": True},
                    "mark-read": {"description": "Mark as read", "batch": True, "destructive": False, "reversible": True, "undo": "mark-unread", "accepts_stdin": True},
                    "mark-unread": {"description": "Mark as unread", "batch": True, "destructive": False, "reversible": True, "undo": "mark-read", "accepts_stdin": True},
                    "star": {"description": "Star messages", "batch": True, "destructive": False, "reversible": True, "undo": "unstar", "accepts_stdin": True},
                    "unstar": {"description": "Remove star", "batch": True, "destructive": False, "reversible": True, "undo": "star", "accepts_stdin": True},
                    "modify": {"description": "Generic label changes", "batch": True, "destructive": False, "reversible": True, "accepts_stdin": True},
                    "labels": {"description": "List labels", "batch": False, "destructive": False},
                    "drafts": {"description": "List drafts", "batch": False, "destructive": False},
                    "filters": {"description": "List filters", "batch": False, "destructive": False},
                },
            },
            "drive": {
                "description": "Google Drive operations",
                "commands": {
                    "search": {"description": "Search files", "batch": False, "destructive": False},
                    "read": {"description": "Read file content", "batch": False, "destructive": False},
                    "info": {"description": "File metadata", "batch": False, "destructive": False},
                    "recent": {"description": "Recent files", "batch": False, "destructive": False},
                    "upload": {"description": "Upload file", "batch": False, "destructive": False},
                    "download": {"description": "Download file", "batch": False, "destructive": False},
                    "mkdir": {"description": "Create folder", "batch": False, "destructive": False},
                    "move": {"description": "Move file to folder", "batch": False, "destructive": False},
                    "copy": {"description": "Copy file", "batch": False, "destructive": False},
                    "trash": {"description": "Move to trash", "batch": False, "destructive": True, "reversible": True, "undo": "untrash", "undo_expires": "30 days"},
                    "untrash": {"description": "Restore from trash", "batch": False, "destructive": False, "reversible": True, "undo": "trash"},
                    "star": {"description": "Star file", "batch": False, "destructive": False, "reversible": True, "undo": "unstar"},
                    "unstar": {"description": "Remove star", "batch": False, "destructive": False, "reversible": True, "undo": "star"},
                    "share": {"description": "Share with user", "batch": False, "destructive": False, "reversible": True, "undo": "unshare"},
                    "unshare": {"description": "Remove user access", "batch": False, "destructive": False, "reversible": False},
                    "transfer-owner": {"description": "Transfer ownership", "batch": False, "destructive": True, "reversible": False},
                    "permissions": {"description": "List permissions", "batch": False, "destructive": False},
                    "comments": {"description": "List comments", "batch": False, "destructive": False},
                    "add-comment": {"description": "Add comment", "batch": False, "destructive": False},
                    "resolve-comment": {"description": "Resolve/reopen comment", "batch": False, "destructive": False, "reversible": True},
                    "reply-comment": {"description": "Reply to comment", "batch": False, "destructive": False},
                },
            },
            "cal": {
                "description": "Google Calendar operations",
                "commands": {
                    "today": {"description": "Today's events", "batch": False, "destructive": False},
                    "week": {"description": "This week's events", "batch": False, "destructive": False},
                    "next": {"description": "Upcoming events", "batch": False, "destructive": False},
                    "list": {"description": "List calendars", "batch": False, "destructive": False},
                    "find": {"description": "Search events", "batch": False, "destructive": False},
                    "create": {"description": "Create event", "batch": False, "destructive": False, "reversible": True, "undo": "delete"},
                    "delete": {"description": "Delete event", "batch": False, "destructive": True, "reversible": False},
                    "update": {"description": "Update event", "batch": False, "destructive": False},
                    "invitations": {"description": "Pending invitations", "batch": False, "destructive": False},
                    "respond": {"description": "Respond to invitation", "batch": False, "destructive": False},
                    "freebusy": {"description": "Check availability", "batch": False, "destructive": False},
                },
            },
            "sheets": {
                "description": "Google Sheets operations",
                "commands": {
                    "read": {"description": "Read spreadsheet", "batch": False, "destructive": False},
                    "update-cell": {"description": "Update single cell", "batch": False, "destructive": True},
                    "write": {"description": "Write values", "batch": False, "destructive": True},
                    "append": {"description": "Append rows", "batch": False, "destructive": False},
                    "clear": {"description": "Clear range", "batch": False, "destructive": True},
                    "create": {"description": "Create spreadsheet", "batch": False, "destructive": False},
                    "list-sheets": {"description": "List sheets in spreadsheet", "batch": False, "destructive": False},
                    "add-sheet": {"description": "Add sheet tab", "batch": False, "destructive": False, "reversible": True, "undo": "delete-sheet"},
                    "delete-sheet": {"description": "Delete sheet tab", "batch": False, "destructive": True, "reversible": False},
                    "rename-sheet": {"description": "Rename sheet tab", "batch": False, "destructive": False},
                },
            },
            "docs": {
                "description": "Google Docs operations",
                "commands": {
                    "read": {"description": "Read document", "batch": False, "destructive": False},
                    "create": {"description": "Create document", "batch": False, "destructive": False},
                    "update": {"description": "Update document", "batch": False, "destructive": True},
                    "export": {"description": "Export document", "batch": False, "destructive": False},
                },
            },
            "forms": {
                "description": "Google Forms operations",
                "commands": {
                    "create": {"description": "Create form", "batch": False, "destructive": False},
                    "read": {"description": "Read form structure", "batch": False, "destructive": False},
                    "responses": {"description": "List form responses", "batch": False, "destructive": False},
                    "add-question": {"description": "Add question to form", "batch": False, "destructive": False},
                    "add-section": {"description": "Add section break", "batch": False, "destructive": False},
                },
            },
        },
        "global_flags": {
            "--json": "Output as JSON (agent-friendly structured output)",
            "--quiet": "Suppress success messages",
            "--dry-run": "Preview without executing (on mutating commands)",
            "--verbose": "Verbose output for debugging",
        },
        "agent_features": {
            "structured_errors": "Errors include code, message, suggestions, and retryable flag",
            "operation_receipts": "Mutating operations return receipts with undo commands",
            "dry_run_preview": "Dry-run shows target details and reversibility",
        },
        "utility_commands": {
            "update": {
                "description": "Self-update desk to latest version",
                "flags": {
                    "--check": "Check for updates without applying",
                    "--json": "Structured output for agents",
                },
            },
        },
    }


@click.group(invoke_without_command=True)
@click.version_option(version=__version__)
@click.option("--verbose", "-v", is_flag=True, help="Verbose output")
@click.option("--capabilities", "capabilities_service", default=None, required=False,
              help="Show capabilities. Use 'all' for everything or specify service: mail, drive, cal, sheets, docs, forms")
@click.pass_context
def main(ctx: click.Context, verbose: bool, capabilities_service: str | None) -> None:
    """Desk - Google Workspace from the command line."""
    ctx.ensure_object(dict)
    ctx.obj["verbose"] = verbose

    if capabilities_service is not None:
        caps = _get_capabilities()
        if capabilities_service not in ("all", "") and capabilities_service in caps["services"]:
            # Filter to just the requested service
            filtered = {
                "version": caps["version"],
                "agent_first": caps["agent_first"],
                "service": capabilities_service,
                "commands": caps["services"][capabilities_service]["commands"],
                "global_flags": caps["global_flags"],
            }
            print(json.dumps(filtered, indent=2))
        elif capabilities_service not in ("all", ""):
            # Unknown service
            console.print(f"[red]Unknown service: {capabilities_service}[/red]")
            console.print(f"[dim]Available: all, {', '.join(caps['services'].keys())}[/dim]")
            ctx.exit(1)
        else:
            print(json.dumps(caps, indent=2))
        ctx.exit(0)

    # Auto-migrate legacy ~/.gmail-cli/ config
    if migrate_legacy_config():
        console.print("[dim]Migrated config from ~/.gmail-cli/ to ~/.desk/[/dim]")
        console.print("[dim]Run 'desk auth login' to grant expanded API access.[/dim]")

    # If no command provided and no flags handled, show help
    if ctx.invoked_subcommand is None:
        click.echo(ctx.get_help())


# --- Setup command ---


@main.command()
@click.option(
    "--credentials",
    "-c",
    type=click.Path(exists=True, path_type=Path),
    help="Path to credentials.json file",
)
@click.option("--gcloud", "use_gcloud", is_flag=True, help="Use gcloud for authentication")
@click.pass_context
def setup(ctx: click.Context, credentials: Path | None, use_gcloud: bool) -> None:
    """Set up Desk authentication.

    For personal use (simplest):

        desk setup --gcloud

    For team setup (with shared credentials):

        desk setup --credentials ~/Downloads/credentials.json
    """
    verbose = ctx.obj.get("verbose", False)

    if use_gcloud:
        console.print("Authenticating with gcloud...")
        creds = login_with_gcloud(verbose=verbose)
        if creds:
            console.print("[green]Authentication successful![/green]")
            console.print("You can now use desk commands.")
        else:
            console.print("[red]gcloud authentication failed.[/red]")
            console.print("Make sure gcloud is installed and try again.")
            sys.exit(1)
        return

    if credentials:
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        shutil.copy(credentials, CREDENTIALS_FILE)
        console.print(f"Copied credentials to {CREDENTIALS_FILE}")
        console.print()
        console.print("Now running authentication flow...")
        try:
            login(verbose=verbose)
        except Exception as e:
            console.print(f"[red]Authentication failed: {e}[/red]")
            sys.exit(1)
        console.print("[green]Authentication successful![/green]")
        return

    # Interactive setup
    console.print("[bold]Desk Setup[/bold]")
    console.print()

    status = get_auth_status()

    if status["gcloud_available"]:
        console.print("Choose setup method:")
        console.print()
        console.print("  [bold]1.[/bold] gcloud (simplest, for personal use)")
        console.print("     Run: [cyan]desk setup --gcloud[/cyan]")
        console.print()
        console.print("  [bold]2.[/bold] Team credentials (for shared projects)")
        console.print("     Run: [cyan]desk setup --credentials /path/to/credentials.json[/cyan]")
    else:
        console.print("gcloud not found. Using team credentials setup.")
        console.print()
        console.print("To set up:")
        console.print("  1. Get credentials.json from your team's 1Password vault")
        console.print("  2. Run: [cyan]desk setup --credentials /path/to/credentials.json[/cyan]")


# --- Auth commands ---


@main.group()
def auth() -> None:
    """Authentication commands."""
    pass


@auth.command("login")
@click.option("--gcloud", "use_gcloud", is_flag=True, help="Use gcloud for authentication")
@click.pass_context
def auth_login(ctx: click.Context, use_gcloud: bool) -> None:
    """Authenticate with Google Workspace.

    Use --gcloud for gcloud-based auth, or ensure credentials.json exists.
    """
    verbose = ctx.obj.get("verbose", False)

    if use_gcloud:
        creds = login_with_gcloud(verbose=verbose)
        if creds:
            console.print("[green]Authentication successful![/green]")
        else:
            console.print("[red]gcloud authentication failed.[/red]")
            sys.exit(1)
    else:
        try:
            login(verbose=verbose)
        except Exception as e:
            console.print(f"[red]Authentication failed: {e}[/red]")
            sys.exit(1)
        console.print("[green]Authentication successful![/green]")


@auth.command("status")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
@click.option("--verify", is_flag=True, help="Verify access to each service (slower)")
def auth_status(as_json: bool, verify: bool) -> None:
    """Check authentication status.

    Use --verify to test actual API access for each service.
    This catches scope mismatches that would cause 403 errors.
    """
    info = get_auth_status(verify=verify)

    if as_json:
        print(json.dumps(info, indent=2))
        return

    if info["authenticated"]:
        method_display = {
            AuthMethod.GCLOUD_ADC: "gcloud ADC",
            AuthMethod.OAUTH_CLIENT: "OAuth credentials",
        }.get(info["method"], info["method"])

        console.print(f"[green]Authenticated[/green] via {method_display}")

        # Show service access if verified
        if info.get("services"):
            console.print()
            console.print("Service access:")
            for service, has_access in info["services"].items():
                if has_access:
                    console.print(f"  {service}: [green]OK[/green]")
                else:
                    console.print(f"  {service}: [red]NO ACCESS[/red] (missing scope)")

            # Check for any failures
            missing = [s for s, ok in info["services"].items() if not ok]
            if missing:
                console.print()
                console.print("[yellow]Some services are inaccessible.[/yellow]")
                console.print("Re-authenticate to fix:")
                if info["method"] == AuthMethod.GCLOUD_ADC:
                    console.print("  [cyan]desk auth login --gcloud[/cyan]")
                else:
                    console.print("  [cyan]desk auth login[/cyan]")
        elif not verify:
            console.print("[dim]Tip: Use --verify to test access to each service[/dim]")
    else:
        console.print("[red]Not authenticated[/red]")
        console.print()
        if info["gcloud_available"]:
            console.print("Quick setup: [cyan]desk setup --gcloud[/cyan]")
        else:
            console.print("Run: [cyan]desk setup[/cyan] for setup instructions")


# --- Update command ---


@main.command()
@click.option("--check", is_flag=True, help="Check for updates without applying")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
@click.pass_context
def update(ctx: click.Context, check: bool, as_json: bool) -> None:
    """Update desk to the latest version.

    Detects how desk was installed and performs the appropriate update.
    Supports editable git clones and pip-from-git installs.

    \b
    Examples:
        desk update              # Update to latest
        desk update --check      # Check without updating
        desk update --check --json  # Machine-readable check
    """
    from desk.update import (
        InstallMethod,
        apply_update,
        check_for_updates,
        detect_install,
    )

    verbose = ctx.obj.get("verbose", False)

    info = detect_install()

    if verbose:
        console.print(f"[dim]Install method: {info.method.value}[/dim]")
        if info.repo_path:
            console.print(f"[dim]Repo path: {info.repo_path}[/dim]")
        if info.git_url:
            console.print(f"[dim]Git URL: {info.git_url}[/dim]")

    if info.method == InstallMethod.UNKNOWN:
        if as_json:
            from desk.agent import ErrorCode, structured_error

            print(json.dumps(structured_error(
                ErrorCode.UPDATE_UNKNOWN_INSTALL,
                "Cannot determine how desk was installed",
            ), indent=2))
        else:
            console.print("[red]Cannot determine how desk was installed.[/red]")
            console.print()
            console.print("Manual update options:")
            console.print("  Editable: [cyan]cd <repo> && git pull && pip install -e .[/cyan]")
            console.print("  Pip:     [cyan]pip install --upgrade git+<repo-url>[/cyan]")
        sys.exit(1)

    # Check for updates
    if check or info.method == InstallMethod.EDITABLE_GIT:
        status = check_for_updates(info)

        if status.error:
            if as_json:
                from desk.agent import ErrorCode, structured_error

                code = getattr(ErrorCode, status.error_code, ErrorCode.OPERATION_FAILED)
                print(json.dumps(structured_error(
                    code, status.error, retryable=status.error_code == "UPDATE_NETWORK_ERROR",
                ), indent=2))
            else:
                console.print(f"[red]{status.error}[/red]")
            sys.exit(1)

        if check:
            if as_json:
                print(json.dumps({
                    "update_available": status.update_available,
                    "current_version": status.current_version,
                    "remote_version": status.remote_version,
                    "commits_behind": status.commits_behind,
                    "install_method": info.method.value,
                }, indent=2))
            elif status.update_available:
                version_str = f"{status.current_version}"
                if status.remote_version:
                    version_str += f" → {status.remote_version}"
                behind = f"{status.commits_behind} commits behind"
                console.print(f"Update available: {version_str} ({behind})")
            else:
                console.print(f"desk is up to date ({status.current_version})")
            return

        if not status.update_available:
            if as_json:
                print(json.dumps({
                    "update_available": False,
                    "current_version": status.current_version,
                    "install_method": info.method.value,
                }, indent=2))
            else:
                console.print(f"desk is up to date ({status.current_version})")
            return

    # Apply update
    if not as_json:
        if info.method == InstallMethod.EDITABLE_GIT:
            console.print("Pulling latest from origin/main...")
        else:
            console.print("Upgrading from git...")

    result = apply_update(info)

    if not result.success:
        if as_json:
            from desk.agent import ErrorCode, structured_error

            code = getattr(ErrorCode, result.error_code, ErrorCode.OPERATION_FAILED)
            print(json.dumps(structured_error(
                code, result.error or "Update failed",
                retryable=result.error_code == "UPDATE_NETWORK_ERROR",
            ), indent=2))
        else:
            console.print(f"[red]{result.error}[/red]")
            if result.error_code == "UPDATE_FAILED" and "diverged" in (result.error or ""):
                console.print()
                console.print("Resolve manually:")
                repo = info.repo_path
                console.print(f"  [cyan]cd {repo} && git pull --rebase origin main[/cyan]")
        sys.exit(1)

    if as_json:
        print(json.dumps({
            "success": True,
            "previous_version": result.previous_version,
            "new_version": result.new_version,
            "install_method": info.method.value,
        }, indent=2))
    else:
        if result.previous_version == result.new_version:
            console.print(f"desk is up to date ({result.new_version})")
        else:
            old, new = result.previous_version, result.new_version
            console.print(f"[green]Updated: {old} → {new}[/green]")


# --- Register subcommand groups ---

from desk.commands.cal import cal  # noqa: E402
from desk.commands.docs import docs  # noqa: E402
from desk.commands.drive import drive  # noqa: E402
from desk.commands.forms import forms  # noqa: E402
from desk.commands.mail import mail  # noqa: E402
from desk.commands.sheets import sheets  # noqa: E402

main.add_command(mail)
main.add_command(drive)
main.add_command(sheets)
main.add_command(docs)
main.add_command(cal)
main.add_command(forms)


if __name__ == "__main__":
    main()
