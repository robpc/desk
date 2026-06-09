---
id: 055
title: Slides Phase 2 — Visual Elements
status: adr-created
effort: M
value: Agents can add images, tables, and shapes/text boxes to slides
created: 2026-06-09
updated: 2026-06-09
adr: docs/decisions/027-slides-visual-elements.md
---

# Idea 055: Slides Phase 2 — Visual Elements

## Problem

Phase 1 (Idea 054) gives agents text on slides via existing placeholders, but a real deck
needs images, tables, and free-standing shapes/text boxes. Without these, agents can edit
text but can't compose a slide's visual content from scratch.

## Sketch

Add element-creation commands to the `desk slides` group:

- `insert-image` — `createImage` from a public URL or Drive file ID, with optional
  position/size
- `insert-table` — `createTable` (rows × cols), addressable for later text insertion
- `insert-shape` / `insert-textbox` — `createShape` (text box, rectangle, etc.), so
  `insert-text` (Phase 1) can then target it
- `delete-object` already exists (Phase 1) and covers removal

Positioning uses the Slides transform model (EMU/point translate + scale). Provide
sensible defaults so agents can place an element without computing a transform, with
optional `--x/--y/--width/--height` flags.

## Open Questions

- [x] Image source → public URL only for now (mirrors `desk docs insert-image`). Drive
      file-ID resolution deferred (see follow-up below).
- [x] Position/size ergonomics → point-based `--x/--y/--width/--height`, all optional,
      with per-element defaults. Internally sent as `unit: PT`. (ADR-027)
- [x] Shape type surface → curated `--type` choice list, default `TEXT_BOX`. (ADR-027)
- [x] Text in a shape → `insert-shape --text` creates the shape and inserts text in one
      batchUpdate via a client-supplied objectId.
- [ ] Table cell text insertion — reuse `insert-text` with a cell-addressing scheme
      (`objectId` + row/col)? Still open; current `insert-text` targets shapes only.
- [ ] Follow-up: accept a Drive file ID as an image source (resolve to a fetchable URL).

## Value Signal

Tables and images are core to most real presentations. Depends on Phase 1's primitives
existing first.

## Effort Guess

M — Several create commands plus a usable positioning story. The transform/EMU model is
the main complexity driver.

## Notes

- Graduated to ADR-027
- Implemented on branch `feat/slides-support`: `insert_image`/`insert_table`/`insert_shape`
  in `services/slides.py` + commands; shared `_element_properties` PT helper. 11 unit tests.
- `insert-text` (Phase 1) is the consumer of shapes/tables created here
