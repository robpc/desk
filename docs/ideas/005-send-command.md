---
id: 005
title: Send Command
status: idea
effort: M
value: Complete the read/write cycle - full email management from CLI
created: 2025-02-06
updated: 2025-02-06
adr: null
---

# Idea 005: Send Command

## Problem

The CLI can read and organize email but cannot send. This is mentioned in CLAUDE.md as a core feature but isn't implemented. Without send, users must switch to web UI or another tool for composing.

## Sketch

```bash
# Basic send
gmail send --to "user@example.com" --subject "Hello" --body "Message body"

# Multiple recipients
gmail send --to "a@example.com" --cc "b@example.com" --bcc "c@example.com" \
  --subject "Team update" --body "..."

# Body from stdin (for piping)
echo "Generated report" | gmail send --to "boss@example.com" --subject "Report" --stdin

# Body from file
gmail send --to "user@example.com" --subject "Notes" --body-file notes.txt

# Attachments (if implemented)
gmail send --to "user@example.com" --subject "Files" --attach report.pdf
```

## Open Questions

- [ ] How to handle multi-line body from CLI? (heredoc? file? stdin?)
- [ ] Support HTML body or plain text only?
- [ ] Attachments in scope or separate idea?
- [ ] `--dry-run` to preview without sending?
- [ ] Confirmation prompt before sending? (destructive in a different way)

## Value Signal

Mentioned in CLAUDE.md as core feature. Natural expectation for a "Gmail CLI".

## Effort Guess

M - Gmail API for sending is straightforward, but good UX for composing multi-line messages from CLI takes thought.

## Notes

- Gmail API: `users.messages.send` with RFC 2822 formatted message
- Need to build MIME message (python `email` stdlib handles this)
- Consider requiring `--yes` or interactive confirm since sending is irreversible
