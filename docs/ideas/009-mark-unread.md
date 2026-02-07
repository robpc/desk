---
id: 009
title: Mark Unread Command
status: idea
effort: S
value: Complete symmetry with mark-read
created: 2025-02-06
updated: 2025-02-06
adr: null
---

# Idea 009: Mark Unread Command

## Problem

We have `mark-read` but no `mark-unread`. Sometimes you read a message but want to mark it unread as a reminder to deal with it later.

## Sketch

```bash
gmail mark-unread <id>
gmail mark-unread ID1 ID2 ID3           # batch
gmail search "..." --json | jq -r '.[].id' | gmail mark-unread --stdin
```

## Implementation

Trivial - add UNREAD label:
```python
def mark_unread(self, message_id: str) -> None:
    self.modify_message(message_id, add_labels=["UNREAD"])
```

CLI is copy of mark-read with label flipped.

## Open Questions

None - straightforward.

## Value Signal

Completeness. Users expect symmetry.

## Effort Guess

S - 15 minutes. Copy mark-read, change label.

## Notes

Could arguably be part of convenience commands (Idea 001) but that's already implemented. This is a gap that was missed.
