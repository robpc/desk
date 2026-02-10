---
id: 005
title: Send Command
status: implemented
effort: M
value: Complete the read/write cycle - full email management from CLI
created: 2025-02-06
updated: 2026-02-07
adr: null
---

# Idea 005: Send Command

## Problem

The CLI can read and organize email but cannot send. Without send, users must switch to web UI or another tool for composing.

## Sketch

```bash
# Basic send
desk mail send --to "user@example.com" --subject "Hello" --body "Message body"

# Multiple recipients
desk mail send --to "a@example.com" --cc "b@example.com" --bcc "c@example.com" \
  --subject "Team update" --body "..."

# Body from stdin (for piping)
echo "Generated report" | desk mail send --to "boss@example.com" --subject "Report" --stdin

# Body from file
desk mail send --to "user@example.com" --subject "Notes" --body-file notes.txt

# Attachments (if implemented)
desk mail send --to "user@example.com" --subject "Files" --attach report.pdf
```

## Open Questions

- [ ] How to handle multi-line body from CLI? (heredoc? file? stdin?)
- [x] Support HTML body or plain text only? → `--html` flag added (PR #4)
- [ ] Attachments in scope or separate idea?
- [ ] `--dry-run` to preview without sending?
- [ ] Confirmation prompt before sending? (see Idea 013)

## Value Signal

Natural expectation for an email CLI. Completes the read/write cycle.

## Effort Guess

M - Gmail API for sending is straightforward, but good UX for composing multi-line messages from CLI takes thought.

## Notes

- Gmail API: `users.messages.send` with RFC 2822 formatted message
- Need to build MIME message (python `email` stdlib handles this)
- Consider requiring `--yes` or interactive confirm since sending is irreversible

## Implementation (2026-02-07)

Implemented with all core functionality:

```bash
# Basic send
desk mail send --to "user@example.com" --subject "Hello" --body "Message"

# Multiple recipients
desk mail send --to "a@example.com" --cc "b@example.com" --bcc "c@example.com" \
  --subject "Update" --body "..."

# Body from stdin
echo "Report" | desk mail send --to "boss@example.com" --subject "Report" --stdin

# Body from file
desk mail send --to "user@example.com" --subject "Notes" --body-file notes.txt

# JSON output
desk mail send --to "user@example.com" --subject "Test" --body "Hi" --json
```

**Decisions made:**
- ~~Plain text only (no HTML)~~ — `--html` flag added in PR #4; builds `multipart/alternative` with plain-text fallback
- No attachments - separate idea (008)
- No confirmation prompt - can add via idea 013 (safety confirmations)
- No dry-run - can add via idea 011
- Body required via exactly one of: `--body`, `--body-file`, `--stdin`
