"""Groups commands — search Google Groups / distribution lists and expand membership."""

import json
import sys

import click
from rich.console import Console
from rich.markup import escape
from rich.table import Table

from desk.agent import (
    ERROR_SUGGESTIONS,
    ErrorCode,
    parse_api_error,
    structured_error,
)
from desk.auth import get_credentials, get_last_auth_failure
from desk.console import error_console
from desk.services.groups import GroupsClient

console = Console()


def _get_client(as_json: bool = False) -> GroupsClient:
    """Get authenticated Groups client or exit."""
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
    return GroupsClient(creds)


def _handle_api_error(e: Exception, as_json: bool, context: dict | None = None) -> None:
    """Handle Directory API errors with structured output when --json is used."""
    raw_error = str(e)
    error_msg = parse_api_error(raw_error)

    if "not found" in raw_error.lower() or "404" in raw_error:
        code = ErrorCode.GROUP_NOT_FOUND
    elif "401" in raw_error or "invalid credentials" in raw_error.lower():
        code = ErrorCode.AUTH_EXPIRED
    elif "403" in raw_error or "permission" in raw_error.lower():
        # Directory reads are frequently admin-gated; surface that explicitly.
        code = ErrorCode.PERMISSION_DENIED
    elif "429" in raw_error or "rate" in raw_error.lower():
        code = ErrorCode.RATE_LIMITED
    elif "400" in raw_error or "invalid" in raw_error.lower():
        code = ErrorCode.INVALID_INPUT
    else:
        code = ErrorCode.OPERATION_FAILED

    suggestions = list(ERROR_SUGGESTIONS.get(code, []))
    if code == ErrorCode.PERMISSION_DENIED:
        suggestions = [
            "Reading group membership via the Directory API often requires Workspace admin or delegated access.",
            *suggestions,
        ]

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
def groups() -> None:
    """Google Groups — search distribution lists and expand membership."""
    pass


@groups.command()
@click.argument("group")
@click.option(
    "--role",
    default=None,
    help="Filter by role: OWNER, MANAGER, MEMBER (comma-separated for multiple).",
)
@click.option("--page-token", "page_token", default=None, help="Continue from previous page")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def members(
    group: str,
    role: str | None,
    page_token: str | None,
    as_json: bool,
) -> None:
    """List members of a group / distribution list.

    GROUP is the group's email address or unique ID.

    Examples:

        desk groups members orionteam@yahooinc.com

        desk groups members orionteam@yahooinc.com --role OWNER,MANAGER

        desk groups members orionteam@yahooinc.com --json
    """
    client = _get_client(as_json)

    try:
        result = client.list_members(group, roles=role, page_token=page_token)
    except Exception as e:
        _handle_api_error(e, as_json, {"group": group})

    if as_json:
        print(json.dumps(result, indent=2))
        return

    member_list = result.get("members", [])
    if not member_list:
        console.print(f"[dim]No members found for {escape(group)}.[/dim]")
        return

    table = Table(title=f"Members of {group}")
    table.add_column("Email", style="cyan", no_wrap=True)
    table.add_column("Role")
    table.add_column("Type")
    table.add_column("Status")
    for m in member_list:
        table.add_row(
            m.get("email", ""),
            m.get("role", ""),
            m.get("type", ""),
            m.get("status", ""),
        )
    console.print(table)
    console.print(f"\n[dim]{len(member_list)} member(s) shown.[/dim]")

    if result.get("nextPageToken"):
        console.print(f"[dim]More results available. Use --page-token {result['nextPageToken']}[/dim]")


@groups.command()
@click.argument("query", required=False, default=None)
@click.option("--domain", default=None, help="Restrict to a domain (default: your whole customer).")
@click.option("--page-token", "page_token", default=None, help="Continue from previous page")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def find(
    query: str | None,
    domain: str | None,
    page_token: str | None,
    as_json: bool,
) -> None:
    """Search for groups, or list all groups in scope.

    QUERY is an optional Directory search expression (e.g. ``name:orion*``
    or ``email:orion*``). Omit it to list every group you can see.

    Examples:

        desk groups find "email:orion*"

        desk groups find "name:Orion Team"

        desk groups find --domain yahooinc.com --json
    """
    client = _get_client(as_json)

    try:
        result = client.search_groups(query=query, domain=domain, page_token=page_token)
    except Exception as e:
        _handle_api_error(e, as_json, {"query": query, "domain": domain})

    if as_json:
        print(json.dumps(result, indent=2))
        return

    group_list = result.get("groups", [])
    if not group_list:
        console.print("[dim]No groups found.[/dim]")
        return

    table = Table(title="Groups")
    table.add_column("Email", style="cyan", no_wrap=True)
    table.add_column("Name")
    table.add_column("Members", justify="right")
    for g in group_list:
        table.add_row(
            g.get("email", ""),
            g.get("name", ""),
            str(g.get("directMembersCount", "")),
        )
    console.print(table)
    console.print(f"\n[dim]{len(group_list)} group(s) shown.[/dim]")

    if result.get("nextPageToken"):
        console.print(f"[dim]More results available. Use --page-token {result['nextPageToken']}[/dim]")


@groups.command()
@click.argument("group")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def get(group: str, as_json: bool) -> None:
    """Show a single group's metadata.

    GROUP is the group's email address or unique ID.

    Examples:

        desk groups get orionteam@yahooinc.com

        desk groups get orionteam@yahooinc.com --json
    """
    client = _get_client(as_json)

    try:
        result = client.get_group(group)
    except Exception as e:
        _handle_api_error(e, as_json, {"group": group})

    if as_json:
        print(json.dumps(result, indent=2))
        return

    table = Table(title=result.get("name") or result.get("email", group))
    table.add_column("Field", style="dim")
    table.add_column("Value")
    table.add_row("Email", result.get("email", ""))
    table.add_row("Name", result.get("name", ""))
    table.add_row("Description", result.get("description", ""))
    table.add_row("Members", str(result.get("directMembersCount", "")))
    aliases = result.get("aliases") or []
    if aliases:
        table.add_row("Aliases", ", ".join(aliases))
    console.print(table)
