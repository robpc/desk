---
id: 030
title: Slides Authoring Refinements + Scope Re-Auth UX (post-launch feedback)
status: accepted
date: 2026-06-09
supersedes: []
superseded_by: null
tags: [slides, auth, api]
---

# ADR-030: Slides Authoring Refinements + Scope Re-Auth UX (post-launch feedback)

## Context

Real-world testing of the Slides feature (an 11-slide deck build) surfaced concrete gaps
(Ideas 059–063). This ADR records the decisions for the clean, low-tension fixes; the
larger authoring-ergonomics question (Idea 061b–d) is deliberately deferred pending the
`add-slide` placeholder change below.

## Decision

### 1. Speaker notes (Idea 059) — new command `desk slides set-notes`

```
desk slides set-notes <presentation-id> <slide> "<text>" [--mode replace|append]
```

Resolves the slide's notes page via `slideProperties.notesPage.notesProperties.
speakerNotesObjectId` and inserts text there (replace clears existing first; append adds at
the end). `read` additionally surfaces each slide's notes text. Maps to a real Slides
concept — no invented vocabulary.

### 2. `add-slide` emits placeholder objectIds (Ideas 062, 061a)

After creating a slide, `add-slide` fetches the new slide and includes its placeholders
(`type` + `objectId`) in the result, so `--json` returns everything needed to fill the
slide. This removes the previously mandatory `inspect` round-trip between `add-slide` and
`insert-text`. (`--json` already prints regardless of `--quiet`; the gap was that only the
slide id, not its placeholders, was returned.)

### 3. Scope re-auth UX (Idea 060)

Two changes so a missing scope points at the real fix (`desk auth login`) instead of the
misleading "request access from the owner":

- **Reactive**: classify a 403 whose payload indicates insufficient scopes
  (`ACCESS_TOKEN_SCOPE_INSUFFICIENT` / "insufficient authentication scopes") as
  `INSUFFICIENT_SCOPES` (whose suggestions already say "run `desk auth login`") rather than
  `PERMISSION_DENIED`. A shared `is_scope_error()` helper lives in `agent.py`; wired into
  the Slides handler now, available for the other services to adopt.
- **Proactive**: `desk auth status` compares the token's granted scopes against
  `config.SCOPES` and reports `missing_scopes`, telling the user to re-auth — caught before
  any API call. `auth status --verify` also now exercises Slides (and Forms).

### 4. Section layout placeholders (Idea 063) — documentation

`SECTION_HEADER` exposing only a title matches Google's layout, not a Desk bug.
`SECTION_TITLE_AND_DESCRIPTION` (already exposed) provides the description placeholder for a
tagline. Resolution is documentation in `add-slide --help`, not code — verified against the
API.

## Alternatives Considered

- **Reclassify scope errors across all services at once** — correct eventually, but a
  larger change touching every command module. We add the shared helper now and wire Slides
  (where it was reported); rolling it out elsewhere is a tracked follow-up, not a blocker.
- **`placeholderIdMappings` on createSlide** (assign deterministic placeholder ids up front)
  instead of a post-create fetch — cleaner in theory but requires knowing each layout's
  placeholder set; the post-create fetch is simpler and robust. Revisit if the extra get
  matters.
- **Inline `add-slide --title/--body`** (Idea 061b) — initially deferred, then **shipped**
  in this same change at the maintainer's request: `add-slide` accepts
  `--title/--subtitle/--body` and fills the matching layout placeholders at creation, so a
  populated slide is one call. A requested placeholder the layout lacks raises
  `INVALID_INPUT` and rolls back the just-created slide (no orphan). Filling text into
  arbitrary (non-layout) positions remains the job of `insert-text`/`insert-shape`. The
  batch/outline forms (061c/d, 057) stay parked under ADR-003.

## Consequences

### Positive
- Speaker notes — the #1 reported gap — are writable and readable.
- `add-slide` → `insert-text` with no `inspect` in between.
- Missing-scope failures tell the user to re-auth instead of sending them down a sharing
  rabbit hole; `auth status` flags scope drift proactively.

### Negative
- `add-slide` does one extra internal `get` to fetch placeholders (one fewer call than the
  agent's own `inspect`, so net positive).
- Scope-error reclassification is wired only into Slides for now (others unchanged until the
  follow-up).

### Neutral
- `set-notes` slightly grows the Slides command surface; it's a core content primitive.

## Implementation Notes

- `services/slides.py`: `set_notes`; `read` includes notes; `add_slide` returns placeholders.
- `commands/slides.py`: `set-notes` command; `add-slide` receipt includes placeholders.
- `agent.py`: `is_scope_error()` helper; Slides handler maps to `INSUFFICIENT_SCOPES`.
- `auth.py`: `get_auth_status` reports `missing_scopes`; `verify_service_access` adds slides
  (+forms). `cli.py`: `auth status` surfaces missing scopes.

## References

- ADR-026 (Slides), ADR-028 (styling/layout)
- Ideas 059, 060, 061, 062, 063
