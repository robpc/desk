"""Tests for Slides service client."""

import pytest
from unittest.mock import MagicMock, patch

from googleapiclient.errors import HttpError


def _make_client(mock_credentials):
    """Build a SlidesClient with a mocked discovery service.

    Returns (client, presentations_mock).
    """
    with patch("desk.services.slides.build") as mock_build:
        mock_service = MagicMock()
        mock_build.return_value = mock_service
        from desk.services.slides import SlidesClient

        client = SlidesClient(mock_credentials)
        presentations = mock_service.presentations.return_value
        return client, presentations


class TestSlidesClientInit:
    """Tests for SlidesClient initialization."""

    def test_creates_slides_service_on_init(self, mock_credentials):
        """Should build the slides v1 service on init."""
        with patch("desk.services.slides.build") as mock_build:
            mock_build.return_value = MagicMock()
            from desk.services.slides import SlidesClient

            SlidesClient(mock_credentials)

            assert mock_build.call_count == 1
            assert mock_build.call_args_list[0][0] == ("slides", "v1")

    def test_does_not_build_drive_eagerly(self, mock_credentials):
        """Drive client is lazy — not built until export/create needs it."""
        with patch("desk.services.slides.build") as mock_build:
            mock_build.return_value = MagicMock()
            from desk.services.slides import SlidesClient

            SlidesClient(mock_credentials)

            # Only the slides service, no drive build yet.
            assert mock_build.call_count == 1


class TestSlidesCreate:
    """Tests for SlidesClient.create."""

    def test_create_returns_presentation(self, mock_credentials):
        with patch("desk.services.slides.build") as mock_build:
            mock_service = MagicMock()
            mock_drive = MagicMock()
            # First build() → slides service, second → drive
            mock_build.side_effect = [mock_service, mock_drive]
            from desk.services.slides import SlidesClient

            client = SlidesClient(mock_credentials)
            presentations = mock_service.presentations.return_value
            presentations.create.return_value.execute.return_value = {
                "presentationId": "pres_123",
                "title": "Deck",
                "slides": [{"objectId": "s1"}],
            }
            mock_drive.files.return_value.get.return_value.execute.return_value = {
                "webViewLink": "https://docs.google.com/presentation/d/pres_123/edit",
            }

            result = client.create("Deck")

            assert result["presentationId"] == "pres_123"
            assert result["title"] == "Deck"
            assert result["slideCount"] == 1
            assert result["webViewLink"].endswith("/edit")

    def test_create_wraps_http_error(self, mock_credentials):
        client, presentations = _make_client(mock_credentials)
        presentations.create.return_value.execute.side_effect = HttpError(
            resp=MagicMock(status=400), content=b'{"error": "bad"}'
        )
        with pytest.raises(RuntimeError, match="Slides API error"):
            client.create("Deck")


class TestSlidesRead:
    """Tests for SlidesClient.read."""

    def test_read_extracts_shape_text(self, mock_credentials):
        client, presentations = _make_client(mock_credentials)
        presentations.get.return_value.execute.return_value = {
            "title": "Deck",
            "slides": [
                {
                    "objectId": "s1",
                    "pageElements": [
                        {
                            "objectId": "e1",
                            "shape": {
                                "text": {
                                    "textElements": [
                                        {"textRun": {"content": "Hello "}},
                                        {"textRun": {"content": "World\n"}},
                                    ]
                                }
                            },
                        }
                    ],
                }
            ],
        }

        result = client.read("pres_123")

        assert result["slideCount"] == 1
        assert result["slides"][0]["text"] == "Hello World"
        assert result["slides"][0]["objectId"] == "s1"

    def test_read_extracts_table_text(self, mock_credentials):
        client, presentations = _make_client(mock_credentials)
        presentations.get.return_value.execute.return_value = {
            "title": "Deck",
            "slides": [
                {
                    "objectId": "s1",
                    "pageElements": [
                        {
                            "objectId": "t1",
                            "table": {
                                "tableRows": [
                                    {
                                        "tableCells": [
                                            {"text": {"textElements": [
                                                {"textRun": {"content": "A"}}]}},
                                            {"text": {"textElements": [
                                                {"textRun": {"content": "B"}}]}},
                                        ]
                                    }
                                ]
                            },
                        }
                    ],
                }
            ],
        }

        result = client.read("pres_123")

        assert "A | B" in result["slides"][0]["text"]

    def test_read_empty_slide_has_empty_text(self, mock_credentials):
        client, presentations = _make_client(mock_credentials)
        presentations.get.return_value.execute.return_value = {
            "title": "Deck",
            "slides": [{"objectId": "s1", "pageElements": []}],
        }

        result = client.read("pres_123")

        assert result["slides"][0]["text"] == ""


class TestSlidesInspect:
    """Tests for SlidesClient.inspect."""

    def test_inspect_surfaces_placeholder_and_object_id(self, mock_credentials):
        client, presentations = _make_client(mock_credentials)
        presentations.get.return_value.execute.return_value = {
            "title": "Deck",
            "slides": [
                {
                    "objectId": "s1",
                    "pageElements": [
                        {
                            "objectId": "title_1",
                            "shape": {
                                "shapeType": "TEXT_BOX",
                                "placeholder": {"type": "TITLE"},
                                "text": {"textElements": [
                                    {"textRun": {"content": "Heading"}}]},
                            },
                        }
                    ],
                }
            ],
        }

        result = client.inspect("pres_123")

        elem = result["slides"][0]["elements"][0]
        assert elem["objectId"] == "title_1"
        assert elem["type"] == "shape"
        assert elem["placeholder"] == "TITLE"
        assert elem["text"] == "Heading"

    def test_inspect_classifies_image_and_table(self, mock_credentials):
        client, presentations = _make_client(mock_credentials)
        presentations.get.return_value.execute.return_value = {
            "title": "Deck",
            "slides": [
                {
                    "objectId": "s1",
                    "pageElements": [
                        {"objectId": "img1", "image": {}},
                        {"objectId": "tbl1", "table": {"rows": 2, "columns": 3}},
                    ],
                }
            ],
        }

        result = client.inspect("pres_123")
        types = {e["objectId"]: e["type"] for e in result["slides"][0]["elements"]}
        assert types["img1"] == "image"
        assert types["tbl1"] == "table"


class TestSlideStructure:
    """Tests for add/delete/duplicate/move slide operations."""

    def test_add_slide_returns_new_object_id(self, mock_credentials):
        client, presentations = _make_client(mock_credentials)
        presentations.batchUpdate.return_value.execute.return_value = {
            "replies": [{"createSlide": {"objectId": "new_slide"}}]
        }

        result = client.add_slide("pres_123", layout="TITLE_ONLY")

        assert result["objectId"] == "new_slide"
        assert result["layout"] == "TITLE_ONLY"
        req = presentations.batchUpdate.call_args[1]["body"]["requests"][0]
        assert req["createSlide"]["slideLayoutReference"]["predefinedLayout"] == "TITLE_ONLY"

    def test_add_slide_passes_insertion_index(self, mock_credentials):
        client, presentations = _make_client(mock_credentials)
        presentations.batchUpdate.return_value.execute.return_value = {"replies": [{}]}

        client.add_slide("pres_123", layout="BLANK", index=0)

        req = presentations.batchUpdate.call_args[1]["body"]["requests"][0]
        assert req["createSlide"]["insertionIndex"] == 0

    def test_delete_slide_by_index_resolves_object_id(self, mock_credentials):
        client, presentations = _make_client(mock_credentials)
        presentations.get.return_value.execute.return_value = {
            "slides": [{"objectId": "s0"}, {"objectId": "s1"}, {"objectId": "s2"}]
        }
        presentations.batchUpdate.return_value.execute.return_value = {}

        result = client.delete_slide("pres_123", "1")

        assert result["objectId"] == "s1"
        req = presentations.batchUpdate.call_args[1]["body"]["requests"][0]
        assert req["deleteObject"]["objectId"] == "s1"

    def test_delete_slide_by_object_id_passthrough(self, mock_credentials):
        client, presentations = _make_client(mock_credentials)
        presentations.batchUpdate.return_value.execute.return_value = {}

        result = client.delete_slide("pres_123", "abc123")

        # Non-numeric → treated as objectId, no get() lookup needed
        assert result["objectId"] == "abc123"
        presentations.get.assert_not_called()

    def test_delete_slide_index_out_of_range(self, mock_credentials):
        client, presentations = _make_client(mock_credentials)
        presentations.get.return_value.execute.return_value = {
            "slides": [{"objectId": "s0"}]
        }
        with pytest.raises(RuntimeError, match="out of range"):
            client.delete_slide("pres_123", "5")

    def test_duplicate_slide_returns_copy_id(self, mock_credentials):
        client, presentations = _make_client(mock_credentials)
        presentations.batchUpdate.return_value.execute.return_value = {
            "replies": [{"duplicateObject": {"objectId": "copy_1"}}]
        }

        result = client.duplicate_slide("pres_123", "orig")

        assert result["objectId"] == "copy_1"
        assert result["sourceObjectId"] == "orig"

    def test_move_slide_sends_position_request(self, mock_credentials):
        client, presentations = _make_client(mock_credentials)
        presentations.batchUpdate.return_value.execute.return_value = {}

        client.move_slide("pres_123", "slideX", 0)

        req = presentations.batchUpdate.call_args[1]["body"]["requests"][0]
        assert req["updateSlidesPosition"]["slideObjectIds"] == ["slideX"]
        assert req["updateSlidesPosition"]["insertionIndex"] == 0


class TestSlidesText:
    """Tests for insert/replace text operations."""

    def test_insert_text_sends_request(self, mock_credentials):
        client, presentations = _make_client(mock_credentials)
        presentations.batchUpdate.return_value.execute.return_value = {}

        client.insert_text("pres_123", "shape_1", "Hi", index=3)

        req = presentations.batchUpdate.call_args[1]["body"]["requests"][0]
        assert req["insertText"]["objectId"] == "shape_1"
        assert req["insertText"]["text"] == "Hi"
        assert req["insertText"]["insertionIndex"] == 3

    def test_replace_text_returns_occurrences(self, mock_credentials):
        client, presentations = _make_client(mock_credentials)
        presentations.batchUpdate.return_value.execute.return_value = {
            "replies": [{"replaceAllText": {"occurrencesChanged": 4}}]
        }

        result = client.replace_text("pres_123", "old", "new", match_case=False)

        assert result["occurrences_changed"] == 4
        req = presentations.batchUpdate.call_args[1]["body"]["requests"][0]
        assert req["replaceAllText"]["containsText"]["text"] == "old"
        assert req["replaceAllText"]["containsText"]["matchCase"] is False
        assert req["replaceAllText"]["replaceText"] == "new"


class TestSlidesExport:
    """Tests for SlidesClient.export."""

    def test_export_unsupported_format(self, mock_credentials):
        client, _ = _make_client(mock_credentials)
        with pytest.raises(RuntimeError, match="Unsupported format"):
            client.export("pres_123", fmt="key")

    def test_export_pdf_uses_drive(self, mock_credentials):
        with patch("desk.services.slides.build") as mock_build:
            mock_service = MagicMock()
            mock_drive = MagicMock()
            mock_build.side_effect = [mock_service, mock_drive]
            from desk.services.slides import SlidesClient

            client = SlidesClient(mock_credentials)
            mock_drive.files.return_value.export.return_value.execute.return_value = b"PDF"

            content = client.export("pres_123", fmt="pdf")

            assert content == b"PDF"
            kwargs = mock_drive.files.return_value.export.call_args[1]
            assert kwargs["mimeType"] == "application/pdf"
            assert kwargs["fileId"] == "pres_123"
