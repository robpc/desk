---
id: "047"
title: Paragraph Spacing Controls
status: implemented
effort: M
value: Give agents and humans direct control over paragraph spacing, line spacing, and indentation — instead of encoding opinions in the markdown converter
created: 2026-04-29
updated: 2026-05-18
adr: 017
---

# Idea 047: Paragraph Spacing Controls

## Problem

`desk docs write-markdown` produces visually tight output because Google Docs' default `NORMAL_TEXT` named style has `spaceBelow: 0pt`. PR #51 attempted to fix this by automatically emitting a per-paragraph `spaceBelow: 8pt` request for every body paragraph in the markdown converter. That fix:

- **Overrides any custom paragraph styling the document already has** — if a user (or template) configured `NORMAL_TEXT.spaceBelow: 12pt`, our hardcoded 8pt wins because explicit per-paragraph styling beats inherited named-style values.
- **Encodes a rendering opinion in the converter**, contrary to ADR-003 ("toolkit, not productivity app").
- **Doesn't fix the root cause** — the bug surfaced because the doc was at the Google default of 0pt, which means the converter is already correctly inheriting from `NORMAL_TEXT`. The expectation gap is that markdown rendering should *look* spaced, but that's a per-doc styling choice, not converter logic.

The right move is to expose the spacing primitives that Google's API provides, so users and agents can configure spacing where it belongs.

## Sketch

Two complementary changes, both backed by `updateParagraphStyle`:

1. **Per-range** — extend `desk docs paragraph-style` with spacing/line-height/indent flags:

   ```bash
   desk docs paragraph-style <id> --start 50 --end 200 --space-below 12
   desk docs paragraph-style <id> --start 1 --end 999 --line-spacing 150
   ```

2. **Per-write** — same flags on `desk docs write-markdown`, opt-in. When passed, the converter emits explicit `updateParagraphStyle` for body paragraphs only (skips headings, list items, code blocks):

   ```bash
   desk docs write-markdown <id> --file content.md --space-below 8
   ```

   Without the flags, `write-markdown` behaves as before — paragraphs inherit the doc's named styles.

## Open Questions

- [x] Unit handling: integer points (matches existing `--font-size` style, simplest) — see ADR-017
- [x] Line-spacing format: integer percentage matching Google's API (`100` = 1.0x, `150` = 1.5x) — see ADR-017
- [x] Should there also be a `named-style` command for doc-level defaults? — **Cannot:** verified against Google Docs v1 discovery doc that `updateNamedStyle` is not a public API request. The only API-available path is per-range `updateParagraphStyle`. See ADR-017 for details.
- [x] Should `write-markdown` accept the same spacing flags? — Yes, opt-in. See ADR-017.
- [ ] Follow-up: `--all` / `--end-of-doc` convenience on `paragraph-style` to avoid computing the end index manually. Captured as Idea 048.

## Value Signal

- Direct trigger: PR #51 and the conversation deciding not to merge it.
- Broader signal: ADR-008 explicitly deferred "Extended paragraph styles: Alignment, line spacing, space before/after, indentation" — this idea closes that gap.
- Agent-first framing: agents producing structured docs need the ability to fine-tune section spacing without nuking existing formatting.

## Effort Guess

S — single service method extension, single CLI command extension, tests. Maps to a single `batchUpdate` request.

## Notes

- Related: ADR-008 (Expanded Docs Editing) deferred this; ADR-017 graduates it.
- Related: PR #51 — closed in favor of this approach. See PR #51 comment for the decision trail.
- Google API references: `updateParagraphStyle`, `paragraphStyle.spaceAbove/spaceBelow/lineSpacing/indentStart/indentEnd/indentFirstLine`.
- Implementation surfaced an API limitation worth recording: Google Docs' public batch API does **not** expose any way to update named-style definitions (`updateNamedStyle` is not in the discovery document, despite being plausible). All paragraph spacing must be applied as explicit per-paragraph styling.
