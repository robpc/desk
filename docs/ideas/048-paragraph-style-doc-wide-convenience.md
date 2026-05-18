---
id: "048"
title: Doc-wide range convenience for paragraph-style
status: adr-created
effort: S
value: Avoid making users compute end-of-doc indices when they want to apply paragraph styling across an entire document
created: 2026-04-29
updated: 2026-05-18
adr: docs/decisions/024-doc-wide-paragraph-style.md
---

# Idea 048: Doc-wide Range Convenience for `paragraph-style`

## Problem

`desk docs paragraph-style` requires explicit `--start` and `--end` indices. To apply spacing to a whole document — common in retrofit scenarios where `write-markdown` was already run without spacing flags — users have to read the doc first to find the end index, then pass it.

## Sketch

Add a flag (one of):

```bash
desk docs paragraph-style <id> --all --space-below 8
desk docs paragraph-style <id> --end-of-doc --space-below 8
```

The implementation reads the doc's body, finds the end index, and applies `updateParagraphStyle` over the full range. Adds one extra API call (`documents.get`).

## Open Questions

- [ ] Does "all" mean the body, the current tab, or all tabs? Default to the current tab's body to match the rest of the docs surface.
- [ ] Should `--all` be mutually exclusive with `--start`/`--end`, or should explicit indices win?
- [ ] One flag (`--all`) or two (`--all` and `--end-of-doc`)? Lean toward `--all`; shorter and matches Unix convention.

## Value Signal

Tied to ADR-017's deferred section. Trigger to graduate: users hitting the retrofit case enough that the recipe friction is observable. Until then, the current explicit-indices form is acceptable.

## Effort Guess

S — extra `documents.get` call, one new flag, validation for mutual exclusivity. Tests are small.

## Notes

- Deferred from ADR-017 (Paragraph Spacing Controls).
- Could also extend to `style` (text styling) and other range-based commands if the pattern proves useful.
