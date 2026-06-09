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


class TestInspectBoundingBoxes:
    """Tests for inspect bounding boxes + flags (ADR-030, Idea 064)."""

    def _pres(self, presentations, elements, page=(720, 405)):
        presentations.get.return_value.execute.return_value = {
            "title": "Deck",
            "pageSize": {"width": {"magnitude": page[0], "unit": "PT"},
                         "height": {"magnitude": page[1], "unit": "PT"}},
            "slides": [{"objectId": "s0", "pageElements": elements}],
        }

    @staticmethod
    def _shape(oid, x, y, w, h, unit="PT", sx=1, sy=1):
        return {
            "objectId": oid,
            "shape": {},
            "size": {"width": {"magnitude": w, "unit": unit},
                     "height": {"magnitude": h, "unit": unit}},
            "transform": {"scaleX": sx, "scaleY": sy,
                          "translateX": x, "translateY": y, "unit": unit},
        }

    def test_box_from_size_and_translate(self, mock_credentials):
        client, presentations = _make_client(mock_credentials)
        self._pres(presentations, [self._shape("a", 50, 60, 200, 100)])

        elem = client.inspect("p1")["slides"][0]["elements"][0]

        assert elem["box"] == {"x": 50, "y": 60, "width": 200, "height": 100}
        assert elem["offSlide"] is False
        assert elem["overlaps"] == []

    def test_box_applies_scale(self, mock_credentials):
        client, presentations = _make_client(mock_credentials)
        self._pres(presentations, [self._shape("a", 0, 0, 100, 50, sx=2, sy=3)])

        box = client.inspect("p1")["slides"][0]["elements"][0]["box"]
        assert box["width"] == 200 and box["height"] == 150

    def test_emu_translate_converted_to_points(self, mock_credentials):
        client, presentations = _make_client(mock_credentials)
        # 914400 EMU = 72 pt; size in EMU too
        self._pres(presentations, [self._shape("a", 914400, 0, 914400, 914400, unit="EMU")])

        box = client.inspect("p1")["slides"][0]["elements"][0]["box"]
        assert box["x"] == 72.0 and box["width"] == 72.0

    def test_off_slide_flagged(self, mock_credentials):
        client, presentations = _make_client(mock_credentials)
        # box runs past the 720x405 slide
        self._pres(presentations, [self._shape("a", 700, 0, 200, 50)])

        elem = client.inspect("p1")["slides"][0]["elements"][0]
        assert elem["offSlide"] is True

    def test_overlap_detected_both_ways(self, mock_credentials):
        client, presentations = _make_client(mock_credentials)
        self._pres(presentations, [
            self._shape("a", 0, 0, 100, 100),
            self._shape("b", 50, 50, 100, 100),   # overlaps a
            self._shape("c", 500, 300, 50, 50),   # disjoint
        ])

        els = {e["objectId"]: e for e in client.inspect("p1")["slides"][0]["elements"]}
        assert els["a"]["overlaps"] == ["b"]
        assert els["b"]["overlaps"] == ["a"]
        assert els["c"]["overlaps"] == []

    def test_edge_touch_is_not_overlap(self, mock_credentials):
        client, presentations = _make_client(mock_credentials)
        self._pres(presentations, [
            self._shape("a", 0, 0, 100, 100),
            self._shape("b", 100, 0, 100, 100),  # shares the x=100 edge
        ])
        els = {e["objectId"]: e for e in client.inspect("p1")["slides"][0]["elements"]}
        assert els["a"]["overlaps"] == []

    def test_element_without_size_has_null_box(self, mock_credentials):
        client, presentations = _make_client(mock_credentials)
        self._pres(presentations, [{"objectId": "a", "shape": {}}])  # no size/transform

        elem = client.inspect("p1")["slides"][0]["elements"][0]
        assert elem["box"] is None
        assert "offSlide" not in elem

    def test_pagesize_reported(self, mock_credentials):
        client, presentations = _make_client(mock_credentials)
        self._pres(presentations, [])
        assert client.inspect("p1")["pageSize"] == {"width": 720, "height": 405}


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


class TestVisualElements:
    """Tests for insert-image / insert-table / insert-shape (Phase 2)."""

    def test_insert_image_builds_pt_properties(self, mock_credentials):
        client, presentations = _make_client(mock_credentials)
        presentations.get.return_value.execute.return_value = {
            "slides": [{"objectId": "s0"}]
        }
        presentations.batchUpdate.return_value.execute.return_value = {
            "replies": [{"createImage": {"objectId": "img1"}}]
        }

        result = client.insert_image("p1", "0", "https://x/y.png", x=100, y=80, width=200)

        assert result["objectId"] == "img1"
        assert result["slideObjectId"] == "s0"
        req = presentations.batchUpdate.call_args[1]["body"]["requests"][0]["createImage"]
        assert req["url"] == "https://x/y.png"
        props = req["elementProperties"]
        assert props["pageObjectId"] == "s0"
        assert props["transform"]["translateX"] == 100
        assert props["transform"]["unit"] == "PT"
        assert props["size"]["width"]["magnitude"] == 200
        # height defaulted
        assert props["size"]["height"]["magnitude"] == 200.0

    def test_insert_table_omits_size_when_unspecified(self, mock_credentials):
        client, presentations = _make_client(mock_credentials)
        presentations.batchUpdate.return_value.execute.return_value = {
            "replies": [{"createTable": {"objectId": "tbl1"}}]
        }

        result = client.insert_table("p1", "objId", 3, 4)

        assert result["objectId"].startswith("table_")  # client-supplied id
        req = presentations.batchUpdate.call_args[1]["body"]["requests"][0]["createTable"]
        assert req["rows"] == 3
        assert req["columns"] == 4
        # No position/size given → elementProperties is just the page reference
        assert req["elementProperties"] == {"pageObjectId": "objId"}

    def test_insert_table_with_data_fills_cells(self, mock_credentials):
        client, presentations = _make_client(mock_credentials)
        presentations.batchUpdate.return_value.execute.return_value = {}

        result = client.insert_table("p1", "s0", data=[["Q", "Rev"], ["Q1", ""]])

        assert result["filled_cells"] == 3  # empty cell skipped
        reqs = presentations.batchUpdate.call_args[1]["body"]["requests"]
        create = reqs[0]["createTable"]
        assert create["rows"] == 2 and create["columns"] == 2
        # all fills target the same client-supplied table id via cellLocation
        tid = create["objectId"]
        fills = [r["insertText"] for r in reqs[1:]]
        assert all(f["objectId"] == tid for f in fills)
        assert {(*f["cellLocation"].values(),): f["text"] for f in fills} == {
            (0, 0): "Q", (0, 1): "Rev", (1, 0): "Q1",
        }

    def test_insert_table_data_dim_mismatch_raises(self, mock_credentials):
        client, _ = _make_client(mock_credentials)
        with pytest.raises(ValueError, match="!= data"):
            client.insert_table("p1", "s0", rows=5, data=[["a"]])

    def test_insert_table_includes_size_when_given(self, mock_credentials):
        client, presentations = _make_client(mock_credentials)
        presentations.batchUpdate.return_value.execute.return_value = {"replies": [{}]}

        client.insert_table("p1", "objId", 2, 2, x=50)

        req = presentations.batchUpdate.call_args[1]["body"]["requests"][0]["createTable"]
        assert "size" in req["elementProperties"]
        assert req["elementProperties"]["transform"]["translateX"] == 50

    def test_insert_shape_default_textbox(self, mock_credentials):
        client, presentations = _make_client(mock_credentials)
        presentations.batchUpdate.return_value.execute.return_value = {"replies": [{}]}

        result = client.insert_shape("p1", "objId")

        req = presentations.batchUpdate.call_args[1]["body"]["requests"]
        assert len(req) == 1  # no text → only createShape
        assert req[0]["createShape"]["shapeType"] == "TEXT_BOX"
        # objectId returned matches the one sent
        assert result["objectId"] == req[0]["createShape"]["objectId"]

    def test_insert_shape_with_text_chains_insert(self, mock_credentials):
        client, presentations = _make_client(mock_credentials)
        presentations.batchUpdate.return_value.execute.return_value = {"replies": [{}, {}]}

        result = client.insert_shape("p1", "objId", shape_type="RECTANGLE", text="Hi")

        reqs = presentations.batchUpdate.call_args[1]["body"]["requests"]
        assert len(reqs) == 2
        assert reqs[0]["createShape"]["shapeType"] == "RECTANGLE"
        assert reqs[1]["insertText"]["text"] == "Hi"
        # Both requests target the same generated objectId
        assert reqs[0]["createShape"]["objectId"] == reqs[1]["insertText"]["objectId"]
        assert result["objectId"] == reqs[0]["createShape"]["objectId"]


class TestParseColor:
    """Tests for _parse_color (Phase 3a)."""

    def test_hex_six(self):
        from desk.services.slides import _parse_color

        c = _parse_color("#1A73E8")
        rgb = c["rgbColor"]
        assert abs(rgb["red"] - 26 / 255) < 1e-6
        assert abs(rgb["green"] - 115 / 255) < 1e-6
        assert abs(rgb["blue"] - 232 / 255) < 1e-6

    def test_hex_three_expands(self):
        from desk.services.slides import _parse_color

        assert _parse_color("#fff") == _parse_color("#ffffff")

    def test_theme_name(self):
        from desk.services.slides import _parse_color

        assert _parse_color("accent1") == {"themeColor": "ACCENT1"}

    def test_invalid_color_raises(self):
        from desk.services.slides import _parse_color

        with pytest.raises(ValueError, match="Invalid color"):
            _parse_color("chartreuse")

    def test_invalid_hex_raises(self):
        from desk.services.slides import _parse_color

        with pytest.raises(ValueError, match="Invalid hex"):
            _parse_color("#12")


class TestRegionBox:
    """Tests for _region_box geometry (Phase 3a)."""

    def test_full_is_inside_margins(self):
        from desk.services.slides import _region_box

        x, y, w, h = _region_box(720, 405, "full")
        assert x == 24 and y == 24
        assert w == 720 - 48 and h == 405 - 48

    def test_right_half_is_right_of_center(self):
        from desk.services.slides import _region_box

        lx, _, lw, _ = _region_box(720, 405, "left-half")
        rx, _, rw, _ = _region_box(720, 405, "right-half")
        assert rx > lx + lw  # right half starts past the left half + gutter
        assert abs(lw - rw) < 1e-9

    def test_grid_cells_distinct(self):
        from desk.services.slides import _region_box

        tl = _region_box(720, 405, "top-left")
        br = _region_box(720, 405, "bottom-right")
        assert br[0] > tl[0] and br[1] > tl[1]

    def test_unknown_region_raises(self):
        from desk.services.slides import _region_box

        with pytest.raises(ValueError, match="Unknown region"):
            _region_box(720, 405, "middle-ish")


class TestRicherRegionsAndGridCells:
    """Tests for thirds regions and _grid_cells (Phase 3b, ADR-029)."""

    def test_column_thirds_span_full_height(self):
        from desk.services.slides import _region_box

        x, y, w, h = _region_box(720, 405, "center-third")
        assert abs(h - (405 - 48)) < 1e-9
        assert x > 24

    def test_row_thirds_span_full_width(self):
        from desk.services.slides import _region_box

        x, y, w, h = _region_box(720, 405, "bottom-third")
        assert abs(w - (720 - 48)) < 1e-9
        assert y > 24

    def test_grid_cells_columns_count_and_order(self):
        from desk.services.slides import _grid_cells

        cells = _grid_cells((0, 0, 300, 100), 3, "columns")
        assert len(cells) == 3
        assert cells[0][0] < cells[1][0] < cells[2][0]
        assert cells[0][1] == cells[1][1] == cells[2][1]

    def test_grid_cells_grid_is_near_square(self):
        from desk.services.slides import _grid_cells

        cells = _grid_cells((0, 0, 300, 300), 4, "grid")
        assert len(cells) == 4
        assert cells[0][1] == cells[1][1]
        assert cells[2][1] > cells[0][1]

    def test_grid_cells_unknown_mode_raises(self):
        from desk.services.slides import _grid_cells

        with pytest.raises(ValueError, match="Unknown arrange mode"):
            _grid_cells((0, 0, 10, 10), 2, "spiral")


class TestArrangeElements:
    """Tests for SlidesClient.arrange_elements (Phase 3b, ADR-029)."""

    def _pres(self, presentations, elements):
        presentations.get.return_value.execute.return_value = {
            "pageSize": {"width": {"magnitude": 720, "unit": "PT"},
                         "height": {"magnitude": 405, "unit": "PT"}},
            "slides": [{"objectId": "s0", "pageElements": elements}],
        }

    def test_arrange_columns_emits_one_request_each(self, mock_credentials):
        client, presentations = _make_client(mock_credentials)
        els = [
            {"objectId": "a", "size": {"width": {"magnitude": 100, "unit": "PT"},
                                       "height": {"magnitude": 50, "unit": "PT"}}},
            {"objectId": "b", "size": {"width": {"magnitude": 100, "unit": "PT"},
                                       "height": {"magnitude": 50, "unit": "PT"}}},
        ]
        self._pres(presentations, els)
        presentations.batchUpdate.return_value.execute.return_value = {}

        client.arrange_elements("p1", ["a", "b"], "columns")

        reqs = presentations.batchUpdate.call_args[1]["body"]["requests"]
        assert len(reqs) == 2
        ax = reqs[0]["updatePageElementTransform"]["transform"]["translateX"]
        bx = reqs[1]["updatePageElementTransform"]["transform"]["translateX"]
        assert bx > ax
        assert all(r["updatePageElementTransform"]["applyMode"] == "ABSOLUTE" for r in reqs)

    def test_arrange_missing_object_raises(self, mock_credentials):
        client, presentations = _make_client(mock_credentials)
        self._pres(presentations, [{"objectId": "a", "size": {
            "width": {"magnitude": 100, "unit": "PT"},
            "height": {"magnitude": 50, "unit": "PT"}}}])

        with pytest.raises(RuntimeError, match="Object not found"):
            client.arrange_elements("p1", ["a", "ghost"], "columns")

    def test_arrange_empty_raises(self, mock_credentials):
        client, _ = _make_client(mock_credentials)
        with pytest.raises(ValueError, match="at least one"):
            client.arrange_elements("p1", [], "columns")

    def test_arrange_region_confines_area(self, mock_credentials):
        client, presentations = _make_client(mock_credentials)
        els = [{"objectId": "a", "size": {"width": {"magnitude": 100, "unit": "PT"},
                                          "height": {"magnitude": 50, "unit": "PT"}}}]
        self._pres(presentations, els)
        presentations.batchUpdate.return_value.execute.return_value = {}

        client.arrange_elements("p1", ["a"], "columns", region="right-half")

        tx = presentations.batchUpdate.call_args[1]["body"]["requests"][0][
            "updatePageElementTransform"]["transform"]["translateX"]
        assert tx > 360


class TestStyleText:
    """Tests for SlidesClient.style_text (Phase 3a)."""

    def test_style_whole_text_default_range(self, mock_credentials):
        client, presentations = _make_client(mock_credentials)
        presentations.batchUpdate.return_value.execute.return_value = {}

        client.style_text("p1", "sh", bold=True, font_size=24)

        req = presentations.batchUpdate.call_args[1]["body"]["requests"][0]["updateTextStyle"]
        assert req["objectId"] == "sh"
        assert req["textRange"] == {"type": "ALL"}
        assert req["style"]["bold"] is True
        assert req["style"]["fontSize"]["magnitude"] == 24
        assert "bold" in req["fields"] and "fontSize" in req["fields"]

    def test_style_color_and_range(self, mock_credentials):
        client, presentations = _make_client(mock_credentials)
        presentations.batchUpdate.return_value.execute.return_value = {}

        client.style_text("p1", "sh", color="#FF0000", start=0, end=5)

        req = presentations.batchUpdate.call_args[1]["body"]["requests"][0]["updateTextStyle"]
        assert req["textRange"] == {"type": "FIXED_RANGE", "startIndex": 0, "endIndex": 5}
        rgb = req["style"]["foregroundColor"]["opaqueColor"]["rgbColor"]
        assert rgb["red"] == 1.0

    def test_style_no_fields_is_noop(self, mock_credentials):
        client, presentations = _make_client(mock_credentials)

        result = client.style_text("p1", "sh")

        assert result["status"] == "ok"
        presentations.batchUpdate.assert_not_called()


class TestFormatElement:
    """Tests for SlidesClient.format_element (Phase 3a)."""

    def _pres_with_element(self, presentations, element):
        presentations.get.return_value.execute.return_value = {
            "slides": [{"objectId": "s0", "pageElements": [element]}]
        }

    def test_format_shape_fill_and_outline(self, mock_credentials):
        client, presentations = _make_client(mock_credentials)
        self._pres_with_element(presentations, {"objectId": "sh", "shape": {}})
        presentations.batchUpdate.return_value.execute.return_value = {}

        result = client.format_element("p1", "sh", fill="#FFFFFF", outline="ACCENT1", outline_weight=2)

        assert result["elementType"] == "shape"
        req = presentations.batchUpdate.call_args[1]["body"]["requests"][0]["updateShapeProperties"]
        props = req["shapeProperties"]
        # SolidFill.color is an OpaqueColor directly — NOT wrapped in opaqueColor.
        fill_color = props["shapeBackgroundFill"]["solidFill"]["color"]
        assert "rgbColor" in fill_color and "opaqueColor" not in fill_color
        outline_color = props["outline"]["outlineFill"]["solidFill"]["color"]
        assert outline_color == {"themeColor": "ACCENT1"}
        assert props["outline"]["weight"]["magnitude"] == 2

    def test_format_image_rejects_fill(self, mock_credentials):
        client, presentations = _make_client(mock_credentials)
        self._pres_with_element(presentations, {"objectId": "img", "image": {}})

        with pytest.raises(ValueError, match="no fill"):
            client.format_element("p1", "img", fill="#FFFFFF")

    def test_format_image_outline(self, mock_credentials):
        client, presentations = _make_client(mock_credentials)
        self._pres_with_element(presentations, {"objectId": "img", "image": {}})
        presentations.batchUpdate.return_value.execute.return_value = {}

        result = client.format_element("p1", "img", outline="#000000")

        assert result["elementType"] == "image"
        req = presentations.batchUpdate.call_args[1]["body"]["requests"][0]
        assert "updateImageProperties" in req

    def test_format_missing_object_raises(self, mock_credentials):
        client, presentations = _make_client(mock_credentials)
        presentations.get.return_value.execute.return_value = {"slides": []}

        with pytest.raises(RuntimeError, match="Object not found"):
            client.format_element("p1", "nope", fill="#FFFFFF")


class TestPlaceElement:
    """Tests for SlidesClient.place_element (Phase 3a)."""

    def test_place_computes_absolute_transform(self, mock_credentials):
        client, presentations = _make_client(mock_credentials)
        # First get() (find element) and second get() (page size) both return this.
        presentations.get.return_value.execute.return_value = {
            "pageSize": {
                "width": {"magnitude": 720, "unit": "PT"},
                "height": {"magnitude": 405, "unit": "PT"},
            },
            "slides": [{
                "objectId": "s0",
                "pageElements": [{
                    "objectId": "el",
                    "size": {
                        "width": {"magnitude": 100, "unit": "PT"},
                        "height": {"magnitude": 50, "unit": "PT"},
                    },
                }],
            }],
        }
        presentations.batchUpdate.return_value.execute.return_value = {}

        client.place_element("p1", "el", "full")

        req = presentations.batchUpdate.call_args[1]["body"]["requests"][0]
        t = req["updatePageElementTransform"]
        assert t["applyMode"] == "ABSOLUTE"
        # full box is 672x357 pt; base is 100x50 → scale 6.72 x 7.14
        assert abs(t["transform"]["scaleX"] - (672 / 100)) < 1e-6
        assert abs(t["transform"]["scaleY"] - (357 / 50)) < 1e-6
        assert t["transform"]["translateX"] == 24

    def test_place_table_uses_translate_only(self, mock_credentials):
        client, presentations = _make_client(mock_credentials)
        # Tables reject scaled transforms → place moves them at scale 1.
        presentations.get.return_value.execute.return_value = {
            "pageSize": {"width": {"magnitude": 720, "unit": "PT"},
                         "height": {"magnitude": 405, "unit": "PT"}},
            "slides": [{"objectId": "s0", "pageElements": [{
                "objectId": "tbl", "table": {"tableRows": []},
                "size": {"width": {"magnitude": 100, "unit": "PT"},
                         "height": {"magnitude": 50, "unit": "PT"}},
            }]}],
        }
        presentations.batchUpdate.return_value.execute.return_value = {}

        client.place_element("p1", "tbl", "bottom-half")

        t = presentations.batchUpdate.call_args[1]["body"]["requests"][0][
            "updatePageElementTransform"]["transform"]
        assert t["scaleX"] == 1 and t["scaleY"] == 1  # moved, not resized

    def test_place_without_size_raises(self, mock_credentials):
        client, presentations = _make_client(mock_credentials)
        presentations.get.return_value.execute.return_value = {
            "pageSize": {"width": {"magnitude": 720, "unit": "PT"},
                         "height": {"magnitude": 405, "unit": "PT"}},
            "slides": [{"objectId": "s0", "pageElements": [{"objectId": "el"}]}],
        }

        with pytest.raises(RuntimeError, match="no resolvable size"):
            client.place_element("p1", "el", "center")


class TestInsertWithRegion:
    """Region overrides explicit coordinates on insert (Phase 3a)."""

    def test_insert_shape_region_sets_box(self, mock_credentials):
        client, presentations = _make_client(mock_credentials)
        presentations.get.return_value.execute.return_value = {
            "pageSize": {"width": {"magnitude": 720, "unit": "PT"},
                         "height": {"magnitude": 405, "unit": "PT"}},
            "slides": [{"objectId": "s0"}],
        }
        presentations.batchUpdate.return_value.execute.return_value = {"replies": [{}]}

        client.insert_shape("p1", "s0", region="full")

        req = presentations.batchUpdate.call_args[1]["body"]["requests"][0]["createShape"]
        size = req["elementProperties"]["size"]
        # full width 672pt, height 357pt
        assert abs(size["width"]["magnitude"] - 672) < 1e-6
        assert abs(size["height"]["magnitude"] - 357) < 1e-6


class TestSetNotes:
    """Tests for SlidesClient.set_notes (ADR-030, Idea 059)."""

    def _page_with_notes(self, presentations, notes_text="", notes_id="notes_1"):
        elements = []
        if notes_text is not None:
            elements = [{
                "objectId": notes_id,
                "shape": {"text": {"textElements": [
                    {"textRun": {"content": notes_text}}]}},
            }]
        presentations.pages.return_value.get.return_value.execute.return_value = {
            "objectId": "s0",
            "slideProperties": {"notesPage": {
                "notesProperties": {"speakerNotesObjectId": notes_id},
                "pageElements": elements,
            }},
        }

    def test_set_notes_replace_clears_then_inserts(self, mock_credentials):
        client, presentations = _make_client(mock_credentials)
        self._page_with_notes(presentations, notes_text="old notes\n")
        presentations.batchUpdate.return_value.execute.return_value = {}

        result = client.set_notes("p1", "s0", "new notes", mode="replace")

        assert result["notesObjectId"] == "notes_1"
        reqs = presentations.batchUpdate.call_args[1]["body"]["requests"]
        assert reqs[0]["deleteText"]["objectId"] == "notes_1"
        assert reqs[1]["insertText"]["text"] == "new notes"
        assert reqs[1]["insertText"]["insertionIndex"] == 0

    def test_set_notes_replace_skips_delete_when_empty(self, mock_credentials):
        client, presentations = _make_client(mock_credentials)
        self._page_with_notes(presentations, notes_text="\n")  # just trailing newline
        presentations.batchUpdate.return_value.execute.return_value = {}

        client.set_notes("p1", "s0", "hi", mode="replace")

        reqs = presentations.batchUpdate.call_args[1]["body"]["requests"]
        assert len(reqs) == 1
        assert "insertText" in reqs[0]

    def test_set_notes_append_inserts_before_trailing_newline(self, mock_credentials):
        client, presentations = _make_client(mock_credentials)
        self._page_with_notes(presentations, notes_text="line one\n")  # len 9
        presentations.batchUpdate.return_value.execute.return_value = {}

        client.set_notes("p1", "s0", " more", mode="append")

        req = presentations.batchUpdate.call_args[1]["body"]["requests"][0]
        assert req["insertText"]["insertionIndex"] == 8  # len-1

    def test_set_notes_no_notes_shape_raises(self, mock_credentials):
        client, presentations = _make_client(mock_credentials)
        presentations.pages.return_value.get.return_value.execute.return_value = {
            "objectId": "s0",
            "slideProperties": {"notesPage": {"notesProperties": {}}},
        }
        with pytest.raises(RuntimeError, match="no speaker-notes"):
            client.set_notes("p1", "s0", "x")


class TestReadIncludesNotes:
    def test_read_surfaces_notes(self, mock_credentials):
        client, presentations = _make_client(mock_credentials)
        presentations.get.return_value.execute.return_value = {
            "title": "Deck",
            "slides": [{
                "objectId": "s0",
                "pageElements": [],
                "slideProperties": {"notesPage": {
                    "notesProperties": {"speakerNotesObjectId": "n1"},
                    "pageElements": [{
                        "objectId": "n1",
                        "shape": {"text": {"textElements": [
                            {"textRun": {"content": "talk track\n"}}]}},
                    }],
                }},
            }],
        }

        result = client.read("p1")

        assert result["slides"][0]["notes"] == "talk track"


class TestAddSlidePlaceholders:
    def test_add_slide_returns_placeholders(self, mock_credentials):
        client, presentations = _make_client(mock_credentials)
        presentations.batchUpdate.return_value.execute.return_value = {
            "replies": [{"createSlide": {"objectId": "new"}}]
        }
        presentations.pages.return_value.get.return_value.execute.return_value = {
            "pageElements": [
                {"objectId": "t1", "shape": {"placeholder": {"type": "TITLE", "index": 0}}},
                {"objectId": "b1", "shape": {"placeholder": {"type": "BODY"}}},
                {"objectId": "x1", "shape": {}},  # non-placeholder shape ignored
            ]
        }

        result = client.add_slide("p1", layout="TITLE_AND_BODY")

        ph = result["placeholders"]
        assert {"type": "TITLE", "objectId": "t1", "index": 0} in ph
        assert {"type": "BODY", "objectId": "b1"} in ph
        assert len(ph) == 2


class TestAddSlideInlineFill:
    """Tests for add-slide inline placeholder fills (ADR-030, Idea 061b)."""

    def _setup(self, presentations, placeholder_types):
        presentations.batchUpdate.return_value.execute.return_value = {
            "replies": [{"createSlide": {"objectId": "new"}}]
        }
        presentations.pages.return_value.get.return_value.execute.return_value = {
            "pageElements": [
                {"objectId": f"ph_{t}", "shape": {"placeholder": {"type": t}}}
                for t in placeholder_types
            ]
        }

    def test_fills_title_and_body_in_one_call(self, mock_credentials):
        client, presentations = _make_client(mock_credentials)
        self._setup(presentations, ["TITLE", "BODY"])

        result = client.add_slide("p1", layout="TITLE_AND_BODY", title="T", body="B")

        # createSlide batch, then a fill batch
        assert presentations.batchUpdate.call_count == 2
        fill_reqs = presentations.batchUpdate.call_args_list[1][1]["body"]["requests"]
        targets = {r["insertText"]["objectId"]: r["insertText"]["text"] for r in fill_reqs}
        assert targets == {"ph_TITLE": "T", "ph_BODY": "B"}
        assert {"field": "title", "objectId": "ph_TITLE"} in result["filled"]

    def test_title_matches_centered_title(self, mock_credentials):
        client, presentations = _make_client(mock_credentials)
        self._setup(presentations, ["CENTERED_TITLE", "SUBTITLE"])

        client.add_slide("p1", layout="TITLE", title="Hi")

        fill_reqs = presentations.batchUpdate.call_args_list[1][1]["body"]["requests"]
        assert fill_reqs[0]["insertText"]["objectId"] == "ph_CENTERED_TITLE"

    def test_missing_placeholder_rolls_back_slide(self, mock_credentials):
        client, presentations = _make_client(mock_credentials)
        self._setup(presentations, ["TITLE"])  # no BODY

        with pytest.raises(ValueError, match="--body: layout .* no matching placeholder"):
            client.add_slide("p1", layout="TITLE_ONLY", title="T", body="B")

        # createSlide, then a deleteObject rollback — and no insertText fill.
        assert presentations.batchUpdate.call_count == 2
        batches = [c[1]["body"]["requests"] for c in presentations.batchUpdate.call_args_list]
        assert "createSlide" in batches[0][0]
        assert batches[1][0]["deleteObject"]["objectId"] == "new"
        assert not any("insertText" in r for b in batches for r in b)

    def test_no_fills_no_second_batch(self, mock_credentials):
        client, presentations = _make_client(mock_credentials)
        self._setup(presentations, ["TITLE", "BODY"])

        result = client.add_slide("p1", layout="TITLE_AND_BODY")

        assert presentations.batchUpdate.call_count == 1
        assert result["filled"] == []


class TestGetTheme:
    """Tests for SlidesClient.get_theme (Idea 069)."""

    def test_reads_master_color_scheme(self, mock_credentials):
        client, presentations = _make_client(mock_credentials)
        presentations.get.return_value.execute.return_value = {
            "masters": [{"pageProperties": {"colorScheme": {"colors": [
                {"type": "ACCENT1", "color": {"red": 1.0, "green": 0.0, "blue": 0.0}},
                {"type": "DARK1", "color": {"red": 0.0, "green": 0.0, "blue": 0.0}},
            ]}}}],
        }

        theme = client.get_theme("p1")["theme"]
        by_name = {c["name"]: c["hex"] for c in theme}
        assert by_name["ACCENT1"] == "#FF0000"
        assert by_name["DARK1"] == "#000000"

    def test_empty_when_no_scheme(self, mock_credentials):
        client, presentations = _make_client(mock_credentials)
        presentations.get.return_value.execute.return_value = {"masters": []}
        assert client.get_theme("p1")["theme"] == []


class TestStyleAlignmentAndValign:
    """Tests for paragraph alignment (style) and content alignment (format) — Idea 071."""

    def test_alignment_adds_paragraph_request(self, mock_credentials):
        client, presentations = _make_client(mock_credentials)
        presentations.batchUpdate.return_value.execute.return_value = {}

        client.style_text("p1", "sh", bold=True, alignment="CENTER")

        reqs = presentations.batchUpdate.call_args[1]["body"]["requests"]
        kinds = [list(r.keys())[0] for r in reqs]
        assert "updateTextStyle" in kinds and "updateParagraphStyle" in kinds
        para = next(r["updateParagraphStyle"] for r in reqs if "updateParagraphStyle" in r)
        assert para["style"]["alignment"] == "CENTER"

    def test_alignment_only_no_text_style(self, mock_credentials):
        client, presentations = _make_client(mock_credentials)
        presentations.batchUpdate.return_value.execute.return_value = {}

        client.style_text("p1", "sh", alignment="END")

        reqs = presentations.batchUpdate.call_args[1]["body"]["requests"]
        assert [list(r.keys())[0] for r in reqs] == ["updateParagraphStyle"]

    def test_valign_on_shape(self, mock_credentials):
        client, presentations = _make_client(mock_credentials)
        presentations.get.return_value.execute.return_value = {
            "slides": [{"objectId": "s0", "pageElements": [{"objectId": "sh", "shape": {}}]}]
        }
        presentations.batchUpdate.return_value.execute.return_value = {}

        client.format_element("p1", "sh", valign="MIDDLE")

        req = presentations.batchUpdate.call_args[1]["body"]["requests"][0]["updateShapeProperties"]
        assert req["shapeProperties"]["contentAlignment"] == "MIDDLE"
        assert "contentAlignment" in req["fields"]

    def test_valign_on_image_raises(self, mock_credentials):
        client, presentations = _make_client(mock_credentials)
        presentations.get.return_value.execute.return_value = {
            "slides": [{"objectId": "s0", "pageElements": [{"objectId": "img", "image": {}}]}]
        }
        with pytest.raises(ValueError, match="content alignment"):
            client.format_element("p1", "img", valign="TOP")


class TestSetCell:
    """Tests for SlidesClient.set_cell (ADR-030, Idea 066)."""

    def _table(self, presentations, cell_text=""):
        presentations.get.return_value.execute.return_value = {
            "slides": [{"objectId": "s0", "pageElements": [{
                "objectId": "tbl",
                "table": {"tableRows": [
                    {"tableCells": [
                        {"text": {"textElements": [{"textRun": {"content": cell_text}}]}},
                        {"text": {}},
                    ]},
                    {"tableCells": [{"text": {}}, {"text": {}}]},
                ]},
            }]}],
        }

    def test_set_cell_replace_uses_cell_location(self, mock_credentials):
        client, presentations = _make_client(mock_credentials)
        self._table(presentations, cell_text="old\n")
        presentations.batchUpdate.return_value.execute.return_value = {}

        result = client.set_cell("p1", "tbl", 0, 0, "new")

        assert result["row"] == 0 and result["col"] == 0
        reqs = presentations.batchUpdate.call_args[1]["body"]["requests"]
        assert reqs[0]["deleteText"]["cellLocation"] == {"rowIndex": 0, "columnIndex": 0}
        assert reqs[1]["insertText"]["cellLocation"] == {"rowIndex": 0, "columnIndex": 0}
        assert reqs[1]["insertText"]["objectId"] == "tbl"
        assert reqs[1]["insertText"]["text"] == "new"

    def test_set_cell_replace_empty_skips_delete(self, mock_credentials):
        client, presentations = _make_client(mock_credentials)
        self._table(presentations, cell_text="")
        presentations.batchUpdate.return_value.execute.return_value = {}

        client.set_cell("p1", "tbl", 1, 1, "x")

        reqs = presentations.batchUpdate.call_args[1]["body"]["requests"]
        assert len(reqs) == 1 and "insertText" in reqs[0]

    def test_set_cell_out_of_range_raises(self, mock_credentials):
        client, presentations = _make_client(mock_credentials)
        self._table(presentations)
        with pytest.raises(ValueError, match="out of range"):
            client.set_cell("p1", "tbl", 5, 0, "x")

    def test_set_cell_non_table_raises(self, mock_credentials):
        client, presentations = _make_client(mock_credentials)
        presentations.get.return_value.execute.return_value = {
            "slides": [{"objectId": "s0", "pageElements": [{"objectId": "sh", "shape": {}}]}]
        }
        with pytest.raises(ValueError, match="not a table"):
            client.set_cell("p1", "sh", 0, 0, "x")


class TestSetText:
    """Tests for SlidesClient.set_text (Idea 072)."""

    def _shape(self, presentations, text=""):
        presentations.get.return_value.execute.return_value = {
            "slides": [{"objectId": "s0", "pageElements": [{
                "objectId": "sh",
                "shape": {"text": {"textElements": [{"textRun": {"content": text}}]}},
            }]}],
        }

    def test_replaces_existing_text(self, mock_credentials):
        client, presentations = _make_client(mock_credentials)
        self._shape(presentations, text="old heading\n")
        presentations.batchUpdate.return_value.execute.return_value = {}

        client.set_text("p1", "sh", "new heading")

        reqs = presentations.batchUpdate.call_args[1]["body"]["requests"]
        assert reqs[0]["deleteText"] == {"objectId": "sh", "textRange": {"type": "ALL"}}
        assert reqs[1]["insertText"]["text"] == "new heading"
        assert reqs[1]["insertText"]["insertionIndex"] == 0

    def test_empty_shape_skips_delete(self, mock_credentials):
        client, presentations = _make_client(mock_credentials)
        self._shape(presentations, text="")
        presentations.batchUpdate.return_value.execute.return_value = {}

        client.set_text("p1", "sh", "hi")

        reqs = presentations.batchUpdate.call_args[1]["body"]["requests"]
        assert len(reqs) == 1 and "insertText" in reqs[0]

    def test_non_shape_raises(self, mock_credentials):
        client, presentations = _make_client(mock_credentials)
        presentations.get.return_value.execute.return_value = {
            "slides": [{"objectId": "s0", "pageElements": [
                {"objectId": "tbl", "table": {"tableRows": []}}]}]
        }
        with pytest.raises(ValueError, match="not a shape"):
            client.set_text("p1", "tbl", "x")


class TestSetBackground:
    """Tests for SlidesClient.set_background (Idea 073)."""

    def test_sets_page_background_color_by_index(self, mock_credentials):
        client, presentations = _make_client(mock_credentials)
        presentations.get.return_value.execute.return_value = {
            "slides": [{"objectId": "s0"}, {"objectId": "s1"}]
        }
        presentations.batchUpdate.return_value.execute.return_value = {}

        client.set_background("p1", "1", "#0B5394")

        req = presentations.batchUpdate.call_args[1]["body"]["requests"][0]["updatePageProperties"]
        assert req["objectId"] == "s1"
        rgb = req["pageProperties"]["pageBackgroundFill"]["solidFill"]["color"]["rgbColor"]
        assert "red" in rgb and "opaqueColor" not in \
            req["pageProperties"]["pageBackgroundFill"]["solidFill"]["color"]
        assert req["fields"] == "pageBackgroundFill.solidFill.color"

    def test_theme_color_by_objectid(self, mock_credentials):
        client, presentations = _make_client(mock_credentials)
        presentations.batchUpdate.return_value.execute.return_value = {}

        client.set_background("p1", "s0", "ACCENT1")  # non-digit → objectId, no get()

        color = presentations.batchUpdate.call_args[1]["body"]["requests"][0][
            "updatePageProperties"]["pageProperties"]["pageBackgroundFill"]["solidFill"]["color"]
        assert color == {"themeColor": "ACCENT1"}
        presentations.get.assert_not_called()

    def test_bad_color_raises(self, mock_credentials):
        client, _ = _make_client(mock_credentials)
        with pytest.raises(ValueError, match="Invalid color"):
            client.set_background("p1", "s0", "chartreuse")


class TestFullBleedRegion:
    def test_full_bleed_has_no_margin(self):
        from desk.services.slides import _region_box

        assert _region_box(720, 405, "full-bleed") == (0.0, 0.0, 720, 405)

    def test_full_still_insets(self):
        from desk.services.slides import _region_box

        x, y, w, h = _region_box(720, 405, "full")
        assert (x, y) == (24, 24) and w == 672 and h == 357


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
