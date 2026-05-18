---
id: "024"
title: Doc-wide Range Convenience for `paragraph-style`
status: accepted
date: 2026-05-18
supersedes: []
superseded_by: null
tags: [docs, cli, agent-first]
---

# ADR-024: Doc-wide Range Convenience for `paragraph-style`

## Context

`desk docs paragraph-style` requires explicit `--start` and `--end` index
arguments. Applying a paragraph-style change to a whole document — the
canonical retrofit case from
[ADR-017](017-paragraph-spacing-and-named-styles.md) ("I forgot to pass
`--space-below 8` to `write-markdown` and now want to add it everywhere") —
forces callers to compute the end index themselves. The typical sequence is:

```bash
desk docs inspect <id> --json | jq '.elements[-1].endIndex'
# read that number
desk docs paragraph-style <id> --start 1 --end <that number minus 1> --space-below 8
```

That's two CLI calls for a one-intent operation. Worse, agents have to
parse JSON output to drive the second call — exactly the kind of
orchestration ADR-006 (Query-Based Bulk Operations) and ADR-023
(Multi-Calendar Query) say the CLI should handle internally.

ADR-017 explicitly deferred this convenience to a follow-up. This ADR
delivers it. See [Idea 048](../ideas/048-paragraph-style-doc-wide-convenience.md).

## Decision

Add a `--all` flag to `desk docs paragraph-style`. When set, the command
internally fetches the document body, computes the valid index range,
and applies the requested paragraph styling across that range.

### Surface

```bash
desk docs paragraph-style <id> --all --space-below 8
desk docs paragraph-style <id> --all --line-spacing 150 --tab "Notes"
```

### Behavior

- **`--all` makes `--start` and `--end` optional.** They are not required
  when `--all` is set. They are an error when `--all` is set (mutually
  exclusive — see below).
- **Scope is the *tab's* body**, not all tabs. If `--tab X` is passed,
  `--all` applies to tab X's body. Otherwise, it applies to the default
  tab. This matches every other `docs` command's tab-scoping behavior.
- **Implementation** is one extra `documents.get` to find the last
  element's `endIndex`, then the existing `updateParagraphStyle` request
  over `(1, end_index - 1)` — the same range computation already in use
  by `write_markdown(replace=True)` at `services/docs.py:822`.
- **Empty-document handling**: if the doc has no content (only the
  trailing newline at index 1), the computed range is `(1, 1)` —
  zero-width. The command emits a receipt with a `"note": "document is
  empty"` field and exits 0 without sending a `batchUpdate`. No API call
  for the actual style update is made.

### Mutual exclusion

`--all` cannot be combined with `--start` or `--end`. Passing them
together returns `INVALID_INPUT` with a suggestion to drop one or the
other. We prefer fail-loud over silently choosing a winner — both forms
express different intents and combining them is almost certainly a
mistake.

### One flag, not two

The idea sketched both `--all` and `--end-of-doc`. We pick `--all`:
shorter, Unix-conventional ("operate on all of it"), and avoids
implying that the command starts somewhere other than the doc's
beginning. `--end-of-doc` would be needed only if there were also a
`--from-cursor` mode; we have no such concept.

### Out of scope

- `--all` on `desk docs style` (text styling), `delete-range`, or other
  range-based commands. Could add later if real usage shows the same
  retrofit pattern; for now this is the only command with a documented
  pain point.
- Multi-tab "all body across every tab" mode. Out of scope; doc-wide
  styling typically targets one tab.
- Updating named-style definitions. The Google Docs API does not expose
  that, as
  [ADR-017](017-paragraph-spacing-and-named-styles.md) records.

## Alternatives Considered

### Alternative 1: Two flags — `--all` and `--end-of-doc`

**Description**: Idea 048 sketched both. `--all` for the whole body,
`--end-of-doc` as a sentinel value for `--end`.

**Pros**:
- `--end-of-doc` composes with explicit `--start N`, letting callers
  style "from index 50 to the end" without computing the end.

**Cons**:
- Two flags for what is functionally one feature ("compute the end for
  me").
- `--end-of-doc` as a sentinel-value pattern conflicts with `--end`'s
  integer type — would require a string union or a separate flag like
  `--end-eof`. Either is awkward.
- Real-usage hit is the "from 1 to end" case, not "from 50 to end."

**Why rejected**: One flag covers the actually-observed pain point.
Defer the partial-range variant until somebody asks for it.

### Alternative 2: Make `--start`/`--end` default to whole-doc when omitted

**Description**: Drop both `required=True`; treat their absence as
"whole document."

**Pros**:
- No new flag.

**Cons**:
- Silent default: agents that forget to pass `--end` would suddenly
  restyle the entire document instead of failing.
- Breaks backward compatibility — existing scripts that mistakenly omit
  `--end` would gain new behavior overnight.
- Makes the intent ambiguous in `--help`.

**Why rejected**: Implicit defaults for destructive-ish operations are
agent-hostile. `--all` is explicit and discoverable.

### Alternative 3: Service-side convenience method, no CLI flag

**Description**: Expose `client.paragraph_style_doc_wide(...)` on the
service layer; let callers (or future commands) opt in to it
programmatically. Keep the CLI's `--start`/`--end` requirement.

**Pros**:
- Keeps CLI surface minimal.

**Cons**:
- Does not solve the user-facing pain. The pain is on the CLI, not in
  Python callers (of whom there are zero).
- Half-fix.

**Why rejected**: The point is to fix the CLI workflow. A
service-only method ships nothing the user can use.

## Consequences

### Positive

- **One-call retrofit.** `paragraph-style <id> --all --space-below 8` is
  the entire workflow.
- **Agent-friendly.** No JSON-parsing-of-`inspect`-output to derive the
  end index.
- **Predictable empty-doc behavior.** No-op with a structured note,
  rather than a Google API error or a silent zero-width update.
- **Matches existing tab semantics.** No new mental model.

### Negative

- **One extra API call** (`documents.get`) when `--all` is used.
  - *Mitigation*: that's the whole point of the flag — the alternative
    is forcing the caller to make that same call themselves, just less
    conveniently.
- **`--all` cannot specify `--start N --all`** ("from 50 to end").
  - *Mitigation*: rare in practice. The ADR's "Out of scope" notes a
    future deferral if real usage demands it.

### Neutral

- The `--all` semantic is "this tab's body" — consistent with every
  other tab-aware command.

## Implementation Notes

### Files affected

- `src/desk/services/docs.py`:
  - New public method `get_body_extent(document_id, tab_id=None) ->
    tuple[int, int]`. Returns `(1, end_index - 1)` for the target tab's
    body, or `(1, 1)` for an empty body. Encapsulates the
    `content[-1]["endIndex"]` pattern already in use four places in the
    file.
  - No change to `update_paragraph_style`. The command layer composes.

- `src/desk/commands/docs.py`:
  - `paragraph_style_cmd` gains a new `--all` flag.
  - `--start` and `--end` drop `required=True`. A validation block at
    the top of the command emits `INVALID_INPUT` if (`--all` and either
    of `--start`/`--end`) or (neither `--all` nor both
    `--start`/`--end`).
  - When `--all` is set, fetch `(start, end)` via
    `client.get_body_extent(document_id, tab_id)`. If the range is
    zero-width, emit a receipt with `"note": "document is empty"` and
    return.

- `tests/test_services/test_docs.py`:
  - `get_body_extent` over a doc with content returns the expected
    range.
  - `get_body_extent` over an empty doc returns `(1, 1)`.

- `tests/test_commands/test_docs.py`:
  - `paragraph-style --all --space-below 8` calls
    `update_paragraph_style` with computed indices.
  - `--all` + `--start` (or `--end`) → `INVALID_INPUT`.
  - Neither `--all` nor `--start`/`--end` → `INVALID_INPUT`.
  - `--all` on empty doc → receipt with `"note": "document is empty"`,
    exit 0, no batch update.

## References

- [Idea 048](../ideas/048-paragraph-style-doc-wide-convenience.md)
- [ADR-017](017-paragraph-spacing-and-named-styles.md) — explicitly
  deferred this convenience
- [ADR-006](006-query-based-bulk-operations.md) — "CLI handles
  orchestration, not the agent"
- [ADR-019](019-errors-to-stderr.md) — stream discipline for the
  INVALID_INPUT path
- [ADR-023](023-multi-calendar-query.md) — same INVALID_INPUT pattern
  for mutually-exclusive flag combinations
