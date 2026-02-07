---
id: 014
title: Test Suite
status: idea
effort: L
value: Confidence in changes, prevent regressions, enable refactoring
created: 2026-02-06
updated: 2026-02-06
adr: null
---

# Idea 014: Test Suite

## Problem

The codebase has ~2500 lines of code across 5 service clients and their CLI commands, but no automated tests. This makes it risky to refactor and hard to verify changes don't break existing functionality.

## Scope

### Unit Tests (Priority 1)

Test service clients with mocked Google API responses:

- `GmailClient` - search, read, modify, batch_modify, labels
- `DriveClient` - search, read, upload, download, mkdir, move, trash, share, star
- `SheetsClient` - read, write, append, clear, create
- `DocsClient` - create, read, update, export
- `CalendarClient` - today, week, next, find, create, update, delete

Each needs:
- Success cases with mocked API responses
- Error cases (API errors, invalid inputs)
- Edge cases (empty results, large responses)

### Integration Tests (Priority 2)

Test CLI commands end-to-end with mocked clients:

- Each command produces expected output
- `--json` flag works correctly
- `--stdin` batch operations work
- Error messages are helpful

### Auth Tests (Priority 3)

- Token refresh flow
- gcloud ADC fallback
- Credential file handling
- `DESK_DEBUG` logging

## Technical Approach

```python
# Example: mocking Gmail API
from unittest.mock import MagicMock, patch

def test_gmail_search():
    mock_service = MagicMock()
    mock_service.users().messages().list().execute.return_value = {
        "messages": [{"id": "123", "threadId": "456"}]
    }

    with patch("desk.services.gmail.build", return_value=mock_service):
        client = GmailClient(mock_creds)
        results = client.search("is:unread")
        assert len(results) == 1
```

### Tools

- `pytest` - test runner
- `pytest-mock` - mocking utilities
- `responses` or `unittest.mock` - HTTP mocking
- `click.testing.CliRunner` - CLI integration tests

## Open Questions

- [ ] Use real API calls in CI with test account? Or fully mocked?
- [ ] Coverage target? (80%? 90%?)
- [ ] Snapshot testing for CLI output?

## Value Signal

- PR review feedback identified this as a gap
- Enables confident refactoring
- Documents expected behavior

## Effort Guess

L - 5 service clients × ~10 methods each × multiple test cases = significant work. Plus CLI integration tests. Estimate 1000-1500 lines of test code.

## Notes

The code is mostly thin wrappers around Google APIs, so risk of subtle bugs is lower than complex business logic. Tests are still valuable for:
- Documenting expected behavior
- Catching regressions during refactoring
- Verifying error handling paths
