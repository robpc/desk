"""Forms commands — create and manage Google Forms."""

import json
import sys

import click
from rich.console import Console
from rich.markup import escape

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
from desk.services.forms import FormsClient

console = Console()


def _get_client(as_json: bool = False) -> FormsClient:
    """Get authenticated Forms client or exit."""
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
    return FormsClient(creds)


def _handle_api_error(e: Exception, as_json: bool, context: dict | None = None) -> None:
    """Handle API errors with structured output when --json is used."""
    raw_error = str(e)
    error_msg = parse_api_error(raw_error)

    if is_scope_error(raw_error):
        code = ErrorCode.INSUFFICIENT_SCOPES
    elif "not found" in raw_error.lower() or "404" in raw_error:
        code = ErrorCode.FORM_NOT_FOUND
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
def forms() -> None:
    """Google Forms — create and manage surveys."""
    pass


@forms.command()
@click.argument("title")
@click.option("--description", "-d", default="", help="Form description")
@click.option("--quiet", "-q", is_flag=True, help="Suppress success messages")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def create(title: str, description: str, quiet: bool, as_json: bool) -> None:
    """Create a new Google Form.

    Examples:

        desk forms create "Weekly Survey"

        desk forms create "Feedback Form" --description "Tell us what you think"
    """
    client = _get_client(as_json)
    try:
        result = client.create(title, description=description)
    except Exception as e:
        _handle_api_error(e, as_json, {"title": title})

    form_id = result.get("formId")
    receipt = operation_receipt(
        operation="create",
        target={
            "id": form_id,
            "title": result.get("title"),
            "link": result.get("responderUri"),
            "editLink": result.get("editUri"),
            "next": f"desk forms publish {form_id}",
        },
    )
    output_result(receipt, as_json, quiet)


@forms.command()
@click.argument("form_id")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def read(form_id: str, as_json: bool) -> None:
    """Read form structure and questions.

    Examples:

        desk forms read <form-id>
    """
    client = _get_client(as_json)
    try:
        result = client.read(form_id)
    except Exception as e:
        _handle_api_error(e, as_json, {"form_id": form_id})

    if as_json:
        print(json.dumps(result, indent=2))
        return

    console.print(f"[bold]{result['title']}[/bold]")
    if result.get("description"):
        console.print(result["description"])
    if "isPublished" in result:
        pub = (
            "[green]published[/green]"
            if result["isPublished"]
            else "[yellow]unpublished[/yellow]"
        )
        acc = (
            "[green]accepting responses[/green]"
            if result.get("isAcceptingResponses")
            else "[yellow]not accepting responses[/yellow]"
        )
        console.print(f"  {pub} · {acc}")
    console.print()
    for i, item in enumerate(result.get("items", []), 1):
        item_type = item.get("type", "unknown")
        item_id = item.get("itemId", "")
        if item_type == "section":
            id_label = f"  [dim](id: {item_id})[/dim]" if item_id else ""
            console.print(f"\n[bold]--- {item['title']} ---[/bold]{id_label}")
            if item.get("description"):
                console.print(f"[dim]{item['description']}[/dim]")
        else:
            req = " [red]*[/red]" if item.get("required") else ""
            console.print(f"  Q{i}. {item['title']}{req}  [dim]({item_type})[/dim]")
            if item.get("options"):
                for opt in item["options"]:
                    if isinstance(opt, dict):
                        label = opt.get("value", "")
                        target = opt.get("goToSectionId") or opt.get("goToAction", "")
                        if target:
                            console.print(f"      - {label}  [dim]→ {target}[/dim]")
                        else:
                            console.print(f"      - {label}")
                    else:
                        console.print(f"      - {opt}")


@forms.command()
@click.argument("form_id")
@click.option("--limit", "-n", default=100, help="Maximum responses to return")
@click.option("--page-token", default=None, help="Token for next page of results")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def responses(form_id: str, limit: int, page_token: str | None, as_json: bool) -> None:
    """List form responses.

    Examples:

        desk forms responses <form-id>

        desk forms responses <form-id> --limit 10

        desk forms responses <form-id> --page-token <token>
    """
    client = _get_client(as_json)
    try:
        result = client.responses(form_id, limit=limit, page_token=page_token)
    except Exception as e:
        _handle_api_error(e, as_json, {"form_id": form_id})

    if as_json:
        print(json.dumps(result, indent=2))
        return

    count = result.get("responseCount", 0)
    console.print(f"[bold]{count} response(s)[/bold]")
    for resp in result.get("responses", []):
        ts = resp.get("lastSubmittedTime", "")
        console.print(f"\n  [dim]{ts}[/dim]")
        for qid, answer in resp.get("answers", {}).items():
            text_answers = answer.get("textAnswers", {}).get("answers", [])
            values = [a.get("value", "") for a in text_answers]
            console.print(f"    {', '.join(values)}")

    next_token = result.get("nextPageToken")
    if next_token:
        console.print(f"\n[dim](more results available, use --page-token {next_token})[/dim]")


@forms.command("add-question")
@click.argument("form_id")
@click.argument("title")
@click.option(
    "--type",
    "question_type",
    type=click.Choice(["text", "paragraph", "choice", "checkbox", "dropdown", "scale"]),
    default="text",
    help="Question type",
)
@click.option("--required", is_flag=True, help="Make question required")
@click.option("--choices", "-c", multiple=True, help="Options for choice/checkbox/dropdown")
@click.option(
    "--goto",
    "-g",
    multiple=True,
    help="Branch: CHOICE=SECTION_ID (e.g., 'Yes=voice_section')",
)
@click.option("--quiet", "-q", is_flag=True, help="Suppress success messages")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def add_question(
    form_id: str,
    title: str,
    question_type: str,
    required: bool,
    choices: tuple[str, ...],
    goto: tuple[str, ...],
    quiet: bool,
    as_json: bool,
) -> None:
    """Add a question to a form.

    Examples:

        desk forms add-question <id> "What's your name?"

        desk forms add-question <id> "Tell us more" --type paragraph

        desk forms add-question <id> "Favorite color?" --type choice -c Red -c Blue -c Green

        desk forms add-question <id> "Rate 1-5" --type scale --required

        desk forms add-question <id> "Tried voice?" --type choice -c Yes -c No \\
            --goto "Yes=voice_section" --goto "No=guides_section"
    """
    # Parse --goto pairs into dict
    goto_map: dict[str, str] | None = None
    if goto:
        if question_type not in ("choice", "dropdown"):
            msg = "Branching (--goto) is only supported for choice and dropdown types"
            if as_json:
                error = structured_error(ErrorCode.INVALID_INPUT, msg)
                print(json.dumps(error, indent=2), file=sys.stderr)
            else:
                error_console.print(f"[red]Error: {msg}[/red]")
            sys.exit(1)
        goto_map = {}
        for pair in goto:
            if "=" not in pair:
                msg = f"Invalid --goto format: '{pair}' (expected CHOICE=SECTION_ID)"
                if as_json:
                    error = structured_error(ErrorCode.INVALID_INPUT, msg)
                    print(json.dumps(error, indent=2), file=sys.stderr)
                else:
                    error_console.print(f"[red]Error: {msg}[/red]")
                sys.exit(1)
            key, value = pair.split("=", 1)
            key, value = key.strip(), value.strip()
            if not key or not value:
                msg = f"Invalid --goto format: '{pair}' (choice and section ID must not be empty)"
                if as_json:
                    error = structured_error(ErrorCode.INVALID_INPUT, msg)
                    print(json.dumps(error, indent=2), file=sys.stderr)
                else:
                    error_console.print(f"[red]Error: {msg}[/red]")
                sys.exit(1)
            goto_map[key] = value

    client = _get_client(as_json)
    try:
        client.add_question(
            form_id,
            title,
            question_type=question_type,
            required=required,
            choices=list(choices) if choices else None,
            goto=goto_map,
        )
    except ValueError as e:
        if as_json:
            error = structured_error(ErrorCode.INVALID_INPUT, str(e))
            print(json.dumps(error, indent=2), file=sys.stderr)
        else:
            error_console.print(f"[red]Error: {e}[/red]")
        sys.exit(1)
    except Exception as e:
        _handle_api_error(e, as_json, {"form_id": form_id, "title": title})

    receipt = operation_receipt(
        operation="add-question",
        target={"id": form_id, "question": title, "type": question_type},
    )
    output_result(receipt, as_json, quiet)


@forms.command("add-section")
@click.argument("form_id")
@click.argument("title")
@click.option("--id", "section_id", default=None, help="Section ID for branching references")
@click.option("--description", "-d", default="", help="Section description")
@click.option("--quiet", "-q", is_flag=True, help="Suppress success messages")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def add_section(
    form_id: str, title: str, section_id: str | None, description: str, quiet: bool, as_json: bool
) -> None:
    """Add a section break to a form.

    Examples:

        desk forms add-section <id> "Part 2: Details"

        desk forms add-section <id> "Background" --description "Tell us about yourself"

        desk forms add-section <id> "Voice Details" --id voice_section
    """
    client = _get_client(as_json)
    try:
        client.add_section(form_id, title, description=description, section_id=section_id)
    except Exception as e:
        _handle_api_error(e, as_json, {"form_id": form_id, "title": title})

    receipt = operation_receipt(
        operation="add-section",
        target={"id": form_id, "section": title},
    )
    output_result(receipt, as_json, quiet)


def _parse_goto(goto: tuple[str, ...], as_json: bool) -> dict[str, str] | None:
    """Parse --goto flag pairs into a dict. Exits on invalid input."""
    if not goto:
        return None
    goto_map: dict[str, str] = {}
    for pair in goto:
        if "=" not in pair:
            msg = f"Invalid --goto format: '{pair}' (expected CHOICE=SECTION_ID)"
            if as_json:
                error = structured_error(ErrorCode.INVALID_INPUT, msg)
                print(json.dumps(error, indent=2), file=sys.stderr)
            else:
                error_console.print(f"[red]Error: {msg}[/red]")
            sys.exit(1)
        key, value = pair.split("=", 1)
        key, value = key.strip(), value.strip()
        if not key or not value:
            msg = f"Invalid --goto format: '{pair}' (choice and section ID must not be empty)"
            if as_json:
                error = structured_error(ErrorCode.INVALID_INPUT, msg)
                print(json.dumps(error, indent=2), file=sys.stderr)
            else:
                error_console.print(f"[red]Error: {msg}[/red]")
            sys.exit(1)
        goto_map[key] = value
    return goto_map


@forms.command("update")
@click.argument("form_id")
@click.option("--title", default=None, help="New form title")
@click.option("--description", "-d", default=None, help="New form description")
@click.option("--quiet", "-q", is_flag=True, help="Suppress success messages")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def update(
    form_id: str, title: str | None, description: str | None, quiet: bool, as_json: bool
) -> None:
    """Update form metadata (title and/or description).

    Examples:

        desk forms update <form-id> --title "New Title"

        desk forms update <form-id> --description "Updated description"

        desk forms update <form-id> --title "New" --description "Both changed"
    """
    if title is None and description is None:
        msg = "At least one of --title or --description is required"
        if as_json:
            error = structured_error(ErrorCode.INVALID_INPUT, msg)
            print(json.dumps(error, indent=2), file=sys.stderr)
        else:
            error_console.print(f"[red]Error: {msg}[/red]")
        sys.exit(1)

    client = _get_client(as_json)
    try:
        client.update_form(form_id, title=title, description=description)
    except Exception as e:
        _handle_api_error(e, as_json, {"form_id": form_id})

    changes: dict = {}
    if title is not None:
        changes["title"] = title
    if description is not None:
        changes["description"] = description

    receipt = operation_receipt(
        operation="update",
        target={"id": form_id},
        changes=changes,
    )
    output_result(receipt, as_json, quiet)


@forms.command("update-question")
@click.argument("form_id")
@click.argument("item_id")
@click.option("--title", default=None, help="New question text")
@click.option("--required/--no-required", default=None, help="Set required flag")
@click.option("--choices", "-c", multiple=True, help="Replace options (choice/checkbox/dropdown)")
@click.option(
    "--goto",
    "-g",
    multiple=True,
    help="Branch: CHOICE=SECTION_ID (e.g., 'Yes=voice_section')",
)
@click.option("--quiet", "-q", is_flag=True, help="Suppress success messages")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def update_question(
    form_id: str,
    item_id: str,
    title: str | None,
    required: bool | None,
    choices: tuple[str, ...],
    goto: tuple[str, ...],
    quiet: bool,
    as_json: bool,
) -> None:
    """Update a question in a form.

    Does not support changing question type. Delete and re-add instead.

    Examples:

        desk forms update-question <form-id> <item-id> --title "Fixed typo?"

        desk forms update-question <form-id> <item-id> --required

        desk forms update-question <form-id> <item-id> -c Red -c Blue -c Green
    """
    goto_map = _parse_goto(goto, as_json)

    client = _get_client(as_json)
    try:
        client.update_item(
            form_id,
            item_id,
            title=title,
            required=required,
            choices=list(choices) if choices else None,
            goto=goto_map,
        )
    except ValueError as e:
        if as_json:
            error = structured_error(ErrorCode.INVALID_INPUT, str(e))
            print(json.dumps(error, indent=2), file=sys.stderr)
        else:
            error_console.print(f"[red]Error: {e}[/red]")
        sys.exit(1)
    except Exception as e:
        _handle_api_error(e, as_json, {"form_id": form_id, "item_id": item_id})

    receipt = operation_receipt(
        operation="update-question",
        target={"id": form_id, "itemId": item_id},
    )
    output_result(receipt, as_json, quiet)


@forms.command("update-section")
@click.argument("form_id")
@click.argument("item_id")
@click.option("--title", default=None, help="New section title")
@click.option("--description", "-d", default=None, help="New section description")
@click.option("--quiet", "-q", is_flag=True, help="Suppress success messages")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def update_section(
    form_id: str,
    item_id: str,
    title: str | None,
    description: str | None,
    quiet: bool,
    as_json: bool,
) -> None:
    """Update a section in a form.

    Examples:

        desk forms update-section <form-id> <item-id> --title "New Section Title"

        desk forms update-section <form-id> <item-id> --description "Updated description"
    """
    if title is None and description is None:
        msg = "At least one of --title or --description is required"
        if as_json:
            error = structured_error(ErrorCode.INVALID_INPUT, msg)
            print(json.dumps(error, indent=2), file=sys.stderr)
        else:
            error_console.print(f"[red]Error: {msg}[/red]")
        sys.exit(1)

    client = _get_client(as_json)
    try:
        client.update_item(form_id, item_id, title=title, description=description)
    except ValueError as e:
        if as_json:
            error = structured_error(ErrorCode.INVALID_INPUT, str(e))
            print(json.dumps(error, indent=2), file=sys.stderr)
        else:
            error_console.print(f"[red]Error: {e}[/red]")
        sys.exit(1)
    except Exception as e:
        _handle_api_error(e, as_json, {"form_id": form_id, "item_id": item_id})

    receipt = operation_receipt(
        operation="update-section",
        target={"id": form_id, "itemId": item_id},
    )
    output_result(receipt, as_json, quiet)


@forms.command("delete-item")
@click.argument("form_id")
@click.argument("item_id")
@click.option("--yes", is_flag=True, help="Skip confirmation prompt")
@click.option("--quiet", "-q", is_flag=True, help="Suppress success messages")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def delete_item(form_id: str, item_id: str, yes: bool, quiet: bool, as_json: bool) -> None:
    """Delete an item (question or section) from a form.

    Examples:

        desk forms delete-item <form-id> <item-id> --yes

        desk forms delete-item <form-id> <item-id> --yes --json
    """
    if not yes:
        if as_json:
            error = structured_error(
                ErrorCode.INVALID_INPUT,
                "Confirmation required: pass --yes to confirm deletion",
            )
            print(json.dumps(error, indent=2), file=sys.stderr)
        else:
            error_console.print("[red]Error: Confirmation required: pass --yes to confirm deletion[/red]")
        sys.exit(1)

    client = _get_client(as_json)
    try:
        client.delete_item(form_id, item_id)
    except ValueError as e:
        if as_json:
            error = structured_error(ErrorCode.INVALID_INPUT, str(e))
            print(json.dumps(error, indent=2), file=sys.stderr)
        else:
            error_console.print(f"[red]Error: {e}[/red]")
        sys.exit(1)
    except Exception as e:
        _handle_api_error(e, as_json, {"form_id": form_id, "item_id": item_id})

    receipt = operation_receipt(
        operation="delete-item",
        target={"id": form_id, "itemId": item_id},
    )
    output_result(receipt, as_json, quiet)


@forms.command("publish")
@click.argument("form_id")
@click.option(
    "--accepting/--no-accepting",
    default=True,
    help="Whether the form accepts new responses (default: accepting)",
)
@click.option("--quiet", "-q", is_flag=True, help="Suppress success messages")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def publish(
    form_id: str, accepting: bool, quiet: bool, as_json: bool
) -> None:
    """Publish a form so it can accept responses.

    Use --no-accepting to keep the form published but stop accepting
    new responses (respondents see a closed message).

    Examples:

        desk forms publish <form-id>

        desk forms publish <form-id> --no-accepting
    """
    client = _get_client(as_json)
    try:
        client.publish(form_id, accepting_responses=accepting)
    except Exception as e:
        _handle_api_error(e, as_json, {"form_id": form_id})

    receipt = operation_receipt(
        operation="publish",
        target={"id": form_id, "acceptingResponses": accepting},
    )
    output_result(receipt, as_json, quiet)


@forms.command("unpublish")
@click.argument("form_id")
@click.option("--quiet", "-q", is_flag=True, help="Suppress success messages")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def unpublish(form_id: str, quiet: bool, as_json: bool) -> None:
    """Unpublish a form (stops accepting responses automatically).

    Examples:

        desk forms unpublish <form-id>
    """
    client = _get_client(as_json)
    try:
        client.unpublish(form_id)
    except Exception as e:
        _handle_api_error(e, as_json, {"form_id": form_id})

    receipt = operation_receipt(
        operation="unpublish",
        target={"id": form_id},
    )
    output_result(receipt, as_json, quiet)
