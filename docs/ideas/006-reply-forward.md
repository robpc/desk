---
id: 006
title: Reply and Forward
status: idea
effort: M
value: Respond to emails without leaving CLI
created: 2025-02-06
updated: 2025-02-06
adr: null
---

# Idea 006: Reply and Forward

## Problem

After reading an email, users may want to reply or forward. Currently requires switching to web UI.

## Sketch

```bash
# Reply to a message
gmail reply <message-id> --body "Thanks for the update!"

# Reply-all
gmail reply <message-id> --all --body "Sounds good to everyone"

# Forward
gmail forward <message-id> --to "colleague@example.com" --body "FYI"

# Body from stdin
echo "Automated response" | gmail reply <message-id> --stdin
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

Natural extension of send. Common workflow: search → read → reply.

## Effort Guess

M - Building on send infrastructure, but threading and quoting add complexity.

## Notes

Depends on send command (Idea 005) being implemented first.
