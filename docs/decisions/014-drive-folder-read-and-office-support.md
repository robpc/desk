---
id: 014
title: Drive Folder Listing, Batch Read, and Office File Support
status: accepted
date: 2026-03-03
supersedes: []
superseded_by: null
tags: [drive, cli, batch, agents, office, composability]
---

# ADR-014: Drive Folder Listing, Batch Read, and Office File Support

## Context

Reading all files in a Google Drive folder currently requires N separate `desk drive read <id>` calls orchestrated by the agent. Uploaded Office files (.docx, .xlsx) come back as binary garbage because `DriveClient.read()` downloads them raw and does `content.decode("utf-8", errors="replace")`.

This surfaced in a real workflow: batch-reading 20+ files from a research folder. Google-native files (Docs, Sheets) worked fine via the export API, but the uploaded .docx and .xlsx were unreadable.

## Decision

### 1. Add `desk drive list-folder <folder-id>` — list files in a folder

A new primitive command that returns file metadata (id, name, mimeType, modifiedTime, size) without reading content:
- Supports `--page-token` for external pagination (matches `search` and `recent` patterns)
- Supports `--type` to filter by friendly MIME type name (e.g. `document`, `spreadsheet`, `pdf`)
- Filters out sub-folders and shortcuts by default
- JSON output includes `nextPageToken` for pagination

### 2. Extend `desk drive read` to accept multiple IDs and `--stdin`

Instead of a compound `read-folder` command, we extend `read` to be composable:
- `desk drive read ID1 ID2 ID3` — read multiple files by argument
- `desk drive list-folder <id> --json | jq -r '.files[].id' | desk drive read --stdin` — pipe from list-folder
- Single-file behavior is unchanged for backward compatibility
- Batch errors use `structured_error()` per file (no silent failures)

This follows the ADR-002 principle: "provide vocabulary, agents write sentences." The agent composes `list-folder` + `read --stdin` instead of calling a monolithic `read-folder`.

### 3. Add local conversion for Office files in `DriveClient.read()`

Route uploaded .docx and .xlsx files to local converters:
- `.docx` -> `python-docx`: extracts paragraph text and table content
- `.xlsx` -> `openpyxl`: reads all sheets as CSV with sheet separators

These are production dependencies (not optional), imported at module level in `services/drive.py`.

## Alternatives Considered

### Alternative 1: Compound `read-folder` command

**Description**: Single command that lists AND reads all files in a folder.

**Pros**:
- One command for the whole workflow
- Simpler for basic use

**Cons**:
- Violates ADR-002 composability principle (invents vocabulary)
- Cannot filter files before reading (wastes API calls)
- Cannot paginate listing separately from reading
- Cannot reuse listing for non-read workflows (e.g. move, trash, share)

**Why rejected**: Compound commands prevent composition. Agents can pipe `list-folder | read --stdin` and insert filtering (`jq`, `--type`) between the steps.

### Alternative 2: Google Import-then-Export

**Description**: Use Google's API to import Office files to native format, then export as text.

**Pros**:
- No new dependencies
- Google handles all format quirks

**Cons**:
- Mutates Drive state (creates temporary native copies)
- Slow (import + export = 2 API calls)
- Lossy conversion
- Cleanup required (delete temp files)

**Why rejected**: Read-only local conversion is cleaner, faster, and doesn't touch the user's Drive.

### Alternative 3: Pandoc as external dependency

**Description**: Use pandoc for universal document conversion.

**Pros**:
- Handles many more formats
- High-fidelity conversion

**Cons**:
- Heavy external dependency (not pip-installable)
- Platform-specific installation
- Overkill for two formats

**Why rejected**: openpyxl and python-docx are pure Python, pip-installable, and sufficient.

## Consequences

### Positive

- Agents can enumerate then selectively read files (composable primitives)
- `list-folder` is reusable for move, trash, share, and other batch workflows
- .docx and .xlsx files are now human/agent-readable
- `read --stdin` pattern matches mail commands (`desk mail archive --stdin`)
- Follows ADR-002: no invented vocabulary

### Negative

- Two new production dependencies (openpyxl, python-docx)
  - *Mitigation*: Both are pure Python, well-maintained, lightweight
- python-docx doesn't extract headers/footers or embedded images
  - *Mitigation*: Sufficient for text content; `desk drive download` available for full fidelity
- Batch folder read requires piping two commands instead of one
  - *Mitigation*: The pipe is trivial and enables filtering between steps

### Neutral

- `list-folder` output ordering is `modifiedTime desc` (matches existing search/recent behavior)
- Multi-sheet .xlsx files use `--- sheet: SheetName ---` separators

## Implementation Notes

**Key files**:
- `src/desk/services/drive.py` — `_read_docx()`, `_read_xlsx()`, `list_folder()`, updated `read()`
- `src/desk/commands/drive.py` — `list-folder` command, `read --stdin`, `_collect_ids()`
- `pyproject.toml` — Added `openpyxl>=3.1` and `python-docx>=1.0`

## References

- [Idea 046: Drive Folder Read](../ideas/046-drive-folder-read.md)
- [ADR-002: Command Composability](002-command-composability.md) (design principle)
- [ADR-006: Query-Based Bulk Operations](006-query-based-bulk-operations.md) (pattern reference)
