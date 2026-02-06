---
id: 002
title: Batch Operations
status: idea
effort: M
value: Efficiency for bulk email management
created: 2025-02-06
updated: 2025-02-06
adr: null
---

# Idea 002: Batch Operations

## Problem

Currently, operating on multiple messages requires looping:
```bash
for id in ID1 ID2 ID3; do gmail archive $id; done
```

This is verbose and makes multiple API calls.

## Sketch

### Option A: Multiple arguments
```bash
gmail archive ID1 ID2 ID3
gmail mark-read ID1 ID2 ID3
gmail modify ID1 ID2 ID3 --remove-label INBOX
```

### Option B: Stdin support
```bash
gmail search "from:bot" --json | jq -r '.[].id' | gmail archive --stdin
```

### Option C: Both
Support both multiple arguments AND stdin piping.

## Technical Notes

Gmail API has `batchModify` endpoint that accepts multiple message IDs in one call:
```
POST /gmail/v1/users/me/messages/batchModify
{
  "ids": ["id1", "id2", "id3"],
  "addLabelIds": ["LABEL"],
  "removeLabelIds": ["LABEL"]
}
```

This is more efficient than individual modify calls.

## Open Questions

- [ ] Should all commands support batch, or just action commands?
- [ ] How to handle partial failures (some IDs succeed, some fail)?
- [ ] Output format for batch operations?

## Value Signal

Common pattern when triaging email: "archive all of these notifications"

## Effort Guess

M - Need to update CLI argument handling, add batchModify to gmail.py, handle error cases.

## Notes

This pairs well with `--json` output for piping search results to actions.
