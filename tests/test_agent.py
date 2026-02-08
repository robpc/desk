"""Tests for agent-first utilities in desk.agent module."""

import json
from datetime import datetime, timezone

import pytest

from desk.agent import (
    ErrorCode,
    ERROR_SUGGESTIONS,
    structured_error,
    operation_receipt,
    dry_run_preview,
    get_undo_info,
    parse_api_error,
    format_error_for_human,
    format_receipt_for_human,
    format_dry_run_for_human,
    UNDO_COMMANDS,
)


# -----------------------------------------------------------------------------
# structured_error tests
# -----------------------------------------------------------------------------


class TestStructuredError:
    """Tests for structured_error function."""

    def test_returns_success_false(self):
        """Error response should have success: false."""
        result = structured_error(
            ErrorCode.MESSAGE_NOT_FOUND,
            "Message not found",
        )
        assert result["success"] is False

    def test_contains_correct_error_code(self):
        """Error response should contain the correct error code as string."""
        result = structured_error(
            ErrorCode.AUTH_REQUIRED,
            "Authentication required",
        )
        assert result["error"]["code"] == "AUTH_REQUIRED"

    def test_uses_default_suggestions_when_not_provided(self):
        """Should use ERROR_SUGGESTIONS when suggestions not provided."""
        result = structured_error(
            ErrorCode.AUTH_REQUIRED,
            "Not authenticated",
        )
        expected_suggestions = ERROR_SUGGESTIONS[ErrorCode.AUTH_REQUIRED]
        assert result["error"]["suggestions"] == expected_suggestions

    def test_uses_custom_suggestions_when_provided(self):
        """Should use custom suggestions when explicitly provided."""
        custom_suggestions = ["Try this", "Or try that"]
        result = structured_error(
            ErrorCode.MESSAGE_NOT_FOUND,
            "Message not found",
            suggestions=custom_suggestions,
        )
        assert result["error"]["suggestions"] == custom_suggestions

    def test_sets_retryable_correctly(self):
        """Should set retryable flag correctly."""
        # Default is False
        result = structured_error(ErrorCode.MESSAGE_NOT_FOUND, "Not found")
        assert result["error"]["retryable"] is False

        # Explicitly True
        result = structured_error(
            ErrorCode.RATE_LIMITED,
            "Too many requests",
            retryable=True,
        )
        assert result["error"]["retryable"] is True

    def test_includes_details_when_provided(self):
        """Should include details dict when provided."""
        details = {"message_id": "abc123", "attempted_at": "2024-01-01"}
        result = structured_error(
            ErrorCode.MESSAGE_NOT_FOUND,
            "Not found",
            details=details,
        )
        assert result["error"]["details"] == details

    def test_empty_details_when_not_provided(self):
        """Should have empty details dict when not provided."""
        result = structured_error(ErrorCode.OPERATION_FAILED, "Failed")
        assert result["error"]["details"] == {}

    def test_is_json_serializable(self):
        """Error response should be JSON serializable."""
        result = structured_error(
            ErrorCode.INVALID_INPUT,
            "Invalid input",
            details={"value": "test"},
        )
        # Should not raise
        json_str = json.dumps(result)
        assert json.loads(json_str) == result


# -----------------------------------------------------------------------------
# operation_receipt tests
# -----------------------------------------------------------------------------


class TestOperationReceipt:
    """Tests for operation_receipt function."""

    def test_returns_success_true(self):
        """Receipt should have success: true."""
        result = operation_receipt(
            operation="archive",
            target={"id": "abc123"},
        )
        assert result["success"] is True

    def test_timestamp_is_iso_format_utc(self):
        """Timestamp should be ISO format in UTC."""
        result = operation_receipt(
            operation="trash",
            target={"id": "abc123"},
        )
        timestamp = result["timestamp"]
        # Should be parseable as ISO format
        parsed = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
        assert parsed.tzinfo is not None  # Has timezone info

    def test_single_target_becomes_list_of_one(self):
        """Single target dict should become a list of one."""
        target = {"id": "abc123", "subject": "Test"}
        result = operation_receipt(
            operation="archive",
            target=target,
        )
        assert result["targets"] == [target]
        assert result["count"] == 1

    def test_multiple_targets_stay_as_list(self):
        """List of targets should remain as list."""
        targets = [
            {"id": "abc123", "subject": "Test 1"},
            {"id": "def456", "subject": "Test 2"},
        ]
        result = operation_receipt(
            operation="archive",
            target=targets,
        )
        assert result["targets"] == targets
        assert result["count"] == 2

    def test_undo_info_populated_when_provided(self):
        """Should include undo command when provided."""
        result = operation_receipt(
            operation="archive",
            target={"id": "abc123"},
            undo_command="desk mail unarchive abc123",
            undo_expires="never",
        )
        assert result["undo"]["available"] is True
        assert result["undo"]["command"] == "desk mail unarchive abc123"
        assert result["undo"]["expires"] == "never"

    def test_undo_not_available_when_not_provided(self):
        """Undo should be unavailable when command not provided."""
        result = operation_receipt(
            operation="send",
            target={"id": "abc123"},
        )
        assert result["undo"]["available"] is False
        assert result["undo"]["command"] is None

    def test_changes_field_included_when_provided(self):
        """Changes field should be included when provided."""
        changes = {"labels_added": ["STARRED"], "labels_removed": []}
        result = operation_receipt(
            operation="star",
            target={"id": "abc123"},
            changes=changes,
        )
        assert result["changes"] == changes

    def test_changes_field_absent_when_not_provided(self):
        """Changes field should not be present when not provided."""
        result = operation_receipt(
            operation="archive",
            target={"id": "abc123"},
        )
        assert "changes" not in result

    def test_is_json_serializable(self):
        """Receipt should be JSON serializable."""
        result = operation_receipt(
            operation="label",
            target=[{"id": "abc"}, {"id": "def"}],
            undo_command="desk mail remove-label Test abc def",
            changes={"labels_added": ["Test"]},
        )
        json_str = json.dumps(result)
        assert json.loads(json_str) == result


# -----------------------------------------------------------------------------
# dry_run_preview tests
# -----------------------------------------------------------------------------


class TestDryRunPreview:
    """Tests for dry_run_preview function."""

    def test_returns_dry_run_true(self):
        """Preview should have dry_run: true."""
        result = dry_run_preview(
            operation="archive",
            targets=[{"id": "abc123"}],
        )
        assert result["dry_run"] is True

    def test_includes_all_required_fields(self):
        """Preview should include all required fields."""
        result = dry_run_preview(
            operation="trash",
            targets=[{"id": "abc123", "subject": "Test"}],
            reversible=True,
            undo_command="desk mail untrash abc123",
        )
        assert "dry_run" in result
        assert "would_execute" in result
        assert "count" in result
        assert "targets" in result
        assert "reversible" in result
        assert "undo_would_be" in result
        assert "warnings" in result

    def test_warnings_list_populated_when_provided(self):
        """Warnings should be included when provided."""
        warnings = ["This will affect 100 messages", "Cannot be undone"]
        result = dry_run_preview(
            operation="delete",
            targets=[{"id": "abc123"}],
            reversible=False,
            warnings=warnings,
        )
        assert result["warnings"] == warnings

    def test_warnings_empty_list_when_not_provided(self):
        """Warnings should be empty list when not provided."""
        result = dry_run_preview(
            operation="archive",
            targets=[{"id": "abc123"}],
        )
        assert result["warnings"] == []

    def test_count_matches_targets_length(self):
        """Count should match the number of targets."""
        targets = [{"id": "a"}, {"id": "b"}, {"id": "c"}]
        result = dry_run_preview(
            operation="archive",
            targets=targets,
        )
        assert result["count"] == 3

    def test_is_json_serializable(self):
        """Preview should be JSON serializable."""
        result = dry_run_preview(
            operation="trash",
            targets=[{"id": "abc", "subject": "Test"}],
            reversible=True,
            undo_command="desk mail untrash abc",
            warnings=["Warning 1"],
        )
        json_str = json.dumps(result)
        assert json.loads(json_str) == result


# -----------------------------------------------------------------------------
# get_undo_info tests
# -----------------------------------------------------------------------------


class TestGetUndoInfo:
    """Tests for get_undo_info function."""

    def test_returns_correct_template_for_archive(self):
        """Should return correct undo command for archive."""
        cmd, expires, reversible = get_undo_info("archive", ids="abc123")
        assert cmd == "desk mail unarchive abc123"
        assert reversible is True

    def test_returns_correct_template_for_trash(self):
        """Should return correct undo command for trash."""
        cmd, expires, reversible = get_undo_info("trash", ids="abc123")
        assert cmd == "desk mail untrash abc123"
        assert "30 days" in expires
        assert reversible is True

    def test_returns_correct_template_for_star(self):
        """Should return correct undo command for star."""
        cmd, expires, reversible = get_undo_info("star", ids="abc123")
        assert cmd == "desk mail unstar abc123"
        assert reversible is True

    def test_substitutes_multiple_ids_correctly(self):
        """Should handle multiple IDs."""
        cmd, _, _ = get_undo_info("archive", ids=["abc", "def", "ghi"])
        assert cmd == "desk mail unarchive abc def ghi"

    def test_handles_label_parameter(self):
        """Should substitute label parameter correctly."""
        cmd, _, _ = get_undo_info("label", ids="abc123", label="Important")
        assert cmd == "desk mail remove-label Important abc123"

    def test_returns_none_for_irreversible_operations(self):
        """Should return None command for irreversible operations."""
        cmd, expires, reversible = get_undo_info("send", ids="abc123")
        assert cmd is None
        assert reversible is False

    def test_returns_none_for_unknown_operations(self):
        """Should return None for unknown operations."""
        cmd, expires, reversible = get_undo_info("unknown_op", ids="abc123")
        assert cmd is None
        assert reversible is False

    def test_thread_operations(self):
        """Should handle thread-level operations."""
        cmd, _, reversible = get_undo_info("thread-archive", ids="thread123")
        assert "thread-label INBOX thread123" in cmd
        assert reversible is True

    def test_drive_operations(self):
        """Should handle Drive operations."""
        cmd, expires, reversible = get_undo_info("drive-trash", ids="file123")
        assert cmd == "desk drive untrash file123"
        assert "30 days" in expires
        assert reversible is True


# -----------------------------------------------------------------------------
# parse_api_error tests
# -----------------------------------------------------------------------------


class TestParseApiError:
    """Tests for parse_api_error function."""

    def test_extracts_message_from_httperror_format(self):
        """Should extract message from HttpError format."""
        error_str = '<HttpError 400 when requesting ... returned "Invalid id value". Details: "...">'
        result = parse_api_error(error_str)
        assert result == "Invalid id value"

    def test_extracts_from_json_message_format(self):
        """Should extract message from JSON format."""
        error_str = '{"message": "Resource not found", "code": 404}'
        result = parse_api_error(error_str)
        assert result == "Resource not found"

    def test_extracts_from_reason_format(self):
        """Should extract reason from JSON format."""
        error_str = '{"reason": "notFound", "domain": "global"}'
        result = parse_api_error(error_str)
        assert result == "notFound"

    def test_removes_api_error_prefix(self):
        """Should remove common API error prefixes."""
        error_str = "Gmail API error: Something went wrong"
        result = parse_api_error(error_str)
        assert result == "Something went wrong"

    def test_truncates_long_errors(self):
        """Should truncate very long error messages."""
        # Use a format that doesn't match any extraction pattern
        long_error = "Some random text " + "x" * 300
        result = parse_api_error(long_error)
        assert len(result) <= 200 or result.endswith("...")

    def test_handles_simple_error_string(self):
        """Should handle simple error strings."""
        error_str = "Connection failed"
        result = parse_api_error(error_str)
        assert result == "Connection failed"


# -----------------------------------------------------------------------------
# Format functions tests
# -----------------------------------------------------------------------------


class TestFormatFunctions:
    """Tests for human-readable format functions."""

    def test_format_error_includes_code_and_message(self):
        """Error format should include code and message."""
        error = structured_error(
            ErrorCode.MESSAGE_NOT_FOUND,
            "Message abc123 not found",
        )
        formatted = format_error_for_human(error)
        assert "MESSAGE_NOT_FOUND" in formatted
        assert "Message abc123 not found" in formatted

    def test_format_error_includes_suggestions(self):
        """Error format should include suggestions."""
        error = structured_error(
            ErrorCode.AUTH_REQUIRED,
            "Not authenticated",
        )
        formatted = format_error_for_human(error)
        assert "desk auth login" in formatted

    def test_format_receipt_includes_operation(self):
        """Receipt format should include operation name."""
        receipt = operation_receipt(
            operation="archive",
            target={"id": "abc123", "subject": "Test Subject"},
        )
        formatted = format_receipt_for_human(receipt)
        assert "archive" in formatted

    def test_format_receipt_shows_undo_command(self):
        """Receipt format should show undo command when available."""
        receipt = operation_receipt(
            operation="trash",
            target={"id": "abc123"},
            undo_command="desk mail untrash abc123",
        )
        formatted = format_receipt_for_human(receipt)
        assert "desk mail untrash abc123" in formatted

    def test_format_dry_run_shows_would_execute(self):
        """Dry run format should show what would execute."""
        preview = dry_run_preview(
            operation="trash",
            targets=[{"id": "abc123", "subject": "Test"}],
            reversible=True,
        )
        formatted = format_dry_run_for_human(preview)
        assert "DRY RUN" in formatted
        assert "trash" in formatted

    def test_format_dry_run_shows_warnings(self):
        """Dry run format should show warnings."""
        preview = dry_run_preview(
            operation="delete",
            targets=[{"id": "abc123"}],
            reversible=False,
            warnings=["Cannot be undone"],
        )
        formatted = format_dry_run_for_human(preview)
        assert "Cannot be undone" in formatted


# -----------------------------------------------------------------------------
# Error code coverage
# -----------------------------------------------------------------------------


class TestErrorCodes:
    """Tests for error code definitions."""

    def test_all_error_codes_are_strings(self):
        """All error codes should be string values."""
        for code in ErrorCode:
            assert isinstance(code.value, str)

    def test_common_errors_have_suggestions(self):
        """Common error codes should have default suggestions."""
        expected_to_have_suggestions = [
            ErrorCode.AUTH_REQUIRED,
            ErrorCode.AUTH_EXPIRED,
            ErrorCode.MESSAGE_NOT_FOUND,
            ErrorCode.LABEL_NOT_FOUND,
            ErrorCode.FILE_NOT_FOUND,
            ErrorCode.PERMISSION_DENIED,
            ErrorCode.RATE_LIMITED,
        ]
        for code in expected_to_have_suggestions:
            assert code in ERROR_SUGGESTIONS, f"{code} should have suggestions"
            assert len(ERROR_SUGGESTIONS[code]) > 0


class TestUndoCommands:
    """Tests for UNDO_COMMANDS registry."""

    def test_all_undo_entries_have_required_fields(self):
        """All undo entries should have template, expires, reversible."""
        for op, info in UNDO_COMMANDS.items():
            assert "template" in info, f"{op} missing template"
            assert "expires" in info, f"{op} missing expires"
            assert "reversible" in info, f"{op} missing reversible"

    def test_irreversible_operations_have_no_template(self):
        """Irreversible operations should have template=None."""
        irreversible = ["send", "reply", "forward", "cal-delete"]
        for op in irreversible:
            if op in UNDO_COMMANDS:
                info = UNDO_COMMANDS[op]
                assert info["template"] is None
                assert info["reversible"] is False
