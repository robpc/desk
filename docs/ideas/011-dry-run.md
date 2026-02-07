---
id: 011
title: Dry Run Mode
status: idea
effort: S
value: Preview actions without executing - safer automation
created: 2025-02-06
updated: 2026-02-06
adr: null
---

# Idea 011: Dry Run Mode

## Problem

Action commands (archive, trash, label, etc.) execute immediately. For automation and scripting, it's useful to preview what would happen without actually doing it.

## Sketch

```bash
# Preview archive
desk mail archive ID1 ID2 ID3 --dry-run
# Output: Would archive 3 messages: ID1, ID2, ID3

# Preview batch operation
desk mail search "from:notifications" --json | jq -r '.[].id' | desk mail archive --stdin --dry-run
# Output: Would archive 47 messages

# Preview label
desk mail label "Archive" ID1 ID2 --dry-run
# Output: Would add label "Archive" to 2 messages
```

## Implementation

Add `--dry-run` flag to all action commands. When set:
1. Collect message IDs as normal
2. Validate they exist (optional - could skip for speed)
3. Print what would happen
4. Exit without calling API

## Open Questions

- [ ] Should dry-run validate message IDs exist? (extra API call)
- [ ] JSON output for dry-run? `{"dry_run": true, "action": "archive", "count": 3, ...}`
- [ ] Global `--dry-run` flag or per-command?

## Value Signal

Standard practice for CLI tools with side effects. Mentioned in CLAUDE.md as verification infrastructure.

## Effort Guess

S - Add flag and conditional to each action command. Mostly copy-paste.

## Notes

Applies to all desk services, not just mail:
- `desk drive trash --dry-run`
- `desk cal delete --dry-run`
- `desk sheets clear --dry-run`
