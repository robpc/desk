"""Desk - Google Workspace CLI."""

import json
import os
import shutil
import sys
from pathlib import Path

import click
from rich.console import Console
from rich.markup import escape

from desk import __version__
from desk.audit import get_audit_logger
from desk.auth import (
    AuthMethod,
    get_auth_status,
    get_credentials,
    get_last_auth_failure,
    login,
    login_with_gcloud,
)
from desk.config import CONFIG_DIR, CREDENTIALS_FILE, migrate_legacy_config
from desk.console import error_console

console = Console()


def _get_credentials_or_exit():
    """Get authenticated credentials or exit with setup instructions."""
    creds = get_credentials()
    if not creds:
        reason, _error_code = get_last_auth_failure()
        error_console.print("[red]Not authenticated.[/red]")
        if reason:
            error_console.print(f"[yellow]{escape(reason)}[/yellow]")
        else:
            error_console.print("Run: [cyan]desk setup[/cyan]")
        sys.exit(1)
    return creds


def _get_capabilities() -> dict:
    """Return structured capabilities for agent introspection."""
    caps = {
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
                    "create": {
                        "description": "Create form",
                        "batch": False, "destructive": False,
                    },
                    "read": {
                        "description": "Read form structure",
                        "batch": False, "destructive": False,
                    },
                    "responses": {
                        "description": "List form responses",
                        "batch": False, "destructive": False,
                    },
                    "add-question": {
                        "description": "Add question to form",
                        "batch": False, "destructive": False,
                    },
                    "add-section": {
                        "description": "Add section break",
                        "batch": False, "destructive": False,
                    },
                },
            },
            "slides": {
                "description": "Google Slides operations",
                "commands": {
                    "create": {"description": "Create presentation", "batch": False, "destructive": False},
                    "read": {"description": "Read presentation text", "batch": False, "destructive": False},
                    "inspect": {"description": "Show structure with objectIds", "batch": False, "destructive": False},
                    "export": {"description": "Export presentation", "batch": False, "destructive": False},
                    "add-slide": {"description": "Add a slide", "batch": False, "destructive": False, "reversible": True},
                    "delete-slide": {"description": "Delete a slide", "batch": False, "destructive": True, "reversible": False},
                    "delete-object": {"description": "Delete a page element", "batch": False, "destructive": True, "reversible": False},
                    "duplicate-slide": {"description": "Duplicate a slide", "batch": False, "destructive": False, "reversible": True},
                    "move-slide": {"description": "Reorder a slide", "batch": False, "destructive": False, "reversible": True},
                    "insert-text": {"description": "Insert text into a shape", "batch": False, "destructive": False},
                    "replace-text": {"description": "Find and replace text", "batch": False, "destructive": True},
                    "set-notes": {"description": "Set a slide's speaker notes", "batch": False, "destructive": False},
                    "set-cell": {"description": "Set a table cell's text", "batch": False, "destructive": False},
                    "set-text": {"description": "Replace a shape's entire text", "batch": False, "destructive": False},
                    "set-background": {"description": "Set a slide's page background color", "batch": False, "destructive": False},
                    "insert-image": {"description": "Insert an image from a URL", "batch": False, "destructive": False, "reversible": True},
                    "insert-table": {"description": "Insert a table", "batch": False, "destructive": False, "reversible": True},
                    "insert-shape": {"description": "Insert a shape or text box", "batch": False, "destructive": False, "reversible": True},
                    "style": {"description": "Style a shape's text", "batch": False, "destructive": False},
                    "format": {"description": "Fill/outline a shape or image", "batch": False, "destructive": False},
                    "place": {"description": "Move/fit an element into a region", "batch": False, "destructive": False},
                    "arrange": {"description": "Distribute elements as columns/rows/grid", "batch": True, "destructive": False},
                    "stack": {"description": "Flow elements in a line (natural size, aligned)", "batch": True, "destructive": False},
                    "group": {"description": "Group elements into one group object", "batch": True, "destructive": False},
                    "ungroup": {"description": "Ungroup a group back into its members", "batch": False, "destructive": False},
                },
            },
            "meet": {
                "description": "Google Meet operations",
                "commands": {
                    "read": {"description": "Read a meeting space's settings", "batch": False, "destructive": False},
                    "update": {"description": "Set auto-record/transcript/smart-notes", "batch": False, "destructive": False, "reversible": True},
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
            "scope_aware": "Commands report required scopes and whether they're enabled",
        },
    }
    _annotate_scopes(caps)
    return caps


def _annotate_scopes(caps: dict) -> None:
    """Add `scope` and `enabled` to every command entry, in place.

    Scopes come from `config.SCOPE_COMMANDS` rather than being written into each
    entry by hand, so the map stays the single source of truth. `enabled` is
    tri-state: True, False, or None when the granted set is unknown (an
    unauthenticated user, or a token predating issue #82). See ADR-034.
    """
    from desk.auth import granted_scopes
    from desk.config import scopes_for_command

    granted = granted_scopes()

    for service, info in caps["services"].items():
        for cmd_name, cmd in info["commands"].items():
            scopes = scopes_for_command(service, cmd_name)
            cmd["scope"] = scopes
            if granted is None:
                cmd["enabled"] = None
            else:
                cmd["enabled"] = all(s in granted for s in scopes)


@click.group(invoke_without_command=True)
@click.version_option(version=__version__)
@click.option("--verbose", "-v", is_flag=True, help="Verbose output")
@click.option("--capabilities", "capabilities_service", default=None, required=False,
              help="Show capabilities. Use 'all' for everything or specify service: mail, drive, cal, sheets, docs, forms, slides")
@click.pass_context
def main(ctx: click.Context, verbose: bool, capabilities_service: str | None) -> None:
    """Desk - Google Workspace from the command line."""
    ctx.ensure_object(dict)
    ctx.obj["verbose"] = verbose

    # Audit logging — see ADR-020 + atrium ADR-004.
    # Skip for --capabilities (introspection-only, no user-visible side effects).
    if capabilities_service is None:
        ctx.obj["audit"] = get_audit_logger(CONFIG_DIR)

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
            error_console.print(f"[red]Unknown service: {capabilities_service}[/red]")
            error_console.print(f"[dim]Available: all, {', '.join(caps['services'].keys())}[/dim]")
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


@main.result_callback()
@click.pass_context
def _audit_subcommand(ctx, _result, **_kwargs):
    """Log each successful subcommand invocation. See ADR-020."""
    audit = (ctx.obj or {}).get("audit") if ctx.obj else None
    if audit is None:
        return
    subcmd = ctx.invoked_subcommand or "none"
    audit.info(f"event=cmd subcmd={subcmd} exit=0")


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
            error_console.print("[red]gcloud authentication failed.[/red]")
            error_console.print("Make sure gcloud is installed and try again.")
            sys.exit(1)
        return

    if credentials:
        CONFIG_DIR.mkdir(parents=True, mode=0o700, exist_ok=True)
        os.chmod(CONFIG_DIR, 0o700)  # fix pre-existing directories
        shutil.copy(credentials, CREDENTIALS_FILE)
        console.print(f"Copied credentials to {CREDENTIALS_FILE}")
        console.print()
        console.print("Now running authentication flow...")
        try:
            login(verbose=verbose, credentials_path=str(credentials))
        except Exception as e:
            error_console.print(f"[red]Authentication failed: {e}[/red]")
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
        console.print("No credentials found.")
        console.print()
        console.print("To set up:")
        console.print("  1. Get credentials.json from your team")
        console.print("  2. Run: [cyan]desk setup --credentials /path/to/credentials.json[/cyan]")


# --- Auth commands ---


@main.group()
def auth() -> None:
    """Authentication commands."""
    pass


@auth.command("set-client")
@click.option("--client-id", required=True, help="Google OAuth Client ID")
@click.option("--client-secret", required=True, help="Google OAuth Client Secret")
@click.option("--project-id", default=None, help="Google Cloud project ID")
def auth_set_client(client_id: str, client_secret: str, project_id: str | None) -> None:
    """Store Google OAuth credentials in the OS keychain.

    Constructs the standard Google "installed" credentials block and stores
    it in the OS keychain. Used by install scripts to provision credentials
    without writing plaintext files to disk.
    """
    from desk.keyring_store import KeyringUnavailableError, check_keyring_backend

    try:
        check_keyring_backend()
    except KeyringUnavailableError as e:
        error_console.print(f"[red]Error: {e}[/red]")
        sys.exit(1)

    from desk import keyring_store

    credentials = {
        "installed": {
            "client_id": client_id,
            "client_secret": client_secret,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
            "redirect_uris": ["http://localhost"],
        }
    }
    if project_id:
        credentials["installed"]["project_id"] = project_id

    keyring_store.set_client_credentials(credentials)
    console.print("Client credentials stored in keychain.")


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
            error_console.print("[red]gcloud authentication failed.[/red]")
            sys.exit(1)
    else:
        try:
            login(verbose=verbose)
        except Exception as e:
            error_console.print(f"[red]Authentication failed: {e}[/red]")
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

        # Proactively flag scope drift (granted token predates a newly added scope).
        missing = info.get("missing_scopes")
        if missing:
            console.print()
            console.print(
                f"[yellow]Missing {len(missing)} scope(s):[/yellow] "
                + ", ".join(s.rsplit('/', 1)[-1] for s in missing)
            )
            login_cmd = (
                "desk auth login --gcloud"
                if info["method"] == AuthMethod.GCLOUD_ADC
                else "desk auth login"
            )
            console.print(f"Re-authenticate to add them: [cyan]{login_cmd}[/cyan]")

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


# --- Register subcommand groups ---

from desk.commands.cal import cal  # noqa: E402
from desk.commands.docs import docs  # noqa: E402
from desk.commands.drive import drive  # noqa: E402
from desk.commands.forms import forms  # noqa: E402
from desk.commands.mail import mail  # noqa: E402
from desk.commands.meet import meet  # noqa: E402
from desk.commands.sheets import sheets  # noqa: E402
from desk.commands.slides import slides  # noqa: E402

main.add_command(mail)
main.add_command(drive)
main.add_command(sheets)
main.add_command(docs)
main.add_command(cal)
main.add_command(forms)
main.add_command(slides)
main.add_command(meet)


if __name__ == "__main__":
    main()
