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
    "full", "full-bleed",
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
    if region == "full-bleed":
        # Edge-to-edge, no margin (full-bleed backgrounds/images).
        return 0.0, 0.0, page_w, page_h

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
                    "notes": self._slide_notes_text(slide).rstrip("\n"),
                })
            return {
                "presentationId": presentation_id,
                "title": pres.get("title", ""),
                "slideCount": len(slides),
                "slides": slides,
            }
        except HttpError as error:
            raise RuntimeError(f"Slides API error: {error}")

    @staticmethod
    def _notes_object_id(slide: dict) -> str | None:
        """Return a slide's speaker-notes objectId, if present."""
        return (
            slide.get("slideProperties", {})
            .get("notesPage", {})
            .get("notesProperties", {})
            .get("speakerNotesObjectId")
        )

    def _slide_notes_text(self, slide: dict) -> str:
        """Extract the speaker-notes text for a slide (empty string if none)."""
        notes_id = self._notes_object_id(slide)
        if not notes_id:
            return ""
        notes_page = slide.get("slideProperties", {}).get("notesPage", {})
        for element in notes_page.get("pageElements", []):
            if element.get("objectId") == notes_id and "shape" in element:
                return self._extract_text_elements(element["shape"].get("text", {}))
        return ""

    @staticmethod
    def _element_box(element: dict) -> dict | None:
        """Compute an element's rendered bounding box in points (ADR-030, Idea 064).

        Derived from base size × transform scale + translate. Rotation/shear are
        ignored (rare for agent-placed elements); returns None when size or
        transform is absent.
        """
        size = element.get("size")
        transform = element.get("transform")
        if not size or not transform:
            return None
        base_w = SlidesClient._dimension_pt(size.get("width"), 0.0)
        base_h = SlidesClient._dimension_pt(size.get("height"), 0.0)
        scale_x = transform.get("scaleX", 1) or 1
        scale_y = transform.get("scaleY", 1) or 1
        tx = transform.get("translateX", 0) or 0
        ty = transform.get("translateY", 0) or 0
        if transform.get("unit") == "EMU":
            tx /= _EMU_PER_PT
            ty /= _EMU_PER_PT
        return {
            "x": round(tx, 1), "y": round(ty, 1),
            "width": round(base_w * scale_x, 1),
            "height": round(base_h * scale_y, 1),
        }

    @staticmethod
    def _boxes_overlap(a: dict, b: dict) -> bool:
        """Axis-aligned overlap test with a small tolerance (edge-touch is not overlap)."""
        eps = 0.5
        return not (
            a["x"] + a["width"] <= b["x"] + eps
            or b["x"] + b["width"] <= a["x"] + eps
            or a["y"] + a["height"] <= b["y"] + eps
            or b["y"] + b["height"] <= a["y"] + eps
        )

    @staticmethod
    def _rgb_to_hex(rgb: dict) -> str:
        """Format an rgbColor ({red,green,blue} 0–1 floats) as #RRGGBB."""
        def chan(v):
            return max(0, min(255, round((v or 0) * 255)))
        return "#{:02X}{:02X}{:02X}".format(
            chan(rgb.get("red")), chan(rgb.get("green")), chan(rgb.get("blue"))
        )

    def get_theme(self, presentation_id: str) -> dict:
        """Return the deck's theme color palette (ADR-030, Idea 069).

        Resolves the active color scheme (master → layout → slide) into a list
        of {name, hex} so an agent can see what ACCENT1..6 / DARK1 / LIGHT1
        actually resolve to before using them in style/format.

        Returns:
            Dict with presentationId and theme (list of {name, hex}).
        """
        try:
            pres = self._get(presentation_id)
            scheme = None
            for container in ("masters", "layouts", "slides"):
                for page in pres.get(container, []):
                    cs = page.get("pageProperties", {}).get("colorScheme")
                    if cs and cs.get("colors"):
                        scheme = cs
                        break
                if scheme:
                    break
            colors = []
            for c in (scheme or {}).get("colors", []):
                colors.append({
                    "name": c.get("type"),
                    "hex": self._rgb_to_hex(c.get("color", {})),
                })
            return {"presentationId": presentation_id, "theme": colors}
        except HttpError as error:
            raise RuntimeError(f"Slides API error: {error}")

    def inspect(self, presentation_id: str) -> dict:
        """Inspect presentation structure with objectIds and computed layout.

        Surfaces each slide's objectId and its page elements (type, objectId,
        placeholder type, text preview) plus each element's computed bounding
        box (x/y/width/height in points) and ``offSlide`` / ``overlaps`` flags,
        so an agent can verify placement without exporting (Idea 064).

        Returns:
            Dict with presentationId, title, pageSize, and slides (each with
            elements carrying box + offSlide + overlaps).
        """
        try:
            pres = self._get(presentation_id)
            page = pres.get("pageSize", {})
            page_w = self._dimension_pt(page.get("width"), 720.0)
            page_h = self._dimension_pt(page.get("height"), 405.0)

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
                        elem: dict = {
                            "objectId": object_id,
                            "type": "shape",
                            "shapeType": shape.get("shapeType", "TEXT_BOX"),
                            "placeholder": placeholder.get("type"),
                            "text": text[:200],
                        }
                    elif "table" in element:
                        table = element["table"]
                        elem = {
                            "objectId": object_id,
                            "type": "table",
                            "rows": table.get("rows", 0),
                            "columns": table.get("columns", 0),
                        }
                    elif "image" in element:
                        elem = {"objectId": object_id, "type": "image"}
                    elif "line" in element:
                        elem = {"objectId": object_id, "type": "line"}
                    else:
                        elem = {"objectId": object_id, "type": "other"}

                    box = self._element_box(element)
                    elem["box"] = box
                    if box:
                        eps = 0.5
                        elem["offSlide"] = (
                            box["x"] < -eps or box["y"] < -eps
                            or box["x"] + box["width"] > page_w + eps
                            or box["y"] + box["height"] > page_h + eps
                        )
                    elements.append(elem)

                # Pairwise overlap flags (only elements with a resolved box).
                for elem in elements:
                    if not elem.get("box"):
                        continue
                    hits = [
                        other["objectId"] for other in elements
                        if other is not elem and other.get("box")
                        and self._boxes_overlap(elem["box"], other["box"])
                    ]
                    elem["overlaps"] = hits

                slides.append({
                    "index": i,
                    "objectId": slide.get("objectId", ""),
                    "elements": elements,
                })
            return {
                "presentationId": presentation_id,
                "title": pres.get("title", ""),
                "pageSize": {"width": round(page_w, 1), "height": round(page_h, 1)},
                "slideCount": len(slides),
                "slides": slides,
            }
        except HttpError as error:
            raise RuntimeError(f"Slides API error: {error}")

    # ── Slide structure ─────────────────────────────────────────────────

    # Logical fill fields → the placeholder type(s) they target, in priority order.
    _PLACEHOLDER_TARGETS = {
        "title": ("TITLE", "CENTERED_TITLE"),
        "subtitle": ("SUBTITLE",),
        "body": ("BODY",),
    }

    @staticmethod
    def _match_placeholder(placeholders: list[dict], types: tuple[str, ...]) -> str | None:
        """Return the objectId of the first placeholder matching any of types."""
        for ph in placeholders:
            if ph.get("type") in types:
                return ph.get("objectId")
        return None

    def add_slide(
        self, presentation_id: str, layout: str = "TITLE_AND_BODY",
        index: int | None = None, object_id: str | None = None,
        title: str | None = None, body: str | None = None,
        subtitle: str | None = None,
    ) -> dict:
        """Add a slide with a predefined layout, optionally filling placeholders.

        Args:
            presentation_id: The presentation ID
            layout: A predefined layout (see PREDEFINED_LAYOUTS)
            index: 0-based insertion position, or None to append
            object_id: Optional client-supplied objectId for the new slide
            title/subtitle/body: Optional text to insert into the matching
                placeholder at creation, so a populated slide is one call
                (ADR-030, Idea 061b). Raises ValueError if the layout lacks a
                requested placeholder.

        Returns:
            Dict with presentationId, objectId (the new slide's id), layout,
            placeholders ({type, objectId}), and filled ([{field, objectId}]).
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

            placeholders = self._slide_placeholders(presentation_id, new_id) if new_id else []

            # Inline placeholder fills. Resolve+validate all targets first; if a
            # requested placeholder is missing, roll back the just-created slide so
            # a bad fill doesn't orphan a blank slide, then raise.
            fills = [(f, t) for f, t in (
                ("title", title), ("subtitle", subtitle), ("body", body),
            ) if t is not None]
            fill_requests = []
            filled = []
            for field, text in fills:
                oid = self._match_placeholder(placeholders, self._PLACEHOLDER_TARGETS[field])
                if not oid:
                    available = sorted({p.get("type") for p in placeholders if p.get("type")})
                    if new_id:
                        self._batch_update(
                            presentation_id, [{"deleteObject": {"objectId": new_id}}]
                        )
                    raise ValueError(
                        f"--{field}: layout {layout} has no matching placeholder "
                        f"(available: {', '.join(available) or 'none'})."
                    )
                fill_requests.append({"insertText": {
                    "objectId": oid, "text": text, "insertionIndex": 0,
                }})
                filled.append({"field": field, "objectId": oid})

            if fill_requests:
                self._batch_update(presentation_id, fill_requests)

            return {
                "presentationId": presentation_id,
                "objectId": new_id,
                "layout": layout,
                "placeholders": placeholders,
                "filled": filled,
            }
        except HttpError as error:
            raise RuntimeError(f"Slides API error: {error}")

    def _slide_placeholders(self, presentation_id: str, slide_id: str) -> list[dict]:
        """Fetch a slide's placeholder shapes as [{type, objectId, index}].

        Lets add-slide hand back the objectIds needed to fill the slide,
        removing the otherwise-mandatory inspect round-trip (ADR-030).
        """
        page = self.service.presentations().pages().get(
            presentationId=presentation_id, pageObjectId=slide_id
        ).execute()
        placeholders = []
        for element in page.get("pageElements", []):
            shape = element.get("shape", {})
            ph = shape.get("placeholder")
            if ph:
                entry = {"type": ph.get("type"), "objectId": element.get("objectId", "")}
                if "index" in ph:
                    entry["index"] = ph["index"]
                placeholders.append(entry)
        return placeholders

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

    def set_notes(
        self, presentation_id: str, slide: str, text: str, mode: str = "replace",
    ) -> dict:
        """Set a slide's speaker notes (ADR-030, Idea 059).

        Targets the slide's notes page speaker-notes shape. ``mode="replace"``
        clears existing notes first; ``mode="append"`` adds to the end.

        Returns:
            Dict with presentationId, slideObjectId, notesObjectId, mode, status.
        """
        try:
            slide_id = self._resolve_slide_object_id(presentation_id, slide)
            page = self.service.presentations().pages().get(
                presentationId=presentation_id, pageObjectId=slide_id
            ).execute()
            notes_id = self._notes_object_id(page)
            if not notes_id:
                raise RuntimeError(
                    f"Slide {slide} has no speaker-notes shape to write to."
                )

            # Current notes length (text bodies carry an implicit trailing newline).
            notes_page = page.get("slideProperties", {}).get("notesPage", {})
            current_len = 0
            for element in notes_page.get("pageElements", []):
                if element.get("objectId") == notes_id and "shape" in element:
                    current_len = len(
                        self._extract_text_elements(element["shape"].get("text", {}))
                    )
                    break

            requests: list[dict] = []
            if mode == "append":
                insert_index = max(0, current_len - 1)
                requests.append({"insertText": {
                    "objectId": notes_id, "text": text, "insertionIndex": insert_index,
                }})
            else:  # replace
                if current_len > 1:
                    requests.append({"deleteText": {
                        "objectId": notes_id, "textRange": {"type": "ALL"},
                    }})
                requests.append({"insertText": {
                    "objectId": notes_id, "text": text, "insertionIndex": 0,
                }})

            self._batch_update(presentation_id, requests)
            return {
                "presentationId": presentation_id,
                "slideObjectId": slide_id,
                "notesObjectId": notes_id,
                "mode": mode,
                "status": "ok",
            }
        except HttpError as error:
            raise RuntimeError(f"Slides API error: {error}")

    def set_cell(
        self, presentation_id: str, table_object_id: str,
        row: int, col: int, text: str, mode: str = "replace",
    ) -> dict:
        """Set the text of a table cell (ADR-030, Idea 066).

        Table cells aren't separate objects — the Slides API addresses them via
        a ``cellLocation`` on the table's objectId. ``insert-text`` against a
        bare table objectId is rejected; this fills the cell at (row, col).

        Returns:
            Dict with presentationId, objectId (table), row, col, mode, status.
        """
        element = self._find_element(presentation_id, table_object_id)
        table = element.get("table")
        if table is None:
            raise ValueError(
                f"Object {table_object_id} is not a table. "
                "Use insert-text for shapes/placeholders."
            )
        rows = table.get("tableRows", [])
        n_rows = len(rows)
        n_cols = len(rows[0].get("tableCells", [])) if rows else 0
        if not (0 <= row < n_rows) or not (0 <= col < n_cols):
            raise ValueError(
                f"Cell ({row},{col}) out of range for a {n_rows}x{n_cols} table."
            )

        cell = rows[row].get("tableCells", [])[col]
        cell_len = len(self._extract_text_elements(cell.get("text", {})))
        cell_location = {"rowIndex": row, "columnIndex": col}

        requests: list[dict] = []
        if mode == "append":
            requests.append({"insertText": {
                "objectId": table_object_id,
                "cellLocation": cell_location,
                "text": text,
                "insertionIndex": max(0, cell_len - 1),
            }})
        else:  # replace
            if cell_len > 1:
                requests.append({"deleteText": {
                    "objectId": table_object_id,
                    "cellLocation": cell_location,
                    "textRange": {"type": "ALL"},
                }})
            requests.append({"insertText": {
                "objectId": table_object_id,
                "cellLocation": cell_location,
                "text": text,
                "insertionIndex": 0,
            }})

        try:
            self._batch_update(presentation_id, requests)
            return {
                "presentationId": presentation_id,
                "objectId": table_object_id,
                "row": row, "col": col, "mode": mode, "status": "ok",
            }
        except HttpError as error:
            raise RuntimeError(f"Slides API error: {error}")

    def set_text(self, presentation_id: str, object_id: str, text: str) -> dict:
        """Replace a shape's entire text, keeping the shape (Idea 072).

        insert-text only inserts/appends and replace-text is find/replace, so
        changing a shape's text otherwise meant delete + re-insert + re-style.
        This clears the shape's text and sets the new value in one batchUpdate.

        Returns:
            Dict with presentationId, objectId, and status.
        """
        element = self._find_element(presentation_id, object_id)
        if "shape" not in element:
            raise ValueError(
                f"Object {object_id} is not a shape. Use set-cell for tables."
            )
        current_len = len(
            self._extract_text_elements(element["shape"].get("text", {}))
        )
        requests: list[dict] = []
        if current_len > 1:  # text bodies carry an implicit trailing newline
            requests.append({"deleteText": {
                "objectId": object_id, "textRange": {"type": "ALL"},
            }})
        requests.append({"insertText": {
            "objectId": object_id, "text": text, "insertionIndex": 0,
        }})
        try:
            self._batch_update(presentation_id, requests)
            return {
                "presentationId": presentation_id,
                "objectId": object_id,
                "status": "ok",
            }
        except HttpError as error:
            raise RuntimeError(f"Slides API error: {error}")

    def set_background(self, presentation_id: str, slide: str, color: str) -> dict:
        """Set a slide's page background color (Idea 073).

        Sets the actual page background via updatePageProperties — no
        rectangle-behind-everything hack (and the Slides API has no z-order
        control, so a background rectangle is awkward anyway). ``color`` accepts
        hex (#RRGGBB) or a theme name (see _parse_color).

        Returns:
            Dict with presentationId, slideObjectId, color, and status.
        """
        slide_id = self._resolve_slide_object_id(presentation_id, slide)
        try:
            self._batch_update(
                presentation_id,
                [{
                    "updatePageProperties": {
                        "objectId": slide_id,
                        "pageProperties": {
                            "pageBackgroundFill": {
                                "solidFill": {"color": _parse_color(color)}
                            }
                        },
                        "fields": "pageBackgroundFill.solidFill.color",
                    }
                }],
            )
            return {
                "presentationId": presentation_id,
                "slideObjectId": slide_id,
                "color": color,
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
        self, presentation_id: str, slide: str,
        rows: int | None = None, columns: int | None = None,
        x: float | None = None, y: float | None = None,
        width: float | None = None, height: float | None = None,
        region: str | None = None,
        data: list[list[str]] | None = None,
    ) -> dict:
        """Insert a table onto a slide, optionally pre-filled with data.

        Args:
            presentation_id: The presentation ID
            slide: Target slide as 0-based index or objectId
            rows/columns: Table dimensions. When ``data`` is given they are
                inferred from it (and validated if also passed).
            x, y: Top-left position in points (default ~50,50)
            width, height: Size in points; when omitted the API sizes the table
            region: A named region (overrides x/y/width/height). See REGIONS.
            data: Rows of cell text to fill at creation (Idea 070). The table is
                created with a client objectId and cells are filled in the same
                batchUpdate, so a populated table is one call.

        Returns:
            Dict with presentationId, slideObjectId, objectId (the table), and
            (when data given) filled_cells count.
        """
        if data is not None:
            if not data or not data[0]:
                raise ValueError("--data must be a non-empty list of rows.")
            d_rows, d_cols = len(data), max(len(r) for r in data)
            if rows is not None and rows != d_rows:
                raise ValueError(f"--rows {rows} != data rows {d_rows}.")
            if columns is not None and columns != d_cols:
                raise ValueError(f"--cols {columns} != data columns {d_cols}.")
            rows, columns = d_rows, d_cols
        if rows is None or columns is None:
            raise ValueError("Provide --rows and --cols, or --data.")
        if rows < 1 or columns < 1:
            raise ValueError(f"Invalid dimensions: rows={rows}, cols={columns}.")

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

            table_id = f"table_{uuid.uuid4().hex[:16]}"
            requests: list[dict] = [{
                "createTable": {
                    "objectId": table_id,
                    "elementProperties": element_props,
                    "rows": rows,
                    "columns": columns,
                }
            }]
            filled = 0
            if data is not None:
                for r, row_values in enumerate(data):
                    for c, value in enumerate(row_values):
                        if value:
                            requests.append({"insertText": {
                                "objectId": table_id,
                                "cellLocation": {"rowIndex": r, "columnIndex": c},
                                "text": value,
                                "insertionIndex": 0,
                            }})
                            filled += 1

            self._batch_update(presentation_id, requests)
            result_dict = {
                "presentationId": presentation_id,
                "slideObjectId": page_id,
                "objectId": table_id,
                "status": "ok",
            }
            if data is not None:
                result_dict["filled_cells"] = filled
            return result_dict
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
        color: str | None = None, alignment: str | None = None,
        start: int | None = None, end: int | None = None,
    ) -> dict:
        """Apply text + paragraph styling to a shape's text.

        Styles the whole shape's text by default; pass start/end for a range.
        ``color`` accepts hex (#RRGGBB) or a theme name (see _parse_color).
        ``alignment`` (START/CENTER/END/JUSTIFIED) sets paragraph alignment.

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

        if not fields and alignment is None:
            return {"presentationId": presentation_id, "objectId": object_id,
                    "status": "ok", "note": "no styles specified"}

        if start is not None and end is not None:
            text_range = {"type": "FIXED_RANGE", "startIndex": start, "endIndex": end}
        else:
            text_range = {"type": "ALL"}

        requests: list[dict] = []
        if fields:
            requests.append({"updateTextStyle": {
                "objectId": object_id,
                "style": style,
                "textRange": text_range,
                "fields": ",".join(fields),
            }})
        if alignment is not None:
            requests.append({"updateParagraphStyle": {
                "objectId": object_id,
                "style": {"alignment": alignment},
                "textRange": text_range,
                "fields": "alignment",
            }})

        try:
            self._batch_update(presentation_id, requests)
            return {"presentationId": presentation_id, "objectId": object_id, "status": "ok"}
        except HttpError as error:
            raise RuntimeError(f"Slides API error: {error}")

    def format_element(
        self, presentation_id: str, object_id: str,
        fill: str | None = None, outline: str | None = None,
        outline_weight: float | None = None, valign: str | None = None,
    ) -> dict:
        """Apply fill/outline (and vertical text alignment) to a shape or image.

        Shapes get a background fill + outline + content (vertical) alignment;
        images get an outline only (the API has no image fill or content
        alignment). Dispatches by the element's actual type.

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
                if valign is not None:
                    props["contentAlignment"] = valign
                    fields.append("contentAlignment")
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
                if valign is not None:
                    raise ValueError("Images have no content alignment; --valign is shape-only.")
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
        """Build an ABSOLUTE updatePageElementTransform placing element in box.

        Shapes/images are scaled to fill the box (scale = target / base). Tables
        reject scaled transforms (their size is row/column-driven), so a table is
        **moved** to the box origin at scale 1 — repositioned, not resized.
        Raises RuntimeError if a non-table element has no resolvable size.
        """
        object_id = element.get("objectId", "")
        box_x, box_y, box_w, box_h = box

        if "table" in element:
            scale_x = scale_y = 1
        else:
            size = element.get("size", {})
            base_w = self._dimension_pt(size.get("width"), 0.0)
            base_h = self._dimension_pt(size.get("height"), 0.0)
            if base_w <= 0 or base_h <= 0:
                raise RuntimeError(
                    f"Cannot place object {object_id}: it has no resolvable size."
                )
            scale_x, scale_y = box_w / base_w, box_h / base_h

        return {
            "updatePageElementTransform": {
                "objectId": object_id,
                "applyMode": "ABSOLUTE",
                "transform": {
                    "scaleX": scale_x, "scaleY": scale_y,
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
