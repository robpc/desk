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
        client.add_slide.assert_called_once_with(
            "p1", layout="TITLE_AND_BODY", index=None, title=None, subtitle=None, body=None
        )

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
            "p1", "0", rows=3, columns=4, x=None, y=None, width=None, height=None,
            region=None, data=None,
        )

    def test_insert_table_rejects_zero_rows(self, runner, mock_get_credentials, mock_slides_client_class):
        from desk.commands.slides import slides

        # Dimension validation lives in the service now; surfaced as INVALID_INPUT.
        client = MagicMock()
        client.insert_table.side_effect = ValueError("Invalid dimensions: rows=0, cols=2.")
        mock_slides_client_class.return_value = client

        result = runner.invoke(
            slides, ["insert-table", "p1", "0", "--rows", "0", "--cols", "2", "--json"]
        )

        assert result.exit_code == 1
        output = json.loads(result.output)
        assert output["error"]["code"] == "INVALID_INPUT"

    def test_insert_table_with_data(self, runner, mock_get_credentials, mock_slides_client_class):
        from desk.commands.slides import slides

        client = MagicMock()
        client.insert_table.return_value = {
            "presentationId": "p1", "slideObjectId": "s0", "objectId": "tbl",
            "status": "ok", "filled_cells": 4,
        }
        mock_slides_client_class.return_value = client

        result = runner.invoke(
            slides, ["insert-table", "p1", "0", "--data", '[["Q","Rev"],["Q1","12"]]', "--json"]
        )

        assert result.exit_code == 0
        out = json.loads(result.output)
        assert out["changes"]["filled_cells"] == 4
        _, kwargs = client.insert_table.call_args
        assert kwargs["data"] == [["Q", "Rev"], ["Q1", "12"]]

    def test_insert_table_bad_data_json(self, runner, mock_get_credentials, mock_slides_client_class):
        from desk.commands.slides import slides

        result = runner.invoke(slides, ["insert-table", "p1", "0", "--data", "not json", "--json"])
        assert result.exit_code == 1
        assert json.loads(result.output)["error"]["code"] == "INVALID_INPUT"


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


class TestInspectTheme:
    def test_theme_flag_includes_palette(self, runner, mock_get_credentials, mock_slides_client_class):
        from desk.commands.slides import slides

        client = MagicMock()
        client.inspect.return_value = {
            "presentationId": "p1", "title": "D", "pageSize": {"width": 720, "height": 405},
            "slideCount": 0, "slides": [],
        }
        client.get_theme.return_value = {"theme": [{"name": "ACCENT1", "hex": "#FF0000"}]}
        mock_slides_client_class.return_value = client

        result = runner.invoke(slides, ["inspect", "p1", "--theme", "--json"])

        assert result.exit_code == 0
        out = json.loads(result.output)
        assert out["theme"][0]["name"] == "ACCENT1"
        client.get_theme.assert_called_once_with("p1")

    def test_no_theme_flag_skips_palette(self, runner, mock_get_credentials, mock_slides_client_class):
        from desk.commands.slides import slides

        client = MagicMock()
        client.inspect.return_value = {
            "presentationId": "p1", "title": "D", "pageSize": {"width": 720, "height": 405},
            "slideCount": 0, "slides": [],
        }
        mock_slides_client_class.return_value = client

        result = runner.invoke(slides, ["inspect", "p1", "--json"])
        assert result.exit_code == 0
        assert "theme" not in json.loads(result.output)
        client.get_theme.assert_not_called()


class TestStyleAlignAndFormatValign:
    def test_style_align(self, runner, mock_get_credentials, mock_slides_client_class):
        from desk.commands.slides import slides

        client = MagicMock()
        client.style_text.return_value = {"presentationId": "p1", "objectId": "sh", "status": "ok"}
        mock_slides_client_class.return_value = client

        result = runner.invoke(slides, ["style", "p1", "sh", "--align", "CENTER", "--json"])

        assert result.exit_code == 0
        assert json.loads(result.output)["changes"]["align"] == "CENTER"
        _, kwargs = client.style_text.call_args
        assert kwargs["alignment"] == "CENTER"

    def test_format_valign(self, runner, mock_get_credentials, mock_slides_client_class):
        from desk.commands.slides import slides

        client = MagicMock()
        client.format_element.return_value = {
            "presentationId": "p1", "objectId": "sh", "elementType": "shape", "status": "ok",
        }
        mock_slides_client_class.return_value = client

        result = runner.invoke(slides, ["format", "p1", "sh", "--valign", "MIDDLE", "--json"])

        assert result.exit_code == 0
        assert json.loads(result.output)["changes"]["valign"] == "MIDDLE"
        _, kwargs = client.format_element.call_args
        assert kwargs["valign"] == "MIDDLE"


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
        client.place_element.assert_called_once_with(
            "p1", "el", region="center", x=None, y=None, width=None, height=None
        )

    def test_place_by_coords_move(self, runner, mock_get_credentials, mock_slides_client_class):
        from desk.commands.slides import slides

        client = MagicMock()
        client.place_element.return_value = {
            "presentationId": "p1", "objectId": "el", "status": "ok",
            "box": {"x": 120, "y": 80, "width": 100, "height": 50},
        }
        mock_slides_client_class.return_value = client

        result = runner.invoke(slides, ["place", "p1", "el", "--x", "120", "--y", "80", "--json"])

        assert result.exit_code == 0
        out = json.loads(result.output)
        assert out["changes"]["box"]["x"] == 120
        client.place_element.assert_called_once_with(
            "p1", "el", region=None, x=120.0, y=80.0, width=None, height=None
        )

    def test_place_table_resize_rejected(self, runner, mock_get_credentials, mock_slides_client_class):
        from desk.commands.slides import slides

        client = MagicMock()
        client.place_element.side_effect = ValueError(
            "Tables can't be resized via the API; move with --x/--y instead."
        )
        mock_slides_client_class.return_value = client

        result = runner.invoke(slides, ["place", "p1", "tbl", "--width", "300", "--json"])
        assert result.exit_code == 1
        assert json.loads(result.output)["error"]["code"] == "INVALID_INPUT"

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


class TestAddSlideEmitsPlaceholders:
    def test_placeholders_in_json(self, runner, mock_get_credentials, mock_slides_client_class):
        from desk.commands.slides import slides

        client = MagicMock()
        client.add_slide.return_value = {
            "presentationId": "p1", "objectId": "new", "layout": "TITLE_AND_BODY",
            "placeholders": [
                {"type": "TITLE", "objectId": "t1"},
                {"type": "BODY", "objectId": "b1"},
            ],
        }
        mock_slides_client_class.return_value = client

        result = runner.invoke(slides, ["add-slide", "p1", "--json"])

        assert result.exit_code == 0
        output = json.loads(result.output)
        phs = output["changes"]["placeholders"]
        assert {"type": "TITLE", "objectId": "t1"} in phs


class TestAddSlideInlineFill:
    def test_add_slide_with_title_body(self, runner, mock_get_credentials, mock_slides_client_class):
        from desk.commands.slides import slides

        client = MagicMock()
        client.add_slide.return_value = {
            "presentationId": "p1", "objectId": "new", "layout": "TITLE_AND_BODY",
            "placeholders": [{"type": "TITLE", "objectId": "t1"}, {"type": "BODY", "objectId": "b1"}],
            "filled": [{"field": "title", "objectId": "t1"}, {"field": "body", "objectId": "b1"}],
        }
        mock_slides_client_class.return_value = client

        result = runner.invoke(
            slides, ["add-slide", "p1", "--title", "Q3", "--body", "Up 12%", "--json"]
        )

        assert result.exit_code == 0
        output = json.loads(result.output)
        assert len(output["changes"]["filled"]) == 2
        client.add_slide.assert_called_once_with(
            "p1", layout="TITLE_AND_BODY", index=None, title="Q3", subtitle=None, body="Up 12%"
        )

    def test_add_slide_missing_placeholder_is_invalid_input(
        self, runner, mock_get_credentials, mock_slides_client_class
    ):
        from desk.commands.slides import slides

        client = MagicMock()
        client.add_slide.side_effect = ValueError(
            "--body: layout TITLE_ONLY has no matching placeholder (available: TITLE)."
        )
        mock_slides_client_class.return_value = client

        result = runner.invoke(
            slides, ["add-slide", "p1", "--layout", "TITLE_ONLY", "--body", "x", "--json"]
        )

        assert result.exit_code == 1
        output = json.loads(result.output)
        assert output["error"]["code"] == "INVALID_INPUT"


class TestSetNotesCommand:
    def test_set_notes(self, runner, mock_get_credentials, mock_slides_client_class):
        from desk.commands.slides import slides

        client = MagicMock()
        client.set_notes.return_value = {
            "presentationId": "p1", "slideObjectId": "s0",
            "notesObjectId": "n1", "mode": "replace", "status": "ok",
        }
        mock_slides_client_class.return_value = client

        result = runner.invoke(slides, ["set-notes", "p1", "0", "Talk track", "--json"])

        assert result.exit_code == 0
        output = json.loads(result.output)
        assert output["operation"] == "set-notes"
        assert output["changes"]["mode"] == "replace"
        client.set_notes.assert_called_once_with("p1", "0", "Talk track", mode="replace")

    def test_set_notes_append(self, runner, mock_get_credentials, mock_slides_client_class):
        from desk.commands.slides import slides

        client = MagicMock()
        client.set_notes.return_value = {
            "presentationId": "p1", "slideObjectId": "s0",
            "notesObjectId": "n1", "mode": "append", "status": "ok",
        }
        mock_slides_client_class.return_value = client

        result = runner.invoke(
            slides, ["set-notes", "p1", "0", "more", "--mode", "append", "--json"]
        )

        assert result.exit_code == 0
        client.set_notes.assert_called_once_with("p1", "0", "more", mode="append")


class TestSetCellCommand:
    def test_set_cell(self, runner, mock_get_credentials, mock_slides_client_class):
        from desk.commands.slides import slides

        client = MagicMock()
        client.set_cell.return_value = {
            "presentationId": "p1", "objectId": "tbl", "row": 0, "col": 1,
            "mode": "replace", "status": "ok",
        }
        mock_slides_client_class.return_value = client

        result = runner.invoke(
            slides, ["set-cell", "p1", "tbl", "Q1", "--row", "0", "--col", "1", "--json"]
        )

        assert result.exit_code == 0
        output = json.loads(result.output)
        assert output["operation"] == "set-cell"
        assert output["changes"]["row"] == 0 and output["changes"]["col"] == 1
        client.set_cell.assert_called_once_with("p1", "tbl", 0, 1, "Q1", mode="replace")

    def test_set_cell_out_of_range_is_invalid_input(
        self, runner, mock_get_credentials, mock_slides_client_class
    ):
        from desk.commands.slides import slides

        client = MagicMock()
        client.set_cell.side_effect = ValueError("Cell (5,0) out of range for a 2x2 table.")
        mock_slides_client_class.return_value = client

        result = runner.invoke(
            slides, ["set-cell", "p1", "tbl", "x", "--row", "5", "--col", "0", "--json"]
        )

        assert result.exit_code == 1
        assert json.loads(result.output)["error"]["code"] == "INVALID_INPUT"


class TestErrorSuggestionsNotMailLeaked:
    def test_slides_invalid_input_has_no_gmail_suggestions(
        self, runner, mock_get_credentials, mock_slides_client_class
    ):
        from desk.commands.slides import slides

        # A slides validation error (negative index) must not suggest mail commands.
        result = runner.invoke(slides, ["add-slide", "p1", "--index", "-1", "--json"])

        assert result.exit_code == 1
        suggestions = " ".join(json.loads(result.output)["error"]["suggestions"]).lower()
        assert "desk mail search" not in suggestions
        assert "message id" not in suggestions


class TestSetTextCommand:
    def test_set_text(self, runner, mock_get_credentials, mock_slides_client_class):
        from desk.commands.slides import slides

        client = MagicMock()
        client.set_text.return_value = {"presentationId": "p1", "objectId": "sh", "status": "ok"}
        mock_slides_client_class.return_value = client

        result = runner.invoke(slides, ["set-text", "p1", "sh", "New heading", "--json"])

        assert result.exit_code == 0
        out = json.loads(result.output)
        assert out["operation"] == "set-text"
        assert out["changes"]["text_length"] == len("New heading")
        client.set_text.assert_called_once_with("p1", "sh", "New heading")

    def test_set_text_non_shape_invalid_input(self, runner, mock_get_credentials, mock_slides_client_class):
        from desk.commands.slides import slides

        client = MagicMock()
        client.set_text.side_effect = ValueError("Object tbl is not a shape. Use set-cell for tables.")
        mock_slides_client_class.return_value = client

        result = runner.invoke(slides, ["set-text", "p1", "tbl", "x", "--json"])
        assert result.exit_code == 1
        assert json.loads(result.output)["error"]["code"] == "INVALID_INPUT"


class TestSetBackgroundCommand:
    def test_set_background(self, runner, mock_get_credentials, mock_slides_client_class):
        from desk.commands.slides import slides

        client = MagicMock()
        client.set_background.return_value = {
            "presentationId": "p1", "slideObjectId": "s1", "color": "#0B5394", "status": "ok",
        }
        mock_slides_client_class.return_value = client

        result = runner.invoke(slides, ["set-background", "p1", "1", "#0B5394", "--json"])

        assert result.exit_code == 0
        out = json.loads(result.output)
        assert out["operation"] == "set-background"
        assert out["changes"]["color"] == "#0B5394"
        client.set_background.assert_called_once_with("p1", "1", "#0B5394")

    def test_set_background_bad_color(self, runner, mock_get_credentials, mock_slides_client_class):
        from desk.commands.slides import slides

        client = MagicMock()
        client.set_background.side_effect = ValueError("Invalid color: nope.")
        mock_slides_client_class.return_value = client

        result = runner.invoke(slides, ["set-background", "p1", "0", "nope", "--json"])
        assert result.exit_code == 1
        assert json.loads(result.output)["error"]["code"] == "INVALID_INPUT"


class TestScopeErrorClassification:
    def test_scope_error_maps_to_insufficient_scopes(
        self, runner, mock_get_credentials, mock_slides_client_class
    ):
        from desk.commands.slides import slides

        client = MagicMock()
        client.read.side_effect = RuntimeError(
            'Slides API error: <HttpError 403 ... "Request had insufficient '
            'authentication scopes." ... ACCESS_TOKEN_SCOPE_INSUFFICIENT>'
        )
        mock_slides_client_class.return_value = client

        result = runner.invoke(slides, ["read", "p1", "--json"])

        assert result.exit_code == 1
        output = json.loads(result.output)
        assert output["error"]["code"] == "INSUFFICIENT_SCOPES"
        # the misleading "request access from owner" advice must NOT appear
        joined = " ".join(output["error"]["suggestions"]).lower()
        assert "desk auth login" in joined
        assert "request access" not in joined


class TestStackCommand:
    def test_stack(self, runner, mock_get_credentials, mock_slides_client_class):
        from desk.commands.slides import slides

        client = MagicMock()
        client.stack_elements.return_value = {
            "presentationId": "p1", "objectIds": ["a", "b", "c"],
            "direction": "vertical", "align": "center", "gap": 12.0,
            "region": None, "status": "ok",
        }
        mock_slides_client_class.return_value = client

        result = runner.invoke(
            slides, ["stack", "p1", "a", "b", "c", "--dir", "vertical", "--align", "center", "--json"]
        )

        assert result.exit_code == 0
        out = json.loads(result.output)
        assert out["operation"] == "stack"
        assert out["changes"]["dir"] == "vertical" and out["changes"]["align"] == "center"
        client.stack_elements.assert_called_once_with(
            "p1", ["a", "b", "c"], "vertical", align="center", gap=12.0, region=None
        )

    def test_stack_requires_dir(self, runner, mock_get_credentials, mock_slides_client_class):
        from desk.commands.slides import slides

        result = runner.invoke(slides, ["stack", "p1", "a", "b"])  # no --dir
        assert result.exit_code != 0

    def test_stack_bad_align_rejected(self, runner, mock_get_credentials, mock_slides_client_class):
        from desk.commands.slides import slides

        result = runner.invoke(slides, ["stack", "p1", "a", "--dir", "vertical", "--align", "middle"])
        assert result.exit_code != 0  # click.Choice rejects


class TestGroupCommand:
    def test_group(self, runner, mock_get_credentials, mock_slides_client_class):
        from desk.commands.slides import slides

        client = MagicMock()
        client.group_elements.return_value = {
            "presentationId": "p1", "groupObjectId": "group_abc",
            "objectIds": ["a", "b", "c"], "status": "ok",
        }
        mock_slides_client_class.return_value = client

        result = runner.invoke(slides, ["group", "p1", "a", "b", "c", "--json"])

        assert result.exit_code == 0
        out = json.loads(result.output)
        assert out["operation"] == "group"
        assert out["targets"][0]["group_object_id"] == "group_abc"
        assert out["undo"]["command"] == "desk slides ungroup p1 group_abc"
        client.group_elements.assert_called_once_with("p1", ["a", "b", "c"])

    def test_group_requires_object_ids(self, runner, mock_get_credentials, mock_slides_client_class):
        from desk.commands.slides import slides

        result = runner.invoke(slides, ["group", "p1"])  # no object ids
        assert result.exit_code != 0

    def test_ungroup(self, runner, mock_get_credentials, mock_slides_client_class):
        from desk.commands.slides import slides

        client = MagicMock()
        client.ungroup_elements.return_value = {
            "presentationId": "p1", "groupObjectId": "group_abc", "status": "ok",
        }
        mock_slides_client_class.return_value = client

        result = runner.invoke(slides, ["ungroup", "p1", "group_abc", "--json"])

        assert result.exit_code == 0
        out = json.loads(result.output)
        assert out["operation"] == "ungroup"
        assert out["targets"][0]["group_object_id"] == "group_abc"
        client.ungroup_elements.assert_called_once_with("p1", "group_abc")


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
