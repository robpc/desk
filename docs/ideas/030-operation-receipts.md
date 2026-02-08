---
id: 030
title: Operation Receipts with Undo Commands
status: planned
effort: M
value: Agents get proof of what happened and can reverse mistakes
created: 2025-02-07
updated: 2025-02-07
adr: 004-agent-first-cli.md
---

# Idea 030: Operation Receipts with Undo Commands

## Problem

After a mutating operation, agents don't know:
- Exactly what happened (did it work? what changed?)
- How to reverse it if needed
- Whether reversal is even possible
- How long they have to undo

Current output for `desk mail archive abc123`:
```
Archived 1 message(s)
```

Not enough for an agent to confidently proceed or recover.

## Sketch

Every mutating command returns a receipt:

```json
{
  "success": true,
  "operation": "archive",
  "timestamp": "2025-02-07T10:30:00Z",
  "target": {
    "type": "message",
    "id": "abc123",
    "subject": "Q4 Report",
    "from": "boss@company.com"
  },
  "changes": {
    "labels_removed": ["INBOX"],
    "labels_added": []
  },
  "undo": {
    "available": true,
    "command": "desk mail unarchive abc123",
    "expires": "No expiration",
    "notes": "Move back to inbox"
  }
}
```

### Undo Commands by Operation

| Operation | Undo Command | Expiration |
|-----------|--------------|------------|
| `archive` | `unarchive` (add INBOX label) | Never |
| `trash` | `untrash` | 30 days (auto-deleted after) |
| `label add` | `remove-label` | Never |
| `mark-read` | `mark-unread` | Never |
| `star` | `unstar` | Never |
| `send` | None | Irreversible |
| `delete` | None | Irreversible |

### Batch Operations

For batch operations, receipt includes all targets:

```json
{
  "success": true,
  "operation": "archive",
  "timestamp": "2025-02-07T10:30:00Z",
  "count": 5,
  "targets": [
    {"id": "abc123", "subject": "Report 1"},
    {"id": "def456", "subject": "Report 2"},
    // ...
  ],
  "undo": {
    "available": true,
    "command": "desk mail unarchive abc123 def456 ...",
    "expires": "No expiration"
  }
}
```

### Human-Readable Mode

```
✓ Archived 1 message

  Subject: Q4 Report
  From: boss@company.com

Undo: desk mail unarchive abc123
```

## Open Questions

- [ ] How much target detail to include? (Subject is useful, but full body is too much)
- [ ] Should we store undo history somewhere? (e.g., `desk undo` to reverse last action)
- [ ] For batch operations with many items, truncate target list?

## Value Signal

This is what makes agents trustworthy with email. "I archived your Q4 report. Here's the undo command if that was wrong." That's confidence-inspiring for users delegating to agents.

## Effort Guess

M - Need to capture target details before operations, add undo metadata. Most operations already have natural inverses; the work is surfacing them consistently.

## Notes

Depends on: Idea 028 (Agent-First Framework)

The undo command feature is particularly valuable because:
1. Agents can offer "undo" in their responses
2. Users see exactly how to reverse an action
3. Creates accountability — agents can't hide what they did

Related: ADR-004, Idea 028
