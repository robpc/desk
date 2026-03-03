"""Gmail API wrapper."""

import base64
import re
import socket
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import google_auth_httplib2
import httplib2
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError


class GmailClient:
    """Client for Gmail API operations."""

    def __init__(self, credentials: Credentials):
        self.credentials = credentials
        self.service = build("gmail", "v1", credentials=credentials)
        self.user_id = "me"
        self._labels_cache: list[dict] | None = None
        self._aliases_cache: list[dict] | None = None
        self._timeout_services: dict[int, object] = {}

    def _build_service_with_timeout(self, timeout: int):
        """Build a Gmail service with a custom timeout.

        Caches by timeout value so repeated calls with the same timeout
        reuse the same service (avoids re-fetching the discovery doc).

        Args:
            timeout: Timeout in seconds for HTTP operations.

        Returns:
            A Gmail service instance with the custom timeout.
        """
        if timeout not in self._timeout_services:
            http = httplib2.Http(timeout=timeout)
            authed_http = google_auth_httplib2.AuthorizedHttp(self.credentials, http=http)
            self._timeout_services[timeout] = build("gmail", "v1", http=authed_http)
        return self._timeout_services[timeout]

    def _batch_get(self, requests: list[tuple[str, object]]) -> dict[str, dict]:
        """Execute multiple API requests in a single batch HTTP call.

        Args:
            requests: List of (request_id, HttpRequest) tuples. The HttpRequest
                objects should be un-executed (built via .get() without .execute()).

        Returns:
            Dict mapping request_id to response dict. Failed individual requests
            are silently omitted.

        Raises:
            RuntimeError: If ALL requests in the batch fail.
        """
        if not requests:
            return {}

        results: dict[str, dict] = {}
        errors: list[str] = []

        def callback(request_id, response, exception):
            if exception is not None:
                errors.append(request_id)
            else:
                results[request_id] = response

        batch = self.service.new_batch_http_request(callback=callback)
        for request_id, request in requests:
            batch.add(request, request_id=request_id)
        batch.execute()

        if errors and not results:
            raise RuntimeError(
                f"All {len(errors)} batch requests failed"
            )

        return results

    def search_all_ids(self, query: str) -> list[str]:
        """Paginate through all messages matching query and return their IDs.

        Uses messages.list with only IDs (no metadata fetch) for efficiency.
        Pages through all results using 500 per page (Gmail max).

        Args:
            query: Gmail search query (same syntax as Gmail search box)

        Returns:
            List of all matching message IDs
        """
        all_ids: list[str] = []
        page_token = None

        try:
            while True:
                request_kwargs = {
                    "userId": self.user_id,
                    "q": query,
                    "maxResults": 500,
                }
                if page_token:
                    request_kwargs["pageToken"] = page_token

                results = (
                    self.service.users().messages().list(**request_kwargs).execute()
                )

                for msg in results.get("messages", []):
                    all_ids.append(msg["id"])

                page_token = results.get("nextPageToken")
                if not page_token:
                    break

            return all_ids

        except HttpError as error:
            raise RuntimeError(f"Gmail API error: {error}")

    def count_messages(self, query: str) -> int:
        """Get approximate count of messages matching a query.

        Uses a single API call with maxResults=1 to get resultSizeEstimate.

        Args:
            query: Gmail search query

        Returns:
            Estimated count of matching messages
        """
        try:
            results = (
                self.service.users()
                .messages()
                .list(userId=self.user_id, q=query, maxResults=1)
                .execute()
            )
            return results.get("resultSizeEstimate", 0)
        except HttpError as error:
            raise RuntimeError(f"Gmail API error: {error}")

    def search(
        self, query: str, max_results: int = 20, page_token: str | None = None
    ) -> dict:
        """Search for messages matching query.

        Args:
            query: Gmail search query (same syntax as Gmail search box)
            max_results: Maximum number of results to return
            page_token: Token for fetching next page of results

        Returns:
            Dict with 'messages' list and 'nextPageToken' (if more results exist)
        """
        try:
            request_kwargs = {
                "userId": self.user_id,
                "q": query,
                "maxResults": max_results,
            }
            if page_token:
                request_kwargs["pageToken"] = page_token

            results = self.service.users().messages().list(**request_kwargs).execute()

            messages = results.get("messages", [])

            # Batch-fetch metadata for all messages
            requests = [
                (
                    msg["id"],
                    self.service.users()
                    .messages()
                    .get(
                        userId=self.user_id,
                        id=msg["id"],
                        format="metadata",
                        metadataHeaders=["From", "Subject", "Date"],
                    ),
                )
                for msg in messages
            ]
            batch_results = self._batch_get(requests)

            # Preserve Gmail's ordering
            detailed = [
                self._parse_message_metadata(batch_results[msg["id"]])
                for msg in messages
                if msg["id"] in batch_results
            ]

            result = {"messages": detailed}
            if results.get("nextPageToken"):
                result["nextPageToken"] = results["nextPageToken"]
            return result

        except HttpError as error:
            raise RuntimeError(f"Gmail API error: {error}")

    # -------------------------------------------------------------------------
    # Threads
    # -------------------------------------------------------------------------

    def search_threads(
        self, query: str, max_results: int = 20, page_token: str | None = None
    ) -> dict:
        """Search for threads matching query.

        Args:
            query: Gmail search query (same syntax as Gmail search box)
            max_results: Maximum number of threads to return
            page_token: Token for fetching next page of results

        Returns:
            Dict with 'threads' list and 'nextPageToken' (if more results exist)
        """
        try:
            request_kwargs = {
                "userId": self.user_id,
                "q": query,
                "maxResults": max_results,
            }
            if page_token:
                request_kwargs["pageToken"] = page_token

            results = self.service.users().threads().list(**request_kwargs).execute()

            threads = results.get("threads", [])

            # Batch-fetch details for all threads
            requests = [
                (
                    thread["id"],
                    self.service.users()
                    .threads()
                    .get(userId=self.user_id, id=thread["id"], format="metadata"),
                )
                for thread in threads
            ]
            batch_results = self._batch_get(requests)

            # Preserve Gmail's ordering
            detailed = []
            for thread in threads:
                if thread["id"] not in batch_results:
                    continue
                detail = batch_results[thread["id"]]
                messages = detail.get("messages", [])
                first_msg = messages[0] if messages else {}
                headers = {
                    h["name"]: h["value"]
                    for h in first_msg.get("payload", {}).get("headers", [])
                }
                detailed.append({
                    "id": detail["id"],
                    "snippet": detail.get("snippet", ""),
                    "messageCount": len(messages),
                    "from": headers.get("From", ""),
                    "subject": headers.get("Subject", ""),
                    "date": headers.get("Date", ""),
                })

            result = {"threads": detailed}
            if results.get("nextPageToken"):
                result["nextPageToken"] = results["nextPageToken"]
            return result

        except HttpError as error:
            raise RuntimeError(f"Gmail API error: {error}")

    def get_thread(self, thread_id: str) -> dict:
        """Get a thread with all its messages.

        Args:
            thread_id: The thread ID

        Returns:
            Thread dict with id and list of full messages
        """
        try:
            thread = (
                self.service.users()
                .threads()
                .get(userId=self.user_id, id=thread_id, format="full")
                .execute()
            )

            messages = []
            for msg in thread.get("messages", []):
                messages.append(self._parse_full_message(msg))

            return {
                "id": thread["id"],
                "messages": messages,
                "messageCount": len(messages),
            }

        except HttpError as error:
            raise RuntimeError(f"Gmail API error: {error}")

    def modify_thread(
        self,
        thread_id: str,
        add_labels: list[str] | None = None,
        remove_labels: list[str] | None = None,
    ) -> None:
        """Modify labels on all messages in a thread.

        Args:
            thread_id: The thread ID
            add_labels: Label IDs or names to add
            remove_labels: Label IDs or names to remove
        """
        body = {}

        if add_labels:
            body["addLabelIds"] = [self._resolve_label(lbl) for lbl in add_labels]

        if remove_labels:
            body["removeLabelIds"] = [self._resolve_label(lbl) for lbl in remove_labels]

        if not body:
            return

        try:
            self.service.users().threads().modify(
                userId=self.user_id,
                id=thread_id,
                body=body,
            ).execute()
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

    # Gmail label color presets (background, text)
    LABEL_COLORS = {
        "berry": ("#dc3912", "#ffffff"),
        "red": ("#fa573c", "#ffffff"),
        "orange": ("#ff9800", "#ffffff"),
        "yellow": ("#ffad46", "#000000"),
        "green": ("#16a765", "#ffffff"),
        "teal": ("#2da2bb", "#ffffff"),
        "blue": ("#4986e7", "#ffffff"),
        "purple": ("#a479e2", "#ffffff"),
        "gray": ("#999999", "#ffffff"),
        "brown": ("#b99aff", "#000000"),
    }

    def create_label(
        self,
        name: str,
        color: str | None = None,
    ) -> dict:
        """Create a new label.

        Args:
            name: Label name. Use "/" for nested labels (e.g., "Projects/Orion").
            color: Optional color name (berry, red, orange, yellow, green, teal, blue, purple, gray, brown).

        Returns:
            The created label dict with id, name, etc.

        Raises:
            ValueError: If label already exists or color is invalid.
        """
        # Check if label already exists
        existing = self._get_label_id(name)
        if existing:
            raise ValueError(f"Label already exists: {name}")

        # Validate color if provided
        if color and color.lower() not in self.LABEL_COLORS:
            valid = ", ".join(sorted(self.LABEL_COLORS.keys()))
            raise ValueError(f"Invalid color '{color}'. Valid colors: {valid}")

        body = {
            "name": name,
            "labelListVisibility": "labelShow",
            "messageListVisibility": "show",
        }

        if color:
            bg, text = self.LABEL_COLORS[color.lower()]
            body["color"] = {
                "backgroundColor": bg,
                "textColor": text,
            }

        try:
            label = (
                self.service.users()
                .labels()
                .create(userId=self.user_id, body=body)
                .execute()
            )
            self._labels_cache = None
            return label
        except HttpError as error:
            raise RuntimeError(f"Gmail API error: {error}")

    def delete_label(self, name: str, timeout: int | None = None) -> None:
        """Delete a label.

        Args:
            name: Label name to delete.
            timeout: Optional timeout in seconds (default uses standard timeout).
                     Use higher values for labels with many messages.

        Raises:
            ValueError: If label not found or is a system label.
            TimeoutError: If the operation times out.
        """
        label_id = self._get_label_id(name)
        if not label_id:
            raise ValueError(f"Label not found: {name}")

        # Prevent deleting system labels
        system_labels = [
            "INBOX", "SPAM", "TRASH", "UNREAD", "STARRED", "IMPORTANT",
            "SENT", "DRAFT", "CATEGORY_PERSONAL", "CATEGORY_SOCIAL",
            "CATEGORY_PROMOTIONS", "CATEGORY_UPDATES", "CATEGORY_FORUMS",
        ]
        if name.upper() in system_labels:
            raise ValueError(f"Cannot delete system label: {name}")

        # Use custom timeout service if specified
        service = (
            self._build_service_with_timeout(timeout) if timeout
            else self.service
        )

        try:
            service.users().labels().delete(
                userId=self.user_id, id=label_id
            ).execute()
            self._labels_cache = None
        except socket.timeout as e:
            raise TimeoutError(
                f"Label deletion timed out (labels with many messages can take a while): {e}"
            )
        except HttpError as error:
            raise RuntimeError(f"Gmail API error: {error}")

    def rename_label(self, old_name: str, new_name: str) -> dict:
        """Rename a label.

        Args:
            old_name: Current label name.
            new_name: New label name.

        Returns:
            The updated label dict.

        Raises:
            ValueError: If label not found or new name already exists.
        """
        label_id = self._get_label_id(old_name)
        if not label_id:
            raise ValueError(f"Label not found: {old_name}")

        # Check if new name already exists
        if self._get_label_id(new_name):
            raise ValueError(f"Label already exists: {new_name}")

        try:
            label = (
                self.service.users()
                .labels()
                .patch(
                    userId=self.user_id,
                    id=label_id,
                    body={"name": new_name},
                )
                .execute()
            )
            self._labels_cache = None
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

    @staticmethod
    def _build_mime_message(body: str, html: bool = False) -> MIMEText | MIMEMultipart:
        """Build a MIME message from body text.

        Args:
            body: The message body
            html: If True, body is HTML. Builds multipart/alternative
                  with a plain-text fallback.

        Returns:
            A MIMEText (plain) or MIMEMultipart (html) message.
        """
        if not html:
            return MIMEText(body)

        # Build multipart/alternative with plain text fallback
        msg = MIMEMultipart("alternative")
        # Strip HTML tags for plain text version
        plain = re.sub(r"<[^>]+>", "", body)
        msg.attach(MIMEText(plain, "plain"))
        msg.attach(MIMEText(body, "html"))
        return msg

    def send(
        self,
        to: list[str],
        subject: str,
        body: str,
        cc: list[str] | None = None,
        bcc: list[str] | None = None,
        html: bool = False,
        from_addr: str | None = None,
    ) -> dict:
        """Send an email.

        Args:
            to: List of recipient email addresses
            subject: Email subject
            body: Email body (plain text, or HTML if html=True)
            cc: List of CC recipients
            bcc: List of BCC recipients
            html: If True, body is HTML with plain-text fallback
            from_addr: Send from this alias (must be configured in Gmail)

        Returns:
            The sent message metadata (id, threadId, labelIds)
        """
        # Build MIME message
        message = self._build_mime_message(body, html=html)
        message["to"] = ", ".join(to)
        message["subject"] = subject

        if from_addr:
            message["from"] = from_addr
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
        html: bool = False,
        from_addr: str | None = None,
    ) -> dict:
        """Reply to an email.

        Args:
            message_id: The message ID to reply to
            body: Reply body (plain text, or HTML if html=True)
            reply_all: If True, reply to all recipients (To + CC)
            html: If True, body is HTML with plain-text fallback
            from_addr: Send from this alias (overrides auto-detect)

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

        # Auto-detect which alias the message was sent to
        if not from_addr:
            from_addr = self.detect_send_as_alias(original)

        # Build subject with Re: prefix
        subject = original.get("subject", "")
        if not subject.lower().startswith("re:"):
            subject = f"Re: {subject}"

        # Build MIME message with threading headers
        message = self._build_mime_message(body, html=html)
        message["to"] = ", ".join(to_addrs)
        message["subject"] = subject

        if from_addr:
            message["from"] = from_addr
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
        html: bool = False,
        from_addr: str | None = None,
    ) -> dict:
        """Forward an email.

        Args:
            message_id: The message ID to forward
            to: List of recipient email addresses
            body: Optional additional message to include before forwarded content
            html: If True, body is HTML with plain-text fallback
            from_addr: Send from this alias (must be configured in Gmail)

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
        message = self._build_mime_message(forward_body, html=html)
        message["to"] = ", ".join(to)
        message["subject"] = subject

        if from_addr:
            message["from"] = from_addr

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

    def list_drafts(
        self, max_results: int = 20, page_token: str | None = None
    ) -> dict:
        """List drafts.

        Args:
            max_results: Maximum number of drafts to return
            page_token: Token for fetching next page of results

        Returns:
            Dict with 'drafts' list and 'nextPageToken' (if more results exist)
        """
        try:
            request_kwargs = {
                "userId": self.user_id,
                "maxResults": max_results,
            }
            if page_token:
                request_kwargs["pageToken"] = page_token

            results = self.service.users().drafts().list(**request_kwargs).execute()

            drafts = results.get("drafts", [])

            # Batch-fetch details for all drafts
            requests = [
                (
                    draft["id"],
                    self.service.users()
                    .drafts()
                    .get(userId=self.user_id, id=draft["id"], format="metadata"),
                )
                for draft in drafts
            ]
            batch_results = self._batch_get(requests)

            # Preserve ordering
            detailed = []
            for draft in drafts:
                if draft["id"] not in batch_results:
                    continue
                detail = batch_results[draft["id"]]
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

            result = {"drafts": detailed}
            if results.get("nextPageToken"):
                result["nextPageToken"] = results["nextPageToken"]
            return result

        except HttpError as error:
            raise RuntimeError(f"Gmail API error: {error}")

    def create_draft(
        self,
        to: list[str],
        subject: str,
        body: str,
        cc: list[str] | None = None,
        bcc: list[str] | None = None,
        html: bool = False,
    ) -> dict:
        """Create a draft email.

        Args:
            to: List of recipient email addresses
            subject: Email subject
            body: Email body (plain text, or HTML if html=True)
            cc: List of CC recipients
            bcc: List of BCC recipients
            html: If True, body is HTML with plain-text fallback

        Returns:
            The created draft with id
        """
        message = self._build_mime_message(body, html=html)
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
        html: bool = False,
    ) -> dict:
        """Update a draft.

        Args:
            draft_id: The draft ID to update
            to: New recipients (if provided)
            subject: New subject (if provided)
            body: New body (if provided)
            cc: New CC recipients (if provided)
            bcc: New BCC recipients (if provided)
            html: If True, body is HTML with plain-text fallback

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
        message = self._build_mime_message(final_body, html=html)
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

    # -------------------------------------------------------------------------
    # Send-as aliases
    # -------------------------------------------------------------------------

    def list_send_as_aliases(self) -> list[dict]:
        """List configured send-as aliases.

        Returns:
            List of alias dicts with sendAsEmail, displayName,
            isDefault, verificationStatus.
        """
        try:
            results = (
                self.service.users()
                .settings()
                .sendAs()
                .list(userId=self.user_id)
                .execute()
            )
            return [
                {
                    "sendAsEmail": alias.get("sendAsEmail", ""),
                    "displayName": alias.get("displayName", ""),
                    "isDefault": alias.get("isDefault", False),
                    "isPrimary": alias.get("isPrimary", False),
                    "verificationStatus": alias.get(
                        "verificationStatus", ""
                    ),
                }
                for alias in results.get("sendAs", [])
            ]
        except HttpError as error:
            raise RuntimeError(f"Gmail API error: {error}")

    def detect_send_as_alias(self, message: dict) -> str | None:
        """Detect which send-as alias a message was delivered to.

        Matches Delivered-To, To, then CC headers against the user's
        configured send-as aliases.  Returns the matching alias email,
        or None if no match (caller should fall back to default).

        Args:
            message: Parsed message dict (from read())

        Returns:
            Matching alias email address, or None
        """
        try:
            if self._aliases_cache is None:
                self._aliases_cache = self.list_send_as_aliases()
            aliases = self._aliases_cache
        except RuntimeError:
            return None

        alias_emails = {
            a["sendAsEmail"].lower()
            for a in aliases
            if a.get("verificationStatus") == "accepted"
            or a.get("isPrimary")
        }

        # Check headers in priority order
        for header_key in ("deliveredTo", "to", "cc"):
            value = message.get(header_key, "")
            if not value:
                continue
            for addr in self._parse_addresses(value):
                # Extract bare email from "Name <email>" format
                bare = addr.strip()
                if "<" in bare and ">" in bare:
                    bare = bare.split("<")[1].split(">")[0]
                if bare.lower() in alias_emails:
                    return bare
        return None

    def _get_label_id(self, label_name: str) -> str | None:
        """Get label ID by name.

        Uses a per-instance cache to avoid repeated list_labels() API calls
        within a single CLI command.
        """
        if self._labels_cache is None:
            self._labels_cache = self.list_labels()
        for label in self._labels_cache:
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
            "deliveredTo": headers.get("Delivered-To", ""),
            # Headers needed for reply/forward
            "messageId": headers.get("Message-ID", headers.get("Message-Id", "")),
            "references": headers.get("References", ""),
            "replyTo": headers.get("Reply-To", ""),
        }

    def _parse_full_message(self, msg: dict) -> dict:
        """Parse full message including body and links."""
        from desk.links import extract_links_from_html

        metadata = self._parse_message_metadata(msg)
        plain, html = self._extract_body_parts(msg.get("payload", {}))
        metadata["body"] = plain

        # Extract links from HTML body
        if html:
            metadata["links"] = extract_links_from_html(html)
        else:
            metadata["links"] = []

        return metadata

    def _extract_body_parts(self, payload: dict) -> tuple[str, str]:
        """Extract both plain text and HTML body from payload.

        Returns:
            Tuple of (plain_text, html). Either may be empty string.
        """
        plain = ""
        html = ""

        # Simple case: body directly in payload (check mimeType)
        if "body" in payload and payload["body"].get("data"):
            decoded = base64.urlsafe_b64decode(payload["body"]["data"]).decode("utf-8")
            mime = payload.get("mimeType", "")
            if mime == "text/html":
                html = decoded
            else:
                plain = decoded
            return plain, html

        # Multipart: collect text/plain and text/html parts
        if "parts" in payload:
            for part in payload["parts"]:
                mime = part.get("mimeType", "")
                if mime == "text/plain" and not plain:
                    if part.get("body", {}).get("data"):
                        plain = base64.urlsafe_b64decode(part["body"]["data"]).decode("utf-8")
                elif mime == "text/html" and not html:
                    if part.get("body", {}).get("data"):
                        html = base64.urlsafe_b64decode(part["body"]["data"]).decode("utf-8")
                # Recurse into nested parts
                if "parts" in part:
                    sub_plain, sub_html = self._extract_body_parts(part)
                    if sub_plain and not plain:
                        plain = sub_plain
                    if sub_html and not html:
                        html = sub_html

        return plain, html

    def _extract_body(self, payload: dict) -> str:
        """Extract plain text body from payload.

        Convenience wrapper around _extract_body_parts.
        """
        plain, _ = self._extract_body_parts(payload)
        return plain

    # -------------------------------------------------------------------------
    # Filters (Gmail Settings)
    # -------------------------------------------------------------------------

    def list_filters(self) -> list[dict]:
        """List all email filters.

        Returns:
            List of filter dicts with id, criteria, and action
        """
        try:
            result = (
                self.service.users()
                .settings()
                .filters()
                .list(userId=self.user_id)
                .execute()
            )
            filters = result.get("filter", [])
            return [self._parse_filter(f) for f in filters]
        except HttpError as error:
            raise RuntimeError(f"Gmail API error: {error}")

    def get_filter(self, filter_id: str) -> dict:
        """Get a filter by ID.

        Args:
            filter_id: The filter ID

        Returns:
            Filter dict with criteria and action
        """
        try:
            result = (
                self.service.users()
                .settings()
                .filters()
                .get(userId=self.user_id, id=filter_id)
                .execute()
            )
            return self._parse_filter(result)
        except HttpError as error:
            raise RuntimeError(f"Gmail API error: {error}")

    def create_filter(
        self,
        from_addr: str | None = None,
        to_addr: str | None = None,
        subject: str | None = None,
        query: str | None = None,
        has_attachment: bool | None = None,
        add_labels: list[str] | None = None,
        remove_labels: list[str] | None = None,
        archive: bool = False,
        mark_read: bool = False,
        star: bool = False,
        forward: str | None = None,
        never_spam: bool = False,
    ) -> dict:
        """Create an email filter.

        Args:
            from_addr: Filter by sender
            to_addr: Filter by recipient
            subject: Filter by subject (contains)
            query: Raw Gmail search query
            has_attachment: Filter messages with attachments
            add_labels: Labels to add
            remove_labels: Labels to remove
            archive: Skip inbox
            mark_read: Mark as read
            star: Star the message
            forward: Email to forward to
            never_spam: Never mark as spam

        Returns:
            Created filter dict
        """
        # Build criteria
        criteria = {}
        if from_addr:
            criteria["from"] = from_addr
        if to_addr:
            criteria["to"] = to_addr
        if subject:
            criteria["subject"] = subject
        if query:
            criteria["query"] = query
        if has_attachment is not None:
            criteria["hasAttachment"] = has_attachment

        if not criteria:
            raise ValueError("At least one filter criteria is required")

        # Build action
        action = {}
        if add_labels:
            action["addLabelIds"] = [self._resolve_label(lbl) for lbl in add_labels]
        if remove_labels:
            action["removeLabelIds"] = [self._resolve_label(lbl) for lbl in remove_labels]
        if archive:
            action.setdefault("removeLabelIds", []).append("INBOX")
        if mark_read:
            action.setdefault("removeLabelIds", []).append("UNREAD")
        if star:
            action.setdefault("addLabelIds", []).append("STARRED")
        if forward:
            action["forward"] = forward
        if never_spam:
            action.setdefault("removeLabelIds", []).append("SPAM")

        if not action:
            raise ValueError("At least one filter action is required")

        body = {"criteria": criteria, "action": action}

        try:
            result = (
                self.service.users()
                .settings()
                .filters()
                .create(userId=self.user_id, body=body)
                .execute()
            )
            return self._parse_filter(result)
        except HttpError as error:
            raise RuntimeError(f"Gmail API error: {error}")

    def delete_filter(self, filter_id: str) -> None:
        """Delete a filter.

        Args:
            filter_id: The filter ID
        """
        try:
            self.service.users().settings().filters().delete(
                userId=self.user_id, id=filter_id
            ).execute()
        except HttpError as error:
            raise RuntimeError(f"Gmail API error: {error}")

    def _parse_filter(self, f: dict) -> dict:
        """Parse a filter response into clean dict."""
        criteria = f.get("criteria", {})
        action = f.get("action", {})

        # Parse action into human-readable form
        actions = []
        if action.get("addLabelIds"):
            for label_id in action["addLabelIds"]:
                if label_id == "STARRED":
                    actions.append("star")
                else:
                    actions.append(f"+{label_id}")
        if action.get("removeLabelIds"):
            for label_id in action["removeLabelIds"]:
                if label_id == "INBOX":
                    actions.append("archive")
                elif label_id == "UNREAD":
                    actions.append("mark-read")
                elif label_id == "SPAM":
                    actions.append("never-spam")
                else:
                    actions.append(f"-{label_id}")
        if action.get("forward"):
            actions.append(f"forward:{action['forward']}")

        return {
            "id": f.get("id", ""),
            "criteria": {
                "from": criteria.get("from", ""),
                "to": criteria.get("to", ""),
                "subject": criteria.get("subject", ""),
                "query": criteria.get("query", ""),
                "hasAttachment": criteria.get("hasAttachment"),
            },
            "action": action,
            "actionSummary": ", ".join(actions) if actions else "(no actions)",
        }

    # -------------------------------------------------------------------------
    # Vacation Responder
    # -------------------------------------------------------------------------

    def get_vacation(self) -> dict:
        """Get vacation auto-reply settings.

        Returns:
            Vacation settings dict with enabled, subject, message, dates
        """
        try:
            result = (
                self.service.users()
                .settings()
                .getVacation(userId=self.user_id)
                .execute()
            )
            return {
                "enabled": result.get("enableAutoReply", False),
                "subject": result.get("responseSubject", ""),
                "message": result.get("responseBodyPlainText", ""),
                "startTime": result.get("startTime"),
                "endTime": result.get("endTime"),
                "contactsOnly": result.get("restrictToContacts", False),
                "domainOnly": result.get("restrictToDomain", False),
            }
        except HttpError as error:
            raise RuntimeError(f"Gmail API error: {error}")

    def set_vacation(
        self,
        enabled: bool,
        message: str | None = None,
        subject: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
        contacts_only: bool = False,
        domain_only: bool = False,
    ) -> dict:
        """Set vacation auto-reply settings.

        Args:
            enabled: Enable or disable auto-reply
            message: Auto-reply message (plain text)
            subject: Auto-reply subject
            start_date: Start date (YYYY-MM-DD)
            end_date: End date (YYYY-MM-DD)
            contacts_only: Only reply to contacts
            domain_only: Only reply to same domain

        Returns:
            Updated vacation settings
        """
        body = {"enableAutoReply": enabled}

        if message is not None:
            body["responseBodyPlainText"] = message
        if subject is not None:
            body["responseSubject"] = subject
        if contacts_only:
            body["restrictToContacts"] = True
        if domain_only:
            body["restrictToDomain"] = True

        # Convert dates to epoch milliseconds
        if start_date:
            from datetime import datetime
            dt = datetime.strptime(start_date, "%Y-%m-%d")
            body["startTime"] = int(dt.timestamp() * 1000)
        if end_date:
            from datetime import datetime
            dt = datetime.strptime(end_date, "%Y-%m-%d")
            # End of day
            dt = dt.replace(hour=23, minute=59, second=59)
            body["endTime"] = int(dt.timestamp() * 1000)

        try:
            result = (
                self.service.users()
                .settings()
                .updateVacation(userId=self.user_id, body=body)
                .execute()
            )
            return {
                "enabled": result.get("enableAutoReply", False),
                "subject": result.get("responseSubject", ""),
                "message": result.get("responseBodyPlainText", ""),
                "startTime": result.get("startTime"),
                "endTime": result.get("endTime"),
                "contactsOnly": result.get("restrictToContacts", False),
                "domainOnly": result.get("restrictToDomain", False),
            }
        except HttpError as error:
            raise RuntimeError(f"Gmail API error: {error}")
