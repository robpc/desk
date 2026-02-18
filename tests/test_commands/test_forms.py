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

    def test_responses_passes_page_token(self, runner, mock_get_credentials, mock_forms_client_class):
        """Should pass page_token to client."""
        from desk.commands.forms import forms

        mock_client = MagicMock()
        mock_client.responses.return_value = {
            "formId": "form_123",
            "responseCount": 1,
            "responses": [{"responseId": "r3", "answers": {}}],
        }
        mock_forms_client_class.return_value = mock_client

        result = runner.invoke(forms, ["responses", "form_123", "--page-token", "tok123", "--json"])

        assert result.exit_code == 0
        mock_client.responses.assert_called_once_with("form_123", limit=100, page_token="tok123")

    def test_responses_shows_next_page_hint(self, runner, mock_get_credentials, mock_forms_client_class):
        """Should show pagination hint in human output when nextPageToken present."""
        from desk.commands.forms import forms

        mock_client = MagicMock()
        mock_client.responses.return_value = {
            "formId": "form_123",
            "responseCount": 1,
            "responses": [],
            "nextPageToken": "next_abc",
        }
        mock_forms_client_class.return_value = mock_client

        result = runner.invoke(forms, ["responses", "form_123"])

        assert result.exit_code == 0
        assert "--page-token next_abc" in result.output

    def test_responses_json_includes_next_page_token(self, runner, mock_get_credentials, mock_forms_client_class):
        """Should include nextPageToken in JSON output."""
        from desk.commands.forms import forms

        mock_client = MagicMock()
        mock_client.responses.return_value = {
            "formId": "form_123",
            "responseCount": 0,
            "responses": [],
            "nextPageToken": "next_abc",
        }
        mock_forms_client_class.return_value = mock_client

        result = runner.invoke(forms, ["responses", "form_123", "--json"])

        assert result.exit_code == 0
        output = json.loads(result.output)
        assert output["nextPageToken"] == "next_abc"


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


class TestFormsUpdate:
    """Tests for desk forms update command."""

    def test_update_title(self, runner, mock_get_credentials, mock_forms_client_class):
        """Should call update_form with title."""
        from desk.commands.forms import forms

        mock_client = MagicMock()
        mock_client.update_form.return_value = {"formId": "form_123", "status": "ok"}
        mock_forms_client_class.return_value = mock_client

        result = runner.invoke(forms, ["update", "form_123", "--title", "New Title", "--json"])

        assert result.exit_code == 0
        output = json.loads(result.output)
        assert output["success"] is True
        assert output["operation"] == "update"
        assert output["changes"]["title"] == "New Title"
        mock_client.update_form.assert_called_once_with("form_123", title="New Title", description=None)

    def test_update_description(self, runner, mock_get_credentials, mock_forms_client_class):
        """Should call update_form with description."""
        from desk.commands.forms import forms

        mock_client = MagicMock()
        mock_client.update_form.return_value = {"formId": "form_123", "status": "ok"}
        mock_forms_client_class.return_value = mock_client

        result = runner.invoke(forms, ["update", "form_123", "-d", "New desc", "--json"])

        assert result.exit_code == 0
        mock_client.update_form.assert_called_once_with("form_123", title=None, description="New desc")

    def test_update_no_flags_errors(self, runner, mock_get_credentials, mock_forms_client_class):
        """Should error when neither --title nor --description provided."""
        from desk.commands.forms import forms

        result = runner.invoke(forms, ["update", "form_123", "--json"])

        assert result.exit_code != 0
        output = json.loads(result.output)
        assert output["error"]["code"] == "INVALID_INPUT"


class TestFormsUpdateQuestion:
    """Tests for desk forms update-question command."""

    def test_update_question_title(self, runner, mock_get_credentials, mock_forms_client_class):
        """Should call update_item with title."""
        from desk.commands.forms import forms

        mock_client = MagicMock()
        mock_client.update_item.return_value = {"formId": "form_123", "status": "ok"}
        mock_forms_client_class.return_value = mock_client

        result = runner.invoke(
            forms, ["update-question", "form_123", "q1", "--title", "Fixed?", "--json"]
        )

        assert result.exit_code == 0
        output = json.loads(result.output)
        assert output["success"] is True
        assert output["operation"] == "update-question"
        mock_client.update_item.assert_called_once_with(
            "form_123", "q1", title="Fixed?", required=None, choices=None, goto=None,
        )

    def test_update_question_required(self, runner, mock_get_credentials, mock_forms_client_class):
        """Should pass required=True when --required used."""
        from desk.commands.forms import forms

        mock_client = MagicMock()
        mock_client.update_item.return_value = {"formId": "form_123", "status": "ok"}
        mock_forms_client_class.return_value = mock_client

        result = runner.invoke(
            forms, ["update-question", "form_123", "q1", "--required", "--json"]
        )

        assert result.exit_code == 0
        mock_client.update_item.assert_called_once_with(
            "form_123", "q1", title=None, required=True, choices=None, goto=None,
        )

    def test_update_question_no_required(self, runner, mock_get_credentials, mock_forms_client_class):
        """Should pass required=False when --no-required used."""
        from desk.commands.forms import forms

        mock_client = MagicMock()
        mock_client.update_item.return_value = {"formId": "form_123", "status": "ok"}
        mock_forms_client_class.return_value = mock_client

        result = runner.invoke(
            forms, ["update-question", "form_123", "q1", "--no-required", "--json"]
        )

        assert result.exit_code == 0
        mock_client.update_item.assert_called_once_with(
            "form_123", "q1", title=None, required=False, choices=None, goto=None,
        )

    def test_update_question_choices(self, runner, mock_get_credentials, mock_forms_client_class):
        """Should pass choices to update_item."""
        from desk.commands.forms import forms

        mock_client = MagicMock()
        mock_client.update_item.return_value = {"formId": "form_123", "status": "ok"}
        mock_forms_client_class.return_value = mock_client

        result = runner.invoke(
            forms, ["update-question", "form_123", "q1", "-c", "X", "-c", "Y", "--json"]
        )

        assert result.exit_code == 0
        mock_client.update_item.assert_called_once_with(
            "form_123", "q1", title=None, required=None, choices=["X", "Y"], goto=None,
        )

    def test_update_question_with_goto(self, runner, mock_get_credentials, mock_forms_client_class):
        """Should parse --goto and pass to update_item."""
        from desk.commands.forms import forms

        mock_client = MagicMock()
        mock_client.update_item.return_value = {"formId": "form_123", "status": "ok"}
        mock_forms_client_class.return_value = mock_client

        result = runner.invoke(
            forms,
            [
                "update-question", "form_123", "q1",
                "-c", "Yes", "-c", "No",
                "--goto", "Yes=sec1", "--goto", "No=SUBMIT_FORM",
                "--json",
            ],
        )

        assert result.exit_code == 0
        mock_client.update_item.assert_called_once_with(
            "form_123", "q1",
            title=None, required=None,
            choices=["Yes", "No"],
            goto={"Yes": "sec1", "No": "SUBMIT_FORM"},
        )

    def test_update_question_valueerror(self, runner, mock_get_credentials, mock_forms_client_class):
        """Should handle ValueError from service."""
        from desk.commands.forms import forms

        mock_client = MagicMock()
        mock_client.update_item.side_effect = ValueError("Item 'q1' not found in form 'form_123'")
        mock_forms_client_class.return_value = mock_client

        result = runner.invoke(
            forms, ["update-question", "form_123", "q1", "--title", "X", "--json"]
        )

        assert result.exit_code != 0
        output = json.loads(result.output)
        assert output["error"]["code"] == "INVALID_INPUT"


class TestFormsUpdateSection:
    """Tests for desk forms update-section command."""

    def test_update_section_title(self, runner, mock_get_credentials, mock_forms_client_class):
        """Should call update_item with title."""
        from desk.commands.forms import forms

        mock_client = MagicMock()
        mock_client.update_item.return_value = {"formId": "form_123", "status": "ok"}
        mock_forms_client_class.return_value = mock_client

        result = runner.invoke(
            forms, ["update-section", "form_123", "sec1", "--title", "New Section", "--json"]
        )

        assert result.exit_code == 0
        output = json.loads(result.output)
        assert output["success"] is True
        assert output["operation"] == "update-section"
        mock_client.update_item.assert_called_once_with(
            "form_123", "sec1", title="New Section", description=None,
        )

    def test_update_section_description(self, runner, mock_get_credentials, mock_forms_client_class):
        """Should call update_item with description."""
        from desk.commands.forms import forms

        mock_client = MagicMock()
        mock_client.update_item.return_value = {"formId": "form_123", "status": "ok"}
        mock_forms_client_class.return_value = mock_client

        result = runner.invoke(
            forms, ["update-section", "form_123", "sec1", "-d", "New desc", "--json"]
        )

        assert result.exit_code == 0
        mock_client.update_item.assert_called_once_with(
            "form_123", "sec1", title=None, description="New desc",
        )

    def test_update_section_no_flags_errors(self, runner, mock_get_credentials, mock_forms_client_class):
        """Should error when neither --title nor --description provided."""
        from desk.commands.forms import forms

        result = runner.invoke(forms, ["update-section", "form_123", "sec1", "--json"])

        assert result.exit_code != 0
        output = json.loads(result.output)
        assert output["error"]["code"] == "INVALID_INPUT"


class TestFormsDeleteItem:
    """Tests for desk forms delete-item command."""

    def test_delete_item_with_yes(self, runner, mock_get_credentials, mock_forms_client_class):
        """Should call delete_item when --yes provided."""
        from desk.commands.forms import forms

        mock_client = MagicMock()
        mock_client.delete_item.return_value = {"formId": "form_123", "status": "ok"}
        mock_forms_client_class.return_value = mock_client

        result = runner.invoke(
            forms, ["delete-item", "form_123", "q1", "--yes", "--json"]
        )

        assert result.exit_code == 0
        output = json.loads(result.output)
        assert output["success"] is True
        assert output["operation"] == "delete-item"
        mock_client.delete_item.assert_called_once_with("form_123", "q1")

    def test_delete_item_without_yes_errors(self, runner, mock_get_credentials, mock_forms_client_class):
        """Should error when --yes not provided."""
        from desk.commands.forms import forms

        result = runner.invoke(forms, ["delete-item", "form_123", "q1", "--json"])

        assert result.exit_code != 0
        output = json.loads(result.output)
        assert output["error"]["code"] == "INVALID_INPUT"
        assert "Confirmation required" in output["error"]["message"]

    def test_delete_item_not_found(self, runner, mock_get_credentials, mock_forms_client_class):
        """Should handle ValueError for missing item."""
        from desk.commands.forms import forms

        mock_client = MagicMock()
        mock_client.delete_item.side_effect = ValueError("Item 'q99' not found in form 'form_123'")
        mock_forms_client_class.return_value = mock_client

        result = runner.invoke(
            forms, ["delete-item", "form_123", "q99", "--yes", "--json"]
        )

        assert result.exit_code != 0
        output = json.loads(result.output)
        assert output["error"]["code"] == "INVALID_INPUT"


class TestFormsPublish:
    """Tests for desk forms publish command."""

    def test_publish_default(self, runner, mock_get_credentials, mock_forms_client_class):
        """Should call publish with accepting_responses=True by default."""
        from desk.commands.forms import forms

        mock_client = MagicMock()
        mock_client.publish.return_value = {"formId": "form_123", "status": "ok"}
        mock_forms_client_class.return_value = mock_client

        result = runner.invoke(forms, ["publish", "form_123", "--json"])

        assert result.exit_code == 0
        output = json.loads(result.output)
        assert output["success"] is True
        assert output["operation"] == "publish"
        mock_client.publish.assert_called_once_with("form_123", accepting_responses=True)

    def test_publish_no_accepting(self, runner, mock_get_credentials, mock_forms_client_class):
        """Should pass accepting_responses=False when --no-accepting used."""
        from desk.commands.forms import forms

        mock_client = MagicMock()
        mock_client.publish.return_value = {"formId": "form_123", "status": "ok"}
        mock_forms_client_class.return_value = mock_client

        result = runner.invoke(forms, ["publish", "form_123", "--no-accepting", "--json"])

        assert result.exit_code == 0
        mock_client.publish.assert_called_once_with("form_123", accepting_responses=False)


class TestFormsUnpublish:
    """Tests for desk forms unpublish command."""

    def test_unpublish(self, runner, mock_get_credentials, mock_forms_client_class):
        """Should call unpublish on client."""
        from desk.commands.forms import forms

        mock_client = MagicMock()
        mock_client.unpublish.return_value = {"formId": "form_123", "status": "ok"}
        mock_forms_client_class.return_value = mock_client

        result = runner.invoke(forms, ["unpublish", "form_123", "--json"])

        assert result.exit_code == 0
        output = json.loads(result.output)
        assert output["success"] is True
        assert output["operation"] == "unpublish"
        mock_client.unpublish.assert_called_once_with("form_123")
