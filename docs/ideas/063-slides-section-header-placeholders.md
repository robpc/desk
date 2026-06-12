---
id: 063
title: SECTION_HEADER tagline — layout coverage / discoverability
status: implemented
effort: S
value: A section slide with a tagline should be obvious, not require insert-shape
created: 2026-06-09
updated: 2026-06-09
adr: docs/decisions/030-slides-authoring-refinements-and-scope-ux.md
---

# Idea 063: SECTION_HEADER tagline — layout coverage / discoverability

## Problem

Adding a slide with `--layout SECTION_HEADER` yields only a `TITLE` placeholder — no
subtitle/body — so a section slide can't hold a tagline without dropping to
`insert-shape --region bottom` (which works, but isn't obvious). Reported from a real deck
build (2026-06-09).

> **Resolved (2026-06-09, ADR-030): documentation, not a bug.** Verified live —
> `SECTION_HEADER` exposes only `TITLE`; `SECTION_TITLE_AND_DESCRIPTION` exposes
> `TITLE` + `SUBTITLE` + `BODY`. `add-slide --help` now documents the layout→placeholder
> behavior and points to `SECTION_TITLE_AND_DESCRIPTION` for a tagline.

## Likely cause (to verify)

This very probably matches Google's actual layout, not a Desk mapping bug — `SECTION_HEADER`
is title-only by design. Desk already exposes **`SECTION_TITLE_AND_DESCRIPTION`**, which has
a description placeholder — i.e. the right layout for "section + tagline" already exists; the
user reached for the wrong one. So this is most likely a **discoverability/documentation**
issue rather than a missing feature.

## Sketch

- Verify against the API which placeholders each predefined layout actually exposes
  (`presentations.pages.get` on a slide created with each layout).
- If confirmed: **document** the layout→placeholder map (which layouts give title only, vs
  title+body/subtitle/description), and point users at `SECTION_TITLE_AND_DESCRIPTION` for a
  tagline. Surface it in `add-slide --help` / the layout choice docs.
- Fallback for title-only layouts: note `insert-shape --region bottom` as the intended path
  for extra text (it works well per the report).
- Only if a placeholder is genuinely missing that Google's layout *should* provide would this
  become a real fix rather than docs.

## Open Questions

- [ ] Confirm empirically: does `SECTION_TITLE_AND_DESCRIPTION` expose a usable description
      placeholder via `insert-text`? (Almost certainly yes.)
- [ ] Best place to surface the layout→placeholder guidance (help text, a `layouts`
      sub-listing, or docs)?

## Value Signal

Real build friction: user wanted a section tagline and had to improvise. Likely solvable by
documentation pointing at an already-supported layout.

## Effort Guess

S — Mostly verification + documentation; code change only if a real placeholder gap exists.

## Notes

- Related: [[slides-phased-rollout]]; layouts are enumerated in `PREDEFINED_LAYOUTS`.
