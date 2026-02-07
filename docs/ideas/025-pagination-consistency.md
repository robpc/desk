---
id: "025"
title: Pagination Consistency
status: idea
effort: M
value: Uniform pagination across all list commands
created: 2026-02-07
updated: 2026-02-07
adr: null
---

# Idea 025: Pagination Consistency

## Problem

List commands have inconsistent pagination support:
- Some have `--max` (cal commands)
- Some have no limit option
- None have `--offset` or cursor-based pagination
- No way to auto-paginate through all results

This makes it hard to process large result sets or script consistent behavior across services.

## Sketch

Standardize all list commands with:

```bash
--limit <n>       # Maximum results to return (renamed from --max for consistency)
--offset <n>      # Skip first N results (where API supports)
--page-token <t>  # Continue from previous page (for cursor-based APIs)
--all             # Auto-paginate and return all results (with reasonable safeguards)
```

Commands affected:
- `desk mail search` - add --limit, --offset, --all
- `desk mail threads` - add --limit, --offset, --all
- `desk mail labels` - add --limit
- `desk mail drafts` - add --limit, --offset, --all
- `desk drive search` - add --limit, --offset, --all
- `desk drive recent` - already has --max, rename to --limit
- `desk sheets list-sheets` - add --limit
- `desk cal today/week/next` - already have --max, rename to --limit
- `desk cal find` - add --limit

## Open Questions

- [ ] Should we rename existing --max to --limit for consistency?
- [ ] How to handle APIs with different pagination models (offset vs cursor)?
- [ ] What's a safe default for --all? (prevent accidental huge fetches)
- [ ] Should --all show progress for large result sets?

## Value Signal

Consistent pagination enables:
- Predictable scripting across services
- Processing large mailboxes/drives
- Page-by-page processing for memory efficiency

Currently each command works slightly differently.

## Effort Guess

**M** - Need to audit all list commands, understand each API's pagination model, and implement consistently. Some APIs use cursors, others use offsets. The `--all` feature needs careful implementation.

## Notes

- Google APIs use different pagination: Gmail uses page tokens, Drive uses page tokens, Sheets doesn't paginate sheet lists
- Consider: output format for --all (streaming vs buffered)
- Breaking change if renaming --max to --limit (deprecation period?)
- This is infrastructure work that improves all services
