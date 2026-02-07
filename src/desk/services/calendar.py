"""Google Calendar API wrapper."""

from datetime import datetime, timedelta

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError


class CalendarClient:
    """Client for Google Calendar API operations."""

    def __init__(self, credentials: Credentials):
        self.service = build("calendar", "v3", credentials=credentials)

    def today(self, calendar_id: str = "primary") -> list[dict]:
        """Get today's events.

        Returns:
            List of event dicts
        """
        now = datetime.now().astimezone()
        start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        end = start + timedelta(days=1)
        return self._list_events(calendar_id, start, end)

    def week(self, calendar_id: str = "primary") -> list[dict]:
        """Get this week's events (Monday through Sunday).

        Returns:
            List of event dicts
        """
        now = datetime.now().astimezone()
        start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        # Go to start of current week (Monday)
        start = start - timedelta(days=start.weekday())
        end = start + timedelta(days=7)
        return self._list_events(calendar_id, start, end)

    def next(self, max_results: int = 10, calendar_id: str = "primary") -> list[dict]:
        """Get next upcoming events.

        Args:
            max_results: Maximum number of events
            calendar_id: Calendar ID

        Returns:
            List of event dicts
        """
        now = datetime.now().astimezone()
        try:
            results = (
                self.service.events()
                .list(
                    calendarId=calendar_id,
                    timeMin=now.isoformat(),
                    maxResults=max_results,
                    singleEvents=True,
                    orderBy="startTime",
                )
                .execute()
            )
            return [self._parse_event(e) for e in results.get("items", [])]
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
            "start": self._parse_time_input(start),
            "end": self._parse_time_input(end),
        }
        if description:
            body["description"] = description
        if attendees:
            body["attendees"] = [{"email": email} for email in attendees]

        try:
            event = (
                self.service.events()
                .insert(calendarId=calendar_id, body=body, sendUpdates="all")
                .execute()
            )
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
            calendar_id: Calendar ID

        Returns:
            Updated event dict
        """
        try:
            event = self.service.events().get(calendarId=calendar_id, eventId=event_id).execute()

            if summary is not None:
                event["summary"] = summary
            if start is not None:
                event["start"] = self._parse_time_input(start)
            if end is not None:
                event["end"] = self._parse_time_input(end)
            if description is not None:
                event["description"] = description
            if add_attendees:
                existing = event.get("attendees", [])
                existing_emails = {a["email"] for a in existing}
                for email in add_attendees:
                    if email not in existing_emails:
                        existing.append({"email": email})
                event["attendees"] = existing

            result = (
                self.service.events()
                .update(
                    calendarId=calendar_id,
                    eventId=event_id,
                    body=event,
                    sendUpdates="all",
                )
                .execute()
            )
            return self._parse_event(result)
        except HttpError as error:
            raise RuntimeError(f"Calendar API error: {error}")

    def find(self, query: str, max_results: int = 10, calendar_id: str = "primary") -> list[dict]:
        """Search for events by text.

        Args:
            query: Search text
            max_results: Maximum results
            calendar_id: Calendar ID

        Returns:
            List of matching events
        """
        try:
            results = (
                self.service.events()
                .list(
                    calendarId=calendar_id,
                    q=query,
                    maxResults=max_results,
                    singleEvents=True,
                    orderBy="startTime",
                    timeMin=datetime.now().astimezone().isoformat(),
                )
                .execute()
            )
            return [self._parse_event(e) for e in results.get("items", [])]
        except HttpError as error:
            raise RuntimeError(f"Calendar API error: {error}")

    def _list_events(self, calendar_id: str, start: datetime, end: datetime) -> list[dict]:
        """List events in a time range."""
        try:
            results = (
                self.service.events()
                .list(
                    calendarId=calendar_id,
                    timeMin=start.isoformat(),
                    timeMax=end.isoformat(),
                    singleEvents=True,
                    orderBy="startTime",
                )
                .execute()
            )
            return [self._parse_event(e) for e in results.get("items", [])]
        except HttpError as error:
            raise RuntimeError(f"Calendar API error: {error}")

    def _parse_event(self, event: dict) -> dict:
        """Parse a Calendar API event into a clean dict."""
        start = event.get("start", {})
        end = event.get("end", {})
        return {
            "id": event.get("id", ""),
            "summary": event.get("summary", "(no title)"),
            "start": start.get("dateTime", start.get("date", "")),
            "end": end.get("dateTime", end.get("date", "")),
            "location": event.get("location", ""),
            "description": event.get("description", ""),
            "htmlLink": event.get("htmlLink", ""),
            "status": event.get("status", ""),
        }

    def _parse_time_input(self, time_str: str) -> dict:
        """Parse a time string into Calendar API format."""
        # If it looks like a date-only (YYYY-MM-DD), use date format
        if len(time_str) == 10 and time_str[4] == "-":
            return {"date": time_str}
        # Parse and attach local timezone if the datetime is naive
        dt = datetime.fromisoformat(time_str)
        if dt.tzinfo is None:
            local_tz = datetime.now().astimezone().tzinfo
            dt = dt.replace(tzinfo=local_tz)
        return {"dateTime": dt.isoformat()}
