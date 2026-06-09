---
id: 027
title: Slides Visual Elements (Phase 2)
status: proposed
date: 2026-06-09
supersedes: []
superseded_by: null
tags: [slides, api]
---

# ADR-027: Slides Visual Elements (Phase 2)

## Context

ADR-026 added Google Slides as a phased service. Phase 1 (Idea 054) shipped content
CRUD: read, inspect, structural slide ops, and text into existing placeholders. Phase 2
(Idea 055) adds the visual building blocks a real deck needs — images, tables, and
free-standing shapes/text boxes.

Creating these elements forces a decision Phase 1 didn't: **how to express position and
size**. The Slides API places elements via an `elementProperties` object containing a
`size` (width/height dimensions) and an `transform` (an affine transform with translate +
scale). Dimensions and transforms accept a `unit` of either `EMU` (English Metric Units —
914400 per inch) or `PT` (points — 12700 EMU each). Agents composing a deck think in
human terms ("a 300pt-wide image near the top-left"), not EMU.

Two more choices fall out of element creation:

- **Image source.** `createImage` takes a `url` that must be publicly accessible. Whether
  to also accept Drive file IDs (which need resolving to a fetchable URL) is a scope
  question.
- **Shape vocabulary.** `createShape` requires a `shapeType` from a large enum. Exposing
  all of it is noise; agents overwhelmingly want text boxes and a few basic shapes.

## Decision

Add three commands to the `desk slides` group:

- **`desk slides insert-image <id> <slide>`** — `--url` (required), optional
  `--x/--y/--width/--height`
- **`desk slides insert-table <id> <slide>`** — `--rows`/`--cols` (required), optional
  `--x/--y/--width/--height`
- **`desk slides insert-shape <id> <slide>`** — `--type` (default `TEXT_BOX`), optional
  `--text`, optional `--x/--y/--width/--height`

`<slide>` accepts a 0-based index or a slide objectId, resolved by the same helper Phase 1
uses. Removal is already covered by `delete-object` (Phase 1).

### Positioning in points, with defaults

`--x/--y` set the element's top-left translate; `--width/--height` set its size. **All are
expressed in points (`PT`)**, and all are optional. When omitted, the command supplies a
sensible default (top-left-ish placement, a default size per element type) so an agent can
drop an element on a slide without doing any geometry. Internally we always send
`size` + `transform` with `unit: "PT"`.

Rationale: EMU is hostile to agents and to humans reading the command. Points map to how
people describe slide layouts, and the API accepts `PT` natively, so no conversion math is
needed on our side.

### Images: public URL only

`insert-image` accepts a public `--url`, mirroring `desk docs insert-image`. Drive file-ID
resolution is deferred — it adds a resolve step and permission edge cases for a
convenience we have no demand signal for yet. Captured as a follow-up in Idea 055.

### Shapes: curated type set, text in one batch

`--type` is a `click.Choice` of a curated subset (`TEXT_BOX`, `RECTANGLE`,
`ROUND_RECTANGLE`, `ELLIPSE`, `DIAMOND`, `CLOUD`, `ARROW`), defaulting to `TEXT_BOX` — the
overwhelmingly common case. When `--text` is supplied, the command sends `createShape`
with a client-supplied `objectId` followed by `insertText` against that id **in a single
batchUpdate**, so "add a labelled box" is one call, not two.

A dedicated `insert-textbox` command was considered but rejected: it's just
`insert-shape` with the default type, so it would duplicate surface for no gain.

## Alternatives Considered

### Alternative 1: EMU-native positioning

**Description**: Expose `--x/--y/--width/--height` in EMU, matching the API's base unit.

**Pros**:
- 1:1 with the API; no unit field to reason about

**Cons**:
- 914400 EMU/inch is meaningless to agents and humans
- Every caller would do conversion math, inviting errors

**Why rejected**: Points are the agent-friendly unit and the API accepts them directly.

### Alternative 2: Full shapeType enum

**Description**: Accept any of the ~150 Slides shape types.

**Pros**:
- Complete coverage

**Cons**:
- Overwhelming choice list; most are never used in agent workflows
- Harder to document and validate

**Why rejected**: A curated subset covers real use; more can be added on demand without a
breaking change.

### Alternative 3: Defer text-in-shape to a second call

**Description**: `insert-shape` only creates the shape; the agent then calls `insert-text`.

**Pros**:
- Simpler single-responsibility command

**Cons**:
- The agent must inspect to learn the new shape's objectId before it can add text — two
  round-trips and an inspect for the most common case (a labelled box)

**Why rejected**: Supplying a client objectId lets us do both in one batchUpdate. The
two-step path still exists for anyone who wants it (`insert-shape` then `insert-text`).

## Consequences

### Positive

- Agents can compose full slide content: images, tables, labelled shapes
- Positioning is expressible without EMU math; defaults make position optional
- "Add a box with text" is a single command/round-trip

### Negative

- Default placement may overlap existing elements (no collision avoidance)
  - *Mitigation*: agents can pass explicit `--x/--y`; `inspect` shows what's already there
- Image source limited to public URLs for now
  - *Mitigation*: documented; Drive-ID resolution captured as a follow-up

### Neutral

- Styling of these elements (fill, outline, font) remains Phase 3 (Idea 056); Phase 2
  elements inherit default/theme appearance

## Implementation Notes

- Extends `src/desk/services/slides.py` (`insert_image`, `insert_table`, `insert_shape`)
  and `src/desk/commands/slides.py`
- Shared `_element_properties(page_id, x, y, width, height, default_w, default_h)` helper
  builds the `size` + `transform` payload in `PT`
- Client-supplied objectId for `insert-shape --text` generated locally (uuid-derived,
  matching the API's `[a-zA-Z0-9_-]{5,50}` constraint)

## References

- [Slides API: pages.elementProperties / transforms](https://developers.google.com/slides/api/reference/rest/v1/presentations.pages)
- ADR-026: Google Slides Support (phasing + Phase 1)
- [Idea 055: Slides Phase 2 — Visual Elements](../ideas/055-slides-visual-elements.md)
