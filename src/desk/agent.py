"""Agent-first utilities for Desk CLI.

This module provides the foundation for agent-optimized CLI output:
- Structured error responses with suggestions
- Operation receipts with undo commands
- Enhanced dry-run previews
- Capabilities introspection

See ADR-004 for design rationale.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from enum import Enum
from typing import Any


class ErrorCode(str, Enum):
    """Machine-readable error codes for agent consumption."""

    # Authentication errors
    AUTH_REQUIRED = "AUTH_REQUIRED"
    AUTH_EXPIRED = "AUTH_EXPIRED"
    AUTH_INVALID = "AUTH_INVALID"

    # Resource errors
    MESSAGE_NOT_FOUND = "MESSAGE_NOT_FOUND"
    THREAD_NOT_FOUND = "THREAD_NOT_FOUND"
    LABEL_NOT_FOUND = "LABEL_NOT_FOUND"
    FILE_NOT_FOUND = "FILE_NOT_FOUND"
    FOLDER_NOT_FOUND = "FOLDER_NOT_FOUND"
    EVENT_NOT_FOUND = "EVENT_NOT_FOUND"
    DOCUMENT_NOT_FOUND = "DOCUMENT_NOT_FOUND"
    SPREADSHEET_NOT_FOUND = "SPREADSHEET_NOT_FOUND"
    FORM_NOT_FOUND = "FORM_NOT_FOUND"

    # Permission errors
    PERMISSION_DENIED = "PERMISSION_DENIED"
    QUOTA_EXCEEDED = "QUOTA_EXCEEDED"
    RATE_LIMITED = "RATE_LIMITED"

    # Validation errors
    INVALID_QUERY = "INVALID_QUERY"
    INVALID_INPUT = "INVALID_INPUT"
    MISSING_REQUIRED = "MISSING_REQUIRED"

    # Operation errors
    OPERATION_FAILED = "OPERATION_FAILED"
    ALREADY_EXISTS = "ALREADY_EXISTS"
    CONFLICT = "CONFLICT"
    TIMEOUT = "TIMEOUT"
    INSUFFICIENT_SCOPES = "INSUFFICIENT_SCOPES"

    # File I/O errors
    LOCAL_FILE_NOT_FOUND = "LOCAL_FILE_NOT_FOUND"
    LOCAL_FILE_READ_ERROR = "LOCAL_FILE_READ_ERROR"
    LOCAL_FILE_WRITE_ERROR = "LOCAL_FILE_WRITE_ERROR"

    # Docs editing errors
    INDEX_OUT_OF_RANGE = "INDEX_OUT_OF_RANGE"
    INVALID_RANGE = "INVALID_RANGE"
    MARKDOWN_PARSE_ERROR = "MARKDOWN_PARSE_ERROR"
    TAB_NOT_FOUND = "TAB_NOT_FOUND"
    TAB_NAME_AMBIGUOUS = "TAB_NAME_AMBIGUOUS"



# Standard suggestions for common errors
ERROR_SUGGESTIONS: dict[ErrorCode, list[str]] = {
    ErrorCode.AUTH_REQUIRED: [
        "Run `desk auth login` to authenticate",
        "Or run `desk setup` for guided setup",
    ],
    ErrorCode.AUTH_EXPIRED: [
        "Run `desk auth login` to refresh credentials",
        "Token may have been revoked - check Google account security settings",
    ],
    ErrorCode.AUTH_INVALID: [
        "Run `desk auth login` to re-authenticate",
        "Token file may be corrupted - delete ~/.desk/token.json and re-login",
    ],
    ErrorCode.MESSAGE_NOT_FOUND: [
        "Run `desk mail search` to find valid message IDs",
        "The message may have been deleted",
        "Check `desk mail search in:trash` if recently deleted",
    ],
    ErrorCode.THREAD_NOT_FOUND: [
        "Run `desk mail threads` to find valid thread IDs",
        "The thread may have been deleted",
    ],
    ErrorCode.LABEL_NOT_FOUND: [
        "Run `desk mail labels` to list available labels",
        "Label names are case-sensitive",
        "Use `desk mail create-label` to create a new label",
    ],
    ErrorCode.FILE_NOT_FOUND: [
        "Run `desk drive search` to find valid file IDs",
        "The file may have been deleted or moved to trash",
        "Check `desk drive search trashed:true` for trashed files",
    ],
    ErrorCode.EVENT_NOT_FOUND: [
        "Run `desk cal today` or `desk cal week` to find valid event IDs",
        "The event may have been deleted or cancelled",
    ],
    ErrorCode.FORM_NOT_FOUND: [
        "Run `desk forms read` to check the form ID",
        "The form may have been deleted or you may not have access",
    ],
    ErrorCode.PERMISSION_DENIED: [
        "You may not have access to this resource",
        "Request access from the owner",
        "Check if the resource is shared with your account",
    ],
    ErrorCode.RATE_LIMITED: [
        "Wait a moment and retry the operation",
        "Consider reducing the frequency of requests",
    ],
    ErrorCode.INVALID_QUERY: [
        "Check the query syntax",
        "See Gmail search operators: https://support.google.com/mail/answer/7190",
    ],
    ErrorCode.INVALID_INPUT: [
        "Message IDs are hex strings like '19c3aa4804ae3ab4'",
        "Use `desk mail search` to find valid message IDs",
        "Check for typos or truncated IDs",
    ],
    ErrorCode.OPERATION_FAILED: [
        "Check the error message for details",
        "Verify you have permission for this operation",
        "Try the operation again - it may be a temporary issue",
    ],
    ErrorCode.LOCAL_FILE_NOT_FOUND: [
        "Check that the file path is correct",
        "Use an absolute path to avoid ambiguity",
    ],
    ErrorCode.TIMEOUT: [
        "The operation is taking longer than expected",
        "This can happen with large datasets (e.g., labels with many messages)",
        "The operation may still complete - check the result before retrying",
        "For very large labels, consider deleting manually in Gmail settings",
    ],
    ErrorCode.INDEX_OUT_OF_RANGE: [
        "Run `desk docs inspect <id>` to see document element indices",
        "Index 1 is the start of the document body",
        "Use --at end to insert at the end of the document",
    ],
    ErrorCode.INVALID_RANGE: [
        "Start index must be less than end index",
        "Both indices must be >= 1",
        "Run `desk docs inspect <id>` to see document element indices",
    ],
    ErrorCode.MARKDOWN_PARSE_ERROR: [
        "Check that the markdown content is valid",
        "Ensure the file is UTF-8 encoded",
    ],
    ErrorCode.TAB_NOT_FOUND: [
        "Run `desk docs list-tabs <document-id>` to see available tabs",
        "--tab accepts either a tab ID or a tab title (case-insensitive)",
    ],
    ErrorCode.TAB_NAME_AMBIGUOUS: [
        "Multiple tabs share that title — re-run with --tab <tabId> from the matches list",
        "Run `desk docs list-tabs <document-id>` to see all tabs with their IDs",
    ],
    ErrorCode.INSUFFICIENT_SCOPES: [
        "Your credentials don't include the required permissions",
        "Run `desk auth login` to re-authenticate with updated scopes",
        "This often happens after desk adds new features requiring additional permissions",
    ],
}


def parse_api_error(error_str: str) -> str:
    """Extract human-readable message from API error strings.

    Google API errors often look like:
    <HttpError 400 when requesting ... returned "Invalid id value". Details: "...">

    This extracts just the useful part: "Invalid id value"
    """
    import re

    # Try to extract quoted message from HttpError format
    # Pattern: returned "message" or "reason": "message"
    patterns = [
        r'returned "([^"]+)"',  # <HttpError ... returned "message">
        r'"message":\s*"([^"]+)"',  # {"message": "..."}
        r'"reason":\s*"([^"]+)"',  # {"reason": "..."}
        r'Error:\s*(.+?)(?:\.|$)',  # Error: message.
    ]

    for pattern in patterns:
        match = re.search(pattern, error_str)
        if match:
            return match.group(1)

    # If no pattern matches, try to clean up the string
    # Remove common prefixes
    cleaned = error_str
    prefixes_to_remove = [
        "Gmail API error: ",
        "Drive API error: ",
        "Calendar API error: ",
        "Sheets API error: ",
        "Docs API error: ",
        "Forms API error: ",
    ]
    for prefix in prefixes_to_remove:
        if cleaned.startswith(prefix):
            cleaned = cleaned[len(prefix):]
            break

    # Truncate if too long (likely contains full HTTP response)
    if len(cleaned) > 200:
        # Try to find a natural break point
        for sep in [". ", ": ", " - "]:
            if sep in cleaned[:150]:
                cleaned = cleaned[:cleaned.index(sep) + 1]
                break
        else:
            cleaned = cleaned[:150] + "..."

    return cleaned


def structured_error(
    code: ErrorCode,
    message: str,
    suggestions: list[str] | None = None,
    retryable: bool = False,
    details: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Create a structured error response for agent consumption.

    Args:
        code: Machine-readable error code
        message: Human-readable error description
        suggestions: List of actionable suggestions (uses defaults if None)
        retryable: Whether the operation might succeed if retried
        details: Additional context about the error

    Returns:
        Structured error dict suitable for JSON output
    """
    if suggestions is None:
        suggestions = ERROR_SUGGESTIONS.get(code, [])

    return {
        "success": False,
        "error": {
            "code": code.value,
            "message": message,
            "suggestions": suggestions,
            "retryable": retryable,
            "details": details or {},
        },
    }


def operation_receipt(
    operation: str,
    target: dict[str, Any] | list[dict[str, Any]],
    undo_command: str | None = None,
    undo_expires: str | None = None,
    changes: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Create an operation receipt for agent consumption.

    Args:
        operation: Name of the operation performed (e.g., "archive", "trash")
        target: Details about what was affected (single item or list)
        undo_command: Command to reverse this operation (None if irreversible)
        undo_expires: When undo becomes unavailable (None = no expiration)
        changes: Details about what changed (labels added/removed, etc.)

    Returns:
        Structured receipt dict suitable for JSON output
    """
    # Normalize target to handle single items and lists
    if isinstance(target, list):
        targets = target
        count = len(target)
    else:
        targets = [target]
        count = 1

    receipt: dict[str, Any] = {
        "success": True,
        "operation": operation,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "count": count,
        "targets": targets,
    }

    if changes:
        receipt["changes"] = changes

    receipt["undo"] = {
        "available": undo_command is not None,
        "command": undo_command,
        "expires": undo_expires,
    }

    return receipt


def dry_run_preview(
    operation: str,
    targets: list[dict[str, Any]],
    reversible: bool = True,
    undo_command: str | None = None,
    warnings: list[str] | None = None,
) -> dict[str, Any]:
    """Create a dry-run preview for agent consumption.

    Args:
        operation: Name of the operation that would be performed
        targets: Details about what would be affected
        reversible: Whether the operation can be undone
        undo_command: Command that would reverse this operation
        warnings: Any warnings about the operation

    Returns:
        Structured preview dict suitable for JSON output
    """
    return {
        "dry_run": True,
        "would_execute": operation,
        "count": len(targets),
        "targets": targets,
        "reversible": reversible,
        "undo_would_be": undo_command,
        "warnings": warnings or [],
    }


# Undo command templates for common operations
UNDO_COMMANDS: dict[str, dict[str, Any]] = {
    # Mail operations
    "archive": {
        "template": "desk mail unarchive {ids}",
        "expires": None,
        "reversible": True,
    },
    "unarchive": {
        "template": "desk mail archive {ids}",
        "expires": None,
        "reversible": True,
    },
    "trash": {
        "template": "desk mail untrash {ids}",
        "expires": "30 days (auto-deleted after)",
        "reversible": True,
    },
    "untrash": {
        "template": "desk mail trash {ids}",
        "expires": None,
        "reversible": True,
    },
    "mark-read": {
        "template": "desk mail mark-unread {ids}",
        "expires": None,
        "reversible": True,
    },
    "mark-unread": {
        "template": "desk mail mark-read {ids}",
        "expires": None,
        "reversible": True,
    },
    "star": {
        "template": "desk mail unstar {ids}",
        "expires": None,
        "reversible": True,
    },
    "unstar": {
        "template": "desk mail star {ids}",
        "expires": None,
        "reversible": True,
    },
    "label": {
        "template": "desk mail remove-label {label} {ids}",
        "expires": None,
        "reversible": True,
    },
    "remove-label": {
        "template": "desk mail label {label} {ids}",
        "expires": None,
        "reversible": True,
    },
    "thread-archive": {
        "template": "desk mail thread-label INBOX {id}",
        "expires": None,
        "reversible": True,
    },
    "thread-trash": {
        "template": "desk mail thread-untrash {id}",
        "expires": "30 days (auto-deleted after)",
        "reversible": True,
    },
    "thread-label": {
        "template": "desk mail thread-remove-label {label} {id}",
        "expires": None,
        "reversible": True,
    },
    # Drive operations
    "drive-trash": {
        "template": "desk drive untrash {id}",
        "expires": "30 days (auto-deleted after)",
        "reversible": True,
    },
    "drive-star": {
        "template": "desk drive unstar {id}",
        "expires": None,
        "reversible": True,
    },
    "drive-unstar": {
        "template": "desk drive star {id}",
        "expires": None,
        "reversible": True,
    },
    # Calendar operations
    "cal-delete": {
        "template": None,
        "expires": None,
        "reversible": False,
    },
    # Send operations (irreversible)
    "send": {
        "template": None,
        "expires": None,
        "reversible": False,
    },
    "reply": {
        "template": None,
        "expires": None,
        "reversible": False,
    },
    "forward": {
        "template": None,
        "expires": None,
        "reversible": False,
    },
}


def get_undo_info(
    operation: str,
    ids: list[str] | str | None = None,
    label: str | None = None,
) -> tuple[str | None, str | None, bool]:
    """Get undo command and expiration for an operation.

    Args:
        operation: Name of the operation
        ids: ID(s) affected by the operation
        label: Label name (for label operations)

    Returns:
        Tuple of (undo_command, expires, reversible)
    """
    info = UNDO_COMMANDS.get(operation)
    if not info:
        return None, None, False

    template = info["template"]
    expires = info["expires"]
    reversible = info["reversible"]

    if template is None:
        return None, expires, reversible

    # Format the template with actual values
    if isinstance(ids, list):
        ids_str = " ".join(ids)
    elif ids:
        ids_str = ids
    else:
        ids_str = ""

    undo_cmd = template.format(ids=ids_str, id=ids_str, label=label or "")
    undo_cmd = " ".join(undo_cmd.split())  # Clean up extra spaces

    return undo_cmd, expires, reversible


def format_error_for_human(error_response: dict[str, Any]) -> str:
    """Format a structured error for human-readable output.

    Args:
        error_response: Structured error from structured_error()

    Returns:
        Formatted string for console output
    """
    err = error_response["error"]
    lines = [
        f"[red]Error: {err['message']} ({err['code']})[/red]",
    ]

    if err["suggestions"]:
        lines.append("")
        lines.append("[dim]Suggestions:[/dim]")
        for suggestion in err["suggestions"]:
            lines.append(f"  [cyan]- {suggestion}[/cyan]")

    return "\n".join(lines)


def format_receipt_for_human(receipt: dict[str, Any]) -> str:
    """Format an operation receipt for human-readable output.

    Args:
        receipt: Structured receipt from operation_receipt()

    Returns:
        Formatted string for console output
    """
    lines = [
        f"[green]Success: {receipt['operation']}[/green]",
    ]

    if receipt["count"] == 1:
        target = receipt["targets"][0]
        if "subject" in target:
            lines.append(f"  Subject: {target['subject']}")
        if "from" in target:
            lines.append(f"  From: {target['from']}")
        if "name" in target:
            lines.append(f"  Name: {target['name']}")
        if "id" in target:
            lines.append(f"  ID: [dim]{target['id']}[/dim]")
    else:
        lines.append(f"  Affected: {receipt['count']} item(s)")

    undo = receipt.get("undo", {})
    if undo.get("available") and undo.get("command"):
        lines.append("")
        lines.append(f"[dim]Undo: {undo['command']}[/dim]")
        if undo.get("expires"):
            lines.append(f"[dim]Expires: {undo['expires']}[/dim]")

    return "\n".join(lines)


def format_dry_run_for_human(preview: dict[str, Any]) -> str:
    """Format a dry-run preview for human-readable output.

    Args:
        preview: Structured preview from dry_run_preview()

    Returns:
        Formatted string for console output
    """
    lines = [
        "[yellow]DRY RUN - No changes made[/yellow]",
        "",
        f"Would {preview['would_execute']} {preview['count']} item(s):",
    ]

    # Show up to 5 targets
    for target in preview["targets"][:5]:
        if "subject" in target:
            lines.append(f"  - {target['subject']} (from {target.get('from', 'unknown')})")
        elif "name" in target:
            lines.append(f"  - {target['name']}")
        elif "id" in target:
            lines.append(f"  - {target['id']}")

    if preview["count"] > 5:
        lines.append(f"  ... and {preview['count'] - 5} more")

    lines.append("")
    if preview["reversible"]:
        lines.append("[dim]This action is reversible.[/dim]")
        if preview.get("undo_would_be"):
            lines.append(f"[dim]Undo would be: {preview['undo_would_be']}[/dim]")
    else:
        lines.append("[yellow]This action cannot be undone.[/yellow]")

    if preview.get("warnings"):
        lines.append("")
        for warning in preview["warnings"]:
            lines.append(f"[yellow]Warning: {warning}[/yellow]")

    return "\n".join(lines)


def output_result(
    result: dict[str, Any],
    as_json: bool,
    quiet: bool = False,
    formatter: callable = None,
) -> None:
    """Output a result in the appropriate format.

    Args:
        result: Structured result (error, receipt, or preview)
        as_json: Whether to output as JSON
        quiet: Whether to suppress human-readable output
        formatter: Custom formatter for human output (auto-detected if None)
    """
    from rich.console import Console

    console = Console()

    if as_json:
        print(json.dumps(result, indent=2))
        return

    if quiet:
        return

    # Auto-detect formatter based on result structure
    if formatter is None:
        if "error" in result:
            formatter = format_error_for_human
        elif "dry_run" in result:
            formatter = format_dry_run_for_human
        elif "operation" in result and "targets" in result:
            formatter = format_receipt_for_human
        else:
            # Fallback to JSON
            print(json.dumps(result, indent=2))
            return

    console.print(formatter(result))
