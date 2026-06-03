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
from desk.auth import (
    clear as auth_clear_action,
)
from desk.auth import (
    logout as auth_logout_action,
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

    # If the new client_id differs from the existing token's client_id, the
    # stored token can no longer refresh. Auto-invalidate it so the user lands
    # in a clean state on the next login.
    existing_token = keyring_store.get_token()
    invalidated_token = False
    if existing_token:
        existing_client_id = existing_token.get("client_id")
        if existing_client_id and existing_client_id != client_id:
            invalidated_token = keyring_store.delete_token()

    keyring_store.set_client_credentials(credentials)
    console.print("Client credentials stored in keychain.")
    if invalidated_token:
        console.print(
            "Cleared stored token (was issued for a different client_id)."
        )


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

        # Show OAuth client + token diagnostics so users can spot stale state.
        client_id = info.get("client_id")
        token_client_id = info.get("token_client_id")
        token_source = info.get("token_source")
        scopes = info.get("scopes") or []

        if client_id:
            console.print(f"  client_id: {escape(client_id)}", soft_wrap=True)
        if token_client_id and token_client_id != client_id:
            console.print(
                f"  [yellow]token client_id: {escape(token_client_id)} "
                "(does not match configured client — "
                "run `desk auth login` to refresh)[/yellow]",
                soft_wrap=True,
            )
        if token_source and token_source != "none":
            console.print(f"  token source: {token_source}")
        if scopes:
            console.print(f"  scopes ({len(scopes)}):")
            for scope in scopes:
                console.print(f"    {escape(scope)}")

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


@auth.command("logout")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def auth_logout(as_json: bool) -> None:
    """Sign out by removing the stored OAuth token.

    Removes the OAuth token from the OS keychain (and scrubs any legacy
    ~/.desk/token.json secrets). Stored client credentials are preserved so
    you can run `desk auth login` again without re-provisioning the client.

    Idempotent: succeeds even if no token is stored.
    """
    result = auth_logout_action()

    if as_json:
        print(json.dumps(result, indent=2))
        return

    if result["keyring_token_removed"] or result["token_file_scrubbed"]:
        if result["keyring_token_removed"]:
            console.print("[green]Removed OAuth token from keychain.[/green]")
        if result["token_file_scrubbed"]:
            console.print("[green]Scrubbed legacy token file.[/green]")
        console.print("Run [cyan]desk auth login[/cyan] to sign in again.")
    else:
        console.print("[dim]No stored OAuth token to remove.[/dim]")


@auth.command("clear")
@click.option("--token", "clear_token", is_flag=True, help="Clear only the OAuth token")
@click.option(
    "--client", "clear_client_flag", is_flag=True, help="Clear only the client credentials"
)
@click.option("--yes", "-y", is_flag=True, help="Skip confirmation prompt")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def auth_clear(
    clear_token: bool, clear_client_flag: bool, yes: bool, as_json: bool
) -> None:
    """Remove stored credentials from the OS keychain.

    By default, clears both the OAuth token and the stored client credentials.
    Use --token to clear only the token, or --client to clear only the client
    credentials. Passing both flags is equivalent to passing neither.

    This is the recovery hatch when the keychain state is stale (e.g. the
    stored token was minted against a different OAuth client than the one
    currently configured, or scopes have drifted).
    """
    # Default: both. Both flags: both. Otherwise honor the explicit flag.
    if clear_token == clear_client_flag:
        do_token = True
        do_client = True
    else:
        do_token = clear_token
        do_client = clear_client_flag

    targets = []
    if do_token:
        targets.append("OAuth token")
    if do_client:
        targets.append("client credentials")
    target_label = " and ".join(targets)

    if not yes:
        if not sys.stdin.isatty():
            if as_json:
                print(
                    json.dumps(
                        {
                            "error": "Non-interactive mode requires --yes flag",
                            "targets": targets,
                        },
                        indent=2,
                    )
                )
            else:
                console.print("[red]Error: Non-interactive mode requires --yes flag[/red]")
            sys.exit(1)
        if not click.confirm(f"Remove {target_label} from keychain?"):
            console.print("[yellow]Cancelled[/yellow]")
            return

    result = auth_clear_action(token=do_token, client=do_client)

    if as_json:
        print(json.dumps(result, indent=2))
        return

    if result["keyring_token_removed"]:
        console.print("[green]Removed OAuth token from keychain.[/green]")
    if result["token_file_scrubbed"]:
        console.print("[green]Scrubbed legacy token file.[/green]")
    if result["keyring_client_removed"]:
        console.print("[green]Removed client credentials from keychain.[/green]")
    if not any(result.values()):
        console.print("[dim]Nothing to remove.[/dim]")
    else:
        console.print("Run [cyan]desk setup[/cyan] to re-authenticate.")


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
