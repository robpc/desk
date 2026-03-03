---
id: "015"
title: Google Shared Drive Support
status: accepted
date: 2026-03-03
supersedes: []
superseded_by: null
tags: [drive, api]
---

# ADR-015: Google Shared Drive Support

## Context

Every Google Drive API v3 call in `DriveClient` is missing the parameters required to access files on Shared Drives (formerly Team Drives). The OAuth scope (`drive`) is correct, but individual API calls need `supportsAllDrives=True`, `includeItemsFromAllDrives=True`, and appropriate `corpora` values. This causes:

- Search/list operations to silently exclude Shared Drive files
- Direct file access by ID to return 404 errors for Shared Drive files
- All write operations targeting Shared Drive folders to fail

All 22 DriveClient methods and 2 DocsClient drive calls are affected.

## Decision

We will add Shared Drive support through centralized helper methods in `DriveClient` that inject the required parameters into every API call. Specifically:

1. **Helper wrappers** (`_files_get`, `_files_list`, `_files_update`, `_files_create`, `_permissions_create`, etc.) that always inject `supportsAllDrives=True` and, for list operations, `includeItemsFromAllDrives=True` with configurable `corpora`.
2. **Default to `corpora="allDrives"`** on list operations so search/recent/list-folder include Shared Drive files out of the box.
3. **`--drive-id` flag** on search, recent, and list-folder commands to scope to a specific Shared Drive (sets `corpora="drive"` + `driveId`).
4. **`--my-drive` flag** on search, recent, and list-folder as a performance shortcut (sets `corpora="user"`).
5. **`desk drive list-drives` command** to discover available Shared Drives.
6. **DocsClient** gets a small helper for its 2 drive calls.

## Alternatives Considered

### Alternative 1: Add parameters to each call individually

**Description**: Directly add `supportsAllDrives=True` to every API call site.

**Pros**:
- Simple, no abstraction
- Easy to review

**Cons**:
- Repetitive — easy to miss one call
- Future calls must remember to add it
- No single place to change behavior

**Why rejected**: Error-prone and not future-proof.

### Alternative 2: Monkey-patch or wrap the Google API service object

**Description**: Override the service builder to always inject parameters.

**Pros**:
- Zero changes to existing methods

**Cons**:
- Fragile — depends on internal Google client library structure
- Hard to debug
- Different parameters needed for different call types

**Why rejected**: Too magical, too fragile.

## Consequences

### Positive

- All existing commands work with Shared Drive files without user action
- Performance-conscious users can scope with `--drive-id` or `--my-drive`
- Future Drive methods automatically get Shared Drive support via helpers

### Negative

- `corpora="allDrives"` is slower than `"user"` for large orgs (mitigated by `--my-drive` flag)
- `transfer_ownership` doesn't work on Shared Drive files (API limitation — we surface a clear error)

## Implementation Notes

- Key files: `src/desk/services/drive.py`, `src/desk/services/docs.py`, `src/desk/commands/drive.py`
- Edge cases: ownership transfer fails on Shared Drives, trash may be restricted by org policy, `organizer`/`fileOrganizer` roles exist on Shared Drives
- Do NOT set `driveId` with `corpora="allDrives"` (API rejects this combination)
