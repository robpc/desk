---
id: "009"
title: Markdown-First Document Creation
status: accepted
date: 2026-02-19
supersedes: []
superseded_by: null
tags: [docs, markdown, agent-first]
---

# ADR-009: Markdown-First Document Creation

## Context

`desk docs create "Title" --body "content"` inserts content as plain text using `insertText`. Agents (and humans) almost always want markdown formatting — headings, bold, links, lists. Today this requires a two-step workflow:

1. `desk docs create "Title"` — create empty doc
2. `desk docs write-markdown <id> --file content.md --replace` — write formatted content

This friction means agents have to remember the two-step dance, and `--body` on `create` is effectively a footgun that inserts unformatted text when users expect formatting.

## Decision

Make markdown the default content format for `desk docs create`:

- **Content from `--body`, `--file`, or `--stdin` is processed as markdown by default**, using the same `write_markdown()` pipeline from ADR-008.
- **Add `--plain` flag** to opt into raw `insertText` behavior (the current default).
- **Add `--file` and `--stdin` options** to `create`, matching `write-markdown`'s interface, so agents can create a doc from a markdown file in one command.
- **When no content is provided**, create an empty doc (no change).

At the service layer, `DocsClient.create()` gains a `markdown: bool = True` parameter. When `markdown=True` and body is non-empty, it creates the doc then calls `self.write_markdown(doc_id, body, replace=True)`.

## Alternatives Considered

### Alternative 1: Keep plain text default, add `--markdown` flag

**Description**: Leave `--body` as plain text; add an explicit `--markdown` flag to opt in.

**Pros**:
- Backwards compatible — no behavior change for existing scripts

**Cons**:
- Agents will always forget to pass `--markdown` and get plain text
- The common case requires an extra flag, violating "make the right thing easy"

**Why rejected**: The overwhelming use case is markdown. Plain text is the exception, not the rule.

### Alternative 2: Auto-detect markdown vs plain text

**Description**: Heuristically detect whether content contains markdown syntax and choose formatting accordingly.

**Pros**:
- "Just works" for both cases

**Cons**:
- Unreliable — plain text that happens to contain `#` or `*` would get misformatted
- Surprising behavior — same command produces different results depending on content
- Agents can't predict what will happen

**Why rejected**: Predictable behavior trumps magic. Explicit `--plain` flag is clearer.

## Consequences

### Positive

- **One-command formatted doc creation**: `desk docs create "Title" --body "# Hello\n\n**Bold**"` just works
- **File-based creation**: `desk docs create "Report" --file report.md` in a single command
- **Agent-friendly**: The default does the right thing; no extra flags needed for the common case

### Negative

- **Breaking change for `--body`**: Existing scripts using `--body` with plain text will now get markdown processing
  - *Mitigation*: This is a young tool with few users. The `--plain` flag provides an escape hatch. The previous behavior was rarely what users actually wanted.

### Neutral

- `docs update` remains plain text — it's for append/prepend/replace operations where markdown processing would be surprising
- `docs write-markdown` is unchanged — still useful for writing to existing docs

## Implementation Notes

- `src/desk/services/docs.py` — `create()` gains `markdown` param
- `src/desk/commands/docs.py` — `create` command gains `--file`, `--stdin`, `--plain`
- Tests updated for new flags and markdown default
