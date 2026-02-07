---
id: 010
title: Thread Support
status: implemented
effort: M
value: Work with email conversations, not just individual messages
created: 2025-02-06
updated: 2026-02-07
adr: null
---

# Idea 010: Thread Support

## Problem

Gmail groups related messages into threads (conversations). Current CLI operates on individual messages. Sometimes you want to archive/label an entire conversation, or read a full thread.

## Sketch

```bash
# Search returns threads instead of messages
desk mail threads "from:boss"
desk mail threads "subject:project update" --json

# Read entire thread
desk mail thread <thread-id>

# Actions on threads
desk mail archive --thread <thread-id>      # archive all messages in thread
desk mail label "Work" --thread <thread-id> # label all messages

# Or dedicated commands
desk mail thread-archive <thread-id>
desk mail thread-label "Work" <thread-id>
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

## Implementation (2026-02-07)

Implemented dedicated thread commands:

```bash
# Search threads
desk mail threads "from:boss"           # Search by thread
desk mail threads "query" --max 10 --json

# Read entire conversation
desk mail thread <thread-id>            # Shows all messages in thread

# Thread actions
desk mail thread-archive <thread-id>    # Archive entire thread
desk mail thread-label Work <thread-id> # Label entire thread
desk mail thread-trash <thread-id>      # Trash entire thread
```

**Design decisions:**
- Separate `threads` command (not `--threads` flag) for clearer semantics
- Dedicated `thread-*` commands rather than `--thread` flags on existing commands
- Thread display shows messages chronologically with clear separators
- All thread action commands support `--dry-run` and `--json`

**Service methods added to GmailClient:**
- `search_threads(query, max_results)` - uses `users.threads.list`
- `get_thread(thread_id)` - uses `users.threads.get` with full format
- `modify_thread(thread_id, add_labels, remove_labels)` - uses `users.threads.modify`

**Thread vs message IDs:**
- Thread ID returned by search is the same as the thread's first message ID in many cases
- Commands clearly named (`thread` vs `read`) to distinguish
