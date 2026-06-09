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


class TestInsertImage:
    def test_insert_image(self, runner, mock_get_credentials, mock_slides_client_class):
        from desk.commands.slides import slides

        client = MagicMock()
        client.insert_image.return_value = {
            "presentationId": "p1", "slideObjectId": "s0", "objectId": "img1", "status": "ok",
        }
        mock_slides_client_class.return_value = client

        result = runner.invoke(
            slides, ["insert-image", "p1", "0", "--url", "https://x/y.png", "--json"]
        )

        assert result.exit_code == 0
        output = json.loads(result.output)
        assert output["targets"][0]["object_id"] == "img1"
        assert "delete-object" in output["undo"]["command"]
        client.insert_image.assert_called_once_with(
            "p1", "0", "https://x/y.png", x=None, y=None, width=None, height=None, region=None
        )

    def test_insert_image_requires_url(self, runner, mock_get_credentials, mock_slides_client_class):
        from desk.commands.slides import slides

        result = runner.invoke(slides, ["insert-image", "p1", "0"])
        assert result.exit_code != 0


class TestInsertTable:
    def test_insert_table(self, runner, mock_get_credentials, mock_slides_client_class):
        from desk.commands.slides import slides

        client = MagicMock()
        client.insert_table.return_value = {
            "presentationId": "p1", "slideObjectId": "s0", "objectId": "tbl1", "status": "ok",
        }
        mock_slides_client_class.return_value = client

        result = runner.invoke(
            slides, ["insert-table", "p1", "0", "--rows", "3", "--cols", "4", "--json"]
        )

        assert result.exit_code == 0
        output = json.loads(result.output)
        assert output["changes"]["rows"] == 3
        client.insert_table.assert_called_once_with(
            "p1", "0", 3, 4, x=None, y=None, width=None, height=None, region=None
        )

    def test_insert_table_rejects_zero_rows(self, runner, mock_get_credentials, mock_slides_client_class):
        from desk.commands.slides import slides

        result = runner.invoke(
            slides, ["insert-table", "p1", "0", "--rows", "0", "--cols", "2", "--json"]
        )

        assert result.exit_code == 1
        output = json.loads(result.output)
        assert output["error"]["code"] == "INVALID_INPUT"


class TestInsertShape:
    def test_insert_shape_with_text(self, runner, mock_get_credentials, mock_slides_client_class):
        from desk.commands.slides import slides

        client = MagicMock()
        client.insert_shape.return_value = {
            "presentationId": "p1", "slideObjectId": "s0", "objectId": "shape_x", "status": "ok",
        }
        mock_slides_client_class.return_value = client

        result = runner.invoke(
            slides, ["insert-shape", "p1", "0", "--text", "Note", "--json"]
        )

        assert result.exit_code == 0
        output = json.loads(result.output)
        assert output["changes"]["type"] == "TEXT_BOX"
        assert output["changes"]["text_length"] == 4
        client.insert_shape.assert_called_once_with(
            "p1", "0", shape_type="TEXT_BOX", text="Note",
            x=None, y=None, width=None, height=None, region=None,
        )

    def test_insert_shape_rejects_bad_type(self, runner, mock_get_credentials, mock_slides_client_class):
        from desk.commands.slides import slides

        result = runner.invoke(slides, ["insert-shape", "p1", "0", "--type", "BOGUS"])
        assert result.exit_code != 0


class TestStyleCommand:
    def test_style(self, runner, mock_get_credentials, mock_slides_client_class):
        from desk.commands.slides import slides

        client = MagicMock()
        client.style_text.return_value = {"presentationId": "p1", "objectId": "sh", "status": "ok"}
        mock_slides_client_class.return_value = client

        result = runner.invoke(
            slides, ["style", "p1", "sh", "--bold", "--font-size", "24", "--color", "#FF0000", "--json"]
        )

        assert result.exit_code == 0
        output = json.loads(result.output)
        assert output["changes"]["bold"] is True
        assert output["changes"]["color"] == "#FF0000"

    def test_style_partial_range_rejected(self, runner, mock_get_credentials, mock_slides_client_class):
        from desk.commands.slides import slides

        result = runner.invoke(slides, ["style", "p1", "sh", "--start", "0", "--json"])

        assert result.exit_code == 1
        output = json.loads(result.output)
        assert output["error"]["code"] == "INVALID_INPUT"

    def test_style_bad_color_rejected(self, runner, mock_get_credentials, mock_slides_client_class):
        from desk.commands.slides import slides

        client = MagicMock()
        client.style_text.side_effect = ValueError("Invalid color: mauve.")
        mock_slides_client_class.return_value = client

        result = runner.invoke(slides, ["style", "p1", "sh", "--color", "mauve", "--json"])

        assert result.exit_code == 1
        output = json.loads(result.output)
        assert output["error"]["code"] == "INVALID_INPUT"


class TestFormatCommand:
    def test_format_shape(self, runner, mock_get_credentials, mock_slides_client_class):
        from desk.commands.slides import slides

        client = MagicMock()
        client.format_element.return_value = {
            "presentationId": "p1", "objectId": "sh", "elementType": "shape", "status": "ok",
        }
        mock_slides_client_class.return_value = client

        result = runner.invoke(
            slides, ["format", "p1", "sh", "--fill", "#FFF3CD", "--outline", "ACCENT1", "--json"]
        )

        assert result.exit_code == 0
        output = json.loads(result.output)
        assert output["changes"]["element_type"] == "shape"
        assert output["changes"]["fill"] == "#FFF3CD"


class TestPlaceCommand:
    def test_place(self, runner, mock_get_credentials, mock_slides_client_class):
        from desk.commands.slides import slides

        client = MagicMock()
        client.place_element.return_value = {
            "presentationId": "p1", "objectId": "el", "region": "center", "status": "ok",
        }
        mock_slides_client_class.return_value = client

        result = runner.invoke(slides, ["place", "p1", "el", "--region", "center", "--json"])

        assert result.exit_code == 0
        output = json.loads(result.output)
        assert output["changes"]["region"] == "center"
        client.place_element.assert_called_once_with("p1", "el", "center")

    def test_place_bad_region_rejected(self, runner, mock_get_credentials, mock_slides_client_class):
        from desk.commands.slides import slides

        result = runner.invoke(slides, ["place", "p1", "el", "--region", "nowhere"])
        assert result.exit_code != 0  # click.Choice rejects


class TestRegionOnInsert:
    def test_region_and_coords_mutually_exclusive(self, runner, mock_get_credentials, mock_slides_client_class):
        from desk.commands.slides import slides

        client = MagicMock()
        mock_slides_client_class.return_value = client

        result = runner.invoke(
            slides,
            ["insert-shape", "p1", "0", "--region", "center", "--x", "10", "--json"],
        )

        assert result.exit_code == 1
        output = json.loads(result.output)
        assert output["error"]["code"] == "INVALID_INPUT"
        client.insert_shape.assert_not_called()

    def test_region_passed_through(self, runner, mock_get_credentials, mock_slides_client_class):
        from desk.commands.slides import slides

        client = MagicMock()
        client.insert_image.return_value = {
            "presentationId": "p1", "slideObjectId": "s0", "objectId": "img", "status": "ok",
        }
        mock_slides_client_class.return_value = client

        result = runner.invoke(
            slides,
            ["insert-image", "p1", "0", "--url", "https://x/y.png", "--region", "right-half", "--json"],
        )

        assert result.exit_code == 0
        client.insert_image.assert_called_once_with(
            "p1", "0", "https://x/y.png",
            x=None, y=None, width=None, height=None, region="right-half",
        )


class TestArrangeCommand:
    def test_arrange_columns(self, runner, mock_get_credentials, mock_slides_client_class):
        from desk.commands.slides import slides

        client = MagicMock()
        client.arrange_elements.return_value = {
            "presentationId": "p1", "objectIds": ["a", "b", "c"],
            "mode": "columns", "region": None, "status": "ok",
        }
        mock_slides_client_class.return_value = client

        result = runner.invoke(
            slides, ["arrange", "p1", "a", "b", "c", "--as", "columns", "--json"]
        )

        assert result.exit_code == 0
        output = json.loads(result.output)
        assert output["changes"]["mode"] == "columns"
        assert output["changes"]["count"] == 3
        assert output["targets"][0]["object_ids"] == ["a", "b", "c"]
        client.arrange_elements.assert_called_once_with(
            "p1", ["a", "b", "c"], "columns", region=None
        )

    def test_arrange_requires_objects(self, runner, mock_get_credentials, mock_slides_client_class):
        from desk.commands.slides import slides

        result = runner.invoke(slides, ["arrange", "p1", "--as", "rows"])
        assert result.exit_code != 0  # nargs=-1 required

    def test_arrange_rejects_bad_mode(self, runner, mock_get_credentials, mock_slides_client_class):
        from desk.commands.slides import slides

        result = runner.invoke(slides, ["arrange", "p1", "a", "--as", "spiral"])
        assert result.exit_code != 0  # click.Choice rejects


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
