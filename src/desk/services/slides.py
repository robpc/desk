"""Google Slides API wrapper.

Phase 1 (ADR-026, Idea 054): content CRUD. Slides is a batchUpdate-style API,
structurally close to Docs — a presentation is a list of slides (pages); each
slide holds page elements (shapes, images, tables); text lives inside shapes and
table cells, addressed by ``objectId``. Mutations are expressed as request
objects (``createSlide``, ``deleteObject``, ``insertText``, ``replaceAllText``).

Use ``inspect()`` to discover the ``objectId``s and placeholder types needed to
target text and structural edits, mirroring ``desk docs inspect``.
"""

import uuid

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

# Predefined slide layouts the Slides API exposes. Surfaced as the choices for
# `add-slide --layout`. See:
# https://developers.google.com/slides/api/reference/rest/v1/presentations.pages#predefinedlayout
PREDEFINED_LAYOUTS = [
    "BLANK",
    "CAPTION_ONLY",
    "TITLE",
    "TITLE_AND_BODY",
    "TITLE_AND_TWO_COLUMNS",
    "TITLE_ONLY",
    "SECTION_HEADER",
    "SECTION_TITLE_AND_DESCRIPTION",
    "ONE_COLUMN_TEXT",
    "MAIN_POINT",
    "BIG_NUMBER",
]

# Curated subset of Slides shape types exposed by `insert-shape --type`. The
# full enum is large and mostly unused by agents; TEXT_BOX is the common case.
# See ADR-027.
SHAPE_TYPES = [
    "TEXT_BOX",
    "RECTANGLE",
    "ROUND_RECTANGLE",
    "ELLIPSE",
    "DIAMOND",
    "CLOUD",
    "RIGHT_ARROW",
]

# Theme color names accepted by `--color`/`--fill`/`--outline` alongside hex.
# Map to a themeColor so a deck stays on-palette. See ADR-028.
THEME_COLORS = [
    "DARK1", "LIGHT1", "DARK2", "LIGHT2",
    "ACCENT1", "ACCENT2", "ACCENT3", "ACCENT4", "ACCENT5", "ACCENT6",
    "HYPERLINK", "FOLLOWED_HYPERLINK",
]

# Named layout regions for the math-free positioning vocabulary (ADR-028).
# Each resolves to a concrete box computed from the slide's real dimensions.
REGIONS = [
    "top-left", "top", "top-right",
    "left", "center", "right",
    "bottom-left", "bottom", "bottom-right",
    "left-half", "right-half", "top-half", "bottom-half",
    "left-third", "center-third", "right-third",
    "top-third", "middle-third", "bottom-third",
    "full",
]

# Element distribution modes for `arrange` (ADR-029).
ARRANGE_MODES = ["columns", "rows", "grid"]

# Layout geometry, in points: outer margin and inter-cell gutter.
_REGION_MARGIN = 24.0
_REGION_GUTTER = 12.0
_EMU_PER_PT = 12700.0


def _parse_color(color: str) -> dict:
    """Parse a color string into a Slides OpaqueColor.

    Accepts ``#RGB`` / ``#RRGGBB`` hex (→ rgbColor) or a theme color name
    (→ themeColor). Raises ValueError on anything else.
    """
    if color.startswith("#"):
        hex_digits = color[1:]
        if len(hex_digits) == 3:
            hex_digits = "".join(c * 2 for c in hex_digits)
        if len(hex_digits) != 6:
            raise ValueError(f"Invalid hex color: {color}. Use #RGB or #RRGGBB.")
        try:
            r = int(hex_digits[0:2], 16) / 255.0
            g = int(hex_digits[2:4], 16) / 255.0
            b = int(hex_digits[4:6], 16) / 255.0
        except ValueError:
            raise ValueError(f"Invalid hex color: {color}.")
        return {"rgbColor": {"red": r, "green": g, "blue": b}}

    name = color.upper()
    if name in THEME_COLORS:
        return {"themeColor": name}

    raise ValueError(
        f"Invalid color: {color}. Use #RRGGBB hex or a theme name "
        f"({', '.join(THEME_COLORS)})."
    )


def _region_box(
    page_w: float, page_h: float, region: str,
) -> tuple[float, float, float, float]:
    """Resolve a region name to an (x, y, width, height) box in points.

    Geometry lives here so agents and commands only ever speak region names.
    """
    m, g = _REGION_MARGIN, _REGION_GUTTER
    cx, cy = m, m
    cw, ch = page_w - 2 * m, page_h - 2 * m

    if region == "full":
        return cx, cy, cw, ch

    half_w = (cw - g) / 2
    half_h = (ch - g) / 2
    if region == "left-half":
        return cx, cy, half_w, ch
    if region == "right-half":
        return cx + half_w + g, cy, half_w, ch
    if region == "top-half":
        return cx, cy, cw, half_h
    if region == "bottom-half":
        return cx, cy + half_h + g, cw, half_h

    # Full-height column thirds and full-width row thirds.
    third_w = (cw - 2 * g) / 3
    third_h = (ch - 2 * g) / 3
    column_thirds = {"left-third": 0, "center-third": 1, "right-third": 2}
    if region in column_thirds:
        col = column_thirds[region]
        return cx + col * (third_w + g), cy, third_w, ch
    row_thirds = {"top-third": 0, "middle-third": 1, "bottom-third": 2}
    if region in row_thirds:
        row = row_thirds[region]
        return cx, cy + row * (third_h + g), cw, third_h

    grid = {
        "top-left": (0, 0), "top": (1, 0), "top-right": (2, 0),
        "left": (0, 1), "center": (1, 1), "right": (2, 1),
        "bottom-left": (0, 2), "bottom": (1, 2), "bottom-right": (2, 2),
    }
    if region not in grid:
        raise ValueError(f"Unknown region: {region}. Valid: {', '.join(REGIONS)}.")
    col, row = grid[region]
    col_w = (cw - 2 * g) / 3
    row_h = (ch - 2 * g) / 3
    x = cx + col * (col_w + g)
    y = cy + row * (row_h + g)
    return x, y, col_w, row_h


def _grid_cells(
    area: tuple[float, float, float, float], n: int, mode: str,
) -> list[tuple[float, float, float, float]]:
    """Split an (x, y, w, h) area into n cells for `arrange`.

    columns → n side-by-side; rows → n stacked; grid → near-square, row-major.
    Returns boxes in points, in placement order.
    """
    import math

    if n < 1:
        return []
    ax, ay, aw, ah = area
    g = _REGION_GUTTER

    if mode == "columns":
        cols, rows = n, 1
    elif mode == "rows":
        cols, rows = 1, n
    elif mode == "grid":
        cols = math.ceil(math.sqrt(n))
        rows = math.ceil(n / cols)
    else:
        raise ValueError(f"Unknown arrange mode: {mode}. Valid: {', '.join(ARRANGE_MODES)}.")

    cell_w = (aw - (cols - 1) * g) / cols
    cell_h = (ah - (rows - 1) * g) / rows

    cells = []
    for i in range(n):
        row, col = divmod(i, cols)
        x = ax + col * (cell_w + g)
        y = ay + row * (cell_h + g)
        cells.append((x, y, cell_w, cell_h))
    return cells


class SlidesClient:
    """Client for Google Slides API operations."""

    def __init__(self, credentials: Credentials):
        self.credentials = credentials
        self.service = build("slides", "v1", credentials=credentials)
        # Drive API needed for webViewLink (create) and export (PDF/PPTX/TXT)
        # since the Slides API doesn't provide these. Lazy-loaded: read(),
        # inspect(), and the mutation methods don't need it.
        self.__drive = None

    @property
    def _drive(self):
        if self.__drive is None:
            self.__drive = build("drive", "v3", credentials=self.credentials)
        return self.__drive

    # ── Helpers ─────────────────────────────────────────────────────────

    def _get(self, presentation_id: str) -> dict:
        """Fetch the full presentation object."""
        return self.service.presentations().get(
            presentationId=presentation_id
        ).execute()

    def _batch_update(self, presentation_id: str, requests: list[dict]) -> dict:
        """Run a batchUpdate and return the raw response."""
        return self.service.presentations().batchUpdate(
            presentationId=presentation_id,
            body={"requests": requests},
        ).execute()

    @staticmethod
    def _extract_text_elements(text: dict) -> str:
        """Join the textRun content of a shape/cell text body into a string."""
        parts = []
        for te in text.get("textElements", []):
            run = te.get("textRun")
            if run:
                parts.append(run.get("content", ""))
        return "".join(parts)

    @classmethod
    def _extract_element_text(cls, element: dict) -> str:
        """Extract text from a single page element (shape or table)."""
        if "shape" in element:
            return cls._extract_text_elements(element["shape"].get("text", {}))
        if "table" in element:
            rows = []
            for row in element["table"].get("tableRows", []):
                cells = []
                for cell in row.get("tableCells", []):
                    cells.append(
                        cls._extract_text_elements(cell.get("text", {})).strip()
                    )
                rows.append(" | ".join(cells))
            return "\n".join(rows)
        return ""

    @staticmethod
    def _element_properties(
        page_id: str,
        x: float | None, y: float | None,
        width: float | None, height: float | None,
        default_w: float, default_h: float,
    ) -> dict:
        """Build an elementProperties payload (size + transform) in points.

        Position/size are optional; omitted values fall back to defaults so an
        element can be placed without geometry. See ADR-027.
        """
        w = width if width is not None else default_w
        h = height if height is not None else default_h
        tx = x if x is not None else 50.0
        ty = y if y is not None else 50.0
        return {
            "pageObjectId": page_id,
            "size": {
                "width": {"magnitude": w, "unit": "PT"},
                "height": {"magnitude": h, "unit": "PT"},
            },
            "transform": {
                "scaleX": 1, "scaleY": 1,
                "translateX": tx, "translateY": ty,
                "unit": "PT",
            },
        }

    @staticmethod
    def _dimension_pt(dim: dict | None, fallback: float) -> float:
        """Convert a Slides Dimension ({magnitude, unit}) to points."""
        if not dim or "magnitude" not in dim:
            return fallback
        magnitude = dim["magnitude"]
        if dim.get("unit") == "EMU":
            return magnitude / _EMU_PER_PT
        return magnitude  # PT (or unspecified — treat as PT)

    def _page_size_pt(self, presentation_id: str) -> tuple[float, float]:
        """Return the slide (width, height) in points.

        Falls back to 16:9 (720x405 pt) if pageSize is absent.
        """
        pres = self._get(presentation_id)
        size = pres.get("pageSize", {})
        w = self._dimension_pt(size.get("width"), 720.0)
        h = self._dimension_pt(size.get("height"), 405.0)
        return w, h

    def _resolve_region_box(
        self, presentation_id: str, region: str,
    ) -> tuple[float, float, float, float]:
        """Resolve a region name to a concrete (x, y, w, h) box in points."""
        w, h = self._page_size_pt(presentation_id)
        return _region_box(w, h, region)

    def _find_element(self, presentation_id: str, object_id: str) -> dict:
        """Find a page element by objectId across all slides.

        Returns the raw element dict. Raises RuntimeError if not found.
        """
        pres = self._get(presentation_id)
        for slide in pres.get("slides", []):
            for element in slide.get("pageElements", []):
                if element.get("objectId") == object_id:
                    return element
        raise RuntimeError(
            f"Object not found: {object_id}. "
            f"Use 'desk slides inspect {presentation_id}' to list objectIds."
        )

    def _resolve_slide_object_id(self, presentation_id: str, slide: str) -> str:
        """Resolve a slide reference to its objectId.

        ``slide`` may be a 0-based index (all digits) or an objectId. Indices
        are resolved against the deck's slide order; objectIds pass through
        untouched (the API validates them).
        """
        if slide.isdigit():
            pres = self._get(presentation_id)
            slides = pres.get("slides", [])
            idx = int(slide)
            if idx >= len(slides):
                raise RuntimeError(
                    f"Slide index {idx} out of range "
                    f"(presentation has {len(slides)} slide(s): 0-{len(slides) - 1})"
                )
            return slides[idx]["objectId"]
        return slide

    # ── Presentation CRUD ───────────────────────────────────────────────

    def create(self, title: str) -> dict:
        """Create a new presentation.

        The Slides API's create accepts only a title; the new deck starts with
        a single default slide. Populate it via add_slide/insert_text.

        Returns:
            Dict with presentationId, title, slideCount, and webViewLink.
        """
        try:
            pres = self.service.presentations().create(
                body={"title": title}
            ).execute()
            pid = pres["presentationId"]

            meta = self._drive.files().get(
                fileId=pid, fields="webViewLink", supportsAllDrives=True
            ).execute()

            return {
                "presentationId": pid,
                "title": pres.get("title", title),
                "slideCount": len(pres.get("slides", [])),
                "webViewLink": meta.get("webViewLink", ""),
            }
        except HttpError as error:
            raise RuntimeError(f"Slides API error: {error}")

    def read(self, presentation_id: str) -> dict:
        """Read a presentation's text content, slide by slide.

        Returns:
            Dict with presentationId, title, slideCount, and slides — each a
            dict of index, objectId, and the concatenated text of its shapes.
        """
        try:
            pres = self._get(presentation_id)
            slides = []
            for i, slide in enumerate(pres.get("slides", [])):
                parts = []
                for element in slide.get("pageElements", []):
                    text = self._extract_element_text(element)
                    if text.strip():
                        parts.append(text.rstrip("\n"))
                slides.append({
                    "index": i,
                    "objectId": slide.get("objectId", ""),
                    "text": "\n".join(parts),
                })
            return {
                "presentationId": presentation_id,
                "title": pres.get("title", ""),
                "slideCount": len(slides),
                "slides": slides,
            }
        except HttpError as error:
            raise RuntimeError(f"Slides API error: {error}")

    def inspect(self, presentation_id: str) -> dict:
        """Inspect presentation structure with objectIds.

        Surfaces each slide's objectId and its page elements (type, objectId,
        placeholder type, and a text preview) so agents know what to target
        with insert-text/delete-object. Parallels ``desk docs inspect``.

        Returns:
            Dict with presentationId, title, and slides (each with elements).
        """
        try:
            pres = self._get(presentation_id)
            slides = []
            for i, slide in enumerate(pres.get("slides", [])):
                elements = []
                for element in slide.get("pageElements", []):
                    object_id = element.get("objectId", "")
                    if "shape" in element:
                        shape = element["shape"]
                        placeholder = shape.get("placeholder", {})
                        text = self._extract_text_elements(
                            shape.get("text", {})
                        ).rstrip("\n")
                        elements.append({
                            "objectId": object_id,
                            "type": "shape",
                            "shapeType": shape.get("shapeType", "TEXT_BOX"),
                            "placeholder": placeholder.get("type"),
                            "text": text[:200],
                        })
                    elif "table" in element:
                        table = element["table"]
                        elements.append({
                            "objectId": object_id,
                            "type": "table",
                            "rows": table.get("rows", 0),
                            "columns": table.get("columns", 0),
                        })
                    elif "image" in element:
                        elements.append({
                            "objectId": object_id,
                            "type": "image",
                        })
                    elif "line" in element:
                        elements.append({
                            "objectId": object_id,
                            "type": "line",
                        })
                    else:
                        elements.append({
                            "objectId": object_id,
                            "type": "other",
                        })
                slides.append({
                    "index": i,
                    "objectId": slide.get("objectId", ""),
                    "elements": elements,
                })
            return {
                "presentationId": presentation_id,
                "title": pres.get("title", ""),
                "slideCount": len(slides),
                "slides": slides,
            }
        except HttpError as error:
            raise RuntimeError(f"Slides API error: {error}")

    # ── Slide structure ─────────────────────────────────────────────────

    def add_slide(
        self, presentation_id: str, layout: str = "TITLE_AND_BODY",
        index: int | None = None, object_id: str | None = None,
    ) -> dict:
        """Add a slide with a predefined layout.

        Args:
            presentation_id: The presentation ID
            layout: A predefined layout (see PREDEFINED_LAYOUTS)
            index: 0-based insertion position, or None to append
            object_id: Optional client-supplied objectId for the new slide

        Returns:
            Dict with presentationId, objectId (the new slide's id), and layout.
        """
        try:
            request: dict = {
                "slideLayoutReference": {"predefinedLayout": layout},
            }
            if index is not None:
                request["insertionIndex"] = index
            if object_id:
                request["objectId"] = object_id

            result = self._batch_update(
                presentation_id, [{"createSlide": request}]
            )
            replies = result.get("replies", [{}])
            new_id = ""
            if replies:
                new_id = replies[0].get("createSlide", {}).get("objectId", "")

            return {
                "presentationId": presentation_id,
                "objectId": new_id,
                "layout": layout,
            }
        except HttpError as error:
            raise RuntimeError(f"Slides API error: {error}")

    def delete_slide(self, presentation_id: str, slide: str) -> dict:
        """Delete a slide by 0-based index or objectId.

        Returns:
            Dict with presentationId, objectId (the deleted slide), and status.
        """
        try:
            object_id = self._resolve_slide_object_id(presentation_id, slide)
            self._batch_update(
                presentation_id, [{"deleteObject": {"objectId": object_id}}]
            )
            return {
                "presentationId": presentation_id,
                "objectId": object_id,
                "status": "ok",
            }
        except HttpError as error:
            raise RuntimeError(f"Slides API error: {error}")

    def delete_object(self, presentation_id: str, object_id: str) -> dict:
        """Delete any page element (or slide) by objectId.

        Returns:
            Dict with presentationId, objectId, and status.
        """
        try:
            self._batch_update(
                presentation_id, [{"deleteObject": {"objectId": object_id}}]
            )
            return {
                "presentationId": presentation_id,
                "objectId": object_id,
                "status": "ok",
            }
        except HttpError as error:
            raise RuntimeError(f"Slides API error: {error}")

    def duplicate_slide(self, presentation_id: str, slide: str) -> dict:
        """Duplicate a slide by 0-based index or objectId.

        Returns:
            Dict with presentationId, sourceObjectId, objectId (the copy),
            and status.
        """
        try:
            object_id = self._resolve_slide_object_id(presentation_id, slide)
            result = self._batch_update(
                presentation_id, [{"duplicateObject": {"objectId": object_id}}]
            )
            replies = result.get("replies", [{}])
            new_id = ""
            if replies:
                new_id = replies[0].get("duplicateObject", {}).get("objectId", "")
            return {
                "presentationId": presentation_id,
                "sourceObjectId": object_id,
                "objectId": new_id,
                "status": "ok",
            }
        except HttpError as error:
            raise RuntimeError(f"Slides API error: {error}")

    def move_slide(
        self, presentation_id: str, slide: str, insertion_index: int,
    ) -> dict:
        """Reorder a slide to a new 0-based position.

        Returns:
            Dict with presentationId, objectId, insertionIndex, and status.
        """
        try:
            object_id = self._resolve_slide_object_id(presentation_id, slide)
            self._batch_update(
                presentation_id,
                [{
                    "updateSlidesPosition": {
                        "slideObjectIds": [object_id],
                        "insertionIndex": insertion_index,
                    }
                }],
            )
            return {
                "presentationId": presentation_id,
                "objectId": object_id,
                "insertionIndex": insertion_index,
                "status": "ok",
            }
        except HttpError as error:
            raise RuntimeError(f"Slides API error: {error}")

    # ── Text ─────────────────────────────────────────────────────────────

    def insert_text(
        self, presentation_id: str, object_id: str, text: str,
        index: int = 0,
    ) -> dict:
        """Insert text into a shape or table cell by objectId.

        The target objectId must be a shape (e.g. a placeholder surfaced by
        inspect) or table cell with a text body. Use inspect to find it.

        Args:
            presentation_id: The presentation ID
            object_id: The shape/cell objectId to insert into
            text: Text to insert
            index: 0-based character insertion index within the shape's text

        Returns:
            Dict with presentationId, objectId, and status.
        """
        try:
            self._batch_update(
                presentation_id,
                [{
                    "insertText": {
                        "objectId": object_id,
                        "text": text,
                        "insertionIndex": index,
                    }
                }],
            )
            return {
                "presentationId": presentation_id,
                "objectId": object_id,
                "status": "ok",
            }
        except HttpError as error:
            raise RuntimeError(f"Slides API error: {error}")

    def replace_text(
        self, presentation_id: str, find_text: str, replace_text: str,
        match_case: bool = True,
    ) -> dict:
        """Find and replace all occurrences of text across the deck.

        Returns:
            Dict with presentationId, occurrences_changed, and status.
        """
        try:
            result = self._batch_update(
                presentation_id,
                [{
                    "replaceAllText": {
                        "containsText": {
                            "text": find_text,
                            "matchCase": match_case,
                        },
                        "replaceText": replace_text,
                    }
                }],
            )
            replies = result.get("replies", [{}])
            occurrences = 0
            if replies:
                occurrences = replies[0].get("replaceAllText", {}).get(
                    "occurrencesChanged", 0
                )
            return {
                "presentationId": presentation_id,
                "occurrences_changed": occurrences,
                "status": "ok",
            }
        except HttpError as error:
            raise RuntimeError(f"Slides API error: {error}")

    # ── Visual elements (Phase 2, ADR-027) ──────────────────────────────

    def insert_image(
        self, presentation_id: str, slide: str, url: str,
        x: float | None = None, y: float | None = None,
        width: float | None = None, height: float | None = None,
        region: str | None = None,
    ) -> dict:
        """Insert an image onto a slide from a public URL.

        Args:
            presentation_id: The presentation ID
            slide: Target slide as 0-based index or objectId
            url: Publicly accessible image URL
            x, y: Top-left position in points (default ~50,50)
            width, height: Size in points (default 300x200)
            region: A named region (overrides x/y/width/height). See REGIONS.

        Returns:
            Dict with presentationId, slideObjectId, objectId (the image), status.
        """
        try:
            page_id = self._resolve_slide_object_id(presentation_id, slide)
            if region:
                x, y, width, height = self._resolve_region_box(presentation_id, region)
            props = self._element_properties(
                page_id, x, y, width, height, default_w=300.0, default_h=200.0,
            )
            result = self._batch_update(
                presentation_id,
                [{"createImage": {"url": url, "elementProperties": props}}],
            )
            replies = result.get("replies", [{}])
            new_id = ""
            if replies:
                new_id = replies[0].get("createImage", {}).get("objectId", "")
            return {
                "presentationId": presentation_id,
                "slideObjectId": page_id,
                "objectId": new_id,
                "status": "ok",
            }
        except HttpError as error:
            raise RuntimeError(f"Slides API error: {error}")

    def insert_table(
        self, presentation_id: str, slide: str, rows: int, columns: int,
        x: float | None = None, y: float | None = None,
        width: float | None = None, height: float | None = None,
        region: str | None = None,
    ) -> dict:
        """Insert a table onto a slide.

        Args:
            presentation_id: The presentation ID
            slide: Target slide as 0-based index or objectId
            rows: Number of rows
            columns: Number of columns
            x, y: Top-left position in points (default ~50,50)
            width, height: Size in points; when omitted the API sizes the table
            region: A named region (overrides x/y/width/height). See REGIONS.

        Returns:
            Dict with presentationId, slideObjectId, objectId (the table), status.
        """
        try:
            page_id = self._resolve_slide_object_id(presentation_id, slide)
            if region:
                x, y, width, height = self._resolve_region_box(presentation_id, region)
            element_props: dict = {"pageObjectId": page_id}
            # Only constrain size/position when the caller asked; otherwise let
            # the API place and size the table by its content.
            if any(v is not None for v in (x, y, width, height)):
                element_props = self._element_properties(
                    page_id, x, y, width, height, default_w=400.0, default_h=200.0,
                )
            result = self._batch_update(
                presentation_id,
                [{
                    "createTable": {
                        "elementProperties": element_props,
                        "rows": rows,
                        "columns": columns,
                    }
                }],
            )
            replies = result.get("replies", [{}])
            new_id = ""
            if replies:
                new_id = replies[0].get("createTable", {}).get("objectId", "")
            return {
                "presentationId": presentation_id,
                "slideObjectId": page_id,
                "objectId": new_id,
                "status": "ok",
            }
        except HttpError as error:
            raise RuntimeError(f"Slides API error: {error}")

    def insert_shape(
        self, presentation_id: str, slide: str, shape_type: str = "TEXT_BOX",
        text: str | None = None,
        x: float | None = None, y: float | None = None,
        width: float | None = None, height: float | None = None,
        region: str | None = None,
    ) -> dict:
        """Insert a shape (default text box) onto a slide, optionally with text.

        When ``text`` is given, the shape is created with a client-supplied
        objectId and the text inserted in the same batchUpdate, so a labelled
        box is one round-trip. See ADR-027.

        ``region`` (see REGIONS) overrides x/y/width/height with a computed box.

        Returns:
            Dict with presentationId, slideObjectId, objectId (the shape), status.
        """
        try:
            page_id = self._resolve_slide_object_id(presentation_id, slide)
            if region:
                x, y, width, height = self._resolve_region_box(presentation_id, region)
            props = self._element_properties(
                page_id, x, y, width, height, default_w=300.0, default_h=100.0,
            )
            object_id = f"shape_{uuid.uuid4().hex[:16]}"
            requests: list[dict] = [{
                "createShape": {
                    "objectId": object_id,
                    "shapeType": shape_type,
                    "elementProperties": props,
                }
            }]
            if text:
                requests.append({
                    "insertText": {
                        "objectId": object_id,
                        "text": text,
                        "insertionIndex": 0,
                    }
                })
            self._batch_update(presentation_id, requests)
            return {
                "presentationId": presentation_id,
                "slideObjectId": page_id,
                "objectId": object_id,
                "status": "ok",
            }
        except HttpError as error:
            raise RuntimeError(f"Slides API error: {error}")

    # ── Styling & layout (Phase 3a, ADR-028) ────────────────────────────

    def style_text(
        self, presentation_id: str, object_id: str,
        bold: bool | None = None, italic: bool | None = None,
        underline: bool | None = None,
        font_size: float | None = None, font_family: str | None = None,
        color: str | None = None,
        start: int | None = None, end: int | None = None,
    ) -> dict:
        """Apply text styling to a shape's text.

        Styles the whole shape's text by default; pass start/end for a range.
        ``color`` accepts hex (#RRGGBB) or a theme name (see _parse_color).

        Returns:
            Dict with presentationId, objectId, and status.
        """
        style: dict = {}
        fields: list[str] = []
        if bold is not None:
            style["bold"] = bold
            fields.append("bold")
        if italic is not None:
            style["italic"] = italic
            fields.append("italic")
        if underline is not None:
            style["underline"] = underline
            fields.append("underline")
        if font_size is not None:
            style["fontSize"] = {"magnitude": font_size, "unit": "PT"}
            fields.append("fontSize")
        if font_family is not None:
            style["fontFamily"] = font_family
            fields.append("fontFamily")
        if color is not None:
            style["foregroundColor"] = {"opaqueColor": _parse_color(color)}
            fields.append("foregroundColor")

        if not fields:
            return {"presentationId": presentation_id, "objectId": object_id,
                    "status": "ok", "note": "no styles specified"}

        if start is not None and end is not None:
            text_range = {"type": "FIXED_RANGE", "startIndex": start, "endIndex": end}
        else:
            text_range = {"type": "ALL"}

        try:
            self._batch_update(
                presentation_id,
                [{
                    "updateTextStyle": {
                        "objectId": object_id,
                        "style": style,
                        "textRange": text_range,
                        "fields": ",".join(fields),
                    }
                }],
            )
            return {"presentationId": presentation_id, "objectId": object_id, "status": "ok"}
        except HttpError as error:
            raise RuntimeError(f"Slides API error: {error}")

    def format_element(
        self, presentation_id: str, object_id: str,
        fill: str | None = None, outline: str | None = None,
        outline_weight: float | None = None,
    ) -> dict:
        """Apply fill/outline to a shape or image.

        Shapes get a background fill + outline; images get an outline only
        (the API has no image fill). Dispatches by the element's actual type.

        Returns:
            Dict with presentationId, objectId, elementType, and status.
        """
        element = self._find_element(presentation_id, object_id)

        # SolidFill.color is an OpaqueColor directly (unlike text's
        # foregroundColor, which is an OptionalColor wrapping opaqueColor).
        outline_obj: dict = {}
        outline_fields: list[str] = []
        if outline is not None:
            outline_obj["outlineFill"] = {
                "solidFill": {"color": _parse_color(outline)}
            }
            outline_fields.append("outline.outlineFill.solidFill.color")
        if outline_weight is not None:
            outline_obj["weight"] = {"magnitude": outline_weight, "unit": "PT"}
            outline_fields.append("outline.weight")

        try:
            if "shape" in element:
                props: dict = {}
                fields: list[str] = []
                if fill is not None:
                    props["shapeBackgroundFill"] = {
                        "solidFill": {"color": _parse_color(fill)}
                    }
                    fields.append("shapeBackgroundFill.solidFill.color")
                if outline_obj:
                    props["outline"] = outline_obj
                    fields.extend(outline_fields)
                if not fields:
                    return {"presentationId": presentation_id, "objectId": object_id,
                            "elementType": "shape", "status": "ok",
                            "note": "no formatting specified"}
                request = {"updateShapeProperties": {
                    "objectId": object_id,
                    "shapeProperties": props,
                    "fields": ",".join(fields),
                }}
                element_type = "shape"
            elif "image" in element:
                if fill is not None:
                    raise ValueError("Images have no fill; use --outline instead.")
                if not outline_obj:
                    return {"presentationId": presentation_id, "objectId": object_id,
                            "elementType": "image", "status": "ok",
                            "note": "no formatting specified"}
                request = {"updateImageProperties": {
                    "objectId": object_id,
                    "imageProperties": {"outline": outline_obj},
                    "fields": ",".join(outline_fields),
                }}
                element_type = "image"
            else:
                raise ValueError(
                    "format supports shapes and images; "
                    f"object {object_id} is neither."
                )

            self._batch_update(presentation_id, [request])
            return {"presentationId": presentation_id, "objectId": object_id,
                    "elementType": element_type, "status": "ok"}
        except HttpError as error:
            raise RuntimeError(f"Slides API error: {error}")

    def _fit_transform_request(self, element: dict, box: tuple) -> dict:
        """Build an ABSOLUTE updatePageElementTransform fitting element to box.

        The API's base size is the un-scaled size, so scale = target / base.
        Raises RuntimeError if the element has no resolvable size.
        """
        object_id = element.get("objectId", "")
        size = element.get("size", {})
        base_w = self._dimension_pt(size.get("width"), 0.0)
        base_h = self._dimension_pt(size.get("height"), 0.0)
        if base_w <= 0 or base_h <= 0:
            raise RuntimeError(
                f"Cannot place object {object_id}: it has no resolvable size."
            )
        box_x, box_y, box_w, box_h = box
        return {
            "updatePageElementTransform": {
                "objectId": object_id,
                "applyMode": "ABSOLUTE",
                "transform": {
                    "scaleX": box_w / base_w, "scaleY": box_h / base_h,
                    "translateX": box_x, "translateY": box_y,
                    "unit": "PT",
                },
            }
        }

    def place_element(
        self, presentation_id: str, object_id: str, region: str,
    ) -> dict:
        """Move and fit an existing element into a named region.

        Reads the element's current base size and computes the transform to
        fill the region box — the caller never does geometry. See ADR-028.

        Returns:
            Dict with presentationId, objectId, region, and status.
        """
        element = self._find_element(presentation_id, object_id)
        page_w, page_h = self._page_size_pt(presentation_id)
        box = _region_box(page_w, page_h, region)
        request = self._fit_transform_request(element, box)

        try:
            self._batch_update(presentation_id, [request])
            return {"presentationId": presentation_id, "objectId": object_id,
                    "region": region, "status": "ok"}
        except HttpError as error:
            raise RuntimeError(f"Slides API error: {error}")

    def arrange_elements(
        self, presentation_id: str, object_ids: list[str], mode: str,
        region: str | None = None,
    ) -> dict:
        """Distribute existing elements into evenly-sized cells (ADR-029).

        The target area is the slide content area, or a named region if given.
        Elements are fitted to their cells in argument order. All transforms
        are sent in one batchUpdate.

        Returns:
            Dict with presentationId, objectIds, mode, region, and status.
        """
        if not object_ids:
            raise ValueError("arrange requires at least one object id.")

        # Fetch once; build an objectId → element map across all slides.
        pres = self._get(presentation_id)
        index: dict[str, dict] = {}
        for slide in pres.get("slides", []):
            for element in slide.get("pageElements", []):
                index[element.get("objectId", "")] = element

        elements = []
        for oid in object_ids:
            if oid not in index:
                raise RuntimeError(
                    f"Object not found: {oid}. "
                    f"Use 'desk slides inspect {presentation_id}' to list objectIds."
                )
            elements.append(index[oid])

        size = pres.get("pageSize", {})
        page_w = self._dimension_pt(size.get("width"), 720.0)
        page_h = self._dimension_pt(size.get("height"), 405.0)
        area = _region_box(page_w, page_h, region) if region else _region_box(
            page_w, page_h, "full"
        )
        cells = _grid_cells(area, len(elements), mode)
        requests = [
            self._fit_transform_request(el, cell)
            for el, cell in zip(elements, cells)
        ]

        try:
            self._batch_update(presentation_id, requests)
            return {"presentationId": presentation_id, "objectIds": object_ids,
                    "mode": mode, "region": region, "status": "ok"}
        except HttpError as error:
            raise RuntimeError(f"Slides API error: {error}")

    # ── Export ───────────────────────────────────────────────────────────

    def export(self, presentation_id: str, fmt: str = "pdf") -> bytes:
        """Export a presentation to a different format via Drive.

        Args:
            presentation_id: The presentation ID
            fmt: Export format (pdf, pptx, txt)

        Returns:
            File content as bytes.
        """
        mime_map = {
            "pdf": "application/pdf",
            "pptx": (
                "application/vnd.openxmlformats-officedocument"
                ".presentationml.presentation"
            ),
            "txt": "text/plain",
        }
        mime = mime_map.get(fmt)
        if not mime:
            raise RuntimeError(
                f"Unsupported format: {fmt}. Use: {', '.join(mime_map)}"
            )

        try:
            # Note: files().export does not accept supportsAllDrives (unlike
            # files().get/files().export_media's sibling params); passing it
            # raises a client-side TypeError.
            return self._drive.files().export(
                fileId=presentation_id, mimeType=mime
            ).execute()
        except HttpError as error:
            raise RuntimeError(f"Slides API error: {error}")
