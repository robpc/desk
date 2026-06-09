"""Tests for slides CLI commands."""

import json
import pytest
from click.testing import CliRunner
from unittest.mock import MagicMock, patch


@pytest.fixture
def runner():
    return CliRunner()


@pytest.fixture
def mock_get_credentials():
    with patch("desk.commands.slides.get_credentials") as mock:
        mock.return_value = MagicMock()
        yield mock


@pytest.fixture
def mock_slides_client_class():
    with patch("desk.commands.slides.SlidesClient") as mock:
        yield mock


class TestSlidesCreate:
    def test_create_json_output(self, runner, mock_get_credentials, mock_slides_client_class):
        from desk.commands.slides import slides

        client = MagicMock()
        client.create.return_value = {
            "presentationId": "p1",
            "title": "Deck",
            "slideCount": 1,
            "webViewLink": "https://docs.google.com/presentation/d/p1/edit",
        }
        mock_slides_client_class.return_value = client

        result = runner.invoke(slides, ["create", "Deck", "--json"])

        assert result.exit_code == 0
        output = json.loads(result.output)
        assert output["success"] is True
        assert output["operation"] == "create"
        assert output["targets"][0]["id"] == "p1"

    def test_create_human_output(self, runner, mock_get_credentials, mock_slides_client_class):
        from desk.commands.slides import slides

        client = MagicMock()
        client.create.return_value = {
            "presentationId": "p1", "title": "Deck", "slideCount": 1, "webViewLink": "",
        }
        mock_slides_client_class.return_value = client

        result = runner.invoke(slides, ["create", "Deck"])

        assert result.exit_code == 0
        assert "create" in result.output.lower()


class TestSlidesRead:
    def test_read_json(self, runner, mock_get_credentials, mock_slides_client_class):
        from desk.commands.slides import slides

        client = MagicMock()
        client.read.return_value = {
            "presentationId": "p1",
            "title": "Deck",
            "slideCount": 1,
            "slides": [{"index": 0, "objectId": "s1", "text": "Hello"}],
        }
        mock_slides_client_class.return_value = client

        result = runner.invoke(slides, ["read", "p1", "--json"])

        assert result.exit_code == 0
        output = json.loads(result.output)
        assert output["slides"][0]["text"] == "Hello"

    def test_read_not_found_json_error(self, runner, mock_get_credentials, mock_slides_client_class):
        from desk.commands.slides import slides

        client = MagicMock()
        client.read.side_effect = RuntimeError("Slides API error: 404 not found")
        mock_slides_client_class.return_value = client

        result = runner.invoke(slides, ["read", "bad", "--json"])

        assert result.exit_code == 1
        output = json.loads(result.output)
        assert output["success"] is False
        assert output["error"]["code"] == "PRESENTATION_NOT_FOUND"


class TestSlidesInspect:
    def test_inspect_json(self, runner, mock_get_credentials, mock_slides_client_class):
        from desk.commands.slides import slides

        client = MagicMock()
        client.inspect.return_value = {
            "presentationId": "p1",
            "title": "Deck",
            "slideCount": 1,
            "slides": [{
                "index": 0, "objectId": "s1",
                "elements": [{
                    "objectId": "t1", "type": "shape",
                    "shapeType": "TEXT_BOX", "placeholder": "TITLE", "text": "Hi",
                }],
            }],
        }
        mock_slides_client_class.return_value = client

        result = runner.invoke(slides, ["inspect", "p1", "--json"])

        assert result.exit_code == 0
        output = json.loads(result.output)
        assert output["slides"][0]["elements"][0]["placeholder"] == "TITLE"


class TestAddSlide:
    def test_add_slide_default_layout(self, runner, mock_get_credentials, mock_slides_client_class):
        from desk.commands.slides import slides

        client = MagicMock()
        client.add_slide.return_value = {
            "presentationId": "p1", "objectId": "new", "layout": "TITLE_AND_BODY",
        }
        mock_slides_client_class.return_value = client

        result = runner.invoke(slides, ["add-slide", "p1", "--json"])

        assert result.exit_code == 0
        output = json.loads(result.output)
        assert output["targets"][0]["slide_object_id"] == "new"
        assert "delete-object" in output["undo"]["command"]
        client.add_slide.assert_called_once_with("p1", layout="TITLE_AND_BODY", index=None)

    def test_add_slide_rejects_invalid_layout(self, runner, mock_get_credentials, mock_slides_client_class):
        from desk.commands.slides import slides

        result = runner.invoke(slides, ["add-slide", "p1", "--layout", "NONSENSE"])

        # Click rejects the choice before the client is touched
        assert result.exit_code != 0

    def test_add_slide_negative_index(self, runner, mock_get_credentials, mock_slides_client_class):
        from desk.commands.slides import slides

        result = runner.invoke(slides, ["add-slide", "p1", "--index", "-1", "--json"])

        assert result.exit_code == 1
        output = json.loads(result.output)
        assert output["error"]["code"] == "INVALID_INPUT"


class TestDeleteSlide:
    def test_delete_slide_requires_yes_noninteractive(self, runner, mock_get_credentials, mock_slides_client_class):
        from desk.commands.slides import slides

        client = MagicMock()
        mock_slides_client_class.return_value = client

        # No --yes, non-interactive (CliRunner stdin is not a tty)
        result = runner.invoke(slides, ["delete-slide", "p1", "2", "--json"])

        assert result.exit_code == 1
        output = json.loads(result.output)
        assert output["error"]["code"] == "INVALID_INPUT"
        client.delete_slide.assert_not_called()

    def test_delete_slide_with_yes(self, runner, mock_get_credentials, mock_slides_client_class):
        from desk.commands.slides import slides

        client = MagicMock()
        client.delete_slide.return_value = {"presentationId": "p1", "objectId": "s2", "status": "ok"}
        mock_slides_client_class.return_value = client

        result = runner.invoke(slides, ["delete-slide", "p1", "2", "--yes", "--json"])

        assert result.exit_code == 0
        output = json.loads(result.output)
        assert output["operation"] == "delete-slide"
        client.delete_slide.assert_called_once_with("p1", "2")


class TestInsertText:
    def test_insert_text(self, runner, mock_get_credentials, mock_slides_client_class):
        from desk.commands.slides import slides

        client = MagicMock()
        client.insert_text.return_value = {"presentationId": "p1", "objectId": "sh", "status": "ok"}
        mock_slides_client_class.return_value = client

        result = runner.invoke(slides, ["insert-text", "p1", "sh", "Title text", "--json"])

        assert result.exit_code == 0
        output = json.loads(result.output)
        assert output["changes"]["text_length"] == len("Title text")
        client.insert_text.assert_called_once_with("p1", "sh", "Title text", index=0)

    def test_insert_text_negative_at(self, runner, mock_get_credentials, mock_slides_client_class):
        from desk.commands.slides import slides

        result = runner.invoke(slides, ["insert-text", "p1", "sh", "x", "--at", "-1", "--json"])

        assert result.exit_code == 1
        output = json.loads(result.output)
        assert output["error"]["code"] == "INVALID_INPUT"


class TestReplaceText:
    def test_replace_text_reports_occurrences(self, runner, mock_get_credentials, mock_slides_client_class):
        from desk.commands.slides import slides

        client = MagicMock()
        client.replace_text.return_value = {
            "presentationId": "p1", "occurrences_changed": 3, "status": "ok",
        }
        mock_slides_client_class.return_value = client

        result = runner.invoke(
            slides, ["replace-text", "p1", "{{x}}", "Y", "--ignore-case", "--json"]
        )

        assert result.exit_code == 0
        output = json.loads(result.output)
        assert output["changes"]["occurrences_changed"] == 3
        client.replace_text.assert_called_once_with("p1", "{{x}}", "Y", match_case=False)


class TestExport:
    def test_export_writes_file(self, runner, mock_get_credentials, mock_slides_client_class, tmp_path):
        from desk.commands.slides import slides

        client = MagicMock()
        client.export.return_value = b"PDFDATA"
        mock_slides_client_class.return_value = client

        dest = tmp_path / "deck.pdf"
        result = runner.invoke(slides, ["export", "p1", str(dest), "--json"])

        assert result.exit_code == 0
        assert dest.read_bytes() == b"PDFDATA"
