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
