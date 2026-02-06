---
id: 001
title: Convenience Commands
status: implemented
effort: S
value: Quality-of-life improvements for common operations
created: 2025-02-06
updated: 2025-02-06
adr: null
---

# Idea 001: Convenience Commands

## Problem

Some operations are common enough that shortcuts would improve ergonomics, even though they can be composed with existing commands.

## Candidates

### `unread` - Shortcut for searching unread
```bash
gmail unread              # = gmail search "is:unread"
gmail unread --max 10     # = gmail search "is:unread" --max 10
```

### `remove-label` - Opposite of `label`
```bash
gmail remove-label ID "Work"   # Remove a label from message
```
Currently requires: `gmail modify ID --remove-label Work`

### `star` / `unstar` - Toggle starred status
```bash
gmail star ID        # = gmail modify ID --add-label STARRED
gmail unstar ID      # = gmail modify ID --remove-label STARRED
```

## Open Questions

- [ ] Is `unread` common enough to warrant a command vs alias?
- [ ] Should `star` be a toggle or separate star/unstar commands?
- [ ] Any other common patterns from real usage?

## Value Signal

Came from first real testing session with an agent. These were the patterns that felt verbose.

## Effort Guess

S - Each is a one-liner wrapper around existing functionality.

## Notes

Per ADR-002, we prefer Gmail's vocabulary. All of these (unread, star) are Gmail concepts, so they fit the philosophy.

Batch support (multiple IDs) is a separate, higher-effort idea.

## Implementation (2025-02-06)

Implemented all candidates:
- `gmail unread` - lists unread messages (supports `--max`, `--json`)
- `gmail star ID` - star a message
- `gmail unstar ID` - remove star from a message
- `gmail remove-label ID LABEL` - remove a label from a message

Added corresponding methods to `GmailClient`: `star()`, `unstar()`, `remove_label()`.
