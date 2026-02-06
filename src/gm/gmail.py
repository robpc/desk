"""Gmail API wrapper."""

from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from google.oauth2.credentials import Credentials


class GmailClient:
    """Client for Gmail API operations."""

    def __init__(self, credentials: Credentials):
        self.service = build("gmail", "v1", credentials=credentials)
        self.user_id = "me"

    def search(self, query: str, max_results: int = 20) -> list[dict]:
        """Search for messages matching query.

        Args:
            query: Gmail search query (same syntax as Gmail search box)
            max_results: Maximum number of results to return

        Returns:
            List of message summaries with id, threadId, snippet
        """
        try:
            results = self.service.users().messages().list(
                userId=self.user_id,
                q=query,
                maxResults=max_results
            ).execute()

            messages = results.get("messages", [])

            # Fetch snippets for each message
            detailed = []
            for msg in messages:
                detail = self.service.users().messages().get(
                    userId=self.user_id,
                    id=msg["id"],
                    format="metadata",
                    metadataHeaders=["From", "Subject", "Date"]
                ).execute()
                detailed.append(self._parse_message_metadata(detail))

            return detailed

        except HttpError as error:
            raise RuntimeError(f"Gmail API error: {error}")

    def read(self, message_id: str) -> dict:
        """Read a full message by ID.

        Returns:
            Message with full content
        """
        try:
            message = self.service.users().messages().get(
                userId=self.user_id,
                id=message_id,
                format="full"
            ).execute()
            return self._parse_full_message(message)
        except HttpError as error:
            raise RuntimeError(f"Gmail API error: {error}")

    def list_labels(self) -> list[dict]:
        """List all labels in the mailbox."""
        try:
            results = self.service.users().labels().list(userId=self.user_id).execute()
            return results.get("labels", [])
        except HttpError as error:
            raise RuntimeError(f"Gmail API error: {error}")

    def add_label(self, message_id: str, label_name: str) -> None:
        """Add a label to a message."""
        # First, find or create the label
        label_id = self._get_label_id(label_name)
        if not label_id:
            raise ValueError(f"Label not found: {label_name}")

        try:
            self.service.users().messages().modify(
                userId=self.user_id,
                id=message_id,
                body={"addLabelIds": [label_id]}
            ).execute()
        except HttpError as error:
            raise RuntimeError(f"Gmail API error: {error}")

    def archive(self, message_id: str) -> None:
        """Archive a message (remove from inbox)."""
        self.modify(message_id, remove_labels=["INBOX"])

    def mark_read(self, message_id: str) -> None:
        """Mark a message as read."""
        self.modify(message_id, remove_labels=["UNREAD"])

    def trash(self, message_id: str) -> None:
        """Move a message to trash."""
        self.modify(message_id, add_labels=["TRASH"], remove_labels=["INBOX"])

    def star(self, message_id: str) -> None:
        """Star a message."""
        self.modify(message_id, add_labels=["STARRED"])

    def unstar(self, message_id: str) -> None:
        """Remove star from a message."""
        self.modify(message_id, remove_labels=["STARRED"])

    def remove_label(self, message_id: str, label_name: str) -> None:
        """Remove a label from a message."""
        label_id = self._get_label_id(label_name)
        if not label_id:
            # Try as system label
            label_id = self._resolve_label(label_name)
        self.modify(message_id, remove_labels=[label_id])

    def modify(
        self,
        message_id: str,
        add_labels: list[str] | None = None,
        remove_labels: list[str] | None = None,
    ) -> None:
        """Modify message labels (generic operation).

        Args:
            message_id: The message ID
            add_labels: Label IDs or names to add
            remove_labels: Label IDs or names to remove
        """
        body = {}

        if add_labels:
            # Resolve label names to IDs for user labels
            body["addLabelIds"] = [self._resolve_label(l) for l in add_labels]

        if remove_labels:
            body["removeLabelIds"] = [self._resolve_label(l) for l in remove_labels]

        if not body:
            return  # Nothing to do

        try:
            self.service.users().messages().modify(
                userId=self.user_id,
                id=message_id,
                body=body,
            ).execute()
        except HttpError as error:
            raise RuntimeError(f"Gmail API error: {error}")

    def _resolve_label(self, label: str) -> str:
        """Resolve a label name to its ID. System labels are returned as-is."""
        # System labels are uppercase and can be used directly
        system_labels = [
            "INBOX", "SPAM", "TRASH", "UNREAD", "STARRED", "IMPORTANT",
            "SENT", "DRAFT", "CATEGORY_PERSONAL", "CATEGORY_SOCIAL",
            "CATEGORY_PROMOTIONS", "CATEGORY_UPDATES", "CATEGORY_FORUMS",
        ]
        if label.upper() in system_labels:
            return label.upper()

        # User label - look up ID
        label_id = self._get_label_id(label)
        if label_id:
            return label_id

        # Return as-is and let API error if invalid
        return label

    def _get_label_id(self, label_name: str) -> str | None:
        """Get label ID by name."""
        labels = self.list_labels()
        for label in labels:
            if label["name"].lower() == label_name.lower():
                return label["id"]
        return None

    def _parse_message_metadata(self, msg: dict) -> dict:
        """Parse message metadata into clean dict."""
        headers = {h["name"]: h["value"] for h in msg.get("payload", {}).get("headers", [])}
        return {
            "id": msg["id"],
            "threadId": msg["threadId"],
            "snippet": msg.get("snippet", ""),
            "from": headers.get("From", ""),
            "subject": headers.get("Subject", ""),
            "date": headers.get("Date", ""),
            "labelIds": msg.get("labelIds", []),
        }

    def _parse_full_message(self, msg: dict) -> dict:
        """Parse full message including body."""
        metadata = self._parse_message_metadata(msg)
        metadata["body"] = self._extract_body(msg.get("payload", {}))
        return metadata

    def _extract_body(self, payload: dict) -> str:
        """Extract message body from payload."""
        import base64

        # Simple case: body directly in payload
        if "body" in payload and payload["body"].get("data"):
            return base64.urlsafe_b64decode(payload["body"]["data"]).decode("utf-8")

        # Multipart: find text/plain part
        if "parts" in payload:
            for part in payload["parts"]:
                if part.get("mimeType") == "text/plain":
                    if part.get("body", {}).get("data"):
                        return base64.urlsafe_b64decode(part["body"]["data"]).decode("utf-8")
                # Recurse into nested parts
                if "parts" in part:
                    body = self._extract_body(part)
                    if body:
                        return body

        return ""
