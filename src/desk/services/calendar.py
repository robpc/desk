"""Google Calendar API wrapper."""

from datetime import datetime, timedelta

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError


def parse_time_input(time_str: str) -> dict:
    """Parse a time string into Calendar API format.

    Public so the command layer can preview what a ``--start`` / ``--end``
    will actually resolve to without performing the write.
    """
    # If it looks like a date-only (YYYY-MM-DD), use date format
    if len(time_str) == 10 and time_str[4] == "-":
        return {"date": time_str}
    # A naive datetime means local wall-clock time *on its own date*, so
    # localize it with astimezone(), which applies the offset in effect
    # that day. Stamping on datetime.now()'s offset instead is an hour
    # out for any date on the far side of a DST boundary (issue #89).
    dt = datetime.fromisoformat(time_str)
    if dt.tzinfo is None:
        dt = dt.astimezone()
    return {"dateTime": dt.isoformat()}


class CalendarClient:
    """Client for Google Calendar API operations."""

    def __init__(self, credentials: Credentials):
        self.service = build("calendar", "v3", credentials=credentials)

    def today(
        self,
        calendar_id: str = "primary",
        page_token: str | None = None,
        date: str | None = None,
    ) -> dict:
        """Get events for a specific day (defaults to today).

        Args:
            calendar_id: Calendar ID
            page_token: Token for fetching next page of results
            date: Optional date string (YYYY-MM-DD). Defaults to today.

        Returns:
            Dict with 'events' list and 'nextPageToken' (if more results exist)
        """
        if date:
            # Build naive midnight, then localize via astimezone() so the
            # offset is correct for that specific date (handles DST).
            naive = datetime.strptime(date, "%Y-%m-%d")
            start = naive.astimezone().replace(
                hour=0, minute=0, second=0, microsecond=0
            )
        else:
            now = datetime.now().astimezone()
            start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        end = start + timedelta(days=1)
        return self._list_events(calendar_id, start, end, page_token=page_token)

    def week(
        self,
        calendar_id: str = "primary",
        page_token: str | None = None,
        date: str | None = None,
    ) -> dict:
        """Get events for a week (defaults to this week, Monday through Sunday).

        Args:
            calendar_id: Calendar ID
            page_token: Token for fetching next page of results
            date: Optional date string (YYYY-MM-DD). Shows the week containing this date.

        Returns:
            Dict with 'events' list and 'nextPageToken' (if more results exist)
        """
        if date:
            naive = datetime.strptime(date, "%Y-%m-%d")
            anchor = naive.astimezone().replace(
                hour=0, minute=0, second=0, microsecond=0
            )
        else:
            anchor = datetime.now().astimezone()
        start = anchor.replace(hour=0, minute=0, second=0, microsecond=0)
        # Go to start of week (Monday)
        start = start - timedelta(days=start.weekday())
        end = start + timedelta(days=7)
        return self._list_events(calendar_id, start, end, page_token=page_token)

    def next(
        self,
        max_results: int = 10,
        calendar_id: str = "primary",
        page_token: str | None = None,
    ) -> dict:
        """Get next upcoming events.

        Args:
            max_results: Maximum number of events
            calendar_id: Calendar ID
            page_token: Token for fetching next page of results

        Returns:
            Dict with 'events' list and 'nextPageToken' (if more results exist)
        """
        now = datetime.now().astimezone()
        try:
            request_kwargs = {
                "calendarId": calendar_id,
                "timeMin": now.isoformat(),
                "maxResults": max_results,
                "singleEvents": True,
                "orderBy": "startTime",
            }
            if page_token:
                request_kwargs["pageToken"] = page_token

            results = self.service.events().list(**request_kwargs).execute()

            result = {
                "events": [
                    self._parse_event(e, calendar_id=calendar_id)
                    for e in results.get("items", [])
                ]
            }
            if results.get("nextPageToken"):
                result["nextPageToken"] = results["nextPageToken"]
            return result
        except HttpError as error:
            raise RuntimeError(f"Calendar API error: {error}")

    def list_calendars(self) -> list[dict]:
        """List all calendars.

        Returns:
            List of calendar dicts
        """
        try:
            results = self.service.calendarList().list().execute()
            return [
                {
                    "id": cal["id"],
                    "summary": cal.get("summary", ""),
                    "primary": cal.get("primary", False),
                    "accessRole": cal.get("accessRole", ""),
                }
                for cal in results.get("items", [])
            ]
        except HttpError as error:
            raise RuntimeError(f"Calendar API error: {error}")

    def create(
        self,
        summary: str,
        start: str,
        end: str,
        description: str = "",
        attendees: list[str] | None = None,
        calendar_id: str = "primary",
    ) -> dict:
        """Create a new event.

        Args:
            summary: Event title
            start: Start time (ISO 8601, e.g., "2024-01-15T10:00:00-05:00")
            end: End time (ISO 8601)
            description: Optional event description
            attendees: Optional list of email addresses to invite
            calendar_id: Calendar ID

        Returns:
            Created event dict
        """
        body = {
            "summary": summary,
            "start": parse_time_input(start),
            "end": parse_time_input(end),
        }
        if description:
            body["description"] = description
        if attendees:
            body["attendees"] = [{"email": email} for email in attendees]

        try:
            event = (
                self.service.events()
                .insert(
                    calendarId=calendar_id,
                    body=body,
                    sendUpdates="all",
                    supportsAttachments=True,
                )
                .execute()
            )
            return self._parse_event(event)
        except HttpError as error:
            raise RuntimeError(f"Calendar API error: {error}")

    def get_event(self, event_id: str, calendar_id: str = "primary") -> dict:
        """Get a single event by ID.

        Args:
            event_id: The event ID
            calendar_id: Calendar ID

        Returns:
            Event dict
        """
        try:
            event = self.service.events().get(
                calendarId=calendar_id, eventId=event_id
            ).execute()
            return self._parse_event(event)
        except HttpError as error:
            raise RuntimeError(f"Calendar API error: {error}")

    def delete(self, event_id: str, calendar_id: str = "primary") -> None:
        """Delete an event.

        Args:
            event_id: The event ID
            calendar_id: Calendar ID
        """
        try:
            self.service.events().delete(
                calendarId=calendar_id, eventId=event_id, sendUpdates="all"
            ).execute()
        except HttpError as error:
            raise RuntimeError(f"Calendar API error: {error}")

    def update(
        self,
        event_id: str,
        summary: str | None = None,
        start: str | None = None,
        end: str | None = None,
        description: str | None = None,
        add_attendees: list[str] | None = None,
        remove_attendees: list[str] | None = None,
        calendar_id: str = "primary",
    ) -> dict:
        """Update an existing event.

        Args:
            event_id: The event ID
            summary: New title (or None to keep)
            start: New start time (or None to keep)
            end: New end time (or None to keep)
            description: New description (or None to keep)
            add_attendees: Email addresses to add
            remove_attendees: Email addresses to remove
            calendar_id: Calendar ID

        Returns:
            Updated event dict
        """
        try:
            event = self.service.events().get(
                calendarId=calendar_id, eventId=event_id
            ).execute()

            if summary is not None:
                event["summary"] = summary
            if start is not None:
                event["start"] = parse_time_input(start)
            if end is not None:
                event["end"] = parse_time_input(end)
            if description is not None:
                event["description"] = description
            if add_attendees:
                existing = event.get("attendees", [])
                existing_emails = {a["email"] for a in existing}
                for email in add_attendees:
                    if email not in existing_emails:
                        existing.append({"email": email})
                event["attendees"] = existing
            actually_removed: list[str] = []
            if remove_attendees:
                remove_set = {e.lower() for e in remove_attendees}
                existing = event.get("attendees", [])
                kept = [a for a in existing if a.get("email", "").lower() not in remove_set]
                actually_removed = [
                    a.get("email", "") for a in existing
                    if a.get("email", "").lower() in remove_set
                ]
                event["attendees"] = kept

            result = (
                self.service.events()
                .update(
                    calendarId=calendar_id,
                    eventId=event_id,
                    body=event,
                    sendUpdates="all",
                    supportsAttachments=True,
                )
                .execute()
            )
            parsed = self._parse_event(result)
            if remove_attendees:
                parsed["removedAttendees"] = actually_removed
            return parsed
        except HttpError as error:
            raise RuntimeError(f"Calendar API error: {error}")

    def find(
        self,
        query: str,
        max_results: int = 10,
        calendar_id: str = "primary",
        page_token: str | None = None,
    ) -> dict:
        """Search for events by text.

        Args:
            query: Search text
            max_results: Maximum results
            calendar_id: Calendar ID
            page_token: Token for fetching next page of results

        Returns:
            Dict with 'events' list and 'nextPageToken' (if more results exist)
        """
        try:
            request_kwargs = {
                "calendarId": calendar_id,
                "q": query,
                "maxResults": max_results,
                "singleEvents": True,
                "orderBy": "startTime",
                "timeMin": datetime.now().astimezone().isoformat(),
            }
            if page_token:
                request_kwargs["pageToken"] = page_token

            results = self.service.events().list(**request_kwargs).execute()

            result = {
                "events": [
                    self._parse_event(e, calendar_id=calendar_id)
                    for e in results.get("items", [])
                ]
            }
            if results.get("nextPageToken"):
                result["nextPageToken"] = results["nextPageToken"]
            return result
        except HttpError as error:
            raise RuntimeError(f"Calendar API error: {error}")

    def _list_events(
        self,
        calendar_id: str,
        start: datetime,
        end: datetime,
        page_token: str | None = None,
    ) -> dict:
        """List events in a time range.

        Returns:
            Dict with 'events' list and 'nextPageToken' (if more results exist)
        """
        try:
            request_kwargs = {
                "calendarId": calendar_id,
                "timeMin": start.isoformat(),
                "timeMax": end.isoformat(),
                "singleEvents": True,
                "orderBy": "startTime",
            }
            if page_token:
                request_kwargs["pageToken"] = page_token

            results = self.service.events().list(**request_kwargs).execute()

            result = {
                "events": [
                    self._parse_event(e, calendar_id=calendar_id)
                    for e in results.get("items", [])
                ]
            }
            if results.get("nextPageToken"):
                result["nextPageToken"] = results["nextPageToken"]
            return result
        except HttpError as error:
            raise RuntimeError(f"Calendar API error: {error}")

    def _parse_event(self, event: dict, calendar_id: str | None = None) -> dict:
        """Parse a Calendar API event into a clean dict.

        Args:
            event: Calendar API event resource.
            calendar_id: The source calendar's ID, surfaced on the
                returned event for multi-calendar provenance. See ADR-023.
        """
        start = event.get("start", {})
        end = event.get("end", {})
        attendees = event.get("attendees", [])
        parsed = {
            "id": event.get("id", ""),
            "summary": event.get("summary", "(no title)"),
            "start": start.get("dateTime", start.get("date", "")),
            "end": end.get("dateTime", end.get("date", "")),
            "location": event.get("location", ""),
            "description": event.get("description", ""),
            "htmlLink": event.get("htmlLink", ""),
            "status": event.get("status", ""),
            "attendees": [
                {
                    "email": a.get("email", ""),
                    "responseStatus": a.get("responseStatus", "needsAction"),
                    "organizer": a.get("organizer", False),
                    "self": a.get("self", False),
                }
                for a in attendees
            ],
            "attendeeCount": len(attendees),
            "attachments": [
                {
                    "title": att.get("title", ""),
                    "fileUrl": att.get("fileUrl", ""),
                    "mimeType": att.get("mimeType", ""),
                }
                for att in event.get("attachments", [])
            ],
        }
        if calendar_id is not None:
            parsed["calendar_id"] = calendar_id
        return parsed

    def invitations(
        self,
        max_results: int = 20,
        calendar_id: str = "primary",
        page_token: str | None = None,
    ) -> dict:
        """List pending invitations (events where user needs to respond).

        Args:
            max_results: Maximum number of results
            calendar_id: Calendar ID
            page_token: Token for fetching next page of results

        Returns:
            Dict with 'events' list and 'nextPageToken' (if more results exist)
        """
        now = datetime.now().astimezone()
        try:
            request_kwargs = {
                "calendarId": calendar_id,
                "timeMin": now.isoformat(),
                "maxResults": max_results,
                "singleEvents": True,
                "orderBy": "startTime",
            }
            if page_token:
                request_kwargs["pageToken"] = page_token

            results = self.service.events().list(**request_kwargs).execute()

            # Filter for events where user needs to respond
            invitations = []
            for event in results.get("items", []):
                attendees = event.get("attendees", [])
                for attendee in attendees:
                    if attendee.get("self") and attendee.get("responseStatus") == "needsAction":
                        invitations.append(self._parse_event(event))
                        break

            result = {"events": invitations}
            if results.get("nextPageToken"):
                result["nextPageToken"] = results["nextPageToken"]
            return result
        except HttpError as error:
            raise RuntimeError(f"Calendar API error: {error}")

    def respond(
        self,
        event_id: str,
        response: str,
        calendar_id: str = "primary",
    ) -> dict:
        """Respond to an event invitation.

        Args:
            event_id: The event ID
            response: Response status ('accepted', 'declined', 'tentative')
            calendar_id: Calendar ID

        Returns:
            Updated event dict
        """
        valid_responses = ("accepted", "declined", "tentative")
        if response not in valid_responses:
            raise ValueError(f"Invalid response '{response}'. Must be one of: {valid_responses}")

        try:
            # Get the event
            event = self.service.events().get(
                calendarId=calendar_id, eventId=event_id
            ).execute()

            # Find self in attendees and update response
            attendees = event.get("attendees", [])
            for attendee in attendees:
                if attendee.get("self"):
                    attendee["responseStatus"] = response
                    break
            else:
                # User not in attendees - this shouldn't happen for invitations
                raise ValueError("You are not an attendee of this event")

            event["attendees"] = attendees

            # Update the event
            result = (
                self.service.events()
                .update(
                    calendarId=calendar_id,
                    eventId=event_id,
                    body=event,
                    sendUpdates="all",
                    supportsAttachments=True,
                )
                .execute()
            )
            return self._parse_event(result)
        except HttpError as error:
            raise RuntimeError(f"Calendar API error: {error}")

    def freebusy(
        self, emails: list[str], start: str, end: str
    ) -> dict[str, list[dict]]:
        """Query free/busy information for given email addresses.

        Args:
            emails: List of email addresses to check
            start: Start of time range (ISO 8601)
            end: End of time range (ISO 8601)

        Returns:
            Dict mapping email to list of busy periods.
            Each busy period is a dict with "start" and "end" keys.
        """
        # Parse times to ensure they have timezone info. Naive values are
        # localized per their own date (see parse_time_input, issue #89).
        start_dt = datetime.fromisoformat(start)
        end_dt = datetime.fromisoformat(end)
        if start_dt.tzinfo is None:
            start_dt = start_dt.astimezone()
        if end_dt.tzinfo is None:
            end_dt = end_dt.astimezone()

        body = {
            "timeMin": start_dt.isoformat(),
            "timeMax": end_dt.isoformat(),
            "items": [{"id": email} for email in emails],
        }

        try:
            result = self.service.freebusy().query(body=body).execute()
            calendars = result.get("calendars", {})

            # Parse results
            freebusy_data = {}
            for email in emails:
                cal_data = calendars.get(email, {})
                busy_periods = cal_data.get("busy", [])
                freebusy_data[email] = busy_periods

            return freebusy_data
        except HttpError as error:
            raise RuntimeError(f"Calendar API error: {error}")
