"""Tests for Forms service client."""

import pytest
from unittest.mock import MagicMock, patch

from googleapiclient.errors import HttpError


class TestFormsClientInit:
    """Tests for FormsClient initialization."""

    def test_creates_forms_service_on_init(self, mock_credentials):
        """Should create Forms service on init."""
        with patch("desk.services.forms.build") as mock_build:
            mock_build.return_value = MagicMock()
            from desk.services.forms import FormsClient

            client = FormsClient(mock_credentials)

            assert mock_build.call_count == 1
            assert mock_build.call_args_list[0][0] == ("forms", "v1")


class TestFormsCreate:
    """Tests for FormsClient.create method."""

    def test_create_returns_form(self, mock_credentials):
        """Should return created form."""
        with patch("desk.services.forms.build") as mock_build:
            mock_service = MagicMock()
            mock_build.return_value = mock_service

            forms_mock = mock_service.forms.return_value
            forms_mock.create.return_value.execute.return_value = {
                "formId": "form_123",
                "info": {"title": "Test Survey"},
                "responderUri": "https://docs.google.com/forms/d/e/xxx/viewform",
            }

            from desk.services.forms import FormsClient

            client = FormsClient(mock_credentials)
            result = client.create("Test Survey")

            assert result["formId"] == "form_123"
            assert result["title"] == "Test Survey"
            assert result["responderUri"]
            assert result["editUri"]
            forms_mock.create.assert_called_once()

    def test_create_with_description_uses_batch_update(self, mock_credentials):
        """Should set description via batchUpdate (create ignores it)."""
        with patch("desk.services.forms.build") as mock_build:
            mock_service = MagicMock()
            mock_build.return_value = mock_service

            forms_mock = mock_service.forms.return_value
            forms_mock.create.return_value.execute.return_value = {
                "formId": "form_123",
                "info": {"title": "Survey"},
                "responderUri": "https://forms.google.com",
            }
            forms_mock.batchUpdate.return_value.execute.return_value = {}

            from desk.services.forms import FormsClient

            client = FormsClient(mock_credentials)
            result = client.create("Survey", description="A description")

            # Create should NOT include description
            create_body = forms_mock.create.call_args[1]["body"]
            assert "description" not in create_body.get("info", {})

            # Description set via batchUpdate
            forms_mock.batchUpdate.assert_called_once()
            batch_body = forms_mock.batchUpdate.call_args[1]["body"]
            update_req = batch_body["requests"][0]["updateFormInfo"]
            assert update_req["info"]["description"] == "A description"
            assert update_req["updateMask"] == "description"

            assert result["description"] == "A description"

    def test_create_without_description_skips_batch_update(self, mock_credentials):
        """Should not call batchUpdate when no description provided."""
        with patch("desk.services.forms.build") as mock_build:
            mock_service = MagicMock()
            mock_build.return_value = mock_service

            forms_mock = mock_service.forms.return_value
            forms_mock.create.return_value.execute.return_value = {
                "formId": "form_123",
                "info": {"title": "Survey"},
                "responderUri": "https://forms.google.com",
            }

            from desk.services.forms import FormsClient

            client = FormsClient(mock_credentials)
            result = client.create("Survey")

            forms_mock.create.assert_called_once()
            forms_mock.batchUpdate.assert_not_called()
            assert result["description"] == ""

    def test_create_not_found_raises_error(self, mock_credentials):
        """Should raise error on API failure."""
        with patch("desk.services.forms.build") as mock_build:
            mock_service = MagicMock()
            mock_build.return_value = mock_service

            forms_mock = mock_service.forms.return_value
            http_error = HttpError(
                resp=MagicMock(status=403),
                content=b'{"error": {"message": "Permission denied"}}',
            )
            forms_mock.create.return_value.execute.side_effect = http_error

            from desk.services.forms import FormsClient

            client = FormsClient(mock_credentials)
            with pytest.raises(RuntimeError, match="Forms API error"):
                client.create("Test")


class TestFormsRead:
    """Tests for FormsClient.read method."""

    def test_read_returns_form_structure(self, mock_credentials):
        """Should return form with simplified items."""
        with patch("desk.services.forms.build") as mock_build:
            mock_service = MagicMock()
            mock_build.return_value = mock_service

            forms_mock = mock_service.forms.return_value
            forms_mock.get.return_value.execute.return_value = {
                "formId": "form_123",
                "info": {"title": "Survey", "description": "Desc"},
                "responderUri": "https://forms.google.com",
                "items": [
                    {
                        "title": "Name?",
                        "questionItem": {
                            "question": {
                                "required": True,
                                "textQuestion": {"paragraph": False},
                            }
                        },
                    },
                    {
                        "title": "Section 2",
                        "pageBreakItem": {},
                    },
                ],
            }

            from desk.services.forms import FormsClient

            client = FormsClient(mock_credentials)
            result = client.read("form_123")

            assert result["formId"] == "form_123"
            assert result["title"] == "Survey"
            assert len(result["items"]) == 2
            assert result["items"][0]["type"] == "text"
            assert result["items"][0]["required"] is True
            assert result["items"][1]["type"] == "section"

    def test_read_includes_publish_state(self, mock_credentials):
        """Should include isPublished and isAcceptingResponses when present."""
        with patch("desk.services.forms.build") as mock_build:
            mock_service = MagicMock()
            mock_build.return_value = mock_service

            forms_mock = mock_service.forms.return_value
            forms_mock.get.return_value.execute.return_value = {
                "formId": "form_123",
                "info": {"title": "Survey"},
                "responderUri": "https://forms.google.com",
                "items": [],
                "publishSettings": {
                    "publishState": {
                        "isPublished": True,
                        "isAcceptingResponses": False,
                    }
                },
            }

            from desk.services.forms import FormsClient

            client = FormsClient(mock_credentials)
            result = client.read("form_123")

            assert result["isPublished"] is True
            assert result["isAcceptingResponses"] is False

    def test_read_omits_publish_state_when_absent(self, mock_credentials):
        """Should not include publish fields when API doesn't return them."""
        with patch("desk.services.forms.build") as mock_build:
            mock_service = MagicMock()
            mock_build.return_value = mock_service

            forms_mock = mock_service.forms.return_value
            forms_mock.get.return_value.execute.return_value = {
                "formId": "form_123",
                "info": {"title": "Survey"},
                "responderUri": "https://forms.google.com",
                "items": [],
            }

            from desk.services.forms import FormsClient

            client = FormsClient(mock_credentials)
            result = client.read("form_123")

            assert "isPublished" not in result
            assert "isAcceptingResponses" not in result


class TestFormsResponses:
    """Tests for FormsClient.responses method."""

    def test_responses_returns_list(self, mock_credentials):
        """Should return responses with count."""
        with patch("desk.services.forms.build") as mock_build:
            mock_service = MagicMock()
            mock_build.return_value = mock_service

            forms_mock = mock_service.forms.return_value
            responses_mock = forms_mock.responses.return_value
            responses_mock.list.return_value.execute.return_value = {
                "responses": [
                    {"responseId": "r1", "answers": {}},
                    {"responseId": "r2", "answers": {}},
                ],
            }

            from desk.services.forms import FormsClient

            client = FormsClient(mock_credentials)
            result = client.responses("form_123")

            assert result["formId"] == "form_123"
            assert result["responseCount"] == 2

    def test_responses_with_page_token(self, mock_credentials):
        """Should pass page_token to API."""
        with patch("desk.services.forms.build") as mock_build:
            mock_service = MagicMock()
            mock_build.return_value = mock_service

            forms_mock = mock_service.forms.return_value
            responses_mock = forms_mock.responses.return_value
            responses_mock.list.return_value.execute.return_value = {
                "responses": [{"responseId": "r3", "answers": {}}],
            }

            from desk.services.forms import FormsClient

            client = FormsClient(mock_credentials)
            client.responses("form_123", page_token="token_abc")

            call_kwargs = responses_mock.list.call_args[1]
            assert call_kwargs["pageToken"] == "token_abc"

    def test_responses_returns_next_page_token(self, mock_credentials):
        """Should include nextPageToken when present in API response."""
        with patch("desk.services.forms.build") as mock_build:
            mock_service = MagicMock()
            mock_build.return_value = mock_service

            forms_mock = mock_service.forms.return_value
            responses_mock = forms_mock.responses.return_value
            responses_mock.list.return_value.execute.return_value = {
                "responses": [{"responseId": "r1", "answers": {}}],
                "nextPageToken": "next_token_xyz",
            }

            from desk.services.forms import FormsClient

            client = FormsClient(mock_credentials)
            result = client.responses("form_123")

            assert result["nextPageToken"] == "next_token_xyz"

    def test_responses_omits_next_page_token_when_absent(self, mock_credentials):
        """Should not include nextPageToken when not in API response."""
        with patch("desk.services.forms.build") as mock_build:
            mock_service = MagicMock()
            mock_build.return_value = mock_service

            forms_mock = mock_service.forms.return_value
            responses_mock = forms_mock.responses.return_value
            responses_mock.list.return_value.execute.return_value = {
                "responses": [],
            }

            from desk.services.forms import FormsClient

            client = FormsClient(mock_credentials)
            result = client.responses("form_123")

            assert "nextPageToken" not in result


class TestFormsAddQuestion:
    """Tests for FormsClient.add_question method."""

    def test_add_text_question(self, mock_credentials):
        """Should add a text question via batchUpdate."""
        with patch("desk.services.forms.build") as mock_build:
            mock_service = MagicMock()
            mock_build.return_value = mock_service

            forms_mock = mock_service.forms.return_value
            forms_mock.batchUpdate.return_value.execute.return_value = {}

            from desk.services.forms import FormsClient

            client = FormsClient(mock_credentials)
            result = client.add_question("form_123", "What's your name?")

            assert result["status"] == "ok"
            forms_mock.batchUpdate.assert_called_once()

    def test_add_choice_question(self, mock_credentials):
        """Should add a choice question with options."""
        with patch("desk.services.forms.build") as mock_build:
            mock_service = MagicMock()
            mock_build.return_value = mock_service

            forms_mock = mock_service.forms.return_value
            forms_mock.batchUpdate.return_value.execute.return_value = {}

            from desk.services.forms import FormsClient

            client = FormsClient(mock_credentials)
            result = client.add_question(
                "form_123",
                "Color?",
                question_type="choice",
                choices=["Red", "Blue"],
            )

            assert result["status"] == "ok"
            call_body = forms_mock.batchUpdate.call_args[1]["body"]
            request = call_body["requests"][0]["createItem"]
            question = request["item"]["questionItem"]["question"]
            assert question["choiceQuestion"]["type"] == "RADIO"
            assert len(question["choiceQuestion"]["options"]) == 2

    def test_add_choice_question_with_goto_section(self, mock_credentials):
        """Should set goToSectionId on choice options."""
        with patch("desk.services.forms.build") as mock_build:
            mock_service = MagicMock()
            mock_build.return_value = mock_service

            forms_mock = mock_service.forms.return_value
            forms_mock.batchUpdate.return_value.execute.return_value = {}

            from desk.services.forms import FormsClient

            client = FormsClient(mock_credentials)
            result = client.add_question(
                "form_123",
                "Tried voice?",
                question_type="choice",
                choices=["Yes", "No"],
                goto={"Yes": "voice_section", "No": "guides_section"},
            )

            assert result["status"] == "ok"
            call_body = forms_mock.batchUpdate.call_args[1]["body"]
            options = call_body["requests"][0]["createItem"]["item"]["questionItem"]["question"]["choiceQuestion"]["options"]
            assert options[0] == {"value": "Yes", "goToSectionId": "voice_section"}
            assert options[1] == {"value": "No", "goToSectionId": "guides_section"}

    def test_add_choice_question_with_goto_action(self, mock_credentials):
        """Should set goToAction for special action values."""
        with patch("desk.services.forms.build") as mock_build:
            mock_service = MagicMock()
            mock_build.return_value = mock_service

            forms_mock = mock_service.forms.return_value
            forms_mock.batchUpdate.return_value.execute.return_value = {}

            from desk.services.forms import FormsClient

            client = FormsClient(mock_credentials)
            result = client.add_question(
                "form_123",
                "Done?",
                question_type="choice",
                choices=["Yes", "No"],
                goto={"Yes": "SUBMIT_FORM", "No": "more_section"},
            )

            assert result["status"] == "ok"
            call_body = forms_mock.batchUpdate.call_args[1]["body"]
            options = call_body["requests"][0]["createItem"]["item"]["questionItem"]["question"]["choiceQuestion"]["options"]
            assert options[0] == {"value": "Yes", "goToAction": "SUBMIT_FORM"}
            assert options[1] == {"value": "No", "goToSectionId": "more_section"}

    def test_add_dropdown_with_goto(self, mock_credentials):
        """Should support goto on dropdown type."""
        with patch("desk.services.forms.build") as mock_build:
            mock_service = MagicMock()
            mock_build.return_value = mock_service

            forms_mock = mock_service.forms.return_value
            forms_mock.batchUpdate.return_value.execute.return_value = {}

            from desk.services.forms import FormsClient

            client = FormsClient(mock_credentials)
            result = client.add_question(
                "form_123",
                "Pick one",
                question_type="dropdown",
                choices=["A", "B"],
                goto={"A": "section_a"},
            )

            assert result["status"] == "ok"
            call_body = forms_mock.batchUpdate.call_args[1]["body"]
            options = call_body["requests"][0]["createItem"]["item"]["questionItem"]["question"]["choiceQuestion"]["options"]
            assert options[0] == {"value": "A", "goToSectionId": "section_a"}
            assert options[1] == {"value": "B"}

    def test_choice_without_options_raises_valueerror(self, mock_credentials):
        """Should raise ValueError when choice type has no options."""
        with patch("desk.services.forms.build") as mock_build:
            mock_build.return_value = MagicMock()

            from desk.services.forms import FormsClient

            client = FormsClient(mock_credentials)
            with pytest.raises(ValueError, match="require at least one option"):
                client.add_question("form_123", "Oops", question_type="choice")

    def test_checkbox_without_options_raises_valueerror(self, mock_credentials):
        """Should raise ValueError when checkbox type has no options."""
        with patch("desk.services.forms.build") as mock_build:
            mock_build.return_value = MagicMock()

            from desk.services.forms import FormsClient

            client = FormsClient(mock_credentials)
            with pytest.raises(ValueError, match="require at least one option"):
                client.add_question("form_123", "Oops", question_type="checkbox")

    def test_dropdown_without_options_raises_valueerror(self, mock_credentials):
        """Should raise ValueError when dropdown type has no options."""
        with patch("desk.services.forms.build") as mock_build:
            mock_build.return_value = MagicMock()

            from desk.services.forms import FormsClient

            client = FormsClient(mock_credentials)
            with pytest.raises(ValueError, match="require at least one option"):
                client.add_question("form_123", "Oops", question_type="dropdown")

    def test_goto_on_checkbox_raises_valueerror(self, mock_credentials):
        """Should raise ValueError when goto used with checkbox type."""
        with patch("desk.services.forms.build") as mock_build:
            mock_build.return_value = MagicMock()

            from desk.services.forms import FormsClient

            client = FormsClient(mock_credentials)
            with pytest.raises(ValueError, match="not supported for checkbox"):
                client.add_question(
                    "form_123",
                    "Pick",
                    question_type="checkbox",
                    choices=["A", "B"],
                    goto={"A": "section_a"},
                )

    def test_add_question_default_index_fetches_form(self, mock_credentials):
        """Should fetch form and set location.index to item count when index is None."""
        with patch("desk.services.forms.build") as mock_build:
            mock_service = MagicMock()
            mock_build.return_value = mock_service

            forms_mock = mock_service.forms.return_value
            forms_mock.get.return_value.execute.return_value = {
                "items": [
                    {"title": "Q1", "questionItem": {"question": {}}},
                    {"title": "Q2", "questionItem": {"question": {}}},
                    {"title": "Q3", "questionItem": {"question": {}}},
                ],
            }
            forms_mock.batchUpdate.return_value.execute.return_value = {}

            from desk.services.forms import FormsClient

            client = FormsClient(mock_credentials)
            result = client.add_question("form_123", "New question")

            assert result["status"] == "ok"
            forms_mock.get.assert_called_once_with(formId="form_123")
            call_body = forms_mock.batchUpdate.call_args[1]["body"]
            location = call_body["requests"][0]["createItem"]["location"]
            assert location["index"] == 3

    def test_add_question_explicit_index_skips_get(self, mock_credentials):
        """Should use provided index and not call forms().get() when index is explicit."""
        with patch("desk.services.forms.build") as mock_build:
            mock_service = MagicMock()
            mock_build.return_value = mock_service

            forms_mock = mock_service.forms.return_value
            forms_mock.batchUpdate.return_value.execute.return_value = {}

            from desk.services.forms import FormsClient

            client = FormsClient(mock_credentials)
            result = client.add_question("form_123", "Inserted question", index=5)

            assert result["status"] == "ok"
            forms_mock.get.assert_not_called()
            call_body = forms_mock.batchUpdate.call_args[1]["body"]
            location = call_body["requests"][0]["createItem"]["location"]
            assert location["index"] == 5


class TestFormsAddSection:
    """Tests for FormsClient.add_section method."""

    def test_add_section_with_custom_id(self, mock_credentials):
        """Should set itemId when section_id is provided."""
        with patch("desk.services.forms.build") as mock_build:
            mock_service = MagicMock()
            mock_build.return_value = mock_service

            forms_mock = mock_service.forms.return_value
            forms_mock.batchUpdate.return_value.execute.return_value = {}

            from desk.services.forms import FormsClient

            client = FormsClient(mock_credentials)
            result = client.add_section("form_123", "Voice Details", section_id="voice_section")

            assert result["status"] == "ok"
            call_body = forms_mock.batchUpdate.call_args[1]["body"]
            item = call_body["requests"][0]["createItem"]["item"]
            assert item["itemId"] == "voice_section"
            assert item["title"] == "Voice Details"

    def test_add_section_without_custom_id(self, mock_credentials):
        """Should not set itemId when section_id is not provided."""
        with patch("desk.services.forms.build") as mock_build:
            mock_service = MagicMock()
            mock_build.return_value = mock_service

            forms_mock = mock_service.forms.return_value
            forms_mock.batchUpdate.return_value.execute.return_value = {}

            from desk.services.forms import FormsClient

            client = FormsClient(mock_credentials)
            result = client.add_section("form_123", "Part 2")

            assert result["status"] == "ok"
            call_body = forms_mock.batchUpdate.call_args[1]["body"]
            item = call_body["requests"][0]["createItem"]["item"]
            assert "itemId" not in item

    def test_add_section_default_index_fetches_form(self, mock_credentials):
        """Should fetch form and set location.index to item count when index is None."""
        with patch("desk.services.forms.build") as mock_build:
            mock_service = MagicMock()
            mock_build.return_value = mock_service

            forms_mock = mock_service.forms.return_value
            forms_mock.get.return_value.execute.return_value = {
                "items": [
                    {"title": "Q1", "questionItem": {"question": {}}},
                    {"title": "Section 1", "pageBreakItem": {}},
                ],
            }
            forms_mock.batchUpdate.return_value.execute.return_value = {}

            from desk.services.forms import FormsClient

            client = FormsClient(mock_credentials)
            result = client.add_section("form_123", "New Section")

            assert result["status"] == "ok"
            forms_mock.get.assert_called_once_with(formId="form_123")
            call_body = forms_mock.batchUpdate.call_args[1]["body"]
            location = call_body["requests"][0]["createItem"]["location"]
            assert location["index"] == 2

    def test_add_section_explicit_index_skips_get(self, mock_credentials):
        """Should use provided index and not call forms().get() when index is explicit."""
        with patch("desk.services.forms.build") as mock_build:
            mock_service = MagicMock()
            mock_build.return_value = mock_service

            forms_mock = mock_service.forms.return_value
            forms_mock.batchUpdate.return_value.execute.return_value = {}

            from desk.services.forms import FormsClient

            client = FormsClient(mock_credentials)
            result = client.add_section("form_123", "Inserted Section", index=3)

            assert result["status"] == "ok"
            forms_mock.get.assert_not_called()
            call_body = forms_mock.batchUpdate.call_args[1]["body"]
            location = call_body["requests"][0]["createItem"]["location"]
            assert location["index"] == 3


class TestSimplifyItems:
    """Tests for FormsClient._simplify_items method."""

    def test_includes_item_id_when_present(self, mock_credentials):
        """Should include itemId in simplified output."""
        with patch("desk.services.forms.build") as mock_build:
            mock_build.return_value = MagicMock()

            from desk.services.forms import FormsClient

            client = FormsClient(mock_credentials)
            items = [
                {"title": "Section 1", "itemId": "sec1", "pageBreakItem": {}},
            ]
            result = client._simplify_items(items)

            assert result[0]["itemId"] == "sec1"
            assert result[0]["type"] == "section"

    def test_omits_item_id_when_absent(self, mock_credentials):
        """Should not include itemId if not present on item."""
        with patch("desk.services.forms.build") as mock_build:
            mock_build.return_value = MagicMock()

            from desk.services.forms import FormsClient

            client = FormsClient(mock_credentials)
            items = [
                {"title": "Section 1", "pageBreakItem": {}},
            ]
            result = client._simplify_items(items)

            assert "itemId" not in result[0]

    def test_includes_branching_on_options(self, mock_credentials):
        """Should include goToSectionId/goToAction on options with branching."""
        with patch("desk.services.forms.build") as mock_build:
            mock_build.return_value = MagicMock()

            from desk.services.forms import FormsClient

            client = FormsClient(mock_credentials)
            items = [
                {
                    "title": "Tried voice?",
                    "questionItem": {
                        "question": {
                            "required": False,
                            "choiceQuestion": {
                                "type": "RADIO",
                                "options": [
                                    {"value": "Yes", "goToSectionId": "voice_section"},
                                    {"value": "No", "goToAction": "SUBMIT_FORM"},
                                ],
                            },
                        }
                    },
                },
            ]
            result = client._simplify_items(items)

            assert result[0]["type"] == "choice"
            options = result[0]["options"]
            assert options[0] == {"value": "Yes", "goToSectionId": "voice_section"}
            assert options[1] == {"value": "No", "goToAction": "SUBMIT_FORM"}

    def test_flattens_options_without_branching(self, mock_credentials):
        """Should flatten options to simple strings when no branching."""
        with patch("desk.services.forms.build") as mock_build:
            mock_build.return_value = MagicMock()

            from desk.services.forms import FormsClient

            client = FormsClient(mock_credentials)
            items = [
                {
                    "title": "Color?",
                    "questionItem": {
                        "question": {
                            "required": False,
                            "choiceQuestion": {
                                "type": "RADIO",
                                "options": [
                                    {"value": "Red"},
                                    {"value": "Blue"},
                                ],
                            },
                        }
                    },
                },
            ]
            result = client._simplify_items(items)

            assert result[0]["options"] == ["Red", "Blue"]

    def test_partial_branching_returns_dicts_for_all(self, mock_credentials):
        """Should return dicts for all options when only some have branching."""
        with patch("desk.services.forms.build") as mock_build:
            mock_build.return_value = MagicMock()

            from desk.services.forms import FormsClient

            client = FormsClient(mock_credentials)
            items = [
                {
                    "title": "Pick",
                    "questionItem": {
                        "question": {
                            "required": False,
                            "choiceQuestion": {
                                "type": "RADIO",
                                "options": [
                                    {"value": "A", "goToSectionId": "section_a"},
                                    {"value": "B"},
                                ],
                            },
                        }
                    },
                },
            ]
            result = client._simplify_items(items)

            options = result[0]["options"]
            assert isinstance(options[0], dict)
            assert options[0] == {"value": "A", "goToSectionId": "section_a"}
            assert isinstance(options[1], dict)
            assert options[1] == {"value": "B"}


# --- Helper for building a form with items (used by mutation tests) ---

def _form_with_items(*items):
    """Build a mock form response with given items."""
    return {"info": {"title": "Test"}, "items": list(items)}


def _text_question_item(item_id, title="Q?"):
    return {
        "itemId": item_id,
        "title": title,
        "questionItem": {
            "question": {"required": False, "textQuestion": {"paragraph": False}}
        },
    }


def _choice_question_item(item_id, title="Pick?", choices=None):
    options = [{"value": c} for c in (choices or ["A", "B"])]
    return {
        "itemId": item_id,
        "title": title,
        "questionItem": {
            "question": {
                "required": False,
                "choiceQuestion": {"type": "RADIO", "options": options},
            }
        },
    }


def _section_item(item_id, title="Section"):
    return {"itemId": item_id, "title": title, "pageBreakItem": {}}


class TestFindItemIndex:
    """Tests for FormsClient._find_item_index method."""

    def test_finds_item_by_id(self, mock_credentials):
        """Should return correct index and item data."""
        with patch("desk.services.forms.build") as mock_build:
            mock_service = MagicMock()
            mock_build.return_value = mock_service

            forms_mock = mock_service.forms.return_value
            forms_mock.get.return_value.execute.return_value = _form_with_items(
                _text_question_item("q1"),
                _section_item("sec1"),
                _text_question_item("q2"),
            )

            from desk.services.forms import FormsClient

            client = FormsClient(mock_credentials)
            index, item = client._find_item_index("form_123", "sec1")

            assert index == 1
            assert item["itemId"] == "sec1"

    def test_raises_on_missing_item(self, mock_credentials):
        """Should raise ValueError when item ID is not found."""
        with patch("desk.services.forms.build") as mock_build:
            mock_service = MagicMock()
            mock_build.return_value = mock_service

            forms_mock = mock_service.forms.return_value
            forms_mock.get.return_value.execute.return_value = _form_with_items(
                _text_question_item("q1"),
            )

            from desk.services.forms import FormsClient

            client = FormsClient(mock_credentials)
            with pytest.raises(ValueError, match="not found"):
                client._find_item_index("form_123", "nonexistent")


class TestUpdateForm:
    """Tests for FormsClient.update_form method."""

    def test_update_title_only(self, mock_credentials):
        """Should send updateFormInfo with title mask."""
        with patch("desk.services.forms.build") as mock_build:
            mock_service = MagicMock()
            mock_build.return_value = mock_service

            forms_mock = mock_service.forms.return_value
            forms_mock.batchUpdate.return_value.execute.return_value = {}

            from desk.services.forms import FormsClient

            client = FormsClient(mock_credentials)
            result = client.update_form("form_123", title="New Title")

            assert result["status"] == "ok"
            call_body = forms_mock.batchUpdate.call_args[1]["body"]
            req = call_body["requests"][0]["updateFormInfo"]
            assert req["info"]["title"] == "New Title"
            assert req["updateMask"] == "title"

    def test_update_description_only(self, mock_credentials):
        """Should send updateFormInfo with description mask."""
        with patch("desk.services.forms.build") as mock_build:
            mock_service = MagicMock()
            mock_build.return_value = mock_service

            forms_mock = mock_service.forms.return_value
            forms_mock.batchUpdate.return_value.execute.return_value = {}

            from desk.services.forms import FormsClient

            client = FormsClient(mock_credentials)
            result = client.update_form("form_123", description="New desc")

            assert result["status"] == "ok"
            call_body = forms_mock.batchUpdate.call_args[1]["body"]
            req = call_body["requests"][0]["updateFormInfo"]
            assert req["info"]["description"] == "New desc"
            assert req["updateMask"] == "description"

    def test_update_both_title_and_description(self, mock_credentials):
        """Should send updateFormInfo with both masks."""
        with patch("desk.services.forms.build") as mock_build:
            mock_service = MagicMock()
            mock_build.return_value = mock_service

            forms_mock = mock_service.forms.return_value
            forms_mock.batchUpdate.return_value.execute.return_value = {}

            from desk.services.forms import FormsClient

            client = FormsClient(mock_credentials)
            result = client.update_form("form_123", title="T", description="D")

            assert result["status"] == "ok"
            call_body = forms_mock.batchUpdate.call_args[1]["body"]
            req = call_body["requests"][0]["updateFormInfo"]
            assert req["info"] == {"title": "T", "description": "D"}
            assert "title" in req["updateMask"]
            assert "description" in req["updateMask"]

    def test_update_neither_raises_valueerror(self, mock_credentials):
        """Should raise ValueError when no fields provided."""
        with patch("desk.services.forms.build") as mock_build:
            mock_build.return_value = MagicMock()

            from desk.services.forms import FormsClient

            client = FormsClient(mock_credentials)
            with pytest.raises(ValueError, match="At least one"):
                client.update_form("form_123")


class TestUpdateItem:
    """Tests for FormsClient.update_item method."""

    def test_update_question_title(self, mock_credentials):
        """Should update question title via updateItem."""
        with patch("desk.services.forms.build") as mock_build:
            mock_service = MagicMock()
            mock_build.return_value = mock_service

            forms_mock = mock_service.forms.return_value
            forms_mock.get.return_value.execute.return_value = _form_with_items(
                _text_question_item("q1", "Old title"),
            )
            forms_mock.batchUpdate.return_value.execute.return_value = {}

            from desk.services.forms import FormsClient

            client = FormsClient(mock_credentials)
            result = client.update_item("form_123", "q1", title="New title")

            assert result["status"] == "ok"
            call_body = forms_mock.batchUpdate.call_args[1]["body"]
            req = call_body["requests"][0]["updateItem"]
            assert req["item"]["title"] == "New title"
            assert req["item"]["itemId"] == "q1"
            assert req["location"]["index"] == 0
            assert "title" in req["updateMask"]

    def test_update_question_required(self, mock_credentials):
        """Should update required flag."""
        with patch("desk.services.forms.build") as mock_build:
            mock_service = MagicMock()
            mock_build.return_value = mock_service

            forms_mock = mock_service.forms.return_value
            forms_mock.get.return_value.execute.return_value = _form_with_items(
                _text_question_item("q1"),
            )
            forms_mock.batchUpdate.return_value.execute.return_value = {}

            from desk.services.forms import FormsClient

            client = FormsClient(mock_credentials)
            result = client.update_item("form_123", "q1", required=True)

            assert result["status"] == "ok"
            call_body = forms_mock.batchUpdate.call_args[1]["body"]
            req = call_body["requests"][0]["updateItem"]
            assert req["item"]["questionItem"]["question"]["required"] is True
            assert "questionItem.question.required" in req["updateMask"]

    def test_update_choice_options(self, mock_credentials):
        """Should replace all options on a choice question."""
        with patch("desk.services.forms.build") as mock_build:
            mock_service = MagicMock()
            mock_build.return_value = mock_service

            forms_mock = mock_service.forms.return_value
            forms_mock.get.return_value.execute.return_value = _form_with_items(
                _choice_question_item("q1", choices=["Old1", "Old2"]),
            )
            forms_mock.batchUpdate.return_value.execute.return_value = {}

            from desk.services.forms import FormsClient

            client = FormsClient(mock_credentials)
            result = client.update_item("form_123", "q1", choices=["New1", "New2", "New3"])

            assert result["status"] == "ok"
            call_body = forms_mock.batchUpdate.call_args[1]["body"]
            req = call_body["requests"][0]["updateItem"]
            cq = req["item"]["questionItem"]["question"]["choiceQuestion"]
            assert cq["type"] == "RADIO"
            assert len(cq["options"]) == 3
            assert cq["options"][0] == {"value": "New1"}

    def test_update_choice_with_goto(self, mock_credentials):
        """Should apply branching to replaced options."""
        with patch("desk.services.forms.build") as mock_build:
            mock_service = MagicMock()
            mock_build.return_value = mock_service

            forms_mock = mock_service.forms.return_value
            forms_mock.get.return_value.execute.return_value = _form_with_items(
                _choice_question_item("q1"),
            )
            forms_mock.batchUpdate.return_value.execute.return_value = {}

            from desk.services.forms import FormsClient

            client = FormsClient(mock_credentials)
            result = client.update_item(
                "form_123", "q1",
                choices=["Yes", "No"],
                goto={"Yes": "sec1", "No": "SUBMIT_FORM"},
            )

            assert result["status"] == "ok"
            call_body = forms_mock.batchUpdate.call_args[1]["body"]
            options = call_body["requests"][0]["updateItem"]["item"]["questionItem"]["question"]["choiceQuestion"]["options"]
            assert options[0] == {"value": "Yes", "goToSectionId": "sec1"}
            assert options[1] == {"value": "No", "goToAction": "SUBMIT_FORM"}

    def test_choices_on_non_choice_raises_valueerror(self, mock_credentials):
        """Should raise ValueError when --choices used on text question."""
        with patch("desk.services.forms.build") as mock_build:
            mock_service = MagicMock()
            mock_build.return_value = mock_service

            forms_mock = mock_service.forms.return_value
            forms_mock.get.return_value.execute.return_value = _form_with_items(
                _text_question_item("q1"),
            )

            from desk.services.forms import FormsClient

            client = FormsClient(mock_credentials)
            with pytest.raises(ValueError, match="only be used on choice"):
                client.update_item("form_123", "q1", choices=["A", "B"])

    def test_goto_without_choices_raises_valueerror(self, mock_credentials):
        """Should raise ValueError when --goto used without --choices."""
        with patch("desk.services.forms.build") as mock_build:
            mock_service = MagicMock()
            mock_build.return_value = mock_service

            forms_mock = mock_service.forms.return_value
            forms_mock.get.return_value.execute.return_value = _form_with_items(
                _choice_question_item("q1"),
            )

            from desk.services.forms import FormsClient

            client = FormsClient(mock_credentials)
            with pytest.raises(ValueError, match="requires --choices"):
                client.update_item("form_123", "q1", goto={"A": "sec1"})

    def test_update_section_title(self, mock_credentials):
        """Should update section title."""
        with patch("desk.services.forms.build") as mock_build:
            mock_service = MagicMock()
            mock_build.return_value = mock_service

            forms_mock = mock_service.forms.return_value
            forms_mock.get.return_value.execute.return_value = _form_with_items(
                _text_question_item("q1"),
                _section_item("sec1", "Old Title"),
            )
            forms_mock.batchUpdate.return_value.execute.return_value = {}

            from desk.services.forms import FormsClient

            client = FormsClient(mock_credentials)
            result = client.update_item("form_123", "sec1", title="New Title")

            assert result["status"] == "ok"
            call_body = forms_mock.batchUpdate.call_args[1]["body"]
            req = call_body["requests"][0]["updateItem"]
            assert req["item"]["title"] == "New Title"
            assert req["location"]["index"] == 1

    def test_update_item_not_found_raises_valueerror(self, mock_credentials):
        """Should raise ValueError when item ID not found."""
        with patch("desk.services.forms.build") as mock_build:
            mock_service = MagicMock()
            mock_build.return_value = mock_service

            forms_mock = mock_service.forms.return_value
            forms_mock.get.return_value.execute.return_value = _form_with_items(
                _text_question_item("q1"),
            )

            from desk.services.forms import FormsClient

            client = FormsClient(mock_credentials)
            with pytest.raises(ValueError, match="not found"):
                client.update_item("form_123", "nonexistent", title="X")


class TestDeleteItem:
    """Tests for FormsClient.delete_item method."""

    def test_delete_question(self, mock_credentials):
        """Should delete a question by its item ID."""
        with patch("desk.services.forms.build") as mock_build:
            mock_service = MagicMock()
            mock_build.return_value = mock_service

            forms_mock = mock_service.forms.return_value
            forms_mock.get.return_value.execute.return_value = _form_with_items(
                _text_question_item("q1"),
                _text_question_item("q2"),
            )
            forms_mock.batchUpdate.return_value.execute.return_value = {}

            from desk.services.forms import FormsClient

            client = FormsClient(mock_credentials)
            result = client.delete_item("form_123", "q2")

            assert result["status"] == "ok"
            call_body = forms_mock.batchUpdate.call_args[1]["body"]
            req = call_body["requests"][0]["deleteItem"]
            assert req["location"]["index"] == 1

    def test_delete_section(self, mock_credentials):
        """Should delete a section by its item ID."""
        with patch("desk.services.forms.build") as mock_build:
            mock_service = MagicMock()
            mock_build.return_value = mock_service

            forms_mock = mock_service.forms.return_value
            forms_mock.get.return_value.execute.return_value = _form_with_items(
                _section_item("sec1"),
                _text_question_item("q1"),
            )
            forms_mock.batchUpdate.return_value.execute.return_value = {}

            from desk.services.forms import FormsClient

            client = FormsClient(mock_credentials)
            result = client.delete_item("form_123", "sec1")

            assert result["status"] == "ok"
            call_body = forms_mock.batchUpdate.call_args[1]["body"]
            req = call_body["requests"][0]["deleteItem"]
            assert req["location"]["index"] == 0

    def test_delete_nonexistent_raises_valueerror(self, mock_credentials):
        """Should raise ValueError when item ID not found."""
        with patch("desk.services.forms.build") as mock_build:
            mock_service = MagicMock()
            mock_build.return_value = mock_service

            forms_mock = mock_service.forms.return_value
            forms_mock.get.return_value.execute.return_value = _form_with_items()

            from desk.services.forms import FormsClient

            client = FormsClient(mock_credentials)
            with pytest.raises(ValueError, match="not found"):
                client.delete_item("form_123", "nonexistent")


class TestPublish:
    """Tests for FormsClient.publish method."""

    def test_publish_with_accepting(self, mock_credentials):
        """Should call setPublishSettings with isPublished and isAcceptingResponses."""
        with patch("desk.services.forms.build") as mock_build:
            mock_service = MagicMock()
            mock_build.return_value = mock_service

            forms_mock = mock_service.forms.return_value
            forms_mock.setPublishSettings.return_value.execute.return_value = {}

            from desk.services.forms import FormsClient

            client = FormsClient(mock_credentials)
            result = client.publish("form_123")

            assert result["status"] == "ok"
            call_body = forms_mock.setPublishSettings.call_args[1]["body"]
            state = call_body["publishSettings"]["publishState"]
            assert state["isPublished"] is True
            assert state["isAcceptingResponses"] is True

    def test_publish_without_accepting(self, mock_credentials):
        """Should set isAcceptingResponses to False when specified."""
        with patch("desk.services.forms.build") as mock_build:
            mock_service = MagicMock()
            mock_build.return_value = mock_service

            forms_mock = mock_service.forms.return_value
            forms_mock.setPublishSettings.return_value.execute.return_value = {}

            from desk.services.forms import FormsClient

            client = FormsClient(mock_credentials)
            result = client.publish("form_123", accepting_responses=False)

            assert result["status"] == "ok"
            call_body = forms_mock.setPublishSettings.call_args[1]["body"]
            state = call_body["publishSettings"]["publishState"]
            assert state["isPublished"] is True
            assert state["isAcceptingResponses"] is False


class TestUnpublish:
    """Tests for FormsClient.unpublish method."""

    def test_unpublish(self, mock_credentials):
        """Should call setPublishSettings with isPublished=False."""
        with patch("desk.services.forms.build") as mock_build:
            mock_service = MagicMock()
            mock_build.return_value = mock_service

            forms_mock = mock_service.forms.return_value
            forms_mock.setPublishSettings.return_value.execute.return_value = {}

            from desk.services.forms import FormsClient

            client = FormsClient(mock_credentials)
            result = client.unpublish("form_123")

            assert result["status"] == "ok"
            call_body = forms_mock.setPublishSettings.call_args[1]["body"]
            state = call_body["publishSettings"]["publishState"]
            assert state["isPublished"] is False
