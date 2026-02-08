---
id: 034
title: Extend Agent-First to All Services
status: planned
effort: M
value: Consistent agent experience across all desk commands
created: 2025-02-08
updated: 2025-02-08
adr: 004-agent-first-cli.md
---

# Idea 034: Extend Agent-First to All Services

## Problem

Agent-first features (structured errors, operation receipts, enhanced dry-run) are only implemented for mail commands. Drive, cal, sheets, and docs still use the old patterns, creating an inconsistent experience.

## Current State

| Service | Structured Errors | Operation Receipts | Enhanced Dry-Run |
|---------|-------------------|-------------------|------------------|
| mail    | ✅                | ✅                | ✅               |
| drive   | ❌                | ❌                | ❌               |
| cal     | ❌                | ❌                | ❌               |
| sheets  | ❌                | ❌                | ❌               |
| docs    | ❌                | ❌                | ❌               |

## Scope

### Drive Commands to Update
- `trash` / `untrash` - receipts with undo
- `star` / `unstar` - receipts with undo
- `upload` / `download` - receipts
- `mkdir` / `move` - receipts
- `share` - receipt (no undo - sharing is complex to reverse)
- All commands - structured error handling

### Cal Commands to Update
- `create` - receipt (no undo - can't uncreate)
- `update` - receipt
- `delete` - receipt (no undo)
- All commands - structured error handling

### Sheets Commands to Update
- `write` / `append` / `clear` - receipts
- `create` - receipt
- All commands - structured error handling

### Docs Commands to Update
- `create` / `update` - receipts
- All commands - structured error handling

## Implementation

The patterns are established in mail.py:
1. Import agent utilities
2. Add `_handle_api_error()` helper
3. Wrap API calls in try/except
4. Return `operation_receipt()` for mutating operations
5. Use `dry_run_preview()` for dry-run output

## Open Questions

- [ ] Should we add idempotency keys to cal create? (prevent duplicate events)
- [ ] Drive operations are more complex (folders, permissions) - same receipt format?

## Effort Guess

M - Patterns established, mostly mechanical application. ~4 files, ~200 lines each.

## Notes

Real agent usage on mail commands validated the approach. Extending to all services ensures consistent experience regardless of which service an agent is working with.

Related: ADR-004, Ideas 028-033
