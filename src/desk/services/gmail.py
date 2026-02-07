"""Gmail API wrapper."""

import base64
from email.mime.text import MIMEText

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError


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
            results = (
                self.service.users()
                .messages()
                .list(userId=self.user_id, q=query, maxResults=max_results)
                .execute()
            )

            messages = results.get("messages", [])

            # Fetch snippets for each message
            detailed = []
            for msg in messages:
                detail = (
                    self.service.users()
                    .messages()
                    .get(
                        userId=self.user_id,
                        id=msg["id"],
                        format="metadata",
                        metadataHeaders=["From", "Subject", "Date"],
                    )
                    .execute()
                )
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
            message = (
                self.service.users()
                .messages()
                .get(userId=self.user_id, id=message_id, format="full")
                .execute()
            )
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

    def create_label(self, name: str) -> dict:
        """Create a new label.

        Args:
            name: Label name. Use "/" for nested labels (e.g., "Projects/Orion").

        Returns:
            The created label dict with id, name, etc.

        Raises:
            ValueError: If label already exists.
        """
        # Check if label already exists
        existing = self._get_label_id(name)
        if existing:
            raise ValueError(f"Label already exists: {name}")

        try:
            label = (
                self.service.users()
                .labels()
                .create(
                    userId=self.user_id,
                    body={
                        "name": name,
                        "labelListVisibility": "labelShow",
                        "messageListVisibility": "show",
                    },
                )
                .execute()
            )
            return label
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
                userId=self.user_id, id=message_id, body={"addLabelIds": [label_id]}
            ).execute()
        except HttpError as error:
            raise RuntimeError(f"Gmail API error: {error}")

    def archive(self, message_id: str) -> None:
        """Archive a message (remove from inbox)."""
        self.modify(message_id, remove_labels=["INBOX"])

    def mark_read(self, message_id: str) -> None:
        """Mark a message as read."""
        self.modify(message_id, remove_labels=["UNREAD"])

    def mark_unread(self, message_id: str) -> None:
        """Mark a message as unread."""
        self.modify(message_id, add_labels=["UNREAD"])

    def trash(self, message_id: str) -> None:
        """Move a message to trash."""
        self.modify(message_id, add_labels=["TRASH"], remove_labels=["INBOX"])

    def star(self, message_id: str) -> None:
        """Star a message."""
        self.modify(message_id, add_labels=["STARRED"])

    def unstar(self, message_id: str) -> None:
        """Remove star from a message."""
        self.modify(message_id, remove_labels=["STARRED"])

    def send(
        self,
        to: list[str],
        subject: str,
        body: str,
        cc: list[str] | None = None,
        bcc: list[str] | None = None,
    ) -> dict:
        """Send an email.

        Args:
            to: List of recipient email addresses
            subject: Email subject
            body: Plain text body
            cc: List of CC recipients
            bcc: List of BCC recipients

        Returns:
            The sent message metadata (id, threadId, labelIds)
        """
        # Build MIME message
        message = MIMEText(body)
        message["to"] = ", ".join(to)
        message["subject"] = subject

        if cc:
            message["cc"] = ", ".join(cc)
        if bcc:
            message["bcc"] = ", ".join(bcc)

        # Encode to base64
        raw = base64.urlsafe_b64encode(message.as_bytes()).decode("utf-8")

        try:
            result = (
                self.service.users()
                .messages()
                .send(userId=self.user_id, body={"raw": raw})
                .execute()
            )
            return result
        except HttpError as error:
            raise RuntimeError(f"Gmail API error: {error}")

    def reply(
        self,
        message_id: str,
        body: str,
        reply_all: bool = False,
    ) -> dict:
        """Reply to an email.

        Args:
            message_id: The message ID to reply to
            body: Plain text reply body
            reply_all: If True, reply to all recipients (To + CC)

        Returns:
            The sent message metadata
        """
        # Fetch original message
        original = self.read(message_id)

        # Determine reply recipient
        reply_to = original.get("replyTo") or original.get("from", "")
        to_addrs = [reply_to] if reply_to else []

        cc_addrs = []
        if reply_all:
            # Add original To recipients (excluding ourselves)
            if original.get("to"):
                to_addrs.extend(self._parse_addresses(original["to"]))
            # Add original CC recipients
            if original.get("cc"):
                cc_addrs = self._parse_addresses(original["cc"])

        # Build subject with Re: prefix
        subject = original.get("subject", "")
        if not subject.lower().startswith("re:"):
            subject = f"Re: {subject}"

        # Build MIME message with threading headers
        message = MIMEText(body)
        message["to"] = ", ".join(to_addrs)
        message["subject"] = subject

        if cc_addrs:
            message["cc"] = ", ".join(cc_addrs)

        # Set threading headers
        if original.get("messageId"):
            message["In-Reply-To"] = original["messageId"]
            refs = original.get("references", "")
            if refs:
                message["References"] = f"{refs} {original['messageId']}"
            else:
                message["References"] = original["messageId"]

        raw = base64.urlsafe_b64encode(message.as_bytes()).decode("utf-8")

        try:
            result = (
                self.service.users()
                .messages()
                .send(
                    userId=self.user_id,
                    body={"raw": raw, "threadId": original["threadId"]},
                )
                .execute()
            )
            return result
        except HttpError as error:
            raise RuntimeError(f"Gmail API error: {error}")

    def forward(
        self,
        message_id: str,
        to: list[str],
        body: str = "",
    ) -> dict:
        """Forward an email.

        Args:
            message_id: The message ID to forward
            to: List of recipient email addresses
            body: Optional additional message to include before forwarded content

        Returns:
            The sent message metadata
        """
        # Fetch original message
        original = self.read(message_id)

        # Build subject with Fwd: prefix
        subject = original.get("subject", "")
        if not subject.lower().startswith("fwd:"):
            subject = f"Fwd: {subject}"

        # Build forwarded body with quoted original
        original_body = original.get("body", "")
        forward_body = body
        if forward_body:
            forward_body += "\n\n"
        forward_body += "---------- Forwarded message ----------\n"
        forward_body += f"From: {original.get('from', '')}\n"
        forward_body += f"Date: {original.get('date', '')}\n"
        forward_body += f"Subject: {original.get('subject', '')}\n"
        forward_body += f"To: {original.get('to', '')}\n"
        if original.get("cc"):
            forward_body += f"Cc: {original['cc']}\n"
        forward_body += f"\n{original_body}"

        # Build MIME message
        message = MIMEText(forward_body)
        message["to"] = ", ".join(to)
        message["subject"] = subject

        raw = base64.urlsafe_b64encode(message.as_bytes()).decode("utf-8")

        try:
            result = (
                self.service.users()
                .messages()
                .send(userId=self.user_id, body={"raw": raw})
                .execute()
            )
            return result
        except HttpError as error:
            raise RuntimeError(f"Gmail API error: {error}")

    def _parse_addresses(self, addr_string: str) -> list[str]:
        """Parse comma-separated email addresses."""
        if not addr_string:
            return []
        return [addr.strip() for addr in addr_string.split(",") if addr.strip()]

    # -------------------------------------------------------------------------
    # Drafts
    # -------------------------------------------------------------------------

    def list_drafts(self, max_results: int = 20) -> list[dict]:
        """List drafts.

        Returns:
            List of draft summaries with id, message snippet, and headers
        """
        try:
            results = (
                self.service.users()
                .drafts()
                .list(userId=self.user_id, maxResults=max_results)
                .execute()
            )

            drafts = results.get("drafts", [])

            # Fetch details for each draft
            detailed = []
            for draft in drafts:
                detail = (
                    self.service.users()
                    .drafts()
                    .get(userId=self.user_id, id=draft["id"], format="metadata")
                    .execute()
                )
                msg = detail.get("message", {})
                headers = {
                    h["name"]: h["value"]
                    for h in msg.get("payload", {}).get("headers", [])
                }
                detailed.append({
                    "id": detail["id"],
                    "messageId": msg.get("id", ""),
                    "snippet": msg.get("snippet", ""),
                    "to": headers.get("To", ""),
                    "subject": headers.get("Subject", ""),
                })

            return detailed

        except HttpError as error:
            raise RuntimeError(f"Gmail API error: {error}")

    def create_draft(
        self,
        to: list[str],
        subject: str,
        body: str,
        cc: list[str] | None = None,
        bcc: list[str] | None = None,
    ) -> dict:
        """Create a draft email.

        Args:
            to: List of recipient email addresses
            subject: Email subject
            body: Plain text body
            cc: List of CC recipients
            bcc: List of BCC recipients

        Returns:
            The created draft with id
        """
        message = MIMEText(body)
        message["to"] = ", ".join(to)
        message["subject"] = subject

        if cc:
            message["cc"] = ", ".join(cc)
        if bcc:
            message["bcc"] = ", ".join(bcc)

        raw = base64.urlsafe_b64encode(message.as_bytes()).decode("utf-8")

        try:
            result = (
                self.service.users()
                .drafts()
                .create(userId=self.user_id, body={"message": {"raw": raw}})
                .execute()
            )
            return result
        except HttpError as error:
            raise RuntimeError(f"Gmail API error: {error}")

    def read_draft(self, draft_id: str) -> dict:
        """Read a draft by ID.

        Returns:
            Draft with full message content
        """
        try:
            draft = (
                self.service.users()
                .drafts()
                .get(userId=self.user_id, id=draft_id, format="full")
                .execute()
            )
            msg = draft.get("message", {})
            parsed = self._parse_full_message(msg)
            parsed["draftId"] = draft["id"]
            return parsed
        except HttpError as error:
            raise RuntimeError(f"Gmail API error: {error}")

    def send_draft(self, draft_id: str) -> dict:
        """Send a draft.

        Args:
            draft_id: The draft ID to send

        Returns:
            The sent message metadata
        """
        try:
            result = (
                self.service.users()
                .drafts()
                .send(userId=self.user_id, body={"id": draft_id})
                .execute()
            )
            return result
        except HttpError as error:
            raise RuntimeError(f"Gmail API error: {error}")

    def delete_draft(self, draft_id: str) -> None:
        """Delete a draft.

        Args:
            draft_id: The draft ID to delete
        """
        try:
            self.service.users().drafts().delete(
                userId=self.user_id, id=draft_id
            ).execute()
        except HttpError as error:
            raise RuntimeError(f"Gmail API error: {error}")

    def update_draft(
        self,
        draft_id: str,
        to: list[str] | None = None,
        subject: str | None = None,
        body: str | None = None,
        cc: list[str] | None = None,
        bcc: list[str] | None = None,
    ) -> dict:
        """Update a draft.

        Args:
            draft_id: The draft ID to update
            to: New recipients (if provided)
            subject: New subject (if provided)
            body: New body (if provided)
            cc: New CC recipients (if provided)
            bcc: New BCC recipients (if provided)

        Returns:
            The updated draft
        """
        # Fetch existing draft to preserve unchanged fields
        existing = self.read_draft(draft_id)

        # Use new values or fall back to existing
        final_to = to if to is not None else self._parse_addresses(existing.get("to", ""))
        final_subject = subject if subject is not None else existing.get("subject", "")
        final_body = body if body is not None else existing.get("body", "")
        final_cc = cc if cc is not None else (
            self._parse_addresses(existing.get("cc", "")) or None
        )
        final_bcc = bcc  # BCC not stored in existing, so only use if provided

        # Build new message
        message = MIMEText(final_body)
        message["to"] = ", ".join(final_to) if final_to else ""
        message["subject"] = final_subject

        if final_cc:
            message["cc"] = ", ".join(final_cc)
        if final_bcc:
            message["bcc"] = ", ".join(final_bcc)

        raw = base64.urlsafe_b64encode(message.as_bytes()).decode("utf-8")

        try:
            result = (
                self.service.users()
                .drafts()
                .update(
                    userId=self.user_id,
                    id=draft_id,
                    body={"message": {"raw": raw}},
                )
                .execute()
            )
            return result
        except HttpError as error:
            raise RuntimeError(f"Gmail API error: {error}")

    # -------------------------------------------------------------------------
    # Attachments
    # -------------------------------------------------------------------------

    def list_attachments(self, message_id: str) -> list[dict]:
        """List attachments for a message.

        Returns:
            List of attachment info dicts with filename, mimeType, size, attachmentId
        """
        try:
            message = (
                self.service.users()
                .messages()
                .get(userId=self.user_id, id=message_id, format="full")
                .execute()
            )
            return self._extract_attachments(message.get("payload", {}))
        except HttpError as error:
            raise RuntimeError(f"Gmail API error: {error}")

    def get_attachment(self, message_id: str, attachment_id: str) -> bytes:
        """Get attachment data by attachment ID.

        Returns:
            Raw attachment bytes
        """
        try:
            attachment = (
                self.service.users()
                .messages()
                .attachments()
                .get(userId=self.user_id, messageId=message_id, id=attachment_id)
                .execute()
            )
            data = attachment.get("data", "")
            return base64.urlsafe_b64decode(data)
        except HttpError as error:
            raise RuntimeError(f"Gmail API error: {error}")

    def get_attachment_by_filename(self, message_id: str, filename: str) -> bytes:
        """Get attachment data by filename.

        Args:
            message_id: The message ID
            filename: The attachment filename to find

        Returns:
            Raw attachment bytes

        Raises:
            ValueError: If attachment not found
        """
        attachments = self.list_attachments(message_id)
        for att in attachments:
            if att["filename"] == filename:
                return self.get_attachment(message_id, att["attachmentId"])

        available = [a["filename"] for a in attachments]
        raise ValueError(f"Attachment '{filename}' not found. Available: {available}")

    def _extract_attachments(self, payload: dict, attachments: list | None = None) -> list[dict]:
        """Recursively extract attachment info from message payload."""
        if attachments is None:
            attachments = []

        # Check if this part is an attachment
        filename = payload.get("filename", "")
        body = payload.get("body", {})
        attachment_id = body.get("attachmentId")

        if filename and attachment_id:
            attachments.append({
                "filename": filename,
                "mimeType": payload.get("mimeType", ""),
                "size": body.get("size", 0),
                "attachmentId": attachment_id,
            })

        # Recurse into parts
        for part in payload.get("parts", []):
            self._extract_attachments(part, attachments)

        return attachments

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
            body["addLabelIds"] = [self._resolve_label(lbl) for lbl in add_labels]

        if remove_labels:
            body["removeLabelIds"] = [self._resolve_label(lbl) for lbl in remove_labels]

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

    def batch_modify(
        self,
        message_ids: list[str],
        add_labels: list[str] | None = None,
        remove_labels: list[str] | None = None,
    ) -> None:
        """Batch modify labels on multiple messages.

        Uses Gmail's batchModify API for efficiency (single API call).

        Args:
            message_ids: List of message IDs
            add_labels: Label IDs or names to add
            remove_labels: Label IDs or names to remove
        """
        if not message_ids:
            return

        body = {"ids": message_ids}

        if add_labels:
            body["addLabelIds"] = [self._resolve_label(lbl) for lbl in add_labels]

        if remove_labels:
            body["removeLabelIds"] = [self._resolve_label(lbl) for lbl in remove_labels]

        if "addLabelIds" not in body and "removeLabelIds" not in body:
            return  # Nothing to do

        try:
            self.service.users().messages().batchModify(
                userId=self.user_id,
                body=body,
            ).execute()
        except HttpError as error:
            raise RuntimeError(f"Gmail API error: {error}")

    def _resolve_label(self, label: str) -> str:
        """Resolve a label name to its ID. System labels are returned as-is."""
        # System labels are uppercase and can be used directly
        system_labels = [
            "INBOX",
            "SPAM",
            "TRASH",
            "UNREAD",
            "STARRED",
            "IMPORTANT",
            "SENT",
            "DRAFT",
            "CATEGORY_PERSONAL",
            "CATEGORY_SOCIAL",
            "CATEGORY_PROMOTIONS",
            "CATEGORY_UPDATES",
            "CATEGORY_FORUMS",
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
            "to": headers.get("To", ""),
            "cc": headers.get("Cc", ""),
            "subject": headers.get("Subject", ""),
            "date": headers.get("Date", ""),
            "labelIds": msg.get("labelIds", []),
            # Headers needed for reply/forward
            "messageId": headers.get("Message-ID", headers.get("Message-Id", "")),
            "references": headers.get("References", ""),
            "replyTo": headers.get("Reply-To", ""),
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
