---
id: "008"
title: Expanded Google Docs Editing via Native API
status: accepted
date: 2026-02-18
supersedes: []
superseded_by: null
tags: [docs, api, editing, agent-first]
---

# ADR-008: Expanded Google Docs Editing via Native API

## Context

Desk's `docs update` command supports three modes: append, prepend, and full replace. Find-and-replace was added (Idea 038) using the Google Docs API's `ReplaceAllTextRequest`. But agents working with Google Docs still hit a wall quickly:

- **No targeted insertion**: Can't insert text at a specific position without replacing everything
- **No deletion**: Can't remove a range of content
- **No text styling**: Can't bold, italicize, or change font size on specific ranges
- **No paragraph styling**: Can't set headings, indentation, or alignment
- **No markdown-to-native formatting**: Writing formatted content requires manual style application
- **No tables or images**: Two of the most common doc elements have no CLI path
- **No document inspection**: Agents can't discover the structure (indices, headings, element positions) needed to use index-based editing

All of these are supported by the Google Docs API via `batchUpdate` requests. The current limitation forces agents into a destructive pattern: read the entire doc as plain text, modify it, and `--mode replace` the whole thing — nuking all formatting, images, and tables in the process.

## Decision

Expand Desk's Docs editing capabilities via new subcommands under `desk docs`. Each operation gets its own subcommand rather than being a new mode on the existing `update` command.

### New subcommands

- **`desk docs insert`** — Insert text at a specific UTF-16 index
- **`desk docs delete-range`** — Delete content between two UTF-16 indices
- **`desk docs style`** — Apply text styling (bold, italic, font size) to a range
- **`desk docs paragraph-style`** — Apply paragraph styling (heading level) to a range
- **`desk docs write-markdown`** — Insert markdown content with native Google Docs formatting
- **`desk docs insert-table`** — Insert a table at a specific index
- **`desk docs insert-image`** — Insert an image by URL at a specific index
- **`desk docs inspect`** — Show document structure with element indices, headings, and content summary

### Key implementation choices

**Separate subcommands over new modes on `update`**: Agents struggle with complex flag interactions on a single command. Separate subcommands are more discoverable, have clearer `--help` output, and align with ADR-004's principle that each command should be independently understandable. An agent can call `desk docs insert --help` and get exactly what it needs.

**markdown-it-py for markdown parsing**: The `write-markdown` command needs to convert markdown to Google Docs `batchUpdate` requests. markdown-it-py produces a flat token stream (open/close pairs) that maps directly to the linear sequence of `insertText` + `updateTextStyle` requests that `batchUpdate` expects. This is a better fit than tree-based parsers like mistune, which require recursive traversal to flatten into linear API calls. markdown-it-py is also CommonMark compliant with a good plugin ecosystem.

**UTF-16 index utilities**: The Google Docs API uses UTF-16 code unit indices internally. Python strings use Unicode code points. A supplementary character (emoji, some CJK, math symbols above U+FFFF) is 1 Python character but 2 UTF-16 code units. We provide `utf16_len()` and `utf16_offset()` utilities in a dedicated module to handle this conversion correctly.

**Dedicated `docs_editing.py` module**: UTF-16 utilities, text normalization, and shared editing helpers live in `src/desk/services/docs_editing.py`, separate from the existing `docs.py` service client. This keeps the service client focused on API calls and avoids bloating it with text-processing logic.

**`inspect` command**: Agents need to discover document structure before they can use index-based commands like `insert`, `delete-range`, and `style`. Without `inspect`, agents would have to parse raw document JSON to find indices — exactly the kind of friction ADR-004 aims to eliminate. `inspect` returns a structured summary: element indices, heading levels, content previews, and table/image locations.

## Alternatives Considered

### Alternative 1: New modes on the `update` command

**Description**: Add `--mode insert-at`, `--mode delete-range`, `--mode style`, etc. to the existing `desk docs update` command.

**Pros**:
- Single command surface — fewer commands to discover
- Consistent with existing `--mode append/prepend/replace` pattern

**Cons**:
- Overloads a single command with too many modes, each requiring different flags
- `desk docs update --mode style --bold --start 10 --end 20` is harder for agents to parse than `desk docs style --bold --start 10 --end 20`
- Help output becomes unwieldy — "this flag only applies when mode is X"
- Agents struggle with conditional flag requirements (ADR-004)

**Why rejected**: Per ADR-004, agent-first design favors commands that are independently understandable. Each editing operation has different required parameters; separate subcommands make each one self-documenting.

### Alternative 2: Single `desk docs edit` with JSON body

**Description**: A single `edit` command that accepts a JSON payload describing the batch of operations to perform, mapping directly to the Google Docs API `batchUpdate` format.

**Pros**:
- Maximum flexibility — any API operation is expressible
- Single command to maintain
- Power users can compose complex multi-step edits

**Cons**:
- Requires agents to construct raw API payloads — counter to Desk's toolkit philosophy
- No discoverability — agents must already know the API schema
- Error messages would be Google API errors, not Desk structured errors
- Defeats the purpose of a CLI abstraction

**Why rejected**: Desk's value is translating API complexity into simple, composable commands. Exposing raw JSON payloads pushes complexity back onto agents.

### Alternative 3: mistune for markdown parsing

**Description**: Use mistune (tree-based AST) instead of markdown-it-py for the `write-markdown` command.

**Pros**:
- Popular library with good maintenance
- Full AST gives maximum structural information

**Cons**:
- Tree-based AST requires recursive traversal to flatten into linear `batchUpdate` requests
- More complex code to map nested structures to sequential API calls
- No significant advantage for this use case — we don't need tree structure

**Why rejected**: markdown-it-py's flat token stream is a natural fit for Google Docs' linear `batchUpdate` model. Simpler mapping code means fewer bugs.

## Consequences

### Positive

- **Real differentiation**: No other Google Workspace CLI offers agent-friendly document editing with formatting support
- **Precise editing**: Agents can make targeted changes without destroying existing content or formatting
- **Markdown bridge**: `write-markdown` lets agents author formatted content naturally — markdown is the lingua franca of LLM output
- **Self-service discovery**: `inspect` closes the loop — agents can discover structure, then act on it, without human intervention

### Negative

- **More surface area**: Eight new subcommands to document, test, and maintain
  - *Mitigation*: Each command is simple and maps to a small number of API calls; shared utilities reduce duplication
- **New dependency**: markdown-it-py is added to the dependency list
  - *Mitigation*: Well-maintained, pure Python, no transitive dependency bloat
- **UTF-16 math is a subtle bug source**: Off-by-one errors in index conversion can corrupt documents
  - *Mitigation*: Dedicated utility functions with thorough test coverage; all index math goes through `docs_editing.py`, never inline

### Neutral

- Existing `docs update` command is unchanged — no migration needed for current users

## Deferred

The following are explicitly out of scope for this ADR and may be addressed in future work:

- **Batch editing**: Accept a JSON file of multiple operations to execute atomically
- **Suggestion mode**: Insert changes as suggestions (track changes) rather than direct edits
- **Named ranges**: Create and reference named ranges for stable position references
- **Regex in find-replace**: Google Docs API only supports literal string matching; regex would require client-side implementation
- **Page/section breaks**: InsertPageBreak and InsertSectionBreak API calls
- **Extended paragraph styles**: Alignment, line spacing, space before/after, indentation
- **Extended text styles**: Underline, strikethrough, foreground/background color, font family

## Implementation Notes

- UTF-16 utilities and text normalization: `src/desk/services/docs_editing.py`
- New commands added to: `src/desk/commands/docs.py`
- Editing methods added to: `src/desk/services/docs.py`
- New dependency: `markdown-it-py` in `pyproject.toml`
- No new OAuth scopes required — editing uses the existing `documents` scope

## References

- [Google Docs API batchUpdate reference](https://developers.google.com/docs/api/reference/rest/v1/documents/batchUpdate)
- ADR-004: Agent-First CLI Design (separate subcommands for discoverability)
- [Idea 038: Docs Find-and-Replace](../ideas/038-docs-find-replace.md) (implemented, established batchUpdate pattern)
