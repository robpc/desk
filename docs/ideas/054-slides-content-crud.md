---
id: 054
title: Slides Phase 1 — Content CRUD
status: adr-created
effort: M
value: Agents can read, draft, and edit Google Slides decks — the foundational layer
created: 2026-06-09
updated: 2026-06-09
adr: docs/decisions/026-google-slides-support.md
---

# Idea 054: Slides Phase 1 — Content CRUD

## Problem

Desk covers every core Workspace editor except Slides. Agents can't read a deck to
summarize it, can't draft a presentation from notes, and can't fix or restructure an
existing one. The Slides API is a `batchUpdate` API structurally close to Docs, so the
inspect-then-mutate model Desk already uses applies directly — but none of it is wired up.

## Sketch

Add a `desk slides` command group with the Phase 1 set from ADR-026:

- `create` — new presentation (title)
- `read` — slides in order, with each shape/placeholder's text
- `inspect` — structure with `objectId`s, placeholder types, text indices
- `add-slide` — add a slide, optional predefined layout
- `delete-slide` — delete by `objectId` or 0-based index
- `insert-text` — insert text into a shape/placeholder by `objectId`
- `replace-text` — find-and-replace across the deck (`replaceAllText`)
- `delete-object` — delete any page element by `objectId`
- `export` — PDF/PPTX/TXT via Drive export

Service client at `src/desk/services/slides.py` (`build("slides", "v1", ...)`), commands at
`src/desk/commands/slides.py`, scope + registration + capabilities entry per ADR-026.

`duplicate-slide` and `move-slide` (reorder) are fast-follows within this phase if the core
lands cleanly.

## Open Questions

- [x] `add-slide` layout handling → predefined-layout enum (`--layout`, choices from
      `PREDEFINED_LAYOUTS`), default `TITLE_AND_BODY`.
- [x] `delete-slide` addressing → supports both. All-digit arg = 0-based index (resolved
      against deck order); otherwise treated as objectId. `delete-object` is objectId-only.
- [x] `insert-text` → takes `--at` (0-based char index, default 0); appends into the shape.
- [x] `read` text extraction → flattened to plain text per slide; tables rendered as
      `cell | cell` rows.
- [x] One scope (`auth/presentations`) covers create + batchUpdate + get. ✓
- [x] Live-verified end-to-end against the API (all 11 commands; create/add-slide/
      inspect/insert-text/replace-text/read/duplicate/move/delete-object/delete-slide/
      export). Export needed a fix: `files().export` rejects `supportsAllDrives`.

## Value Signal

Completes Desk's coverage of Google's core editors. "Summarize this deck" and "draft a
deck from these notes" are common agent asks with no current path.

## Effort Guess

M — New service client + ~9 commands, but the inspect-then-mutate pattern and Drive-based
export are both already proven in the Docs commands. Mostly adaptation, not invention.

## Notes

- Graduated to ADR-026
- Phases 2–4 captured as Ideas 055–057
- Reuses the Docs `inspect`/`export` model (ADR-008, ADR-014)
- Implemented on branch `feat/slides-support`: `services/slides.py`,
  `commands/slides.py`, scope in `config.py`, `PRESENTATION_NOT_FOUND` in `agent.py`,
  registration + capabilities in `cli.py`. 11 commands; 34 unit tests.
- Setup prerequisite discovered during verification: the Slides API must be enabled in
  the user's Google Cloud project, and `desk auth login` re-run for the new scope.
