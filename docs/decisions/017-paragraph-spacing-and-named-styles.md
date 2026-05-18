---
id: "017"
title: Paragraph Spacing Controls
status: accepted
date: 2026-04-29
supersedes: []
superseded_by: null
tags: [docs, editing, agent-first, styling]
---

# ADR-017: Paragraph Spacing Controls

## Context

`desk docs write-markdown` produces tight, wall-of-text output because Google Docs' default `NORMAL_TEXT.spaceBelow` is 0pt. PR #51 proposed to fix this by automatically emitting `updateParagraphStyle` with `spaceBelow: 8pt` for every body paragraph during markdown conversion.

That fix has two problems:

1. **It overrides documents that have custom paragraph styling.** Explicit per-paragraph `spaceBelow` beats any value inherited from `NORMAL_TEXT`. A user who has configured a template with 12pt spacing would have it silently clobbered to 8pt every time they ran `write-markdown`.
2. **The converter currently respects inheritance, and that's the right behavior.** For body paragraphs, the converter emits no `updateParagraphStyle` request at all — paragraphs inherit `NORMAL_TEXT`. The "bug" is that Google's default `NORMAL_TEXT.spaceBelow` is 0pt; the converter is doing the correct thing by not overriding it.

This is an expectation gap, not a bug in the converter. Markdown-rendering tools elsewhere (browsers, GitHub) display body paragraphs with spacing because their default body styles configure it. The correct fix is to give Desk users the ability to configure their documents the same way — not to bake an opinion into the converter.

ADR-008 explicitly deferred extended paragraph styles (line spacing, space before/after, indentation). This ADR delivers them.

### Discovery during implementation

The original draft of this ADR proposed a second command, `desk docs named-style`, to configure a document's `NORMAL_TEXT` / `HEADING_N` named-style defaults once per document. Verification against the cached `docs.v1` discovery document (`googleapiclient/discovery_cache/documents/docs.v1.json`) confirmed that **the Google Docs API does not expose any public request to update named-style definitions.** The full Request union has no `updateNamedStyle` or equivalent; `DocumentStyle` covers page-level fields only (margins, page size, headers/footers). The only API-available path to changing paragraph spacing is `updateParagraphStyle` over an explicit range, which sets explicit per-paragraph styling that overrides the inherited named style.

This finding eliminates the named-style approach. The decision below is scoped accordingly.

## Decision

Two complementary additions, both backed by `updateParagraphStyle` (the only API request available for paragraph spacing):

### 1. Extend `desk docs paragraph-style` with per-range spacing flags

The command already takes `--start`, `--end`, `--heading`, and `--alignment`. Add:

- `--space-above N` — points (integer) above the paragraph
- `--space-below N` — points (integer) below the paragraph
- `--line-spacing N` — line spacing as integer percentage (Google's native unit: `100` = single, `115` = 1.15x, `150` = 1.5x, `200` = double)
- `--indent-start N` — left indent in points
- `--indent-end N` — right indent in points
- `--indent-first-line N` — first-line indent in points

All flags are optional and additive. The service method (`update_paragraph_style`) gains corresponding parameters and only includes a field in the `updateParagraphStyle.fields` mask if the caller passed it.

### 2. Add the same spacing flags to `desk docs write-markdown` as opt-in styling

When the user passes any spacing/indent flag to `write-markdown`, the markdown converter emits per-paragraph `updateParagraphStyle` requests for **body paragraphs only** — headings, list items, and fenced code blocks are excluded so their named-style spacing (or the user's explicit list/code styling) is preserved. With no flag, the converter behaves as before and inherits the document's named styles unchanged.

This recovers the ergonomic case raised by a contributor (markdown rendering with visible body spacing) without baking an opinion into the converter: the user explicitly opts in per write, gets exactly what they asked for, and gets nothing if they don't ask. It supersedes PR #51's always-on approach.

The implementation lives in the converter (annotation pass) rather than as a post-pass at the service layer, so we can selectively skip headings/lists/code rather than blindly applying spacing to every paragraph in the inserted range.

Do **not** add a `named-style` command — the underlying API does not support it.

### Unit conventions

- **Spacing and indentation**: integer points. `--space-below 8` → `{ "magnitude": 8, "unit": "PT" }`. Matches the existing `--font-size` flag's integer convention. We don't accept "8pt" or "8px" strings; if multi-unit support becomes a need, we revisit.
- **Line spacing**: integer percentage. `--line-spacing 115` → `lineSpacing: 115`. Matches Google's API field directly; documented in `--help`.
- **Validation**: reject negative spacing values; reject `--line-spacing < 50` (Google's effective floor).

### User recipe for "default body spacing"

For the originating use case ("I want my markdown-rendered doc to have visible body paragraph spacing by default"), the recipe is a single command:

```bash
desk docs write-markdown <id> --file content.md --space-below 8
```

For retrofitting an existing document or adjusting specific ranges, `paragraph-style` provides the same spacing flags scoped to a `--start`/`--end` range.

## Alternatives Considered

### Alternative 1: Hardcode 8pt below body paragraphs in the converter (PR #51 approach)

**Description**: Emit `updateParagraphStyle` with `spaceBelow: 8pt` for every body paragraph during markdown conversion, skipping headings, lists, and code blocks.

**Pros**:
- Zero-config: matches user expectation for default-styled docs out of the box
- No new commands needed

**Cons**:
- Silently overrides custom paragraph styling on existing documents
- Bakes a rendering opinion into the converter, conflicting with ADR-003 (toolkit, not productivity app)
- Encodes a single magic number (8pt) with no escape hatch short of post-processing
- Doesn't fix the actual root cause (the doc's `NORMAL_TEXT` configuration)

**Why rejected**: The converter currently inherits document style correctly. We should not break that property. Users who want default markdown-style spacing apply it explicitly via `paragraph-style` (and, if needed, re-apply after writing).

### Alternative 2: Have `write-markdown` mutate the doc's named style as a side effect

**Description**: When `write-markdown` runs, automatically issue a request to set `NORMAL_TEXT.spaceBelow` to 8pt if it's currently 0pt.

**Why rejected**: The Google Docs API does not expose a request to update named-style definitions. This option is not implementable.

### Alternative 3: New `desk docs named-style` command for document-level configuration

**Description**: A new command that configures the doc's `NORMAL_TEXT` / `HEADING_N` named-style spacing in a single `updateNamedStyle` request, affecting all current and future paragraphs of that style.

**Why rejected**: The Google Docs API does not expose `updateNamedStyle` (verified against `docs.v1` discovery). We cannot implement this.

### Alternative 4: Multi-unit string parsing (`8pt`, `0.5in`, etc.)

**Description**: Accept unit suffixes on spacing flags and parse them into the appropriate `Dimension` object.

**Pros**:
- More expressive; matches CSS/Word conventions

**Cons**:
- More parsing surface, more validation, more error paths
- Existing flags (`--font-size`) use plain integers; introducing a different convention here is inconsistent
- Points are the canonical Google Docs unit — rare for a user to need anything else

**Why rejected**: Consistency with `--font-size` and YAGNI. We can add unit suffixes later without breaking integer callers.

## Consequences

### Positive

- **Closes ADR-008's deferred work** on extended paragraph styles
- **Preserves the converter's correct inheritance behavior** — `write-markdown` still respects whatever named-style configuration the doc has
- **Fits Google's API surface directly** — `paragraph-style` is a thin wrapper over `updateParagraphStyle`, no invented vocabulary (ADR-002)

### Negative

- **No one-shot doc-level spacing config**: users cannot configure `NORMAL_TEXT.spaceBelow` once and have it apply forever. Every `write-markdown` invocation that wants body spacing must pass the relevant flag. This is a Google API limitation, not a Desk choice — there is no public request to update named-style definitions.
  - *Mitigation*: the opt-in flags on `write-markdown` make this a one-flag-per-invocation cost, not a separate command.
- **Spacing applied this way is explicit per-paragraph styling, not inherited.** Future paragraphs added through other commands (e.g. `docs insert`) won't pick it up unless they also opt in.
  - *Mitigation*: documented in `--help`. If users hit this gap, we revisit by either reading the doc to retro-apply spacing or shipping the deferred `--all` convenience.

### Neutral

- PR #51's converter changes are not merged. The bug fix it tried to deliver is replaced by a user-controlled lever.
- No new OAuth scopes; uses existing `documents` scope.

## Deferred

- A `--all` or `--end-of-doc` convenience on `paragraph-style` to target the entire document without computing the end index. Useful for retrofitting docs that were written without spacing flags. Tracked as Idea 048; revisit if users frequently hit the retrofit case.

## Implementation Notes

- `src/desk/services/docs.py`:
  - Extend `update_paragraph_style()` with `space_above`, `space_below`, `line_spacing`, `indent_start`, `indent_end`, `indent_first_line` parameters.
  - New helper `_build_paragraph_style_fields` keeps spacing/indent translation in one place.
  - Plumb the same parameters through `write_markdown()` so the converter can emit per-paragraph styling.
- `src/desk/services/markdown_to_docs.py`:
  - `MarkdownConverter` accepts a body-paragraph style config. When set, `paragraph_open`/`paragraph_close` emit a `paragraph_style` annotation only when the paragraph is *not* inside a list item, code block, or heading. The annotation translates to a single `updateParagraphStyle` request via existing annotation plumbing.
- `src/desk/commands/docs.py`:
  - Add the new flags to `paragraph_style_cmd` and `write_markdown_cmd` and pass them through.
  - Validate negative values and minimum line-spacing percentage at the service layer; surface as `INVALID_INPUT` at the CLI layer.
- `tests/`:
  - Unit tests for the service method covering field-mask construction, unit conversion, and validation errors.
  - Converter tests for opt-in spacing emission (body paragraphs only, headings/lists/code excluded).
  - CLI tests covering happy paths and validation failures on both commands.

## References

- ADR-002: No Invented Vocabulary
- ADR-003: Unified Workspace CLI (toolkit, not productivity app)
- ADR-004: Agent-First CLI Design
- ADR-008: Expanded Docs Editing — explicitly deferred extended paragraph styles
- Idea 047: Paragraph Spacing Controls
- PR #51: superseded by this ADR
- [Google Docs API: updateParagraphStyle](https://developers.google.com/docs/api/reference/rest/v1/documents/request#updateparagraphstylerequest)
- [Google Docs v1 discovery doc](https://docs.googleapis.com/$discovery/rest?version=v1) — confirms no `updateNamedStyle` request exists
