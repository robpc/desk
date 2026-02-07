---
id: "025"
title: Pagination Consistency
status: implemented
effort: S
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
- No way to continue from a previous page for large result sets

## Sketch

Standardize list commands with:

```bash
--max <n>         # Maximum results to return (existing)
--limit <n>       # Alias for --max (consistency)
--page-token <t>  # Continue from previous page (cursor-based APIs only)
```

**Page token APIs** (Gmail, Drive, Calendar):
- Add `--page-token` to continue from previous results
- JSON output includes `nextPageToken` when more results exist

**Non-paginated APIs** (Sheets list-sheets, Gmail labels):
- These return all results in one call
- Only `--max`/`--limit` applies (client-side filtering)

Commands to update:
- `desk mail search` - add --page-token, include nextPageToken in JSON
- `desk mail threads` - add --page-token, include nextPageToken in JSON
- `desk mail drafts` - add --page-token, include nextPageToken in JSON
- `desk drive search` - add --page-token, include nextPageToken in JSON
- `desk drive recent` - add --page-token, include nextPageToken in JSON
- `desk cal today/week/next/find` - add --page-token, include nextPageToken in JSON

## Decisions Made

- [x] Keep `--max` and add `--limit` as synonym (no breaking change)
- [x] Drop `--offset` - no Google Workspace APIs use offset pagination
- [x] Drop `--all` - solve when it's actually needed
- [x] Add `--page-token` only for cursor-based APIs

## Value Signal

Consistent pagination enables:
- Processing large result sets page by page
- Predictable scripting across services
- Memory-efficient processing of large mailboxes/drives

## Effort Guess

**S** - Add --page-token flag and wire through to existing API calls. Include nextPageToken in JSON output. Straightforward once pattern is established.

## Notes

- Google Workspace APIs use cursor-based pagination (page tokens), not offset/limit
- Sheets metadata and Gmail labels return everything in one call (no pagination needed)
- Pattern: `--json` output includes `nextPageToken` field when more pages exist
