---
id: 010
title: Thread Support
status: idea
effort: M
value: Work with email conversations, not just individual messages
created: 2025-02-06
updated: 2025-02-06
adr: null
---

# Idea 010: Thread Support

## Problem

Gmail groups related messages into threads (conversations). Current CLI operates on individual messages. Sometimes you want to archive/label an entire conversation, or read a full thread.

## Sketch

```bash
# Search returns threads instead of messages
gmail threads "from:boss"
gmail threads "subject:project update" --json

# Read entire thread
gmail thread <thread-id>

# Actions on threads
gmail archive --thread <thread-id>      # archive all messages in thread
gmail label "Work" --thread <thread-id> # label all messages

# Or dedicated commands
gmail thread-archive <thread-id>
gmail thread-label "Work" <thread-id>
```

## Technical Notes

- Gmail API has separate `users.threads.*` endpoints
- Thread contains list of messages
- Thread actions (archive, label) apply to all messages in thread

## Open Questions

- [ ] Should `search` have a `--threads` flag, or separate `threads` command?
- [ ] How to display thread in terminal? (collapsed? expanded? tree?)
- [ ] Should action commands gain `--thread` flag or have separate thread commands?
- [ ] Thread IDs vs message IDs - how to make clear to users?

## Value Signal

More natural for email management - people think in conversations.

## Effort Guess

M - New API endpoints, new display logic, decision on command structure.

## Notes

Many Gmail operations naturally apply to threads. Web UI defaults to thread view. CLI being message-centric might feel unnatural to users.
