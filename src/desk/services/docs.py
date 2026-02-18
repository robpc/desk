"""Google Docs API wrapper."""

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError


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

    def create(self, title: str, body: str = "") -> dict:
        """Create a new Google Doc.

        Args:
            title: Document title
            body: Optional initial text content

        Returns:
            Dict with documentId, title, and webViewLink
        """
        try:
            doc = self.service.documents().create(body={"title": title}).execute()
            doc_id = doc["documentId"]

            if body:
                self.service.documents().batchUpdate(
                    documentId=doc_id,
                    body={"requests": [{"insertText": {"location": {"index": 1}, "text": body}}]},
                ).execute()

            # Get the web link from Drive
            meta = self._drive.files().get(fileId=doc_id, fields="webViewLink").execute()

            return {
                "documentId": doc_id,
                "title": title,
                "webViewLink": meta.get("webViewLink", ""),
            }
        except HttpError as error:
            raise RuntimeError(f"Docs API error: {error}")

    def read(self, document_id: str) -> dict:
        """Read a document and return its content as markdown-ish text.

        Args:
            document_id: The document ID

        Returns:
            Dict with title, documentId, and body text
        """
        try:
            doc = self.service.documents().get(documentId=document_id).execute()
            title = doc.get("title", "")
            body = self._extract_text(doc)
            return {
                "documentId": document_id,
                "title": title,
                "body": body,
            }
        except HttpError as error:
            raise RuntimeError(f"Docs API error: {error}")

    def update(self, document_id: str, text: str, mode: str = "append") -> dict:
        """Insert or replace text in a document.

        Args:
            document_id: The document ID
            text: Text content to insert
            mode: "append" (end), "prepend" (beginning), or "replace" (replace all)

        Returns:
            Dict with documentId and status
        """
        try:
            if mode == "replace":
                # Get current document to find end index
                doc = self.service.documents().get(documentId=document_id).execute()
                body = doc.get("body", {})
                content = body.get("content", [])
                end_index = content[-1]["endIndex"] if content else 1

                requests = []
                # Delete existing content (leave the trailing newline)
                if end_index > 2:
                    requests.append(
                        {
                            "deleteContentRange": {
                                "range": {"startIndex": 1, "endIndex": end_index - 1}
                            }
                        }
                    )
                # Insert new text at beginning
                requests.append({"insertText": {"location": {"index": 1}, "text": text}})
            elif mode == "prepend":
                requests = [{"insertText": {"location": {"index": 1}, "text": text}}]
            else:  # append
                doc = self.service.documents().get(documentId=document_id).execute()
                body = doc.get("body", {})
                content = body.get("content", [])
                end_index = content[-1]["endIndex"] if content else 1
                # Insert before the trailing newline
                insert_index = max(1, end_index - 1)
                requests = [{"insertText": {"location": {"index": insert_index}, "text": text}}]

            self.service.documents().batchUpdate(
                documentId=document_id,
                body={"requests": requests},
            ).execute()

            return {"documentId": document_id, "mode": mode, "status": "ok"}
        except HttpError as error:
            raise RuntimeError(f"Docs API error: {error}")

    def find_and_replace(
        self, document_id: str, find_text: str, replace_text: str, match_case: bool = True
    ) -> dict:
        """Find and replace all occurrences of text in a document.

        Uses the Google Docs API's ReplaceAllTextRequest, which preserves formatting.

        Args:
            document_id: The document ID
            find_text: Text to search for
            replace_text: Replacement text
            match_case: Whether the search is case-sensitive (default True)

        Returns:
            Dict with documentId, occurrences_changed, and status
        """
        try:
            result = self.service.documents().batchUpdate(
                documentId=document_id,
                body={
                    "requests": [
                        {
                            "replaceAllText": {
                                "containsText": {
                                    "text": find_text,
                                    "matchCase": match_case,
                                },
                                "replaceText": replace_text,
                            }
                        }
                    ]
                },
            ).execute()

            # Extract occurrences changed from the reply
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

    def insert_at(self, document_id: str, text: str, index: int | None = None) -> dict:
        """Insert text at a specific index or end of document.

        Args:
            document_id: The document ID
            text: Text to insert
            index: 1-based character index, or None for end of document

        Returns:
            Dict with documentId and status
        """
        from desk.services.docs_editing import normalize_text

        text = normalize_text(text)
        try:
            if index is None:
                request = {"insertText": {
                    "endOfSegmentLocation": {},
                    "text": text,
                }}
            else:
                request = {"insertText": {
                    "location": {"index": index},
                    "text": text,
                }}

            self.service.documents().batchUpdate(
                documentId=document_id,
                body={"requests": [request]},
            ).execute()

            return {"documentId": document_id, "status": "ok"}
        except HttpError as error:
            raise RuntimeError(f"Docs API error: {error}")

    def delete_range(self, document_id: str, start_index: int, end_index: int) -> dict:
        """Delete content between start and end indices.

        Args:
            document_id: The document ID
            start_index: Start index (1-based, inclusive)
            end_index: End index (exclusive)

        Returns:
            Dict with documentId and status
        """
        try:
            self.service.documents().batchUpdate(
                documentId=document_id,
                body={"requests": [{
                    "deleteContentRange": {
                        "range": {"startIndex": start_index, "endIndex": end_index}
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
                        "range": {"startIndex": start_index, "endIndex": end_index},
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
    ) -> dict:
        """Apply paragraph styling to a range.

        Args:
            document_id: The document ID
            start_index: Start of range
            end_index: End of range
            heading: Heading level 1-6, or 0 for normal text
            alignment: "START", "CENTER", "END", "JUSTIFIED"

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
                        "range": {"startIndex": start_index, "endIndex": end_index},
                        "paragraphStyle": style,
                        "fields": ",".join(fields_list),
                    }
                }]},
            ).execute()

            return {"documentId": document_id, "status": "ok"}
        except HttpError as error:
            raise RuntimeError(f"Docs API error: {error}")

    def insert_table(
        self, document_id: str, rows: int, columns: int, index: int | None = None
    ) -> dict:
        """Insert a table at a specific index or end of document.

        Args:
            document_id: The document ID
            rows: Number of rows
            columns: Number of columns
            index: 1-based index, or None for end of document

        Returns:
            Dict with documentId and status
        """
        try:
            if index is None:
                location = {"endOfSegmentLocation": {}}
            else:
                location = {"location": {"index": index}}

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
    ) -> dict:
        """Insert an inline image.

        Args:
            document_id: The document ID
            uri: Public URL of the image
            index: 1-based index, or None for end of document
            width: Image width in points
            height: Image height in points

        Returns:
            Dict with documentId and status
        """
        try:
            if index is None:
                location = {"endOfSegmentLocation": {}}
            else:
                location = {"location": {"index": index}}

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
        self, document_id: str, markdown: str, index: int | None = None, replace: bool = False
    ) -> dict:
        """Write markdown content with native Docs formatting.

        Args:
            document_id: The document ID
            markdown: Markdown source text
            index: Insert at this index, or None for end of document
            replace: If True, replace entire document content

        Returns:
            Dict with documentId and status
        """
        from desk.services.markdown_to_docs import markdown_to_requests

        try:
            if replace:
                # Fetch doc to get end index for deletion
                doc = self.service.documents().get(documentId=document_id).execute()
                body = doc.get("body", {})
                content = body.get("content", [])
                end_index = content[-1]["endIndex"] if content else 1

                requests: list[dict] = []
                if end_index > 2:
                    requests.append({
                        "deleteContentRange": {
                            "range": {"startIndex": 1, "endIndex": end_index - 1}
                        }
                    })
                # After deletion, insert at index 1
                requests.extend(markdown_to_requests(markdown, base_index=1))
            elif index is not None:
                requests = markdown_to_requests(markdown, base_index=index)
            else:
                # Append: need doc length for style offsets
                doc = self.service.documents().get(documentId=document_id).execute()
                body = doc.get("body", {})
                content = body.get("content", [])
                end_index = content[-1]["endIndex"] if content else 1
                insert_index = max(1, end_index - 1)
                requests = markdown_to_requests(markdown, base_index=insert_index)

            if requests:
                self.service.documents().batchUpdate(
                    documentId=document_id,
                    body={"requests": requests},
                ).execute()

            return {"documentId": document_id, "status": "ok"}
        except HttpError as error:
            raise RuntimeError(f"Docs API error: {error}")

    def inspect(self, document_id: str) -> dict:
        """Inspect document structure with indices.

        Returns document elements with their start/end indices so agents
        can plan index-based edits.

        Args:
            document_id: The document ID

        Returns:
            Dict with documentId, title, and elements list
        """
        try:
            doc = self.service.documents().get(documentId=document_id).execute()
            title = doc.get("title", "")
            body = doc.get("body", {})
            elements = []

            for element in body.get("content", []):
                start = element.get("startIndex", 0)
                end = element.get("endIndex", 0)

                if "paragraph" in element:
                    para = element["paragraph"]
                    style = para.get("paragraphStyle", {})
                    named_style = style.get("namedStyleType", "NORMAL_TEXT")
                    text = self._extract_paragraph_text(para).rstrip("\n")
                    elements.append({
                        "type": "paragraph",
                        "startIndex": start,
                        "endIndex": end,
                        "style": named_style,
                        "text": text[:200],  # Truncate for readability
                    })
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
            return self._drive.files().export(fileId=document_id, mimeType=mime).execute()
        except HttpError as error:
            raise RuntimeError(f"Docs API error: {error}")

    def _extract_text(self, doc: dict) -> str:
        """Extract text from a Google Docs document structure.

        Handles paragraphs and tables. Tables are formatted as markdown tables.
        """
        parts = []
        body = doc.get("body", {})
        for element in body.get("content", []):
            if "paragraph" in element:
                parts.append(self._extract_paragraph_text(element["paragraph"]))
            elif "table" in element:
                parts.append(self._extract_table_text(element["table"]))
        return "".join(parts)

    def _extract_paragraph_text(self, paragraph: dict) -> str:
        """Extract text from a paragraph element."""
        parts = []
        for pe in paragraph.get("elements", []):
            if "textRun" in pe:
                parts.append(pe["textRun"].get("content", ""))
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

        # Determine column count from widest row
        col_count = max(len(r) for r in rows)

        lines = []
        for i, row in enumerate(rows):
            # Pad row to match column count
            while len(row) < col_count:
                row.append("")
            lines.append("| " + " | ".join(row) + " |")
            if i == 0:
                lines.append("| " + " | ".join("---" for _ in range(col_count)) + " |")
        return "\n".join(lines) + "\n"
