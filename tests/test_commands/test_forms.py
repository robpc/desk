"""Tests for forms CLI commands."""

import json
import pytest
from click.testing import CliRunner
from unittest.mock import MagicMock, patch


@pytest.fixture
def runner():
    """Create a Click CLI test runner."""
    return CliRunner()


@pytest.fixture
def mock_get_credentials():
    """Mock the get_credentials function."""
    with patch("desk.commands.forms.get_credentials") as mock:
        mock.return_value = MagicMock()
        yield mock


@pytest.fixture
def mock_forms_client_class():
    """Mock the FormsClient class."""
    with patch("desk.commands.forms.FormsClient") as mock:
        yield mock


class TestFormsCreate:
    """Tests for desk forms create command."""

    def test_create_form_json_output(self, runner, mock_get_credentials, mock_forms_client_class):
        """Should output created form receipt as JSON."""
        from desk.commands.forms import forms

        mock_client = MagicMock()
        mock_client.create.return_value = {
            "formId": "form_id",
            "title": "Survey",
            "responderUri": "https://docs.google.com/forms/d/e/xxx/viewform",
            "editUri": "https://docs.google.com/forms/d/form_id/edit",
        }
        mock_forms_client_class.return_value = mock_client

        result = runner.invoke(forms, ["create", "Survey", "--json"])

        assert result.exit_code == 0
        output = json.loads(result.output)
        assert output["success"] is True
        assert output["operation"] == "create"

    def test_create_form_with_description(
        self, runner, mock_get_credentials, mock_forms_client_class
    ):
        """Should pass description to client."""
        from desk.commands.forms import forms

        mock_client = MagicMock()
        mock_client.create.return_value = {
            "formId": "form_id",
            "title": "Survey",
            "responderUri": "https://forms.google.com",
            "editUri": "https://docs.google.com/forms/d/form_id/edit",
        }
        mock_forms_client_class.return_value = mock_client

        result = runner.invoke(forms, ["create", "Survey", "-d", "A description", "--json"])

        assert result.exit_code == 0
        mock_client.create.assert_called_once_with("Survey", description="A description")


class TestFormsRead:
    """Tests for desk forms read command."""

    def test_read_with_json_output(self, runner, mock_get_credentials, mock_forms_client_class):
        """Should output form structure as JSON."""
        from desk.commands.forms import forms

        mock_client = MagicMock()
        mock_client.read.return_value = {
            "formId": "form_123",
            "title": "Test Survey",
            "description": "A survey",
            "responderUri": "https://forms.google.com",
            "items": [{"title": "Name?", "type": "text", "required": True}],
        }
        mock_forms_client_class.return_value = mock_client

        result = runner.invoke(forms, ["read", "form_123", "--json"])

        assert result.exit_code == 0
        output = json.loads(result.output)
        assert output["formId"] == "form_123"
        assert output["title"] == "Test Survey"
        assert len(output["items"]) == 1


class TestFormsResponses:
    """Tests for desk forms responses command."""

    def test_responses_json_output(self, runner, mock_get_credentials, mock_forms_client_class):
        """Should output responses as JSON."""
        from desk.commands.forms import forms

        mock_client = MagicMock()
        mock_client.responses.return_value = {
            "formId": "form_123",
            "responseCount": 2,
            "responses": [
                {"responseId": "r1", "answers": {}},
                {"responseId": "r2", "answers": {}},
            ],
        }
        mock_forms_client_class.return_value = mock_client

        result = runner.invoke(forms, ["responses", "form_123", "--json"])

        assert result.exit_code == 0
        output = json.loads(result.output)
        assert output["responseCount"] == 2


class TestFormsAddQuestion:
    """Tests for desk forms add-question command."""

    def test_add_question_json_output(self, runner, mock_get_credentials, mock_forms_client_class):
        """Should output receipt as JSON."""
        from desk.commands.forms import forms

        mock_client = MagicMock()
        mock_client.add_question.return_value = {"formId": "form_123", "status": "ok"}
        mock_forms_client_class.return_value = mock_client

        result = runner.invoke(forms, ["add-question", "form_123", "Name?", "--json"])

        assert result.exit_code == 0
        output = json.loads(result.output)
        assert output["success"] is True
        assert output["operation"] == "add-question"

    def test_add_choice_question(self, runner, mock_get_credentials, mock_forms_client_class):
        """Should pass choices to client."""
        from desk.commands.forms import forms

        mock_client = MagicMock()
        mock_client.add_question.return_value = {"formId": "form_123", "status": "ok"}
        mock_forms_client_class.return_value = mock_client

        result = runner.invoke(
            forms,
            [
                "add-question",
                "form_123",
                "Color?",
                "--type",
                "choice",
                "-c",
                "Red",
                "-c",
                "Blue",
                "--json",
            ],
        )

        assert result.exit_code == 0
        mock_client.add_question.assert_called_once_with(
            "form_123",
            "Color?",
            question_type="choice",
            required=False,
            choices=["Red", "Blue"],
            goto=None,
        )

    def test_add_question_with_goto(self, runner, mock_get_credentials, mock_forms_client_class):
        """Should parse --goto flags and pass goto map to client."""
        from desk.commands.forms import forms

        mock_client = MagicMock()
        mock_client.add_question.return_value = {"formId": "form_123", "status": "ok"}
        mock_forms_client_class.return_value = mock_client

        result = runner.invoke(
            forms,
            [
                "add-question",
                "form_123",
                "Tried voice?",
                "--type",
                "choice",
                "-c",
                "Yes",
                "-c",
                "No",
                "--goto",
                "Yes=voice_section",
                "--goto",
                "No=guides_section",
                "--json",
            ],
        )

        assert result.exit_code == 0
        mock_client.add_question.assert_called_once_with(
            "form_123",
            "Tried voice?",
            question_type="choice",
            required=False,
            choices=["Yes", "No"],
            goto={"Yes": "voice_section", "No": "guides_section"},
        )

    def test_goto_with_invalid_type_errors(self, runner, mock_get_credentials, mock_forms_client_class):
        """Should error when --goto used with non-choice/dropdown type."""
        from desk.commands.forms import forms

        result = runner.invoke(
            forms,
            [
                "add-question",
                "form_123",
                "Name?",
                "--type",
                "text",
                "--goto",
                "x=y",
                "--json",
            ],
        )

        assert result.exit_code != 0
        output = json.loads(result.output)
        assert output["error"]["code"] == "INVALID_INPUT"

    def test_goto_with_bad_format_errors(self, runner, mock_get_credentials, mock_forms_client_class):
        """Should error when --goto value missing = separator."""
        from desk.commands.forms import forms

        result = runner.invoke(
            forms,
            [
                "add-question",
                "form_123",
                "Pick",
                "--type",
                "choice",
                "-c",
                "A",
                "--goto",
                "bad_format",
                "--json",
            ],
        )

        assert result.exit_code != 0
        output = json.loads(result.output)
        assert output["error"]["code"] == "INVALID_INPUT"

    def test_goto_with_empty_value_errors(self, runner, mock_get_credentials, mock_forms_client_class):
        """Should error when --goto has empty value."""
        from desk.commands.forms import forms

        result = runner.invoke(
            forms,
            ["add-question", "form_123", "Pick", "--type", "choice", "-c", "A", "--goto", "A=", "--json"],
        )

        assert result.exit_code != 0
        output = json.loads(result.output)
        assert output["error"]["code"] == "INVALID_INPUT"

    def test_goto_with_empty_key_errors(self, runner, mock_get_credentials, mock_forms_client_class):
        """Should error when --goto has empty key."""
        from desk.commands.forms import forms

        result = runner.invoke(
            forms,
            ["add-question", "form_123", "Pick", "--type", "choice", "-c", "A", "--goto", "=sec", "--json"],
        )

        assert result.exit_code != 0
        output = json.loads(result.output)
        assert output["error"]["code"] == "INVALID_INPUT"

    def test_goto_strips_whitespace(self, runner, mock_get_credentials, mock_forms_client_class):
        """Should strip whitespace from goto key and value."""
        from desk.commands.forms import forms

        mock_client = MagicMock()
        mock_client.add_question.return_value = {"formId": "form_123", "status": "ok"}
        mock_forms_client_class.return_value = mock_client

        result = runner.invoke(
            forms,
            ["add-question", "form_123", "Pick", "--type", "choice", "-c", "Yes", "--goto", " Yes = sec1 ", "--json"],
        )

        assert result.exit_code == 0
        mock_client.add_question.assert_called_once_with(
            "form_123",
            "Pick",
            question_type="choice",
            required=False,
            choices=["Yes"],
            goto={"Yes": "sec1"},
        )

    def test_goto_with_checkbox_type_errors(self, runner, mock_get_credentials, mock_forms_client_class):
        """Should error when --goto used with checkbox type."""
        from desk.commands.forms import forms

        result = runner.invoke(
            forms,
            ["add-question", "form_123", "Pick", "--type", "checkbox", "-c", "A", "--goto", "A=sec", "--json"],
        )

        assert result.exit_code != 0
        output = json.loads(result.output)
        assert output["error"]["code"] == "INVALID_INPUT"

    def test_validation_error_no_choices(self, runner, mock_get_credentials, mock_forms_client_class):
        """Should error when choice type has no options."""
        from desk.commands.forms import forms

        mock_client = MagicMock()
        mock_client.add_question.side_effect = ValueError(
            "Choice questions require at least one option"
        )
        mock_forms_client_class.return_value = mock_client

        result = runner.invoke(
            forms,
            ["add-question", "form_123", "Oops", "--type", "choice", "--json"],
        )

        assert result.exit_code != 0
        output = json.loads(result.output)
        assert output["error"]["code"] == "INVALID_INPUT"
        assert "require at least one option" in output["error"]["message"]


class TestFormsAddSection:
    """Tests for desk forms add-section command."""

    def test_add_section_with_id(self, runner, mock_get_credentials, mock_forms_client_class):
        """Should pass section_id to client."""
        from desk.commands.forms import forms

        mock_client = MagicMock()
        mock_client.add_section.return_value = {"formId": "form_123", "status": "ok"}
        mock_forms_client_class.return_value = mock_client

        result = runner.invoke(
            forms,
            ["add-section", "form_123", "Voice Details", "--id", "voice_section", "--json"],
        )

        assert result.exit_code == 0
        mock_client.add_section.assert_called_once_with(
            "form_123",
            "Voice Details",
            description="",
            section_id="voice_section",
        )

    def test_add_section_without_id(self, runner, mock_get_credentials, mock_forms_client_class):
        """Should pass section_id=None when --id not provided."""
        from desk.commands.forms import forms

        mock_client = MagicMock()
        mock_client.add_section.return_value = {"formId": "form_123", "status": "ok"}
        mock_forms_client_class.return_value = mock_client

        result = runner.invoke(
            forms,
            ["add-section", "form_123", "Part 2", "--json"],
        )

        assert result.exit_code == 0
        mock_client.add_section.assert_called_once_with(
            "form_123",
            "Part 2",
            description="",
            section_id=None,
        )
