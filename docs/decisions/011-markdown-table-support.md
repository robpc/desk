---
id: "011"
title: Markdown Table Support in write-markdown
status: accepted
date: 2026-02-22
supersedes: []
superseded_by: null
tags: [docs, markdown, tables]
---

# ADR-011: Markdown Table Support in write-markdown

## Context

`desk docs write-markdown` converts markdown to native Google Docs formatting. It handles headings, bold, italic, code, links, lists, and horizontal rules — but silently drops markdown tables. Tables render as raw pipe-character text instead of native Google Docs tables.

Tables are one of the most common formatting elements in documents. Agents generating reports, comparisons, or structured data frequently use markdown tables. Dropping them is a significant gap.

## Decision

Add markdown table parsing and native Google Docs table generation to `write-markdown`.

### Key implementation choices

**Enable markdown-it-py's built-in table extension**: `md.enable("table")` on the CommonMark parser adds GFM-style table support. No new dependencies needed — the extension ships with markdown-it-py.

**Single batchUpdate with pre-calculated cell indices**: The Google Docs API's `insertTable` creates an empty table with a deterministic index layout. Cell indices follow the formula:

```
cell(i, j) = table_start + 4 + i * (2 * num_cols + 1) + j * 2
```

Cell content is inserted in **reverse row-major order** (bottom-right to top-left) so that each insertion at an earlier index only shifts cells that have already been processed. This allows table creation and population in a single `batchUpdate` call — no document re-reads needed.

**Segment-based parsing**: The converter now returns `ContentSegment` objects — either text (with annotations) or table (with cell content and per-cell annotations). `markdown_to_requests()` processes segments front-to-back, tracking a running cursor, and generates all requests for a single `batchUpdate`.

**Bold header cells by default**: Markdown table headers (`<th>`) are automatically bolded, matching standard document conventions.

## Alternatives Considered

### Multi-batchUpdate approach

Insert each segment (text or table) in a separate `batchUpdate` call, re-reading the document between calls to find insertion points.

**Pros**: Simpler index math — no cross-segment offset tracking.

**Cons**: Multiple API calls per document (one per segment). Slow for documents with several tables. Unnecessary since the single-call approach is correct.

**Why rejected**: Pre-calculated indices are deterministic and well-tested. One API call is always preferable to many.

### Re-read document after insertTable

Insert the table, call `documents.get()` to find cell indices, then populate cells.

**Pros**: No index math at all — read the actual indices from the API.

**Cons**: Requires two additional API calls per table (get + populate). The empty table index layout is deterministic, making re-reads wasteful.

**Why rejected**: Unnecessary overhead when the index formula is known and testable.

## Consequences

### Positive

- `write-markdown` now handles the full range of common markdown formatting
- Agents can generate documents with tables without workarounds
- Single API call — no performance regression for table-free documents, minimal overhead for documents with tables

### Negative

- Table cell index math is subtle — off-by-one errors could corrupt documents
  - *Mitigation*: Thorough unit tests for index calculation with various table sizes
- Inline formatting in table cells adds complexity
  - *Mitigation*: Reuses existing inline token processing with redirected output buffers

## Implementation Notes

- `src/desk/services/markdown_to_docs.py` — table parsing, `TableData`, `ContentSegment`, cell index formula
- `tests/test_services/test_markdown_to_docs.py` — table parsing and request generation tests
- No changes to CLI commands, service client, or OAuth scopes
