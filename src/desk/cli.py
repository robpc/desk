"""Desk - Google Workspace CLI."""

import json
import shutil
import sys
from pathlib import Path

import click
from rich.console import Console

from desk import __version__
from desk.auth import (
    AuthMethod,
    get_auth_status,
    get_credentials,
    login,
    login_with_gcloud,
)
from desk.config import CONFIG_DIR, CREDENTIALS_FILE, migrate_legacy_config

console = Console()


def _get_credentials_or_exit():
    """Get authenticated credentials or exit with setup instructions."""
    creds = get_credentials()
    if not creds:
        console.print("[red]Not authenticated.[/red]")
        console.print("Run: [cyan]desk setup[/cyan]")
        sys.exit(1)
    return creds


@click.group()
@click.version_option(version=__version__)
@click.option("--verbose", "-v", is_flag=True, help="Verbose output")
@click.pass_context
def main(ctx: click.Context, verbose: bool) -> None:
    """Desk - Google Workspace from the command line."""
    ctx.ensure_object(dict)
    ctx.obj["verbose"] = verbose

    # Auto-migrate legacy ~/.gmail-cli/ config
    if migrate_legacy_config():
        console.print("[dim]Migrated config from ~/.gmail-cli/ to ~/.desk/[/dim]")
        console.print("[dim]Run 'desk auth login' to grant expanded API access.[/dim]")


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


# --- Register subcommand groups ---

from desk.commands.cal import cal  # noqa: E402
from desk.commands.docs import docs  # noqa: E402
from desk.commands.drive import drive  # noqa: E402
from desk.commands.mail import mail  # noqa: E402
from desk.commands.sheets import sheets  # noqa: E402

main.add_command(mail)
main.add_command(drive)
main.add_command(sheets)
main.add_command(docs)
main.add_command(cal)


if __name__ == "__main__":
    main()
