"""Google Docs API wrapper."""

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from desk.links import format_markdown_link


class DocsClient:
    """Client for Google Docs API operations."""

    def __init__(self, credentials: Credentials):
        self.credentials = credentials
        self.service = build("docs", "v1", credentials=credentials)
        # Drive API needed for webViewLink (create) and export (PDF/TXT/DOCX)
        # since Docs API doesn't provide these operations.
        # Lazy-loaded: read() and update() don't need it.
        self.__drive = None

    @property
    def _drive(self):
        if self.__drive is None:
            self.__drive = build("drive", "v3", credentials=self.credentials)
        return self.__drive

    # ── Helpers for tab-aware locations ─────────────────────────────────

    @staticmethod
    def _location(index: int, tab_id: str | None = None) -> dict:
        """Build a location object, optionally scoped to a tab."""
        loc = {"index": index}
        if tab_id:
            loc["tabId"] = tab_id
        return loc

    @staticmethod
    def _range(start: int, end: int, tab_id: str | None = None) -> dict:
        """Build a range object, optionally scoped to a tab."""
        r = {"startIndex": start, "endIndex": end}
        if tab_id:
            r["tabId"] = tab_id
        return r

    @staticmethod
    def _end_of_segment(tab_id: str | None = None) -> dict:
        """Build an endOfSegmentLocation, optionally scoped to a tab."""
        loc: dict = {}
        if tab_id:
            loc["tabId"] = tab_id
        return loc

    def _get_body(self, document_id: str, tab_id: str | None = None) -> tuple[dict, dict]:
        """Get a document and its body, optionally for a specific tab.

        Returns:
            Tuple of (full doc dict, body dict)
        """
        if tab_id:
            doc = self.service.documents().get(
                documentId=document_id, includeTabsContent=True
            ).execute()
            for tab in self._flatten_tabs(doc.get("tabs", [])):
                if tab.get("tabProperties", {}).get("tabId") == tab_id:
                    return doc, tab.get("documentTab", {}).get("body", {})
            raise RuntimeError(f"Tab not found: {tab_id}")
        else:
            doc = self.service.documents().get(documentId=document_id).execute()
            return doc, doc.get("body", {})

    @staticmethod
    def _flatten_tabs(tabs: list[dict]) -> list[dict]:
        """Flatten a nested tab tree into a flat list."""
        result = []
        for tab in tabs:
            result.append(tab)
            result.extend(DocsClient._flatten_tabs(tab.get("childTabs", [])))
        return result

    # ── Tab management ──────────────────────────────────────────────────

    def list_tabs(self, document_id: str) -> list[dict]:
        """List all tabs in a document.

        Args:
            document_id: The document ID

        Returns:
            List of dicts with tabId, title, index, parentTabId
        """
        try:
            doc = self.service.documents().get(
                documentId=document_id, includeTabsContent=True
            ).execute()

            result = []
            for tab in self._flatten_tabs(doc.get("tabs", [])):
                props = tab.get("tabProperties", {})
                result.append({
                    "tabId": props.get("tabId", ""),
                    "title": props.get("title", ""),
                    "index": props.get("index", 0),
                    "parentTabId": props.get("parentTabId"),
                })
            return result
        except HttpError as error:
            raise RuntimeError(f"Docs API error: {error}")

    def add_tab(
        self, document_id: str, title: str,
        index: int | None = None, parent_tab_id: str | None = None,
    ) -> dict:
        """Create a new tab in a document.

        Args:
            document_id: The document ID
            title: Tab title
            index: Optional position index
            parent_tab_id: Optional parent tab ID for nesting

        Returns:
            Dict with tabId and title
        """
        try:
            request: dict = {"tabProperties": {"title": title}}
            if index is not None:
                request["tabProperties"]["index"] = index
            if parent_tab_id:
                request["parentTabId"] = parent_tab_id

            result = self.service.documents().batchUpdate(
                documentId=document_id,
                body={"requests": [{"createTab": request}]},
            ).execute()

            # Extract the new tab info from the reply
            replies = result.get("replies", [{}])
            tab_info = {}
            if replies:
                created = replies[0].get("createTab", {}).get("tab", {})
                props = created.get("tabProperties", {})
                tab_info = {
                    "tabId": props.get("tabId", ""),
                    "title": props.get("title", title),
                }

            return tab_info
        except HttpError as error:
            raise RuntimeError(f"Docs API error: {error}")

    def delete_tab(self, document_id: str, tab_id: str) -> dict:
        """Delete a tab from a document.

        Args:
            document_id: The document ID
            tab_id: The tab ID to delete

        Returns:
            Dict with documentId and status
        """
        try:
            self.service.documents().batchUpdate(
                documentId=document_id,
                body={"requests": [{"deleteTab": {"tabId": tab_id}}]},
            ).execute()

            return {"documentId": document_id, "status": "ok"}
        except HttpError as error:
            raise RuntimeError(f"Docs API error: {error}")

    def rename_tab(self, document_id: str, tab_id: str, title: str) -> dict:
        """Rename a tab.

        Args:
            document_id: The document ID
            tab_id: The tab ID to rename
            title: New title for the tab

        Returns:
            Dict with tabId and title
        """
        try:
            self.service.documents().batchUpdate(
                documentId=document_id,
                body={"requests": [{
                    "updateTabProperties": {
                        "tabProperties": {
                            "tabId": tab_id,
                            "title": title,
                        },
                        "fields": "title",
                    }
                }]},
            ).execute()

            return {"tabId": tab_id, "title": title}
        except HttpError as error:
            raise RuntimeError(f"Docs API error: {error}")

    # ── Document CRUD ───────────────────────────────────────────────────

    def create(self, title: str, body: str = "", markdown: bool = True) -> dict:
        """Create a new Google Doc.

        Args:
            title: Document title
            body: Optional initial content
            markdown: If True (default), process body as markdown with native
                     formatting. If False, insert as plain text.

        Returns:
            Dict with documentId, title, and webViewLink
        """
        try:
            doc = self.service.documents().create(body={"title": title}).execute()
            doc_id = doc["documentId"]

            if body:
                if markdown:
                    self.write_markdown(doc_id, body, replace=True)
                else:
                    self.service.documents().batchUpdate(
                        documentId=doc_id,
                        body={"requests": [{
                            "insertText": {"location": {"index": 1}, "text": body}
                        }]},
                    ).execute()

            # Get the web link from Drive
            meta = self._drive.files().get(
                fileId=doc_id, fields="webViewLink", supportsAllDrives=True
            ).execute()

            return {
                "documentId": doc_id,
                "title": title,
                "webViewLink": meta.get("webViewLink", ""),
            }
        except HttpError as error:
            raise RuntimeError(f"Docs API error: {error}")

    def read(self, document_id: str, tab_id: str | None = None) -> dict:
        """Read a document and return its content as markdown-ish text.

        Args:
            document_id: The document ID
            tab_id: Optional tab ID to read from

        Returns:
            Dict with title, documentId, and body text
        """
        try:
            doc, body = self._get_body(document_id, tab_id)
            title = doc.get("title", "")
            text = self._extract_text_from_body(body)
            return {
                "documentId": document_id,
                "title": title,
                "body": text,
            }
        except HttpError as error:
            raise RuntimeError(f"Docs API error: {error}")

    def update(
        self, document_id: str, text: str, mode: str = "append",
        tab_id: str | None = None,
    ) -> dict:
        """Insert or replace text in a document.

        Args:
            document_id: The document ID
            text: Text content to insert
            mode: "append" (end), "prepend" (beginning), or "replace" (replace all)
            tab_id: Optional tab ID to target

        Returns:
            Dict with documentId and status
        """
        try:

            if mode == "replace":
                _, body = self._get_body(document_id, tab_id)
                content = body.get("content", [])
                end_index = content[-1]["endIndex"] if content else 1

                requests = []
                if end_index > 2:
                    requests.append({
                        "deleteContentRange": {
                            "range": self._range(1, end_index - 1, tab_id)
                        }
                    })
                requests.append({"insertText": {
                    "location": self._location(1, tab_id),
                    "text": text,
                }})
            elif mode == "prepend":
                requests = [{"insertText": {
                    "location": self._location(1, tab_id),
                    "text": text,
                }}]
            else:  # append
                _, body = self._get_body(document_id, tab_id)
                content = body.get("content", [])
                end_index = content[-1]["endIndex"] if content else 1
                insert_index = max(1, end_index - 1)
                requests = [{"insertText": {
                    "location": self._location(insert_index, tab_id),
                    "text": text,
                }}]

            self.service.documents().batchUpdate(
                documentId=document_id,
                body={"requests": requests},
            ).execute()

            return {"documentId": document_id, "mode": mode, "status": "ok"}
        except HttpError as error:
            raise RuntimeError(f"Docs API error: {error}")

    def find_and_replace(
        self, document_id: str, find_text: str, replace_text: str,
        match_case: bool = True, tab_id: str | None = None,
    ) -> dict:
        """Find and replace all occurrences of text in a document.

        Args:
            document_id: The document ID
            find_text: Text to search for
            replace_text: Replacement text
            match_case: Whether the search is case-sensitive (default True)
            tab_id: Optional tab ID to scope the search

        Returns:
            Dict with documentId, occurrences_changed, and status
        """
        try:

            request: dict = {
                "containsText": {
                    "text": find_text,
                    "matchCase": match_case,
                },
                "replaceText": replace_text,
            }
            if tab_id:
                request["tabsCriteria"] = {"tabIds": [tab_id]}

            result = self.service.documents().batchUpdate(
                documentId=document_id,
                body={"requests": [{"replaceAllText": request}]},
            ).execute()

            replies = result.get("replies", [{}])
            occurrences = 0
            if replies:
                occurrences = replies[0].get("replaceAllText", {}).get(
                    "occurrencesChanged", 0
                )

            return {
                "documentId": document_id,
                "occurrences_changed": occurrences,
                "status": "ok",
            }
        except HttpError as error:
            raise RuntimeError(f"Docs API error: {error}")

    def find_paragraph_boundary(
        self, document_id: str, index: int, position: str = "after",
        tab_id: str | None = None,
    ) -> int:
        """Find a paragraph boundary near the given index.

        Args:
            document_id: The document ID
            index: A character index within the target paragraph
            position: "after" to get the end of the paragraph (insert point
                     for adding content after it), or "before" to get the
                     start of the paragraph.
            tab_id: Optional tab ID

        Returns:
            The resolved insertion index at the paragraph boundary.

        Raises:
            RuntimeError: If no paragraph contains the given index.
        """
        _, body = self._get_body(document_id, tab_id)
        for element in body.get("content", []):
            if "paragraph" not in element:
                continue
            start = element.get("startIndex", 0)
            end = element.get("endIndex", 0)
            if start <= index < end:
                if position == "before":
                    return start
                else:
                    return end
        raise RuntimeError(
            f"No paragraph found containing index {index}. "
            "Use 'desk docs inspect' to see valid indices."
        )

    def insert_at(
        self, document_id: str, text: str, index: int | None = None,
        tab_id: str | None = None,
    ) -> dict:
        """Insert text at a specific index or end of document.

        Args:
            document_id: The document ID
            text: Text to insert
            index: 1-based character index, or None for end of document
            tab_id: Optional tab ID to target

        Returns:
            Dict with documentId and status
        """
        from desk.services.docs_editing import normalize_text

        text = normalize_text(text)
        try:

            if index is None:
                request = {"insertText": {
                    "endOfSegmentLocation": self._end_of_segment(tab_id),
                    "text": text,
                }}
            else:
                request = {"insertText": {
                    "location": self._location(index, tab_id),
                    "text": text,
                }}

            self.service.documents().batchUpdate(
                documentId=document_id,
                body={"requests": [request]},
            ).execute()

            return {"documentId": document_id, "status": "ok"}
        except HttpError as error:
            raise RuntimeError(f"Docs API error: {error}")

    def delete_range(
        self, document_id: str, start_index: int, end_index: int,
        tab_id: str | None = None,
    ) -> dict:
        """Delete content between start and end indices.

        Args:
            document_id: The document ID
            start_index: Start index (1-based, inclusive)
            end_index: End index (exclusive)
            tab_id: Optional tab ID to target

        Returns:
            Dict with documentId and status
        """
        try:

            self.service.documents().batchUpdate(
                documentId=document_id,
                body={"requests": [{
                    "deleteContentRange": {
                        "range": self._range(start_index, end_index, tab_id)
                    }
                }]},
            ).execute()

            return {"documentId": document_id, "status": "ok"}
        except HttpError as error:
            raise RuntimeError(f"Docs API error: {error}")

    def update_text_style(
        self,
        document_id: str,
        start_index: int,
        end_index: int,
        bold: bool | None = None,
        italic: bool | None = None,
        code: bool | None = None,
        link_url: str | None = None,
        font_size: float | None = None,
        underline: bool | None = None,
        strikethrough: bool | None = None,
        font_family: str | None = None,
        tab_id: str | None = None,
    ) -> dict:
        """Apply text styling to a range.

        Args:
            document_id: The document ID
            start_index: Start of range
            end_index: End of range
            bold: Set bold
            italic: Set italic
            code: Set monospace font (Courier New)
            link_url: Set hyperlink
            font_size: Set font size in points
            underline: Set underline
            strikethrough: Set strikethrough
            font_family: Set font family name
            tab_id: Optional tab ID to target

        Returns:
            Dict with documentId and status
        """
        style: dict = {}
        fields_list: list[str] = []

        if bold is not None:
            style["bold"] = bold
            fields_list.append("bold")
        if italic is not None:
            style["italic"] = italic
            fields_list.append("italic")
        if underline is not None:
            style["underline"] = underline
            fields_list.append("underline")
        if strikethrough is not None:
            style["strikethrough"] = strikethrough
            fields_list.append("strikethrough")
        if code is not None and code:
            style["weightedFontFamily"] = {"fontFamily": "Courier New"}
            fields_list.append("weightedFontFamily")
        elif font_family is not None:
            style["weightedFontFamily"] = {"fontFamily": font_family}
            fields_list.append("weightedFontFamily")
        if link_url is not None:
            style["link"] = {"url": link_url}
            fields_list.append("link")
        if font_size is not None:
            style["fontSize"] = {"magnitude": font_size, "unit": "PT"}
            fields_list.append("fontSize")

        if not fields_list:
            return {"documentId": document_id, "status": "ok", "note": "no styles specified"}

        try:

            self.service.documents().batchUpdate(
                documentId=document_id,
                body={"requests": [{
                    "updateTextStyle": {
                        "range": self._range(start_index, end_index, tab_id),
                        "textStyle": style,
                        "fields": ",".join(fields_list),
                    }
                }]},
            ).execute()

            return {"documentId": document_id, "status": "ok"}
        except HttpError as error:
            raise RuntimeError(f"Docs API error: {error}")

    def update_paragraph_style(
        self,
        document_id: str,
        start_index: int,
        end_index: int,
        heading: int | None = None,
        alignment: str | None = None,
        tab_id: str | None = None,
    ) -> dict:
        """Apply paragraph styling to a range.

        Args:
            document_id: The document ID
            start_index: Start of range
            end_index: End of range
            heading: Heading level 1-6, or 0 for normal text
            alignment: "START", "CENTER", "END", "JUSTIFIED"
            tab_id: Optional tab ID to target

        Returns:
            Dict with documentId and status
        """
        style: dict = {}
        fields_list: list[str] = []

        if heading is not None:
            if heading == 0:
                style["namedStyleType"] = "NORMAL_TEXT"
            else:
                style["namedStyleType"] = f"HEADING_{heading}"
            fields_list.append("namedStyleType")
        if alignment is not None:
            style["alignment"] = alignment
            fields_list.append("alignment")

        if not fields_list:
            return {"documentId": document_id, "status": "ok", "note": "no styles specified"}

        try:

            self.service.documents().batchUpdate(
                documentId=document_id,
                body={"requests": [{
                    "updateParagraphStyle": {
                        "range": self._range(start_index, end_index, tab_id),
                        "paragraphStyle": style,
                        "fields": ",".join(fields_list),
                    }
                }]},
            ).execute()

            return {"documentId": document_id, "status": "ok"}
        except HttpError as error:
            raise RuntimeError(f"Docs API error: {error}")

    def insert_table(
        self, document_id: str, rows: int, columns: int,
        index: int | None = None, tab_id: str | None = None,
    ) -> dict:
        """Insert a table at a specific index or end of document.

        Args:
            document_id: The document ID
            rows: Number of rows
            columns: Number of columns
            index: 1-based index, or None for end of document
            tab_id: Optional tab ID to target

        Returns:
            Dict with documentId and status
        """
        try:

            if index is None:
                location = {"endOfSegmentLocation": self._end_of_segment(tab_id)}
            else:
                location = {"location": self._location(index, tab_id)}

            self.service.documents().batchUpdate(
                documentId=document_id,
                body={"requests": [{
                    "insertTable": {**location, "rows": rows, "columns": columns}
                }]},
            ).execute()

            return {"documentId": document_id, "status": "ok"}
        except HttpError as error:
            raise RuntimeError(f"Docs API error: {error}")

    def insert_image(
        self,
        document_id: str,
        uri: str,
        index: int | None = None,
        width: float | None = None,
        height: float | None = None,
        tab_id: str | None = None,
    ) -> dict:
        """Insert an inline image.

        Args:
            document_id: The document ID
            uri: Public URL of the image
            index: 1-based index, or None for end of document
            width: Image width in points
            height: Image height in points
            tab_id: Optional tab ID to target

        Returns:
            Dict with documentId and status
        """
        try:

            if index is None:
                location = {"endOfSegmentLocation": self._end_of_segment(tab_id)}
            else:
                location = {"location": self._location(index, tab_id)}

            request: dict = {**location, "uri": uri}
            if width is not None or height is not None:
                size: dict = {}
                if width is not None:
                    size["width"] = {"magnitude": width, "unit": "PT"}
                if height is not None:
                    size["height"] = {"magnitude": height, "unit": "PT"}
                request["objectSize"] = size

            self.service.documents().batchUpdate(
                documentId=document_id,
                body={"requests": [{"insertInlineImage": request}]},
            ).execute()

            return {"documentId": document_id, "status": "ok"}
        except HttpError as error:
            raise RuntimeError(f"Docs API error: {error}")

    def write_markdown(
        self, document_id: str, markdown: str,
        index: int | None = None, replace: bool = False,
        tab_id: str | None = None,
    ) -> dict:
        """Write markdown content with native Docs formatting.

        Args:
            document_id: The document ID
            markdown: Markdown source text
            index: Insert at this index, or None for end of document
            replace: If True, replace entire document content
            tab_id: Optional tab ID to target

        Returns:
            Dict with documentId and status
        """
        from desk.services.markdown_to_docs import markdown_to_requests

        try:

            if replace:
                _, body = self._get_body(document_id, tab_id)
                content = body.get("content", [])
                end_index = content[-1]["endIndex"] if content else 1

                requests: list[dict] = []
                if end_index > 2:
                    requests.append({
                        "deleteContentRange": {
                            "range": self._range(1, end_index - 1, tab_id)
                        }
                    })
                requests.extend(markdown_to_requests(markdown, base_index=1, tab_id=tab_id))
            elif index is not None:
                requests = markdown_to_requests(markdown, base_index=index, tab_id=tab_id)
            else:
                _, body = self._get_body(document_id, tab_id)
                content = body.get("content", [])
                end_index = content[-1]["endIndex"] if content else 1
                insert_index = max(1, end_index - 1)
                requests = markdown_to_requests(markdown, base_index=insert_index, tab_id=tab_id)

            if requests:
                self.service.documents().batchUpdate(
                    documentId=document_id,
                    body={"requests": requests},
                ).execute()

            return {"documentId": document_id, "status": "ok"}
        except HttpError as error:
            raise RuntimeError(f"Docs API error: {error}")

    def inspect(self, document_id: str, tab_id: str | None = None) -> dict:
        """Inspect document structure with indices.

        Args:
            document_id: The document ID
            tab_id: Optional tab ID to inspect

        Returns:
            Dict with documentId, title, and elements list
        """
        try:
            doc, body = self._get_body(document_id, tab_id)
            title = doc.get("title", "")
            elements = []

            for element in body.get("content", []):
                start = element.get("startIndex", 0)
                end = element.get("endIndex", 0)

                if "paragraph" in element:
                    para = element["paragraph"]
                    style = para.get("paragraphStyle", {})
                    named_style = style.get("namedStyleType", "NORMAL_TEXT")
                    text = self._extract_paragraph_text(para).rstrip("\n")
                    elem_dict: dict = {
                        "type": "paragraph",
                        "startIndex": start,
                        "endIndex": end,
                        "style": named_style,
                        "text": text[:200],
                    }
                    if "bullet" in para:
                        elem_dict["bullet"] = True
                    has_hr_element = any(
                        "horizontalRule" in pe
                        for pe in para.get("elements", [])
                    )
                    has_border_hr = (
                        not text
                        and "borderBottom" in style
                    )
                    if has_hr_element or has_border_hr:
                        elem_dict["horizontalRule"] = True
                    elements.append(elem_dict)
                elif "table" in element:
                    table = element["table"]
                    rows = len(table.get("tableRows", []))
                    cols = 0
                    if rows > 0:
                        cols = len(table["tableRows"][0].get("tableCells", []))
                    elements.append({
                        "type": "table",
                        "startIndex": start,
                        "endIndex": end,
                        "rows": rows,
                        "columns": cols,
                    })
                elif "sectionBreak" in element:
                    elements.append({
                        "type": "sectionBreak",
                        "startIndex": start,
                        "endIndex": end,
                    })

            return {
                "documentId": document_id,
                "title": title,
                "endIndex": body.get("content", [{}])[-1].get("endIndex", 1)
                if body.get("content")
                else 1,
                "elements": elements,
            }
        except HttpError as error:
            raise RuntimeError(f"Docs API error: {error}")

    def export(self, document_id: str, fmt: str = "pdf") -> bytes:
        """Export a document to a different format.

        Args:
            document_id: The document ID
            fmt: Export format (pdf, txt, docx, html)

        Returns:
            File content as bytes
        """
        mime_map = {
            "pdf": "application/pdf",
            "txt": "text/plain",
            "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            "html": "text/html",
        }
        mime = mime_map.get(fmt)
        if not mime:
            raise RuntimeError(f"Unsupported format: {fmt}. Use: {', '.join(mime_map)}")

        try:
            return self._drive.files().export(
                fileId=document_id, mimeType=mime, supportsAllDrives=True
            ).execute()
        except HttpError as error:
            raise RuntimeError(f"Docs API error: {error}")

    # ── Text extraction helpers ─────────────────────────────────────────

    def _extract_text(self, doc: dict) -> str:
        """Extract text from a Google Docs document structure (legacy, default tab)."""
        return self._extract_text_from_body(doc.get("body", {}))

    def _extract_text_from_body(self, body: dict) -> str:
        """Extract text from a body dict. Handles paragraphs and tables.

        Bullet and numbered list items are prefixed with ``- `` or ``N. ``
        so that agents can distinguish list items from plain paragraphs.
        """
        parts = []
        ordered_counter = 0
        prev_list_id: str | None = None

        for element in body.get("content", []):
            if "paragraph" in element:
                para = element["paragraph"]
                text = self._extract_paragraph_text(para)
                bullet = para.get("bullet")
                if bullet:
                    list_id = bullet.get("listId", "")
                    nesting = bullet.get("nestingLevel", 0)
                    indent = "  " * nesting

                    # Detect ordered vs unordered from the list's glyphType.
                    # Google Docs stores list metadata at the document level
                    # under "lists", but we may not always have access to it
                    # from just the body.  Fall back to unordered when unknown.
                    glyph = (
                        bullet.get("listProperties", {})
                        .get("nestingLevels", [{}])[0]
                        .get("glyphType", "")
                        if "listProperties" in bullet
                        else ""
                    )
                    is_ordered = glyph.upper() in (
                        "DECIMAL", "ALPHA", "ROMAN",
                        "UPPER_ALPHA", "UPPER_ROMAN",
                    )

                    if is_ordered:
                        if list_id != prev_list_id:
                            ordered_counter = 1
                        else:
                            ordered_counter += 1
                        prefix = f"{indent}{ordered_counter}. "
                    else:
                        prefix = f"{indent}- "

                    # Prepend the bullet prefix to the first line
                    text = prefix + text.lstrip()
                    prev_list_id = list_id
                else:
                    prev_list_id = None
                    ordered_counter = 0

                parts.append(text)
            elif "table" in element:
                prev_list_id = None
                ordered_counter = 0
                parts.append(self._extract_table_text(element["table"]))
        return "".join(parts)

    def _extract_paragraph_text(self, paragraph: dict) -> str:
        """Extract text from a paragraph element.

        Hyperlinked text is emitted as ``[text](url)`` so that URLs
        are preserved in the output.  Smart chips (person mentions,
        rich links) are rendered inline.
        """
        parts = []
        for pe in paragraph.get("elements", []):
            if "textRun" in pe:
                run = pe["textRun"]
                content = run.get("content", "")
                link_url = run.get("textStyle", {}).get("link", {}).get("url")
                if link_url:
                    # Strip trailing newline from link text, re-append after
                    text = content.rstrip("\n")
                    trailing = content[len(text):]
                    parts.append(f"{format_markdown_link(text, link_url)}{trailing}")
                else:
                    parts.append(content)
            elif "person" in pe:
                props = pe["person"].get("personProperties", {})
                name = props.get("name", "").strip()
                email = props.get("email", "")
                display = name or email or "someone"
                parts.append(f"@{display}")
            elif "richLink" in pe:
                props = pe["richLink"].get("richLinkProperties", {})
                uri = props.get("uri", "")
                title = props.get("title", "").strip()
                if uri and title:
                    parts.append(format_markdown_link(title, uri))
                elif uri:
                    parts.append(uri)
        return "".join(parts)

    def _extract_table_text(self, table: dict) -> str:
        """Extract text from a table element, formatted as a markdown table."""
        rows = []
        for row in table.get("tableRows", []):
            cells = []
            for cell in row.get("tableCells", []):
                cell_parts = []
                for content in cell.get("content", []):
                    if "paragraph" in content:
                        cell_parts.append(
                            self._extract_paragraph_text(content["paragraph"])
                        )
                    elif "table" in content:
                        cell_parts.append(self._extract_table_text(content["table"]))
                text = " ".join(cell_parts).replace("\n", " ").strip()
                cells.append(text.replace("|", "\\|"))
            rows.append(cells)

        if not rows:
            return ""

        col_count = max(len(r) for r in rows)

        lines = []
        for i, row in enumerate(rows):
            while len(row) < col_count:
                row.append("")
            lines.append("| " + " | ".join(row) + " |")
            if i == 0:
                lines.append("| " + " | ".join("---" for _ in range(col_count)) + " |")
        return "\n".join(lines) + "\n"
