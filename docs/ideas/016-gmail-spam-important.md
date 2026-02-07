---
id: "016"
title: Gmail Spam and Important Markers
status: idea
effort: S
value: Complete message classification primitives
created: 2026-02-07
updated: 2026-02-07
adr: null
---

# Idea 016: Gmail Spam and Important Markers

## Problem

Desk has `star`/`unstar` and `archive` commands but lacks commands for spam reporting and importance marking. These are first-class Gmail concepts with dedicated system labels (SPAM, IMPORTANT) that have semantic meaning beyond regular labels.

## Sketch

```bash
desk mail spam <message-id>...         # Report as spam (moves to spam folder)
desk mail not-spam <message-id>...     # Mark as not spam (moves to inbox)
desk mail important <message-id>...    # Mark as important
desk mail not-important <message-id>...# Remove important marker
```

All commands support:
- Multiple message IDs as arguments
- `--stdin` for piping IDs
- `--dry-run` for preview
- `--json` for structured output

Implementation uses the existing `modify` infrastructure with the SPAM and IMPORTANT labels.

## Open Questions

- [ ] Does marking as spam also report to Google for spam filtering improvement?
- [ ] Should `not-spam` automatically move to INBOX or just remove SPAM label?
- [ ] Is IMPORTANT label behavior different from regular labels (ML-driven)?

## Value Signal

Spam management is essential for email hygiene. The `important` marker integrates with Gmail's priority inbox. These are basic email operations that any complete email client supports.

## Effort Guess

**S** - These are thin wrappers around the existing `modify` command infrastructure. Just need to map the semantic operations to the correct label additions/removals.

## Notes

- SPAM and IMPORTANT are system labels, already defined in Gmail
- Marking as spam may trigger Gmail's spam learning
- Consider: should spam also remove from INBOX? Gmail does this automatically
- Follows pattern established by `star`/`unstar`, `archive`
