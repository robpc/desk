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
    ) -> dict:
        """Insert an image onto a slide from a public URL.

        Args:
            presentation_id: The presentation ID
            slide: Target slide as 0-based index or objectId
            url: Publicly accessible image URL
            x, y: Top-left position in points (default ~50,50)
            width, height: Size in points (default 300x200)

        Returns:
            Dict with presentationId, slideObjectId, objectId (the image), status.
        """
        try:
            page_id = self._resolve_slide_object_id(presentation_id, slide)
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
    ) -> dict:
        """Insert a table onto a slide.

        Args:
            presentation_id: The presentation ID
            slide: Target slide as 0-based index or objectId
            rows: Number of rows
            columns: Number of columns
            x, y: Top-left position in points (default ~50,50)
            width, height: Size in points; when omitted the API sizes the table

        Returns:
            Dict with presentationId, slideObjectId, objectId (the table), status.
        """
        try:
            page_id = self._resolve_slide_object_id(presentation_id, slide)
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
    ) -> dict:
        """Insert a shape (default text box) onto a slide, optionally with text.

        When ``text`` is given, the shape is created with a client-supplied
        objectId and the text inserted in the same batchUpdate, so a labelled
        box is one round-trip. See ADR-027.

        Returns:
            Dict with presentationId, slideObjectId, objectId (the shape), status.
        """
        try:
            page_id = self._resolve_slide_object_id(presentation_id, slide)
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
            return self._drive.files().export(
                fileId=presentation_id, mimeType=mime, supportsAllDrives=True
            ).execute()
        except HttpError as error:
            raise RuntimeError(f"Slides API error: {error}")
