---
id: 006
title: Reply and Forward
status: implemented
effort: M
value: Respond to emails without leaving CLI
created: 2025-02-06
updated: 2026-02-07
adr: null
---

# Idea 006: Reply and Forward

## Problem

After reading an email, users may want to reply or forward. Currently requires switching to web UI.

## Sketch

```bash
# Reply to a message
desk mail reply <message-id> --body "Thanks for the update!"

# Reply-all
desk mail reply <message-id> --all --body "Sounds good to everyone"

# Forward
desk mail forward <message-id> --to "colleague@example.com" --body "FYI"

# Body from stdin
echo "Automated response" | desk mail reply <message-id> --stdin
```

## Technical Notes

- Reply needs to set `In-Reply-To` and `References` headers for threading
- Reply-to address should come from original message's `Reply-To` or `From`
- Gmail API: same `users.messages.send` but with `threadId` to keep in thread
- Forward includes original message body (quoted)

## Open Questions

- [ ] Include quoted original in reply? (Gmail style)
- [ ] How to handle attachments on forward?
- [ ] Reply to specific recipient vs reply-all default?

## Value Signal

Natural extension of send. Common workflow: search -> read -> reply.

## Effort Guess

M - Building on send infrastructure, but threading and quoting add complexity.

## Notes

Depends on send command (Idea 005) being implemented first.

## Implementation (2026-02-07)

Implemented both reply and forward commands:

```bash
# Reply to sender
desk mail reply MESSAGE_ID --body "Thanks!"

# Reply to all (sender + To + CC)
desk mail reply MESSAGE_ID --all --body "Sounds good"

# Forward with optional note
desk mail forward MESSAGE_ID --to "colleague@example.com"
desk mail forward MESSAGE_ID --to "user@example.com" --body "FYI - see below"

# Body from stdin or file
echo "Response" | desk mail reply MESSAGE_ID --stdin
desk mail reply MESSAGE_ID --body-file response.txt
```

**Technical implementation:**
- Reply sets `In-Reply-To` and `References` headers for proper threading
- Reply uses `Reply-To` header if present, otherwise `From`
- Reply sends with `threadId` to keep messages in same Gmail thread
- Forward includes quoted original with standard Gmail-style header block
- Forward creates new thread (no threadId)

**Decisions made:**
- No quoted original in reply body (keeps it simple, user can add context)
- Attachments on forward not included (separate idea 008)
- Reply defaults to sender only; use `--all` for reply-all
