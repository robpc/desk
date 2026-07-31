"""Meet commands — meeting-space recording and transcription settings.

See ADR-036. Co-hosts are not here: `spaces.members.create` is gated behind
Google's Developer Preview Program, so it stays a UI-only step.
"""

import json
import sys

import click
from rich.console import Console
from rich.markup import escape

from desk.agent import (
    ERROR_SUGGESTIONS,
    ErrorCode,
    enforce_scopes,
    is_scope_error,
    operation_receipt,
    output_result,
    parse_api_error,
    structured_error,
)
from desk.auth import get_credentials, get_last_auth_failure
from desk.config import scopes_for_service
from desk.console import error_console
from desk.services.meet import AUTO_GENERATION_CHOICES, MeetClient

console = Console()


def _get_client(as_json: bool = False) -> MeetClient:
    """Get authenticated Meet client or exit.

    Gates the whole service on `meetings.space.settings` (ADR-034/036) — this is
    a scope no existing token has, so the fast fail here is the common path until
    users re-auth.
    """
    enforce_scopes(scopes_for_service("meet"), as_json)
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
    return MeetClient(creds)


def _handle_api_error(e: Exception, as_json: bool, context: dict | None = None) -> None:
    """Handle API errors with structured output when --json is used."""
    raw_error = str(e)
    error_msg = parse_api_error(raw_error)

    if is_scope_error(raw_error):
        code = ErrorCode.INSUFFICIENT_SCOPES
    elif "not found" in raw_error.lower() or "404" in raw_error:
        code = ErrorCode.SPACE_NOT_FOUND
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
def meet() -> None:
    """Google Meet — meeting-space recording and transcription settings.

    A space is addressed by its meeting code (the `abc-defg-hij` in a Meet URL)
    or its space ID. `desk cal` reports this as `conferenceId` on any event with
    a Meet link, so the two compose:

        desk cal create "Training" --start ... --end ... --meet --json
        desk meet update <conferenceId> --auto-record on

    Not supported — Google limitations, not Desk ones:

    \b
      - Co-hosts. Turning on host management and naming co-hosts is UI-only;
        the Meet API's space-members endpoint is restricted to Google's
        Developer Preview Program. Note the ordering trap when doing it by
        hand: co-hosts are picked from the event's invited guests, so add
        guests first or the picker is empty.
      - Per-occurrence settings. Artifact settings belong to the space, so on a
        recurring event they apply to every occurrence.
    """
    pass


@meet.command()
@click.argument("space")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def read(space: str, as_json: bool) -> None:
    """Read a meeting space's settings.

    SPACE is a meeting code (abc-defg-hij), a space ID, or a full spaces/… name.

    Examples:

        desk meet read abc-defg-hij

        desk meet read abc-defg-hij --json
    """
    client = _get_client(as_json)

    try:
        result = client.get_space(space)
    except Exception as e:
        _handle_api_error(e, as_json, {"space": space})

    if as_json:
        print(json.dumps(result, indent=2))
        return

    console.print(f"[bold]{escape(result['meetingCode'] or result['name'])}[/bold]")
    if result["meetingUri"]:
        console.print(f"  URI:            {result['meetingUri']}")
    console.print(f"  Auto-record:    {result['autoRecord'] or '(unset)'}")
    console.print(f"  Auto-transcript:{result['autoTranscript'] or '(unset)'}")
    console.print(f"  Auto smart notes:{result['autoSmartNotes'] or '(unset)'}")
    if result["moderation"]:
        console.print(f"  Moderation:     {result['moderation']}")


@meet.command()
@click.argument("space")
@click.option(
    "--auto-record",
    type=click.Choice(AUTO_GENERATION_CHOICES),
    help="Record the meeting automatically",
)
@click.option(
    "--auto-transcript",
    type=click.Choice(AUTO_GENERATION_CHOICES),
    help="Transcribe the meeting automatically",
)
@click.option(
    "--auto-smart-notes",
    type=click.Choice(AUTO_GENERATION_CHOICES),
    help="Generate smart notes automatically",
)
@click.option("--quiet", "-q", is_flag=True, help="Suppress success messages")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def update(
    space: str,
    auto_record: str | None,
    auto_transcript: str | None,
    auto_smart_notes: str | None,
    quiet: bool,
    as_json: bool,
) -> None:
    """Set a meeting space's auto-artifact settings.

    SPACE is a meeting code (abc-defg-hij), a space ID, or a full spaces/… name.

    Each setting takes on, off, or default — `default` stops overriding and
    defers to your Workspace policy. Settings you don't pass are left alone.

    Examples:

        desk meet update abc-defg-hij --auto-record on

        desk meet update abc-defg-hij --auto-record on --auto-transcript on

        desk meet update abc-defg-hij --auto-record default
    """
    client = _get_client(as_json)

    try:
        result = client.configure_artifacts(
            space,
            auto_record=auto_record,
            auto_transcript=auto_transcript,
            auto_smart_notes=auto_smart_notes,
        )
    except ValueError as e:
        if as_json:
            error = structured_error(
                ErrorCode.INVALID_INPUT,
                str(e),
                suggestions=[
                    "Pass at least one of --auto-record, --auto-transcript, "
                    "or --auto-smart-notes",
                    f"Values: {', '.join(AUTO_GENERATION_CHOICES)}",
                ],
            )
            print(json.dumps(error, indent=2), file=sys.stderr)
        else:
            error_console.print(f"[red]Error: {e}[/red]")
        sys.exit(1)
    except Exception as e:
        _handle_api_error(e, as_json, {"space": space})

    changes = {}
    if auto_record is not None:
        changes["autoRecord"] = result["autoRecord"] or auto_record
    if auto_transcript is not None:
        changes["autoTranscript"] = result["autoTranscript"] or auto_transcript
    if auto_smart_notes is not None:
        changes["autoSmartNotes"] = result["autoSmartNotes"] or auto_smart_notes

    receipt = operation_receipt(
        operation="update",
        target={
            "name": result["name"],
            "meetingCode": result["meetingCode"],
            "meetingUri": result["meetingUri"],
        },
        changes=changes,
    )
    output_result(receipt, as_json, quiet)
