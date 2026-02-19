---
id: "010"
title: Google Docs Tab Support
status: accepted
date: 2026-02-19
supersedes: []
superseded_by: null
tags: [docs, tabs, api, agent-first]
---

# ADR-010: Google Docs Tab Support

## Context

Google Docs added document tabs in late 2024 — similar to sheet tabs in spreadsheets, a single document can have multiple tabs with independent content. The API supports this via:

- `includeTabsContent` parameter on `documents.get`
- `createTab` request in `batchUpdate`
- `deleteTab` request in `batchUpdate`
- `updateDocumentTabProperties` request in `batchUpdate`
- `tabId` field in location/range objects for content operations

Desk has no tab support today. All operations implicitly target the first (default) tab. As document tabs become more common, agents need the ability to manage and target specific tabs.

## Decision

Add tab support to Desk Docs in two parts:

### 1. Tab management commands

Following the Sheets tab pattern (`sheets list-sheets`, `sheets add-sheet`, etc.):

- **`desk docs list-tabs <id>`** — List tabs with ID, title, and nesting
- **`desk docs add-tab <id> --title "Name"`** — Create a tab (optional `--index`, `--parent`)
- **`desk docs delete-tab <id> --tab <tab-id>`** — Delete a tab (with `--yes` for skip confirm)
- **`desk docs rename-tab <id> --tab <tab-id> --title "New"`** — Rename a tab

### 2. `--tab` option on content commands

All content-targeting commands gain `--tab <tab-id>` to target a specific tab:

`read`, `update`, `inspect`, `insert`, `delete-range`, `style`, `paragraph-style`, `write-markdown`, `insert-table`, `insert-image`

When `--tab` is omitted, behavior is identical to today (first/default tab).

### Implementation approach

**Service layer**: New `list_tabs()`, `add_tab()`, `delete_tab()`, `rename_tab()` methods. Existing content methods gain `tab_id: str | None = None` parameter. Helper methods `_get_body()` for tab-aware reads and `_location()` / `_range()` for tab-aware location objects.

**Markdown converter**: `markdown_to_requests()` gains `tab_id` parameter, injecting `tabId` into all generated location and range objects.

## Alternatives Considered

### Alternative 1: Tab support as separate commands only

**Description**: Only add tab management (list/add/delete/rename) but don't add `--tab` to content commands. Users would need to read/write the default tab only.

**Pros**:
- Simpler implementation — fewer methods to modify

**Cons**:
- Defeats the purpose — managing tabs is useless if you can't put content in them
- Agents would have no way to write to non-default tabs

**Why rejected**: Tab management without content targeting is incomplete.

### Alternative 2: Tab name instead of tab ID

**Description**: Use `--tab "Tab Name"` instead of `--tab <tab-id>` for targeting.

**Pros**:
- More human-friendly
- Avoids needing to look up tab IDs

**Cons**:
- Tab names aren't unique — a document can have multiple tabs with the same name
- Requires an extra API call to resolve name to ID
- Agents should use `list-tabs` to discover IDs, which is more reliable

**Why rejected**: Tab IDs are unambiguous. Agents can discover them via `list-tabs`.

## Consequences

### Positive

- **Full tab lifecycle**: Create, list, rename, delete, and target content in specific tabs
- **Backwards compatible**: Omitting `--tab` preserves existing behavior
- **Consistent pattern**: Follows the same naming convention as Sheets tab management

### Negative

- **Many methods touched**: 10+ service methods and commands gain `tab_id` parameter
  - *Mitigation*: The change is mechanical — add parameter, inject into location objects
- **API version dependency**: Tab features require a recent API version
  - *Mitigation*: The Docs API v1 already supports tabs; no version change needed

### Neutral

- Tab IDs are opaque strings assigned by Google — agents must call `list-tabs` to discover them

## Implementation Notes

- `src/desk/services/docs.py` — 4 new methods + `tab_id` param on 10 existing methods
- `src/desk/commands/docs.py` — 4 new commands + `--tab` option on 10 existing commands
- `src/desk/services/markdown_to_docs.py` — `tab_id` param on `markdown_to_requests`
- No new OAuth scopes required

## References

- [Google Docs API tabs documentation](https://developers.google.com/docs/api/concepts/tabs)
- [batchUpdate createTab](https://developers.google.com/docs/api/reference/rest/v1/documents/batchUpdate)
- ADR-008: Expanded Docs Editing (established subcommand pattern)
