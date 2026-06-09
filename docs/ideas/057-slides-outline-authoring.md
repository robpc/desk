---
id: 057
title: Slides Phase 4 — Outline-First Authoring
status: questioned
effort: L
value: Agents generate a whole deck from a markdown/outline in one command
created: 2026-06-09
updated: 2026-06-09
adr: null
---

> **Open question on whether to build this at all (2026-06-09).** This is the most
> workflow-encoding of the Slides phases and sits closest to the line ADR-003 draws
> against pre-built workflows: with Phases 1–3a in place, an agent can already compose a
> deck from primitives (`add-slide` + `insert-text`/`insert-shape` + `--region`). A
> single `write-markdown`/`from-outline` command risks becoming the opinionated "make me
> a deck" shortcut ADR-003 warns against. Parked pending a decision that the convenience
> clearly outweighs that concern. Prefer investing in layout primitives (Phase 3b) first.

# Idea 057: Slides Phase 4 — Outline-First Authoring

## Problem

The Slides primitives (Phases 1–3) require an agent to think in shapes, `objectId`s, and
`batchUpdate` requests — awkward for the common ask "here's an outline, make me a deck."
This is the slide analog of the gap `desk docs write-markdown` closed for documents: a
high-level entry point that maps structured text to native Slides structure. It's also the
part that's hardest for an agent to assemble correctly from primitives, so it earns a
dedicated convenience command — once the primitives exist to build on.

## Sketch

Add a high-level authoring command:

- `write-markdown` / `from-outline` — take a markdown outline and generate slides:
  - top-level headings (`#`) → new slides with a title placeholder
  - bullet lists → body content on the current slide
  - a slide separator (`---` or `##`) → slide boundary
  - optional speaker notes from a designated block

Built entirely on Phase 1–2 primitives (`add-slide`, `insert-text`, maybe `insert-image`),
so it adds mapping logic rather than new API plumbing.

## Open Questions

- [ ] Outline dialect — reuse the `docs write-markdown` conventions where they map, or
      define a slide-specific mapping (heading levels → slide vs. bullet)?
- [ ] Layout selection — infer from content (title-only vs. title+body), or take a flag?
- [ ] Does this respect ADR-002 (no invented vocabulary)? `write-markdown` already exists
      for Docs, so the pattern is established — but confirm the mapping doesn't encode a
      workflow opinion that belongs in the agent (ADR-003).
- [ ] Speaker notes — in scope for v1 of this command, or follow-up?
- [ ] Idempotency / update-in-place vs. always-append (Idea 033 considerations)?

## Value Signal

This is the most ergonomic entry point and likely the most-used once it exists — "make a
deck from this" is a frequent agent ask. It's deliberately last because it should sit on
proven primitives, not substitute for them (see ADR-026, Alternative 3).

## Effort Guess

L — The plumbing is reused from earlier phases, but the outline→Slides mapping has many
edge cases (nesting, mixed content, layout inference, notes) and needs careful design to
avoid baking in opinions. Warrants its own ADR.

## Notes

- Follows Ideas 054–056; depends on their primitives
- Parallels `desk docs write-markdown` (ADR-009: markdown-first create)
- Must stay on the right side of ADR-002 / ADR-003 (vocabulary, no pre-built workflows)
