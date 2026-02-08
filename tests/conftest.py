"""Shared test fixtures for desk CLI tests."""

import pytest
from unittest.mock import MagicMock, patch


@pytest.fixture
def mock_credentials():
    """Mock Google OAuth credentials."""
    creds = MagicMock()
    creds.valid = True
    creds.expired = False
    return creds


@pytest.fixture
def mock_build():
    """Patch googleapiclient.discovery.build."""
    with patch("googleapiclient.discovery.build") as mock:
        yield mock


@pytest.fixture
def mock_gmail_service():
    """Pre-configured mock Gmail service.

    The Gmail API uses a fluent interface like:
        service.users().messages().list(userId="me", q="query").execute()

    This fixture pre-configures the mock chain to return empty results by default.
    Tests can override specific return values as needed.
    """
    service = MagicMock()

    # Messages endpoints
    messages = service.users.return_value.messages.return_value
    messages.list.return_value.execute.return_value = {"messages": []}
    messages.get.return_value.execute.return_value = {}
    messages.modify.return_value.execute.return_value = {}
    messages.batchModify.return_value.execute.return_value = {}
    messages.send.return_value.execute.return_value = {}

    # Attachments
    attachments = messages.attachments.return_value
    attachments.get.return_value.execute.return_value = {"data": ""}

    # Threads endpoints
    threads = service.users.return_value.threads.return_value
    threads.list.return_value.execute.return_value = {"threads": []}
    threads.get.return_value.execute.return_value = {"messages": []}
    threads.modify.return_value.execute.return_value = {}

    # Labels endpoints
    labels = service.users.return_value.labels.return_value
    labels.list.return_value.execute.return_value = {"labels": []}
    labels.create.return_value.execute.return_value = {}
    labels.delete.return_value.execute.return_value = {}
    labels.patch.return_value.execute.return_value = {}

    # Drafts endpoints
    drafts = service.users.return_value.drafts.return_value
    drafts.list.return_value.execute.return_value = {"drafts": []}
    drafts.get.return_value.execute.return_value = {}
    drafts.create.return_value.execute.return_value = {}
    drafts.update.return_value.execute.return_value = {}
    drafts.send.return_value.execute.return_value = {}
    drafts.delete.return_value.execute.return_value = {}

    # Settings > Filters
    filters = service.users.return_value.settings.return_value.filters.return_value
    filters.list.return_value.execute.return_value = {"filter": []}
    filters.get.return_value.execute.return_value = {}
    filters.create.return_value.execute.return_value = {}
    filters.delete.return_value.execute.return_value = {}

    # Settings > Vacation
    settings = service.users.return_value.settings.return_value
    settings.getVacation.return_value.execute.return_value = {}
    settings.updateVacation.return_value.execute.return_value = {}

    return service


@pytest.fixture
def mock_drive_service():
    """Pre-configured mock Drive service."""
    service = MagicMock()

    # Files endpoints
    files = service.files.return_value
    files.list.return_value.execute.return_value = {"files": []}
    files.get.return_value.execute.return_value = {}
    files.get_media.return_value.execute.return_value = b""
    files.create.return_value.execute.return_value = {}
    files.update.return_value.execute.return_value = {}
    files.delete.return_value.execute.return_value = {}
    files.export.return_value.execute.return_value = b""
    files.export_media.return_value.execute.return_value = b""

    # Permissions endpoints
    permissions = service.permissions.return_value
    permissions.create.return_value.execute.return_value = {}
    permissions.list.return_value.execute.return_value = {"permissions": []}
    permissions.delete.return_value.execute.return_value = {}

    return service


@pytest.fixture
def mock_calendar_service():
    """Pre-configured mock Calendar service."""
    service = MagicMock()

    # Events endpoints
    events = service.events.return_value
    events.list.return_value.execute.return_value = {"items": []}
    events.get.return_value.execute.return_value = {}
    events.insert.return_value.execute.return_value = {}
    events.update.return_value.execute.return_value = {}
    events.delete.return_value.execute.return_value = {}

    # CalendarList endpoints
    calendar_list = service.calendarList.return_value
    calendar_list.list.return_value.execute.return_value = {"items": []}

    return service


@pytest.fixture
def mock_sheets_service():
    """Pre-configured mock Sheets service."""
    service = MagicMock()

    # Spreadsheets endpoints
    spreadsheets = service.spreadsheets.return_value
    spreadsheets.get.return_value.execute.return_value = {}
    spreadsheets.create.return_value.execute.return_value = {}

    # Values endpoints
    values = spreadsheets.values.return_value
    values.get.return_value.execute.return_value = {"values": []}
    values.update.return_value.execute.return_value = {}
    values.append.return_value.execute.return_value = {}
    values.clear.return_value.execute.return_value = {}
    values.batchGet.return_value.execute.return_value = {"valueRanges": []}
    values.batchUpdate.return_value.execute.return_value = {}

    return service


@pytest.fixture
def mock_docs_service():
    """Pre-configured mock Docs service."""
    service = MagicMock()

    # Documents endpoints
    documents = service.documents.return_value
    documents.get.return_value.execute.return_value = {"body": {"content": []}}
    documents.create.return_value.execute.return_value = {}
    documents.batchUpdate.return_value.execute.return_value = {}

    return service
