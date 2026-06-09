---
id: 028
title: Slides Styling and Relative Layout (Phase 3a)
status: accepted
date: 2026-06-09
supersedes: []
superseded_by: null
tags: [slides, api, layout]
---

# ADR-028: Slides Styling and Relative Layout (Phase 3a)

## Context

ADR-026 staged Slides; Phases 1–2 shipped content CRUD and visual elements. Phase 3
(Idea 056) is styling & layout — the broadest, most edge-case-heavy slice. Rather than
attempt all of it (text styling, paragraph bullets, element fill/outline, transforms,
backgrounds, layouts, themes) at once, this ADR takes a **focused, high-value slice
(Phase 3a)** and defers the rest.

Two needs drive 3a:

1. **Styling.** Make text and elements look intentional: bold/italic/color/font on text,
   fill and outline on shapes and images. These map to well-understood Slides requests
   (`updateTextStyle`, `updateShapeProperties`, `updateImageProperties`).

2. **Layout without math.** This is the important one. Positioning elements by `--x/--y`
   in points (Phase 2) asks an agent to do geometry — exactly the kind of arithmetic LLMs
   are unreliable at and that produces overlapping or off-slide elements. The agent
   *knows* where it wants something ("top-right", "left half", "centered"); it shouldn't
   have to translate that into coordinates. We want the agent to describe layout in
   **relative terms** and have the command do the math internally, using the actual slide
   dimensions.

## Decision

### Styling commands

- **`desk slides style <id> <object-id>`** — text styling on a shape's text.
  Flags: `--bold/--no-bold`, `--italic/--no-italic`, `--underline/--no-underline`,
  `--font-size <pt>`, `--font <family>`, `--color <color>`. Applies to the whole shape's
  text by default; `--start/--end` narrow to a character range. (`updateTextStyle`.)

- **`desk slides format <id> <object-id>`** — element fill/outline.
  Flags: `--fill <color>`, `--outline <color>`, `--outline-weight <pt>`. Dispatches by
  element type: shapes get background fill + outline (`updateShapeProperties`); images get
  outline only (`updateImageProperties`). Table-cell styling is deferred.

**Color vocabulary.** `<color>` accepts a hex string (`#RRGGBB` or `#RGB`) **or** a theme
color name (`DARK1`, `LIGHT1`, `DARK2`, `LIGHT2`, `ACCENT1`–`ACCENT6`, `HYPERLINK`,
`FOLLOWED_HYPERLINK`). Hex maps to an `rgbColor` (0–1 channels); names map to `themeColor`.
Theme names let a deck stay on-palette without the agent knowing exact RGB.

### Relative layout

Introduce a **named-region vocabulary** that the agent uses instead of coordinates. A
region resolves to a concrete box (position + size in points) computed from the slide's
real `pageSize`, inside a margin, with a gutter between grid cells:

- 3×3 grid: `top-left`, `top`, `top-right`, `left`, `center`, `right`, `bottom-left`,
  `bottom`, `bottom-right`
- halves: `left-half`, `right-half`, `top-half`, `bottom-half`
- `full`

Wired in two places:

- **On insert** — `insert-image`/`insert-table`/`insert-shape` gain `--region <name>` as an
  alternative to `--x/--y/--width/--height`. The region supplies both position and size.
  `--region` and explicit coordinates are mutually exclusive.
- **On existing elements** — a new **`desk slides place <id> <object-id> --region <name>`**
  moves and fits an existing element into a region. It reads the element's current size and
  computes the transform internally (the agent never does the scaling math).

The geometry (margins, gutters, grid arithmetic, EMU↔PT conversion of `pageSize`) lives in
one helper; commands and agents only ever speak region names.

## Alternatives Considered

### Alternative 1: Coordinates only (status quo from Phase 2)

**Why rejected**: Forces agents into geometry they get wrong. The whole point of 3a's
layout work is to remove that. Coordinates remain available for precision, but are no
longer the only option.

### Alternative 2: A full grid/columns layout engine (e.g. CSS-grid-like specs)

**Description**: Let agents specify arbitrary grids, spans, flow, auto-packing.

**Why rejected**: Large design and implementation surface for speculative value. A fixed
region vocabulary covers the overwhelmingly common cases ("title top, chart right-half")
and can grow (thirds, quadrants) on demand without breaking callers.

### Alternative 3: Include transforms, backgrounds, layouts, bullets now

**Why rejected**: That's the rest of Idea 056 and multiplies API edge cases. Keeping 3a to
styling + relative layout keeps the change reviewable and verifiable. The remainder is
captured as Phase 3b.

## Consequences

### Positive

- Agents style text and elements with simple flags and an on-palette color vocabulary
- Layout is expressed the way an LLM reasons ("right-half"), with the math hidden
- `place` fixes the common "I added it, now move it where I meant" loop without geometry

### Negative

- Region boxes use fixed margins/gutters — not pixel-perfect for every design
  - *Mitigation*: explicit `--x/--y/--width/--height` remain for precision
- `place` reads the element to compute scale (an extra round-trip)
  - *Mitigation*: acceptable; it's a single get() and avoids agent math
- Table-cell styling and element transforms beyond place are deferred (Phase 3b)

### Neutral

- Region names are a small invented vocabulary, but they describe *layout intent*, not
  service operations — consistent with ADR-002's spirit (the alternative is raw geometry,
  which is worse for agents)

## Implementation Notes

- `src/desk/services/slides.py`: `style_text`, `format_element`, region helpers
  (`_page_size_pt`, `_region_box`), `place_element`; a `_parse_color` for hex/theme
- `src/desk/commands/slides.py`: `style`, `format`, `place` commands; `--region` on the
  three insert commands
- `agent.py`: reuse existing error codes (`INVALID_INPUT` for bad color/region)

## References

- [Slides API: updateTextStyle / updateShapeProperties / updateImageProperties](https://developers.google.com/slides/api/reference/rest/v1/presentations/request)
- ADR-026 (phasing), ADR-027 (visual elements / PT positioning)
- [Idea 056: Slides Phase 3 — Styling & Layout](../ideas/056-slides-styling-layout.md)
