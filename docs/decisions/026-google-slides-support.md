---
id: 026
title: Google Slides Support
status: proposed
date: 2026-06-09
supersedes: []
superseded_by: null
tags: [slides, api, new-service]
---

# ADR-026: Google Slides Support

## Context

Desk supports Gmail, Drive, Sheets, Docs, Calendar, and Forms. Google Slides is the
remaining core Workspace editor with no Desk coverage. Agents building workflows around
decks — drafting a presentation from notes, updating an existing deck, reading slide
content to summarize or reformat it — currently have no path through Desk.

The Slides API (v1) is a `batchUpdate`-style API, structurally very close to the Docs API
that Desk already implements (ADR-008). A presentation is a list of pages (slides); each
page holds page elements (shapes, images, tables, lines); text lives inside shapes and
table cells. Mutations are expressed as request objects (`createSlide`, `deleteObject`,
`insertText`, `replaceAllText`, …) addressed by stable `objectId`s. This is the same
inspect-indices-then-mutate model Desk's Docs commands already expose, so there is a
working reference implementation to lean on.

Two forces shape this decision:

1. **Surface area.** The Slides API is broad — slides, text, images, tables, shapes,
   styling, transforms, layouts, masters, themes. Shipping all of it at once would be a
   large, hard-to-review change, and much of the styling surface is low-value for agents
   relative to its complexity. We need a way to land useful capability early without
   committing to the whole API up front.
2. **Agent ergonomics.** Slides has no markdown or outline concept. To put content on a
   slide an agent must create shapes and insert text by `objectId`. The primitives are
   awkward to compose blind; agents need a `read`/`inspect` path to discover object IDs
   before mutating, mirroring how `desk docs inspect` works.

## Decision

Add Google Slides as a new Desk service, delivered in **phases**. This ADR covers the
decision to add the service and the **Phase 1 command set**; later phases are captured as
ideas and will graduate via their own ADRs (or amendments to this one) as we reach them.

### Phasing strategy

- **Phase 1 — Content CRUD** (this ADR; Idea 054). Read, inspect, and structural
  create/delete/edit of slides and text. This is the foundation everything else builds on
  and the layer agents most need first.
- **Phase 2 — Visual elements** (Idea 055). Images, tables, and shapes/text boxes.
- **Phase 3 — Styling & layout** (Idea 056). Text and paragraph styling, element fill/
  outline/transform, backgrounds, layouts.
- **Phase 4 — Outline-first authoring** (Idea 057). A higher-level `write-markdown`/
  outline command that generates a deck from structured text, parallel to
  `desk docs write-markdown`.

Each phase is additive and non-breaking. We can stop after any phase if demand doesn't
justify the next.

### Phase 1 commands

- **`desk slides create`** — Create a new presentation (with title)
- **`desk slides read`** — Read presentation content: slides in order, with the text of
  each shape/placeholder
- **`desk slides inspect`** — Show structure with `objectId`s: slides, page elements,
  placeholder types, and text insertion indices (parallel to `desk docs inspect`)
- **`desk slides add-slide`** — Add a slide, optionally with a predefined layout
  (e.g. `TITLE_AND_BODY`)
- **`desk slides delete-slide`** — Delete a slide (by `objectId` or 0-based index)
- **`desk slides insert-text`** — Insert text into a shape/placeholder by `objectId`
- **`desk slides replace-text`** — Find-and-replace text across the deck
  (`replaceAllText`)
- **`desk slides delete-object`** — Delete any page element by `objectId`
- **`desk slides export`** — Export as PDF/PPTX/TXT via Drive export

`duplicate-slide` (cheap template reuse) and `move-slide` (reorder via
`updateSlidesPosition`) are natural fast-follows within Phase 1 if the core lands cleanly,
but are not required for the phase to be useful.

All commands follow existing Desk patterns: structured errors, operation receipts,
`--json` output, and the `--quiet` flag (ADR-004, ADR-019).

### Scopes

One new OAuth scope is required:

- `https://www.googleapis.com/auth/presentations` — read/write presentations

Export uses the Drive scope Desk already holds. Users must re-authenticate once
(`desk auth login`) to pick up the new scope.

### API quirks anticipated

- **Object IDs.** Mutations address elements by `objectId`. Clients may supply their own
  IDs on create requests (useful for deterministic follow-up edits), or let the API
  assign them. Where we let agents target elements, the CLI uses `objectId`s, not
  positional indices, because indices shift as elements are added/removed — the same
  stability rationale as Forms item IDs (Idea 040). Slides may be addressed by index for
  convenience where unambiguous (e.g. `delete-slide`).
- **Text insertion needs a shape.** `insertText` targets an existing shape with a text
  body. A fresh blank slide's placeholders exist per its layout; `inspect` surfaces them
  so agents know what to target. Inserting text into arbitrary positions (new text boxes)
  is Phase 2 (`createShape` first).
- **Create ignores rich initial content.** As with Forms, `presentations.create` accepts
  little beyond a title; slides and content are added via `batchUpdate`. Expect a
  create-then-populate flow.

## Alternatives Considered

### Alternative 1: Ship the full Slides API at once

**Description**: One large change covering content, visual elements, styling, and layouts.

**Pros**:
- Complete API coverage in a single release
- No multi-phase coordination

**Cons**:
- Very large, hard-to-review change
- Much of the styling/transform surface is high-complexity, low-agent-value
- Delays any usable capability until everything is done

**Why rejected**: Phasing lands useful CRUD early and lets demand guide how far we push
into styling. Mirrors how Forms (ADR-007) and Docs editing (ADR-008) were staged.

### Alternative 2: Read-only Slides

**Description**: Only `read`/`inspect`/`export` — no mutations.

**Pros**:
- Smallest possible surface; no write scope risk
- Covers "summarize/extract from a deck" use cases

**Cons**:
- Agents can't build or fix decks — the more compelling workflows
- Inconsistent with every other Desk editor, which are read/write

**Why rejected**: The write path is what makes the service worth adding. Read-only would
leave the headline use case (drafting/editing decks) unserved.

### Alternative 3: Lead with outline/markdown-first authoring

**Description**: Make `write-markdown`-style deck generation the Phase 1 deliverable.

**Pros**:
- Highest-level, most ergonomic entry point for agents
- "Here's an outline, make a deck" is a common ask

**Cons**:
- Depends on the content-CRUD primitives underneath to exist and be solid first
- Bakes in layout/mapping opinions before we understand the primitives' edges
- Harder to verify incrementally

**Why rejected**: Authoring is the right *destination* (Phase 4) but the wrong *start*. It
should sit on top of proven primitives, not substitute for them.

## Consequences

### Positive

- Desk covers all of Google's core Workspace editors
- Agents can read, draft, and edit decks; export to PDF/PPTX/TXT
- Reuses the Docs inspect-then-mutate model — little new conceptual surface for users
- Phased delivery keeps each change reviewable and demand-driven

### Negative

- One new OAuth scope requires re-authentication for existing users
  - *Mitigation*: `desk auth login` handles it; call it out in release notes
- The Slides object model (shapes, placeholders, IDs) is less intuitive than Docs' linear
  text; `inspect` is essential and must be good
  - *Mitigation*: invest in clear `inspect` output before write commands

### Neutral

- Styling and visual elements are deferred — Phase 1 decks will be structurally complete
  but visually plain until later phases land

## Implementation Notes

- Service client: `src/desk/services/slides.py` — `build("slides", "v1", ...)`
- Commands: `src/desk/commands/slides.py`
- Scope added to `src/desk/config.py`
- Registered in `src/desk/cli.py` (`main.add_command(slides)` + capabilities dict entry)
- Error code (e.g. `PRESENTATION_NOT_FOUND`) added to `src/desk/agent.py`
- Export reuses the Drive export path already used by `desk docs export` (ADR-014)

## References

- [Google Slides API v1 documentation](https://developers.google.com/slides/api/reference/rest)
- [Idea 054: Slides Phase 1 — Content CRUD](../ideas/054-slides-content-crud.md)
- [Idea 055: Slides Phase 2 — Visual Elements](../ideas/055-slides-visual-elements.md)
- [Idea 056: Slides Phase 3 — Styling & Layout](../ideas/056-slides-styling-layout.md)
- [Idea 057: Slides Phase 4 — Outline-First Authoring](../ideas/057-slides-outline-authoring.md)
- ADR-007: Google Forms Support (new-service template; item-ID-over-index rationale)
- ADR-008: Expanded Docs Editing (inspect-then-mutate model this reuses)
- ADR-004: Agent-First CLI Design
